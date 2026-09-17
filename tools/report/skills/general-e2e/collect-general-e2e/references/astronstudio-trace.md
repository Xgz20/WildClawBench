# AstronStudio 轨迹归档与检索

## 输入门禁

归档器只接受 `execute-general-e2e` 生成的 AstronStudio 终态 `automation-state.json`。以下任一条不成立时失败关闭：

- 阶段不是 `COMPLETED` 或 `FAILED`；
- Prompt 不是已确认发送一次；
- `thread_id / turn_id / provider session_id / cwd` 未完整验证；
- SQLite 快照 `quick_check` 不通过；
- `projection_turns` 与项目 Workspace 不唯一或 cwd 不一致；
- `provider_runtime_events` 中的 thread、turn、provider session 或 lifecycle generation 不唯一；
- 原生 user message 与 Prompt digest 不一致，或最终 assistant message 与执行阶段保存的最终回复不一致。

工具不依赖标题、最近修改时间、Workspace basename 或最近任务猜测归属。状态库只读快照最多重试三次，不改写 AStudio 源库。

## 产物

默认输出到执行状态文件同目录的 `trace/`：

```text
trace/
├── raw/
│   └── astronstudio-provider-events.jsonl
├── transcript.jsonl
└── trace-index.json
```

- `raw/*.jsonl` 保留精确 turn 范围内可取得的原生事件包装、数据库 sequence 和持久化时间。
- `transcript.jsonl` 使用 General E2E `transcript-event:v1`，包含 user/assistant 消息、工具调用/结果、call ID、时序、终态和可取得 usage。不将 reasoning 流当作可见 assistant 回复。
- `trace-index.json` 记录 adapter 版本、原生会话绑定、原始事件范围、产物哈希、调用/结果 sequence 和完整性。

`commandExecution` 标准化为 `command`，参数保留 `command/cwd/command_actions`，结果保留输出、exit code、耗时和原生状态；`fileChange` 标准化为 `file_change`；`mcpToolCall` 保留原生工具名和结构化参数/结果。每个工具调用只记一个 `tool_call`，返回另记一个使用同一 call ID 的 `tool_result`；不将两者计为两次调用。

终态 Workspace 内的绝对路径同时保留 `raw` 值和 `/tmp_workspace` 规范值。不可靠映射的外部路径保留原值并将规范值设为 `null`，不猜测或改写工具参数。

## 完整性

`complete` 表示原生 turn 已归档、存在 start/completed 边界、唯一 user message、至少一个 assistant message，且每个已归档工具调用都有关联返回。标准化有意过滤的流式 delta、reasoning 摘要和重复 item update 仍存在原始 JSONL 中，不等于原始事件丢失。

缺少边界、消息、call/result 一侧或出现不支持的 item 类型时写入 `partial` 和具体 `missing`。`omitted_event_count` 只表示原生归档层已知遗漏，不用来统计有意不转换的流式事件。只有摘要或索引、没有原始归档时不得标记 `complete`。

## 评分兼容和只读检索

标准事件顶层保留 `role/content`，工具调用另带有 `message.content[].type=tool_use`、`name`、`input`和 `arguments`，因此可被现有 `transcript_loader` 及通用自建题中的 backend-neutral 规则读取。平台原生完整性仍以 canonical `type/tool/source` 字段为准，兼容视图不取代原始证据。

检索器先校验 transcript 的 size、SHA-256 和 event count，再按标准 sequence 范围、call ID、原始/规范路径或文本执行只读查询。过滤条件为 AND，结果返回总命中数、页码、前后页状态、transcript 行号和原始事件引用。
