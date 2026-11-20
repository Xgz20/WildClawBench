---
id: 01_Office_Documents_task_005_annual_deck
name: 年度数据到可编辑汇报PPT
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
  - general-challenge
judge_evidence:
  required:
    - path: results/annual.pptx
      role: candidate_deliverable
    - path: results/evidence.csv
      role: candidate_deliverable
    - path: results/notes.docx
      role: candidate_deliverable
scoring_runtime:
  office: true
  office_render: true
dataset_report: {"category": "office_documents", "category_name": "文档与办公交付", "category_order": 0, "checkpoint_capabilities": {"automated.boundary_cases": ["reasoning_planning"], "automated.business_correctness": ["data_processing"], "automated.delivery_integrity": ["verification_delivery"], "automated.evidence_binding": ["verification_delivery"], "llm_judge.decision_grounding": ["data_processing"], "llm_judge.usable_handoff": ["verification_delivery"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-challenge"}
---

# 年度数据到可编辑汇报PPT

## Prompt

请依据给定结账快照，为澄岭智服制作2026年度经营汇报。任务口径、八页结构和12项指标定义见 /tmp_workspace/brief.docx，数据在 /tmp_workspace/metrics.xlsx，样式参考 /tmp_workspace/theme.pptx。

固定截止2026-12-31，时区Asia/Shanghai；材料是合成的完整年度快照，不按今天截断月份，不联网补数据。更正列非空时覆盖原值，0是有效更正；按每行金额单位换算。比率先汇总各自分子分母。财务营业成本与运营服务成本不混用。应收按固定截止日区分30天、31天和未到期，不能把未来到期发票并入已到期回款率。

交付 /tmp_workspace/results/annual.pptx：恰好8页，包含封面，全部可见。沿用模板画布和字体，可按内容重排。正文、来源、页码及图表标签不少于16pt，文字、表格与图表原生可编辑；不能整页截图。第3、4、5页分别保留月度两年收入、季度收入/营业成本、季度交付/结单率的原生图表及可编辑内嵌数据。图表、可见指标与原始数据一致；不得用正确缓存掩盖错误数据或公式。图表类型、系列顺序、对象创建顺序、等价布局及正确等价公式均可。

交付 /tmp_workspace/results/evidence.csv：UTF-8，可有BOM，字段kpi_id、slide、value、unit、source_cells、method，允许对应中文表头和行列重排。覆盖brief定义的22条记录；同一记录不得有相互冲突的字段。K指标value保留2位小数，百分比按百分数点/%表示，图表比率按ratio保存至少6位小数。source_cells用实际工作表!单元格或范围，多个以分号分隔。单位及计算说明明确，slide为实际页码。

交付 /tmp_workspace/results/notes.docx：按页组织讲解要点，保留K指标编号，与PPT和CSV的数值、窗口、单位及结论一致。说明事实、建议和未知，不把收入确认调整直接解释为业务停止，不编造2027预测、满意度目标或已完成催收。

仅读取给定输入并离线完成，不访问账号、发送消息或执行建议中的真实业务动作。输入文件保留原字节；所有新交付写results，临时文件写results或系统临时目录。

## Expected Behavior

独立归一化三张源表，正确处理更正0、单位和不同分母、到期边界，完成22记录及八页原生汇报和讲解。图表缓存、实际内嵌数据/公式结果与可见数字一致；未知的因果、目标与预测保留未知。

## Grading Criteria

### Automated group

- [ ] `business_correctness`: 逐字段核12指标在账本、原生PPT、实际PDF及讲解中的数值，核图表40点与四类账龄；缺一个交付不抹掉其它可判断字段。
- [ ] `boundary_cases`: 核0更正/单位/分母/账龄边界，原生图表与可信重算数据一致，以及实际字号和明显页外/强重叠字形。完整视觉适配另由Judge检查。
- [ ] `delivery_integrity`: 八页可见原生内容、账本字段及唯一记录、讲解可解析、描述和页码完整且输入未改。
- [ ] `evidence_binding`: 22记录的来源范围实际存在并覆盖该指标/系列需要的源格与单位；引用正确但无关的格子不得充当依据。

### Judge group

- [ ] `decision_grounding`: 独立读取源表、更正/单位/截止规则及三份交付，核实际图表的类目、图例、单位、趋势与结论。规则值正确不代表因果解释正确，缓存不代替实际数据源。
- [ ] `usable_handoff`: 读取实际PPTX和派生预览、CSV及DOCX，核模板样式、可编辑文字/图表/内嵌数据、可读字号、遮挡/溢出和页级讲解。自动字形检查不证明全部版式可用。

## Automated Checks

```python
def grade(**kwargs):
    from pathlib import Path
    import runpy
    import pdfplumber
    import pypdf
    root = Path(kwargs.get("workspace_path") or "/tmp_workspace")
    result = runpy.run_path(str(root / "gt" / "grader.py"))["grade"](root)
    return {"business_correctness": result["business_correctness"], "boundary_cases": result["boundary_cases"],
            "delivery_integrity": result["delivery_integrity"], "evidence_binding": result["evidence_binding"], "overall_score": result["overall_score"]}
```

## LLM Judge Rubric

### Criterion 1: 经营事实与结论依据 (key: decision_grounding, weight: 0.7)

判据：独立读取源表、更正/单位/截止规则及三份交付，核实际图表的类目、图例、单位、趋势与结论。规则值正确不代表因果解释正确，缓存不代替实际数据源。

**Score 1.0**: 关键数字和结论均有材料支持，更正、分母、期限与成本口径正确，图表意义一致，区分事实、建议和未知。

**Score 0.5**: 主结论与核心数字成立，无关键虚构、反向趋势或跨产物冲突，仅遗漏一处非关键解释或定位。

**Score 0.0**: 关键数字或图表含义错误，忽略更正/单位/分母/期限，把确认调整判为停业，虚构预测、目标或业务动作已经完成，或存在影响经营判断的矛盾。

### Criterion 2: 原生汇报与可复核交接 (key: usable_handoff, weight: 0.3)

判据：读取实际PPTX和派生预览、CSV及DOCX，核模板样式、可编辑文字/图表/内嵌数据、可读字号、遮挡/溢出和页级讲解。自动字形检查不证明全部版式可用。

**Score 1.0**: 八页汇报、证据账本和讲解完整可用，关键原生对象可解析且数据对应，全部页面可读，读者能据来源复核。

**Score 0.5**: 主要交付与原生对象可用，无关键遮挡或数据冲突，仅有不影响主要复核的一处非关键交接说明/样式问题。

**Score 0.0**: 主要交付缺失/不可用，图片冒充原生对象，关键文字/图表被遮挡或溢出，读者不能对应来源/讲解，或主要答案只在聊天中。

## Workspace Path

```
workspace/general/challenge/01_Office_Documents/01_Office_Documents_task_005_annual_deck
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- H005；L3是设计预估。源数据及公司均为自有合成，不含线上原文、真实财务附件或账号。素材格式/PPT生成及评分侧渲染不使本题成为视觉输入题。
- 规则权重业务0.55、边界0.25、交付0.15、证据0.05；hybrid规则75%/语义25%。业务12指标均值0.7、图表0.2、账龄0.1；每指标账本/PPT/PDF/讲解权重0.35/0.3/0.2/0.15。
- 边界数值机制0.4、可编辑图表数据一致性0.3、字号/明显几何适配0.3。文字位置通过实际PDF字形观察，原生文本与可见值关联，适应对象创建顺序。普通文本框溢出、颜色、遮挡、类目与因果解释仍须独立Judge。
- 内嵌XLSX来源回执绑定冻结PPTX/部件/原字节，清缓存后实际重算，所有源副本、重算文件、PDF与回执保留Worker派生目录。缓存对但公式错必须失分；缺GT/环境/引擎失败不补能力零分。
- 评分Worker需要已声明并冻结的pdfplumber/pypdf依赖及可信Office/字体锁，见私有scoring_dependencies.json。作者使用独立Python3.12虚拟环境共享现有受管库，版本/导入已probe；这不是默认3.11 bootstrap配置或全部库文件字节锁，正式校准必须统一匹配环境及安装制品。
- 数值万元/元及百分数点容差0.0051，图表ratio容差1e-6；允许CSV BOM/别名/重排、等价数值表示、图表系列顺序、正确公式和原生布局。缺列不被当作已知空值，描述或证据缺失不抹掉其它业务字段。
- 独立计算及作者控制不等于专家审阅、独立语义评分、四端执行或难度/组合区分度的实测。正式发布仍须完整60题冻结与12题校准。
