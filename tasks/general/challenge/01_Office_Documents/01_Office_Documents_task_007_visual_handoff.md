---
id: 01_Office_Documents_task_007_visual_handoff
name: 截图批注驱动的交接稿修订
category: office_documents
timeout_seconds: 900
modality: multimodal
attachment_size_limit_mb: 5
difficulty: L3
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
    - path: results/handoff_revised.docx
      role: candidate_deliverable
    - path: results/visual_changes.json
      role: candidate_deliverable
dataset_report: {"category": "office_documents", "category_name": "文档与办公交付", "category_order": 0, "checkpoint_capabilities": {"automated.boundary_cases": ["reasoning_planning"], "automated.business_correctness": ["data_processing"], "automated.delivery_integrity": ["verification_delivery"], "automated.evidence_binding": ["verification_delivery"], "llm_judge.decision_grounding": ["data_processing"], "llm_judge.usable_handoff": ["verification_delivery"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-challenge"}
---

# 截图批注驱动的交接稿修订

## Prompt

请按截图中的可见批注修订发布交接稿。原稿是 /tmp_workspace/handoff.docx；修改权限与逐处记录格式见 /tmp_workspace/edit_scope.md；三张批注截图为 /tmp_workspace/annotated_pages/page_01.png、page_02.png、page_03.png，按①至⑧各核对一次。机构、岗位与材料均为合成，离线完成，只制作文档。

必须实际理解图片中的圈选、箭头、删除线、划除提案、保留文字和步骤移动关系，按所指对象处理，不能按批注就近位置或全文同词直接替换。edit_scope.md的修改范围优先；越界提案保留原文，并在记录中说明未采纳依据。相似文字、相邻岗位或表格行都要分别核对。步骤调整要改变实际段落顺序并同步编号，不能只在记录中说明。

交付 /tmp_workspace/results/handoff_revised.docx：完整的原生可编辑修订稿，保留原稿的指定页面设置、字体字号/颜色、原生表格和未获授权的内容。不能用截图替代Word正文，不能只交修改片段。保留/删除以所选对象为边界，允许按范围文件给出的等价插入和原生自动编号方式。

交付 /tmp_workspace/results/visual_changes.json：UTF-8逐处记录，数组或含changes数组的对象均可，八项顺序不限；字段和允许的等价表示以edit_scope.md为准。每项写批注编号、原图名和实际SHA-256、动作、源对象定位、修订前后值、批注文字框和所指对象框、说明；移动还需实际落点框与落点前的源对象。坐标按原始1600×1300图片，不能用整张图片当目标框。说明采用、保留或拒绝的图像和范围依据，记录须与真实Word一致，不能代替实际修订。

五份输入原字节保持不变，所有新交付写results，临时材料写results或系统临时目录。不要访问真实账号或实际执行发布、通知、退款、权限变更等业务动作。

## Expected Behavior

读取三张图片并把八处指向与范围映射到实际原稿；完成限定修订、保留与越界拒绝，保持原生格式，逐项给出可回溯图片/源对象/修改结果记录。

## Grading Criteria

### Automated group

- [ ] `business_correctness`: 实际Word中的八处修订、保留/拒绝动作与逐处账本一致，核正文、原生表格与真实步骤顺序，不以记录声明代替文档修改。
- [ ] `boundary_cases`: 核同文不同对象、准备岗与后备岗、局部删除、跨行箭头、撤销提案、相似段落插入、实际步骤与编号、越界提案等控制。
- [ ] `delivery_integrity`: 两项交付完整可解析、原文和指定原生样式/表结构/页面参数保持，未修改五份输入；明确缺失字段而不抹去其它可判项。
- [ ] `evidence_binding`: 八项图片名与源SHA、批注/目标区域及移动落点对应实际输入，拒绝整图框或错行定位；坐标绑定不证明已理解图像。

### Judge group

- [ ] `decision_grounding`: 独立实际查看三张原始图片，沿圈选/实线箭头及移动虚线判断目标、删除/保留和越界限制，核实际Word与JSON。不能仅凭OCR文字、坐标重合、作者参考或候选自述作结论。
- [ ] `usable_handoff`: 核实际可编辑Word与八处修改记录，保留指定页面/字体/原生表和受保护文字，记录能回指输入图片及源对象；接受等价坐标、原生自动编号和允许的行内插入。

## Automated Checks

```python
def grade(**kwargs):
    from pathlib import Path
    import runpy
    root=Path(kwargs.get("workspace_path") or "/tmp_workspace")
    result=runpy.run_path(str(root/"gt/grader.py"))["grade"](root)
    return {key:result[key] for key in ("business_correctness","boundary_cases","delivery_integrity","evidence_binding","overall_score")}
```

## LLM Judge Rubric

### Criterion 1: 图像批注与修订取舍 (key: decision_grounding, weight: 0.7)

判据：独立实际查看三张原始图片，沿圈选/实线箭头及移动虚线判断目标、删除/保留和越界限制，核实际Word与JSON。不能仅凭OCR文字、坐标重合、作者参考或候选自述作结论。

**Score 1.0**: 八项关键图像关系、目标、动作和范围判断均正确；改值/删除/保留/插入/移动与真实Word一致，解释能对应实际可见笔迹，没有把图中文稿提案当实际业务执行。

**Score 0.5**: 八项关键目标、动作、替换/删留内容、步骤关系及范围均正确，仅一项非关键解释或局部区域定位不够清楚；没有关键正文或账本矛盾。

**Score 0.0**: 任一关键对象或箭头落点判断错误、撤销提案被采纳、误删越界段落、关键替换/插入/顺序错误，或仅有OCR/账本声明却未完成真实修订；未查看所依赖的图片时保持未决，不能猜分。

### Criterion 2: 原生交接稿与逐处记录 (key: usable_handoff, weight: 0.3)

判据：核实际可编辑Word与八处修改记录，保留指定页面/字体/原生表和受保护文字，记录能回指输入图片及源对象；接受等价坐标、原生自动编号和允许的行内插入。

**Score 1.0**: 完整修订稿可直接核对，实际内容/步骤编号与八处记录一致；所需原生正文、表格、页面和关键字形可用，来源定位清楚且输入未改。

**Score 0.5**: 主要交付与关键事实/顺序均可使用、无关键矛盾，仅有一处不影响复核的非关键定位、格式或说明问题。

**Score 0.0**: 主要Word缺失/损坏、非原生、不可读或严重版式破坏，记录无法对应或与实际关键修订矛盾，保护内容被改，或交付主要留在聊天中。

## Workspace Path

```
workspace/general/challenge/01_Office_Documents/01_Office_Documents_task_007_visual_handoff
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- 本题是general-hard通用办公与图片理解任务，双标签custom/general-hard；L3与区分度为设计预估，未完成四端或12题校准。
- 仅保留线上意图原型，五份输入和参考均为合成自建；GAIA只作为视觉工具工作流方法参考，不复制原题/素材。
- 私有GT保留两份fork_turns=none的独立模型原始标注、输入SHA、逐项对账及作者像素复核，明确不是人工专家双标注，也不是独立语义Judge。
- 自动规则核真实Word和结构化记录，区域/SHA只作定位与来源依据；Judge须实际读取三张图片及交付，未看图或证据不足保持未决。
- 规则grade入口核真实双记录及输入/图片/复核绑定；缺GT、缺依赖、规则失败或未完成标注门禁保留评测异常，不能补能力零分。
- 46项作者控制和参考规则分不是hybrid完整分数；语义权重25%未调用独立Judge。
