# OmniCam Aura

![OmniCam Aura 图标](artwork/OmniCam-Aura.png)

面向 PMA110 和 PLK110 的无界面 KernelSU 模块与 LSPosed 插件。当前本地验证版本为 **1.1.1**（`versionCode=8`）。

| 机型 | 固件／相机 | 验证范围 |
| --- | --- | --- |
| PMA110 | 相机 7.006.77 | 保留原有适配；历史版本已安装，未在本次重新实拍 |
| OnePlus PLK110 | Android 17，`PLK110_17.0.0.102(CN01)`，相机 7.006.100（versionCode 60000） | 本地真机审查与回归中，实际验证范围见 RELEASE_NOTES.md |

## 功能

- 理光 GR 模式、影调、焦距条、快照对焦及相机／相册水印。
- POP 模式、复古资源与高像素支持，滑杆进成片。配置已启用 Ultra HDR，但本次动态照片最终文件未检出 gain map，尚未通过完整 HDR 验收。
- 移轴拍照模式。
- Find X10 的清透／琥珀滤镜、调色盘预览与成片、闪光灯亮度、AI 构图配置及哈苏相关滤镜、调色盘和柔光资源。

LSPosed 包名为 `local.omnicam.aura`，作用域为 `com.oplus.camera` 和 `com.coloros.gallery3d`。APK 没有 Activity、启动入口或设置界面；PLK110 的可选反色补光通过 KernelSU 模块操作切换。

## 安装

1. 在 KernelSU 中安装发行页的模块 ZIP。
2. 安装同一发行版的 APK，并在 LSPosed 中启用 Aura，勾选相机和相册作用域。
3. 在 KernelSU／KowSU 的应用配置中，找到系统相机 `com.oplus.camera`，将 App Profile 设为“自定义”，关闭“卸载模块”。相机不需要超级用户权限，保持关闭即可。
4. 重启设备使模块挂载和 Hook 生效。

Aura 与 OmniCam Muse 的相机 Hook 和挂载资源重叠，只启用其中一套。

支持管理器包名为 `com.kowx712.supermanager` 的 KernelSU 环境。安装器使用 KernelSU 提供的 `KSU` 环境变量识别框架，管理器包名不参与授权或挂载。需要已启用的挂载元模块、Zygisk 和 LSPosed；PLK110 验证环境为 Magic Mount-rs 4.0.11、Zygisk Next 1.5.0 和 LSPosed 2.2.1。

“卸载模块”会让相机进程看不到 Aura 挂载的配置，但 LSPosed 仍可能启用 GR／POP 入口，导致预览黑屏。即使 `bind.log` 显示挂载成功，也需要确认相机的应用配置；无须全局关闭其他应用的卸载策略。原生回调已修复算法库调用 `dlopen(NULL)` 时，对空库名执行字符串查找导致的崩溃。

POP 继承照片模式，GR 继承大师模式。PLK110 的 GR 保留原生 GR SDK 会话与 P010／HLG 预览，但 HAL 使用本机大师模式的调校标记，并与原厂大师一样关闭 HAL 的两项预先 HDR 处理标志；SDK 的 HDR 预览、APS Ultra HDR 和成片 gain map 保持启用。这修复了 HAL 重复／不匹配处理引起的发白、暗部压黑和过饱和，不修改 EV、ISO、快门或 LUT 曲线。POP 在 GL 线程的 Canvas 构造完成后，仅补建缺失的遮罩 shader，解决切换模式时的预览线程空指针。

PLK110 的 APS 决策表将 GR 纳入大师的多帧、BasicTone、超广角校正和 HDR transform 条件；本机成片工厂缺少 GR 注册，因此只在工厂查询时为 GR 选择已存在的大师策略，实际帧仍保持 GR 身份。该组合修复了快速图编码失败后写出原始 P010，以及最终成片管线为空导致相册记录被删除的问题。PMA110 保留原有 SDK 适配，不安装该 PLK110 工厂 Hook。

GR 沿用原厂大师的延迟成片流程：相机前台可先显示快速图，进入相册后再完成 APS 处理并替换为最终 HEIF。本轮已验证连续拍摄后的完整回调、最终文件与 HDR gain map；不能仅凭媒体记录的 `is_pending=0` 或文件大小短期稳定判断最终处理完成，也不能在验收前强停相机。

相机 GR 水印设置可以进入相册样式编辑页。PLK110 当前相册的 GR 样式字段为 `A0`，原规则 `z0` 实为视频样式，已通过 PLK110 独立符号覆盖修正；PMA110 规则保持原样。样式切换、退出后重新进入的持久化复验仍待完成。

PLK110 使用 `module/profiles/PLK110` 独立配置，保留原厂相机 ID、24mm 主摄、3.5×／7× 焦段、分辨率和 APS 硬件参数，不覆盖原厂 ISP 与 Gamma。GR、POP 和调色盘所需功能合入原厂配置，不启用原厂没有的前置高像素节点。该配置仅适用于表中固件；安装时拒绝其他固件或相机版本。

启动时若固件不匹配或配置挂载失败，脚本按成功挂载的逆序卸载，再写入 `skip_mount` 阻止元模块挂载算法库；卸载失败会明确记入日志。`mount-ready` 只表示配置挂载完成，service 在元模块执行之后核对五个算法库的实际内容；任何库不匹配时，先撤销确认属于 Aura 且位于最上层的算法库挂载，再逆序撤销配置，移除 mount-ready 并写 skip_mount。挂载所有权依据 mountinfo 的 parent 链判断，其他模块的覆盖层不会被卸载；无法完整回滚时明确记录错误并保留 mounted-targets。库由 Magic Mount-rs／Hybrid Mount 提供，不再通过 `post-mount.sh` 重复绑定。Magic Mount-rs 已在上述设备验证，Hybrid Mount 本轮未实测。诊断日志位于 `/data/adb/modules/omnicam_aura/bind.log` 和 `service.log`；修复原因后重新安装模块，不要仅删除阻止挂载的标记。

功能配置只来自 ODM，不再生成 `settings.conf`，service 不写 `override_config_data.xml`，也不删除模式数据库。模式表的升降级由相机自己的 `db.version` 生命周期处理。PLK110 真机移除旧覆盖键后，GR 五档焦距、POP、移轴、调色盘和闪光灯亮度仍正常；停用模块并重启后，GR／POP 入口消失，相机正常预览。PMA110 原先仅存在于覆盖表中的 POP 成片 HDR 列表项和闪光灯亮度开关已移入 PMA110 ODM 配置，保持原有效值。

安装器会清理旧版写入的 10 个相机覆盖键，以及相册 `business_featureSwitch_is_camera_gr_supported` 偏好，保留其他设置；仅在确有改动时，将清理前的真实文件保存到 `/data/adb/omnicam_aura/legacy-overrides.*`。相册的清理前快照单独保存到 `legacy-gallery-overrides.*`。这是清理前快照，不是原厂备份。文件原先不存在时不创建占位文件；重复安装不会把空配置覆盖到旧快照。快照位于模块目录外，不受 KernelSU 更新替换目录影响。停用模块并重启即可撤销 ODM 功能配置。

## PLK110 手动反色补光

默认关闭，前置普通拍照保持原厂“关闭／补光自动／常亮”选项。POP 独立补建遮罩 shader，不 Hook `j0()` 的返回值，也不写入其静态 Boolean 缓存。

在 KernelSU／KowSU 的 Aura 模块卡片执行“操作”，可在开启与关闭之间切换，随后重启设备生效。开启后按厂商反色补光逻辑运行：前置闪光选项会变化，低光时可能自动补光。再次操作并重启恢复原厂默认行为。选择保存在 `/data/adb/omnicam_aura/inverse-light`，更新保留选择，卸载删除选择；PMA110 不使用此开关。

启用时，启动脚本从默认配置生成运行时 ODM 文件，仅添加补光位 4（二进制字符串 `100`）；关闭时直接挂载默认配置。发行版默认配置始终不含该位。缓存值只由相机正常读取实际配置后生成，切换不向应用持久覆盖表写值。

## BasicTone 与相机升级边界

**PLK110 的 BasicTone 并非全量保留原厂实现。** 模块用 8960 字节的 `X9/X10 photo-portrait palette router 1.0.13` 替换 `/odm/lib64/libBasicTonePhoto.so`，将常规路径转发到随附的 PMA110 `libBasicTonePhotoX9.so`（版本日期 2026-03-19），调色盘路径使用 X10 实现。PLK110 原厂库标识为 `BasicTone VERSION(QCOM): 2025-05-20`。该替换影响普通拍照、人像等全部调用 BasicTone 的模式，不能将 GR 预览修复视为所有模式色彩一致性的证明。成片对照结论与限制见 RELEASE_NOTES.md；本次不做额外调色补偿。

机型／固件清单的唯一来源为 `config/supported-devices.json`。Gradle 生成 Java 和 C++ 白名单，`tools/verify_aura.py` 校验模块 `device.sh` 与清单一致；PMA110 仍不增加固件限制。安装时检查相机 versionName，启动时检查机型／固件，**尚未在运行时核对相机 versionCode**。相机可能在固件不变时单独升级，届时旧 DEX 指纹或原生布局可能失效；安装时的版本检查不能覆盖这种情况。仅使用表中的相机版本，单独更新相机前停用 Aura，重新适配并验证后再启用。

## 构建

需要 JDK 17 或更新版本、Android SDK（含 API 37、Build Tools、NDK 29.0.14206865 和 CMake 3.22.1）、Python 3 与 Git。设置 `JAVA_HOME`、`ANDROID_HOME`／`ANDROID_SDK_ROOT`，或通过 `local.properties` 指向 SDK。

```sh
./build.sh --sdk /absolute/path/to/android-sdk
python3 -m unittest discover -s tools -p 'test_*.py' -v
```

macOS 和 Linux 使用 `./build.sh`；已设置 SDK 环境变量或 `local.properties` 时可省略 `--sdk`。脚本可以从任意工作目录调用，参数原样传给 `tools/build_release.py`，也可通过 `OMNICAM_PYTHON` 指定 Python 3 可执行文件。macOS 可先运行 `export JAVA_HOME=$(/usr/libexec/java_home -v 21)` 选择已安装的 JDK 21。

Windows 使用 `./build.ps1`，也可直接运行 `python tools/build_release.py --sdk C:/path/to/android-sdk`。配套 APK 输出到 `module/omnicam-aura-1.1.1.apk`，KernelSU ZIP 输出到项目根目录 `OmniCam-Aura-1.1.1-KSU.zip`，构建脚本会进行结构与签名检查。切换发行版本时，先将 `module` 中的旧版 APK 移出打包目录。

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
