# DeepSeek Harness PoC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a pinned DeepSeek Harness Docker image and a standalone converter/runner PoC that emits WildClawBench-compatible transcript and usage artifacts.

**Architecture:** A Node 24 image installs the published DSH CLI and writes raw, uncompressed session logs to a mounted directory. A standard-library Python module converts those logs into OpenClaw-compatible messages and WCB usage totals; a thin CLI runs conversion alone or orchestrates one Docker task without registering a production backend.

**Tech Stack:** Docker, Bash, Node.js 24, `@deepseek-ai/dsh@0.1.0-rc.6`, Python 3.11 `unittest`.

---

### Task 1: Define the transcript and usage conversion contract

**Files:**
- Create: `tests/fixtures/deepseek_harness/session.jsonl`
- Create: `tests/fixtures/deepseek_harness/child/session.jsonl`
- Create: `tests/test_deepseek_harness_transcript.py`
- Create: `src/agents/deepseek_harness/__init__.py`
- Create: `src/agents/deepseek_harness/transcript.py`

- [x] **Step 1: Write failing conversion tests**

Create fixture events for `user/message`, `assistant/message`, `tool/call`, `tool/result`, usage, and one child session. Assert `convert_sessions()` returns OpenClaw messages and aggregated WCB totals, rejects malformed JSONL, and deduplicates a tool call already present in an assistant message.

- [x] **Step 2: Run tests and verify RED**

Run: `python -m unittest tests/test_deepseek_harness_transcript.py -v`

Expected: import failure because `src.agents.deepseek_harness.transcript` does not exist.

- [x] **Step 3: Implement the minimal converter**

Expose:

```python
class DshSessionFormatError(ValueError): ...

def convert_sessions(session_root: Path) -> ConversionResult: ...
def write_conversion(session_root: Path, output_dir: Path) -> ConversionResult: ...
```

`ConversionResult` contains `messages`, `usage`, and source session metadata. Read `session.jsonl` recursively, validate the header, map four event types, aggregate only assistant-message usage, and write `chat.jsonl`, `usage.json`, and `conversion_manifest.json` atomically.

- [x] **Step 4: Run tests and verify GREEN**

Run: `python -m unittest tests/test_deepseek_harness_transcript.py -v`

Expected: all conversion tests pass.

### Task 2: Add the standalone PoC CLI

**Files:**
- Create: `tests/test_deepseek_harness_poc.py`
- Create: `tools/deepseek_harness_poc.py`

- [x] **Step 1: Write failing CLI tests**

Test `convert` end to end with a temporary output directory. Test Docker command construction through a pure `build_docker_command()` function, asserting workspace/session mounts, model variables, inherited credential names, timeout/container cleanup inputs, and absence of secret values in manifest data.

- [x] **Step 2: Run tests and verify RED**

Run: `python -m unittest tests/test_deepseek_harness_poc.py -v`

Expected: import failure because `tools.deepseek_harness_poc` does not exist.

- [x] **Step 3: Implement CLI and Docker orchestration**

Implement `convert` and `run`. `run` creates a unique container name, mounts the workspace read-write and output sessions directory, inherits API key environment names, captures stdout/stderr into the output directory, enforces timeout, removes the container in `finally`, and converts any persisted session before returning the DSH exit code.

- [x] **Step 4: Run tests and verify GREEN**

Run: `python -m unittest tests/test_deepseek_harness_poc.py -v`

Expected: all CLI tests pass without Docker or network access.

### Task 3: Build the pinned Docker image

**Files:**
- Create: `docker/deepseek-harness/Dockerfile`
- Create: `docker/deepseek-harness/wcb-dsh`
- Create: `docker/deepseek-harness/README.md`
- Create: `tests/test_deepseek_harness_docker.py`

- [x] **Step 1: Write failing static contract tests**

Assert the Dockerfile defaults to Node 24 and DSH `0.1.0-rc.6`, uses `npm install -g`, and invokes `dsh --version`. Assert the entrypoint requires `DSH_MODEL_ID` and `OPENROUTER_API_KEY`, disables telemetry/title generation, uses raw session JSONL, keeps DeepSeek Search enabled, and executes the headless profile with `--patch` before the task argument.

- [x] **Step 2: Run tests and verify RED**

Run: `python -m unittest tests/test_deepseek_harness_docker.py -v`

Expected: missing Docker files cause assertion failures.

- [x] **Step 3: Implement Docker and entrypoint files**

Install the pinned npm package with Node 24 in the WCB evaluation base. Generate a Cordis patch from environment expressions without embedding credentials. Persist sessions below `$DSH_HOME/sessions`, disable session-title LLM and telemetry, and run from `/tmp_workspace`.

- [x] **Step 4: Run static tests and build smoke**

Run: `python -m unittest tests/test_deepseek_harness_docker.py -v`

Run: `docker build -t wildclawbench-deepseek-harness-poc:0.1.0-rc.6 docker/deepseek-harness`

Run: `docker run --rm --entrypoint dsh wildclawbench-deepseek-harness-poc:0.1.0-rc.6 --version`

Expected: tests pass, build exits 0, version output contains `0.1.0-rc.6`.

### Task 4: Verify compatibility and document evidence

**Files:**
- Modify: `tests/test_deepseek_harness_transcript.py`
- Modify: `docker/deepseek-harness/README.md`

- [x] **Step 1: Add compatibility assertions**

Feed generated `chat.jsonl` into `extract_usage_from_jsonl()` and `_load_tool_pairs()`. Assert both agree with the converter totals and tool statuses.

- [x] **Step 2: Run focused and adjacent regression tests**

Run:

```bash
python -m unittest \
  tests/test_deepseek_harness_transcript.py \
  tests/test_deepseek_harness_poc.py \
  tests/test_deepseek_harness_docker.py \
  tests/test_tool_metrics.py -v
```

Expected: all focused and adjacent tests pass.

- [x] **Step 3: Run source and artifact checks**

Run: `python -m compileall -q src/agents/deepseek_harness tools/deepseek_harness_poc.py tests/test_deepseek_harness_*.py`

Run: `git diff --check`

Expected: both commands exit 0.

- [x] **Step 4: Update README with verified and unverified boundaries**

Document exact build/convert/run commands, output artifacts, credential handling, and whether Docker build, no-key behavior, and real-model smoke were actually executed.

### Task 5: Commit only PoC files

**Files:**
- Stage only the files listed in Tasks 1-4 and the approved spec/plan.

- [x] **Step 1: Inspect status and diff**

Run: `git status --short` and `git diff --check`.

- [x] **Step 2: Run final verification**

Repeat the complete focused test command, compileall, Docker version smoke when the image built, and inspect that no credential value appears in tracked files or generated manifests.

- [x] **Step 3: Create Chinese Conventional Commit**

Run:

```bash
git add docs/superpowers/specs/2026-08-14-deepseek-harness-poc-design.md \
  docs/superpowers/plans/2026-08-14-deepseek-harness-poc.md \
  docker/deepseek-harness src/agents/deepseek_harness \
  tools/deepseek_harness_poc.py tests/fixtures/deepseek_harness \
  tests/test_deepseek_harness_transcript.py \
  tests/test_deepseek_harness_poc.py \
  tests/test_deepseek_harness_docker.py
git commit -m "feat(deepseek-harness): 增加 Docker 与轨迹转换 PoC"
```

### Follow-up: Align Evaluation Base and Reasoning Metadata

- [x] Use `wildclawbench-codex-ubuntu:v0.0` as the final image while copying
  the Node 24 runtime required by DSH.
- [x] Verify base-layer inheritance, root execution, WCB dependency retention,
  and `node-pty` process spawning.
- [x] Declare `DSH_REASONING` in the hand-declared model's
  `reasoningEfforts` before selecting that effort.
- [x] Run a credentialed `xopglm52` smoke without persisting credentials. The
  request reached MaaS but returned HTTP 401, so no successful real-model task
  is claimed.
