---
id: 02_Data_Analysis_task_008_parameterized_model
name: 提成模型的参数化与情景联动
category: data_analysis
timeout_seconds: 900
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L4
grading_type: automated
tags:
  - custom
  - general-hard
  - general-challenge
judge_evidence:
  required:
    - path: results/compensation_model.xlsx
      role: candidate_deliverable
    - path: results/validation.md
      role: candidate_deliverable
scoring_runtime:
  office: true
dataset_report: {"category": "data_analysis", "category_name": "数据分析与表格建模", "category_order": 1, "checkpoint_capabilities": {"boundary_cases": ["reasoning_planning"], "business_correctness": ["data_processing"], "delivery_integrity": ["verification_delivery"], "evidence_binding": ["verification_delivery"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-challenge"}
---

# 提成模型的参数化与情景联动

## Prompt

请建立可修改参数、实时联动的季度工资提成测算模型，交付可给同事继续改参数核对的原生Excel。

只读取/tmp_workspace/payroll.xlsx、policy.md和scenario_inputs.json。payroll.xlsx含12员工、36考勤、110销售、34退款；scenario_inputs.json为三情景×三个月共9组参数。固定2026-07至2026-09、CNY，全部为合成练习。严格按policy.md：按月边际阶梯、到分后封顶、跨月退款按原销售月累计退款前后重算整月封顶差额、已扣不重扣。底薪与补贴分别到分；cap=0为真零，零出勤不抹去提成，净提成和工资允许负数。排除季度外/未posted行但保留行和处理原因。不要自行增加税费、实际发薪、邮件或联网。

全部交付放/tmp_workspace/results，每份不超过5MiB：

1. compensation_model.xlsx：自包含、可编辑、有真实联动公式，无宏或外部数据链接。保留全部源行和九组原生数值参数。可用统一“情景×员工×月份”公式计算108条工资与216条追溯，再提供所选情景的36/72行查看；也允许其它等价动态实现。三情景的9行月度对比及相对Base差额须同时实时更新，不能粘贴当前答案或用静态快照代替。一个可见的数字情景选择入口保存为1，1/2/3对应Base/Growth/Guardrail；标签使用active_scenario_id、scenario_selector、查看情景编号、活动情景编号或情景选择编号之一，其右侧紧邻可编辑数字单元格。改选择入口只切换查看，不改源记录或参数。对应查看的scenario_id必须反映实际所选情景。

在可见的一行表头中呈现以下字段，英文键或语义明确对应的中文均可，Sheet名称、坐标、列顺序、记录顺序、辅助列和合理等价标量公式不限。所选情景查看表分别只有当前36/72行，各键唯一；共享计算明细可另放。不要把汇总总计混入明细记录，也不要制作多个同样字段的竞争输出或隐藏结果冒充可读表：
- 所选情景员工月度（36行）：scenario_id, employee_id, month, paid_fraction, gross_sales, commission_raw, base_pay, allowance, earned_commission, clawback, net_commission, total_pay
- 所选情景原月回溯（72行）：scenario_id, employee_id, original_month, pay_month, original_gross, refund_before, refund_through, eligible_before, eligible_after, commission_before, commission_after, current_clawback
- 三情景月度对比（9行）：scenario_id, scenario_name, month, base_pay, allowance, earned_commission, clawback, net_commission, total_pay, delta_base_pay, delta_allowance, delta_earned_commission, delta_clawback, delta_net_commission, delta_total_pay

原月≤截至月的72行均保留，同月current_clawback为0。commission_raw保留6位，paid_fraction保留足够精度；其余金额到分，不用显示格式替代计算舍入。三情景对比六项金额为当月12员工合计，delta_字段是该情景同月减Base同月。

底稿使用以下一行表头字段或清楚对应中文，原值可见且数值为可编辑原生数值；原始ID/月份/状态原义保留。sales/refunds在原字段右侧增加decision，posted/not_posted/outside_period或明确中文。派生/审计表不能替代原始底稿：
- employees：employee_id, employee_name, base_monthly_salary
- attendance：attendance_id, employee_id, month, paid_days, standard_days
- sales：sale_id, employee_id, month, amount, status
- refunds：refund_id, employee_id, refund_month, original_sale_id, amount, status
- parameters：scenario_id, scenario_name, month, salary_multiplier, tier1_limit, tier2_limit, rate1, rate2, rate3, commission_cap, full_allowance

参数变更应只影响相关情景；原月参数变动须传播到以后月份退款追溯，其它情景/月份仍保持正确。零封顶不可当作空值或无限。公式数量不设门槛，以真实数值响应判断联动。

2. validation.md：说明参数入口、选择入口、刷新方法、退款追溯/封顶/舍入限制，来源明确为payroll.xlsx、policy.md、scenario_inputs.json。实际修改参数、重算并恢复，不能虚构运行。至少验证以下一个操作：growth_september_cap（Growth九月commission_cap由3000改2100）、guardrail_september_zero_cap（Guardrail九月commission_cap由800改0）、base_july_rate（Base七月rate1由0.01改0.02）。记录受影响员工/月/情景、其它情景未被误改及恢复结果。为便于同事定位，把一次实际操作按下列键逐行“key: value”各写一次，数值自行计算，不照抄题面或猜结果：
test_id、scenario_id、month、field、old_value、new_value、metric、before、after、restored、parameter_input、result_locator。
test_id为上述操作ID；metric从base_pay/allowance/earned_commission/clawback/net_commission/total_pay中选择该次确实发生变化的一项，before/after/restored对应“情景×月份”该指标的月合计；parameter_input定位被改的原生参数单元格，result_locator定位对比表该情景同月指标单元格，格式为Sheet名!A1。保存基线原参数、情景1；记录只描述实际做过的操作。

评分会在独立副本清除公式缓存后实际重算，并切换情景及修改三个原生参数，核对逐员工、追溯、全部9行对比和未受影响结果。只交正确静态基线或常量公式不能获得动态模型主要分；无任何有效参数数字响应时业务项最高0.5。原三份输入保持只读，全部新文件写results，离线完成，不发消息、邮件、付款或连接真实账号。

## Expected Behavior

源行与九组参数完整，以统一可编辑口径计算月度边际阶梯、封顶和累计退款前后差额；所选36/72行及三情景对比在实际参数修改后正确联动。L4为设计预估。

## Grading Criteria

- [ ] `business_correctness`: 建立可修改参数、自动联动的工资模型；保留原始底稿，展示三情景结果及差异，禁止写死情景答案。
- [ ] `boundary_cases`: 逐项识别并正确处理：阶梯边界误算；退款重复扣减；情景只改标签。以独立反例验证，不只检索关键词。
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
workspace/general/challenge/02_Data_Analysis/02_Data_Analysis_task_008_parameterized_model
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- 线上来源只作去身份用途原型，全部数据合成；SpreadsheetBench为方法参考。16,848项双路源核对独立于候选，不是人工专家复核。
- 已获用户明确同意采用统一公式表；参考按情景×员工×月份108行工资、216行追溯和9行月度对比联动，不使用指标选择器伪造双变量敏感性表，不退化为静态快照。
- 自动四项.55/.25/.15/.05；业务为当前工资.45/追溯.35/三情景对比.20，边界为处理状态宏平均.20/边界员工.20/五组真实选择和参数响应.60。实际扰动不锁作者坐标或Sheet。
- 三个原生参数响应比较所有变化字段，并要求其余结果仍正确。全静态或常量公式的业务项最高.5；输入被改或原生源记录不全时边界/交付为0、业务最高.5。
- validation只自动核结构化操作事实、可回查入口及独立原生响应，开放行文和完整视觉质量不自动评价；没有人工薪资专家或真实Harness成绩。
- 缺GT/helper/受管上下文、锁漂移及引擎超时保持evaluation_error，不补候选零分。900为元数据，四端执行、难度梯度与区分度尚待校准。
