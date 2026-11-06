# AstronStudio macOS 并发队列契约

## 适用范围

`scripts/run_astronstudio_macos_batch.mjs` 在一个已解压的 General E2E execution unit 内，按冻结顺序调用单题执行器。新队列默认为 `ui_slots=1`、后台 `run_slots=3`，可显式配置1–8，并满足冻结配置及逐thread流租约门禁。probe 的 execution_concurrency 和 initial_concurrency 均为3；已有队列沿用原冻结发行和槽位，包括显式单槽配置。真实原生重叠由执行证据确认，默认值及fixture不代表真机并发结论。

## 调用与状态

```bash
node scripts/run_astronstudio_macos_batch.mjs \
  --unit-root /absolute/extracted-unit \
  --run-config /absolute/frozen-run-config.json \
  --queue-id <稳定ID> \
  [--run-slots 3] \
  [--task-id <完整任务ID> ...]
```

未指定任务时使用 `manifest.task_ids` 的完整顺序。指定任务时保留命令中的顺序；任务必须属于当前 unit 且不能重复。队列状态位于：

- `.general-e2e/queues/<queue-id>/queue-state.json`；
- `.general-e2e/queues/<queue-id>/queue-receipt.json`，仅在队列完成时生成；
- `.general-e2e/queues/<queue-id>/worker.lock`，仅在 Worker 存活时存在。

queue digest 覆盖 batch/unit、dataset、manifest SHA、运行配置 digest、任务顺序、UI/后台槽位、明确失败后的继续策略，以及传给单题 Driver 的 CDP/UI/身份绑定控制参数。它不冻结或执行题目 metadata 的 `timeout_seconds`；恢复时任一项变化都会被拒绝。

## 一次发送和切题门禁

每题仍由单题执行器维护 `dispatch_attempt_count<=1`、Prompt digest 和原生身份。队列先持久化 `TASK_DISPATCH_REQUESTED`，再在唯一 UI 槽中启动单题 Driver；Driver 绑定 thread/turn/session/cwd 后退出发送阶段，队列才可串行发送下一题。后台活动数低于冻结槽位时按 manifest 顺序补位。

`RUNNING` 任务继续占后台槽位但不阻止其他空槽补位；`NEEDS_ATTENTION`、缺少 automation state 或发送临界点不明确时停止新发送并保留其他活动任务身份。未启用继续策略时，可信 `FAILED` 会停止补发尚未发送的任务，但已活动任务仍观察到终态。`queue-receipt.json` 复核每题发送计数、唯一 attempt 和整体终态；它不代替 collect receipt。

## Worker 与客户端中断恢复

恢复必须使用同一 unit、run config、queue ID、任务参数和 `--resume`。死亡 Worker 的陈旧锁只在恢复模式清理，并在 history 中登记 `WORKER_PROCESS_LOST / WORKER_RESUMED` 及全部活动 task ID。队列读取各活动题已有 `automation-state.json` 后，只调用单题执行器的 `--resume --observe-once`，不重新走 fresh dispatch。

单题状态已经绑定 `thread_id / turn_id / session_id / cwd` 时，客户端重启后仍按这些身份查询原生状态：若原 turn 仍可继续或已完成，就沿用原 attempt 收口；若原生状态为 `interrupted/cancelled`，则保存 `cancelled` 可信失败。两种结果都不重发 Prompt。客户端尚未恢复到冻结的 loopback CDP 和可见配置时，probe 失败并保留现场。

## attempt 选择边界

队列第一次读取每题 automation state 时，把 `attempt_id` 登记到 `attempts`，并固定为 `selected_attempt_id`。后续状态文件出现不同 attempt 会报 `ATTEMPT_SWITCH_REQUIRES_NEW_QUEUE`，不得由队列或 collect 按时间、目录顺序或“最新”隐式选择。

同一个已准备 unit 当前只允许一个登记 attempt。需要重新做题时，必须保留原 unit/queue 作为证据，重新准备独立 execution unit 并使用新的 queue ID；后续评分或报告若比较多个 attempt，必须由上层显式声明选择策略。

## 并发门禁

`--run-slots` 默认 `3`、上限 `8`，且不得超过冻结运行配置的 `maximum_execution_concurrency`。每次发送前，单题 Driver 会读取原生状态库：所有活动 session 必须都属于队列已登记集合且数量小于槽位上限；出现未登记活动 session 时失败关闭，不发送 Prompt。改变槽位、任务范围或 Driver 参数后不得恢复旧 queue。

0.14.52显式`--resume --retry-pre-send-task-id ID`可在精确绑定RUNNING同伴存在且有空槽时恢复该零发送任务；同伴只观察、不重派。队列传递全部当前同伴session allowlist到单题Driver，二次fresh原生核验仍可拒绝任何外来活动、目标已接受或身份不完整；任何NEEDS_ATTENTION同伴阻断。此恢复不适用于已发送/未知发送。原配置/题序/并发digest不变。

0.14.53可在全部已派任务真正原生空闲、队列worker结束后运行`scripts/prepare_astronstudio_native_projects.mjs --unit-root ABS --run-config ABS --queue-id ID --output NEW_JSON`。入口核验manifest SHA、原队列完整task_ids/config digest、真实模型权限及每个项目唯一完整cwd；既有项目直接复核，缺失项目只用公开“添加项目/输入路径”登记。不调用新任务/新线程/编辑器/发送，不修改automation state或队列attempt，不开私有评分目录。任意活动/外来worker/未知UI表单/原生身份歧义/配置漂移均拒绝；部分失败保留已有原生项目和独立准备回执，恢复新output时再次幂等读回。它不能冒充70题执行，也不改变UI发送单槽和原生Agent最多3槽。
