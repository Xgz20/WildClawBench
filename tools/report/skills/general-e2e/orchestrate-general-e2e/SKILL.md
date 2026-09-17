---
name: orchestrate-general-e2e
description: 将有效 General E2E 执行回执交接为独立单题评分工作空间并调度 Codex 或 API Judge；用于评分编排，不负责执行用例或亲自判断分数。
---

# 编排 General E2E 评分

为每个任务建立隔离评分 attempt，冻结裁判配置并维护可恢复的评分队列。

## 当前能力门禁

先运行：

```bash
python -m eval_general_e2e skills --name orchestrate-general-e2e --json
```

只有 `implementation_status` 为 `operational` 时才创建评分任务。当前 `interface_only` 表示评分工作空间和调度实现尚未交付；不得把当前控制会话的临时判断写成正式 `score.json`，也不得借用 Web E2E 浏览器评分协议。

## 责任边界

- 输入：有效执行回执、scoring 包和冻结裁判配置。
- 输出：独立评分工作空间、评分队列、裁判任务状态和有效 submission。
- 单题评分会话相互隔离；编排器负责调度，单题评分 Agent 不调度下一题。
- 默认后端是 `codex-agent-judge-v1`，`api-judge-v1` 只能显式选择且不能静默切换。
- 不执行被测 Harness，不替代单题评分判断，不生成最终汇总报告。
