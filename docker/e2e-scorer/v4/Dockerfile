# Upgrade only Codex/DSH; retain the validated three-CLI runtime and Office layer.
ARG EVAL_BASE_IMAGE=wildclawbench-e2e-scorer:v0.3-amd64
FROM ${EVAL_BASE_IMAGE}
ARG CODEX_VERSION=0.172.0
ARG DSH_VERSION=0.2.2-rc.5
ARG CLAUDE_CODE_VERSION=2.1.330
ARG NPM_REGISTRY=https://registry.npmmirror.com
# The target-platform package cache is a build mount, not an image layer.
RUN --mount=type=bind,source=npm-cache,target=/opt/scorer-npm-cache,rw \
    npm install -g --offline --cache=/opt/scorer-npm-cache --registry="${NPM_REGISTRY}" \
      "@openai/codex@${CODEX_VERSION}" "@deepseek-ai/dsh@${DSH_VERSION}" \
 && codex --version && dsh --version && claude --version \
 && rm -rf /root/.codex /root/.dsh /root/.claude /root/.claude.json /opt/runtime-score-skill
COPY runtime-skill /opt/runtime-score-skill
COPY wcb-dsh /usr/local/bin/wcb-dsh
COPY validate_runtime.py /opt/validate-scorer-runtime.py
COPY build-manifest.json /opt/scorer-build-manifest.json
RUN chmod 755 /usr/local/bin/wcb-dsh \
 && /opt/scoring-runtime/bin/python -c 'import hashlib,json,pathlib;p=pathlib.Path("/opt/runtime-score-skill/references/scoring-runtime-lock.json");m=json.loads(pathlib.Path("/opt/scoring-runtime/general-e2e-runtime.json").read_text());assert m["runtime_lock_sha256"]==hashlib.sha256(p.read_bytes()).hexdigest(),"SCORER_PARENT_RUNTIME_LOCK_MISMATCH"' \
 && /opt/scoring-runtime/bin/python /opt/runtime-score-skill/scripts/score_general_e2e.py probe-runtime --runtime-python /opt/scoring-runtime/bin/python \
 && /opt/scoring-runtime/bin/python /opt/validate-scorer-runtime.py --office --output /opt/scorer-preflight.json
LABEL org.astron.eval.role="headless-scorer" \
      org.astron.eval.codex.version="${CODEX_VERSION}" \
      org.astron.eval.dsh.version="${DSH_VERSION}" \
      org.astron.eval.claudecode.version="${CLAUDE_CODE_VERSION}" \
      org.astron.eval.scorer.version="v0.4"
WORKDIR /job
ENTRYPOINT []
