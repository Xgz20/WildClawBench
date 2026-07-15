# AstronCode 评测镜像：在 codex 评测镜像之上叠加 @iflytek/astron-code CLI。
# 构建需要访问 iflytek 内网 npm registry；离线分发通过 docker save 出 tar。
FROM wildclawbench-codex-ubuntu:v0.0

ARG ASTRON_CODE_VERSION=0.0.5-benchmark-adapt.10
ARG NPM_REGISTRY=https://depend.iflytek.com/artifactory/api/npm/npm-repo/

RUN npm install -g "@iflytek/astron-code@${ASTRON_CODE_VERSION}" \
      --registry="${NPM_REGISTRY}" \
    && astron-code --version
