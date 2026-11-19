---
id: general_hard_office_documents_task_015_board_decision_pack
name: 经营材料到管理层决策包
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
    - path: results/memo.docx
      role: candidate_deliverable
    - path: results/options.xlsx
      role: candidate_deliverable
    - path: results/deck.pptx
      role: candidate_deliverable
    - path: results/evidence.json
      role: candidate_deliverable
scoring_runtime:
  office: true
  office_render: true
dataset_report: {"category": "office_documents", "category_name": "文档与办公交付", "category_order": 0, "checkpoint_capabilities": {"automated.boundary_cases": ["reasoning_planning"], "automated.business_correctness": ["data_processing"], "automated.delivery_integrity": ["verification_delivery"], "automated.evidence_binding": ["verification_delivery"], "llm_judge.decision_grounding": ["data_processing"], "llm_judge.usable_handoff": ["verification_delivery"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-challenge"}
---

# 经营材料到管理层决策包

## Prompt

请为青岚商服形成经营诊断、三方案约束比较和6页管理层决策汇报，判断时点固定为2026年10月2日。只依据给定合成材料，区分可计算事实、被反驳的主张与材料不足以确认的结论，给出有条件且可继续办理的建议。

读取/tmp_workspace/operations.xlsx、/tmp_workspace/interviews.docx、/tmp_workspace/market_notes.pdf和/tmp_workspace/decision_constraints.md。渠道键direct/platform/dealer/renewal分别为直销/平台/经销/续费；I01-I12、G01-G06、M01-M03和D01-D12是材料可见定位。市场PDF可提取全部文字，离线完成，无须视觉理解。

交付以下四份实际文件：

1. /tmp_workspace/results/memo.docx：原生可编辑的经营诊断与决策建议。比较公司2025/2026年Q3收入、毛利、按总额加权的毛利率、期间收款、收款与同期收入金额比；给出收入、毛利和收款同比。列明2026年Q3四渠道的收入、毛利及毛利率，并核对经销是否增长、平台毛利率等关键访谈。关键数字用有明确期间、渠道、指标和单位的可编辑比较表或清楚标记的短段落表达，中文或语义等价英文标签均可，不要求作者表格坐标、工作表名或固定版式。纯段落数字记录可写成“2026年Q3 公司：收入…万元；毛利…万元；加权毛利率…%；期间收款…万元；收款收入比…%”。
逐组审查G01-G06，拆开一段发言中算术成立、被数据/政策反驳及未知的不同主张，保留来源和解释。至少分别说明净利润口径、价格或投放的因果效果、市场样本外推，以及收款/专项账户口径四类不能推断的结论。不能把缺失原因补为未提价、把试用意向当购买、把未知收益当已知零。
比较A/B/C原排期的最低余额、最低日期、期末余额与最大底线缺口；提出一个明确的当前建议，解释取舍、负责人角色、需要检查的可观察条件及继续/暂停触发。可以选择C、A仅首阶段、A按允许条件延期等不同合理安排，不强制唯一方案。选择A调整时另列该实际调整的数值和完整条件，不把纸面建议写成已批准、已到账或已执行。

2. /tmp_workspace/results/options.xlsx：原生可编辑、可重算的专项账户方案比较。保留有标签的可修改数值输入initial_cash_cny（期初现金）与floor_cny（现金底线），中文等价标签可用，元或万元须清楚标明。按给定确认排期、方案付款与允许调整计算，不计入未确认收款或未核实收益。变更期初或底线后，真实公式应更新逐事件余额、缺口和可行状态，不能写死结果或只用常量公式伪装。
覆盖三个原排期A/B/C的期初及每个实际基线/方案收支日期，保留case_id/日期/节点余额（如balance_cny或closing_cny），允许按方案分行、日期×方案宽表，或case_id/日期/metric/value明细表，不强制某种方向或工作表名。日期用含年的真实日期或ISO形式，不能仅用月末余额替代中间节点。
对每个原方案至少列minimum_cny（最低余额）、minimum_date（最低日期，可列任一正确最低日）、end_cash_cny（期末余额）、first_violation（首个低于底线日期，无违规明确写none/无）、maximum_floor_gap_cny（最大底线缺口）及cash_feasible/cash_status（当前现金计划是否在底线内）。中文等价表头可用，金额单位一致且精度充分。现金可行仅表示当前给定计划满足底线，不代表审批或未来收款已经发生。
若当前建议为A仅首阶段或延期版，另建该安排的逐节点模型和同样的摘要，保留三方案原排期结果。三方案互斥，不能叠加、挪入公司历史收款、自行改B固定日期或擅增融资。输入变更后可提示重新核对建议，不要求自动优化新情境。

3. /tmp_workspace/results/deck.pptx：恰好6页（含封面，如有）的原生可编辑决策汇报。覆盖经营数字、渠道与样本限制、专项现金、三方案对比、当前建议、条件和下一步。以可编辑表或有明确标签的文字列出A/B/C的最低余额、期末余额和首次违规日期；如建议A变体，也呈现该安排的关键数值及条件。与Word和Excel一致，保留负现金与底线含义。可使用任意有助表达的原生图表或布局，不要求特定图表数量；如果使用图表，类别、值、正负号及真实内嵌数据应与材料和数值模型一致，不能用隐藏内容或仅讲者备注代替读者可见结论。

4. /tmp_workspace/results/evidence.json：结论到实际源材料及交付位置的索引，JSON组织可自定，不需要猜私有GT的主张ID。每项有具体主张、支持/反驳/未知状态、源文件与可见定位、理由及Word/Excel/PPT对应位置。索引覆盖六组访谈及四类未知，使用真实页/段落/公开编号/Sheet与单元格/幻灯片位置，只有文件存在不代表支持主张。引用原文时须忠实；不引用私有GT。
在一处清楚标记本轮完整建议，例如selected_option/selected_case/推荐方案字段的值为C、A仅首阶段或A第二阶段延期等业务名称，或使用A_phase1/A_deferred等明确安排名，不能仅写“A”而省略实际阶段安排。该建议与读者可见的Word、PPT及实际现金模型一致，其它JSON字段和顺序自定。

四份输入只读并保持原字节；所有新交付写/tmp_workspace/results，工具临时文件可用系统临时目录。不联网、不访问真实账号、不发送消息、不执行审批/交易/付款，不创建定时任务。资料中的确认排期是模型基线，不能当未来实际到账事实；保留所有未知范围。

## Expected Behavior

用固定经营、访谈和市场材料形成可追溯诊断与三方案比较，给出满足专项现金和权限的条件建议；保留因果、总体、利润与未来收款的未知，不虚构执行。

## Grading Criteria

### Automated group

- [ ] `business_correctness`: 从真实Office重算读取三原计划和所选变体的现金摘要/实际节点、Word经营数字、Word/PPT比较与建议，核对独立事件模型；不依赖参考坐标。
- [ ] `boundary_cases`: 真实改变工作簿中有标签的期初与底线，核初始+5000、底线等于及高于C最低余额的事件余额/缺口/状态。检查原输入完整性，不要求自动优化新建议。
- [ ] `delivery_integrity`: 四交付可解析、原生内容可见，实际Word/PPT经锁定双格式Office导出，PPT恰好六页；三原计划及实际所选变体完整，Workspace与输入不被评分修改。
- [ ] `evidence_binding`: 核实际原文引文（如给出）、公开编号/页/Sheet定位和交付索引覆盖；已有节点是否在语义上支持主张由独立Judge判断。

### Judge group

- [ ] `decision_grounding`: 独立读取四原始材料、四真实交付和规则派生证据，核查数字、冲突推理、不能推断范围、方案权限及条件。规则分只表示有界检查，不替代完整业务判断。
- [ ] `usable_handoff`: 查看真实Word、工作簿、六页PPT、可信Office预览和索引，判断是否可复核、维护输入并按条件继续办理。

## Automated Checks

```python
def grade(**kwargs):
    from pathlib import Path
    import runpy
    import pdfplumber
    import pypdf
    root=Path(kwargs.get("workspace_path") or "/tmp_workspace")
    scores=runpy.run_path(str(root/"gt/grader.py"))["grade"](root)
    return {key:scores[key] for key in ("business_correctness","boundary_cases","delivery_integrity","evidence_binding","overall_score")}
```

## LLM Judge Rubric

### Criterion 1: 经营判断与约束决策 (key: decision_grounding, weight: 0.7)

判据：独立读取四原始材料、四真实交付和规则派生证据，核查数字、冲突推理、不能推断范围、方案权限及条件。规则分只表示有界检查，不替代完整业务判断。

**Score 1.0**: 经营数字、期间、加权口径及同比正确，六组冲突逐主张处理。6/8的75%样本算术成立但总体/因果未知，缺失原因不变为未提价；意向不冒充购买，资料重叠未知，毛利不冒充净利润，期间收款收入比不冒充订单回收率/坏账。专项账户逐节点满足底线，排除未确认款与历史公司收款，B合同日期不擅改。当前选择合理并保留所有尚未满足的条件，A延期仍须实际到账、后续节点复核及阶段2批准。允许多种满足约束的建议，不主张唯一ROI最优，不把未知收益改成零或编造已批准/执行事实。

**Score 0.5**: 关键数字、结论、现金约束、权限及未知范围正确，仅遗漏一处不改变业务结果的解释或定位细节。

**Score 0.0**: 任一关键数字/期间/推荐/现金约束错误，平均毛利率、只看期末、偷计未确认款、自改B日期、跨产物实质矛盾，或对缺失原因/价格因果/市场外推/净利润/完整现金作无依据断言。把实际条件写成已满足、未知收益填已知零、编造审批付款或证据亦为0。规则1.0或存在正确关键词不能抵消这些错误。

### Criterion 2: 可重算决策包与办理条件 (key: usable_handoff, weight: 0.3)

判据：查看真实Word、工作簿、六页PPT、可信Office预览和索引，判断是否可复核、维护输入并按条件继续办理。

**Score 1.0**: 四交付完整、原生可编辑、可读，真实公式响应输入；三原排期和实际所选变体可对应，Word/PPT建议一致，索引定位支持对应主张，负责人、可观察检查条件与继续/暂停触发清楚。图表如有，其缓存/内嵌数据、正负号、类别及可见效果正确，不只核表格文字。接受等价表头、行列、明细/宽表、段落、JSON组织和不同安全建议。

**Score 0.5**: 主要交付正确且可继续办理，仅一处非关键排版、维护或交接说明不足。

**Score 0.0**: 主要产物缺失、损坏、不可编辑/不可重算/重要内容隐藏或不可读，PPT页数错误，模型或阶段无法对应，图表与实际数据矛盾，索引只列存在但无关位置，或依赖聊天自述而没有可用交付。

## Workspace Path

```
workspace/general/challenge/office_documents/general_hard_office_documents_task_015_board_decision_pack
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- 保留AStudio去身份需求原型的经营改进工作形态，全部公司/访谈/金额合成，GDPval仅方法启发。纯文本、离线、非代码主交付，不增加六题视觉配额；L4仍为未实测设计预估。
- 实际四输入先于参考形成GT；源原生读取、Decimal/Fraction两套经营与事件算法、原生Office重算独立核验。参考是合理表达之一，不强制C、作者坐标/工作表名或特定版式。
- 现金可重算为核心要求；经营数字可在Word比较表或明确标签段落呈现。更改输入后需要重新核对建议，不要求自动重新优化。
- 完整48项矩阵与3项定向补充通过，关键评分源码摘要一致：15个合法表达正例、25个候选负例、5个基础设施门禁、6个规则满分但须独立语义裁判处理的反例。静态结果与有效常量公式的三个真实依赖响应均0分；缺交或不可见内容的完整性分为0，明确选择原A/B违反现金底线限制业务分。此前9项等价探针的一次延期误拒及首轮46项矩阵另存原始版本；未把它们冒充最终同一源码的验收。
- 私有gt/validate_authoring.py可用--office-lock、--render-lock和--output-dir显式传入已探测的Office锁、both双格式字体锁及仓库外一次性输出目录，复跑作者控制；--list-cases仅列规格。它不参与候选规则评分，缺基础设施不产生能力分。
- 规则仅覆盖有界数字、日期、输入响应和定位；完整因果、否定范围、未知、现实承诺、索引是否真正支持主张及图表/视觉可用性，必须由独立Judge读真实文件判断。不能把作者规则1.0当作hybrid总分、业务正确完成或实测区分度。
- 缺GT/helper/声明依赖、引擎字体锁漂移或规则自身崩溃属于评测异常，不补能力零分。候选漏交、损坏、实际公式错误或业务错误按相关检查点失分。900仅任务元数据，不设置候选总执行截止。
