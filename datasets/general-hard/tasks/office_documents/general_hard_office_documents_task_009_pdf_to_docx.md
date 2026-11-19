---
id: general_hard_office_documents_task_009_pdf_to_docx
name: 复杂文本PDF转Word与表格保真
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
    - path: results/converted.docx
      role: candidate_deliverable
    - path: results/conversion_audit.csv
      role: candidate_deliverable
scoring_runtime:
  office: true
  office_render: true
dataset_report: {"category": "office_documents", "category_name": "文档与办公交付", "category_order": 0, "checkpoint_capabilities": {"automated.boundary_cases": ["reasoning_planning"], "automated.business_correctness": ["data_processing"], "automated.delivery_integrity": ["verification_delivery"], "automated.evidence_binding": ["verification_delivery"], "llm_judge.decision_grounding": ["data_processing"], "llm_judge.usable_handoff": ["verification_delivery"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-hard"}
---

# 复杂文本PDF转Word与表格保真

## Prompt

请将 /tmp_workspace/source.pdf 转换为完整、原生可编辑的Word，并完成转换核对。源件是六页可提取文字的合成检验结算说明，不是扫描图片。结构约束及核对单元见 /tmp_workspace/layout_contract.json；离线完成。

交付 /tmp_workspace/results/converted.docx：保留全部原文、可见编号、四张逻辑表的行列/表头层级、原生合并关系、数据/单位、正文顺序和六条真实脚注。不要只摘录或总结，不将整页PDF/截图嵌入Word代替正文、表格或脚注。相同的数值、状态词或段落提示不共享条件；注释应附着在源件所指的实际单元格/段落。

允许合理重分页、列宽与字体选择；T02可为一张连续原生表或连续续表，重复表头/续组提示不计新增业务行。同组跨页边界保持，不根据分页重建分组；内部脚注ID和自动显示编号可变化，但脚注文字保留源Fxx标识与适用对象。普通正文末尾的附注列表不能替代Word原生脚注。表格应在有效页面内可读，正文/表格至少9pt、脚注至少8.5pt，自动引用符号除外；不得靠隐藏、缩成不可读小字或裁切塞入页面。

本次只转换原件，不改写或重算业务记录：保留0、未提供、待核和原展示金额，不推断审批/付款已完成，不根据表内材料名称补造附件。原文页号与“续页”等指向源PDF，重分页后不擅自改成Word页号。

交付 /tmp_workspace/results/conversion_audit.csv：UTF-8可带BOM，按结构契约的32个source_unit各一行，行列顺序不限，允许约定中文列名和源页范围表示。列为source_id、source_pages、source_locator、target_locator、status、issue。源定位指向实际PDF页及源单元；目标按契约指向实际Word段落、表格/单元格或原生注释节点。多个目标节点用分号分隔，续表要覆盖全部实际片段，不能只定位第一段就声称整张T02已转。状态converted/partial/missing及issue说明必须忠实于实际结果；有缺损时记录真实问题和定位，不以声明代替转换。

两个输入原字节保持不变。所有新交付写results，临时材料写results或系统临时目录；不访问网络、真实账号，不实际办理检验、结算、付款或对外确认。

## Expected Behavior

将源六页转换为原生可编辑正文/四表/六真实脚注，保留数据、逻辑关系、顺序与未知状态；合理重排分页并提交真实覆盖32单元的源页→实际Word节点核对。

## Grading Criteria

### Automated group

- [ ] `business_correctness`: 实际原生Word中的正文、四表数据/单位/未知状态和六条真实脚注内容与源PDF一致；以实际渲染可见性约束原生观察，不以审计声明代替转换。
- [ ] `boundary_cases`: 核同值错列/错行、逻辑合并与分组、六条注释实际挂接、正文及记录顺序；接受续表拆分、等价网格细分、不同包内note ID和正文合理分段。
- [ ] `delivery_integrity`: 完整原生Word和32行审计可解析，状态与实际转换一致；可信Writer实际PDF中正文、表格及注释可读，不被图片或隐藏文字替代，输入未改。
- [ ] `evidence_binding`: 审计源页/源ID与两份原始输入一致，目标指向实际Word段落、表格/单元格及原生注释；多个续表片段应覆盖整张逻辑表。

### Judge group

- [ ] `decision_grounding`: 独立对照实际源PDF、结构契约、原生Word和可信派生PDF，核对行列/合并、数值单位、六脚注归属、正文顺序及未知状态。原生XML存在、字词齐全或CSV声明不能单独证明正确转换。
- [ ] `usable_handoff`: 检查实际可用文件及可信PDF中的表格、注释和字形，审计能回指真实节点与源页；允许合理重分页、列宽/字体、续表和内部ID变化，不能将唯一作者版式当作标准。

## Automated Checks

```python
def grade(**kwargs):
    from pathlib import Path
    import runpy
    import pdfplumber
    import pypdf
    root=Path(kwargs.get("workspace_path") or "/tmp_workspace")
    result=runpy.run_path(str(root/"gt/grader.py"))["grade"](root)
    return {key:result[key] for key in ("business_correctness","boundary_cases","delivery_integrity","evidence_binding","overall_score")}
```

## LLM Judge Rubric

### Criterion 1: 转换保真与事实边界 (key: decision_grounding, weight: 0.7)

判据：独立对照实际源PDF、结构契约、原生Word和可信派生PDF，核对行列/合并、数值单位、六脚注归属、正文顺序及未知状态。原生XML存在、字词齐全或CSV声明不能单独证明正确转换。

**Score 1.0**: 所有关键数据和条件可对应原件，表格关系、实际脚注范围及顺序正确，0/未提供/待核保持；审计真实，无未经授权的重算、补造、错位或虚构全转换。

**Score 0.5**: 全部关键数值、单位、分组/合并、脚注及事实范围正确，仅一项非关键说明或定位不足，不影响主要内容理解。

**Score 0.0**: 任一关键数值/单位/未知状态被改造，数据错位、关键合并或脚注范围错误，只有摘要/图片/普通注释列表，或重要原文/整列不可见却声称完整转换；证据缺失时保持未决，不能猜测。

### Criterion 2: 可编辑Word与缺损核对交接 (key: usable_handoff, weight: 0.3)

判据：检查实际可用文件及可信PDF中的表格、注释和字形，审计能回指真实节点与源页；允许合理重分页、列宽/字体、续表和内部ID变化，不能将唯一作者版式当作标准。

**Score 1.0**: 完整原生Word可继续编辑和复核，所需表格/文字/脚注均可读且无关键裁切，32条审计状态真实、节点定位充分、输入未改；源页引用明确指原PDF。

**Score 0.5**: 主要内容完整正确并可交接，仅一处不影响主要复核的非关键版式、定位或说明问题，无关键事实/范围矛盾。

**Score 0.0**: 主要交付缺失/损坏/非原生、文字表格被图片替代或隐藏、重要内容裁切/无法使用、注释关系或审计无法复核，或主要结果只在聊天中。

## Workspace Path

```
datasets/general-hard/workspace/office_documents/general_hard_office_documents_task_009_pdf_to_docx
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- 本题仅WorkBuddy Office方法启发，全部内容合成自建，不复制原题/素材，无新增线上原型；正文PDF无需视觉理解，评分端渲染不改变pure-text归属。
- 原始事实、pypdf文字和pdfplumber实际矩形/数值独立核验均先于参考Word，不从候选或参考产物反推源GT。作者参考不是唯一合法版式/分页。
- 评分需独立DOCX渲染Profile（bootstrap-office-render --document-format docx），明确Office/字体/PDF依赖锁；不能沿用PPTX锁。PDF query所在CLI与规则Worker分别满足依赖。
- 规则观察真实原生节点、合并和注释关系、CSV、实际Writer PDF文字/字号/页界；完整遮挡、对比度、版式可用性和业务事实由独立Judge核验，不能把结构/路径元数据当已看图。
- 36项作者控制及参考规则分不等于hybrid完整分；25%语义尚未独立运行。L3、四端兼容和区分度为待校准设计状态。
- 缺GT/helper、缺/漂移运行时锁/字体/引擎、PDF依赖和规则失败保留评测异常，不补能力零分；正常候选漏交/格式或业务错误由冻结规则分别给分。
- 900为任务元数据，General E2E不据此给候选设能力截止；受管Worker超时属于评测执行异常。
