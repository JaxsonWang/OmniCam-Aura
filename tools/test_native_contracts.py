"""编译真实 GR native 代码，验证导出和 Hook 安装合同及失败透传。"""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parent.parent


class NativeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which("clang++") or shutil.which("g++")
        if compiler is None:
            raise unittest.SkipTest("原生合同测试需要 C++ 编译器")
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        work = Path(cls.directory.name)
        (work / "android").mkdir()
        (work / "sys").mkdir()
        (work / "android/log.h").write_text(
            "#pragma once\n"
            "#define ANDROID_LOG_INFO 4\n"
            "#define ANDROID_LOG_ERROR 6\n"
            'extern "C" int __android_log_print(int, const char *, const char *, ...);\n'
        )
        (work / "sys/system_properties.h").write_text(
            "#pragma once\n"
            "#define PROP_VALUE_MAX 92\n"
            'extern "C" int __system_property_get(const char *, char *);\n'
        )
        # 设备策略有独立测试；此处只隔离入口链接依赖，hookExport 使用真实实现。
        (work / "device_policy.h").write_text(
            "#pragma once\n"
            "namespace aura {\n"
            "inline bool devicePolicyMatches(const char *, const char *, int) { return false; }\n"
            "}\n"
        )
        source = work / "test.cpp"
        source.write_text(r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdarg>
#include <cstdio>
#include <cstring>
#include <dlfcn.h>
#include <map>
#include <string>
#include <vector>

void *testDlsym(void *, const char *);
int testDladdr(const void *, Dl_info *);
#define dlsym testDlsym
#define dladdr testDladdr
#include "gr_basictone.cpp"
#include "native_entry.cpp"
#undef dlsym
#undef dladdr

const std::vector<std::string> algoSymbols = {
    "_ZN7android14getLmtParamsV1ER12ProcessParamPNS_15AlgoProcessDataEi",
    "_ZN7android14getVigParamsV1ER12ProcessParamPNS_15AlgoProcessDataERK15ApsBufferPlanes",
    "_ZN7android15doFilterProcessEPNS_15AlgoProcessDataEi",
    "_ZN7android16doFilterRegisterEPNS_15AlgoProcessDataEi",
    "_ZN7android18doFilterUnregisterEPNS_15AlgoProcessDataEi",
    "_ZN7android17doFilterProcessV2EPNS_15AlgoProcessDataEi",
};
const std::vector<std::string> toneSymbols = {
    "_ZN13BasicTone_OGL11processCoreEP5ImageS1_PvS2_",
    "_ZN13BasicTone_OGL7loadLutE7CamMode",
};
struct Call {
    std::string name;
    std::vector<void *> arguments;
    int value;
    int profile;
    uint32_t mode;
};
struct InstalledHook {
    void *replacement;
    bool algo;
};
std::map<std::string, void *> exports;
std::vector<std::string> required;
std::vector<std::string> resolved;
std::vector<std::string> logs;
std::vector<void *> hooked;
std::vector<InstalledHook> installed;
std::vector<Call> calls;
std::string model = "PLK110";
bool baseAvailable = true;
int baseLookups = 0;
int failAt = 0;
bool omitBackup = false;
void *libraryHandle = reinterpret_cast<void *>(0x1000);
void *libraryBase = reinterpret_cast<void *>(0x10000000);
int decision;

extern "C" int __system_property_get(const char *key, char *value) {
    assert(std::strcmp(key, "ro.product.model") == 0);
    std::strcpy(value, model.c_str());
    return static_cast<int>(model.size());
}

extern "C" int __android_log_print(int, const char *, const char *format, ...) {
    char message[1024];
    va_list args;
    va_start(args, format);
    std::vsnprintf(message, sizeof(message), format, args);
    va_end(args);
    logs.emplace_back(message);
    return 0;
}

void installPopPathRemap(HookFunction) { assert(false); }

void *testDlsym(void *handle, const char *symbol) {
    assert(handle == libraryHandle);
    resolved.emplace_back(symbol);
    auto found = exports.find(symbol);
    return found == exports.end() ? nullptr : found->second;
}

int testDladdr(const void *address, Dl_info *info) {
    ++baseLookups;
    assert(address == exports.at(algoSymbols[0]));
    info->dli_fbase = libraryBase;
    return baseAvailable ? 1 : 0;
}

uint32_t frameMode(void *frame) {
    return *reinterpret_cast<uint32_t *>(static_cast<char *>(frame) + 0x18);
}

void *fakeFactory(void *factory, int mode) {
    calls.push_back({"factory", {factory}, mode, activeProfile, 0});
    return &decision;
}

void fakeLmt(void *parameters, void *frame, int stage) {
    calls.push_back({"lmt", {parameters, frame}, stage, activeProfile, frameMode(frame)});
}

void fakeVig(void *parameters, void *frame, void *planes) {
    calls.push_back({"vig", {parameters, frame, planes}, 0, activeProfile, frameMode(frame)});
}

int fakeV2(void *frame, int stage) {
    calls.push_back({"v2", {frame}, stage, activeProfile, frameMode(frame)});
    return -702;
}

int fakeV1(void *frame, int stage) {
    calls.push_back({"v1", {frame}, stage, activeProfile, frameMode(frame)});
    return 611;
}

int fakeRegister(void *frame, int stage) {
    calls.push_back({"register", {frame}, stage, activeProfile, frameMode(frame)});
    return 0;
}

int fakeUnregister(void *frame, int stage) {
    calls.push_back({"unregister", {frame}, stage, activeProfile, frameMode(frame)});
    return 0;
}

uintptr_t fakeCore(void *object, void *input, void *output, void *parameters, void *metadata) {
    calls.push_back({"core", {object, input, output, parameters, metadata}, 0, activeProfile, 0});
    return 0x12345678;
}

uintptr_t fakeLut(void *object, int mode) {
    calls.push_back({"lut", {object}, mode, activeProfile, 0});
    return 0x87654321;
}

int fakeSetting(void *settings, const void *key, int fallback) {
    assert(key == &kGrSizeKey && fallback == 0);
    return *static_cast<int *>(settings);
}

struct Buffers {
    alignas(8) std::array<uint8_t, 0x8120> frame{};
    alignas(8) std::array<uint8_t, 0x40> parameters{};
    alignas(8) std::array<uint8_t, 0xec0> object{};
    int factory = 19;
    int planes = 23;
    int input = 29;
    int output = 31;
    int metadata = 41;
    int settings = 63;

    Buffers() {
        frame.fill(0x39);
        parameters.fill(0x57);
        object.fill(0x73);
        *reinterpret_cast<uint32_t *>(frame.data() + 0x18) = 69;
        *reinterpret_cast<void **>(frame.data() + 0x8110) = &settings;
        std::strcpy(reinterpret_cast<char *>(object.data() + 8), "/original/vendor/lut");
        *reinterpret_cast<int *>(object.data() + 0xeb0) = 415;
    }
};

void assertCall(const char *name, const std::vector<void *> &arguments, int value) {
    assert(!calls.empty());
    const auto &call = calls.back();
    assert(call.name == name && call.arguments == arguments && call.value == value);
}

void assertPassthrough(bool algo) {
    assert(!(algo ? algoHooksReady.load() : basicToneHooksReady.load()));
    Buffers data;
    const auto oldFrame = data.frame;
    const auto oldParameters = data.parameters;
    const auto oldObject = data.object;
    auto oldProfiles = frameProfiles;
    int oldProfile = activeProfile;
    frameProfiles.clear();
    frameProfiles[data.parameters.data()] = {kGr};
    frameProfiles[&data.metadata] = {kHost};
    activeProfile = kGr;
    for (const auto &item : installed) {
        if (item.algo != algo) continue;
        size_t previousCalls = calls.size();
        if (item.replacement == reinterpret_cast<void *>(createCaptureDecision)) {
            auto wrapper = reinterpret_cast<decltype(originalCaptureDecisionFactory)>(item.replacement);
            assert(wrapper(&data.factory, 37) == &decision);
            assertCall("factory", {&data.factory}, 37);
        } else if (item.replacement == reinterpret_cast<void *>(getLmtParams)) {
            auto wrapper = reinterpret_cast<decltype(originalGetLmtParams)>(item.replacement);
            wrapper(data.parameters.data(), data.frame.data(), 17);
            assertCall("lmt", {data.parameters.data(), data.frame.data()}, 17);
            assert(calls.back().mode == 69);
        } else if (item.replacement == reinterpret_cast<void *>(getVigParams)) {
            auto wrapper = reinterpret_cast<decltype(originalGetVigParams)>(item.replacement);
            wrapper(data.parameters.data(), data.frame.data(), &data.planes);
            assertCall("vig", {data.parameters.data(), data.frame.data(), &data.planes}, 0);
            assert(calls.back().mode == 69);
        } else if (item.replacement == reinterpret_cast<void *>(filterProcessV2)) {
            auto wrapper = reinterpret_cast<decltype(originalFilterProcessV2)>(item.replacement);
            assert(wrapper(data.frame.data(), 47) == -702);
            assertCall("v2", {data.frame.data()}, 47);
            assert(calls.back().mode == 69);
        } else if (item.replacement == reinterpret_cast<void *>(processCore)) {
            auto wrapper = reinterpret_cast<decltype(originalProcessCore)>(item.replacement);
            assert(wrapper(data.object.data(), &data.input, &data.output,
                           data.parameters.data(), &data.metadata) == 0x12345678);
            assertCall("core", {data.object.data(), &data.input, &data.output,
                                data.parameters.data(), &data.metadata}, 0);
        } else if (item.replacement == reinterpret_cast<void *>(loadLut)) {
            auto wrapper = reinterpret_cast<decltype(originalLoadLut)>(item.replacement);
            assert(wrapper(data.object.data(), 37) == 0x87654321);
            assertCall("lut", {data.object.data()}, 37);
        } else {
            assert(false);
        }
        assert(calls.size() == previousCalls + 1 && calls.back().profile == kGr);
        assert(data.frame == oldFrame && data.parameters == oldParameters && data.object == oldObject);
        assert(activeProfile == kGr);
        assert(frameProfiles.size() == 2);
        assert(frameProfiles.at(data.parameters.data()).profile == kGr);
        assert(frameProfiles.at(&data.metadata).profile == kHost);
    }
    frameProfiles = oldProfiles;
    activeProfile = oldProfile;
}

int fakeHook(void *address, void *replacement, void **backup) {
    // 首次安装前整组符号必须已解析；每次回调都检查提交前已安装 wrapper 的实际行为。
    for (const auto &symbol : required) {
        assert(std::find(resolved.begin(), resolved.end(), symbol) != resolved.end());
        assert(exports.count(symbol) == 1);
    }
    bool algo = replacement != reinterpret_cast<void *>(processCore) &&
                replacement != reinterpret_cast<void *>(loadLut);
    assert(!(algo ? algoHooksReady.load() : basicToneHooksReady.load()));
    hooked.push_back(address);
    void *original = address;
    if (replacement == reinterpret_cast<void *>(createCaptureDecision)) {
        assert(address == static_cast<char *>(libraryBase) + kCaptureDecisionFactoryOffset);
        original = reinterpret_cast<void *>(fakeFactory);
    }
    if (static_cast<int>(hooked.size()) == failAt) {
        // 分开验证错误返回码与空 backup，避免两个故障同时出现掩盖任一检查缺失。
        *backup = omitBackup ? nullptr : original;
        assertPassthrough(algo);
        return omitBackup ? 0 : -17;
    }
    *backup = original;
    installed.push_back({replacement, algo});
    assertPassthrough(algo);
    size_t hookCount = hooked.size();
    size_t resolveCount = resolved.size();
    onLibraryLoadedForGr(fakeHook, algo ? "libAlgoInterface.so" : "libBasicTonePhotoX9.so", libraryHandle);
    assert(hooked.size() == hookCount && resolved.size() == resolveCount);
    return 0;
}

void populate(const std::vector<std::string> &symbols) {
    required = symbols;
    if (symbols == algoSymbols) {
        const std::vector<void *> functions = {
            reinterpret_cast<void *>(fakeLmt), reinterpret_cast<void *>(fakeVig),
            reinterpret_cast<void *>(fakeV1), reinterpret_cast<void *>(fakeRegister),
            reinterpret_cast<void *>(fakeUnregister), reinterpret_cast<void *>(fakeV2),
        };
        for (size_t i = 0; i < symbols.size(); ++i) exports[symbols[i]] = functions[i];
    } else {
        assert(symbols == toneSymbols);
        exports[symbols[0]] = reinterpret_cast<void *>(fakeCore);
        exports[symbols[1]] = reinterpret_cast<void *>(fakeLut);
    }
}

bool logged(const std::string &text) {
    return std::any_of(logs.begin(), logs.end(), [&](const std::string &message) {
        return message.find(text) != std::string::npos;
    });
}

void assertAlgoUninstalled() {
    assert(hooked.empty());
    assert(!algoHooksReady.load() && !algoHooksAttempted.load());
    assert(!getSettingInt);
    assert(!originalGetLmtParams);
    assert(!originalGetVigParams);
    assert(!originalFilterProcessV2);
    assert(!filterProcessV1);
    assert(!filterRegisterV1);
    assert(!filterUnregisterV1);
    assert(!originalCaptureDecisionFactory);
}

void assertAlgoEnabled() {
    assert(algoHooksReady.load() && algoHooksAttempted.load());
    Buffers data;
    getSettingInt = fakeSetting;
    if (model == "PLK110") {
        assert(createCaptureDecision(&data.factory, 37) == &decision);
        assertCall("factory", {&data.factory}, 33);
    }
    frameProfiles.clear();
    getLmtParams(data.parameters.data(), data.frame.data(), 7);
    assertCall("lmt", {data.parameters.data(), data.frame.data()}, 7);
    if (basicToneHooksAttempted.load() && !basicToneHooksReady.load()) {
        assert(frameProfiles.empty());
        getLmtParams(&data.metadata, data.frame.data(), 8);
        assertCall("lmt", {&data.metadata, data.frame.data()}, 8);
        assert(frameProfiles.empty());
    } else {
        assert(frameProfiles.at(data.parameters.data()).profile == kGr);
    }
    getVigParams(data.parameters.data(), data.frame.data(), &data.planes);
    assert(data.parameters[0x1a] == 0);
    size_t previous = calls.size();
    assert(filterProcessV2(data.frame.data(), 11) == 611);
    assert(calls.size() == previous + 3 && frameMode(data.frame.data()) == 69);
    const char *expected[] = {"register", "v1", "unregister"};
    for (size_t i = 0; i < 3; ++i) {
        const auto &call = calls[previous + i];
        assert(call.name == expected[i] && call.mode == 37 && call.value == 11);
        assert(call.arguments == std::vector<void *>{data.frame.data()});
    }
    data.settings = 0;
    assert(filterProcessV2(data.frame.data(), 13) == -702);
    assertCall("v2", {data.frame.data()}, 13);
    frameProfiles.clear();
}

void assertToneEnabled() {
    assert(basicToneHooksReady.load() && basicToneHooksAttempted.load());
    Buffers data;
    activeProfile = kGr;
    assert(loadLut(data.object.data(), 37) == 0x87654321);
    assert(std::strcmp(reinterpret_cast<char *>(data.object.data() + 8), kGrLmtPath) == 0);
    assert(*reinterpret_cast<int *>(data.object.data() + 0xeb0) == -1);
    frameProfiles[data.parameters.data()] = {kGr};
    activeProfile = kHost;
    assert(processCore(data.object.data(), &data.input, &data.output,
                       data.parameters.data(), &data.metadata) == 0x12345678);
    assertCall("core", {data.object.data(), &data.input, &data.output,
                        data.parameters.data(), &data.metadata}, 0);
    assert(calls.back().profile == kGr && activeProfile == kHost);
    assert(frameProfiles.count(data.parameters.data()) == 0);
    activeProfile = kUnknown;
}

void loadGroup(bool algo) {
    populate(algo ? algoSymbols : toneSymbols);
    onLibraryLoadedForGr(fakeHook, algo ? "libAlgoInterface.so" : "libBasicTonePhotoX9.so", libraryHandle);
}

void assertNoRetry(bool algo) {
    size_t hookCount = hooked.size();
    size_t resolveCount = resolved.size();
    failAt = 0;
    onLibraryLoadedForGr(fakeHook, algo ? "libAlgoInterface.so" : "libBasicTonePhoto.so", libraryHandle);
    assert(hooked.size() == hookCount && resolved.size() == resolveCount);
}

int main(int argc, char **argv) {
    assert(argc >= 2);
    std::string scenario = argv[1];
    if (scenario == "algo-complete") {
        assert(argc == 3);
        model = argv[2];
        loadGroup(true);
        assert(hooked.size() == (model == "PLK110" ? 4 : 3));
        assert(baseLookups == 1);
        assert(getSettingInt);
        assert(originalGetLmtParams && originalGetVigParams && originalFilterProcessV2);
        assert(reinterpret_cast<void *>(filterProcessV1) == exports.at(algoSymbols[2]));
        assert(reinterpret_cast<void *>(filterRegisterV1) == exports.at(algoSymbols[3]));
        assert(reinterpret_cast<void *>(filterUnregisterV1) == exports.at(algoSymbols[4]));
        assert((originalCaptureDecisionFactory != nullptr) == (model == "PLK110"));
        assert(!basicToneHooksReady.load() && !basicToneHooksAttempted.load());
        assertNoRetry(true);
        assertAlgoEnabled();
    } else if (scenario == "algo-missing") {
        assert(argc == 3);
        populate(algoSymbols);
        auto missing = algoSymbols.at(std::stoi(argv[2]));
        exports.erase(missing);
        onLibraryLoadedForGr(fakeHook, "libAlgoInterface.so", libraryHandle);
        assertAlgoUninstalled();
        assert(baseLookups == 0);
        assert(resolved.size() == algoSymbols.size());
        for (const auto &symbol : algoSymbols) {
            assert(std::count(resolved.begin(), resolved.end(), symbol) == 1);
        }
        assert(logs.size() == 1 && logged(missing));
    } else if (scenario == "algo-empty") {
        onLibraryLoadedForGr(fakeHook, "libAlgoInterface.so", libraryHandle);
        assertAlgoUninstalled();
        assert(baseLookups == 0);
        assert(logs.size() == algoSymbols.size());
        for (const auto &symbol : algoSymbols) assert(logged(symbol));
    } else if (scenario == "algo-base-missing") {
        populate(algoSymbols);
        baseAvailable = false;
        onLibraryLoadedForGr(fakeHook, "libAlgoInterface.so", libraryHandle);
        assertAlgoUninstalled();
        assert(baseLookups == 1);
        assert(logged("base unavailable"));
    } else if (scenario == "tone-complete") {
        loadGroup(false);
        assert(hooked.size() == 2 && originalProcessCore && originalLoadLut);
        assert(!algoHooksReady.load() && !algoHooksAttempted.load());
        assertNoRetry(false);
        assertToneEnabled();
    } else if (scenario == "tone-missing") {
        assert(argc == 3);
        populate(toneSymbols);
        auto missing = toneSymbols.at(std::stoi(argv[2]));
        exports.erase(missing);
        onLibraryLoadedForGr(fakeHook, "libBasicTonePhotoX9.so", libraryHandle);
        assert(hooked.empty() && !originalProcessCore && !originalLoadLut);
        assert(!basicToneHooksReady.load() && !basicToneHooksAttempted.load());
        assert(logs.size() == 1 && logged(missing));
    } else if (scenario == "tone-router") {
        onLibraryLoadedForGr(fakeHook, "libBasicTonePhoto.so", libraryHandle);
        assert(hooked.empty() && !originalProcessCore && !originalLoadLut);
        assert(resolved.size() == toneSymbols.size());
        assert(!basicToneHooksReady.load() && !basicToneHooksAttempted.load());
        assert(logs.empty());
    } else if (scenario == "hook-failure") {
        assert(argc == 6);
        bool algo = std::strcmp(argv[2], "algo") == 0;
        model = argv[3];
        failAt = std::stoi(argv[4]);
        omitBackup = std::strcmp(argv[5], "empty-backup") == 0;
        if (!algo) frameProfiles[&decision] = {kGr};
        loadGroup(algo);
        if (!algo) assert(frameProfiles.empty());
        assert(hooked.size() == static_cast<size_t>(failAt));
        assert(installed.size() == static_cast<size_t>(failAt - 1));
        assert(algo ? algoHooksAttempted.load() : basicToneHooksAttempted.load());
        assert(!(algo ? basicToneHooksAttempted.load() : algoHooksAttempted.load()));
        assert(logged(algo ? "GR AlgoInterface hook group disabled" : "GR BasicTone hook group disabled"));
        assertPassthrough(algo);
        assertNoRetry(algo);
        assertPassthrough(algo);
    } else if (scenario == "independent-groups") {
        assert(argc == 4);
        bool failedAlgo = std::strcmp(argv[2], "algo") == 0;
        bool failureFirst = std::strcmp(argv[3], "first") == 0;
        if (!failureFirst) loadGroup(!failedAlgo);
        failAt = static_cast<int>(hooked.size()) + (failedAlgo ? 4 : 2);
        if (!failedAlgo) frameProfiles[&decision] = {kGr};
        loadGroup(failedAlgo);
        if (!failedAlgo) assert(frameProfiles.empty());
        assertPassthrough(failedAlgo);
        assertNoRetry(failedAlgo);
        if (failureFirst) loadGroup(!failedAlgo);
        assert(algoHooksReady.load() == !failedAlgo);
        assert(basicToneHooksReady.load() == failedAlgo);
        assert(algoHooksAttempted.load() && basicToneHooksAttempted.load());
        assertPassthrough(failedAlgo);
        if (failedAlgo) assertToneEnabled(); else assertAlgoEnabled();
    } else if (scenario == "null-hook") {
        assert(argc == 3);
        bool algo = std::strcmp(argv[2], "algo") == 0;
        populate(algo ? algoSymbols : toneSymbols);
        onLibraryLoadedForGr(nullptr, algo ? "libAlgoInterface.so" : "libBasicTonePhotoX9.so", libraryHandle);
        assert(hooked.empty() && installed.empty());
        assert(!(algo ? algoHooksReady.load() : basicToneHooksReady.load()));
        assert(logged("hook group disabled"));
        assertNoRetry(algo);
    } else if (scenario == "unrelated") {
        onLibraryLoadedForGr(nullptr, nullptr, libraryHandle);
        onLibraryLoadedForGr(fakeHook, "", libraryHandle);
        onLibraryLoadedForGr(fakeHook, "/system/lib64/libc.so", libraryHandle);
        onLibraryLoadedForGr(fakeHook, "libAlgoProcess.so", libraryHandle);
        assertAlgoUninstalled();
        assert(resolved.empty() && logs.empty());
    } else {
        assert(false);
    }
}
''')
        cls.executable = work / "test-native-contracts"
        cpp = PROJECT / "app/src/main/cpp"
        subprocess.run(
            [compiler, "-std=c++17", "-I", str(work), "-I", str(cpp),
             str(source), "-o", str(cls.executable), "-ldl"],
            check=True,
        )

    def run_scenario(self, *arguments):
        subprocess.run([str(self.executable), *arguments], check=True)

    def test_complete_algo_contract_preserves_device_specific_hooks(self):
        for model in ("PLK110", "PMA110"):
            with self.subTest(model=model):
                self.run_scenario("algo-complete", model)

    def test_each_missing_algo_export_disables_the_whole_group(self):
        for index in range(6):
            with self.subTest(export=index):
                self.run_scenario("algo-missing", str(index))

    def test_all_missing_algo_exports_are_reported(self):
        self.run_scenario("algo-empty")

    def test_missing_library_base_leaves_offsets_and_hooks_unset(self):
        self.run_scenario("algo-base-missing")

    def test_complete_basictone_pair_installs_once(self):
        self.run_scenario("tone-complete")

    def test_each_incomplete_basictone_pair_disables_both_hooks(self):
        for index in range(2):
            with self.subTest(export=index):
                self.run_scenario("tone-missing", str(index))

    def test_router_without_basictone_exports_is_not_an_error(self):
        self.run_scenario("tone-router")

    def test_each_algo_hook_failure_stops_install_and_passes_through_without_retry(self):
        for model, hook_count in (("PLK110", 4), ("PMA110", 3)):
            for failure in ("error", "empty-backup"):
                for index in range(1, hook_count + 1):
                    with self.subTest(model=model, failure=failure, hook=index):
                        self.run_scenario("hook-failure", "algo", model, str(index), failure)

    def test_each_basictone_hook_failure_preserves_profile_path_and_cache(self):
        for failure in ("error", "empty-backup"):
            for index in (1, 2):
                with self.subTest(failure=failure, hook=index):
                    self.run_scenario("hook-failure", "tone", "PLK110", str(index), failure)

    def test_one_failed_group_does_not_disable_the_other_group(self):
        for failed_group in ("algo", "tone"):
            for order in ("first", "last"):
                with self.subTest(failed_group=failed_group, order=order):
                    self.run_scenario("independent-groups", failed_group, order)

    def test_missing_hook_function_keeps_groups_disabled_without_retry(self):
        for group in ("algo", "tone"):
            with self.subTest(group=group):
                self.run_scenario("null-hook", group)

    def test_null_and_unrelated_library_callbacks_are_ignored(self):
        self.run_scenario("unrelated")


if __name__ == "__main__":
    unittest.main()
