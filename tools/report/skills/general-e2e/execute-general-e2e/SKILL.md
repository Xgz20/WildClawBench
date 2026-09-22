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

只有 `implementation_status` 为 `operational` 时才发送 Prompt。当前 `0.10.8/operational` 支持 AstronStudio macOS 只读探针、单题执行和持久化并发队列，以及 WorkBuddy macOS 默认三路后台队列；UI Prompt 发送固定单槽，后台 Agent 默认 3 槽、可配置 1–8，并按可信终态动态补位。QwenWork 单题入口会从已完成会话语义导航到唯一“新任务”页，并允许未发送 attempt 精确复用已经落库的同名同 Workspace 项目。应用路径通过 vendored `desktop-app-discovery` 按显式路径、当前进程、系统登记和标准目录发现并冻结，恢复只复核原路径。不要用 Web E2E Driver 或旧 `eval_e2e` 替代，因为它们的终态、证据和恢复语义不同。

## WorkBuddy / QwenWork macOS 开发入口

`drivers/workbuddy/execute.mjs` 与 `drivers/qwenwork/driver.mjs` 提供受控单题开发入口；先读取对应 `--help`、只读 probe 与本机配置，再确认没有冲突的活动任务。WorkBuddy 要求 Node ≥22，使用原生 WebSocket/CDP；QwenWork 在其 Driver 目录 `npm ci` 安装锁定的 playwright-core。QwenWork 恢复使用独立的 fresh probe，不能改冻结配置来绕过 journal 校验。两者都在发送前落盘且禁止不确定发送后的重发。

WorkBuddy 已有五题值守闭环；`0.10.7` 修正队列回执、长路径预检和新版资源 finalizer 装配，仍须用新批次验证三路原生重叠、动态补位、恢复与正式 collect，不能只凭 fixture 或本 Skill 为 operational 提升并发支持声明。`0.10.8` 只扩展 QwenWork 连续任务的新任务路由与未发送项目恢复，QwenWork 仍不继承 AstronStudio/WorkBuddy 的后台并发支持。原生字段或停止确认不足时保留 NEEDS_ATTENTION，正式采集接入通用 finalizer 和真实平台 cleanup hook。

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

`--timeout-ms`、`--poll-interval-ms` 和 `--identity-timeout-ms` 只控制 CDP/UI 操作、轮询节奏和发送后原生身份绑定，不限制被测 Harness 完成任务的时间。评分阶段的 `score_timeout_seconds`/规则 Worker 超时是独立的评分基础设施边界。

`--run-slots` 默认 `3`，接受 `1–8`。队列逐题串行执行 UI 发送动作，后台已绑定的原生 Agent 最多并行到冻结槽位；任一任务完成后按 manifest 顺序补位。完整状态、恢复、客户端中断和多 attempt 边界见 [AstronStudio macOS 队列契约](references/astronstudio-macos-queue.md)。

## 责任边界

- 输入：execution 包、Harness 配置和执行策略。
- 输出：原生 thread/turn/session/cwd 绑定、执行终态和初步资源记录。
- Prompt 发送意图和 digest 必须先持久化；发送状态不确定时进入人工关注，不重发。
- 支持 `automated` 与 `human_assisted`，人工语义干预必须单独记录。
- 不读取 scoring 包，不冻结正式候选，不启动裁判或汇总报告。
- execute 输出仍是采集前记录；只有 `collect-general-e2e` 完成轨迹、资源、候选冻结和正式回执后才能进入评分。
