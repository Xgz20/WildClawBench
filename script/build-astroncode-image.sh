#!/usr/bin/env bash
# 构建 AstronCode 评测镜像并导出离线 tar 到 Images/。
# 用法：bash script/build-astroncode-image.sh
# 默认构建 v2（AstronCode 0.0.6+ 安装方式，按 registry latest 安装）。
# 可选：ASTRON_CODE_VERSION=0.0.6 IMAGE_TAG=v0.2 bash script/build-astroncode-image.sh
# 可选：ASTRONCODE_DOCKER_VARIANT=v1 IMAGE_TAG=v0.1-test.8 bash script/build-astroncode-image.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_NAME="wildclawbench-astroncode-ubuntu"
IMAGE_TAG="${IMAGE_TAG:-v0.2}"
ASTRONCODE_DOCKER_VARIANT="${ASTRONCODE_DOCKER_VARIANT:-v2}"
BUILD_CONTEXT="${REPO_ROOT}/docker/astroncode/${ASTRONCODE_DOCKER_VARIANT}"
DOCKERFILE="${BUILD_CONTEXT}/Dockerfile"
# gzip 压缩导出（docker load 直接支持 .tar.gz）；镜像 ~11.8GB，压缩后 ~4-5GB
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
