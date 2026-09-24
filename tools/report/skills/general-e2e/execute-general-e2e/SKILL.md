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

只有 `implementation_status` 为 `operational` 时才发送 Prompt。当前 `0.11.9/operational` 支持 AstronStudio macOS 只读探针、单题执行和持久化并发队列，以及 WorkBuddy/QwenWork macOS 的默认三路后台队列入口；UI Prompt 发送固定单槽，后台 Agent 默认 3 槽、可配置 1–8，并按可信终态动态补位。QwenWork 单题入口会从已完成会话语义导航到唯一“新任务”页，允许未发送 attempt 精确复用已经落库的同名同 Workspace 项目，在终态观察时刷新同一 session 的 Prompt/transcript provenance，并在恢复观察前把 UI 路由精确导航到目标项目任务。应用路径通过 vendored `desktop-app-discovery` 按显式路径、当前进程、系统登记和标准目录发现并冻结，恢复只复核原路径。不要用 Web E2E Driver 或旧 `eval_e2e` 替代，因为它们的终态、证据和恢复语义不同。

## DoubaoWork macOS 开发入口

`0.11.9` 提供 `drivers/doubaowork/driver.mjs` 与只读 `probe.mjs`；其控制与原生消息读取来自共用 `doubaowork` 组件，Web 入口使用同一源码。先在该 Driver 目录 `npm ci`，再运行 probe；General 只接受自身 execution manifest，不使用 Web prepared task 校验。单题入口为 `--unit-root ABS --task-id ID --project-name NAME`，默认保持当前权限并要求模型匹配 manifest；CLI 不选择模型或提升权限。

更新客户端后必须重新 probe，并用与新版本匹配的新包；恢复拒绝版本、manifest、Prompt、场景与目录漂移。2.31.3 的模型控件和 ProseMirror 编辑器按唯一语义/作用域定位；新建任务后输入区仍可能保留旧项目，必须明确选择目标项目并回读。发送前检查 GUI 锁屏状态、完整目录、模型/权限与 Prompt，持久化意图后只发送一次；两个场景共享运行期 UI 锁。

`--resume` 仅恢复观察。只有已确认发送 0 次、未落盘发送意图、完整项目/目录身份仍匹配的发送前失败，才可显式传 `--resume --retry-pre-send-failure`；重试先通过原 project ID 的编辑对话框重新读取完整目录，不能只复用旧 tooltip；原失败 journal 先归档。已发送或不确定发送不适用。原生 Prompt 从绑定 conversation 的 IM message Store 读取，不把 Markdown 渲染文本当成原文。

开发队列入口为 `drivers/doubaowork/batch.mjs --unit-root ABS --queue-id ID --expected-permission LABEL --run-slots N`，N 接受 1–3，默认 1。先按 manifest 顺序预建全部项目并保存零发送 journal，再从每个精确 project 的编辑对话框只读回验完整目录（取消关闭），随后单槽发送并动态补位。恢复使用原冻结发行与 `--resume`；不确定发送不重发，未知活动会话或待交互暂停队列；失败收尾不再向页面发送通用 Escape，未知弹窗须保留，不静默取消。原生并发按绑定助手的 elapsed 区间核算，字段缺失则 null，不能用槽位代替。

发送前读取本机文件系统 NAME_MAX/PATH_MAX，按 UTF-8 字节校验 Workspace、Prompt、控制产物和原生 session 路径预算；拒绝链接、不可写目录及未知限制。发送前重试和恢复重新检查，未初始化的原生活动状态不能当作空闲。

原生 Success、workspace、回复及按 cwd 隔离的本地工具回调交给 General collector；原生 checkpoint 的 task_finish.receiveTimestamp 只在完整身份绑定和时钟校验后用于流程耗时。发送前安装工具 observer，每秒只读留存本 attempt 已观察调用的 uploaded 结果账本，并保留首次观测时间；不刷新客户端 30 分钟 TTL，不改工具行为。完成后恢复回调、订阅和采样定时器。窗口占用和订阅显示另存原件，不能充当累计 Token。未完成场景收口时私有 journal 保留 attention。实际真机范围、独立发行和剩余准入项见仓库统一接入契约。

发送前同时核对前台请求与后台工具交付。并发只放行同队列、同会话、完整 Workspace 和原生请求 ID 一致且前台仍活动的交付；孤立或归属未知的后台交付阻断发送和陈旧锁恢复。原生会话完成但后台交付未结束时保持 `NEEDS_ATTENTION`，不得收口。

`0.11.9` 将每次单题 Worker 的锁 owner 写入私有 journal；只读恢复先持久化清除旧完成观察，再进行连接与目录检查，避免中断留下旧成功可采集。若原点击结果未落盘，只有已绑定的原生成功用户消息与 Prompt/project/workspace 一致，才补记“恢复时观察到接受”；发送边界沿用原 dispatch 时间，未知 click_returned_at 不补造，不再次发送。

单题 Driver 硬中断后，可显式恢复已核验退出的同机 owner：

```bash
node drivers/doubaowork/recover-lock.mjs \
  --unit-root /absolute/extracted-unit \
  --task-id <完整任务ID> \
  --expected-owner-id <原attempt锁中的精确instance_id>
```

该入口要求 journal 中的原 owner 完整匹配、原进程已退出或 PID 已复用、两次 fresh 原生/UI 空闲证明；排他归档相关旧 UI/attempt 锁，核对输入和 journal 字节不变，恢复回执写入原控制目录。发送尝试尚未登记时，还要求当前草稿无用户消息、原生 session 目录集合未增加，且本 attempt 的工具/生命周期观察器没有事件，才恢复这些空观察器；检查失败仍保留 attempt 锁。随后沿原发行和原权限配置执行 `--resume`，只观察原 attempt。活 owner、外机、未知进程身份、其他 owner 的 UI 锁、漂移、已有归档或并发恢复均拒绝。不支持旧版缺少 owner 证明的 journal 或托管队列 owner 恢复，不手删这些锁。发送意图已落盘但接受未知的 attempt 仍不能重发。

原生“待确认”按侧栏状态与稳定 conversation ID 绑定；文件授权还读取已绑定请求的原生 quick_reply block（scene 2、action 1010/1011），覆盖按钮在 CDN iframe 内、主 DOM 没有 approval 标签的情况。未知授权不自动批准，存在待确认时停止新派发并进入 NEEDS_ATTENTION。记录过原生确认或存在原生授权历史的 attempt 不得假定人工操作数为0；当前不提供人工授权后继续自动收口/评分的准入。

## WorkBuddy / QwenWork macOS 开发入口

`drivers/workbuddy/execute.mjs` 与 `drivers/qwenwork/driver.mjs` 提供受控单题开发入口；`drivers/workbuddy/batch.mjs` 与 `drivers/qwenwork/batch.mjs` 提供按 manifest 顺序冻结的队列入口。先读取对应 `--help`、只读 probe 与本机配置，再确认没有冲突的活动任务。WorkBuddy 要求 Node ≥22，使用原生 WebSocket/CDP；QwenWork 在其 Driver 目录 `npm ci` 安装锁定的 playwright-core。QwenWork 恢复使用独立的 fresh probe，不能改冻结配置来绕过 journal 校验。两者都在发送前落盘且禁止不确定发送后的重发。

WorkBuddy 已有五题值守闭环；`0.10.7` 修正队列回执、长路径预检和新版资源 finalizer 装配，仍须用新批次验证三路原生重叠、动态补位、恢复与正式 collect，不能只凭 fixture 或本 Skill 为 operational 提升并发支持声明。`0.10.13` 增加 QwenWork 项目预建、SQLite 在线备份和延迟 session_id 恢复；`0.10.14` 在预建项目发送前恢复唯一“新任务”页。用户明确授权时，队列传入 `--skip-clarifications`，才会对已绑定会话中具有唯一“跳过”和“下一题”控件的追问卡片点击“跳过”并记录 journal 事件；其他弹窗不适用此规则。项目预建在发送前为每题落盘 journal，随后仍按 manifest 顺序单槽发送。后台槽位与原生重叠分别留证；r21 固定五题已有哈希绑定的原生三路重叠和动态补位证据。原生字段或停止确认不足时保留 NEEDS_ATTENTION，正式采集接入通用 finalizer 和真实平台 cleanup hook。

`0.10.15` 为 QwenWork 预建后发送加入 probe 完成、项目恢复、Prompt 重填和最终回读的时间事件，仅用于定位 r20 真机原生峰值仍为 2 的原因，不改变一次发送或验收门禁。新增事件不能替代原始 segment 的主 turn 时间。

`0.10.16` 增加 QwenWork Token 暴露的独立安全启动入口和 `--require-token-exposure` 队列门禁。Web 端已验证客户端进程必须在启动时设置 `QODERCN_EXPOSE_TOKEN_USAGE=1`；General 只向新 QwenWork 子进程注入该变量，不修改全局环境。启动器要求无活动原生会话、精确 9250 监听 PID、应用路径与进程启动身份一致，TERM 超时后再次核对身份才允许 KILL。启动后必须核对新监听 PID、进程开关与同一应用/runtime；无法证明时停止。**开关可见不等于 Token 指标已通过**：collect 0.7.6 已对精确 1.2.0 runtime Profile 完成逐请求/响应与主 turn 对账，r23 新五题的 Input、Output、Total、Cache Read 全部 observed。后续运行仍须逐题校验；旧 masked 批次不得回填，Cache Write、reasoning Token 和 HTTP attempts 仍保持 null。

`0.10.17` 在某题终态观察短暂进入 `NEEDS_ATTENTION` 后，继续把该题已发送且队列绑定的 session/conversation 留在活动会话观察白名单中；只供其它已发送题目的恢复观察，队列仍在 attention 时停止补发，未知会话仍失败关闭。

`0.10.18` 对批量 Worker 硬中断留下的 owner lock 提供**显式** `--resume --recover-stale-owner`。只接受同一冻结队列、fresh 且空闲的只读 probe、同一 host 上已证实退出或 PID 复用的 owner；任何 attempt lock 存在、owner 仍活动、身份/配置漂移都拒绝。旧 owner 原件归档，新 owner 以排他文件取得，恢复后仍逐题读取原 journal 并禁止再次发送已尝试 Prompt。没有这些条件时保持锁，不手删。单题 Driver 锁须先用下述独立工具核验恢复，队列不自动删除它。

`0.10.19` 针对已点击发送、只有 conversation/sub-chat/cwd 临时绑定却始终没有原生 session ID 的情况：如果 60 秒的**基础设施身份落库观察窗**后仍无活动 stream，转入 `NEEDS_ATTENTION` 并保留原 attempt，不重发、不补零；原生确在运行时即使超过该窗口也继续等待。它不是题目执行 deadline，不能据此判定模型能力失败。

`0.10.27` 使用同一 conversation/sub-chat/session/project/cwd 的最新数据库标题核对 UI，兼容客户端自动命名；同名多会话、ID/目录漂移仍拒绝。仅标题渲染滞后时有 2 秒 UI 一致性观察窗，持续不符仍暂停，不能按标题相近或 DOM 顺序猜测目标。

`0.10.26` 对已确认目标会话的原生 stream/UI 状态冲突，重新查询同一身份、Prompt 与待交互状态一次；若只是采集过程中任务刚结束，可以直接取得一致终态，持续冲突仍保留 NEEDS_ATTENTION。重查不重发、不放宽身份或授权门禁，不增加题目执行 deadline。

`0.10.25` 在连接 CDP、建项目或发送前执行路径预检。只读 probe 从已安装 SDK 的纯编码函数确认“ASCII 映射 + 前缀截断 + 哈希后缀”能力，校验其源码 SHA 与 runtime 一致；不按客户端版本白名单放行。预检覆盖原始任务/控制路径、编码后的原生 project 目录及 transcript/segment 路径预算，读取所在文件系统 NAME_MAX/PATH_MAX，拒绝越界、链接、不可写和越限，记录 `PATH_PREFLIGHT_VERIFIED`。恢复使用 fresh probe 重新检查，未知编码能力安全暂停。详见 [QwenWork 路径预检](references/qwenwork-path-preflight.md)。

`0.10.24` 在成功跳过追问后清除旧关注状态、保留 RUNNING 并交给下一轮重新查询原生状态，避免刚跳过就将旧 SQLite 观察判成终态冲突而暂停队列。

`0.10.23` 先持久化临时 conversation/sub-chat/cwd，再等待标题与 UI 就绪，避免短暂缺标题后丢失活动会话白名单。问卷定位进一步限定 `user-question-footer`，区分同名的页头导航箭头和页脚提交按钮，仍只点击唯一“跳过”。

`0.10.22` 在已绑定与临时会话中都检查当前 conversation/sub-chat 的待交互状态；只有同一问卷容器内唯一“跳过/下一题”才执行用户授权的跳过。未知授权、未知弹窗、歧义与未授权追问均记录 `NEEDS_ATTENTION`，不代答、不自动批准。Driver 连接失败等异常退出会让队列安全暂停，保留原 attempt；正常运行返回码 4 与已落盘关注状态返回码 3 单独处理，避免无限轮询旧 RUNNING journal。

`0.10.21` 修复发送临界中断后 `DISPATCHING` 行被遗漏的问题：恢复先观察原 attempt，未绑定或仍不确定时暂停补发；只有全部行真实终态才发布完成回执，旧的“队列完成但子任务未终态”状态明确拒绝。

`0.10.20` 增加单题陈旧锁的独立受控恢复入口。必须确认原 Driver 和队列 owner 均已退出，提供精确 owner ID、原冻结配置及 fresh 空闲 probe；工具排他归档旧锁、校验 journal 字节不变，不发送 Prompt、不修改 journal。活进程、未知身份、已有归档、竞争恢复、链接路径或配置漂移一律拒绝。恢复工具可独立用于旧发行留下的锁；后续 batch 仍必须沿用原发行与原参数，以免冻结源码摘要漂移。

```bash
node drivers/qwenwork/recover-lock.mjs \
  --unit-root /absolute/extracted-unit \
  --config /absolute/original/config.json \
  --expected-owner-id <锁内精确owner_id> \
  --probe /absolute/new/idle-probe.json \
  --probe-sha256 <sha256> \
  --output /absolute/new/lock-recovery.json
```

确认回执为 `RECOVERED` 后，用原队列命令增加 `--resume --recover-stale-owner` 并传入 fresh probe；仅队列 owner 已释放时省略 `--recover-stale-owner`。不确定发送始终只观察原 attempt。恢复失败保留现场，不手删锁。

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

队列只为当前队列中已绑定的 running session 放行 active-session；发现队列外或缺失原生 ID 时停止并写入 `NEEDS_ATTENTION`。每题 `dispatch_attempt_count` 必须为 1；`native_interval_coverage` 缺失时保持 `null/unavailable`，不把队列槽位或轮询次数当作原生并发和 Token 证据。QwenWork r21 已有五题原生三路、动态补位和正式闭环，r23 已有五题核心 Token 和固定 gpt-6-sol/high 报告；故障加固的剩余边界见仓库证据记录，不能据此声明无人值守恢复。

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
