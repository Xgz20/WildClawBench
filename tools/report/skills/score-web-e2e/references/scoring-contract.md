# Web E2E 评分 JSON 契约

## `score_input.json`

评分 Agent 只填写判断和证据。文件位于当前单题工作空间的 `private-scoring/score_input.json`：

```json
{
  "evaluation_status": "completed",
  "evaluation_error": null,
  "site_url": "http://127.0.0.1:4173",
  "browser": {"name": "Codex Browser", "viewport": "1440x900"},
  "criteria": [
    {
      "key": "header_daily_overview",
      "score": 1.0,
      "reason": "页面展示指定标题和今日概览。",
      "actions": ["打开首页", "检查顶部区域"],
      "evidence": [
        {"type": "screenshot", "path": "evidence/header.png", "description": "顶部区域"}
      ]
    }
  ],
  "aesthetic_score": null,
  "aesthetic_reason": null,
  "scorer": {"agent": "Codex", "model": "", "session_id": ""}
}
```

`evaluation_status` 只允许 `completed` 或 `evaluation_error`。每个 task contract criterion 必须恰好出现一次，不能增加、删除或改名。

若站点无法启动、浏览器不可用或评分流程异常，将 `evaluation_status` 设为 `evaluation_error` 并填写 `evaluation_error`。此时允许保留初始化后的 `score: null`、空动作和空证据；`finalize_score.mjs` 会保留“未判断”事实，并将总分及维度强制记为 0。若异常前已填写某个 criterion 分数，该项仍必须带理由、动作和证据。

`execution_record.json` 是可选输入，默认批次不生成。缺失时 `finalize_score.mjs` 将 `execution.status` 写为 `not_recorded`，Token、请求数、耗时、成本、工具调用数和格式准确率均为 `null`；这不影响正常浏览器评分和总分。若管理员显式启用执行记录，`tools.format_accuracy` 使用 0–1 比例，不确定字段仍填 `null`，不能凭印象填写。

## `task_score.json`

`finalize_score.mjs` 生成以下稳定结构，保存为 `private-scoring/task_score.json`：

- `identity`：批次、题目、模型、Harness；
- `execution`：执行状态和资源数据；
- `evaluation`：评分状态、浏览器、逐检查点分数与证据；
- `metrics.total_score`：0–100，全部题目总平均分的输入；
- `metrics.primary_dimensions`：一级维度 0–100；
- `metrics.secondary_dimensions`：二级维度 0–100；
- `metrics.aesthetic`：页面美观度，独立于总分；
- `provenance`：题目与 Workspace 哈希、Skill 版本和评分时间。

执行错误、超时和评测异常仍应生成 `task_score.json`。它们的 `metrics.total_score` 为 0，状态字段保留异常类型；汇总报告才能同时计算完成率和全量平均分。`not_recorded + evaluation.completed` 视为正常完成，只表示本批次没有采集执行资源数据。
