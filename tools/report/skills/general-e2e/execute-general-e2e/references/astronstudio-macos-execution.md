# AstronStudio macOS 单题执行契约

## 适用范围

`scripts/execute_astronstudio_macos.mjs` 接收一个已解压的 General E2E execution unit、一个完整 task ID 和 G2-01 冻结运行配置。它完成单题 Prompt 一次发送、`thread_id / turn_id / session_id / cwd` 绑定和原生终态观察。

当前实现不负责任务级超时停止、候选冻结、轨迹归档、资源采集、评分或报告。题目 metadata 的 `timeout_seconds` 只作为数据集兼容字段，不参与被测 Harness 的执行 deadline；执行状态中的 `execution.deadline_at` 固定为 `null`。`--timeout-ms`、`--identity-timeout-ms` 和轮询间隔只服务于 CDP/UI 操作、网络探测和发送后身份绑定。串行批量由 [macOS 队列入口](astronstudio-macos-queue.md) 调用本执行器；采集与正式回执由 `collect-general-e2e` 负责。执行器输出的 `execution-record.json` 因此固定为 `evidence.completeness=partial`、`candidate.drift_status=not_frozen`、`resource_metrics_path=null`，不能直接作为评分准入回执。

## 调用

```bash
node scripts/execute_astronstudio_macos.mjs \
  --unit-root /absolute/extracted-unit \
  --task-id 02_Code_Intelligence_task_001_temperature_cli_fix \
  --run-config /absolute/astronstudio-macos-run-config.json
```

恢复同一 attempt：

```bash
node scripts/execute_astronstudio_macos.mjs \
  --unit-root /absolute/extracted-unit \
  --task-id <完整任务ID> \
  --run-config /absolute/astronstudio-macos-run-config.json \
  --resume
```

输出位于 `<unit-root>/.general-e2e/execution/<task-id>/`：

- `automation-state.json`：遵循 [execution state schema](astronstudio-execution-state-v1.schema.json)；
- `execution-record.json`：遵循仓库 `general-e2e execution-record v1`；
- `final-response.md`：原生终态可取得最终助手回复时写入；
- `driver.lock`：仅在 Driver 进程存活期间存在。

## 一次发送与恢复

1. 校验 execution manifest、Prompt SHA-256、冻结配置 digest、客户端版本、模型、推理强度和权限。
2. 新建空白任务并按绝对路径选择 execution task 的 `workspace/`。
3. 填入 Prompt，保存 workspace 原生会话基线、路由 thread 和 `intent_persisted`；随后把 `dispatch_attempt_count` 原子地固定为 `1`。
4. 只调用一次发送动作。发送返回后记录 `sent_at`；连接在临界点断开时，先用已保存的 route/baseline 查询原生状态库。
5. 只有唯一匹配的 cwd、route thread、新 turn 和 provider session 同时存在时才确认发送。否则写 `uncertain / NEEDS_ATTENTION`，恢复不得再次调用发送动作。
6. 恢复只观察同一 `attempt_id` 和已绑定身份。原 thread 出现其他 turn、身份不唯一、未知状态或待授权/待用户输入时均进入 `NEEDS_ATTENTION`。

`0.11.25` 在发送点击前同次回读唯一可见的 Prompt、完整 Workspace、无遮挡发送按钮和未知对话框数量；点击改为 CDP 鼠标移动/按下/释放事件。点击动作返回不代表客户端已受理，仍以原生 thread/turn/session/cwd 为准。校验失败或发送后无原生身份都保留一次发送意图并暂停，不自动补点或重置计数。

`0.11.26` 只对编辑器自动生成的 `role=link / contenteditable=false` URL chip，在冻结 Prompt 中按 DOM 顺序找到完全相同的 `http(s)` `title`，用 chip 的可见文本重建期望显示值；正文其他字符仍要求完全一致。发送前的同次回读与填入后的回读使用同一规则，缺失 title、未知协议或不一致均失败关闭。超时诊断只记录长度与 chip 数，不再输出完整草稿文本。

`0.11.27` 发送前还要求当前目标 thread 的本地 `server.log` 中有未释放、持续至少 1.5 秒的精确 `orchestration.thread:<thread-id>` 流租约。按目标 route 和 attempt 创建时间过滤结构化 `admitted/released` 事件，不把其它订阅的 active lease 列表当作该 thread 的准入。最多只读等待 120 秒；未取得正证据时在发送意图落盘前失败，`dispatch_attempt_count=0`，不点击按钮。此门禁不替代发送后的原生 thread/turn/session/cwd 绑定。

`0.11.28` 在发送意图落盘前先移开项目预览悬停卡片，并按唯一 Prompt、Workspace、弹窗和发送按钮无遮挡回读目标。此时未就绪属于发送前失败，`dispatch_attempt_count=0`；只有通过该检查后才持久化一次发送意图。落盘后的最终点击仍重新检查目标；若此时出现竞态或断连，保留 `PROMPT_SEND_UNCERTAIN` 且绝不补点。项目本地显示别名不改变 Prompt 或 Workspace 身份。

`0.11.29` 对“项目已创建但当前对话仍留在其他 Workspace”增加发送前回读：仅在项目选择控件缺失时，用状态库中完整 Workspace 唯一查得 project ID，打开该项目侧边栏的唯一“新建对话”按钮；新路由必须空白、可见路径必须精确等于目标 Workspace，原生 thread→project→cwd 也必须一致。任一步失败保持零发送并留基础设施错误，不把项目 basename 或本地显示别名当路径证据。

`0.11.30` 对项目导航与路径控件异步出现的竞态补充二次回读：若目标完整路径已经在当前空白路由可见，且原生 thread→project→cwd 唯一一致，则直接接受当前路由；点击目标项目“新建对话”后即使路由 ID 不变，也只在相同 UI 与原生身份门禁通过时接受。没有正证据仍在发送意图落盘前停止。

状态查询只读取主状态库的临时副本及同批复制的 WAL/SHM，不写源库。AStudio 热写入导致副本 `quick_check` 或查询短暂失败时，单次查询先退避重试；Prompt 已发送并绑定身份后，终态轮询继续保留同一 attempt 重试，不因此创建新任务或再次发送。`--resume --observe-once` 仍只尝试一次上层观察；该次读取失败会持久化 `NATIVE_STATE_READ_FAILED / NEEDS_ATTENTION`，可再次恢复。

执行锁遗留时，只有 `--resume` 且记录的 PID 已不存活才允许清除陈旧锁；普通新运行不会接管锁。单题 Driver 同时持有 unit 级 `astronstudio-ui.lock` 和 task 级 `driver.lock`，因此即使绕过队列直接启动多个单题入口，也只有一个进程可以操作 AStudio UI。

发送前 Driver 失败会写 `FAILED / infrastructure_error / not_sent`，该 attempt 保持终态，`--resume` 只回读而不会在原 attempt 补发。修复环境或 Driver 后，应保留失败状态作为证据并从新准备的 execution unit 创建新 attempt；不得删除状态后把后续发送伪装成同一次执行。

## 终态

`projection_turns.state=completed` 是可信成功终态，不要求 workspace 必须发生变化，因此纯回复任务也能完成。`error/failed` 映射为 `infrastructure_error`，`interrupted/cancelled` 映射为 `cancelled`。执行器会持续观察到可信原生终态或需要人工关注的状态，不会因为题目 `timeout_seconds` 到期而停止被测 Harness；可信停止、静默窗口、任务进程收口和 `timeout` 候选冻结属于采集/故障处理契约，而非题目执行 deadline。

退出码：

- `0`：`COMPLETED`；
- `4`：已发送并绑定身份，当前仍为 `RUNNING`（通常来自 `--detach-after-submit`）；
- `3`：`NEEDS_ATTENTION`；
- `2`：参数、输入、执行失败或原生失败终态。
