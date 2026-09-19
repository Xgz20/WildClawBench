# Web 站点端到端自动化评测生产验收清单

本文仅供内部开发和发布验收使用，是 Web E2E 自动化发布候选的 Git 管理验收台账。Windows 或 macOS 真机验证必须以本文为任务清单，记录同一发布身份下的状态和证据；代码测试、旧批次结果和口头结论不能替代当前真机验收。

## 1. 当前结论

当前功能准入结论中，AstronStudio×Windows 和 WorkBuddy×Windows 均已完成 V00–V17，状态为 **无人值守高可用已验证**；QwenWork×Windows 已完成当前身份的单 L1 execution→score→submission→return，状态为 **主流程生产可用**。独立的 Windows 资源指标门禁已在 revision `ff5d476b3355960a71326ba4944a63923ce7022c` 上完成 P6–P9，三个 Harness 的四个核心 Token 字段均为 `observed`，状态为 **PASSED**；这只升级资源指标可汇总结论，不改变 QwenWork 的并发与恢复准入层级。

AstronStudio×Windows 功能准入基线 revision 为 `6988b5252bc9140e86dae139fdffbcfc964bcfbf`，验收包锁定 execute 1.11.16 / AstronStudio Driver 1.10.18 / orchestrate 0.2.6 / score 4.5.2 / run 1.3.7 / report 1.0.2。Windows 10 10.0.19042 x64 真机使用 AstronStudio 3.3.1.277、Codex Desktop 26.908.9136（CDP runtime 152.0.7977.83）、GLM-5.2 / High / full-access：正式 ZIP 的单 Prompt 执行→评分→submission→return 已闭环；独立控制任务接管、Harness 重启安全失败、Codex 平台托管重启、发送前唯一重试、执行超时、评分 attempt 隔离和 submission 发布中断恢复均通过。V03–V10 依据完全一致的 execute/score/report/run 内容 SHA、实际 orchestrate 0.2.6 运行身份及正式 ZIP V11 冒烟完成证据重绑定；默认端口 9240 已恢复并重新通过进程路径检查。

WorkBuddy×Windows 功能准入基线 revision 为 `ee70a67b0d53bf700a389b7fbe3f68fde3c3b288`，补充验收包锁定 execute 1.11.21 / WorkBuddy Driver 1.8.24 / orchestrate 0.2.6 / score 4.5.2 / run 1.3.8 / report 1.0.2。同一 Windows 真机使用 WorkBuddy 5.5.6.0、Codex Desktop 26.908.9136（CDP runtime 152.0.7977.83）、xopglm52 / full-access：V03 单题、V05 默认双路五题动态补位、五题评分/回传/报告、正式包单 Prompt、独立控制任务接管、Harness 重启安全失败、Codex 平台托管重启、发送前唯一重试、执行超时、评分 attempt 隔离和 submission 发布中断恢复均通过。

QwenWork×Windows 主流程功能准入基线 revision 为 `24771ce5f86f9bbc9336cf0c0c48effa5f0b2990`，单题包锁定 execute 1.11.21 / QwenWork Driver 1.10.10 / orchestrate 0.2.6 / score 4.5.2 / run 1.3.8 / report 1.0.2。同一 Windows 真机使用 QwenWorkCN 1.0.5.0、Codex Desktop 26.908.9136（CDP runtime 152.0.7977.83）、标准｜Qwen3.8-Flash / full-access：probe、单 L1 执行、Codex 可见 UI 项目注册、内置 Browser 评分、submission 和 return 均通过，评分 88 分，候选双副本哈希无漂移，三阶段状态均为 `COMPLETED`。终态截图曾连续超时，控制端停止旧观察进程后以同一 run-id/attempt 重启 QwenWork 并恢复采集，未重发 Prompt，最终回执仍为 `SUCCEEDED` 且 `manual_interventions=[]`。该结论允许先进入受控正式评测，但首个正式批次必须先跑 3–5 个 L1 canary；当前身份的三题串行、默认三槽、并发评分、管理员 import/report 和 V12–V17 尚未重新绑定，因此不能标记为“并发生产可用”或“无人值守高可用”。

AstronStudio×macOS 已在同一实现 revision 的干净检出上完成单 L1 的 execution→score→submission→return，状态为 **主流程生产可用**：AstronStudio 3.0.0-alpha.19、Codex Desktop 26.908.70816、GLM-5.2 / High / full-access，执行回执 `integrity.valid=true`，评分 81 分，候选双副本哈希无漂移，三阶段状态均为 `COMPLETED`。该结论允许先进入受控正式评测，但首个正式批次必须先跑 3–5 个 L1 canary 再放大；当前 revision 的三题串行、五题默认三槽、三路评分动态补位、管理员 import/report 和 V12–V17 恢复边界尚未重新绑定，因此不能标记为“并发生产可用”或“无人值守高可用”。历史 macOS 本地重打包与 Windows `232007` 正式包的 Skill content SHA 未能重现一致，只能作为各自独立包身份。当前源码候选已改用统一确定性构建器，但跨平台问题只有在提交后由 macOS/Windows 对同一 revision 生成并逐字节对账后才能关闭。QwenWork 和其余 macOS 组合不在当前高可用声明范围。

当前对外分发包已更新为 `web-e2e-20260917-153405-custom40` 和 `web-e2e-20260917-153405-opensource120`，source revision 均为 `b8296d8f4ec7a2bf81b814e4460453c0bf5e4068`。分发包已包含资源指标工作空间；上述各 Harness 准入结论仍按实际真机验收身份解读，不因重新打包自动升级。

2026-09-19 的当前源码候选把 Web 五个阶段 Skill 接入 Web/General 共用的确定性构建器，并将 prepare/score/report/orchestrate/execute/run 版本分别提升到 `4.4.0/4.5.4/1.1.1/0.3.1/1.13.1/1.4.1`。该候选尚未基于提交后的 revision 重新生成正式 40/120 包，也未完成双平台字节对账或新版本真机 smoke，因此不替换上面的正式分发身份和既有准入结论。

### 当前实施进度

| 阶段 | 状态 | 完成条件 | 证据 |
| --- | --- | --- | --- |
| P0 修复跨平台发布门禁 | `PASSED` | macOS 三 Harness 前置准备、Windows 精确进程身份、QwenWork 重启入口、测试入口和路径兼容测试全部通过 | 原发布门禁测试均通过；升级后项目对话框兼容修改的 Codex Desktop Driver 为 52/52、准备工作空间 31/31 |
| P1 固化发布 revision | `PASSED` | 只提交相关改动，记录完整 commit SHA，工作树中无遗漏的相关修改 | 当前正式分发包 `b8296d8f4ec7a2bf81b814e4460453c0bf5e4068`；功能准入基线分别为 AstronStudio `6988b525...`、WorkBuddy `ee70a67...`、QwenWork `24771ce...` |
| P2 生成正式包 | `PASSED` | 自建 40 题、开源 120 题各生成一个新批次，两个批次均包含三 Harness、资源指标记录和五个版本化 Skill ZIP | `web-e2e-20260917-153405-custom40` / `opensource120`，source revision `b8296d8...`；每批 11 个 ZIP，共 22/22 SHA 匹配；6 个 execution ZIP 分别包含 40/120 份 `execution_record.json`，execution/scoring 公私边界审计通过 |
| P3 macOS 受影响项回归 | `IN_PROGRESS` | 依照第 4 节完成并登记证据 | AstronStudio 当前 revision 的单 L1 execution→score→submission→return 已通过，达到“主流程生产可用”；并发重绑定、管理员 import/report 和 V12–V17 尚未完成 |
| P4 Windows 真机回归 | `IN_PROGRESS` | 每个目标 Harness 依照第 4 节完成并登记证据 | AstronStudio×Windows、WorkBuddy×Windows V00–V17 已全部通过；QwenWork×Windows 当前身份的 V00/V02/V03/V06/V08/V09/V11 已通过，达到“主流程生产可用”，更高层级仍待按需迭代 |
| P5 发布结论 | `PASSED` | 平台准入层级、验证状态和待验收项只在本内部清单维护；对外指导手册只提供可执行的使用说明 | 指导手册已移除平台验证状态、revision、验收矩阵和待验证说明；各 Harness 的内部准入结论继续以本清单为准 |
| P10 统一 Skill 构建候选 | `IN_PROGRESS` | Web prepare 使用统一确定性构建器；40/120 批次 Skill set 身份一致；macOS/Windows 同 revision 归档逐字节一致；完成安装检查和最小真机 smoke | Web Python 115/115、General Python 136/136、旧 `eval_e2e` 60/60、General/共享 Node 68/68、Web 四组 Driver Node 242/242、13 个 Skill quick validate、13/13 Skill build/verify 和 layout 均通过；仓库内详细/开源 Profile 双批次的五个 Skill ZIP、build manifest 与 Skill set SHA 完全一致。待提交后生成正式 40/120 包并进行 Windows/macOS 对账，不能提前标为 `PASSED` |

### 1.1 Windows 资源指标验收增补（实现三 Harness 结果可汇总）

本节是当前资源指标实现新增后的独立门禁，不会把旧的执行/评分闭环证据自动升级为“资源指标已验收”。目标是同一个 Windows 批次中，AstronStudio、WorkBuddy、QwenWork 三个 Harness 的每个用例都能在 `execution_record.json` 产生资源字段，评分回传后仍保留这些字段，最终在报告 JSON、领导版 Markdown 和 Excel 的“站点评测指标”中出现。

#### 通过口径

每个 Harness 至少完成 1 个全新 L1 用例，推荐使用同一批次、同一模型和同一推理强度。以下字段必须具有有效状态（`observed` 或明确的 `inferred`）：

| 字段 | 要求 | 说明 |
| --- | --- | --- |
| `execution.duration_seconds` | 必须有值 | Driver 流程壁钟，包含 UI 操作和终态收口。 |
| `execution.agent_duration_seconds` | 必须有值 | Harness 原生智能体耗时或有明确依据的推导值。 |
| `usage.request_count` | 必须有值 | Harness 原生请求/响应事件计数，不宣称是所有 HTTP 重试次数。 |
| `tools.call_count` | 必须有值 | 按原生调用 ID 去重，结果事件不重复计算。 |
| `usage.input_tokens`、`output_tokens`、`total_tokens`、`cache_read_input_tokens` | 三个 Harness 均需 `observed` 才能宣称“Token 指标已打通” | 不完整、隐藏或未经 Profile 验证时为 `null`，并记录覆盖率，不能补零。 |
| `usage.cache_creation_input_tokens`、`reasoning_output_tokens`、`request_attempt_count` | 可为 `null` | 当前三个 Harness 没有可靠的统一原生来源；报告必须显示未知/覆盖不足，而不是推算。 |

报告的完整总量只接受 `observed`、`inferred` 或兼容旧记录的 `legacy`。`partial`、`masked`、`unverified`、`unavailable` 仅进入已知小计和覆盖率，不能进入总量。若要求“3 个 Harness 评测结果都带上 Token 指标”，任一 Harness 的四个核心 Token 字段为 `unverified` 或 `masked`，则资源指标门禁不通过，报告只能作为不完整数据报告发布。

#### P6：源码与 Windows 分发包门禁

- [x] 当前提交包含 `execute-web-e2e` 资源采集器、三个 Driver 的终态调用、统一 `execution_record.json` 写入和独立的 QwenWork runtime Profile；不能继续使用不含资源采集的 execute 1.11.x 旧包。
- [x] 在 Windows 干净目录安装本次最新 Skill 包；当前正式分发包为 execute `1.12.6`、WorkBuddy Driver `1.8.27`、AstronStudio Driver `1.10.21`、QwenWork Driver `1.10.17`，实际值以本批次 `skills-manifest.json` 和包内 Driver metadata 为准。
- [x] Windows Node.js 运行所有 metrics/Driver 测试并记录退出码；SQLite 优先使用 `node:sqlite`，只有运行时不提供时才验证 `py -3`/`python` 的只读回退。不得把依赖安装到题目 `workspace/`。
- [x] 重新计算 Skill content SHA、ZIP SHA 和 `source_revision`，并将它们写入本清单；旧包的 SHA 或旧验收包不能作为本门禁证据。

#### P7：Windows 三 Harness 采集冒烟

每个 Harness 都按相同顺序完成一个全新 L1：只读 probe → `run_slots=1` 单题执行 → 明确终态 → 资源采集 → 评分。执行前确认没有活动任务，且没有设置 `WEB_E2E_RESOURCE_METRICS=off`。每项都要记录批次、完整 task ID、attempt ID、客户端版本、Driver 版本、模型/推理强度、绝对 workspace、原生数据源相对路径和来源 SHA-256。

- [x] **AstronStudio×Windows**：确认 Driver 能从当前用户状态库按桌面 thread/turn 精确映射原生 session，原生日志 cwd 与题目根一致；`input/output/total/cache_read/request_count/call_count/agent_duration_seconds` 均为 `observed` 或 `inferred`。
- [x] **WorkBuddy×Windows**：确认本地 session JSONL 按唯一 conversation/message ID 关联，消息 usage 去重且 cwd 一致；同上核心字段有效，缺失字段只能记录 `partial` 与已知小计。
- [x] **QwenWork×Windows**：使用 execute-web-e2e 1.12.6 或更新版本的普通单题/批量入口，由 Driver 在首题前安全重启客户端并只向新客户端子进程注入 Token 开关。不在控制终端、系统全局环境或题目 Prompt 中手工设置 `QODERCN_EXPOSE_TOKEN_USAGE`：

  ```bat
  call "C:\Skills\execute-web-e2e\scripts\run-qwenwork.cmd" "D:\WebE2E\<batch_id>__qwenwork\execution\tasks\<task_id>"
  ```

  [x] 记录新进程由 Driver 管理开关（`managed_by=qwenwork-driver`），回读 transcript 的 provider、版本和主 turn；按 request ID 去重，响应集合与 `turn.finished` 终值一致，输入已含缓存，且 `cache_read_input_tokens <= input_tokens`。
  [x] 读取 Windows 当前 QwenWork runtime、SDK package 和 transcript 版本，计算 runtime SHA-256；已建立 Windows 精确 Profile 并补齐平台、客户端版本、SDK、transcript 和 runtime SHA 匹配测试。任一身份漂移时 Token 状态保持 `unverified`，不进入完整总量。

#### P8：评分回传透传门禁

- [x] 对上述三个 execution 结果分别复制评分工作空间并完成评分；评分 Agent 不读取或修改 `execution/tasks/` 原件。
- [x] 每个 `score/tasks/<task_id>/private-scoring/task_score.json` 或最终 `submission.json` 保留 `usage.collection`、Token 字段、请求数、工具数、执行耗时和智能体耗时；评分自身的 Token 不得混入被评 Harness 资源。
- [x] 生成三个独立 return ZIP，检查 ZIP 内每个任务都有这些字段，且候选 workspace 哈希未漂移；缺失或 `unverified` 不能静默改成 0。

#### P9：报告闭环门禁

- [x] 使用同一批次的三个 return ZIP 和同一份 `<batch_id>__report-config.yaml` 运行 `report-web-e2e`；不能混入旧批次或不同 Profile。
- [x] 在 `web_e2e_report_data.json` 中逐单元检查：`total_input_tokens`、`total_output_tokens`、`total_cache_read_input_tokens`、`total_tokens`、`total_requests`、`tool_call_count`、`total_duration_seconds`、`total_agent_duration_seconds` 及其 `resource_metrics.*.covered_cases/total_cases/status_counts`。
- [x] 领导版 Markdown 的“总览”表和“资源数据覆盖”表能看到三个 Harness；总量与 JSON 一致，不完整字段显示空值/已知小计和覆盖率。
- [x] Excel 仅保留 `站点评测指标`、`难度对比`、`用例对比明细` 三个 Sheet；“站点评测指标”总览列出输入/输出/缓存读取/缓存写入/智能体耗时等资源列，缓存写入未知时显示空值；保存后检查公式错误和关键值与 JSON/Markdown 一致。
- [x] 报告生成完成后，将报告 JSON、Markdown、Excel、三份 return receipt、三份资源字段抽样和来源 SHA 写回本清单；其中任何一个 Harness 缺少核心 Token 覆盖时，P9 标记 `BLOCKED`，不得写成“三 Harness 指标已完成”。

#### Windows 完成后的升级条件

只有 P6–P9 全部通过，且三个 Harness 的核心 Token 字段均为 `observed`、请求数/工具数/两类耗时均有有效状态，才能将本清单中的“Windows 资源指标”标记为 `PASSED`，并在报告结论中宣称三个 Harness 结果可横向比较。仅有代码测试、旧批次数值、QwenWork 的请求/工具/耗时，或报告能生成但 Token 为 `unverified`，都只能标记 `IN_PROGRESS`/`BLOCKED`。

当前已知状态（2026-09-17 全新 L1 闭环后）：Windows 资源指标门禁为 **PASSED**。AstronStudio、WorkBuddy、QwenWork 三个 Harness 在同一批次的四个核心 Token 字段均为 `observed`，请求数、工具数、执行流程耗时和智能体耗时均有有效状态；评分透传、三份 return、管理员导入及 JSON/Markdown/三 Sheet Excel 报告均已完成。历史 QwenWork 样本继续按事实保持 `masked`，没有回填或改写。

#### 2026-09-17 Windows 指标只读诊断记录

实现 revision：`345597345a58109f2bf501a20970e12b25776581`；execute `1.12.1` / metrics collector `1.1.0`；AstronStudio Driver `1.10.20`、WorkBuddy Driver `1.8.27`、QwenWork Driver `1.10.12`。本次以当前采集器重新读取既有完成会话，旁路输出诊断 JSON，未回填历史 execution/score/submission；以下数值是诊断证据，不能登记为本次全新 L1 通过。

| Harness | 当前采集器结果 | 原因与影响 | 门禁结论 |
| --- | --- | --- | --- |
| AstronStudio 3.3.1.277 | 所有资源值为空，`SOURCE_READ_FAILED` | `drivers/metrics/collect.mjs` 固定搜索 `%USERPROFILE%\.acode\sessions`，本机该目录不存在；状态库已成功按 thread/turn 映射 native session。日志实际位于 `%LOCALAPPDATA%\Programs\AStudio Data\acode-home-overlay\sessions`，cwd 与任务根精确一致。直接调用同一 parser 可取得完整数值，证明故障在日志路径发现。 | P6/P7 `BLOCKED` |
| WorkBuddy 5.5.6.0 | input `1026008`、output `7569`、total `1033577`、cache read `980544`，四项均 `observed`；请求 `25`、工具 `26`；智能体耗时 `463.247` 秒（`inferred`） | 唯一 conversation/message ID 和 cwd 校验通过，usage 覆盖 `25/25`，无采集警告。当前样本未发现采集异常；仍需本次新包 L1。 | 历史样本诊断通过；P7 `NOT_STARTED` |
| QwenWorkCN 1.0.5.0 | 请求 `30`、工具 `30`、智能体耗时 `722.388` 秒均 `observed`；核心 Token 均为空且为 `masked`；暴露 usage 覆盖 `0/30` | 实际 SDK 为 `@ali/qodercn-agent-sdk-next@1.0.28`，transcript `1.1.32`，runtime SHA 与已验 macOS 完全相同。但 `qwen-profile.mjs` 只接受 `platform=darwin`、`client_version=1.0.5`，本机为 `win32`、`1.0.5.0`，匹配返回 `null`。即使新进程暴露非零 Token，现有代码也只能得到 `unverified`。历史样本只能证明 Token 被隐藏，不能反推其启动环境。 | P6/P7 `BLOCKED` |

QwenWork runtime SHA-256：`e86620b7e772d1f536ba15beea8c3059bf6075dffb478aceaa8cad328a879c28`。后续应先扩展严格的 Windows 身份匹配和测试，再按 P7 显式环境开关启动新进程、运行全新 L1，并完成 request/response/turn.finished 对账；仅设置开关不足以解除当前阻断。

三份样本均为 `07_Website_Generation_task_ab078_svg_smartphone_speech_bubbles`：

| Harness | 原批次 / attempt | 原生来源 SHA-256 |
| --- | --- | --- |
| AstronStudio | `windows-as-release-6988b52-v11-20260915-232329` / `6bccf792-afaa-421f-adcd-e6f8cf5637bd` | 实际 rollout `506ae66dff2069a5cade626003462a78262235d76b25e2d77fc6d6a05e4181ae` |
| WorkBuddy | `windows-wb-release-ee70a67-v03-20260916-0616` / `5bd61018-c557-44d5-b092-ec6acb636c64` | session JSONL `bc438ee9a356fd5a7c38518f1e73d370d9ee08143ef3fa6a5a55c3147837e0fd` |
| QwenWork | `windows-qwen-mainflow-24771ce-l1-20260916-113542` / `7d3a45d3-e73e-4644-ae41-c33977fa0f17` | transcript `8b1e5dd98c313c44b3c7d5a7246b8e8a748ee49e10847a7bdfa78bd00242fdf1`；事件段 `7ba371ca5f9880ba925d8627e57510bf382d600ac50ce1c7771a95ea88d7437f` |

证据目录：`D:\WorkProgram\xingchen\astroncode\dev\astroncode-eval\report-workspace\windows-metrics-audit-20260917`。`diagnostic-evidence.json` SHA-256 为 `f0fb988acb8ec2c0a43f4699e5fa29d9c0f78c1ce37a4ba3c2b05b2b3feb0bea`，包含三个绝对任务路径、会话/客户端/模型身份、来源 SHA、当前实现 SHA、完整采集状态，以及核对前后的候选和正式文件 SHA。三个候选均与原终态冻结 SHA 一致，automation、execution record、execution receipt、submission 均未变化。`verify-evidence.mjs` 是只读复现入口，拒绝覆盖已有诊断输出。

验证环境与测试：Windows Node `22.22.2`（`C:\Users\xgzhu6\.workbuddy\binaries\node\versions\22.22.2-3\node.exe`，原生 `node:sqlite`）下 metrics `17/17`、AstronStudio `49/49`、WorkBuddy `92/92`、QwenWork `41/41`，退出码均为 `0`；仓库 `.venv` Python `3.11.9` / PyYAML `6.0.3`、`PYTHONUTF8=1` 下 `tests.test_web_e2e_resource_packaging`、`tests.test_prepare_web_e2e_workspaces`、`tests.test_report_web_e2e`、`tests.test_score_web_e2e` 共 `88/88`，退出码 `0`。测试证明现有测试和透传/覆盖率逻辑通过，未覆盖上述两个 Windows 实机适配缺口。

环境复现注意：PATH 默认 Node `18.16.1` 缺少 `node:sqlite` 且未安装 `sqlite3.exe`，AstronStudio 原测试因此 `48/49`；默认 `py -3` 缺少 PyYAML。Windows 将 `.agents/skills/*` 检出成普通链接文本，报告测试按该入口加载时会 `FileNotFoundError`；本次在工程内 `.agents\windows-metrics-validation`（`feat/windows-metrics-validation`）用可恢复目录联接完成测试。Node 测试使用 PowerShell 枚举 `*.test.mjs` 后传入完整文件列表，避免不同 Node 版本对目录/通配符的解析差异。

上述只读诊断阶段未修改采集实现、未生成或安装新的正式 Skill ZIP、未启动客户端或新发 Prompt，也未执行真实评分/回传/报告。其结论仅用于定位缺口；旧 V00–V17 主流程结论不因此升级为资源指标已验收。

#### 2026-09-17 Windows 指标修复与静态回归

修复候选最初为 execute `1.12.2` / metrics collector `1.1.1`、AstronStudio Driver `1.10.21`、WorkBuddy Driver `1.8.27`、QwenWork Driver `1.10.13`。AstronStudio 现在同时检查旧 `%USERPROFILE%\.acode\sessions` 与由已验证 `state.sqlite` 推导的相邻 `acode-home-overlay\sessions`，多个根重复命中仍以 `AMBIGUOUS_TRACE` 失败关闭。QwenWork 最初增加 `platform=win32`、`client_version=1.0.5.0` 的精确 Profile；真机 probe 随后发现客户端已升级到 `1.0.6.0`，其 SDK `1.0.28` 与 runtime SHA `e86620b7e772d1f536ba15beea8c3059bf6075dffb478aceaa8cad328a879c28` 均未变化，因此当前候选继续升级为 execute `1.12.3` / collector `1.1.2` / QwenWork Driver `1.10.14`，并为 1.0.6.0 新增独立精确 Profile ID。SDK、transcript、平台、客户端版本和 runtime SHA 任一漂移仍不放行归一化。

Windows Node `22.22.2` 下 metrics `19/19`、AstronStudio `49/49`、WorkBuddy `92/92`、QwenWork `41/41` 全部通过；仓库 `.venv` Python `3.11.9` 下资源打包、准备、评分和报告四组测试 `88/88` 通过。报告测试入口改为直接加载受版本控制的 `tools/report/skills/web-e2e/report-web-e2e`，不再依赖 Windows 是否把 `.agents/skills` 检出为真实符号链接。

修复后的采集器只读重放同一历史样本：AstronStudio 得到 input `4389411`、output `32133`、total `4421544`、cache read `4155584`、请求 `57`、工具 `76`、智能体耗时 `750.035` 秒，全部无告警；旁路文件 `astronstudio-postfix-readonly-metrics.json` SHA-256 为 `356b49bc3d53772c25f744a22998b75e17dde41ac404663e0ae0850b52cb88e4`。QwenWork 精确命中 `qwenwork-1.0.5-qoder-cache-inclusive-v1`，但旧会话仍为 `QWEN_TOKEN_USAGE_MASKED`；旁路文件 `qwenwork-postfix-readonly-metrics.json` SHA-256 为 `717a452a880f985ea19515981fec77806740b039d4198aac4ef6ea143a89b350`。这证明两个实现缺口已修复，但不能替代 P7 的全新非零 Token L1。

#### 2026-09-17 Windows 三 Harness 资源指标 P6–P9 真机闭环

验收批次为 `windows-metrics-ff5d476-l1-20260917-114821`，source revision 为 `ff5d476b3355960a71326ba4944a63923ce7022c`，Profile 为 `artifactsbench-web-v1`，三个 Harness 均执行同一全新 L1 `07_Website_Generation_task_ab078_svg_smartphone_speech_bubbles`。管理员批次根为 `D:\WorkProgram\xingchen\astroncode\dev\astroncode-eval\report-workspace\web-e2e-automation-packages\windows-metrics-ff5d476-l1-20260917-114821`，短路径 worker 根为 `D:\debug-workspace\web-e2e\m\ff5d476-114821`，其中 `as`、`wb`、`qw` 分别对应三个 Harness；每题候选路径长度为 135，满足 WorkBuddy 的 Windows 短路径门禁。较早的 `windows-metrics-47ef174-l1-20260917-113743` 仅为 `prepared`、0 executed，保留审计但未混入本次结果。

P6 分发身份如下；三个 worker 的安装检查均返回 `all_current=true`：

| Skill | 版本 | content SHA-256 | ZIP SHA-256 |
| --- | --- | --- | --- |
| score-web-e2e | `4.5.2` | `9e870f17452d00d11a2d0f339b4e12d477bceb623206af34cc6f76bb64625e93` | `4ce81bbc5126be94254c38ec4c7fed58c7a3a02efa13f4d53b0d3e1843c66425` |
| report-web-e2e | `1.1.0` | `75ca2afe27129000c3613129868067dcb459c4e1a206d1067f6c6ac22d7fd697` | `810e5f5e807ef5992dd3340b1d32c9aac47733eaaa1f69810a3c8c7490f4313f` |
| orchestrate-web-e2e | `0.2.6` | `7b2c9fca36a158dc5e0beb98642aef1684bce23e76457b92ea8ff527a5db27a4` | `73d578ab6f21d03d10d0d5bd0ca235422809f5cda730707f69eafc11b73fc211` |
| execute-web-e2e | `1.12.3` | `98b3a8531d507d6a8bfe2e69e1093ad529afc39ca131efecc3e5c9e8b454d8fb` | `3203d89d6b16504aa491fa4cd9bd02606731ca93097f4348dd3ffeb319599fef` |
| run-web-e2e | `1.3.9` | `ce013596ff6b15b25ee65dde7e7889f34016c1aa84ee52a3b9bca1c46c1e599f` | `671de274921d47fbc526c7392be3c83fe4fe3f1bf2b9981ab26a29c82ea44953` |

Driver 版本为 AstronStudio `1.10.21`、WorkBuddy `1.8.27`、QwenWork `1.10.14`，metrics collector 为 `1.1.2`。Windows Node `22.22.2` 下 metrics `19/19`、AstronStudio `49/49`、WorkBuddy `92/92`、QwenWork `41/41` 均以退出码 0 通过；仓库 `.venv` Python 下资源打包、准备、评分和报告测试 `88/88` 通过。测试、Skill 与 Driver 依赖均未写入候选 `workspace/`。

P7 的三个 execution receipt 均为 `integrity.valid=true`、`manual_interventions=[]`，候选哈希与终态冻结值一致，采集告警均为空：

| Harness / 客户端 / 模型 | attempt / 原生会话 | input / output / total / cache read | 请求 / 工具 / 流程耗时 / 智能体耗时 | 原生来源 SHA-256 | 状态结论 |
| --- | --- | --- | --- | --- | --- |
| AstronStudio `3.3.1.277` / GLM-5.2 High | `8975e60a-3c64-43bc-a8ea-e8b186c625ac` / rollout session `01a0ad85-2457-7810-a746-ac07ab90f2bc` | `481070 / 8293 / 489363 / 465088` | `14 / 13 / 310.407s / 204.741s` | `44c85d42ebad61481fe8905b74f332d66a208851416e8ed01d923df24db05b80` | 四个核心 Token、工具数、两类耗时 `observed`；请求数 `inferred` |
| WorkBuddy `5.5.6.0` / xopglm52 | `f797cd05-ba3c-490e-aa0d-e3235439095d` / conversation `bb4b666f-2ef7-4d3c-8d25-fdd22649f2dd` | `556077 / 6671 / 562748 / 512128` | `14 / 14 / 375.931s / 312.410s` | `30f99521a0145eec6e7c55ca79cd1e0de4daa93e32301a5c4c1555284fa2ab29` | 四个核心 Token、请求数、工具数、流程耗时 `observed`，响应覆盖 `14/14`；智能体耗时 `inferred` |
| QwenWork `1.0.6.0` / 标准｜Qwen3.8-Flash | `63020ead-4aab-40e5-a38f-b2bfb89f8a49` / session `50db1cd4-40e4-4198-a60e-c5cd03dc6a71` / turn `686cb8d5-23e2-4ef0-8fe2-ccbc4372ed43` | `562753 / 11498 / 574251 / 513280` | `12 / 15 / 414.868s / 289.372s` | transcript `f4e1f94cd2765d6875b94a45f33e12d7abca97340ad42fb9223d0c8b168fa374`；segment `1399ae4e8d7c691054100f78022aa5b31fc1c6643b30b47e422a641e67e7ab62` | 四个核心 Token、请求数、工具数、两类耗时全部 `observed`，响应覆盖 `12/12` |

QwenWork 执行前显式设置 `QODERCN_EXPOSE_TOKEN_USAGE=1`，并通过 `--restart-app-first` 启动新客户端 PID `43640`。运行身份为 `@ali/qodercn-agent-sdk-next@1.0.28`、transcript `1.1.32`、runtime SHA `e86620b7e772d1f536ba15beea8c3059bf6075dffb478aceaa8cad328a879c28`，精确命中 `qwenwork-1.0.6-qoder-cache-inclusive-v1`。主 turn 的 `model.request.started` 与 `model.response.completed` 均为 12 个唯一 ID，集合完全一致且 provider 全部为 `qoder`；非零 usage 与 `cache_read <= input` 异常数均为 0，唯一一条 `turn.finished` 的终值与逐响应总和一致。另有一个后台 request，已明确登记为 `background-turn` 并排除于主任务统计。

P8 的评分目录均由冻结 execution 复制生成，评分站点通过受管静态服务实际渲染并留存截图；停止服务、清理运行时副本和截图接收器可信终态检查通过。三个 `task_score.json` 的总分分别为 AstronStudio 76、WorkBuddy 63、QwenWork 78，执行资源字段从对应 `execution_record.json` 完整透传：

| Harness | 候选 SHA-256 | execution record SHA-256 | task score SHA-256 | submission SHA-256 | return ZIP / 外部 receipt SHA-256 |
| --- | --- | --- | --- | --- | --- |
| AstronStudio | `45021050b3cae098bce96eb25e1c13ba1dfe3e639806229a27ac735dfd2e87c8` | `1e0874d8a6b5ddeebd9d4ba380b6dd012e1d60fdecb9071611d9f7dd8d76017c` | `259c3490e3a1ff1ec8161e174db2d04643fc6ffba8de1d38c778de7684d31ea0` | `5eff7fef288c36981f58f5b1fa892f832485c05201fc9933e9a371783a889d76` | `8388d78b4f772f32efd76f74fd6ee16104dfe992f2303e0ca6f0bd7e06fa50a7` / `98321d6f7edb67507dcc234bbeb47e61ddda2ae03f512a22e0dabfed3b2f254c` |
| WorkBuddy | `60532170abf2af47f22f5519cfe3727d098f428fefbd77771448699df0199d02` | `df5565b454c42317722ca59008b6e5f1216036f6e9ba728b0e3065fbefa860e8` | `8a38367bfddeb95d4003bb8b136fba15200a4a208a7aeca4f7d7218db988b05a` | `dbb6c224fb1098352b017d0fb97edcefa40c7ec3c57cbe7654377b3ad729e25a` | `4016547823153c199665996ad1d4e1f4bfc0023beb668474900c4f99d9f8c6ae` / `e79aab7647f4ffa1aac663c893b2921c563492c4f4b3277c5c041ac9a8ec4636` |
| QwenWork | `06b348e2fbb2e695104fdd6ab158f6fbf417efe00266bda6a48c2e6dddf7d35f` | `0cf8fd1286d19f9bd58c254a38a717e056d311d2b6597375737986b050da1556` | `8a193584a4538cbb5514113a4050850a393d46f624dc4b5c6554b8437d398355` | `c248396e24f008c969735a37ed5b63cfc80ec11f9d1c3566645e3396080fea85` | `cef1ff8fabf2fc0f93b59325a0754d50f42b7202ebb6b2b5261be6e4e8437fe4` / `85af4490886520cf2620ce96c32570a16dea7e0c5b44cad219c036848536d1b3` |

三份 return 均已原子导入管理员批次的 `returns/<harness>/`，collect 状态为 `COMPLETED`。P9 使用同一份 `windows-metrics-ff5d476-l1-20260917-114821__report-config.yaml` 汇总，最终产物位于管理员批次的 `report-output`：

| 产物 | SHA-256 |
| --- | --- |
| `web_e2e_report_data.json` | `b87a77adce8261fec73010c704d137a7cc94e9a29b563819a03db7c910faeb8b` |
| `Web站点端到端评测领导版.md` | `c61a6587dff5c35cf99cba0fac4db5ce787ff427623f6d6d993702fb10438e51` |
| `Web站点端到端评测报告.xlsx` | `f736e9ef575ff01ae825b532d21d56107cf48faeb326eb7c71e365e17dde70b4` |

JSON 和 Markdown 中三个 Harness 的资源总量、覆盖率和来源状态与单题产物一致；缓存写入、QwenWork 推理 Token 和 HTTP 尝试次数继续显示未知，没有补零。Excel 只包含 `站点评测指标`、`难度对比`、`用例对比明细`，公式错误扫描为 0，关键值与 JSON/Markdown 一致。Windows 上 `artifact-tool` 的最小 `workbook.render()` 以退出码 `-1073741819` 复现原生崩溃，因此按 Skill 允许的 `--skip-preview true` 生成正式 XLSX，再用独立只读渲染器逐表检查三个 Sheet，未把跳过内置预览本身记为视觉通过。最终三个 worker 的 `execute/score/package` 均为 `COMPLETED`，管理员批次的 `prepare/collect/report` 均为 `COMPLETED`；据此 P6–P9 和 Windows 资源指标门禁均为 `PASSED`。

#### 2026-09-17 QwenWork Token 自动注入实机验收

在上述 `ff5d476...` 实机闭环中，控制任务显式设置 `QODERCN_EXPOSE_TOKEN_USAGE=1` 并使用 `--restart-app-first`；execute-web-e2e 1.12.3 / QwenWork Driver 1.10.14 本身只负责透传已有环境变量，尚未做到普通 Skill 调用自动开启。自动注入最初在 execute-web-e2e 1.12.4 / QwenWork Driver 1.10.15 中实现，本轮最终发布身份为 execute 1.12.6 / Driver 1.10.17 / collector 1.1.3，并同时覆盖原生目录选择异步回读和 Windows Node 18 长日志路径：全新单题默认安全重启，全新批次默认只在第一题前安全重启，Driver 向新客户端子进程同时注入 CDP 参数和 Token 开关，不修改控制 Harness 的全局环境；发现活动任务时失败关闭。

该改动消除了用户或 Prompt 手工设置环境变量的要求，但属于 Driver 核心启动行为变化。`ff5d476...` 的 P6–P9 证据继续有效，不直接改写为新发布身份；本节只重验自动注入、Windows Node 18 采集和单 L1 执行，不替代 P8/P9 评分、回传与报告，也不把单题结果外推为并发或无人值守高可用。

真实迭代现场均保留，未把失败样本伪装成通过：

- `qwenwork-token-auto-629819d-l1-20260917-141901` 使用 execute `1.12.4` / Driver `1.10.15`，自动重启后的状态已记录 `managed_by=qwenwork-driver`，但原生目录选择后立即读取到旧占位文字“选择文件夹”，在发送 Prompt 前以 `INFRA_FAILED` 收口；候选 SHA 未变化、`PROMPT_SENT=0`。修复为有界等待异步标签更新。
- `qwenwork-token-auto-d6ede80-l1-20260917-143405` 使用 execute `1.12.5` / Driver `1.10.16`，执行 `SUCCEEDED` 且 receipt 完整，但 Windows Node `18.16.1` 对长度 263 的真实 segment 路径执行 `realpath(file)` 返回 `ENOENT`，正式 execution record 保留 `SOURCE_READ_FAILED`，不作为指标通过证据。修复后的只读重放得到四项核心 Token `observed`，但未回填旧回执。

最终正式批次为 `qwenwork-token-auto-c257fbd-l1-20260917-145043`，source revision 为 `c257fbdd016b450fc62f06dc9f7b4f2b0a78a8fd`，执行包位于 `D:\WorkProgram\xingchen\astroncode\dev\astroncode-eval\report-workspace\web-e2e-automation-packages\qwenwork-token-auto-c257fbd-l1-20260917-145043`，独立 worker 根为 `D:\debug-workspace\web-e2e\m\c257fbd-145043\qw`。execute-web-e2e `1.12.6` 的 content SHA-256 为 `a6c14d71cebb6bd00e8aba1c08b307977ba7a0438402dd910ff08454d701cb6d`，ZIP SHA-256 为 `934313c38bed3c6acb8c60405d64ed36766d12e4fbd521cc65a4a24ecd206e38`；安装检查返回 `all_current=true`。只读 probe 确认 QwenWorkCN `1.0.6.0`、Driver `1.10.17`、模型 `标准｜Qwen3.8-Flash`、`full-access`、CDP/SQLite/UI 均就绪。

最终 L1 使用 `run_slots=1`，队列为 `COMPLETED`，execution receipt 为 `integrity.valid=true`、`manual_interventions=[]`，automation 为 `SUCCEEDED`，状态与队列中 `PROMPT_SENT` / `TASK_DISPATCHED` 均只有一次。新客户端 PID `1236` 的 `client.launch.environment_preparation.token_usage_exposure` 精确记录 `managed_by=qwenwork-driver`、`value=1`、`scope=client-process`；控制 Harness 全局环境未被修改。候选从初始 SHA `6dd93633cb8abae0fdec0cd768bc942d5cf35a22a793aad1cbac2e7832f38dd7` 冻结为 `0188519e61d525b0c8395177dc2d88064ac9c190dd568dc110ce315019ff7ad5`，receipt 复核完全一致；终态进程清理成功并观察到 `45535ms` 静默窗。

collector `1.1.3` 在正式终态原生写入 input `1531951`、output `23861`、total `1555812`、cache read `1449600`、请求 `26`、工具 `25`，四项核心 Token、请求数、工具数和两类耗时均为 `observed`，警告为空。运行身份为 `@ali/qodercn-agent-sdk-next@1.0.28`、transcript `1.1.32`、runtime SHA `e86620b7e772d1f536ba15beea8c3059bf6075dffb478aceaa8cad328a879c28`，精确命中 `qwenwork-1.0.6-qoder-cache-inclusive-v1`。主 turn `6e47d1ef-1c2b-4f05-b037-e8cd107e7646` 的 `model.request.started` 与 `model.response.completed` 均为 26 个唯一 ID，集合一致、provider 全部为 `qoder`、零 usage 响应数与 `cache_read > input` 异常数均为 0；唯一 `turn.finished` 与逐响应总和一致。另有 4 个后台请求和 3 个后台工具调用，已作为 `background-turn` 排除于主任务统计。

正式证据 SHA-256：execution receipt `a90160dcde98b7bdcf51d2984aeb446a82bca957205d0cbca930af3a0ebeecaa`，execution record `b2f749c70be0fb4a2abf7b63c6797fba0c04e1905b3cc99aa15b179008d4636e`，automation state `407d3aee3cee1ec49558695bb3cd635c806ec3569acecf830fc25bfb189cbd93`，queue state `50d6947e7222a94373b43f2b2d62cb9d56a93fb7a8b766f8079fff1ee375c165`。据此，execute `1.12.6` / Driver `1.10.17` / collector `1.1.3` 在 Windows QwenWorkCN `1.0.6.0` 下的“自动注入 + 单 L1 资源指标”门禁为 `PASSED`；用户不需要手工开启 Token 开关。新正式包按本清单 6.2 先执行 3–5 个 L1、并发 1 的 QwenWork canary，之后再按受影响范围恢复并发。

## 2. 状态与更新规则

| 状态 | 含义 |
| --- | --- |
| `NOT_STARTED` | 当前发布身份下尚未执行，且没有可继承的同版本证据。 |
| `IN_PROGRESS` | 已开始，尚未满足验收条件；必须记录正在执行的批次或阻塞点。 |
| `BLOCKED` | 已执行但被明确问题阻塞；记录错误、复现入口和所需处理，不得改写为失败题目得分。 |
| `PASSED` | 当前发布身份下已满足验收条件，且证据路径、时间和操作者均已登记。 |
| `STALE` | 旧发布曾通过或有部分证据，但客户端、Driver、Skill 或关键依赖变化后需要重验。 |

验收状态记录单项是否通过；对外可用结论按以下三级准入，避免为了补齐低频故障注入而长期阻塞正常生产：

| 准入层级 | 最低证据 | 允许范围 | 尚未覆盖时的约束 |
| --- | --- | --- | --- |
| 主流程生产可用 | 当前实现 revision 和客户端身份下，至少一个 L1 完成 probe、执行、Codex Browser 评分、submission 与 return，候选哈希无漂移 | 可开始受控正式评测 | 首个正式批次先跑 3–5 个 L1 canary；并发和异常恢复失败时允许人工介入 |
| 并发生产可用 | 当前身份下完成三题串行自动切题、五题默认执行并发与动态补位、默认三路评分、submission、return、import/report | 可按默认并发运行常规批次 | 客户端崩溃、控制任务中断等恢复场景仍需值守 |
| 无人值守高可用 | 并发生产可用，并完成 V12–V17 的接管、客户端重启、超时、重试、失败 attempt 隔离和 submission 恢复 | 可按已验证边界无人值守运行 | 多活动会话崩溃等契约明确要求失败关闭的场景仍转人工 |

同一组合可以在矩阵仍有 `IN_PROGRESS` 项时达到较低准入层级；文档必须同时写明已达到的层级和未覆盖项，不能把“主流程生产可用”简写为“完全生产已验证”。

以下任一变化发生后，受影响项必须从 `PASSED` 改为 `STALE`：

- 被评测 Harness 或 Codex Desktop 升级到未经验证的版本；
- `execute-web-e2e` 的对应 Driver、`orchestrate-web-e2e`、`score-web-e2e` 或 `run-web-e2e` 内容 SHA 改变；
- 桌面 CDP 前置、项目注册、进程终态、并发调度、候选完整性、submission、回传或报告契约发生变化；
- 操作系统大版本、CPU 架构或安装形态发生变化；
- 已记录证据丢失、哈希不一致，或无法证明来自登记的发布身份。

仅文档变化且五个 Skill 内容 SHA、依赖锁和客户端版本完全不变时，可以由复核人注明“证据沿用”，不机械重跑；不能只凭 Git revision 相近自动沿用。

更新清单时只修改自己负责的 Harness×OS 列及对应验收记录。`PASSED` 记录必须随同代码提交到 Git；本地绝对路径可以作为定位线索，但还要记录可离线核对的 receipt/SHA，避免换机后只剩不可访问路径。

## 3. 发布身份

### 3.1 当前正式分发包

下表是当前用于新评测的分发身份。真机执行必须使用本节登记的批次、Skill content SHA 和 ZIP SHA；`20260917-153405` 之前的批次仅作为历史证据或故障对照。

| 项目 | 值 |
| --- | --- |
| 正式分发包实现/source revision | `b8296d8f4ec7a2bf81b814e4460453c0bf5e4068` |
| 自建评测批次 | `web-e2e-20260917-153405-custom40`，40 题，`web-e2e-detailed-v1` |
| 开源评测批次 | `web-e2e-20260917-153405-opensource120`，120 题，`artifactsbench-web-v1` |
| 被评 Harness | `astronstudio`、`workbuddy`、`qwenwork` |
| `execute-web-e2e` | `1.12.6` |
| AstronStudio / WorkBuddy / QwenWork Driver | `1.10.21` / `1.8.27` / `1.10.17` |
| `orchestrate-web-e2e` | `0.2.6` |
| `score-web-e2e` | `4.5.2` |
| `run-web-e2e` | `1.3.9` |
| `report-web-e2e` | `1.1.0` |
| 执行记录 | `execution_record_included=true`；每个 execution ZIP 包含全部用例的 `execution_record.json` |
| 报告配置 | `configuration_status=requires_model_mapping`；生成正式报告前必须填写三个 Harness 的 `model_id`，`model_display_name` 和 `reasoning_effort` 按实际评测配置填写 |

| Skill | 版本 | content SHA-256 | ZIP SHA-256 |
| --- | --- | --- | --- |
| `score-web-e2e` | `4.5.2` | `6fdc8e9a9a8d014b4dab2a4c053d586a08e1f962f03a5071817e251aa2defe0a` | `34afc5c963f21ca9815d02d0b89a8d0bb80cec9ec263e53c6fb50eb08f84cbf0` |
| `report-web-e2e` | `1.1.0` | `051c7e6f89296d154a186e7776b53858b0fa11a1ed62f2578ca022a939460442` | `18ef1741d14bb650556ff97811b718640d2fdb9e11daf5423e197d84a71db734` |
| `orchestrate-web-e2e` | `0.2.6` | `350224caf3e92793b559fcce23748f4817f0d95e09cd647d28daa2b53a3f4d70` | `d1882a4b1d370a32a542a9954bc6ec133853af51ca7c627e85a3a111a057d244` |
| `execute-web-e2e` | `1.12.6` | `a75fb9baaf3e082b0892f242c77d4140ec1de65aea085cb099d954331e46a07e` | `f308c9f339507309b6cf21fbc9164c6470086e180c83667eb9cbe9a6d3ec2845` |
| `run-web-e2e` | `1.3.9` | `8461fa7a2619ca337e9a123edd7b69b2db79f8e9c5b7e8cd06071e9479d4886f` | `1e3b407e89e8d1d295a72d8d6e104f04bc0060ccc50f8d657f11822f34375e68` |

正式包位于 `report-workspace/web-e2e-automation-packages/`。两个批次均包含三个 Harness 的 execution/scoring ZIP 和五个 Skill ZIP，每批 11 个 ZIP。本轮只读审计逐项重算 22 个 ZIP 的 SHA-256，结果全部与 `batch_manifest.json` 一致；6 个 execution ZIP 分别含有 40/120 份 `execution_record.json`，execution/scoring 公私边界审计通过。

以下 3.1.1–3.1.4 保留各 Harness 功能准入的真机基线和重绑关系。这些记录用于解释当前准入等级，不是应继续分发的旧 Skill 包。

### 3.1.1 AstronStudio Windows 证据沿用与正式包重绑定

提交 `6988b5252bc9140e86dae139fdffbcfc964bcfbf` 已固化 execute 1.11.16 / AstronStudio Driver 1.10.18 / run 1.3.7 / orchestrate 0.2.6。诊断批次 `windows-as-driver-1.10.18-v03-20260915-185350`、`windows-as-driver-1.10.18-v04-20260915-185842` 和 `windows-as-driver-1.10.18-v05-20260915-194158` 的 execute、score、report、run content/ZIP SHA 与 `232007` 正式包逐项一致；V06–V10 实际使用仓库 orchestrate 0.2.6，且候选完整性、submission、return、import/report 证据均可独立校验。由于旧诊断 manifest 自身锁定 0.2.5，不能单独作为正式身份；本轮额外从正式 0.2.6 ZIP 完成 V11 单 Prompt 全流程，并直接完成 V12–V17 恢复边界，故按第 2 节“内容 SHA 与客户端版本完全不变可注明证据沿用”的规则，把 V03–V10 重绑定到当前发布身份。V15 后已将 AstronStudio 恢复到 127.0.0.1:9240，标准启动脚本确认监听 PID 37408 的主程序路径为 `C:\Users\xgzhu6\AppData\Local\Programs\AStudio\AStudio.exe`。

### 3.1.2 AstronStudio macOS 独立包身份

macOS 在干净 worktree `6988b5252bc9140e86dae139fdffbcfc964bcfbf` 上生成了独立单题批次 `web-e2e-20260916-095335-mac-astron-release-6988b52-smoke`。批次内五个 Skill 版本与当时 `6988b525...` 基线一致，实际 content SHA 为 score `6fdc8e9a...`、report `a2236d07...`、orchestrate `350224ca...`、execute `c73a0c0d...`、run `4b9e7748...`，没有重现 Windows `232007` manifest 中的 content SHA；CRLF 模拟也未得到精确匹配，根因尚未确认。该批次 manifest、解压后的隔离 Skill 和评分时独立安装的 score 4.5.2 在本批次内部完全一致，`check_web_e2e_skills.py` 返回 `all_current=true`，所以本轮真机结果可证明这个 macOS 独立包身份的功能，不证明 Windows ZIP 可在 macOS 重现，也不允许把两者作为同一个归档身份混用。

本轮 execution/scoring ZIP SHA 分别为 `90b9c767...` / `ffc6a65d...`。当前源码候选已统一文本换行、文件排序、时间戳、权限、存储方式和内容哈希规范，并在 Web prepare 中落地同一个构建器；但历史差异只有在提交后的同一 revision 上完成 macOS/Windows 双端重算和归档逐字节对账后才能关闭。修复只影响打包/哈希身份时不要求重跑已经完成的页面评分，但新 Skill release 必须重新执行安装校验和一个 L1 包级冒烟。

### 3.1.3 WorkBuddy Windows 补充发布身份

提交 `ee70a67b0d53bf700a389b7fbe3f68fde3c3b288` 固化 execute 1.11.21 / WorkBuddy Driver 1.8.24 / run 1.3.8，重点覆盖 CDP 瞬时连接重试、默认双路执行、终态状态滞留、5.5.6 完全访问确认和重启后侧栏会话缺失。`windows-wb-release-ee70a67-v03-20260916-0616` 与 `windows-wb-release-ee70a67-v05-20260916-0616` 的 manifest 均精确绑定该 revision 和五个 Skill content SHA。V03–V17 使用 WorkBuddy 5.5.6.0、xopglm52 / full-access 完成，不沿用 5.5.3 的历史生产结论；V01 仓库测试为 92/92，通过后才开始真机验收。

### 3.1.4 QwenWork Windows 主流程验收身份

批次 `windows-qwen-mainflow-24771ce-l1-20260916-113542` 的 manifest 精确绑定 `24771ce5f86f9bbc9336cf0c0c48effa5f0b2990`，锁定 score 4.5.2 / report 1.0.2 / orchestrate 0.2.6 / execute 1.11.21 / run 1.3.8；五个 Skill content SHA 与当前安装完全一致。QwenWork Driver 仍为 1.10.10，当前 revision 相对既有验证基线没有 QwenWork Driver 运行时代码差异。本轮只用该身份完成一个 L1 全闭环，用于满足“主流程生产可用”门禁；历史串行、默认三槽、报告和恢复证据不自动升格为当前 `PASSED`。

正式包可以在 macOS 或 Windows 的干净检出中生成。准备脚本继续从仓库读取题目和 Workspace，并调用统一 E2E 构建器生成五个阶段 Skill；分发 Skill 不依赖 checkout。必须满足以下门禁：

- 生成机器的检出必须包含 P1 记录的实现提交，且打包前 Web E2E 相关源码和题目目录没有未提交修改；
- `batch_manifest.json`、`packages/skills-build-manifest.json`、`packages/skills-manifest.json` 和各 Harness manifest 的 `source_revision` 必须等于打包时的 `git rev-parse HEAD`；
- 自建、开源两个批次的五个 Skill 名称、版本、运行 `content_sha256`、ZIP SHA 和 `skill_set_sha256` 必须完全一致，五个 ZIP 逐字节一致；`skills-build-manifest.json` 的完整构建内容 SHA 同时逐项一致。运行内容哈希规范化排除来源 revision，构建内容哈希与 ZIP SHA 仍保留完整来源和归档审计；
- 同一提交在 macOS 与 Windows 生成的五个 Skill ZIP 也必须逐字节一致；未完成双端对账时只能保留候选状态，不能关闭 P10。历史包 SHA 不要求与新 release 相等，也不能混用旧包清单；
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
| `mac-astron-release-6988b52-v11-20260916` | macOS 26.6.2 / x86_64 | AstronStudio 3.0.0-alpha.19 | GLM-5.2 / High / full-access | Codex Desktop 26.908.70816 | `web-e2e-20260916-095335-mac-astron-release-6988b52-smoke` | Codex（本机） | 2026-09-16 | 同实现 revision 的独立 macOS 包；单 L1 execution→score→submission→return 完成，达到“主流程生产可用”；与 Windows `232007` content SHA 不同，不作为同一归档身份 |
| `windows-astron-v03-20260915` | Windows 10 10.0.19042 / x64 | AstronStudio 3.2.1.242 | GLM-5.2 / High | 尚未参与评分 | `windows-astron-v03-20260915-155220` | Codex（本机） | 2026-09-15 | 实现 revision `0486480`；execute 1.11.13 / Driver 1.10.15；Node 24.19.0；V02/V03 已通过，当前使用经完整路径校验的 AStudio 和 127.0.0.1:9241 |
| `windows-astron-driver-11016-20260915` | Windows 10 10.0.19042 / x64 | AstronStudio 3.2.1.242 | GLM-5.2 / High | 未启动评分；Codex 9230 未启用 | `windows-astron-driver-1.10.16-functional-20260915-173623` | Codex（本机） | 2026-09-15 | 未提交功能候选；V02 通过，V03 两个隔离 attempt 均失败关闭；未启动 V04–V09 |
| `windows-astron-331277-20260915` | Windows 10 10.0.19042 / x64 | AstronStudio 3.3.1.277 | GLM-5.2 / High | 未启动评分；Codex 9230 未启用 | `windows-astron-driver-1.10.16-final-20260915-175731` | Codex（本机） | 2026-09-15 | 未提交功能候选；升级后 V02 通过，V03 两个隔离 attempt 均失败关闭；后端反复 `read ENOTCONN` 退出并重启，未启动 V04–V09 |
| `windows-astron-331277-driver-11018-20260915` | Windows 10 10.0.19042 / x64 | AstronStudio 3.3.1.277 | GLM-5.2 / High | Codex Desktop 26.908.9136；CDP runtime 152.0.7977.83 | `windows-as-driver-1.10.18-v05-20260915-194158` | Codex（本机） | 2026-09-15 | 未提交功能候选；AStudio 经环境隔离启动在 127.0.0.1:9241，后端 PID 34848；Codex 以 127.0.0.1:9230 完成评分；V02–V10 通过，平均分 74；项目注册使用未打包 orchestrate 0.2.6，默认 9240 仍有陈旧监听 |
| `windows-astron-release-6988b52-20260916` | Windows 10 10.0.19042 / x64 | AstronStudio 3.3.1.277 | GLM-5.2 / High / full-access | Codex Desktop 26.908.9136；CDP runtime 152.0.7977.83 | `web-e2e-20260915-232007-opensource120`；验证 batch `windows-as-release-6988b52-v11-20260915-232329` | Codex（本机） | 2026-09-16 | AstronStudio Windows 功能准入基线；Node 24.17.0；AstronStudio 127.0.0.1:9240、Codex 127.0.0.1:9230；V00–V17 全部通过 |
| `windows-workbuddy-release-ee70a67-20260916` | Windows 10 10.0.19042 / x64 | WorkBuddy 5.5.6.0 | xopglm52 / full-access | Codex Desktop 26.908.9136；CDP runtime 152.0.7977.83 | `windows-wb-release-ee70a67-v03-20260916-0616`、`windows-wb-release-ee70a67-v05-20260916-0616` | Codex（本机） | 2026-09-16 | WorkBuddy Windows 功能准入基线；Node 24.17.0；WorkBuddy 127.0.0.1:9229（V15 同身份恢复到 9299）、Codex 127.0.0.1:9230；V00–V17 全部通过 |
| `windows-qwen-mainflow-24771ce-20260916` | Windows 10 10.0.19042 / x64 | QwenWorkCN 1.0.5.0 | 标准｜Qwen3.8-Flash / full-access | Codex Desktop 26.908.9136；CDP runtime 152.0.7977.83 | `windows-qwen-mainflow-24771ce-l1-20260916-113542` | Codex（本机） | 2026-09-16 | QwenWork Windows 主流程功能准入基线；Node 18.16.1；QwenWork 127.0.0.1:9250、Codex 127.0.0.1:9230；V00/V02/V03/V06/V08/V09/V11 通过 |

## 4. Harness×OS 验收矩阵

缩写：`N`=`NOT_STARTED`，`I`=`IN_PROGRESS`，`B`=`BLOCKED`，`P`=`PASSED`，`S`=`STALE`。矩阵记录各 Harness×OS 的功能准入基线状态；分发包更新不会自动改写矩阵，也不能把下方历史证据直接改写成 `P`。

| ID | 验收项 | macOS AstronStudio | macOS WorkBuddy | macOS QwenWork | Windows AstronStudio | Windows WorkBuddy | Windows QwenWork |
| --- | --- | --- | --- | --- | --- | --- | --- |
| V00 | 发布身份和依赖锁定 | P | I | I | P | P | P |
| V01 | 仓库测试与 Skill 校验 | P | P | P | P | P | P |
| V02 | 只读 probe 与 CDP 进程身份 | P | P | P | P | P | P |
| V03 | 单个 L1、`run_slots=1` | P | P | P | P | P | P |
| V04 | 三个 L1 串行自动进入下一题 | I | S | S | P | P | S |
| V05 | 五个 L1、Harness 默认槽位动态补位 | I | S | S | P | P | S |
| V06 | Codex Desktop 项目精确注册 | P | S | S | P | P | P |
| V07 | 默认三路并发评分与动态补位 | I | S | S | P | P | S |
| V08 | submission 原子生成 | P | S | S | P | P | P |
| V09 | return ZIP、外部 receipt 与 SHA | P | S | S | P | P | P |
| V10 | 管理员 import 与报告三件套 | I | S | N | P | P | S |
| V11 | 一个 Prompt 执行→评分→打包 | P | S | N | P | P | P |
| V12 | 独立控制任务接管磁盘状态 | N | S | N | P | P | S |
| V13 | 被评 Harness 重启恢复/安全失败 | N | S | N | P | P | S |
| V14 | Codex Desktop 重启恢复 | N | S | N | P | P | S |
| V15 | 执行/评分超时与发送前重试 | N | S | N | P | P | S |
| V16 | 评分失败 attempt 隔离和错误回执 | N | S | N | P | P | N |
| V17 | submission 发布中断恢复 | N | S | N | P | P | N |

### 4.1 各项验收条件

| ID | 操作与通过条件 | 必须保存的证据 |
| --- | --- | --- |
| V00 | `git rev-parse HEAD`、五个 Skill metadata/ZIP/content SHA、Harness/Codex/OS/架构全部登记；批次 `source_revision` 与 HEAD 一致 | 发布身份表、`skills-manifest.json`、批次 manifest |
| V01 | 三个执行 Driver、Codex Desktop Driver、截图接收器、相关 Python 测试和全部 Skill `quick_validate.py` 通过 | 命令、退出码、通过/失败数和时间 |
| V02 | 只读 `--probe` 成功；CDP 仅监听 `127.0.0.1`；端口监听者完整路径等于发现的主程序；桌面解锁、状态库和关键 UI 就绪 | probe JSON、主程序路径、端口/PID、客户端版本 |
| V03 | 一个 L1 题目终态明确，模型/权限回读正确，候选非空，`execution_record.json` 与自动化状态一致 | task ID、automation state、execution record、候选 SHA |
| V04 | 三题以 `run_slots=1` 自动切题，无重复项目、重复 Prompt 或跳题 | queue state、三题 conversation/thread ID、终态时间线 |
| V05 | 五题使用 Harness 当前默认槽位（WorkBuddy、AstronStudio、QwenWork 均为 `run_slots=3`）；首批投递后，任一题完成即补入下一题；`ui_slots=1` | queue state、槽位时间线、五题终态、execution receipt |
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
| `windows-astron-v02-20260915` | AstronStudio×Windows | V02 | `PASSED` | `0486480ca9dda5a5b6269d997caf7fb8af4e8444`；run 1.3.5；Driver 1.10.15 | `windows-astron-v03-20260915-155220` | `start_windows_desktop_debug.ps1 -Application AstronStudio -CheckOnly`；Driver `--probe` | `D:\debug-workspace\web-e2e\windows-release-astron-20260915-154252\V02-preflight.json` | 2026-09-15 / Codex | 完整路径 `C:\Users\xgzhu6\AppData\Local\Programs\AStudio\AStudio.exe`；客户端 3.2.1.242；初始 CDP 为 127.0.0.1:9240；Node 24.19.0 的 `node:sqlite` 可读状态库；GLM-5.2 / High；full-access；GUI 解锁 |
| `windows-astron-v03-20260915` | AstronStudio×Windows | V03 | `PASSED` | `0486480ca9dda5a5b6269d997caf7fb8af4e8444`；execute 1.11.13；Driver 1.10.15；run 1.3.5；Playwright 1.55.0 | `windows-astron-v03-20260915-155220`；ab063 | 单个 L1，`run_slots=1`；原端口异常后在已验证 AStudio 的 127.0.0.1:9241 恢复同一队列 | `D:\debug-workspace\web-e2e\windows-release-astron-20260915-154252\workers\v03\windows-astron-v03-20260915-155220__astronstudio`；receipt SHA `2c37b1fa581929859244f161349d1154135749be986e809caaf84e01c89de3c6`；queue SHA `24ac560f798c69e383040fb11bf0de53124e1cbc76840f85709f5995e958f2ea`；候选 SHA `5f995643bfee9b03d8b339de34484ce59aba50aadfae0de5969221f3bbc42409` | 2026-09-15 / Codex | 正式 Skill content SHA 全部匹配；1/1 `SUCCEEDED`，`PROMPT_SENT=1`，状态库终态；进程清理支持且成功，45 秒静默窗后无残留；`integrity.valid=true`。首次 attempt 在发送前因旧端口目标失效而归档，确认 `PROMPT_SENT=0` 后仅重试一次；Windows 原生打包/校验受换行和 `Path` 排序影响，使用未修改标准脚本在 WSL 生成并复核与清单一致的正式内容 |
| `windows-astron-v04-20260915` | AstronStudio×Windows | V04 | `PASSED` | `0486480ca9dda5a5b6269d997caf7fb8af4e8444`；execute 1.11.13；Driver 1.10.15；run 1.3.5；Playwright 1.55.0 | `windows-astron-v04-20260915-161506`；ab063、ab078、ab095 | 三个 L1，`run_slots=1`；不指定模型；full-access；127.0.0.1:9241 | `D:\debug-workspace\web-e2e\windows-release-astron-20260915-154252\workers\v04\windows-astron-v04-20260915-161506__astronstudio\windows-astron-v04-20260915-161506__astronstudio`；receipt SHA `7c3af75be240b3329ccd096585e3b21fc4c67c65222f20fa385dd503d8c8b08b`；queue SHA `6d63505b873d1236b4975dc7af952739a5e1cdd25fe259938b533819b0b803f0` | 2026-09-15 / Codex | 历史 Windows 完整三题证据使用 Driver 1.10.6/1.10.7 且无 `process_cleanup`，不能覆盖 1.10.15 的清理后切题门禁，故重新执行；3/3 `SUCCEEDED`，依次投递，两次自动切题，每题不同 conversation/turn 且 `PROMPT_SENT=1`；三题 cleanup 均支持并成功，候选 SHA 分别为 `dd491756...`、`73170d94...`、`70b0436c...`；`integrity.valid=true` |
| `windows-astron-v05-20260915` | AstronStudio×Windows | V05 | `BLOCKED` | `0486480ca9dda5a5b6269d997caf7fb8af4e8444`；execute 1.11.13；Driver 1.10.15；run 1.3.5；Playwright 1.55.0 | `windows-astron-v05-20260915-165935`；ab063、ab078、ab095、ab097、ab102 | 五个 L1；省略 `--run-slots`，Driver 默认冻结为 3；`ui_slots=1`；不指定模型；full-access；127.0.0.1:9241 | `D:\debug-workspace\web-e2e\windows-release-astron-20260915-154252\workers\v05\windows-astron-v05-20260915-165935__astronstudio`；原失败 automation SHA `219ea674...`；恢复收口后 SHA `c88ecf852ee262a5d9f6433aa6fcb0b178f5b3589d7ab9302eed3f86a6f795e7`；execution record SHA `21d1b771eb2c586c8fde763e36a71c01b525f0302d5b184ad64bf3c8d4f0d4e8` | 2026-09-15 / Codex | 首题 Prompt 仅发送一次。1.10.16 只读验证从持久化的发送前路由严格恢复 thread `c66b89e2-...`、turn `01a0a44e-...` 与精确 cwd；原状态文件只读验证前后 SHA 不变。随后正式 `--resume --observe-once` 写回该身份，状态库确认旧 AStudio 退出已使 turn 变为 `interrupted`，最终安全收口为 `INFRA_FAILED`；其余四题仍未投递，未评分、未生成 submission/return |
| `windows-astron-11016-static-20260915` | AstronStudio×Windows | V01 | `PASSED` | 工作树 execute 1.11.14；Driver 1.10.16 | 不适用 | Node 24.19.0 `npm test`；准备脚本 unittest；Skill quick validate | 现位于仓库 `tools/report/skills/web-e2e/execute-web-e2e` | 2026-09-15 / Codex | AstronStudio Driver 47/47、`tests.test_prepare_web_e2e_workspaces` 31/31、Skill 校验通过；覆盖发送后延迟 session、无路由拒绝恢复、120–180 秒窗口和持久化路由恢复；代码测试不替代真机通过 |
| `windows-astron-11016-v02-20260915` | AstronStudio×Windows | V02 | `PASSED` | 诊断 ZIP execute 1.11.14；Driver 1.10.16；run 1.3.5 | `windows-astron-driver-1.10.16-functional-20260915-173623` | 版本化 ZIP 解压；`start_windows_desktop_debug.ps1 -CheckOnly`；Driver `--probe` | `D:\debug-workspace\web-e2e\windows-as-driver-1.10.16-functional-20260915-173623\windows-astron-driver-1.10.16-functional-20260915-173623\workers\v02` | 2026-09-15 / Codex | 127.0.0.1:9240、PID 38040、AStudio.exe 完整路径、客户端 3.2.1.242、Node `node:sqlite`、GUI 解锁、GLM-5.2 / High、full-access、`active_session_count=0`，probe `ready=true` |
| `windows-astron-11016-v03-socket-close-20260915` | AstronStudio×Windows | V03 | `BLOCKED` | 诊断 ZIP execute 1.11.14；Driver 1.10.16（最小身份窗 60 秒的中间构建） | `windows-as-11016-v03-20260915-174000`；ab078 | `run_slots=1`；full-access；127.0.0.1:9240 | `D:\debug-workspace\web-e2e\windows-as-driver-1.10.16-functional-20260915-173623\windows-astron-driver-1.10.16-functional-20260915-173623\workers\v03`；queue SHA `faa1f1f10937af9f1b6ea723c124332c91806fbbc1f2a9d2bfdeae841ba8ea2f`；automation SHA `149e9655657f2d27ec5c0f962721e6273322aa5329ae1ea83dead2355fd8dc29`；截图 SHA `c8fb0a47e55477a51f24d617d8e5b1831c0dc90a80b585873a7ac09a0de31328` | 2026-09-15 / Codex | 点击发送后 UI 明确显示 `SocketCloseError: 1000`，状态库没有创建精确 cwd session，候选无变化；Driver 保留 `PROMPT_SENT=1` 并失败关闭，未猜测重发 |
| `windows-astron-11016-v03-delayed-session-20260915` | AstronStudio×Windows | V03 | `BLOCKED` | 诊断 ZIP execute 1.11.14；Driver 1.10.16（最小身份窗 60 秒的中间构建） | `windows-as-11016-v03b-20260915-174300`；ab078 | 活动会话为 0 后 `--restart-app-first`；`run_slots=1`；full-access；127.0.0.1:9240 | `D:\debug-workspace\web-e2e\windows-as-driver-1.10.16-functional-20260915-173623\windows-astron-driver-1.10.16-functional-20260915-173623\workers\v03b`；queue SHA `d52b0a1df9fe3d756113c40d4ef9187167583273b651e2d4f9d9b0fce07d5720`；终态 automation SHA `5d0bb98e023abbdbd1afe1691d005a9679eedfb4b9c049f214d68cac33140b0b`；execution record SHA `ba731e6b2325fb9e3ee8cc2037a239fcbdb91cbb40cb979133ccfbf965d74d80` | 2026-09-15 / Codex | session `e078dd65-...` 在发送后约 59.6 秒才出现，严格恢复成功并保持 `PROMPT_SENT=1`；随后约 8 分钟状态库无进展、候选仍仅 `.gitkeep`。`desktop-main.log` 持续 `SocketOpenError`，`server-child.log` 反复未处理 `read ENOTCONN`，AStudio/9240 连接反复不可用；状态库最终把原 turn 标为 `interrupted`，Driver 收口为 `INFRA_FAILED`，Windows 精确进程清理成功且 45 秒静默窗无残留。未生成有效 execution receipt，故停止 V04/V05 放大验证 |
| `windows-astron-331277-v02-20260915` | AstronStudio×Windows | V02 | `PASSED` | 未提交诊断 ZIP execute 1.11.14；Driver 1.10.16；run 1.3.5 | `windows-astron-driver-1.10.16-final-20260915-175731` | 标准 `start_windows_desktop_debug.ps1 -Application AstronStudio`；版本化 ZIP Driver `--probe` | `D:\debug-workspace\web-e2e\windows-as-driver-1.10.16-final-20260915-175731\windows-astron-driver-1.10.16-final-20260915-175731\workers\upgraded-v02-20260915-180748` | 2026-09-15 / Codex | AStudio.exe 完整路径 `C:\Users\xgzhu6\AppData\Local\Programs\AStudio\AStudio.exe`；客户端 3.3.1.277；127.0.0.1:9240、PID 36596；状态库可读，GUI 解锁，GLM-5.2 / High、full-access、`active_session_count=0`，probe `ready=true` |
| `windows-astron-331277-v03-send-20260915` | AstronStudio×Windows | V03 | `BLOCKED` | 未提交诊断 ZIP execute 1.11.14；Driver 1.10.16（最终 120–180 秒实现） | `windows-as-3.3.1.277-v03-20260915-180849`；ab078 | 单个 L1，`run_slots=1`；full-access；127.0.0.1:9240；终止后只观察 `--resume`，未重发 | `D:\debug-workspace\web-e2e\windows-as-driver-1.10.16-final-20260915-175731\windows-astron-driver-1.10.16-final-20260915-175731\workers\upgraded-v03-20260915-180849`；queue SHA `724d142c42cf4b3859b6212b17f827692ff436c3e8c29e8476a9237f11f5bcad`；automation SHA `ba5d5cf615e0206e756f824f1052c9370e40caf7792161f55524174d2098d8ad`；execution record SHA `9960f74fa5889f4b48f598c0a51ec37187c133913ad237e790e1c846a39eebfa`；截图 SHA `6af3d09d16b2cae441b2b56dbaf02262d6f2f040f780ebfbda6364366c11147b` | 2026-09-15 / Codex | Prompt 点击后等待约 121.6 秒仍无路由、session、turn 或 cwd，状态库 session 数保持 29，截图显示 Prompt 仍在新建对话输入框；Driver 保留 `PROMPT_SENT=1` 并 `NEEDS_ATTENTION` 失败关闭。同期 `server-child.log:11420-11446` 记录未处理 `read ENOTCONN`，`desktop-main.log:6178-6346` 记录后端连续退出、重启和 `SocketOpenError`；恢复观察未发现延迟 session |
| `windows-astron-331277-v03-presend-20260915` | AstronStudio×Windows | V03 | `BLOCKED` | 未提交诊断 ZIP execute 1.11.14；Driver 1.10.16（最终 120–180 秒实现） | `windows-as-3.3.1.277-v03b-20260915-181433`；ab078 | 后端短暂稳定且 probe 再次通过后使用全新 worker；单个 L1，`run_slots=1`；full-access；127.0.0.1:9240 | `D:\debug-workspace\web-e2e\windows-as-driver-1.10.16-final-20260915-175731\windows-astron-driver-1.10.16-final-20260915-175731\workers\upgraded-v03b-20260915-181433`；queue SHA `ba089fffc02bbdd5a3016d2a55d865eb7baf603ee1c1e72fc6684d5a2d38aa28`；automation SHA `01c48d623c00ab27c27641c311bc47bf1961e4cce03022a24b0cecdf35d04c19`；终态截图 SHA `500e143f4f5e3798d08ba33318bae2e1b54aa4909a3d9806e87ecea5a0d97bc8` | 2026-09-15 / Codex | 新建任务期间后端 PID 31396 被 36244 替换，Driver 在发送前因“新建任务后未进入新的可编辑任务路由”收口为 `INFRA_FAILED`；`sent_at=null`、没有 Prompt 重发、候选无变化。3.3.1.277 升级未解除 Windows 后端稳定性阻塞，按顺序门禁停止 V04/V05，Codex 保持非调试启动且未进入评分 |
| `windows-astron-11018-static-20260915` | AstronStudio×Windows | V01 | `PASSED` | 工作树 execute 1.11.16；Driver 1.10.18；run 1.3.7 | 不适用 | Node 24.19.0 显式测试文件；Python unittest；execute/run quick validate；PowerShell/Node 语法检查 | 现位于仓库 `tools/report/skills/web-e2e/execute-web-e2e`、`tools/report/skills/web-e2e/run-web-e2e` | 2026-09-15 / Codex | AstronStudio Driver 49/49、准备脚本 31/31、两个 Skill 校验通过；覆盖启动环境隔离、SQLite 子进程硬超时和 DOM 回退；`git diff --check` 除 CRLF 提示外无错误 |
| `windows-astron-11018-v02-20260915` | AstronStudio×Windows | V02 | `PASSED` | 工作树 execute 1.11.16；Driver 1.10.18；run 1.3.7 | `windows-as-driver-1.10.18-v03-20260915-185350` | 环境隔离启动；Node 24 Driver `--probe`；127.0.0.1:9241 | AStudio 主进程 PID 30604、后端 PID 34848；`C:\Users\xgzhu6\AppData\Local\Programs\AStudio\AStudio.exe` | 2026-09-15 / Codex | 客户端 3.3.1.277、状态库可读、GUI 解锁、GLM-5.2 / High、full-access、活动会话为 0，`ready=true`；启动仅从 AStudio 子进程环境移除控制/IPC变量，父终端环境恢复；9240 仍为无存活所属进程的陈旧监听 |
| `windows-astron-11018-v03-20260915` | AstronStudio×Windows | V03 | `PASSED` | HEAD `4c635115562284de0603a99e6368ee4b8a46e1a7` 上未提交功能候选；execute 1.11.16；Driver 1.10.18；run 1.3.7 | `windows-as-3.3.1.277-v03-final-20260915-185350`；ab078 | 单个 L1；`run_slots=1`；GLM-5.2；full-access；127.0.0.1:9241 | `D:\debug-workspace\web-e2e\windows-as-driver-1.10.18-v03-20260915-185350\windows-as-driver-1.10.18-v03-20260915-185350\harnesses\astronstudio`；receipt SHA `43fabdd94221327592472f11dfb597dcc48caa71fe196b9d5c50c212c88e855d`；queue SHA `132c4b3b86c77509bf99fbcd814f791437725e636717028bb4f222c4893e5333` | 2026-09-15 / Codex | 1/1 `SUCCEEDED`；thread `def96da8-c3a8-4e09-8f71-6c08a0366da8`、turn `01a0a4b4-7067-7930-b86f-aa745075df75`；`PROMPT_SENT=1`，清理成功，`integrity.valid=true` |
| `windows-astron-11018-v04-20260915` | AstronStudio×Windows | V04 | `PASSED` | HEAD `4c635115562284de0603a99e6368ee4b8a46e1a7` 上未提交功能候选；execute 1.11.16；Driver 1.10.18；run 1.3.7 | `windows-as-3.3.1.277-v04-final-20260915-185842`；ab063、ab078、ab095 | 三个 L1；`run_slots=1`；GLM-5.2；full-access；127.0.0.1:9241 | `D:\debug-workspace\web-e2e\windows-as-driver-1.10.18-v04-20260915-185842\windows-as-driver-1.10.18-v04-20260915-185842\harnesses\astronstudio`；receipt SHA `b9c3f28345108bf11715e0733f00bc86be90c773892d0641f54a9ef59fef7037`；queue SHA `2efb4776e1003543981bca59756b55cc68a04ba202ff76869bc3b53091e44418` | 2026-09-15 / Codex | 3/3 `SUCCEEDED`，严格串行切题；每题不同 conversation/turn、`PROMPT_SENT=1`、GLM-5.2 / High、清理成功，`integrity.valid=true`；AStudio 后端 PID 34848 全程稳定 |
| `windows-astron-11018-v05-20260915` | AstronStudio×Windows | V05 | `PASSED` | HEAD `4c635115562284de0603a99e6368ee4b8a46e1a7` 上未提交功能候选；execute 1.11.16；Driver 1.10.18；run 1.3.7 | `windows-as-3.3.1.277-v05-final-20260915-194158`；ab063、ab078、ab095、ab097、ab102 | 五个 L1；默认 `run_slots=3`、`ui_slots=1`；GLM-5.2；full-access；127.0.0.1:9241；同 run-id 恢复 | `D:\debug-workspace\web-e2e\windows-as-driver-1.10.18-v05-20260915-194158\windows-as-driver-1.10.18-v05-20260915-194158\harnesses\astronstudio`；receipt SHA `b1667497a64b1868871437d9c09d47327fd25273971b2b39a73ee8b169817a59`；queue SHA `c189f215432df9677e6286779d06a7a1e08210a24680be3df133def5e3fe4b0b` | 2026-09-15 / Codex | 5/5 `SUCCEEDED`、五个唯一 conversation/turn、每题 `PROMPT_SENT=1`、GLM-5.2 / High / full-access、SQLite 终态、清理成功、`manual_interventions=[]`、`integrity.valid=true`。ab078 完成后补 ab097，ab063 完成后补 ab102；控制 Worker 三次由宿主回收/优雅停止后均按 `PROCESS_LOST` 或中断记录恢复，不重发 Prompt；误用 Node 18 时只产生可恢复的 `sqlite3.exe ENOENT`，随后用 Node 24 状态库确认终态 |
| `windows-astron-11018-v06-prepared-20260915` | AstronStudio×Windows | V06 | `IN_PROGRESS` | orchestrate 0.2.5；score 4.5.2；Codex Desktop 26.908.9136 | `windows-as-driver-1.10.18-v05-20260915-194158`；5 题 | 标准评分副本生成；`scoring-control init --score-slots 3`；只读 Codex/9230 检查 | scoring state SHA `055cfb170a5ed727a28566da7bb1fc94bb71cb8a3b0f590a9654842589d304a1`；execution receipt SHA `b1667497...` | 2026-09-15 / Codex | execution/score 双副本哈希全部一致，5 个项目待注册，状态为 `PREPARED/PENDING_PROJECT`。当前 Codex PID 18968 未带 9230，端口未监听，内置 `list_projects` 返回 `Transport closed`；控制任务不能重启自身，待外部以 127.0.0.1:9230 调试模式重启后原状态继续 |
| `windows-astron-11018-v06-20260915` | AstronStudio×Windows | V06 | `PASSED` | HEAD `4c635115...` 上未提交功能候选；仓库 orchestrate 0.2.6；score 4.5.2；Codex Desktop 26.908.9136 / runtime 152.0.7977.83 | 同 V05 五题 | 127.0.0.1:9230；Codex 可见 UI“在此电脑上添加文件夹”项目注册；逐题 preflight | `score/.orchestrate-web-e2e/project-registry.json`；SHA `0cbcb87589f3c70b050b2181bbdfb8636e1698372c9ece82cff5764dcd9670fc` | 2026-09-15 / Codex | 5/5 唯一项目，精确绑定各自 `score/tasks/<task_id>`；项目 ID 分别为 `8a33dc8e...`、`01497e08...`、`994527d3...`、`4f664a31...`、`dd127f5a...`；没有指向 execution 原件，未使用 renderer bridge |
| `windows-astron-11018-v07-20260915` | AstronStudio×Windows | V07 | `PASSED` | 仓库 orchestrate 0.2.6；已安装 score 4.5.2 | 同 V05 五题 | 默认 `score_slots=3`；Codex Desktop 独立 thread/browser/4173–4177；动态补位 | `score/.orchestrate-web-e2e/scoring-automation-state.json`；SHA `d826b64828ca59aaccab7728d59611b64ef2d3d91d491e23c0544d690a4456fb` | 2026-09-15 / Codex | 5/5 `COMPLETED`，得分 78、70、76、64、82；ab095 首次因模型容量失败，错误 attempt 原子归档后按契约唯一重试成功，未切换模型；五题候选双副本哈希无漂移，4173–4177 服务及运行时副本均清理 |
| `windows-astron-11018-v08-20260915` | AstronStudio×Windows | V08 | `PASSED` | 仓库 orchestrate 0.2.6；score 4.5.2 | 同 V05 五题 | 最后一题 `mark-complete` 后原子构建 submission | `submission.json`；SHA `f197442c137603fefb2596867c7ef2e33d21a64d6c7b8756d48c36baa0a2be11` | 2026-09-15 / Codex | scoring phase 与 submission status 均为 `COMPLETED`，`attempt_count=1`；5/5 完整 task ID，最终候选双副本哈希和端口审计通过，无 pending 文件 |
| `windows-astron-11018-v09-20260915` | AstronStudio×Windows | V09 | `PASSED` | run 1.3.7 | 同 V05 五题 | `run_web_e2e.py export-return` | `D:\debug-workspace\web-e2e\windows-as-driver-1.10.18-v05-20260915-194158\offline-return\windows-as-driver-1.10.18-v05-20260915-194158__astronstudio__return.zip`；ZIP SHA `bc7d6d606ee5af77a440d8577ac0b6f0d6adf0fa699ac5c5262c5862ff99776b`；外部 receipt SHA `edd56d457b57d9d2a8c475fc71145f0c020212505c65c388fec9765dd2dd0863` | 2026-09-15 / Codex | 5,348,366 字节、289 个文件；回执绑定批次、Harness、GLM-5.2、Profile、完整五题和 ZIP SHA；导入门禁再次确认无路径穿越、符号链接、浏览器 profile、密钥及禁止目录 |
| `windows-astron-11018-v10-20260915` | AstronStudio×Windows | V10 | `PASSED` | run 1.3.7；report 1.0.2；ArtifactsBench Profile | 同 V05 五题 | `import-return`；报告聚合；Artifact Tool 构建；WPS 独立只读渲染 | import receipt SHA `8132c4dbc0e098658cb1c615b4524034e06d5788e254201dad488aa1ef79455a`；报告 JSON/MD/XLSX SHA `189a0687...` / `91e0586a...` / `aad7b6f8...`；batch state SHA `b1ee825b...` | 2026-09-15 / Codex | collect/report 均 `COMPLETED`；5/5 完成、平均分 74、完成率 100%；Excel 三 Sheet 顺序和关键值通过，保存后公式错误扫描为 0；Artifact Tool 内置预览原生崩溃后按 Skill 降级，WPS 逐 Sheet PDF/PNG 只读预览均无截断或乱码 |
| `windows-astron-release-v00-20260916` | AstronStudio×Windows | V00 | `PASSED` | `6988b5252bc9140e86dae139fdffbcfc964bcfbf`；execute 1.11.16 / Driver 1.10.18；orchestrate 0.2.6；score 4.5.2；run 1.3.7；report 1.0.2 | `web-e2e-20260915-232007-custom40`、`web-e2e-20260915-232007-opensource120` | 标准准备脚本；三 Harness；Profile auto；重算 manifest/hash | `report-workspace/web-e2e-automation-packages/`；两批次 40/120 题、各 11 ZIP，22/22 SHA 匹配；五个 Skill content/ZIP SHA 见 3.1 | 2026-09-16 / Codex | 两批次 source revision 均为 `6988b525...`，Harness 均为 AstronStudio/WorkBuddy/QwenWork，execution/scoring 边界审计通过，正式身份锁定 |
| `windows-astron-release-v01-20260916` | AstronStudio×Windows | V01 | `PASSED` | 同 V00；Node 24.17.0；playwright-core 1.55.0 | 不适用 | 三执行 Driver、Codex Desktop Driver、截图接收器、准备脚本与六个 Skill quick validate | 当前仓库；Astron 49/49、WorkBuddy 87/87、QwenWork 40/40、Codex 52/52、receiver 8/8、prepare 31/31；六个 Skill 校验通过 | 2026-09-16 / Codex | Windows Node 测试使用显式测试文件；所有命令退出码为 0 |
| `windows-astron-release-v02-20260916` | AstronStudio×Windows | V02 | `PASSED` | 同 V00；AstronStudio 3.3.1.277 | `windows-as-release-6988b52-20260915-232329` | 标准 Windows 调试启动脚本；Driver `--probe`；最终恢复 127.0.0.1:9240 | `D:\debug-workspace\web-e2e\windows-as-release-6988b52-20260915-232329\V02-astronstudio-probe-pass.json`；启动日志 `V02-start-windows-desktop-debug.log` | 2026-09-16 / Codex | probe `ready=true`、状态库可读、GUI 解锁、GLM-5.2 / High / full-access、活动会话为 0；V15 后标准启动脚本再次确认 9240/PID 37408 和 AStudio.exe 完整路径 |
| `windows-astron-release-v03-v10-rebind-20260916` | AstronStudio×Windows | V03–V10 | `PASSED` | 当前正式包与旧功能批次的 execute/score/report/run content 和 ZIP SHA 逐项一致；实际评分运行时 orchestrate 0.2.6 | `windows-as-driver-1.10.18-v03-20260915-185350`、`v04-20260915-185842`、`v05-20260915-194158` | 内容哈希审计；正式 0.2.6 ZIP V11 冒烟；旧五题 execution→score→submission→return→import/report 证据复核 | V05 根 `D:\debug-workspace\web-e2e\windows-as-driver-1.10.18-v05-20260915-194158\windows-as-driver-1.10.18-v05-20260915-194158\harnesses\astronstudio`；execution receipt `b1667497...`；scoring state `d826b648...`；submission `f197442c...`；return ZIP `bc7d6d60...`；import receipt `8132c4db...` | 2026-09-16 / Codex | V03 1/1、V04 3/3、V05 5/5 执行成功；V06–V10 五题平均 74 且完整性无漂移。旧 manifest 的 orchestrate 0.2.5 不单独用于晋级，正式 V11 对 0.2.6 包完成补充绑定 |
| `windows-astron-release-v11-20260916` | AstronStudio×Windows | V11 | `PASSED` | 同 V00；五个 Skill 均从正式 ZIP 解压 | `windows-as-release-6988b52-v11-20260915-232329`；ab078 | 用户单个 `$run-web-e2e` Prompt；execute→score→package | `D:\debug-workspace\web-e2e\windows-as-release-6988b52-20260915-232329\workers\v11\windows-as-release-6988b52-v11-20260915-232329__astronstudio`；unit state SHA `8a3551b774528cf1db56fd163229858134ffa5fe11bcf30af57e7760ddf6c09f`；execution receipt `97404891...`；scoring state `2280cf62...`；submission `65b4aec3...`；return ZIP `32287a78...` | 2026-09-16 / Codex | 三阶段均 `COMPLETED`；执行仅一次 Prompt，候选 SHA `a8422d20...`；评分 thread `01a0a5bb-...` 得分 76；return ZIP 1,049,592 字节、76 文件 |
| `windows-astron-release-v12-20260916` | AstronStudio×Windows | V12 | `PASSED` | 同 V00 | `v12-independent-handoff`；ab078 | 精确终止原 Worker PID 2016；独立 Codex 任务以相同参数 `--resume` 接管 | V12 根 `D:\debug-workspace\web-e2e\windows-as-release-6988b52-20260915-232329\workers\v12\windows-as-release-6988b52-v11-20260915-232329__astronstudio`；queue SHA `16e391ab...`；automation SHA `86afbb0d...`；receipt SHA `2ac294df...` | 2026-09-16 / Codex | 新控制任务 `01a0a5c9-...` 使用 Worker PID 31204；conversation `7be3e960-...`、turn `01a0a5c7-...`、attempt `98f0dfd7-...` 全部沿用；`WORKER_INTERRUPTED=1`、`WORKER_RESUMED=1`、`PROMPT_SENT=1`，最终成功 |
| `windows-astron-release-v13-20260916` | AstronStudio×Windows | V13 | `PASSED` | 同 V00 | `v13-harness-restart`；ab078 | Prompt 发送后精确结束 AStudio 进程树；`--resume --restart-app-on-resume` | V13 根 `D:\debug-workspace\web-e2e\windows-as-release-6988b52-20260915-232329\workers\v13\windows-as-release-6988b52-v11-20260915-232329__astronstudio`；queue SHA `0301557d...`；automation/result SHA `3518a48c...` | 2026-09-16 / Codex | 原 conversation `72dcbe73-...`、turn `01a0a5ce-...` 被状态库明确标记 `interrupted`；Driver 安全收口 `INFRA_FAILED`，没有重发，候选 SHA 前后均为 `6dd93633...`。这是验收条件允许的安全失败分支 |
| `windows-astron-release-v14-20260916` | AstronStudio×Windows | V14 | `PASSED` | 同 V00；Codex Desktop 26.908.9136 | V12 评分副本；ab078 | `restart_windows_desktop_debug.ps1` 平台托管重启；同一评分 thread 恢复 | V14/V17 共用评分根；重启 status SHA `55c511b8...`；stdout SHA `0a19121b...`；task score SHA `8f739eff...` | 2026-09-16 / Codex | 重启前后均为 thread `01a0a5d3-...`、attempt 1、deadline `2026-09-15T18:08:20.503Z`；重启后端口 4183 服务重建，最终得分 75、候选 SHA 不变；等待序列为两次 `POLL_TIMEOUT` 后 `COMPLETED` |
| `windows-astron-release-v15-20260916` | AstronStudio×Windows | V15 | `PASSED` | 同 V00 | `v15-presend-timeout`；ab078 | 9242 不监听触发发送前失败；启动后 `--resume --retry-pre-send-failure`；执行上限 10 秒；同会话只观察恢复 | V15 根 `D:\debug-workspace\web-e2e\windows-as-release-6988b52-20260915-232329\workers\v15\windows-as-release-6988b52-v11-20260915-232329__astronstudio`；queue SHA `b74dedbc...`；automation SHA `a9bfa2b6...`；execution record SHA `197c8d94...`；旧 attempt SHA `9b4bbff5...` | 2026-09-16 / Codex | 旧 attempt `a479f64b-...` 为 `INFRA_FAILED`、`sent_at=null`、Prompt 0 次、候选无变化并已归档；新 attempt `0df7db61-...` Prompt 1 次，状态库复制短暂超时后只观察恢复，最终 `TIMEOUT`，停止/取消/5 秒静默均确认，未伪造成功；V14 同时证明评分轮询超时与 deadline 可区分 |
| `windows-astron-release-v16-20260916` | AstronStudio×Windows | V16 | `PASSED` | 与正式包相同的 orchestrate 0.2.6 / score 4.5.2 / Codex 客户端 | 旧 V07 五题中的 ab095 | 复核模型容量失败后的 `prepare-retry` 原子归档与第二次线程 | 旧 V05 根；scoring state SHA `d826b648...`；attempt error receipt SHA `0446ae9e...`；archive SHA `51b6d14d...`；submission SHA `f197442c...` | 2026-09-16 / Codex | attempt 1 明确 `FAILED: Selected model is at capacity`，候选在归档前/恢复后均为 `d9a55ceb...`；attempt 2 完成，`retry_count=1`，未切换模型，结构化错误回执完整 |
| `windows-astron-release-v17-20260916` | AstronStudio×Windows | V17 | `PASSED` | 同 V00；orchestrate 0.2.6 | V12 评分副本；ab078 | 在 pending submission 持久化后注入发布中断；连续两次 `build-submission` | V14/V17 评分根；中断 pending SHA 与最终 submission SHA 均为 `749aac5df958fb0412b69e1de1073506f5a4c1428a782cbf33ea06383eed6c76`；最终 scoring state SHA `fba290ec...` | 2026-09-16 / Codex | 中断时 phase `FINALIZING`、submission `GENERATING`、pending 存在且正式文件不存在；恢复后 phase/submission 均 `COMPLETED`、pending 清除、attempt_count 仍为 1；第二次构建幂等 |
| `mac-astron-release-v11-20260916` | AstronStudio×macOS | V00/V02/V03/V06/V08/V09/V11 | `PASSED` | `6988b5252bc9140e86dae139fdffbcfc964bcfbf`；execute 1.11.16 / Driver 1.10.18；orchestrate 0.2.6；score 4.5.2；run 1.3.7 | `web-e2e-20260916-095335-mac-astron-release-6988b52-smoke`；ab078 | `$run-web-e2e` 单次恢复指令；执行/评分均单槽；Codex 可见 UI 项目注册；内置 Browser 评分；export-return | worker `/Users/gzx/debug-workspace/web-e2e/mac-release-validation-20260916-6988b52/workers/v11/web-e2e-20260916-095335-mac-astron-release-6988b52-smoke__astronstudio`；execution receipt `bf15df13...`；queue `40cff7ff...`；scoring state `0f8aecf0...`；task score `0a33a1d6...`；submission `36dcce38...`；unit state `225b9f98...`；return ZIP `96fa39f8...`；外部 receipt `bffe999b...` | 2026-09-16 / Codex | probe `ready=true`；1/1 `SUCCEEDED`，执行 115.389 秒，候选 SHA `753f8360...`；项目 ID `83a1206f-...`，评分 thread `01a0a7f7-...`，得分 81；execution/score 双副本哈希一致，三阶段均 `COMPLETED`，return ZIP 4,719,652 字节、51 文件；无人工授权或异常恢复 |
| `windows-workbuddy-release-v00-v02-20260916` | WorkBuddy×Windows | V00–V02 | `PASSED` | `ee70a67b0d53bf700a389b7fbe3f68fde3c3b288`；execute 1.11.21 / Driver 1.8.24；orchestrate 0.2.6；score 4.5.2；run 1.3.8；report 1.0.2 | `windows-wb-release-ee70a67-v03-20260916-0616` | manifest/content SHA 审计；`node --test test`；标准 Windows 前置；Driver `--probe` | `D:\debug-workspace\web-e2e\w\wb3g-061735\manifest.json`；仓库测试 92/92 | 2026-09-16 / Codex | WorkBuddy 5.5.6.0、xopglm52 / full-access、Node 24.17.0；客户端与 Codex 仅监听回环地址；probe 就绪后进入真机题目 |
| `windows-workbuddy-release-v03-v05-20260916` | WorkBuddy×Windows | V03–V05 | `PASSED` | 同 WorkBuddy V00；默认 `run_slots=2` | `windows-wb-release-ee70a67-v03-20260916-0616`、`v05-20260916-0616`；ab063、ab078、ab095、ab097、ab102 | 单题串行；三题串行；五题默认双槽动态补位 | V03 receipt SHA `4c362b3be62a5ce291a34ace24665be4e53f56f92ba84424eecc18ef58a4287f`；V05 receipt SHA `bdd1d0e2fc955b7690dc67f839cceac4010a2b49665945d4e22c1cd667329e18` | 2026-09-16 / Codex | V03 1/1、V04 3/3、V05 5/5 成功；每题 Prompt 仅发送一次、模型/权限一致、候选完整性有效；双槽完成后动态补位，无人工批准 |
| `windows-workbuddy-release-v06-v10-20260916` | WorkBuddy×Windows | V06–V10 | `PASSED` | 同 WorkBuddy V00；Codex Desktop 26.908.9136 | V05 五题 | 可见 UI 精确注册；默认三路评分；submission；return；幂等 import/report | scoring state SHA `2fef2ee8b2bc913eb30df45fff58ea560e678a63d98ab882da0cea42d5074f47`；submission SHA `75cd1a41ae82401276c1f9b4cf3b430d69ab8dd1df9bf4ab5f4622d6ed25ccfe`；return ZIP SHA `a1fa6742bcd1ab98dc7bbf43a78bad2a8c12f139f99f69a55e2ef900e5eabe9b` | 2026-09-16 / Codex | 5/5 完成，得分 77/74/82/82/70，平均 77；回传包 12,874,142 字节；重复导入幂等；JSON/Markdown/三 Sheet Excel 结构检查通过，未把 Excel 原生渲染失败伪装为通过 |
| `windows-workbuddy-release-v11-20260916` | WorkBuddy×Windows | V11 | `PASSED` | 同 WorkBuddy V00 | V03 单题；ab078 | 单个 `$run-web-e2e` Prompt；execute→score→submission→return | 根 `D:\debug-workspace\web-e2e\w\x11r0949`；candidate SHA `a4c33d17...1c644c`；submission SHA `2f988fee...45a58`；return ZIP SHA `c33d4d43...e8ad6` | 2026-09-16 / Codex | 执行、评分、打包均完成；评分 77；return ZIP 2,345,485 字节、57 文件；首个模型侧 `UNKNOWN_STOP_REASON` 样本保留为诊断证据，未折算为题目零分 |
| `windows-workbuddy-release-v12-v13-20260916` | WorkBuddy×Windows | V12–V13 | `PASSED` | 同 WorkBuddy V00 | V03 单题；ab078 | 精确终止控制 Worker 后独立任务接管；Prompt 发送后精确重启 WorkBuddy 并观察恢复 | V12 根 `D:\debug-workspace\web-e2e\w\x12w`；candidate SHA `cf22d1fbf6f7abe9a1ecd7f9dd4d6755bfe6d3229293c0f8ed42f80e80f9f4d9`；V13 根 `D:\debug-workspace\web-e2e\w\x13w` | 2026-09-16 / Codex | V12 沿用同一 attempt/conversation，`WORKER_INTERRUPTED=1`、`WORKER_RESUMED=1`、`PROMPT_SENT=1` 后成功；V13 重启后原会话无唯一 host，安全收口 `INFRA_FAILED`，候选无变化且未重发 |
| `windows-workbuddy-release-v14-20260916` | WorkBuddy×Windows | V14 | `PASSED` | 同 WorkBuddy V00；Codex Desktop 26.908.9136 | V12 评分副本；ab078 | 平台托管重启 Codex；同一评分 thread 原地恢复 | `D:\debug-workspace\web-e2e\w\x12w\v14-codex-restart\status.json`；restart status SHA `eee8f017...6c6cc`；score SHA `64e2bd21...de8d`；submission SHA `7d882aac...55b8e` | 2026-09-16 / Codex | 重启后同一 thread `01a0a809-...`、attempt 1、deadline 不变；中断态映射为 `NEEDS_ATTENTION` 后继续原 thread，最终得分 67，未新建评分 attempt |
| `windows-workbuddy-release-v15-20260916` | WorkBuddy×Windows | V15 | `PASSED` | 同 WorkBuddy V00 | `windows-wb-556-v15-ee70a67-20260916-1048`；ab078 | 9299 未监听触发发送前失败；同端点启动后唯一重试；执行上限 10 秒 | 根 `D:\debug-workspace\web-e2e\w\x15w`；旧 attempt `6743c771-...`；新 attempt `39faff75-...` | 2026-09-16 / Codex | 旧 attempt `sent_at=null`、Prompt 0 次并原子归档；新 attempt Prompt 1 次后进入 `TIMEOUT`，停止/取消、45 秒进程静默和 5 秒候选静默均确认，候选 SHA 前后不变 |
| `windows-workbuddy-release-v16-v17-20260916` | WorkBuddy×Windows | V16–V17 | `PASSED` | 同 WorkBuddy V00 | V12 评分副本；ab078 | 受控无评分产物故障→错误 attempt 归档→唯一重试；pending submission 后注入中断→重复恢复构建 | 根 `D:\debug-workspace\web-e2e\w\x16v17`；attempt error receipt SHA `2c0ab066e01850c3a5e4cd2b00040a7b01c1561a3249f8109f681bfad1c98225`；最终 submission SHA `f409086c988cf93e0ae57bc5d97c979b3edba6ff131169aa80157240634a5feb` | 2026-09-16 / Codex | attempt 1 结构化失败并隔离，attempt 2 同模型完成、得分 67、`retry_count=1`；发布中断时 `FINALIZING/GENERATING` 且仅 pending 存在，恢复后 `COMPLETED`、pending 清除、`attempt_count=1`，第二次构建幂等 |
| `windows-qwen-mainflow-24771ce-20260916` | QwenWork×Windows | V00/V02/V03/V06/V08/V09/V11 | `PASSED` | `24771ce5f86f9bbc9336cf0c0c48effa5f0b2990`；execute 1.11.21 / Driver 1.10.10；orchestrate 0.2.6；score 4.5.2；run 1.3.8；report 1.0.2 | `windows-qwen-mainflow-24771ce-l1-20260916-113542`；ab078 | 单次 `$run-web-e2e` 实施指令；执行/评分均单槽；Codex 可见 UI 项目注册；内置 Browser 评分；export-return | 根 `D:\debug-workspace\web-e2e\q\run-20260916-113542\windows-qwen-mainflow-24771ce-l1-20260916-113542__qwenwork`；execution receipt `ff03bf92...f9e1ce`；queue `3fad47c1...3b5df`；scoring state `43d44e35...2e727`；task score `bf6496d4...d97f9`；submission `04efc832...fd00a`；unit state `0a512f0a...e6265`；return ZIP `d4f0981c...6f8c5`；外部 receipt `f5ce0c6a...2615a` | 2026-09-16 / Codex | probe `ready=true`；1/1 `SUCCEEDED`，执行 980.983 秒，候选 SHA `af442f88...547f9`；项目 ID `ec658d30-...`，评分 thread `01a0a85c-...`，得分 88；终态截图超时后同 run-id/attempt 重启客户端恢复，Prompt 未重发、无人工批准；return ZIP 2,337,860 字节、76 项，无不安全路径、禁止目录或浏览器 profile；三阶段均 `COMPLETED` |

### 4.3 本轮 macOS 冒烟边界

当前 revision 的 AstronStudio 单 L1 已从只读 probe 继续完成执行、评分、submission 和离线回传。执行只发送一次 Prompt，回读 GLM-5.2 / High / full-access，execution receipt `integrity.valid=true`；Codex Desktop 通过可见 UI 注册精确评分项目，独立评分 thread 使用内置 Browser 取得桌面和窄屏证据，得分 81；评分服务和运行时副本已清理，execution/score 候选 SHA 均保持 `753f8360...`。最终 unit state 中 execute、score、package 都为 `COMPLETED`，因此 AstronStudio×macOS 达到“主流程生产可用”。

本轮没有重复执行三题串行、五题默认三槽、三路评分动态补位、管理员 import/report 或 V12–V17。旧 macOS 批次证明这些功能曾在相同客户端系列上工作，但不能直接升级为当前 revision 的 `PASSED`；矩阵继续保留 `IN_PROGRESS`/`NOT_STARTED`，对应“并发生产可用”和“无人值守高可用”尚未完成。生产投入采用渐进方式：首个正式批次先执行 3–5 个 L1 canary，execution receipt、评分和回传均通过后再放大，不再为了上线前形式完整而重跑全部历史回归。

macOS 的 AstronStudio、WorkBuddy 和 QwenWork 当前均记录 `terminal_process_cleanup.supported=false`；这表示本平台没有执行 Windows 等价的候选进程枚举与终止，不表示已证明没有残留进程。QwenWork V03 终态后仍观察到其自启的 headless Chrome/预览服务残留；完整生产验收必须单独补齐 macOS 精确进程收口，不能以执行回执有效替代该平台能力缺口。

用户为 AstronStudio 增加录屏权限并主动重启后，只读 probe 返回 `ready=true`，客户端仍为 3.0.0-alpha.19，模型/推理强度为 GLM-5.2 / High，权限为 full-access，9240 调试端点正常。但 SQLite 状态库仍投影出一个来自已完成 V05 任务的 `open_turn`，而对应 latest turn 已是 `completed`、session 已 ready。该不一致未影响 V06–V09，但当前重启保护会因此失败关闭；在定位投影清理机制并完成受控重启验收前，V13 仍保持 `NOT_STARTED`。

### 4.4 本轮 QwenWork Windows 主流程边界

当前 revision 的 QwenWork 单 L1 已完成 probe、执行、评分、submission 和离线回传。执行只发送一次 Prompt，回读标准｜Qwen3.8-Flash / full-access，execution receipt `integrity.valid=true`；Codex Desktop 通过可见 UI 把评分目录精确注册为项目，独立评分 thread 使用内置 Browser 取得桌面、交互和窄屏证据，得分 88；评分服务和运行时副本已清理，execution/score 候选 SHA 始终为 `af442f8846514005e1858a4b3e300fbcfb3c84f80f65e46471f538fcb89547f9`。return ZIP 与外部 receipt 的身份和 SHA 一致，包内 submission SHA 等于原件，且未发现不安全路径、`.git`、`node_modules`、运行时缓存或 Chromium profile。最终 unit state 中 execute、score、package 均为 `COMPLETED`，因此 QwenWork×Windows 达到“主流程生产可用”。

本轮没有重跑三题串行、五题默认三槽、默认并发评分、管理员 import/report 或 V12–V17。旧 Windows 批次证明这些能力曾在 QwenWorkCN 1.0.5.0 系列工作，但不能直接升级为当前 revision 的 `PASSED`；矩阵继续保留 `STALE`/`NOT_STARTED`。生产投入采用渐进方式：首个正式批次先执行 3–5 个 L1 canary，execution receipt、评分和回传均通过后再放大；并发或异常恢复失败时允许人工介入，不为上线前形式完整而大规模重跑全部历史回归。

## 5. 历史证据索引

以下只用于定位旧结果和决定哪些项为 `STALE`，不等于当前正式分发包已通过对应的功能准入项。

| Harness×OS | 历史范围 | 本地证据 |
| --- | --- | --- |
| WorkBuddy×macOS | 五题执行、评分、回传、报告及恢复边界 | `/Users/gzx/debug-workspace/web-e2e/web-e2e-20260908-123216` |
| AstronStudio×macOS | 单题 execution→score→submission→return；另有串行/并发执行 | `/Users/gzx/debug-workspace/web-e2e/astronstudio-full-flow-validation/workers/web-e2e-20260909-092954__astronstudio` |
| QwenWork×macOS | 三题执行、评分、submission、return | `/Users/gzx/debug-workspace/web-e2e/qwenwork-concurrent3.q563DW/worker/web-e2e-20260909-164755__qwenwork` |
| AstronStudio×Windows | 早期全流程与恢复验收 | 已由 `6988b525...` / AstronStudio 3.3.1.277 的 V00–V17 仓库内证据替代；旧证据仅用于问题对照 |
| WorkBuddy×Windows | 5.5.3 历史全流程与恢复验收 | 已由 `ee70a67` / WorkBuddy 5.5.6.0 的 V00–V17 当前证据替代；旧证据仅用于问题对照 |
| QwenWork×Windows | 1.0.5.0 历史批次覆盖全流程和部分恢复边界；当前 revision 已重绑一个 L1 主流程闭环 | 当前 V00/V02/V03/V06/V08/V09/V11 已通过；V04/V05/V07/V10/V12–V15 保留 `STALE`，V16/V17 为 `NOT_STARTED` |

## 6. Windows Codex 正式打包与继续验证 Prompt

### 6.1 在 Windows 本地生成正式包

代码推送后，在 Windows Codex 的仓库任务中直接输入下面 Prompt。控制任务会在本机生成两个正式批次：自建 40 题和开源 120 题；每个批次同时包含 AstronStudio、WorkBuddy、QwenWork 三个 Harness 的 execution/scoring 包，因此不需要从 macOS 传包。

```text
请使用 $prepare-web-e2e-workspaces 在当前 Windows 仓库中为 Web E2E 当前发布候选生成正式评测包。如果 Windows 无法解析仓库 .agents/skills 下的符号链接，则直接读取并遵循 tools/report/skills/web-e2e/prepare-web-e2e-workspaces/SKILL.md，不要复制或改写 Skill。

先完成发布门禁：
1. 使用 git rev-parse --show-toplevel、git rev-parse HEAD 和 git status --short 确认仓库、完整 revision 和工作树状态；从本清单 3.1 读取“正式分发包实现/source revision”，执行 git merge-base --is-ancestor <该revision> HEAD，退出码必须为 0。Web E2E Skill、准备脚本、tasks/07_Website_Generation 和 tasks/extension/07_Website_Generation 存在未提交修改时停止，不得带脏源码打包。
2. 检查可用的 Python 3 和 PyYAML；缺失依赖由控制任务安装到仓库自己的 Python 环境，不得安装到任何题目 workspace。
3. 从 tasks/extension/07_Website_Generation 按文件名排序收集全部 Markdown 用例 ID，必须恰好 40 个；从 tasks/07_Website_Generation 按文件名排序收集全部 Markdown 用例 ID，必须恰好 120 个。数量不符立即停止，不猜测、不跳题。

使用同一个本机时间戳，在 report-workspace/web-e2e-automation-packages 下生成两个全新且不覆盖历史目录的批次：
- web-e2e-<时间戳>-custom40：上述 40 个自建用例；
- web-e2e-<时间戳>-opensource120：上述 120 个开源用例。

两个批次都指定 --harness astronstudio、--harness workbuddy、--harness qwenwork，metric profile 使用 auto，显式传入 --include-execution-record；不预填模型和推理强度。应直接调用仓库标准准备脚本，不手工拼 ZIP。

生成后逐项校验：
1. 两个 batch_manifest.json 的 source_revision 都严格等于开始时记录的完整 HEAD，每个批次的 task_ids 分别为 40/120，harnesses 都严格包含 astronstudio、workbuddy、qwenwork。
2. 每个批次均存在三 Harness 各自的 execution.zip 和 scoring.zip、报告配置、`packages/skills-build-manifest.json`、`packages/skills-manifest.json`，以及五个版本化 Skill ZIP；统一构建清单验包通过，`execution_record_included=true`。
3. 两个批次中五个 Skill 的名称、版本、运行 content SHA、完整构建 content SHA、ZIP SHA 和 `skill_set_sha256` 逐项相同，五个 ZIP 逐字节一致；分别使用本次 manifest 验证文件，不与旧正式包 SHA 比较。
4. 逐个打开 6 个 execution ZIP，自建批次每包必须包含 40 份 `execution_record.json`，开源批次每包必须包含 120 份；审计 execution ZIP 不含 Ground Truth、Rubric、checker、eval 或 gt，scoring ZIP 不含候选 workspace、PROMPT.md 或 execution_record.json。
5. 确认两份报告配置的 `configuration_status=requires_model_mapping`；在执行/评分阶段可以保持该状态，生成正式报告前必须填写三个 Harness 的 `model_id`，并按实际评测配置展示名和推理强度。
6. 把生成路径、批次 ID、完整 source revision、五个 Skill 版本/content SHA/ZIP SHA、Skill set SHA 和校验结果写入 docs/design/web-e2e/Web站点端到端自动化评测生产验收清单.md；只更新 P2 的新正式包证据，P10 必须等 macOS/Windows 同 revision 对账和最小 smoke 后才能标为 PASSED。本轮不要执行题目、提交或推送。
```

### 6.2 使用最新正式包执行 canary 或身份漂移复验

P2 通过后，在 Windows Codex 的仓库任务中输入下面 Prompt。它适用于新正式包的小批量 canary，也适用于 Harness、Skill、模型或系统身份变化后的受影响项复验：

```text
请以仓库 docs/design/web-e2e/Web站点端到端自动化评测生产验收清单.md 为唯一任务清单，使用 3.1 登记的最新正式分发包验证我指定的 Harness。

先执行只读检查：
1. 用 git rev-parse --show-toplevel 和 git rev-parse HEAD 确认仓库及 revision，读取 3.1 登记的正式分发包 source revision，确认它是当前 HEAD 的祖先；同时确认 Web E2E Skill、准备脚本和题目目录没有未提交修改。
2. 只使用 3.1 登记的自建/开源批次，逐项复核 source_revision、Skill 版本、content SHA、ZIP SHA、`execution_record_included=true` 和三个 Harness 范围。任一项不一致时停止，不使用旧包或临时重打包。
3. 只读发现目标 Harness 和 Codex Desktop 的真实可执行程序完整路径，检查对应本机 CDP 端口监听者和完整进程路径。不要按进程名批量结束程序。
4. 读取目标 Harness 的客户端版本、Driver、模型、推理强度、权限和操作系统身份，与本清单已有证据对比。身份一致时执行 1–3 个 L1 canary；任一关键身份变化时，将受影响 V 项标为 `STALE`，从 V02 只读 probe 和 V03 单 L1 开始复验。

按上一步确定的范围执行 canary 或单项复验。每完成或失败一个 V 项，都更新清单中的单项验收记录与矩阵状态，写明命令或原 Prompt、批次/任务 ID、绝对证据路径、receipt/SHA、时间和错误；不要把代码测试当作真机通过。

候选 execution/score workspace 在被评 Harness 完成后不可修改；端口冲突只允许修改 private-scoring/runtime-workspace。任何候选哈希漂移、身份不一致、活动任务不唯一或状态不明确都失败关闭。若需要重启承载当前任务的 Codex Desktop，先持久化状态，并使用 run-web-e2e 的 restart_windows_desktop_debug.ps1 计划任务入口；不要让控制任务直接退出或普通 Start-Process 重启自身。

本轮先做到清单中当前指定的下一个 V 项，通过后给出证据摘要和下一项；不要一次执行全部高耗时用例，也不要提交或推送，除非我另行要求。
```

## 7. 发布判定

发布结论必须使用第 2 节的三级准入名称，并附带当前 revision、客户端和 Skill 身份。一个当前身份的完整 L1 worker 闭环通过后，可以先标记“主流程生产可用”并以 3–5 个 L1 canary 启动正式评测；并发执行、并发评分和报告在当前身份下通过后，升级为“并发生产可用”；V12–V17 全部通过或经评审明确不适用后，才标记“无人值守高可用”。

`BLOCKED`、`STALE` 或缺失证据不能折算为更高层级。较低层级不要求为补齐更高层级而在上线前机械重跑全部历史用例，但必须保留未覆盖项、值守要求和失败后的人工处置边界。任何关键 identity 变化仍按第 2 节转为 `STALE`，至少重跑 probe 与一个 L1 完整闭环。
