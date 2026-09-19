# DoubaoWork macOS Web E2E P1 只读能力与字段映射

证据日期：2026-09-19（Asia/Shanghai）。任务：`MAC-DOUBAOWORK-WEB`。状态：**P1 完成；P2 客户端离线 journal 已实现，真机执行及正式 Web 闭环未开始**。

本文记录本任务分支上的只读 probe、旧 smoke 原生证据旁路解析、脱敏 fixture 与公共接口缺口。它不把 2026-09-19 的旧站点生成 smoke 升级为正式 execution/collect/评分证据，也不声明 DoubaoWork 已达到 Web 主流程生产可用。

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
- `select-folder.swift`：迁入并加固旧 probe helper；拒绝多主应用、相对/符号链接目录，仍要求客户端 tooltip 完整路径二次回读。当前只通过静态 typecheck，没有在本轮运行。
- `test/fixtures/`：Prompt、文件内容、工具结果、绝对路径、真实 session/agent ID 均已替换；没有账号、认证、历史侧栏或截图。

实现 SHA：P1 `f168f2e4c7e5e447249cfb7e96b0d195b99e3e60`；P2 离线 journal `d183e28f2224aed40fd14ae43d8f7ab9ce6cbb0b`。

Focused checks：Node 23/23 通过；五个 `.mjs` `node --check` 通过；`swiftc -typecheck select-folder.swift` 与 `git diff --check` 通过。只读实机 probe 最终退出码 0；原生旁路提取退出码 0。P2 新增测试全部是 fixture/离线状态测试，不能替代真机一次发送、P3 正式收口或评分闭环。

## 4. COMMON / CB-B 精确接口需求

本任务已审阅 COMMON-001 的 General CB-A。`wildclawbench.general-e2e-execution-state/v1` 对 DoubaoWork Web **不适用**，不创建 General adapter，也不把私有 native evidence 填入 General Schema。业务身份、单次发送、真实绑定证据和 unknown 失败关闭原则继续遵守 Web Driver 契约。

以下公共文件/行为由 COMMON 协调，本任务不在平台分支修改：

1. `tools/report/skills/web-e2e/execute-web-e2e/drivers/metrics/{capture,collect,parsers}.mjs`：注册 `harness=doubaowork` 的 adapter hook；允许 Token/request/duration 为 `null`，工具 known subtotal 与 coverage 不得升级为完整总量；可信 source 只能是已按显式 conversation/session 绑定的 trajectory，unbound agent/browser 日志不得混入。
2. Web 公共 finalizer/automation state（CB-B）：接收 `conversation_id` 与 `session_directory_id`，允许客户端原生不存在的 `turn_id/cwd=null`；在 tooltip 完整路径、Prompt SHA、发送一次、session 目录证据和可信终态未共同满足前，保持 `NEEDS_ATTENTION/unverified`，不能生成 `integrity.valid=true`。
3. Web trace/provenance（CB-B）：支持同一 attempt 的多 artifact（规范化 transcript、UI 最终回复、原生 trajectory source index）；每份保存相对路径、SHA、大小、原始/脱敏范围和 completeness，不强制 AstronStudio session 字段。
4. 平台进程清理 hook（CB-B）：DoubaoWork 尚未证明按 session + 完整 cwd 精确枚举候选子进程；必须先允许 `supported=false` 并阻断正式完整收口，不能按 DoubaoWork/Node 名称宽泛终止。
5. `tools/report/e2e-shared/desktop-app-discovery/profiles.mjs`、`components.json`、确定性构建装配与 vendored 副本：新增 `doubaowork` 的 macOS app/Bundle ID/端点 Profile，构建时从 canonical 装配，禁止手改 vendor。
6. Web prepare/run/发行路由：`prepare_web_e2e_workspaces.py` 的 known harness、execute Skill 入口/包布局、`run-web-e2e` macOS application 路由及安装清单需要纳入 DoubaoWork；正式加入前先完成单题 P2/P3，默认 `ui_slots=1/run_slots=1`，不继承其他 Harness 的三槽声明。

## 5. 下一阶段桌面时段申请材料

待 COMMON 分配独占时段后，P2 只覆盖一个全新 L1、本地电脑→新建项目：

- 应用：`/Applications/DoubaoWork.app` 2.28.12，macOS x86_64；不擅自升级、重启或切模型。
- 操作：先只读枚举 page/session 与是否存在运行/待处理会话；创建本题新项目；运行目录 helper；tooltip 回读完整路径；保持当前非空模型显示和当前权限；写入 intent/Prompt SHA/attempt 后仅发送一次；捕获新 conversation ID；只观察，不评分。
- 恢复：`READY_TO_SEND` 后中断先查新 session；无法唯一确认是否发送就停在 `NEEDS_ATTENTION`，不重发。未知终态、追问或授权转人工；不代答。
- 收口：当前没有可信原生终态/cwd/进程清理，所以首次时段目标是获得缺口样本和失败关闭行为，不预承诺正式 execution receipt。原始日志仍只留 `<DEBUG_ROOT>`。
