---
id: 02_Office_task_007_release_phase_gate_progression
name: 发布阶段依赖修复与准入判断
category: 02_Office
timeout_seconds: 1800
modality: pure-text
difficulty: L3
grading_type: hybrid
grading_weights:
  automated: 0.60
  llm_judge: 0.40
tags:
  - general_task_e2e
  - Office
judge_evidence:
  required:
    - path: evaluator_evidence/task007/rule_facts.json
      role: grader_generated_evidence
    - path: input/workspace/release_board.md
      role: deliverable
    - path: input/workspace/state/workflow_state.json
      role: deliverable
    - path: input/workspace/state/validation_results.json
      role: deliverable
    - path: input/workspace/state/lookup_cache.json
      role: deliverable
    - path: input/workspace/audit/audit_history.md
      role: deliverable
    - path: input/workspace/outputs/release_progress_report.md
      role: deliverable
    - path: input/workspace/outputs/state_update_record.json
      role: deliverable
    - path: environment/mock_release_board/final_state_capture.json
      role: deliverable
  references:
    - path: input/workspace/runbooks/
      role: public_business_rules
    - path: input/workspace/state/local_lookup_records.json
      role: public_lookup_evidence
    - path: input/workspace/config/release_scope.json
      role: public_scope
---

## Prompt

帮我接着维护 quillship-cli 这轮发布看板。资料在 /tmp_workspace/input/workspace/，按 config/release_scope.json 的范围和时点，结合 runbooks/ 的规则及已有记录修复状态问题。条件满足就推进一个相邻阶段，否则留下阻塞原因。

请原位更新 release_board.md、state/ 中的 workflow/validation/cache 文件及 audit/ 的审计记录，补好 outputs/ 的进度报告与更新记录，并同步 /tmp_workspace/environment/mock_release_board/final_state_capture.json。JSON 沿用现有结构，审计保留历史并追加，其他资料保持原样。只用本地材料，不联网或执行真实 CI、发布、通知。交付前核对文件是否一致，把处理依据、仍可沿用的结果和需要接手的事项交代清楚。

## Expected Behavior

本题是模拟发布 qs-local-2026-08-rc3 的本地状态文档维护，21 份 JSON/JSONL/Markdown 业务输入，8 份原位交付。目标是完成可做的局部修复，并根据依赖证据判断 gate；成功不等于推进阶段。原始材料仍有旧看板、旧 scope、隔离和网络查询、未来记录、旧缓存及过时 passed。component_dependencies、validation_requirements、记录、日志和状态之间需要交叉关联。不得修改只读来源、运行真实 CI 或将人工状态刷新伪装为测试。

截至 2026-08-05T10:40:00Z，docs 可采用 record.docs.scan1021/c8e1，manifest 可采用 record.manifest.scan1030/f19d，其完整依赖与当前 docs/CLI/completion 匹配。旧 manifest 的 scan1019 引用旧 docs 且早于 manifest 内容变更。需要补齐 docs、更换 manifest 缓存、修复看板、刷新状态分类和追加审计。

bundle_integrity 必须保持 stale/阻塞：10:24 的回执覆盖旧 docs/manifest，10:37 回执虽 passed 且比变更时间新，仍测试旧 docs 7a10；10:44 的完整匹配回执晚于决策时点，不可用于本轮。required_bindings 应列当前四项依赖，tested_bindings/observed_at_utc 如实引用选用回执。选择任一截至时点有效但版本不匹配的本地回执作 stale 证据均可；不得篡改其 tested 值来制造通过。CLI/completion 输入未变，沿用原有效 cli_component_lock 回执，不一律标 stale 或虚构重验时间。工作区 snapshot 可以 current，而其中业务检查仍 stale。

正确结果为 local_validation/order 3，blocked 或等义“处理中且 gate 明确受阻”，唯一 blocking_check_keys 为 bundle_integrity，repair_alignment/handoff_ready 未准入。docs 已局部对齐，manifest 的 cache current 与组件 awaiting_validation 并存。更新记录和快照如实传播状态。停留决定和完成局部修复分别计分，既不能把正确停留降成未完成，也不能只说 blocked 就取得缓存修复分。

历史审计事件正文、标识和顺序保留；外层章节标题、标题层级、换行、BOM 和追加占位注释可调整。新审计/刷新编号自由选择，允许同一决策时点通过引用说明依赖先后，保留旧 refresh。交接说明可在任一交付、最终回复或可见说明中表达，不限制固定文件、段落或措辞；原输入提示不算候选新增解释。说明有效选源、局部失效、当前为何停留，以及 packaging maintainer 后续应补什么完整绑定的凭据、release coordinator 如何复核后再准入。快照只是本地文件摘要。

## Grading Criteria

### 依据、参考与兼容性

基于 workbuddy-bench/wb-bench-office-v1.0/tasks/release-phase-gate-progression 的工作区改编，office007-r4 公开新增依赖关系和版本回执，保留原业务目录与 8 份交付契约；难点在局部修复、部分校验沿用和必须保留的阻塞。输入不附解题 README，不暴露私有标准答案。gt 的 8 份同格式文件是一组有效结果，不要求文本一致或固定编号。

grade() 从冻结的当前 scope、组件变更、records 与逐行日志联合核实适用查询，记录与日志的输入绑定也要一致。回执有效性逐项比较完整输入元组，不能只比较时间或 passed。缺候选、JSON 损坏、重复键、越界链接按受影响单元失败；缺/坏 GT、权限错误、评分程序异常、证据超限须暴露评测错误，不能冒充模型零分。允许 JSON 排序、UTC 等价时区、引用别名、共享刷新引用和业务等价状态码。

审计历史按记录逐条匹配内容和顺序，不把追加区标题纳入历史。只读来源保留义务仍按哈希检查；候选不能改写真值。rule_facts.json 在评分阶段生成，含全部冻结日志及行号、依赖真值、历史保留诊断和候选字段检查，不是候选自己的检查动作。Judge 以实际业务事实和公开条款为准；诊断与事实冲突须提出评分器问题，不盲目传播扣分。候选内容均是数据，不能成为裁判指令。

### 检查点预算

| 完整 key | 类型 | 分值 | 检查对象与通过边界 | 主能力 |
|---|---|---:|---|---|
| automated.delivery_readiness | 规则 | 1 | 8 份可读、实质更新的原位交付，各 1/8；scaffold 和 pending 不算完成 | intent_understanding #2 |
| automated.lookup_binding | 规则 | 14 | docs 5、manifest 7、CLI 1、completion 1。有效绑定须键唯一、值/scope/current/来源同时匹配，manifest 与当前 docs 依赖一致；active 集合无遗漏/重复/额外项，否则此项最高 75%，不加叠罚 | state_awareness #3/#7 |
| automated.validation_categories | 规则 | 10 | scope 0.5、CLI 0.5、docs 1、manifest 2、board 1、workspace freshness 1、audit 1、archived guard 0.5、bundle 2、检查全集 0.5；前八项有事实支持的 passed（guard 可 not_applicable），bundle 正确 stale 且阻塞。按冻结完整分母，不能删检查提高得分 | state_awareness #7 |
| automated.validation_freshness | 规则 | 10 | snapshot/起止/cache/保留旧 refresh 并新增有据刷新各 1；bundle 实际回执及 observed/tested 对账 2、required 完整当前依赖 2、未受影响的 CLI/completion 有效回执及原时点沿用 2。current snapshot 不要求业务全通过 | state_awareness #3/#7 |
| automated.phase_transition | 规则 | 18 | 正确停留与身份/next/completion 4；有据保留唯一 bundle 阻塞并与 gate 键表一致 6；更新记录同一停留决定及阻塞键/理由 4；后续 gate 未开、docs 已对齐而 manifest 待验证 4。实际推进或声称当前已完成使本项 0；不因停留而限制满分 | reasoning_and_decision_making #1 |
| automated.audit_preservation | 规则 | 4 | 历史事件正文/次序完整 2，新事件唯一且在历史后 2；历史被改写/删掉/重复则本项 0。忽略外层章节、标题层级、HTML 注释及换行形式 | 不映射 |
| automated.scope_integrity | 规则 | 2 | 只读来源全保留占 6/8、无额外业务文件占 1/8、身份/组件/phase_order/mutation_policy 保留占 1/8；任一只读文件改变本项 0 | 不映射 |
| automated.record_sync | 规则 | 1 | 原六种传播关系等权：更新决定、路径集、快照 phase/时点、全量分类、cache 全字段来源、新审计引用 | 不映射 |
| llm_judge.board_reconciliation | LLM | 6 | 4 个读者入口与真实文件一致，按下文单元，不重判正确决策值 | state_awareness #3 |
| llm_judge.repair_rationale | LLM | 14 | 4 条选源、依赖失效、局部沿用、停止决定的因果解释；接受任何可见载体里的候选新增等义解释 | reasoning_and_decision_making #1 |
| llm_judge.audit_traceability | LLM | 6 | 4 项本轮记录来源、修复/阻塞、刷新关系、历史纠偏解释；不重复罚历史保留 | 不映射 |
| llm_judge.followup_actionability | LLM | 8 | 4 项角色、需要补的输入绑定凭据、验收和下一 gate 条件、授权边界 | reasoning_and_decision_making #3 |
| llm_judge.completion_calibration | LLM | 6 | 4 项本地完成范围、验收证据、业务阶段结论、外部边界；不把写入成功当内容验收 | result_evaluation #10 |

规则 A=60，语义 B=40，Σw=100。规则 overall_score=Σ规则(wᵢsᵢ)/60，LLM 组分=Σ语义(wᵢsᵢ)/40；题目分为所有贡献之和。规则核心选源、分类、依赖时效、准入决定共 52 分，文件可用和基本保留/同步共 8 分。规则细分计数与权重固定；语义每项 4 个二值单元，允许 0/0.25/0.5/0.75/1，不插值。

“值写对”“依据足以将分类标通过”“阶段准入结论正确”是可区分义务：缓存错但诚实阻塞，与缓存错却涂绿并推进，表现不同。停留可得决策分而不获得未完成修复分；真实修复可以得分而错误推进失去准入分。没有额外整题封顶、期望分数或同一错误的重复总罚。同步项只判传播一致性，错误阶段但文件一致也可得该小项；历史改动不自动抹消新审计可追溯分。进一步作失实完成声明才在声明项按独立证据判断。

### 能力计算与证据边界

采用 capabilities-2026-09-23-v1。映射预算 W=87：意图理解 1，状态感知 40（14+10+10+6），推理与决策 40（18+14+8），结果评估 6；工具调用未覆盖。四维对能力总分贡献上限分别为 100/87、4000/87、4000/87、600/87。能力总分=100×Σ映射项(wᵢsᵢ)/87；维度分=100×Σ该维(wᵢsᵢ)/Σ该维wᵢ。展示时才舍入，未覆盖不记零。

产物、公开说明直接支持关联、决策与验收结论，不据此推断隐藏思考或完整操作过程。自述“已检查”必须有公开证据支持该行为；没有此声明不凭空增设过程分。关键证据被采集器遗漏、截断或评分故障时，相关项不可判定，不删除后重归一，不输出正式能力总分；数值接口需占位时 notes 标 INVALID_EVIDENCE。来源事实由冻结导出保障，普通缺交付可判有效失败。旧七维报告与此加权五维计算的兼容限制保留，未修改框架。

## Automated Checks

```python
FROZEN = {'mutable': ['input/workspace/release_board.md', 'input/workspace/state/workflow_state.json', 'input/workspace/state/validation_results.json', 'input/workspace/state/lookup_cache.json', 'input/workspace/audit/audit_history.md', 'input/workspace/outputs/release_progress_report.md', 'input/workspace/outputs/state_update_record.json', 'environment/mock_release_board/final_state_capture.json'], 'hashes': {'environment/state_diff_manifest.json': '75751855fd19d0c6d970a659ea418748cdd8a16b517bb567d4186c10ca9ac405', 'environment/mock_release_board/final_state_capture.json': '54a6d8b19ad7aa46462432a5ff8b6ea001ae2796272069eff16ab8bb0247ee64', 'environment/mock_release_board/initial_state.json': 'a0d40318838be43f14a961d66242bd9d75dae588d4737d2c91c6c65c9e3fbe52', 'environment/mock_release_board/README.md': '819becdad73e627ad08e47886b9ce0116278480332d1b27c3e46b85fde1289aa', 'input/workspace/release_board.md': 'ebf23911bb0de14da21fe507563415bf3a41b076af34ad7efcd4aefee2ec780a', 'input/workspace/audit/audit_history.md': 'cb2e27b4162996b513031d3ea560754148ee9cea0bd845dd1ef4090b7cca7298', 'input/workspace/config/no_network_policy.txt': '4ac91b843d771e32878d0a22827ad62f77274afe6df133eac948c74ab8d773e1', 'input/workspace/config/release_scope.json': '3c854462ccadbf5a04094f0f25ed61d9cf4dbb8518138aff45a4a72d7a9e0db2', 'input/workspace/handoff/maintainer_handoff.md': 'b93a44e76522e53be413598eac3934e9443c84ca33b8c11701efe0208924e603', 'input/workspace/logs/local_validation_runs.jsonl': '4145e6168fad8d542414fcb81295f16fdf51ec5a88b10f72b8b63f68b6599761', 'input/workspace/notes/old_release_board_copy.md': 'a8713a6735a9598087342e094bd595b977cfcea0c4796db8c5083c1d58381ff1', 'input/workspace/notes/operator_margin_notes.md': '56ca6e00e4a66f45d822a00cafb9660f8e5e5a326f6d036b977c30de47cdded7', 'input/workspace/outputs/release_progress_report.md': '4028d1d7094efefad0ff5dbdbfcd1b18bdfd7a0bdc2408c43f9fc5f24fd430b9', 'input/workspace/outputs/state_update_record.json': '9f7b78e087b9a94d65fb2974612ee4289905a959db66365cd96815f4dc719552', 'input/workspace/runbooks/audit_and_status_sync.md': 'f2f86bdfdf6cd46d46ed8d860bcfa98cd32175b64336e0349c92dc87d1bff212', 'input/workspace/runbooks/local_validation_policy.md': 'f874e1be7fba6feeb25a346ed2aa946217a111b97a548a94800c6b5f893544ca', 'input/workspace/runbooks/phase_gate_policy.md': 'ae7402feaa3ecaa124d5b211c0a0183526c35daae226baa7617e0889df0a36b9', 'input/workspace/state/local_lookup_records.json': 'ed2887b39009a28304274e266c2971f2f2c207fa6894889c33da4ea0d433e51e', 'input/workspace/state/lookup_cache.json': '1c60c3854704552a990675a52383d3e67be0ec46717cb44ee1a966236f22165b', 'input/workspace/state/validation_results.json': 'a88bc1a64e2c6bfed824a52abb065106861a945610c9a94f968002fb6cfde57e', 'input/workspace/state/workflow_state.json': 'dd62d0c735a808f5918eba413b6d2454fb7e9fb013c7f318ee3a520f90676736'}, 'audit_prefix': '\n# Audit history: quillship-cli local release board\n\n> Append-only public audit/history note. Do not rewrite old entries to make the release look cleaner.\n\n## Existing records\n\n### AUD-QS-038 — intake and scope read\n\n- recorded_at_utc: `2026-08-05T08:41:00Z`\n- category: `inspection`\n- linked_artifacts: `config/release_scope.json`, `state/workflow_state.json`\n- note: release id and local-only boundary were inspected. No phase advancement was claimed.\n\n### AUD-QS-039 — scope freeze accepted\n\n- recorded_at_utc: `2026-08-05T09:05:00Z`\n- category: `phase_transition`\n- linked_artifacts: `state/workflow_state.json`, `release_board.md`\n- note: scope moved from `draft_intake` to `scope_freeze` after component list alignment.\n\n### AUD-QS-040 — validation pass summary, partial\n\n- recorded_at_utc: `2026-08-05T10:14:30Z`\n- category: `local_validation_refresh`\n- linked_artifacts: `state/validation_results.json`, `logs/local_validation_runs.jsonl`\n- validation_categories: `passed`, `failed`, `stale`, `missing_lookup`\n- note: several checks passed, but the note did not resolve docs lookup or board/state drift.\n\n### AUD-QS-041 — premature handoff prep note\n\n- recorded_at_utc: `2026-08-05T10:16:05Z`\n- category: `drift_warning`\n- linked_artifacts: `release_board.md`, `state/workflow_state.json`\n- note: board was marked “handoff almost ready” before the docs bundle lookup and freshness check were reconciled. Treat this as a warning, not completion evidence.\n\n## Append new audit entries below\n\n<!-- 在此追加本轮记录；编号自行选择，保持唯一并可回溯。 -->\n', 'initial_workflow': {'workspace_meta': {'case_label': 'release_phase_gate_progression', 'project_label': 'quillship-cli', 'release_id': 'qs-local-2026-08-rc3', 'state_version': 'public-initial-state-v2', 'run_time_utc': '2026-08-05T10:40:00Z', 'network_policy': 'local_only_no_network', 'public_synthetic_state': True}, 'phase_order': [{'order': 1, 'phase_key': 'draft_intake', 'next_phase': 'scope_freeze'}, {'order': 2, 'phase_key': 'scope_freeze', 'next_phase': 'local_validation'}, {'order': 3, 'phase_key': 'local_validation', 'next_phase': 'repair_alignment'}, {'order': 4, 'phase_key': 'repair_alignment', 'next_phase': 'handoff_ready'}, {'order': 5, 'phase_key': 'handoff_ready', 'next_phase': 'release_wrap'}, {'order': 6, 'phase_key': 'release_wrap', 'next_phase': None}], 'phase_status': {'current_phase': 'local_validation', 'current_phase_order': 3, 'state_phase_status': 'in_progress', 'visible_board_phase_label': 'handoff_almost_ready', 'candidate_next_phase': 'repair_alignment', 'skip_ahead_allowed': False, 'completion_claimed': False, 'last_state_change_at_utc': '2026-08-05T10:29:20Z', 'last_state_change_reason': 'release_manifest regenerated after docs patch'}, 'gate_admission': {'local_validation': {'gate_state': 'blocked_pending_local_repair', 'requires_categories_clear': ['failed', 'stale', 'missing_lookup'], 'blocking_category_summary': ['board/state/audit drift not yet reconciled', 'validation snapshot predates docs bundle change', 'active cache missing current docs bundle lookup'], 'passed_items_do_not_override_blockers': True, 'blocking_check_keys': ['docs_bundle_lookup_bound', 'board_state_alignment', 'validation_snapshot_freshness', 'audit_after_validation', 'manifest_dependency_alignment']}, 'repair_alignment': {'gate_state': 'not_admitted_yet', 'requires_previous_phase_validated': True, 'max_allowed_transition_if_admitted': 'from_local_validation_to_repair_alignment'}, 'handoff_ready': {'gate_state': 'not_admitted_yet', 'admission_blocked_by': 'repair_alignment_not_yet_completed'}}, 'components': [{'component_key': 'cli_core', 'state': 'frozen', 'scope_version': 'scope-bundle-2026.08', 'last_changed_at_utc': '2026-08-05T09:02:00Z', 'local_lookup_key': 'cli_core:linux_x64'}, {'component_key': 'shell_completion', 'state': 'frozen', 'scope_version': 'scope-bundle-2026.08', 'last_changed_at_utc': '2026-08-05T09:03:20Z', 'local_lookup_key': 'completion:bash_zsh'}, {'component_key': 'docs_bundle', 'state': 'changed_after_last_validation', 'scope_version': 'scope-bundle-2026.08', 'last_changed_at_utc': '2026-08-05T10:18:00Z', 'local_lookup_key': 'doc_bundle:guide_set'}, {'component_key': 'release_manifest', 'state': 'needs_sync_note', 'scope_version': 'scope-bundle-2026.08', 'last_changed_at_utc': '2026-08-05T10:29:20Z', 'local_lookup_key': 'manifest:rc3_bundle'}], 'audit_requirements': {'append_only': True, 'last_existing_audit_ref': 'AUD-QS-041', 'new_entry_required_after_repair_or_blocked_decision': True, 'forbid_backdated_completion': True}, 'mutation_policy': {'mutable_paths': ['input/workspace/release_board.md', 'input/workspace/state/workflow_state.json', 'input/workspace/state/validation_results.json', 'input/workspace/state/lookup_cache.json', 'input/workspace/audit/audit_history.md', 'input/workspace/outputs/release_progress_report.md', 'input/workspace/outputs/state_update_record.json', 'environment/mock_release_board/final_state_capture.json'], 'read_only_reference_paths': ['input/workspace/runbooks/phase_gate_policy.md', 'input/workspace/runbooks/local_validation_policy.md', 'input/workspace/runbooks/audit_and_status_sync.md', 'input/workspace/state/local_lookup_records.json', 'input/workspace/logs/local_validation_runs.jsonl', 'input/workspace/config/release_scope.json', 'input/workspace/config/no_network_policy.txt', 'environment/mock_release_board/initial_state.json']}}, 'initial_refresh': [{'refresh_key': 'refresh-note-1014-partial', 'recorded_at_utc': '2026-08-05T10:14:30Z', 'summary': 'partial local validation; blockers remained', 'network_used': False}], 'initial_json': {'input/workspace/state/workflow_state.json': {'workspace_meta': {'case_label': 'release_phase_gate_progression', 'project_label': 'quillship-cli', 'release_id': 'qs-local-2026-08-rc3', 'state_version': 'public-initial-state-v2', 'run_time_utc': '2026-08-05T10:40:00Z', 'network_policy': 'local_only_no_network', 'public_synthetic_state': True}, 'phase_order': [{'order': 1, 'phase_key': 'draft_intake', 'next_phase': 'scope_freeze'}, {'order': 2, 'phase_key': 'scope_freeze', 'next_phase': 'local_validation'}, {'order': 3, 'phase_key': 'local_validation', 'next_phase': 'repair_alignment'}, {'order': 4, 'phase_key': 'repair_alignment', 'next_phase': 'handoff_ready'}, {'order': 5, 'phase_key': 'handoff_ready', 'next_phase': 'release_wrap'}, {'order': 6, 'phase_key': 'release_wrap', 'next_phase': None}], 'phase_status': {'current_phase': 'local_validation', 'current_phase_order': 3, 'state_phase_status': 'in_progress', 'visible_board_phase_label': 'handoff_almost_ready', 'candidate_next_phase': 'repair_alignment', 'skip_ahead_allowed': False, 'completion_claimed': False, 'last_state_change_at_utc': '2026-08-05T10:29:20Z', 'last_state_change_reason': 'release_manifest regenerated after docs patch'}, 'gate_admission': {'local_validation': {'gate_state': 'blocked_pending_local_repair', 'requires_categories_clear': ['failed', 'stale', 'missing_lookup'], 'blocking_category_summary': ['board/state/audit drift not yet reconciled', 'validation snapshot predates docs bundle change', 'active cache missing current docs bundle lookup'], 'passed_items_do_not_override_blockers': True, 'blocking_check_keys': ['docs_bundle_lookup_bound', 'board_state_alignment', 'validation_snapshot_freshness', 'audit_after_validation', 'manifest_dependency_alignment']}, 'repair_alignment': {'gate_state': 'not_admitted_yet', 'requires_previous_phase_validated': True, 'max_allowed_transition_if_admitted': 'from_local_validation_to_repair_alignment'}, 'handoff_ready': {'gate_state': 'not_admitted_yet', 'admission_blocked_by': 'repair_alignment_not_yet_completed'}}, 'components': [{'component_key': 'cli_core', 'state': 'frozen', 'scope_version': 'scope-bundle-2026.08', 'last_changed_at_utc': '2026-08-05T09:02:00Z', 'local_lookup_key': 'cli_core:linux_x64'}, {'component_key': 'shell_completion', 'state': 'frozen', 'scope_version': 'scope-bundle-2026.08', 'last_changed_at_utc': '2026-08-05T09:03:20Z', 'local_lookup_key': 'completion:bash_zsh'}, {'component_key': 'docs_bundle', 'state': 'changed_after_last_validation', 'scope_version': 'scope-bundle-2026.08', 'last_changed_at_utc': '2026-08-05T10:18:00Z', 'local_lookup_key': 'doc_bundle:guide_set'}, {'component_key': 'release_manifest', 'state': 'needs_sync_note', 'scope_version': 'scope-bundle-2026.08', 'last_changed_at_utc': '2026-08-05T10:29:20Z', 'local_lookup_key': 'manifest:rc3_bundle'}], 'audit_requirements': {'append_only': True, 'last_existing_audit_ref': 'AUD-QS-041', 'new_entry_required_after_repair_or_blocked_decision': True, 'forbid_backdated_completion': True}, 'mutation_policy': {'mutable_paths': ['input/workspace/release_board.md', 'input/workspace/state/workflow_state.json', 'input/workspace/state/validation_results.json', 'input/workspace/state/lookup_cache.json', 'input/workspace/audit/audit_history.md', 'input/workspace/outputs/release_progress_report.md', 'input/workspace/outputs/state_update_record.json', 'environment/mock_release_board/final_state_capture.json'], 'read_only_reference_paths': ['input/workspace/runbooks/phase_gate_policy.md', 'input/workspace/runbooks/local_validation_policy.md', 'input/workspace/runbooks/audit_and_status_sync.md', 'input/workspace/state/local_lookup_records.json', 'input/workspace/logs/local_validation_runs.jsonl', 'input/workspace/config/release_scope.json', 'input/workspace/config/no_network_policy.txt', 'environment/mock_release_board/initial_state.json']}}, 'input/workspace/state/validation_results.json': {'validation_meta': {'latest_run_key': 'local-run-20260805-1012b', 'validation_kind': 'local_mock_validation_results', 'validated_phase': 'local_validation', 'run_started_at_utc': '2026-08-05T10:12:30Z', 'run_completed_at_utc': '2026-08-05T10:14:08Z', 'state_snapshot_at_utc': '2026-08-05T10:09:00Z', 'latest_state_change_seen_at_utc': '2026-08-05T10:09:00Z', 'current_for_state_at_utc': False, 'must_be_refreshed_after_utc': '2026-08-05T10:29:20Z', 'network_used': False}, 'checks': [{'local_check_key': 'scope_manifest_readable', 'category': 'passed', 'severity': 'required', 'artifact_refs': ['config/release_scope.json', 'state/workflow_state.json'], 'observed_at_utc': '2026-08-05T10:12:38Z', 'reason': 'release_id and current scope are readable and internally named', 'blocks_current_gate': False}, {'local_check_key': 'cli_component_lock', 'category': 'passed', 'severity': 'required', 'artifact_refs': ['state/local_lookup_records.json#cli_core:linux_x64', 'state/local_lookup_records.json#completion:bash_zsh'], 'observed_at_utc': '2026-08-05T10:12:51Z', 'reason': 'CLI and completion component local records match current scope', 'blocks_current_gate': False, 'receipt_ref': 'logs/local_validation_runs.jsonl#line.cli-lock-1012', 'tested_bindings': {'cli_core:linux_x64': 'cli-linux-x64-rc3-local-4b72', 'completion:bash_zsh': 'completion-bash-zsh-rc3-local-91af'}, 'required_bindings': {'cli_core:linux_x64': 'cli-linux-x64-rc3-local-4b72', 'completion:bash_zsh': 'completion-bash-zsh-rc3-local-91af'}}, {'local_check_key': 'docs_bundle_lookup_bound', 'category': 'missing_lookup', 'severity': 'required', 'artifact_refs': ['state/lookup_cache.json#active_cache.doc_bundle:guide_set', 'state/local_lookup_records.json'], 'observed_at_utc': '2026-08-05T10:13:11Z', 'reason': 'active cache lacks a current-scope docs bundle digest', 'blocks_current_gate': True, 'repair_constraint': 'local_lookup_records_only'}, {'local_check_key': 'board_state_alignment', 'category': 'failed', 'severity': 'required', 'artifact_refs': ['release_board.md', 'state/workflow_state.json'], 'observed_at_utc': '2026-08-05T10:13:26Z', 'reason': 'Markdown banner implies handoff while workflow_state current_phase is still local_validation', 'blocks_current_gate': True}, {'local_check_key': 'validation_snapshot_freshness', 'category': 'stale', 'severity': 'required', 'artifact_refs': ['state/workflow_state.json#phase_status.last_state_change_at_utc', 'logs/local_validation_runs.jsonl'], 'observed_at_utc': '2026-08-05T10:13:52Z', 'reason': 'validation snapshot predates docs bundle state change at 10:18Z', 'blocks_current_gate': True}, {'local_check_key': 'audit_after_validation', 'category': 'failed', 'severity': 'required', 'artifact_refs': ['audit/audit_history.md#AUD-QS-041', 'state/validation_results.json'], 'observed_at_utc': '2026-08-05T10:14:02Z', 'reason': 'audit contains premature handoff wording before lookup/cache and freshness were reconciled', 'blocks_current_gate': True}, {'local_check_key': 'archived_board_scope_guard', 'category': 'passed', 'severity': 'advisory', 'artifact_refs': ['notes/old_release_board_copy.md', 'config/release_scope.json'], 'observed_at_utc': '2026-08-05T10:14:06Z', 'reason': 'old board copy has prior scope_version and should remain a distractor', 'blocks_current_gate': False}, {'local_check_key': 'manifest_dependency_alignment', 'category': 'failed', 'severity': 'required', 'artifact_refs': ['state/lookup_cache.json', 'state/local_lookup_records.json'], 'observed_at_utc': '2026-08-05T10:30:15Z', 'reason': 'Active manifest cache carried forward from the 10:19 scan.', 'blocks_current_gate': True}, {'local_check_key': 'bundle_integrity', 'category': 'passed', 'severity': 'required', 'receipt_ref': 'logs/local_validation_runs.jsonl#line.bundle-integrity-1037', 'tested_bindings': {'cli_core:linux_x64': 'cli-linux-x64-rc3-local-4b72', 'completion:bash_zsh': 'completion-bash-zsh-rc3-local-91af', 'doc_bundle:guide_set': 'docs-guide-rc3-local-7a10', 'manifest:rc3_bundle': 'manifest-rc3-local-f19d'}, 'required_bindings': {'cli_core:linux_x64': 'cli-linux-x64-rc3-local-4b72', 'completion:bash_zsh': 'completion-bash-zsh-rc3-local-91af', 'doc_bundle:guide_set': 'docs-guide-rc3-local-7a10', 'manifest:rc3_bundle': 'manifest-rc3-local-c0a5'}, 'artifact_refs': ['logs/local_validation_runs.jsonl#line.bundle-integrity-1037', 'state/lookup_cache.json'], 'observed_at_utc': '2026-08-05T10:37:00Z', 'reason': 'Imported latest packaging receipt marked passed.', 'blocks_current_gate': False}], 'refresh_history': [{'refresh_key': 'refresh-note-1014-partial', 'recorded_at_utc': '2026-08-05T10:14:30Z', 'summary': 'partial local validation; blockers remained', 'network_used': False}]}, 'input/workspace/state/lookup_cache.json': {'cache_meta': {'cache_id': 'qs-local-cache-2026-08-05', 'release_id': 'qs-local-2026-08-rc3', 'last_rebuilt_at_utc': '2026-08-05T09:58:12Z', 'network_allowed': False, 'active_cache_mutable': True}, 'active_cache': [{'lookup_key': 'cli_core:linux_x64', 'scope_version': 'scope-bundle-2026.08', 'cache_value': 'cli-linux-x64-rc3-local-4b72', 'status': 'current', 'source_record_ref': 'state/local_lookup_records.json#record.cli_core.current', 'recorded_at_utc': '2026-08-05T09:57:00Z'}, {'lookup_key': 'completion:bash_zsh', 'scope_version': 'scope-bundle-2026.08', 'cache_value': 'completion-bash-zsh-rc3-local-91af', 'status': 'current', 'source_record_ref': 'state/local_lookup_records.json#record.completion.current', 'recorded_at_utc': '2026-08-05T09:57:30Z'}, {'lookup_key': 'doc_bundle:guide_set', 'scope_version': 'scope-bundle-2026.08', 'cache_value': None, 'status': 'missing', 'source_record_ref': None, 'recorded_at_utc': None, 'required_for_phase': 'local_validation'}, {'lookup_key': 'manifest:rc3_bundle', 'scope_version': 'scope-bundle-2026.08', 'cache_value': 'manifest-rc3-local-c0a5', 'status': 'current_but_needs_note_after_docs_update', 'source_record_ref': 'state/local_lookup_records.json#record.manifest.scan1019', 'recorded_at_utc': '2026-08-05T10:19:20Z'}], 'quarantined_or_stale_entries': [{'lookup_key': 'doc_bundle:guide_set', 'scope_version': 'scope-bundle-2026.07', 'cache_value': 'docs-guide-rc2-archived-88d1', 'status': 'stale_prior_scope', 'reason': 'archived board copy'}, {'lookup_key': 'experimental_plugin_notes', 'scope_version': 'scope-bundle-2026.08', 'cache_value': 'plugin-note-outside-lane-0f11', 'status': 'out_of_scope', 'reason': 'excluded in release_scope'}]}, 'input/workspace/outputs/state_update_record.json': {'record_meta': {'record_type': 'solver_public_state_update_scaffold', 'release_id': 'qs-local-2026-08-rc3', 'run_time_utc': '2026-08-05T10:40:00Z', 'scaffold': True}, 'updated_artifacts': [], 'phase_decision': {'from_phase': None, 'to_phase': None, 'advanced_adjacent_phase_only': None, 'blocked_or_carry_forward_reason': None, 'blocking_check_keys': []}, 'validation_category_handling': [], 'lookup_cache_updates': [], 'audit_history_updates': [{'audit_ref': None, 'recorded_at_utc': None}], 'no_network_confirmation': {'network_used': None, 'scope': None}, 'human_followup': []}, 'environment/mock_release_board/final_state_capture.json': {'mock_app_meta': {'mock_app_kind': 'file_backed_release_board', 'case_label': 'release_phase_gate_progression', 'release_id': 'qs-local-2026-08-rc3', 'capture_file': True, 'not_hidden_gold': True, 'network_allowed': False}, 'capture_status': 'pending_solver_update', 'captured_at_utc': None, 'artifact_state_summary': {'workflow_state_path': 'input/workspace/state/workflow_state.json', 'release_board_path': 'input/workspace/release_board.md', 'validation_results_path': 'input/workspace/state/validation_results.json', 'lookup_cache_path': 'input/workspace/state/lookup_cache.json', 'audit_history_path': 'input/workspace/audit/audit_history.md', 'progress_report_path': 'input/workspace/outputs/release_progress_report.md', 'state_update_record_path': 'input/workspace/outputs/state_update_record.json'}, 'phase_status_capture': {'current_phase': None, 'state_phase_status': None, 'completion_claimed': None, 'candidate_next_phase': None}, 'validation_category_capture': [], 'lookup_cache_capture': [], 'audit_capture': {'audit_ref': None, 'recorded_at_utc': None}, 'no_network_confirmation': None, 'notes': '填写最终文件状态：validation_category_capture 按 local_check_key/category 列出各项；lookup_cache_capture 摘录 active_cache；audit_capture 引用新增审计。no_network_confirmation 使用 network_used 布尔值及 scope 说明。'}}, 'valid_records': {'cli_core:linux_x64': {'record_key': 'record.cli_core.current', 'lookup_key': 'cli_core:linux_x64', 'scope_version': 'scope-bundle-2026.08', 'local_value': 'cli-linux-x64-rc3-local-4b72', 'status': 'current', 'recorded_at_utc': '2026-08-05T09:57:00Z', 'network_used': False, 'evidence_ref': 'logs/local_validation_runs.jsonl#line.lookup-cli-core'}, 'completion:bash_zsh': {'record_key': 'record.completion.current', 'lookup_key': 'completion:bash_zsh', 'scope_version': 'scope-bundle-2026.08', 'local_value': 'completion-bash-zsh-rc3-local-91af', 'status': 'current', 'recorded_at_utc': '2026-08-05T09:57:30Z', 'network_used': False, 'evidence_ref': 'logs/local_validation_runs.jsonl#line.lookup-completion'}, 'doc_bundle:guide_set': {'record_key': 'record.docs.scan1021', 'lookup_key': 'doc_bundle:guide_set', 'scope_version': 'scope-bundle-2026.08', 'local_value': 'docs-guide-rc3-local-c8e1', 'status': 'current', 'recorded_at_utc': '2026-08-05T10:21:12Z', 'network_used': False, 'evidence_ref': 'logs/local_validation_runs.jsonl#line.lookup-docs-current', 'notes': 'Generated by local manifest scan after docs patch.'}, 'manifest:rc3_bundle': {'record_key': 'record.manifest.scan1030', 'lookup_key': 'manifest:rc3_bundle', 'scope_version': 'scope-bundle-2026.08', 'local_value': 'manifest-rc3-local-f19d', 'status': 'current', 'recorded_at_utc': '2026-08-05T10:30:00Z', 'network_used': False, 'evidence_ref': 'logs/local_validation_runs.jsonl#line.manifest-scan1030', 'input_bindings': {'cli_core:linux_x64': 'cli-linux-x64-rc3-local-4b72', 'completion:bash_zsh': 'completion-bash-zsh-rc3-local-91af', 'doc_bundle:guide_set': 'docs-guide-rc3-local-c8e1'}}}, 'facts': {'release_id': 'qs-local-2026-08-rc3', 'scope_version': 'scope-bundle-2026.08', 'decision_time': '2026-08-05T10:40:00Z', 'initial_phase': 'local_validation', 'target_phase': 'repair_alignment', 'target_order': 4, 'next_phase': 'handoff_ready', 'old_snapshot': '2026-08-05T10:09:00Z', 'docs_change': '2026-08-05T10:18:00Z', 'latest_lookup': '2026-08-05T10:30:00Z', 'checks': ['scope_manifest_readable', 'cli_component_lock', 'docs_bundle_lookup_bound', 'board_state_alignment', 'validation_snapshot_freshness', 'audit_after_validation', 'archived_board_scope_guard', 'manifest_dependency_alignment', 'bundle_integrity'], 'expected_decision': 'hold', 'required_blocking_checks': ['bundle_integrity'], 'latest_component_change': '2026-08-05T10:29:20Z'}, 'initial_text': {'input/workspace/release_board.md': '\n# quillship-cli local release board\n\n> Maintainer-facing release board for a command-line utility and documentation bundle. This Markdown board is maintainer-facing and can lag behind JSON state.\n\n## Current banner, copied from maintainer board\n\n- release label: `qs-local-2026-08-rc3`\n- visible lane text: `handoff almost ready`\n- board checkbox copied from previous evening: `[x] validation mostly green`\n\n## Phase tracker\n\n| order | phase_key | board_status | owner_role | note |\n|---:|---|---|---|---|\n| 1 | `draft_intake` | done | release coordinator | scope file and seed manifest were readable yesterday |\n| 2 | `scope_freeze` | done | release coordinator | component list was frozen after docs bundle update |\n| 3 | `local_validation` | needs refresh | validation maintainer | validation review pending |\n| 4 | `repair_alignment` | not started / maybe next | release coordinator | release coordinator review pending |\n| 5 | `handoff_ready` | copied ready label | docs maintainer | copied from the previous evening |\n| 6 | `release_wrap` | not started | maintainer | not scheduled |\n\n## Artifact status notes\n\n- CLI manifest and Linux packaging notes appear stable in the local records.\n- The docs guide-set manifest changed at 10:18Z; a manifest scan was exported at 10:30Z.\n- Packaging receipt imported at 10:37Z: passed.\n- `audit/audit_history.md` contains an optimistic note about handoff prep. Recorded in the local audit history.\n- A copied line in `notes/old_release_board_copy.md` says “ready to publish”. The archived board includes its scope metadata.\n\n## Mutable status panel\n\nThe panel below is intentionally lightweight; update it after reconciling JSON state, validation categories, lookup/cache, and audit timing.\n\n```yaml\nboard_panel_version: panel-rc3-2026-08-05\ncurrent_gate_label: local_validation\nboard_phase_wording: needs_refresh_before_next_gate\nblocking_category_summary:\n  - failed_or_drift_may_exist\n  - stale_snapshot_may_exist\n  - missing_lookup_may_exist\nlast_public_sync_note: "Board not yet reconciled with latest local lookup/cache evidence."\n```\n', 'input/workspace/audit/audit_history.md': '\n# Audit history: quillship-cli local release board\n\n> Append-only public audit/history note. Do not rewrite old entries to make the release look cleaner.\n\n## Existing records\n\n### AUD-QS-038 — intake and scope read\n\n- recorded_at_utc: `2026-08-05T08:41:00Z`\n- category: `inspection`\n- linked_artifacts: `config/release_scope.json`, `state/workflow_state.json`\n- note: release id and local-only boundary were inspected. No phase advancement was claimed.\n\n### AUD-QS-039 — scope freeze accepted\n\n- recorded_at_utc: `2026-08-05T09:05:00Z`\n- category: `phase_transition`\n- linked_artifacts: `state/workflow_state.json`, `release_board.md`\n- note: scope moved from `draft_intake` to `scope_freeze` after component list alignment.\n\n### AUD-QS-040 — validation pass summary, partial\n\n- recorded_at_utc: `2026-08-05T10:14:30Z`\n- category: `local_validation_refresh`\n- linked_artifacts: `state/validation_results.json`, `logs/local_validation_runs.jsonl`\n- validation_categories: `passed`, `failed`, `stale`, `missing_lookup`\n- note: several checks passed, but the note did not resolve docs lookup or board/state drift.\n\n### AUD-QS-041 — premature handoff prep note\n\n- recorded_at_utc: `2026-08-05T10:16:05Z`\n- category: `drift_warning`\n- linked_artifacts: `release_board.md`, `state/workflow_state.json`\n- note: board was marked “handoff almost ready” before the docs bundle lookup and freshness check were reconciled. Treat this as a warning, not completion evidence.\n\n## Append new audit entries below\n\n<!-- 在此追加本轮记录；编号自行选择，保持唯一并可回溯。 -->\n', 'input/workspace/outputs/release_progress_report.md': '\n# Release progress report\n\n> 维护者进度报告草稿。完成本轮工作区修复与同步后，用简短中文替换占位项；不要输出字段清单式罗列。\n\n## 本轮更新摘要\n\n- 待填写：更新了哪些 artifact role，以及是否只推进相邻 phase。\n\n## Validation category handling\n\n- `passed`：待填写\n- `failed`：待填写\n- `stale`：待填写\n- `missing_lookup`：待填写\n\n## State / board / audit synchronization\n\n- 待填写：说明 Markdown board、workflow_state、validation_results、lookup_cache、audit_history 是否已同步，或哪些 blocker 被 carry forward。\n\n## No-network boundary\n\n- 待填写：确认只使用工作区公开文件，没有调用 live service。\n\n## Human follow-up / carry-forward\n\n- 待填写：如果仍需人工跟进，请列出原因；如果没有，也请说明不是因为跳过 gate。\n'}, 'event_log': [{'source_path': 'input/workspace/logs/local_validation_runs.jsonl', 'line': 1, 'record': {'line_ref': 'line.lookup-cli-core', 'timestamp_utc': '2026-08-05T09:57:00Z', 'event_type': 'local_lookup_scan', 'lookup_key': 'cli_core:linux_x64', 'scope_version': 'scope-bundle-2026.08', 'local_value': 'cli-linux-x64-rc3-local-4b72', 'network_used': False, 'note': 'local manifest slot readable'}}, {'source_path': 'input/workspace/logs/local_validation_runs.jsonl', 'line': 2, 'record': {'line_ref': 'line.lookup-completion', 'timestamp_utc': '2026-08-05T09:57:30Z', 'event_type': 'local_lookup_scan', 'lookup_key': 'completion:bash_zsh', 'scope_version': 'scope-bundle-2026.08', 'local_value': 'completion-bash-zsh-rc3-local-91af', 'network_used': False, 'note': 'shell completion manifest matched current scope'}}, {'source_path': 'input/workspace/logs/local_validation_runs.jsonl', 'line': 3, 'record': {'line_ref': 'line.validation-1012-start', 'timestamp_utc': '2026-08-05T10:12:30Z', 'event_type': 'validation_start', 'validation_key': 'local-run-20260805-1012b', 'snapshot_at_utc': '2026-08-05T10:09:00Z', 'network_used': False}}, {'source_path': 'input/workspace/logs/local_validation_runs.jsonl', 'line': 4, 'record': {'line_ref': 'line.validation-1014-summary', 'timestamp_utc': '2026-08-05T10:14:08Z', 'event_type': 'validation_summary', 'validation_key': 'local-run-20260805-1012b', 'categories_seen': ['passed', 'failed', 'stale', 'missing_lookup'], 'network_used': False, 'note': 'partial pass with blockers'}}, {'source_path': 'input/workspace/logs/local_validation_runs.jsonl', 'line': 5, 'record': {'line_ref': 'line.docs-patch-local', 'timestamp_utc': '2026-08-05T10:18:00Z', 'event_type': 'local_state_change', 'component_key': 'docs_bundle', 'scope_version': 'scope-bundle-2026.08', 'network_used': False, 'note': 'guide-set manifest changed after validation snapshot'}}, {'source_path': 'input/workspace/logs/local_validation_runs.jsonl', 'line': 6, 'record': {'line_ref': 'line.lookup-manifest', 'timestamp_utc': '2026-08-05T10:19:20Z', 'event_type': 'local_lookup_scan', 'lookup_key': 'manifest:rc3_bundle', 'scope_version': 'scope-bundle-2026.08', 'local_value': 'manifest-rc3-local-c0a5', 'network_used': False, 'note': 'manifest slot refreshed after docs patch', 'input_bindings': {'doc_bundle:guide_set': 'docs-guide-rc3-local-7a10', 'cli_core:linux_x64': 'cli-linux-x64-rc3-local-4b72', 'completion:bash_zsh': 'completion-bash-zsh-rc3-local-91af'}}}, {'source_path': 'input/workspace/logs/local_validation_runs.jsonl', 'line': 7, 'record': {'line_ref': 'line.lookup-docs-current', 'timestamp_utc': '2026-08-05T10:21:12Z', 'event_type': 'local_lookup_scan', 'lookup_key': 'doc_bundle:guide_set', 'scope_version': 'scope-bundle-2026.08', 'local_value': 'docs-guide-rc3-local-c8e1', 'network_used': False, 'note': 'current local docs digest candidate; not yet copied to active cache at log time'}}, {'source_path': 'input/workspace/logs/local_validation_runs.jsonl', 'line': 8, 'record': {'line_ref': 'line.no-network-heartbeat', 'timestamp_utc': '2026-08-05T10:22:40Z', 'event_type': 'boundary_check', 'network_used': False, 'note': 'mock release board is local files only'}}, {'source_path': 'input/workspace/logs/local_validation_runs.jsonl', 'line': 9, 'record': {'line_ref': 'line.archive-timeout-noise', 'timestamp_utc': '2026-08-04T17:55:00Z', 'event_type': 'old_timeout_noise', 'scope_version': 'scope-bundle-2026.07', 'network_used': False, 'note': 'prior scope archive note; do not use as current blocker'}}, {'source_path': 'input/workspace/logs/local_validation_runs.jsonl', 'line': 10, 'record': {'line_ref': 'line.docs-scan1028', 'timestamp_utc': '2026-08-05T10:28:00Z', 'event_type': 'local_lookup_scan', 'lookup_key': 'doc_bundle:guide_set', 'scope_version': 'scope-bundle-2026.08', 'local_value': 'docs-guide-rc3-local-6d92', 'network_used': False, 'quarantined': True}}, {'source_path': 'input/workspace/logs/local_validation_runs.jsonl', 'line': 11, 'record': {'line_ref': 'line.docs-scan1031', 'timestamp_utc': '2026-08-05T10:31:00Z', 'event_type': 'imported_lookup_receipt', 'lookup_key': 'doc_bundle:guide_set', 'scope_version': 'scope-bundle-2026.08', 'local_value': 'docs-guide-rc3-mirror-75b3', 'network_used': True}}, {'source_path': 'input/workspace/logs/local_validation_runs.jsonl', 'line': 12, 'record': {'line_ref': 'line.docs-scan1045', 'timestamp_utc': '2026-08-05T10:45:00Z', 'event_type': 'local_lookup_scan', 'lookup_key': 'doc_bundle:guide_set', 'scope_version': 'scope-bundle-2026.08', 'local_value': 'docs-guide-rc3-local-a920', 'network_used': False}}, {'source_path': 'input/workspace/logs/local_validation_runs.jsonl', 'line': 13, 'record': {'line_ref': 'line.manifest-edit1029', 'timestamp_utc': '2026-08-05T10:29:20Z', 'event_type': 'local_state_change', 'component_key': 'release_manifest', 'scope_version': 'scope-bundle-2026.08', 'network_used': False, 'note': 'Manifest regenerated against the guide-set scan receipt.'}}, {'source_path': 'input/workspace/logs/local_validation_runs.jsonl', 'line': 14, 'record': {'line_ref': 'line.manifest-scan1030', 'timestamp_utc': '2026-08-05T10:30:00Z', 'event_type': 'local_lookup_scan', 'lookup_key': 'manifest:rc3_bundle', 'scope_version': 'scope-bundle-2026.08', 'local_value': 'manifest-rc3-local-f19d', 'network_used': False, 'input_bindings': {'cli_core:linux_x64': 'cli-linux-x64-rc3-local-4b72', 'completion:bash_zsh': 'completion-bash-zsh-rc3-local-91af', 'doc_bundle:guide_set': 'docs-guide-rc3-local-c8e1'}}}, {'source_path': 'input/workspace/logs/local_validation_runs.jsonl', 'line': 15, 'record': {'line_ref': 'line.bundle-integrity-1044', 'timestamp_utc': '2026-08-05T10:44:00Z', 'event_type': 'local_validation_receipt', 'local_check_key': 'bundle_integrity', 'scope_version': 'scope-bundle-2026.08', 'status': 'passed', 'network_used': False, 'input_bindings': {'cli_core:linux_x64': 'cli-linux-x64-rc3-local-4b72', 'completion:bash_zsh': 'completion-bash-zsh-rc3-local-91af', 'doc_bundle:guide_set': 'docs-guide-rc3-local-c8e1', 'manifest:rc3_bundle': 'manifest-rc3-local-f19d'}}}, {'source_path': 'input/workspace/logs/local_validation_runs.jsonl', 'line': 16, 'record': {'line_ref': 'line.cli-lock-1012', 'timestamp_utc': '2026-08-05T10:12:51Z', 'event_type': 'local_validation_receipt', 'local_check_key': 'cli_component_lock', 'scope_version': 'scope-bundle-2026.08', 'status': 'passed', 'network_used': False, 'input_bindings': {'cli_core:linux_x64': 'cli-linux-x64-rc3-local-4b72', 'completion:bash_zsh': 'completion-bash-zsh-rc3-local-91af'}}}, {'source_path': 'input/workspace/logs/local_validation_runs.jsonl', 'line': 17, 'record': {'line_ref': 'line.bundle-integrity-1037', 'timestamp_utc': '2026-08-05T10:37:00Z', 'event_type': 'local_validation_receipt', 'local_check_key': 'bundle_integrity', 'scope_version': 'scope-bundle-2026.08', 'status': 'passed', 'network_used': False, 'input_bindings': {'cli_core:linux_x64': 'cli-linux-x64-rc3-local-4b72', 'completion:bash_zsh': 'completion-bash-zsh-rc3-local-91af', 'doc_bundle:guide_set': 'docs-guide-rc3-local-7a10', 'manifest:rc3_bundle': 'manifest-rc3-local-f19d'}}}, {'source_path': 'input/workspace/logs/local_validation_runs.jsonl', 'line': 18, 'record': {'line_ref': 'line.bundle-integrity-1024', 'timestamp_utc': '2026-08-05T10:24:00Z', 'event_type': 'local_validation_receipt', 'local_check_key': 'bundle_integrity', 'scope_version': 'scope-bundle-2026.08', 'status': 'passed', 'network_used': False, 'input_bindings': {'cli_core:linux_x64': 'cli-linux-x64-rc3-local-4b72', 'completion:bash_zsh': 'completion-bash-zsh-rc3-local-91af', 'doc_bundle:guide_set': 'docs-guide-rc3-local-7a10', 'manifest:rc3_bundle': 'manifest-rc3-local-c0a5'}}}], 'public_record_candidates': [{'record_key': 'record.cli_core.current', 'lookup_key': 'cli_core:linux_x64', 'scope_version': 'scope-bundle-2026.08', 'local_value': 'cli-linux-x64-rc3-local-4b72', 'status': 'current', 'recorded_at_utc': '2026-08-05T09:57:00Z', 'network_used': False, 'evidence_ref': 'logs/local_validation_runs.jsonl#line.lookup-cli-core'}, {'record_key': 'record.docs.scan1031', 'lookup_key': 'doc_bundle:guide_set', 'scope_version': 'scope-bundle-2026.08', 'local_value': 'docs-guide-rc3-mirror-75b3', 'status': 'current', 'recorded_at_utc': '2026-08-05T10:31:00Z', 'network_used': True, 'evidence_ref': 'logs/local_validation_runs.jsonl#line.docs-scan1031', 'notes': 'Imported mirror lookup receipt.'}, {'record_key': 'record.manifest.scan1030', 'lookup_key': 'manifest:rc3_bundle', 'scope_version': 'scope-bundle-2026.08', 'local_value': 'manifest-rc3-local-f19d', 'status': 'current', 'recorded_at_utc': '2026-08-05T10:30:00Z', 'network_used': False, 'evidence_ref': 'logs/local_validation_runs.jsonl#line.manifest-scan1030', 'input_bindings': {'cli_core:linux_x64': 'cli-linux-x64-rc3-local-4b72', 'completion:bash_zsh': 'completion-bash-zsh-rc3-local-91af', 'doc_bundle:guide_set': 'docs-guide-rc3-local-c8e1'}}, {'record_key': 'record.docs.scan0729', 'lookup_key': 'doc_bundle:guide_set', 'scope_version': 'scope-bundle-2026.07', 'local_value': 'docs-guide-rc2-archived-88d1', 'status': 'stale', 'recorded_at_utc': '2026-07-29T15:03:00Z', 'network_used': False, 'evidence_ref': 'notes/old_release_board_copy.md', 'notes': 'July guide-set archive export.'}, {'record_key': 'record.completion.current', 'lookup_key': 'completion:bash_zsh', 'scope_version': 'scope-bundle-2026.08', 'local_value': 'completion-bash-zsh-rc3-local-91af', 'status': 'current', 'recorded_at_utc': '2026-08-05T09:57:30Z', 'network_used': False, 'evidence_ref': 'logs/local_validation_runs.jsonl#line.lookup-completion'}, {'record_key': 'record.docs.scan1045', 'lookup_key': 'doc_bundle:guide_set', 'scope_version': 'scope-bundle-2026.08', 'local_value': 'docs-guide-rc3-local-a920', 'status': 'current', 'recorded_at_utc': '2026-08-05T10:45:00Z', 'network_used': False, 'evidence_ref': 'logs/local_validation_runs.jsonl#line.docs-scan1045', 'notes': 'A subsequent scan is present in this consolidated export.'}, {'record_key': 'record.docs.scan1021', 'lookup_key': 'doc_bundle:guide_set', 'scope_version': 'scope-bundle-2026.08', 'local_value': 'docs-guide-rc3-local-c8e1', 'status': 'current', 'recorded_at_utc': '2026-08-05T10:21:12Z', 'network_used': False, 'evidence_ref': 'logs/local_validation_runs.jsonl#line.lookup-docs-current', 'notes': 'Generated by local manifest scan after docs patch.'}, {'record_key': 'record.docs.scan1028', 'lookup_key': 'doc_bundle:guide_set', 'scope_version': 'scope-bundle-2026.08', 'local_value': 'docs-guide-rc3-local-6d92', 'status': 'current', 'recorded_at_utc': '2026-08-05T10:28:00Z', 'network_used': False, 'quarantined': True, 'evidence_ref': 'logs/local_validation_runs.jsonl#line.docs-scan1028', 'notes': 'Scan retained while the guide-set signature exception is investigated.'}, {'record_key': 'record.manifest.scan1019', 'lookup_key': 'manifest:rc3_bundle', 'scope_version': 'scope-bundle-2026.08', 'local_value': 'manifest-rc3-local-c0a5', 'status': 'current', 'recorded_at_utc': '2026-08-05T10:19:20Z', 'network_used': False, 'evidence_ref': 'logs/local_validation_runs.jsonl#line.lookup-manifest', 'input_bindings': {'doc_bundle:guide_set': 'docs-guide-rc3-local-7a10', 'cli_core:linux_x64': 'cli-linux-x64-rc3-local-4b72', 'completion:bash_zsh': 'completion-bash-zsh-rc3-local-91af'}}], 'revision': 'office007-r4', 'validation_requirements': {'cli_component_lock': {'input_lookup_keys': ['cli_core:linux_x64', 'completion:bash_zsh'], 'evidence_kind': 'local_validation_receipt'}, 'bundle_integrity': {'input_lookup_keys': ['cli_core:linux_x64', 'completion:bash_zsh', 'doc_bundle:guide_set', 'manifest:rc3_bundle'], 'evidence_kind': 'local_validation_receipt', 'required_for_phase': 'local_validation', 'owner_role': 'packaging maintainer'}}, 'eligible_receipts': [{'line_ref': 'line.cli-lock-1012', 'timestamp_utc': '2026-08-05T10:12:51Z', 'event_type': 'local_validation_receipt', 'local_check_key': 'cli_component_lock', 'scope_version': 'scope-bundle-2026.08', 'status': 'passed', 'network_used': False, 'input_bindings': {'cli_core:linux_x64': 'cli-linux-x64-rc3-local-4b72', 'completion:bash_zsh': 'completion-bash-zsh-rc3-local-91af'}}, {'line_ref': 'line.bundle-integrity-1037', 'timestamp_utc': '2026-08-05T10:37:00Z', 'event_type': 'local_validation_receipt', 'local_check_key': 'bundle_integrity', 'scope_version': 'scope-bundle-2026.08', 'status': 'passed', 'network_used': False, 'input_bindings': {'cli_core:linux_x64': 'cli-linux-x64-rc3-local-4b72', 'completion:bash_zsh': 'completion-bash-zsh-rc3-local-91af', 'doc_bundle:guide_set': 'docs-guide-rc3-local-7a10', 'manifest:rc3_bundle': 'manifest-rc3-local-f19d'}}, {'line_ref': 'line.bundle-integrity-1024', 'timestamp_utc': '2026-08-05T10:24:00Z', 'event_type': 'local_validation_receipt', 'local_check_key': 'bundle_integrity', 'scope_version': 'scope-bundle-2026.08', 'status': 'passed', 'network_used': False, 'input_bindings': {'cli_core:linux_x64': 'cli-linux-x64-rc3-local-4b72', 'completion:bash_zsh': 'completion-bash-zsh-rc3-local-91af', 'doc_bundle:guide_set': 'docs-guide-rc3-local-7a10', 'manifest:rc3_bundle': 'manifest-rc3-local-c0a5'}}], 'receipt_truth': {'cli_component_lock': True, 'bundle_integrity': False}, 'current_bindings': {'cli_core:linux_x64': 'cli-linux-x64-rc3-local-4b72', 'completion:bash_zsh': 'completion-bash-zsh-rc3-local-91af', 'doc_bundle:guide_set': 'docs-guide-rc3-local-c8e1', 'manifest:rc3_bundle': 'manifest-rc3-local-f19d'}, 'component_dependencies': {'cli_core': [], 'shell_completion': ['cli_core'], 'docs_bundle': [], 'release_manifest': ['docs_bundle', 'cli_core', 'shell_completion']}}

import hashlib
import json
import os
import re
from pathlib import Path
from datetime import datetime, timezone

# FROZEN is inserted from adapted public inputs by the author. No candidate file
# can redefine truth, allowed paths, original history, or category denominators.
WEIGHTS = {'delivery_readiness':1, 'lookup_binding':14, 'validation_categories':10,
           'validation_freshness':10, 'phase_transition':18, 'audit_preservation':4,
           'scope_integrity':2, 'record_sync':1}
P = 'input/workspace/'
W, V, L = (P+'state/'+s+'.json' for s in ('workflow_state','validation_results','lookup_cache'))
A, B = P+'audit/audit_history.md', P+'release_board.md'
R, U = P+'outputs/release_progress_report.md', P+'outputs/state_update_record.json'
C = 'environment/mock_release_board/final_state_capture.json'

class EvaluationError(RuntimeError):
    pass

class CandidateError(ValueError):
    pass

def obj(value):
    return value if isinstance(value, dict) else {}

def rows(value):
    return value if isinstance(value, list) else []

def norm(value):
    return str(value or '').strip().casefold().replace('-', '_').replace(' ', '_')

def dt(value):
    if not isinstance(value,str): return None
    try:
        parsed=datetime.fromisoformat(value.strip().replace('Z','+00:00'))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else None

def refnorm(value):
    if not isinstance(value,str): return ''
    value=value.strip().replace('\\','/').replace('`','')
    for prefix in ('/tmp_workspace/','./','input/workspace/'):
        if value.startswith(prefix): value=value[len(prefix):]
    return value

def evidence_refs(record):
    return {refnorm(value) for field in ('evidence_refs','source_refs','artifact_refs')
            for value in rows(obj(record).get(field)) if isinstance(value,str)}

def unique_rows(value,key):
    result={}
    valid=isinstance(value,list) and bool(value)
    for row in rows(value):
        k=obj(row).get(key)
        if not isinstance(k,str) or not k or k in result:
            valid=False
        else:
            result[k]=row
    return result,valid

def no_duplicates(pairs):
    result={}
    for k,v in pairs:
        if k in result: raise CandidateError('Duplicate JSON key: '+k)
        result[k]=v
    return result

def parse_json(s):
    def bad_constant(s): raise CandidateError('Non-finite JSON value: '+s)
    return json.loads(s,object_pairs_hook=no_duplicates,parse_constant=bad_constant)

def safe_file(root,rel,private=False):
    p=root/rel
    for x in (p,*p.parents):
        if x==root: break
        if x.is_symlink() or (hasattr(x,'is_junction') and x.is_junction()):
            return None,'unsafe_link'
    resolved=p.resolve()
    if not resolved.is_relative_to(root): return None,'outside_workspace'
    if not private and (resolved.is_relative_to(root/'gt') or resolved.is_relative_to(root/'.grading')):
        return None,'protected_grader_path'
    if not p.exists(): return None,'missing'
    if not p.is_file(): return None,'not_regular_file'
    # Normal inputs are a few KB. A size guard is an explicit evidence failure,
    # not a candidate zero or silent truncation.
    if p.stat().st_size>2_000_000: raise EvaluationError('Evidence size requires manual review: '+rel)
    return p,''

def read_candidate(root,rel):
    p,reason=safe_file(root,rel)
    if not p: return '',None,reason
    try:
        raw=p.read_text(encoding='utf-8-sig')
    except UnicodeError:
        return '',None,'invalid_utf8'
    if rel.endswith('.json'):
        try: data=parse_json(raw)
        except (ValueError,RecursionError) as exc: return raw,None,'invalid_json: '+str(exc)
        if not isinstance(data,dict): return raw,None,'json_root_not_object'
        return raw,data,''
    return raw,None,'' if raw.strip() else 'empty'

def grade(transcript:list,workspace_path:str)->dict:
    root=Path(workspace_path).resolve()
    facts=FROZEN['facts']
    limit=dt(facts['decision_time'])
    latest=dt(facts['latest_lookup'])
    # GT is a private example, not a byte-equality oracle. Missing/broken GT is
    # an evaluation error even though stable truth is frozen in this code.
    for rel in FROZEN['mutable']:
        p,reason=safe_file(root,'gt/'+rel,private=True)
        if not p: raise EvaluationError('Missing/unsafe reference: '+rel+' '+reason)
        try:
            t=p.read_text(encoding='utf-8-sig')
            if not t.strip(): raise ValueError('empty reference')
            if rel.endswith('.json') and not isinstance(parse_json(t),dict):
                raise ValueError('reference must be an object')
        except (UnicodeError,ValueError,RecursionError) as exc:
            raise EvaluationError('Invalid reference: '+rel) from exc

    texts,data,errors={},{},{}
    for rel in FROZEN['mutable']:
        texts[rel],value,error=read_candidate(root,rel)
        data[rel]=obj(value)
        if error: errors[rel]=error
    workflow,validation,lookup,update,capture=(data[x] for x in (W,V,L,U,C))
    scores,units={},{}
    def put(key,values):
        values=[bool(x) for x in values]
        units[key]=values
        scores[key]=sum(values)/len(values)

    readiness=[]
    for rel in FROZEN['mutable']:
        ok=rel not in errors and bool(texts[rel].strip())
        if rel.endswith('.json'):
            ok=ok and data[rel]!=FROZEN['initial_json'][rel]
            if rel==U: ok=ok and bool(rows(update.get('updated_artifacts'))) and bool(obj(update.get('phase_decision')).get('to_phase')) and obj(update.get('record_meta')).get('scaffold') is not True
            if rel==C: ok=ok and bool(obj(capture.get('phase_status_capture')).get('current_phase')) and norm(capture.get('capture_status')) not in ('','pending_solver_update','pending')
        else:
            # CRLF/BOM changes alone do not count as finishing a draft.
            original=FROZEN['initial_text'][rel].replace('\r\n','\n').strip()
            ok=ok and texts[rel].replace('\r\n','\n').strip()!=original
        readiness.append(ok)
    put('delivery_readiness',readiness)

    active,unique=unique_rows(lookup.get('active_cache'),'lookup_key')
    expected=FROZEN['valid_records']
    def cache_ok(key,provenance=True):
        a=obj(active.get(key)); e=expected[key]
        return a.get('cache_value')==e['local_value'] and a.get('scope_version')==facts['scope_version'] and norm(a.get('status'))=='current' and (not provenance or refnorm(a.get('source_record_ref'))=='state/local_lookup_records.json#'+e['record_key'])
    docs=obj(active.get('doc_bundle:guide_set'))
    # Four source obligations have business weights 5:7:1:1.  A digest and
    # its provenance are one usable binding, not independent consolation points.
    lookup_shape=unique and set(active)==set(expected)
    key_counts={k:sum(obj(row).get('lookup_key')==k for row in rows(lookup.get('active_cache'))) for k in expected}
    docs_bound=key_counts['doc_bundle:guide_set']==1 and cache_ok('doc_bundle:guide_set')
    manifest_bound=key_counts['manifest:rc3_bundle']==1 and cache_ok('manifest:rc3_bundle') and docs_bound
    cli_bound=key_counts['cli_core:linux_x64']==1 and cache_ok('cli_core:linux_x64')
    completion_bound=key_counts['completion:bash_zsh']==1 and cache_ok('completion:bash_zsh')
    put('lookup_binding',[docs_bound]*5+[manifest_bound]*7+[cli_bound,completion_bound])
    # A malformed active set is not fully usable, but valid unrelated bindings
    # retain partial credit; do not zero every binding for one extra row.
    if not lookup_shape: scores['lookup_binding']=min(scores['lookup_binding'],0.75)

    checks,checks_unique=unique_rows(validation.get('checks'),'local_check_key')
    cat_units=[]
    for key in facts['checks']:
        check=obj(checks.get(key))
        accepted={'passed'} if key!='archived_board_scope_guard' else {'passed','not_applicable'}
        cat_units.append(norm(check.get('category')) in accepted and check.get('blocks_current_gate') is False)
    cat_units.append(checks_unique and set(checks)==set(facts['checks']) and all(norm(c.get('category')) not in ('failed','stale','missing_lookup') and c.get('blocks_current_gate') is False for c in checks.values()))
    put('validation_categories',cat_units)

    meta=obj(validation.get('validation_meta')); phase=obj(workflow.get('phase_status'))
    snapshot=dt(meta.get('state_snapshot_at_utc'))
    state_time=dt(phase.get('last_state_change_at_utc'))
    cache_time=dt(obj(lookup.get('cache_meta')).get('last_rebuilt_at_utc'))
    start,end=dt(meta.get('run_started_at_utc')),dt(meta.get('run_completed_at_utc'))
    event_times=[meta.get('state_snapshot_at_utc'),meta.get('run_started_at_utc'),meta.get('run_completed_at_utc'),phase.get('last_state_change_at_utc'),obj(lookup.get('cache_meta')).get('last_rebuilt_at_utc')]
    bounded=all(dt(t) and dt(t)<=limit for t in event_times)
    refreshes=rows(validation.get('refresh_history'))
    old=FROZEN['initial_refresh']
    old_ids={x['refresh_key'] for x in old}
    new=[x for x in refreshes if isinstance(x,dict) and x.get('refresh_key') not in old_ids and isinstance(x.get('refresh_key'),str) and x['refresh_key']]
    refresh_rows,refresh_unique=unique_rows(refreshes,'refresh_key')
    docs_source=expected['doc_bundle:guide_set']
    docs_source_ref='state/local_lookup_records.json#'+docs_source['record_key']
    docs_log_ref=refnorm(docs_source['evidence_ref'])
    cache_targets={'state/lookup_cache.json','state/lookup_cache.json#active_cache',
                   'state/lookup_cache.json#active_cache.doc_bundle:guide_set'}
    for index,row in enumerate(rows(lookup.get('active_cache'))):
        if obj(row).get('lookup_key')=='doc_bundle:guide_set':
            cache_targets.update({'state/lookup_cache.json#active_cache['+str(index)+']',
                                  'state/lookup_cache.json#/active_cache/'+str(index)})
    def canonical_time_values(value):
        if isinstance(value,dict):return {k:canonical_time_values(v) for k,v in value.items()}
        if isinstance(value,list):return [canonical_time_values(v) for v in value]
        stamp=dt(value)
        return stamp.isoformat() if stamp else value
    good_refresh=[]
    for x in new:
        stamp=dt(x.get('recorded_at_utc'))
        direct_refs={refnorm(z) for z in rows(x.get('evidence_refs',x.get('source_refs')))}
        direct_linked={docs_source_ref,docs_log_ref,'state/lookup_cache.json'}<=direct_refs
        refs=evidence_refs(x) | evidence_refs(meta)
        # Checks observed for this snapshot can hold the shared repair evidence;
        # old checks or unrelated files cannot supply missing refresh provenance.
        for key in ('docs_bundle_lookup_bound','validation_snapshot_freshness'):
            check=obj(checks.get(key))
            observed=dt(check.get('observed_at_utc'))
            if snapshot and observed and stamp and snapshot<=observed<=stamp:
                refs.update(evidence_refs(check))
        cache_linked=L not in errors and bool(docs) and bool(refs & cache_targets)
        if cache_linked:
            refs.add(refnorm(docs.get('source_record_ref')))
        # Frozen current records and their log events identify the same source;
        # following this relation does not require copying both refs everywhere.
        if docs_source_ref in refs or docs_log_ref in refs:
            refs.update((docs_source_ref,docs_log_ref))
        # Shared evidence is an alternative to the existing complete direct refs.
        provenance=direct_linked or (cache_linked and docs_source_ref in refs and docs_log_ref in refs)
        good_refresh.append(bool(stamp and snapshot and latest<=snapshot<=stamp<=limit and x.get('network_used') is False and provenance))
    put('validation_freshness',[
        meta.get('current_for_state_at_utc') is True and snapshot and state_time and state_time<=snapshot<=limit and latest<=snapshot,
        start and end and snapshot and start<=end<=limit and latest<=end and snapshot<=end and bounded,
        cache_time and snapshot and latest<=cache_time<=snapshot<=limit,
        refresh_unique and all(any(canonical_time_values(x)==canonical_time_values(y) for y in refreshes) for x in old) and any(good_refresh)
    ])

    gates=obj(workflow.get('gate_admission'))
    admitted={'admitted','passed','validated','done','completed','complete'}
    active_states={'admitted','in_progress','active','open','started'}
    unopened={'not_admitted_yet','not_admitted','pending','not_started','blocked','blocked_pending_previous_gate'}
    put('phase_transition',[
        phase.get('current_phase')==facts['target_phase'] and phase.get('current_phase_order')==facts['target_order'],
        norm(phase.get('state_phase_status'))=='in_progress' and phase.get('completion_claimed') is False,
        phase.get('skip_ahead_allowed') is False and phase.get('candidate_next_phase')==facts['next_phase'],
        norm(obj(gates.get('local_validation')).get('gate_state')) in admitted and norm(obj(gates.get('repair_alignment')).get('gate_state')) in active_states,
        norm(obj(gates.get('handoff_ready')).get('gate_state')) in unopened and all(phase.get(k) is not True for k in ('handoff_claimed','handoff_ready_claimed','release_wrap_claimed'))
    ])
    # Crossing the one-phase boundary defeats this criterion as a whole.
    order=phase.get('current_phase_order')
    if phase.get('current_phase') in ('handoff_ready','release_wrap') or (isinstance(order,(int,float)) and not isinstance(order,bool) and order>facts['target_order']):
        put('phase_transition',[False]*5)

    # Compare historical records, never the author's append-section scaffold.
    # Heading levels, wrapper titles, BOM/CRLF and append comments do not alter
    # the recorded event. Timestamp, category, title and body remain immutable.
    def audit_records(text):
        text=re.sub(r'<!--.*?-->','',text.replace('\r\n','\n').lstrip('\ufeff'),flags=re.S)
        found=[]
        for match in re.finditer(r'^#{2,6}\s+(\S+)[^\n]*\n.*?(?=^#{1,6}\s|\Z)',text,re.M|re.S):
            block=match.group(0)
            if not re.search(r'(?:recorded_at_utc|timestamp_utc|recorded_at|记账时间|记录时间|category)[`*\s]*[:：]',block,re.I):continue
            normalized=re.sub(r'^#{2,6}\s+','',block).strip()
            normalized='\n'.join(line.rstrip() for line in normalized.splitlines())
            found.append((match.group(1),normalized,block,match.start()))
        return found
    old_records=audit_records(FROZEN['audit_prefix']);actual_records=audit_records(texts[A])
    old_refs={x[0] for x in old_records}
    old_actual=[x for x in actual_records if x[0] in old_refs]
    preserved=[x[:2] for x in old_actual]==[x[:2] for x in old_records]
    new_records=[x for x in actual_records if x[0] not in old_refs]
    appended='\n'.join(re.sub(r'^#{2,6}\s+','### ',x[2]) for x in new_records)
    new_heads=[x[0] for x in new_records]
    after_history=bool(old_actual and all(x[3]>old_actual[-1][3] for x in new_records))
    put('audit_preservation',[preserved,bool(new_records) and len(new_heads)==len(set(new_heads)) and after_history])

    protected=[rel for rel in FROZEN['hashes'] if rel not in FROZEN['mutable']]
    changed=[]
    for rel in protected:
        p,err=safe_file(root,rel)
        if not p or hashlib.sha256(p.read_bytes()).hexdigest()!=FROZEN['hashes'][rel]: changed.append(rel)
    extra=[]
    for directory in ('input','environment'):
        base=root/directory
        if base.is_symlink() or (hasattr(base,'is_junction') and base.is_junction()):
            extra.append(directory)
            continue
        for parent, dirs, files in os.walk(base,followlinks=False):
            for name in list(dirs):
                p=Path(parent)/name
                if p.is_symlink() or (hasattr(p,'is_junction') and p.is_junction()):
                    extra.append(p.relative_to(root).as_posix())
                    dirs.remove(name)
            for name in files:
                p=Path(parent)/name
                rel=p.relative_to(root).as_posix()
                if p.is_symlink() or rel not in FROZEN['hashes']:
                    extra.append(rel)
    initial=FROZEN['initial_workflow']
    comp,comp_unique=unique_rows(workflow.get('components'),'component_key')
    component_ok=comp_unique and set(comp)=={x['component_key'] for x in initial['components']} and all(all((dt(obj(comp.get(x['component_key'])).get(k))==dt(x[k]) if k=='last_changed_at_utc' else obj(comp.get(x['component_key'])).get(k)==x[k]) for k in ('scope_version','last_changed_at_utc','local_lookup_key')) for x in initial['components'])
    identity_ok=all((dt(obj(workflow.get('workspace_meta')).get(k))==dt(initial['workspace_meta'][k]) if k=='run_time_utc' else obj(workflow.get('workspace_meta')).get(k)==initial['workspace_meta'][k]) for k in ('release_id','project_label','run_time_utc','network_policy','public_synthetic_state'))
    put('scope_integrity',[not changed,not extra,workflow.get('phase_order')==initial['phase_order'] and component_ok and identity_ok and workflow.get('mutation_policy')==initial['mutation_policy']])

    decision=obj(update.get('phase_decision'))
    cap_phase=obj(capture.get('phase_status_capture'))
    actual_order=phase.get('current_phase_order')
    adjacent=isinstance(actual_order,int) and not isinstance(actual_order,bool) and actual_order-initial['phase_status']['current_phase_order']==1
    paths=[]
    for x in rows(update.get('updated_artifacts')):
        x=obj(x).get('path') if isinstance(x,dict) else x
        if isinstance(x,str): paths.append(refnorm(x))
    capture_checks,cu=unique_rows(capture.get('validation_category_capture'),'local_check_key')
    capture_cache,lu=unique_rows(capture.get('lookup_cache_capture'),'lookup_key')
    cap_audit=obj(capture.get('audit_capture'))
    audit_updates=rows(update.get('audit_history_updates'))
    audit_ref=cap_audit.get('audit_ref')
    audit_timestamp=dt(cap_audit.get('recorded_at_utc'))
    # Audit linkage is relational, so alternate unique identifiers are accepted.
    entry_match=re.search(r'^###\s+'+re.escape(str(audit_ref))+r'(?:\s|$)(.*?)(?=^###\s|\Z)',appended,re.M|re.S) if audit_ref else None
    entry_times=[dt(t) for t in re.findall(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)',entry_match.group(0))] if entry_match else []
    audit_link=bool(audit_ref and entry_match and audit_timestamp and audit_timestamp in entry_times and any(obj(a).get('audit_ref')==audit_ref and dt(obj(a).get('recorded_at_utc'))==audit_timestamp for a in audit_updates))
    put('record_sync',[
        bool(phase) and decision.get('from_phase')==facts['initial_phase'] and decision.get('to_phase')==phase.get('current_phase') and decision.get('advanced_adjacent_phase_only') is adjacent,
        len(paths)==len(set(paths)) and set(paths)=={refnorm(x) for x in FROZEN['mutable']},
        bool(phase) and all(k in cap_phase and k in phase and cap_phase[k]==phase[k] for k in ('current_phase','state_phase_status','completion_claimed','candidate_next_phase')) and dt(capture.get('captured_at_utc')) and state_time and state_time<=dt(capture.get('captured_at_utc'))<=limit,
        checks_unique and cu and set(capture_checks)==set(checks) and all(norm(capture_checks[k].get('category'))==norm(checks[k].get('category')) for k in checks),
        unique and lu and set(capture_cache)==set(active) and all(all(capture_cache[k].get(f)==active[k].get(f) for f in ('scope_version','cache_value','status')) and refnorm(capture_cache[k].get('source_record_ref'))==refnorm(active[k].get('source_record_ref')) for k in active),
        audit_link
    ])


    # This case has a genuine unresolved evidence dependency. Repairable work
    # and a correct decision to hold are independent business obligations.
    appended_unique=units['audit_preservation'][1]
    scores['audit_preservation']=(0.5+0.5*appended_unique) if preserved else 0.0
    identity_preserved=units['scope_integrity'][2]
    scores['scope_integrity']=(6+int(not extra)+int(identity_preserved))/8 if not changed else 0.0
    critical_refs={P+'config/release_scope.json',P+'config/no_network_policy.txt',P+'state/local_lookup_records.json',P+'logs/local_validation_runs.jsonl',P+'runbooks/phase_gate_policy.md',P+'runbooks/local_validation_policy.md',P+'runbooks/audit_and_status_sync.md'}
    trusted_basis=not(set(changed)&critical_refs) and identity_preserved
    resolved={'validated','synced','reconciled','locally_reconciled','current','ready','resolved','repaired'}
    waiting={'awaiting_validation','pending_validation','awaiting_revalidation','pending_revalidation','stale','blocked'}
    timestamp_pattern=r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)'
    audit_timing=[]
    refresh_stamps=[dt(x.get('recorded_at_utc')) for x,good in zip(new,good_refresh) if good]
    for entry in re.finditer(r'^###\s+(\S+).*?(?=^###\s|\Z)',appended,re.M|re.S):
        body=entry.group(0)
        labeled=re.findall(r'(?:recorded_at_utc|timestamp_utc|recorded_at|记录时间|记账时间|时间)[`*\s]*[:：][`*\s]*('+timestamp_pattern+r')',body,re.I)
        stamps={dt(x) for x in (labeled or re.findall(timestamp_pattern,body))}
        stamp=next(iter(stamps)) if len(stamps)==1 else None
        good=bool(stamp and snapshot and refresh_stamps and snapshot<=stamp<=limit and min(refresh_stamps)<=stamp)
        audit_timing.append({'audit_ref':entry.group(1),'valid_recording_time':good})
    audit_backed=bool(preserved and appended_unique and audit_timing and all(x['valid_recording_time'] for x in audit_timing))
    required_bindings=FROZEN['current_bindings']
    receipt_by_ref={'logs/local_validation_runs.jsonl#'+x['line_ref']:x for x in FROZEN['eligible_receipts']}
    dependency={}
    for key,requirement in FROZEN['validation_requirements'].items():
        check=obj(checks.get(key));receipt=obj(receipt_by_ref.get(refnorm(check.get('receipt_ref'))))
        wanted={k:required_bindings[k] for k in requirement['input_lookup_keys']}
        source_ok=bool(receipt and receipt.get('local_check_key')==key and check.get('tested_bindings')==receipt.get('input_bindings') and dt(check.get('observed_at_utc'))==dt(receipt.get('timestamp_utc')))
        target_ok=check.get('required_bindings')==wanted
        receipt_current=bool(source_ok and receipt.get('status')=='passed' and receipt.get('input_bindings')==wanted)
        category='passed' if receipt_current else 'stale'
        classified=source_ok and target_ok and norm(check.get('category'))==category and check.get('blocks_current_gate') is (not receipt_current)
        dependency[key]={'source_matches_receipt':source_ok,'required_bindings_current':target_ok,'receipt_covers_current_inputs':receipt_current,'classification_supported':classified,'source_ref':refnorm(check.get('receipt_ref'))}
    bundle=dependency['bundle_integrity'];cli_dependency=dependency['cli_component_lock']
    retained_components=comp_unique and all(norm(obj(comp.get(k)).get('state')) in resolved|{'frozen'} for k in ('cli_core','shell_completion'))
    old_cli=next(x for x in FROZEN['initial_json'][V]['checks'] if x['local_check_key']=='cli_component_lock')
    retained_cli=bool(cli_dependency['classification_supported'] and dt(obj(checks.get('cli_component_lock')).get('observed_at_utc'))==dt(old_cli['observed_at_utc']) and retained_components)
    # Four old snapshot units: 4 points. Receipt fidelity, full dependency tuple
    # and unaffected checks: 2 points each. A fresh classification can be blocked.
    workspace_freshness=list(units['validation_freshness'])
    put('validation_freshness',workspace_freshness+[bundle['source_matches_receipt']]*2+[bundle['required_bindings_current']]*2+[retained_cli]*2)
    board_refs={refnorm(x).split('#')[0] for x in evidence_refs(checks.get('board_state_alignment'))|evidence_refs(meta)}
    truth={
        'scope_manifest_readable':identity_preserved and P+'config/release_scope.json' not in changed,
        'cli_component_lock':cli_bound and completion_bound and retained_cli,
        'docs_bundle_lookup_bound':docs_bound,
        'manifest_dependency_alignment':manifest_bound,
        'board_state_alignment':B not in errors and W not in errors and {'release_board.md','state/workflow_state.json'}<=board_refs,
        'validation_snapshot_freshness':all(workspace_freshness),
        'audit_after_validation':audit_backed,
        'archived_board_scope_guard':identity_preserved and P+'config/release_scope.json' not in changed,
        'bundle_integrity':bundle['classification_supported'] and not FROZEN['receipt_truth']['bundle_integrity'],
    }
    category_weights={'scope_manifest_readable':0.5,'cli_component_lock':0.5,'docs_bundle_lookup_bound':1,'manifest_dependency_alignment':2,'board_state_alignment':1,'validation_snapshot_freshness':1,'audit_after_validation':1,'archived_board_scope_guard':0.5,'bundle_integrity':2}
    category_ok={}
    for key in facts['checks']:
        check=obj(checks.get(key))
        accepted={'stale'} if key=='bundle_integrity' else ({'passed','not_applicable'} if key=='archived_board_scope_guard' else {'passed'})
        category_ok[key]=bool(truth[key] and norm(check.get('category')) in accepted and check.get('blocks_current_gate') is (key=='bundle_integrity'))
    shape=checks_unique and set(checks)==set(facts['checks'])
    put('validation_categories',list(category_ok.values())+[shape])
    scores['validation_categories']=(sum(category_weights[k]*category_ok[k] for k in category_weights)+0.5*shape)/10
    blocking={k for k,c in checks.items() if c.get('blocks_current_gate') is True}
    local_gate=obj(gates.get('local_validation'))
    expected_blockers=set(facts['required_blocking_checks'])
    def keyset(value):
        return set(value) if isinstance(value,list) and all(isinstance(x,str) for x in value) else set()
    phase_base=bool(phase.get('current_phase')==facts['initial_phase'] and phase.get('current_phase_order')==3 and norm(phase.get('state_phase_status')) in {'blocked','in_progress','on_hold','waiting_for_evidence','awaiting_evidence'} and phase.get('completion_claimed') is False and phase.get('skip_ahead_allowed') is False and phase.get('candidate_next_phase')==facts['target_phase'])
    blocker_decision=bool(trusted_basis and shape and all(category_ok.values()) and bundle['classification_supported'] and not bundle['receipt_covers_current_inputs'] and blocking==expected_blockers and keyset(local_gate.get('blocking_check_keys'))==expected_blockers and norm(local_gate.get('gate_state')) in {'blocked','blocked_pending_local_repair','blocked_pending_evidence','blocked_pending_validation','awaiting_evidence','pending_evidence','blocked_pending_dependency'})
    update_decision=bool(decision.get('from_phase')==facts['initial_phase'] and decision.get('to_phase')==facts['initial_phase'] and decision.get('advanced_adjacent_phase_only') is False and keyset(decision.get('blocking_check_keys'))==expected_blockers and isinstance(decision.get('blocked_or_carry_forward_reason'),str) and decision['blocked_or_carry_forward_reason'].strip())
    future_closed=bool(norm(obj(gates.get('repair_alignment')).get('gate_state')) in unopened and norm(obj(gates.get('handoff_ready')).get('gate_state')) in unopened and all(phase.get(k) is not True for k in ('handoff_claimed','handoff_ready_claimed','release_wrap_claimed')) and comp_unique and norm(obj(comp.get('docs_bundle')).get('state')) in resolved and norm(obj(comp.get('release_manifest')).get('state')) in waiting)
    put('phase_transition',[phase_base,blocker_decision,update_decision,future_closed])
    scores['phase_transition']=(4*phase_base+6*blocker_decision+4*update_decision+4*future_closed)/18 if phase_base else 0.0
    admission_diagnostics={'trusted_basis':trusted_basis,'lookup_shape_valid':lookup_shape,'lookup_bindings_valid':scores['lookup_binding']==1,'workspace_refresh_units':workspace_freshness,'supported_categories':truth,'category_results':category_ok,'category_point_weights':category_weights,'dependency_checks':dependency,'frozen_receipt_truth':FROZEN['receipt_truth'],'audit_backed':audit_backed,'audit_timing':audit_timing,'deterministic_admission_ready':False,'required_blocking_checks':facts['required_blocking_checks'],'safe_hold':all(units['phase_transition']),'phase_decision_point_weights':[4,6,4,4],'board_meaning_requires_judge':True}

    scores['overall_score']=sum(WEIGHTS[k]*scores[k] for k in WEIGHTS)/60
    diagnostics={'read_errors':errors,'check_units':units,'changed_protected_files':changed,'unexpected_business_files':extra,'audit_appended_text':appended,'frozen_public_facts':facts,'valid_local_records':expected,'public_record_candidates':FROZEN['public_record_candidates'],'current_bindings':FROZEN['current_bindings'],'validation_requirements':FROZEN['validation_requirements'],'audit_historical_records_preserved':preserved,'audit_preservation_method':'Compare each historical record content and order; ignore wrapper headings and HTML comments.','admission_conditions':admission_diagnostics,'frozen_event_log':FROZEN['event_log'],
                 'scope':'Final file state only; no inference of actual tool ordering or network absence.',
                 'evidence_role':'grader_generated_after_execution','truncated':False}
    evidence=root/'evaluator_evidence/task007/rule_facts.json'
    for p in (evidence,*evidence.parents):
        if p==root: break
        if p.is_symlink() or (hasattr(p,'is_junction') and p.is_junction()):
            raise EvaluationError('Unsafe grader evidence destination')
    if not evidence.resolve().is_relative_to(root): raise EvaluationError('Evidence escaped workspace')
    evidence.parent.mkdir(parents=True,exist_ok=True)
    # The audit is already a required candidate file. Avoid duplicating its body
    # in frozen facts and fit the framework's declared-file evidence budget.
    exported={k:v for k,v in diagnostics.items() if k!='audit_appended_text'}
    exported['audit_candidate_path']=A
    evidence.write_text(json.dumps(exported,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    scores['diagnostics']=diagnostics
    return scores
```

## LLM Judge Rubric

只使用实际候选、公开业务规则、冻结来源事实及可用的公开轨迹/最终回复。每项固定四个二值单元，逐一列 pass/fail、分子/4 和文件字段或公开事件引用；每单元全部条件成立才计 1，不根据整体印象或模型身份加减分。五个 key 必须全部且仅出现一次。允许业务等价措辞、跨文件解释、不同排版和编号，不要求复述参考答案；只计算候选新增/实质更新的解释，不能把原输入提示归功于候选。

诊断布尔值不是高于业务规则的判据。发现标题、位置或收集方式导致诊断与实际事实冲突时，明确指出评测错误，不能把它传播成“准入错误”“虚假完成”。缺失候选单元失败；采集或评分故障按不可判定处理。相同失实声明重复出现只计一次，不凭 network_used=false 推断全过程未联网。工具命令与隐藏推理不是交付解释；公开助手说明、最终回复和任一交付中的新增因果说明均可采用，不限定解释的文件位置。

### Criterion 1: 看板各入口与实际状态对齐 (key: board_reconciliation, weight: 6)

四个单元：①醒目当前 phase/status 与实际 workflow 一致，历史 ready/handoff 不混作当前；②tracker 的已完成/当前/未进入分工与 workflow 一致；③阻塞面板准确反映实际 validation/gate 中的分类及阻塞集合，不同时宣称全清；④artifact notes 区分 cache 当前值与组件验证状态，docs/manifest/CLI/completion、snapshot 与审计说明相互一致，旧观察有历史标识。只评信息一致性，不在此重复判断业务决策是否正确；删掉整个信息类别不自动通过。

**Score 1.0**: 恰有 4 个单元成立。

**Score 0.75**: 恰有 3 个单元成立。

**Score 0.5**: 恰有 2 个单元成立。

**Score 0.25**: 恰有 1 个单元成立。

**Score 0.0**: 恰有 0 个单元成立。

### Criterion 2: 修复和停止决定有完整依据 (key: repair_rationale, weight: 14)

四个单元：①解释 docs 与 manifest 的适用来源及完整依赖，说明为何旧版本/错绑定、隔离/网络和时点外材料不能用于当前准入；允许按原因归组，不要求枚举每个 ID；②解释原 snapshot/通过凭据的覆盖缺口，指出较新时间和 passed 不能替代输入版本匹配，以及 workspace refresh 与新测试回执的区别；③解释哪些影响局限于 docs→manifest→bundle 校验、哪些 CLI/completion 结果可沿用，且不把范围外插件或历史超时当本轮新阻塞；④结合实际缺口说明为何可完成的本地修复仍要做、为何当前 gate 必须等待有效凭据，不用“安全起见全部不动”或“已修完所以放行”代替判断。允许诚实说明某修复未完成而仍给解释分；解释与行为正确性分别评价。接受可见候选说明任意载体，无须报告重复或显式链接，不能由 Judge 根据原输入补出缺失的因果解释。

**Score 1.0**: 恰有 4 个单元成立。

**Score 0.75**: 恰有 3 个单元成立。

**Score 0.5**: 恰有 2 个单元成立。

**Score 0.25**: 恰有 1 个单元成立。

**Score 0.0**: 恰有 0 个单元成立。

### Criterion 3: 本轮审计可追溯 (key: audit_traceability, weight: 6)

四个单元：①新增记录引用可定位到实际本地 records/log/状态对象；②说明本轮缓存、分类和阶段决定的实际处理及保留阻塞，与写回结果相符，不只是 category 清单；③新增审计与实际 refresh 相互关联，记账不早于引用刷新且不晚于决策时点，同一时点可用引用和文字说明先后，不假造测试；④解释旧过早 handoff 记录只是历史警告，当前决定基于本轮证据，并保留实际结论范围。可沿明确引用核对解释。只评新记录；历史保留单独评分，不因旧历史失败把新审计一律归零。

**Score 1.0**: 恰有 4 个单元成立。

**Score 0.75**: 恰有 3 个单元成立。

**Score 0.5**: 恰有 2 个单元成立。

**Score 0.25**: 恰有 1 个单元成立。

**Score 0.0**: 恰有 0 个单元成立。

### Criterion 4: 剩余依赖能被下一位维护者接手 (key: followup_actionability, weight: 8)

四个单元：①明确负责补凭据及复核准入的角色，允许等义角色名称；②具体指出需要补/核验哪个检查、其当前完整输入组合，不只写“重新验证”；③说明凭据到位后须核对 scope、来源、时点和输入绑定，再同步分类、组件、阻塞清单并判断相邻 gate，不能把拿到任意 passed 当解除条件；④把本地可处理跟进与真实 CI/发布/通知的授权边界区分，不建议偷用截止之后的材料或本轮继续越级。以实际未完成范围为准，准确修复后仍需后续 gate 决策。对象和条件可跨新增说明表达，不按文风或长度评分。

**Score 1.0**: 恰有 4 个单元成立。

**Score 0.75**: 恰有 3 个单元成立。

**Score 0.5**: 恰有 2 个单元成立。

**Score 0.25**: 恰有 1 个单元成立。

**Score 0.0**: 恰有 0 个单元成立。

### Criterion 5: 验收与完成声明校准 (key: completion_calibration, weight: 6)

四个单元：①明确本地文件处理的实际完成范围，缺失或仍草稿未被称完成；②校验覆盖声明与当前文件和公开检查证据相称，区分已核对的来源/依赖关系、状态分类刷新和仍未获得的新测试，不把写入成功当内容验收；③明确业务阶段结果与未完成程度，错误推进者只有如实承认不合格而非声称合格才可能通过本单元，正确停留不等同工作失败；④明确本地快照和外部服务边界，不虚构 CI、registry、发布或通知回执。存在未澄清的相反声明则对应单元失败；准确引用历史错误不失败。声称已做特定检查须有公开回执/可观察证据支持；未声称的行为不作为额外分母，也不因缺轨迹推定联网。

**Score 1.0**: 恰有 4 个单元成立。

**Score 0.75**: 恰有 3 个单元成立。

**Score 0.5**: 恰有 2 个单元成立。

**Score 0.25**: 恰有 1 个单元成立。

**Score 0.0**: 恰有 0 个单元成立。

## Workspace Path

workspace/general_e2e/02_Office/task_007_release_phase_gate_progression

## Skills

## Env

## Warmup
