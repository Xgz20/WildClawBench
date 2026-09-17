#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DRIVER_DIR="$(cd "$SCRIPT_DIR/../drivers/qwenwork" && pwd)"

if [ "${1:-}" = "--probe" ]; then
  shift
  exec node "$DRIVER_DIR/driver.mjs" --probe "$@"
fi

if [ $# -eq 0 ]; then
  echo "用法: bash .agents/skills/execute-web-e2e/scripts/run-qwenwork.sh <单题目录> [选项]" >&2
  echo "预检: bash .agents/skills/execute-web-e2e/scripts/run-qwenwork.sh --probe" >&2
  exit 2
fi

TASK_ROOT="$1"
shift

if [ ! -d "$DRIVER_DIR/node_modules/playwright-core" ]; then
  echo "尚未安装依赖，请先执行：" >&2
  echo "  cd $DRIVER_DIR && npm ci" >&2
  exit 2
fi

exec node "$DRIVER_DIR/driver.mjs" --workspace "$TASK_ROOT" "$@"
