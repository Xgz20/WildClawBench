# General E2E 开发接续入口

更新：2026-09-23（Asia/Shanghai）。这是当前开发顺序、Harness 集成状态和下一步的唯一维护入口。新会话先读本文，再按当前任务读取对应 Skill、源码与证据；无需通读历史聊天或旧并行台账。

## 当前路线与工作边界

先串行完成 **macOS：AstronStudio → WorkBuddy → QwenWork → DoubaoWork 的 General E2E**，进入实际评测，再开展 Windows 支持。AstronStudio 已有受控生产证据；WorkBuddy 新 v2 包已完成 5 题、3 路并发执行/采集/评分编排/回传/报告 canary，原生请求峰值 3，评分仍有评测异常和容量失败，完整生产准入继续按剩余故障矩阵收口。DoubaoWork 原任务是 Web，现改为优先建设 General；Web 后续收口暂缓。

- 唯一开发目录：`/Users/gzx/Project/GitHub/xgz/ai/evaluate/WildClawBench/WildClawBench`；分支 `feature/astroncode-eval`。后续直接在当前主工作区开发、验证和提交；控制 worktree 已完成汇入，仅保留审计。
- 直接在工作区分支串行修改；不创建平台任务、subagent 或新 worktree，不恢复旧并行任务。桌面验证无需申请时段，但操作前检查真实活动任务、草稿、进程和 CDP 身份，保留无关现场。该约束针对开发派发，评分所需的独立 Judge 任务仍按阶段 Skill 创建。
- 每完成一个可验收事项，更新本文对应行和必要证据索引，运行受影响检查，单独提交中文 `type(scope): 中文说明`。本地提交；当前不 push。
- 调试、smoke、临时包、运行与评分产物：`/Users/gzx/debug-workspace/e2e-evaluate`。正式发行：主检出的 `report-workspace`。任务产物均在本地。
- 先用值守单槽验证全链路，再验证五题默认三路执行、动态补位和恢复不重发。**开发串行不等于评测串行**。WorkBuddy 已完成三槽调度、补位和完成态恢复，不能由发送后未结束的任务数推定原生执行并发；无人值守 Worker 崩溃恢复、Apple Silicon、更高并发和全量 60 题另行扩容。
- 客户端版本记录为兼容性元数据，不设精确版本白名单；根据实际能力、原生字段、UI 行为与回归证据判断兼容性。冻结的运行/评分包身份仍需校验。
- 题目 `timeout_seconds` 仅为兼容元数据，**不限制被评测 Harness 总执行时长，也不参与能力评分**。执行等待可信终态、明确异常或人工处理；UI/CDP 操作、启动/停止、身份绑定、进程清理、评分 Worker/API/线程 deadline 继续独立生效。

## 代码基线与发行边界

2026-09-21 已将控制分支 `b759d87feb1eb94ad9d22294d0f2ad0ed41f6084` 快进合入工作区分支 `feature/astroncode-eval`（原 HEAD `e17c11c7c839365e7409ae3fa53ed667c6e49299`），完整保留控制分支提交历史，无冲突。后续使用工作区实际 HEAD，不 checkout 旧 SHA、不继续在控制 worktree 追加开发。

2026-09-21 接收基线 `414beeff50ad456a4624038f4519dd0a9b8412d8` 及之前 WorkBuddy/QwenWork/DoubaoWork 代码均已进入主工作区；合并代码不提升未完成的真机验收结论。此次未 push。

QwenWork 单题正式闭环实现提交为 `56584119fb9e2b316359f0ecf7b7008a453bfd04`。其独立 release `qwenwork-macos-general-5658411` 和 suite SHA-256 `ad21c166cbcacfa0fed452ab3a92c1dfb3f6bdcbef9c39d0cfe973809f03d6b9` 已通过验包；包内 run/report 0.5.1 对冻结单题重建出与工作区一致的 return package 和 10 Sheet 报告。本地尚未 push。

QwenWork 三题单槽正式 canary 已在 `1f018446a5a0be60487c40405ce6f9863b2d2319` 完成：3/3 执行/采集/评分有效，均分 0.9625；回传、导入和 10 Sheet 报告通过。完整原件见[三题证据](evidence/qwenwork-macos-general-small3-20260922/README.md)。

原三条并行开发的已接收代码及其控制分支提交映射均已进入当前工作区。Qwen selector/SQLite 加固源 `993cdc5` 对应控制提交 `f0bf24f`；collector/metadata 为 `acfc7a1`、`5263890`、`679a1e3`、`82cd3e1`。Doubao Web finalizer/bridge/route/metrics 为 `9bb30aa`、`694536d`、`07b31b7`、`e2c1d9e`。后续从当前树继续，不能因源提交不是祖先再次 cherry-pick；旧 worktree 仅作审计，暂不删除。

当前七个 General Skill：prepare `0.2.0`、execute `0.10.27`、collect `0.7.6`、orchestrate `0.9.5`、score `0.8.2`、report `0.5.1`、run `0.5.2`。execute 增加 QwenWork 队列项目预建、SQLite 在线备份、延迟 session_id 同 attempt 绑定，并修复预建项目发送前的新任务页导航；用户授权的追问“跳过”通过显式队列开关启用。`0.10.15` 加入发送前阶段时间事件；`0.10.16` 增加精确 9250 监听进程的 Token 开关安全启动与冻结探针门禁。collect `0.7.6` 对 QwenWorkCN 1.2.0 新会话的精确 runtime/开关与非零逐响应 usage 对账后才发布四个核心 Token，旧 masked 批次仍保持不可用；内容行 session/cwd 门禁不变。已发布的旧发行与验收结果仍绑定各自源码 revision；后续以 `eval_general_e2e/stages.py` 和各 `skill-metadata.json` 为准。

当前报告发行与产物见[用例对比及单元评分详情证据](evidence/general-report-details-20260921/README.md)。`89d13d0` 在既有[单元对比报告](evidence/general-report-comparison-20260921/README.md)基础上，将工具数移到请求数后，明细改为每题各单元得分并列，并增加每单元评分详情，共九张公共表加每单元一张详情；v8 为 10 Sheet。题面、规则和判词读取 SHA 绑定的冻结评分包，缺失不从当前任务源码补齐。总览不显示成本与超时数，双耗时与无根因领导版 Markdown 保留。效率明细按普通输入、缓存命中输入、缓存写入输入、输出四类展示，保留总 Token、平均 Token 和命中率；v8 平均 Token 154693、命中率 91.4086%，缓存写入与精确普通输入仍未知。分类/难度/模态、七维评分和工具次数已接入，工具质量比率暂缓。此次只更新报告，没有新增 Harness 或评分执行，原生三路并发结论不变。

2026-09-21 报告跨 Harness 只读复核：使用独立 report `0.5.0` 对 AstronStudio 已有批次 `general-macos-current-smoke-20260919-141301` 执行输入验证与内存聚合，通过；2/2 valid、均分 0.9125 保持不变，两题题面/工具轨迹完整，生成用例对比与 `评分详情_Spark X2.5@AstronStudio` 数据。没有重跑 Harness/Judge，也没有重生成该批 Excel。报告展示与评分元数据读取是公共链路；WorkBuddy 专有代码仅用于其原生指标补采。QwenWork collector 输出公共契约，但尚无真实完整回传可做相同验证，不能由报告支持推导其执行链路已经可用。此次改动范围是 General 报告，Web 报告另行维护。

本机 Python 使用 `/Users/gzx/Project/GitHub/xgz/ai/evaluate/WildClawBench/WildClawBench/.venv/bin/python`；Node 测试启动 Python 子进程时同时设置 `PYTHON` 并将本工作区 `.venv/bin` 放到 PATH 前部，避免回落到旧系统 Python。各 Driver 使用自身 package-lock 安装依赖，不借用旧平台 worktree 的 node_modules。

本次工作区迁移验证：General Node 162/162、DoubaoWork/Web metrics Node 87/87、Python layout/orchestration/build/metadata 44/44，共 293/293；7 Skill 布局和文档链接检查通过。首次检查暴露旧系统 Python 与本工作区缺少 playwright-core，已使用仓库 Python 3.11，并按 QwenWork/DoubaoWork 各自锁文件离线 npm ci 后重验；未修改锁文件、未运行被测 Harness 或评分。

## Harness × 平台进度

“受控生产可用”只覆盖证据中的环境和运行方式；“已有代码”不表示真机闭环。下表 General 状态不继承 Web 结果，Windows 的 NOT_RUN 表示本仓库当前台账没有目标平台验收证据。

| Harness | macOS General | Windows General | 下一步与证据 |
| --- | --- | --- | --- |
| AstronStudio | **受控生产可用**，x86_64；AStudio 3.3.1；G4-03 五题三槽全链路，后续 `457e355` 双题 smoke 2/2 valid，均分 0.9125 | **暂缓 / NOT_RUN**；共享发现、部分 Windows 代码路径与方案存在，原生执行/采集/评分闭环未验收 | 保留现有结果；新公共基线正式使用前做受影响 canary。[双题证据](evidence/macos-current-smoke-20260919/README.md)、[五题证据](evidence/g4-03/README.md) |
| WorkBuddy | **5 题 canary 已完成**，5.5.6 / x86_64 / xopglm52 / default-sandbox；5/5 执行和 collect，3 路原生请求峰值、2 次动态补位、每题一次发送，评分/回传/报告闭环；2 个有效分、2 个评测异常、1 个容量未评分，不能把本轮写成 5/5 valid | **暂缓 / NOT_RUN**；现有 Web/共享 Windows 能力不能证明 General 已支持 | 主流程代码、短路径发行和 WorkBuddy 重启故障验证已完成。剩余未知授权/追问安全暂停，以及 0.9.4 新包评分稳定性回归。[v2 加固 canary](evidence/workbuddy-hardening-20260921/README.md) |
| QwenWork | **1.2.0 固定五题、真实三路执行与三路评分已闭环；核心 Token 另批 5/5 可观测**。r21 五题各发送一次，原始主 turn 覆盖 5/5 后峰值 3，动态补位 2；`gpt-6-sol/high` 5/5 有效评分、回传/10 Sheet 报告。r23 带进程级开关的五题批次中输入、输出、总 Token、Cache Read 均为 5/5 observed，报告总 Token 1,611,922；Cache Write、推理 Token、HTTP 尝试仍未知 | **暂缓 / NOT_RUN**；尚无本 General 接入的 Windows 实现交付与真机证据 | r27 发送临界中断恢复/正式收口、r29 断连重连、r30 问卷自动跳过且无需人工续观通过；r31 路径预算、r32 未知授权、r33 关键收口故障已验，r35 终态/标题时差自动恢复通过；其余异常分支继续按 CV/GV 表审计。[三题正式证据](evidence/qwenwork-macos-general-small3-20260922/README.md)、[五题及 Token 证据](evidence/qwenwork-macos-five3-20260923/README.md) |
| DoubaoWork | **General 尚未接入**；当前 `eval_general_e2e/adapters/` 只有 astronstudio、workbuddy、qwenwork。可复用 discovery 与 Web 专属控制/原生解析经验，但尚无 General Driver、collector/正式回执与闭环 | **暂缓 / NOT_RUN**；Windows 可通过 CDP 自动化是可行性线索，不等于 General 已实现 | QwenWork 收口后接 General；先梳理可复用底层和 General 注册/发行缺口，不直接套 Web receipt |

DoubaoWork Web 的历史进展单独保留：一次开发 canary 已发送且产生 `countdown/index.html`，仍为 `NEEDS_ATTENTION`；UI 等价绑定、Prompt 回读、cleanup 候选模块、driver-side finalizer、内存 receipt bridge、公共路由和 metrics 已有离线实现。公共 route 仍拒绝 batch/formal receipt；可信终态/工作目录证据、真实 cleanup、正式 execution/receipt、评分/报告均未闭环。它既不是 Web 生产准入，也不是 General 完成。详见[历史 Web 任务卡](../e2e/collaboration/tasks/MAC-DOUBAOWORK-WEB.md)和[等价证据方案](../e2e/collaboration/doubaowork-web-integration.md)，其中旧调度安排不再执行。

## 下一会话直接做什么

**新 Harness 的集成任务必须包含加固实现与验收。** 开始任务时使用[统一接入契约 0.2 的任务范围模板](../e2e/端到端自动化评测Harness接入契约.md#integration-task-template)，将[CV01–CV17 共用矩阵](../e2e/端到端自动化评测Harness接入契约.md#hardening-matrix)和相应 GV/WV 纳入本客户端的现有进度/证据记录。分开记录实现、自动化/模拟、真机结果；基础必需项未通过，完整集成保持未完成。并发和无人值守按声明范围加验，不要求先做完所有平台或可选指标。本文维护各客户端实际进展，矩阵要求与模板只在统一契约维护；旧并行任务卡不再作为新任务模板。

### WorkBuddy：v2 canary 已闭环，剩余真机故障矩阵与评分稳定性

v2 配置 `run_slots=3`，5 题执行和正式 collect 均通过，原生请求实际重叠峰值 3，动态补位 2，每题一次发送，并完成评分编排、回传和报告。报告保留 2 个有效分、2 个评分评测异常和 1 个容量未评分；这证明控制流程能继续收口，不等于评分服务在每题都稳定产出有效分。执行、采集和报告原件见[v2 加固 canary](evidence/workbuddy-hardening-20260921/README.md)。

2026-09-21 对源码与发行证据复核后，以下事项仍未完成，不能只保留“三路实跑”一项：

1. **并发回执口径与有效性解耦：已完成**。v2 已分别记录调度占用和原生请求区间，原生峰值 3；并发观测不足不再自动令执行回执无效。
2. **长路径发送前检查：已完成**。attempt 创建和 UI 操作前均检查扁平化 native project 路径，长路径失败在发送前收口。
3. **新包 canary：已完成**。仅 5 题、3 路并发；Token/原生耗时、动态补位、恢复不重发、正式 collect、评分、回传和最新报告均已留证。它不是 60 题全量测试，也不替代剩余真机故障矩阵。
4. **剩余加固**：WorkBuddy 客户端执行中重启/重连已完成最小真机验证；仍需补未知授权/追问安全暂停与同 attempt 恢复，以及使用 0.9.4 Prompt 的新包评分稳定性验证。评分侧保留容量错误原 thread、不新开会话。Codex 重启验证暂缓，避免远程控制链路中断。Driver README 与本证据已同步，后续不创建平台 worktree。

无人值守 Worker 崩溃自动恢复、Apple Silicon、Windows、更高并发、60 题全量与裁判校准仍属后续扩容，不作为当前短路径、值守小批次的统一前置条件。缓存写入/精确普通输入未知以及用户暂缓的工具质量比率也不阻塞现有评分与报告。

**加固边界复核（2026-09-21）**：当前已完成身份/目录/Prompt 绑定、发送意图持久化与不确定不重发、排他锁、UI/内部草稿一致性、原生终态检查、轨迹/资源 provenance、候选冻结与哈希复验、评分隔离及回传/报告校验。真实故障证据包括 CDP 提前关闭后同 attempt 恢复且未重发、发送控件/草稿不同步时停止、文档预览被误识别后的定位修复，以及 v4 迟到评分恢复。v8 证明五题完整闭环与完成态 resume，不等于完成故障注入矩阵。

- 进程收口的真实 TERM/KILL 和无关进程保护证据位于 `/Users/gzx/debug-workspace/e2e-evaluate/wb-hardening-20260921/faults/process-cleanup/`；发送临界点强杀 Worker 后同 attempt 不重发证据位于 `/Users/gzx/debug-workspace/e2e-evaluate/wbh1/faults/worker-kill/`。这些是故障验收证据，不混入能力评分。
- WorkBuddy 客户端执行中重启/重连已有最小真机证据；未知授权/追问、stale lock 无人值守自动恢复仍未形成完整矩阵，当前策略是暂停并保留现场，不自动抢占陈旧锁。Codex 重启项因远程控制风险暂缓。
- 下一步只补上述最小真机故障验证和评分稳定性，不扩展到 60 题全量。AstronStudio 历史 MAC 表不能直接作为 WorkBuddy 通过依据；题目 `timeout_seconds` 继续不限制执行或参与评分。

### 1. QwenWork General：五题真实三路与核心 Token 已验，补故障矩阵

1. 使用[五题证据](evidence/qwenwork-macos-five3-20260923/README.md)核对 r21 的同批次 5/5 一次发送、原始主 turn 真正三路、两次动态补位、同 attempt 恢复、正式采集、`gpt-6-sol/high` 三路语义评分、回传和 10 Sheet 报告。r20 短题轮次只观察到峰值 2，不能抹掉或改写；预建是可选执行策略，不把 UI 准备或队列占槽计入原生任务耗时。
2. r23 在新客户端进程启用 `QODERCN_EXPOSE_TOKEN_USAGE=1` 后，对五题逐响应与主 turn 完整对账，输入/输出/总 Token/Cache Read 均 5/5 observed；报告总 Token 1,611,922。旧 r20/r21 隐藏零值不可回填。Cache Write、推理 Token、HTTP 尝试和实际模型 ID 仍未知。
3. 后续裁判配置固定为 `gpt-6-sol/high`；原 r20 astra/high 评分保留为历史 submission，不覆盖它。题目 `timeout_seconds` 不限制 QwenWork 或评分 thread。
4. r27 使用 `9f94ef7` 新发行，在发送临界中断队列与 Driver 后，精确归档两把锁，恢复原 attempt/session，发送和 Prompt 匹配数均为 1；正式 collector/finalizer/verify-only PASS。r26 的“队列完成但子任务 DISPATCHING”无效回执保留，已修复，不当作通过证据。
5. r28 独立技术问卷验证 CDP 断连安全暂停、原 session 重连、自动页脚“跳过”及原生最终回复；execute `0.10.23` 修复临时标题缺失时的身份保留，并按 `user-question-footer` 排除同名页头箭头。r29 同源码新 attempt 已复验临时身份、断连重连和跳过终态。`f07d0b3` / 0.10.24 消除跳过后的旧状态冲突，r30 新批次自动 RUNNING→COMPLETED、一次跳过、一次发送、人工 resume=0；正式 release 为 `qwenwork-question-f07d0b3`。
6. 本轮重要加固已验证：r31 发送前原始/编码路径预算、中文/空格与最长任务 ID/越限负例；r32 未知授权自动暂停、人工拒绝后原会话完成且恢复原权限；r33 正式 finalizer CLI 的持续残留拒绝、迟到写入拒绝、TERM→KILL、迟到子进程和冻结后漂移。见[CV/GV 证据表](evidence/qwenwork-macos-five3-20260923/README.md#声明范围与-cvgv-符合性记录)。
7. 当前执行发行为 `qwenwork-hardening-190406c`，execute `0.10.27`；r35 新 attempt 验证终态快照复查和自动标题同步，RUNNING→COMPLETED、发送/匹配 1、复查 1，无人工恢复；Qwen Node 115/115、发行/布局 16/16 PASS。剩余 CV02/03/07/11/13/14 与 GV03/04/06 的部分异常分支继续做证据审计，完整接入保持 IN_PROGRESS。实际模型 ID 和可选未知指标不阻塞评分；Codex 重启暂缓，Apple Silicon/Windows/60 题/无人值守另验。
8. 2026-09-23 前轮公共回归一度因本机磁盘耗尽报 `ENOSPC`，当时只读检查剩余约 150 MiB；之后外部可用空间恢复至约 2.1 GiB，失败单项已通过重验。已有故障证据、冻结候选、发行与报告均保留。

历史证据根：`/Users/gzx/debug-workspace/e2e-evaluate/qwenwork-macos-general-e2e/`。SLOT04 未建 attempt，退出最终由用户确认；关闭库 probe 当时报 error 14，后续修复只有离线证据。本轮整理未操作客户端，不把历史“进程已退出”当作当前现场。

### 2. DoubaoWork General：QwenWork 收口后开始

复用已集成的本地电脑 → 本地项目发现、控制与原始轨迹读取能力；为 General 增加 adapter/Driver 注册、prepare/execute 路由、正式证据与资源映射、进程收口、发行依赖闭包。先通过单题执行到报告，再用 3–5 题覆盖文件和纯回复。Web 的等价 UI 绑定只作为证据方案参考，是否满足 General 正式采集契约需验证；缺失原生字段不能伪造，也不假定永远必须存在不存在的字段。

旧 Web canary 原件：`/Users/gzx/debug-workspace/e2e-evaluate/doubaowork-macos-web-e2e/slot-mac-20260919-01-canary/`，attempt `f2d106cc-aeb4-4f56-a863-9a82edec5c6e`。旧观察记录候选进程/8848 服务残留、精确 live revision 和最终回复证据不完整；恢复前只读核验现状，不把旧 PID 当作当前 PID、不重发旧 Prompt、不把旧 canary 补写为正式成功。

### 3. 评测与延后项

macOS 四个 Harness 达到声明范围的全链路准入后，使用冻结数据集和发行先做 canary，再进入实际批次；新客户端可以随已支持客户端分别形成评测结果。60 题全量是评测/扩容阶段，不要求先补齐双平台或无人值守才开始。

- Windows：整体暂缓，macOS 四个 General 收口后再启动；先 AstronStudio，其他三个按需求串行。保留[Windows 实施清单](AstronStudio-Windows通用E2E开发启动包.md)，没有 Windows 真机证据就保持 NOT_RUN。
- COMMON-CM01：General 报告已支持平均 Token、输入缓存命中率、任务/流程耗时和工具调用数；常规指标在各 Harness 的完整原生对账仍需分别验证。工具格式准确率/执行成功率/不确定占比本阶段暂缓，平均积分与统一异常率等未完成；[指标盘点](Web与通用E2E指标盘点及Harness可行性分析.md)是历史分析。已知小计、coverage、null 语义继续保留，不能把工具 completed 当成业务 success。
- 默认三路执行是各新 Harness 单槽闭环后的接入目标；WorkBuddy 已验证三槽调度，原生三路重叠仍待验收。更高并发、无人值守恢复、Apple Silicon、裁判校准分别立项。

## 新会话 Prompt

```text
继续 WildClawBench 的 macOS General E2E 串行开发。
唯一修改目录：/Users/gzx/Project/GitHub/xgz/ai/evaluate/WildClawBench/WildClawBench
分支：feature/astroncode-eval。
先检查该工作区的 Git 状态，读取 docs/design/general-e2e/README.md，按其中“下一会话直接做什么”完成 WorkBuddy 并发回执/路径预检工程收尾与新包 canary，再进入 QwenWork General 的真实单题闭环。
新增或继续 Harness 集成时，读取统一接入契约 0.2 第1.9/1.10节，将 CV01–CV17 和 General GV 纳入本客户端任务，包含基础加固代码、反例测试及适用真机故障验证；基础必需项未通过不得关闭完整接入。
如果 README 已记录该项完成，则执行其下一项；以仓库当前记录和本机证据为准，不依赖旧聊天。
直接在当前工作区分支串行迭代，不创建平台任务、subagent 或 worktree，不申请桌面时段，不 push。
每完成一个事项，补充真实证据和 README 对应进度，运行必要检查并单独提交中文 Conventional Commit。
优先完成 macOS 四个 Harness 的 General 并开始评测，Windows 和 DoubaoWork Web 后续收口暂缓。
题目 timeout_seconds 不限制 Harness 执行、不参与评分；基础设施与评分控制 deadline 独立处理。
读各阶段 Skill 时使用上述工作区下 tools/report/skills/general-e2e 的版本。
```

## 按需参考与更新规则

[技术方案](通用场景端到端自动化评测技术方案.md)解释架构；[契约决策](通用场景端到端自动化评测契约决策记录.md)与[统一 Harness 接入契约](../e2e/端到端自动化评测Harness接入契约.md)定义不变量；[验收清单](通用场景端到端自动化评测实现计划与验收清单.md)保留 G/MAC/WIN ID 和技术验收历史；`evidence/` 保存可复核索引。新会话不需要一开始全部加载。

旧 `docs/design/e2e/collaboration/` 的任务分派、worktree 回收、桌面 SLOT、双平台同时推进和逐交接接收流程已退役，仅按需查历史。历史 evidence 中的“当前/下一项”也是当时快照，不覆盖本文。

后续每项提交只更新本文受影响的状态/下一步与一个必要证据索引；写明源码/包身份、真实执行和评分数量、未完成项、产物路径、仍活动运行和恢复入口。已有真机结论保留原 revision，源码更新只触发受影响回归；本轮文档整理没有重新执行 Harness 或评分。
