# MAC-DOUBAOWORK-WEB：DoubaoWork macOS Web

> 历史档案：保留迁移前的日期、版本、结果和失败记录。“当前/下一步”、旧派发和桌面时段要求仅属当时快照。现行集成要求及各 Harness 进度只维护在[统一集成契约](../../../端到端自动化评测Harness接入契约.md)。

> 历史档案（2026-09-21 冻结）：仅供提交与证据追溯，旧派发、时段、负责人、下一项和跨平台并行安排均已退役。当前状态和操作以 [General E2E 接续入口](../../../端到端自动化评测Harness接入契约.md#integration-progress) 为准；本文件不再例行更新。

| 字段 | 当前值 |
| --- | --- |
| 唯一负责人 / 实际任务 ID | 独立 Codex 开发任务 / `MAC-DOUBAOWORK-WEB` |
| 工作状态 / 代码交付 | ACTIVE / INTEGRATED；P1 已完成，P2 已完成一次开发 canary 的单次发送与 session 绑定；0.5.0 等价绑定/候选 cleanup、finalizer 与 receipt bridge 离线加固已接收，但终态仍为 `NEEDS_ATTENTION`，未正式收口 |
| 分支 / worktree | `feat/doubaowork-macos-web-e2e` / `<主项目>/.agents/doubaowork-macos-web-e2e`，已核验绑定 |
| 创建 base / 已采用公共基线 | `03c38f280a64ad9bc9308c768f0f5795050355cc` / COMMON-001、COMMON-002 均已 ADOPTED；COMMON-002 merge `ca7cc2ed74e3c8bb148ccd702c385f1ba8f62cb9` |
| 已读台账的 SYNC_SHA / 必需源码 | `46a23a43572aed34bc2eec457d67423e2bce08af` / `eb23784a7ed25b0f0364db0392783de277b22b96`，均已通过祖先检查 |
| 同步源 / 实现与集成 SHA | `github/feature/astroncode-eval`；P1 `f168f2e4c7e5e447249cfb7e96b0d195b99e3e60`、P2 journal `d183e28f2224aed40fd14ae43d8f7ab9ce6cbb0b`、canary 事后交付 `47dcaee`、COMMON-002 merge `ca7cc2e`；离线加固源提交 `40c2f71`、`2e21a54`、`5d7b6d9`；集成 `11d0182`、`b57b03e`、`0424174`；未 push |
| 最后更新 | 2026-09-20（Asia/Shanghai），接收 `MAC-DOUBAOWORK-WEB-004` receipt bridge 适配；未操作客户端 |

## 本轮范围与修改归属

实现 DoubaoWork 的正式 Web Driver、终态/轨迹/资源采集、执行回执、浏览器评分交接、恢复和发行。任务入口必须为本地电脑/本地项目；本轮不实现 DoubaoWork General。

技术细项与证据入口：[Web 验收清单](../../web/生产验收历史-20260923.md)中新建本 Harness/平台/版本的记录，映射 C/W、CV/WV。

先前 probe 与分析仍在独立未合入 worktree；未随 Git 收录前，它们不是接收方可用依赖。先前生成站点 smoke 不等于正式回执/评分；UI 消耗的单位与终态/Token 原生语义需实际核对。

## 依赖与完成清单

COMMON-001/002 已采用。desktop-app-discovery 1.2.0、execute-web-e2e 1.14.0、run-web-e2e 1.4.2、orchestrate-web-e2e 0.3.2 均已进入本分支，prepare 4.4.0 已支持 `harness=doubaowork`。COMMON-002 的 General trace/finalizer wire 对 Web 不适用；本任务仍不依赖 COMMON-CM01 的全部新增指标实现。

本次 prepared input/Skills 包绑定源码 `c098a2e386baec6b04ed4af615349bea974f0746` 和 execute 1.13.1 / run 1.4.1 / orchestrate 0.3.1；live Driver 0.3.0 则是以该 base 为起点的未提交迭代，automation state 没有 `source_revision`，也未归档运行时文件哈希/dirty diff。事后提交 `47dcaee` 包含 live 后修复，不能冒充精确 live revision。分支随后采用 COMMON-002 同样不追溯改变 canary 身份。

- [x] P1：本机只读 probe、原生身份与字段/能力映射。证据见 [P1 记录](../../../../web-e2e/evidence/doubaowork-macos-web-e2e/README.md)；缺失字段保持 null/unverified，不代表正式执行通过。
- [ ] P2：单题一次发送、可信终态、恢复和正式证据收口。客户端 journal、一次真机发送、UI/native session 绑定和只观察恢复已完成；`0.5.0` 已补 UI 等价绑定、Prompt 回读、进程重挂和恢复状态加固，`9bb30aa` 已加入 driver-side finalizer assessment，但可信终态、native cwd、公共 cleanup/receipt 和正式证据收口仍未通过。
- [ ] P3：原始轨迹/资源对账与完整单题评分/回传/报告。
- [ ] P4：按场景验收三题串行、五题动态补位及声明并发。
- [ ] P5：受影响故障加固、候选不可变与仓库外发行。
- [x] P6：代码/证据/交接集成，必需接收动作完成；集成提交为 `9bb30aa`。

勾选附实现/集成 SHA 与验收证据；此卡不复制技术验收 PASS 表。

## 下一项与阻塞

下一项：不再连接或操作 DoubaoWork UI。先补齐 Web metrics、公共 execute/run 路由、可信 terminal/cwd，并把已有 driver-side assessment/receipt bridge 与候选 cleanup 接入正式 finalizer/receipt 和发行入口；以后只有在这些实现完成且另行批准新批次/时段后才做真机复验。

当前依赖缺口：Web metrics 尚未注册 DoubaoWork；execute/run 尚无公共 DoubaoWork 路由；nullable native identity、多 artifact trace、可信终态/cwd、平台精确 cleanup、正式 Web finalizer/receipt 与发行装配尚未闭环。精确需求见 [MAC-DOUBAOWORK-WEB-001](../handoffs/MAC-DOUBAOWORK-WEB-001.md)。缺少可信原生终态/cwd/进程清理时不得生成正式完整回执。

## 本机现场与恢复

`SLOT-MAC-20260919-01` 已释放，之后未再连接或操作 DoubaoWork UI。本次唯一实际发送的 canary 仍为 `NEEDS_ATTENTION`：候选已生成 `countdown/index.html` 和两张截图，但没有可信原生终态/cwd 或正式 execution/score/submission。20:20:10+08:00 的只读现场核验还发现同一进程组内的 DoubaoWork sandbox Bash/Python 两个进程仍在候选 `workspace/countdown` 上，其中 Python 监听 8848；未执行终止，因此 cleanup 明确未完成。本地证据根为 `/Users/gzx/debug-workspace/e2e-evaluate/doubaowork-macos-web-e2e/`。

仓库内 canary 索引只保存脱敏后的 session 哈希、文件哈希和状态边界。最新 1,893 字节 UI 回复没有唯一原件；旧 `ui-final-reply.txt` 仅是 145 字节部分回复，不能冒充最终证据。

增量更正与 COMMON 接收动作见 [MAC-DOUBAOWORK-WEB-002](../handoffs/MAC-DOUBAOWORK-WEB-002.md)；已消费的 `MAC-DOUBAOWORK-WEB-001` 保持原样，不静默改写历史交接。

## 接收记录

| 交接 ID | 状态 | 已采用集成 SHA | 处理结果、验收证据/阻塞 | 下一项 |
| --- | --- | --- | --- | --- |
| COMMON-001 | ADOPTED | merge `6cd5aac76055503380af6380cd203196515de642`；固定 `SYNC_SHA=0dd42824cb8eb510ab126fd74553f93312c9f201`，推荐源码 `ed366b30bc5ddd2ae35ef6361c3ac7c72ce9963a`，CB-A `abce5da832f16b48cd402ceef04a6abda544a379` | 推荐源码与 CB-A 均已核验为 SYNC_SHA 祖先并合入；General Schema 对 Web 不适用，不创建 General adapter | 后续由 COMMON-002 记录承接 |
| COMMON-002 | ADOPTED | merge `ca7cc2ed74e3c8bb148ccd702c385f1ba8f62cb9`；`SYNC_SHA=46a23a43572aed34bc2eec457d67423e2bce08af`；必需源码 `eb23784a7ed25b0f0364db0392783de277b22b96` | 两个源码均为 HEAD 祖先；采用 discovery 1.2.0、Web execute 1.14.0 / run 1.4.2 / orchestrate 0.3.2，prepare 已支持 DoubaoWork。共享 discovery 测试 3/3 通过，真实安装只读核验 `identity_verified=true`；General finalizer/trace 不作为 Web 正式收口证据 | 补 Web metrics、execute/run 路由、terminal/cwd、cleanup、finalizer/receipt 与发行 |
| MAC-DOUBAOWORK-WEB-003 | ADOPTED | `11d0182`、`b57b03e`、`0424174`、`9bb30aa`（源提交 `40c2f71`、`2e21a54`、`5d7b6d9`、`6ec2912`） | 等价绑定、Prompt 回读、候选 cleanup 生命周期、恢复状态与 driver-side finalizer 门禁；集成树 Doubao Node 60/60、MJS 检查和 diff 检查通过；未操作客户端，未接公共 route/receipt | Web metrics、可信 native terminal/cwd、公共 cleanup/finalizer/receipt 接线 |
| MAC-DOUBAOWORK-WEB-004 | ADOPTED | `694536d`（源提交 `2e7c3b8`） | receipt bridge 仅内存映射 Web v1 字段，复用 finalizer 全部门禁；ready/native identity mismatch fixture；Doubao Node 62/62；未生成正式 receipt、未操作客户端 | 公共 route/receipt 接线与真机新 slot 前发行 |
| MAC-DOUBAOWORK-WEB-005 | ADOPTED | `f38b66f`、集成 `07b31b7` | 新增 DoubaoWork `run-doubaowork.sh/.mjs` 与 public route，注册 metrics profile，严格复用 finalizer/receipt bridge；明确拒绝 `--batch`/`--formal-receipt`；Doubao Node 64/64 | 补可信 native terminal/cwd、公共 cleanup/finalizer 接线；新时段验证后才能开放 batch/formal receipt |

## 本轮交付

P1 已形成 DoubaoWork 专属只读 probe、共享 discovery 接入、原生 trajectory 旁路解析、macOS 目录 helper、脱敏 fixtures 与证据记录。P2 Driver 0.5.0 已完成唯一 dispatch、严格项目/路径/模型/权限/Prompt 回读、conversation→project→workspace 等价绑定、进程身份锁、候选 cleanup 加固与只观察恢复；`9bb30aa` 增加不直接生成 receipt 的 driver-side finalizer assessment，`694536d` 增加只读内存 receipt bridge，`f38b66f` 增加 metrics 注册与离线公共 route，且仅接受会话级 `prompt_readback.status=verified`。当前 route 明确拒绝 batch/formal receipt；canary 仍因可信终态/cwd、公共 cleanup/finalizer 和正式 evidence 收口缺失保持 `NEEDS_ATTENTION`。没有正式 execution/评分/回传/报告或发行证据。未 push、未操作客户端。
