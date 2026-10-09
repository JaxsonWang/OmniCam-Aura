#!/system/bin/sh
# 只导出诊断所需的白名单信息；原始日志不落盘，不读取照片、账户或应用设置。
set -eu
umask 077

fail() {
    printf 'Aura 诊断导出失败：%s\n' "$1" >&2
    exit 1
}

MODDIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd -P)
OUTPUT_DIR=/sdcard/Download/OmniCam-Aura
while [ "$#" -gt 0 ]; do
    case "$1" in
        --module-dir|--output-dir)
            [ "$#" -ge 2 ] && [ -n "$2" ] || fail "参数 $1 缺少目录"
            case "$1" in
                --module-dir) MODDIR=$2 ;;
                --output-dir) OUTPUT_DIR=$2 ;;
            esac
            shift 2
            ;;
        *) fail "不支持的参数：$1" ;;
    esac
done
[ -d "$MODDIR" ] || fail '模块目录不存在'
MODDIR=$(CDPATH='' cd -- "$MODDIR" && pwd -P) || fail '无法访问模块目录'
mkdir -p -- "$OUTPUT_DIR" || fail '无法创建导出目录'
OUTPUT_DIR=$(CDPATH='' cd -- "$OUTPUT_DIR" && pwd -P) || fail '无法访问导出目录'

# 临时工作区留在 root 私有模块目录；共享存储只出现已经过滤的成品。
WORK=$(mktemp -d "$MODDIR/.diagnostics.XXXXXXXX") || fail '无法创建私有临时目录'
FINAL=
PUBLISHED=0
cleanup() {
    RESULT=$?
    trap - EXIT HUP INT TERM
    if [ "$PUBLISHED" -eq 0 ] && [ -n "$FINAL" ]; then rm -f -- "$FINAL"; fi
    rm -rf -- "$WORK"
    exit "$RESULT"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
REPORT="$WORK/report"
mkdir "$REPORT" || fail '无法创建报告目录'

cat > "$WORK/filter.awk" <<'AWK'
function scrub(s, low) {
    low = tolower(s)
    # 自由文本中的敏感键不保留值，也不猜测其具体格式。
    if (low ~ /token|authorization|password|passwd|cookie|account|email|e-mail|imei|imsi|serial|android_id|advertising_id|latitude|longitude|gps|location[=:]|(^|[^[:alpha:]])lat[=:]|(^|[^[:alpha:]])lon[=:]|联系人|账号|帐户|经纬度/)
        return "[已移除含敏感字段的日志行]"
    gsub(/[[:alnum:]_.+-]+@[[:alnum:]_.-]+\.[[:alpha:]]+/, "[EMAIL]", s)
    gsub(/[[:alpha:]][[:alnum:]+.-]*:\/\/[^[:space:]<>"\047]+/, "[URI]", s)
    # 文件名可以带空格，因此从私有路径起移除行尾，避免漏出后半段名称。
    gsub(/\/(sdcard|storage|mnt\/media_rw|data\/user|data\/user_de|data\/data)\/.*/, "[PRIVATE_PATH]", s)
    gsub(/[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+(:[0-9]+)?/, "[IP]", s)
    # IPv6、MAC 和设备标识可能没有字段名；移除独立的多段十六进制地址。
    gsub(/[[:xdigit:]]+:[[:xdigit:]]+:[[:xdigit:]]+:[[:xdigit:]:]+/, "[NETWORK_ADDRESS]", s)
    gsub(/[[:xdigit:]:]*::[[:xdigit:]:]+/, "[NETWORK_ADDRESS]", s)
    gsub(/[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]*/, "[IDENTIFIER]", s)
    gsub(/[[:alnum:]_-]+\.(jpg|jpeg|heic|heif|png|mp4|JPG|JPEG|HEIC|HEIF|PNG|MP4)/, "[MEDIA_FILE]", s)
    return substr(s, 1, 2048)
}
function wanted(s) {
    return s ~ /(^|[^[:alnum:]_.])(com\.oplus\.camera|com\.coloros\.gallery3d|local\.omnicam\.aura)([^[:alnum:]_.]|$)/
}
{
    keep = 1
    if (mode == "lsposed") keep = $0 ~ /(^|[^[:alnum:]_.])local\.omnicam\.aura([^[:alnum:]_.]|$)/
    if (mode == "mount") keep = index($4, "/adb/modules/omnicam_aura/") || index($4, "/adb/modules_update/omnicam_aura/") || index($4, module "/") == 1
    if (mode == "version") keep = $0 ~ /^[[:space:]]*version(Name|Code)=/
    if (mode == "crash") {
        # threadtime 的 PID 是第三列。只保留明确标注目标进程的同一崩溃记录。
        if ($0 ~ /FATAL EXCEPTION:|\*\*\* \*\*\* \*\*\*|Process:|>>>/) {
            active = wanted($0)
            crash_pid = $3
        }
        keep = wanted($0) || (active && $3 == crash_pid && $0 ~ / (AndroidRuntime|DEBUG)[[:space:]]*:/)
    }
    if (mode == "version") sub(/^[[:space:]]+/, "", $0)
    if (keep) {
        # versionCode 后面还带平台字段；清除前导空白后只保留版本本身。
        if (mode == "version") {
            line = $0
            sub(/[[:space:]]+.*$/, "", line)
            line = scrub(line)
        } else line = scrub($0)
        lines[count % limit] = line
        count++
    }
}
END {
    if (!count) print "没有匹配记录。"
    begin = count > limit ? count - limit : 0
    for (i = begin; i < count; i++) print lines[i % limit]
}
AWK

# 所有读取的退出码独立于过滤管道保存，避免把读取失败当成空日志。
capture() {
    NAME=$1
    MODE=$2
    LIMIT=$3
    shift 3
    (
        if "$@" 2> "$WORK/read.err"; then READ_RESULT=0; else READ_RESULT=$?; fi
        printf '%s\n' "$READ_RESULT" > "$WORK/read.status"
    ) | awk -v mode="$MODE" -v limit="$LIMIT" -v module="$MODDIR" -f "$WORK/filter.awk" > "$REPORT/$NAME" || fail '日志过滤或报告写入失败'
    [ -s "$WORK/read.status" ] || fail '无法确定诊断源读取结果'
    READ_RESULT=$(cat "$WORK/read.status")
    if [ "$READ_RESULT" -ne 0 ]; then
        printf '不可用（读取失败，exit=%s）。\n' "$READ_RESULT" > "$REPORT/$NAME" || fail '无法写入诊断状态'
        awk -v limit=5 -f "$WORK/filter.awk" "$WORK/read.err" >> "$REPORT/$NAME" || fail '无法写入诊断错误'
    fi
}

cat > "$REPORT/阅读说明.txt" <<'EOF'
OmniCam Aura 本地诊断包

此包由用户主动导出，没有自动上传。分享前请自行解压检查。
仅包含白名单系统属性、相机/相册/Aura 版本、模块配置与挂载状态、最近的模块日志、
LSPosed 中 Aura 模块的日志、当前相机/相册/Aura 进程的警告与错误，以及匹配这些包的崩溃片段。
没有读取照片、应用偏好设置、账户列表、完整系统属性或完整应用列表。
日志中的敏感字段行、共享存储路径、用户数据路径、URI、网络地址和媒体文件名已过滤。
自动过滤无法保证识别所有自由文本个人信息；请检查内容后再自行分享。
每行最多 2048 字符；模块日志最多 250 行/最近 96 KiB；LSPosed 最多 400 行/最近 256 KiB；
每个进程日志最多 300 行；崩溃缓冲区读取最近 600 行，只保留匹配目标的记录。
“不可用”表示读取失败、源不存在或应用未运行，不能据此认定功能正常。
EOF

{
    for PROPERTY in ro.product.model ro.product.device ro.product.manufacturer ro.build.version.release ro.build.version.sdk ro.build.display.id ro.build.version.security_patch; do
        if VALUE=$(getprop "$PROPERTY" 2>/dev/null); then
            printf '%s=%s\n' "$PROPERTY" "${VALUE:-不可用（空值）}"
        else
            printf '%s=不可用（读取失败）\n' "$PROPERTY"
        fi
    done
} > "$REPORT/device.txt" || fail '无法写入设备信息'

for PACKAGE in com.oplus.camera com.coloros.gallery3d local.omnicam.aura; do
    capture "version-$PACKAGE.txt" version 2 dumpsys package "$PACKAGE"
done
capture module.prop plain 30 cat "$MODDIR/module.prop"
for LOG in bind service; do
    capture "$LOG.log" plain 250 tail -c 98304 "$MODDIR/$LOG.log"
done
{
    for FLAG in skip_mount mount-ready disable remove; do
        if [ -e "$MODDIR/$FLAG" ]; then VALUE=present; else VALUE=absent; fi
        printf '%s=%s\n' "$FLAG" "$VALUE"
    done
} > "$REPORT/module-state.txt" || fail '无法写入模块状态'
capture control-status.txt plain 12 sh "$MODDIR/control.sh" status
capture mounts.txt mount 100 cat /proc/self/mountinfo

LATEST=
for LOG in /data/adb/lspd/log/modules_*.log /data/adb/lspd/log/modules.log; do
    [ -f "$LOG" ] || continue
    if [ -z "$LATEST" ] || [ "$LOG" -nt "$LATEST" ]; then LATEST=$LOG; fi
done
if [ -n "$LATEST" ]; then
    capture lsposed.log lsposed 400 tail -c 262144 "$LATEST"
else
    printf '不可用（未找到当前 LSPosed 模块日志）。\n' > "$REPORT/lsposed.log"
fi

for PACKAGE in com.oplus.camera com.coloros.gallery3d local.omnicam.aura; do
    if PIDS=$(pidof "$PACKAGE" 2>/dev/null) && [ -n "$PIDS" ]; then
        case "$PIDS" in *[!0-9\ ]*) fail '进程查询返回了无效 PID' ;; esac
        for PID in $PIDS; do
            capture "logcat-$PACKAGE-$PID.log" plain 300 logcat -d -v threadtime -t 300 -b main -b system --pid="$PID" '*:W' Aura:V OmniCamAura:V RicohGrPort:V PopPort:V
        done
    else
        printf '不可用（应用未运行或无法查询进程）。\n' > "$REPORT/logcat-$PACKAGE.log"
    fi
done
capture crashes.log crash 300 logcat -d -v threadtime -t 600 -b crash '*:V'

# tar 与 gzip 分开执行，任一步失败都不会留下可误认成品的命名文件。
tar -cf "$WORK/report.tar" -C "$WORK" report 2> "$WORK/archive.err" || fail 'tar 归档失败'
gzip -c "$WORK/report.tar" > "$WORK/report.tar.gz" 2> "$WORK/archive.err" || fail 'gzip 压缩失败'
[ -s "$WORK/report.tar.gz" ] || fail '归档文件为空'
STAMP=$(date '+%Y%m%d-%H%M%S') || fail '无法读取导出时间'
CANDIDATE="$OUTPUT_DIR/OmniCam-Aura-$STAMP-${WORK##*.diagnostics.}.tar.gz"
# 复用 mktemp 的随机后缀；noclobber 原子占位，不覆盖同名用户文件。
(set -C; : > "$CANDIDATE") 2>/dev/null || fail '无法为诊断包保留唯一文件名'
FINAL=$CANDIDATE
cp -- "$WORK/report.tar.gz" "$FINAL" || fail '无法写入诊断包'
PUBLISHED=1
printf '%s\n' "$FINAL"
