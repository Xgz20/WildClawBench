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

当前 `0.9.4/operational` 已交付 automated/hybrid/llm_judge 路由、默认 3 槽且上限 8 的语义评分调度、Codex 项目/任务编排、API Judge 队列与崩溃恢复、统一 `verify-score` 准入、完整范围 submission、独立重评分编排、动态 Codex Desktop 发现、macOS 一次性托管重启入口，以及保留审计的迟到完成评分恢复。v5 评分 Prompt 明确容量异常与候选能力失败的控制策略。评分任务提交前还必须自检 evidence/query 绑定和未发生类完整 transcript 覆盖。迟到恢复发生在旧 submission 之后时，可用显式入口严格复算恢复前内容、按原 SHA 归档并原子替换 submission；其他内容漂移仍失败关闭。G4-03 已用旧版本 AstronStudio macOS 五题覆盖两题 automated、一题 hybrid、两题 llm_judge，得到 5/5 有效评分、回传和三种报告；语义评分固定为 `gpt-6-astra/high`，三会话并发。该证据只支持当时已验证的平台与版本组合，不能自动升级到本版共享发现/重启实现，也不能外推 Windows 或其他 Harness。

普通生产调用不传 `--acceptance-id`。该参数仅用于显式验收留证；传入后，编排状态、队列摘要、评分 Prompt 与每题 `attempt-manifest.json` 中的 acceptance ID 必须完全一致。API Judge 不接受此标记，缺失或不一致时失败关闭。

## 责任边界

- 输入：有效执行回执、scoring 包和冻结裁判配置。
- 输出：独立评分工作空间、评分队列、裁判任务状态和有效 submission。
- 单题评分会话相互隔离；编排器负责调度，单题评分 Agent 不调度下一题。
- 默认后端是 `codex-agent-judge-v1`，`api-judge-v1` 只能显式选择且不能静默切换。
- 不执行被测 Harness，不替代单题评分判断，不生成最终汇总报告。

## 已交付编排子能力

需要初始化或恢复 Codex 评分任务时，读取 [Codex 项目与任务编排](references/codex-orchestration.md)，使用 `scripts/orchestrate_general_e2e.py`。控制器通过 `recommended_actions` 驱动控制 Harness 调用项目列表、`create_thread`、`wait_threads` 和必要的线程检查，不直接伪造模型或工具结果。

每题项目根是独立私有评分 attempt，项目注册器位于 `drivers/codex-desktop/`。语义评分默认 3 槽、可配置 1–8；原 thread 未取得明确终态时不创建替代任务。`automated` 仅运行代码规则并生成 `not-required` 语义组件，不占语义槽；`hybrid` 先运行并冻结规则组件，再进入控制 Harness 语义评分槽；`llm_judge` 直接进入语义槽。线程返回完成后继续占用原槽位并给出 `VERIFY_SCORE`，只有 `record-score` 调用 score Skill 的 `verify-score` 通过并锁定 `score.json` 后才动态补位。

若评分任务显示 `Selected model is at capacity. Please try a different model.`，Codex 会在原任务中自行最多重试 5 次；控制任务继续等待同一 thread，不调用 `create_thread`、不切模型、不创建替代评分 attempt。只有原 thread 最终明确失败后才按现有失败状态收口。候选没有产物、产物损坏或内容不满足题意属于被评测结果；评分会话按 rubric 形成零分、部分分或合法 unresolved，控制任务不能因此终止队列、停止后续题目或重跑 Harness。评分基础设施证据/身份损坏与候选能力失败必须分开。

macOS 当前控制任务需要为 Codex Desktop 补开 CDP 时，必须按 [Codex 项目与任务编排](references/codex-orchestration.md) 使用 `scripts/restart_macos_desktop_debug.sh`。该脚本随 Skill 的 `desktop-debug` 共享组件独立分发；应用路径动态发现并冻结，退出只对已核对根 PID 执行有界 TERM/KILL，不调用 Apple Events、`System Events` 或退出框 UI Automation；禁止用 `launchctl submit` 或常驻 KeepAlive Job 自重启。

显式选择 `api-judge-v1` 时，读取 [API Judge 编排](references/api-orchestration.md)。API 任务从 `API_READY` 进入 `API_RUNNING` 后才调用 score Skill；恢复始终续同一 attempt，已形成终态时不重复请求，结果未知时失败关闭。API 队列不注册 Codex 项目、不创建线程，也不在失败时回退到 Codex。

全部任务进入终态后，读取 [submission 与重评分编排](references/submission-and-rescore.md)。`build-submission` 完整枚举冻结范围并区分 `valid / evaluation_error / unscored`；`init-rescore` 只从已锁定 submission 中选择已有合法评分的任务，创建新的 orchestration 和 attempt，源文件保持不变。
