#!/bin/bash
set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd -P)"
skill_root="$(cd "$script_dir/.." && pwd -P)"
packaged_entrypoint="$skill_root/vendor/e2e-shared/desktop-debug/restart_macos_desktop_debug.sh"
repository_entrypoint="$skill_root/../../../e2e-shared/desktop-debug/restart_macos_desktop_debug.sh"

if [[ -f "$packaged_entrypoint" ]]; then
  exec /bin/bash "$packaged_entrypoint" "$@"
fi
if [[ -f "$repository_entrypoint" ]]; then
  exec /bin/bash "$repository_entrypoint" "$@"
fi

echo "Missing bundled desktop-debug component: $packaged_entrypoint" >&2
exit 2
