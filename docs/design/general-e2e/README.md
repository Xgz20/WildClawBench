# General E2E 开发接续入口

更新：2026-09-21（Asia/Shanghai）。这是当前开发顺序、Harness 集成状态和下一步的唯一维护入口。新会话先读本文，再按当前任务读取对应 Skill、源码与证据；无需通读历史聊天或旧并行台账。

## 当前路线与工作边界

先串行完成 **macOS：AstronStudio → WorkBuddy → QwenWork → DoubaoWork 的 General E2E**，进入实际评测，再开展 Windows 支持。AstronStudio 与 WorkBuddy 已有受控生产证据；WorkBuddy 五题默认三路也已完成，下一项是 QwenWork。DoubaoWork 原任务是 Web，现改为优先建设 General；Web 后续收口暂缓。

- 唯一开发目录：`/Users/gzx/Project/GitHub/xgz/ai/evaluate/WildClawBench/WildClawBench`；分支 `feature/astroncode-eval`。后续直接在当前主工作区开发、验证和提交；控制 worktree 已完成汇入，仅保留审计。
- 直接在工作区分支串行修改；不创建平台任务、subagent 或新 worktree，不恢复旧并行任务。桌面验证无需申请时段，但操作前检查真实活动任务、草稿、进程和 CDP 身份，保留无关现场。该约束针对开发派发，评分所需的独立 Judge 任务仍按阶段 Skill 创建。
- 每完成一个可验收事项，更新本文对应行和必要证据索引，运行受影响检查，单独提交中文 `type(scope): 中文说明`。本地提交；当前不 push。
- 调试、smoke、临时包、运行与评分产物：`/Users/gzx/debug-workspace/e2e-evaluate`。正式发行：主检出的 `report-workspace`。任务产物均在本地。
- 先用值守单槽验证全链路，再验证五题默认三路执行、动态补位和恢复不重发。**开发串行不等于评测串行**。WorkBuddy 已完成该范围；无人值守 Worker 崩溃恢复、Apple Silicon、更高并发和全量 60 题另行扩容。
- 客户端版本记录为兼容性元数据，不设精确版本白名单；根据实际能力、原生字段、UI 行为与回归证据判断兼容性。冻结的运行/评分包身份仍需校验。
- 题目 `timeout_seconds` 仅为兼容元数据，**不限制被评测 Harness 总执行时长，也不参与能力评分**。执行等待可信终态、明确异常或人工处理；UI/CDP 操作、启动/停止、身份绑定、进程清理、评分 Worker/API/线程 deadline 继续独立生效。

## 代码基线与发行边界

2026-09-21 已将控制分支 `b759d87feb1eb94ad9d22294d0f2ad0ed41f6084` 快进合入工作区分支 `feature/astroncode-eval`（原 HEAD `e17c11c7c839365e7409ae3fa53ed667c6e49299`），完整保留控制分支提交历史，无冲突。后续使用工作区实际 HEAD，不 checkout 旧 SHA、不继续在控制 worktree 追加开发。

最近实现提交 `414beeff50ad456a4624038f4519dd0a9b8412d8` 及之前 WorkBuddy/QwenWork/DoubaoWork 已接收代码均已进入主工作区；合并代码不提升未完成的真机验收结论。此次未 push。

原三条并行开发的已接收代码及其控制分支提交映射均已进入当前工作区。Qwen selector/SQLite 加固源 `993cdc5` 对应控制提交 `f0bf24f`；collector/metadata 为 `acfc7a1`、`5263890`、`679a1e3`、`82cd3e1`。Doubao Web finalizer/bridge/route/metrics 为 `9bb30aa`、`694536d`、`07b31b7`、`e2c1d9e`。后续从当前树继续，不能因源提交不是祖先再次 cherry-pick；旧 worktree 仅作审计，暂不删除。

当前七个 General Skill：prepare `0.2.0`、execute `0.10.4`、collect `0.6.1`、orchestrate `0.9.2`、score `0.8.1`、report `0.2.2`、run `0.5.0`。execute `0.10.4` 的 WorkBuddy 默认三路队列和队列内活动会话门禁已由 v8 五题真机验收。后续以 `eval_general_e2e/stages.py` 和各 `skill-metadata.json` 为准；不要把新源码/包版本倒填进旧 smoke。

本机 Python 使用 `/Users/gzx/Project/GitHub/xgz/ai/evaluate/WildClawBench/WildClawBench/.venv/bin/python`；Node 测试启动 Python 子进程时同时设置 `PYTHON` 并将本工作区 `.venv/bin` 放到 PATH 前部，避免回落到旧系统 Python。各 Driver 使用自身 package-lock 安装依赖，不借用旧平台 worktree 的 node_modules。

本次工作区迁移验证：General Node 162/162、DoubaoWork/Web metrics Node 87/87、Python layout/orchestration/build/metadata 44/44，共 293/293；7 Skill 布局和文档链接检查通过。首次检查暴露旧系统 Python 与本工作区缺少 playwright-core，已使用仓库 Python 3.11，并按 QwenWork/DoubaoWork 各自锁文件离线 npm ci 后重验；未修改锁文件、未运行被测 Harness 或评分。

## Harness × 平台进度

“受控生产可用”只覆盖证据中的环境和运行方式；“已有代码”不表示真机闭环。下表 General 状态不继承 Web 结果，Windows 的 NOT_RUN 表示本仓库当前台账没有目标平台验收证据。

| Harness | macOS General | Windows General | 下一步与证据 |
| --- | --- | --- | --- |
| AstronStudio | **受控生产可用**，x86_64；AStudio 3.3.1；G4-03 五题三槽全链路，后续 `457e355` 双题 smoke 2/2 valid，均分 0.9125 | **暂缓 / NOT_RUN**；共享发现、部分 Windows 代码路径与方案存在，原生执行/采集/评分闭环未验收 | 保留现有结果；新公共基线正式使用前做受影响 canary。[双题证据](evidence/macos-current-smoke-20260919/README.md)、[五题证据](evidence/g4-03/README.md) |
| WorkBuddy | **主流程受控生产可用**，5.5.6 / x86_64 / xopglm52 / default-sandbox；五题默认三路执行、2 次动态补位、collect、评分、回传和报告完成，5/5 valid，均分 0.8275 | **暂缓 / NOT_RUN**；现有 Web/共享 Windows 能力不能证明 General 已支持 | 三路发行可用于正式批次前 canary；无人值守 Worker 崩溃恢复等另验。[三路 v8 证据](evidence/workbuddy-macos-general-v8-three-slot-20260921/README.md)、[单槽 v4 证据](evidence/workbuddy-macos-general-v4-20260921/README.md) |
| QwenWork | **开发中，尚无真实发送闭环**；专属 Driver、恢复锁、selector/SQLite 快照、CB-B collector 和 metadata 预检已接入。最近 SLOT04 真机在项目控件歧义处退出，`PROMPT_SENT=0`，无 attempt | **暂缓 / NOT_RUN**；尚无本 General 接入的 Windows 实现交付与真机证据 | **当前下一项**：验证 selector/probe → 一次发送/同 attempt 恢复 → 正式 collect/cleanup → 评分/回传/报告。[旧失败证据](evidence/qwenwork-macos-slot04-canary-20260919/README.md) |
| DoubaoWork | **General 尚未接入**；当前 `eval_general_e2e/adapters/` 只有 astronstudio、workbuddy、qwenwork。可复用 discovery 与 Web 专属控制/原生解析经验，但尚无 General Driver、collector/正式回执与闭环 | **暂缓 / NOT_RUN**；Windows 可通过 CDP 自动化是可行性线索，不等于 General 已实现 | QwenWork 收口后接 General；先梳理可复用底层和 General 注册/发行缺口，不直接套 Web receipt |

DoubaoWork Web 的历史进展单独保留：一次开发 canary 已发送且产生 `countdown/index.html`，仍为 `NEEDS_ATTENTION`；UI 等价绑定、Prompt 回读、cleanup 候选模块、driver-side finalizer、内存 receipt bridge、公共路由和 metrics 已有离线实现。公共 route 仍拒绝 batch/formal receipt；可信终态/工作目录证据、真实 cleanup、正式 execution/receipt、评分/报告均未闭环。它既不是 Web 生产准入，也不是 General 完成。详见[历史 Web 任务卡](../e2e/collaboration/tasks/MAC-DOUBAOWORK-WEB.md)和[等价证据方案](../e2e/collaboration/doubaowork-web-integration.md)，其中旧调度安排不再执行。

## 下一会话直接做什么

### 已完成：WorkBuddy General 五题默认三路执行

v8 保持 UI 单槽，真实观测 `run_slots=3`、最大并发 3、2 次动态补位、每题一次发送，并完成 collect、评分、回传、报告和与真机同 SHA 的正式发行。旧 v4 单槽产物和成绩保持原身份。长路径失败批次及短路径要求见[证据索引](evidence/workbuddy-macos-general-v8-three-slot-20260921/README.md)。

### 1. QwenWork General：完成真实单题，再扩到小批

1. 检查当前工作区/分支/dirty 状态，读取 `execute-general-e2e/SKILL.md`；代码在 `tools/report/skills/general-e2e/execute-general-e2e/drivers/qwenwork/`，采集在 `eval_general_e2e/adapters/qwenwork/`，只读原生字段预检入口为 `tools/qwenwork_metadata_preflight.py`。该 Skill 取自当前工作区的 canonical 路径，避免读取旧控制/平台 worktree 的同名 Skill。
2. 重新探测本机 QwenWork 安装、版本、活动会话与 loopback CDP。历史环境为 `/Applications/QwenWorkCN.app`、1.0.6/x86_64、端口 9250，均需刷新；保持用户当前模型/权限。验证当前 selector 唯一语义定位和活动 WAL/关闭库快照，不因旧 SLOT04 失败重复重构已集成的修复。
3. 从当前提交构建并验证独立发行，在调试根准备全新单题执行包和 attempt；按实际 CLI help/Skill 生成命令，不原样重放历史 canary 配置。Driver 依赖在自己的锁定 `package.json`/lockfile 下安装，不能借用 Web 的 node_modules。
4. 一次发送后绑定原生 session、完整 cwd、Prompt digest，观察可信终态；同 attempt 恢复只观察、不重发。用真实日志核验 metadata coverage，缺失 usage 保留 null/coverage，不因未匹配旧 1.0.5 Token Profile 阻塞整条执行链。
5. 读 `collect-general-e2e`，接入并验证实际 cleanup 和公共 finalizer，归档 raw/标准 transcript、候选和正式回执。完成独立评分、submission、return/import、同源报告后，扩到覆盖文件/纯回复与三种评分类型的小批，随后补五题默认三路执行与动态补位，再冻结相应发行和支持范围。

历史证据根：`/Users/gzx/debug-workspace/e2e-evaluate/qwenwork-macos-general-e2e/`。SLOT04 未建 attempt，退出最终由用户确认；关闭库 probe 当时报 error 14，后续修复只有离线证据。本轮整理未操作客户端，不把历史“进程已退出”当作当前现场。

### 2. DoubaoWork General：QwenWork 收口后开始

复用已集成的本地电脑 → 本地项目发现、控制与原始轨迹读取能力；为 General 增加 adapter/Driver 注册、prepare/execute 路由、正式证据与资源映射、进程收口、发行依赖闭包。先通过单题执行到报告，再用 3–5 题覆盖文件和纯回复。Web 的等价 UI 绑定只作为证据方案参考，是否满足 General 正式采集契约需验证；缺失原生字段不能伪造，也不假定永远必须存在不存在的字段。

旧 Web canary 原件：`/Users/gzx/debug-workspace/e2e-evaluate/doubaowork-macos-web-e2e/slot-mac-20260919-01-canary/`，attempt `f2d106cc-aeb4-4f56-a863-9a82edec5c6e`。旧观察记录候选进程/8848 服务残留、精确 live revision 和最终回复证据不完整；恢复前只读核验现状，不把旧 PID 当作当前 PID、不重发旧 Prompt、不把旧 canary 补写为正式成功。

### 3. 评测与延后项

macOS 四个 Harness 达到声明范围的全链路准入后，使用冻结数据集和发行先做 canary，再进入实际批次；新客户端可以随已支持客户端分别形成评测结果。60 题全量是评测/扩容阶段，不要求先补齐双平台或无人值守才开始。

- Windows：整体暂缓，macOS 四个 General 收口后再启动；先 AstronStudio，其他三个按需求串行。保留[Windows 实施清单](AstronStudio-Windows通用E2E开发启动包.md)，没有 Windows 真机证据就保持 NOT_RUN。
- COMMON-CM01：异常率、工具调用成功率、平均积分、输入缓存命中率、平均 Token 的统一实现/原生对账仍未完成；[指标盘点](Web与通用E2E指标盘点及Harness可行性分析.md)是历史分析。它不阻塞已明确接口的客户端接入；已知小计、coverage、null 语义继续保留，不能把工具 completed 当成业务 success。
- 默认三路执行是各新 Harness 单槽闭环后的接入目标；WorkBuddy 已完成。更高并发、无人值守恢复、Apple Silicon、裁判校准分别立项。

## 新会话 Prompt

```text
继续 WildClawBench 的 macOS General E2E 串行开发。
唯一修改目录：/Users/gzx/Project/GitHub/xgz/ai/evaluate/WildClawBench/WildClawBench
分支：feature/astroncode-eval。
先检查该工作区的 Git 状态，读取 docs/design/general-e2e/README.md，按其中“下一会话直接做什么”推进 QwenWork General 的真实单题闭环。
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
