# DeepSeek Harness Evaluation Image

This image is the runtime for the WildClawBench `deepseek-harness` backend. It
uses `wildclawbench-codex-ubuntu:v0.0` as the final evaluation base, adds Node
24 from `node:24-bookworm-slim`, and installs the published
`@deepseek-ai/dsh@0.1.2-rc.1` package. Versioned build contexts are immutable:
`v1` preserves DSH `0.1.0-rc.6`, `v2` preserves DSH `0.1.1-rc.2`, and `v3`
contains DSH `0.1.2-rc.1`. `versions.json` maps image tags to those contexts
and selects v0.2 by default.

The shared WCB base keeps the Python, browser, media, and document toolchain
aligned with the other Harness images. Both bases run as root, so this is task
environment parity rather than an additional Docker permission grant. DSH
still uses `DSH_PERMISSION_MODE=danger-full-access` inside the task container.

## Build

```bash
bash docker/deepseek-harness/build.sh --version v0.2 --skip-save

docker run --rm --entrypoint dsh \
  wildclawbench-deepseek-harness-ubuntu:v0.2 --version
```

The expected version is `0.1.2-rc.1`. The local Docker daemon must already
contain `wildclawbench-codex-ubuntu:v0.0`. `EVAL_BASE_IMAGE` and
`NODE_RUNTIME_IMAGE` are build arguments when compatible mirrored tags are
required, but they must match the selected manifest entry. Set
`NPM_REGISTRY=<registry>` when a compatible npm mirror is required. Omit
`--version` to build the default v0.2 image, or use `--version v0.1` or
`--version v0.0` to rebuild a preserved historical image. Omit `--skip-save`
to export the selected image below `Images/`.

## Run Through WildClawBench

Export credentials in the host environment. Do not put secret values in the
command line or a tracked configuration file. `DEEPSEEK_API_KEY` is optional
and is used only by DSH-native DeepSeek Search. The runner also passes through
`DEEPSEEK_SEARCH_BASE_URL` and `DEEPSEEK_SEARCH_MODEL_ID` when set. The base
URL must expose an Anthropic-compatible Messages endpoint; DSH appends
`/messages`. The Search model defaults to `deepseek-v4-flash` when the model ID
is omitted. Native Search is enabled by default for backward compatibility.
Set `DEEPSEEK_SEARCH_ENABLED=false` to remove both the DeepSeek Search provider
and the model-facing `web_search` tool. In that mode the Search key, base URL,
and model ID are unnecessary; task-provided alternatives such as
`agent-browser` remain available.

```bash
export OPENROUTER_API_KEY='<redacted>'
export OPENROUTER_BASE_URL='https://provider.example/v2'
export DOCKER_IMAGE_DEEPSEEK_HARNESS='wildclawbench-deepseek-harness-ubuntu:v0.2'
export DEEPSEEK_SEARCH_ENABLED=false

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

When WCB resolves a MaaS output limit, it passes the protocol-neutral
`maxTokens` model setting to DSH. The v0.2 entry point forces
`compat.maxTokensField=max_tokens` only for `openai-completions`; Responses
keeps no Completions-only compat switch and lets pi-ai serialize the same value
as `max_output_tokens`. This prevents a Responses profile from failing during
plugin loading before its first model request.

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

## Cost Observation

DSH session events expose uncached input, output, cache-read, and cache-write
token counts, but they do not expose a trustworthy provider cost. The Harness
therefore only writes raw usage and an explicit cost status. Cost is calculated
when generating the report, using the evaluated model, `--pricing-date`, and
the versioned `tools/report/data/entities.yaml` pricing registry. This keeps
different models and Harnesses on one pricing path.

The report command must provide the pricing snapshot date, for example:

```bash
uv run python tools/report/scripts/generate_eval_report.py \
  --result-root <round-result-root> \
  --entities tools/report/data/entities.yaml \
  --pricing-date 2026-08-15
```

`usage.json` and `conversion_manifest.json` record token usage plus
`cost_status`, `cost_source`, `cost_scope`, and a reason when cost is
unavailable. The status values are:

- `estimated`: the report applied a valid model pricing profile to the recorded
  token usage.
- `unavailable`: DSH did not provide a provider cost, the model has no pricing
  profile, or session usage could not be exported/converted; `cost_usd` remains
  `0.0` for compatibility and must not be interpreted as free usage. The
  report will replace this status with a model-registry estimate when possible.
- `not_applicable`: no model tokens were recorded.

DSH reports `inputTokens` separately from `cacheReadTokens` and
`cacheWriteTokens`, so the estimator does not subtract cache tokens from input.
`cost_scope` is `model_tokens_only`: external Search/tool-provider charges are
not inferred from DSH session events and remain outside this estimate. If an
internal gateway model has no public price, add a dated model pricing profile
to the report registry rather than setting a Harness-global price.

## Standalone Diagnostics

The original PoC entry point remains useful for conversion and image-level
diagnostics independent of `run_batch.py`:

```bash
uv run python tools/deepseek_harness_poc.py convert \
  --sessions /path/to/sessions \
  --output /path/to/output

uv run python tools/deepseek_harness_poc.py run \
  --image wildclawbench-deepseek-harness-ubuntu:v0.2 \
  --workspace /path/to/task-workspace \
  --model xopglm52 \
  --api openai-responses \
  --output /path/to/output \
  --prompt 'Complete the task and verify the result.'
```

The converter recursively includes root and child `session.jsonl` files while
leaving native files unchanged. The diagnostic runner writes redacted stdout,
stderr, and a manifest that stores only a prompt digest.

## v0.2 Upgrade Verification

Verified on 2026-09-04 against the official `dsh-v0.1.2-rc.1` release:

- The Linux amd64 image built successfully and reported DSH `0.1.2-rc.1` with
  Node `v24.19.0`.
- A request-capture mock observed `max_tokens=16384` on
  `/v1/chat/completions` and `max_output_tokens=16384` on `/v1/responses`.
- A complete Responses SSE mock returned `responses-smoke-complete`, and DSH
  exited successfully instead of failing during plugin loading.
- A two-request Chat Completions mock executed the DSH `bash` tool, returned
  its `shell-ok` result to the model, and exited successfully.
- The existing converter accepted the new native session and generated five
  messages with one paired tool use/result and usage for two model requests.
- A real Spark-X2.5 `openai-responses` task then completed on v0.2 with exit
  code 0, seven model requests, seven paired tool use/results, a generated
  deliverable, five successful Claude Opus 5 Judge items, score `0.9496`, and
  anomaly verdict `PASS`.

This validates image construction, profile composition, protocol-specific
output-limit serialization, local and real-provider tool round trips, native
session persistence, conversion, grading, and anomaly scanning. The real smoke
ran before a dedicated model-catalog credential was configured, so it did not
exercise `max_output_tokens=256000`; that field mapping is covered by the local
request-capture mocks. It does not replace a full benchmark run. The detailed
evidence boundary is recorded in `DeepSeekHarness镜像更新日志.md`.

## Historical v0.1 Verification

Verified on 2026-08-27 against the official `dsh-v0.1.1-rc.2` tag at commit
`b150a551b8d465e31e418e1b2eaf5e79bbb7d28e`:

- The image built successfully and reported DSH `0.1.1-rc.2` with Node
  `v24.19.0`.
- The launcher and headless help surfaces completed successfully, and the
  existing WCB patch composed the custom model, JSONL persistence, optional
  DeepSeek Search, and web-tool rows without errors.
- A container-level Chat Completions smoke against a local mock endpoint
  reached `/v1/chat/completions`, returned `mock-smoke-ok`, and persisted a
  21-line `session.jsonl` file.
- The existing transcript converter accepted that native session and generated
  `chat.jsonl`, `usage.json`, and `conversion_manifest.json`.

This verifies image construction, profile composition, one model request, raw
session persistence, and conversion without exposing real credentials. It does
not replace a real provider smoke or full benchmark run.

## Historical v0.0 Verification

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
DeepSeek Search, native multimodal tasks, full-benchmark behavior, and report
cost recalculation against a real priced model remain outside this verification
boundary.
