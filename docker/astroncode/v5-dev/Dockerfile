# AstronCode 0.0.35 development evaluation image.
# Runtime credentials and model configuration are not included in this image.
FROM wildclawbench-astroncode-ubuntu:v0.5

ARG ASTRON_CODE_DEV_VERSION=0.0.35
ARG NPM_REGISTRY=https://depend.iflytek.com/artifactory/api/npm/npm-repo/

RUN npm uninstall -g @iflytek/astron-code @iflytek/astron-code-dev \
      >/dev/null 2>&1 || true \
    && npm install -g "@iflytek/astron-code-dev@${ASTRON_CODE_DEV_VERSION}" \
      --registry="${NPM_REGISTRY}" \
    && command -v astron-code-dev \
    && astron-code-dev --version \
    && ! command -v astron-code >/dev/null 2>&1
