# OpenCode 评测镜像：在 codex 评测镜像之上叠加 opencode CLI（npm 全局安装）。
# 复用 codex 镜像的 conda/playwright/node20 全套评测环境，只叠加一层 npm 安装。
# 离线分发通过 docker save 出 tar.gz。
FROM wildclawbench-codex-ubuntu:v0.0

# 锁定版本以保证镜像可复现（当前评测基线 1.18.4）；重建/升级只需改此默认值或传 --build-arg。
ARG OPENCODE_VERSION=1.18.4
# 默认用公共 npm registry；内网构建可传 --build-arg NPM_REGISTRY=...
ARG NPM_REGISTRY=https://registry.npmjs.org/

# 上游 npm 包名是 opencode-ai（安装出 /usr/bin/opencode），非 opencode。
RUN if [ -n "${OPENCODE_VERSION}" ]; then \
      pkg="opencode-ai@${OPENCODE_VERSION}"; \
    else \
      pkg="opencode-ai"; \
    fi \
    && npm install -g "$pkg" --registry="${NPM_REGISTRY}" \
    && opencode --version

# config 目录（OPENCODE_CONFIG_CONTENT 经 env 注入，无需预置文件）
# data 目录（XDG_DATA_HOME=/root/.local/share，opencode.db + storage + log 落此）
RUN mkdir -p /root/.config/opencode /root/.local/share/opencode \
    && chmod -R 700 /root/.config/opencode /root/.local/share/opencode
