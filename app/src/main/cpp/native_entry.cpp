// LSPosed native module entry for the camera process (listed in assets/native_init).
#include <android/log.h>
#include <cstdint>
#include <dlfcn.h>

#include "native_hooks.h"

namespace {

struct NativeApiEntries {
    uint32_t version;
    HookFunction hook;
    int (*unhook)(void *);
};

using LibraryLoadedCallback = void (*)(const char *name, void *handle);

HookFunction installHook;

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
    installHook = entries->hook;
    installPopPathRemap(installHook);
    return onLibraryLoaded;
}
