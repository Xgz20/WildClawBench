#!/usr/bin/env bash
set -euo pipefail

HARNESS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${HARNESS_DIR}/../.." && pwd)"
MANIFEST="${HARNESS_DIR}/versions.json"
REQUESTED_VERSION=""
SKIP_SAVE="${SKIP_SAVE:-0}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version)
      [[ $# -ge 2 && -n "$2" ]] || { echo "--version requires a value" >&2; exit 2; }
      REQUESTED_VERSION="$2"
      shift 2
      ;;
    --skip-save) SKIP_SAVE=1; shift ;;
    -h|--help) echo "Usage: bash docker/mimocode/build.sh [--version VERSION] [--skip-save]"; exit 0 ;;
    *) echo "Unknown MiMoCode build option: $1" >&2; exit 2 ;;
  esac
done

VERSION_RECORD="$(python3 - "${MANIFEST}" "${REQUESTED_VERSION}" <<'PY'
import json, sys
manifest_path, requested = sys.argv[1:]
manifest = json.loads(open(manifest_path, encoding="utf-8").read())
version = requested or manifest["default"]
entry = manifest["versions"].get(version)
if entry is None:
    raise SystemExit(f"Unknown MiMoCode image version: {version}")
if entry.get("buildable") is False:
    raise SystemExit(f"MiMoCode {version} cannot be rebuilt: {entry['build_unavailable_reason']}")
args = entry["build_args"]
print("\x1f".join((version, entry["image"], entry["context"], entry["dockerfile"], args["MIMOCODE_VERSION"], args["EVAL_BASE_IMAGE"])))
PY
)"
IFS=$'\x1f' read -r VERSION IMAGE_REF CONTEXT_REL DOCKERFILE_REL PINNED_MIMOCODE_VERSION PINNED_EVAL_BASE_IMAGE <<< "${VERSION_RECORD}"
BUILD_CONTEXT="${HARNESS_DIR}/${CONTEXT_REL}"
DOCKERFILE="${HARNESS_DIR}/${DOCKERFILE_REL}"
[[ -z "${MIMOCODE_VERSION:-}" || "${MIMOCODE_VERSION}" == "${PINNED_MIMOCODE_VERSION}" ]] || {
  echo "MIMOCODE_VERSION must be ${PINNED_MIMOCODE_VERSION} for ${IMAGE_REF}; select the image with --version" >&2
  exit 2
}
docker image inspect "${PINNED_EVAL_BASE_IMAGE}" >/dev/null 2>&1 || { echo "Missing required base image: ${PINNED_EVAL_BASE_IMAGE}" >&2; exit 2; }

BUILD_ARGS=(
  --build-arg "MIMOCODE_VERSION=${PINNED_MIMOCODE_VERSION}"
  --build-arg "EVAL_BASE_IMAGE=${PINNED_EVAL_BASE_IMAGE}"
)
[[ -z "${NPM_REGISTRY:-}" ]] || BUILD_ARGS+=(--build-arg "NPM_REGISTRY=${NPM_REGISTRY}")
[[ -z "${HTTP_PROXY_INNER:-}" ]] || BUILD_ARGS+=(--build-arg "http_proxy=${HTTP_PROXY_INNER}" --build-arg "HTTP_PROXY=${HTTP_PROXY_INNER}")
[[ -z "${HTTPS_PROXY_INNER:-}" ]] || BUILD_ARGS+=(--build-arg "https_proxy=${HTTPS_PROXY_INNER}" --build-arg "HTTPS_PROXY=${HTTPS_PROXY_INNER}")

docker build -f "${DOCKERFILE}" "${BUILD_ARGS[@]}" -t "${IMAGE_REF}" "${BUILD_CONTEXT}"
INSTALLED_VERSION="$(docker run --rm --entrypoint mimo "${IMAGE_REF}" --version 2>/dev/null | head -1 || true)"
[[ "${INSTALLED_VERSION}" == "${PINNED_MIMOCODE_VERSION}" ]] || { echo "Unexpected installed MiMoCode version: ${INSTALLED_VERSION:-unknown}" >&2; exit 3; }
echo "Installed MiMoCode: ${INSTALLED_VERSION}"

if [[ "${SKIP_SAVE}" == "1" ]]; then
  echo "OK: ${IMAGE_REF} (SKIP_SAVE=1, no archive exported)"
else
  mkdir -p "${REPO_ROOT}/Images"
  TAR_PATH="${REPO_ROOT}/Images/${IMAGE_REF%:*}_${IMAGE_REF##*:}.tar.gz"
  TEMP_TAR_PATH="${TAR_PATH}.tmp.$$"
  trap 'rm -f "${TEMP_TAR_PATH:-}"' EXIT
  docker save "${IMAGE_REF}" | gzip > "${TEMP_TAR_PATH}"
  mv "${TEMP_TAR_PATH}" "${TAR_PATH}"
  trap - EXIT
  echo "OK: ${IMAGE_REF} -> ${TAR_PATH}"
fi
echo "Enable: export DOCKER_IMAGE_MIMOCODE='${IMAGE_REF}'"
