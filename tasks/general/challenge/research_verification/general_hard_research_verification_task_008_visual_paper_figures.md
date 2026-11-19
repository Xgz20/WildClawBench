---
id: general_hard_research_verification_task_008_visual_paper_figures
name: 论文图形证据与文字结论一致性
category: research_verification
timeout_seconds: 900
modality: multimodal
attachment_size_limit_mb: 5
difficulty: L4
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
    - path: results/figure_review.xlsx
      role: candidate_deliverable
    - path: results/review_notes.docx
      role: candidate_deliverable
scoring_runtime:
  office: true
dataset_report: {"category": "research_verification", "category_name": "研究检索与证据核验", "category_order": 2, "checkpoint_capabilities": {"automated.boundary_cases": ["reasoning_planning"], "automated.business_correctness": ["retrieval_verification"], "automated.delivery_integrity": ["verification_delivery"], "automated.evidence_binding": ["retrieval_verification"], "llm_judge.decision_grounding": ["retrieval_verification"], "llm_judge.usable_handoff": ["verification_delivery"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-challenge"}
---

# 论文图形证据与文字结论一致性

## Prompt

仅依据本题本地四张原始实验图与paper_excerpts.md，逐项核对8项论述的图形关系、误差区间、轴尺度、图例和实验条件。材料是原创受控虚构研究记录，不对应现实模型或人类实验。

先读取 /tmp_workspace/delivery_contract.md。原图位于 /tmp_workspace/figures/，文字方法与8项待核验论述位于 /tmp_workspace/paper_excerpts.md，可判精度位于 /tmp_workspace/reading_tolerance.json。必须实际读取原图；文件名、OCR文字或论述中写出的数字不能替代读图。

交付 /tmp_workspace/results/figure_review.xlsx：原生可见、可编辑、自包含的8项核验矩阵，保留实际判断对象、判断、读数或范围和单位、轴与图例条件、局部原图位置、对应E段及限制。允许清楚的逻辑分表、合表、重排、长/宽/转置表或内联读数，不要求特定Sheet/单元格、全部28点或公式。

交付 /tmp_workspace/results/review_notes.docx：原生可编辑说明，可按论述或主题解释可保留/需修正的结论、替代解释、未知及下一步核查。两产物应在同一判断对象和范围上相容，不必机械镜像。

每项图形依据绑定实际原图文件与可辨局部，支持delivery_contract.md说明的像素/归一化框、多边形、点位与必要轴/图例/标记上下文。轴或图例须结合相关点、误差端点或点组，不用整图框或孤立数字替代证据。数值按reading_tolerance.json处理；未知不填零，不编造缺失检验、质量或因果实验。区分事实、证据充分性及复合命题；可分项判断，但不能只换标签逃避可见反证。

离线完成，仅访问本题材料；不跟随链接联网，不访问真实账号、不发消息、不调用付费接口。全部输入只读保持原字节，所有新交付只写results。

## Expected Behavior

实际读取四图并完整核验8项图文主张，保持读数、设置、轴尺度、单位、图例、SD及方法条件；区分描述、证据充分性、统计/质量/因果未知和组内直接反证。交付两件原生可回查、同范围相容的产物。来源真值先于参考冻结；模型复核非人类专家意见。

## Grading Criteria

### Automated group

- [ ] `business_correctness`: 核8项原论述的可观察读数与描述性判断；按实际系列、设置、单位及公开容差检验近似值/有信息量范围，核已报告SD端点。允许最小必要读数、不同逻辑布局及明确内联读数，不要求照抄28点或参考单元格。
- [ ] `boundary_cases`: 核对数预算增量、SD交叠的统计限制、耗时与未知质量、组内直接图形反证及真实因果未知；区分事实、元命题与复合命题，不能只换标签抹去反证。
- [ ] `delivery_integrity`: 两件原生可见可编辑且自包含的交付可读，原始与公开辅助输入保持字节，核同一对象/范围的明确跨产物转写冲突；Word允许主题组织，不强制重复Excel结构。
- [ ] `evidence_binding`: 固定8个论述绑定机会，核四张实际原PNG的SHA/解码、候选局部区域与真实轴/图例/标记/SD/点组对应；整图框、漏图或错图不能无条件满分。机械绑定不证明真正看图或科学解释。

### Judge group

- [ ] `decision_grounding`: 独立打开全部四张原PNG并结合E01至E04、源先行区间及公开容差核8项论证；不把自动高分、SHA、标签、OCR或坐标命中当实际看图或科学正确证明。事实和证明充分性分别判断，C07不得用泛化不确定性略去两组内可见向下反证。
- [ ] `usable_handoff`: 下游能从两件原生产物恢复8项原论述、实际判断对象、读数条件、原图局部、文字位置、限制与未决项；允许主题汇总和逻辑链接，不要求镜像模板。

## Automated Checks

```python
def grade(**kwargs) -> dict:
    import runpy
    from pathlib import Path
    root = Path(kwargs.get("workspace_path") or "/tmp_workspace")
    result = runpy.run_path(str(root / "gt/grader.py"))["grade"](workspace_path=str(root), transcript=kwargs.get("transcript"))
    return {"business_correctness": result["business_correctness"],
            "boundary_cases": result["boundary_cases"],
            "delivery_integrity": result["delivery_integrity"],
            "evidence_binding": result["evidence_binding"],
            "overall_score": result["overall_score"]}
```

## LLM Judge Rubric

### Criterion 1: 结论有实际图文依据 (key: decision_grounding, weight: 0.7)

判据：独立打开全部四张原PNG并结合E01至E04、源先行区间及公开容差核8项论证；不把自动高分、SHA、标签、OCR或坐标命中当实际看图或科学正确证明。事实和证明充分性分别判断，C07不得用泛化不确定性略去两组内可见向下反证。

**Score 1.0**: 8项的关键读数、轴/单位/图例、SD与实验条件及论证均获实际原图和E段支持；C04保留统计事实未知并拒绝交叠已证明，C06保留质量未知并拒绝由时延证明质量，C07保留合并正/组内负及因果未知；无编造实验或无条件外推。

**Score 0.5**: 主要图形结论与事实/证明边界成立，未虚构关键数据，但遗漏非关键解释、局部定位或继续验证条件；合理的命题范围、措辞和布局差异不扣为科学错误。

**Score 0.0**: 关键结论被原图反驳，错误读取对数轴、单位或SD，虚构显著性/质量/因果实测，或未对主要原论述作实质核验。

### Criterion 2: 产物可继续复核 (key: usable_handoff, weight: 0.3)

判据：下游能从两件原生产物恢复8项原论述、实际判断对象、读数条件、原图局部、文字位置、限制与未决项；允许主题汇总和逻辑链接，不要求镜像模板。

**Score 1.0**: 两件原生产物可用，8项均有可回查的图文依据、单位/设置/对象和限制，替代解释与下一步清楚，同范围内容一致。

**Score 0.5**: 核心交付及8项仍可对应，缺少非关键定位或交接细节，不影响主要复核。

**Score 0.0**: 主要交付不可用、主要原论述无法对应、来源定位不成立或同一对象/范围的跨产物矛盾阻断复核。

## Workspace Path

```
workspace/general/challenge/research_verification/general_hard_research_verification_task_008_visual_paper_figures
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- L4为设计估计，900秒为元数据；作者Worker控制不等于四端Harness可用性、多模型区分度或正式评分。
- A=.55业务+.25边界+.15交付+.05绑定；S=.70结论依据+.30交接；正式hybrid=.75A+.25S。未运行独立Judge不得产生hybrid。
- 现有6输入、28份源先行GT及原参考逐字节保留；新增公开交付合同和私有辅助规则。
- 自动观察是有界解析；合法但未支持的表示/命题范围为typed待独立复核，不填候选0或自动满分。缺私有来源/GT/helper/解码器/Office能力为评测异常；候选漏交、明确错误或保护输入变更按业务契约失分。
- 四张原图在GT/source_originals/figures中按原SHA冻结，semantic Judge必须打开相同图像；缺图/解码/传输不完备应停止为评测输入异常。坐标或SHA本身不能机械证明候选实际看过图。
- 参考仅为非盲作者示例与作者控制输入，不是规则读取的oracle。允许合理等价措辞、单位换算、区间、布局、判断对象和区域。
- 输入保护违规仅归delivery_integrity中的intact机会；私有原图仍允许独立核科学/数值/绑定，不将单一输入违规扩为自动四项总清零。
