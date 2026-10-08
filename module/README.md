# OmniCam Aura 1.1.1（本地验证）

适配组合：PMA110／相机 7.006.77；PLK110／固件 `PLK110_17.0.0.102(CN01)`／相机 7.006.100（versionCode 60000）。同版 APK 包名为 `local.omnicam.aura`，LSPosed 作用域为相机和相册。

在 KernelSU／KowSU 中安装 ZIP 和配套 APK，启用 LSPosed，将相机 App Profile 设为自定义并关闭“卸载模块”，保持超级用户权限关闭，然后重启。Aura 与 Muse 只启用一套。管理器 `com.kowx712.supermanager` 可用；依赖挂载元模块、Zygisk、LSPosed。本轮使用 Magic Mount-rs 4.0.11；Hybrid Mount 未实测。

POP 在 Canvas 构造完成后的 GL 线程补建缺失遮罩 shader，不强制全局反色补光、不修改其静态缓存。PLK110 默认反色补光关闭；在模块卡片执行“操作”并重启可手动开启，再次操作并重启关闭。开启后使用厂商逻辑，前置闪光选项会变化，低光可能自动补光。偏好保存在模块目录外，更新保留，卸载删除。PMA110 不使用此手动开关。

功能开关只来自 ODM 与 APK Hook，service 不再写相机／相册的功能偏好或删除模式数据库。安装器清理旧版曾使用的 10 个相机覆盖键和相册 `business_featureSwitch_is_camera_gr_supported`，并仅在有改动时将真实清理前文件保存到 `/data/adb/omnicam_aura/legacy-overrides.*`；相册快照单独保存在 `legacy-gallery-overrides.*`；不创建空备份，也不覆盖已有快照。停用模块并重启后，PLK110 已实测 GR／POP 入口消失、相机正常预览。

post-fs-data 中途失败会逆序卸载已完成的挂载，再写 skip_mount。算法库由元模块挂载，已删除重复绑定的 post-mount.sh。mount-ready 只标记配置挂载成功；service 随后核对五个实际算法库并准备资源。库不匹配时也回滚：先撤销确认属于 Aura 的算法库顶层挂载，再逆序撤销本次配置，移除 mount-ready 并写 skip_mount。按 mountinfo parent 链确认所有权；其他模块的上层挂载不动，无法完整回滚时记录错误并保留清单。失败详情见 bind.log / service.log，修复后重新安装，不要直接删除失败标记。

GR 沿用大师模式的成像契约：PLK110 保留原生 GR SDK／APS 身份、P010 预览、HLG 显示与成片 HDR；HAL 使用原厂大师调校及其两项关闭的预先 HDR 标志，避免重复处理。GR 的多帧、BasicTone、超广角校正和 HDR transform 条件与大师一致；仅在成片策略工厂中为 GR 选择本机已注册的大师实现，修复无效 HEIC 和相册记录消失。该工厂适配只作用于精确白名单内的 PLK110，PMA110 保持原行为。

GR 的五档焦距已取得可解码的最终 HEIF 与完整 HDR gain map；连续拍摄后需让原厂延迟任务完成，相册读回已经验证。POP 预览、拍摄和动态照片保存通过，但本次最终动态照片未检出 HDR gain map，不能视为完整 HDR 验收通过。PLK110 相册的 GR 样式字段映射已修正，退出后重新进入能否保留样式仍待真机复验。

PLK110 保留原厂镜头、分辨率、ISP、Gamma 和 APS 硬件参数，但 **BasicTone 已整体替换**：8960 字节的 X9/X10 router 1.0.13 取代原厂 2025-05-20 库，常规路径转发 PMA110 X9（2026-03-19），调色盘路径使用 X10。这影响普通拍照和人像等调用 BasicTone 的全部模式，四组前后置普通照片／人像的单库对照，在当前室内静物与天花板场景未见明显整体色偏、泛白或影调突变；部分自动曝光不同，不代表完整原厂一致性。完整成片验证范围以仓库 RELEASE_NOTES.md 为准。

机型／固件白名单由同一 JSON 生成 Java、原生和模块选择器，并由发行校验检查一致性。相机版本只在安装时检查，运行时尚未核对 versionCode；相机单独升级可能破坏指纹或原生布局，应先停用模块再重新适配。PMA110 本轮未重新真机验证，Hybrid Mount、真人肤色和全部拍摄场景亦未验收。

源码、macOS build.sh 用法和授权范围见仓库根目录 README.md 与 LICENSE；1.1.1 的已验证范围和待验收项目见 RELEASE_NOTES.md。
