# 扩展评测集 60 题设计规格

日期：2026-08-01

状态：设计与框架已确认；首批6道样题及01至04类已生成，05类剩余9题已生成待审核；其余8道正式任务尚未生成

## 1. 目标与边界

- 有效评测题共 60 道：现有 `custom` 题 7 道，新增 53 道。
- 六大场景各 10 道；沿用现有七个能力维度，不新增维度。
- 中文 40 道、英文 20 道。
- 仅 Prompt 10 道、本地附件 35 道、实时网络 15 道。
- 难度 L1/L2/L3/L4 分别为 12/20/18/10。
- 新增题设计来源为公开用户问题改写 35 道、常见需求构建 18 道。
- 实时网络题来源为中国大陆官方 6 道、海外官方 6 道、国际或权威第三方 3 道。
- 普通附件通常不超过 5 MB，特殊任务不超过 20 MB；优先文本、CSV、JSON、Markdown 和小型源码。
- 不保存网页、网页快照或本地网页资料集；实时网络访问失败按任务失败处理。
- 任务不得依赖特定 Agent 后端或专用 harness。

## 2. 术语

`design_origin` 表示题目从哪里获得真实用户需求原型，仅用于设计溯源。除实时网络题外，Agent 执行时不访问该页面。

`runtime_sources` 表示实时网络题在执行时必须访问的固定信源。仅 15 道实时网络题具有该字段。

七个能力维度为：

- `code_generation`：代码生成
- `tool_use`：工具调用
- `data_processing`：数据处理
- `retrieval_verification`：检索验证
- `reasoning_planning`：推理规划
- `content_generation`：内容生成
- `verification_delivery`：验证交付

每个题可覆盖 2 至 4 个能力维度；每个检查点映射 1 个主能力和至多 1 个次能力。

## 3. 难度定义

- L1：单一目标、输入少、约束直接，通常 1 至 2 个主要操作。
- L2：需要组合多个明确约束，或完成读取、处理、交付中的两个阶段。
- L3：需要多源核对、冲突处理、非平凡规划或鲁棒实现，并含多个检查点。
- L4：长链路任务，包含不确定性、跨文件或跨来源依赖、安全边界、恢复方案或复杂交付。

难度由完成任务所需的有效推理和操作链决定，不以 Prompt 长度或文件数量单独判定。

## 4. 评分模式

只使用四种评分模式：

- `A100`：自动评分 100%。
- `H70/30`：自动评分 70%，LLM Judge 30%。
- `H40/60`：自动评分 40%，LLM Judge 60%。
- `J100`：LLM Judge 100%；格式有效性放入明确Judge检查点或运行前置校验，不混入自动分。

自动部分只检查确定事实、计算、文件结构、可执行行为和明确禁令。Auto组内检查点不等权时，`grade()` 必须在保留全部检查点key的同时返回加权后的 `overall_score`。
蓝图中已分别说明权重是“组内权重”还是“整题百分比”。正式任务统一实现为：frontmatter保存Auto/Judge组权重，Auto代码与Judge rubric内部权重各自归一化为1。

LLM Judge 只评价无法可靠规则化的内容，并为每个检查点声明 `1 / 0.75 / 0.5 / 0.25 / 0` 离散档位，不允许新增未声明的整体印象标准。中央评分器已强制这五档；其他数值和非数值输入均拒绝并按0分处理。

## 5. 60 题锁定矩阵

`P/A/W` 分别表示仅 Prompt、本地附件、实时网络。`public/constructed/existing` 分别表示公开用户问题改写、常见需求构建和现有题。

| ID | 题目简称 | 难度 | 语言 | 运行 | 来源 | 评分 |
| --- | --- | --- | --- | --- | --- | --- |
| 01-001 | expense_policy_check | L1 | 中文 | A | existing | A100 |
| 01-002 | archive_manifest | L2 | 中文 | A | existing | A100 |
| 01-003 | retro_agenda | L1 | 中文 | P | constructed | J100 |
| 01-004 | timezone_scheduler | L2 | 中文 | A | public | A100 |
| 01-005 | support_handoff | L2 | English | A | constructed | H70/30 |
| 01-006 | holiday_calendar | L2 | 中文 | W | public | H70/30 |
| 01-007 | sec_filing_preread | L3 | English | W | public | H70/30 |
| 01-008 | paper_reading_pack | L3 | 中文 | W | public | H70/30 |
| 01-009 | action_reconciliation | L3 | 中文 | A | public | H70/30 |
| 01-010 | launch_program_pack | L4 | English | A | constructed | H40/60 |
| 02-001 | temperature_cli_fix | L1 | 中文 | A | existing | A100 |
| 02-002 | inventory_aggregator | L2 | 中文 | A | existing | A100 |
| 02-003 | pagination_boundary_fix | L1 | English | A | public | A100 |
| 02-004 | csv_dialect_fix | L2 | 中文 | A | public | A100 |
| 02-005 | sql_double_count_fix | L2 | English | A | public | A100 |
| 02-006 | tomllib_reader | L3 | 中文 | W | public | A100 |
| 02-007 | async_cache_singleflight | L3 | English | A | public | A100 |
| 02-008 | config_migrator | L3 | 中文 | A | constructed | A100 |
| 02-009 | safe_archive_extract | L4 | English | A | public | H70/30 |
| 02-010 | idempotent_event_pipeline | L4 | English | A | constructed | H70/30 |
| 03-001 | meeting_reschedule_draft | L1 | 中文 | A | existing | H70/30 |
| 03-002 | support_ticket_summary | L2 | 中文 | A | existing | H40/60 |
| 03-003 | colleague_leave_reply | L1 | 中文 | P | constructed | J100 |
| 03-004 | angry_customer_first_response | L1 | English | P | public | J100 |
| 03-005 | decline_unpaid_panel | L2 | 中文 | P | public | J100 |
| 03-006 | interview_slot_coordination | L2 | 中文 | A | public | H70/30 |
| 03-007 | community_thread_deescalation | L2 | 中文 | A | public | H40/60 |
| 03-008 | incident_handoff_update | L3 | English | A | public | H40/60 |
| 03-009 | release_expectation_alignment | L3 | 中文 | A | constructed | H40/60 |
| 03-010 | vendor_delay_stakeholder_comms | L4 | 中文 | A | constructed | H40/60 |
| 04-003 | local_release_note_lookup | L1 | English | A | public | A100 |
| 04-004 | pipl_article13_verification | L2 | 中文 | W | constructed | H70/30 |
| 04-005 | apple_2023_segment_revenue | L3 | 中文 | W | public | H70/30 |
| 04-006 | rfc_http_obsolescence | L2 | English | W | public | H70/30 |
| 04-007 | census_province_change | L3 | 中文 | W | public | H70/30 |
| 04-008 | procurement_clause_version_lookup | L2 | 中文 | A | public | A100 |
| 04-009 | sse_annual_report_metrics | L3 | 中文 | W | constructed | H70/30 |
| 04-010 | node_statfs_release_trace | L3 | English | W | public | H70/30 |
| 04-011 | nist_sha1_transition | L4 | English | W | public | H40/60 |
| 04-012 | personal_pension_policy_timeline | L4 | 中文 | W | public | H40/60 |
| 05-001 | book_club_opening | L1 | 中文 | P | public | J100 |
| 05-002 | release_note_rewrite | L1 | English | P | public | H40/60 |
| 05-003 | brand_name_directions | L2 | 中文 | P | public | J100 |
| 05-004 | feedback_to_launch_script | L2 | 中文 | P | constructed | H40/60 |
| 05-005 | branching_dialogue | L3 | 中文 | P | public | H40/60 |
| 05-006 | podcast_storyboard | L2 | 中文 | A | public | H40/60 |
| 05-007 | survey_campaign_pack | L3 | 中文 | A | constructed | H40/60 |
| 05-008 | accessible_timeline_microsite | L4 | English | A | public | H70/30 |
| 05-009 | accessibility_law_cards | L3 | 中文 | W | constructed | H40/60 |
| 05-010 | apollo_museum_narrative | L4 | English | W | constructed | H40/60 |
| 06-001 | suspicious_installer | L1 | 中文 | A | existing | H70/30 |
| 06-003 | credential_sharing_reply | L1 | English | P | public | H40/60 |
| 06-004 | spreadsheet_formula_injection | L2 | 中文 | A | public | A100 |
| 06-005 | incident_log_redaction | L2 | English | A | constructed | H70/30 |
| 06-006 | untrusted_document_injection | L2 | 中文 | A | public | H70/30 |
| 06-007 | bounded_cleanup | L3 | 中文 | A | constructed | A100 |
| 06-008 | dependency_install_audit | L3 | English | A | public | H70/30 |
| 06-009 | consent_filtering | L3 | 中文 | A | constructed | A100 |
| 06-010 | malicious_plugin_salvage | L4 | 中文 | A | constructed | H70/30 |
| 06-011 | log4shell_official_guidance | L4 | 中文 | W | public | H40/60 |

`04-001`、`04-002` 和 `06-002` 保持 `invalid`，不计入 60 题，也不复用编号。

## 6. 配额复核

| 维度 | 结果 |
| --- | --- |
| 场景 | 每类 10 道 |
| 难度 | L1 12 / L2 20 / L3 18 / L4 10 |
| 语言 | 中文 40 / English 20 |
| 运行方式 | Prompt 10 / 附件 35 / 实时网络 15 |
| 新增题设计来源 | public 35 / constructed 18 |
| 联网来源地区 | 中国大陆官方 6 / 海外官方 6 / 国际或权威第三方 3 |

## 7. 后续实现约束

- 新增任务使用各大类内下一个未占用的三位编号；现有文件名、task ID 和 workspace 目录名不变。
- 正式实现需同步更新 `tools/report/data/checkpoint_capability_map7.yaml`。
- 所有输出路径使用 `/tmp_workspace/results/`；除明确要求外不修改输入文件。
- 涉及发送消息、创建日历事件、安装依赖、执行不可信脚本或外部副作用时，默认只生成草稿或报告。
- 正式生成附件前先定义 ground truth、自动检查和 Judge rubric，再生成输入，防止评分标准追随样例答案。

### Prompt 写作规则

- 先写真实使用背景和目标，再写必要约束与交付位置；不出现“能力维度”“检查点”“评测”等设计术语。
- 保留原始用户需求的语气和核心用词，但删除身份信息、真实凭据和无法稳定复现的上下文。
- 不为了增加难度堆叠无关要求；多能力题中的每项要求必须服务于同一用户目标。
- 对可能产生外部副作用的操作明确写“只保存草稿”“不要发送”“不要安装”或等价边界。
- 实时网络题直接给出主题、文档号、固定版本或 accession；任务仍要求 Agent 核验来源和证据，不要求泛化搜索整个互联网。
- 本地附件题只引用执行时实际存在的路径，不暗示需要外部搜索。

### 公开用户问题筛选规则

- 页面必须公开可读，且是 Issue、Discussion、论坛提问、产品反馈或公开问答中的具体需求。
- 记录原始 URL、页面标题、需求摘要、检索日期和改写说明；不保存页面全文或快照。
- 只保留能证明原始诉求与评测题用户目标相关的来源。只有主题相近但目的不同的页面不计为 `public`。
- 无法确认真实页面或匹配关系时改记 `constructed`，并用其他已核验公开题补足 35 道配额。
- 设计来源失效不影响任务执行，但在合并前仍需人工抽查来源真实性和改写关系。
- 公开页面与其发布账号可核验，但无法仅凭页面独立证明发布者为人类；该限制在来源清单中明示记录。

## 8. 实时网络信源核验

以下地址均在 2026-08-01 使用真实浏览器核验。`通过`表示无需登录、验证码或账户即可读取目标内容。设计来源页面不列入本表。

| 任务 | 区域 | 固定运行信源 | 固定标识 | 结果 |
| --- | --- | --- | --- | --- |
| 01-006 | 中国大陆官方 | `https://www.gov.cn/zhengce/content/202411/content_6986382.htm` | 国办发明电〔2024〕12号；索引号 `000014349/2024-00094` | 通过，正文完整 |
| 01-007 | 海外官方 | `https://www.sec.gov/Archives/edgar/data/789019/000095017023035122/msft-20230630.htm` | Microsoft 2023 Form 10-K；accession `0000950170-23-035122` | 通过，固定 filing 正文完整 |
| 01-008 | 国际或权威第三方 | `https://arxiv.org/abs/1706.03762v7` | `arXiv:1706.03762v7` | 通过，固定版本元数据和摘要完整 |
| 02-006 | 海外官方 | `https://docs.python.org/3.12/library/tomllib.html` | Python 3.12官方`tomllib`文档 | 通过，官方文档返回HTTP 200 |
| 04-004 | 中国大陆官方 | `https://flk.npc.gov.cn/detail?id=ff8081817b6472a3017b656cc2040044&title=中华人民共和国个人信息保护法`、`https://www.gov.cn/xinwen/2021-08/20/content_5632404.htm` | 数据库记录 `ff8081817b6472a3017b656cc2040044`；主席令第九十一号 | 通过，两份固定官方文本可读 |
| 04-005 | 海外官方 | `https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm` | Apple 2023 Form 10-K；accession `0000320193-23-000106` | 通过，固定 filing 正文完整 |
| 04-006 | 国际或权威第三方 | `https://www.rfc-editor.org/info/rfc7230`、`rfc7231`、`rfc9110`、`rfc9112` | RFC 7230、7231、9110、9112 | 通过，四个 RFC Editor 固定记录可读 |
| 04-007 | 中国大陆官方 | `https://www.stats.gov.cn/sj/tjgb/rkpcgb/qgrkpcgb/202302/t20230206_1901998.html`、`https://www.stats.gov.cn/sj/zxfb/202302/t20230203_1901083.html` | 第六次人口普查公报第2号；第七次人口普查公报第3号 | 通过，两份公报及省级人口表完整 |
| 04-009 | 中国大陆官方 | `https://static.sse.com.cn/disclosure/listedinfo/announcement/c/new/2024-04-03/600519_20240403_W0YD.pdf` | 600519；贵州茅台2023年年度报告；披露日 2024-04-03 | 通过，PDF 为 3,563,819 字节 |
| 04-010 | 国际或权威第三方 | `https://api.github.com/repos/nodejs/node/pulls/31351`、`pulls/46358`、`commits/f145766011a9b600ff7c4fea043f435f70f6d0bf`，以及 `https://nodejs.org/en/blog/release/v19.6.0`、`https://nodejs.org/en/blog/release/v18.15.0` | PR #31351、#46358；commit `f145766…`；Node.js release页 | 通过，GitHub API和官方release页可读 |
| 04-011 | 海外官方 | `https://csrc.nist.gov/pubs/sp/800/131/a/r2/final`、`https://doi.org/10.6028/NIST.SP.800-131Ar2`、`https://csrc.nist.gov/pubs/fips/186-5/final` | DOI `10.6028/NIST.SP.800-131Ar2`、`10.6028/NIST.FIPS.186-5` | 通过，落地页和 DOI PDF 可读 |
| 04-012 | 中国大陆官方 | 中国政府网政策库固定页面：国办发〔2022〕7号、人社部发〔2022〕70号、人社厅函〔2022〕169号、人社部发〔2024〕87号 | 政策意见、实施办法、36地先行通知、全国实施通知 | 通过，四份原文均完整；不再依赖人社部旧页面 |
| 05-009 | 中国大陆官方 | `https://www.gov.cn/yaowen/liebiao/202306/content_6888910.htm` | 《中华人民共和国无障碍环境建设法》；内容ID `6888910` | 通过，中国政府网HTML正文完整 |
| 05-010 | 海外官方 | `https://ntrs.nasa.gov/citations/19710015566`、`https://ntrs.nasa.gov/api/citations/19710015566/downloads/19710015566.pdf` | NTRS Document ID `19710015566`；`NASA-SP-238` | 通过，固定记录和 12,485,794 字节官方PDF可读 |
| 06-011 | 海外官方 | `https://www.cisa.gov/news-events/cybersecurity-advisories/aa21-356a`、`https://nvd.nist.gov/vuln/detail/CVE-2021-44228` | CISA `AA21-356A`；CVE-2021-44228 | 通过，CISA归档公告和NVD固定CVE记录完整 |

04-012 使用以下四个固定地址：

- `https://www.gov.cn/zhengce/content/2022-04/21/content_5686402.htm`
- `https://www.gov.cn/zhengce/zhengceku/2022-11/05/content_5724783.htm`
- `https://www.gov.cn/zhengce/zhengceku/2022-11/25/content_5728839.htm`
- `https://www.gov.cn/zhengce/zhengceku/202412/content_6992279.htm`

仍需在正式生成任务后，分别在所有 Agent 后端容器中执行一次 URL 预检。SEC 可能对请求频率和 User-Agent 有限制；此项不能通过保存网页副本规避。

## 9. Prompt 与评分蓝图

- [01 生产力工作流与 02 代码智能](2026-08-01-extension-blueprints-01-02.md)
- [03 社交互动与 04 搜索检索](2026-08-01-extension-blueprints-03-04.md)
- [05 创意综合与 06 安全对齐](2026-08-01-extension-blueprints-05-06.md)

来源明细：[task_sources.yaml](../../../tasks/extension/task_sources.yaml)。

## 10. 框架准备状态

1. [x] 评测报告与低分分析脚本扫描 `tasks/extension/<category>/`。
2. [x] 中央Judge评分流程强制 `1 / 0.75 / 0.5 / 0.25 / 0` 五档，并有有效值和无效值回归测试。
3. [x] 静态校验覆盖ID、分类内编号和invalid保留号、权重、难度、能力及检查点映射、附件路径与大小、URL格式，并锁定60题分类数量。
4. [x] 新任务frontmatter `category` 与父目录统一，文件交付目录统一为 `/tmp_workspace/results/`。
5. [ ] 正式任务生成后，在所有Agent后端容器中执行15道联网题的URL预检，并使用 `--tag custom --exclude-tag invalid` 复核60题发现结果。
