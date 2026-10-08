#!/system/bin/sh

[ "${KSU:-}" = true ] || abort 'Aura 需要 KernelSU 环境'
[ "$ARCH" = arm64 ] || abort 'Aura 只支持 arm64'
MODDIR=$MODPATH
# shellcheck source=module/device.sh
. "$MODPATH/device.sh" || abort 'Aura 没有匹配当前机型和固件的配置'
INSTALLED_CAMERA=$(dumpsys package com.oplus.camera | sed -n 's/^[[:space:]]*versionName=//p' | head -n 1)
[ "$INSTALLED_CAMERA" = "$CAMERA_VERSION" ] || abort "相机版本不匹配: ${INSTALLED_CAMERA}，要求 ${CAMERA_VERSION}"
# shellcheck source=module/clear-overrides.sh
. "$MODPATH/clear-overrides.sh"
clear_camera_overrides /data/user/0/com.oplus.camera/shared_prefs/override_config_data.xml /data/adb/omnicam_aura \
    || abort 'Aura 无法撤销旧版相机覆盖设置'
clear_gallery_overrides /data/user/0/com.coloros.gallery3d/shared_prefs/business_featureSwitch_config.xml /data/adb/omnicam_aura \
    || abort 'Aura 无法撤销旧版相册覆盖设置'
ui_print "- 机型: $DEVICE / 相机: $CAMERA_VERSION"
ui_print '- 使用 KernelSU 模块接口，不依赖管理器包名'
if [ "$DEVICE" = PLK110 ]; then
    ui_print '- 保留 PLK110 原厂 ISP、Gamma 和 APS 硬件参数'
fi
ui_print '- 需要已启用的挂载元模块、Zygisk 和 LSPosed'
ui_print '- 相机 App Profile 请选择自定义，并关闭“卸载模块”'
ui_print '- “卸载模块”开启时，相机进程看不到 Aura 配置，会出现黑屏'
ui_print '- 相机无需开启超级用户权限'
set_perm_recursive "$MODPATH" 0 0 0755 0644
for SCRIPT in customize.sh device.sh post-fs-data.sh service.sh action.sh uninstall.sh; do
    set_perm "$MODPATH/$SCRIPT" 0 0 0755
done
