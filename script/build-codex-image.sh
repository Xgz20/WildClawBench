#!/usr/bin/env bash
# 构建 Codex CLI 升级镜像并导出离线 tar 到 Images/。
# 用法：bash script/build-codex-image.sh
# 默认在 wildclawbench-codex-ubuntu:v0.0 之上安装 Codex CLI 0.146.0，产出 :v0.1。
# 换版本：CODEX_VERSION=0.145.0 IMAGE_TAG=v0.1-codex0.145 bash script/build-codex-image.sh
# 换源：NPM_REGISTRY=https://registry.npmjs.org/ bash script/build-codex-image.sh
# 跳过导出（只本地构建，省 5GB 磁盘与压缩时间）：SKIP_SAVE=1 bash script/build-codex-image.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_NAME="wildclawbench-codex-ubuntu"
IMAGE_TAG="${IMAGE_TAG:-v0.1}"
BASE_IMAGE="${EVAL_BASE_IMAGE:-wildclawbench-codex-ubuntu:v0.0}"

BUILD_CONTEXT="${REPO_ROOT}/docker/codex"
DOCKERFILE="${BUILD_CONTEXT}/Dockerfile"
# gzip 压缩导出（docker load 直接支持 .tar.gz）
TAR_PATH="${REPO_ROOT}/Images/${IMAGE_NAME}_${IMAGE_TAG}.tar.gz"

if [[ ! -f "${DOCKERFILE}" ]]; then
  echo "Missing Codex Dockerfile at: ${DOCKERFILE}" >&2
  exit 1
fi

# 覆盖底座会把升级层盖回自己身上，产生自引用的不可复现镜像。
if [[ "${BASE_IMAGE}" == "${IMAGE_NAME}:${IMAGE_TAG}" ]]; then
  echo "Refusing to build ${IMAGE_NAME}:${IMAGE_TAG} on top of itself" >&2
  echo "Set a different IMAGE_TAG or EVAL_BASE_IMAGE." >&2
  exit 1
fi

if ! docker image inspect "${BASE_IMAGE}" >/dev/null 2>&1; then
  echo "Base image not found locally: ${BASE_IMAGE}" >&2
  echo "Load it first: docker load -i Images/wildclawbench-codex-ubuntu_v0.0.tar" >&2
  exit 1
fi

BUILD_ARGS=(--build-arg "EVAL_BASE_IMAGE=${BASE_IMAGE}")
if [[ -n "${CODEX_VERSION:-}" ]]; then
  BUILD_ARGS+=(--build-arg "CODEX_VERSION=${CODEX_VERSION}")
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

# 记录实际装进镜像的版本，便于对齐评测报告口径。
INSTALLED_VERSION="$(docker run --rm --entrypoint codex "${IMAGE_NAME}:${IMAGE_TAG}" --version 2>/dev/null | head -1 || true)"
echo "Installed Codex CLI: ${INSTALLED_VERSION:-unknown}"

if [[ "${SKIP_SAVE:-}" == "1" ]]; then
  echo "OK: ${IMAGE_NAME}:${IMAGE_TAG} (SKIP_SAVE=1，未导出 tar)"
else
  mkdir -p "${REPO_ROOT}/Images"
  docker save "${IMAGE_NAME}:${IMAGE_TAG}" | gzip > "${TAR_PATH}"
  echo "OK: ${IMAGE_NAME}:${IMAGE_TAG} -> ${TAR_PATH}"
  echo "离线加载：docker load -i ${TAR_PATH##*/}"
fi

echo "启用：export DOCKER_IMAGE_CODEX='${IMAGE_NAME}:${IMAGE_TAG}'"
