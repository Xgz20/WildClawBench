# AstronStudio rollout 工具与请求统计

## 来源与修复

桌面 `provider_runtime_events` 记录 app-server 协议事件。`commandExecution` 和 `fileChange` 是事件类型，不是模型真实工具名。此前框架只统计这些事件及 MCP/dynamic tool，导致独立 `read`、`update_plan` 等调用遗漏，并将 `bash/exec_command`、`write/edit` 合并。`astronstudio-provider-events.jsonl` 是该事件表的归档，不是 rollout 的原样副本。

新采集 CLI 从绑定 session 的 rollout 归档原件，同时保留 provider events。共享实现为 `tools/report/e2e-shared/general-resource-supplements/astronstudio-rollout.mjs`。报告和资源指标均调用同一个解析器。

## 统计契约

- 校验 session_meta 的 session/cwd、明确的 turn、冻结 Prompt SHA、终态。只纳入精确绑定 turn；内部 turn metadata 冲突拒绝。
- function_call 和 custom_tool_call 使用原始 name；包括失败或被拒绝的调用意图，不冒充工具成功次数。原生 tool_search_call 使用协议名称 tool_search。
- 按 call_id 去重完全一致的回放；同 ID 内容冲突拒绝；所有 output 记录均排除。保留原始行号和内容摘要用于核对，不从 Bash 命令语义拆出 Read/Write。
- 请求数是累计 token_count 的推进次数；每次推进都要求累计值与 last_token_usage 对账。重复累计快照排除，前一 turn 的累计量作为基线。缺失/不一致只留小计与 null；HTTP 请求尝试及内部重试仍不可观测。
- 旧执行、评分与证据保持冻结。独立补充层绑定原执行 SHA、状态、rollout SHA，并在报告时重读原件复算。可叠加此前资源补采，不覆盖 Token、耗时等无关指标。

## 本轮离线验收范围

60 个有效会话/turn 逐项绑定后，rollout 中 704 次函数调用与 24 次原生工具搜索合计 728 次。旧报告 495 次均可按 call_id 对应。655 条用量事件含 15 条重复累计快照，640 次有效推进与旧请求数一致。该数字是本轮原件复算结果，不是解析器中的常量。

回归覆盖真实名称、原生工具搜索、结果排除、跨 turn 排除、重复/冲突、会话/目录/Prompt 漂移、用量缺口、失败终态和补充层篡改。此修复没有重新执行被评客户端，也没有重新判分。
