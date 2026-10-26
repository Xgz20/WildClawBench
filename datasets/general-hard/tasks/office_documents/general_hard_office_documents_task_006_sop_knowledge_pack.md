---
id: general_hard_office_documents_task_006_sop_knowledge_pack
name: 跨部门SOP整合与双受众交接
category: office_documents
timeout_seconds: 900
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L3
grading_type: hybrid
grading_weights:
  automated: 0.75
  llm_judge: 0.25
tags:
  - custom
  - general-hard
judge_evidence:
  required:
    - path: results/operator.docx
      role: candidate_deliverable
    - path: results/supervisor.docx
      role: candidate_deliverable
    - path: results/coverage.csv
      role: candidate_deliverable
dataset_report: {"category": "office_documents", "category_name": "文档与办公交付", "category_order": 0, "checkpoint_capabilities": {"automated.boundary_cases": ["reasoning_planning"], "automated.business_correctness": ["data_processing"], "automated.delivery_integrity": ["verification_delivery"], "automated.evidence_binding": ["verification_delivery"], "llm_judge.decision_grounding": ["data_processing"], "llm_judge.usable_handoff": ["verification_delivery"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-hard"}
---

# 跨部门SOP整合与双受众交接

## Prompt

请为澄川售后服务中心制作两套统一退款SOP手册，供操作员受理和主管处理异常。输入为 /tmp_workspace/manuals/ 下6份可提取文本DOCX、/tmp_workspace/authority.yaml 的职权域/冲突裁决与逻辑依赖，以及 /tmp_workspace/incidents.csv 的10个当前情境。全部机构、业务和材料均为合成；离线完成。

operator.docx写成操作员可查用的手册：说明入口、岗位、常规步骤、异常分支和当前安全交接终点。supervisor.docx面向主管：说明冲突如何裁决、审批/执行/解除各自归属、不同事件时限、升级和恢复条件。整合为可用流程，不把6份原文简单拼接或把历史冲突并列为任选口径。文件日期不能代替授权规则。没有批准、验收、解除或付款回执，不假设它们已经发生。

交付到 /tmp_workspace/results/operator.docx、/tmp_workspace/results/supervisor.docx 和 /tmp_workspace/results/coverage.csv。两份DOCX保留原生可编辑正文和表格。至少用原生表覆盖全部10个情境：操作员表提供incident_id、route、next_owner、clock_state、operator_action；主管表提供incident_id、approval_owner、execution_owner、ack_hours、inspection_workdays、payment_workdays、clearance_roles、supervision_action。允许中文表头、角色/步骤字典名称、行列重排、分表和自定章节名，按同一incident_id汇合字段即可；动作说明需足以继续办理，不能只有代码。

coverage.csv使用UTF-8，可带BOM，字段为incident_id、route、next_owner、approval_owner、execution_owner、ack_hours、inspection_workdays、payment_workdays、clock_state、clearance_roles、steps、forbidden_steps、operator_ref、supervisor_ref、source_refs、explanation；允许对应中文别名及行列重排。同一情境不得出现相互冲突的字段。时限分别用工作小时/工作日的数值；集合无序，空集合用空白或N/A，保留相应列。字段、路线、角色和步骤语义见authority.yaml。

steps以分号列逻辑路径，只到当前安全终点；表达依赖而非已执行记录，不重复办理已有节点。无依赖边的并行步骤可交换顺序。forbidden_steps列本情境禁止动作。approval_owner为金额审批职能归属、execution_owner为满足门禁后的执行归属、clearance_roles为异常仍需的解除确认；它们互不替代，不表示动作已发生。

operator_ref、supervisor_ref使用对应DOCX文件名#实际可见章节或锚点；多个用分号分隔，实际章节中的原生表须包含该情境对应受众的全部字段，不能只引用存在的无关标题。source_refs用输入文件#条款/控制项或incidents.csv#情境编号，可有多个；应覆盖有效时限、权限、流程及本情境适用异常的实际依据，支持条款也应保留。explanation说明裁决及下一步。

只制作交接材料，不访问真实账号、发送消息、变更权限或执行退款。结论区分事实、建议和未知。输入原字节保持不变，所有新文件写results，临时材料写results或系统临时目录。

## Expected Behavior

按职权域而非文档日期整合SOP，独立判10情境当前安全路径、岗位、时限、时钟与解除要求，保留合法偏序和未知；完成两套原生手册及实际来源/章节映射。

## Grading Criteria

### Automated group

- [ ] `business_correctness`: 逐情境独立核CSV路线、岗位、时限、时钟、解除集合、步骤DAG及禁止动作；另核两份原生DOCX中的受众字段，缺列不抹去其它可判字段。
- [ ] `boundary_cases`: 核5000审批/执行、签收与验收区分、独立风险解除、时钟接续、重复关联、撤回与当前账户，以及全部路径偏序和安全终点。
- [ ] `delivery_integrity`: 三份交付可解析、10情境及字段齐全、动作说明存在且输入字节未改；自然语言正确性由独立Judge核验。
- [ ] `evidence_binding`: 逐情境核实际来源条款覆盖、源SHA及两份手册实际章节内的相应字段；仅有同名标题或真实但无关引用不能替代依据。

### Judge group

- [ ] `decision_grounding`: 独立读取6份源手册、authority和情境，核两份手册及CSV的实际含义。不能以结构化字段正确或规则分代替正文真实性。检查三种事件时限、审批/执行分离、5000边界、先验收后有效书面批准、安全/隐私独立解除、重复关联、撤回/账户复核和暂停接续。
- [ ] `usable_handoff`: 核操作员是否能找到实际入口和下一步，主管是否能处理异常、升级与恢复；引用是否支撑办理说明。允许不同章节、表拆分、拓扑顺序及措辞，不按关键词或参考稿逐字匹配。

## Automated Checks

```python
def grade(**kwargs):
    from pathlib import Path
    import runpy
    root = Path(kwargs.get("workspace_path") or "/tmp_workspace")
    result = runpy.run_path(str(root / "gt" / "grader.py"))["grade"](root)
    return {"business_correctness": result["business_correctness"], "boundary_cases": result["boundary_cases"],
            "delivery_integrity": result["delivery_integrity"], "evidence_binding": result["evidence_binding"], "overall_score": result["overall_score"]}
```

## LLM Judge Rubric

### Criterion 1: 权限裁决与办理事实 (key: decision_grounding, weight: 0.7)

判据：独立读取6份源手册、authority和情境，核两份手册及CSV的实际含义。不能以结构化字段正确或规则分代替正文真实性。检查三种事件时限、审批/执行分离、5000边界、先验收后有效书面批准、安全/隐私独立解除、重复关联、撤回/账户复核和暂停接续。

**Score 1.0**: 关键流程、权限、时限及异常均有正确来源和裁决，三份交付无关键矛盾；无回执不说已付款，无解除不说已恢复；事实、下一步和未知明确。

**Score 0.5**: 核心路径和权限成立，无未授权付款/解除、关键时钟错误或跨产物矛盾，仅遗漏一处不影响办理的非关键说明。

**Score 0.0**: 跨域按最新日期裁决、混淆审批执行、允许先付/未验收、风险未解除即放行、重置时钟、撤回直接关单、重复另建，或正文虚构已付款/解除等关键事实；核心业务未完成。

### Criterion 2: 双受众流程与可复核交接 (key: usable_handoff, weight: 0.3)

判据：核操作员是否能找到实际入口和下一步，主管是否能处理异常、升级与恢复；引用是否支撑办理说明。允许不同章节、表拆分、拓扑顺序及措辞，不按关键词或参考稿逐字匹配。

**Score 1.0**: 两套手册分别满足受众需要，常规与异常可查用，10情境可定位，步骤和交接/恢复条件清楚，依据可复核；不是原文拼贴或仅表格代码。

**Score 0.5**: 主要交接可继续办理，受众及情境清楚，只有一处非关键入口/定位/说明遗漏，不影响关键异常处理。

**Score 0.0**: 主要手册缺失/无法使用，仅拼贴冲突原文，受众不分、关键动作或升级条件无法判断，跨产物不能对应，或主要解释仅在聊天中。

## Workspace Path

```
datasets/general-hard/workspace/office_documents/general_hard_office_documents_task_006_sop_knowledge_pack
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- H006；L3为设计预估；仅GDPval职业工作包/交付核验方法启发，全部素材与主体为自有合成，不复制原题、附件或线上Query，不计自然线上原型。
- hybrid规则75%/语义25%。规则内业务0.55、边界0.25、交付0.15、证据0.05。业务为CSV字段均值0.6、操作员3字段均值0.2、主管6字段均值0.2；全部按10情境平均。具体字段及边界组见私有business_oracle/counterexamples。
- 引用字段只证明定位/来源覆盖；自然语言含义、是否有效整合和未授权承诺必须独立Judge。作者语义负例故意保持类型字段正确，规则仍1.0，不冒充完整hybrid合格。
- 空集合与缺列分开；字段冲突仅使该字段失分，合理别名、BOM、拆表及行列重排不扣。路径按所需节点集合、唯一性、偏序与当前安全终点验证，不绑定唯一序列。
- 独立标签、控制流及物理来源复算先于评分，不由参考产物生成GT；作者计算交叉验证不是第二专家审阅或四端实测。
- 规则及DOCX文本helper只用Python标准库，无网络、LLM、Office或新依赖。素材与参考稿已经作者渲染检查；文本字段规则不证明完整视觉版式或语义正确。
- 缺GT/helper或评分崩溃保留评测异常；候选漏交按字段计分。改输入使边界、交付及证据归零，业务字段单独保留。此题没有正式Harness执行、独立语义评分或实测难度结论。
