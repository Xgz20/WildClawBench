# WorkBuddy macOS General v2 加固 canary

> 证据边界：本文只记录所列日期、批次和 revision 的事实，保留原失败与未知项。当前集成进度和下一步统一见[集成契约](../../../e2e/端到端自动化评测Harness接入契约.md#integration-progress)，不从本文旧“当前/下一步”推导最新支持状态。

日期：2026-09-21（Asia/Shanghai）。本证据只覆盖 WorkBuddy macOS x86_64 的 5 题 canary，不是 60 题全量评测，也不扩大 Windows、Apple Silicon 或其他 Harness 的支持范围。

## 冻结身份

- Harness：WorkBuddy 5.5.6 / macOS x86_64；模型：`xopglm52`；单元：`wb`。
- 发行：`workbuddy-hardening-20260921-v2`，suite SHA-256：`8bed29d5024733569062f646859082dda4289f8820711bfe3f16d45db533bdb2`。
- Skill：execute `0.10.7`、collect `0.7.3`、orchestrate `0.9.3`、score `0.8.1`、report `0.5.0`。
- 数据集 digest：`119568a06a100461445c92544ca4c90e0c5c70fba49711a0fd915a6c708f1d0a`。
- 执行根：`/Users/gzx/debug-workspace/e2e-evaluate/wbh2/x/wbh2__wb`。
- 评分编排根：`/Users/gzx/debug-workspace/e2e-evaluate/wbh2/o/wbh2-gpt6-astra-high`。

## 执行、采集和并发

本轮仅冻结并执行 5 题，`run_slots=3`。5/5 任务均正常完成、每题发送一次；原生请求区间覆盖 5/5，原生并发峰值为 3，动态补位 2，队列 integrity/concurrency 均通过。Worker 强杀恢复证据保留在 `/Users/gzx/debug-workspace/e2e-evaluate/wbh1/faults/worker-kill/`，同一 attempt 恢复后 5 题发送计数仍为 1。

正式 collect/finalizer 5/5 通过，verify-only 5/5 通过。收集回执 SHA-256：`4e83c46e42b1ea6b948155131c057d9af0967d128caeecd78368a2aaba2f6637`。

资源汇总：模型响应 47、总 Token 2,318,336、缓存读取 2,196,992、工具调用 66、原生任务耗时 1,230.418 秒、流程耗时 1,415.750 秒。缓存写入和普通输入缺少完整独立来源，报告保持 `-`，没有按 0 补造。

## 评分、回传和报告

评分没有重跑 Harness。5 个原始评分 thread 均保持原 attempt；遇到 `Selected model is at capacity...` 的第 008 题在原 thread 内形成明确失败后收口，没有新开会话或切换模型。候选评分异常继续进入队列，没有终止控制会话。

- 有效评分 2：第 004 题语义分 0.90，第 005 题自动评分 0.8417。
- 评分 `evaluation_error` 2：第 007 题 `SEMANTIC_CITATION_NOT_QUERIED`，第 009 题 `SEMANTIC_ABSENCE_COVERAGE_REQUIRED`。
- 未评分 1：第 008 题容量错误导致原 thread `THREAD_FAILED`。
- submission：`/Users/gzx/debug-workspace/e2e-evaluate/wbh2/o/wbh2-gpt6-astra-high/submission.json`。
- 回传包：`/Users/gzx/debug-workspace/e2e-evaluate/wbh2/returns/wbh2__wb__return__fcac632207489806.zip`，SHA-256：`286d4a4d0a172bdab63f22a27195161ab6e9e47c19a315049d500ae71a383527`。
- 报告目录：`/Users/gzx/debug-workspace/e2e-evaluate/wbh2/current/wbh2/reports/workbuddy-hardening-20260921-v2`。
- 报告输入验证 PASS；Excel 10 个 Sheet、关键范围和公式错误扫描 PASS。报告总览保留 5/5 正常完成、评测异常 2、有效评分 2、未评分 1，不把异常或未评分补成能力零分。

## WorkBuddy 重启/重连故障验证

在独立单题 attempt `c92a85fc-9115-4dab-8a91-34ea928bc105` 中，Prompt 只发送一次并绑定了 `conversation_id=c0a1ab89-4382-4dbe-9579-810d6744ffd9`、`request_id=req-1790002888976031`。随后核对并停止 WorkBuddy 根 PID `92862`：TERM 无效，复核可执行路径后 KILL；使用现有启动脚本重新启动 WorkBuddy，新的根 PID 为 `61831`，`9229` 暴露 1 个 target。

同 attempt 恢复观察未能在客户端重启后确认唯一终态，dispatch journal 按安全策略进入 `NEEDS_ATTENTION`，`dispatch_attempt_count` 仍为 1，Prompt 未重发，也没有新 attempt。Codex `9230` 在整个操作后仍可达，未执行 Codex 重启。原始证据：`/Users/gzx/debug-workspace/e2e-evaluate/wb-restart-20260921/faults/restart-reconnect/restart-reconnect-evidence.json`。

## 已验证加固与剩余边界

代码收尾已完成：并发回执与有效性解耦，调度占用峰值和原生请求重叠峰值分开记录；native project 扁平化路径在创建 attempt 和操作 UI 前检查；Worker 恢复保持原 attempt；finalizer 正式接收 JSONL Token、缓存读取和原生耗时。

真实进程收口已验证受管进程 TERM/KILL 清理和无关进程保护，证据位于 `/Users/gzx/debug-workspace/e2e-evaluate/wb-hardening-20260921/faults/process-cleanup/`。发送临界点强杀 Worker 的同 attempt 不重发也已验证。

仍未形成 WorkBuddy 真机矩阵的项目：未知授权或追问时的安全暂停与恢复、stale lock 无人值守自动恢复。客户端重启/重连的最小证据已完成，但该 attempt 是故障验证，不进入本轮能力评分。题目 `timeout_seconds` 不限制被评测 Harness 执行，也不参与评分；评分 thread deadline 仍按编排器安全边界处理。Codex 重启验证暂缓。

