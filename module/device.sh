#!/system/bin/sh
# 由 config/supported-devices.json 生成；通过 tools/generate_device_policy.py 更新。
# shellcheck disable=SC2034
# 仅允许同分支的数字补丁号，不把未知主版本当作已兼容。
aura_match_patch_version() {
    case "$1" in "$2"*"$3") ;; *) return 1 ;; esac
    AURA_PATCH=${1#"$2"}
    AURA_PATCH=${AURA_PATCH%"$3"}
    case "$AURA_PATCH" in ''|*[!0-9]*) return 1 ;; esac
}

camera_version_matches() {
    case "$DEVICE" in
        PMA110) [ "$1" = 7.006.77 ] ;;
        PLK110) aura_match_patch_version "$1" 7.006. '' ;;
        *) return 1 ;;
    esac
}

DEVICE=$(getprop ro.product.model)
FIRMWARE=$(getprop ro.build.display.id)
ANDROID_SDK=$(getprop ro.build.version.sdk)
DEVICE_POLICY_ERROR=
case "$DEVICE" in
    PMA110)
        CAMERA_VERSION=7.006.77
        CONFIG_DIR="$MODDIR/"payload
        BIND_ISP=1
        BIND_GAMMA=1
        ;;
    PLK110)
        CAMERA_VERSION='7.006.*'
        if ! aura_match_patch_version "$FIRMWARE" PLK110_17.0.0. '(CN01)'; then
            DEVICE_POLICY_ERROR="系统分支不兼容: $FIRMWARE"
            echo "Aura: $DEVICE_POLICY_ERROR" >&2
            return 1
        fi
        if [ "$ANDROID_SDK" != 37 ]; then
            DEVICE_POLICY_ERROR="Android API 不兼容: $ANDROID_SDK"
            echo "Aura: $DEVICE_POLICY_ERROR" >&2
            return 1
        fi
        CONFIG_DIR="$MODDIR/"profiles/PLK110/config
        BIND_ISP=0
        BIND_GAMMA=0
        ;;
    *)
        DEVICE_POLICY_ERROR="不支持的机型: $DEVICE"
        echo "Aura: $DEVICE_POLICY_ERROR" >&2
        return 1
        ;;
esac
