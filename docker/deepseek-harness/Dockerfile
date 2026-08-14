ARG EVAL_BASE_IMAGE=wildclawbench-codex-ubuntu:v0.0
ARG NODE_RUNTIME_IMAGE=node:24-bookworm-slim

FROM ${NODE_RUNTIME_IMAGE} AS node-runtime
FROM ${EVAL_BASE_IMAGE}

ARG DSH_VERSION=0.1.0-rc.6
ARG NPM_REGISTRY=https://registry.npmmirror.com

ENV DSH_HOME=/root/.dsh \
    DSH_PERMISSION_MODE=danger-full-access \
    DSH_TELEMETRY_DISABLED=1

# The WCB base currently ships Node 20, while DSH requires Node ^22.19 or >=24.
# Copy the pinned-major runtime from the official Node image without replacing
# the evaluation base's Python, browser, media, and document toolchain.
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
    && npm install -g "@deepseek-ai/dsh@${DSH_VERSION}" \
    && dsh --version \
    && npm cache clean --force

WORKDIR /tmp_workspace

COPY --chmod=0755 wcb-dsh /usr/local/bin/wcb-dsh

ENTRYPOINT ["/usr/local/bin/wcb-dsh"]
