# Original CLI evaluation images can be reused through EVAL_BASE_IMAGE.
ARG EVAL_BASE_IMAGE=python:3.11-bookworm
ARG NODE_RUNTIME_IMAGE=node:24-bookworm-slim
FROM ${NODE_RUNTIME_IMAGE} AS node-runtime
FROM ${EVAL_BASE_IMAGE}
ARG CODEX_VERSION=0.171.0
ARG DSH_VERSION=0.1.2-rc.1
ARG NPM_REGISTRY=https://registry.npmmirror.com
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG DEBIAN_MIRROR=https://mirrors.tuna.tsinghua.edu.cn/debian
ARG DEBIAN_SECURITY_MIRROR=https://mirrors.tuna.tsinghua.edu.cn/debian-security
COPY --from=node-runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=node-runtime /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/npm
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/scoring-runtime/playwright-browsers
RUN ln -sf ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && ln -sf ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
 && pip install --no-cache-dir uv==0.13.6 pyyaml==6.0.3 jsonschema==4.26.0 openpyxl==3.1.5 playwright==1.55.0
RUN if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
      sed -i "s|http://deb.debian.org/debian-security|${DEBIAN_SECURITY_MIRROR}|g; s|http://deb.debian.org/debian|${DEBIAN_MIRROR}|g" /etc/apt/sources.list.d/debian.sources; \
    fi \
 && python -m playwright install-deps chromium \
 && rm -rf /var/lib/apt/lists/*
COPY runtime-skill /opt/runtime-score-skill
RUN python /opt/runtime-score-skill/scripts/score_general_e2e.py bootstrap-runtime --venv-root /opt/scoring-runtime \
 && /opt/scoring-runtime/bin/python /opt/runtime-score-skill/scripts/offline_browser_validate.py --probe --output-dir /opt/scoring-browser-preflight
COPY wcb-dsh /usr/local/bin/wcb-dsh
RUN chmod 755 /usr/local/bin/wcb-dsh \
 && npm install -g --registry="${NPM_REGISTRY}" "@openai/codex@${CODEX_VERSION}" "@deepseek-ai/dsh@${DSH_VERSION}" \
 && codex --version && dsh --version \
 && rm -rf /root/.codex /root/.dsh
COPY validate_runtime.py /opt/validate-scorer-runtime.py
COPY build-manifest.json /opt/scorer-build-manifest.json
LABEL org.astron.eval.role="headless-scorer" \
      org.astron.eval.codex.version="${CODEX_VERSION}" \
      org.astron.eval.dsh.version="${DSH_VERSION}"
ENV PYTHONUTF8=1 DSH_TELEMETRY_DISABLED=1 DEEPSEEK_SEARCH_ENABLED=false
WORKDIR /job
ENTRYPOINT []
