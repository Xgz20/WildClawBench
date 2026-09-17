#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DRIVER_DIR="$(cd "$SCRIPT_DIR/../drivers/codex-desktop" && pwd)"

if [ ! -d "$DRIVER_DIR/node_modules/playwright-core" ]; then
  echo "尚未安装依赖，请先执行：" >&2
  echo "  cd $DRIVER_DIR && npm ci" >&2
  exit 2
fi

exec node "$DRIVER_DIR/register-projects.mjs" "$@"

