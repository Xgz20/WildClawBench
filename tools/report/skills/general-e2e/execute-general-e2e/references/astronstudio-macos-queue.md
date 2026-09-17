# AstronStudio macOS 串行队列契约

## 适用范围

`scripts/run_astronstudio_macos_batch.mjs` 在一个已解压的 General E2E execution unit 内，按冻结顺序调用单题执行器。G2-06 发布范围只有 `ui_slots=1 / run_slots=1`。它不复用 Web 队列的三槽默认值，也不把 fixture 测试当成 MAC-08 并发真机证据。

## 调用与状态

```bash
node scripts/run_astronstudio_macos_batch.mjs \
  --unit-root /absolute/extracted-unit \
  --run-config /absolute/frozen-run-config.json \
  --queue-id <稳定ID> \
  [--task-id <完整任务ID> ...]
```

未指定任务时使用 `manifest.task_ids` 的完整顺序。指定任务时保留命令中的顺序；任务必须属于当前 unit 且不能重复。队列状态位于：

- `.general-e2e/queues/<queue-id>/queue-state.json`；
- `.general-e2e/queues/<queue-id>/queue-receipt.json`，仅在队列完成时生成；
- `.general-e2e/queues/<queue-id>/worker.lock`，仅在 Worker 存活时存在。

queue digest 覆盖 batch/unit、dataset、manifest SHA、运行配置 digest、任务顺序、单槽值、明确失败后的继续策略，以及传给单题 Driver 的超时参数。恢复时任一项变化都会被拒绝。

## 一次发送和切题门禁

每题仍由单题执行器维护 `dispatch_attempt_count<=1`、Prompt digest 和原生身份。队列先持久化 `TASK_DISPATCH_REQUESTED`，再启动单题 Driver。当前题只有 `COMPLETED`，或在显式 `--continue-on-terminal-failure` 下得到 `FAILED` 可信终态，才会进入下一题。

`RUNNING`、`NEEDS_ATTENTION`、缺少 automation state 或 Driver 返回后无法确认终态时都阻止切题。`queue-receipt.json` 复核每题发送计数、唯一 attempt 和整体终态；它不代替 collect receipt。

## Worker 与客户端中断恢复

恢复必须使用同一 unit、run config、queue ID、任务参数和 `--resume`。死亡 Worker 的陈旧锁只在恢复模式清理，并在 history 中登记 `WORKER_PROCESS_LOST / WORKER_RESUMED`。队列读取当前题已有 `automation-state.json` 后，只调用单题执行器的 `--resume`，不重新走 fresh dispatch。

单题状态已经绑定 `thread_id / turn_id / session_id / cwd` 时，客户端重启后仍按这些身份查询原生状态：若原 turn 仍可继续或已完成，就沿用原 attempt 收口；若原生状态为 `interrupted/cancelled`，则保存 `cancelled` 可信失败。两种结果都不重发 Prompt。客户端尚未恢复到冻结的 loopback CDP 和可见配置时，probe 失败并保留现场。

## attempt 选择边界

队列第一次读取每题 automation state 时，把 `attempt_id` 登记到 `attempts`，并固定为 `selected_attempt_id`。后续状态文件出现不同 attempt 会报 `ATTEMPT_SWITCH_REQUIRES_NEW_QUEUE`，不得由队列或 collect 按时间、目录顺序或“最新”隐式选择。

同一个已准备 unit 当前只允许一个登记 attempt。需要重新做题时，必须保留原 unit/queue 作为证据，重新准备独立 execution unit 并使用新的 queue ID；后续评分或报告若比较多个 attempt，必须由上层显式声明选择策略。

## 并发门禁

`--run-slots` 只接受 `1`。五题三槽动态补位、并发隔离、进程收口和串行对照属于 MAC-08/G4-05，必须在目标客户端和发布身份上另行验收后才能提高默认值。
