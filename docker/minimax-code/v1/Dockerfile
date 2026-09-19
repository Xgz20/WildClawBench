ARG EVAL_BASE_IMAGE=wildclawbench-codex-ubuntu:v0.0
ARG NODE_RUNTIME_IMAGE=node:24-bookworm-slim

FROM ${NODE_RUNTIME_IMAGE} AS node-runtime
FROM ${EVAL_BASE_IMAGE}

ARG MCODE_VERSION=0.4.12
ARG NPM_REGISTRY=https://registry.npmjs.org/

ENV MINIMAX_DATA_DIR=/tmp/wildclaw_mcode \
    MCODE_DISABLE_TELEMETRY=1 \
    DO_NOT_TRACK=1

# MiniMax Code requires Node >=22.19. Keep the Codex v0.0 evaluation base's
# Python, browser, document and media toolchain, and replace only Node/npm.
COPY --from=node-runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=node-runtime /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/npm
COPY --from=node-runtime /usr/local/lib/node_modules/corepack /usr/local/lib/node_modules/corepack

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash ca-certificates curl g++ git make python3 ripgrep \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -sf ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && ln -sf ../lib/node_modules/corepack/dist/corepack.js /usr/local/bin/corepack \
    && node --version | grep '^v24\.' \
    && npm config set registry "${NPM_REGISTRY}" \
    && npm install -g --ignore-scripts=false --include=optional "@minimax-ai/code@${MCODE_VERSION}" \
    && mcode --version | grep -Fx "${MCODE_VERSION}" \
    && npm cache clean --force

WORKDIR /tmp_workspace

COPY --chmod=0755 wcb-mcode /usr/local/bin/wcb-mcode

ENTRYPOINT ["/usr/local/bin/wcb-mcode"]
