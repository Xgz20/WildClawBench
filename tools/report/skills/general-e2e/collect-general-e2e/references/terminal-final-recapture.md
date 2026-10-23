# 显式终态回复补采

适用于执行器把同 turn 较早助手消息冻结为 final，而 completed turn 指向的原生消息、provider 完成项、SDK 最后助手消息及 task_complete.last_agent_message 逐字一致的已授权修复。不是重新执行或重新评分入口。未知来源、消息歧义、模型/high/会话/Prompt 冲突或候选变化全部拒绝。

先保留原件，建立 `wildclawbench.terminal-final-recapture-input/v1` JSON。`profile` 为 `bound-terminal-final-recapture/v1`，`created_at` 是本次观察补采时刻，不改原执行时间。`sources` 必须精确包含以下 role，各为 `{path,sha256,size}`，路径为输入目录内 `inputs/` 下的普通文件，不能链接或越界：

- `original_state`、`original_record`、`original_final`：原始冻结 state、原控制 execution record、原回复字节。
- `native_binding`：精确 thread/latest_turn/project/workspace_root 与原生 resume session_id。
- `native_turn`：含 thread_id/turn_id/state/completed_at/assistant_message_id 的原生 completed turn。
- `native_messages`：同 thread/turn 的助手投影原件，含 message_id/role/text/is_streaming。
- `provider_rows`：精确绑定 thread/turn 的原始 provider_runtime_events JSONL，保留 event_json 和真实 sequence。
- `sdk`：精确绑定的 SDK JSONL 原件。
- `candidate_tree`：由 `recaptureCandidateTree` 得到的相对文件、目录、链接、mode、字节 SHA 树；必须与补采时和正式冻结候选一致。
- `authorization`、`authorization_review`：本轮直接人类授权记录及其所批准的审阅文件。授权必须为 GRANTED、profile 一致、source/scope 非空且 review_sha256 匹配。

当前 profile 仅接受原 state 已核实的自定义模型/high，并从 config_id、execution_revision、configured_model_name 重建 SDK model ID。要求原始发送恰好一次、同一 completed turn、唯一最终消息和生命周期；没有语义上“更好答案”的选择。

```text
node /absolute/collect/scripts/prepare_astronstudio_terminal_final_recapture.mjs --input-manifest /absolute/input-manifest.json --output-dir /absolute/unit/.general-e2e/execution/task/recapture-001
node /absolute/collect/scripts/archive_astronstudio_trace.mjs --state-file /absolute/unit/.general-e2e/execution/task/recapture-001/automation-state.json --terminal-final-recapture-manifest /absolute/unit/.general-e2e/execution/task/recapture-001/recapture-manifest.json --state-db /absolute/bound-snapshot.sqlite --rollout-file /absolute/bound-sdk.jsonl --source-policy bound-native-sdk
```

输出目录必须全新且位于 unit 内、candidate workspace 外。旧文件不覆盖。按输出 state 继续原 resource/finalize CLI，正式收口后由 verify-only 重验。原 run-config、原 attempt、执行时间和发送次数均保持。run 的 record-execution 通过显式 `--state` 选择已授权的派生 state，其原 state 保留在补采来源中。

归档器必须显式传入补采 manifest；不会在普通终稿不一致时自动切换。当前不与 native-provider-log-retention profile 叠加，缺少运行库 provider 来源的组合继续拒绝。15 个来源绑定文件均随 trace 冻结，资源来源闭包包含它们；独立评分/回传按标准完整 trace handoff 消费。
