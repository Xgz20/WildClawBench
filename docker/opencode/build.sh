#!/usr/bin/env bash
set -euo pipefail

HARNESS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${HARNESS_DIR}/../.." && pwd)"
MANIFEST="${HARNESS_DIR}/versions.json"
REQUESTED_VERSION=""
SKIP_SAVE="${SKIP_SAVE:-0}"

usage() {
  cat <<'EOF'
Usage: bash docker/opencode/build.sh [--version VERSION] [--skip-save]

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
      echo "Unknown OpenCode build option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -x "${REPO_ROOT}/.venv/bin/python3" ]]; then
  PYTHON=("${REPO_ROOT}/.venv/bin/python3")
elif [[ -x "${REPO_ROOT}/.venv/bin/python" ]]; then
  PYTHON=("${REPO_ROOT}/.venv/bin/python")
elif command -v python3 >/dev/null 2>&1; then
  PYTHON=(python3)
elif command -v uv >/dev/null 2>&1; then
  PYTHON=(uv run python)
else
  echo "Repository .venv/bin/python3 or .venv/bin/python, system python3, or uv is required to read ${MANIFEST}" >&2
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
    raise SystemExit(f"Unknown OpenCode image version: {version} (available: {available})")
args = entry["build_args"]
values = (
    version,
    entry["image"],
    entry["context"],
    entry["dockerfile"],
    args["OPENCODE_VERSION"],
    args["EVAL_BASE_IMAGE"],
)
if any("\x1f" in value or "\n" in value for value in values):
    raise SystemExit("Invalid control character in OpenCode versions.json")
print("\x1f".join(values))
PY
)"; then
  exit 2
fi

IFS=$'\x1f' read -r VERSION IMAGE_REF CONTEXT_REL DOCKERFILE_REL PINNED_OPENCODE_VERSION PINNED_BASE_IMAGE <<< "${VERSION_RECORD}"
BUILD_CONTEXT="${HARNESS_DIR}/${CONTEXT_REL}"
DOCKERFILE="${HARNESS_DIR}/${DOCKERFILE_REL}"

[[ -d "${BUILD_CONTEXT}" ]] || { echo "Missing OpenCode build context: ${BUILD_CONTEXT}" >&2; exit 2; }
[[ -f "${DOCKERFILE}" ]] || { echo "Missing OpenCode Dockerfile: ${DOCKERFILE}" >&2; exit 2; }
BUILD_CONTEXT="$(cd "${BUILD_CONTEXT}" && pwd -P)"
DOCKERFILE="$(cd "$(dirname "${DOCKERFILE}")" && pwd -P)/$(basename "${DOCKERFILE}")"
[[ "$(dirname "${BUILD_CONTEXT}")" == "${HARNESS_DIR}" && "$(basename "${BUILD_CONTEXT}")" =~ ^v[0-9]+$ ]] || {
  echo "Invalid OpenCode build context: ${BUILD_CONTEXT}" >&2
  exit 2
}
case "${DOCKERFILE}" in
  "${BUILD_CONTEXT}"/*) ;;
  *) echo "Invalid OpenCode Dockerfile path: ${DOCKERFILE}" >&2; exit 2 ;;
esac

[[ -z "${OPENCODE_VERSION:-}" || "${OPENCODE_VERSION}" == "${PINNED_OPENCODE_VERSION}" ]] || {
  echo "OPENCODE_VERSION must be ${PINNED_OPENCODE_VERSION} for ${IMAGE_REF}" >&2
  exit 2
}
[[ -z "${EVAL_BASE_IMAGE:-}" || "${EVAL_BASE_IMAGE}" == "${PINNED_BASE_IMAGE}" ]] || {
  echo "EVAL_BASE_IMAGE must be ${PINNED_BASE_IMAGE} for ${IMAGE_REF}" >&2
  exit 2
}
[[ "${PINNED_BASE_IMAGE}" != "${IMAGE_REF}" ]] || {
  echo "Refusing to build ${IMAGE_REF} on top of itself" >&2
  exit 2
}
if ! docker image inspect "${PINNED_BASE_IMAGE}" >/dev/null 2>&1; then
  echo "Base image not found locally: ${PINNED_BASE_IMAGE}" >&2
  echo "Load it first: docker load -i Images/wildclawbench-codex-ubuntu_v0.0.tar" >&2
  exit 1
fi

BUILD_ARGS=(
  --build-arg "OPENCODE_VERSION=${PINNED_OPENCODE_VERSION}"
  --build-arg "EVAL_BASE_IMAGE=${PINNED_BASE_IMAGE}"
)
[[ -z "${NPM_REGISTRY:-}" ]] || BUILD_ARGS+=(--build-arg "NPM_REGISTRY=${NPM_REGISTRY}")
[[ -z "${HTTP_PROXY_INNER:-}" ]] || BUILD_ARGS+=(--build-arg "http_proxy=${HTTP_PROXY_INNER}" --build-arg "HTTP_PROXY=${HTTP_PROXY_INNER}")
[[ -z "${HTTPS_PROXY_INNER:-}" ]] || BUILD_ARGS+=(--build-arg "https_proxy=${HTTPS_PROXY_INNER}" --build-arg "HTTPS_PROXY=${HTTPS_PROXY_INNER}")
[[ -z "${NO_PROXY_INNER:-}" ]] || BUILD_ARGS+=(--build-arg "no_proxy=${NO_PROXY_INNER}" --build-arg "NO_PROXY=${NO_PROXY_INNER}")

docker build -f "${DOCKERFILE}" "${BUILD_ARGS[@]}" -t "${IMAGE_REF}" "${BUILD_CONTEXT}"

if ! INSTALLED_VERSION="$(docker run --rm --entrypoint opencode "${IMAGE_REF}" --version)"; then
  echo "Failed to verify installed OpenCode version for ${IMAGE_REF}" >&2
  exit 3
fi
if [[ "${INSTALLED_VERSION}" != "${PINNED_OPENCODE_VERSION}" ]]; then
  echo "Unexpected installed OpenCode version: ${INSTALLED_VERSION:-unknown}" >&2
  exit 3
fi
echo "Installed OpenCode: ${INSTALLED_VERSION}"

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

echo "Enable: export DOCKER_IMAGE_OPENCODE='${IMAGE_REF}'"
