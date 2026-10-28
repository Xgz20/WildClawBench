---
id: general_hard_data_analysis_task_009_capacity_optimization
name: 供应与产能约束下的业务分配模型
category: data_analysis
timeout_seconds: 900
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L4
grading_type: automated
tags:
  - custom
  - general-hard
judge_evidence:
  required:
    - path: results/allocation.xlsx
      role: candidate_deliverable
    - path: results/decision.md
      role: candidate_deliverable
scoring_runtime:
  office: true
dataset_report: {"category": "data_analysis", "category_name": "数据分析与表格建模", "category_order": 1, "checkpoint_capabilities": {"boundary_cases": ["reasoning_planning"], "business_correctness": ["data_processing"], "delivery_integrity": ["verification_delivery"], "evidence_binding": ["verification_delivery"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-hard"}
---

# 供应与产能约束下的业务分配模型

## Prompt

请为一个合成单周期供货需求制定确定可执行的整数分配方案，核对资源、费用和优先级取舍，交给同事复核。

只读取/tmp_workspace/demand.csv、capacity.xlsx、costs.csv、constraints.md：12种商品、3工厂、全部36条工厂×商品路线、2种全厂共享物料、24条配方和36条路线费用。固定单周期、CNY，预算与口径以constraints.md为准，不补加班、外包、跨期库存、税费或真实经营动作。

严格执行硬约束：每条路线交付量为非负整数；禁止路线为0；正生产达到该工厂×SKU最小批量且不超过路线最大量。min_batch是启用门槛，不是批量倍数。每个SKU总交付不超过需求，priority1还须达到minimum_service。每厂件数和工时分别约束，不能跨厂借用；两种物料跨所有工厂/商品共同扣减。真实0配方/费用不能当缺失。费用包括每件生产与运输、每条正路线一次开线费、每个正生产工厂一次启动费；成本表中重复列出的同厂启动费只能收一次，0路线不收开线费。全部费用到分，满足预算。

目标顺序为：先最小priority1缺口，固定其最优值再最小priority2缺口，再固定前两项最小priority3缺口，最后在相同最小缺口向量下最小化总费用。不能以总缺口或更低费用换少交高优先级。可以使用保证等价的加权目标，但须说明为什么保证优先顺序。不同的可行最优分配矩阵均接受。

全部新交付放/tmp_workspace/results，每份不超过5MiB，原四份输入只读：

1. allocation.xlsx：自包含可编辑原生工作簿，无宏或外部链接。保留全部113条源记录和原字段，给出下列可见的一行表头明细，英文键或对应中文可用。Sheet名、行列顺序、空白间隔列和合理辅助列不限，各业务键唯一，0量及禁止路线也列出。可以使用有效公式或完整正确的静态核算表；本题不要求改约束后自动重新优化，不要求交付代码、指定求解器或达到公式数量。计算值与显示格式有别，分数解即使显示为整数也不是可执行整数方案。
- 工厂×商品分配（36行）：plant_id, sku_id, units, production_cost, transport_cost, setup_cost, line_total, line_active
- 商品需求/缺口（12行）：sku_id, priority, demand_units, minimum_service, served_units, unmet_units
- 工厂件数/工时（3行）：plant_id, used_units, unit_capacity, unit_slack, used_labour, labour_capacity, labour_slack, active, activation_cost
- 共享物料（2行）：material_id, used_units, available_units, slack

units为该工厂该SKU的整周期交付件数；production_cost/transport_cost为该路线总生产/运输费，setup_cost为正路线一次费，line_total是上述三项之和，line_active是该路线是否正生产（true/false或1/0）。商品served_units跨工厂汇总，unmet_units=需求减交付。工厂active和activation_cost只按是否有正生产及该厂单次费计算，不能把启动费重复进每条路线。各slack为上限减已用。数量、工时、物料保留各自单位，不将工厂件数上限等同工时。

另有可见control/value两列表或对应中文：priority1_unmet、priority2_unmet、priority3_unmet、production_cost、transport_cost、setup_cost、activation_cost、total_cost、budget、budget_slack、all_demand_satisfied、all_hard_constraints_satisfied、total_delivered、full_demand_total、unit_capacity_total、full_service_unit_bound_gap。成本与余量CNY到分，真假项用true/false或1/0。full_service_unit_bound_gap=max(全需求件数减工厂总件数上限,0)，只是一个全需求不可行性下界，不能冒充精确优先级缺口。诊断不反向填平业务数值。

底稿需保留原源字段，需求和费用分别来自demand.csv和costs.csv，能力与配方来自capacity.xlsx。具体字段如下（英文或明确对应中文），不要只留汇总或求解器状态：
- demand：sku_id, sku_name, priority, demand_units, minimum_service, destination
- plants：plant_id, plant_name, unit_capacity, labour_capacity
- routes：plant_id, sku_id, eligible, max_units, min_batch, labour_per_unit
- materials：material_id, available_units
- recipes：sku_id, material_id, units_per_item
- costs：plant_id, sku_id, variable_cost, transport_cost, line_setup_fee, plant_activation_fee

2. decision.md：说明当前全需求是否可行、分配方案的缺口向量、条件费用和资源取舍，说明怎样按字典序确定方案，并给出至少一个能用源数字复算的全需求不可行性依据。求解器名称/status、LP分数界或“看起来最优”不能替代可执行方案；全需求不可行的一个简单下界，也不必独自证明所有优先级和成本最优，需区分各证明范围。

请把保存方案的以下事实按“key: value”逐行各写一次，数值自行核算：priority1_unmet、priority2_unmet、priority3_unmet、production_cost、transport_cost、setup_cost、activation_cost、total_cost、budget、budget_slack、all_demand_satisfied。

另用同样格式记录一个实际成立的源数字证明，certificate_kind选择下列一种；source_file填capacity.xlsx，source_locator定位相关原始Sheet及记录ID（可以用工厂A/B/C、共享物料M1/M2、单件耗料S01-S12等唯一稳定ID，不能伪造行）：
- factory_units：full_demand_units、available_factory_units、minimum_total_unmet_bound。证明需求件数超过工厂件数上限之和；定位工厂A/B/C，避免只凭单厂证明总能力不足。
- combined_material：full_demand_units、combined_supply_units、min_material_coefficient_per_item、finished_units_upper_bound、minimum_total_unmet_bound。用两种共享物料约束相加，逐SKU配方系数和的最小值给出成品件数上界floor(两物料总供应/该系数)。定位M1/M2及全部S01-S12配方。物料单位不能直接当成成品缺口。
- material_requirement：full_demand_units、material_id、required_material_units、available_material_units、material_shortage_units。按每SKU全需求×对应物料配方核算总物料需求，与真实供应比较，只把差值称为该物料单位的不足；定位该物料和全部S01-S12配方，不把物料差值冒充成品缺口。

说明明确引用demand.csv、capacity.xlsx、costs.csv、constraints.md。若使用求解工具，区分实际运行、得到的可行方案、阶段最优界和未验证推断，不虚构日志或专家审批。静态交付不代表改约束后已重新求解；只需当前给定源材料下的确定方案和完整核算。

评分会在独立副本清除公式缓存并重算，从你实际给出的36条整数分配重新核对93项源约束、优先级缺口和条件成本，允许等价最优矩阵。更便宜或相同总缺口但少交高优先级会失分；分数解、不可行计划和缺源底稿会受限。说明自动核对结构化事实及源证明，普通解释文字不能代替数值证据。离线完成，不连接真实工厂、供应商或账号，不下单、不发消息、不付款。

## Expected Behavior

在整数、路线批量/资格、最低服务、工厂件数/工时、共享物料和预算内求字典序缺口最小、该向量下费用最低的确定计划；核算与源证明可复算，允许不同等价最优矩阵及完整静态表。L4为设计预估。

## Grading Criteria

- [ ] `business_correctness`: 输出可行分配、总成本及约束检查；若无法满足全部需求，按规定优先级给出最小缺口并解释。
- [ ] `boundary_cases`: 逐项识别并正确处理：分数解冒充可执行方案；漏最小批量；只比较总成本。以独立反例验证，不只检索关键词。
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
datasets/general-hard/workspace/data_analysis/general_hard_data_analysis_task_009_capacity_optimization
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- SpreadsheetBench仅方法启发，无线上原型和直接复制题目。全部数据合成；v1源/求解记录保留，参考之前明确收紧为v2资源约束。
- 源先行HiGHS直接75变量MILP与CBC完整121选项独立建模，四阶段值一致，两解各93项精确检查及6项解析界通过，最优(0,7,22,481355分)。参考矩阵不是评分目标，真实可行更优候选触发oracle矛盾评测异常。
- 内部四项.55/.25/.15/.05。业务为优先级.65/固定完整最优缺口后的成本间隙.20/自核算.15；后级仅在前级最优时计分。边界为可行整数硬约束.60/源不可行性证明.40。不可行或缺计划时业务最高.25；输入/底稿缺失时最高.5且边界0。
- 候选公式/完整静态表均接受，不设置公式数量或自动重优化要求。Office只清缓存读当前计划，作者参考1125项原生数量变更核验不强加给候选。评分Worker不需要SciPy/PuLP/CBC等求解器。
- 自动规则只判源硬约束、目标/成本间隙、可见核算表、结构化说明事实和一个源证明；不自动判断开放措辞、完整视觉质量、求解器运行主张或供应链专家结论。
- 缺GT/helper/受管上下文、引擎身份漂移、超时和潜在合法公式兼容问题保持evaluation_error。900为任务元数据，真实四端运行、L4难度梯度与组合区分度未实测。
