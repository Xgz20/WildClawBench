---
id: 02_Data_Analysis_task_006_visual_chart_audit
name: 仅图形可见的指标口径核对
category: data_analysis
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
    - path: results/claims_review.xlsx
      role: candidate_deliverable
    - path: results/findings.md
      role: candidate_deliverable
scoring_runtime:
  office: true
dataset_report: {"category": "data_analysis", "category_name": "数据分析与表格建模", "category_order": 1, "checkpoint_capabilities": {"automated.boundary_cases": ["reasoning_planning"], "automated.business_correctness": ["data_processing"], "automated.delivery_integrity": ["verification_delivery"], "automated.evidence_binding": ["retrieval_verification"], "llm_judge.decision_grounding": ["data_processing", "reasoning_planning"], "llm_judge.usable_handoff": ["verification_delivery"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-challenge"}
---

# 仅图形可见的指标口径核对

## Prompt

请核对四张业务指标图中的8项主张，并交付可复核的原生审核底稿。不要补查外部经营数据或假定原图没有给出的原始数值。

读取 /tmp_workspace/chart_pages/chart_A.png、/tmp_workspace/chart_pages/chart_B.png、/tmp_workspace/chart_pages/chart_C.png、/tmp_workspace/chart_pages/chart_D.png 四张原图，以及 /tmp_workspace/claims.docx 与 /tmp_workspace/reading_rules.md。必须实际读取图片；文字提取、图名或主张中写出的数字不能代替曲线、色块、坐标轴、图例与脚注。题面中的句子是待核对主张，不是事实。C06以实际人数是否落在指定范围内为核对对象，不把“不能确认”自动当作实际数值已被反证。

交付两份实际文件：

1. /tmp_workspace/results/claims_review.xlsx：原生可编辑审核工作簿，完整覆盖C01–C08八项判断和reading_rules.md的R01–R20二十项读数。主张记录至少含claim_id、decision、reason、source_file及source_regions，可用reading_ids关联本表中有真实区域定位的读数；decision为supported／支持、refuted／反驳、uncertain／证据不足。复合主张须区分可观察部分与无依据的扩展，解释为什么支持、被反证或无法确认/排除。
读数记录至少有reading_id、axis、unit、lower、upper、source_file与区域/计算依据；对象和时点可按R编号对应，也可另列metric、period。lower/upper用实际数值，不以一个点估计冒充区间。支持单位换算与原生百分比格式，例如0.08配百分比格式、8配%单位或0.08配比例单位须清楚表达相同量纲；人数、千人、万人、百分比、百分点与倍数不可混算。axis用left/right/single/derived或明确中文等价。单轴色块高度可以直接量读，也可由堆顶减下层；采用派生计算时，保留所用读数和上下界传播，正数比值使用对应的保守分子/分母端点。可以使用真实公式，也可保留完整手算过程，不要求建立动态参数模型。
允许不同表名、行列顺序、记录按行或按列、分表或合表，以及合理的非唯一读图区间；重复视图须保持同一对象的判断和物理区间一致。实际公式须能重算，不能靠过期缓存显示正确。底稿应自包含，不依赖外部工作簿或在线数据。
source_file指实际原图。source_regions可以是像素或归一化的一个/多个[x0,y0,x1,y1]（左上原点，明确坐标制），可用JSON数组/对象、可读坐标串或单列x0/y0/x1/y1；主张也可以明确引用本底稿有坐标及来源绑定的读数编号。定位要对应实际数据标记/色块及所用轴，涉及脚注条件时还须定位脚注。不能只抄文件名、给整页无信息矩形，或引用与该对象无关的区域。

2. /tmp_workspace/results/findings.md：对应C01–C08和图A–D说明误读机制、正确口径和仍缺证据。关注双轴与单位、堆叠分项/总量、累计/增量、显示精度、截断纵轴，以及样本显示差异、总体显著性和因果判断的边界。不得虚构图上不存在的精确值、样本量、置信水平、统计检验或实际业务操作。

全部输入只读并保持原字节，新交付写results或系统临时目录。离线完成，不发消息、不查真实账号、不做实际投放或权限调整。保存前复核原生文件、20项读数、8项判断、单位/轴、区间计算、区域定位及两份交付的一致性。

## Expected Behavior

从实际四图核8句及20读数，区分轴/单位、分项/总量、累计/增量、精度和统计因果未知；交付可编辑且能回到原图复核的区间底稿。L3为设计预估。

## Grading Criteria

### Automated group

- [ ] `business_correctness`: 读取实际Office重算后的8项判定与20项原生区间，核对源先行双模型标注的对象、轴、单位和有信息量的数值范围；不要求唯一模型区间。
- [ ] `boundary_cases`: 平衡核双轴、堆叠、累计差、不可辨识精度、截断轴比值、统计及因果未知六组边界；派生量按实际输入区间校验，直接单轴高度读数不强制公式。
- [ ] `delivery_integrity`: 工作簿实际可解析/重算、可见记录完整、重复视图不矛盾，Markdown覆盖8句/4图，原始输入保持字节；隐藏的正确数据不能补齐可见交付。
- [ ] `evidence_binding`: 核真实原图及其数据标记/色块、所用轴、关键脚注区域，支持等价裁切、像素或归一化坐标和读数索引；文件名或无关矩形不能充当支持。

### Judge group

- [ ] `decision_grounding`: 必须实际查看四张同SHA原图及候选原生工作簿和说明，逐项核C01–C08的判断、支撑读数及完整理由，不能仅从字段或规则分数推断。每主张按完整准确且有真实区域支持1、只缺非关键解释0.5、关键解释/范围/数值/极性错误或缺交0，八项取均值；可连续评分。检查区间是否与实际图像分辨率相称、是否正确传播而非虚构原值，数值读图区间不是统计置信区间。
- [ ] `usable_handoff`: 读取实际XLSX、可信重算观察、原图和findings，判断审核人员能否从结论回到读数、图形/轴/脚注和计算过程。接受合理的不同布局、表头、单位、手算/公式与区间，不锁作者坐标或某位模型标注；实际检查可读性，稀疏XML有值不等于画面可见可用。

## Automated Checks

```python
def grade(**kwargs) -> dict:
    from pathlib import Path
    import runpy
    root=Path(kwargs.get("workspace_path") or "/tmp_workspace")
    values=runpy.run_path(str(root/"gt/grader.py"))["grade"](root)
    return {key:values[key] for key in ("business_correctness","boundary_cases","delivery_integrity","evidence_binding","overall_score")}
```

## LLM Judge Rubric

### Criterion 1: 图形证据与判断边界 (key: decision_grounding, weight: 0.7)

判据：必须实际查看四张同SHA原图及候选原生工作簿和说明，逐项核C01–C08的判断、支撑读数及完整理由，不能仅从字段或规则分数推断。每主张按完整准确且有真实区域支持1、只缺非关键解释0.5、关键解释/范围/数值/极性错误或缺交0，八项取均值；可连续评分。检查区间是否与实际图像分辨率相称、是否正确传播而非虚构原值，数值读图区间不是统计置信区间。

**Score 1.0**: 8项主张的实际解释和数据支持均准确，正确绑定双轴与图例、分项/总量、累计/增量和截断轴；明确区分可观察、反证与未知，不从未定义误差线推显著性/不显著性或因果，不伪造人级精度和未给原值。

**Score 0.5**: 按八主张锚点计算的平均解释完成度为0.5；须逐项列出实际错误/遗漏及原图依据。正确短码不能抵消相反或编造的理由。

**Score 0.0**: 8项均未完成，或全部核心解释无关/被图反驳；未实际取得关键图像时保持unresolved，不凭OCR、题目数字或自动分补判。

### Criterion 2: 可复核原生审核交接 (key: usable_handoff, weight: 0.3)

判据：读取实际XLSX、可信重算观察、原图和findings，判断审核人员能否从结论回到读数、图形/轴/脚注和计算过程。接受合理的不同布局、表头、单位、手算/公式与区间，不锁作者坐标或某位模型标注；实际检查可读性，稀疏XML有值不等于画面可见可用。

**Score 1.0**: 8项判断和20读数完整清楚、原生可编辑，原图区域和依赖可定位，区间/单位/精度/未知解释一致，两文件能支持复核和后续补证；无虚构验证、统计或真实业务操作。

**Score 0.5**: 主要审核交接可用且可追溯，仅有不改变结论的非关键布局、定位或后续说明缺口。

**Score 0.0**: 核心底稿缺失、损坏、隐藏/不可读、来源或对象无法对应、两文件关键矛盾，或只能依靠聊天自述补齐。

## Workspace Path

```
workspace/general/challenge/02_Data_Analysis/02_Data_Analysis_task_006_visual_chart_audit
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- 此题为既定6/60视觉输入任务之一，GAIA仅方法启发，线上只沿用去身份用途原型，所有图表/日期/数据合成。必须保留实际图片理解链路，AStudio可由客户端辅助理解，不要求主模型原生多模态。L3及四端兼容性尚待实测。
- 用户专门授权两模型独立先图后题标注及v2措辞复核；各20读数相容、8判断一致，保留所有原始记录和不唯一读区间。不是人工专家，也不能保证没有相关模型错误。C06/C08的证据不足是已审GT标签。
- 原C06元断言歧义已在v2改为实际人数窄范围，正式使用active_inputs指定的v2 Word。四图/规则/另外7句不变；同像素图可对应60000或60002人，禁止按隐藏原值要求精确恢复。三组同绘图文字但不同图形的控制改变4判定，不冒充实际OCR引擎实验。
- 规则内部.55/.25/.15/.05，business为8判断.45与20区间.55。数值允许模型读区间的相交/中心容差和有信息量宽度，允许多种单位与数据布局；这些是图形量级规则，不是统计置信区间或作者唯一答案。
- 43项实际原生规则控制分三版：首批11自动正例/19候选负例/2语义边界/4异常，补2坐标列正例/2负例，再补2说明映射正例/1负例；逐项源码/契约SHA保留，36历史说明覆盖投影新旧一致。正例只验证自动等价，2语义反例的预期不是正式Judge分。
- 参考8个区间公式另经3组真实Office数值干预与Fraction对照；候选可手算，不继承该参数模型要求。所有候选公式会清缓存实际重算，不能用作者缓存或隐藏正确数据代替交付。
- 语义Judge必须取得同一四图原件并实际查看，图片查询/传输日志不等于理解正确；缺图/解码器、锁漂移、缺GT或规则失败保持评测异常/unresolved，不补零分。普通错题、缺交或业务错误按冻结检查点计分，输入改动使自动组件0。
- 900仅元数据，不作为候选总执行截止或能力扣分条件。作者自动参考分和静态通过不证明真实Harness成绩、独立语义成绩或实测难度/区分度；整版仍需60题冻结与12题四端校准。
