#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DRIVER_DIR="$(cd "$SCRIPT_DIR/../drivers/workbuddy" && pwd)"

if [ $# -eq 0 ]; then
  echo "用法: bash .agents/skills/execute-web-e2e/scripts/run-workbuddy-batch.sh <Harness 根目录> --run-id <ID> --task-id <ID> [--task-id <ID> ...] [选项]" >&2
  exit 2
fi

HARNESS_ROOT="$1"
shift

if [ ! -d "$DRIVER_DIR/node_modules/playwright-core" ]; then
  echo "尚未安装依赖，请先执行：" >&2
  echo "  cd $DRIVER_DIR && npm ci" >&2
  exit 2
fi

exec node "$DRIVER_DIR/batch.mjs" --harness-root "$HARNESS_ROOT" "$@"
