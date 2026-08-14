# DeepSeek Harness Formal Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a production `deepseek-harness` backend to WildClawBench that runs DSH in the normal evaluation lifecycle and emits gradable transcript, usage, task output, anomaly, and report artifacts.

**Architecture:** A native `DeepSeekHarnessAgent(BaseAgent)` starts a detached evaluation container, copies read-only task input into `/tmp_workspace`, installs task skills under `$DSH_HOME/skills`, and executes `wcb-dsh` while the container remains alive for grading. The existing session converter preserves raw JSONL, writes OpenClaw-compatible `chat.jsonl` and usage, and copies the transcript back to the path expected by graders.

**Tech Stack:** Python 3.11, `unittest`, Docker, Bash, DeepSeek Harness `0.1.0-rc.6`, WildClawBench runner/grading/report utilities.

---

### Task 1: Implement Runner Configuration and Container Contract

**Files:**
- Create: `tests/test_deepseek_harness_runner.py`
- Create: `src/agents/deepseek_harness/runner.py`

- [ ] **Step 1: Write failing configuration tests**

Test these public behaviors with `unittest.TestCase`:

```python
from src.agents.deepseek_harness.runner import (
    DEFAULT_DSH_API,
    build_container_command,
    normalize_dsh_model_id,
    resolve_dsh_config,
)

self.assertEqual(normalize_dsh_model_id("openrouter/xopglm52"), "xopglm52")
self.assertEqual(
    normalize_dsh_model_id("openrouter/anthropic/model"),
    "anthropic/model",
)
self.assertEqual(normalize_dsh_model_id("xopglm52"), "xopglm52")

config = resolve_dsh_config(
    image="dsh:test",
    openrouter_api_key="test-key",
    openrouter_base_url="https://maas.example/v2",
)
self.assertEqual(config.api, DEFAULT_DSH_API)
self.assertEqual(config.openrouter_base_url, "https://maas.example/v2")
```

Assert an unsupported API raises `ValueError`. Assert `build_container_command()` includes detached mode, `--entrypoint /bin/bash`, resource limits, a read-only `<workspace>/exec:/mnt/wildclaw_src` mount, model/API/key env, and `tail -f /dev/null`. Empty base URL and DeepSeek Search key must be omitted rather than emitted as empty values.

- [ ] **Step 2: Run tests and verify RED**

```bash
uv run python -m unittest tests/test_deepseek_harness_runner.py -v
```

Expected: import failure because `runner.py` does not exist.

- [ ] **Step 3: Implement configuration and startup**

Define:

```python
SUPPORTED_DSH_APIS = ("openai-completions", "openai-responses")
DEFAULT_DSH_API = "openai-completions"
DEFAULT_IMAGE = "wildclawbench-deepseek-harness-ubuntu:v0.0"
DSH_HOME = "/root/.dsh"
DSH_SESSIONS_DIR = f"{DSH_HOME}/sessions"
DSH_SKILLS_DIR = f"{DSH_HOME}/skills"
OPENCLAW_TRANSCRIPT_PATH = "/root/.openclaw/agents/main/sessions/chat.jsonl"
SRC_MOUNT = "/mnt/wildclaw_src"
PROMPT_PATH = "/tmp/wildclaw_dsh_prompt.txt"


def normalize_dsh_model_id(model: str) -> str:
    return model.strip().removeprefix("openrouter/")
```

Define a frozen `DeepSeekHarnessConfig` and `resolve_dsh_config()` that resolve image, key, base URL and API from explicit argument, then environment, then documented defaults. Validate API membership. Implement atomic `write_execution_status()` and JSONL `append_agent_log_event()` helpers. Implement `build_container_command()` as a pure function and a subprocess startup wrapper; validate the key before `docker run`. Do not define or export `DeepSeekHarnessAgent` in this task, so this intermediate commit has no partially implemented abstract `BaseAgent` subclass.

- [ ] **Step 4: Run tests and verify GREEN**

Run the Step 2 command. Expected: all configuration and command tests pass without Docker.

- [ ] **Step 5: Commit**

```bash
git add src/agents/deepseek_harness/runner.py \
  tests/test_deepseek_harness_runner.py
git commit -m "feat(deepseek-harness): 增加容器配置与命令构建"
```

### Task 2: Implement Workspace, Skills, Prompt, and Timeout Lifecycle

**Files:**
- Modify: `src/agents/deepseek_harness/runner.py`
- Modify: `src/agents/deepseek_harness/__init__.py`
- Modify: `tests/test_deepseek_harness_runner.py`

- [ ] **Step 1: Write failing lifecycle tests**

Instantiate `DeepSeekHarnessAgent` with a resolved test config, then build an `AgentTaskSpec` with a temporary `<workspace>/exec`. Patch Docker boundaries and verify this order:

```text
initialize status -> start container -> probe version -> prepare workspace
-> setup_skills(/root/.dsh/skills) -> run_warmup(detach_background=True)
-> snapshot_workspace_state -> copy prompt -> run DSH -> export sessions
```

Assert `thinking="high"` becomes `DSH_REASONING=high`. Assert the Docker exec command reads the container prompt file and does not contain the prompt text. Add missing-key, nonzero exit, and timeout cases. Timeout must terminate DSH inside the container and return `AgentExecution(error="DeepSeek Harness run timed out", elapsed_time=timeout)`.

- [ ] **Step 2: Run tests and verify RED**

```bash
uv run python -m unittest tests/test_deepseek_harness_runner.py -v
```

Expected: failures because `run_task()` and its lifecycle helpers are absent.

- [ ] **Step 3: Implement the lifecycle**

Create `DeepSeekHarnessAgent(BaseAgent)` with concrete `expects_gateway`, `transcript_container_path`, `run_task()` and `collect_usage()` methods so the class is immediately instantiable. Export the class and existing conversion API from `src/agents/deepseek_harness/__init__.py`. Use `setup_skills`, `run_warmup`, `snapshot_workspace_state`, and `container_resource_args` from `src.utils.docker_utils`. Prepare workspace with:

```bash
mkdir -p /tmp_workspace
cp -r /mnt/wildclaw_src/. /tmp_workspace
chmod -R u+w /tmp_workspace
```

Transfer the prompt with a temporary host file and `docker cp`, deleting the host file in `finally`. Execute:

```bash
cd /tmp_workspace
echo $$ > /tmp/wildclaw_dsh.pid
exec /usr/local/bin/wcb-dsh "$(cat /tmp/wildclaw_dsh_prompt.txt)"
```

Capture stdout/stderr in `<output_dir>/agent.log`. Wait with the task timeout. On timeout, TERM then KILL the PID from `/tmp/wildclaw_dsh.pid`, kill the host `docker exec`, and stop all task mutation before grading.

Do not return from `run_task()` until session export has run. Record Harness version, image, API, normalized model, elapsed time, exit code, timeout and failure stage in `execution_status.json`.

- [ ] **Step 4: Run tests and verify GREEN**

Run the Step 2 command. Expected: normal, missing-key, nonzero-exit and timeout lifecycle tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/agents/deepseek_harness/runner.py \
  src/agents/deepseek_harness/__init__.py \
  tests/test_deepseek_harness_runner.py
git commit -m "feat(deepseek-harness): 接入任务执行生命周期"
```

### Task 3: Preserve Sessions and Install the Grading Transcript

**Files:**
- Modify: `src/agents/deepseek_harness/runner.py`
- Modify: `tests/test_deepseek_harness_runner.py`

- [ ] **Step 1: Write failing artifact tests**

Use `tests/fixtures/deepseek_harness` as native sessions. Verify export writes raw files below `<output_dir>/dsh_sessions`, calls `write_conversion()`, leaves `chat.jsonl`, `usage.json` and `conversion_manifest.json` on the host, then copies `chat.jsonl` to `/root/.openclaw/agents/main/sessions/chat.jsonl` in the running container.

Test `collect_usage()` with populated and missing usage files. The fixture must produce:

```python
{
    "input_tokens": 18,
    "output_tokens": 7,
    "cache_read_tokens": 2,
    "cache_write_tokens": 4,
    "total_tokens": 31,
    "cost_usd": 0.0,
    "request_count": 3,
    "elapsed_time": 12.5,
}
```

Verify export still runs after DSH nonzero exit and timeout. Conversion failure must preserve raw sessions, record the failure, and return an execution error.

- [ ] **Step 2: Run tests and verify RED**

```bash
uv run python -m unittest tests/test_deepseek_harness_runner.py -v
```

Expected: artifact, transcript and usage assertions fail.

- [ ] **Step 3: Implement export, conversion and usage**

Copy sessions with:

```text
docker cp <task-id>:/root/.dsh/sessions/. <output_dir>/dsh_sessions
```

Call `write_conversion()` only when a `session.jsonl` exists. If DSH fails before creating one, preserve the primary DSH error and write zero usage. After conversion, create the transcript directory with `docker exec mkdir -p` and install host `chat.jsonl` with `docker cp`.

Implement `collect_usage()` with all standard numeric fields, defensive zero defaults, float `cost_usd`, and rounded elapsed time. `prepare_grading_transcript()` returns the installed OpenClaw-compatible path.

- [ ] **Step 4: Run focused compatibility tests**

```bash
uv run python -m unittest \
  tests/test_deepseek_harness_runner.py \
  tests/test_deepseek_harness_transcript.py -v
```

Expected: all tests pass and existing WCB grading/tool parsers still read generated `chat.jsonl`.

- [ ] **Step 5: Commit**

```bash
git add src/agents/deepseek_harness/runner.py tests/test_deepseek_harness_runner.py
git commit -m "feat(deepseek-harness): 保存评测轨迹与用量"
```

### Task 4: Register the Backend in `run_batch`

**Files:**
- Create: `tests/test_deepseek_harness_integration.py`
- Modify: `src/utils/cli_args.py`
- Modify: `eval/run_batch.py`

- [ ] **Step 1: Write failing CLI and policy tests**

Test:

```python
parser = build_run_batch_parser("openrouter/test", 1)
args = parser.parse_args([
    "--task", "task.md", "--agent-backend", "deepseek-harness",
])
self.assertEqual(args.agent_backend, "deepseek-harness")
self.assertIsNone(args.dsh_api)

responses = parser.parse_args([
    "--task", "task.md", "--agent-backend", "deepseek-harness",
    "--dsh-api", "openai-responses",
])
self.assertEqual(responses.dsh_api, "openai-responses")
```

Invalid APIs must fail parser validation. Add integration assertions that `run_batch.py` imports and constructs `DeepSeekHarnessAgent(api=args.dsh_api)`, and includes the class in both `grade_on_error` and workspace-change collection policies.

- [ ] **Step 2: Run tests and verify RED**

```bash
uv run python -m unittest tests/test_deepseek_harness_integration.py -v
```

Expected: parser rejects the backend and wiring assertions fail.

- [ ] **Step 3: Add CLI and backend construction**

Add `deepseek-harness` to backend choices and:

```python
parser.add_argument(
    "--dsh-api",
    choices=["openai-completions", "openai-responses"],
    default=None,
    help="DeepSeek Harness OpenAI wire API; falls back to DSH_API, then openai-completions",
)
```

Import the class in `eval/run_batch.py` and construct it in an explicit `elif`. Add it to the existing policy tuples so failed runs can still be graded and full workspace changes are collected. Do not alter defaults for other backends.

- [ ] **Step 4: Run framework regressions**

```bash
uv run python -m unittest \
  tests/test_deepseek_harness_integration.py \
  tests/test_run_batch_task_counts.py \
  tests/test_openclaw_backends.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/utils/cli_args.py eval/run_batch.py tests/test_deepseek_harness_integration.py
git commit -m "feat(eval): 注册 DeepSeek Harness 后端"
```

### Task 5: Register Tool Metrics and Report Identity

**Files:**
- Modify: `src/utils/tool_metrics.py`
- Modify: `tests/test_tool_metrics.py`
- Modify: `tools/report/data/entities.yaml`
- Modify: `tools/report/tests/test_analysis_pipeline.py`

- [ ] **Step 1: Write failing metric and entity tests**

Feed `completed`, `error`, `pending` and nonempty status-less results to `parse_tool_metrics(path, "deepseek-harness")`. Expect success, failure, unclear and success respectively. Load `entities.yaml` and expect `registry.harness_display("deepseek-harness") == "DeepSeek Harness"`.

- [ ] **Step 2: Run tests and verify RED**

```bash
uv run python -m unittest \
  tests/test_tool_metrics.py \
  tools/report/tests/test_analysis_pipeline.py -v
```

Expected: metrics are empty and entity lookup falls back to the raw ID.

- [ ] **Step 3: Implement the classifier and entity**

```python
def classify_deepseek_harness(tool_name: str, content: str, status: str = "") -> str:
    st = (status or "").lower()
    if st == "completed":
        return "success"
    if st == "error":
        return "failure"
    if st in {"running", "pending"}:
        return "unclear"
    return "success" if content else "unclear"


register_classifier(("deepseek-harness",), classify_deepseek_harness)
```

```yaml
  deepseek-harness:
    display_name: DeepSeek Harness
    family: DeepSeek Harness
    aliases: []
    capabilities: {}
```

- [ ] **Step 4: Run metric and report tests**

Run Step 2 again. Expected: all tests pass and existing Harness metrics remain unchanged.

- [ ] **Step 5: Commit**

```bash
git add src/utils/tool_metrics.py tests/test_tool_metrics.py \
  tools/report/data/entities.yaml tools/report/tests/test_analysis_pipeline.py
git commit -m "feat(report): 注册 DeepSeek Harness 指标与实体"
```

### Task 6: Promote the Docker Contract from PoC to Formal Backend

**Files:**
- Modify: `docker/deepseek-harness/README.md`
- Modify: `tests/test_deepseek_harness_docker.py`
- Modify: `docs/superpowers/specs/2026-08-14-deepseek-harness-integration-design.md`

- [ ] **Step 1: Write failing documentation-contract tests**

Assert README uses `wildclawbench-deepseek-harness-ubuntu:v0.0`, documents `DOCKER_IMAGE_DEEPSEEK_HARNESS`, and includes `run_batch.py --agent-backend deepseek-harness --dsh-api openai-completions`.

- [ ] **Step 2: Run tests and verify RED**

```bash
uv run python -m unittest tests/test_deepseek_harness_docker.py -v
```

Expected: README assertions fail because it still describes only the PoC entry point.

- [ ] **Step 3: Update docs and build the formal image tag**

Keep the Dockerfile and pinned package unchanged. Document formal build/run commands, image override, explicit Chat/Responses pairing, standalone PoC diagnostics, and Search/multimodal boundaries.

```bash
docker build -t wildclawbench-deepseek-harness-ubuntu:v0.0 docker/deepseek-harness
docker run --rm --entrypoint dsh \
  wildclawbench-deepseek-harness-ubuntu:v0.0 --version
```

Expected version: `0.1.0-rc.6`.

- [ ] **Step 4: Run contract and config smokes**

```bash
uv run python -m unittest tests/test_deepseek_harness_docker.py -v
docker run --rm \
  -e DSH_MODEL_ID=xopglm52 \
  -e OPENROUTER_API_KEY=dummy \
  -e DSH_API=openai-responses \
  wildclawbench-deepseek-harness-ubuntu:v0.0 --dump-config \
  >/tmp/wcb-dsh-config.txt
```

Expected: tests and dump-config pass; no real credential is used.

- [ ] **Step 5: Commit**

```bash
git add docker/deepseek-harness/README.md tests/test_deepseek_harness_docker.py \
  docs/superpowers/specs/2026-08-14-deepseek-harness-integration-design.md
git commit -m "docs(deepseek-harness): 发布正式评测镜像用法"
```

### Task 7: Run the Complete Offline Verification Suite

**Files:**
- Modify: `docs/superpowers/plans/2026-08-14-deepseek-harness-integration.md`

- [ ] **Step 1: Run focused and adjacent tests**

```bash
uv run python -m unittest \
  tests/test_deepseek_harness_transcript.py \
  tests/test_deepseek_harness_poc.py \
  tests/test_deepseek_harness_docker.py \
  tests/test_deepseek_harness_runner.py \
  tests/test_deepseek_harness_integration.py \
  tests/test_tool_metrics.py \
  tests/test_run_batch_task_counts.py \
  tests/test_openclaw_backends.py \
  tools/report/tests/test_analysis_pipeline.py -v
```

Expected: zero failures and errors.

- [ ] **Step 2: Run source, diff and secret checks**

```bash
uv run python -m compileall -q \
  src/agents/deepseek_harness \
  tests/test_deepseek_harness_*.py
git diff --check
```

Load the ignored root `.env`, compare configured model/judge secret values against the Git diff, and fail if a full value is present. Never print secret values.

- [ ] **Step 3: Verify a real detached container without network**

Start the formal image with `--entrypoint /bin/bash`, copy a fixture into `/tmp_workspace`, verify `/root/.dsh/skills` is writable, confirm the container stays alive, then remove only the explicitly named smoke container.

- [ ] **Step 4: Record executed checks**

Mark only commands actually run as complete. Record a pre-existing failure separately rather than changing unrelated code.

- [ ] **Step 5: Commit plan evidence if changed**

```bash
git add docs/superpowers/plans/2026-08-14-deepseek-harness-integration.md
git commit -m "test(deepseek-harness): 记录正式集成验证"
```

### Task 8: Run a Real `run_batch` Evaluation and Final Review

**Files:**
- Generated, ignored: `/Users/gzx/Project/GitHub/xgz/ai/evaluate/WildClawBench/eval_out_debug/smoke/deepseek-harness-integration/`
- Modify when evidence changes: `docker/deepseek-harness/README.md`
- Modify when evidence changes: `docs/superpowers/specs/2026-08-14-deepseek-harness-integration-design.md`

- [ ] **Step 1: Run the real Chat `/v2` task**

Load credentials from the ignored root `.env`; do not put their values in commands or tracked files:

```bash
set -a
. /Users/gzx/Project/GitHub/xgz/ai/evaluate/WildClawBench/WildClawBench/.env
set +a
export OPENROUTER_BASE_URL='https://maas-api.cn-huabei-1.xf-yun.com/v2'
export DOCKER_IMAGE_DEEPSEEK_HARNESS='wildclawbench-deepseek-harness-ubuntu:v0.0'
export OUTPUT_SUBDIR='/Users/gzx/Project/GitHub/xgz/ai/evaluate/WildClawBench/eval_out_debug/smoke/deepseek-harness-integration/xopglm52'

uv run eval/run_batch.py \
  --agent-backend deepseek-harness \
  --dsh-api openai-completions \
  --thinking high \
  --task tasks/03_Social_Interaction/03_Social_Interaction_task_2_chat_action_extraction.md \
  --model openrouter/xopglm52
```

- [ ] **Step 2: Validate evaluation artifacts**

Locate the one run directory and assert:

```text
execution_status.status == finished
execution_status.harness == deepseek-harness
execution_status.api == openai-completions
score.json contains numeric scores
usage.request_count > 0
conversion_manifest.message_count > 0
dsh_sessions contains session.jsonl
chat.jsonl contains assistant, tool_use and tool_result
task_output/workspace/results/results.md exists and is non-empty
anomalies.has_validity_failure == false
```

Run the scoped validity checker:

```bash
uv run python \
  tools/report/skills/validate-eval-results/scripts/validate_eval_results.py \
  --result-root "$OUTPUT_SUBDIR" \
  --models xopglm52 \
  --harnesses deepseek-harness \
  --fail-on fail \
  --output-dir "$OUTPUT_SUBDIR/validity"
```

Expected: the selected single-task smoke has no upstream validity failure.

- [ ] **Step 3: Review logs and secret safety**

Inspect agent/runner logs, execution status, transcript, conversion manifest, usage, score and anomalies. Compare `.env` secrets against generated text artifacts without printing them; fail on any full-value match.

- [ ] **Step 4: Request independent code review**

Review `f26029a..HEAD` against the design. Fix every Critical or Important finding, rerun affected tests, and document residual boundaries.

- [ ] **Step 5: Run final verification and commit evidence updates**

Repeat Task 7 tests, compileall, Docker version, `git diff --check`, worktree status and secret scan. Commit only evidence files if they changed:

```bash
git add docker/deepseek-harness/README.md \
  docs/superpowers/specs/2026-08-14-deepseek-harness-integration-design.md
git commit -m "test(deepseek-harness): 记录正式评测闭环"
```

Expected final state: Chinese Conventional Commits only, clean worktree, and no live Search/native multimodal claim without a separate successful test.
