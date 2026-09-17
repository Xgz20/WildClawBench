---
name: collect-general-e2e
description: 收集 General E2E 执行状态、终态 Workspace、原始轨迹和资源数据并形成正式执行回执；不用于导入评分回传包或决定分数。
---

# 采集 General E2E 证据

将一次执行 attempt 收口为冻结候选和可审计证据，阶段名固定为 `collect-evidence`，不与 `import-return` 混用。

## 当前能力门禁

先运行：

```bash
python -m eval_general_e2e skills --name collect-general-e2e --json
```

整个 Skill 只有 `implementation_status` 为 `operational` 时才能生成冻结候选和正式执行回执。当前 `0.3.0/interface_only` 已交付 AstronStudio macOS 的轨迹和资源子能力：可将精确绑定的原生 turn 事件归档为原始 JSONL、标准 transcript 和 trace index，并从冻结轨迹映射 `resource-metrics-v1`。候选冻结和正式收口仍未交付，不得将这些产物单独宣称为可评分回执。不得从最终文件反推或补造工具记录、Token、请求次数及原生会话身份。

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
- 不调度评分、不判定 criterion、不导入管理员侧回传包。
