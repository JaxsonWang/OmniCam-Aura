// 在设备上使用原厂解析器读取配置；只向标准输出写入 JSON，不修改相机文件。
#include <cstdio>
#include <dlfcn.h>

int main(int argc, char **argv) {
    if (argc != 2) {
        std::fprintf(stderr, "Usage: read_camera_config CONFIG_PATH\n");
        return 2;
    }
    void *library = dlopen("/odm/lib64/libAlgoProcess.so", RTLD_NOW | RTLD_LOCAL);
    if (!library) {
        std::fprintf(stderr, "%s\n", dlerror());
        return 1;
    }
    auto read = reinterpret_cast<void *(*)(const char *)>(dlsym(library, "json_object_from_file"));
    auto serialize = reinterpret_cast<const char *(*)(void *)>(dlsym(library, "json_object_to_json_string"));
    auto release = reinterpret_cast<int (*)(void *)>(dlsym(library, "json_object_put"));
    auto initialize = reinterpret_cast<void (*)()>(dlsym(library, "loadOpSecurityLib"));
    if (!read || !serialize || !release || !initialize) {
        std::fprintf(stderr, "Camera JSON API is unavailable\n");
        return 1;
    }
    initialize();
    void *config = read(argv[1]);
    if (!config) {
        std::fprintf(stderr, "Cannot parse %s\n", argv[1]);
        return 1;
    }
    const char *json = serialize(config);
    int result = json && std::puts(json) >= 0 ? 0 : 1;
    release(config);
    return result;
}
