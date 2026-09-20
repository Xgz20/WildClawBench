# WorkBuddy macOS General 离线预检

在真实新时段开始前，从脱仓后的 `general-e2e` Skill 根目录运行：

```bash
node execute-general-e2e/drivers/workbuddy/preflight.mjs --skill-root /absolute/general-e2e
```

预检只读取包内文件，确认 `task-process-cleanup` 共享组件、WorkBuddy CB-B collector、
四个原生 source gate 字段和 CB-B 的 state/trace/resource/cleanup 输入仍可装配。输出 `PASS`
只代表离线包完整，不代表客户端已启动、slot 已取得、历史 canary 已处理或真机
collect/cleanup 已通过。

正式 collect 还必须保存本题的 `conversationId`、`requestId`、原生 `cwd`、终态来源、
原始 trace、resource metrics，以及 cleanup 前后精确 Workspace 进程快照；缺任一项应
保持 `REVIEW/未验证`，不能用状态字段或候选 Workspace 反推。

## CB-B 原生证据采集

执行阶段写入终态 `dispatch-journal.json` 和 `execution-state.json` 后，使用
`collect-general-e2e` 下的 WorkBuddy collector 组装通用 finalizer 所需的 CB-B 输入：

```bash
node collect-general-e2e/drivers/workbuddy/collector.mjs \
  --unit-root /absolute/unit-root \
  --journal-file /absolute/unit-root/.general-e2e/execution/<task-id>/workbuddy/dispatch-journal.json \
  --state-file /absolute/unit-root/.general-e2e/execution/<task-id>/workbuddy/execution-state.json \
  --history-root /absolute/WorkBuddyExtension/Data \
  --output-root /absolute/unit-root/.general-e2e/collection/<attempt-id>
```

collector 只读取已终态的 CB-A 状态、dispatch journal、WorkBuddy 原生 history 和绑定证据，
输出 `execution/automation-state.json`、`trace/trace-index.json`、原始 history、绑定证据和
`resource-metrics.json`。输出目录必须是单元内尚不存在的目录；journal/state 的任务身份、
Prompt digest、一次发送、原生 `conversationId`/`requestId`/`cwd` 和每个绑定文件的 SHA-256
必须一致。历史解析或 digest 校验失败时原子失败关闭，不留下部分输出。

该 collector 不启动、停止、重启或通过 CDP 操作 WorkBuddy，也不执行进程清理；采集结果只
作为通用 `finalize_general_execution.mjs` 的输入。正式收口仍必须由平台真实 cleanup hook
完成精确 Workspace 进程清理、静默窗口和不可变 verify-only 校验。未知的 token、credit、
重试、终端或耗时字段继续保持 `null`/`unavailable`/`unverified`。
