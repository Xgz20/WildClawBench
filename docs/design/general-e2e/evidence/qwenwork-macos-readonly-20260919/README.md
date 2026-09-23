# QwenWork macOS General E2E 只读能力与字段映射证据

> 历史快照：本文的版本、结果和“当前/下一步”仅对应所列日期及 revision，保留原结论，不作为现在的执行指令。最新进度见[接续入口](../../README.md#qwenwork-剩余生产准入事项)，后续三路、Token 与加固证据见[五题及 r21–r35 记录](../qwenwork-macos-five3-20260923/README.md)。

日期：2026-09-19（Asia/Shanghai）。任务：`MAC-QWENWORK-GENERAL`。范围：P1 只读 probe、原生身份/终态/轨迹/资源字段映射、CB-A 状态 fixture；不包含 Prompt 发送、客户端启动/重启、UI 操作、正式 collect、评分、并发或发行验收。

## 1. 结论

本机 QwenWork 原生数据足以支持客户端专属的只读发现、稳定会话绑定、终态分类、脱敏轨迹规范化和资源原始字段解析。当前安装身份是 `QwenWorkCN 1.0.6`、Bundle ID `cn.qwenwork.desktop.mac`、Intel `x86_64`；SDK 为 `@ali/qodercn-agent-sdk-next@1.0.28`，transcript 为 `1.1.32`，runtime SHA-256 为 `e86620b7e772d1f536ba15beea8c3059bf6075dffb478aceaa8cad328a879c28`。

历史已验的 macOS Token Profile 只覆盖客户端 `1.0.5`。虽然当前 `1.0.6` 的 SDK、transcript 和 runtime SHA 与该 Profile 相同，客户端版本已经漂移，因此不能继承归一化结论：客户端私有观察保留 `unverified` 原始 usage；严格 General `resource-metrics/v1` 不能把未验证原始数值作为归一化指标，发布视图使用 `null + unavailable + coverage 0/N`，并保留 `QWEN_TOKEN_SEMANTICS_UNVERIFIED` 告警。这个表示差异需要 COMMON 决定是否在后续公共版本中增加“unverified + null”的统一语义。

只读 probe 时 QwenWork 未运行、CDP `9250` 未开放，状态库没有活动或 pending 会话；因此没有干扰桌面现场，也没有取得任何 UI 控件、一次发送、恢复或真机执行通过结论。

## 2. 本机只读证据

执行入口：

```bash
node tools/report/skills/general-e2e/execute-general-e2e/drivers/qwenwork/probe.mjs \
  --output /Users/gzx/debug-workspace/e2e-evaluate/qwenwork-macos-general-e2e/probe-20260919.json
```

本地报告（不入仓）SHA-256：`fa762864f2d931a57156d6dde3d0ec88ba699e1e4a51efe090de23f5e13f5da9`；大小 `3151` bytes。报告包含本机绝对路径，因此只在调试工作区保存；仓库 fixture 使用合成 ID、`/private/tmp/...` 路径和 `[REDACTED_*]` 内容。

| 检查 | 结果 | 证据边界 |
| --- | --- | --- |
| 应用发现 | `/Applications/QwenWorkCN.app`，Bundle ID、主程序与 `app.asar` 校验通过 | 只证明当前安装身份，不证明 UI 可控 |
| 客户端身份 | `1.0.6` / build `26091603` / `x86_64` | 未启动应用 |
| 进程与 CDP | 主进程 `0`；CDP 未开放 | 未为 probe 启动或重启 |
| SQLite 快照 | `quick_check=ok`；21 个会话 | 从 `agents.db` + 可选 WAL/SHM 临时快照只读查询 |
| 活动现场 | active/pending `0` | 依据 `stream_id` 或 running/needs_attention/pending/starting 状态；不替代桌面时段锁 |
| 原生终态 | completed `18`、cancelled `2`、interrupted `1` | 只证明字段可读和映射样本存在，不复用历史任务为 General smoke |
| 稳定身份覆盖 | session/conversation/sub-chat/local-project/cwd 均 `21/21` | 未输出历史会话 ID、标题、Prompt 或回复 |
| 原生轨迹 | transcript 27、segment 1584；transcript 版本唯一为 `1.1.32` | 只读统计；原始日志不入仓；符号链接跳过并告警 |
| Token Profile | 当前匹配结果 `null` | 当前 1.0.6 不继承历史 1.0.5 Profile |

probe 明确记录未执行：启动/重启、聚焦/修改 UI、选择项目/目录、切换模型/权限、发送 Prompt、停止会话。

## 3. 原生身份与终态映射

| General 概念 | QwenWork 原生来源 | CB-A 输出/规则 |
| --- | --- | --- |
| conversation | `chats.id` | 保存在 `extensions.qwenwork.conversation_id`；不伪装为 thread |
| sub-chat | `sub_chats.id` | 保存在 `extensions.qwenwork.sub_chat_id` |
| session | `sub_chats.session_id` | 唯一稳定原生 ID，映射 `session.session_id` |
| local project | `chats.local_project_id` | 发送前后选择候选时必须一致 |
| cwd | `local_projects.root_paths[0]`，回退 `projects.path/chats.worktree_path` | 必须与完整 candidate Workspace 相同 |
| thread/turn | 当前数据库与 transcript 没有可证明等价的公共层级 | `thread_id=null`、`turn_id=null`；禁止填 task ID/UUID |
| running | `sub_chats.stream_id != null` 优先；或原生 running/pending 等状态 | `phase=RUNNING`，不可冻结 |
| completed | `chats.ext.taskStatus=completed` | 仅在会话/cwd/绑定证据验证后输出 `COMPLETED/completed` |
| cancelled | 原生 cancelled | 仅停止确认后输出 `FAILED/cancelled`；否则 `NEEDS_ATTENTION` |
| interrupted | 原生 interrupted | `FAILED/infrastructure_error`，保留原生状态 |
| failed/error | 原生失败状态 | `FAILED/infrastructure_error`；不自动归为候选能力错误 |
| 未知状态 | 未识别的新值或缺值 | `NEEDS_ATTENTION`，不猜测终态 |

会话选择遵守：优先按已持久化 session/sub-chat/conversation ID + 完整 cwd 精确匹配；新发送后只允许在已捕获的 exact local project、发送前 baseline 和时间边界内选择唯一候选；仅有 cwd/最近更新时间时返回空，不猜最新会话。

## 4. 轨迹与资源映射

原生布局：

- transcript：`~/.qwenworkcn/projects/<encoded-cwd>/<session-id>.jsonl`；包含 user/assistant 文本、tool_use/tool_result、sessionId、cwd 和 transcript 版本。
- segment：`~/.qwenworkcn/logs/sessions/<encoded-cwd>/<session-id>/segments/*.jsonl`；包含 turn、request、response usage、tool、permission、shell exit code 和终态。
- 状态库：`~/Library/Application Support/QwenWorkCN/data/agents.db`；会话/cwd/终态绑定源。

规范化规则：

- user text → `user_message`；assistant text → `assistant_message`。
- assistant `tool_use` → `tool_call`；user `tool_result` 结合 `tool.shell.finished/tool.execution.finished/permission.resolved` → `tool_result` 和 success/error/unknown，额外保留 native outcome/exit code。
- thinking 内容不作为必需轨迹输出；后台/子代理 turn 从主任务 usage 分离。
- `model.response.completed` usage 按 request ID 去重，并与主 `turn.finished` 终值对账；缺响应、终值冲突、cache read 大于 input 均不发布完整值。

| 指标 | 原生来源与口径 | 当前 1.0.6 发布状态 |
| --- | --- | --- |
| input/output Token | 主 turn 的 `model.response.completed` 求和，与 `turn.finished` 对账 | `null/unavailable`；私有观察 `unverified` |
| total Token | input + output；input 已包含 cache read，不重复加缓存 | 同上 |
| cache read | response/turn 的 `cache_read_input_tokens`，必须 `<= input` | 同上 |
| cache creation | 原生字段恒为零不能证明独立缓存写入观测 | `null/unavailable` |
| reasoning output | 未暴露 | `null/unavailable` |
| request count | 主 turn 唯一 `model.request.started.request_id` | 可观测；不是 HTTP 尝试数 |
| request attempt | 不可见传输重试 | `null/unavailable` |
| tool call count | 主 turn 唯一 `tool.requested.tool_call_id` | 可观测；结果不重复计数 |
| agent duration | 主 turn `turn.finished.duration_ms` | 可观测 |
| wall duration | CB-A execution state started/finished | 由执行状态提供；本次未执行用例 |

partial 指标保持 `value=null`，仅在语义已验证的响应子集上写 `known_subtotals`，并写 `known/total/unit`；masked/unavailable/unverified 原始语义不伪造成零。

## 5. 代码、fixtures 与验证

客户端专属文件：

- `eval_general_e2e/adapters/qwenwork/`：共享组件 binding、严格历史 Profile、transcript/resource adapter 和 CB-B 前私有 evidence 对象。
- `tools/report/skills/general-e2e/execute-general-e2e/drivers/qwenwork/`：只读 probe、SQLite 快照、稳定会话选择、终态映射和 CB-A 通用状态构造。
- `tests/general_e2e/fixtures/qwenwork/`：由本机字段结构生成的脱敏 transcript/segment/session/runtime fixtures。
- `tests/general_e2e/qwenwork_*.test.mjs` 与 `test_qwenwork_adapter.py`：Profile 漂移、coverage、背景 turn、tool result、CB-A null ID、只读边界和严格 General resource contract。

已验证：新增 Node 测试 12/12、Python 测试 3/3、模块语法检查通过。代码提交 SHA 由任务卡和交接在实现提交后登记，避免文档自指。

## 6. 尚未证明与 COMMON 接口需求

未证明：UI 控件唯一性、当前模型/权限回读、一次发送、原生 session 捕获时序、正常/失败/追问/授权/超时真机终态、停止确认、恢复不重发、纯回复/文件任务、当前 1.0.6 非零 Token 对账、正式 collect/评分/回传/报告、三题串行/五题补位、发行闭包。

CB-B 需要提供：

1. trace-index 对“只有真实 Qwen session ID、无 Astron thread/turn/lifecycle”的正式映射；不得要求伪造字段。
2. 一个 attempt 的 transcript + 多 segment 原始 artifact、状态库绑定证据和脱敏副本 provenance；支持多文件 SHA/size/range。
3. QwenWork 可信来源集合：精确 session/cwd 下的 transcript/segments、只读 SQLite 快照元数据；拒绝遍历其他会话补值。
4. collect finalizer 与平台进程清理 hook：只按本 attempt 的原生身份/进程生命周期收口，不复制 AstronStudio finalizer。
5. execute/collect Skill 构建装配和发行清单，使 QwenWork 专属代码使用本 Skill 内 vendored 依赖，不在发行期跨 Skill 或依赖仓库 `eval_general_e2e` 路径。
6. 统一决定严格 resource v1 如何表示“原始数值存在但 Profile 未验证”；当前实现以私有 `unverified` 观察 + 公共 `unavailable/null` 保证现有 validator 可接受。

## 7. 下一步桌面时段需求

应用：`/Applications/QwenWorkCN.app`（1.0.6/x86_64）。范围：控制任务分配的一个全新 General canary；保持用户当前模型/权限，不主动切换。预计操作：重新只读检查活动会话 → 在独占时段按获准方式开放控制端点/启动客户端 → 回读模型/权限和目录 → 新建任务 → 发送一次 Prompt → 捕获 session/cwd → 观察可信终态 → 只收集本题证据。恢复方案：发送前持久化意图、Prompt SHA、baseline 和 local project；发送边界不明或 ID 不唯一时进入 `NEEDS_ATTENTION`，不重发；恢复只按持久化原生 ID 打开原会话；停止未确认时不冻结候选。
