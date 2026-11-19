---
id: general_hard_office_documents_task_014_support_localization
name: 多语言支持知识包的事实一致性
category: office_documents
timeout_seconds: 900
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L4
grading_type: hybrid
grading_weights:
  automated: 0.25
  llm_judge: 0.75
tags:
  - custom
  - general-hard
judge_evidence:
  required:
    - path: results/faq_zh.docx
      role: candidate_deliverable
    - path: results/faq_en.docx
      role: candidate_deliverable
    - path: results/faq_vi.docx
      role: candidate_deliverable
    - path: results/case_replies.csv
      role: candidate_deliverable
scoring_runtime:
  office: true
  office_render: true
dataset_report: {"category": "office_documents", "category_name": "文档与办公交付", "category_order": 0, "checkpoint_capabilities": {"automated.case_routing": ["reasoning_planning"], "automated.delivery_integrity": ["verification_delivery"], "automated.evidence_binding": ["retrieval_verification"], "automated.faq_coverage": ["verification_delivery"], "llm_judge.decision_grounding": ["data_processing", "reasoning_planning"], "llm_judge.localization_consistency": ["content_generation"], "llm_judge.scope_and_promises": ["reasoning_planning"], "llm_judge.usable_handoff": ["verification_delivery"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-hard"}
---

# 多语言支持知识包的事实一致性

## Prompt

请更新NoriDesk的中文、英文、越南语支持知识包，并为18个情境提供可使用的回复草稿。所有产品信息以本题固定发布说明为准，不补充外部产品事实，不作超出已知范围的承诺。

读取 /tmp_workspace/release_notes.md、/tmp_workspace/faq_old/zh.md、/tmp_workspace/faq_old/en.md、/tmp_workspace/faq_old/vi.md、/tmp_workspace/support_cases.csv 和 /tmp_workspace/terms.csv。判断时点采用发布说明的固定时点；context_json中的空值表示未知。发布说明效力高于旧FAQ，术语表不改变功能政策。禁止的是无依据的命题，引用或明确否定旧错误说法可以保留其字面。

交付四份实际文件：

1. /tmp_workspace/results/faq_zh.docx、/tmp_workspace/results/faq_en.docx、/tmp_workspace/results/faq_vi.docx：分别为原生可编辑的中、英、越FAQ。每份保留K01–K12共12个主题，逐项纠正旧口径，清楚说明当前支持范围、条件、边界、临时绕过、未发布和未知事项。每个主题以可见的Kxx编号开始，有本语种题目、完整回答和相关发布说明定位（release_notes.md#Fxx）。可以调整主题顺序、段落或表格、样式和分页，不要求旧稿逐字翻译。不同语言保持事实、限制、否定和非承诺的一致，专业名词按terms.csv；套餐、角色、版本、地区、单位和credits标签准确保留。避免把版本号等同已获准预览、申请等同批准、临时绕过等同已修复、未知等同0或不存在，也不把某功能门槛扩展为另一功能的要求。

2. /tmp_workspace/results/case_replies.csv：UTF-8 CSV，每个case_id恰好一行，覆盖18个情境。至少含case_id、locale、topic_id、decision、reply、source_refs。标识和语种对应输入，reply使用该情境语种，写出有依据的判断、限制和可执行下一步；source_refs用release_notes.md#Fxx，多个定位可用分号，须支持本条实际主张。行列顺序可变，可加说明列。CSV表格中的结构化状态不能替代回复正文的真实含义。

decision从以下短码中选择：supported（满足当前给定支持条件）、supported_text_only（仅文本/元数据范围支持）、per_file_limit（单文件超限）、file_count_limit（批文件数超限）、batch_size_limit（批总量超限）、role_not_allowed（当前角色不能办理）、export_row_limit（导出行数超限）、preview_conditions_not_met（未满足预览条件）、workaround_only（仅提供临时绕过）、online_reauth_required（需联网重新验证）、refund_review（符合标准申请条件，仅可进入退款审核）、standard_policy_not_met（未满足标准申请条件，交账单核实）、feature_not_released（所需功能尚未发布）、enterprise_required（套餐不足）、retention_expired（记录超过保留期）、manual_assessment_only（仅可申请人工评估）、reseller_review（转售商渠道审核）。短码表达分流，不表达实际操作、审批或金额已确定。

回复要分别核对单文件/数量/总量、权限与套餐行数、稳定与预览资格、离线窗口与记录保留、自然日与工作日、退款申请与实际批准。未知的退款金额、恢复可能性、实际迁移结果和未发布日期不得猜测，不用0填补未知；已知限制也不扩展成材料未给的全面否定。保留支持人员能继续核实的下一步。

全部原输入只读，保持原字节；新交付写 /tmp_workspace/results，可使用系统临时目录制作。离线完成，不访问真实账号、不联网、不发送回复、不改角色权限、不代办退款或迁移、不创建定时任务。保存前检查三语一致性、18条唯一性、来源、原生可编辑性和实际可读性。

## Expected Behavior

按固定事实和18个已知情境更新三语FAQ与回复，保持事实、否定、范围、术语及非承诺一致，提供真实可编辑且可追溯的四交付。

## Grading Criteria

### Automated group

- [ ] `case_routing`: 核对18条公开短码、语种及主题与独立情境真值；只核结构化判断，不据此认定回复语义正确。
- [ ] `faq_coverage`: 从实际可编辑Word正文核三语各12个可见K主题及非空回答，允许主题顺序和段落/表格变化；不以覆盖替代事实正确。
- [ ] `delivery_integrity`: 三Word可解析、无未决修订，实际Office导出文字可见且不越页；18条CSV唯一完整，输入保持原字节。
- [ ] `evidence_binding`: FAQ和回复均引用真实发布说明的相关主事实ID；自动只核实体定位，完整支持关系由语义裁判检查。

### Judge group

- [ ] `decision_grounding`: 独立读取六源、36条实际Word回答及18条回复，逐单元与最高效力发布说明和语言无关允许/禁止/未知命题比较。按54单元的事实完成度取均值：完整准确1，只有不改变判断的非关键解释遗漏0.5，关键数值/范围/条件/结论错误或缺交0；这些档位是单元锚点，最终可连续评分。实际正文与结构化短码矛盾时按正文事实判，不把自动满分当作通过。
- [ ] `scope_and_promises`: 核对P01–P07七组禁用命题在所有相关FAQ/回复中的真实语义，以及SSO和迁移条件、每次导出与未单列导入上限两组范围。九组等权：所有相关出现均正确且关键限制完整1，只有非关键解释不足0.5，任一错误承诺/相反极性/缺失关键限制0；取均值。明确否定或纠正错误命题不失分。未知不自动为真或假，申请、审核、目标均不等于现实完成。
- [ ] `localization_consistency`: 检查三套Word及对应回复的实际语种、术语、指代和自然表达；逐主题比较三语事实、条件、否定与未知是否一致。按12个FAQ主题和18条回复的30单元等权，语种/术语正确且可理解1，非关键语言不自然但不改意义0.5，错误语种、难以理解或改变业务含义0。事实错误可同时影响本地化语义，但不得要求作者逐字措辞或自称母语专家。
- [ ] `usable_handoff`: 实际检查原生Word、CSV和绑定的Office预览；判断支持人员能否定位主题、复核本条依据和继续办理。接受等价布局与措辞。预览文字提取只证明局部可见，裁判仍须检查实际版面；正确但与主张无关的Fxx定位不算证据支持。

## Automated Checks

```python
def grade(**kwargs) -> dict:
    from pathlib import Path
    import runpy
    import pdfplumber
    root=Path(kwargs.get("workspace_path") or "/tmp_workspace")
    values=runpy.run_path(str(root/"gt/grader.py"))["grade"](root)
    return {key:values[key] for key in ("case_routing","faq_coverage","delivery_integrity","evidence_binding","overall_score")}
```

## LLM Judge Rubric

### Criterion 1: 三语事实与情境判断 (key: decision_grounding, weight: 0.5)

判据：独立读取六源、36条实际Word回答及18条回复，逐单元与最高效力发布说明和语言无关允许/禁止/未知命题比较。按54单元的事实完成度取均值：完整准确1，只有不改变判断的非关键解释遗漏0.5，关键数值/范围/条件/结论错误或缺交0；这些档位是单元锚点，最终可连续评分。实际正文与结构化短码矛盾时按正文事实判，不把自动满分当作通过。

**Score 1.0**: 全部54单元均有材料支持，数值、单位、版本/渠道、套餐、角色、地区、边界和情境分流准确，旧口径已纠正。

**Score 0.5**: 54单元按逐项锚点计算的平均事实完成度为0.5；需列出缺失或错误单元及真实依据。

**Score 0.0**: 没有可核验正确单元，或实际核心文本全部缺失/无关；不能从文件名、ID、关键词或正确短码补事实分。

### Criterion 2: 否定范围与非承诺边界 (key: scope_and_promises, weight: 0.25)

判据：核对P01–P07七组禁用命题在所有相关FAQ/回复中的真实语义，以及SSO和迁移条件、每次导出与未单列导入上限两组范围。九组等权：所有相关出现均正确且关键限制完整1，只有非关键解释不足0.5，任一错误承诺/相反极性/缺失关键限制0；取均值。明确否定或纠正错误命题不失分。未知不自动为真或假，申请、审核、目标均不等于现实完成。

**Score 1.0**: 九组范围和限制均正确；无即时全额退款、实际审批/迁移/授权、OCR发布、Windows已修、数据已删除/备份必恢复、全量CSV/无限行或两工作日解决承诺。自然日与工作日、离线与保留期、导出上限与未知导入上限均区分。

**Score 0.5**: 按九组锚点取平均为0.5，须具体指出错误组、出现位置、极性和源事实；不能凭禁用字符串下结论。

**Score 0.0**: 九组均错误、关键限制均未表达，或没有可核验实际内容；未知金额填确认0、把未承诺当实际不存在等按对应组记错。

### Criterion 3: 本地化与跨语种一致性 (key: localization_consistency, weight: 0.15)

判据：检查三套Word及对应回复的实际语种、术语、指代和自然表达；逐主题比较三语事实、条件、否定与未知是否一致。按12个FAQ主题和18条回复的30单元等权，语种/术语正确且可理解1，非关键语言不自然但不改意义0.5，错误语种、难以理解或改变业务含义0。事实错误可同时影响本地化语义，但不得要求作者逐字措辞或自称母语专家。

**Score 1.0**: 30单元均使用指定语种且自然可理解，术语准确，三语保留相同事实和否定限制，无错误指代或误译造成的额外承诺。

**Score 0.5**: 按30单元锚点计算语言与一致性完成度平均为0.5，须定位实际措辞问题及影响。

**Score 0.0**: 所有指定语种内容缺失/不可理解，或全部业务含义发生错误变化。

### Criterion 4: 可用知识包与回复交接 (key: usable_handoff, weight: 0.1)

判据：实际检查原生Word、CSV和绑定的Office预览；判断支持人员能否定位主题、复核本条依据和继续办理。接受等价布局与措辞。预览文字提取只证明局部可见，裁判仍须检查实际版面；正确但与主张无关的Fxx定位不算证据支持。

**Score 1.0**: 三FAQ和18回复完整可编辑/可使用，真实内容清晰可读，来源支持对应判断、范围和下一步，未知与待核实交接明确；没有假装发送或完成现实操作。

**Score 0.5**: 主要内容可用且判断可追溯，仅非关键排版、来源定位或下一步交接不足，不影响主要办理。

**Score 0.0**: 主要交付缺失/损坏/隐藏或不可读、内容对象无法对应、证据不支持关键主张、无法继续办理，或依赖聊天自述补齐。

## Workspace Path

```
datasets/general-hard/workspace/office_documents/general_hard_office_documents_task_014_support_localization
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- 全部产品、事实与情境为合成固定资料，仅GDPval方法启发，无线上原型；纯文本、离线、非代码主交付，L4为设计预估，不增加6题视觉输入配额。
- 源真值先于参考，18情境以两套数值/日期/谓词路径核验，另255条边界核验。用户明确授权中英越各一名模型代理替代人工复核，最终zh/en第2轮、vi第3轮各18接受；保留全部原始分歧、修订与来源SHA。不是人工、母语专家或每语种双标。
- 正式采用自动.25/语义.75，修订原蓝图自动.75/语义.25草案。否定、范围和非承诺须读完整意义，自动只核公开结构、分流、实体定位和实际Office可见文字；作者规则1.0不能代表语义或总分。
- 规则内部case_routing/faq_coverage/delivery_integrity/evidence_binding按.45/.20/.20/.15加权。语义按54事实单元、9组边界及30语言单元锚点取均值，交接独立判断，接受事实等价表达。
- {'positive': 3, 'negative': 14, 'semantic_only': 4, 'infrastructure': 4}实际Office/CSV控制；semantic_only仅检验自动规则的明确边界，源依据上的预期失败不是已执行的独立Judge评分。
- 缺GT/helper/评分依赖/环境锁或引擎漂移属于评测异常，无能力分；缺交、损坏、重复、错误分流和输入被改按相关检查点计分。宏/主动外链超出被动Office Profile须显式异常，不猜零分。
- 900仅任务元数据，不作为候选总执行截止或能力扣分条件；仍待四端实际预检、独立语义评分和难度/区分度校准。
