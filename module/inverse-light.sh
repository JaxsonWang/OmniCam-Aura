#!/system/bin/sh
# 仅在用户主动选择后生成运行时 ODM 配置；不修改发行配置、应用 prefs 或 Java 缓存。
read_inverse_light_state() {
    INVERSE_ENABLED=0
    if [ ! -e "$1" ] && [ ! -L "$1" ]; then return 0; fi
    if [ ! -f "$1" ]; then
        echo 'Aura: 无法读取反色补光开关，停止挂载或操作' >&2
        return 1
    fi
    INVERSE_BYTES=$(od -An -v -tu1 "$1") || return 1
    if ! INVERSE_ENABLED=$(printf '%s\n' "$INVERSE_BYTES" | awk '
        {
            for (i = 1; i <= NF; i++) {
                count++
                if (count == 1 && ($i == 48 || $i == 49)) value = $i - 48
                else if (count != 2 || $i != 10) invalid = 1
            }
        }
        END { if (count < 1 || invalid) exit 1; print value }
    '); then
        echo 'Aura: 反色补光开关值无效或无法读取，停止挂载或操作' >&2
        return 1
    fi
}

save_inverse_light_state() {
    INVERSE_STATE=$1
    INVERSE_NEXT=$2
    case "$INVERSE_NEXT" in
        0|1) ;;
        *) echo 'Aura: 反色补光目标值无效，未修改设置' >&2; return 1 ;;
    esac
    read_inverse_light_state "$INVERSE_STATE" || return 1
    INVERSE_STATE_DIR=${INVERSE_STATE%/*}
    if ! mkdir -p "$INVERSE_STATE_DIR" || ! chmod 0700 "$INVERSE_STATE_DIR"; then
        echo 'Aura: 无法创建反色补光设置目录' >&2
        return 1
    fi
    umask 077
    INVERSE_TEMP=$(mktemp "$INVERSE_STATE_DIR/.inverse-light.XXXXXX") || return 1
    if ! printf '%s\n' "$INVERSE_NEXT" > "$INVERSE_TEMP" ||
        ! mv -f "$INVERSE_TEMP" "$INVERSE_STATE"; then
        rm -f "$INVERSE_TEMP"
        echo 'Aura: 无法保存反色补光选择，原设置未改变' >&2
        return 1
    fi
    INVERSE_ENABLED=$INVERSE_NEXT
}

prepare_inverse_light_config() {
    INVERSE_STATE=$1
    CAMERA_CONFIG_SOURCE="$CONFIG_DIR/oplus_camera_config"
    [ "$DEVICE" = PLK110 ] || return 0
    read_inverse_light_state "$INVERSE_STATE" || return 1
    [ "$INVERSE_ENABLED" = 1 ] || return 0
    if grep -q 'com.oplus.feature.colorful.screen.torch.config' "$CAMERA_CONFIG_SOURCE"; then
        echo 'Aura: 默认 PLK110 配置出现非原厂补光键，停止挂载' >&2
        return 1
    fi
    mkdir -p "$MODDIR/runtime" || return 1
    # 原厂按二进制字符串解析该键；100 只表示位 4，不能写成十进制字符串 4。
    awk '
        NR > 1 { print previous }
        { previous = $0 }
        END {
            if (previous != "]") exit 2
            print ", {\"VendorTag\":\"com.oplus.feature.colorful.screen.torch.config\",\"Type\":\"String\",\"Count\":\"1\",\"Value\":\"100\"}"
            print "]"
        }
    ' "$CAMERA_CONFIG_SOURCE" > "$MODDIR/runtime/oplus_camera_config" || return 1
    CAMERA_CONFIG_SOURCE="$MODDIR/runtime/oplus_camera_config"
    echo 'Aura: 用户已手动启用反色补光；使用原厂反色补光逻辑'
}
