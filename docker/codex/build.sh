#!/usr/bin/env bash
# Canonical Codex image builder. Official image references and build inputs are
# resolved from versions.json and cannot be overridden independently.
set -euo pipefail

HARNESS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${HARNESS_DIR}/../.." && pwd)"
MANIFEST="${HARNESS_DIR}/versions.json"
REQUESTED_VERSION=""

usage() {
  cat <<'EOF'
Usage: bash docker/codex/build.sh [--version VERSION] [--skip-save]

Builds the default version from versions.json when --version is omitted.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version)
      if [[ $# -lt 2 || -z "$2" ]]; then
        echo "--version requires a value" >&2
        exit 2
      fi
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
      echo "Unknown Codex build option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ "${WCB_LEGACY_BUILD_WRAPPER:-}" == "1" ]]; then
  if [[ -n "${IMAGE_TAG:-}" && "${IMAGE_TAG}" != "v0.1" ]]; then
    echo "Unsupported legacy Codex image tag: ${IMAGE_TAG}" >&2
    exit 2
  fi
  if [[ -n "${REQUESTED_VERSION}" && "${REQUESTED_VERSION}" != "v0.1" ]]; then
    echo "Unsupported legacy Codex image version: ${REQUESTED_VERSION}" >&2
    exit 2
  fi
  REQUESTED_VERSION="${REQUESTED_VERSION:-v0.1}"
elif [[ -n "${IMAGE_TAG:-}" ]]; then
  echo "IMAGE_TAG is a legacy option; use --version" >&2
  exit 2
fi

if ! VERSION_RECORD="$(python3 - "${MANIFEST}" "${REQUESTED_VERSION}" <<'PY'
import json
import sys

manifest_path, requested = sys.argv[1:]
with open(manifest_path, encoding="utf-8") as stream:
    manifest = json.load(stream)
version = requested or manifest["default"]
entry = manifest["versions"].get(version)
if entry is None:
    available = ", ".join(manifest["versions"])
    raise SystemExit(f"Unknown Codex image version: {version} (available: {available})")
args = entry.get("build_args", {})
values = (
    version,
    entry["image"],
    entry["context"],
    entry["dockerfile"],
    args["CODEX_VERSION"],
    args["EVAL_BASE_IMAGE"],
)
if any("\t" in value or "\n" in value for value in values):
    raise SystemExit("Invalid control character in Codex versions.json")
print("\t".join(values))
PY
)"; then
  exit 2
fi

IFS=$'\t' read -r VERSION IMAGE_REF CONTEXT_REL DOCKERFILE_REL PINNED_CODEX_VERSION PINNED_BASE_IMAGE <<< "${VERSION_RECORD}"
BUILD_CONTEXT="${HARNESS_DIR}/${CONTEXT_REL}"
DOCKERFILE="${HARNESS_DIR}/${DOCKERFILE_REL}"

if [[ ! -d "${BUILD_CONTEXT}" ]]; then
  echo "Missing Codex build context: ${BUILD_CONTEXT}" >&2
  exit 2
fi
if [[ ! -f "${DOCKERFILE}" ]]; then
  echo "Missing Codex Dockerfile: ${DOCKERFILE}" >&2
  exit 2
fi
BUILD_CONTEXT="$(cd "${BUILD_CONTEXT}" && pwd -P)"
DOCKERFILE="$(cd "$(dirname "${DOCKERFILE}")" && pwd -P)/$(basename "${DOCKERFILE}")"
CONTEXT_PARENT="$(dirname "${BUILD_CONTEXT}")"
CONTEXT_NAME="$(basename "${BUILD_CONTEXT}")"
if [[ "${CONTEXT_PARENT}" != "${HARNESS_DIR}" || ! "${CONTEXT_NAME}" =~ ^v[0-9]+$ ]]; then
  echo "Invalid Codex build context: ${BUILD_CONTEXT}" >&2
  exit 2
fi
case "${DOCKERFILE}" in
  "${BUILD_CONTEXT}"/*) ;;
  *) echo "Invalid Codex Dockerfile path: ${DOCKERFILE}" >&2; exit 2 ;;
esac

if [[ -n "${CODEX_VERSION:-}" && "${CODEX_VERSION}" != "${PINNED_CODEX_VERSION}" ]]; then
  echo "CODEX_VERSION must be ${PINNED_CODEX_VERSION} for ${IMAGE_REF}" >&2
  exit 2
fi
if [[ -n "${EVAL_BASE_IMAGE:-}" && "${EVAL_BASE_IMAGE}" != "${PINNED_BASE_IMAGE}" ]]; then
  echo "EVAL_BASE_IMAGE must be ${PINNED_BASE_IMAGE} for ${IMAGE_REF}" >&2
  exit 2
fi
if [[ "${PINNED_BASE_IMAGE}" == "${IMAGE_REF}" ]]; then
  echo "Refusing to build ${IMAGE_REF} on top of itself" >&2
  exit 2
fi
if ! docker image inspect "${PINNED_BASE_IMAGE}" >/dev/null 2>&1; then
  echo "Base image not found locally: ${PINNED_BASE_IMAGE}" >&2
  echo "Load it first: docker load -i Images/wildclawbench-codex-ubuntu_v0.0.tar" >&2
  exit 1
fi

BUILD_ARGS=(
  --build-arg "EVAL_BASE_IMAGE=${PINNED_BASE_IMAGE}"
  --build-arg "CODEX_VERSION=${PINNED_CODEX_VERSION}"
)
if [[ -n "${NPM_REGISTRY:-}" ]]; then
  BUILD_ARGS+=(--build-arg "NPM_REGISTRY=${NPM_REGISTRY}")
fi
if [[ -n "${HTTP_PROXY_INNER:-}" ]]; then
  BUILD_ARGS+=(--build-arg "http_proxy=${HTTP_PROXY_INNER}" --build-arg "HTTP_PROXY=${HTTP_PROXY_INNER}")
fi
if [[ -n "${HTTPS_PROXY_INNER:-}" ]]; then
  BUILD_ARGS+=(--build-arg "https_proxy=${HTTPS_PROXY_INNER}" --build-arg "HTTPS_PROXY=${HTTPS_PROXY_INNER}")
fi
if [[ -n "${NO_PROXY_INNER:-}" ]]; then
  BUILD_ARGS+=(--build-arg "no_proxy=${NO_PROXY_INNER}" --build-arg "NO_PROXY=${NO_PROXY_INNER}")
fi

docker build \
  -f "${DOCKERFILE}" \
  "${BUILD_ARGS[@]}" \
  -t "${IMAGE_REF}" \
  "${BUILD_CONTEXT}"

INSTALLED_VERSION="$(docker run --rm --entrypoint codex "${IMAGE_REF}" --version 2>/dev/null | head -1 || true)"
echo "Installed Codex CLI: ${INSTALLED_VERSION:-unknown}"

if [[ "${SKIP_SAVE:-}" == "1" ]]; then
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

echo "Enable: export DOCKER_IMAGE_CODEX='${IMAGE_REF}'"
