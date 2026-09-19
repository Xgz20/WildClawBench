# MiniMax Code evaluation image

`wildclawbench-minimax-code-ubuntu:v0.0` installs `@minimax-ai/code@0.4.12`
on the required Node 24 runtime while retaining the complete
`wildclawbench-codex-ubuntu:v0.0` evaluation toolchain.

Build without exporting an archive:

```bash
bash docker/minimax-code/build.sh --skip-save
```

Build and export `Images/wildclawbench-minimax-code-ubuntu_v0.0.tar.gz`:

```bash
bash docker/minimax-code/build.sh
```

Run a WildClawBench task:

```bash
OUTPUT_SUBDIR=/path/to/output \
DOCKER_IMAGE_MINIMAX_CODE=wildclawbench-minimax-code-ubuntu:v0.0 \
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1 \
OPENROUTER_API_KEY="$OPENROUTER_API_KEY" \
uv run eval/run_batch.py \
  --agent-backend minimax-code \
  --mcode-api openai-responses \
  --task tasks/03_Social_Interaction/03_Social_Interaction_task_2_chat_action_extraction.md \
  --model openrouter/example-model
```

Supported provider protocols are `openai-completions`, `openai-responses`, and
`anthropic-messages`. `OPENROUTER_*` remains the WildClawBench generic external
model slot and does not imply that the request must pass through OpenRouter.
When the shared MaaS output-limit switch is enabled, the runner resolves the
model limit and forwards it to `mcode provider add --output-limit`; it stays
unset by default for cross-Harness compatibility.

Each run preserves the native `stream-json` trace as
`minimax_code_trace.jsonl`, bounded native diagnostics under
`minimax_code_diagnostics/`, the last assistant message, and the converted
OpenClaw-compatible `chat.jsonl`. Provider configuration and its API key stay
inside the task container's temporary `MINIMAX_DATA_DIR` and are not exported.

MiniMax Code 0.4.12 custom providers use provider-default reasoning. A
WildClawBench `--thinking` value is recorded in `execution_status.json` but is
not forwarded as `--effort`, because named effort levels are not declared by
the custom-provider CLI contract.
