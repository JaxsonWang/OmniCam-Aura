#!/system/bin/sh
# 安装时撤销旧版曾写入的键；新版本由 ODM 或 APK Hook 提供功能配置。
clear_legacy_overrides() (
    PREF_FILE=$1
    STATE_DIR=$2
    PACKAGE=$3
    OVERRIDE_KIND=$4
    SNAPSHOT_PREFIX=$5
    [ -f "$PREF_FILE" ] || return 0
    am force-stop "$PACKAGE" || return 1
    CLEAN_FILE=$(mktemp "$PREF_FILE.aura.XXXXXX") || return 1
    trap 'rm -f "$CLEAN_FILE"' EXIT
    cp -p "$PREF_FILE" "$CLEAN_FILE" || return 1
    # SharedPreferences 和旧版 service 均按单行元素写入；不接受未知格式后继续安装。
    if ! awk -v override_kind="$OVERRIDE_KIND" '
        BEGIN {
            keys["com.oplus.gr.mode.support"] = 1
            keys["com.oplus.camera.mode.data.db.version"] = 1
            keys["com.oplus.available.gr.mode.zoomvalues"] = 1
            keys["com.oplus.gr.mode.marked.zoomvalues"] = 1
            keys["com.oplus.camera.capture.hdr.cap.mode.value"] = 1
            keys["com.oplus.camera.preview.hdr.cap.mode.value"] = 1
            keys["com.oplus.feature.retro.camera.support"] = 1
            keys["com.oplus.flashlevel.configurable.support"] = 1
            keys["com.oplus.feature.tilt.shift.photo.support"] = 1
            keys["com.oplus.feature.colorful.screen.torch.config"] = 1
        }
        {
            if (override_kind == "camera") {
                for (key in keys) {
                    if (!index($0, "name=\"" key "\"")) continue
                    if ($0 !~ /^[[:space:]]*<string name="[^"]*">[^<]*<\/string>[[:space:]]*$/) exit 2
                    next
                }
            } else if (override_kind == "gallery" &&
                       index($0, "name=\"business_featureSwitch_is_camera_gr_supported\"")) {
                if ($0 !~ /^[[:space:]]*<boolean name="business_featureSwitch_is_camera_gr_supported" value="(true|false)"[[:space:]]*\/>[[:space:]]*$/) exit 2
                next
            }
            print
        }
    ' "$PREF_FILE" > "$CLEAN_FILE"; then
        echo 'Aura: 旧覆盖设置格式异常，未修改原文件' >&2
        rm -f "$CLEAN_FILE"
        return 1
    fi
    if cmp -s "$PREF_FILE" "$CLEAN_FILE"; then
        rm -f "$CLEAN_FILE"
        return 0
    fi
    # 先在临时文件上确认最终上下文，失败时原文件仍保持原位。
    restorecon "$CLEAN_FILE" || return 1
    mkdir -p "$STATE_DIR" || return 1
    chmod 0700 "$STATE_DIR" || return 1
    BACKUP_FILE=$(mktemp "$STATE_DIR/$SNAPSHOT_PREFIX.XXXXXX") || return 1
    # 这是清理前快照，不冒充原厂设置；位于模块目录之外，更新不会删除。
    if ! cp -p "$PREF_FILE" "$BACKUP_FILE"; then
        rm -f "$BACKUP_FILE"
        return 1
    fi
    mv "$CLEAN_FILE" "$PREF_FILE" || return 1
    echo "Aura: 已撤销旧覆盖键；清理前快照: $BACKUP_FILE"
)

clear_camera_overrides() {
    clear_legacy_overrides "$1" "$2" com.oplus.camera camera legacy-overrides
}

clear_gallery_overrides() {
    clear_legacy_overrides "$1" "$2" com.coloros.gallery3d gallery legacy-gallery-overrides
}
