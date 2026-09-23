# MAC-DOUBAOWORK-WEB-003：原生字段审计、等价绑定与候选进程收口交接

> 历史档案：保留迁移前的日期、版本、结果和失败记录。“当前/下一步”、旧派发和桌面时段要求仅属当时快照。现行集成要求及各 Harness 进度只维护在[统一集成契约](../../../端到端自动化评测Harness接入契约.md)。

> 历史档案（2026-09-21 冻结）：仅供提交与证据追溯，旧派发、时段、负责人、下一项和跨平台并行安排均已退役。当前状态和操作以 [General E2E 接续入口](../../../端到端自动化评测Harness接入契约.md#integration-progress) 为准；本文件不再例行更新。

| 字段 | 值 |
| --- | --- |
| 交接 ID / 时间 | MAC-DOUBAOWORK-WEB-003 / 2026-09-19（Asia/Shanghai） |
| 来源任务 / 目标任务 | MAC-DOUBAOWORK-WEB / COMMON、后续 DoubaoWork Web 接线 |
| 前序交接 | `MAC-DOUBAOWORK-WEB-001`、`MAC-DOUBAOWORK-WEB-002` 已消费并保持原样 |
| 当前分支 | `feat/doubaowork-macos-web-e2e`；未 push、未合主分支 |
| 当前 HEAD | `21bd705aed8562ae9c4c79e1bb85824f10c5946b`（合入 COMMON-004 修订） |
| COMMON-004 固定同步 | 远端 `feature/astroncode-eval` 的 `ddba8d645da18af75d04fad4a7a47ec1aaa1c161`；必需源码 `2023b4d5d1d703c81ff8ed15e0d5ada29cd0dca4` 已核验为祖先 |
| 集成状态 | ADOPTED；`6ec2912` 已合入 `feat/e2e-harness-contract`，仅完成离线 finalizer 适配，未操作 DoubaoWork 客户端或历史 canary |

## 1. 已绑定原生样本的审计结论

本轮只读复核使用已绑定的 2.28.12 canary session；没有重新连接或操作 DoubaoWork UI，也没有重发 Prompt、修改候选或处理历史残留进程。

- session 目录共 6 个文件；`trajectory.jsonl` 28 行，规范化后 29 个事件。
- trajectory 顶层可观察字段只有 `role`、`content`、`tool_calls`、`tool_call_id`；没有时间戳、cwd、session/turn 状态或结束事件字段。
- SDK 日志与 session 的绑定核验：仅按 session ID 命中的文件数为 0，仅按完整 task root 命中的文件数为 0，同时绑定两者的文件数为 0。
- 工具结果中的 `completed`、`pwd` 或绝对 `file_path` 只能证明工具活动；不能提升为 Agent 原生终态或 session 原生 cwd。
- 新解析器在真实样本上的结果为：`native_capabilities.terminal.status=unavailable`、`authoritative_source=null`、`candidate_event_count=0`；`workspace_binding.status=unverified`、`native_cwd=null`；请求路径引用 5 次，其中结构化 tool path 2 次、tool result path 3 次；`tool_activity_is_sufficient=false`。
- 旧有公共占位字段 `terminal.status` 仍为 `unverified`。native 字段缺失不应永久阻塞 Web 适配，但也不能伪造字段或把该 canary 改写为成功。

## 2. 本轮平台代码交付

### 2.1 精确候选进程收口

Driver 0.4.0 的基础提交为 `0f6d2c6717950720775a8fffe813f98ebf0237d0`；审查发现动态生命周期反例后，修复提交为 `40c2f71ad06903967344fe9d4ef951fc7c57ecd0`。当前 `process-cleanup.mjs` 的接口为：

- `snapshotDoubaoCandidateProcesses(candidateWorkspace)`：要求普通绝对 workspace，冻结 canonical path/device/inode；用两次 `ps` 夹住 `lsof` cwd 读取，只接受读取前后 PID/PPID/PGID/启动时间/可执行文件稳定的身份。cwd 等于候选目录或位于其下的是 seed，再按父链加入后代；`..cache` 等合法 basename、同名其他任务和路径前缀碰撞均按边界正确处理。
- `cleanupDoubaoCandidateProcesses(candidateWorkspace)`：首次接纳时同时验证身份和 cwd/父链归属；之后跨 snapshot 保留已验证 PID+启动身份，即使父进程先退出、子进程重挂或同身份进程改变 cwd 也继续追踪。每次 TERM/KILL 前再次核对锁定 workspace 实体和进程身份；PID 一旦复用，本轮永久禁发信号。workspace 实体变化、身份/归属无法验证、信号失败、残留或 quiet window 不足均失败关闭。

该模块仍未接入公共 finalizer/hook/receipt，也未用于历史 canary；不按 Python、Node、DoubaoWork 或端口名宽泛清理，不结束整个进程组。

### 2.2 Web 等价证据链

Driver 0.5.0 的交付提交为 `2e21a54d6fa4a8d4c2d4005a2d31df77f927677d`：

- `conversation → project → 完整 tooltip workspace`：状态保存 project ID SHA、workspace tooltip 显示 SHA、workspace 路径边界和来源；绑定快照要求当前会话所属 project ID 与已确认 project 一致，project 控件唯一回读。
- Prompt 发送前保存 raw SHA/bytes，并按 `crlf-to-lf+strip-trailing-newlines/v1` 生成回读 SHA/bytes；发送后只接受同一 conversation 的最新 user message 精确匹配，旧回复、错误 conversation、错误 project 或规范化不一致均失败关闭。
- 每次 `inspectPage` 都记录并由 `validateObservationBinding(state, snapshot)` 核对当前 conversation ID；恢复不再只在导航后检查一次。
- 正向完成候选要求非空最终回复和可见最终回复操作区这一正向 UI 标识，并同时要求当前绑定会话无 busy/stop/pending/error。稳定文本、工具结果中的 `completed`、其他会话 busy 或旧 canary 文件不能单独升级为终态。
- 该交付仍只生成开发 observation；公共 Web v1 finalizer、正式 execution record/receipt、collector/parser、run/execute route 和 cleanup hook 尚未接线，因此不会声明正式 `SUCCEEDED` 或 `integrity.valid=true`。

## 3. 离线验证

DoubaoWork Driver 当前专属测试为 **60/60**，包含：

- 发送前/发送后 Prompt 规范化和 user message SHA/bytes 回读；错误会话、错误 project、旧回复、Prompt 不匹配、缺少正向完成标识和 pending/error 反例；
- ps/lsof 身份夹取、`..cache` 路径边界、PID 初次复用后重入、父退出后的 reparent 子进程、首次归属变化、已验证后同身份 cwd 变化、workspace inode 替换；
- 真实 cleanup 测试只在唯一临时目录创建并终止本测试自建 Node 父子进程，回读零残留；
- finalizer adapter 的 UI/native/cleanup/candidate 门禁、native 身份不一致和发送前 Prompt 未回读反例；
- 所有现有 Driver/fixture/state/native-evidence 测试均包含在上述 `npm test` 结果中。

另有 Node 语法检查、Swift helper typecheck 和 `git diff --check`；这些是离线代码证据，不是桌面真机 E2E、评分、回传或报告证据。

## 4. canary 身份与边界

历史 `SLOT-MAC-20260919-01` 仍是 Driver 0.3.0 的一次实际发送，精确 live revision 未冻结；`0f6d2c6`、`40c2f71`、`2e21a54` 均是 canary 后离线开发交付，不能反向冒充 live 运行身份。旧 canary 继续保持 `NEEDS_ATTENTION`，不追溯补写 terminal/cwd、cleanup、正式 execution/score/submission/report，也不因本交接重新占用桌面。

## 5. 尚未完成的接线与下一步

1. COMMON 注册 Doubao Web v1 collector/parser、严格 evidence gate 和 macOS execute/run/application route；保持现有其他 Harness 语义不变，Doubao 默认 `ui_slots=1/run_slots=1`。
2. 将平台的 binding snapshot、Prompt 回读、UI final candidate、native artifact index、cleanup/quiet 结果接入公共 automation sidecar、`collection.sources[]` 与正式 receipt；未接线前仍保持 `NEEDS_ATTENTION`。
3. 在全新、明确批准的独占桌面时段，以冻结的 Driver/Skill/客户端身份从 probe 和单题重新验收；不重复本次 Prompt，不把离线 60/60 或旧 canary 作为生产准入。
4. 在 cleanup hook/route/finalizer/receipt 通过组合测试与新批次验收前，不声明 DoubaoWork Web 已完成正式执行、评分、回传或报告闭环。

## 6. Driver-side finalizer adapter 增量（本轮）

本轮来源提交 `6ec29126d9f49bace96e9c4823c08f9728ca700d` 新增 `finalizer.mjs`，导出 `assessDoubaoWebFinalization(...)` 和
`wildclawbench.doubaowork-web-finalizer-assessment/v1`。它是 Web v1 公共 receipt 的
driver-side 适配器，不修改公共 `run-web-e2e` 路由，也不直接生成或覆盖正式
`execution-receipt.json`。开发 observation 现在会附带 assessment，后续公共接线可
消费同一份稳定门禁结果。

assessment 的有效条件为：UI conversation/project/workspace/Prompt 回读和稳定完成候选
全部通过；native evidence schema 且 conversation/session/workspace 身份一致；精确
cleanup `supported=true`、`success=true`、无残留并完成 quiet window；候选 workspace
明确 `frozen=true` 且有 SHA-256。缺任一项都返回 `NEEDS_ATTENTION`、
`integrity.valid=false`，并列出失败代码。

原生终态与 cwd 始终按实际字段原样报告。即便等价 Web 证据链具备，
`native_terminal_verified` 和 `native_cwd_verified` 仍不会由 UI 状态推导。发送前摘要
也不能代替绑定 conversation 的 Prompt 回读：只有
`state.session.prompt_readback.status=verified` 才算通过。

本轮验证：Doubao Driver `npm test` **60/60**，所有 Driver 目标文件 `node --check`
通过，`git diff --check` 通过。未连接 DoubaoWork、未操作真实进程、未处理历史 canary。
