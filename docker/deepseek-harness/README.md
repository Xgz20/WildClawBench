# DeepSeek Harness Docker PoC

This image uses `wildclawbench-codex-ubuntu:v0.0` as its final evaluation base,
adds a Node 24 runtime from `node:24-bookworm-slim`, installs the published
`@deepseek-ai/dsh@0.1.0-rc.6` package, and runs one
`dsh --profile headless` task. It is intentionally independent from the
production `eval/run_batch.py` backend registry.

The shared WCB base keeps the Python, Playwright/browser, media, and document
toolchain aligned with the other Harness images. Both bases run as root, so
this change is about task-environment parity rather than granting additional
Docker filesystem permissions. DSH still uses its explicit
`DSH_PERMISSION_MODE=danger-full-access` setting inside the container.

## Build

```bash
docker build \
  -t wildclawbench-deepseek-harness-poc:0.1.0-rc.6 \
  docker/deepseek-harness
```

The local Docker daemon must already contain
`wildclawbench-codex-ubuntu:v0.0`. `EVAL_BASE_IMAGE` and `NODE_RUNTIME_IMAGE`
are build arguments when compatible mirrored tags are required. The WCB base
currently contains Node 20, which is below DSH's supported
`^22.19.0 || >=24.0.0` range; the build therefore copies Node 24 without
discarding the rest of the WCB environment.

The default npm registry is `https://registry.npmmirror.com`. Override it with
`--build-arg NPM_REGISTRY=<registry>` when necessary. The build runs
`dsh --version`, so an unavailable package or invalid published artifact fails
the image build.

## Convert existing sessions

```bash
python tools/deepseek_harness_poc.py convert \
  --sessions /path/to/sessions \
  --output /path/to/output
```

The converter writes `chat.jsonl`, `usage.json`, and
`conversion_manifest.json`. It recursively includes root and child
`session.jsonl` files, while the native files remain unchanged.

## Run one task

Export credentials in the host environment. Do not put secret values in the
command line or a tracked configuration file.

```bash
export OPENROUTER_API_KEY='<redacted>'
export OPENROUTER_BASE_URL='https://openrouter.ai/api/v1'
# Optional: enables the DSH-native DeepSeek Search provider.
export DEEPSEEK_API_KEY='<redacted>'

python tools/deepseek_harness_poc.py run \
  --image wildclawbench-deepseek-harness-poc:0.1.0-rc.6 \
  --workspace /path/to/task-workspace \
  --model deepseek/deepseek-chat-v3.1 \
  --api openai-completions \
  --output /path/to/output \
  --prompt 'Complete the task and verify the result.'
```

`--api` accepts `openai-completions` and `openai-responses`; it defaults to
`openai-completions` for backward compatibility. Select the API and base URL as
one explicit pair. Do not infer the API from a `/v1` or `/v2` suffix because
those paths are provider-specific. For the tested MaaS route, Chat Completions
uses `--api openai-completions` with a `/v2` base URL, while Responses uses
`--api openai-responses` with a `/v1` base URL.

The Docker command inherits credential environment variable names. The
generated Cordis patch contains `apiKeyEnv` references, not credential values.
The PoC disables telemetry and auxiliary LLM title generation, stores raw JSONL
below `output/sessions`, and leaves DSH-native DeepSeek Search enabled.

Additional run artifacts are `dsh.stdout.log`, `dsh.stderr.log`, and
`run_manifest.json`. Known credential values are redacted before stdout or
stderr is persisted; the prompt is represented in the manifest only by its
SHA-256 digest.

## Verification boundary

Verified in this branch on 2026-08-14:

- The offline converter, WCB usage/tool parser compatibility, Docker static
  contract, and CLI cleanup/redaction tests pass.
- The image built successfully as
  `wildclawbench-deepseek-harness-poc:0.1.0-rc.6`; npm installed the pinned
  package and the build-stage `dsh --version` returned `0.1.0-rc.6`.
- The final image's root filesystem starts with the same 11 layers as
  `wildclawbench-codex-ubuntu:v0.0`; runtime smoke preserved root execution,
  Node 24.19.0, Python 3.11, Playwright/PyMuPDF/Pillow/openpyxl/pandas, and
  ffmpeg.
- A container `dsh --version` smoke returned `0.1.0-rc.6`. The image's
  `node-pty` native spawn smoke returned `NODE_PTY_OK exit=0`.
- `--dump-config` with a dummy key parsed the generated patch and showed the
  OpenRouter route, raw session persistence, disabled title LLM, and enabled
  DeepSeek Search. The dummy credential value was absent from the dump.
- Missing `DSH_MODEL_ID` and missing `OPENROUTER_API_KEY` both fail before a
  model request with exit code 2.
- For the AstronCode spelling `openrouter/xopglm52`, pass the bare DSH model ID
  `xopglm52`; AstronCode strips the Harness route prefix before writing its
  provider config. When `--reasoning high` is set, the entrypoint declares
  that level in the hand-declared model metadata before selecting it.
- A credentialed `xopglm52` Chat Completions smoke against the tested MaaS
  `/v2` endpoint exited 0. The model created and read back the requested file;
  raw session conversion emitted 7 messages and usage for 3 model requests.
  The same Chat configuration against `/v1` returned HTTP 401, confirming that
  the earlier authentication-looking error was caused by an API/endpoint
  mismatch for this provider.
- A second credentialed smoke used `openai-responses` against the same MaaS
  provider's `/v1` endpoint. It also exited 0, created/read the requested file,
  and emitted 7 converted messages with usage for 3 model requests. The raw
  session replay state records `api: openai-responses`.

The first build attempt could not fetch Docker Hub's anonymous token. For the
successful local build, the same Node 24 base image was pulled from a local
mirror and tagged as `node:24-bookworm-slim`; the Dockerfile itself still uses
the standard image reference. A credentialed `xopglm52` smoke loaded secrets
only from the ignored repository `.env`. The successful smoke verifies Chat
model calls, tool execution, task mutation, raw session persistence, and
transcript/usage conversion for both supported OpenAI wire APIs. Live DeepSeek
Search remains unverified.
