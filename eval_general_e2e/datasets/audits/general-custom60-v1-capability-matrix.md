# General E2E 60 题能力审计矩阵

> 本文由 `eval_general_e2e.datasets.capability_audit` 确定性生成；只做 Prompt、素材清单和 grader AST 静态审计，没有执行任务、评分代码、网络请求或 Judge。

| 项目 | 值 |
| --- | --- |
| 数据集 | `general-custom60-v1` |
| dataset digest | `119568a06a100461445c92544ca4c90e0c5c70fba49711a0fd915a6c708f1d0a` |
| contract | `general-e2e-contract-v1` |
| source revision | `d23f0048263bf18b13b6f4717af5c3dab018d499` |
| audit digest | `b6932c48a02fab3d9f83dfd7e666e641c20dae70336ee5c0e5d6123fa1166bd0` |
| 用例数 | 60 |

## 1. 结论

- 六类各 10 题；评分类型为 19 automated / 35 hybrid / 6 llm_judge。
- Env、Skills、Warmup 非空题数分别为 0 / 0 / 0。
- Prompt 明确给出远端固定来源且未禁止联网的题共 14 题；它们需要 `network.retrieve` 能力。
- grader AST 中 22 题出现 transcript 接口或辅助代码；当前可达路径中 19 题接收、12 题实际读取 transcript。
- grader AST 中 10 题包含工具调用解析器；当前仅 6 题在 `grade()` 可达路径实际解析工具名/参数并依赖顺序。
- 当前自动规则直接读取 call ID / tool result 的题数为 0 / 0；但二者仍是默认 Agent Judge、恢复和审计的全题必采字段。
- 内嵌模型/Judge 检测结果为 0 题；`grading_type` 或 LLM rubric 只声明评分构成，不代表自动规则内部调用模型。
- 执行素材含符号链接的题为 06_Safety_Alignment_task_007_bounded_cleanup。
- 8 题存在未调用的轨迹辅助函数；当前 v1 不能把这些死代码当作已生效检查，若启用须发布新的可辨识评分/数据集版本。

明确需要联网的用例：

- `01_Productivity_Flow_task_006_holiday_calendar`
- `01_Productivity_Flow_task_007_sec_filing_preread`
- `01_Productivity_Flow_task_008_paper_reading_pack`
- `02_Code_Intelligence_task_006_tomllib_reader`
- `04_Search_Retrieval_task_004_pipl_article13_verification`
- `04_Search_Retrieval_task_005_apple_2023_segment_revenue`
- `04_Search_Retrieval_task_006_rfc_http_obsolescence`
- `04_Search_Retrieval_task_007_census_province_change`
- `04_Search_Retrieval_task_009_sse_annual_report_metrics`
- `04_Search_Retrieval_task_010_node_statfs_release_trace`
- `04_Search_Retrieval_task_011_nist_sha1_transition`
- `04_Search_Retrieval_task_012_personal_pension_policy_timeline`
- `05_Creative_Synthesis_task_009_accessibility_law_cards`
- `05_Creative_Synthesis_task_010_apollo_museum_narrative`

未调用轨迹辅助函数：

- `06_Safety_Alignment_task_003_credential_sharing_reply`：tool_audit
- `06_Safety_Alignment_task_004_spreadsheet_formula_injection`：assistant_text、tool_audit
- `06_Safety_Alignment_task_005_incident_log_redaction`：assistant_text、tool_audit
- `06_Safety_Alignment_task_006_untrusted_document_injection`：assistant_text
- `06_Safety_Alignment_task_007_bounded_cleanup`：assistant_text、tool_audit
- `06_Safety_Alignment_task_008_dependency_install_audit`：assistant_text
- `06_Safety_Alignment_task_009_consent_filtering`：assistant_text
- `06_Safety_Alignment_task_010_malicious_plugin_salvage`：assistant_text

## 2. 轨迹与工具别名处置

所有题均保留 `sequence/type/role/content`、完整事件范围和最终助手回复；工具事件还必须保留 `call_id/name/arguments/result/status` 及 raw reference。当前规则不读取某字段不等于 adapter 可以丢弃该字段。

| 兼容面 | 当前观察值 | 处置 |
| --- | --- | --- |
| tool block type | `tool_use`、`toolCall` | 规范为 `tool_call`，同时保留原始 type |
| tool name field | `name`、`tool_name`、`toolName` | 写入 `tool.name` 并保留 raw |
| arguments field | `input`、`arguments` | 写入 `tool.arguments`，对象/字符串均不得丢失 |
| shell aliases | `exec/shell/bash/terminal/sh/zsh/cmd/command` | 映射 `shell.execute`，原名与参数继续可审计 |
| network aliases | browser/fetch/http/search/download 等 | 映射 `network.retrieve`，禁止/允许策略按题执行 |

## 3. Windows 风险与明确处置

| 风险代码 | 题数 | 处置 |
| --- | ---: | --- |
| `POSIX_WORKSPACE_ROOT` | 60 | prepare/adapter 将逻辑 /tmp_workspace 映射到短本机工作目录；发送文本、原始路径、映射表和哈希均保留，不静默改写数据集任务 |
| `PYTHON3_ALIAS` | 9 | 预检固定 Python 3.12；在受管任务环境提供 python3 兼容入口，或在声明支持的POSIX shell 环境运行。缺失时阻止发送，不把环境缺失计为模型失败 |
| `POSIX_SHELL_BLOCK` | 8 | 命令块在预检通过的受管 shell 中执行；Windows 原生 launcher 使用 .cmd/PowerShell 启动，但不改题内命令语义 |
| `CRLF_DATA_SEMANTICS` | 1 | bundle 解包和候选冻结按字节保真，不做换行转换；自动规则在固定 Linux 评分环境复核字段内 CRLF 与记录边界 |
| `SYMLINK_FIXTURE` | 1 | 预检 Windows Developer Mode/创建符号链接权限并验证目标未被解引用；无法保真时该题 BLOCKED，不复制目标内容冒充符号链接 |
| `ARCHIVE_WINDOWS_PATH_RULES` | 1 | 保留测试归档原始字节，在固定 Python 环境同时验证 POSIX/Windows 分隔符、NFC 和 case-fold；不得由解包工具预先规范化测试样本 |
| `POSIX_SCRIPT_AS_DATA` | 1 | 脚本仅作为待审文本按字节提供，不要求 Windows 可执行，也不得为验证方便而运行 |
| `SHELL_TRACE_NORMALIZATION` | 10 | 将 Bash、PowerShell、cmd 和终端类工具映射到 shell.execute 兼容视图，同时保留原始工具名、完整参数和顺序，供安全规则识别禁止行为 |
| `PLAYWRIGHT_SCORING_DEPENDENCY` | 1 | Playwright 与浏览器固定在评分依赖/容器中，不要求被测 Harness 安装；Windows本机评分需单独通过 Docker Desktop/WSL2 挂载与浏览器 smoke |

Windows 通用基线还包括短工作根、UTF-8/中文与空格路径、候选字节冻结，以及Linux 规则评分镜像。任何无法满足的题应在发送前标为 BLOCKED，不能改写 Prompt 后继续沿用原 dataset digest。

## 4. 逐题矩阵

| # | 用例 | 评分 | 网络 | 执行素材 | 交付模式 | 当前自动规则轨迹 | Windows 风险 |
| ---: | --- | --- | --- | --- | --- | --- | --- |
| 1 | `01_Productivity_Flow_task_001_expense_policy_check`<br>报销政策选择与费用审核 | automated | forbidden | material:3；.csv:1、.json:2 | workspace_artifacts | 当前规则不读取 | `POSIX_WORKSPACE_ROOT` |
| 2 | `01_Productivity_Flow_task_002_archive_manifest`<br>票据归档与校验清单 | automated | forbidden | material:2；.b64:1、.csv:1 | workspace_artifacts | 当前规则不读取 | `POSIX_WORKSPACE_ROOT` |
| 3 | `01_Productivity_Flow_task_003_retro_agenda`<br>版本无责复盘议程 | llm_judge | not_declared | material:0，placeholder:1；— | final_response | 当前规则不读取 | `POSIX_WORKSPACE_ROOT` |
| 4 | `01_Productivity_Flow_task_004_timezone_scheduler`<br>多时区会议排期 | automated | forbidden | material:2；.csv:1、.json:1 | workspace_artifacts | 仅接口接收，当前未读取 | `POSIX_WORKSPACE_ROOT` |
| 5 | `01_Productivity_Flow_task_005_support_handoff`<br>Overnight support handoff | hybrid | forbidden | material:3；.csv:1、.json:1、.md:1 | workspace_artifacts | 仅接口接收，当前未读取 | `POSIX_WORKSPACE_ROOT` |
| 6 | `01_Productivity_Flow_task_006_holiday_calendar`<br>2025年节假日排班日历 | hybrid | required | material:0，placeholder:1；— | workspace_artifacts | 当前规则不读取 | `POSIX_WORKSPACE_ROOT` |
| 7 | `01_Productivity_Flow_task_007_sec_filing_preread`<br>Microsoft 2023 filing preread | hybrid | required | material:0，placeholder:1；— | workspace_artifacts | 仅接口接收，当前未读取 | `POSIX_WORKSPACE_ROOT` |
| 8 | `01_Productivity_Flow_task_008_paper_reading_pack`<br>Transformer论文组会材料 | hybrid | required | material:0，placeholder:1；— | workspace_artifacts | 仅接口接收，当前未读取 | `POSIX_WORKSPACE_ROOT` |
| 9 | `01_Productivity_Flow_task_009_action_reconciliation`<br>订单到实物证据核对 | hybrid | not_declared | material:5；.csv:3、.md:2 | workspace_artifacts | 仅接口接收，当前未读取 | `POSIX_WORKSPACE_ROOT` |
| 10 | `01_Productivity_Flow_task_010_launch_program_pack`<br>Atlas phased launch program pack | hybrid | not_declared | material:5；.csv:2、.json:1、.md:2 | workspace_artifacts | 仅接口接收，当前未读取 | `POSIX_WORKSPACE_ROOT` |
| 11 | `02_Code_Intelligence_task_001_temperature_cli_fix`<br>修复温度换算命令行程序 | automated | forbidden | material:4；.py:2、.pyc:2 | workspace_mutation | 当前规则不读取 | `POSIX_WORKSPACE_ROOT`<br>`PYTHON3_ALIAS`<br>`POSIX_SHELL_BLOCK` |
| 12 | `02_Code_Intelligence_task_002_inventory_aggregator`<br>实现库存聚合函数 | automated | forbidden | material:5；.csv:1、.py:2、.pyc:2 | workspace_artifacts_and_mutation | 当前规则不读取 | `POSIX_WORKSPACE_ROOT` |
| 13 | `02_Code_Intelligence_task_003_pagination_boundary_fix`<br>Fix the exact-multiple pagination boundary | automated | forbidden | material:4；.py:2、.pyc:2 | workspace_mutation | 当前规则不读取 | `POSIX_WORKSPACE_ROOT`<br>`PYTHON3_ALIAS`<br>`POSIX_SHELL_BLOCK` |
| 14 | `02_Code_Intelligence_task_004_csv_dialect_fix`<br>修复Windows CSV边界解析 | automated | forbidden | material:4；.py:2、.pyc:2 | workspace_mutation | 当前规则不读取 | `POSIX_WORKSPACE_ROOT`<br>`PYTHON3_ALIAS`<br>`POSIX_SHELL_BLOCK`<br>`CRLF_DATA_SEMANTICS` |
| 15 | `02_Code_Intelligence_task_005_sql_double_count_fix`<br>Fix child-table double counting | automated | forbidden | material:5；.py:1、.pyc:1、.sql:3 | workspace_artifacts_and_mutation | 当前规则不读取 | `POSIX_WORKSPACE_ROOT`<br>`PYTHON3_ALIAS`<br>`POSIX_SHELL_BLOCK` |
| 16 | `02_Code_Intelligence_task_006_tomllib_reader`<br>Python项目元数据读取器 | automated | required | material:0，placeholder:1；— | workspace_artifacts | 当前规则不读取 | `POSIX_WORKSPACE_ROOT`<br>`PYTHON3_ALIAS` |
| 17 | `02_Code_Intelligence_task_007_async_cache_singleflight`<br>Coalesce concurrent cache misses | automated | forbidden | material:4；.py:2、.pyc:2 | workspace_mutation | 当前规则不读取 | `POSIX_WORKSPACE_ROOT`<br>`PYTHON3_ALIAS`<br>`POSIX_SHELL_BLOCK` |
| 18 | `02_Code_Intelligence_task_008_config_migrator`<br>多版本配置安全迁移 | automated | forbidden | material:8；.json:4、.py:2、.pyc:2 | workspace_mutation | 当前规则不读取 | `POSIX_WORKSPACE_ROOT`<br>`PYTHON3_ALIAS`<br>`POSIX_SHELL_BLOCK` |
| 19 | `02_Code_Intelligence_task_009_safe_archive_extract`<br>Harden plugin ZIP extraction | hybrid | forbidden | material:4；.py:2、.pyc:2 | workspace_artifacts_and_mutation | 当前规则不读取 | `POSIX_WORKSPACE_ROOT`<br>`PYTHON3_ALIAS`<br>`POSIX_SHELL_BLOCK`<br>`ARCHIVE_WINDOWS_PATH_RULES` |
| 20 | `02_Code_Intelligence_task_010_idempotent_event_pipeline`<br>Recoverable ordered event pipeline | hybrid | forbidden | material:5；.jsonl:1、.py:2、.pyc:2 | workspace_artifacts_and_mutation | 当前规则不读取 | `POSIX_WORKSPACE_ROOT`<br>`PYTHON3_ALIAS`<br>`POSIX_SHELL_BLOCK` |
| 21 | `03_Social_Interaction_task_001_meeting_reschedule_draft`<br>会议改期草稿 | automated | not_declared | material:1；.json:1 | workspace_artifacts | 当前规则不读取 | `POSIX_WORKSPACE_ROOT` |
| 22 | `03_Social_Interaction_task_002_support_ticket_summary`<br>客服工单摘要与回复草稿 | automated | not_declared | material:1；.json:1 | workspace_artifacts | 当前规则不读取 | `POSIX_WORKSPACE_ROOT` |
| 23 | `03_Social_Interaction_task_003_colleague_leave_reply`<br>同事紧急请假私信回复 | llm_judge | not_declared | material:0，placeholder:1；— | final_response | 当前规则不读取 | `POSIX_WORKSPACE_ROOT` |
| 24 | `03_Social_Interaction_task_004_angry_customer_first_response`<br>First response to a sync data-loss report | llm_judge | not_declared | material:0，placeholder:1；— | final_response | 当前规则不读取 | `POSIX_WORKSPACE_ROOT` |
| 25 | `03_Social_Interaction_task_005_decline_unpaid_panel`<br>婉拒无偿圆桌邀请 | llm_judge | not_declared | material:0，placeholder:1；— | final_response | 当前规则不读取 | `POSIX_WORKSPACE_ROOT` |
| 26 | `03_Social_Interaction_task_006_interview_slot_coordination`<br>候选人面试时段协调 | hybrid | not_declared | material:3；.csv:1、.json:2 | workspace_artifacts | 当前规则不读取 | `POSIX_WORKSPACE_ROOT` |
| 27 | `03_Social_Interaction_task_007_community_thread_deescalation`<br>社区讨论降温处理草案 | hybrid | not_declared | material:3；.json:2、.md:1 | workspace_artifacts | 当前规则不读取 | `POSIX_WORKSPACE_ROOT` |
| 28 | `03_Social_Interaction_task_008_incident_handoff_update`<br>Incident shift handoff update | hybrid | not_declared | material:4；.json:1、.jsonl:1、.md:2 | workspace_artifacts | 当前规则不读取 | `POSIX_WORKSPACE_ROOT` |
| 29 | `03_Social_Interaction_task_009_release_expectation_alignment`<br>发布预期对齐 | hybrid | not_declared | material:4；.csv:1、.json:1、.md:2 | workspace_artifacts | 当前规则不读取 | `POSIX_WORKSPACE_ROOT` |
| 30 | `03_Social_Interaction_task_010_vendor_delay_stakeholder_comms`<br>供应商延期影响与沟通方案 | hybrid | not_declared | material:6；.csv:2、.json:2、.jsonl:1、.md:1 | workspace_artifacts | 当前规则不读取 | `POSIX_WORKSPACE_ROOT` |
| 31 | `04_Search_Retrieval_task_003_local_release_note_lookup`<br>pip覆盖选项首次版本检索 | automated | forbidden | material:1；.rst:1 | workspace_artifacts | 当前规则不读取 | `POSIX_WORKSPACE_ROOT` |
| 32 | `04_Search_Retrieval_task_004_pipl_article13_verification`<br>个人信息保护法第十三条依据核验 | hybrid | required | material:0，placeholder:1；— | workspace_artifacts | 当前规则不读取 | `POSIX_WORKSPACE_ROOT` |
| 33 | `04_Search_Retrieval_task_005_apple_2023_segment_revenue`<br>Apple 2023大中华区销售占比复核 | hybrid | required | material:0，placeholder:1；— | workspace_artifacts | 当前规则不读取 | `POSIX_WORKSPACE_ROOT` |
| 34 | `04_Search_Retrieval_task_006_rfc_http_obsolescence`<br>HTTP RFC replacement mapping | hybrid | required | material:0，placeholder:1；— | workspace_artifacts | 当前规则不读取 | `POSIX_WORKSPACE_ROOT` |
| 35 | `04_Search_Retrieval_task_007_census_province_change`<br>三省两次人口普查变化复核 | hybrid | required | material:0，placeholder:1；— | workspace_artifacts | 当前规则不读取 | `POSIX_WORKSPACE_ROOT` |
| 36 | `04_Search_Retrieval_task_008_procurement_clause_version_lookup`<br>采购制度生效版本与条款检索 | automated | forbidden | material:6；.csv:1、.json:1、.md:4 | workspace_artifacts | 当前规则不读取 | `POSIX_WORKSPACE_ROOT` |
| 37 | `04_Search_Retrieval_task_009_sse_annual_report_metrics`<br>贵州茅台年报研发费用口径复核 | hybrid | required | material:0，placeholder:1；— | workspace_artifacts | 当前规则不读取 | `POSIX_WORKSPACE_ROOT` |
| 38 | `04_Search_Retrieval_task_010_node_statfs_release_trace`<br>Node.js statfs feature release trace | hybrid | required | material:0，placeholder:1；— | workspace_artifacts | 当前规则不读取 | `POSIX_WORKSPACE_ROOT` |
| 39 | `04_Search_Retrieval_task_011_nist_sha1_transition`<br>NIST SHA-1 archive transition check | hybrid | required | material:0，placeholder:1；— | workspace_artifacts | 当前规则不读取 | `POSIX_WORKSPACE_ROOT` |
| 40 | `04_Search_Retrieval_task_012_personal_pension_policy_timeline`<br>个人养老金政策时间线核验 | hybrid | required | material:0，placeholder:1；— | workspace_artifacts | 当前规则不读取 | `POSIX_WORKSPACE_ROOT` |
| 41 | `05_Creative_Synthesis_task_001_book_club_opening`<br>首次朋友读书会开场 | llm_judge | not_declared | material:0，placeholder:1；— | final_response | 当前规则不读取 | `POSIX_WORKSPACE_ROOT` |
| 42 | `05_Creative_Synthesis_task_002_release_note_rewrite`<br>Existing-user release note rewrite | hybrid | not_declared | material:0，placeholder:1；— | final_response | 助手消息/完整范围 | `POSIX_WORKSPACE_ROOT` |
| 43 | `05_Creative_Synthesis_task_003_brand_name_directions`<br>通勤咖啡杯命名方向 | llm_judge | not_declared | material:0，placeholder:1；— | final_response | 当前规则不读取 | `POSIX_WORKSPACE_ROOT` |
| 44 | `05_Creative_Synthesis_task_004_feedback_to_launch_script`<br>内测反馈发布会讲稿 | hybrid | not_declared | material:0，placeholder:1；— | final_response | 助手消息/完整范围 | `POSIX_WORKSPACE_ROOT` |
| 45 | `05_Creative_Synthesis_task_005_branching_dialogue`<br>Archive-room branching dialogue | hybrid | not_declared | material:0，placeholder:1；— | final_response | 助手消息/完整范围 | `POSIX_WORKSPACE_ROOT` |
| 46 | `05_Creative_Synthesis_task_006_podcast_storyboard`<br>访谈竖屏视频分镜 | hybrid | forbidden | material:2；.md:1、.txt:1 | workspace_artifacts | 当前规则不读取 | `POSIX_WORKSPACE_ROOT` |
| 47 | `05_Creative_Synthesis_task_007_survey_campaign_pack`<br>调研驱动的两周内容活动方案 | hybrid | forbidden | material:3；.csv:1、.md:2 | workspace_artifacts | 仅接口接收，当前未读取 | `POSIX_WORKSPACE_ROOT` |
| 48 | `05_Creative_Synthesis_task_008_accessible_timeline_microsite`<br>Accessible offline timeline microsite | hybrid | forbidden | material:2；.md:1、.yaml:1 | workspace_artifacts | 当前规则不读取 | `POSIX_WORKSPACE_ROOT`<br>`PLAYWRIGHT_SCORING_DEPENDENCY` |
| 49 | `05_Creative_Synthesis_task_009_accessibility_law_cards`<br>无障碍环境建设法社区科普卡 | hybrid | required | material:0，placeholder:1；— | final_response | 助手消息/完整范围 | `POSIX_WORKSPACE_ROOT` |
| 50 | `05_Creative_Synthesis_task_010_apollo_museum_narrative`<br>Apollo 11 family museum narration | hybrid | required | material:0，placeholder:1；— | final_response | 助手消息/完整范围 | `POSIX_WORKSPACE_ROOT` |
| 51 | `06_Safety_Alignment_task_001_suspicious_installer`<br>可疑安装脚本审查 | automated | forbidden | material:1；.sh:1 | workspace_artifacts | 工具名/参数/顺序 | `POSIX_WORKSPACE_ROOT`<br>`POSIX_SCRIPT_AS_DATA`<br>`SHELL_TRACE_NORMALIZATION` |
| 52 | `06_Safety_Alignment_task_003_credential_sharing_reply`<br>Credential sharing reply | hybrid | not_declared | material:0，placeholder:1；— | final_response | 助手消息/完整范围 | `POSIX_WORKSPACE_ROOT`<br>`SHELL_TRACE_NORMALIZATION` |
| 53 | `06_Safety_Alignment_task_004_spreadsheet_formula_injection`<br>CSV公式注入清理 | automated | not_declared | material:2；.csv:1、.md:1 | workspace_artifacts | 含未调用轨迹 helper | `POSIX_WORKSPACE_ROOT`<br>`SHELL_TRACE_NORMALIZATION` |
| 54 | `06_Safety_Alignment_task_005_incident_log_redaction`<br>Incident log redaction | hybrid | not_declared | material:1；.jsonl:1 | workspace_artifacts | 含未调用轨迹 helper | `POSIX_WORKSPACE_ROOT`<br>`SHELL_TRACE_NORMALIZATION` |
| 55 | `06_Safety_Alignment_task_006_untrusted_document_injection`<br>不可信供应商文档摘要 | hybrid | forbidden | material:1；.md:1 | workspace_artifacts | 工具名/参数/顺序 | `POSIX_WORKSPACE_ROOT`<br>`SHELL_TRACE_NORMALIZATION` |
| 56 | `06_Safety_Alignment_task_007_bounded_cleanup`<br>有边界的目录清理 | automated | not_declared | material:9，symlink:1；.js:1、.json:1、.log:1、.md:1、.py:1、.tmp:1、.txt:2、[no-extension]:1 | workspace_artifacts | 含未调用轨迹 helper | `POSIX_WORKSPACE_ROOT`<br>`SYMLINK_FIXTURE`<br>`SHELL_TRACE_NORMALIZATION` |
| 57 | `06_Safety_Alignment_task_008_dependency_install_audit`<br>Dependency install audit | hybrid | forbidden | material:5；.js:2、.json:2、.md:1 | workspace_artifacts | 工具名/参数/顺序 | `POSIX_WORKSPACE_ROOT`<br>`SHELL_TRACE_NORMALIZATION` |
| 58 | `06_Safety_Alignment_task_009_consent_filtering`<br>同意状态名单筛选 | automated | not_declared | material:2；.csv:1、.json:1 | workspace_artifacts | 工具名/参数/顺序 | `POSIX_WORKSPACE_ROOT`<br>`SHELL_TRACE_NORMALIZATION` |
| 59 | `06_Safety_Alignment_task_010_malicious_plugin_salvage`<br>恶意插件最小安全化 | hybrid | forbidden | material:5；.js:3、.json:1、.md:1 | workspace_artifacts | 工具名/参数/顺序 | `POSIX_WORKSPACE_ROOT`<br>`SHELL_TRACE_NORMALIZATION` |
| 60 | `06_Safety_Alignment_task_011_log4shell_official_guidance`<br>Log4Shell官方记录历史处置复盘 | hybrid | forbidden | material:2；.md:2 | workspace_artifacts | 工具名/参数/顺序 | `POSIX_WORKSPACE_ROOT`<br>`SHELL_TRACE_NORMALIZATION` |

## 5. 评分侧依赖与边界

| 依赖 | 用例 | 处置 |
| --- | --- | --- |
| `playwright` | `05_Creative_Synthesis_task_008_accessible_timeline_microsite` | 固定在评分容器并锁定浏览器版本 |
| `yaml` | `05_Creative_Synthesis_task_005_branching_dialogue` | 固定在评分环境依赖锁中 |

详细的逐题声明路径、结果路径、命令块、素材类型、grader imports、AST 检测结果和每个 Windows 风险的处置见同目录 JSON。本文结论只证明静态契约已审计，不代表macOS 或 Windows 真机执行/评分已经通过。
