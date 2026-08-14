# DeepSeek Harness Evaluation Image

This image is the runtime for the WildClawBench `deepseek-harness` backend. It
uses `wildclawbench-codex-ubuntu:v0.0` as the final evaluation base, adds Node
24 from `node:24-bookworm-slim`, and installs the published
`@deepseek-ai/dsh@0.1.0-rc.6` package.

The shared WCB base keeps the Python, browser, media, and document toolchain
aligned with the other Harness images. Both bases run as root, so this is task
environment parity rather than an additional Docker permission grant. DSH
still uses `DSH_PERMISSION_MODE=danger-full-access` inside the task container.

## Build

```bash
docker build \
  -t wildclawbench-deepseek-harness-ubuntu:v0.0 \
  docker/deepseek-harness

docker run --rm --entrypoint dsh \
  wildclawbench-deepseek-harness-ubuntu:v0.0 --version
```

The expected version is `0.1.0-rc.6`. The local Docker daemon must already
contain `wildclawbench-codex-ubuntu:v0.0`. `EVAL_BASE_IMAGE` and
`NODE_RUNTIME_IMAGE` are build arguments when compatible mirrored tags are
required. The default npm registry is `https://registry.npmmirror.com`; use
`--build-arg NPM_REGISTRY=<registry>` when necessary.

## Run Through WildClawBench

Export credentials in the host environment. Do not put secret values in the
command line or a tracked configuration file. `DEEPSEEK_API_KEY` is optional
and is used only by DSH-native DeepSeek Search.

```bash
export OPENROUTER_API_KEY='<redacted>'
export OPENROUTER_BASE_URL='https://provider.example/v2'
export DOCKER_IMAGE_DEEPSEEK_HARNESS='wildclawbench-deepseek-harness-ubuntu:v0.0'

uv run eval/run_batch.py \
  --agent-backend deepseek-harness \
  --dsh-api openai-completions \
  --thinking high \
  --task tasks/03_Social_Interaction/03_Social_Interaction_task_2_chat_action_extraction.md \
  --model openrouter/xopglm52
```

`--dsh-api` accepts `openai-completions` and `openai-responses`. If omitted,
the runner reads `DSH_API` and then defaults to `openai-completions`.
`OPENROUTER_BASE_URL` is passed through unchanged: the runner neither infers a
protocol from the URL suffix nor rewrites the endpoint.

For the MaaS route used by the PoC verification, the tested pairs are:

- Chat Completions: `openai-completions` with the provider's `/v2` endpoint.
- OpenAI Responses: `openai-responses` with the provider's `/v1` endpoint.

Those suffixes are provider-specific and are not a general protocol rule.

The formal backend starts a detached container, read-only mounts the task
input, copies it to `/tmp_workspace`, installs task skills below
`/root/.dsh/skills`, and leaves the container alive for grading. Because DSH
accepts only lowercase kebab-case skill names, the runner stages each complete
bundle, normalizes its frontmatter name (for example `03_task2` to
`03-task2`), updates staged `{baseDir}` references, and rejects normalized-name
collisions. The original task skill is never modified. Ordered `/<name>`
gestures are prepended to the task prompt so DSH performs native direct skill
invocation; the runner does not concatenate skill bodies into the prompt.

The backend exports raw sessions to `dsh_sessions`, converts them into
`chat.jsonl`, `usage.json`, and `conversion_manifest.json`, then installs the
normalized transcript at the OpenClaw-compatible path expected by WCB graders.
`run_batch.py` removes the container after grading and output collection.

## Standalone Diagnostics

The original PoC entry point remains useful for conversion and image-level
diagnostics independent of `run_batch.py`:

```bash
uv run python tools/deepseek_harness_poc.py convert \
  --sessions /path/to/sessions \
  --output /path/to/output

uv run python tools/deepseek_harness_poc.py run \
  --image wildclawbench-deepseek-harness-ubuntu:v0.0 \
  --workspace /path/to/task-workspace \
  --model xopglm52 \
  --api openai-responses \
  --output /path/to/output \
  --prompt 'Complete the task and verify the result.'
```

The converter recursively includes root and child `session.jsonl` files while
leaving native files unchanged. The diagnostic runner writes redacted stdout,
stderr, and a manifest that stores only a prompt digest.

## Verification Boundary

Verified by the preceding PoC work on 2026-08-14:

- The image built from the WCB Codex base and reported DSH `0.1.0-rc.6`.
- The final image preserved root execution, Node 24.19.0, Python 3.11, browser,
  media, and document dependencies from the shared evaluation base.
- Chat with the tested MaaS `/v2` endpoint and Responses with `/v1` both exited
  successfully, executed file tools, and converted 7 messages with usage for 3
  model requests.
- Missing `DSH_MODEL_ID` or `OPENROUTER_API_KEY` failed before a model request.

The formal backend has offline unit coverage for container construction,
workspace/skills/warmup, skill-name normalization and native gestures, timeout
handling, transcript conversion, usage, grading policy, metrics, and report
identity. An initial real `run_batch.py` run exposed the invalid underscore
skill name and completed with `results.md not found`.

After the skill discovery repair, a fresh single-task Chat `/v2` evaluation on
2026-08-14 completed through the formal `run_batch.py` path with exit code 0:

- `execution_status.json` recorded `finished`, DSH `0.1.0-rc.6`,
  `openai-completions`, model `xopglm52`, and Harness exit code 0.
- The real grader produced `overall_score = 0.6218` with no error, and
  `task_output/workspace/results/results.md` contained 11,209 bytes.
- Usage recorded 11 requests and 134,664 total tokens. Conversion produced 25
  messages; `chat.jsonl` contained 11 assistant messages, 10 tool calls, and 10
  tool results.
- The native session contained one skill catalog and one direct skill
  invocation, with no `skill` tool call. This confirms that the prefixed
  `/<name>` gesture loaded the task skill directly.
- `anomalies.json` reported `validity_verdict = PASS` and no validity failure.
  The separate scoped validity checker reported `REVIEW` with zero errors and
  one `SUMMARY_MISSING` warning because a single-task run has no
  `summary_all_*.json`; it did not report a task validity failure.

This evidence verifies one text/tool task, not the full benchmark. Live
DeepSeek Search, native multimodal tasks, full-benchmark behavior, and inferred
USD cost remain outside this verification boundary.
