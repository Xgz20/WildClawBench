# DeepSeek Harness Docker 与轨迹转换 PoC 设计

## 决策摘要

本阶段验证 DeepSeek Harness 能否在独立 Docker 容器中执行一次 headless 任务，并把原生 session JSONL 转换为 WildClawBench 已有评分器、异常检测和工具指标能够读取的 OpenClaw 兼容 transcript，同时生成统一 usage 汇总。

镜像通过 npm 固定安装 `@deepseek-ai/dsh@0.1.0-rc.6`。PoC 不把 DeepSeek Harness 注册到 `eval/run_batch.py`，避免在真实 session 契约验证前影响正式跑批入口。

## 目标与非目标

目标：

- 构建可追溯的 `wildclawbench-deepseek-harness-poc` 镜像。
- 使用 `dsh --profile headless` 执行单个任务，并把原生 session 写到持久卷。
- 保留所有原生根/子 session JSONL。
- 生成 OpenClaw 兼容 `chat.jsonl` 和 WildClawBench 统一 `usage.json`。
- 用离线 fixture 验证消息、工具调用、工具结果、usage、异常输入和多 session 聚合。

非目标：

- 不增加 `--agent-backend deepseek-harness`。
- 不修改报告枚举、正式工具指标 classifier 或异常归因规则。
- 不把未运行的真实模型 smoke 声称为端到端通过。
- 不统一不同 Harness 的 Web Search 实现；DeepSeek Search 是 DSH 原生能力。

## Docker 设计

镜像基于 Node 24 Debian slim，使用以下构建参数：

- `DSH_VERSION`，默认 `0.1.0-rc.6`。
- `NPM_REGISTRY`，默认 `https://registry.npmmirror.com`。

镜像安装 `@deepseek-ai/dsh@${DSH_VERSION}`，并在构建阶段执行 `dsh --version`。由于发布包中的 `node-pty` 在 Node 24/Linux x64 会回退到 `node-gyp rebuild`，镜像同时安装 `python3`、`make` 和 `g++`。运行时使用 `/tmp_workspace` 作为工作目录，`/root/.dsh` 作为 `DSH_HOME`，通过 `/usr/local/bin/wcb-dsh` 生成固定 patch 后启动 headless profile。

运行时环境变量：

- `DSH_MODEL_ID`：OpenRouter 模型 ID，必填，例如 `deepseek/deepseek-chat-v3.1`。
- `OPENROUTER_API_KEY`：模型凭据，必填，只通过环境变量传递。
- `OPENROUTER_BASE_URL`：默认 `https://openrouter.ai/api/v1`。
- `DSH_REASONING`：可选 reasoning level。
- `DEEPSEEK_API_KEY`：可选，供 DSH 原生 DeepSeek Search 使用。

patch 固定以下行为：

- 模型 provider 为 `openrouter`，模型 ID 来自环境变量。
- `llm-pi-ai` 使用 OpenAI-compatible 协议和环境变量凭据引用。
- session persistence 使用 `$DSH_HOME/sessions`、`compression: none`、`packChunks: false`。
- 禁用自动 session title LLM，避免无关辅助请求污染 usage。
- 设置 `DSH_PERMISSION_MODE=danger-full-access` 和 `DSH_TELEMETRY_DISABLED=1`。

## 转换契约

转换器递归读取输入目录中的 `session.jsonl`。每个文件首行必须是 `type=session` header，后续合法 JSON object 按事件顺序处理；空行忽略，JSON 损坏、缺 header 或压缩文件明确报错。

事件映射：

| DSH 事件 | OpenClaw 兼容输出 |
|---|---|
| `user/message` | `type=message`、`role=user`，保留内容块 |
| `assistant/message` | `role=assistant`，保留 text/reasoning/tool-call；usage 转为 WCB 命名 |
| `tool/call` | 若 assistant message 未携带同一 call ID，补一条 `tool_use` |
| `tool/result` | `role=user` 的 `tool_result`，以 `error` 或 `message.isError` 判断状态 |
| 其他事件 | 原生文件保留，兼容 transcript 不输出 |

工具参数必须解析为 JSON object；标量或解析失败时保存到 `_value` 或 `_raw`，不能丢弃原始内容。工具结果的非字符串内容使用稳定 JSON 序列化。

## Usage 口径

只聚合 `assistant/message.data.usage`，避免同时计算 `assistant/chunk` usage 造成重复。所有 session 的字段相加：

- `inputTokens` -> `input_tokens`
- `outputTokens` -> `output_tokens`
- `cacheReadTokens` -> `cache_read_tokens`
- `cacheWriteTokens` -> `cache_write_tokens`
- `total_tokens` 为上述四项之和
- 每个带 usage 的 assistant message 计为一次 `request_count`
- DSH 原生事件不提供 USD 成本时，`cost_usd` 为 `0.0`，PoC 不编造价格

兼容 transcript 中对应 assistant message 同时写入 OpenClaw usage 字段，供已有 `extract_usage_from_jsonl()` 复核。

## PoC 命令入口

`tools/deepseek_harness_poc.py` 提供两个子命令：

- `convert --sessions <dir> --output <dir>`：离线生成 `chat.jsonl`、`usage.json` 和 `conversion_manifest.json`。
- `run --image <tag> --workspace <dir> --model <id> --output <dir> --prompt <text>`：启动临时容器、挂载工作区和 session 输出、等待退出，然后调用同一转换器。

运行命令不把密钥写入命令日志、manifest 或 patch；Docker 通过 `--env OPENROUTER_API_KEY` 继承宿主同名环境变量。

## 失败边界

- npm 包或基础镜像不可下载时，Docker 构建失败，不回退到浮动版本。
- 未提供模型 ID 或 API key 时，入口在模型调用前失败。
- DSH 退出非零时仍尝试转换已经落盘的 session，并原样返回非零退出码。
- timeout 由 PoC CLI 的 `--timeout` 控制；超时后停止并删除容器，再转换已落盘内容。
- 转换失败不删除原生 session。

## 验收条件

- 离线测试覆盖文本、工具成功/失败、usage、去重、多 session、坏 JSONL。
- 转换结果能被 `src.utils.grading.extract_usage_from_jsonl` 和 `src.utils.tool_metrics._load_tool_pairs` 读取。
- Docker 镜像构建后 `dsh --version` 输出固定版本。
- 无密钥配置检查不会发起模型请求。
- 真实模型 smoke 只有在外部提供凭据且实际执行成功时才标记通过。

## 已知基线

实现前 `tests/test_tool_metrics.py` 的 16 项测试通过。`tests/test_anomalies.py` 有 1 个既有断言失败，并因当前 Python 环境缺少 `python-dotenv` 出现 4 个导入错误；这些结果记录为本分支修改前基线。
