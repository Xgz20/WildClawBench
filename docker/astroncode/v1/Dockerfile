# AstronCode <=0.0.5 评测镜像：旧版需要额外烘焙 astron-spark provider/catalog/profile。
# 构建 context 使用 docker/astroncode/v1，以便 COPY codex-astron-config。
FROM wildclawbench-codex-ubuntu:v0.0

ARG ASTRON_CODE_VERSION=0.0.5-test.8
ARG NPM_REGISTRY=https://depend.iflytek.com/artifactory/api/npm/npm-repo/

RUN npm uninstall -g @iflytek/astron-code >/dev/null 2>&1 || true \
    && npm install -g "@iflytek/astron-code@${ASTRON_CODE_VERSION}" \
      --registry="${NPM_REGISTRY}" \
    && astron-code --version

COPY codex-astron-config /opt/codex-astron-config
RUN CODEX_HOME=/root/.acode sh /opt/codex-astron-config/scripts/install-macos-linux.sh \
    && cat /root/.acode/config.toml
