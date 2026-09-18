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

只有 `implementation_status` 为 `operational` 时才形成完整评分 submission。当前 `0.2.0/interface_only` 已交付 Codex 项目注册和可恢复单题任务编排子能力：可以创建独立评分 attempt、冻结裁判配置并持久化 project/thread/cursor/deadline；语义取证、结构化判定、合分与 submission 尚未交付。因此不得把线程完成状态当成有效评分，也不得借用 Web E2E 浏览器评分协议。

## 责任边界

- 输入：有效执行回执、scoring 包和冻结裁判配置。
- 输出：独立评分工作空间、评分队列、裁判任务状态和有效 submission。
- 单题评分会话相互隔离；编排器负责调度，单题评分 Agent 不调度下一题。
- 默认后端是 `codex-agent-judge-v1`，`api-judge-v1` 只能显式选择且不能静默切换。
- 不执行被测 Harness，不替代单题评分判断，不生成最终汇总报告。

## 已交付编排子能力

需要初始化或恢复 Codex 评分任务时，读取 [Codex 项目与任务编排](references/codex-orchestration.md)，使用 `scripts/orchestrate_general_e2e.py`。控制器只接受已明确配置模型和推理强度的 `codex-agent-judge-v1`，当前不接收 API Judge；它通过 `recommended_actions` 驱动控制 Harness 调用项目列表、`create_thread`、`wait_threads` 和必要的线程检查，不直接调用模型或伪造工具结果。

每题项目根是独立私有评分 attempt，项目注册器位于 `drivers/codex-desktop/`。同一编排首版固定单槽；原 thread 未取得明确终态时不创建替代任务。G3-04 接入真实语义评分和结果校验前，本 Skill 保持 `interface_only`。
