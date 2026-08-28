#!/usr/bin/env bash
set -euo pipefail

HARNESS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${HARNESS_DIR}/../.." && pwd)"
MANIFEST="${HARNESS_DIR}/versions.json"
REQUESTED_VERSION=""
SKIP_SAVE="${SKIP_SAVE:-0}"

usage() {
  cat <<'EOF'
Usage: bash docker/claudecode/build.sh [--version VERSION] [--skip-save]

Builds the default version from versions.json when --version is omitted.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version)
      [[ $# -ge 2 && -n "$2" ]] || { echo "--version requires a value" >&2; exit 2; }
      REQUESTED_VERSION="$2"
      shift 2
      ;;
    --skip-save)
      SKIP_SAVE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown Claude Code build option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if command -v python3 >/dev/null 2>&1; then
  PYTHON=(python3)
elif command -v uv >/dev/null 2>&1; then
  PYTHON=(uv run python)
else
  echo "python3 or uv is required to read ${MANIFEST}" >&2
  exit 2
fi

if ! VERSION_RECORD="$("${PYTHON[@]}" - "${MANIFEST}" "${REQUESTED_VERSION}" <<'PY'
import json
import sys

manifest_path, requested = sys.argv[1:]
with open(manifest_path, encoding="utf-8") as stream:
    manifest = json.load(stream)
version = requested or manifest["default"]
entry = manifest["versions"].get(version)
if entry is None:
    available = ", ".join(manifest["versions"])
    raise SystemExit(
        f"Unknown Claude Code image version: {version} (available: {available})"
    )
args = entry["build_args"]
values = (
    version,
    entry["image"],
    entry["context"],
    entry["dockerfile"],
    args["CLAUDE_CODE_VERSION"],
    args["EVAL_BASE_IMAGE"],
    args["NODE_RUNTIME_IMAGE"],
)
if any("\x1f" in value or "\n" in value for value in values):
    raise SystemExit("Invalid control character in Claude Code versions.json")
print("\x1f".join(values))
PY
)"; then
  exit 2
fi

IFS=$'\x1f' read -r VERSION IMAGE_REF CONTEXT_REL DOCKERFILE_REL PINNED_CLAUDE_CODE_VERSION PINNED_EVAL_BASE_IMAGE PINNED_NODE_RUNTIME_IMAGE <<< "${VERSION_RECORD}"
BUILD_CONTEXT="${HARNESS_DIR}/${CONTEXT_REL}"
DOCKERFILE="${HARNESS_DIR}/${DOCKERFILE_REL}"

[[ -d "${BUILD_CONTEXT}" ]] || { echo "Missing Claude Code build context: ${BUILD_CONTEXT}" >&2; exit 2; }
[[ -f "${DOCKERFILE}" ]] || { echo "Missing Claude Code Dockerfile: ${DOCKERFILE}" >&2; exit 2; }
BUILD_CONTEXT="$(cd "${BUILD_CONTEXT}" && pwd -P)"
DOCKERFILE="$(cd "$(dirname "${DOCKERFILE}")" && pwd -P)/$(basename "${DOCKERFILE}")"
[[ "$(dirname "${BUILD_CONTEXT}")" == "${HARNESS_DIR}" && "$(basename "${BUILD_CONTEXT}")" =~ ^v[0-9]+$ ]] || {
  echo "Invalid Claude Code build context: ${BUILD_CONTEXT}" >&2
  exit 2
}
case "${DOCKERFILE}" in
  "${BUILD_CONTEXT}"/*) ;;
  *) echo "Invalid Claude Code Dockerfile path: ${DOCKERFILE}" >&2; exit 2 ;;
esac

[[ -z "${CLAUDE_CODE_VERSION:-}" || "${CLAUDE_CODE_VERSION}" == "${PINNED_CLAUDE_CODE_VERSION}" ]] || {
  echo "CLAUDE_CODE_VERSION must be ${PINNED_CLAUDE_CODE_VERSION} for ${IMAGE_REF}" >&2
  exit 2
}
[[ -z "${EVAL_BASE_IMAGE:-}" || "${EVAL_BASE_IMAGE}" == "${PINNED_EVAL_BASE_IMAGE}" ]] || {
  echo "EVAL_BASE_IMAGE must be ${PINNED_EVAL_BASE_IMAGE} for ${IMAGE_REF}" >&2
  exit 2
}
[[ -z "${NODE_RUNTIME_IMAGE:-}" || "${NODE_RUNTIME_IMAGE}" == "${PINNED_NODE_RUNTIME_IMAGE}" ]] || {
  echo "NODE_RUNTIME_IMAGE must be ${PINNED_NODE_RUNTIME_IMAGE} for ${IMAGE_REF}" >&2
  exit 2
}
[[ "${PINNED_EVAL_BASE_IMAGE}" != "${IMAGE_REF}" ]] || {
  echo "Refusing to build ${IMAGE_REF} on top of itself" >&2
  exit 2
}
if ! docker image inspect "${PINNED_EVAL_BASE_IMAGE}" >/dev/null 2>&1; then
  echo "Base image not found locally: ${PINNED_EVAL_BASE_IMAGE}" >&2
  echo "Load it first: docker load -i Images/wildclawbench-codex-ubuntu_v0.0.tar" >&2
  exit 1
fi

BUILD_ARGS=(
  --build-arg "CLAUDE_CODE_VERSION=${PINNED_CLAUDE_CODE_VERSION}"
  --build-arg "EVAL_BASE_IMAGE=${PINNED_EVAL_BASE_IMAGE}"
  --build-arg "NODE_RUNTIME_IMAGE=${PINNED_NODE_RUNTIME_IMAGE}"
)
[[ -z "${NPM_REGISTRY:-}" ]] || BUILD_ARGS+=(--build-arg "NPM_REGISTRY=${NPM_REGISTRY}")
[[ -z "${HTTP_PROXY_INNER:-}" ]] || BUILD_ARGS+=(--build-arg "http_proxy=${HTTP_PROXY_INNER}" --build-arg "HTTP_PROXY=${HTTP_PROXY_INNER}")
[[ -z "${HTTPS_PROXY_INNER:-}" ]] || BUILD_ARGS+=(--build-arg "https_proxy=${HTTPS_PROXY_INNER}" --build-arg "HTTPS_PROXY=${HTTPS_PROXY_INNER}")
[[ -z "${NO_PROXY_INNER:-}" ]] || BUILD_ARGS+=(--build-arg "no_proxy=${NO_PROXY_INNER}" --build-arg "NO_PROXY=${NO_PROXY_INNER}")

docker build -f "${DOCKERFILE}" "${BUILD_ARGS[@]}" -t "${IMAGE_REF}" "${BUILD_CONTEXT}"

INSTALLED_VERSION="$(docker run --rm --entrypoint claude "${IMAGE_REF}" --version 2>/dev/null | head -1 || true)"
echo "Installed Claude Code CLI: ${INSTALLED_VERSION:-unknown}"

if [[ "${SKIP_SAVE}" == "1" ]]; then
  echo "OK: ${IMAGE_REF} (SKIP_SAVE=1, no archive exported)"
else
  IMAGE_NAME="${IMAGE_REF%:*}"
  IMAGE_TAG="${IMAGE_REF##*:}"
  TAR_PATH="${REPO_ROOT}/Images/${IMAGE_NAME##*/}_${IMAGE_TAG}.tar.gz"
  TEMP_TAR_PATH="${TAR_PATH}.tmp.$$"
  trap 'rm -f "${TEMP_TAR_PATH:-}"' EXIT
  mkdir -p "${REPO_ROOT}/Images"
  docker save "${IMAGE_REF}" | gzip > "${TEMP_TAR_PATH}"
  mv "${TEMP_TAR_PATH}" "${TAR_PATH}"
  trap - EXIT
  echo "OK: ${IMAGE_REF} -> ${TAR_PATH}"
  echo "Load offline: docker load -i ${TAR_PATH##*/}"
fi

echo "Enable: export DOCKER_IMAGE_CLAUDECODE='${IMAGE_REF}'"
