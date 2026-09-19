# MAC-QWENWORK-GENERAL：QwenWork macOS General

| 字段 | 当前值 |
| --- | --- |
| 唯一负责人 / 实际任务 ID | 独立开发任务 / `MAC-QWENWORK-GENERAL`；由 COMMON 控制任务派发 |
| 工作状态 / 代码交付 | ACTIVE / LOCAL_ONLY；P1 已完成，P2 离线 Driver 已提交，live canary/正式 collect 未完成 |
| 计划分支 / worktree | `feat/qwenwork-macos-general-e2e` / `<主项目>/.agents/qwenwork-macos-general-e2e`；绑定已核验 |
| 创建 base / 已采用公共基线 | `03c38f280a64ad9bc9308c768f0f5795050355cc` / 推荐源码 `ed366b30bc5ddd2ae35ef6361c3ac7c72ce9963a` |
| 已读台账的 SYNC_SHA / 实际工作 HEAD | `0dd42824cb8eb510ab126fd74553f93312c9f201` / 更新本卡前实现 HEAD `0b732fb432674eb2c1fd388018b1e66ede790066` |
| 同步源 / 实现与集成 SHA | `github/feature/astroncode-eval`（COMMON 已核验）；CB-A `abce5da832f16b48cd402ceef04a6abda544a379`；P1 `3f4ccbced1e90d71bea66508dfe8cca698bc7bea`；P2 离线 `0b732fb432674eb2c1fd388018b1e66ede790066`，均未集成/未 push |
| 最后更新 | 2026-09-19（Asia/Shanghai），完成 P2 离线一次发送/恢复 Driver 与并发门禁；未操作客户端 |

## 本轮范围与修改归属

实现 QwenWork 的 General Driver、轨迹/资源适配、正式 collect、评分交接和声明范围的并发/恢复。负责客户端专属层与 fixtures；共用文件由 COMMON 协调，不能独自泛化整套 General 注册入口。

技术细项与证据入口：[General 验收清单](../../../general-e2e/通用场景端到端自动化评测实现计划与验收清单.md)中本 Harness 独立记录，映射 C/G、CV/GV；不复用 Windows 或 AstronStudio 通过状态。

Windows 同号版本、旧 macOS token profile 不能覆盖当前 macOS 运行时。未匹配的字段先保留 unverified/null 与原始证据。

## 依赖与完成清单

硬依赖：[COMMON](COMMON.md) 的 COMMON-CB04 已发布，且本任务的 adapter/状态/指标接口约定可取得。**不依赖 COMMON-CM01 的全部新增指标实现。** 基线未发布时可继续只读环境盘点、已有日志/fixture 分析和差异清单；不自创公共字段或依赖未合入 worktree。

- [x] P1：本机只读 probe、原生身份与字段/能力映射。实现 `3f4ccbced1e90d71bea66508dfe8cca698bc7bea`；证据：[qwenwork-macos-readonly-20260919](../../../general-e2e/evidence/qwenwork-macos-readonly-20260919/README.md)。
- [ ] P2：单题一次发送、可信终态、恢复和正式证据收口。离线 Driver/mock 已由 `0b732fb432674eb2c1fd388018b1e66ede790066` 完成；仍缺 live canary、CB-B 正式证据收口和 cleanup。
- [ ] P3：原始轨迹/资源对账与完整单题评分/回传/报告。
- [ ] P4：按场景验收三题串行、五题动态补位及声明并发。
- [ ] P5：受影响故障加固、候选不可变与仓库外发行。
- [ ] P6：代码/证据/交接集成，必需接收动作完成。

勾选附实现/集成 SHA 与验收证据；此卡不复制技术验收 PASS 表。

## 下一项与阻塞

下一项：等待 COMMON 发布 CB-B 固定 SHA/准确组件版本并同步 binding；在控制任务分配的桌面独占时段先运行 canary `--validate-only`，再完成一个全新 General canary 的 UI 回读、一次发送、session/cwd/Prompt 捕获和同 attempt 恢复。

当前依赖缺口：CB-A 已采用；COMMON 正在发布 CB-B/trace-index v2/cleanup hook，固定 SHA 尚未取得。General Skill 当前未独立装配 `playwright-core`，不得借用 Web Skill 运行时。当前 QwenWorkCN 1.0.6 未命中历史 macOS 1.0.5 Token Profile，严格资源输出保持 null/coverage，须用当前身份真机非零样本对账后才能新增 Profile。当前未分配桌面时段，不能验证 UI/发送/恢复。

## 本机现场与恢复

本地证据根：`/Users/gzx/debug-workspace/e2e-evaluate/qwenwork-macos-general-e2e/`。2026-09-19 只读 probe 时 QwenWork 主进程 0、CDP 未开放、状态库 active/pending 0；这不等于已取得桌面锁。客户端为 1.0.6/x86_64；原生 session/conversation/sub-chat/local-project/cwd 可读，公共 thread/turn 无等价字段，必须为 null。

桌面时段准备：应用 `/Applications/QwenWorkCN.app`；范围为控制任务分配的一个全新 General canary；保持用户当前模型/权限。操作前重跑只读 probe，确认活动会话和控制端点；发送前持久化 attempt、Prompt SHA、baseline/local project。发送边界不明、ID 不唯一、未知交互或停止未确认时保留 `NEEDS_ATTENTION` 并禁止重发/冻结；恢复只按原生 ID 进入原会话。

P2 canary CLI、冻结配置、前置条件和回退方案见 [qwenwork-macos-p2-offline-20260919](../../../general-e2e/evidence/qwenwork-macos-p2-offline-20260919/README.md)。Driver 增加真实 attempt OS 锁，桌面 slot 字段不作为互斥实现；双 worker mock 证明总 dispatch `<=1`。

## 接收记录

| 交接 ID | 状态 | 已采用集成 SHA | 处理结果、验收证据/阻塞 | 下一项 |
| --- | --- | --- | --- | --- |
| COMMON-001 | VERIFIED | `0dd42824cb8eb510ab126fd74553f93312c9f201`（推荐源码 `ed366b30...963a`） | 无活动 QwenWork 会话后 merge；已按 CB-A 输出 session/cwd/证据，thread/turn 为 null；公共 55/55、新增 Node 12/12、Python 3/3 通过 | P2 真机时段；CB-B 接口交接 |

## 本轮交付

P1 `3f4ccbced1e90d71bea66508dfe8cca698bc7bea` 完成只读 probe、原生字段/终态映射、adapter/fixtures。P2 离线提交 `0b732fb432674eb2c1fd388018b1e66ede790066` 增加 UI/Workspace/配置回读、一次发送 journal、session/cwd/Prompt 绑定、恢复不重发、可信终态、attempt 锁、symlink 防护和工具结局修正。公共 55/55、QwenWork Node 25/25、Python 3/3 与语法检查通过。交接 [MAC-QWENWORK-GENERAL-002](../handoffs/MAC-QWENWORK-GENERAL-002.md) 列出 CB-B/发行装配/live canary 接收动作。没有启动/重启客户端、选择目录、切换配置或发送 Prompt；没有本平台新真机执行/collect/评分/并发/发行结论。未 push、未集成。
