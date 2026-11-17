---
id: general_hard_office_documents_task_011_linked_report_update
name: 财务修正后的多产物同步更新
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
judge_evidence:
  required:
    - path: results/finance_revised.xlsx
      role: candidate_deliverable
    - path: results/report_revised.docx
      role: candidate_deliverable
    - path: results/deck_revised.pptx
      role: candidate_deliverable
    - path: results/change_impact.json
      role: candidate_deliverable
scoring_runtime:
  office: true
  office_render: true
dataset_report: {"category": "office_documents", "category_name": "文档与办公交付", "category_order": 0, "checkpoint_capabilities": {"automated.boundary_cases": ["reasoning_planning"], "automated.business_correctness": ["data_processing"], "automated.delivery_integrity": ["verification_delivery"], "automated.evidence_binding": ["verification_delivery"], "llm_judge.decision_grounding": ["data_processing"], "llm_judge.usable_handoff": ["verification_delivery"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-hard"}
---

# 财务修正后的多产物同步更新

## Prompt

请把澄宁精密制造的财务重述同步到已有工作簿、Word报告和PPT，并留下可复核的更正影响记录。全部材料为合成离线业务资料。读取 /tmp_workspace/finance.xlsx、/tmp_workspace/report.docx、/tmp_workspace/deck.pptx 和 /tmp_workspace/corrections.csv；CSV八项更正本身均已批准，不代表后续对外确认、付款或其他业务审批已完成。

交付四份实际文件：/tmp_workspace/results/finance_revised.xlsx、/tmp_workspace/results/report_revised.docx、/tmp_workspace/results/deck_revised.pptx、/tmp_workspace/results/change_impact.json。把八项更正应用到各自年份、月份和指标，联动修正全部原有期间汇总、比率、同比基期、Word正文/表格/真实脚注、PPT正文/原生图表/真实内嵌数据和讲者备注。结论按各自真实期间更新，不把季度现金方向代替累计方向，不把月末应收余额当期间流量，也不把本题简化经营利润称为净利润。工作簿Scope中未提供的信息继续保持未知，不能补Q4或编造执行结果。

保留原业务字段、事实行身份与期间、可见K/P/F标识、图表系列名和类别。只改八项源事实及其传播影响，其余源值、未受影响期间、无关制度和限制说明保留。工作簿源金额保持原生数值和CNY元口径，衍生结果保留真实依赖这些源输入的可重算公式，不能填静态结果或常量公式。报告与PPT延续万元和百分数口径；图表为可编辑原生对象，实际内嵌工作簿与图表缓存同步，负值必须在图中可见。Word两条原生脚注及其实际挂接关系保留。可以合理改变工作表名称、行列顺序、等价公式、样式、分页和页序，但要保留全部业务内容与可追溯关系。

change_impact.json使用一个JSON对象，其中corrections为八条事件。每条包含correction_id、source、targets。source包含file、locator、period、metric、old_value、old_unit、new_value、new_unit、normalized_new_cny；源file为corrections.csv，locator可用实际row:N或更正ID。targets为逐项影响记录，每条包含file、locator、before、after、unit。共享业务节点需在每个相关更正事件中分别记录；覆盖原材料全部受影响的业务单元格、指标、表格值、脚注、结论及图表系列/类别点和必要坐标约束，新增辅助计算节点可另作说明。

target的file使用results下相对路径，或以/tmp_workspace/开头的规范路径；locator指向当前交付中的实际位置。工作簿用Sheet!A1；Word用实际paragraph:N、table:N/row:R/cell:C或相应可见K/P/F标识；PPT用实际slide:N/shape:S/paragraph:P、讲者备注节点，以及chart:N/series:S/point:P（point从0起），可使用原生投影的等价plot/val定位。before、after应是该实际节点修改前后的值，金额/比率unit可为CNY、元、万元、ratio、%；允许等价单位换算。结论方向用positive/negative/zero，收入与利润方向对象用revenue_yoy、op_yoy，现金方向对象用q2、ytd；坐标约束可用axis_min或auto_axis_allowed对象。保留范围和未知项可另列说明。不要填写宿主机绝对路径，也不要把“路径存在”或账本自述当成内容已更新的证明。

原四份输入保持原字节；所有新交付与工作文件写results或系统临时目录。离线完成，不访问网络、真实账号，不发送消息、报批、付款或新建定时任务。

## Expected Behavior

八项批准更正同步到可重算工作簿、Word与PPT的全部实际业务节点，保护无关事实与未知范围，并交付可验证的更正影响账本。

## Grading Criteria

### Automated group

- [ ] `business_correctness`: 核对八项源事实、100个衍生结果及实际Word/PPT数字与图表点，分别按真实业务字段/可见标识定位，不以账本声明替代文件。
- [ ] `boundary_cases`: 验证全部月度输入的真实公式响应、零/负现金/万元/同比基期与应收快照、82个保护源值、脚注挂接、实际内嵌表/缓存/负轴和可观察结论边界。
- [ ] `delivery_integrity`: 四文件可解析且原生可编辑，公式完整，Word/PPT实际经共享双格式锁导出可见内容，输入和冻结Workspace保持不变。
- [ ] `evidence_binding`: 逐事件核对完整业务影响闭包、修改前后值和实际当前节点；重复、缺项或已存在但不支持主张的定位均不作为有效绑定。

### Judge group

- [ ] `decision_grounding`: 独立阅读原始四份输入与全部实际交付，核对两期口径、全部数字/脚注/图表/备注和变化解释；规则观察与账本不能代替真实业务判定。
- [ ] `usable_handoff`: 直接查看原生Word、工作簿、PPT与账本和冻结可信派生预览，判断可读、可编辑、可重算及逐事件复核能力。

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

### Criterion 1: 重述口径与跨产物结论 (key: decision_grounding, weight: 0.7)

判据：独立阅读原始四份输入与全部实际交付，核对两期口径、全部数字/脚注/图表/备注和变化解释；规则观察与账本不能代替真实业务判定。

**Score 1.0**: 八项更正与完整传递影响正确，源事实/公式/报告/图表/内嵌数据/备注一致；基期、零、负号、单位、季度与累计现金及期末快照均正确，无虚构Q4、净利润、付款或其他审批；无关制度与限制含义保留。

**Score 0.5**: 全部关键数值、源事实、公式、传播范围和结论正确，仅遗漏一项不影响复核的非关键解释或引用细节。

**Score 0.0**: 漏关键更正或传播，基期/单位/期间/符号/快照错误、常量模型，正文/图表/脚注/备注与账本矛盾，误把季度负现金推广为累计负现金，改变保护含义或编造未知/后续办理结果。证据不足时保持未决，不猜测。

### Criterion 2: 原生文件与更正交接可用性 (key: usable_handoff, weight: 0.3)

判据：直接查看原生Word、工作簿、PPT与账本和冻结可信派生预览，判断可读、可编辑、可重算及逐事件复核能力。

**Score 1.0**: 三份原生业务产物可继续使用，四图真实可编辑并有一致内嵌数据，负柱、关键数字/脚注/表格实际可见且清晰；账本覆盖全部相关业务节点，定位对应当前文件，无越界修改。允许等价布局、页序、公式、措辞与单位表示。

**Score 0.5**: 主要产物完整正确且可使用，仅一项非关键排版、说明或定位不足，不影响复核与后续维护。

**Score 0.0**: 主要产物缺失/损坏/非原生，模型写死，图表截图或内嵌数据失效，负值被裁掉，重要内容遮挡/不可读，账本与实际文件无法对应，或只能依赖聊天自述。

## Workspace Path

```
datasets/general-hard/workspace/office_documents/general_hard_office_documents_task_011_linked_report_update
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- 保留AStudio去身份需求原型，全部附件与数字为合成自建；SpreadsheetBench仅方法参考，未复制原题。L4为实测前设计预估，尚未验证四端难度或区分度。
- 独立GT从真实源文件、Decimal/Fraction及实际源公式AST建立，先于参考；282数值节点、143传播节点。参考只是合法表达之一。
- 自动规则读取真实原生数字/脚注/缓存/内嵌表及三种实际输入响应，覆盖100公式；完整语义、未知主张、保护含义与视觉可用性由独立Judge核验。
- 评分使用core0.12/score0.20同源私有helper和显式both共享v2锁，Word与PPTX导出各自留回执。必须声明并真实probe PDF依赖与引擎/字体，不能套旧单格式锁。
- 51项完整基线矩阵，加Word定位/脚注措辞7项、P21余额单位3项最终定向回归；三轮分别保留确切GT绑定，不声称61项全在同一源码版本上运行。作者控制及规则参考分不等于hybrid完整分；三项语义边界例规则仍满分，必须由独立Judge判定。未据此生成正式Harness成绩或冻结发行。
- 缺GT/helper/依赖、锁/字体/引擎漂移和规则失败为评测异常，候选漏交或业务错误按指标计分；900仅为任务元数据，不据此设置候选总截止。
