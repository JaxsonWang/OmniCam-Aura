#!/system/bin/sh
# 仅在用户主动选择后生成运行时 ODM 配置；不修改发行配置、应用 prefs 或 Java 缓存。
prepare_inverse_light_config() {
    INVERSE_STATE=$1
    CAMERA_CONFIG_SOURCE="$CONFIG_DIR/oplus_camera_config"
    [ "$DEVICE" = PLK110 ] || return 0
    [ -f "$INVERSE_STATE" ] || return 0
    case "$(cat "$INVERSE_STATE")" in
        0) return 0 ;;
        1) ;;
        *) echo 'Aura: 反色补光开关值无效，停止挂载' >&2; return 1 ;;
    esac
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
