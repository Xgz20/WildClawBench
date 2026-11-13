---
name: orchestrate-e2e-pipeline
description: 在 Codex 控制会话中消费 General/Web 单题执行就绪队列，统一调度现有评分 Skill，支持脚本执行中接续评分、整批评分和并发逐题评分。
---

# 编排执行与评分流水线

取得 evaluator checkout、workspace-root 与 batch-id。执行可由 `$execute-sandbox-e2e` 启动，也可 attach 已由 CLI 启动的同一批次。持续状态由 Python 执行器和评分编排器保存。

使用已安装该 checkout 依赖的 Python 解释器调用 helper。

为当前控制聊天选用唯一 owner，后续调用持续携带同一 owner。换控制聊天接续时，先确认旧控制聊天停止，再显式迁移 owner 并保存理由。评分任务沿已记录的原生 thread/host 接续。

```bash
python <skill-dir>/scripts/run_pipeline.py --repo-root <evaluator-root> -- \
  pipeline --workspace-root <evaluation-root> --batch-id <batch-id> \
  next-actions --owner <control-chat-id> --after-cursor 0 --wait-seconds 20
```

依推荐动作串行写入控制状态，评分聊天可按独立评分槽并发。

1. `PREPARE_SCORING_CONTEXT` 调用 prepare-context，带 execution-key、claim-id 和 owner。取得只属于本题的标准评分根、评分包和冻结 Skill 根。
2. `INIT_EXISTING_ORCHESTRATOR` 调用 init-orchestration，在同一上下文中建立现有 General/Web 编排。每个子编排配置 1 槽，由父流水线统一控制并发预算。
3. `FOLLOW_EXISTING_ORCHESTRATOR` 调用 poll，读取该上下文冻结的 orchestrate Skill，按其 recommended_actions 执行规则 Worker、项目注册、评分聊天创建、等待与验分。General 使用 `$orchestrate-general-e2e` 和 `$score-general-e2e`，Web 使用 `$orchestrate-web-e2e` 和 `$score-web-e2e`。
4. 评分项目按完整绝对路径独立注册，每题使用独立原生聊天。CREATE_THREAD 使用下层动作冻结的 model/thinking；记录真实 thread/host 后继续等原聊天。Web 各评分聊天使用自己的 Desktop Browser 路由和分配端口。
5. 下层评分及 submission 验证完成后调用 record-submission。父队列释放该题评分槽，继续领取已就绪题。
6. 收到 `COMPOSE_SELECTED_RESULTS` 后调用 `pipeline compose`，按完整 unit/run 范围生成 `selected-results.json` 和标准 submission。General 的基础设施失败保留为 unscored。Web 只有全范围标准评分回执齐备后生成标准 submission，缺口保留在 selected-results。报告阶段读取这些范围与来源，再按相应 report Skill 的包契约组装和发布。

`scoring_mode=streaming` 时单题就绪即准入，`batch` 时等待执行范围收口。空队列但执行仍活动时继续使用带游标的有界等待，并将活动评分聊天合并调用 wait_threads。控制会话中断后从相同批次和 owner 接续。

原件和评分候选保持只读管理，依赖、build 与服务写入受管运行时副本。发生输入漂移时保留原尝试，从校验备份产生新副本并记录恢复谱系。下层容量重试、Browser 预检、原生终态和验分继续遵守对应冻结 Skill。

本 Skill 依赖 evaluator checkout 的公开 Python CLI。分发给独立评分人员的 purpose=scoring 包包含标准单题评分输入与相应冻结 Skill。

旧批次的收集器需要修复时，可以在首次 prepare-context 显式传入 `--verification-skill-dir`，指定独立构建的新版 collect-general-e2e。交接包保存该补充校验器及摘要，批次原 Skill、数据集和评分材料继续保留。已发布的评分上下文使用其冻结校验器。
