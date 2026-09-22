---
name: collect-general-e2e
description: 收集 General E2E 执行状态、终态 Workspace、原始轨迹和资源数据并形成正式执行回执；不用于导入评分回传包或决定分数。
---

# 采集 General E2E 证据

将一次执行 attempt 收口为冻结候选和可审计证据，阶段名固定为 `collect-evidence`，不与 `import-return` 混用。

## 能力门禁

先运行：

```bash
python -m eval_general_e2e skills --name collect-general-e2e --json
```

当前 `0.7.3/operational` 支持 AstronStudio 与 WorkBuddy macOS 采集；WorkBuddy 支持原生 session JSONL 的模型响应数、Token、缓存读取及运行时请求耗时，finalizer 按正式 `collection.coverage` 和字段状态接受已验证的 observed/partial/unavailable 指标，不再把历史 unavailable 当作固定门禁。不得从最终文件反推或补造工具记录、Token、请求次数及原生会话身份。

新增通用 [CB-B 收口接口](references/general-finalization.md) 接受 CB-A 状态与 trace-index v2，保留多个原始文件和 nullable 原生 ID。必须提供真实平台进程清理 hook；WorkBuddy 已有运行时采集和真实 macOS cleanup/finalizer canary，入口见 [WorkBuddy 收口入口](drivers/workbuddy/finalize.mjs)。QwenWorkCN 1.0.6 / macOS x86_64 已完成单题原生采集、真实 cleanup/finalizer、评分、回传和报告闭环；该证据不外推并发、Apple Silicon、Windows 或全量评测。

WorkBuddy macOS 的离线门禁还要求 `state.extensions.workbuddy.identity_mapping` 明确列出
conversation/session/cwd 与 terminal 状态的原生来源。`session.verified=true`、`phase=COMPLETED`
以及 `session.cwd == candidate_workspace` 只能在这些来源字段同时存在时把
`native_terminal`/`native_cwd` 标为 `verified`；从 `state.session`、phase 或候选 Workspace
反推来源会失败关闭并保持未验证。真机 WorkBuddy collect/cleanup 已完成 canary；完整数据集评分、报告与发行使用仍需分别验收。

真实新时段前可在脱仓的 General Skill 根目录运行 WorkBuddy 只读预检；它不启动客户端、不申请
slot、不读取历史 canary，只确认 `task-process-cleanup` 共享组件、WorkBuddy source gate 与 CB-B
输入入口仍在包内：

```bash
node execute-general-e2e/drivers/workbuddy/preflight.mjs --skill-root /absolute/general-e2e
```

输出 `status=PASS` 仅表示离线装配完整；仍需真机字段 `conversationId`、`requestId`、原生 `cwd`、
终态来源、原始 trace 文件、resource metrics 和 cleanup 前后进程快照，才能进入正式 collect。

## 正式收口流程

WorkBuddy collector 默认在 `~/.workbuddy/projects` 查找唯一 `<sessionId>.jsonl`，可用 `--native-projects-root` 指定安装数据根。校验 session/cwd、运行时 trace ID、原始 Prompt（或客户端 user_query 包装）、工具调用集合和回复一致后，复用公共解析器按 `providerData.messageId` 去重。一个响应中的多个工具只算一次模型响应，usage 的 raw/归一化副本不重复相加。`request_count` 是已落盘模型响应数，HTTP 失败重试另为 unavailable；缓存读取是输入 Token 的子集。JSONL 缺失时模型响应数为 null，不能用顶层会话请求数代替；错会话、Prompt 或 usage 冲突失败关闭。

对已经冻结且评分完成的 unit，使用[WorkBuddy 指标补采](drivers/workbuddy/README.md)新增独立补充证据。它不覆盖 execution record、候选、评分或旧回执；将新增 evidence 随 `package-return` 交付，使用 report `>=0.3.0` 复算并生成新报告。

WorkBuddy 耗时来自已绑定的 runtime snapshot，不依赖 JSONL 或数据库更新时间：`agent_duration_seconds` 为 `request.startedAt`（缺失则 `timestamp`）至 `completedAt`（缺失则 `finishTimestamp`）；`duration_seconds` 为 `prompt.sent_at` 至同一原生完成点。前者包含工具与客户端处理，后者还包含发送/排队等待，均不是纯模型推理耗时。内部 `finishTimestamp` 略早于 `completedAt` 属正常；时间戳类型错误、倒序或结束字段顺序冲突失败关闭，缺失字段为 null，真实零耗时保留 0。题目 `timeout_seconds` 不参与耗时采集、执行限制或评分。

已有冻结批次运行 `drivers/workbuddy/supplement-timing.mjs --unit-root UNIT --execution-record FROZEN_RECORD`；仅使用归档证据，在 `evidence/timing-supplements/<task-id>/` 新增不可覆盖的补采，保留旧 Token 补采并绑定其 SHA（如有）。之后重新 package/import/select，使用 report `>=0.3.1` 生成新目录报告，不重跑 Harness 或评分。

先用下述两个子能力生成并校验 trace 与 resource metrics，再运行正式收口器：

```bash
node scripts/finalize_astronstudio_execution.mjs \
  --unit-root /absolute/unit-root \
  --state-file /absolute/unit-root/.general-e2e/execution/<task-id>/automation-state.json \
  --trace-index /absolute/unit-root/.general-e2e/execution/<task-id>/trace/trace-index.json \
  --resource-metrics /absolute/unit-root/.general-e2e/execution/<task-id>/trace/resource-metrics.json
```

收口器在发布候选前校验 package manifest、dataset、task/attempt、Prompt digest、一次发送、原生会话和终态；随后只终止与候选 Workspace 绝对路径或 cwd 精确绑定的 macOS 任务进程，等待零残留安静窗口，再确认 Workspace 静默并复制完整目录树。默认不排除 `.git`、`node_modules` 或 `__pycache__`；确需忽略或禁止目录时，必须通过 `--candidate-policy` 提供带理由的 basename 策略。

正式产物位于 `evidence/tasks/<task-id>/<attempt-id>/`，包括冻结候选、候选描述、执行状态快照、轨迹、资源指标、进程收口、证据清单和正式 `execution-record.json`。当 unit manifest 中所有任务都各有唯一 attempt 时，生成 `receipts/collect-evidence-receipt.json`。当前版本不替多 attempt 选择优胜 attempt；同一任务已有另一正式 attempt 时失败关闭。

正式 evidence 和 receipt 都不可覆盖。完成后必须运行不可变校验：

```bash
node scripts/finalize_astronstudio_execution.mjs \
  --verify-only \
  --unit-root /absolute/unit-root \
  --task-id <task-id>
```

校验同时重算冻结候选与原始 Workspace，验证 evidence manifest、receipt 哈希及候选/执行回执身份。任何漂移都必须阻断评分。完整参数、目录策略和失败边界见 [AstronStudio 正式收口](references/astronstudio-finalization.md)。

## AstronStudio 轨迹子能力

归档前必须确认 `automation-state.json` 已终态、Prompt 只发送一次，且 `thread_id / turn_id / session_id / cwd` 已验证。归档器仅读 SQLite/WAL 快照，不读“最近任务”：

```bash
node scripts/archive_astronstudio_trace.mjs \
  --state-file /absolute/unit/.general-e2e/execution/<task-id>/automation-state.json
```

只读查询不改写轨迹，范围、call ID、路径和文本过滤按 AND 组合：

```bash
node scripts/query_trace.mjs \
  --trace-index /absolute/trace/trace-index.json \
  --call-id <call-id> --page 1 --page-size 50
```

完整参数、产物和失败门禁见 [AstronStudio 轨迹归档与检索](references/astronstudio-trace.md)。

## AstronStudio 资源指标子能力

资源采集只消费已校验的执行状态和 G2-03 轨迹，不再次读取热写数据库：

```bash
node scripts/collect_astronstudio_resource_metrics.mjs \
  --state-file /absolute/automation-state.json \
  --trace-index /absolute/trace/trace-index.json
```

Token 使用逐次原生 `last*` 增量求和并与累计 `total*` 对账；工具数按唯一原生 call ID；流程耗时来自执行状态，智能体耗时来自原生 turn 边界。`request_count` 只表示已对账的 usage 推进次数并标记 `inferred`，不能解释为 HTTP 请求数；缓存写入和请求尝试数保持 `null/unavailable`。每个字段独立记录状态、依据、覆盖和证据引用，部分数据使用 `known_subtotals`，不把未知量补零。详见 [AstronStudio 资源指标采集](references/astronstudio-resource-metrics.md)。

## 责任边界

- 输入：执行状态、原生轨迹和终态 Workspace。
- 输出：冻结候选、原始/标准轨迹、资源指标、证据清单和执行回执。
- 校验 attempt 身份、Prompt digest、原生会话绑定及候选完整性。
- 未知指标保留 `null` 和来源状态；不能按零值填充。
- 支持 AstronStudio 和 WorkBuddy macOS 平台收口；其他平台必须明确失败，不得伪造进程清理成功。
- `completed` 必须提供 trace 和 resource metrics；非成功终态只归档实际存在的部分证据。
- `timeout/cancelled` 必须已有执行阶段确认的取消结果，避免后台任务继续写入候选。
- 不调度评分、不判定 criterion、不导入管理员侧回传包。
