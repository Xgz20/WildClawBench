# DoubaoWork macOS Web E2E 能力与 canary 证据

证据日期：2026-09-19（Asia/Shanghai）。任务：`MAC-DOUBAOWORK-WEB`。状态：**P1 完成；P2 已完成一次开发 canary 的单次发送、UI/native session 绑定和站点文件生成，可信终态、cwd、进程清理和正式 Web 闭环仍未完成**。

本文记录本任务分支上的只读 probe、旧 smoke 原生证据旁路解析、脱敏 fixture、`SLOT-MAC-20260919-01` 开发 canary 与公共接口缺口。它不把旧 smoke 或本次 UI 完成候选升级为正式 execution/collect/评分证据，也不声明 DoubaoWork 已达到 Web 主流程生产可用。

## 1. 当前环境与只读 probe

| 项目 | 当前只读实测 |
| --- | --- |
| OS / 架构 | macOS 26.6.2（25G83）/ x86_64 |
| 客户端 | `/Applications/DoubaoWork.app`，Bundle ID `com.work.pc.doubao`，2.28.12 |
| 控制端点 | `127.0.0.1:9260`；唯一监听者命令路径属于同一 app 内 `DoubaoWork Browser` |
| 浏览器 / CDP | Chrome 147.0.7727.149 / Protocol 1.3 |
| HTTP discovery | 唯一 `type=page` 的 `doubaowork://doubaowork-chat/chat/<id>`；另有同 hostname 的 `type=other`，不作为可控页面 |
| Playwright | 唯一 `chrome://doubaowork-chat/chat/<id>`；conversation ID 哈希与 discovery 一致 |
| DOM | 可读，`main=1`、`dialog=0`、`contenteditable=1`；只保存计数和脱敏 URL，不保存标题正文、aria 或截图 |
| 原生数据根 | `.sessions` 与 `sdk_storage/log` 均存在；probe 只保存 metadata，不扫描最近 session 绑定任务 |
| 客户端状态改变 | 无；没有点击、输入、模型/权限切换、Prompt 发送、启动或重启；probe 后原 PID 和监听端口仍保持 |

仓库外原件：`<DEBUG_ROOT>/p1-readonly-20260919-v2/probe.json`，SHA-256 `ae37247eff8b9ee022ee4d7424857aafe33cb157d0ad54d193d7dc9440ed635c`。`<DEBUG_ROOT>` 为 `/Users/gzx/debug-workspace/e2e-evaluate/doubaowork-macos-web-e2e`，不进入仓库或发行包。

开发中先后发现并修复两项 probe 自身问题：HTTP target 过滤最初误把 `type=other` 算作页面；Playwright 方法解构后丢失绑定。两次都在连接/发送前或只读连接阶段失败，没有改变客户端状态。最终 v2 报告退出码为 0；这只证明只读连接能力，不证明当前可发送、可恢复或可正式收口。

## 2. 原生证据布局与字段映射

旧 smoke 已捕获的 UI conversation ID 与当前页面哈希一致，且精确对应：

```text
~/Library/Application Support/DoubaoWork/Default/.doubaowork/
  agent_mode/workspace/.sessions/<conversation-id>/
    agents/<agent-id>/system/trajectory.jsonl
```

对该显式 ID 运行 `native-evidence.mjs`，没有扫描“最近目录”。原始 trajectory 为 3 行、3,079 字节，SHA-256 `de96a96ae991dfce8a592c78ab8fab01fd2af2746668d1f6daa4cc5c00de8d96`；仓库只保留字段形状相同的脱敏 fixture。旁路输出 `<DEBUG_ROOT>/p1-native-evidence-20260919/native-evidence.json` SHA-256 为 `bb37bb9fb5913303c11a6d5d6e99dff73a102d289eab439f54e6c10fd188b483`。

| 目标字段 / 能力 | 当前原生来源 | 当前映射 | 状态与边界 |
| --- | --- | --- | --- |
| conversation/session | CDP URL + `.sessions/<id>` | 两者 ID 精确一致；仓库证据只存哈希和长度 | 单旧样本已观察；新 attempt 仍须重新捕获并核对 |
| turn ID | 未发现 | `null` | `unavailable`，不以 task ID/UUID 伪造 |
| native cwd | session/trajectory 未提供 | `null`；requested workspace 单独保存 | `unverified`；目录 tooltip 完整路径回读不能冒充 native cwd |
| Prompt | trajectory `role=user/content` | 可规范化为 user message | 私有证据保留；入仓 fixture 已替换正文 |
| 工具调用 | `tool_calls[].id/type/function.name/function.arguments` | call ID、名称、参数和原始行定位 | 已知小计 1；完整分母未知，状态 `partial` |
| 工具结果 | `role=tool/tool_call_id/content` | 与 call ID 关联 | 1/1 已匹配；无结构化成功字段，业务 outcome 保持 `unknown` |
| 最终回复 | 旧 UI smoke 可见；trajectory 无最终 assistant 行 | trajectory 中不补造 | 原生 trace `partial`；正式 final reply 需另存 UI 证据并标明来源 |
| 可信终态 | 未发现 session/turn 完成事件 | `terminal.status=unverified` | UI 回复/操作控件只是候选，不能写 `SUCCEEDED` |
| Token / request | trajectory 与已绑定 agent 日志未发现 | 全部 `null` | `unavailable`，不是真实零 |
| 耗时 | trajectory 无可信时间戳和终态边界 | 两类 duration 均 `null` | `unavailable` |
| 积分 | 未发现绑定当前 session/attempt 的结算来源；浏览器日志显示 credit 模块未启用 | value/unit 均 `null` | `unavailable`，不能从 UI“消耗”或 Token 反推 |
| agent infra 日志 | `sdk_storage/log/agent_infra/*.log` | 只登记相对路径/大小/mtime | 能看到 runtime/file tool 生命周期，但没有会话绑定，不能混入本题 trace/指标 |

解析结果摘要：user message 1、assistant tool call 1、tool result 1、assistant final message 0；`NATIVE_CWD_UNAVAILABLE`、`NATIVE_TERMINAL_UNAVAILABLE`、`FINAL_ASSISTANT_MISSING_FROM_TRAJECTORY` 三个缺口均保留。Token、请求数、缓存、推理、耗时和积分全部为 `null`；工具调用仅输出 known subtotal 与 `coverage={numerator:1, denominator:null}`。

## 3. 本分支实现与验证

专属目录：`tools/report/skills/web-e2e/execute-web-e2e/drivers/doubaowork/`。

- `probe.mjs`：校验 app/Bundle ID、唯一 loopback 监听者、CDP 版本、唯一 page target 和只读 DOM；默认不产出敏感截图/aria。
- `platform.mjs`：只读应用身份、监听进程和原生 source metadata 发现；session 必须显式传入数字 ID。
- `native-evidence.mjs`：有界读取显式 session 的普通 `trajectory.jsonl`，输出 adapter 私有旁路证据；不修改源文件或历史 execution。
- `state.mjs`：客户端专属 automation journal 与恢复决策；保存 Prompt SHA 而非正文，在 UI click 前原子登记唯一 dispatch attempt，并用 UI/native 两组发送前基线失败关闭地绑定新 session。当前不生成正式 execution record。
- `driver.mjs`：只接受真实 v3 prepared task；选择单题根而非候选 `workspace/`；完整 tooltip、项目 ID、项目名、权限、模型和 Prompt 富文本逐块回读后单次发送；排他锁记录 host/PID/start identity 并拒绝 symlink 祖先、活 worker 和 stale 自动接管；普通恢复只观察。
- `select-folder.swift`：迁入并加固旧 probe helper；拒绝多主应用、相对/符号链接目录，仍要求客户端 tooltip 完整路径二次回读；本次 canary 已用于选择单题根。
- `test/fixtures/`：Prompt、文件内容、工具结果、绝对路径、真实 session/agent ID 均已替换；没有账号、认证、历史侧栏或截图。

实现 SHA：P1 `f168f2e4c7e5e447249cfb7e96b0d195b99e3e60`；P2 离线 journal `d183e28f2224aed40fd14ae43d8f7ab9ce6cbb0b`；开发 canary 的事后代码/证据提交 `47dcaee`。`47dcaee` 包含 live observation 后追加的修复，不是精确 live 代码快照。

Focused checks：Node 39/39 通过；六个 `.mjs` `node --check` 通过；`swiftc -typecheck select-folder.swift` 与 `git diff --check` 通过。只读实机 probe、开发 canary 单次 dispatch/session 绑定和离线 native snapshot 均退出码 0；这些仍不能替代可信原生终态、P3 正式收口或评分闭环。

## 4. `SLOT-MAC-20260919-01` 开发 canary

仓库内脱敏索引：[canary-slot-mac-20260919-01.json](canary-slot-mac-20260919-01.json)。仓库外原件位于 `<DEBUG_ROOT>/slot-mac-20260919-01-canary/development-run-03/`；真实 conversation/session ID、截图、最终回复、原始 trajectory 和私有 automation state 不进入 Git。

- 输入是 prepare 公共入口生成的真实 `wildclawbench.web-e2e-batch/v3` L1，Prompt SHA-256 为 `04816a6c...c29f`，客户端选择单题根，未暴露 score/private-scoring。
- prepared input/Skills 包冻结在源码 `c098a2e386baec6b04ed4af615349bea974f0746`：execute 1.13.1、run 1.4.1、orchestrate 0.3.1、score 4.5.4、report 1.1.1。这是输入包身份，不是实际 live Driver 的精确源码身份。
- live automation state 只记录 Driver 0.3.0；当时仓库 base 为 `c098a2e...`，Driver 处于未提交的多轮迭代状态，没有归档运行时 Driver 文件哈希或 dirty diff，故 `source_revision=null`、精确 live 代码快照未冻结。事后提交 `47dcaee` 还包含 observation 唯一文件名和 pre-send retry 等 live 后修复，不能反向充当精确 live revision。
- 四次发送前失败分别暴露 tooltip 等待/`~/` 规范化、遗留 dialog、项目创建后未进入新对话、ProseMirror 尾部空段问题；每次 `dispatch_attempt_count=0`，原状态 no-clobber 归档后才显式续跑。
- 唯一实际发送的 attempt 为 `dispatch_attempt_count=1`；实际模型“自动 高”、权限“按需确认”；UI conversation 与 native session directory 的 SHA-256 均为 `a672e6e3...3709c`。恢复只按该绑定观察，没有重发。
- 11:39:32Z 的早期 observation 仍有当前会话 busy spinner，145 字节回复只是部分状态；其中 `SLOT_RELEASED` 结论已作废。11:47:06Z 最新 observation 的 busy/stop/dialog/question/approval 均为 0，UI 回复候选为 1,893 字节，但仍是 `trusted=false`。
- live revision 复用了固定回复/截图/native 文件名，因此最新 observation 指向的回复原件仍是早期 145 字节部分内容；索引明确把该引用判为无效，不声称保存了最新 UI 回复/截图。代码已改为每次 observation 唯一文件名，并要求回复文件 SHA/字节数与同次 DOM 一致，但这项修复尚未重新占用桌面验证。
- 释放桌面后从已绑定 session 只读重建 native snapshot：29 个规范化事件、工具调用 known subtotal 14、coverage denominator 为 `null`；`native_cwd=null`、`terminal.status=unverified`。轨迹中能看到指向候选 workspace 的 Bash 建目录和 Write 写文件，但这只能证明发生过写入，不能补出可信终态或 cwd。
- 20:11:13+08:00 的只读文件系统复核确认候选 workspace 有 4 个普通文件、0 个符号链接、0 个已知禁止运行时目录：`.gitkeep` 0 字节；`countdown/index.html` 18,216 字节，SHA-256 `b43018a6...8f36d`；桌面截图 51,639 字节，SHA-256 `f07eafe4...f647`；移动截图 51,491 字节，SHA-256 `5020624a...ad2c`。HTML 的 mtime 晚于两张截图，且没有正式 provenance，因此不声称截图对应当前 HTML。旧索引中“只有 `.gitkeep`、未生成站点”的判断错误，已更正为“站点已生成但未正式收集、未评分”。
- 20:20:10+08:00 的只读进程核验发现同一进程组内的 DoubaoWork sandbox Bash/Python 两个进程仍以 `workspace/countdown` 为 cwd，其中 Python（PID 83960）监听 TCP 8848；没有终止它们。该现场直接表明进程清理尚未完成，不能把 UI idle 写成完整执行终态。
- 自动化状态保持 `NEEDS_ATTENTION`，未生成正式 `execution_record.json`、execution receipt、score 或 report。11:47:06Z 已确认无 busy/stop/pending，`SLOT-MAC-20260919-01` 为 `SLOT_RELEASED`，之后未再连接或操作 DoubaoWork UI。

## 5. COMMON-002 采用结果与剩余公共接口

本分支已合入 `SYNC_SHA=46a23a43572aed34bc2eec457d67423e2bce08af`，COMMON-002 必需源码 `eb23784a7ed25b0f0364db0392783de277b22b96` 为当前 HEAD 祖先。已采用 desktop-app-discovery 1.2.0、execute-web-e2e 1.14.0、run-web-e2e 1.4.2 和 orchestrate-web-e2e 0.3.2；prepare 4.4.0 已识别 `harness=doubaowork`。这些是 canary 后采用的当前分支版本，不追溯改写 live Driver 身份。真实安装只读 discovery 返回 `identity_verified=true`，应用仍是 `/Applications/DoubaoWork.app` 2.28.12 / `com.work.pc.doubao`。

COMMON-002 的 General trace v2 / finalizer wire 对 DoubaoWork Web **不适用**，不创建 General adapter，也不把私有 native evidence 填入 General Schema。已交付的 discovery Profile 和 prepare 支持不再列为缺口；业务身份、单次发送、真实绑定证据和 unknown 失败关闭原则继续遵守 Web Driver 契约。

剩余缺口由 Web 公共入口与本平台 Driver 共同收口：

1. `tools/report/skills/web-e2e/execute-web-e2e/drivers/metrics/{capture,collect,parsers}.mjs`：注册 `harness=doubaowork` 的 adapter hook；允许 Token/request/duration 为 `null`，工具 known subtotal 与 coverage 不得升级为完整总量；可信 source 只能是已按显式 conversation/session 绑定的 trajectory，unbound agent/browser 日志不得混入。
2. Web 公共 finalizer/automation state（CB-B）：接收 `conversation_id` 与 `session_directory_id`，允许客户端原生不存在的 `turn_id/cwd=null`；在 tooltip 完整路径、Prompt SHA、发送一次、session 目录证据和可信终态未共同满足前，保持 `NEEDS_ATTENTION/unverified`，不能生成 `integrity.valid=true`。
3. Web trace/provenance（CB-B）：支持同一 attempt 的多 artifact（规范化 transcript、UI 最终回复、原生 trajectory source index）；每份保存相对路径、SHA、大小、原始/脱敏范围和 completeness，不强制 AstronStudio session 字段。
4. 平台进程清理 hook（CB-B）：DoubaoWork 尚未证明按 session + 完整 cwd 精确枚举候选子进程；必须先允许 `supported=false` 并阻断正式完整收口，不能按 DoubaoWork/Node 名称宽泛终止。
5. Web execute/run 公共路由、正式 finalizer/receipt 与发行清单：execute Skill 还没有 `run-doubaowork` 入口，run-web-e2e 也没有 DoubaoWork application 路由。正式加入前默认 `ui_slots=1/run_slots=1`，不继承其他 Harness 的三槽声明。

## 6. 后续动作与再次占用桌面的前置条件

当前 canary 已释放时段，不再连接或操作 DoubaoWork UI。先离线补齐 metrics、Web finalizer/receipt、可信 terminal/cwd 方案、精确 cleanup 和公共路由；这些依赖仍缺失时继续保持 `NEEDS_ATTENTION`。

以后若另行批准新批次和独占时段，不重复本次 Prompt，只复验 observation 唯一文件、可信终态/cwd/清理的新实现：

- 应用：`/Applications/DoubaoWork.app` 2.28.12，macOS x86_64；不擅自升级、重启或切模型。
- 操作：先只读枚举 page/session 与是否存在运行/待处理会话；创建本题新项目；运行目录 helper；tooltip 回读完整路径；保持当前非空模型显示和当前权限；写入 intent/Prompt SHA/attempt 后仅发送一次；捕获新 conversation ID；只观察，不评分。
- 恢复：`READY_TO_SEND` 后中断先查新 session；无法唯一确认是否发送就停在 `NEEDS_ATTENTION`，不重发。未知终态、追问或授权转人工；不代答。
- 收口：当前没有可信原生终态/cwd/进程清理，所以首次时段目标是获得缺口样本和失败关闭行为，不预承诺正式 execution receipt。原始日志仍只留 `<DEBUG_ROOT>`。
