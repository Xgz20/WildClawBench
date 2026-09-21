#!/usr/bin/env bash
set -euo pipefail

HARNESS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${HARNESS_DIR}/../.." && pwd)"
MANIFEST="${HARNESS_DIR}/versions.json"
REQUESTED_VERSION=""
SKIP_SAVE="${SKIP_SAVE:-0}"

usage() {
  cat <<'EOF'
Usage: bash docker/zcode/build.sh [--version VERSION] [--skip-save]

Builds the pinned ZCode source revision declared in versions.json.
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
      echo "Unknown ZCode build option: $1" >&2
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

VERSION_RECORD="$("${PYTHON[@]}" - "${MANIFEST}" "${REQUESTED_VERSION}" <<'PY'
import json
import sys

manifest_path, requested = sys.argv[1:]
with open(manifest_path, encoding="utf-8") as stream:
    manifest = json.load(stream)
version = requested or manifest["default"]
entry = manifest["versions"].get(version)
if entry is None:
    available = ", ".join(manifest["versions"])
    raise SystemExit(f"Unknown ZCode image version: {version} (available: {available})")
args = entry["build_args"]
values = (
    version,
    entry["image"],
    entry["context"],
    entry["dockerfile"],
    args["ZCODE_VERSION"],
    args["ZCODE_SOURCE_COMMIT"],
    args["ZCODE_REPOSITORY"],
    args["EVAL_BASE_IMAGE"],
    args["NODE_BUILDER_IMAGE"],
)
if any("\x1f" in value or "\n" in value for value in values):
    raise SystemExit("Invalid control character in ZCode versions.json")
print("\x1f".join(values))
PY
)"

IFS=$'\x1f' read -r VERSION IMAGE_REF CONTEXT_REL DOCKERFILE_REL PINNED_ZCODE_VERSION PINNED_SOURCE_COMMIT PINNED_REPOSITORY PINNED_EVAL_BASE_IMAGE PINNED_NODE_BUILDER_IMAGE <<< "${VERSION_RECORD}"
BUILD_CONTEXT="${HARNESS_DIR}/${CONTEXT_REL}"
DOCKERFILE="${HARNESS_DIR}/${DOCKERFILE_REL}"

[[ -d "${BUILD_CONTEXT}" ]] || { echo "Missing ZCode build context: ${BUILD_CONTEXT}" >&2; exit 2; }
[[ -f "${DOCKERFILE}" ]] || { echo "Missing ZCode Dockerfile: ${DOCKERFILE}" >&2; exit 2; }

[[ -z "${ZCODE_VERSION:-}" || "${ZCODE_VERSION}" == "${PINNED_ZCODE_VERSION}" ]] || {
  echo "ZCODE_VERSION must be ${PINNED_ZCODE_VERSION} for ${IMAGE_REF}" >&2
  exit 2
}
[[ -z "${ZCODE_SOURCE_COMMIT:-}" || "${ZCODE_SOURCE_COMMIT}" == "${PINNED_SOURCE_COMMIT}" ]] || {
  echo "ZCODE_SOURCE_COMMIT must be ${PINNED_SOURCE_COMMIT} for ${IMAGE_REF}" >&2
  exit 2
}
[[ -z "${ZCODE_REPOSITORY:-}" || "${ZCODE_REPOSITORY}" == "${PINNED_REPOSITORY}" ]] || {
  echo "ZCODE_REPOSITORY must be ${PINNED_REPOSITORY} for ${IMAGE_REF}" >&2
  exit 2
}
[[ -z "${EVAL_BASE_IMAGE:-}" || "${EVAL_BASE_IMAGE}" == "${PINNED_EVAL_BASE_IMAGE}" ]] || {
  echo "EVAL_BASE_IMAGE must be ${PINNED_EVAL_BASE_IMAGE} for ${IMAGE_REF}" >&2
  exit 2
}
[[ -z "${NODE_BUILDER_IMAGE:-}" || "${NODE_BUILDER_IMAGE}" == "${PINNED_NODE_BUILDER_IMAGE}" ]] || {
  echo "NODE_BUILDER_IMAGE must be ${PINNED_NODE_BUILDER_IMAGE} for ${IMAGE_REF}" >&2
  exit 2
}

docker image inspect "${PINNED_EVAL_BASE_IMAGE}" >/dev/null 2>&1 || {
  echo "Missing required base image: ${PINNED_EVAL_BASE_IMAGE}" >&2
  exit 2
}

BUILD_ARGS=(
  --build-arg "ZCODE_VERSION=${PINNED_ZCODE_VERSION}"
  --build-arg "ZCODE_SOURCE_COMMIT=${PINNED_SOURCE_COMMIT}"
  --build-arg "ZCODE_REPOSITORY=${PINNED_REPOSITORY}"
  --build-arg "EVAL_BASE_IMAGE=${PINNED_EVAL_BASE_IMAGE}"
  --build-arg "NODE_BUILDER_IMAGE=${PINNED_NODE_BUILDER_IMAGE}"
)
[[ -z "${NPM_REGISTRY:-}" ]] || BUILD_ARGS+=(--build-arg "NPM_REGISTRY=${NPM_REGISTRY}")
[[ -z "${HTTP_PROXY_INNER:-}" ]] || BUILD_ARGS+=(--build-arg "http_proxy=${HTTP_PROXY_INNER}" --build-arg "HTTP_PROXY=${HTTP_PROXY_INNER}")
[[ -z "${HTTPS_PROXY_INNER:-}" ]] || BUILD_ARGS+=(--build-arg "https_proxy=${HTTPS_PROXY_INNER}" --build-arg "HTTPS_PROXY=${HTTPS_PROXY_INNER}")
[[ -z "${NO_PROXY_INNER:-}" ]] || BUILD_ARGS+=(--build-arg "no_proxy=${NO_PROXY_INNER}" --build-arg "NO_PROXY=${NO_PROXY_INNER}")

docker build -f "${DOCKERFILE}" "${BUILD_ARGS[@]}" -t "${IMAGE_REF}" "${BUILD_CONTEXT}"

INSTALLED_VERSION="$(docker run --rm --entrypoint zcode "${IMAGE_REF}" --version 2>/dev/null | head -1 || true)"
[[ "${INSTALLED_VERSION}" == "${PINNED_ZCODE_VERSION}" ]] || {
  echo "Unexpected installed ZCode version: ${INSTALLED_VERSION:-unknown}" >&2
  exit 3
}
echo "Installed ZCode: ${INSTALLED_VERSION}"

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

echo "Enable: export DOCKER_IMAGE_ZCODE='${IMAGE_REF}'"
