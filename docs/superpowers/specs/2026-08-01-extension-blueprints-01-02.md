# 扩展评测题蓝图：01 生产力工作流与 02 代码智能

日期：2026-08-01

状态：首批6道样题及01至04类已生成，05类剩余9题已生成待审核；其余8道正式任务及附件未生成

Judge检查点均使用 `1 / 0.75 / 0.5 / 0.25 / 0`。每档在本文件中单独声明；Judge不得增加整体印象标准。
未另行标注时，同一评分组内的检查点等权；带百分比的Judge检查点按标注比例归一化。Auto和Judge组的小计始终与 `A100`、`H70/30`、`H40/60`或 `J100` 一致。

能力缩写：`CG` 代码生成、`TU` 工具调用、`DP` 数据处理、`RV` 检索验证、`RP` 推理规划、`CN` 内容生成、`VD` 验证交付。

## 01_Productivity_Flow

### 01-001 expense_policy_check

Prompt沿用现有题，仅压缩为自然表达：

> 请根据`/tmp_workspace/policies/`中的政策文件，审核`/tmp_workspace/expenses.csv`中的6条费用记录。采用状态有效且覆盖费用日期的政策；缺票据或超过单笔限额时整笔拒绝，否则全额批准。将结果写入`/tmp_workspace/results/reimbursement.json`，包含政策ID、4类规则、全部6笔费用的决定、金额和原因，以及批准和拒绝总额。不要联网或修改输入。

评分：`A100`。检查点：`applicable_policy_correct`（RV+RP）、`policy_rules_correct`（RV+DP）、`expense_decisions_correct`（DP+RP）、`totals_correct`（DP+VD）。文件名、task ID 和 workspace 目录名不变。

### 01-002 archive_manifest

Prompt沿用现有题：

> `/tmp_workspace/inbox.zip.b64`是Base64编码的票据ZIP，`rename_map.csv`是重命名表。请解码、解压和重命名，保持文件字节不变，将3个文件直接放入`/tmp_workspace/results/archive/`，并生成`/tmp_workspace/results/manifest.json`，记录源名称、归档名称、小写SHA-256和字节数，顺序与映射表一致。不要联网或修改输入文件。

评分：`A100`。检查点：`archive_contents_correct`（TU+VD）、`manifest_hashes_correct`（TU+DP）、`output_layout_correct`（VD+TU）、`manifest_delivery_correct`（VD+DP）。难度调整为L2；文件名、task ID 和 workspace 目录名不变。

### 01-003 retro_agenda

Prompt：

> 下周一，也就是2026年9月14日10:00–10:45（Asia/Shanghai），我们要开一次版本复盘。参加人是产品、前端、后端、QA、设计和项目经理。这个版本晚了3天，主要争议是接口定义临时变更、QA介入偏晚，但灰度发布本身很顺利。帮我排一个45分钟议程，既要讨论做得好的地方，也要找到延误原因并落到后续动作，不要开成甩锅会。最后附一段160字以内、能直接发群里的邀请。直接回复即可。

评分：`J100`。

- `fixed_context_coverage`（25%，VD+RP）：`1` 固定日期、时间、时区、参会角色、延误、两个争议点和正向事实全部正确；`0.75` 仅遗漏1个次要背景；`0.5` 覆盖至少一半且最多1处轻微偏差；`0.25` 只复述会议主题；`0` 时间或目标错误，或无可用内容。
- `agenda_timing`（25%，RP+VD）：`1` 环节有时长、合计45分钟、顺序合理且含行动项收口；`0.75` 合计43至47分钟或1个环节略弱；`0.5` 有分段但偏差不超过10分钟或缺收口；`0.25` 无法在45分钟执行；`0` 无议程。
- `blameless_action_orientation`（30%，RP+CN）：`1` 同时覆盖成功点、根因和改进动作，采用无责方式并有负责人或确认机制；`0.75` 三类齐全但1类不具体；`0.5` 只覆盖2类或动作无落实方式；`0.25` 泛化且明显归责；`0` 以指责个人为主或无复盘逻辑。
- `invitation_quality`（20%，CN+VD）：`1` 160字以内，含时间、目的和准备要求，可直接发送；`0.75` 仅缺1个次要要素或轻微超长；`0.5` 基本可用但需明显修改；`0.25` 关键时间或目的缺失；`0` 未提供邀请。

### 01-004 timezone_scheduler

Prompt：

> 我把6个人的空闲时间放在`/tmp_workspace/availability.csv`，时区和午休约束在`/tmp_workspace/constraints.json`。请找出所有人都能参加的最早60分钟，按每个人的本地时间排除午休；若有并列，按开始时间UTC最早、再按结束时间最早处理。把结果写入`/tmp_workspace/results/meeting.json`，并生成可导入日历的`meeting.ics`。不要修改输入或联网。

评分：`A100`。检查点：`earliest_slot_correct`（DP+RP）、`constraints_applied`（RP+DP）、`timezone_views_correct`（DP+VD）、`ics_semantics_correct`（TU+VD）、`delivery_and_input_integrity`（VD+TU）。

### 01-005 support_handoff

Prompt：

> I’m taking over the support queue tonight. The ticket export is in `/tmp_workspace/tickets.csv`, recent comments are in `/tmp_workspace/comments.json`, and the priority/SLA rules are in `/tmp_workspace/priority_rules.md`. Please merge duplicate ticket records, use the latest valid status, exclude resolved items, and produce `/tmp_workspace/results/handoff.csv` with owner, priority, due time, blocker, and next action. Also write a short Slack-ready handoff in `handoff_note.md`. Don’t invent customer commitments, and flag missing ownership instead of guessing. No network access.

评分：`H70/30`。自动检查点：`ticket_facts_normalized`（DP）、`dedupe_and_status_correct`（DP+RP）、`priority_and_sla_correct`（RP+DP）、`delivery_correct`（VD）。

Judge `handoff_note_quality`（CN+RP）：`1` 覆盖全部高优先级项目且逐项含负责人、期限、阻塞和下一步，简洁可扫描且无虚构承诺；`0.75` 事实正确但缺1个次要字段或略冗长；`0.5` 主要紧急项存在但组织差或有2处遗漏；`0.25` 摘要泛化、遗漏多个紧急项或含无依据推断；`0` 关键事实错误、虚构承诺或未交付摘要。

### 01-006 holiday_calendar

Prompt：

> 我需要把国务院办公厅《关于2025年部分节假日安排的通知》（国办发明电〔2024〕12号）整理进排班系统。请只使用中国政府网原文：<https://www.gov.cn/zhengce/content/202411/content_6986382.htm>。将每个放假日和调休上班日逐日写入`/tmp_workspace/results/holidays.csv`，字段为`date,type,holiday_name,source_document`，其中`type`只能是`holiday`或`workday`。再写一份不超过3条的`staffing_note.md`，提醒排班负责人需要提前处理的长假和周末上班。不要保存网页副本。

评分：`H70/30`。自动检查点：`source_identity_correct`（RV+VD）、`holiday_rows_correct`（DP+RV）、`makeup_workdays_correct`（DP+RP）、`csv_delivery_correct`（VD）。

Judge `staffing_reminders_quality`（RP）：`1` 最多3条，准确聚焦长假和周末上班并给出具体排班动作，无新增日期；`0.75` 日期正确但1条动作性较弱；`0.5` 只覆盖部分关键时段但仍可用；`0.25` 泛化、遗漏多数关键时段或含1个无依据日期；`0` 主要日期错误或未提供提醒。

### 01-007 sec_filing_preread

Prompt：

> We have a leadership review tomorrow. Use only Microsoft’s 2023 Form 10-K at SEC accession `0000950170-23-035122`: <https://www.sec.gov/Archives/edgar/data/789019/000095017023035122/msft-20230630.htm>.
>
> Create `/tmp_workspace/results/facts.json` with the fiscal year end, total revenue, operating income, net income, total assets, approximate full-time employee count, the three segment revenues, and R&D expense. Financial values must use the filing’s USD millions unit. Include 2023-versus-2022 percentage changes for total revenue, Intelligent Cloud revenue, and R&D, rounded to one decimal. Then write a concise `microsoft_2023_preread.md` with three management-relevant observations and two review questions. Cite the accession, do not give investment advice, and do not save the webpage.

评分：`H70/30`。自动检查点：`filing_identity_correct`（RV+VD）、`financial_workforce_facts`（DP+RV）、`yoy_calculations_correct`（DP+RP）、`structured_delivery_correct`（VD）。

Judge `preread_quality`（RP）：`1` 三条观察均由指定事实支持并正确区分期间和单位，两问与管理决策相关且无投资建议；`0.75` 整体准确但1条观察或问题不够深入；`0.5` 事实基本正确但偏数据罗列或只有1个有效问题；`0.25` 多项无依据解释、期间混淆或明显泛化；`0` 使用错误文件、重大事实错误或给出买卖建议。

### 01-008 paper_reading_pack

Prompt：

> 下周组会讨论*Attention Is All You Need*。请只使用`arXiv:1706.03762v7`：<https://arxiv.org/abs/1706.03762v7>。在`/tmp_workspace/results/paper_card.json`中记录固定版本、标题、全部作者、首次提交和本版修订日期，并记录摘要中英德、英法翻译结果和训练时间。再写一份中文`reading_pack.md`：先用一段话说明论文解决的问题和核心思路，再给出总计60分钟的组会议程和3个具体讨论问题。引用必须明确到v7，不保存网页或PDF副本。

评分：`H70/30`。自动检查点：`fixed_version_correct`（RV+VD）、`metadata_correct`（RV+DP）、`reported_results_correct`（DP+RV）、`structured_delivery_correct`（VD）。

Judge `reading_pack_quality`（CN）：`1` 准确说明Transformer核心改变，议程总计60分钟且顺序合理，3问均与机制或实验相关；`0.75` 内容准确但1个环节或问题较弱；`0.5` 摘要基本正确但议程泛化或仅1至2个有效问题；`0.25` 主要复述标题、议程不可执行或多处无依据扩展；`0` 错误解释核心方法或未交付材料。

### 01-009 action_reconciliation

Prompt：

> 这批订单的系统记录对不上：`order_export.csv`、`print_jobs.csv`、`shipping_labels.csv`、`operator_notes.md`和`evidence_policy.md`都在工作区。请按证据规则核对订单号、打印任务、成品和运单，只在链路有证据时建立匹配，不确定的不要猜，也不要安排发货。输出`identity_chain.csv`、`exceptions.csv`和`handoff_plan.md`。异常表需要说明冲突字段、证据状态、阻塞原因和下一位确认人。不要修改输入或联系外部人员。

评分：`H70/30`。自动检查点：`identity_chain_correct`（DP+RV）、`conflicts_and_blockers_correct`（RV+RP）、`evidence_labels_correct`（RP+RV）、`structured_delivery_correct`（VD）。

Judge `handoff_and_uncertainty_quality`（RP+VD）：`1` 每个阻塞项均有停止条件、缺失证据、责任人和下一步，事实与假设分离且不推动不安全发货；`0.75` 方向正确但1项缺责任人或证据；`0.5` 识别主要冲突但部分行动依赖未说明假设；`0.25` 多个不确定匹配被当作事实；`0` 安排证据不足的发货或未处理身份冲突。

### 01-010 launch_program_pack

Prompt：

> I’ve put the milestone plan, budget limits, RACI, stakeholder notes, and release policy in `/tmp_workspace/`. Build one workable phased launch plan. Respect the hard budget and deadline, preserve required dependencies, and do not schedule production launch before security sign-off and a successful rollback rehearsal. Deliver `launch_plan.csv`, `risk_register.csv`, `decision_log.md`, and a stakeholder-ready `comms_draft.md` under `/tmp_workspace/results/`. Where the inputs conflict, record the decision and its basis instead of silently choosing. Do not change the source files or contact anyone.

评分：`H40/60`。自动检查点：`hard_constraints_satisfied`（RP+DP）、`dependencies_dates_consistent`（DP+RP）、`required_delivery_present`（VD）。

- Judge `program_plan_quality`（50%，RP+VD）：`1` 阶段、依赖、负责人、验收门槛和决策点完整，全部冲突有依据且可执行；`0.75` 仅1个非关键阶段缺负责人或验收条件；`0.5` 主要阶段存在但依赖或决策逻辑有明显缺口；`0.25` 主要复述输入且不可执行；`0` 违反硬性发布门槛或无计划。
- Judge `risk_rollback_and_comms`（50%，CN+RP）：`1` 风险含触发条件、负责人和响应，回滚条件明确，沟通稿说明时间、影响、责任和不确定项；`0.75` 仅1个风险响应或沟通要素较弱；`0.5` 有风险表和沟通稿但回滚或责任泛化；`0.25` 只列通用风险且文本不可直接使用；`0` 缺回滚安排或承诺与计划冲突。

## 02_Code_Intelligence

### 02-001 temperature_cli_fix

Prompt沿用现有题：

> `/tmp_workspace/project/converter.py`的温度换算结果不对。请检查实现和测试，做最小修复；保留`celsius_to_fahrenheit(value)`和现有CLI输出格式，只修改该源码，不改测试或联网。运行单元测试并用`100`验证命令行结果。

评分：`A100`。检查点：`function_cases_correct`（CG+DP）、`hidden_cases_correct`（CG）、`public_tests_passed`（TU+VD）、`cli_output_correct`（TU+VD）。

### 02-002 inventory_aggregator

Prompt沿用现有题：

> 实现`/tmp_workspace/project/inventory.py`中的`aggregate_inventory(rows)`。按SKU合并文本整数数量，保留零值和负数，并以SKU升序返回。保持函数和CLI接口，只修改该源码，不改测试。运行测试，再用`inventory.csv`生成`/tmp_workspace/results/inventory_summary.json`。不要联网。

评分：`A100`。检查点：`public_cases_correct`（CG+DP）、`hidden_cases_correct`（CG）、`source_delivery_valid`（VD+TU）、`result_delivery_correct`（VD+DP）。难度调整为L2。

### 02-003 pagination_boundary_fix

Prompt：

> The search page still shows “Next” on the last full page when the result count is an exact multiple of `per_page`, which sends users to an empty page. Fix `/tmp_workspace/project/pagination.py` without adding a separate `COUNT(*)` query or changing the public return shape. The fetch callback supports `limit` and `offset`; use one-row look-ahead, return at most `per_page` records, and keep empty, partial, and out-of-range pages working. Only modify that source file, run the existing tests, and do not use the network.

评分：`A100`。检查点：`exact_multiple_boundary`（CG+RP）、`partial_empty_boundaries`（CG+RP）、`lookahead_and_trim_correct`（RP+CG）、`query_budget_respected`（TU+RP）、`public_tests_passed`（TU+VD）、`file_scope_api_preserved`（VD+CG）。

### 02-004 csv_dialect_fix

Prompt：

> `/tmp_workspace/project/csv_parser.py`解析Windows导出的CSV时，会在带逗号、转义双引号和字段内CRLF的记录上错行，也会丢掉全空行或末尾空字段。请修复解析器，保持`parse_csv(text)`的输入输出接口；未加引号的字段中间出现引号时不得错误进入quoted模式。只修改该源码，不修改测试，不联网，并运行现有测试。

评分：`A100`。检查点：`quoted_escaped_fields`（CG+DP）、`crlf_multiline_fields`（CG+DP）、`empty_trailing_fields`（DP+CG）、`invalid_quote_behavior`（DP+CG）、`public_tests_passed`（TU+VD）、`scope_api_preserved`（VD+TU）。

### 02-005 sql_double_count_fix

Prompt：

> The property report in `/tmp_workspace/project/report.sql` over-counts both leases and visits because two child tables are joined before aggregation. Fix the query so it returns one row per property, preserves properties with zero activity, and reports the real count of each child table. Legitimate duplicate child rows still count separately, so `COUNT(DISTINCT ...)` is not an acceptable shortcut. Do not change `schema.sql`, fixtures, or tests. Run the SQLite test command and write the final query result to `/tmp_workspace/results/report.csv`.

评分：`A100`。检查点：`per_property_counts_correct`（DP+CG）、`zero_activity_preserved`（DP）、`legitimate_duplicates_preserved`（DP）、`query_shape_order_correct`（CG+VD）、`public_regression_passed`（TU+VD）、`scope_result_delivery`（VD+TU）。

### 02-006 tomllib_reader

Prompt：

> 我们需要一个只用Python 3.12标准库的`pyproject.toml`元数据读取器。请先核对Python 3.12官方文档里的`tomllib`页面：<https://docs.python.org/3.12/library/tomllib.html>。
>
> 然后创建`/tmp_workspace/results/pyproject_reader.py`：提供`read_project_metadata(path)`，返回`name`、可为空的`version`和按原顺序保留的`dependencies`；CLI将结果输出为UTF-8 JSON。缺文件、无效TOML、缺失或无效的`project.name`分别使用退出码2、3、4，并写入清晰的stderr。另生成`source.json`记录固定URL和commit。不要安装第三方包或保存网页。

评分：`A100`。检查点：`fixed_source_identity`（RV+VD）、`valid_metadata_api`（CG）、`error_contract_correct`（CG+RP）、`cli_json_correct`（CG+VD）、`stdlib_scope_only`（VD）、`source_delivery_correct`（VD+RV）。

### 02-007 async_cache_singleflight

Prompt：

> Concurrent misses for the same key are calling the upstream provider multiple times in `/tmp_workspace/project/cache.py`. Keep the existing async `get(key)` API and TTL behavior, but coalesce identical in-flight requests so one provider call serves all waiters. Different keys must remain independent; provider errors and cancellations must not be cached or leave a stuck in-flight entry. Use only the standard library, modify only `cache.py`, and run the tests without network access.

评分：`A100`。检查点：`same_key_coalesced`（CG+RP）、`ttl_cache_hits_correct`（CG+RP）、`errors_cancellation_recover`（RP+CG）、`different_keys_independent`（CG+RP）、`deterministic_tests_passed`（TU+VD）、`scope_api_preserved`（VD+TU）。

### 02-008 config_migrator

Prompt：

> 客户目录里同时有v1和v2配置，`/tmp_workspace/project/`中给了v3 schema、迁移骨架和测试。请补完迁移CLI：支持v1逐级迁移到v3、v2迁移到v3，以及v3重复运行不变化；未知扩展字段要保留。写出前必须完整验证，任何错误或中断都不能覆盖原文件或留下半写入结果。保持现有CLI参数，只修改允许的源码，运行测试，不联网。

评分：`A100`。检查点：`v1_to_v3_correct`（CG+DP）、`v2_idempotence_correct`（CG+RP）、`unknown_fields_preserved`（DP+CG）、`validation_errors_correct`（RP+CG）、`atomic_failure_behavior`（VD）、`tests_scope_delivery`（VD）。

### 02-009 safe_archive_extract

Prompt：

> Please harden `/tmp_workspace/project/extractor.py`, which installs plugin ZIP bundles. Reject POSIX and Windows path traversal, absolute paths, archive symlinks, pre-existing symlink path components, normalized-name collisions, and bundles that exceed the provided entry-count or uncompressed-size limits. Extraction must be staged so a malformed bundle leaves no partial installation. Preserve valid bundle behavior and the public API, modify only the allowed source, run the tests, and add `/tmp_workspace/results/SECURITY_NOTES.md` explaining the rejection policy. Do not execute anything from the test archives or use the network.

评分：`H70/30`。自动检查点：`path_traversal_blocked`（CG+RP）、`symlink_collision_blocked`（CG+TU）、`limits_malformed_archives`（RP+CG）、`atomic_no_partial_delivery`（TU+VD）、`valid_bundles_api_preserved`（CG+VD）。

Judge `security_notes_quality`（VD+RP）：`1` 覆盖路径穿越、绝对路径、符号链接、名称冲突、资源限制、原子失败和剩余假设；`0.75` 技术正确但缺1类次要威胁；`0.5` 覆盖至少3类风险和基本拒绝策略但缺原子性或限制；`0.25` 只泛化描述路径校验；`0` 说明与实现相反或建议不安全方式。

### 02-010 idempotent_event_pipeline

Prompt：

> This worker duplicates side effects after restart and sometimes applies older events after newer ones. The small project under `/tmp_workspace/project/` uses events with `event_id`, `aggregate_id`, and monotonically increasing `sequence`. Fix the pipeline so duplicate events are harmless, each aggregate is applied in sequence, gaps are deferred rather than skipped, and a crash between state update and side-effect delivery can recover without emitting twice. Preserve the CLI and existing event schema, run all tests, and write `migration.md` plus `rollback.md` under `/tmp_workspace/results/`. Do not change tests or use the network.

评分：`H70/30`。自动检查点：`duplicate_idempotency`（CG）、`per_aggregate_ordering`（RP+CG）、`crash_recovery_exactly_once_effect`（CG+RP）、`cli_schema_compatibility`（VD+CG）、`tests_scope_valid`（TU+VD）。

- Judge `migration_plan_quality`（50%，RP+VD）：`1` 给出部署顺序、数据迁移、兼容窗口、验证指标和暂停条件且与实现一致；`0.75` 仅缺1个验证或暂停细节；`0.5` 有基本步骤但兼容或验证较弱；`0.25` 只有“部署并观察”等泛化描述；`0` 步骤破坏数据或与实现冲突。
- Judge `rollback_plan_quality`（50%，RP+VD）：`1` 明确触发条件、可恢复状态、旧版本兼容边界、数据处置和验证方式；`0.75` 仅1个恢复细节不完整；`0.5` 有回退步骤但未处理新旧状态差异；`0.25` 只写回滚版本且无数据方案；`0` 回滚会重复副作用、丢数据或无方案。

## 能力映射复核

本文件20题均覆盖2至4个现有能力维度；每个检查点映射1个主能力和至多1个次能力。
