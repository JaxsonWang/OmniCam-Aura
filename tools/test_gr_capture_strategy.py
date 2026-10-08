"""编译真实 GR native Hook，验证 capture decision 工厂映射与机型边界。"""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parent.parent


class GrCaptureStrategyTests(unittest.TestCase):
    def test_factory_mapping_and_install_boundary(self):
        compiler = shutil.which("clang++") or shutil.which("g++")
        if compiler is None:
            self.skipTest("GR capture strategy 测试需要 C++ 编译器")

        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            (work / "android").mkdir()
            (work / "sys").mkdir()
            (work / "android/log.h").write_text(
                "#define ANDROID_LOG_INFO 4\n"
                "#define ANDROID_LOG_ERROR 6\n"
                "inline int __android_log_print(int, const char *, const char *, ...) { return 0; }\n"
            )
            (work / "sys/system_properties.h").write_text(
                "#pragma once\n"
                "#define PROP_VALUE_MAX 92\n"
                "extern \"C\" int __system_property_get(const char *, char *);\n"
            )
            (work / "test.cpp").write_text(
                r'''
#include <cassert>
#include <cstring>
#include <string>

#include "gr_basictone.cpp"

std::string testModel;
void *seenFactory;
int seenMode;
void *factoryResult;
int hookCalls;
int hookResult;
void *hookAddress;
void *hookReplacement;

extern "C" int __system_property_get(const char *key, char *value) {
    const std::string &property = std::strcmp(key, "ro.product.model") == 0
        ? testModel : std::string();
    std::memcpy(value, property.c_str(), property.size() + 1);
    return static_cast<int>(property.size());
}

void *fakeFactory(void *factory, int mode) {
    seenFactory = factory;
    seenMode = mode;
    return factoryResult;
}

int fakeHook(void *address, void *replacement, void **backup) {
    ++hookCalls;
    hookAddress = address;
    hookReplacement = replacement;
    *backup = reinterpret_cast<void *>(fakeFactory);
    return hookResult;
}

void hookExport(HookFunction, void *, const char *, void *, void **, const char *) {}

int main() {
    struct Factory { int marker; } factory{7};
    int createdDecision = 0;
    originalCaptureDecisionFactory = fakeFactory;

    factoryResult = &createdDecision;
    assert(createCaptureDecision(&factory, 37) == &createdDecision);
    assert(seenFactory == &factory);
    assert(seenMode == 33);

    assert(createCaptureDecision(&factory, 69) == &createdDecision);
    assert(seenFactory == &factory);
    assert(seenMode == 69);

    factoryResult = nullptr;
    assert(createCaptureDecision(&factory, 37) == nullptr);
    assert(seenFactory == &factory);
    assert(seenMode == 33);

    originalCaptureDecisionFactory = nullptr;
    hookCalls = 0;
    hookResult = 0;
    testModel = "PMA110";
    void *base = reinterpret_cast<void *>(0x10000000);
    hookCaptureDecisionFactory(fakeHook, base);
    assert(hookCalls == 0);
    assert(originalCaptureDecisionFactory == nullptr);

    testModel = "PLK110";
    hookCaptureDecisionFactory(fakeHook, base);
    assert(hookCalls == 1);
    assert(hookAddress == static_cast<char *>(base) + kCaptureDecisionFactoryOffset);
    assert(hookReplacement == reinterpret_cast<void *>(createCaptureDecision));
    assert(originalCaptureDecisionFactory == fakeFactory);

    originalCaptureDecisionFactory = nullptr;
    hookCalls = 0;
    hookResult = -1;
    hookCaptureDecisionFactory(fakeHook, base);
    assert(hookCalls == 1);
    assert(originalCaptureDecisionFactory == nullptr);
}
'''
            )
            cpp = PROJECT / "app/src/main/cpp"
            executable = work / "test-gr-capture-strategy"
            subprocess.run(
                [
                    compiler,
                    "-std=c++17",
                    "-I",
                    str(work),
                    "-I",
                    str(cpp),
                    str(work / "test.cpp"),
                    "-o",
                    str(executable),
                    "-ldl",
                ],
                check=True,
            )
            subprocess.run([str(executable)], check=True)


if __name__ == "__main__":
    unittest.main()
