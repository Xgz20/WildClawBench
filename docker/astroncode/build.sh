#!/usr/bin/env bash
# Canonical AstronCode image builder. Official image references and build
# inputs are resolved from versions.json and cannot be combined independently.
set -euo pipefail

HARNESS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${HARNESS_DIR}/../.." && pwd)"
MANIFEST="${HARNESS_DIR}/versions.json"
REQUESTED_VERSION=""

usage() {
  cat <<'EOF'
Usage: bash docker/astroncode/build.sh [--version VERSION] [--skip-save]

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
      echo "Unknown AstronCode build option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ "${WCB_LEGACY_BUILD_WRAPPER:-}" == "1" ]]; then
  LEGACY_VARIANT_VERSION=""
  case "${ASTRONCODE_DOCKER_VARIANT:-}" in
    "") ;;
    v1) LEGACY_VARIANT_VERSION="v0.1-test.8" ;;
    v2) LEGACY_VARIANT_VERSION="v0.2" ;;
    v3) LEGACY_VARIANT_VERSION="v0.3" ;;
    v4) LEGACY_VARIANT_VERSION="v0.4-ppt" ;;
    v5) LEGACY_VARIANT_VERSION="v0.5" ;;
    *)
      echo "Unsupported legacy AstronCode build mapping: variant=${ASTRONCODE_DOCKER_VARIANT} tag=${IMAGE_TAG:-<default>}" >&2
      exit 2
      ;;
  esac

  LEGACY_TAG_VERSION="${IMAGE_TAG:-}"
  if [[ -n "${LEGACY_VARIANT_VERSION}" && -n "${LEGACY_TAG_VERSION}" && "${LEGACY_VARIANT_VERSION}" != "${LEGACY_TAG_VERSION}" ]]; then
    echo "Unsupported legacy AstronCode build mapping: variant=${ASTRONCODE_DOCKER_VARIANT} tag=${IMAGE_TAG}" >&2
    exit 2
  fi
  LEGACY_VERSION="${LEGACY_TAG_VERSION:-${LEGACY_VARIANT_VERSION}}"
  if [[ -n "${REQUESTED_VERSION}" && -n "${LEGACY_VERSION}" && "${REQUESTED_VERSION}" != "${LEGACY_VERSION}" ]]; then
    echo "Unsupported legacy AstronCode build mapping: --version=${REQUESTED_VERSION} legacy=${LEGACY_VERSION}" >&2
    exit 2
  fi
  REQUESTED_VERSION="${REQUESTED_VERSION:-${LEGACY_VERSION}}"
elif [[ -n "${ASTRONCODE_DOCKER_VARIANT:-}" || -n "${IMAGE_TAG:-}" ]]; then
  echo "ASTRONCODE_DOCKER_VARIANT and IMAGE_TAG are legacy options; use --version" >&2
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
    raise SystemExit(f"Unknown AstronCode image version: {version} (available: {available})")
args = entry.get("build_args", {})
values = (
    version,
    entry["image"],
    entry["context"],
    entry["dockerfile"],
    args.get("ASTRON_CODE_VERSION", ""),
    args.get("SEARCH_UPDATER_VERSION", ""),
    args.get("NODEJS_VERSION", ""),
)
if any("\t" in value or "\n" in value for value in values):
    raise SystemExit("Invalid control character in AstronCode versions.json")
print("\t".join(values))
PY
)"; then
  exit 2
fi

IFS=$'\t' read -r VERSION IMAGE_REF CONTEXT_REL DOCKERFILE_REL PINNED_ASTRON_CODE_VERSION PINNED_SEARCH_UPDATER_VERSION PINNED_NODEJS_VERSION <<< "${VERSION_RECORD}"
BUILD_CONTEXT="${HARNESS_DIR}/${CONTEXT_REL}"
DOCKERFILE="${HARNESS_DIR}/${DOCKERFILE_REL}"

if [[ ! -d "${BUILD_CONTEXT}" ]]; then
  echo "Missing AstronCode build context: ${BUILD_CONTEXT}" >&2
  exit 2
fi
if [[ ! -f "${DOCKERFILE}" ]]; then
  echo "Missing AstronCode Dockerfile: ${DOCKERFILE}" >&2
  exit 2
fi
BUILD_CONTEXT="$(cd "${BUILD_CONTEXT}" && pwd -P)"
DOCKERFILE="$(cd "$(dirname "${DOCKERFILE}")" && pwd -P)/$(basename "${DOCKERFILE}")"
CONTEXT_PARENT="$(dirname "${BUILD_CONTEXT}")"
CONTEXT_NAME="$(basename "${BUILD_CONTEXT}")"
if [[ "${CONTEXT_PARENT}" != "${HARNESS_DIR}" || ! "${CONTEXT_NAME}" =~ ^v[0-9]+$ ]]; then
  echo "Invalid AstronCode build context: ${BUILD_CONTEXT}" >&2
  exit 2
fi
case "${DOCKERFILE}" in
  "${BUILD_CONTEXT}"/*) ;;
  *) echo "Invalid AstronCode Dockerfile path: ${DOCKERFILE}" >&2; exit 2 ;;
esac

if [[ -n "${ASTRON_CODE_VERSION:-}" && "${ASTRON_CODE_VERSION}" != "${PINNED_ASTRON_CODE_VERSION}" ]]; then
  echo "ASTRON_CODE_VERSION must be ${PINNED_ASTRON_CODE_VERSION} for ${IMAGE_REF}" >&2
  exit 2
fi
if [[ -n "${NODEJS_VERSION:-}" && "${NODEJS_VERSION}" != "${PINNED_NODEJS_VERSION}" ]]; then
  echo "NODEJS_VERSION must be ${PINNED_NODEJS_VERSION:-unset} for ${IMAGE_REF}" >&2
  exit 2
fi
if [[ -n "${SEARCH_UPDATER_VERSION:-}" && "${SEARCH_UPDATER_VERSION}" != "${PINNED_SEARCH_UPDATER_VERSION}" ]]; then
  echo "SEARCH_UPDATER_VERSION must be ${PINNED_SEARCH_UPDATER_VERSION:-unset} for ${IMAGE_REF}" >&2
  exit 2
fi

BUILD_ARGS=(--build-arg "ASTRON_CODE_VERSION=${PINNED_ASTRON_CODE_VERSION}")
if [[ -n "${PINNED_NODEJS_VERSION}" ]]; then
  BUILD_ARGS+=(--build-arg "NODEJS_VERSION=${PINNED_NODEJS_VERSION}")
fi
if [[ -n "${PINNED_SEARCH_UPDATER_VERSION}" ]]; then
  BUILD_ARGS+=(--build-arg "SEARCH_UPDATER_VERSION=${PINNED_SEARCH_UPDATER_VERSION}")
fi
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

INSTALLED_VERSION="$(docker run --rm --entrypoint astron-code "${IMAGE_REF}" --version 2>/dev/null | head -1 || true)"
echo "Installed AstronCode: ${INSTALLED_VERSION:-unknown}"

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

echo "Enable: export DOCKER_IMAGE_ASTRONCODE='${IMAGE_REF}'"
