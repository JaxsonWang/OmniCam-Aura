// GR port, native half.
//
// The GR mode reuses the professional (master) capture pipeline. GR frames are recognised by the
// gr_effect_size APS setting (63) and get:
//   * BasicTone: the GR LMT/SC/CWCM tree (staged by service.sh) instead of the host ODM tree;
//   * no artistic vignette from the V1 vignette parameters;
//   * the Meishe V1 filter node (clarity, vignette, grain), run with the GR capture mode.
// 偏移对应模块随附的 libAlgoInterface.so / libBasicTonePhotoX9.so；
// PLK110 的原厂 libAlgoInterface 与该库使用相同布局，设备检查位于 native_entry.cpp。
#include <android/log.h>
#include <atomic>
#include <cstdint>
#include <cstring>
#include <dlfcn.h>
#include <mutex>
#include <string>
#include <sys/system_properties.h>
#include <unordered_map>

#include "native_hooks.h"

namespace {

constexpr char kTag[] = "RicohGrPort";
constexpr char kGrLmtPath[] = "/data/user/0/com.oplus.camera/files/ricoh_gr/lmt";
constexpr char kHostLmtPath[] = "/odm/etc/camera/basictone/lmt";
constexpr uint32_t kGrCaptureMode = 37;
constexpr int kMasterCaptureMode = 33;
constexpr uintptr_t kCaptureDecisionFactoryOffset = 0x20ee21c;

// APS setting keys use libc++'s 24-byte short-string layout on this firmware.
struct alignas(8) SettingKey {
    uint8_t length;
    char text[23];
};
const SettingKey kGrSizeKey = {28, "gr_effect_size"};

int (*getSettingInt)(void *settings, const void *key, int fallback);
void (*originalGetLmtParams)(void *, void *, int);
void (*originalGetVigParams)(void *, void *, void *);
int (*originalFilterProcessV2)(void *, int);
int (*filterProcessV1)(void *, int);
int (*filterRegisterV1)(void *, int);
int (*filterUnregisterV1)(void *, int);
uintptr_t (*originalProcessCore)(void *, void *, void *, void *, void *);
uintptr_t (*originalLoadLut)(void *, int);
void *(*originalCaptureDecisionFactory)(void *, int);

// 组内安装全部成功后才提交功能；失败留下的 wrapper 仅透传，不再次安装已有 Hook。
std::atomic<bool> algoHooksAttempted{false};
std::atomic<bool> algoHooksReady{false};
std::atomic<bool> basicToneHooksAttempted{false};
std::atomic<bool> basicToneHooksReady{false};

// getLmtParamsV1 runs per frame before BasicTone; remember which LUT tree belongs to each parameter
// block so processCore/loadLut (which no longer see the frame) can pick it.
enum Profile { kUnknown = -1, kHost = 0, kGr = 1 };
struct FrameProfile {
    Profile profile = kHost;
};
std::mutex profileMutex;
std::unordered_map<void *, FrameProfile> frameProfiles;
thread_local int activeProfile = kUnknown;

bool isGrFrame(void *frame) {
    void *settings = *reinterpret_cast<void **>(static_cast<char *>(frame) + 0x8110);
    return getSettingInt(settings, &kGrSizeKey, 0) == 63;
}

void getLmtParams(void *parameters, void *frame, int stage) {
    if (!algoHooksReady.load(std::memory_order_acquire)) {
        originalGetLmtParams(parameters, frame, stage);
        return;
    }
    bool gr = isGrFrame(frame);
    originalGetLmtParams(parameters, frame, stage);
    FrameProfile profile;
    profile.profile = gr ? kGr : kHost;
    std::lock_guard<std::mutex> lock(profileMutex);
    // BasicTone 安装中或已失败时不会消费记录，不能继续积累参数地址。
    if (basicToneHooksAttempted.load(std::memory_order_acquire) &&
        !basicToneHooksReady.load(std::memory_order_acquire)) return;
    frameProfiles[parameters] = profile;
}

void getVigParams(void *parameters, void *frame, void *planes) {
    originalGetVigParams(parameters, frame, planes);
    if (!algoHooksReady.load(std::memory_order_acquire)) return;
    if (isGrFrame(frame)) static_cast<uint8_t *>(parameters)[0x1a] = 0;
}

int withGrCaptureMode(int (*operation)(void *, int), void *frame, int stage) {
    auto *mode = reinterpret_cast<uint32_t *>(static_cast<char *>(frame) + 0x18);
    uint32_t previous = *mode;
    *mode = kGrCaptureMode;
    int result = operation(frame, stage);
    *mode = previous;
    return result;
}

int filterProcessV2(void *frame, int stage) {
    if (!algoHooksReady.load(std::memory_order_acquire) || !isGrFrame(frame)) {
        return originalFilterProcessV2(frame, stage);
    }
    // Registration happens before gr_effect_size is attached, so the V1 node's whole lifecycle
    // is scoped to this call, where the frame is known to be GR. The per-image object is
    // consumed after capture; session and request modes are untouched.
    int registration = withGrCaptureMode(filterRegisterV1, frame, stage);
    if (registration != 0) return registration;
    int result = withGrCaptureMode(filterProcessV1, frame, stage);
    withGrCaptureMode(filterUnregisterV1, frame, stage);
    return result;
}

uintptr_t processCore(void *object, void *input, void *output, void *parameters, void *metadata) {
    if (!basicToneHooksReady.load(std::memory_order_acquire)) {
        return originalProcessCore(object, input, output, parameters, metadata);
    }
    int previous = activeProfile;
    activeProfile = kUnknown;
    FrameProfile profile;
    bool known = false;
    {
        std::lock_guard<std::mutex> lock(profileMutex);
        auto found = frameProfiles.find(parameters);
        if (found != frameProfiles.end()) {
            profile = found->second;
            known = true;
            frameProfiles.erase(found);
        }
    }
    if (known) {
        activeProfile = profile.profile;
    }
    uintptr_t result = originalProcessCore(object, input, output, parameters, metadata);
    activeProfile = previous;
    return result;
}

uintptr_t loadLut(void *object, int mode) {
    if (!basicToneHooksReady.load(std::memory_order_acquire)) return originalLoadLut(object, mode);
    // Intermediate ODT passes carry no profile; they keep the object's current LUTs.
    if (activeProfile != kUnknown) {
        char *lmtPath = static_cast<char *>(object) + 0x008;  // 256-byte path buffer
        const char *desired = activeProfile == kGr ? kGrLmtPath : kHostLmtPath;
        if (std::strlen(desired) < 240 && std::strcmp(lmtPath, desired) != 0) {
            std::strcpy(lmtPath, desired);
            // The path is not part of the vendor cache key, so a profile switch forces a reload.
            *reinterpret_cast<int *>(static_cast<char *>(object) + 0xeb0) = -1;
            __android_log_print(ANDROID_LOG_INFO, kTag, "BasicTone profile=%s path=%s",
                                activeProfile == kGr ? "GR" : "host", desired);
        }
    }
    return originalLoadLut(object, mode);
}

bool isPlk110() {
    char model[PROP_VALUE_MAX]{};
    __system_property_get("ro.product.model", model);
    return std::strcmp(model, "PLK110") == 0;
}

void *createCaptureDecision(void *factory, int mode) {
    if (!algoHooksReady.load(std::memory_order_acquire)) {
        return originalCaptureDecisionFactory(factory, mode);
    }
    // PLK110 的 FeatureFactory 没有注册 GR(37)，会创建基类 decision 并产出空 pipeline。
    // 这里只把工厂查询键映射到已注册的 MASTER(33)：factory、返回值和 frame 均保持原样，
    // 因而 GR SDK、HDR 与后续原厂处理仍由原生链路决定。
    int factoryMode = mode == static_cast<int>(kGrCaptureMode) ? kMasterCaptureMode : mode;
    return originalCaptureDecisionFactory(factory, factoryMode);
}

bool hookCaptureDecisionFactory(HookFunction hook, void *base) {
    // PMA110 有自己的原厂注册表，不安装 PLK110 固定偏移 Hook。
    if (!isPlk110()) return true;
    if (originalCaptureDecisionFactory) return true;
    void *address = static_cast<char *>(base) + kCaptureDecisionFactoryOffset;
    int result = hook ? hook(address, reinterpret_cast<void *>(createCaptureDecision),
                             reinterpret_cast<void **>(&originalCaptureDecisionFactory)) : -1;
    if (result != 0 || !originalCaptureDecisionFactory) {
        originalCaptureDecisionFactory = nullptr;
        __android_log_print(ANDROID_LOG_ERROR, kTag,
                            "capture decision factory hook failed at +0x%lx",
                            static_cast<unsigned long>(kCaptureDecisionFactoryOffset));
        return false;
    }
    __android_log_print(ANDROID_LOG_INFO, kTag,
                        "capture decision factory hook installed; awaiting GR group commit");
    return true;
}

void hookAlgoInterface(HookFunction hook, void *handle) {
    if (algoHooksAttempted.load(std::memory_order_acquire)) return;
    const char *lmtSymbol = "_ZN7android14getLmtParamsV1ER12ProcessParamPNS_15AlgoProcessDataEi";
    const char *vigSymbol = "_ZN7android14getVigParamsV1ER12ProcessParamPNS_15AlgoProcessDataERK15ApsBufferPlanes";
    const char *processV1Symbol = "_ZN7android15doFilterProcessEPNS_15AlgoProcessDataEi";
    const char *registerV1Symbol = "_ZN7android16doFilterRegisterEPNS_15AlgoProcessDataEi";
    const char *unregisterV1Symbol = "_ZN7android18doFilterUnregisterEPNS_15AlgoProcessDataEi";
    const char *processV2Symbol = "_ZN7android17doFilterProcessV2EPNS_15AlgoProcessDataEi";
    bool complete = true;
    auto resolve = [&](const char *symbol) {
        void *address = dlsym(handle, symbol);
        if (!address) {
            complete = false;
            __android_log_print(ANDROID_LOG_ERROR, kTag,
                                "GR AlgoInterface contract missing: %s; hooks disabled", symbol);
        }
        return address;
    };
    // V2 的 GR 分支直接调用 V1 生命周期；必须先确认整组导出，再设置偏移或安装 Hook。
    void *lmtAddress = resolve(lmtSymbol);
    resolve(vigSymbol);
    void *processV1Address = resolve(processV1Symbol);
    void *registerV1Address = resolve(registerV1Symbol);
    void *unregisterV1Address = resolve(unregisterV1Symbol);
    resolve(processV2Symbol);
    if (!complete) return;
    Dl_info info{};
    if (!dladdr(lmtAddress, &info)) {
        __android_log_print(ANDROID_LOG_ERROR, kTag,
                            "GR AlgoInterface base unavailable; hooks disabled");
        return;
    }
    bool expected = false;
    if (!algoHooksAttempted.compare_exchange_strong(expected, true)) return;
    filterProcessV1 = reinterpret_cast<decltype(filterProcessV1)>(processV1Address);
    filterRegisterV1 = reinterpret_cast<decltype(filterRegisterV1)>(registerV1Address);
    filterUnregisterV1 = reinterpret_cast<decltype(filterUnregisterV1)>(unregisterV1Address);
    // Same setting accessor that getLmtParamsV1 calls at 0x2035b78.
    getSettingInt = reinterpret_cast<decltype(getSettingInt)>(
        static_cast<char *>(info.dli_fbase) + 0x150cdd0);
    if (!hookCaptureDecisionFactory(hook, info.dli_fbase) ||
        !hookExport(hook, handle, lmtSymbol, reinterpret_cast<void *>(getLmtParams),
                    reinterpret_cast<void **>(&originalGetLmtParams), kTag) ||
        !hookExport(hook, handle, processV2Symbol, reinterpret_cast<void *>(filterProcessV2),
                    reinterpret_cast<void **>(&originalFilterProcessV2), kTag) ||
        !hookExport(hook, handle, vigSymbol, reinterpret_cast<void *>(getVigParams),
                    reinterpret_cast<void **>(&originalGetVigParams), kTag)) {
        __android_log_print(ANDROID_LOG_ERROR, kTag,
                            "GR AlgoInterface hook group disabled; installed wrappers pass through");
        return;
    }
    algoHooksReady.store(true, std::memory_order_release);
    __android_log_print(ANDROID_LOG_INFO, kTag, "GR AlgoInterface hook group ready");
}

void hookBasicTone(HookFunction hook, void *handle) {
    if (basicToneHooksAttempted.load(std::memory_order_acquire)) return;
    // The X10 router exports getAlgoAPI only; its X9 backend keeps these BasicTone_OGL entries.
    const char *coreSymbol = "_ZN13BasicTone_OGL11processCoreEP5ImageS1_PvS2_";
    const char *lutSymbol = "_ZN13BasicTone_OGL7loadLutE7CamMode";
    void *coreAddress = dlsym(handle, coreSymbol);
    void *lutAddress = dlsym(handle, lutSymbol);
    if (!coreAddress && !lutAddress) return;
    if (!coreAddress || !lutAddress) {
        __android_log_print(ANDROID_LOG_ERROR, kTag,
                            "GR BasicTone contract missing: %s; hooks disabled",
                            coreAddress ? lutSymbol : coreSymbol);
        return;
    }
    bool expected = false;
    if (!basicToneHooksAttempted.compare_exchange_strong(expected, true)) return;
    if (!hookExport(hook, handle, coreSymbol, reinterpret_cast<void *>(processCore),
                    reinterpret_cast<void **>(&originalProcessCore), kTag) ||
        !hookExport(hook, handle, lutSymbol, reinterpret_cast<void *>(loadLut),
                    reinterpret_cast<void **>(&originalLoadLut), kTag)) {
        {
            std::lock_guard<std::mutex> lock(profileMutex);
            frameProfiles.clear();
        }
        __android_log_print(ANDROID_LOG_ERROR, kTag,
                            "GR BasicTone hook group disabled; installed wrappers pass through");
        return;
    }
    basicToneHooksReady.store(true, std::memory_order_release);
    __android_log_print(ANDROID_LOG_INFO, kTag, "GR BasicTone hook group ready");
}

}  // namespace

void onLibraryLoadedForGr(HookFunction hook, const char *name, void *handle) {
    // dlopen(nullptr) 表示当前进程，并非具名算法库；LSPosed 会原样传递这个空库名。
    if (name == nullptr) return;
    if (std::strstr(name, "libAlgoInterface.so")) {
        hookAlgoInterface(hook, handle);
    } else if (std::strstr(name, "libBasicTonePhotoX9.so") || std::strstr(name, "libBasicTonePhoto.so")) {
        hookBasicTone(hook, handle);
    }
}
