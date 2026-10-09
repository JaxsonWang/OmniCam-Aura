#!/system/bin/sh
# 管理器的旧“操作”入口沿用同一套校验和持久化；网页使用明确的 on/off 命令。
set -eu
MODDIR=${0%/*}
exec sh "$MODDIR/control.sh" toggle
