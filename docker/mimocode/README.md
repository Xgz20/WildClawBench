# MiMoCode 评测镜像

`wildclawbench-mimocode-ubuntu:v0.0` 基于 `wildclawbench-codex-ubuntu:v0.0`，
通过 npm 固定安装 `@mimo-ai/cli@0.1.14`。无需构建 MiMoCode 源码。

在仓库根目录执行：

```bash
bash docker/mimocode/build.sh --skip-save
docker run --rm --entrypoint mimo wildclawbench-mimocode-ubuntu:v0.0 --version
```

省略 `--skip-save` 时导出 `Images/wildclawbench-mimocode-ubuntu_v0.0.tar.gz`。
脚本每次执行 `docker build`，会复用构建缓存并更新同名 tag。可用
`NPM_REGISTRY=https://registry.npmmirror.com` 指定 npm 源。

## 评测入口

先在当前 shell 设置 `OPENROUTER_API_KEY`、`OPENROUTER_BASE_URL`，以及独立的
`ANTHROPIC_API_KEY`、`ANTHROPIC_BASE_URL`、`JUDGE_MODEL`。前两项始终用于被评测模型，
即便选择 Anthropic 协议也不自动借用裁判凭据。

```bash
DOCKER_IMAGE_MIMOCODE=wildclawbench-mimocode-ubuntu:v0.0 \
uv run eval/run_batch.py --agent-backend mimocode \
  --mimocode-api openai-chat-completions \
  --task tasks/03_Social_Interaction/03_Social_Interaction_task_2_chat_action_extraction.md \
  --model openrouter/xopglm52
```

`--mimocode-api`（别名 `--mimo-api`）优先于 `MIMOCODE_API`，缺省为 `openai-responses`。
不会根据失败自动切换协议。

| 参数 | Provider SDK | endpoint 拼接 |
| --- | --- | --- |
| `openai-responses` | `@ai-sdk/openai` | base URL + `/responses` |
| `openai-chat-completions` | `@ai-sdk/openai-compatible` | base URL + `/chat/completions` |
| `anthropic-messages` | `@ai-sdk/anthropic` | base URL + `/messages` |

Base URL 要包含服务所需的版本前缀；例如 Anthropic 接口若位于 `/v1/messages`，
传入的 base URL 必须以 `/v1` 结束。此适配器不改写 endpoint。
`--thinking` 请求记录在状态文件中，但当前不将任意模型的 `high` 强制映射为
MiMoCode provider variant；`thinking_forwarded=false`、`provider_default` 是明确边界。
CLI 的 `--thinking` 仅用于导出推理文本，不代表强制开启高推理档位。

## 轨迹与指标

- `mimocode_trace.jsonl`：未经追加或改写的 `mimo run --format json --thinking` 主会话输出。
- `mimocode.db`：独立容器中的 SQLite online backup，包含已持久化会话、消息、工具部分及子会话；不导出认证和配置文件。
- `chat.jsonl`：主会话评分兼容轨迹，保留文本、推理和工具结果。
- `conversion_manifest.json`：转换数量、session ID、终态判断依据和范围。
- `execution_status.json`：退出码、超时、错误阶段；CLI 返回 0 但含 error 或未正常 stop，不视为成功。
- `usage.json`：数据库中主会话及其后代会话已完成模型步骤的统计；缓存不重复计入 input，reasoning 计入 output 并另列子集，provider total 使用原生 `tokens.total`。

`usage_complete` 仅指声明的 `usage_scope=session_tree_completed_steps`；自动 checkpoint-writer
等后代会话也计入，但未持久化的失败尝试及会话树外辅助调用仍不等于完整账单。数据库不可用时
仅能回退到 `main_session_completed_steps`，且该次采集明确报错。超时保留已完成步骤的用量，
并标记不完整。费用按报告端模型价格表计算，`cost_status=unavailable` 不等于免费。
以上轨迹不是 HTTP wire request/response 录制。

## 验证边界

三种协议均有真实 CLI + 本地模拟服务的工具闭环测试：

```bash
WCB_MIMOCODE_DOCKER_TESTS=1 uv run python -m unittest tests.test_mimocode_wire -v
```

GLM5.2 + MaaS 的 Chat 冒烟已跑通。Responses 冒烟出现反复 `tool-calls` 而无工具完成事件并超时，
尚未定位到网关、SDK 或 Harness 的具体责任层；不能将该组合标为已验收。Anthropic Messages
目前为本地协议测试通过，尚未做真实模型完整评测。
