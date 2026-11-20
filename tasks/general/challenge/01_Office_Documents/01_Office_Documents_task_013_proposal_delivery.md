---
id: 01_Office_Documents_task_013_proposal_delivery
name: 多约束方案响应与报价交付包
category: office_documents
timeout_seconds: 900
modality: pure-text
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
    - path: results/proposal.docx
      role: candidate_deliverable
    - path: results/quote.xlsx
      role: candidate_deliverable
    - path: results/customer_email.md
      role: candidate_deliverable
    - path: results/exceptions.csv
      role: candidate_deliverable
scoring_runtime:
  office: true
  office_render: true
dataset_report: {"category": "office_documents", "category_name": "文档与办公交付", "category_order": 0, "checkpoint_capabilities": {"automated.boundary_cases": ["reasoning_planning"], "automated.business_correctness": ["data_processing"], "automated.delivery_integrity": ["verification_delivery"], "automated.evidence_binding": ["verification_delivery"], "llm_judge.decision_grounding": ["data_processing"], "llm_judge.usable_handoff": ["verification_delivery"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-challenge"}
---

# 多约束方案响应与报价交付包

## Prompt

请为澄源园区完成三个技术方案与三处屋面场地的响应和报价交付。只依据给定合成固定参数比较，不调查或编造市场价格、补贴、实际发电或工程核验结论。

读取 /tmp_workspace/customer_requirements.docx、/tmp_workspace/options.csv、/tmp_workspace/technical_notes.pdf、/tmp_workspace/response_template.docx。需求编号Q01–Q12、场地S1/S2/S3、方案A/B/C及技术规则T01–T12为公开的业务定位。按技术规则求达到各场地目标的最小整片组件数，分别核验面积、屋面类型荷载、DC上限、换屋面权限、含税基础预算和前置材料。区分feasible/conditional/infeasible；不能用低价补偿硬约束失败，未知不能变成0或已核实。

交付以下四份实际文件：

1. /tmp_workspace/results/quote.xlsx：原生可编辑且可重算的报价工作簿。保留三场地参数、三设备参数与共用参数的可识别输入，各自带site_id、option_id、parameter_id/value；数值参数用可修改的原生数值，布尔/材料状态及未知原义保留。可以使用输入Word的field_id×S1/S2/S3布局、按对象的宽表或字段明细表，不要求指定工作表名或坐标。
覆盖九个site_id/option_id组合。计算项至少包括module_count、dc_kwp、area_m2、design_load_kg_m2、annual_energy_kwh、inverter_count、replacement_area_m2；全部必要未税成本cost_module/cost_inverter/cost_cable/cost_isolation/cost_mounting/cost_installation/cost_replacement/cost_drainage/cost_design/cost_inspection/cost_adhesion/cost_corrosion；供货/施工/技术服务三个subtotal、对应三个tax、gross_total及budget_margin。可用语义等价的中文表头，宽表或按metric/value的明细表均可。遵循T08的分税率和到分舍入，金额单位为CNY，容量kWp、面积m2、荷载kg/m2、年量kWh/year；保留计算精度，展示时金额精确到分，技术数值可至少保留两位。组件/逆变器必须整数。
逐组合保留T09八项AREA、LOAD、GRID、REPLACEMENT、BUDGET、ADHESION、CORROSION、REPAIR_SCOPE的判定及最终status。各检查可用pass/fail/unknown/not_applicable或语义等价中文；明确失败优先于其他未知。计算须真实依赖工作簿源输入，不能写死结果或用常量公式伪装；固定不适用的成本零值允许直接填写0。给出当前输入的每场地selected_option/status/gross_total/budget_margin；输入变化后需重新核对推荐，不要求自动优化新情境。

2. /tmp_workspace/results/proposal.docx：按模板四个一级章节含义组织原生可编辑响应。用可编辑比较表覆盖九组合的site_id、option_id、组件数、DC容量、面积、年量、逆变器数、状态、含税基础额和预算余量，可拆分技术/报价表并调整行列、中英表头、样式、页序和分页。逐场地清楚列出推荐方案、状态、含税基础额、预算余量、选择理由及必要前置条件，可用表格或以S1/S2/S3起头的有字段标签段落。Q01–Q12均有实际响应、依据及尚未满足事项，不保留“待填写”占位。不得将未知修复费、补贴或核验状态扩展成已经确认，也不得将已有基础预算余量承诺为最终含未知费用后不超支。

3. /tmp_workspace/results/customer_email.md：给项目组的沟通草稿，清楚列出三场地的selected_option、status、gross_total、budget_margin，可用Markdown表格或明确字段标签的短段落；用日常语言解释关键淘汰理由、条件与下一步。仅保存，不发送，不宣称下单、付款、现场核验或实施审批已经完成。

4. /tmp_workspace/results/exceptions.csv：逐条列出所有明确失败或待核实项，包括已经不可行组合的其他未知项。至少含site_id、option_id、rule_id、status、observed、limit、source_file、source_locator、next_action，中文等价列名可用。rule_id是T09八项检查名，硬失败status=fail，条件status=unknown；保留实际值与限制值，缺值用空值或unknown，不猜数值。source_file指实际输入，source_locator可用原生位置或公开可见S/field定位，例如S1/usable_area_m2或对应表格单元格；单独可见场地列S1也是有效对象定位，但不能引用另一场地或无关需求。可选rule_source用technical_notes.pdf#Txx补充规则依据。文件存在或自述“已核验”不等于对应事实成立。

所有价格均为本题合成未税参数，报价边界按T12。未知补贴不抵减总价，未知修复费不能填已确认的0元，列入报价的核验费不等于核验已完成。四份原始输入保持原字节，只读不覆盖；新文件写results或系统临时目录。全程离线，不访问真实账号，不联网、不发送邮件、报批、下单、付款或创建定时任务。

## Expected Behavior

在三场地与三方案的固定参数下，准确计算必要基础报价、分类硬失败和条件，给出有依据的推荐、逐项响应和未决交接，不编造市场价、补贴或工程批准。

## Grading Criteria

### Automated group

- [ ] `business_correctness`: 读取实际原生工作簿重算值、九组合约束与推荐、Word比较/需求、沟通稿及例外元组和值，核对独立243数值和来源事实。
- [ ] `boundary_cases`: 按逻辑源字段在实际工作簿中作四组受控数值扰动，核验非零计算依赖及容量/面积/荷载/预算状态；检查整屋面计价、必要BOM、税舍入、未知原义和附条件选择。
- [ ] `delivery_integrity`: 四交付可解析，九组合与三场地、需求响应及例外集合完整；Word实际经锁定Office导出可见内容，输入与冻结Workspace保持不变。
- [ ] `evidence_binding`: 例外的实际值/限制/场地与原生源定位一致，不能用已存在但不支持主张的Q/T/另一场地定位替代真实依据。

### Judge group

- [ ] `decision_grounding`: 独立读取四输入和四真实交付，核验硬约束、全部必要成本、含税口径、推荐理由、未知修复费/补贴与核验条件；规则命中或候选自述不能代替完整业务判断。
- [ ] `usable_handoff`: 实际查看原生Word、工作簿、可信派生预览、沟通稿与例外表，判断读者能否维护输入、重算、复核九组合并继续确认缺口。

## Automated Checks

```python
def grade(**kwargs):
    from pathlib import Path
    import runpy
    import pdfplumber
    import pypdf
    root=Path(kwargs.get("workspace_path") or "/tmp_workspace")
    values=runpy.run_path(str(root/"gt/grader.py"))["grade"](root)
    return {key:values[key] for key in ("business_correctness","boundary_cases","delivery_integrity","evidence_binding","overall_score")}
```

## LLM Judge Rubric

### Criterion 1: 方案选择与未知范围 (key: decision_grounding, weight: 0.7)

判据：独立读取四输入和四真实交付，核验硬约束、全部必要成本、含税口径、推荐理由、未知修复费/补贴与核验条件；规则命中或候选自述不能代替完整业务判断。

**Score 1.0**: 九组合计算、逐项检查和推荐均被给定参数支持；正确优先排除硬失败，保留所有条件，不用低价或未知补贴补偿限制；整屋面范围、必要BOM、三个税率及舍入正确，四交付一致，未知费用/材料未被猜测，不虚构实际勘察、发电保证、审批或付款。

**Score 0.5**: 所有关键计算、约束、推荐、范围及条件正确，仅遗漏一项不改变业务结果的非关键解释或定位细节。

**Score 0.0**: 任一关键推荐/硬约束错误、遗漏必要费用或税范围、把S3条件/修复费当已核实或0、编造/抵减补贴，跨产物矛盾、来源不支持主张，或虚构实际工程/审批/付款结果。规则满分不能抵消这些关键错误。

### Criterion 2: 可重算交付与后续确认 (key: usable_handoff, weight: 0.3)

判据：实际查看原生Word、工作簿、可信派生预览、沟通稿与例外表，判断读者能否维护输入、重算、复核九组合并继续确认缺口。

**Score 1.0**: 四交付清晰、完整可用，工作簿真实依赖可识别输入而非静态结果，Word可编辑且比较/响应有对应关系；推荐、条件、例外和下一步可追溯，沟通稿未假装发送。接受等价工作表名/行列/宽明细表、中英表头、公式、段落和分页。

**Score 0.5**: 主要产物完整正确且可继续使用，仅一处非关键排版、维护说明或交接细节不足。

**Score 0.0**: 主要交付缺失/损坏/不可编辑/不可重算、重要内容隐藏或不可读、组合或条件无法对应、例外不可据以跟进，或只能依赖聊天自述。

## Workspace Path

```
workspace/general/challenge/01_Office_Documents/01_Office_Documents_task_013_proposal_delivery
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- AStudio去身份需求原型保留业务形态；全部设备/屋面/价格为合成固定数据，GDPval仅方法参考，未复制公开原题。纯文本、离线、非代码主交付，不增加六题视觉配额；L4为实测前预估。
- GT早于参考，实际Word和PDF分别双路径读取，Decimal与分数计算交叉核对243数值及九个最小整片不等式。参考只是满足契约的一种表达，不要求作者坐标或公式样式。
- 真实Office基线与四组源参数扰动核数值/约束及可见汇总；30固定不适用结构零不强制伪公式。推荐选择是明确的当前输入决策记录，不要求自动优化新情境。
- 61项完整基线矩阵（17合法表达、37候选负例、5基础设施、2语义专用），加7项例外缺交专项回归与1项实际公式错误验证；三批分别保留源码绑定，不声称69项全在最终同一版执行。作者参考规则分不等于hybrid语义总分，尚无本题正式Harness成绩或实测难度。
- 规则只覆盖受控数值/状态/ID/来源和原生观察；完整理由、虚构补贴或现实批准、未知修复费用的含义及实际可读性必须由独立Judge查看真实文件。
- 缺GT/helper/已声明依赖、引擎/字体/锁漂移或规则崩溃属于评测异常；候选漏交、损坏或业务错误按相关检查点失分。900仅元数据，不据此设置候选总执行截止。
