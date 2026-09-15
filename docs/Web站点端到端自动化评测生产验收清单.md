# Web 站点端到端自动化评测生产验收清单

本文是 Web E2E 自动化发布候选的 Git 管理验收台账。Windows 或 macOS 真机验证必须以本文为任务清单，记录同一发布身份下的状态和证据；代码测试、旧批次结果和口头结论不能替代当前真机验收。

## 1. 当前结论

当前发布候选处于 `IN_PROGRESS`：AstronStudio 的 macOS 三题串行、五题默认三槽动态补位、Codex Desktop 项目注册与并发评分、submission、离线回传、管理员幂等导入和报告三件套已经形成 V04–V10 功能证据。评分期间发现 Desktop `create_thread` 返回 `threadId` 前评分任务可能已经写入受管输出，原 `record-thread` 会误判为未归档输出；修复已在 `0486480ca9dda5a5b6269d997caf7fb8af4e8444` 固化为 `orchestrate-web-e2e` 0.2.5，并通过 Codex Desktop Driver 50/50 与准备工作空间 31/31 测试。新的自建 40 题和开源 120 题正式包已绑定该 revision 并通过 22/22 ZIP SHA 与隔离审计。正式 0.2.5 ZIP 的单个 L1 冒烟已完成 AstronStudio 执行，评分控制状态安全停在 `PENDING_PROJECT`；当前承载控制任务的 ChatGPT/Codex Desktop 没有 9230 调试端点，自动前置无法为运行中的单实例补加启动参数，需按调试模式重启后从原状态继续。V11–V17 恢复边界仍待完成；`100045`、`183141` 及更早正式包均已失效。

### 当前实施进度

| 阶段 | 状态 | 完成条件 | 证据 |
| --- | --- | --- | --- |
| P0 修复跨平台发布门禁 | `PASSED` | macOS 三 Harness 前置准备、Windows 精确进程身份、QwenWork 重启入口、测试入口和路径兼容测试全部通过 | 原发布门禁测试均通过；0.2.5 增量回归为 Codex Desktop Driver 50/50、准备工作空间 31/31 |
| P1 固化发布 revision | `PASSED` | 只提交相关改动，记录完整 commit SHA，工作树中无遗漏的相关修改 | `0486480ca9dda5a5b6269d997caf7fb8af4e8444`；执行终态和评分会话竞态修复均已提交，未纳入无关的 `requirements.txt` 和 AstronCode 用量文件 |
| P2 生成正式包 | `PASSED` | 自建 40 题、开源 120 题各生成一个新批次，两个批次均包含三 Harness 并绑定实际打包 revision；五个 Skill ZIP 版本与 SHA 完整 | `web-e2e-20260915-140309-custom40`、`web-e2e-20260915-140309-opensource120`；共 22/22 ZIP SHA 与 6+6 execution/scoring 隔离审计通过 |
| P3 macOS 受影响项回归 | `IN_PROGRESS` | 依照第 4 节完成并登记证据 | AstronStudio V04–V10 功能闭环完成；正式 0.2.5 ZIP 的单 L1 执行已通过，评分项目注册等待 Codex 9230 调试端点，V11–V17 尚未完成 |
| P4 Windows 真机回归 | `NOT_STARTED` | 每个目标 Harness 依照第 4 节完成并登记证据 | Windows worker、return receipt、报告和恢复状态 |
| P5 发布结论 | `NOT_STARTED` | 所有声明为生产可用的 Harness×OS 组合均为 `PASSED`，未通过组合在指导手册中明确降级 | 本清单、指导手册和正式包 manifest 一致 |

## 2. 状态与更新规则

| 状态 | 含义 |
| --- | --- |
| `NOT_STARTED` | 当前发布身份下尚未执行，且没有可继承的同版本证据。 |
| `IN_PROGRESS` | 已开始，尚未满足验收条件；必须记录正在执行的批次或阻塞点。 |
| `BLOCKED` | 已执行但被明确问题阻塞；记录错误、复现入口和所需处理，不得改写为失败题目得分。 |
| `PASSED` | 当前发布身份下已满足验收条件，且证据路径、时间和操作者均已登记。 |
| `STALE` | 旧发布曾通过或有部分证据，但客户端、Driver、Skill 或关键依赖变化后需要重验。 |

以下任一变化发生后，受影响项必须从 `PASSED` 改为 `STALE`：

- 被评测 Harness 或 Codex Desktop 升级到未经验证的版本；
- `execute-web-e2e` 的对应 Driver、`orchestrate-web-e2e`、`score-web-e2e` 或 `run-web-e2e` 内容 SHA 改变；
- 桌面 CDP 前置、项目注册、进程终态、并发调度、候选完整性、submission、回传或报告契约发生变化；
- 操作系统大版本、CPU 架构或安装形态发生变化；
- 已记录证据丢失、哈希不一致，或无法证明来自登记的发布身份。

仅文档变化且五个 Skill 内容 SHA、依赖锁和客户端版本完全不变时，可以由复核人注明“证据沿用”，不机械重跑；不能只凭 Git revision 相近自动沿用。

更新清单时只修改自己负责的 Harness×OS 列及对应验收记录。`PASSED` 记录必须随同代码提交到 Git；本地绝对路径可以作为定位线索，但还要记录可离线核对的 receipt/SHA，避免换机后只剩不可访问路径。

## 3. 发布身份

### 3.1 当前发布候选

下表记录已固化并重新打包的发布身份。真机验收必须使用本节的 revision、Skill content SHA 和新批次；`100045`、`183141` 及更早批次只能作为历史证据。

| 项目 | 值 |
| --- | --- |
| Web E2E 实现 revision | `0486480ca9dda5a5b6269d997caf7fb8af4e8444` |
| 正式包 source revision | `0486480ca9dda5a5b6269d997caf7fb8af4e8444` |
| `execute-web-e2e` | `1.11.13` |
| WorkBuddy Driver | `1.8.19` |
| AstronStudio Driver | `1.10.15` |
| QwenWork Driver | `1.10.10` |
| `orchestrate-web-e2e` | `0.2.5` |
| `score-web-e2e` | `4.5.2` |
| `run-web-e2e` | `1.3.5` |
| `report-web-e2e` | `1.0.2` |
| Skill ZIP/content SHA | 见下表；两个正式批次逐项一致 |
| Node.js / Playwright | `真机验收时填写；Driver 锁定 playwright-core 1.55.0` |

| Skill | 版本 | content SHA-256 | ZIP SHA-256 |
| --- | --- | --- | --- |
| `score-web-e2e` | `4.5.2` | `6fdc8e9a9a8d014b4dab2a4c053d586a08e1f962f03a5071817e251aa2defe0a` | `9121323a68457c4ba28a741b479126d5d6b33d57421feaa4a87532536acf34e1` |
| `report-web-e2e` | `1.0.2` | `a2236d07217989d73befc711e6019932b5e8910bee1938cb9011bf8d7c6d4875` | `ebb7796fba2caa9b2361b540a167001cca4d645a1ebcb02e084392d346092b6b` |
| `orchestrate-web-e2e` | `0.2.5` | `3bf5d6bea6ca31c3b7464a46616f791073c2868e676cb8d9b3647dd97a075c18` | `73a4cfdb6d02dfdcb56be0a8f7a526b1a457988602d81abd3354b031b5ab348d` |
| `execute-web-e2e` | `1.11.13` | `fadcffe629b05f1444af61267ff8721308a07e7df580d8afed3025b9db1b8ae6` | `bdeda81b3a7137f2704179c35fddb89f528b2f239f9d7f267dd3f81dfe5da502` |
| `run-web-e2e` | `1.3.5` | `64845b60286fbd436c67632fd597a47afe56df595627ce089770cba44ffff4f8` | `aa2f94587e9e6813e4885f92df15be82fe64d280d2d0f3c5cff8af5f40c23f9d` |

正式包位于 `report-workspace/web-e2e-automation-packages/`：

- `web-e2e-20260915-140309-custom40`：40 个自建用例，`web-e2e-detailed-v1`；
- `web-e2e-20260915-140309-opensource120`：120 个开源用例，`artifactsbench-web-v1`。

两个批次均包含 `astronstudio`、`workbuddy`、`qwenwork`，各有 11 个 ZIP。2026-09-15 的只读审计逐项重算了 22 个 ZIP 的 SHA-256，结果均与各自 `batch_manifest.json` 一致；6 个 execution ZIP 均不含 Ground Truth、Rubric、checker、`eval/`、`gt/`、`private-scoring/` 或 `task_contract.json`，6 个 scoring ZIP 均不含 `workspace/`、`PROMPT.md`、`execution_record.json` 或 `task_manifest.json`。五个 Skill 的版本、content SHA 和 ZIP SHA 在两个批次中逐项一致。`report_config_ready=false` 表示管理员尚未填写本次实际模型映射，是准备阶段的预期状态。各 execution/scoring ZIP 的独立 SHA 以对应批次 `batch_manifest.json` 为准。

正式包可以在 macOS 或 Windows 的干净检出中生成；本轮先在 macOS 当前仓库生成并审计，Windows 也可按同一代码自行重建用于同机验收。准备脚本只读取仓库中的题目、Workspace 和 Skill 源码，写出的路径统一使用可移植格式。必须满足以下门禁：

- 生成机器的检出必须包含 P1 记录的实现提交，且打包前 Web E2E 相关源码和题目目录没有未提交修改；
- `batch_manifest.json`、`packages/skills-manifest.json` 和各 Harness manifest 的 `source_revision` 必须等于打包时的 `git rev-parse HEAD`；
- 自建、开源两个批次的五个 Skill 名称、版本和 `content_sha256` 必须完全一致；
- ZIP 的 `sha256` 绑定本次实际生成的归档。不同操作系统或不同生成时间产生的 ZIP 归档 SHA 不要求与历史包相等，不能混用旧包的 SHA；
- 生成后以该批次及其外部 receipt 为唯一验证输入，不再用同 revision 的另一个本地重打包结果替换中途产物。

### 3.2 真机身份记录

每台验收机器增加一行。不要把同一 Harness 的题目拆到多台机器。

| 记录 ID | OS/版本/架构 | Harness/版本 | 被评模型 | Codex Desktop/版本 | 批次 ID | 操作者 | 时间 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `mac-release-smoke-astronstudio-20260914` | macOS 26.6.2 / x86_64 | AstronStudio 3.0.0-alpha.19 | GLM-5.2 / High | 未参与评分 | `web-e2e-20260914-161830-custom40` | Codex（本机） | 2026-09-14 | 原 attempt 在 Driver 1.10.13 创建，使用本轮 1.10.14 代码恢复同一 thread 并收口 |
| `mac-release-smoke-workbuddy-20260914` | macOS 26.6.2 / x86_64 | WorkBuddy 5.5.3 | xopglm52 | 未参与评分 | `web-e2e-20260914-161830-custom40` | Codex（本机） | 2026-09-14 | 发送前失败 attempt 已隔离归档，Driver 1.8.19 重试成功 |
| `mac-release-smoke-qwenwork-20260914` | macOS 26.6.2 / x86_64 | QwenWorkCN 1.0.5 | 高级 | 未参与评分 | `web-e2e-20260914-161830-custom40` | Codex（本机） | 2026-09-14 | 单一稳定 session/stream 正常终态；被评 Agent 自检耗时较长 |
| `mac-astron-v04-v09-20260915` | macOS 26.6.2 / x86_64 | AstronStudio 3.0.0-alpha.19 | GLM-5.2 / High | Codex Desktop 26.903.71938 | `web-e2e-20260914-202829-mac-astron-concurrent5-fixed` | Codex（本机） | 2026-09-15 | execute 1.11.13 / Driver 1.10.15 未提交工作树功能证据；批次 revision 不包含修复，不作为正式发布证据 |
| `mac-astron-v04-v10-20260915` | macOS 26.6.2 / x86_64 | AstronStudio 3.0.0-alpha.19 | GLM-5.2 / High | Codex Desktop 26.903.71938 | `web-e2e-20260915-115625-mac-astron-release-concurrent5` | Codex（本机） | 2026-09-15 | execute 1.11.13 / Driver 1.10.15；评分运行时使用与提交 `0486480` 相同内容的 orchestrate 0.2.5 热修复，包内仍为 0.2.4，因此作为功能证据并等待正式 ZIP 冒烟重绑定 |
| `mac-astron-v025-zip-smoke-20260915` | macOS 26.6.2 / x86_64 | AstronStudio 3.0.0-alpha.19 | GLM-5.2 / High | Codex Desktop 26.903.71938 | `web-e2e-20260915-140309-mac-astron-v025-smoke` | Codex（本机） | 2026-09-15 | 五个 Skill 从正式 ZIP 解压且内容 SHA 与 `140309-opensource120` 完全一致；单 L1 execution 已通过，评分等待 9230 调试端点 |

## 4. Harness×OS 验收矩阵

缩写：`N`=`NOT_STARTED`，`I`=`IN_PROGRESS`，`B`=`BLOCKED`，`P`=`PASSED`，`S`=`STALE`。矩阵记录当前发布候选状态，不能把下方历史证据直接改写成 `P`。

| ID | 验收项 | macOS AstronStudio | macOS WorkBuddy | macOS QwenWork | Windows AstronStudio | Windows WorkBuddy | Windows QwenWork |
| --- | --- | --- | --- | --- | --- | --- | --- |
| V00 | 发布身份和依赖锁定 | I | I | I | I | I | I |
| V01 | 仓库测试与 Skill 校验 | P | P | P | P | P | P |
| V02 | 只读 probe 与 CDP 进程身份 | P | P | P | S | S | S |
| V03 | 单个 L1、`run_slots=1` | P | P | P | S | S | S |
| V04 | 三个 L1 串行自动进入下一题 | I | S | S | S | S | S |
| V05 | 五个 L1、默认三槽动态补位 | I | S | S | S | S | S |
| V06 | Codex Desktop 项目精确注册 | I | S | S | S | S | S |
| V07 | 默认三路并发评分与动态补位 | I | S | S | S | S | S |
| V08 | submission 原子生成 | I | S | S | S | S | S |
| V09 | return ZIP、外部 receipt 与 SHA | I | S | S | S | S | S |
| V10 | 管理员 import 与报告三件套 | I | S | N | S | S | S |
| V11 | 一个 Prompt 执行→评分→打包 | I | S | N | S | S | S |
| V12 | 独立控制任务接管磁盘状态 | N | S | N | S | S | S |
| V13 | 被评 Harness 重启恢复/安全失败 | N | S | N | S | S | S |
| V14 | Codex Desktop 重启恢复 | N | S | N | S | S | S |
| V15 | 执行/评分超时与发送前重试 | N | S | N | S | S | S |
| V16 | 评分失败 attempt 隔离和错误回执 | N | S | N | S | S | N |
| V17 | submission 发布中断恢复 | N | S | N | S | S | N |

### 4.1 各项验收条件

| ID | 操作与通过条件 | 必须保存的证据 |
| --- | --- | --- |
| V00 | `git rev-parse HEAD`、五个 Skill metadata/ZIP/content SHA、Harness/Codex/OS/架构全部登记；批次 `source_revision` 与 HEAD 一致 | 发布身份表、`skills-manifest.json`、批次 manifest |
| V01 | 三个执行 Driver、Codex Desktop Driver、截图接收器、相关 Python 测试和全部 Skill `quick_validate.py` 通过 | 命令、退出码、通过/失败数和时间 |
| V02 | 只读 `--probe` 成功；CDP 仅监听 `127.0.0.1`；端口监听者完整路径等于发现的主程序；桌面解锁、状态库和关键 UI 就绪 | probe JSON、主程序路径、端口/PID、客户端版本 |
| V03 | 一个 L1 题目终态明确，模型/权限回读正确，候选非空，`execution_record.json` 与自动化状态一致 | task ID、automation state、execution record、候选 SHA |
| V04 | 三题以 `run_slots=1` 自动切题，无重复项目、重复 Prompt 或跳题 | queue state、三题 conversation/thread ID、终态时间线 |
| V05 | 五题默认 `run_slots=3`；前三题投递后，任一题完成即补入下一题；`ui_slots=1` | queue state、槽位时间线、五题终态、execution receipt |
| V06 | 每个评分目录只注册到一个精确 Codex 项目，项目路径等于 `score/tasks/<task_id>`，没有指向 execution 原件 | registration JSON、Codex 项目/任务 ID |
| V07 | `score_slots=3`，每题独立任务、Browser、端口；任一题终态后动态补位 | scoring state、端口表、thread/cursor、逐题 score |
| V08 | 全题评分通过后只生成一次有效 `submission.json`；候选双副本哈希无漂移 | submission SHA、build state、完整性输出 |
| V09 | 生成 return ZIP 与外部 receipt；两者身份一致、SHA 匹配；ZIP 不含浏览器 profile、密钥和禁止目录 | return receipt、ZIP SHA、内容审计 |
| V10 | 管理员离线导入幂等，报告 JSON/Markdown/Excel 同批次、同 Profile、完整 task IDs | import 状态、三件套路径与审计输出 |
| V11 | 用户只输入题目包和评分包的一个 `$run-web-e2e` Prompt 即闭环，无人工脚本步骤 | 原 Prompt、控制任务 ID、unit state、return receipt |
| V12 | 原控制任务硬中断后，另一个独立 Codex 任务沿用 worker/queue/thread/cursor/attempt，不重发 Prompt | 中断前后 worker identity、cursor、接管审计 |
| V13 | 先持久化再触发被评 Harness 重启；单活动会话安全恢复，无法证明安全或多并发崩溃时失败关闭 | restart 状态、原会话 ID、恢复/NEEDS_ATTENTION 证据 |
| V14 | 使用平台托管重启入口重启 Codex，恢复后沿用原评分任务和状态 | restart status/log、原 thread/cursor、恢复结果 |
| V15 | 安全超时不伪造成功；发送前失败只在证明 Prompt 未被接收后重试一次；评分 deadline 与轮询超时可区分 | timeout/retry 计数、deadline、错误回执 |
| V16 | 失败 attempt 的 `private-scoring` 原子归档，生成结构化错误回执；候选未修改，重试从干净私有输入开始 | attempt archive、error receipt/SHA、候选 SHA 对比 |
| V17 | 在 submission 临时发布边界中断后可幂等收口；已发布文件丢失或漂移时失败关闭 | 中断点、恢复输出、最终 submission SHA |

### 4.2 单项验收记录

每执行一个 V 项追加一行。失败也必须记录，不能只保留最终成功结果。

| 记录 ID | Harness×OS | V 项 | 状态 | Git/Skill 身份 | 批次/任务 ID | 命令或 Prompt | 证据路径及 SHA | 时间/操作者 | 备注或阻塞原因 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `mac-release-tests-20260914` | 三 Harness×macOS；公共静态门禁适用于两端 | V01 | `PASSED` | execute 1.11.12；run 1.3.5；Playwright 1.55.0 | 不适用 | Driver/npm、Python unittest、Skill quick validate | 仓库工作树；39+87+40+48+8+104 项全部通过 | 2026-09-14 / Codex | 系统 Python 缺少 PyYAML，按仓库 `.venv` 执行 Python/Skill 校验 |
| `mac-release-tests-20260915` | 三 Harness×macOS；公共静态门禁适用于两端 | V01 | `PASSED` | `9c83621b9e766f467f376f09df567002e8fd0d6c`；execute 1.11.13；Playwright 1.55.0 | 不适用 | Driver/npm、Python unittest、Skill quick validate | 仓库工作树；43+87+40+48+8+113 项全部通过；六个仓库 Skill 校验通过 | 2026-09-15 / Codex | 系统 Python 首次校验因缺少 PyYAML 退出，按仓库 `.venv` 重跑后通过；未修改系统环境 |
| `mac-release-preflight-20260914` | AstronStudio×macOS | V02 | `PASSED` | run 1.3.5 | `web-e2e-20260914-161830-custom40` | `start_macos_desktop_debug.sh --application astronstudio --check-only` | CDP 9240，PID 2683，完整路径属于 `/Applications/AStudio.app` | 2026-09-14 / Codex | 只读复核通过 |
| `mac-release-preflight-20260914` | WorkBuddy×macOS | V02 | `PASSED` | run 1.3.5 | `web-e2e-20260914-161830-custom40` | `start_macos_desktop_debug.sh --application workbuddy --check-only` | CDP 9229，PID 5326，完整路径属于 `/Applications/WorkBuddy.app` | 2026-09-14 / Codex | Electron 主程序按 `.app/Contents/MacOS/` 完整路径识别 |
| `mac-release-preflight-20260914` | QwenWork×macOS | V02 | `PASSED` | run 1.3.5 | `web-e2e-20260914-161830-custom40` | `start_macos_desktop_debug.sh --application qwenwork --check-only` | CDP 9250，PID 42021，完整路径属于 `/Applications/QwenWorkCN.app` | 2026-09-14 / Codex | probe 同时确认状态库、目录 helper、模型与权限控件 |
| `mac-release-l1-20260914` | AstronStudio×macOS | V03 | `PASSED` | execute 1.11.12；恢复代码 Driver 1.10.14 | `07_Website_Generation_task_002_focus_pomodoro_clock` | 原 attempt `--resume --observe-once` | worker 根 `mac-release-smoke-20260914-161830`；state SHA `dcb10d65...`；候选 SHA `f4626e2f...` | 2026-09-14 / Codex | `SUCCEEDED`；thread `636fd6a7-...`；`PROMPT_SENT=1`；原 state 保留创建时 Driver 1.10.13 |
| `mac-release-l1-20260914` | WorkBuddy×macOS | V03/V15 | `PASSED` | execute 1.11.12；Driver 1.8.19 | `07_Website_Generation_task_002_focus_pomodoro_clock` | `--resume --retry-pre-send-failure` | state SHA `de6a2f8a...`；候选 SHA `d409d4ec...`；旧 attempt `6ffba96a-...` 已归档 | 2026-09-14 / Codex | `SUCCEEDED`；xopglm52；full-access；`PROMPT_SENT=1` |
| `mac-release-l1-20260914` | QwenWork×macOS | V03 | `PASSED` | execute 1.11.12；Driver 1.10.10 | `07_Website_Generation_task_002_focus_pomodoro_clock` | 单题 Driver，未显式指定模型 | state SHA `cdc19b72...`；候选 SHA `787e6a3b...` | 2026-09-14 / Codex | `SUCCEEDED`；高级；full-access；`PROMPT_SENT=1`；约 1629.5 秒 |
| `mac-astron-v04-cleanup-gate-20260914` | AstronStudio×macOS | V04 | `FAILED` | 临时工作树；execute 1.11.12；Driver 1.10.14 | `mac-release-v04-serial3-20260914` | 三个 L1，`run_slots=1` | queue SHA `a62e602d4c4f593244553174ccd67654f7d633a4ffee1c839e26563e1e4189e2` | 2026-09-14 / Codex | 第一题实际 `SUCCEEDED`，但旧 Driver 未写 `terminal_process_cleanup`，公共队列失败关闭且未投递后两题；由此定位自动切题缺陷 |
| `mac-astron-v04-permission-restart-20260914` | AstronStudio×macOS | V04/V13 | `FAILED` | 临时工作树；execute 1.11.13；Driver 1.10.15 | `mac-release-v04-serial3-fixed-20260914` | 三个 L1，`run_slots=1` | queue SHA `c4a269ba6141f3d4d99df9f0d31fb61fde99ea1ed88054a099490848847835c4` | 2026-09-14 / Codex | 前两题成功并自动切题；第三题运行期间用户为 AstronStudio 授予录屏权限并主动重启，原 turn 明确变为 `interrupted`，Driver 以 `INFRA_FAILED` 收口且未重发 Prompt；不是客户端无故崩溃 |
| `mac-astron-v04-rerun-20260914` | AstronStudio×macOS | V04 | `PASSED` | 未提交工作树；execute 1.11.13；Driver 1.10.15 | `mac-release-v04-serial3-rerun-20260914`；ab078、ab097、ab102 | 三个 L1，`run_slots=1` | worker `mac-release-validation-20260914-201445/workers/fixed-serial-rerun/...__astronstudio`；queue SHA `199d989be0e08eb4d5f4df976b7c4965ee023739ad820c18f21e1710c1e357bd`；receipt SHA `91345b7f3d509bc60d2cda52017965be7537ab4f366105a8ad806146911dc7f2` | 2026-09-14 / Codex | 3/3 `SUCCEEDED`；依次投递；每题 `PROMPT_SENT=1`；GLM-5.2 / High；full-access；`integrity.valid=true`；因临时批次 revision 未包含工作树修复，矩阵仍记 `I` |
| `mac-astron-v05-20260914` | AstronStudio×macOS | V05 | `PASSED` | 未提交工作树；execute 1.11.13；Driver 1.10.15 | `mac-release-v05-concurrent5-fixed-20260914`；ab063、ab078、ab095、ab097、ab102 | 五个 L1，默认 `run_slots=3` | worker `mac-release-validation-20260914-201445/workers/fixed-concurrent/...__astronstudio`；queue SHA `bd2de0e47c5709b0b860cd4f76867e860c5c4a3e28114d34cd724413a960475c`；receipt SHA `821e2d3954dbfdfc7b3ea343a357f1207b80ed9cda2c45652090ed804907c119` | 2026-09-14 / Codex | 5/5 `SUCCEEDED`；`ui_slots=1`；ab078 完成补入 ab097，ab063 完成补入 ab102；每题 `PROMPT_SENT=1`；`integrity.valid=true`；总耗时约 7 分 51 秒；矩阵待正式身份重绑定 |
| `mac-astron-v06-20260915` | AstronStudio×macOS | V06 | `PASSED` | 未提交工作树；Codex Desktop 26.903.71938；orchestrate 0.2.4 | `web-e2e-20260914-202829-mac-astron-concurrent5-fixed`；同 V05 五题 | Codex Desktop 可见 UI + macOS Accessibility 注册 | `score/.orchestrate-web-e2e/project-registry.json`；SHA `d1947cfc442feabf7afe1b93ee6fe89589aa7d5da9cdadb5d2fc1f628048f9bc` | 2026-09-15 / Codex | 5/5 项目路径精确指向 `score/tasks/<task_id>`，未使用 renderer bridge；第四题首次“前往文件夹”15 秒超时，确认未注册后以 30 秒安全重试成功，没有重复项目 |
| `mac-astron-v07-20260915` | AstronStudio×macOS | V07 | `PASSED` | 未提交工作树；score 4.5.2；orchestrate 0.2.4 | 同 V06 五题 | 默认 `score_slots=3` | `score/.orchestrate-web-e2e/scoring-automation-state.json`；SHA `15dd328c9dd507ee3bfd78ab520cccacf18b73c4fc85415d0858daee57c9b21e` | 2026-09-15 / Codex | 五题均一次完成、无重试，独占端口 4173–4177；得分依次为 75、64、85、90、52；execution/score 候选 SHA 始终一致，服务与运行时副本已清理 |
| `mac-astron-v08-20260915` | AstronStudio×macOS | V08 | `PASSED` | 未提交工作树；orchestrate 0.2.4 | 同 V06 五题 | submission 原子生成 | `submission.json`；SHA `414b5479a99a2ee6e1e31aa3a9a0dbfa941ed3c75f92e7f7f7ad3131d8b1c1d1` | 2026-09-15 / Codex | `phase=COMPLETED`，submission `attempt_count=1`，5/5 candidate artifact `valid=true`，无 pending 文件 |
| `mac-astron-v09-20260915` | AstronStudio×macOS | V09 | `PASSED` | 未提交工作树；run 1.3.5 | 同 V06 五题 | `run_web_e2e.py export-return` | `workers/fixed-concurrent/offline-return/*__return.zip`；ZIP SHA `eca6f7d19d030776d9f733606f47127a77db3c67e38136cb47e24f66f47bc27c`；外部 receipt SHA `68d2d120bc5781258c0517262a5218cfa043b1278dfd89f6a3e0babede65f54c` | 2026-09-15 / Codex | 16,439,768 字节、225 个文件；ZIP/回执身份与 SHA 一致；包内 submission SHA 与原件一致；无不安全路径、符号链接、禁止目录或敏感文件；导出后五题候选 SHA 仍无漂移 |
| `mac-release-packages-v025-20260915` | 三 Harness×双平台可分发包 | V00 | `PASSED` | `0486480ca9dda5a5b6269d997caf7fb8af4e8444`；orchestrate 0.2.5 | `web-e2e-20260915-140309-custom40`、`web-e2e-20260915-140309-opensource120` | 标准准备脚本；三 Harness；Profile auto | 两批次各 11 个 ZIP，22/22 SHA 通过；6 个 execution 与 6 个 scoring 隔离审计通过；orchestrate content SHA `3bf5d6bea6ca31c3b7464a46616f791073c2868e676cb8d9b3647dd97a075c18` | 2026-09-15 / Codex | 40/120 题、三 Harness、五 Skill 版本和 content SHA 一致，`report_config_ready=false` 为预期状态 |
| `mac-astron-v04-v10-formal-flow-20260915` | AstronStudio×macOS | V04–V10 | `PASSED` | execute 1.11.13；Driver 1.10.15；评分运行时内容等同 orchestrate 0.2.5 | `web-e2e-20260915-115625-mac-astron-release-concurrent5`；ab063、ab078、ab095、ab097、ab102 | 三题串行、五题默认三槽；可见 UI 注册；三路评分；导出、幂等导入、报告 | registry `0aa3a168...`；scoring state `c94dda5a...`；submission `6ad79964...`；return ZIP `c87c3831...`；receipt `687b2b02...`；报告 JSON/MD/XLSX `02ea9dd2...` / `c79d999a...` / `a80dd60...`；batch state `46dc1e5e...` | 2026-09-15 / Codex | 5/5 completed，平均分 77.2，总耗时 988.478 秒；包内 orchestrate 仍为 0.2.4，因此矩阵保持 `I`，正式 0.2.5 ZIP 冒烟通过后再重绑定 |
| `mac-astron-v025-zip-smoke-20260915` | AstronStudio×macOS | V03/V11 | `IN_PROGRESS` | `0486480ca9dda5a5b6269d997caf7fb8af4e8444`；execute 1.11.13；Driver 1.10.15；orchestrate 0.2.5 正式 ZIP | `web-e2e-20260915-140309-mac-astron-v025-smoke`；ab078 | 从版本化 ZIP 解压五 Skill；`run_slots=1`；后续 score/package/collect/report | execution receipt SHA `3f35c8c3...`，`integrity.valid=true`；scoring state SHA `3044af32...`，`phase=PREPARED/PENDING_PROJECT` | 2026-09-15 / Codex | AstronStudio 执行通过且只发送一次 Prompt；Codex 9230 未监听，自动前置无法为运行中单实例补启动参数，状态已持久化，调试模式重启后继续原评分任务 |

### 4.3 本轮 macOS 冒烟边界

三 Harness 的 V03 证明当前前置脚本能够连接正确客户端、完成项目/模型/权限回读、只发送一次 Prompt，并按稳定会话终态冻结候选。AstronStudio 的三题串行、五题默认三槽动态补位，以及同一五题的项目注册、三路评分、submission、离线回传、幂等导入和报告三件套已经完成；评分和导出前后的 execution/score 候选 SHA 均无漂移。评分运行时使用的 0.2.5 热修复已原样提交为 `0486480`，但该五题包内仍附带 0.2.4，所以 V06–V10 在发布矩阵中仍记为 `I`。当前正式 0.2.5 ZIP 的单 L1 冒烟已完成 execution 并安全停在 `PENDING_PROJECT`，待 Codex 9230 恢复后继续 score/package/collect/report；V11 完成后再继续 V12–V17，P3 仍为 `IN_PROGRESS`。

macOS 的 AstronStudio、WorkBuddy 和 QwenWork 当前均记录 `terminal_process_cleanup.supported=false`；这表示本平台没有执行 Windows 等价的候选进程枚举与终止，不表示已证明没有残留进程。QwenWork V03 终态后仍观察到其自启的 headless Chrome/预览服务残留；完整生产验收必须单独补齐 macOS 精确进程收口，不能以执行回执有效替代该平台能力缺口。

用户为 AstronStudio 增加录屏权限并主动重启后，只读 probe 返回 `ready=true`，客户端仍为 3.0.0-alpha.19，模型/推理强度为 GLM-5.2 / High，权限为 full-access，9240 调试端点正常。但 SQLite 状态库仍投影出一个来自已完成 V05 任务的 `open_turn`，而对应 latest turn 已是 `completed`、session 已 ready。该不一致未影响 V06–V09，但当前重启保护会因此失败关闭；在定位投影清理机制并完成受控重启验收前，V13 仍保持 `NOT_STARTED`。

## 5. 历史证据索引

以下只用于定位旧结果和决定哪些项为 `STALE`，不等于当前发布候选通过。

| Harness×OS | 历史范围 | 本地证据 |
| --- | --- | --- |
| WorkBuddy×macOS | 五题执行、评分、回传、报告及恢复边界 | `/Users/gzx/debug-workspace/web-e2e/web-e2e-20260908-123216` |
| AstronStudio×macOS | 单题 execution→score→submission→return；另有串行/并发执行 | `/Users/gzx/debug-workspace/web-e2e/astronstudio-full-flow-validation/workers/web-e2e-20260909-092954__astronstudio` |
| QwenWork×macOS | 三题执行、评分、submission、return | `/Users/gzx/debug-workspace/web-e2e/qwenwork-concurrent3.q563DW/worker/web-e2e-20260909-164755__qwenwork` |
| AstronStudio×Windows | 手册记录过全流程与恢复验收，缺少仓库内统一验收摘要 | 当前发布候选须重新登记 V00–V17 |
| WorkBuddy×Windows | 手册记录过 5.5.3 全流程与恢复验收，缺少仓库内统一验收摘要 | 当前发布候选须重新登记 V00–V17 |
| QwenWork×Windows | 手册记录过 1.0.5.0 全流程和部分恢复边界，V16/V17 缺少直接真机记录 | 当前发布候选须重新登记 V00–V17 |

## 6. Windows Codex 正式打包与继续验证 Prompt

### 6.1 在 Windows 本地生成正式包

代码推送后，在 Windows Codex 的仓库任务中直接输入下面 Prompt。控制任务会在本机生成两个正式批次：自建 40 题和开源 120 题；每个批次同时包含 AstronStudio、WorkBuddy、QwenWork 三个 Harness 的 execution/scoring 包，因此不需要从 macOS 传包。

```text
请使用 $prepare-web-e2e-workspaces 在当前 Windows 仓库中为 Web E2E 当前发布候选生成正式评测包。如果 Windows 无法解析仓库 .agents/skills 下的符号链接，则直接读取并遵循 tools/report/skills/prepare-web-e2e-workspaces/SKILL.md，不要复制或改写 Skill。

先完成发布门禁：
1. 使用 git rev-parse --show-toplevel、git rev-parse HEAD 和 git status --short 确认仓库、完整 revision 和工作树状态；执行 git merge-base --is-ancestor 9c83621b9e766f467f376f09df567002e8fd0d6c HEAD，退出码必须为 0。Web E2E Skill、准备脚本、tasks/07_Website_Generation 和 tasks/extension/07_Website_Generation 存在未提交修改时停止，不得带脏源码打包。
2. 检查可用的 Python 3 和 PyYAML；缺失依赖由控制任务安装到仓库自己的 Python 环境，不得安装到任何题目 workspace。
3. 从 tasks/extension/07_Website_Generation 按文件名排序收集全部 Markdown 用例 ID，必须恰好 40 个；从 tasks/07_Website_Generation 按文件名排序收集全部 Markdown 用例 ID，必须恰好 120 个。数量不符立即停止，不猜测、不跳题。

使用同一个本机时间戳，在 report-workspace/web-e2e-automation-packages 下生成两个全新且不覆盖历史目录的批次：
- web-e2e-<时间戳>-custom40：上述 40 个自建用例；
- web-e2e-<时间戳>-opensource120：上述 120 个开源用例。

两个批次都指定 --harness astronstudio、--harness workbuddy、--harness qwenwork，metric profile 使用 auto；不预填模型和推理强度，不生成 execution_record。应直接调用仓库标准准备脚本，不手工拼 ZIP。

生成后逐项校验：
1. 两个 batch_manifest.json 的 source_revision 都严格等于开始时记录的完整 HEAD，每个批次的 task_ids 分别为 40/120，harnesses 都严格包含 astronstudio、workbuddy、qwenwork。
2. 每个批次均存在三 Harness 各自的 execution.zip 和 scoring.zip、报告配置、packages/skills-manifest.json，以及五个版本化 Skill ZIP。
3. 两个批次中五个 Skill 的名称、版本和 content_sha256 逐项相同；分别使用本次 manifest 记录的 ZIP sha256 验证文件，不与旧 macOS 包的 ZIP SHA 比较。
4. 审计 execution ZIP 不含 Ground Truth、Rubric、checker、eval 或 gt；scoring ZIP 不含候选 workspace、PROMPT.md 或 execution_record.json。
5. 把生成路径、批次 ID、完整 source revision、五个 Skill 版本/content SHA/ZIP SHA、校验结果写入 docs/Web站点端到端自动化评测生产验收清单.md，将 P2 标为 PASSED；本轮不要执行题目、提交或推送。
```

### 6.2 使用 Windows 本地正式包继续真机验证

P2 通过后，在 Windows Codex 的仓库任务中输入下面 Prompt。它要求控制任务自行发现仓库和刚生成的最新有效包，不需要先手工填写路径：

```text
请以仓库 docs/Web站点端到端自动化评测生产验收清单.md 为唯一任务清单，继续当前发布候选的 Windows 真机验收。

先执行只读检查：
1. 用 git rev-parse --show-toplevel 和 git rev-parse HEAD 确认仓库及 revision，读取本清单登记的“Web E2E 实现 revision”，并确认该 revision 是当前 HEAD 的祖先；同时确认该 revision 之后 Web E2E Skill、准备脚本和题目目录没有代码变化或未提交修改。仅本清单等验收文档位于后续提交不改变发布身份；P2 写入本清单的预期证据记录可以保留在工作树中，不视为源码污染。
2. 读取五个 Web E2E Skill 的 skill-metadata.json；在 report-workspace/web-e2e-automation-packages 中查找 source_revision 精确等于 P2 登记的“正式包 source revision”、同时包含 AstronStudio、WorkBuddy、QwenWork 的正式自建/开源批次，并逐项复核 Skill content SHA 与本清单一致。不存在时停止并报告，不使用其他 revision 的旧包或临时重打包。
3. 只读发现 AstronStudio 和 Codex Desktop 的真实可执行程序完整路径，使用 Test-Path 验证；检查 9230/9240 端口监听者和完整进程路径。不要按进程名批量结束程序。
4. 对照清单输出当前应执行的下一个 V 项、已有状态、批次和证据目录。若前置身份不一致，标记 BLOCKED 并停止。

从 V02 开始按顺序验证 AstronStudio×Windows：只读 probe、单个 L1、三个 L1 串行、五个 L1 默认三槽动态补位、Codex 项目注册、三路评分、submission、return、import/report、单 Prompt和恢复边界。每完成或失败一个 V 项，都更新清单中的单项验收记录与矩阵状态，写明命令或原 Prompt、批次/任务 ID、绝对证据路径、receipt/SHA、时间和错误；不要把代码测试当作真机通过。

候选 execution/score workspace 在被评 Harness 完成后不可修改；端口冲突只允许修改 private-scoring/runtime-workspace。任何候选哈希漂移、身份不一致、活动任务不唯一或状态不明确都失败关闭。若需要重启承载当前任务的 Codex Desktop，先持久化状态，并使用 run-web-e2e 的 restart_windows_desktop_debug.ps1 计划任务入口；不要让控制任务直接退出或普通 Start-Process 重启自身。

本轮先做到清单中当前指定的下一个 V 项，通过后给出证据摘要和下一项；不要一次执行全部高耗时用例，也不要提交或推送，除非我另行要求。
```

## 7. 发布判定

单个 Harness×OS 只有 V00–V17 全部为 `PASSED`，或未执行项有经过评审的明确非适用说明时，才能在指导手册中标记“生产已验证”。若只通过 V00–V11，可标记“主流程已验证，恢复边界未完成”；若只通过 V00–V05，只能标记“执行阶段已验证”。`BLOCKED`、`STALE` 或缺失证据均不能折算为通过。
