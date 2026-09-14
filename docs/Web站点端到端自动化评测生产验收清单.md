# Web 站点端到端自动化评测生产验收清单

本文是 Web E2E 自动化发布候选的 Git 管理验收台账。Windows 或 macOS 真机验证必须以本文为任务清单，记录同一发布身份下的状态和证据；代码测试、旧批次结果和口头结论不能替代当前真机验收。

## 1. 当前结论

当前发布候选处于 `IN_PROGRESS`：跨平台代码门禁已修复并通过本地聚焦测试，但尚未提交，因此没有可用于正式打包和真机验收的最终 Git revision。AstronStudio、WorkBuddy、QwenWork 的 macOS/Windows 历史证据均保留为参考，但不能直接标记当前候选为 `PASSED`。

### 当前实施进度

| 阶段 | 状态 | 完成条件 | 证据 |
| --- | --- | --- | --- |
| P0 修复跨平台发布门禁 | `PASSED` | macOS 三 Harness 前置准备、Windows 精确进程身份、QwenWork 重启入口、测试入口和路径兼容测试全部通过 | AstronStudio 36/36、WorkBuddy 86/86、QwenWork 40/40、Codex Desktop 48/48、截图接收器 8/8、Web E2E Python 103/103；五个 Skill 校验通过 |
| P1 固化发布 revision | `NOT_STARTED` | 只提交相关改动，记录完整 commit SHA，工作树中无遗漏的相关修改 | Git commit |
| P2 生成正式包 | `NOT_STARTED` | 三 Harness 的自建 40 题、开源 120 题新批次均绑定 P1 revision；五个 Skill ZIP 版本与 SHA 完整 | `report-workspace/web-e2e-automation-packages/` 下新批次 manifest |
| P3 macOS 受影响项回归 | `NOT_STARTED` | 依照第 4 节完成并登记证据 | 本机 worker、return receipt 和报告产物 |
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

| 项目 | 值 |
| --- | --- |
| Git revision | `待 P1 提交后填写，当前基线 a0e2c0d+未提交相关修改` |
| `execute-web-e2e` | `1.11.11` |
| WorkBuddy Driver | `1.8.18` |
| AstronStudio Driver | `1.10.13` |
| QwenWork Driver | `1.10.10` |
| `orchestrate-web-e2e` | `0.2.4` |
| `score-web-e2e` | `4.5.2` |
| `run-web-e2e` | `1.3.4` |
| `report-web-e2e` | `1.0.2` |
| Skill ZIP/content SHA | `待 P2 正式打包后填写` |
| Node.js / Playwright | `真机验收时填写；Driver 锁定 playwright-core 1.55.0` |

### 3.2 真机身份记录

每台验收机器增加一行。不要把同一 Harness 的题目拆到多台机器。

| 记录 ID | OS/版本/架构 | Harness/版本 | 被评模型 | Codex Desktop/版本 | 批次 ID | 操作者 | 时间 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `待填写` |  |  |  |  |  |  |  |  |

## 4. Harness×OS 验收矩阵

缩写：`N`=`NOT_STARTED`，`I`=`IN_PROGRESS`，`B`=`BLOCKED`，`P`=`PASSED`，`S`=`STALE`。矩阵记录当前发布候选状态，不能把下方历史证据直接改写成 `P`。

| ID | 验收项 | macOS AstronStudio | macOS WorkBuddy | macOS QwenWork | Windows AstronStudio | Windows WorkBuddy | Windows QwenWork |
| --- | --- | --- | --- | --- | --- | --- | --- |
| V00 | 发布身份和依赖锁定 | I | I | I | I | I | I |
| V01 | 仓库测试与 Skill 校验 | I | I | I | I | I | I |
| V02 | 只读 probe 与 CDP 进程身份 | S | S | S | S | S | S |
| V03 | 单个 L1、`run_slots=1` | S | S | S | S | S | S |
| V04 | 三个 L1 串行自动进入下一题 | S | S | S | S | S | S |
| V05 | 五个 L1、默认三槽动态补位 | S | S | S | S | S | S |
| V06 | Codex Desktop 项目精确注册 | S | S | S | S | S | S |
| V07 | 默认三路并发评分与动态补位 | N | S | S | S | S | S |
| V08 | submission 原子生成 | S | S | S | S | S | S |
| V09 | return ZIP、外部 receipt 与 SHA | S | S | S | S | S | S |
| V10 | 管理员 import 与报告三件套 | N | S | N | S | S | S |
| V11 | 一个 Prompt 执行→评分→打包 | N | S | N | S | S | S |
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
| `待填写` |  |  |  |  |  |  |  |  |  |

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

## 6. Windows Codex 继续验证 Prompt

代码和正式包推送后，在 Windows Codex 的仓库任务中可直接输入下面 Prompt。它要求控制任务自行发现仓库和最新有效包，不需要先手工填写路径：

```text
请以仓库 docs/Web站点端到端自动化评测生产验收清单.md 为唯一任务清单，继续当前发布候选的 Windows 真机验收。

先执行只读检查：
1. 用 git rev-parse --show-toplevel 和 git rev-parse HEAD 确认仓库及 revision，并确认工作树中没有会污染验收的相关未提交修改。
2. 读取五个 Web E2E Skill 的 skill-metadata.json；在 report-workspace/web-e2e-automation-packages 中查找 source_revision 精确等于当前 HEAD、Harness 为 AstronStudio 的最新正式自建/开源批次。不存在时停止并报告，不使用旧包。
3. 只读发现 AstronStudio 和 Codex Desktop 的真实可执行程序完整路径，使用 Test-Path 验证；检查 9230/9240 端口监听者和完整进程路径。不要按进程名批量结束程序。
4. 对照清单输出当前应执行的下一个 V 项、已有状态、批次和证据目录。若前置身份不一致，标记 BLOCKED 并停止。

从 V02 开始按顺序验证 AstronStudio×Windows：只读 probe、单个 L1、三个 L1 串行、五个 L1 默认三槽动态补位、Codex 项目注册、三路评分、submission、return、import/report、单 Prompt和恢复边界。每完成或失败一个 V 项，都更新清单中的单项验收记录与矩阵状态，写明命令或原 Prompt、批次/任务 ID、绝对证据路径、receipt/SHA、时间和错误；不要把代码测试当作真机通过。

候选 execution/score workspace 在被评 Harness 完成后不可修改；端口冲突只允许修改 private-scoring/runtime-workspace。任何候选哈希漂移、身份不一致、活动任务不唯一或状态不明确都失败关闭。若需要重启承载当前任务的 Codex Desktop，先持久化状态，并使用 run-web-e2e 的 restart_windows_desktop_debug.ps1 计划任务入口；不要让控制任务直接退出或普通 Start-Process 重启自身。

本轮先做到清单中当前指定的下一个 V 项，通过后给出证据摘要和下一项；不要一次执行全部高耗时用例，也不要提交或推送，除非我另行要求。
```

## 7. 发布判定

单个 Harness×OS 只有 V00–V17 全部为 `PASSED`，或未执行项有经过评审的明确非适用说明时，才能在指导手册中标记“生产已验证”。若只通过 V00–V11，可标记“主流程已验证，恢复边界未完成”；若只通过 V00–V05，只能标记“执行阶段已验证”。`BLOCKED`、`STALE` 或缺失证据均不能折算为通过。
