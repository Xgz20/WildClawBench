# Incremental AMD64 release. Parent images are read-only build inputs.
ARG EVAL_BASE_IMAGE=wildclawbench-e2e-scorer:codex-0.171.0-office-v1
ARG CLAUDE_CODE_IMAGE=wildclawbench-claudecode-ubuntu:v0.4
FROM ${CLAUDE_CODE_IMAGE} AS claude-source
FROM ${EVAL_BASE_IMAGE}
ARG CODEX_VERSION=0.171.0
ARG DSH_VERSION=0.1.2-rc.1
ARG CLAUDE_CODE_VERSION=2.1.330
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/scoring-runtime/playwright-browsers \
    PYTHONUTF8=1 DSH_TELEMETRY_DISABLED=1 DEEPSEEK_SEARCH_ENABLED=false \
    CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 DISABLE_AUTOUPDATER=1
COPY --from=claude-source /usr/local/lib/node_modules/@anthropic-ai /usr/local/lib/node_modules/@anthropic-ai
RUN node -e 'const fs=require("fs"),p="/usr/local/lib/node_modules/@anthropic-ai/claude-code";const b=require(p+"/package.json").bin;fs.rmSync("/usr/local/bin/claude",{force:true});fs.symlinkSync(p+"/"+(typeof b==="string"?b:b.claude),"/usr/local/bin/claude")' \
 && rm -rf /root/.codex /root/.dsh /root/.claude /root/.claude.json /opt/runtime-score-skill
COPY runtime-skill /opt/runtime-score-skill
COPY wcb-dsh /usr/local/bin/wcb-dsh
COPY validate_runtime.py /opt/validate-scorer-runtime.py
COPY build-manifest.json /opt/scorer-build-manifest.json
# Reuse only a runtime with the identical frozen lock; then probe it with the new Skill.
RUN chmod 755 /usr/local/bin/wcb-dsh \
 && /opt/scoring-runtime/bin/python -c 'import hashlib,json,pathlib; p=pathlib.Path("/opt/runtime-score-skill/references/scoring-runtime-lock.json"); m=json.loads(pathlib.Path("/opt/scoring-runtime/general-e2e-runtime.json").read_text()); assert m["runtime_lock_sha256"]==hashlib.sha256(p.read_bytes()).hexdigest(), "SCORER_PARENT_RUNTIME_LOCK_MISMATCH"' \
 && /opt/scoring-runtime/bin/python /opt/runtime-score-skill/scripts/score_general_e2e.py probe-runtime --runtime-python /opt/scoring-runtime/bin/python \
 && /opt/scoring-runtime/bin/python /opt/validate-scorer-runtime.py --office --output /opt/scorer-preflight.json
LABEL org.astron.eval.role="headless-scorer" \
      org.astron.eval.codex.version="${CODEX_VERSION}" \
      org.astron.eval.dsh.version="${DSH_VERSION}" \
      org.astron.eval.claudecode.version="${CLAUDE_CODE_VERSION}" \
      org.astron.eval.scorer.version="v0.3"
WORKDIR /job
ENTRYPOINT []
