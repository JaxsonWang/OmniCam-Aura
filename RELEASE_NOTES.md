# OmniCam Aura 1.1.1（本地验证）

APK 与 KernelSU 模块统一为 1.1.1，`versionCode=8`。本轮已验证范围和仍待真机验收的项目见下文。

## 修复

- PLK110：固件 `PLK110_17.0.0.102(CN01)`，相机 7.006.100 / versionCode 60000。保留原厂镜头、24mm 主摄、3.5×／7× 焦段、分辨率、ISP、Gamma 和 APS 硬件参数。
- GR HDR：PLK110 保留原生 GR 会话、P010 输入、HLG 显示和 APS Ultra HDR；仅让 HAL 使用本机大师调校及相同的预先 HDR 标志。修复发白、暗部压黑和异常过饱和，未修改曝光或 LUT 曲线。
- GR 保存：补齐四处大师／GR 算法决策条件，恢复 BasicTone 与 HDR transform；在 PLK110 成片工厂查询时让 GR 使用本机大师策略，实际帧模式不变。修复 47.6 MB 原始 P010 误写为 HEIC，以及空成片管线导致相册记录被删除。
- GR 水印：PLK110 相册的 `Section.style` 改为真实 GR 字段 `A0`，避免将默认 GR 样式写入视频字段 `z0`。仅覆盖 PLK110 符号，PMA110 保持原规则；保存持久化尚待真机复验。
- POP：在 GL 线程的 Canvas 构造完成后，只创建缺失的 inverse-mask shader；通过 DEX 指纹定位字段与类型，不修改全局反色补光返回值和缓存。默认配置已删除位 4。
- 配置生命周期：删除 settings.conf、service 的覆盖 XML 写入、模块内 prefs 备份及手动删除模式数据库的逻辑。ODM 是唯一功能配置源；相机自行处理模式数据库的版本升降级。
- 旧版安装清理：精确删除曾使用的 10 个相机覆盖键及相册旧 GR boolean，其他键保留。存在改动时在 `/data/adb/omnicam_aura/legacy-overrides.*` 保存相机真实清理前快照，相册使用独立的 `legacy-gallery-overrides.*`；不存在的文件不造空备份，重复安装不覆盖快照。
- 挂载失败：持久记录本次成功的配置、资源、ISP／Gamma 挂载，失败时逆序卸载，再写 skip_mount。service 算法库核对失败同样回滚，并撤销属于 Aura 的算法库顶层挂载；按 mountinfo parent 链识别所有权，不误卸载其他模块。回滚不完整时记录错误并保留清单。
- 删除重复库绑定的 post-mount.sh。算法库由元模块挂载，service 只核对实际内容。删除安装目录中无意义的 skip_mount／mount-ready 清除操作。
- Java／原生白名单由同一份 `config/supported-devices.json` 生成，发行校验同步检查 device.sh。PMA110 原有效配置不变，两个先前只存在于覆盖表的值移入其 ODM 配置。
- 新增 macOS／Linux `build.sh`，复用 Python 构建、打包和校验流程。

## 手动反色补光

PLK110 默认保持原厂前置闪光行为。在 KernelSU／KowSU 的 Aura 模块卡片执行“操作”，随后重启，可开启反色补光；再次操作并重启关闭。手动开启后会采用厂商原生逻辑，改变前置闪光选项，并可能在低光时自动补光。更新保留选择，卸载删除选择。POP 不依赖此开关，PMA110 不受影响。

## BasicTone 影响范围

模块以 8960 字节的 `X9/X10 photo-portrait palette router 1.0.13` 替换 PLK110 原厂 `libBasicTonePhoto.so`（`BasicTone VERSION(QCOM): 2025-05-20`），常规路径使用 PMA110 的 X9 库（2026-03-19），调色盘路径使用 X10 库。影响所有调用 BasicTone 的模式，包括普通拍照和前后置人像，不限于 GR。未实施调色补偿。

已采集停用 KernelSU 模块并重启后的原厂对照（LSPosed 仍启用）。另在其余 Aura 配置与 Hook 均启用的条件下，仅临时换回 PLK110 原厂 BasicTone 库，完成普通拍照、人像的前后置四组成片对照，随后恢复模块库。当前室内静物／天花板场景未见明显整体色偏、异常泛白或影调突变。部分配对自动曝光不同：前置普通照片 ISO 640／800，后置普通照片约 1/13s／1/12s；前置人像均为 1/25s、ISO 1600。此结果仅说明当前场景未观察到明显色彩回归，不代表完整原厂一致性、真人肤色、人物分割、细节、HDR 或全部光线场景已验收。

## 安装和升级边界

在 KernelSU／KowSU 中安装同版 ZIP、安装配套 APK，在 LSPosed 勾选相机和相册，将相机 App Profile 设为自定义并关闭“卸载模块”，然后重启。相机无需超级用户权限。Aura 与 Muse 只启用一套。

真机环境：Magic Mount-rs 4.0.11、Zygisk Next 1.5.0、LSPosed 2.2.1；管理器包名 `com.kowx712.supermanager`。Hybrid Mount 本轮未实测。

安装器检查相机 versionName，Java／原生启动检查机型和固件，尚未在运行时检查相机 versionCode。相机单独升级可能在固件白名单仍匹配时破坏 DEX 指纹或原生布局；请在升级相机前停用 Aura，待重新适配后启用。PMA110 本轮没有真机回归，保留历史行为由配置与主机测试约束。

## 当前验证证据

- 主机单元测试 31 项通过；ShellCheck 通过；macOS build.sh 已实际构建 APK 和模块 ZIP，并通过 verify_aura.py。
- PLK110 符号回放：相机 198 项、缺失 0；相册旧映射回放 20 项、缺失 0，但该检查未发现 GR 字段语义错误。PLK110 专用的 7 条新相机规则及 GR 水印字段覆盖已收进 symbols-plk110.json，基础 PMA110 规则不增加解析项；水印字段修正后的相册回放仍待设备恢复。
- POP 21 次往返、42 次切换，相机 PID 不变，测试时间窗无新增崩溃；日志记录 shader 在 PreviewGLThread 初始化，反色补光缓存仍为 false。
- 移除全部旧覆盖键后，GR 五档焦段、POP、移轴、调色盘和闪光灯亮度入口仍正常。
- KernelSU 停用并重启：enabled=false，Aura 挂载数为 0，覆盖 XML 为空，GR／POP 入口消失，相机正常预览；前置闪光选项与默认启用模块时同为“关闭／补光自动／常亮”。
- 真机临时隔离目录中完成 6 次实际 bind，在第 7 次注入无效目标后，6 个挂载逆序卸载成功，未残留挂载。此演练不修改 ODM 系统目标。
- GR 五档 16／24／48／85／170mm 均已取得可解码的最终 HEIF，MediaStore 宽高完整，EXIF 等效焦距对应；全部包含完整 Oplus HDR gain map，最大增益约 4.926。预览颜色与实际 HDR 显示已由用户确认正常。室内近距离场景中 85／170mm 使用主摄数字变焦，本次不代表远景长焦解析力验收。
- GR 连续拍摄的第二张及后续照片先写入带 `DEFER_JOB_QUICK_IMAGE` 标记的快速 JPEG。保持相机进程并打开相册后，日志确认 `onApsStartProcess` → `onHeicReceived` → 最终文件替换成功，标记由 270532608 更新为 536870912；连续 24mm 与 170mm 样张均形成有效最终 HEIF。早前在后处理完成前强停相机的诊断样张不计入最终验收。
- POP 最终动态照片为 3408×5488 JPEG，移轴为 3072×4608 HEIF，均能解码并正常入库。POP 最终动态照片未检出标准或 Oplus 私有 HDR gain map；静态／动态照片对照及封装时序尚未验证，不能仅依据配置或另一张快速图宣称完整 HDR 成片通过。
- GR 修复版第一轮 KernelSU 安装、APK 覆盖与重启通过：模块／APK 均为 1.1.1／code 8，五个算法库各一层挂载，覆盖 XML 为空。反色补光关闭时前置菜单为“关闭／补光自动／常亮”。随后已执行开启操作并重启，但 ADB 连接尚未恢复，开启行为、二次覆盖安装和最终关闭恢复仍待验收。新增水印字段修正的同版本构建尚未安装到设备。
- GR 水印设置入口、样式预览和应用动作已实测；重新进入时未保留所选样式。字段映射修正后的保存回传及新 APK 真机复验尚未完成。

本轮最终成片、EXIF、HDR、连续拍摄日志与操作记录位于 `build/audit-1.1.1/final-acceptance/`；选定的最终样张清单为 `accepted-samples.json`，不包含尚未完成延迟处理的诊断样张。
