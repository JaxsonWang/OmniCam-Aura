#!/system/bin/sh
# 安装和启动共用同一机型选择，阻止把另一台设备的配置挂载到当前相机。
# 以下变量由加载此文件的安装及启动脚本使用。
# shellcheck disable=SC2034
DEVICE=$(getprop ro.product.model)
case "$DEVICE" in
    PMA110)
        CAMERA_VERSION=7.006.77
        CONFIG_DIR="$MODDIR/payload"
        BIND_ISP=1
        BIND_GAMMA=1
        ;;
    PLK110)
        CAMERA_VERSION=7.006.100
        if [ "$(getprop ro.build.display.id)" != 'PLK110_17.0.0.102(CN01)' ]; then
            echo 'Aura: PLK110 固件不匹配，需要重新提取原厂配置' >&2
            return 1
        fi
        CONFIG_DIR="$MODDIR/profiles/PLK110/config"
        BIND_ISP=0
        BIND_GAMMA=0
        ;;
    *)
        echo "Aura: 不支持的机型 $DEVICE" >&2
        return 1
        ;;
esac
SETTINGS="$MODDIR/profiles/$DEVICE/settings.conf"
