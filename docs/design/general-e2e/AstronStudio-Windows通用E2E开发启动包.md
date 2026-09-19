# AstronStudio Windows 通用 E2E 开发启动包

日期：2026-09-19。用途：在新的 Windows 开发任务中，独立完成 AstronStudio General E2E 平台适配和真机验收，无需读取 macOS 控制任务的聊天记录。

每次开始或恢复，先读 [macOS / Windows 协作台账](../e2e/collaboration/README.md)与 [Windows 任务卡](../e2e/collaboration/tasks/WIN-ASTRONSTUDIO-GENERAL.md)。公共基线、未处理交接和下一项从仓库读取；本文只提供 Windows 实施细节，不能替代持续协作台账。

**契约与 macOS 最终 smoke 修复合入、公共接口基线明确后，Windows 可以与三个 macOS Harness 任务并行开发，不必等待新增指标全部实现。** Windows 使用独立 worktree，先验证本机执行和采集，再完成本机评分闭环。Windows 执行、macOS 评分另作交接验收，不替代 Windows 本机能力。

当前开发基线另见 [COMMON-003](../e2e/collaboration/handoffs/COMMON-003.md)：本轮集成三个 macOS 开发 Driver、升级 execute Skill 并修复 Qwen CLI 路径别名，不改变 Windows wire 或 cleanup 要求。Windows 处理最新交接后继续 G5-01，不等待 Mac canary 完成。

当前公共正式收口接口见 [COMMON-002](../e2e/collaboration/handoffs/COMMON-002.md)：新 Windows 状态使用 CB-A，采集使用 trace-index v2 与通用 finalizer，必须提供实际 Windows cleanup hook。先完成该交接列出的基线回归，再推进本机 G5-01；旧 AstronStudio macOS wrapper 不代表 Windows 支持。

本文是开发交接说明，不是 Windows 已支持的声明。核验源码为 `457e35560ea5cd090db1ce8b68c747de95ae3622`，**这不是后续启动时的冻结基线**。实际启动时必须重新核对入口、契约和能力状态。技术验收更新[实现计划与验收清单](通用场景端到端自动化评测实现计划与验收清单.md)，代码采用状态与交接接收写入任务卡，本文不再维护一份 PASS 表。

## 1. 开始前只需明确这些信息

| 信息 | 来源与缺失时处理 |
| --- | --- |
| 冻结基线 SHA | 从协作台账 `baseline.md` 读取已发布的 40 位 SHA、必要接口与交接；Windows 核对实际提交并回写任务卡，无需从另一聊天索取。未发布时可先盘点环境，不把任意“最新 HEAD”当作已协调基线 |
| 工作目录与分支 | 从当前打开的主项目根目录创建 `.agents/astronstudio-windows-general-e2e`，分支为 `feat/astronstudio-windows-general-e2e`；不得在原工作分支改代码 |
| 调试产物根目录 | 默认建议 `C:\e2e-debug\astronstudio-general`；先验证可写且与候选、源码和正式发行目录隔离，冲突或不可写时选择另一独立短路径并记录 |
| 执行配置 | 优先读取 Windows 本机已明确配置的模型、推理强度和权限，并冻结实际值；不照搬 macOS 的模型、版本、权限或路径 |
| 评分配置 | 默认目标为 `codex-agent-judge-v1`；从本机批次配置读取明确的模型/推理强度。API Judge 单独冻结 endpoint、模型、预算和凭据来源；缺少配置时只阻塞对应真实评分，不阻塞开发、fixture 和只读 probe |

后两项无法从本机配置确定时，在需要真实调用前一次性列出缺项。密钥只使用本机私有配置，文档与提交不记录密钥。所有任务 Workspace、数据库快照、候选、评分和报告留在本地；本地执行不表示模型服务必须离线。

控制任务交付基线时，将契约版本、macOS smoke 证据索引、共用接口/指标变更的提交及未完成项、共享文件归属写入公共基线和交接文件。若已有发行包，附 source revision、dataset digest 和包 SHA；如果 Windows 开发需要重建，则记录新的实现 SHA 和发行身份，不能借用旧包的 SHA。

## 2. 可直接复制到 Windows 新任务的 Prompt

日常继续工作使用协作台账中的短 Prompt 即可。首次开发也可使用下方完整 Prompt；它从仓库解析基线，不要求人工重复传递 SHA 或历史聊天。Windows 本地项目路径、安装位置和运行时由开发任务自行探测。

```text
任务ID=WIN-ASTRONSTUDIO-GENERAL
BASE_SHA=从 docs/design/e2e/collaboration/baseline.md 读取已发布基线并核验

请在当前 Windows 本地电脑的 WildClawBench 项目中，实施 AstronStudio Windows 的 General（通用场景）端到端自动化评测适配与真机验收。请直接开展工作，不能只输出方案。本任务不依赖其他聊天记录，以仓库契约、源码和本机实际证据为准。

启动与工作边界：
1. 先读取 AGENTS.md、docs/design/e2e/collaboration/README.md、baseline.md、本任务卡及所有目标含本任务ID/ALL的正式交接，再读取 docs/design/general-e2e/AstronStudio-Windows通用E2E开发启动包.md。按协作台账检查同步来源、Git/worktree、本机现场和已采用基线，处理未接收交接；核对 BASE_SHA 的契约、macOS 最终 smoke 证据与公共接口。不得把旧版本号或历史通过状态当作 Windows 证据。
2. 在当前打开项目根目录的 .agents/astronstudio-windows-general-e2e 创建独立 worktree，分支 feat/astronstudio-windows-general-e2e，从已核验且包含 BASE_SHA 与最新交接台账的 SYNC_SHA 开始。若路径/分支已存在，先核对身份、未提交工作与本机运行，符合本任务才恢复并按协作规则更新；不删除、不重置、不覆盖。记录源码基线、SYNC_SHA 和实际 HEAD，后续命令显式使用此 worktree。保留原工作分支和其他 worktree 的内容。
3. 调试、探针、临时构建和真机批次使用独立本地短路径，优先 C:\e2e-debug\astronstudio-general；不要放进源码仓库的 report-workspace。代码及脱敏的最小 fixture/证据索引放在本 worktree，完整原始数据留在本机证据目录。任务产物不使用云电脑。
4. 采用统一契约的共用章与 General 章；Web 章只用于识别差异，不能用 Web E2E 或旧 eval_e2e 替代 General。参考现有 macOS 代码但保留真实平台边界，不删除平台检查来假装支持 Windows。

实施要求：
5. 先完成 G5-01：环境清单、应用发现、CDP 进程/端口/页面身份、本机状态库位置与只读 probe。探针不发送 Prompt、不顺便重启。CDP 未开启时，把启动/重启作为独立步骤：确认无冲突活动工作后，仅对本任务目标应用开启 loopback 调试并复核身份；发现无关活动任务就保留现场。
6. 实现 Windows 原生 launcher/probe、单题和队列入口、目录选择与完整路径回读、配置回读、一次发送、原生 thread/turn/session/cwd 绑定、终态判断、停止和原会话恢复。UI 单槽、后台执行先单槽验收；通过后再验证默认三槽与五题动态补位。不得宣称未测并发值或架构已支持。
7. 复用公共状态机、契约和解析逻辑，Windows 层处理安装/进程/路径/编码/命令/SQLite 快照差异。不得复制整套 macOS 实现形成第二套业务语义，也不得手改 vendor 生成副本。共用 Schema、指标公式、注册入口、发行机制若需改变，先提交具体变更建议和受影响文件清单；接口已定则直接按其实现，接口未定只隔离受阻部分并继续独立工作。
8. 按 prepare → execute → collect-evidence → score → package → import-return → report 推进，核验正式回执、轨迹、候选哈希和报告一致性。轨迹需被真实 grader 消费；文件任务和纯回复任务都必须验收。执行包不含 rubric/GT/grader，评分只用冻结候选和受管运行时。
9. 对现有 token、缓存、请求、工具、耗时字段逐项做原生对账。新增任务异常率、工具成功率、已结算积分均值、缓存命中率、平均 token 遵守共用契约，不另建 Windows 专用公式。共用字段尚未落地时先保留原始证据、字段映射和 fixture，不向严格 v1 Schema 私加字段。未知量保持 null、known subtotal 与 coverage；不可为补指标重发任务。
10. AstronStudio 积分只把 turn.billing.settled/chargedPoints 作为待验证线索，核对 Windows 实际事件、单位、结算范围和去重；工具有 result/completed 不等于成功；中途失败后正常完成不等于任务最终异常；重试消耗不得丢失。
11. Windows 本机评分和 Windows 执行→macOS 评分分别验收。没有 Mac 接收方时先完成导出、身份/哈希检查和 Windows 本机闭环，将 WIN-07 标为待协调，不能用 Windows 自导入冒充跨机验证。API 配置缺失时保留 WIN-10 缺口，不静默换后端。
12. 加固需验证发送临界点、活 Worker 重复接管、Harness/控制/评分客户端重启、超时停止、精确进程树清理、SQLite 热写、路径/编码、未知授权、冻结后漂移及重复/冲突导入。控制端重启必须先有独立存活的托管入口和恢复状态，不能先把自身关闭。保留失败现场，不按进程名批量杀进程、不代答、不修候选。
13. 采用固定 S1–S5、原题时限和数据集 digest，不改题目/grader 以绕过 Windows 差异。故障注入另建验收批次。执行重跑按当前契约准备独立 unit，评分重跑引用原冻结候选并建立独立评分 attempt。
14. 完成 Windows 仓库外发行验证，核对单 Skill/suite、共享组件闭包、依赖锁、版本和 SHA；Windows 专属改动需提供公共回归结果和待由 macOS 执行的复验清单。不要在 Windows 伪造 macOS 真机 PASS。

交付与推进：
15. 每阶段更新自己的协作任务卡、交接接收结果和既有 G5/WIN 验收记录，并映射统一契约 C/G 与 CV/GV；记录命令、退出码、身份、证据路径/哈希、结论和下一步。有跨任务影响时新增 handoff，明确另一平台要做的动作；不能只在聊天总结。本文第 6 节规定的材料必须交付。
16. 先处理会阻断本轮执行的交接，再完成本任务卡当前下一项。首次实施按 G5-01、S1/S4 单槽执行采集、五题、本机评分、恢复和脱仓验证推进；已有进展不从头重做。首次汇报给出实际 worktree/分支/SHA、已接收变更和环境检查/probe 结果或具体缺口。
17. 只在缺少关键配置、权限或外部协作确实阻塞时汇总询问；继续所有不依赖它的工作。真实失败如实报告，不用静态测试代替真机验收，不因为新增指标不可用而阻塞可完成的主流程。
18. 本任务交付到代码、测试、证据与可审核差异。提交/push 按本次或既有授权执行，已有授权不重复询问；没有远端发布授权则保留待发布材料。只有集成负责人合并公共分支，不因开发分支已 push 就标为集成。commit 使用 type(scope): 中文说明且只含相关文件。最终报告明确实现、fixture、真机、已发布/集成和待接收范围。
```

## 3. 源码定位与修改归属

阅读顺序为[统一接入契约](../e2e/端到端自动化评测Harness接入契约.md) → [General 契约决策](通用场景端到端自动化评测契约决策记录.md) → [运行 Schema](../../../eval_general_e2e/contracts/README.md) → [技术方案](通用场景端到端自动化评测技术方案.md) → [验收清单](通用场景端到端自动化评测实现计划与验收清单.md)。执行各阶段时，再读取 `tools/report/skills/general-e2e/` 下对应 `SKILL.md` 和 references。

以下是核验基线中的真实入口，启动时用 `rg` 复核；文件改名应追踪替代入口，不能依赖本文行号。

| 入口/范围 | 作用与 Windows 工作边界 |
| --- | --- |
| `tools/report/e2e-shared/desktop-app-discovery/` | 已有 Windows 发现分支；复用安装、注册表、进程候选核验，需 Windows 真机证据 |
| `tools/report/skills/web-e2e/run-web-e2e/scripts/start_windows_desktop_debug.ps1` 与 `restart_windows_desktop_debug.ps1` | 已有原生入口线索，支持 `AstronStudio` 选择；必须审查身份/活动任务/恢复语义后复用或提取。默认 `All` 不可用于本次目标应用操作，不能让 General 发行包依赖未声明安装的 Web Skill |
| `tools/report/skills/general-e2e/execute-general-e2e/scripts/` | `probe_astronstudio_macos.mjs`、`execute_astronstudio_macos.mjs`、`run_astronstudio_macos_batch.mjs` 当前有 darwin 门禁；新增原生 Windows 路径并抽取共用逻辑，旧 macOS 入口保持兼容 |
| `tools/report/skills/general-e2e/collect-general-e2e/scripts/` | 复核 trace、usage、SQLite 热写快照、finalize 的平台假设；不能只做到点击与执行就结束 |
| `eval_general_e2e/adapters/astronstudio/`、`eval_general_e2e/adapters/components.py` | 现有组件绑定与校验；后者涉及其他 Harness 的公共扩展，不由 Windows 独自另造一套注册机制 |
| `tools/report/skills/general-e2e/run-general-e2e/scripts/run_general_e2e.py` | 当前绑定 AstronStudio execution-state；检查 Windows 是否兼容现有状态，不能仅改 driver 名而漏掉恢复/采集门禁 |
| `tools/report/skills/general-e2e/orchestrate-general-e2e/`、`score-general-e2e/`、`report-general-e2e/` | Windows 本机规则运行时、Codex/API 评分、Excel 引擎及回传链路；已有 `.cmd` 或 PowerShell 文件不证明完整闭环通过 |
| `tools/e2e-build/build_skill_packages.py`、`tools/report/e2e-shared/components.json` | 公共构建与组件来源；新增平台文件必须进入闭包，生成副本通过构建更新 |
| `tests/general_e2e/` | 契约、Driver、trace/usage/finalize、编排、运行时、回传/报告和打包测试；Windows 另加必要平台 fixture |

**Windows 任务负责平台实现和证据，控制任务协调公共语义与集成。** macOS WorkBuddy General、QwenWork General、DoubaoWork Web 与此任务可并行；共享注册、Schema、指标聚合、公共队列和发行机制由一个变更集中处理。Windows 可提出和实现经协调的公共修复，不要求所有公共文件绝对只读。兼容性提交以明确 SHA 交接，闲置且干净的开发 worktree 再更新；真机批次中途不切换代码和已安装 Skill。

Git 无文本冲突仍需检查语义冲突。合并前重点复核平台默认值、状态版本、指标分母、生成文件与源文件一致性，以及 macOS 原有恢复行为。两台机器的桌面互不争用；同一 Windows 桌面上多个控制进程仍需互斥，不能认为 worktree 锁自动覆盖整台机器。

## 4. 分阶段清单与完成条件

以下顺序优先尽早证明 Windows 本机可运行。跨机交接可在本机闭环后补验；这改变执行先后，不改变既有 G5 依赖与完成定义。

| 阶段 | 具体工作 | 完成证据与既有编号 |
| --- | --- | --- |
| A：冻结输入与平台盘点 | 检查基线、worktree、契约/Schema；记录 Windows build/架构、安装路径、客户端和运行时版本、DB、CDP；区分 PowerShell 5.1/7、原生 Windows 与 WSL | 启动快照、只读 probe、应用/端口身份；G5-01、WIN-01/02，CV01/02/16 |
| B：最小执行与正式采集 | S1 文件任务、S4 纯回复各单槽执行；验证目录/模型/权限、一次发送、原生身份、终态、原始/标准轨迹、资源、冻结和 collect receipt | G5-02 的首批证据，WIN-03/05/06，CV03/07/11/12/13，GV02/03/04；此时不宣称五题并发完成 |
| C：五题及动态补位 | 先三题串行，再 S1–S5 五题；UI 单槽，后台默认三槽；同名目录和各 session 授权无串题 | G5-02、WIN-04；CV10/GV08；重复运行使用独立 unit，失败和消耗留档 |
| D：Windows 本机完整闭环 | 受管规则 Worker、独立 Codex 评分、显式 API 评分；submission、package、import、JSON/Markdown/Excel | G5-04、WIN-08/09/10/14；GV05/06/07；三个评分类型均有证据，不补无效零分 |
| E：恢复与故障加固 | 发送临界点、控制者接管、三类重启、deadline/停止确认、迟到子进程、未知授权、冻结漂移、回传冲突 | G5-05、WIN-11/12/13；CV04/05/06/08/09/14。安全失败且不重发可为对应故障项的正确结果 |
| F：跨机交接与发行 | Windows 执行包交给 Mac 本地评分，再回 Windows 导入核验；Windows 仓库外单 Skill/suite，短路径与声明并发复验 | G5-03/06、WIN-07/15；CV15/16。需 Mac 端真实回执；未安排接收方则保留该项缺口 |

固定用例沿用数据集 manifest 顺序与 digest，不以五道近似题替代：

| 用例 | 完整 task ID | 类型 |
| --- | --- | --- |
| S1 | `02_Code_Intelligence_task_001_temperature_cli_fix` | automated |
| S2 | `06_Safety_Alignment_task_001_suspicious_installer` | automated |
| S3 | `01_Productivity_Flow_task_005_support_handoff` | hybrid |
| S4 | `01_Productivity_Flow_task_003_retro_agenda` | llm_judge |
| S5 | `03_Social_Interaction_task_003_colleague_leave_reply` | llm_judge |

Windows 专项应覆盖盘符/反斜杠、中文/空格、短路径与过长路径拒绝、大小写比较、UTF-8/CRLF、工具命令前置检查、文件占用、SQLite DB/WAL 一致快照、进程创建时间/命令行、子孙进程和 PID 复用。symlink/junction/reparse point 按现有候选与解包策略允许或拒绝，不能跟随链接读写外部路径。缺 Python/工具/环境/Skills/Warmup 属于环境前置缺口，不改题、不改候选、不据此给能力零分。

首次 scope 到五题平台接入与声明能力的加固。`WIN-16` 的 60 题全量、裁判校准和更高并发属于后续扩容，未运行就保留 `NOT_RUN`；五题完成不等于 G6 或全部 Windows 发布门槛完成。

## 5. 指标协作和验证入口

共用指标协议冻结后，Windows 优先交付原生字段映射、脱敏样本、去重与终态判断。公共聚合尚未完成时，这些工作可独立推进。参见统一契约 C15/C16：

- 任务异常按最终执行状态统计，和工具中途错误、评分异常分别报告；未知终态不算正常。
- 工具成功需明确业务结果，不能把所有 `tool_result` 当成功；重试新调用分别计数。
- 积分须验证实际结算、单位和 attempt 归属，不能从 UI 消耗或 token 猜金额；缺失不填零。
- 缓存率用同范围 `Σcache_read / Σcache-inclusive input`；平均 token/积分声明所选 attempt 或全部尝试范围，不能漏掉失败重试。
- 不完整值使用 `null + known subtotal + coverage`；完整比率/均值未知时，完整子集结果必须标注覆盖，不能把小计除以全体伪装完整指标。

在**开发 worktree 根目录**选择已核对的 Windows Python 与 Node 运行时。以下为现有入口，可先做基线检查；不是宣称已在 Windows 通过，也不是完整测试集：

```powershell
python -m eval_general_e2e skills --json
python -m eval_general_e2e check-layout
python -m unittest tests.general_e2e.test_contracts tests.general_e2e.test_shared_components -v
node --test tests/general_e2e/desktop_app_discovery.test.mjs
python tools/e2e-build/build_skill_packages.py --help
```

`python` 若未指向项目运行时，改用核对过的绝对可执行路径。按依赖锁安装缺少的测试依赖，基线失败与本次回归分别记录；不临时升级依赖以掩盖失败。根据改动运行 `tests/general_e2e/` 中 execute/batch、trace/resource/finalize、local_scoring_runtime、scoring_orchestration、run/report、release/build 等聚焦测试。公共变更还需受影响的 Web 和 macOS 回归；fixture 通过不能代替目标平台真机。

Windows 执行入口尚未完成时不提供假想的 `execute_astronstudio_windows` 命令。开发任务应将最终真实命令、PowerShell 引号处理、参数、输出目录、resume 和恢复前置条件写入对应 Skill references 与验收证据。

## 6. 每轮交付与阻塞处理

每轮至少交付以下材料，后续任务可据此继续：

1. **启动快照**：主项目/worktree、分支、base/implementation SHA、dirty 状态、契约版本、OS/客户端/Driver/运行时、dataset/Skill/组件身份、请求/实际配置、调试根目录。本地可保存 `kickoff.json`，这是开发记录，不是新增运行 Schema。
2. **变更清单**：Windows 专属文件、公共文件、生成文件、公共依赖 SHA、macOS 需复验的行为；不能只给一个提交号。
3. **测试记录和真机证据索引**：命令、退出码、完整 task/attempt/session/thread/turn、目录、轨迹范围、收口与候选哈希、回执、报告、原始证据位置。仓库只纳入必要脱敏 fixture/索引，原始证据保留本地并以哈希定位。
4. **符合性与支持边界**：按现有 G5/WIN 更新状态，映射 C/G/CV/GV；说明主流程、并发、恢复、两种评分后端、本机/跨机分别到哪一步。缺失指标单列来源和覆盖，不能冒充全覆盖。
5. **恢复交接**：把当前队列/attempt、仍活动的 Worker/客户端/任务进程、是否冻结、下一个唯一验收项、实际 resume 命令与条件写入任务卡；跨任务影响另写交接文件。下一任务先检查状态，不能重新初始化覆盖原批次。

| 情况 | 处理方式 |
| --- | --- |
| 台账尚未发布冻结 SHA 或契约/接口尚未合入 | 继续本机只读盘点和差异分析；在任务卡记录所需提交及 COMMON 依赖，不猜测兼容基线 |
| 共享接口待协调 | 给出最小提案、文件/字段与样本；继续 Windows 平台层和 fixture，不分叉公共语义 |
| 登录、模型/评分配置或 OS 权限缺失 | 汇总具体缺项，只暂停依赖该配置的真机步骤；不扩大权限、不代填凭据 |
| 探针发现其他活动任务、未知发送状态或停止未确认 | 保留状态与原生身份，停止新投递；不重发、不以批量杀进程清场 |
| 新增积分/缓存等字段暂不可验证 | 保留原始证据与 null/覆盖，继续可验证主流程 |
| 没有 Mac 跨机接收方 | 完成本机闭环、导出与静态校验；WIN-07 记录待协调，不能标 PASS |

最终交接明确列出已完成与缺口，并说明能否声明 Windows 单槽主流程、默认三槽并发或无人值守能力。接口契约与现有验收清单共同决定结论，不能以“代码已写完”“CDP 已连通”作为完整验收。
