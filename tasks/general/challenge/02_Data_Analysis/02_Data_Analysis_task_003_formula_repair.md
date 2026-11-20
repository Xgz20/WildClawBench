---
id: 02_Data_Analysis_task_003_formula_repair
name: 工龄政策变化下的公式修复
category: data_analysis
timeout_seconds: 900
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L3
grading_type: automated
tags:
  - custom
  - general-hard
  - general-challenge
scoring_runtime:
  office: true
  office_render: false
dataset_report: {"category": "data_analysis", "category_name": "数据分析与表格建模", "category_order": 1, "checkpoint_capabilities": {"boundary_cases": ["reasoning_planning"], "business_correctness": ["data_processing"], "delivery_integrity": ["verification_delivery"], "evidence_binding": ["verification_delivery"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-challenge"}
---

# 工龄政策变化下的公式修复

## Prompt

请按公司新政策修复休假核算工作簿，保留可重算公式与原有结构。

读取/tmp_workspace/leave_model.xlsx、/tmp_workspace/policy.md、/tmp_workspace/cases.csv。12名员工均为合成数据，规则只适用于这份练习。policy.md给出整年工龄、闰日周年、分档天数、fte折算及缺失/未来入职处理。不要用365或365.25近似整年，也不要写死当前结果。参数输入发生变化时相关结果应自动更新。

交付：
1. /tmp_workspace/results/leave_model_repaired.xlsx：在副本中修复Leave!E6:H17的48个公式，并将工作簿级名称AsOfDate修正到Control!$B$3。Control!B3最终保持2026-02-28。其余名称、参数值、原始人员、非目标公式、三个Sheet名称与顺序、布局及样式语义保持；需要辅助公式可使用原预留Leave!J5:O17。不能删除名称、移动既有行列、增加Sheet、隐去数据、引入外部依赖或只交静态数值。所有48个结果格保留公式，空值也由公式返回。
2. /tmp_workspace/results/formula_changes.md：写修复理由及验证方法，并按policy.md的两张Markdown表记录五项实际修改和三个基准日共36项员工验证。修复表使用target,before,after,rule_id，填写原始和最终交付的实际公式或名称引用，不能用省略号。验证表使用employee_id,as_of_date,complete_years,base_days,entitled_days,status；日期ISO格式，未知留空，合法零写0。核验日期为2026-02-28、2026-03-01、2028-02-29，完成后还原基准日。声明工具执行须有实际依据。

三份输入只读，所有新交付写入results；每份不超过5MiB，不要求交付代码。离线完成，不访问真实账号、不发消息或调用付费接口。候选可用任意满足契约的表格工具，实际评分会在副本中清除公式缓存，再改变基准日、政策参数、fte及有效入职日期重算；不要求候选安装特定重算引擎。

## Expected Behavior

以独立公司规则修复整年工龄、闰日周年、档位、向下折算和缺失状态，保留命名区域、结构与原始数据；多组输入改变后实际重算正确，修改记录定位到真实公式。L3仅设计预估。

## Grading Criteria

- [ ] `business_correctness`: 修复公式与参数引用，保留工作簿结构；修改基准日期后，所有员工结果正确变化，不能写死当前结果。
- [ ] `boundary_cases`: 逐项识别并正确处理：写死数值；满周年边界错误；公式缓存掩盖错误。以独立反例验证，不只检索关键词。
- [ ] `delivery_integrity`: 全部要求的产物可解析/可使用，跨产物关键事实一致；保护文件与输入未改变。
- [ ] `evidence_binding`: 来源/验证记录定位到实际材料、产物或最终候选源码；自述已运行不能代替独立验证。

## Automated Checks

```python
def grade(**kwargs) -> dict:
    from pathlib import Path
    import runpy
    root=Path(kwargs.get("workspace_path") or "/tmp_workspace")
    scores=runpy.run_path(str(root/"gt/grader.py"))["grade"](root)
    return {key:scores[key] for key in ("business_correctness","boundary_cases","delivery_integrity","evidence_binding","overall_score")}
```

## LLM Judge Rubric

## Workspace Path

```
workspace/general/challenge/02_Data_Analysis/02_Data_Analysis_task_003_formula_repair
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- 源于已审核AStudio工龄公式需求原型，全部人员/日期/政策和结构重新合成；SpreadsheetBench仅作方法参考，不直接复制题目。
- GT先从真实输入构造：CSV、stdlib OOXML及独立库读取；周年枚举与年月日算法、Fraction与Decimal向下取整互核。原生参考不反推真值。
- 自动规则权重.55/.25/.15/.05；业务含基线.65、48公式保留.20和36验证记录.15。边界按五组实际Office中应改变的业务输出评分，全部非目标结果亦须正确；基线和修改范围完整后才运行。不信任候选缓存，五组均无业务响应时业务分最高.5。
- 输入或结构/保护内容破坏、结果不可见时业务分最高.5，输入改动使边界/交付/证据为0。缺GT、helper漂移、引擎漂移或实际工具失败保留评测异常，不补能力零分。
- 非目标内容按单元格原值/原公式、字体/填充/边框/数字格式/对齐、行列尺寸/合并/冻结和Sheet名称/顺序等语义核验，不按ZIP字节或公式实现风格评分。预留区允许辅助实现。
- 所有评分派生文件位于冻结Workspace外，原交付不改写。没有LLM Judge或人工专家成绩；四端仍待预检校准，900是元数据，不设候选总执行截止。
