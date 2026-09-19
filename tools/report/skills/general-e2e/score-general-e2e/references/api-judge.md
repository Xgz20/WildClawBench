# General E2E API Judge 评分协议

## 适用边界

`api-judge-v1` 是显式选择的可选语义后端，支持 `anthropic-messages`、`openai-chat-completions` 和 `openai-responses`。它不依赖 Docker，不调用旧 WildClawBench grading，也不会在失败时切换 provider、模型、协议或 Codex Agent。

API 配置是评分 attempt 的冻结输入。配置文件必须是普通 JSON 文件：

```json
{
  "schema_version": "wildclawbench.general-e2e-api-judge-runtime/v1",
  "provider": "anthropic-messages",
  "base_url": "https://api.example.com",
  "credential_env": "ANTHROPIC_API_KEY",
  "max_output_tokens": 1024,
  "timeout_seconds": 180,
  "max_attempts": 1,
  "max_input_chars": 120000,
  "max_evidence_item_chars": 20000,
  "temperature": 0,
  "reasoning_parameter": "none"
}
```

`base_url` 不能包含 userinfo、query 或 fragment；非 loopback 地址必须使用 HTTPS。Anthropic Messages 在其后追加 `/v1/messages`，OpenAI Chat Completions 追加 `/chat/completions`，OpenAI Responses 追加 `/responses`。`credential_env` 只保存环境变量名，密钥值不能进入配置、attempt、日志或报告。

## 单题流程

准备 attempt 时同时传入冻结 API 配置：

```bash
python <skill-dir>/scripts/score_general_e2e.py prepare \
  --unit-root /absolute/execution-unit \
  --execution-record /absolute/execution-record.json \
  --scoring-package /absolute/unit-scoring.zip \
  --task-id TASK_ID \
  --scoring-attempt-id SCORE_ATTEMPT_ID \
  --output-root /absolute/private-scores \
  --judge-protocol api-judge-v1 \
  --judge-model MODEL_ID \
  --judge-reasoning-effort high \
  --judge-attempt-id JUDGE_ATTEMPT_ID \
  --api-runtime-config /private/api-runtime.json
```

完成全部阶段：

```bash
python <skill-dir>/scripts/score_general_e2e.py run-api-score \
  --attempt-root /absolute/private-attempt \
  --runtime-python /absolute/general-e2e-runtime/bin/python
```

纯 `llm_judge` 任务可省略 `--runtime-python`；`hybrid` 任务首次运行必须提供冻结规则运行时。也可先调用 `prepare-semantics`，再用 `run-api-judge` 只完成语义阶段。

## 输入与输出契约

`semantic/api-input.json` 把 rubric、响应契约和冻结证据打包为 system/user prompt。候选文件和轨迹始终标记为证据而非指令；每项记录原始字符数、实际包含字符数、截断或省略状态。总字符和单项字符都受冻结预算限制，省略内容不能作为已判定 criterion 的引用。

每个 criterion 必须按原顺序返回：`key`、`judged|unresolved`、原分值锚点或 `null`、中文理由、证据 ID，以及支持证据和反例检查声明。理由必须说明为何当前证据对应所选锚点；满分、零分、部分分和 `unresolved` 都不能省略。未知证据、未包含内容、改写 key、越界分数、非中文理由、缺失声明或多余字段都会失败关闭。`unresolved` 保持评测异常，不按零分处理。

## 重试、审计与恢复

只在冻结的 `max_attempts` 范围内重试。HTTP 408/409/425/429/500/502/503/504、传输错误、响应 JSON 解析失败、结构化契约失败和 `SEMANTIC_REASON_LANGUAGE_INVALID` 可重试；其他 HTTP 状态不重试。每次尝试写入独立的请求、provider 响应和解析产物，并在 `api-audit.json` 中记录 requested/returned model、endpoint 身份、timeout、输出上限、reasoning 参数方式、HTTP 状态、usage、错误和所选尝试。

已存在语义终态时重复命令只复用终态，不再次调用 API。如果进程在请求写入后、响应落盘前中断，恢复会以 `API_JUDGE_ATTEMPT_OUTCOME_UNKNOWN` 失败关闭，避免无法证明安全时重复调用。API 最终失败仍生成语义失败审计，随后合成为 `valid=false / total_score=null` 的标准 `score.json`；不得补零或创建 Codex 评分任务兜底。
