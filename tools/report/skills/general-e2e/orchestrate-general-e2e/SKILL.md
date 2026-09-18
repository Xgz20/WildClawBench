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

只有 `implementation_status` 为 `operational` 时才形成完整生产评分闭环。当前 `0.5.0/interface_only` 已交付 Codex 项目/任务编排、API Judge 队列与崩溃恢复、Judge 配置写入评分 attempt、统一的 `verify-score` 准入、完整范围 submission 和独立重评分编排；语义取证、transport、结构化判定与标准 `score.json` 由配套 score Skill 提供。真实 Codex 小批和 API Judge 生产准入尚未交付，不能借用 Web E2E 浏览器评分协议。

## 责任边界

- 输入：有效执行回执、scoring 包和冻结裁判配置。
- 输出：独立评分工作空间、评分队列、裁判任务状态和有效 submission。
- 单题评分会话相互隔离；编排器负责调度，单题评分 Agent 不调度下一题。
- 默认后端是 `codex-agent-judge-v1`，`api-judge-v1` 只能显式选择且不能静默切换。
- 不执行被测 Harness，不替代单题评分判断，不生成最终汇总报告。

## 已交付编排子能力

需要初始化或恢复 Codex 评分任务时，读取 [Codex 项目与任务编排](references/codex-orchestration.md)，使用 `scripts/orchestrate_general_e2e.py`。控制器通过 `recommended_actions` 驱动控制 Harness 调用项目列表、`create_thread`、`wait_threads` 和必要的线程检查，不直接伪造模型或工具结果。

每题项目根是独立私有评分 attempt，项目注册器位于 `drivers/codex-desktop/`。同一编排首版固定单槽；原 thread 未取得明确终态时不创建替代任务。线程返回完成后，控制器保持当前槽位并给出 `VERIFY_SCORE`，只有 `record-score` 调用 score Skill 的 `verify-score` 通过并锁定 `score.json` 后才进入下一题。

显式选择 `api-judge-v1` 时，读取 [API Judge 编排](references/api-orchestration.md)。API 任务从 `API_READY` 进入 `API_RUNNING` 后才调用 score Skill；恢复始终续同一 attempt，已形成终态时不重复请求，结果未知时失败关闭。API 队列不注册 Codex 项目、不创建线程，也不在失败时回退到 Codex。

全部任务进入终态后，读取 [submission 与重评分编排](references/submission-and-rescore.md)。`build-submission` 完整枚举冻结范围并区分 `valid / evaluation_error / unscored`；`init-rescore` 只从已锁定 submission 中选择已有合法评分的任务，创建新的 orchestration 和 attempt，源文件保持不变。
