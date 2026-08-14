# DeepSeek Harness Docker PoC

This image installs the published `@deepseek-ai/dsh@0.1.0-rc.6` package and
runs one `dsh --profile headless` task. It is intentionally independent from
the production `eval/run_batch.py` backend registry.

## Build

```bash
docker build \
  -t wildclawbench-deepseek-harness-poc:0.1.0-rc.6 \
  docker/deepseek-harness
```

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
# Optional: enables the DSH-native DeepSeek Search provider.
export DEEPSEEK_API_KEY='<redacted>'

python tools/deepseek_harness_poc.py run \
  --image wildclawbench-deepseek-harness-poc:0.1.0-rc.6 \
  --workspace /path/to/task-workspace \
  --model deepseek/deepseek-chat-v3.1 \
  --output /path/to/output \
  --prompt 'Complete the task and verify the result.'
```

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
- A container `dsh --version` smoke returned `0.1.0-rc.6`. The image's
  `node-pty` native spawn smoke returned `NODE_PTY_OK exit=0`.
- `--dump-config` with a dummy key parsed the generated patch and showed the
  OpenRouter route, raw session persistence, disabled title LLM, and enabled
  DeepSeek Search. The dummy credential value was absent from the dump.
- Missing `DSH_MODEL_ID` and missing `OPENROUTER_API_KEY` both fail before a
  model request with exit code 2.

The first build attempt could not fetch Docker Hub's anonymous token. For the
successful local build, the same Node 24 base image was pulled from a local
mirror and tagged as `node:24-bookworm-slim`; the Dockerfile itself still uses
the standard image reference. No credentialed real-model task was executed,
so model quality, actual task mutation, and live DeepSeek Search results remain
unverified.
