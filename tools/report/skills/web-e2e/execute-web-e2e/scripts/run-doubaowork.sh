#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ "$#" -eq 0 ]; then
  echo "用法: bash .agents/skills/execute-web-e2e/scripts/run-doubaowork.sh <prepared 单题目录> --output-dir <仓库外目录> [选项]" >&2
  echo "预检: bash .agents/skills/execute-web-e2e/scripts/run-doubaowork.sh --probe [选项]" >&2
  exit 2
fi
exec node "$SCRIPT_DIR/run-doubaowork.mjs" "$@"
