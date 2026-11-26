#!/usr/bin/env bash
# Canonical full scorer build: Codex + DSH + managed Python/Chromium + Office.
set -euo pipefail
SCORER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCORER_DIR}/../.." && pwd)"
if [[ -n "${WCB_BUILD_PYTHON:-}" ]]; then
  PYTHON=("${WCB_BUILD_PYTHON}")
elif [[ -x "${REPO_ROOT}/.venv/bin/python" ]]; then
  PYTHON=("${REPO_ROOT}/.venv/bin/python")
elif command -v python3 >/dev/null 2>&1; then
  PYTHON=(python3)
elif command -v uv >/dev/null 2>&1; then
  PYTHON=(uv run --python 3.11 python)
else
  echo 'Python 3 is required to prepare a context; transfer a prepared context to Docker-only servers.' >&2
  exit 2
fi
# Later explicit --context/--tag arguments override these defaults.
exec "${PYTHON[@]}" "${REPO_ROOT}/tools/e2e-build/build_headless_scorer.py" \
  --context "${REPO_ROOT}/.cache/headless-scorer-build" \
  --tag wildclawbench-e2e-scorer:codex-0.171.0-office-v1 --with-office "$@"
