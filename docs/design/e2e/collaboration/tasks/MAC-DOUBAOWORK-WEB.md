# MAC-DOUBAOWORK-WEB：DoubaoWork macOS Web

| 字段 | 当前值 |
| --- | --- |
| 唯一负责人 / 实际任务 ID | 独立 Codex 开发任务 / `MAC-DOUBAOWORK-WEB` |
| 工作状态 / 代码交付 | ACTIVE / LOCAL_ONLY；P1 只读适配与 P2 离线发送恢复 journal 已实现，尚未集成或真机验证 |
| 分支 / worktree | `feat/doubaowork-macos-web-e2e` / `<主项目>/.agents/doubaowork-macos-web-e2e`，已核验绑定 |
| 创建 base / 已采用公共基线 | `03c38f280a64ad9bc9308c768f0f5795050355cc` / COMMON-001 已 ADOPTED；公共基线 merge `6cd5aac76055503380af6380cd203196515de642` |
| 已读台账的 SYNC_SHA / 实际实现 HEAD | 固定 `0dd42824cb8eb510ab126fd74553f93312c9f201`；P2 实现 `d183e28f2224aed40fd14ae43d8f7ab9ce6cbb0b` |
| 同步源 / 实现与集成 SHA | `github/feature/astroncode-eval`；P1 `f168f2e4c7e5e447249cfb7e96b0d195b99e3e60`、P2 `d183e28f2224aed40fd14ae43d8f7ab9ce6cbb0b`；未集成、未 push |
| 最后更新 | 2026-09-19（Asia/Shanghai），完成 P2 离线 journal 与 COMMON 接口交接 |

## 本轮范围与修改归属

实现 DoubaoWork 的正式 Web Driver、终态/轨迹/资源采集、执行回执、浏览器评分交接、恢复和发行。任务入口必须为本地电脑/本地项目；本轮不实现 DoubaoWork General。

技术细项与证据入口：[Web 验收清单](../../../web-e2e/Web站点端到端自动化评测生产验收清单.md)中新建本 Harness/平台/版本的记录，映射 C/W、CV/WV。

先前 probe 与分析仍在独立未合入 worktree；未随 Git 收录前，它们不是接收方可用依赖。先前生成站点 smoke 不等于正式回执/评分；UI 消耗的单位与终态/Token 原生语义需实际核对。

## 依赖与完成清单

硬依赖：[COMMON](COMMON.md) 的 COMMON-CB04 已发布，且本任务的 adapter/状态/指标接口约定可取得。**不依赖 COMMON-CM01 的全部新增指标实现。** 基线未发布时可继续只读环境盘点、已有日志/fixture 分析和差异清单；不自创公共字段或依赖未合入 worktree。

- [x] P1：本机只读 probe、原生身份与字段/能力映射。证据见 [P1 记录](../../../web-e2e/evidence/doubaowork-macos-web-e2e/README.md)；缺失字段保持 null/unverified，不代表正式执行通过。
- [ ] P2：单题一次发送、可信终态、恢复和正式证据收口。客户端离线 journal 与恢复决策已完成；真机一次发送、可信终态和正式收口仍未验证。
- [ ] P3：原始轨迹/资源对账与完整单题评分/回传/报告。
- [ ] P4：按场景验收三题串行、五题动态补位及声明并发。
- [ ] P5：受影响故障加固、候选不可变与仓库外发行。
- [ ] P6：代码/证据/交接集成，必需接收动作完成。

勾选附实现/集成 SHA 与验收证据；此卡不复制技术验收 PASS 表。

## 下一项与阻塞

下一项：等待 COMMON 分配独占桌面时段；获配后只用一个全新 L1 验证本地电脑→新建项目、完整路径回读、保持并回读模型/权限、单次发送和新原生 session 捕获。发送结果、终态或绑定任一不唯一时进入 `NEEDS_ATTENTION`，不重发。

当前依赖缺口：COMMON-001/CB-A 已采用，但其 General Schema 对本 Web 任务不适用；COMMON 的 Web CB-B 仍需提供 native identity/provenance、多 artifact trace、公共 finalizer、平台进程清理 hook、指标注册和发行装配。精确需求见 [MAC-DOUBAOWORK-WEB-001](../handoffs/MAC-DOUBAOWORK-WEB-001.md)。缺少可信原生终态/cwd/进程清理时不得生成正式完整回执。

## 本机现场与恢复

当前没有本任务 queue、worker 或活动批次；仅只读观察到 DoubaoWork 2.28.12 的既有进程、loopback `9260` 和旧 smoke 完成页，不能据此推断整台桌面空闲。P1 未截图、未点击、未发送、未启动/重启客户端；本地证据根为 `/Users/gzx/debug-workspace/e2e-evaluate/doubaowork-macos-web-e2e/`。旧 smoke 的显式 session 旁路解析不回填历史 execution/score/submission。

下一桌面时段材料已写入 P1 记录：应用为 DoubaoWork 2.28.12；范围限一个全新 L1 的本地电脑→新建项目、目录回读、一次发送和新 session 捕获；操作前检查活动/待处理会话；发送临界区未知时停在 NEEDS_ATTENTION，不重发；不切模型、不提升权限、不代答追问。

## 接收记录

| 交接 ID | 状态 | 已采用集成 SHA | 处理结果、验收证据/阻塞 | 下一项 |
| --- | --- | --- | --- | --- |
| COMMON-001 | ADOPTED | merge `6cd5aac76055503380af6380cd203196515de642`；固定 `SYNC_SHA=0dd42824cb8eb510ab126fd74553f93312c9f201`，推荐源码 `ed366b30bc5ddd2ae35ef6361c3ac7c72ce9963a`，CB-A `abce5da832f16b48cd402ceef04a6abda544a379` | 推荐源码与 CB-A 均已核验为 SYNC_SHA 祖先并合入；General Schema 对 Web 不适用，不创建 General adapter。DoubaoWork Node 23/23、MJS 静态检查、Swift typecheck 通过 | 等待 Web CB-B 与桌面时段；相关测试通过后再记 VERIFIED |

## 本轮交付

P1 已形成 DoubaoWork 专属只读 probe、平台/source discovery、原生 trajectory 旁路解析、macOS 目录 helper、脱敏 fixtures 与证据记录；最终只读实机 probe 和原生旁路提取退出码均为 0。P2 新增客户端专属 automation journal：发送意图和 Prompt SHA 先落盘，UI click 前原子写入唯一 dispatch attempt，两组发送前基线各自唯一且新 ID 相等时才做 tentative session binding；未知状态不重发。当前 Node 23/23、5 个 MJS `node --check`、Swift typecheck 与 `git diff --check` 均通过。没有新 Prompt、正式 execution/collect/评分/回传/报告或发行证据；未 push、未合主分支。
