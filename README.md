# OmniCam Aura

![OmniCam Aura 图标](artwork/OmniCam-Aura.png)

面向 PMA110 和 PLK110 的无界面 KernelSU 模块与 LSPosed 插件。当前发行版本为 **1.0.1**（`versionCode=7`）。

| 机型 | 固件／相机 | 验证范围 |
| --- | --- | --- |
| PMA110 | 相机 7.006.77 | 保留原有适配；历史版本已安装，未在本次重新实拍 |
| OnePlus PLK110 | Android 17，`PLK110_17.0.0.102(CN01)`，相机 7.006.100 | 已安装验证，GR 五档焦距与 POP 预览已复测，GR 24mm 实拍保存成功；完整成片效果与相册功能仍需逐项验证 |

## 功能

- 理光 GR 模式、影调、焦距条、快照对焦及相机／相册水印。
- POP 模式、复古资源与高像素支持；滑杆进成片，成片走 Ultra HDR。
- 移轴拍照模式。
- Find X10 的清透／琥珀滤镜、调色盘预览与成片、闪光灯亮度、AI 构图配置及哈苏相关滤镜、调色盘和柔光资源。

LSPosed 包名为 `local.omnicam.aura`，作用域为 `com.oplus.camera` 和 `com.coloros.gallery3d`。APK 没有 Activity、启动入口或设置界面，功能固定启用。

## 安装

1. 在 KernelSU 中安装发行页的模块 ZIP。
2. 安装同一发行版的 APK，并在 LSPosed 中启用 Aura，勾选相机和相册作用域。
3. 在 KernelSU／KowSU 的应用配置中，找到系统相机 `com.oplus.camera`，将 App Profile 设为“自定义”，关闭“卸载模块”。相机不需要超级用户权限，保持关闭即可。
4. 重启设备使模块挂载和 Hook 生效。

Aura 与 OmniCam Muse 的相机 Hook 和挂载资源重叠，只启用其中一套。

支持管理器包名为 `com.kowx712.supermanager` 的 KernelSU 环境。安装器使用 KernelSU 提供的 `KSU` 环境变量识别框架，管理器包名不参与授权或挂载。需要已启用的挂载元模块、Zygisk 和 LSPosed；PLK110 验证环境为 Magic Mount-rs 4.0.11、Zygisk Next 1.5.0 和 LSPosed 2.2.1。

“卸载模块”会让相机进程看不到 Aura 挂载的配置，但 LSPosed 仍可能启用 GR／POP 入口，导致预览黑屏。即使 `bind.log` 显示挂载成功，也需要确认相机的应用配置；无须全局关闭其他应用的卸载策略。原生回调已修复算法库调用 `dlopen(NULL)` 时，对空库名执行字符串查找导致的崩溃。

PLK110 的 GR 保留原厂 HDR 预览模式表，撤回不匹配的 GR HDR 预览声明，解决 16／24／48mm 发白；POP 补齐过渡遮罩 shader 的初始化功能位，解决切换模式时的预览线程空指针。GR 的成片 HDR 配置保持原有设置，预览修复不通过修改 EV、ISO 或快门实现。

PLK110 使用 `module/profiles/PLK110` 独立配置，保留原厂相机 ID、24mm 主摄、3.5×／7× 焦段、分辨率和 APS 硬件参数，不覆盖原厂 ISP 与 Gamma。GR、POP 和调色盘所需功能合入原厂配置，不启用原厂没有的前置高像素节点。该配置仅适用于表中固件；安装时拒绝其他固件或相机版本。

启动时若固件不匹配或配置挂载失败，会写入 `skip_mount` 阻止元模块挂载算法库。只有配置与算法库全部挂载完成，才会写入相机设置。诊断日志位于 `/data/adb/modules/omnicam_aura/bind.log` 和 `service.log`；修复原因后重新安装模块，不要仅删除阻止挂载的标记。

首次写入前保存 `override_config_data.xml` 到模块的 `backup` 目录。若需要重建缺少移轴的模式排序数据库，也先保存数据库及其日志文件。模块不会删除照片，但重建模式排序会改变“更多”面板顺序。停用模块并重启可撤销系统文件挂载；相机设置备份需按实际改动手动恢复，避免覆盖安装之后的个人设置。

## 构建

需要 JDK 17 或更新版本、Android SDK（含 API 37、Build Tools、NDK 29.0.14206865 和 CMake 3.22.1）、Python 3 与 Git。设置 `JAVA_HOME`、`ANDROID_HOME`／`ANDROID_SDK_ROOT`，或通过 `local.properties` 指向 SDK。

```sh
python3 tools/build_release.py --sdk /absolute/path/to/android-sdk
python3 -m unittest discover -s tools -p 'test_*.py' -v
```

Windows 也可运行 `./build.ps1`。配套 APK 输出到 `module/omnicam-aura-1.0.1.apk`，KernelSU ZIP 输出到项目根目录 `OmniCam-Aura-1.0.1-KSU.zip`，构建脚本会进行结构与签名检查。切换发行版本时，先将 `module` 中的旧版 APK 移出打包目录。

构建默认使用 Android 调试签名。若要使用自己的发布证书，设置 `OMNICAM_KEYSTORE`、`OMNICAM_STORE_PASSWORD`、`OMNICAM_KEY_ALIAS` 和 `OMNICAM_KEY_PASSWORD`；证书与密码均不应提交到仓库。不同证书签发的 APK 不能直接覆盖安装。

## PLK110 配置与符号验证

`tools/read_camera_config.cpp` 通过设备原厂 `libAlgoProcess.so` 读取加密配置，仅向标准输出写入 JSON。用 NDK 将它编译为 arm64 可执行文件后，通过 ADB 放入 `/data/local/tmp`，在设备上使用以下库路径运行：

```sh
adb -s SERIAL shell env LD_LIBRARY_PATH=/system/lib64:/system_ext/lib64:/odm/lib64:/vendor/lib64 /data/local/tmp/omnicam-aura-read-config /odm/etc/camera/config/oplus_camera_config
```

生成器输入目录应包含 `config/camera_unit_config`、`config/camera_unit_feature_config.protobuf`，以及上述工具读取的 `oplus_camera_config.json`、`oplus_camera_algo_switch_config.json`、`oplus_camera_preview_decision_config.json`。原厂输入应保存在本地诊断目录，不使用另一机型配置替代。

```sh
python3 tools/prepare_plk110.py build/device-plk110/stock module/profiles/PLK110/config
python3 tools/replay_symbols.py --serial SERIAL --sdk /absolute/path/to/android-sdk --apk /product/app/OplusCamera/OplusCamera.apk --section camera --profile PLK110 --output build/camera-symbols.json
```

符号验证需先完成一次 Gradle 构建，以取得依赖。它在设备上的独立进程读取 DEX，不安装 APK、不启用 LSPosed Hook、不启动相机。相册使用 `--section gallery`，APK 路径由 `adb -s SERIAL shell pm path com.coloros.gallery3d` 获取。

## 来源与许可

本仓库的原创源码和脚本按 [MIT 许可证](LICENSE) 开放。相机厂商的库、固件配置及媒体资源保留原权利人的权利；MIT 许可证不授予这些文件的再许可。项目与相机厂商无隶属关系。
