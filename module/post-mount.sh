#!/system/bin/sh
set -eu
MODDIR=${0%/*}
exec >> "$MODDIR/bind.log" 2>&1
# shellcheck source=module/device.sh
. "$MODDIR/device.sh"
[ ! -f "$MODDIR/skip_mount" ] || exit 1

bind_library() {
    NAME=$1
    SOURCE="$MODDIR/system/odm/lib64/$NAME"
    TARGET="/odm/lib64/$NAME"
    test -f "$SOURCE"
    test -f "$TARGET"
    chown root:root "$SOURCE"
    chmod 0644 "$SOURCE"
    chcon u:object_r:same_process_hal_file:s0 "$SOURCE"
    mount --bind "$SOURCE" "$TARGET"
}

# KernelSU 在挂载元模块完成后执行此阶段，支持 Magic Mount-rs 和 Hybrid Mount。
bind_library libBasicTonePhotoX9.so
bind_library libBasicTonePhotoX10.so
bind_library libBasicTonePhoto.so
bind_library libAlgoInterface.so
bind_library libmsnativefilter.so
touch "$MODDIR/mount-ready"
echo "libraries ready device=$DEVICE"
