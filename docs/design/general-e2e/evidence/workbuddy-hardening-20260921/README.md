# WorkBuddy macOS General v2 加固 canary

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

## 已验证加固与剩余边界

代码收尾已完成：并发回执与有效性解耦，调度占用峰值和原生请求重叠峰值分开记录；native project 扁平化路径在创建 attempt 和操作 UI 前检查；Worker 恢复保持原 attempt；finalizer 正式接收 JSONL Token、缓存读取和原生耗时。

真实进程收口已验证受管进程 TERM/KILL 清理和无关进程保护，证据位于 `/Users/gzx/debug-workspace/e2e-evaluate/wb-hardening-20260921/faults/process-cleanup/`。发送临界点强杀 Worker 的同 attempt 不重发也已验证。

仍未形成 WorkBuddy 真机矩阵的项目：客户端执行中重启/重连、未知授权或追问时的安全暂停与恢复、stale lock 无人值守自动恢复。它们是独立技术验收项，不混入本轮能力分数。题目 `timeout_seconds` 不限制被评测 Harness 执行，也不参与评分；评分 thread deadline 仍按编排器安全边界处理。

