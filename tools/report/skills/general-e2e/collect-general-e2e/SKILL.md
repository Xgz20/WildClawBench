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

当前 `0.4.0/operational` 支持 AstronStudio macOS 的完整采集阶段：精确归档原生 turn、生成标准 transcript 和资源指标、收口任务进程、冻结终态候选，并生成正式执行回执。不得从最终文件反推或补造工具记录、Token、请求次数及原生会话身份。

## 正式收口流程

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
- 只支持 AstronStudio macOS 正式收口；其他平台必须明确失败，不得伪造进程清理成功。
- `completed` 必须提供 trace 和 resource metrics；非成功终态只归档实际存在的部分证据。
- `timeout/cancelled` 必须已有执行阶段确认的取消结果，避免后台任务继续写入候选。
- 不调度评分、不判定 criterion、不导入管理员侧回传包。
