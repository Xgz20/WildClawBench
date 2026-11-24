ARG EVAL_BASE_IMAGE=wildclawbench-codex-ubuntu:v0.0
FROM ${EVAL_BASE_IMAGE}

# Latest pinned Codex CLI for the Spark-X2.6 evaluation round.
ARG CODEX_VERSION=0.171.0
ARG NPM_REGISTRY=https://registry.npmmirror.com

RUN npm config set registry "${NPM_REGISTRY}" \
    && npm uninstall -g @openai/codex >/dev/null 2>&1 || true \
    && npm install -g "@openai/codex@${CODEX_VERSION}" --registry="${NPM_REGISTRY}" \
    && codex --version \
    && rm -rf /root/.codex \
    && install -d -m 700 /root/.codex /root/.codex/sessions
