#!/bin/bash
set -u

SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
HELPER="$SCRIPT_DIR/tools/prepare_scoring_workspace.py"

if command -v python3 >/dev/null 2>&1; then
  python3 "$HELPER" --package-root "$SCRIPT_DIR"
  STATUS=$?
elif command -v python >/dev/null 2>&1; then
  python "$HELPER" --package-root "$SCRIPT_DIR"
  STATUS=$?
else
  echo "FAIL: 未找到 Python。请使用支持目录合并的 ZIP 工具手工准备评分工作空间。"
  STATUS=2
fi

echo
read -r -p "按回车键关闭..."
exit "$STATUS"
