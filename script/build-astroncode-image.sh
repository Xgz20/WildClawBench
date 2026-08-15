#!/usr/bin/env bash
# Compatibility entry point. New commands should use docker/astroncode/build.sh.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WCB_LEGACY_BUILD_WRAPPER="1"
export WCB_LEGACY_BUILD_WRAPPER
exec "${REPO_ROOT}/docker/astroncode/build.sh" "$@"
