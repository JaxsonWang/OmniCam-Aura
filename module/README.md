# OmniCam Aura 1.0.1

适配组合：PMA110／相机 7.006.77；PLK110／固件 `PLK110_17.0.0.102(CN01)`／相机 7.006.100。

安装此 KernelSU 模块后，安装同版配套 APK `omnicam-aura-1.0.1.apk`，在 LSPosed 中启用并勾选相机 `com.oplus.camera` 和相册 `com.coloros.gallery3d`。在 KernelSU／KowSU 中将相机的 App Profile 设为“自定义”，关闭“卸载模块”，保持超级用户权限关闭，然后重启。Aura 与 Muse 只能启用其一。

管理器包名 `com.kowx712.supermanager` 可用；依赖 KernelSU 模块接口、挂载元模块、Zygisk 和 LSPosed。挂载脚本支持 Magic Mount-rs 的 post-mount 阶段。

相机开启“卸载模块”时，进程内会缺少 GR／POP 配置而黑屏，即使全局挂载日志正常也不能省略此设置。原生回调已修复算法库调用 `dlopen(NULL)` 引发的崩溃。

PLK110 已撤回不匹配的 GR HDR 预览声明，解决主摄／超广角发白；同时初始化 POP 过渡遮罩 shader，解决模式切换崩溃。成片 HDR 配置保持原有设置。

PLK110 保留原厂镜头、分辨率、ISP、Gamma 和 APS 硬件参数。已经完成安装验证、配置回归、相机 191 个符号和相册 20 个符号验证，以及 GR 五档焦距和 POP 预览复测。GR 24mm 实拍保存 HEIC 成功，回读成片未见预览修复前的大面积发白；完整成片效果与相册功能尚未逐项验证。

挂载失败详情见模块目录的 `bind.log`。固件不匹配时拒绝挂载，需重新适配后安装；不要强行移除 `skip_mount`。相机设置和可能重建的模式排序数据库备份位于 `backup` 目录。

源码、构建说明和授权范围见仓库根目录的 README.md 与 LICENSE。
