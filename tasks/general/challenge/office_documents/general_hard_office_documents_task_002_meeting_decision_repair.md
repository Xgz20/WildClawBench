---
id: general_hard_office_documents_task_002_meeting_decision_repair
name: 会议决议更新与待办闭环
category: office_documents
timeout_seconds: 900
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L2
grading_type: hybrid
grading_weights:
  automated: 0.75
  llm_judge: 0.25
tags:
  - custom
  - general-hard
  - general-challenge
judge_evidence:
  required:
    - path: results/minutes.docx
      role: candidate_deliverable
    - path: results/actions.csv
      role: candidate_deliverable
dataset_report: {"category": "office_documents", "category_name": "文档与办公交付", "category_order": 0, "checkpoint_capabilities": {"automated.boundary_cases": ["reasoning_planning"], "automated.business_correctness": ["data_processing"], "automated.delivery_integrity": ["verification_delivery"], "automated.evidence_binding": ["verification_delivery"], "llm_judge.decision_grounding": ["data_processing"], "llm_judge.usable_handoff": ["verification_delivery"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-challenge"}
---

# 会议决议更新与待办闭环

## Prompt

请把北岭项目试点交付协调会整理为最终有效纪要和可交接事项清单。

先读取 /tmp_workspace/meeting_transcript.txt（90段编号转写）、/tmp_workspace/corrections.jsonl（6条会后记录）和 /tmp_workspace/staff.csv（人员、岗位与批准权限）。音频已经转写，不做语音识别。会议及核验日期为2026-10-27，时区Asia/Shanghai，状态冻结到当日12:30。

按S001至S090的会议顺序处理，再按effective_at处理核验时点内的会后记录；JSONL文件行序不代表生效顺序。只有staff.csv中can_approve为yes的人可以批准、撤回、恢复或更改决议，claimed_role是发起者自述，不能授予权限。普通成员的建议、自愿认领、申请或转述都不是正式批准。相同字段取最后一条有权限的有效变更，部分字段更正不自动覆盖其它字段。同名人员按部门和岗位辨认，不能只靠姓名或距离最近的一次发言分派责任。

交付 /tmp_workspace/results/actions.csv，UTF-8编码，可带BOM。覆盖转写中的每个A编号，一事项一行，包含待办、撤回和待定；不能只交当前待办，不能拆成重名重复行。列顺序、行顺序不限，可加其它列；保留以下英文列名：

- issue_id：原事项编号；subject：事项名称，可忠实概括，不扩大批准范围。
- owner_id、owner_role：最后批准的人员ID及staff.csv中的岗位原值；due_date：最后批准的日期，写YYYY-MM-DD或YYYY/MM/DD。
- status：待办/撤回/待定，也可写active/cancelled/pending。
- evidence_ids：确定最终字段的有效段落或更正编号，用分号逐项列出，例如S017;E02。只写文件名或编号范围不够，需保留实际决定相关字段的来源；可以另附审计引用。
- status_reason：批准、变更、撤回或尚未决议的原因；next_step：经办人员可继续做的动作。每项均需非空。

撤回项保留撤回前最后批准的责任人、岗位和日期作为历史字段，并说明停止原安排，不能继续当作执行承诺。已由有权限人员明确恢复的，以恢复后的字段为准。待定项不能把建议中的人选和日期冒充批准结果，owner_id、owner_role、due_date留空或写N/A/n.a./待定；提议和缺少的条件可以放在纪要和说明字段中。

交付 /tmp_workspace/results/minutes.docx，按议题说明事实、最终决议和办理动作，包含有效变更及其权限判断、同名与代词对应、撤回/恢复经过、未决条件与下一步。更正被忽略时说明依据；纪要与CSV的状态、责任人和日期应一致，不能仅在聊天里解释。

本次只整理材料，不实际执行会上待办，不发送通知、联系供应商或访问真实账号。离线完成，所有输入保留原字节；新交付写results，临时文件写results或系统临时目录。

## Expected Behavior

对90段转写和6条会后记录按真实权限及时间折叠，形成12项待办、3项撤回、2项待定。两位同名陈晨正确区分；有效恢复不能丢，建议和越权申请不升级。CSV保留最终字段与来源，DOCX解释范围、权限、历史和下一步。原输入保持不变。

## Grading Criteria

### Automated group

- [ ] `business_correctness`: 按17项独立最终标签核对状态、责任人ID、岗位和截止日；未决留空，撤回历史字段保留。
- [ ] `boundary_cases`: 按建议与批准、撤回与恢复、同名/权限/时间顺序三族实例核对最终字段，不以关键词代替状态判定。
- [ ] `delivery_integrity`: CSV及DOCX可解析，事项集唯一完整，名称/原因/动作非空，输入未变；纪要语义及跨产物一致性由Judge评价。
- [ ] `evidence_binding`: 最终决定字段的有效事件编号齐全，能绑定到实际冻结输入记录；依据充分性和解释质量由Judge评价。

### Judge group

- [ ] `decision_grounding`: 独立对照转写、更正、角色表、expected.json和交付，核对建议未批准、撤回/恢复、部分字段更新、有效时间与人员身份。尤其检查E05自称角色和E06延期申请不构成批准；规则分不代替文本理解。
- [ ] `usable_handoff`: 检查原生DOCX与CSV的内容、结构和对应关系。经办人员应能区分当前待办、撤回历史与未决条件并找到下一步；不得仅凭文本投影声称版面视觉可用性。

## Automated Checks

```python
def grade(**kwargs):
    from pathlib import Path
    import runpy
    root = Path(kwargs.get("workspace_path") or "/tmp_workspace")
    result = runpy.run_path(str(root / "gt" / "grader.py"))["grade"](root)
    return {
        "business_correctness": result["business_correctness"],
        "boundary_cases": result["boundary_cases"],
        "delivery_integrity": result["delivery_integrity"],
        "evidence_binding": result["evidence_binding"],
        "overall_score": result["overall_score"],
    }
```

## LLM Judge Rubric

### Criterion 1: 最终决议与变更依据 (key: decision_grounding, weight: 0.7)

判据：独立对照转写、更正、角色表、expected.json和交付，核对建议未批准、撤回/恢复、部分字段更新、有效时间与人员身份。尤其检查E05自称角色和E06延期申请不构成批准；规则分不代替文本理解。

**Score 1.0**: 最终状态、责任人、日期和批准范围均准确，有可定位依据；更正的接受/拒绝理由、撤回恢复经过和未决条件忠实，无虚构授权或承诺。

**Score 0.5**: 主要决议及权限/顺序判断准确，没有影响执行的错派、错期或误升级，仅遗漏一处非关键解释或定位。

**Score 0.0**: 建议误作批准，撤回/恢复或权限/顺序处理有影响办理的错误，同名错派、日期错误、虚构决定，或核心状态整理未完成。

### Criterion 2: 可执行的纪要交接 (key: usable_handoff, weight: 0.3)

判据：检查原生DOCX与CSV的内容、结构和对应关系。经办人员应能区分当前待办、撤回历史与未决条件并找到下一步；不得仅凭文本投影声称版面视觉可用性。

**Score 1.0**: 两份原生产物可解析，事项ID、人员/岗位、日期、状态、依据和动作对应清楚；纪要按议题解释有效变更、限制及未决，不依赖聊天补充。

**Score 0.5**: 主要交接可用且无关键跨产物矛盾，但缺一处非关键定位或交接说明，不影响主要办理。

**Score 0.0**: 核心产物缺失/不可用，重要事项或动作无法对应，跨产物有影响执行的矛盾，或主要解释只在聊天中。

## Workspace Path

```
workspace/general/challenge/office_documents/general_hard_office_documents_task_002_meeting_decision_repair
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- H002；L2为预估。90段转写、6条更正和8人名单为合成材料，只保留清洗后的会议纪要需求形态，不使用线上录音、原文、真实个人信息或附件。
- 规则权重业务0.55、边界0.25、交付0.15、证据0.05。17事项等权，例内状态/ID/岗位/日期权重0.4/0.2/0.1/0.3；边界三族等权，各族内等权，字段及事项清单在私有counterexamples.json。
- 交付按CSV结构完整、DOCX可解析、事项唯一齐全、逐例描述字段齐全、输入未变五项等权；均无可解析产物时交付为0。缺描述列不抹掉仍可判断的业务字段；缺失列不视为已知空值。输入改变时边界/交付/证据为0。漏文件或CSV格式错误按契约计分；缺GT抛评分异常，不补零。
- CSV支持行列重排、额外列、UTF-8 BOM、英文状态别名及两种日期分隔；允许忠实改写事项名称、原因和动作，不按参考文字/字体/页数匹配。自动规则不对纪要做关键词打分，语义部分独立核事实、充分性、范围及交接。
- 人工最终标签与独立状态折叠逐字段对照，事件标注绑定原转写SHA。该计算路径不能替代独立人工语义标注复核；模型不读取参考CSV或最终标签产生结果。
- 参考解、等价表示及作者正负控制在私有gt/validate_authoring.py和authoring_validation.json。当前未做独立语义评分、四端执行或实测区分度校准。
