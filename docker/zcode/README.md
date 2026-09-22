# ZCode evaluation image

`wildclawbench-zcode-ubuntu:v0.0` pins the ZCode CLI runtime `0.16.9` at source commit
`872ad960de7ec172591f7e1952f7849229f94521`. The final evaluation layer is
based on `wildclawbench-codex-ubuntu:v0.0`; a Node 24.14 builder produces the
self-contained Linux x64 SEA binary.

Build without exporting an archive:

```bash
bash docker/zcode/build.sh --skip-save
```

Build and export `Images/wildclawbench-zcode-ubuntu_v0.0.tar.gz`:

```bash
bash docker/zcode/build.sh
```

Run a WildClawBench task through OpenAI Responses:

```bash
OUTPUT_SUBDIR=/path/to/output \
DOCKER_IMAGE_ZCODE=wildclawbench-zcode-ubuntu:v0.0 \
OPENROUTER_BASE_URL=https://example.test/v1 \
OPENROUTER_API_KEY="$OPENROUTER_API_KEY" \
uv run eval/run_batch.py \
  --agent-backend zcode \
  --zcode-api openai-responses \
  --task tasks/03_Social_Interaction/03_Social_Interaction_task_2_chat_action_extraction.md \
  --model openrouter/example-model
```

Supported provider protocols are `openai-responses`,
`openai-chat-completions`, and `anthropic-messages`. `OPENROUTER_*` is the
WildClawBench generic external-model slot and does not require OpenRouter.

Each run preserves ZCode's native headless `stream-json` output as
`zcode_trace.jsonl`, plus converted `chat.jsonl`, `usage.json`, and
`conversion_manifest.json`. Provider configuration and its API key stay in the
task container's temporary ZCode data directory and are not exported.
