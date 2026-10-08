#!/system/bin/sh
# 由 config/supported-devices.json 生成；通过 tools/generate_device_policy.py 更新。
# shellcheck disable=SC2034
DEVICE=$(getprop ro.product.model)
case "$DEVICE" in
    PMA110)
        CAMERA_VERSION=7.006.77
        CONFIG_DIR="$MODDIR/"payload
        BIND_ISP=1
        BIND_GAMMA=1
        ;;
    PLK110)
        CAMERA_VERSION=7.006.100
        if [ "$(getprop ro.build.display.id)" != 'PLK110_17.0.0.102(CN01)' ]; then
            echo 'Aura: 固件不匹配，需要重新提取原厂配置' >&2
            return 1
        fi
        CONFIG_DIR="$MODDIR/"profiles/PLK110/config
        BIND_ISP=0
        BIND_GAMMA=0
        ;;
    *)
        echo "Aura: 不支持的机型 $DEVICE" >&2
        return 1
        ;;
esac
