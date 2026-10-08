"""在指定 Android 设备的独立进程中验证符号规则，不安装模块。"""

import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
from zipfile import ZipFile

PROJECT = Path(__file__).resolve().parent.parent


def run(*args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--sdk", type=Path, required=True)
    parser.add_argument("--apk", required=True, help="设备上的 APK 路径")
    parser.add_argument("--section", choices=("camera", "gallery"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--profile", choices=("PMA110", "PLK110"), required=True)
    args = parser.parse_args()
    cache = Path.home() / ".gradle/caches/modules-2/files-2.1"
    aar, = (cache / "org.luckypray/dexkit/2.3.0").glob("*/dexkit-2.3.0.aar")
    kotlin, = (cache / "org.jetbrains.kotlin/kotlin-stdlib/2.4.20").glob("*/kotlin-stdlib-2.4.20.jar")
    flatbuffers, = (cache / "com.google.flatbuffers/flatbuffers-java/23.5.26").glob("*/flatbuffers-java-23.5.26.jar")
    work = PROJECT / "build/symbol-replay"
    classes = work / "classes"
    classes.mkdir(parents=True, exist_ok=True)
    with ZipFile(aar) as archive:
        for source, name in (("classes.jar", "dexkit.jar"), ("jni/arm64-v8a/libdexkit.so", "libdexkit.so")):
            (work / name).write_bytes(archive.read(source))
    android = args.sdk / "platforms/android-37.0/android.jar"
    java_bin = Path(os.environ["JAVA_HOME"]) / "bin"
    run(java_bin / "javac", "--release", "17", "-classpath",
        os.pathsep.join(map(str, (android, work / "dexkit.jar", kotlin))), "-d", classes,
        PROJECT / "tools/symbols/Replay.java",
        PROJECT / "app/src/main/java/local/jiege/hook/common/SymbolSearch.java")
    jar = work / "replay-classes.jar"
    run(java_bin / "jar", "cf", jar, "-C", classes, ".")
    dex = work / "replay.jar"
    run(args.sdk / "build-tools/37.0.0/d8", "--min-api", "28", "--lib", android,
        "--output", dex, jar, work / "dexkit.jar", kotlin, flatbuffers)
    remote = "/data/local/tmp/omnicam-aura-symbol-replay"
    adb = ["adb", "-s", args.serial]
    run(*adb, "shell", "mkdir", "-p", remote)
    run(*adb, "push", dex, work / "libdexkit.so", PROJECT / "app/src/main/assets/symbols.json", remote + "/")
    command = ["env", f"CLASSPATH={remote}/replay.jar", "app_process", "/", "local.omnicam.tools.Replay",
               f"{remote}/libdexkit.so", f"{remote}/symbols.json", args.section, args.apk]
    if args.profile == "PLK110":
        run(*adb, "push", PROJECT / "app/src/main/assets/symbols-plk110.json", remote + "/")
        command.append(f"{remote}/symbols-plk110.json")
    result = run(*adb, "shell", shlex.join(command), capture_output=True, text=True)
    report = json.loads(result.stdout)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f'{args.section}: {len(report["resolved"])} resolved, {len(report["failures"])} missing')
    for key, value in report["failures"].items():
        print(f"  {key}: {value}")
    if report["failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
