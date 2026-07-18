# AstronCode >=0.0.6 评测镜像：模型默认配置随 CLI 内置，运行时只写 API Key。
# 构建需要访问 iflytek 内网 npm registry；离线分发通过 docker save 出 tar。
FROM wildclawbench-codex-ubuntu:v0.0

ARG ASTRON_CODE_VERSION=
ARG NPM_REGISTRY=https://depend.iflytek.com/artifactory/api/npm/npm-repo/

RUN npm uninstall -g @iflytek/astron-code >/dev/null 2>&1 || true \
    && if [ -n "${ASTRON_CODE_VERSION}" ]; then \
         package="@iflytek/astron-code@${ASTRON_CODE_VERSION}"; \
       else \
         package="@iflytek/astron-code"; \
       fi \
    && npm install -g "${package}" \
      --registry="${NPM_REGISTRY}" \
    && astron-code --version

RUN mkdir -p /root/.acode && chmod 700 /root/.acode
