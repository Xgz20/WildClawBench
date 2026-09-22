ARG NODE_BUILDER_IMAGE=node:24.14.0-bookworm-slim
ARG EVAL_BASE_IMAGE=wildclawbench-codex-ubuntu:v0.0

FROM ${NODE_BUILDER_IMAGE} AS zcode-builder

ARG ZCODE_VERSION=0.16.9
ARG ZCODE_SOURCE_COMMIT=872ad960de7ec172591f7e1952f7849229f94521
ARG ZCODE_REPOSITORY=https://github.com/Xgz20/ZCode.git
ARG NPM_REGISTRY=https://registry.npmjs.org/

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl git python3 make g++ tar unzip xz-utils \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --filter=blob:none --no-checkout "${ZCODE_REPOSITORY}" /opt/zcode-src \
    && cd /opt/zcode-src \
    && git checkout --detach "${ZCODE_SOURCE_COMMIT}" \
    && test "$(git rev-parse HEAD)" = "${ZCODE_SOURCE_COMMIT}" \
    && python3 -c 'from pathlib import Path; m="supportedArchitectures:\\n"; replacement="supportedArchitectures:\\n  os:\\n    - linux\\n  cpu:\\n    - x64\\n  libc:\\n    - glibc\\n"; f=lambda p: p.write_text((lambda t: t.split(m, 1)[0] + replacement if m in t else t)(p.read_text(encoding="utf-8")), encoding="utf-8"); [f(p) for p in (Path("/opt/zcode-src/pnpm-workspace.yaml"), Path("/opt/zcode-src/apps/zcode-cli/pnpm-workspace.yaml"))]' \
    && if [ "${NPM_REGISTRY}" != "https://registry.npmjs.org/" ]; then \
         sed -i "s#https://registry.npmjs.org/#${NPM_REGISTRY%/}/#g" pnpm-lock.yaml apps/zcode-cli/pnpm-lock.yaml; \
       fi

WORKDIR /opt/zcode-src

RUN corepack enable \
    && corepack prepare pnpm@10.33.2 --activate \
    && sed -i "s#^registry=.*#registry=${NPM_REGISTRY%/}#" .npmrc \
    && pnpm config set registry "${NPM_REGISTRY}" \
    && npm_config_nodedir=/usr/local pnpm install --frozen-lockfile \
       --filter '@zcode/cli...' \
       --filter '@zcode/node-repl-host...' \
       --filter '@zcode/browser-use-plugin...' \
    && pnpm --filter '@zcode/cli...' build \
    && pnpm --filter '@zcode/node-repl-host' build \
    && pnpm --filter '@zcode/browser-use-plugin' build \
    && pnpm exec tsc -p packages/shared/tsconfig.json \
    && node apps/zcode-cli/packages/cli/scripts/build-sea.mjs \
       --target linux-x64 \
       --node-binary linux-x64=/usr/local/bin/node \
    && test -x apps/zcode-cli/packages/cli/dist/zcode-linux-x64 \
    && test "$(apps/zcode-cli/packages/cli/dist/zcode-linux-x64 --version)" = "${ZCODE_VERSION}"

FROM ${EVAL_BASE_IMAGE}

ARG ZCODE_VERSION=0.16.9
ARG ZCODE_SOURCE_COMMIT=872ad960de7ec172591f7e1952f7849229f94521

LABEL org.opencontainers.image.title="WildClawBench ZCode evaluation image" \
      org.opencontainers.image.version="${ZCODE_VERSION}" \
      org.opencontainers.image.revision="${ZCODE_SOURCE_COMMIT}"

COPY --from=zcode-builder --chmod=0755 \
  /opt/zcode-src/apps/zcode-cli/packages/cli/dist/zcode-linux-x64 \
  /usr/local/bin/zcode
COPY --chmod=0755 wcb-zcode /usr/local/bin/wcb-zcode

RUN zcode --version | grep -Fx "${ZCODE_VERSION}"

WORKDIR /tmp_workspace
ENTRYPOINT ["/usr/local/bin/wcb-zcode"]
