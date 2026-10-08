// LSPosed native module entry for the camera process (listed in assets/native_init).
#include <android/log.h>
#include <cstdint>
#include <cstring>
#include <dlfcn.h>
#include <sys/system_properties.h>

#include "native_hooks.h"

namespace {

struct NativeApiEntries {
    uint32_t version;
    HookFunction hook;
    int (*unhook)(void *);
};

using LibraryLoadedCallback = void (*)(const char *name, void *handle);

HookFunction installHook;

bool supportedDevice() {
    char model[PROP_VALUE_MAX]{};
    char firmware[PROP_VALUE_MAX]{};
    __system_property_get("ro.product.model", model);
    __system_property_get("ro.build.display.id", firmware);
    return std::strcmp(model, "PMA110") == 0 ||
        (std::strcmp(model, "PLK110") == 0 &&
         std::strcmp(firmware, "PLK110_17.0.0.102(CN01)") == 0);
}

void onLibraryLoaded(const char *name, void *handle) {
    onLibraryLoadedForGr(installHook, name, handle);
}

}  // namespace

void hookExport(HookFunction hook, void *handle, const char *symbol, void *replacement,
                void **backup, const char *tag) {
    void *address = dlsym(handle, symbol);
    if (!address || !hook || hook(address, replacement, backup) != 0) {
        __android_log_print(ANDROID_LOG_ERROR, tag, "native hook failed: %s", symbol);
    }
}

extern "C" __attribute__((visibility("default"), used))
LibraryLoadedCallback native_init(const NativeApiEntries *entries) {
    // 原生入口早于 Java Hook 执行，必须独立阻止在不匹配的固件上使用固定偏移。
    if (!supportedDevice()) {
        __android_log_print(ANDROID_LOG_ERROR, "Aura", "unsupported device/firmware; native hooks disabled");
        return nullptr;
    }
    installHook = entries->hook;
    installPopPathRemap(installHook);
    return onLibraryLoaded;
}
