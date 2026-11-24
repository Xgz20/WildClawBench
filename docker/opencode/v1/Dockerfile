ARG EVAL_BASE_IMAGE=wildclawbench-codex-ubuntu:v0.0
FROM ${EVAL_BASE_IMAGE}

ARG OPENCODE_VERSION=1.18.4
ARG NPM_REGISTRY=https://registry.npmjs.org/

RUN npm install -g "opencode-ai@${OPENCODE_VERSION}" --registry="${NPM_REGISTRY}" \
    && opencode --version

RUN mkdir -p /root/.config/opencode /root/.local/share/opencode \
    && chmod -R 700 /root/.config/opencode /root/.local/share/opencode
