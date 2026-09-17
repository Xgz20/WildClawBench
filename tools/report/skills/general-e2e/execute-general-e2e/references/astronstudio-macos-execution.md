# AstronStudio macOS 单题执行契约

## 适用范围

`scripts/execute_astronstudio_macos.mjs` 接收一个已解压的 General E2E execution unit、一个完整 task ID 和 G2-01 冻结运行配置。它完成单题 Prompt 一次发送、`thread_id / turn_id / session_id / cwd` 绑定和原生终态观察。

当前实现不负责超时停止、候选冻结、轨迹归档、资源采集、评分或报告。串行批量由 [macOS 队列入口](astronstudio-macos-queue.md) 调用本执行器；采集与正式回执由 `collect-general-e2e` 负责。执行器输出的 `execution-record.json` 因此固定为 `evidence.completeness=partial`、`candidate.drift_status=not_frozen`、`resource_metrics_path=null`，不能直接作为评分准入回执。

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

状态查询只读取主状态库的临时副本及同批复制的 WAL/SHM，不写源库。AStudio 热写入导致副本 `quick_check` 或查询短暂失败时，单次查询先退避重试；Prompt 已发送并绑定身份后，终态轮询继续保留同一 attempt 重试，不因此创建新任务或再次发送。`--resume --observe-once` 仍只尝试一次上层观察；该次读取失败会持久化 `NATIVE_STATE_READ_FAILED / NEEDS_ATTENTION`，可再次恢复。

执行锁遗留时，只有 `--resume` 且记录的 PID 已不存活才允许清除陈旧锁；普通新运行不会接管锁。单题 Driver 同时持有 unit 级 `astronstudio-ui.lock` 和 task 级 `driver.lock`，因此即使绕过队列直接启动多个单题入口，也只有一个进程可以操作 AStudio UI。

发送前 Driver 失败会写 `FAILED / infrastructure_error / not_sent`，该 attempt 保持终态，`--resume` 只回读而不会在原 attempt 补发。修复环境或 Driver 后，应保留失败状态作为证据并从新准备的 execution unit 创建新 attempt；不得删除状态后把后续发送伪装成同一次执行。

## 终态

`projection_turns.state=completed` 是可信成功终态，不要求 workspace 必须发生变化，因此纯回复任务也能完成。`error/failed` 映射为 `infrastructure_error`，`interrupted/cancelled` 映射为 `cancelled`。达到任务时限时 G2-02 只进入 `NEEDS_ATTENTION` 并保留现场；可信停止、静默窗口、任务进程收口和 `timeout` 候选冻结属于 G2-05。

退出码：

- `0`：`COMPLETED`；
- `4`：已发送并绑定身份，当前仍为 `RUNNING`（通常来自 `--detach-after-submit`）；
- `3`：`NEEDS_ATTENTION`；
- `2`：参数、输入、执行失败或原生失败终态。
