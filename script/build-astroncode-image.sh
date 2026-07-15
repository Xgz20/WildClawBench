#!/usr/bin/env bash
# 构建 AstronCode 评测镜像并导出离线 tar 到 Images/。
# 用法：bash script/build-astroncode-image.sh
# 可选：IMAGE_TAG=v0.1 bash script/build-astroncode-image.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_NAME="wildclawbench-astroncode-ubuntu"
IMAGE_TAG="${IMAGE_TAG:-v0.0}"
# gzip 压缩导出（docker load 直接支持 .tar.gz）；镜像 ~11.8GB，压缩后 ~4-5GB
TAR_PATH="${REPO_ROOT}/Images/${IMAGE_NAME}_${IMAGE_TAG}.tar.gz"

docker build \
  -f "${REPO_ROOT}/docker/astroncode/Dockerfile" \
  -t "${IMAGE_NAME}:${IMAGE_TAG}" \
  "${REPO_ROOT}/docker/astroncode"

mkdir -p "${REPO_ROOT}/Images"
docker save "${IMAGE_NAME}:${IMAGE_TAG}" | gzip > "${TAR_PATH}"
echo "OK: ${IMAGE_NAME}:${IMAGE_TAG} -> ${TAR_PATH}"
echo "离线加载：docker load -i ${TAR_PATH##*/}"
