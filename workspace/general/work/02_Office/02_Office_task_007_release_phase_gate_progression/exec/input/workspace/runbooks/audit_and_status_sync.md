
# Audit and status synchronization rules

Audit/history 不是装饰文本。它必须能解释实际发生的 state transition、validation refresh 和 lookup/cache repair。

## Required synchronization

- `release_board.md` 的 current status、`workflow_state.json` 的 phase/status、`validation_results.json` 的 category、`lookup_cache.json` 的 active cache 和 `audit_history.md` 的最新记录必须在角色层面一致。
- 如果 board 上有旧的 ready/handoff 语言，但 JSON 或 validation 仍阻塞，应把 board 修正为同步后的状态，不得只在 summary 中提一句。
- 如果推进 phase，audit 记录必须晚于 validation refresh，并说明只推进了相邻 phase。
- 如果不推进 phase，audit 记录必须说明 blocker category 和 carry-forward reason。

## Audit entry shape

请在 `audit/audit_history.md` 追加一条中文记录，建议包含：

- `category`: inspection、local_validation_refresh、lookup_cache_repair、phase_transition、blocked_carry_forward 或 status_sync 中的一个或多个
- `linked_artifacts`: 使用相对路径或 artifact role，不要写私有路径
- `validation_categories`: 概括本轮处理过的 category
- `phase_note`: 说明是否相邻推进，或为何保持 blocked
- `no_network`: 明确本轮未使用 live service

不要改写旧记录来制造连续性；如果旧记录有误，用新记录说明纠偏。

## 记录粒度

本轮可以使用一次决策时点记账。同一时间戳的记录应通过 refresh/audit 引用及文字说明依赖先后，不要为制造先后关系编造未来时间。审计编号、刷新编号自行选择并保持唯一；不要求特定编号或特定报告标题。阶段编码保留 phase_order 中的值，新增准入状态可用 admitted / in_progress / not_admitted_yet 等清楚表达状态。

更新记录的 updated_artifacts 列出本轮实际写入路径，包含更新记录自身；最终快照的 lookup_cache_capture 保留每条 active cache 的 lookup_key、scope_version、cache_value、status、source_record_ref，以便下一位维护者核对来源与范围。

新增审计应标明 recorded_at_utc 或等义的明确记账时间；若正文引用多个历史时间，需把本条记账时间单独标明，避免混淆。更新记录/快照中的引用用于交付对账，其缺项不抹消正文中已存在的有效审计。

phase_decision.blocking_check_keys 记录实际保留的阻塞键。给下一位维护者的说明应区分本轮已修复、沿用的有效结果和必须补的凭据，并说明后续解除阻塞需要核对哪些输入；可以写在看板、报告、状态备注或新增审计中并互相引用，无须重复同一解释。
