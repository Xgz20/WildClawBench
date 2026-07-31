# AstronCode 0.0.13 evaluation image. Runtime credentials and configuration
# are provided when the container starts and are not included in this image.
FROM wildclawbench-codex-ubuntu:v0.0

ARG ASTRON_CODE_VERSION=0.0.13
ARG NPM_REGISTRY=https://depend.iflytek.com/artifactory/api/npm/npm-repo/

RUN npm uninstall -g @iflytek/astron-code >/dev/null 2>&1 || true \
    && npm install -g "@iflytek/astron-code@${ASTRON_CODE_VERSION}" \
      --registry="${NPM_REGISTRY}" \
    && astron-code --version \
    && rm -rf /root/.acode \
    && install -d -m 700 /root/.acode
