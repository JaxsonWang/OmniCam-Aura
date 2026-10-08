"""构建、打包并校验配套 APK 与 KernelSU 模块，支持 macOS、Linux 和 Windows。"""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

PROJECT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", type=Path, default=os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT"))
    args = parser.parse_args()
    env = os.environ.copy()
    if args.sdk:
        env["ANDROID_HOME"] = str(args.sdk.resolve())
    props = dict(line.split("=", 1) for line in (PROJECT / "module/module.prop").read_text().splitlines() if "=" in line)
    version = props["version"]
    wrapper = ["cmd", "/c", str(PROJECT / "gradlew.bat")] if os.name == "nt" else ["sh", str(PROJECT / "gradlew")]
    subprocess.run([*wrapper, ":app:assembleRelease", "--console=plain"], cwd=PROJECT, env=env, check=True)
    apk = PROJECT / "module" / f"omnicam-aura-{version}.apk"
    shutil.copy2(PROJECT / "app/build/outputs/apk/release/app-release.apk", apk)
    archive = PROJECT / f"OmniCam-Aura-{version}-KSU.zip"
    for command in ([sys.executable, str(PROJECT / "tools/zip_module.py"), str(PROJECT / "module"), str(archive)],
                    [sys.executable, str(PROJECT / "tools/verify_aura.py")]):
        subprocess.run(command, cwd=PROJECT, env=env, check=True)
    print(f"APK: {apk}\nKernelSU: {archive}")


if __name__ == "__main__":
    main()
