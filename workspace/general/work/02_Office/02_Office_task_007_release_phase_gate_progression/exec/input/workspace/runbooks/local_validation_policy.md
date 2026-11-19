
# Local validation policy

本工作区没有真实 CI 或外部 package registry。`validation_results.json` 记录的是工作区校验状态分类，你可以在修复工作区文件后更新它，但必须保留可追溯 evidence refs。

## Category semantics

| category | 含义 | 对 phase gate 的影响 | 工作区修复方式 |
|---|---|---|---|
| `passed` | 该检查在当前引用范围内支持 admission | 只有所有依赖项也不阻塞时才有用 | 保留，不要为了凑数重复写 passed |
| `failed` | 工作区文件之间存在矛盾或规则违反 | 阻塞推进 | 修复对应可变文件，记录 refresh 依据 |
| `stale` | 检查早于它声称覆盖的 state/cache/audit change | 阻塞完成或 handoff | 在修复后写新的 workspace refresh record |
| `missing_lookup` | 所需 lookup/cache 条目缺失或不匹配 | 阻塞推进 | 从工作区 lookup records 补齐，或保留 blocked |
| `not_applicable` | 当前 release scope 不需要该检查 | 不作为通过证据 | 需要写明 scope 依据 |

## Freshness rules

- `validation_results.validation_meta.state_snapshot_at_utc` 早于 `workflow_state.phase_status.last_state_change_at_utc` 时，受影响依赖的 validation 不能证明当前 state；未涉及变更的输入绑定仍可沿用原有效回执。
- lookup/cache 修改后，应在 `validation_results.refresh_history` 添加一条 workspace refresh 记录，并更新对应检查的 category/reason/source refs。
- audit 只能在实际 repair/refresh 之后追加；旧 audit 记录不能倒填成通过。

## Lookup rules

1. 对同一个 `lookup_key`，优先选择 `scope_version` 与 `config/release_scope.json.current_scope.scope_version` 一致、`status=current`、`network_used=false` 的记录。
2. `status=stale`、`quarantined=true`、`scope_version` 不匹配或来自 archived note 的记录不得写入 active cache。
3. 如果没有合格工作区记录，必须保持 `missing_lookup` 或 blocked，不得编造 digest、URL 或远程查询结果。

## Summary wording

最后的 progress report 应说明 artifact role、category、是否工作区修复、是否仍需人工跟进。不要输出预设结果式逐字段映射，也不要声称调用了真实服务。

本轮更新形成的 validation snapshot 应覆盖本轮写回状态，并引用实际修复依据；旧 refresh 记录保留。对于同一记账时点，校验中的 audit_after_validation 可以核对最终新增审计与刷新记录的引用关系，不表示真实 CI 已执行。

## 状态与证据约定

- 用于本轮准入的查询记录和对应日志，时间均不得晚于 config/release_scope.json 中的决策时点；合并导出中可能含后续记录。记录与日志的 lookup_key、scope、值、时间及网络来源应相符；quarantined=true 的记录或日志不参与准入。不能只按最新时间或记录名称选取。
- 只有对应对象已修复且有当前依据，才把 category 写成 passed；仅修改 category/blocks_current_gate 不构成修复。无法证明时保留实际 blocker。
- docs_bundle 与 release_manifest 的组件 state 也须反映处理结果；changed_after_last_validation、needs_sync_note 仍表示待处理。修复完成可使用 validated、synced、reconciled、locally_reconciled、current、ready、resolved 或 repaired 等业务状态码。来源已同步但组合校验仍待补证时，release_manifest 应标为 awaiting_validation、pending_validation、stale 或等义待验证状态，不能把 cache 的 current 当作组件全部验证完成。CLI 与 completion 保留原冻结状态也有效。
- 准入必须基于可追溯的本地来源、有效刷新、已同步的组件与看板以及保留历史的新审计；来源记录、日志或规则被改写后，不能据此宣称合法准入。

## 依赖版本与校验凭据

`config/release_scope.json` 的 component_dependencies 和 validation_requirements 规定依赖范围。manifest 查询记录及对应日志的 input_bindings 必须与当前依赖的有效本地值一致，且查询不得早于该组件的最后一次内容变更；仅 scope/current 或较新时间不足以证明可用。

`cli_component_lock`、`bundle_integrity` 的通过凭据来自只读 JSONL 中 local_validation_receipt 事件。回执必须属于当前 scope、本地无网络、未隔离、时间不晚于决策时点；其 input_bindings 要完整匹配该检查依赖的当前有效值。原始 passed 表示被测试的那组输入通过，不自动适用于后来修复的缓存。版本不匹配时用 stale 并保持阻塞；没有本地可用回执时用 missing_lookup。不得把工作区 refresh 当作新测试回执，也不能为方便完成而改写原始回执。

校验行的 receipt_ref 指向实际采用的回执；tested_bindings 如实摘录回执输入，observed_at_utc 保留回执时间；required_bindings 写本轮实际需要验证的完整依赖值。三者可直接与日志对账，不能把新值填进 tested_bindings 来伪造覆盖。未受影响的 CLI/completion 继续使用原有效回执，不能因为 docs 变更而一律重标过期或虚构新的测试时间。

state_snapshot_at_utc/current_for_state_at_utc 描述本轮状态分类是否已刷新，不表示每个业务检查都通过。可以形成当前且准确的工作区 snapshot，同时保留 stale 或 missing_lookup。工作区可完成的缓存/看板修复仍须完成；确需新打包校验时，交由 packaging maintainer 在相应授权和时点下补充回执，本轮不运行真实 CI。
