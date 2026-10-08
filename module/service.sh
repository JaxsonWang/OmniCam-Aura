#!/system/bin/sh

MODDIR=${0%/*}
exec >> "$MODDIR/service.log" 2>&1
mount_state_log() {
    echo "$1"
}
# shellcheck source=module/mount-state.sh
. "$MODDIR/mount-state.sh"
# shellcheck source=module/device.sh
. "$MODDIR/device.sh" || exit 1
if [ ! -f "$MODDIR/mount-ready" ]; then
    echo 'Aura: 配置挂载未完成，请查看 bind.log' >&2
    exit 1
fi
# late_start 晚于 Magic Mount-rs / Hybrid Mount 的挂载阶段。库由元模块提供，
# 此处只核对实际内容；不再把同一文件重复 bind，也不自行创建 ODM 目标文件。
LIBRARY_MOUNTS=
LIBRARY_FAILURE=0
HIDDEN_LIBRARY_MOUNT=0
for LIBRARY in libBasicTonePhotoX9.so libBasicTonePhotoX10.so libBasicTonePhoto.so libAlgoInterface.so libmsnativefilter.so; do
    LIBRARY_SOURCE="$MODDIR/system/odm/lib64/$LIBRARY"
    LIBRARY_TARGET="/odm/lib64/$LIBRARY"
    if mount_entry_owned "$LIBRARY_SOURCE" "$LIBRARY_TARGET"; then
        LIBRARY_MOUNTS="$LIBRARY_SOURCE	$LIBRARY_TARGET
$LIBRARY_MOUNTS"
    elif mount_entry_present "$LIBRARY_SOURCE" "$LIBRARY_TARGET"; then
        echo "Aura: 其他挂载覆盖了本模块算法库，拒绝卸载上层 $LIBRARY_TARGET" >&2
        HIDDEN_LIBRARY_MOUNT=1
    fi
    if ! cmp -s "$LIBRARY_SOURCE" "$LIBRARY_TARGET"; then
        echo "Aura: 元模块未提供匹配的算法库 $LIBRARY" >&2
        LIBRARY_FAILURE=1
    fi
done
if [ "$LIBRARY_FAILURE" -ne 0 ]; then
    CONFIGURATION_MOUNTS=
    ROLLBACK_COMPLETE=1
    if [ "$HIDDEN_LIBRARY_MOUNT" -ne 0 ]; then
        ROLLBACK_COMPLETE=0
    fi
    if [ -s "$MOUNT_STATE_FILE" ]; then
        CONFIGURATION_MOUNTS=$(cat "$MOUNT_STATE_FILE")
    else
        echo 'Aura: 缺少本次配置挂载清单，无法证明配置回滚完整' >&2
        ROLLBACK_COMPLETE=0
    fi
    ROLLBACK_ENTRIES="$LIBRARY_MOUNTS
$CONFIGURATION_MOUNTS"
    if ! rollback_mount_entries "$ROLLBACK_ENTRIES"; then
        ROLLBACK_COMPLETE=0
    fi
    if [ "$ROLLBACK_COMPLETE" -eq 1 ]; then
        rm -f "$MOUNT_STATE_FILE"
    else
        echo 'Aura: 回滚不完整，保留 mounted-targets 供诊断' >&2
    fi
    rm -f "$MODDIR/mount-ready"
    if ! touch "$MODDIR/skip_mount"; then
        echo 'Aura: 无法写入 skip_mount' >&2
    fi
    exit 1
fi
echo "Aura: 配置与元模块算法库已就绪 device=$DEVICE"
APP=/data/user/0/com.oplus.camera
OUT=$APP/files/ricoh_gr/lmt

until [ -d "$APP" ]; do
    sleep 1
done

APP_UID=$(stat -c %u "$APP")
echo "Aura: ODM 配置是功能开关的唯一来源，不写入相机覆盖设置"

mkdir -p "$OUT"
chown "$APP_UID:$APP_UID" "$APP/files"
chmod 0770 "$APP/files"
for ORIGINAL in /odm/etc/camera/basictone/lmt/*; do
    NAME=${ORIGINAL##*/}
    case "$NAME" in
        LMTPhotoLut*|SCLut*)
            # 调色盘 LUT 保留在共享 ODM 目录；GR 使用独立配置。
            continue
            ;;
        SC16*|SC32*|CWCM*)
            cp "$MODDIR/payload/gr_adjustment_lmt/$NAME" "$OUT/$NAME"
            ;;
        *)
            if [ -L "$OUT/$NAME" ]; then rm "$OUT/$NAME"; fi
            if [ -d "$ORIGINAL" ]; then
                mkdir -p "$OUT/$NAME"
                cp -R "$ORIGINAL/." "$OUT/$NAME/"
            else
                cp "$ORIGINAL" "$OUT/$NAME"
            fi
            ;;
    esac
done
chown -R "$APP_UID:$APP_UID" "$APP/files/ricoh_gr"
restorecon -R "$APP/files/ricoh_gr"

# GR watermark fonts: the styles name their fonts by URL, which the camera cannot load. Fonts the
# gallery already downloaded for its watermark editor are copied where the GR hook finds them
# (FZLTZCHK is also in the camera's own files/video_watermark).
GALLERY_FONTS=/data/user/0/com.coloros.gallery3d/files/watermark_master/materia
mkdir -p "$APP/files/jiege/fonts"
for FONT in GilroySemiBold.otf FZLTZCHK.TTF; do
    [ -f "$GALLERY_FONTS/$FONT" ] && ! cmp -s "$GALLERY_FONTS/$FONT" "$APP/files/jiege/fonts/$FONT" && cp "$GALLERY_FONTS/$FONT" "$APP/files/jiege/fonts/$FONT"
done
chown -R "$APP_UID:$APP_UID" "$APP/files/jiege"
chmod 0771 "$APP/files/jiege"
restorecon -R "$APP/files/jiege"

# 先准备 POP 资源，再等待相册，避免相机启动时资源尚未就绪。
ASSET_DIR="$APP/files/pop_port"
PLD_APP="$APP/files/odm/etc/camera/pld_watermark"
# 模式表由相机依据 ODM 中的 db.version 升降级，不删除用户数据库。
mkdir -p "$ASSET_DIR/setting_Retro" "$ASSET_DIR/meishe_lut" "$ASSET_DIR/pld_watermark" "$ASSET_DIR/apk_resources/json" "$ASSET_DIR/apk_resources/img" "$PLD_APP"
cp -f "$MODDIR/payload/setting_Retro/"* "$ASSET_DIR/setting_Retro/"
cp -f "$MODDIR/payload/meishe_lut/"* "$ASSET_DIR/meishe_lut/"
cp -a "$MODDIR/payload/pld_watermark/." "$ASSET_DIR/pld_watermark/"
cp -a "$MODDIR/payload/pld_watermark/." "$PLD_APP/"
cp -a "$MODDIR/payload/apk_resources/." "$ASSET_DIR/apk_resources/"
chown -R "$APP_UID:$APP_UID" "$APP/files/pop_port" "$APP/files/odm"
find "$ASSET_DIR" "$PLD_APP" -type d -exec chmod 0755 {} \;
find "$ASSET_DIR" "$PLD_APP" -type f -exec chmod 0644 {} \;
restorecon -R "$ASSET_DIR" "$APP/files/odm" 2>/dev/null || true

GALLERY=/data/user/0/com.coloros.gallery3d
until [ -d "$GALLERY" ]; do
    sleep 1
done
GALLERY_UID=$(stat -c %u "$GALLERY")
# 相册 GR 开关由 APK Hook 提供，不写入持久 SharedPreferences。
STYLE_OUT="$GALLERY/files/ricoh_gr_styles"
mkdir -p "$STYLE_OUT"
cp "$MODDIR/payload/watermark_master_styles/"*.json "$STYLE_OUT/"
if [ -d "$MODDIR/payload/watermark_drawables" ]; then
    cp "$MODDIR/payload/watermark_drawables/"*.webp "$STYLE_OUT/" 2>/dev/null || true
fi
CAM_ML="$APP/files/mode_limit_watermark"
mkdir -p "$CAM_ML"
for i in 1 2 3 4 5; do
    ID="gr_style_${i}"
    NAME="gr_style_${i}.json"
    JSON="$MODDIR/payload/watermark_master_styles/$NAME"
    if [ -f "$JSON" ]; then
        mkdir -p "$CAM_ML/$ID"
        cp -f "$JSON" "$CAM_ML/$ID/$NAME"
        cp -f "$JSON" "$CAM_ML/$NAME"
        if [ -d "$MODDIR/payload/watermark_drawables" ]; then
            cp -f "$MODDIR/payload/watermark_drawables/"*.webp "$CAM_ML/$ID/" 2>/dev/null || true
        fi
    fi
done
if [ -d "$MODDIR/payload/watermark_drawables" ]; then
    cp -f "$MODDIR/payload/watermark_drawables/"*.webp "$CAM_ML/" 2>/dev/null || true
fi
chown -R "$GALLERY_UID:$GALLERY_UID" "$STYLE_OUT"
chmod 0644 "$STYLE_OUT"/*
restorecon -R "$STYLE_OUT"
chown -R "$APP_UID:$APP_UID" "$CAM_ML"
find "$CAM_ML" -type f -exec chmod 0644 {} \;
find "$CAM_ML" -type d -exec chmod 0755 {} \;
restorecon -R "$CAM_ML"
echo 'Aura: 相机和相册资源准备完成'
