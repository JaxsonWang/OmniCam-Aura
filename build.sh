#!/bin/sh
# macOS / Linux 构建入口，版本与打包校验统一由 Python 脚本管理。
set -eu

PROJECT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
PYTHON=${OMNICAM_PYTHON:-python3}
exec "$PYTHON" "$PROJECT_DIR/tools/build_release.py" "$@"
