# WorkBuddy macOS General 执行与采集

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


## runtime API 与正式收口

新版客户端支持 `window.wb.conversations.get(id).requestEntries()` 时，执行器按精确 cwd、会话、request、Prompt SHA 绑定并归档原始运行时快照；collector 读取该快照，无需 `--history-root`。旧 SQLite/history 路径保留。运行时版本只作为元数据，未见过的版本仍按应用身份与实际能力验证。

collector 输出目录中的 `execution/automation-state.json` 带有最终回复的路径和哈希；正式收口须使用这个输出状态，而非执行器的原始状态：

```bash
node collect-general-e2e/drivers/workbuddy/finalize.mjs \
  --unit-root /absolute/unit-root \
  --state-file /absolute/collection/execution/automation-state.json \
  --trace-index /absolute/collection/trace/trace-index.json \
  --resource-metrics /absolute/collection/resource-metrics.json \
  --python /absolute/python3

node collect-general-e2e/drivers/workbuddy/finalize.mjs \
  --verify-only --unit-root /absolute/unit-root --task-id <完整任务ID>
```

入口执行真实 macOS Workspace 精确进程清理、默认 5 秒零残留窗口、5 秒文件静默、完整候选冻结和回执哈希校验。禁止覆盖正式 evidence/receipt。当前仍在接入验收，资源覆盖与评分准入、固定数据集完整闭环尚需完成；不能把 canary PASS 解释为全部通用评测生产可用。

`workbuddy-evidence` 是 execute/collect 的共享发行组件；两个 Skill ZIP 各自包含所需依赖，可在无仓库环境加载，控制器不再依赖 `eval_general_e2e` 的仓库路径。


资源 `collection.status` 表示绑定原生请求的证据是否完整，逐字段 `metrics.*.status/coverage` 表示数值是否可观测。完整请求的空 usage 不阻断内容评分：token/cache 仍为 `null/unavailable`，工具和 request 数仍保留真实观测。截断轨迹、未知块、部分已知数据或非法数值仍阻断或降级，不能把采集缺失写成完整。


## 持久化三路队列

```bash
node execute-general-e2e/drivers/workbuddy/batch.mjs \
  --unit-root /absolute/new-execution-unit --queue-id serial-01 \
  --endpoint http://127.0.0.1:9229 --expected-permission default-sandbox \
  --run-slots 3
```

`--run-slots` 默认 3、范围 1–8。UI 创建任务、选目录和发送始终单槽；绑定后的原生 Agent 最多按冻结槽位后台运行，任一题取得可信终态后按 manifest 顺序动态补位。每次新发送前，Driver 从队列状态重验所有活动 conversation/cwd/attempt，只允许本队列已经登记且仍为 `RUNNING` 的会话；额外活动会话、身份漂移、未知 UI busy 或达到槽位上限均失败关闭。

发送前还按 WorkBuddy 实际规则把绝对 Workspace 去掉开头 `/` 并把路径分隔符替换为 `-`，校验单个 native project 目录不超过 255 UTF-8 字节，并为 session JSONL 校验 macOS 1024 字节路径上限。越限在创建 attempt、占用发送 reservation 或操作 UI 之前失败，提示改用更短的 unit 根；短路径 smoke 通过不代替此预检。

恢复使用相同参数并增加 `--resume`。队列在 `.general-e2e/queues/workbuddy/` 冻结 manifest、顺序、槽位、Driver 摘要和每题预留 attempt ID。新队列拒绝接管队列外已有 attempt；恢复只观察原 attempt，不重发已发送 Prompt。完成后生成 `*-receipt.json`：`observed_max_concurrency` 明确为 Prompt 已发送至终态的调度占用峰值，`native_observed_max_concurrency` 来自 runtime request 起止区间，并带原生区间覆盖率；两者不能互换。`integrity.valid` 只校验终态、attempt 唯一和无重复发送，并发是否达到请求槽位在 `concurrency_evidence` 独立报告。该回执证明队列调度，不替代正式 collect receipt。

活动或陈旧 owner-lock 均不会自动删除。异常退出后的锁恢复属于值守操作：先核对锁中的主机和 PID 生命周期及真实任务现场，再处理已证明死亡的旧 Worker；不能直接删除未知锁后新建 attempt。尚未验收无人值守恢复。
