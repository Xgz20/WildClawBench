---
name: execute-sandbox-e2e
description: 使用 WildClawBench Python 入口在 AgentCube Windows 沙箱中执行 General/Web 用例，管理批次、并发、多 run、原始结果备份、恢复和分发。
---

# 执行沙箱端到端评测

先取得 WildClawBench checkout 的绝对路径和评测工作根。仓库提供 `eval/run_e2e.py`，本 Skill 提供其公开调用封装。认证由执行进程的 `AGENTCUBE_AUTH_TOKEN` 提供，App-ID、User-ID 与端点来自非敏感配置。

使用已安装该 checkout 依赖的 Python 解释器调用下列 helper。

```bash
python <skill-dir>/scripts/run_sandbox.py --repo-root <evaluator-root> -- \
  run --workspace-root <evaluation-root> --scenario general \
  --dataset general-custom70-v3 --task-id <task-id> \
  --model spark-x2.6 --reasoning-effort high \
  --agentcube-config <config.json> --concurrency 3 --runs 1 \
  --timeout-override 10800 --jsonl
```

Web 使用 `--scenario web`。多配置单元使用 `--plan <batch-plan.json>`。`--timeout-override` 以秒覆盖整次调用中的 wgui 运行预算；计划内也可逐 unit 声明。`--dry-run` 生成冻结材料和计划摘要。

执行器保存父批次、unit、run、task 与 attempt 身份，每次 run 使用独立沙箱。控制会话通过精确批次的 status 或事件游标观察。恢复使用 resume 和原 batch-id，按持久化远端 job 继续观察。

每题完成原生绑定、远端进程收口和备份后发布 execution-ready。查看原生工具过程时读取已归一化 transcript 及 raw 引用，ATIF 的转换状态单独记录。

执行可在受管独立进程中运行，启动时保留完整 argv、PID、创建身份及日志位置。控制会话重连后先核验原进程，继续观察原批次。创建或派发未知时进入 NEEDS_ATTENTION，依据平台和原 job 证据恢复。

结果操作使用同一入口的 restore、export、import。restore 生成新工作副本，source archive SHA 作为恢复依据。export 支持按 execution-key、unit 和 run 选择，purpose=scoring 会生成独立评分材料及锁定 Skill。

需要执行与评分并行时，将批次交给 `$orchestrate-e2e-pipeline`。它消费相同的 execution-ready 队列。
