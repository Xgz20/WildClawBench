---
id: general_hard_data_analysis_task_007_rolling_ledger
name: 跨月客户余额与回款勾稽
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
    - path: results/ledger.xlsx
      role: candidate_deliverable
    - path: results/exceptions.csv
      role: candidate_deliverable
    - path: results/method.md
      role: candidate_deliverable
scoring_runtime:
  office: true
dataset_report: {"category": "data_analysis", "category_name": "数据分析与表格建模", "category_order": 1, "checkpoint_capabilities": {"boundary_cases": ["reasoning_planning"], "business_correctness": ["data_processing"], "delivery_integrity": ["verification_delivery"], "evidence_binding": ["verification_delivery"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-challenge"}
---

# 跨月客户余额与回款勾稽

## Prompt

请构建跨月客户余额与回款勾稽模型，交给同事后可在Excel底稿补录更正，直接看到流水重排和账龄变化；不能只交静态汇总。

读取/tmp_workspace/orders.xlsx、payments.csv、opening.csv和rules.md。orders.xlsx有180条订单/退货物理记录，payments.csv有90条银行物理记录，opening.csv有12客户期初；全部为合成CNY练习。严格使用rules.md固定的业务期间、上海资料截点、先范围后去重、同客户引用、整组超额待核、逐笔顺序、带符号现金和期末FIFO口径，不按运行日期或物理行序计算。不联网，不改原输入。

交付三个实际文件，每份不超过5MiB，全部放/tmp_workspace/results：
1. ledger.xlsx：自包含、可编辑原生工作簿。保留全部源行和期初；金额、business_date和上海本地entered_at为实际驱动模型的可修改原生数值/日期时间输入，CSV原ISO文本可另列。保留一个真实依赖输入的模型，不做三套平行模型、不写死当前余额、不只重算总额。修改一条迟录记录的本地录入时点后，符合条件的业务须按原业务日加入，流水序号、每笔余额、客户、月度、账龄和控制联动。保留迟录/排除行，不能制作前先过滤丢掉。允许递推或按业务键累计等合理公式，公式数量不设门槛；不含宏或外部数据链接。

在可见、清楚的一行表头中保留下列语义字段，英文键或明确对应中文均可。Sheet名称、位置、列序、客户分表和合理辅助列不限，不锁作者坐标/公式/排序编码。各表记录唯一，不能用隐藏结果或混杂快照代替实际输出：
- 客户汇总：customer_id, opening_balance, invoice, sales_return, receipt, refund, matched_net_cash, closing_balance, unresolved_order_rows, unresolved_payment_rows, posted_events, receivable_remaining, customer_credit, not_due, d1_30, d31_60, d61_90, d90_plus
- 已确认业务流水：record_id, customer_id, customer_sequence, business_date, event_type, logical_id, ar_delta, balance_before, balance_after, global_sequence
- 全部源行处理审计：record_id, source, logical_id, customer_id, decision, unresolved_flag, cash_disposition, bank_known_delta
- 客户月度：customer_id, month, opening_balance, invoice, sales_return, receipt, refund, closing_balance
- 有效债权/账龄明细：source_record_id, customer_id, document_no, business_date, due_date, original_amount, return_amount, net_amount, allocated_cash, remaining, overdue_days, bucket

source为orders/payments；event_type沿用invoice/sales_return/receipt/refund。流水只列已确认事件并按客户、业务日、类型优先级、record数字序可读排序，customer_sequence从每客户1起，global_sequence为该可见顺序的1起序号。审计保留所有物理行；decision分别说明posted、范围排除、duplicate、conflict、状态/币种排除、非法金额/类型、未知客户、原单歧义、跨客户/缺失/不早于引用及整组退货/退款超额，可用对应中文；unresolved_flag为实质未决0/1。未知银行金额留空并说明unquantified，不能填确认0；cash_disposition区分not_applicable/outside_scope/duplicate/unquantified/known_suspense/matched。
账龄含所有有效债权，即使已清；期初source_record_id为OPEN_加customer_id，本期为原invoice的record_id。可保留inactive潜在槽位，但需有recognized_flag明确其不是债权。已清项bucket=cleared、overdue_days留空，未清项按实际到期日分not_due/d1_30/d31_60/d61_90/d90_plus。不同英文/中文等价状态可清楚对应，客户预收单列，剩余应收减预收等于净应收。
另有可见控制项表，以control、value两列表头或对应中文标识，控制键为：bank_known_net, matched_net_cash, known_suspense_net, known_cash_gap, closing_net_AR, remaining_receivables, customer_credit, unresolved_order_groups, unresolved_payment_groups, unquantified_bank_groups, unresolved_order_rows, unresolved_payment_rows, fully_identified。这些键只标识需核对内容，不给答案。真实差额应显示0.00；存在未决时fully_identified必须为false。控制是终端诊断，不能反向填平模型。

2. exceptions.csv：UTF-8，列出全部非posted物理行，区分范围排除、重传和实质未决。至少包含record_id, source, logical_id, customer_id, decision, unresolved, cash_disposition, known_bank_delta, source_file, source_locator, next_action。unresolved用true/false或1/0；known_bank_delta有已知现金时填带符号金额，其余留空，cash_disposition说明为什么。source_file是真实orders.xlsx或payments.csv，source_locator可用唯一record_id回查。每行写明后续行动，不能吞掉未匹配负退款或对未知金额造零。
3. method.md：说明业务日与可得性、分组去重/冲突、整组待核、余额负值、FIFO、已知暂挂/未知金额和控制边界；明确CSV/说明对应保存时基线，Excel补录后须重新导出复核。列明固定期间和上海截点；为便于核对，也用“control键: 计算值”各列一次上述13个控制。差额0不表示全部真实交易已识别或结清，不虚构审计、审批、发送或真实付款。

评分在独立副本中清除公式缓存后实际重算，并分别激活一条迟录订单、一条迟录回款和一条迟录退款，核对逐笔/客户/月度/账龄及其余结果。原交付不改。全静态正确基线不能获得动态模型大部分分；无有效数字响应时业务检查点最高0.5。输入保护或原生模型不完整会影响交付/边界。完成前核对三份产物一致，原始四份输入保持只读，离线完成，不连接真实账号、不发消息或执行真实财务业务。

## Expected Behavior

按源先行口径构建一个原生动态账簿，逐笔、客户、月度、FIFO和带符号现金同时正确；保留未决/未知、完整底稿及可回查例外。L4为设计预估。

## Grading Criteria

- [ ] `business_correctness`: 构建逐客户按业务时间滚动的余额模型，处理补录和退款，产出差异清单与账龄分析，控制合计必须勾稽。
- [ ] `boundary_cases`: 逐项识别并正确处理：按行序计算；跨客户串余额；把控制总数一致当逐笔正确。以独立反例验证，不只检索关键词。
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
workspace/general/challenge/data_analysis/general_hard_data_analysis_task_007_rolling_ledger
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- 线上来源仅用途原型，全部数据合成。25,422项双路源核对独立于候选；非人工专家。SpreadsheetBench仅方法参考。
- 自动规则按.55/.25/.15/.05加权；业务为客户.20/流水.25/账龄.20/月度.15/控制.10/例外.10，边界为状态类别宏平均.25和三组原生补录响应.75。
- 每组补录只改候选自身匹配原始输入中的本地entered_at，真实重算，核对所有变化字段并要求其余已存在结果正确。保留快照时逐个验证实际驱动入口，不锁作者坐标；无有效数字响应时业务最高.5。
- 表头、Sheet、列序及等价标量公式可变，布局不锁作者实现。自动验收只证明可见表、计算、输入响应和固定控制事实，不声称开放说明质量、完整视觉质量或会计专家结论。
- 保护输入被改使边界/交付/来源分为0且业务最高.5。缺GT/helper/引擎/锁漂移、Office超时及合法未支持结构保持evaluation_error，不计候选零分。
- 900仅元数据，四端执行及L4难度/组合区分度均待实测；本题作者控制与Worker验收不是模型/Harness成绩。
