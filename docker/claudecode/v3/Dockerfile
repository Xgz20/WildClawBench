ARG EVAL_BASE_IMAGE=wildclawbench-codex-ubuntu:v0.0
ARG NODE_RUNTIME_IMAGE=node:24-bookworm-slim

FROM ${NODE_RUNTIME_IMAGE} AS node-runtime
FROM ${EVAL_BASE_IMAGE}

ARG CLAUDE_CODE_VERSION=2.1.250
ARG NPM_REGISTRY=https://registry.npmjs.org

ENV CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 \
    DISABLE_AUTOUPDATER=1

COPY --from=node-runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=node-runtime /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/npm
COPY --from=node-runtime /usr/local/lib/node_modules/corepack /usr/local/lib/node_modules/corepack

RUN ln -sf ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -sf ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && ln -sf ../lib/node_modules/corepack/dist/corepack.js /usr/local/bin/corepack \
    && node --version | grep '^v24\.' \
    && npm config set registry "${NPM_REGISTRY}" \
    && npm install -g --allow-scripts=@anthropic-ai/claude-code \
      "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}" \
    && claude --version | grep "${CLAUDE_CODE_VERSION}" \
    && npm cache clean --force \
    && rm -rf /root/.claude /root/.claude.json \
    && install -d -m 700 /root/.claude \
    && install -d -m 755 /claude_code/log \
    && test ! -e /claude_code/.env

RUN command -v google-chrome \
    && command -v agent-browser \
    && command -v git \
    && command -v jq \
    && python3 -c 'import fitz, playwright; print("Python evaluation tools ready")'

WORKDIR /tmp_workspace

CMD ["/bin/bash", "-lc", "tail -f /dev/null"]
