FROM node:24-bookworm-slim

ARG DSH_VERSION=0.1.0-rc.6
ARG NPM_REGISTRY=https://registry.npmmirror.com

ENV DSH_HOME=/root/.dsh \
    DSH_PERMISSION_MODE=danger-full-access \
    DSH_TELEMETRY_DISABLED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash ca-certificates curl g++ git make python3 ripgrep \
    && rm -rf /var/lib/apt/lists/* \
    && npm config set registry "${NPM_REGISTRY}" \
    && npm install -g "@deepseek-ai/dsh@${DSH_VERSION}" \
    && dsh --version \
    && npm cache clean --force

WORKDIR /tmp_workspace

COPY --chmod=0755 wcb-dsh /usr/local/bin/wcb-dsh

ENTRYPOINT ["/usr/local/bin/wcb-dsh"]
