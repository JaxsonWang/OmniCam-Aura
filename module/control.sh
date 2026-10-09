#!/system/bin/sh
# 模块网页的固定命令入口；选择值与实际挂载状态分别报告。
set -eu
MODDIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd -P)
STATE_DIR=/data/adb/omnicam_aura
STATE="$STATE_DIR/inverse-light"

fail() {
    printf 'Aura: %s\n' "$1" >&2
    exit 1
}

case "${1-}" in
    status|toggle) [ "$#" -eq 1 ] || fail '命令参数无效' ;;
    inverse)
        [ "$#" -eq 2 ] || fail '补光命令需要 on 或 off'
        case "$2" in on|off) ;; *) fail '补光命令需要 on 或 off' ;; esac
        ;;
    *) fail '仅支持 status、inverse on、inverse off 或 toggle' ;;
esac
COMMAND=$1

compatibility_error() {
    COMPATIBLE=false
    REASON="${REASON:+${REASON}；}$1"
}

COMPATIBLE=true
REASON=
DEVICE=
FIRMWARE=
ANDROID_SDK=
CONFIG_DIR=
DEVICE_POLICY_ERROR=
if [ -f "$MODDIR/device.sh" ] && [ -r "$MODDIR/device.sh" ]; then
    # shellcheck source=module/device.sh
    if ! . "$MODDIR/device.sh"; then
        compatibility_error "${DEVICE_POLICY_ERROR:-设备兼容策略读取失败}"
    fi
else
    DEVICE=$(getprop ro.product.model) || fail '无法读取机型'
    FIRMWARE=$(getprop ro.build.display.id) || fail '无法读取系统版本'
    ANDROID_SDK=$(getprop ro.build.version.sdk) || fail '无法读取 Android API'
    compatibility_error '设备兼容策略文件不可读'
fi

CAMERA_ACTUAL=
if CAMERA_DUMP=$(dumpsys package com.oplus.camera); then
    CAMERA_ACTUAL=$(printf '%s\n' "$CAMERA_DUMP" | awk '
        /^[[:space:]]*versionName=/ { sub(/^[[:space:]]*versionName=/, ""); print; exit }
    ')
    if [ -z "$CAMERA_ACTUAL" ]; then
        compatibility_error '无法读取相机版本'
    elif [ "$COMPATIBLE" = true ] && ! camera_version_matches "$CAMERA_ACTUAL"; then
        compatibility_error "相机版本不兼容: $CAMERA_ACTUAL"
    fi
else
    compatibility_error '相机版本读取失败'
fi
if [ "$COMPATIBLE" = true ]; then
    REASON='版本范围内；功能仍按运行时合同检查'
fi
MODULE_VERSION=$(sed -n 's/^version=//p' "$MODDIR/module.prop") || fail '无法读取模块版本'
[ -n "$MODULE_VERSION" ] || fail '模块版本缺失'

# shellcheck source=module/inverse-light.sh
. "$MODDIR/inverse-light.sh"
read_inverse_light_state "$STATE" || exit 1

if [ "$COMMAND" != status ]; then
    [ "$DEVICE" = PLK110 ] || fail '此手动反色补光开关仅用于 PLK110'
    if [ "$COMMAND" = toggle ]; then
        NEXT=$((1 - INVERSE_ENABLED))
    elif [ "$2" = on ]; then
        NEXT=1
    else
        NEXT=0
    fi
    if [ "$NEXT" = 1 ] && [ "$COMPATIBLE" != true ]; then
        fail "当前版本不能启用反色补光：$REASON"
    fi
    save_inverse_light_state "$STATE" "$NEXT" || exit 1
fi

if [ "$COMMAND" = toggle ]; then
    if [ "$INVERSE_ENABLED" = 1 ]; then
        echo '已选择开启：重启后前置闪光选项与低光补光由厂商反色逻辑控制'
    else
        echo '已选择关闭：重启后恢复原厂前置闪光行为'
    fi
    echo '请重启设备使选择生效。再次执行模块操作可反向切换。POP 不依赖此开关。'
    exit 0
fi

ACTIVE_INVERSE=null
LIVE_CONFIG=/odm/etc/camera/config/oplus_camera_config
if [ "$DEVICE" = PLK110 ] && [ -f "$MODDIR/mount-ready" ] &&
    [ -n "$CONFIG_DIR" ] && [ -r "$LIVE_CONFIG" ] &&
    awk -v target="$LIVE_CONFIG" '$5 == target { found = 1 } END { exit !found }' /proc/self/mountinfo; then
    if [ -f "$MODDIR/runtime/oplus_camera_config" ] &&
        cmp -s "$LIVE_CONFIG" "$MODDIR/runtime/oplus_camera_config"; then
        ACTIVE_INVERSE=true
    elif cmp -s "$LIVE_CONFIG" "$CONFIG_DIR/oplus_camera_config"; then
        ACTIVE_INVERSE=false
    fi
fi

# 按字节转义全部 JSON 控制字符，保留 UTF-8；不把设备信息当作 Shell 或 JSON 代码。
json_string() {
    printf '%s' "$1" | od -An -v -tu1 | LC_ALL=C awk '
        BEGIN { printf "\"" }
        {
            for (i = 1; i <= NF; i++) {
                if ($i == 34) printf "\\\""
                else if ($i == 92) printf "\\\\"
                else if ($i < 32) printf "\\u%04x", $i
                else printf "%c", $i
            }
        }
        END { printf "\"" }
    '
}
INVERSE_JSON=false
[ "$INVERSE_ENABLED" != 1 ] || INVERSE_JSON=true
printf '{"model":%s,"androidSdk":%s,"firmware":%s,"cameraVersion":%s,"moduleVersion":%s,"compatible":%s,"reason":%s,"inverseLight":%s,"activeInverseLight":%s}\n' \
    "$(json_string "$DEVICE")" "$(json_string "$ANDROID_SDK")" "$(json_string "$FIRMWARE")" \
    "$(json_string "$CAMERA_ACTUAL")" "$(json_string "$MODULE_VERSION")" "$COMPATIBLE" \
    "$(json_string "$REASON")" "$INVERSE_JSON" "$ACTIVE_INVERSE"
