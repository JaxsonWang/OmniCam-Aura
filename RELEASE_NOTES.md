# OmniCam Aura 1.0.1

适配 OnePlus PLK110，修复相机预览黑屏、GR 主摄／超广角发白，以及模式切换崩溃。保留 PMA110 原有适配。APK 与 KernelSU 模块统一为版本 1.0.1，内部 `versionCode=7`，支持覆盖较早的同签名测试版。

## 适配与修复

- PLK110：Android 17、固件 `PLK110_17.0.0.102(CN01)`、相机 7.006.100；使用独立配置，保留原厂镜头、分辨率、ISP、Gamma 和 APS 硬件参数。
- PMA110：相机 7.006.77，保留原有配置与功能。
- 支持管理器包名为 `com.kowx712.supermanager` 的 KernelSU／KowSU，补齐 Magic Mount-rs 的挂载阶段处理。
- 修正 GR HDR 预览声明，解决 16／24／48mm 发白，保留原厂其他模式的 HDR 预览配置与 GR 成片 HDR 设置。
- 补齐 POP 过渡遮罩 shader 初始化，解决 `GLES20Canvas` 空指针；原生库加载回调正确处理 `dlopen(NULL)`。
- 增加机型、固件与相机版本校验，以及相机设置和模式排序数据库备份。

## 功能

- 理光 GR 模式、影调、焦距条、快照对焦及相机／相册水印。
- POP 模式、复古资源、高像素支持与成片调节。
- 移轴拍照、清透／琥珀滤镜、调色盘、闪光灯亮度与相关滤镜资源。
- 无界面 LSPosed 插件：包名 `local.omnicam.aura`，作用域为系统相机和相册。

## 安装

1. 在 KernelSU／KowSU 中安装 `OmniCam-Aura-1.0.1-KSU.zip`。
2. 安装 `omnicam-aura-1.0.1.apk`，在 LSPosed 中启用 Aura，勾选 `com.oplus.camera` 和 `com.coloros.gallery3d`。
3. 将系统相机的 App Profile 设为“自定义”，关闭“卸载模块”。相机的超级用户权限保持关闭。
4. 重启设备。Aura 与 OmniCam Muse 只启用其中一套。

需要已启用的挂载元模块、Zygisk 和 LSPosed。PLK110 验证环境为 Magic Mount-rs 4.0.11、Zygisk Next 1.5.0、LSPosed 2.2.1。相机开启“卸载模块”时，即使全局挂载成功，进程内仍可能缺少 Aura 配置而黑屏。

## 验证范围

- Release 构建、APK 签名、无界面 Manifest、模块结构与版本一致性校验。
- 9 项回归测试通过，覆盖配置保留、安装约束和原生空库名回调；ShellCheck 通过。
- PLK110 相机 191 个／相册 20 个 DEX 符号解析通过。
- 同一实现的真机验证已完成 GR 16／24／48／85／170mm 和 POP 预览，GR 24mm 实拍保存 HEIC 成功，回读成片未见之前的大面积发白。本轮修复验证期间相机进程持续运行，崩溃日志没有新增记录。

本次发布将已验证的测试版统一编号为 1.0.1；更名后的产物重新完成构建与结构校验。PMA110 未在本次重新实拍，完整成片风格、全部拍摄场景和相册功能仍需逐项验证。仅支持上述适配组合。
