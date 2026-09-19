# MAC-QWENWORK-GENERAL：QwenWork macOS General

| 字段 | 当前值 |
| --- | --- |
| 唯一负责人 / 实际任务 ID | 独立开发任务 / `MAC-QWENWORK-GENERAL`；由 COMMON 控制任务派发 |
| 工作状态 / 代码交付 | ACTIVE / LOCAL_ONLY；P1 已完成，P2 live canary 在发送前门禁失败，正式 collect 未完成 |
| 计划分支 / worktree | `feat/qwenwork-macos-general-e2e` / `<主项目>/.agents/qwenwork-macos-general-e2e`；绑定已核验 |
| 创建 base / 已采用公共基线 | `03c38f280a64ad9bc9308c768f0f5795050355cc` / 推荐源码 `ed366b30bc5ddd2ae35ef6361c3ac7c72ce9963a` |
| 已读台账的 SYNC_SHA / 实际工作 HEAD | `0dd42824cb8eb510ab126fd74553f93312c9f201` / canary Driver `9081df5288d59c83e9e4d34d3bc8b288d96d7568` |
| 同步源 / 实现与集成 SHA | `github/feature/astroncode-eval`（COMMON 已核验）；CB-A `abce5da832f16b48cd402ceef04a6abda544a379`；P1 `3f4ccbced1e90d71bea66508dfe8cca698bc7bea`；P2 Driver 修复至 `9081df5288d59c83e9e4d34d3bc8b288d96d7568`，均未集成/未 push |
| 最后更新 | 2026-09-19（Asia/Shanghai），SLOT04 真实 prepare PASS；UI project trigger 重复导致发送前失败关闭，`PROMPT_SENT=0` |

## 本轮范围与修改归属

实现 QwenWork 的 General Driver、轨迹/资源适配、正式 collect、评分交接和声明范围的并发/恢复。负责客户端专属层与 fixtures；共用文件由 COMMON 协调，不能独自泛化整套 General 注册入口。

技术细项与证据入口：[General 验收清单](../../../general-e2e/通用场景端到端自动化评测实现计划与验收清单.md)中本 Harness 独立记录，映射 C/G、CV/GV；不复用 Windows 或 AstronStudio 通过状态。

Windows 同号版本、旧 macOS token profile 不能覆盖当前 macOS 运行时。未匹配的字段先保留 unverified/null 与原始证据。

## 依赖与完成清单

硬依赖：[COMMON](COMMON.md) 的 COMMON-CB04 已发布，且本任务的 adapter/状态/指标接口约定可取得。**不依赖 COMMON-CM01 的全部新增指标实现。** 基线未发布时可继续只读环境盘点、已有日志/fixture 分析和差异清单；不自创公共字段或依赖未合入 worktree。

- [x] P1：本机只读 probe、原生身份与字段/能力映射。实现 `3f4ccbced1e90d71bea66508dfe8cca698bc7bea`；证据：[qwenwork-macos-readonly-20260919](../../../general-e2e/evidence/qwenwork-macos-readonly-20260919/README.md)。
- [ ] P2：单题一次发送、可信终态、恢复和正式证据收口。离线 Driver 已修复至 `9081df5288d59c83e9e4d34d3bc8b288d96d7568`；SLOT04 在发送前发现两个可见 project trigger 并失败关闭，仍缺 selector/probe 加固、一次真机发送、CB-B 正式证据收口和 cleanup。
- [ ] P3：原始轨迹/资源对账与完整单题评分/回传/报告。
- [ ] P4：按场景验收三题串行、五题动态补位及声明并发。
- [ ] P5：受影响故障加固、候选不可变与仓库外发行。
- [ ] P6：代码/证据/交接集成，必需接收动作完成。

勾选附实现/集成 SHA 与验收证据；此卡不复制技术验收 PASS 表。

## 下一项与阻塞

下一项：先离线修复并审查 project trigger 唯一定位与关闭后 sidecar-free WAL 数据库只读 probe；采用父任务 CLI main-guard 修复 `dc5ff64` 后复核脱仓 ZIP。完成后再申请新桌面时段，从全新 attempt 做 UI 回读、一次发送、session/cwd/Prompt 捕获和同 attempt 恢复。

当前依赖缺口：两个可见 project trigger 不能按稳定语义唯一定位；客户端完全退出且 WAL/SHM 消失后，现有 probe 对 sidecar-free WAL 主库报 SQLite error 14。CB-A/CB-B 公共基线已存在，但 QwenWork cleanup 仍未真机验收；General Skill 当前未独立装配 `playwright-core`，不得借用 Web Skill 运行时。当前 QwenWorkCN 1.0.6 未命中历史 macOS 1.0.5 Token Profile，严格资源输出保持 null/coverage。SLOT04 已释放，当前无桌面许可。

## 本机现场与恢复

本地证据根：`/Users/gzx/debug-workspace/e2e-evaluate/qwenwork-macos-general-e2e/`。SLOT04 启动前 QwenWork 主进程 0、CDP 未开放、状态库 active/pending 0；启动后 UI 前检在任何变更前因 project trigger `2` 个候选失败。退出确认弹窗最终由用户手动点击，不能写成自动恢复通过；最终无主进程/9250/数据库写者，immutable 只读诊断 `quick_check=ok`、active/pending 0，但标准 probe 仍报 error 14。

下一桌面时段准备：应用 `/Applications/QwenWorkCN.app`；范围为控制任务重新分配的一个全新 General canary；保持用户当前模型/权限。操作前重跑已修复 probe，确认活动会话和控制端点；发送前必须得到唯一当前视图 project trigger。发送边界不明、ID 不唯一、未知交互或停止未确认时保留 `NEEDS_ATTENTION` 并禁止重发/冻结；恢复只按原生 ID 进入原会话。

P2 canary CLI、冻结配置、前置条件和回退方案见 [qwenwork-macos-p2-offline-20260919](../../../general-e2e/evidence/qwenwork-macos-p2-offline-20260919/README.md)。Driver 增加真实 attempt OS 锁，桌面 slot 字段不作为互斥实现；双 worker mock 证明总 dispatch `<=1`。

## 接收记录

| 交接 ID | 状态 | 已采用集成 SHA | 处理结果、验收证据/阻塞 | 下一项 |
| --- | --- | --- | --- | --- |
| COMMON-001 | VERIFIED | `0dd42824cb8eb510ab126fd74553f93312c9f201`（推荐源码 `ed366b30...963a`） | 无活动 QwenWork 会话后 merge；已按 CB-A 输出 session/cwd/证据，thread/turn 为 null；公共 55/55、新增 Node 12/12、Python 3/3 通过 | P2 真机时段；CB-B 接口交接 |
| MAC-QWENWORK-GENERAL-003 | OPEN | 未集成 | SLOT04 真实 prepare PASS；发送前 project trigger `2` 个候选失败，`PROMPT_SENT=0`；用户手动确认退出；关闭库 probe error 14 | selector/probe 独立修复审查后申请新 slot |

## 本轮交付

P1 `3f4ccbced1e90d71bea66508dfe8cca698bc7bea` 完成只读 probe、原生字段/终态映射、adapter/fixtures。P2 Driver 经 `f6076ac`、`39b2109`、`9081df5` 完成恢复、COMMON-002 binding、窗口归属和重复恢复反例。SLOT04 用 `9081df5` 构建 release 并完成单题 prepare，但在发送前 UI 唯一性门禁失败；详见 [MAC-QWENWORK-GENERAL-003](../handoffs/MAC-QWENWORK-GENERAL-003.md) 和 [SLOT04 证据](../../../general-e2e/evidence/qwenwork-macos-slot04-canary-20260919/README.md)。本轮没有 Prompt 发送、attempt、resume、collect、评分或模型能力结论。未 push、未集成。
