#!/system/bin/sh
# 按机型挂载配置，共享滤镜资源；只有 PMA110 使用随附 ISP 和 Gamma。
MODDIR=${0%/*}
LOG=$MODDIR/bind.log
set -eu

log() {
    echo "$1" >> "$LOG"
}

mount_state_log() {
    log "$1"
}
# shellcheck source=module/mount-state.sh
. "$MODDIR/mount-state.sh"

finish_mounts() {
    RESULT=$?
    [ "$RESULT" -ne 0 ] || return 0
    log "FAILED exit=$RESULT; rolling back configuration mounts"
    if rollback_mount_entries "$MOUNTED_TARGETS" >> "$LOG" 2>&1; then
        rm -f "$MOUNT_STATE_FILE"
    else
        log 'rollback incomplete; mounted-targets retained'
    fi
    # 元模块随后读取此标记，不再叠加与配置不一致的算法库。
    rm -f "$MODDIR/mount-ready"
    touch "$MODDIR/skip_mount"
    trap - EXIT HUP INT TERM
    exit "$RESULT"
}

bind_file() {
    SOURCE="$1"
    TARGET="$2"
    chown root:root "$SOURCE"
    chmod 0644 "$SOURCE"
    chcon u:object_r:vendor_configs_file:s0 "$SOURCE" 2>> "$LOG"
    if mount --bind "$SOURCE" "$TARGET" >> "$LOG" 2>&1; then
        mount_state_record "$SOURCE" "$TARGET"
        log "file bind ok $TARGET"
    else
        log "file bind FAIL $TARGET"
        return 1
    fi
}

label_tree() {
    DIR=$1
    chown -R root:root "$DIR"
    find "$DIR" -type d -exec chmod 0755 {} \;
    find "$DIR" -type f -exec chmod 0644 {} \;
    chcon -R u:object_r:vendor_configs_file:s0 "$DIR" 2>>"$LOG"
}

bind_merged_dir() {
    LIVE=$1
    EXTRA=$2
    DEST=$3
    TARGET=$4
    log "merge $TARGET from $LIVE"
    if [ ! -d "$LIVE" ]; then
        log "missing live $LIVE"
        return 1
    fi
    rm -rf "$DEST"
    mkdir -p "$DEST"
    cp -a "$LIVE"/. "$DEST"/
    if [ -d "$EXTRA" ]; then
        cp -a "$EXTRA"/. "$DEST"/
    fi
    label_tree "$DEST"
    if mount --bind "$DEST" "$TARGET" >> "$LOG" 2>&1; then
        mount_state_record "$DEST" "$TARGET"
        log "dir bind ok $TARGET"
    else
        log "dir bind FAIL $TARGET"
        return 1
    fi
}

: > "$LOG"
rm -f "$MODDIR/mount-ready"
if [ -f "$MODDIR/skip_mount" ]; then
    log '挂载已被阻止，修复原因后请重新安装模块'
    exit 1
fi
mount_state_reset
trap finish_mounts EXIT
trap 'exit 1' HUP INT TERM
# shellcheck source=module/device.sh
if ! . "$MODDIR/device.sh" >> "$LOG" 2>&1; then
    # 元模块随后才读取 skip_mount，阻止固件更新后自动覆盖原厂算法库。
    exit 1
fi
log "begin device=$DEVICE"
# shellcheck source=module/inverse-light.sh
. "$MODDIR/inverse-light.sh"
prepare_inverse_light_config /data/adb/omnicam_aura/inverse-light >> "$LOG" 2>&1

for SOURCE in "$CONFIG_DIR"/*; do
    [ -f "$SOURCE" ] || continue
    NAME=${SOURCE##*/}
    if [ "$NAME" = oplus_camera_config ]; then SOURCE=$CAMERA_CONFIG_SOURCE; fi
    case "$NAME" in
        camera_unit_config|camera_unit_feature_config.protobuf|oplus_camera_config|oplus_camera_algo_switch_config|oplus_camera_aps_config|oplus_camera_preview_decision_config.json)
            bind_file "$SOURCE" "/odm/etc/camera/config/$NAME"
            ;;
    esac
done

bind_merged_dir /odm/etc/camera/meishe_lut "$MODDIR/payload/meishe_lut" "$MODDIR/merged/meishe_lut" /odm/etc/camera/meishe_lut

BT_EXTRA=$MODDIR/merged/basictone_extra
rm -rf "$BT_EXTRA"
mkdir -p "$BT_EXTRA/setting_Retro"
if [ -d "$MODDIR/payload/setting_Retro" ]; then
    cp -a "$MODDIR/payload/setting_Retro"/. "$BT_EXTRA/setting_Retro"/
fi
cp -a "$MODDIR/payload/x10_basictone"/. "$BT_EXTRA"/
bind_merged_dir /odm/etc/camera/basictone "$BT_EXTRA" "$MODDIR/merged/basictone" /odm/etc/camera/basictone

log "polaroid=$(ls -l /odm/etc/camera/meishe_lut/polaroid_sdr.mslut 2>&1)"
log "host_film=$(ls -l /odm/etc/camera/meishe_lut/fuji-nc.bin 2>&1)"
log "retro_ini=$(ls -l /odm/etc/camera/basictone/setting_Retro/SimTool_Master.ini 2>&1)"
log "host_setting=$(ls -d /odm/etc/camera/basictone/setting 2>&1)"

if [ "$BIND_ISP" -eq 1 ]; then
  for LENS in main wide tele ultratele; do
    NAME="com.qti.tuned.lighthouse${LENS}.bin"
    SOURCE="$MODDIR/payload/isp/$NAME"
    TARGET="/odm/lib64/camera/$NAME"
    chown root:root "$SOURCE"
    chmod 0644 "$SOURCE"
    chcon u:object_r:vendor_file:s0 "$SOURCE" 2>>"$LOG"
    if mount --bind "$SOURCE" "$TARGET" >>"$LOG" 2>&1; then
        mount_state_record "$SOURCE" "$TARGET"
        log "isp bind ok $TARGET"
    else
        log "isp bind FAIL $TARGET"
        exit 1
    fi
  done
fi
if [ "$BIND_GAMMA" -eq 1 ]; then
  for NAME in gamma_preview_sdr_conf.json gamma_quick_sdr_conf.json gamma_preview_hdr_conf.json; do
    bind_file "$MODDIR/payload/gamma/$NAME" "/odm/etc/camera/$NAME"
  done
fi
# 此标记只表示本脚本的配置挂载全部完成；算法库随后由挂载元模块提供。
touch "$MODDIR/mount-ready"
log "end"
