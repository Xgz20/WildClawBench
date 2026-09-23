ARG EVAL_BASE_IMAGE=wildclawbench-codex-ubuntu:v0.0

FROM ${EVAL_BASE_IMAGE}

ARG MIMOCODE_VERSION=0.1.14
ARG NPM_REGISTRY=https://registry.npmjs.org/

RUN npm install --global --registry="${NPM_REGISTRY}" "@mimo-ai/cli@${MIMOCODE_VERSION}" \
    && mimo --version | grep -Fx "${MIMOCODE_VERSION}"

COPY --chmod=0755 wcb-mimocode /usr/local/bin/wcb-mimocode

RUN mimo --version | grep -Fx "${MIMOCODE_VERSION}"

WORKDIR /tmp_workspace
ENTRYPOINT ["/usr/local/bin/wcb-mimocode"]
