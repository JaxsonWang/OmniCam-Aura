#!/system/bin/sh
# 记录本次启动由 Aura 自己创建的 bind，并只撤销当前最上层仍属于 Aura 的挂载。

MOUNT_STATE_FILE=$MODDIR/mounted-targets
MOUNTED_TARGETS=

mount_state_reset() {
    rm -f "$MOUNT_STATE_FILE" "$MOUNT_STATE_FILE.tmp"
    MOUNTED_TARGETS=
}

mount_state_record() {
    MOUNT_SOURCE=$1
    MOUNT_TARGET=$2
    MOUNTED_TARGETS="$MOUNT_SOURCE	$MOUNT_TARGET
$MOUNTED_TARGETS"
    printf '%s' "$MOUNTED_TARGETS" > "$MOUNT_STATE_FILE.tmp" || return 1
    mv "$MOUNT_STATE_FILE.tmp" "$MOUNT_STATE_FILE"
}

mount_entry_owned() {
    MOUNT_SOURCE=$1
    MOUNT_TARGET=$2
    # /data 是独立文件系统时 mountinfo 的 root 省略 /data；同时接受完整 root。
    MOUNT_ROOT=${MOUNT_SOURCE#/data}
    awk -v source="$MOUNT_SOURCE" -v root="$MOUNT_ROOT" -v target="$MOUNT_TARGET" '
        $5 == target {
            roots[$1] = $4
            parents[$2] = 1
        }
        END {
            for (id in roots) {
                if (!(id in parents)) {
                    top_count++
                    top_root = roots[id]
                }
            }
            exit !(top_count == 1 && (top_root == source || top_root == root))
        }
    ' /proc/self/mountinfo
}

mount_entry_present() {
    MOUNT_SOURCE=$1
    MOUNT_TARGET=$2
    MOUNT_ROOT=${MOUNT_SOURCE#/data}
    awk -v source="$MOUNT_SOURCE" -v root="$MOUNT_ROOT" -v target="$MOUNT_TARGET" '
        $5 == target && ($4 == source || $4 == root) { found = 1 }
        END { exit !found }
    ' /proc/self/mountinfo
}

rollback_mount_entries() {
    ROLLBACK_ENTRIES=$1
    ROLLBACK_FAILED=0
    while IFS='	' read -r MOUNT_SOURCE MOUNT_TARGET; do
        [ -n "$MOUNT_SOURCE" ] || continue
        if ! mount_entry_owned "$MOUNT_SOURCE" "$MOUNT_TARGET"; then
            mount_state_log "rollback REFUSED unowned $MOUNT_TARGET"
            ROLLBACK_FAILED=1
            continue
        fi
        if umount "$MOUNT_TARGET"; then
            mount_state_log "rollback ok $MOUNT_TARGET"
        else
            mount_state_log "rollback FAIL $MOUNT_TARGET"
            ROLLBACK_FAILED=1
        fi
    done <<EOF
$ROLLBACK_ENTRIES
EOF
    [ "$ROLLBACK_FAILED" -eq 0 ]
}
