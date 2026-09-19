# 脱敏 fixture 说明

`trajectory-partial.jsonl` 只保留 2026-09-19 DoubaoWork 2.28.12 本机只读样本已经确认的字段形状：`role/content`、`tool_calls[].id/type/function.name/function.arguments` 与 `tool_call_id`。Prompt、文件内容、工具结果、绝对路径、真实会话 ID 和 agent ID 均已替换；原样本只有 3 行，没有原生终态、cwd、时间戳、usage 或最终 assistant 消息。

`probe-targets.json` 使用合成 ID，覆盖 HTTP discovery 的 `doubaowork://` scheme 与非聊天后台页面。fixture 不包含账号、历史侧栏、认证信息或截图，不能作为真机通过证据。
