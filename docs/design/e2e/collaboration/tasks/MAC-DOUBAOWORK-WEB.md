# MAC-DOUBAOWORK-WEB：DoubaoWork macOS Web

| 字段 | 当前值 |
| --- | --- |
| 唯一负责人 / 实际任务 ID | 独立 Codex 开发任务 / `MAC-DOUBAOWORK-WEB` |
| 工作状态 / 代码交付 | ACTIVE / LOCAL_ONLY；P1 只读 probe、原生字段映射、脱敏 fixtures 与离线 adapter 已实现，尚未集成 |
| 分支 / worktree | `feat/doubaowork-macos-web-e2e` / `<主项目>/.agents/doubaowork-macos-web-e2e`，已核验绑定 |
| 创建 base / 已采用公共基线 | `03c38f280a64ad9bc9308c768f0f5795050355cc` / COMMON-001 已 SEEN，待本批独立修改提交后 merge |
| 已读台账的 SYNC_SHA / 实际工作 HEAD | 已固定并读取 `0dd42824cb8eb510ab126fd74553f93312c9f201`；当前仍基于创建 base，提交/merge 后更新 |
| 同步源 / 实现与集成 SHA | `github/feature/astroncode-eval`；当前实现待本地提交，未集成、未 push |
| 最后更新 | 2026-09-19（Asia/Shanghai），完成 P1 并收到 COMMON-001 |

## 本轮范围与修改归属

实现 DoubaoWork 的正式 Web Driver、终态/轨迹/资源采集、执行回执、浏览器评分交接、恢复和发行。任务入口必须为本地电脑/本地项目；本轮不实现 DoubaoWork General。

技术细项与证据入口：[Web 验收清单](../../../web-e2e/Web站点端到端自动化评测生产验收清单.md)中新建本 Harness/平台/版本的记录，映射 C/W、CV/WV。

先前 probe 与分析仍在独立未合入 worktree；未随 Git 收录前，它们不是接收方可用依赖。先前生成站点 smoke 不等于正式回执/评分；UI 消耗的单位与终态/Token 原生语义需实际核对。

## 依赖与完成清单

硬依赖：[COMMON](COMMON.md) 的 COMMON-CB04 已发布，且本任务的 adapter/状态/指标接口约定可取得。**不依赖 COMMON-CM01 的全部新增指标实现。** 基线未发布时可继续只读环境盘点、已有日志/fixture 分析和差异清单；不自创公共字段或依赖未合入 worktree。

- [x] P1：本机只读 probe、原生身份与字段/能力映射。证据见 [P1 记录](../../../web-e2e/evidence/doubaowork-macos-web-e2e/README.md)；缺失字段保持 null/unverified，不代表正式执行通过。
- [ ] P2：单题一次发送、可信终态、恢复和正式证据收口。
- [ ] P3：原始轨迹/资源对账与完整单题评分/回传/报告。
- [ ] P4：按场景验收三题串行、五题动态补位及声明并发。
- [ ] P5：受影响故障加固、候选不可变与仓库外发行。
- [ ] P6：代码/证据/交接集成，必需接收动作完成。

勾选附实现/集成 SHA 与验收证据；此卡不复制技术验收 PASS 表。

## 下一项与阻塞

下一项：提交当前独立实现，merge 固定 `SYNC_SHA=0dd42824...` 并回写 COMMON-001 ADOPTED；继续实现 P2 的 Web 状态机/一次发送恢复，但在桌面时段前只做离线代码。独占时段获配后，用一个全新 L1 验证本地电脑→新建项目、完整路径回读、单次发送和新原生 session 捕获。

当前依赖缺口：COMMON-001/CB-A 已发布，但其 General Schema 对本 Web 任务不适用；COMMON 的 Web CB-B 仍需提供 native identity/provenance、多 artifact trace、公共 finalizer、平台进程清理 hook 和发行装配。P2 客户端离线状态机可继续；缺少可信原生终态/cwd/进程清理时不得生成正式完整回执。

## 本机现场与恢复

当前没有本任务 queue、worker 或活动批次；仅只读观察到 DoubaoWork 2.28.12 的既有进程、loopback `9260` 和旧 smoke 完成页，不能据此推断整台桌面空闲。P1 未截图、未点击、未发送、未启动/重启客户端；本地证据根为 `/Users/gzx/debug-workspace/e2e-evaluate/doubaowork-macos-web-e2e/`。旧 smoke 的显式 session 旁路解析不回填历史 execution/score/submission。

下一桌面时段材料已写入 P1 记录：应用为 DoubaoWork 2.28.12；范围限一个全新 L1 的本地电脑→新建项目、目录回读、一次发送和新 session 捕获；操作前检查活动/待处理会话；发送临界区未知时停在 NEEDS_ATTENTION，不重发；不切模型、不提升权限、不代答追问。

## 接收记录

| 交接 ID | 状态 | 已采用集成 SHA | 处理结果、验收证据/阻塞 | 下一项 |
| --- | --- | --- | --- | --- |
| COMMON-001 | SEEN | 待 merge；固定 `SYNC_SHA=0dd42824...`，推荐源码 `ed366b30...`，CB-A `abce5da8...` | 已读取交接与 General adapter 接口；General Schema 对 Web 不适用。当前无活动批次，先提交独立修改再 merge；Web CB-B 缺口见 P1 记录 | 提交、merge、回写 ADOPTED 后继续 P2 离线状态机 |

## 本轮交付

P1 已形成 DoubaoWork 专属只读 probe、平台/source discovery、原生 trajectory 旁路解析、macOS 目录 helper、脱敏 fixtures、14 个 Node 测试和证据记录；最终只读实机 probe 退出码 0，原生旁路提取退出码 0，Swift 仅 typecheck。没有新 Prompt、正式 execution/collect/评分/回传/报告或发行证据。当前待提交、待 merge COMMON-001、未 push；完成后新增本任务交接并登记实现 SHA。
