---
name: execute-general-e2e
description: 在 AstronStudio 等桌面 Harness 中执行单个或批量 General E2E 用例；用于自动或人机协作做题，不负责正式证据收口、评分或报告。
---

# 执行 General E2E 用例

驱动或协助桌面 Harness 执行 execution 包，并持久化可恢复的发送和原生会话状态。

## 当前能力门禁

先运行：

```bash
python -m eval_general_e2e skills --name execute-general-e2e --json
```

只有 `implementation_status` 为 `operational` 时才发送 Prompt。当前 `0.10.17/operational` 支持 AstronStudio macOS 只读探针、单题执行和持久化并发队列，以及 WorkBuddy/QwenWork macOS 的默认三路后台队列入口；UI Prompt 发送固定单槽，后台 Agent 默认 3 槽、可配置 1–8，并按可信终态动态补位。QwenWork 单题入口会从已完成会话语义导航到唯一“新任务”页，允许未发送 attempt 精确复用已经落库的同名同 Workspace 项目，在终态观察时刷新同一 session 的 Prompt/transcript provenance，并在恢复观察前把 UI 路由精确导航到目标项目任务。应用路径通过 vendored `desktop-app-discovery` 按显式路径、当前进程、系统登记和标准目录发现并冻结，恢复只复核原路径。不要用 Web E2E Driver 或旧 `eval_e2e` 替代，因为它们的终态、证据和恢复语义不同。

## WorkBuddy / QwenWork macOS 开发入口

`drivers/workbuddy/execute.mjs` 与 `drivers/qwenwork/driver.mjs` 提供受控单题开发入口；`drivers/workbuddy/batch.mjs` 与 `drivers/qwenwork/batch.mjs` 提供按 manifest 顺序冻结的队列入口。先读取对应 `--help`、只读 probe 与本机配置，再确认没有冲突的活动任务。WorkBuddy 要求 Node ≥22，使用原生 WebSocket/CDP；QwenWork 在其 Driver 目录 `npm ci` 安装锁定的 playwright-core。QwenWork 恢复使用独立的 fresh probe，不能改冻结配置来绕过 journal 校验。两者都在发送前落盘且禁止不确定发送后的重发。

WorkBuddy 已有五题值守闭环；`0.10.7` 修正队列回执、长路径预检和新版资源 finalizer 装配，仍须用新批次验证三路原生重叠、动态补位、恢复与正式 collect，不能只凭 fixture 或本 Skill 为 operational 提升并发支持声明。`0.10.13` 增加 QwenWork 项目预建、SQLite 在线备份和延迟 session_id 恢复；`0.10.14` 在预建项目发送前恢复唯一“新任务”页。用户明确授权时，队列传入 `--skip-clarifications`，才会对已绑定会话中具有唯一“跳过”和“下一题”控件的追问卡片点击“跳过”并记录 journal 事件；其他弹窗不适用此规则。项目预建在发送前为每题落盘 journal，随后仍按 manifest 顺序单槽发送。后台槽位与原生重叠分别留证，真实三路重叠尚需新批次证明。原生字段或停止确认不足时保留 NEEDS_ATTENTION，正式采集接入通用 finalizer 和真实平台 cleanup hook。

`0.10.15` 为 QwenWork 预建后发送加入 probe 完成、项目恢复、Prompt 重填和最终回读的时间事件，仅用于定位 r20 真机原生峰值仍为 2 的原因，不改变一次发送或验收门禁。新增事件不能替代原始 segment 的主 turn 时间。

`0.10.16` 增加 QwenWork Token 暴露的独立安全启动入口和 `--require-token-exposure` 队列门禁。Web 端已验证客户端进程必须在启动时设置 `QODERCN_EXPOSE_TOKEN_USAGE=1`；General 只向新 QwenWork 子进程注入该变量，不修改全局环境。启动器要求无活动原生会话、精确 9250 监听 PID、应用路径与进程启动身份一致，TERM 超时后再次核对身份才允许 KILL。启动后必须核对新监听 PID、进程开关与同一应用/runtime；无法证明时停止。**开关可见不等于 Token 指标已通过**：1.2.0 仍需新会话非零 usage、请求/响应与主 turn 终值对账，以及精确 runtime Profile，旧 masked 批次不得回填。

`0.10.17` 在某题终态观察短暂进入 `NEEDS_ATTENTION` 后，继续把该题已发送且队列绑定的 session/conversation 留在活动会话观察白名单中；只供其它已发送题目的恢复观察，队列仍在 attention 时停止补发，未知会话仍失败关闭。

```bash
node drivers/qwenwork/token-launch.mjs \
  --app-path /Applications/QwenWorkCN.app \
  --session-db "/Users/$USER/Library/Application Support/QwenWorkCN/data/agents.db" \
  --trace-root "/Users/$USER/.qwenworkcn" \
  --endpoint http://127.0.0.1:9250 \
  --output /absolute/new/token-launch.json
```

之后重新生成只读 probe，并在新的 QwenWork 队列中传 `--require-token-exposure`；已有队列只沿原配置恢复，不能中途更改开关。

QwenWork 批量入口示例：

```bash
node drivers/qwenwork/batch.mjs \
  --unit-root /absolute/extracted-unit \
  --queue-id qwenwork-macos-general-five3 \
  --endpoint http://127.0.0.1:9250 \
  --session-db "/Users/$USER/Library/Application Support/QwenWorkCN/data/agents.db" \
  --trace-root "/Users/$USER/.qwenworkcn" \
  --probe /absolute/fresh-probe.json \
  --probe-sha256 <sha256> \
  --preprepare-projects \
  --skip-clarifications \
  --require-token-exposure
```

队列只为当前队列中已绑定的 running session 放行 active-session；发现队列外或缺失原生 ID 时停止并写入 `NEEDS_ATTENTION`。每题 `dispatch_attempt_count` 必须为 1；`native_interval_coverage` 缺失时保持 `null/unavailable`，不把队列槽位或轮询次数当作原生并发和 Token 证据。当前 QwenWork 三题单槽已有正式闭环，默认三路与动态补位仍需在真实桌面时段验收。

QwenWork 1.2.0 可能在 Prompt 发送后先写入 conversation/sub-chat/stream，再延迟补齐 `session_id`。托管队列只在唯一原生 conversation/sub-chat/project/cwd 绑定时暂占后台槽位；完整 session ID 和 Prompt transcript 校验仍是正式终态和 collect 的门禁。队列恢复 probe 的 SHA 不属于冻结 queue digest；初始托管 probe 通过 `--initial-probe` 传入，不改写 task config 的冻结 digest。托管队列在高频 WAL 写入期间用 SQLite 只读源连接的在线备份生成一致快照；普通单题/只读探针仍使用严格的源文件稳定性检查。

## AstronStudio macOS 只读探针

在发送任何 Prompt 前运行：

```bash
node scripts/probe_astronstudio_macos.mjs \
  --output /absolute/new/probe.json \
  --config-output /absolute/new/run-config.json
```

探针只读取 macOS、应用包、精确主进程、GUI 锁定状态、CDP 元数据与可见模型/推理/权限、状态库快照和依赖版本。应用发现校验 Bundle ID、主可执行文件和必需资源；进程/锁屏只用 `ps` 与 `ioreg`，不调用 `System Events` 或目标 App Apple Events。它不启动、退出或重启 AStudio，不点击 UI，不选择工作空间/模型，不读取 composer 内容，也不发送 Prompt。输出路径必须是新文件。

只有探针返回 `PASS` 才会写 `run-config.json`；CDP 缺失或不属于已核对主进程、`DevToolsActivePort` 早于当前进程、状态库快照不完整、模型/推理/权限不能从可见 UI 回读时均返回 `NEEDS_ATTENTION`，不会用最近线程的持久化模型冒充当前配置。完整字段和失败语义见 [AstronStudio macOS 探针契约](references/astronstudio-macos-probe.md)。

## AstronStudio macOS 单题执行

使用已经验证并解压的 execution unit，传入 G2-01 冻结配置：

```bash
node scripts/execute_astronstudio_macos.mjs \
  --unit-root /absolute/extracted-unit \
  --task-id <完整任务ID> \
  --run-config /absolute/frozen-run-config.json
```

已有状态只能加 `--resume` 恢复同一 attempt。执行器在发送前持久化 Prompt digest、路由和会话基线；发送临界点不明确时写 `uncertain / NEEDS_ATTENTION`，不得再次调用发送动作。终态由原生状态库的精确 thread/turn/session/cwd 判断，不以文件变化或 UI 最终文本代替，因此纯回复任务同样可识别。完整调用、输出和当前未实现边界见 [AstronStudio macOS 单题执行契约](references/astronstudio-macos-execution.md)。

## AstronStudio macOS 并发队列

对 execution unit 的全部任务按 manifest 顺序执行：

```bash
node scripts/run_astronstudio_macos_batch.mjs \
  --unit-root /absolute/extracted-unit \
  --run-config /absolute/frozen-run-config.json \
  --queue-id <稳定ID>
```

Worker 中断后使用相同参数并增加 `--resume`。队列冻结 manifest、运行配置、任务顺序、失败策略和单题 Driver 参数的 digest；每题第一次观察到的 `attempt_id` 会登记为唯一选择。恢复必须沿用该 attempt 及其原生会话；General E2E 不把题目 metadata 中的 `timeout_seconds` 转成被测 Harness 的执行 deadline。发现状态文件被替换为其他 attempt 时失败关闭。当前题未得到可信终态时，下一题保持 `PENDING`。

`--timeout-ms`、`--poll-interval-ms` 和 `--identity-timeout-ms` 只控制 CDP/UI 操作、轮询节奏和发送后原生身份绑定，不限制被测 Harness 完成任务的时间。评分规则 Worker 的进程超时是独立的基础设施保护；新的 General 评分编排不设置任务级 deadline。

`--run-slots` 默认 `3`，接受 `1–8`。队列逐题串行执行 UI 发送动作，后台已绑定的原生 Agent 最多并行到冻结槽位；任一任务完成后按 manifest 顺序补位。完整状态、恢复、客户端中断和多 attempt 边界见 [AstronStudio macOS 队列契约](references/astronstudio-macos-queue.md)。

## 责任边界

- 输入：execution 包、Harness 配置和执行策略。
- 输出：原生 thread/turn/session/cwd 绑定、执行终态和初步资源记录。
- Prompt 发送意图和 digest 必须先持久化；发送状态不确定时进入人工关注，不重发。
- 支持 `automated` 与 `human_assisted`，人工语义干预必须单独记录。
- 不读取 scoring 包，不冻结正式候选，不启动裁判或汇总报告。
- execute 输出仍是采集前记录；只有 `collect-general-e2e` 完成轨迹、资源、候选冻结和正式回执后才能进入评分。
