#!/system/bin/sh
set -eu
MODDIR=${0%/*}
# shellcheck source=module/device.sh
. "$MODDIR/device.sh"
if [ "$DEVICE" != PLK110 ]; then
    echo '此手动反色补光开关仅用于 PLK110，PMA110 保持原有设置。'
    exit 1
fi
STATE_DIR=/data/adb/omnicam_aura
STATE="$STATE_DIR/inverse-light"
ENABLED=0
if [ -f "$STATE" ]; then ENABLED=$(cat "$STATE"); fi
case "$ENABLED" in
    0) NEXT=1; DESCRIPTION='已选择开启：重启后前置闪光选项与低光补光由厂商反色逻辑控制' ;;
    1) NEXT=0; DESCRIPTION='已选择关闭：重启后恢复原厂前置闪光行为' ;;
    *) echo '反色补光开关值无效，未修改设置' >&2; exit 1 ;;
esac
mkdir -p "$STATE_DIR"
chmod 0700 "$STATE_DIR"
umask 077
printf '%s\n' "$NEXT" > "$STATE.tmp"
mv "$STATE.tmp" "$STATE"
echo "$DESCRIPTION"
echo '请重启设备使选择生效。再次执行模块操作可反向切换。POP 不依赖此开关。'
