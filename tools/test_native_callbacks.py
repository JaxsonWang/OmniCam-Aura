"""在主机运行原生库加载回调，覆盖真机 dlopen(NULL) 崩溃路径。"""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

PROJECT = Path(__file__).resolve().parent.parent


class NativeCallbackTests(unittest.TestCase):
    def test_main_process_handle_does_not_match_named_camera_libraries(self):
        compiler = shutil.which("clang++") or shutil.which("g++")
        if compiler is None:
            self.skipTest("原生回调测试需要 C++ 编译器")
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
                "#include <cstdlib>\n"
                "#define PROP_VALUE_MAX 92\n"
                "inline int __system_property_get(const char *, char *) { std::abort(); }\n"
            )
            source = work / "test.cpp"
            source.write_text(
                '#include "native_hooks.h"\n'
                '#include <cstdlib>\n'
                'void hookExport(HookFunction, void *, const char *, void *, void **, const char *) { std::abort(); }\n'
                'int main() {\n'
                '  onLibraryLoadedForGr(nullptr, nullptr, reinterpret_cast<void *>(1));\n'
                '  onLibraryLoadedForGr(nullptr, "", reinterpret_cast<void *>(1));\n'
                '  onLibraryLoadedForGr(nullptr, "/system/lib64/libc.so", reinterpret_cast<void *>(1));\n'
                '}\n'
            )
            cpp = PROJECT / "app/src/main/cpp"
            executable = work / "test-callback"
            subprocess.run([compiler, "-std=c++17", "-I", str(work), "-I", str(cpp),
                            str(source), str(cpp / "gr_basictone.cpp"), "-o", str(executable), "-ldl"], check=True)
            subprocess.run([str(executable)], check=True)


if __name__ == "__main__":
    unittest.main()
