# WorkBuddy macOS General E2E 只读能力与字段映射证据

日期：2026-09-19（Asia/Shanghai）。任务：`MAC-WORKBUDDY-GENERAL`。范围：P1 只读 probe、原生身份/终态/轨迹/资源字段映射、CB-A 状态 fixture；不包含 Prompt 发送、客户端启动/重启、UI 操作、正式 collect、评分、并发或发行验收。

## 1. 结论

本机 WorkBuddy 5.5.3 原生数据足以支持客户端专属的只读安装发现、Workspace/会话/请求绑定、终态分类、脱敏轨迹规范化和资源原始字段解析。当前安装为 `/Applications/WorkBuddy.app`，Bundle ID `com.tencent.workbuddy.mac`，版本 `5.5.3`，Intel `x86_64`。该版本的 `CFBundleExecutable` 是通用名称 `Electron`，公共 `WORKBUDDY_APP_PROFILE` 只接受 `WorkBuddy/CodeBuddy`，因此本任务在专属 driver 内增加了只允许 `5.5.3 + Electron` 的安装变体；未修改 COMMON 公共 profile，其他 Electron 版本继续失败关闭。

原生稳定身份映射为 `session_id=conversationId`、`turn_id=requestId`、`thread_id=null`。绝对 Workspace 的 MD5 是历史目录键；这是原生布局标识，不作为安全摘要。历史只读样本已验证完整的 user → tool call → tool result → assistant 链路，但历史任务不冒充本轮 General smoke。

资源口径区分主请求和关联工具子任务：主请求只读取 conversation index 的 `request.usage`；tool-result 内的关联 usage 单独保留，不并入主请求总量。历史样本主请求为 input/output/total `34164/2087/36251`；关联 usage 为 `181061/3774/184835`，其中 `138496 + 42565 = 181061`。`credit=4.36` 只有字段存在性证据，结算范围、单位和状态未核验，因此保持 `unverified`。

只读 probe 时 WorkBuddy 未运行，CDP 未探测；所以没有干扰桌面现场，也没有取得 UI 配置回读、一次发送、恢复或真机执行通过结论。probe 的 `PASS` 只表示安装身份和本次原生数据源可读，运行准备状态仍是 `DISCOVERED_NOT_CONNECTED`。

## 2. 本机只读证据

执行入口：

```bash
node tools/report/skills/general-e2e/execute-general-e2e/drivers/workbuddy/probe.mjs \
  --output /Users/gzx/debug-workspace/e2e-evaluate/workbuddy-macos-general-e2e/probe-workbuddy-5.5.3-readonly.json
```

本地报告（不入仓）SHA-256：`fb37a0969c9b3e200d82f18d3f9e116a15922317d85f693e21a8cde5a2d7b0c9`；大小 `4109` bytes。报告包含本机绝对路径和原生会话标识，只保存在调试工作区；仓库 fixture 使用合成 ID、临时 Workspace 和合成内容。

| 检查 | 结果 | 证据边界 |
| --- | --- | --- |
| 应用发现 | Bundle ID、`app.asar`、版本和 `Electron` 主程序校验通过；来源为 Spotlight | 专属变体只批准 5.5.3，不泛化到其他 Electron 版本 |
| 客户端身份 | WorkBuddy `5.5.3` / `x86_64` | 未启动应用 |
| 进程与 CDP | 主进程 0；`status=not_probed`，原因 `workbuddy-not-running` | 未为 probe 启动或重启客户端 |
| 会话索引 | `codebuddy-sessions.vscdb` 只读查询成功；1 个 session，含 conversation/cwd/status | 未输出原生 ID、标题或用户 ID；未做发送后增量捕获 |
| 历史布局 | 2 个账号目录、10 个 Workspace 历史、10 个 conversation 目录、4 个消息文件 | 只读统计；原始历史不入仓 |
| 日志布局 | extension 5 个 run 目录；application 4 个 run 目录 | 只证明目录可见，尚未纳入正式 provenance |
| 历史对账 | Workspace key、conversation、request 唯一绑定；请求/会话终态均成功；4 个规范化事件、1 个顶层 tool call | 历史样本不是新 General attempt |

probe 明确未执行：启动/重启、聚焦/修改 UI、选择 Workspace、切换模型/权限、发送 Prompt、停止会话。

## 3. 原生身份与终态映射

| General 概念 | WorkBuddy 原生来源 | CB-A 输出/规则 |
| --- | --- | --- |
| session | `codebuddy-sessions.vscdb` 的 `session:*`.conversationId | `session.session_id` |
| turn | conversation `index.json` 的 `requests[].id` | `session.turn_id` |
| thread | 当前原生布局没有可证明的 AstronStudio 等价层级 | `session.thread_id=null`；禁止填 task ID 或任意 UUID |
| cwd | `session:*`.cwd | 必须与完整 candidate Workspace 的 realpath 相同 |
| Workspace history | `MD5(realpath(workspace))` | 只用于定位当前 Workspace 的原生 history 目录 |
| completed | session `Completed` 且 request `complete`，轨迹完整 | `phase=COMPLETED` / `business_status=completed` |
| 原生失败 | session 或 request 为 failed/error/cancelled 等明确失败值 | `phase=FAILED`，保留原生状态和结构化错误 |
| 未知/进行中/不完整 | 状态未知、未终结或轨迹缺失 | `NEEDS_ATTENTION`，不得冻结或猜测终态 |

会话绑定同时要求：唯一 `conversationId`、完全一致的 cwd、唯一 request ID、Prompt SHA 一致、已持久化的一次发送状态，以及非空绑定证据。发送状态不明、ID 不唯一或 cwd/Prompt 不一致时失败关闭。

## 4. 轨迹与资源映射

原生布局：

- 会话索引：`~/Library/Application Support/WorkBuddy/codebuddy-sessions.vscdb` 的 `ItemTable session:*`。
- Workspace 历史：`~/Library/Application Support/WorkBuddyExtension/Data/<account>/VSCode/<identity>/history/<md5(abs-workspace)>/`。
- conversation：Workspace `index.json` → `<conversationId>/index.json` → `messages/<messageId>.json`。

规范化规则：

- user text → `user_message`；assistant text → `assistant_message`。
- assistant `tool-call` → `tool_call`；tool `tool-result` → `tool_result`，call ID 必须一一配对。
- 消息 envelope/inner role、request ID、conversation/request/message 引用任一不一致都失败关闭。
- 未支持内容类型或不完整消息写入 completeness 缺口，不把 partial 轨迹提升为 completed。

| 指标 | 原生来源与口径 | 当前发布状态 |
| --- | --- | --- |
| input/output/total Token | 精确绑定的 `requests[].usage` | `observed`；不叠加关联 tool usage |
| cache read/cache creation/reasoning | 主请求 usage 未暴露 | `null/unavailable`，coverage `0/1` |
| request count | 精确绑定的一个原生 request | `1/observed` |
| request attempt count | 传输层重试不可见 | `null/unavailable`，不能因只有一个 request ID 填 1 |
| tool call count | 绑定 request 中唯一顶层 tool-call ID | `observed`；result 不重复计数 |
| wall/agent duration | request 只有 startedAt，无已核验 request 完成时间或 agent duration | `null/unavailable` |
| 关联 tool usage | `tool-result.result.result.usage` | 仅保存在私有 observation，标记 partial，不并入主请求 |
| credit | 关联 usage 的 `credit` | `unverified`；不能冒充已结算积分 |

partial/unavailable 指标保持 `value=null`；只有 Schema 允许的 partial/unverified 指标才写 known subtotal。主请求与关联 scope 分开，避免重复计数或把子任务资源归给主请求。

## 5. 代码、fixtures 与验证

实现提交：`2112a86450ba2f22fb284d37a20921cd7e65db69`。

客户端专属文件：

- `eval_general_e2e/adapters/workbuddy/`：共享组件 binding、5.5.3 安装变体、原生 history/轨迹/资源 adapter。
- `tools/report/skills/general-e2e/execute-general-e2e/drivers/workbuddy/`：只读 probe 和 CB-A execution state 构造。
- `tests/general_e2e/fixtures/workbuddy/`：脱敏合成 history fixture。
- `tests/general_e2e/workbuddy_*.test.mjs`：原生布局、资源口径、应用发现、CB-A 状态和失败关闭测试。

已验证：公共 Python 回归 55/55、新增 Node 测试 9/9、General E2E 全量 Node 测试 69/69、四个新增模块语法检查、共享组件布局检查和 `git diff --check` 通过。CB-A 完成态 fixture 已由公共 Python validator 验证。Python 使用主工程既有 `.venv`；没有在 worktree 创建或安装新环境。

额外运行的 General E2E 全量 Python discover 共发现 127 项，但没有全绿：1 个失败、4 个错误均来自冻结 dataset manifest 与当前任务源不一致，或缺少 `report-workspace/.../general-custom60-v1.dataset.zip`。本任务从 merge HEAD 到实现 HEAD 的变更路径不包含 dataset 源、manifest 或 report-workspace；因此把它记录为独立基线/生成物缺口，不计作 WorkBuddy 专属测试通过，也不改动这些不归本任务所有的文件。

## 6. 尚未证明与 COMMON 接口需求

未证明：UI 控件唯一性、当前模型/权限回读、控制端点归属、一次发送、发送临界恢复、正常/失败/追问/授权/超时真机终态、停止确认、纯回复/文件任务、正式 collect/评分/回传/报告、三题串行/五题动态补位、仓库外发行。

COMMON 需要处理：

1. 决定公共 `WORKBUDDY_APP_PROFILE` 是否正式支持 macOS `CFBundleExecutable=Electron`。当前专属 driver 只放行已核验 5.5.3，不能把它解释为跨版本公共支持。
2. CB-B 支持一个 attempt 的 workspace/conversation/request/message 多 artifact、会话索引绑定证据和脱敏副本 provenance；哈希、size、逻辑 source ref 和范围应可交叉核验。
3. trace-index 接受 WorkBuddy 的 `session_id=conversationId`、`turn_id=requestId`、`thread_id=null`，不得要求伪造 AstronStudio ID。
4. WorkBuddy collect finalizer 与 macOS 精确进程清理 hook 只按本 attempt 的原生身份和进程生命周期收口，不复制 AstronStudio finalizer。
5. execute/collect Skill 的注册与构建装配应包含 WorkBuddy 专属源码、fixtures 需要的 vendored 组件和发行清单，仓库外运行不能依赖 `eval_general_e2e` 源码路径。
6. 公共报告继续区分主请求与关联 tool usage；未验证 `credit` 不进入积分排名或成本换算。

## 7. 下一步桌面时段需求

应用：`/Applications/WorkBuddy.app`（5.5.3/x86_64）。范围：控制任务分配的一个全新 General canary；保持用户当前模型/权限，不主动切换。预计操作：重新只读检查活动会话 → 在独占时段按获准方式开放控制端点/启动客户端 → 回读模型/权限和完整 Workspace → 新建任务 → 发送一次 Prompt → 捕获 conversation/request/cwd → 观察可信终态 → 只收集本题证据。

恢复方案：发送前持久化意图、Prompt SHA 和 session/history baseline；发送边界不明或 ID 不唯一时进入 `NEEDS_ATTENTION`，不重发；恢复只按持久化原生 ID 进入原会话；停止未确认时不冻结候选。正式 collect 仍等待 COMMON-CB05。
