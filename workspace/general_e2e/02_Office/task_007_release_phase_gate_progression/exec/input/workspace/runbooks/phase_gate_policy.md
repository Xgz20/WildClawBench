
# Phase gate policy: quillship-cli release progression

本文件是专用发布状态看板的公开规则源，不是预填处理清单。请同时读取 Markdown board、JSON state、validation results、lookup/cache 和 audit history，再判断本轮允许的状态变化。

## Phase order

| order | phase_key | 中文说明 | admission gate | 不能跳过的原因 |
|---:|---|---|---|---|
| 1 | `draft_intake` | 收集工作区 release 范围和待处理材料 | scope 文件可读，release id 明确 | 后续 gate 依赖同一 release id |
| 2 | `scope_freeze` | 冻结本轮 CLI / docs / manifest 范围 | scope、component list、变更窗口一致 | validation 必须针对冻结后的范围 |
| 3 | `local_validation` | 解释并刷新 workspace validation category | 没有未处理的 `failed`、`stale`、`missing_lookup` | passed 项不能覆盖阻塞项 |
| 4 | `repair_alignment` | 修复/同步 board、JSON state、cache 和 audit drift | 修复证据、状态字段、audit note 互相一致 | 未同步就 handoff 会制造假完成 |
| 5 | `handoff_ready` | 写交接摘要并准备维护者复核 | 上一 phase 已真实 admitted，audit 后置 | 交接不是跳过验证的快捷方式 |
| 6 | `release_wrap` | release 收尾 | handoff 已被工作区证据支持 | 本轮通常不应越过相邻 phase |

## Decision rules

1. JSON `workflow_state.phase_status.current_phase` 是判断当前 gate 的主状态源；Markdown board 的 banner 可能是人工复制或旧板遗留。
2. 如果 `validation_results.json` 中仍存在当前 phase 依赖的 `failed`、`stale` 或 `missing_lookup`，不得推进 phase，不得把 handoff 或 release 写成 complete。
3. `missing_lookup` 只能用 `state/local_lookup_records.json`、`logs/local_validation_runs.jsonl` 和 `config/release_scope.json` 里的工作区记录修复；不得联网查询。
4. `stale` 的判定看 validation snapshot 时间是否早于相关 state/cache/audit 修改时间。修复后需要在 `validation_results.json` 的 workspace refresh 区域记录新的解释结果。
5. `failed` 的判定看公开文件是否矛盾。应先修复可变文件中的矛盾，再刷新对应 category；不能仅在 summary 里解释。
6. 每轮最多推进一个相邻 phase。即使多个 blocker 被修复，也不能从 `local_validation` 直接跳到 `handoff_ready` 或 `release_wrap`。
7. 如果任一阻塞项无法用工作区证据修复，应保持当前 phase 或明确 blocked，并在 progress report 与 audit 中说明 carry-forward 原因。

## Mutable file contract

本轮仅更新看板、workflow/validation/cache 状态、审计、两份 outputs 文件及最终状态快照，具体路径见 `state/workflow_state.json` 的 `mutation_policy.mutable_paths`。特别注意：

- `state/local_lookup_records.json`、`logs/local_validation_runs.jsonl`、`config/release_scope.json` 是只读证据。
- `audit/audit_history.md` 是 append-friendly 文档；不要改写旧记录来假装过去已经通过。
- `environment/mock_release_board/final_state_capture.json` 是公开状态快照文件，不是额外交付文件。它应反映你实际写入后的工作区状态摘要。

准入判断基于本轮依赖绑定，而非将 passed 行数相加。gate_admission.local_validation.blocking_check_keys 与实际 blocks_current_gate=true 的检查键保持一致；部分修复完成但仍有必要凭据缺口时，保持 local_validation，后续阶段仍未准入。
