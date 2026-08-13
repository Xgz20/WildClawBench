#!/usr/bin/env bash
# 构建 AstronCode 评测镜像并导出离线 tar 到 Images/。
# 用法：bash script/build-astroncode-image.sh
# 默认构建 v4-ppt（AstronCode 0.0.13 + SearchAgent + PPT 渲染依赖）。
# v3 覆盖：ASTRONCODE_DOCKER_VARIANT=v3 IMAGE_TAG=v0.3 bash script/build-astroncode-image.sh
# v2 覆盖：ASTRONCODE_DOCKER_VARIANT=v2 ASTRON_CODE_VERSION=0.0.6 IMAGE_TAG=v0.2 bash script/build-astroncode-image.sh
# v1 覆盖：ASTRONCODE_DOCKER_VARIANT=v1 IMAGE_TAG=v0.1-test.8 bash script/build-astroncode-image.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_NAME="wildclawbench-astroncode-ubuntu"
IMAGE_TAG="${IMAGE_TAG:-v0.4-ppt}"
ASTRONCODE_DOCKER_VARIANT="${ASTRONCODE_DOCKER_VARIANT:-v4}"

case "${ASTRONCODE_DOCKER_VARIANT}" in
  v1|v2|v3|v4) ;;
  *)
    echo "Unknown AstronCode docker variant: ${ASTRONCODE_DOCKER_VARIANT}" >&2
    exit 1
    ;;
esac

BUILD_CONTEXT="${REPO_ROOT}/docker/astroncode/${ASTRONCODE_DOCKER_VARIANT}"
DOCKERFILE="${BUILD_CONTEXT}/Dockerfile"
# gzip 压缩导出（docker load 直接支持 .tar.gz）；包含 LibreOffice 的镜像更大，
# 需要构建机保留足够的 Docker 临时空间和 Images 输出空间。
TAR_PATH="${REPO_ROOT}/Images/${IMAGE_NAME}_${IMAGE_TAG}.tar.gz"

if [[ ! -f "${DOCKERFILE}" ]]; then
  echo "Unknown AstronCode docker variant: ${ASTRONCODE_DOCKER_VARIANT}" >&2
  echo "Expected Dockerfile at: ${DOCKERFILE}" >&2
  exit 1
fi

BUILD_ARGS=()
if [[ -n "${ASTRON_CODE_VERSION:-}" ]]; then
  BUILD_ARGS+=(--build-arg "ASTRON_CODE_VERSION=${ASTRON_CODE_VERSION}")
fi
if [[ -n "${SEARCH_UPDATER_VERSION:-}" ]]; then
  BUILD_ARGS+=(--build-arg "SEARCH_UPDATER_VERSION=${SEARCH_UPDATER_VERSION}")
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
  -t "${IMAGE_NAME}:${IMAGE_TAG}" \
  "${BUILD_CONTEXT}"

mkdir -p "${REPO_ROOT}/Images"
docker save "${IMAGE_NAME}:${IMAGE_TAG}" | gzip > "${TAR_PATH}"
echo "OK: ${IMAGE_NAME}:${IMAGE_TAG} -> ${TAR_PATH}"
echo "离线加载：docker load -i ${TAR_PATH##*/}"
