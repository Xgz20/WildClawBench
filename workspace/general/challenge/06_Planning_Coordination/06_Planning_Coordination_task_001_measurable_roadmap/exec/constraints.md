# 2027 第一季度行动规划约束

C01 权威与事实边界
约束文件中的已批准目标和资源上限优先于 strategy_notes.docx 的讨论愿望。baseline.csv 的 verified 行才是当前可用事实；旧看板不得混用。所有未来指标都是拟议目标，不能写成已实现或保证增长。无需开展真实试点。

C02 周期与角色
规划窗口为 2027-01-04 至 2027-03-28。双周周期不可跨期借用容量。只使用 PM、OPS、ANALYST 三个已确认角色；每项动作有且只有一个牵头角色，协作者工时另列。基线容量为扣除日常事务后的可用小时，不得再乘以全职天数。PRODUCT 不是已确认资源。

| period | start | end |
| --- | --- | --- |
| P1 | 2027-01-04 | 2027-01-17 |
| P2 | 2027-01-18 | 2027-01-31 |
| P3 | 2027-02-01 | 2027-02-14 |
| P4 | 2027-02-15 | 2027-02-28 |
| P5 | 2027-03-01 | 2027-03-14 |
| P6 | 2027-03-15 | 2027-03-28 |

C03 目标与可测定义
| goal_id | metric_id | minimum_rate | minimum_sample | due_period | baseline_status |
| --- | --- | --- | --- | --- | --- |
| G1 | M1 | 0.85 | 40 | P6 | verified |
| G2 | M2 | 0.90 | 20 | P6 | verified |
| G3 | M3 | 0.80 | 10 | P6 | verified |
| G4 | M4 | unknown | unknown | P1 | unknown |

G1 对应 M1。至少40个合格工单的未来观察窗，按相同首响定义拟定不低于85%的目标；不是承诺能实现95%。G2 对应 M2。至少20份引导材料抽查，按同样完整性定义拟定不低于90%的目标。G3 对应 M3。至少10项预登记到期承诺，拟定不低于80%的按原到期验收目标。目标分子分母可选择更大的合理样本，比例须由分子除以分母计算，不要求复刻某个排期。
G4 对应 M4。当前激活率未知；P1交付合格账户、去重事件和观察窗的定义及采集验证方案，不能填0%、7%或任何数值增长承诺。真实基线待后续采集；本季度路线图中明确未知和复核责任。

C04 必须覆盖的成果与成本下限
下表描述可验收成果，不是指定动作措辞。可自行拆分/合并动作，同一动作可覆盖多个outcome；每个outcome选择一个方法，分期工时按outcome归属累计。合并不会消除各成果各角色的最低成本。预留/待条件动作同样占用排期容量。无需提交脚本。

| outcome | goals | method | PM | OPS | ANALYST | predecessors | latest | gate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| O1 | G1,G2,G3,G4 | definitions | 6 | 2 | 6 | - | P1 | none |
| O2 | G1 | triage | 2 | 10 | 2 | O1 | P3 | none |
| O2 | G1 | scripts | 4 | 6 | 4 | O1 | P3 | none |
| O3 | G1 | ticket_sample | 0 | 14 | 4 | O2 | P5 | none |
| O4 | G2 | checklist | 4 | 8 | 2 | O1 | P3 | none |
| O5 | G2 | retrospective | 2 | 8 | 4 | O4 | P5 | none |
| O5 | G2 | live_pilot | 2 | 12 | 4 | O4 | P5 | Q1 |
| O6 | G3 | commitment_log | 6 | 2 | 2 | O1 | P3 | none |
| O7 | G3 | closure_sample | 4 | 4 | 2 | O6 | P5 | none |
| O8 | G1,G2,G3,G4 | review | 6 | 4 | 8 | O3,O5,O7 | P6 | none |

O1 交付统一指标字典、现状复算与G4采集方案。O2 交付分流规则或应答脚本并规定接单验收。O3 交付至少40个工单的首响复测计划和记录模板。O4 交付20份引导所用的核对表和完整性判定。O5 retrospective是复盘已有20份材料的内部演练，不宣称真实新客转化；live_pilot是新客试点。O6 交付承诺登记和原到期不改写规则。O7 交付至少10项承诺的观察与验收计划。O8 汇总三项比率、G4缺口、资源占用和下一步决策。
每条依赖表示前序成果全部完成后的下一个周期才能开始。可并行但不可在同一周期声称已完成依赖。O8固定在P6，其他动作可在P1至P5内按上限自由排布。跨期动作须把实际小时列到所处各期。

C05 未决批准与替代路径
Q1 新客试点需产品负责人确认数据采集和访谈许可，当前状态unknown，最早P3才可能获准。由PM在P2末前复核。不得把预期批准写成已批准，也不得把PRODUCT口头协助折算为容量。可选择retrospective的内部材料演练按计划推进；若选择live_pilot，最早P4，标记conditional并预留完整资源，其后依赖该成果的复盘也必须conditional。Q1未决时不启动真实接触。路线图必须记录Q1、责任PM、复核截止P2、未知状态、选用内部演练或待批准的处置。

C06 交付的数据结构
roadmap.xlsx包含四类有表头记录：目标(goals)、动作(actions)、工时(loads)、决策(decisions)。可同页或多页，页名、列顺序和动作ID自由；中文/英文列名均可。每类记录给出下列字段并保留业务编号G1-G4、M1-M4、O1-O8、Q1、P1-P6及角色代码，以便后续导入。不要把纯图片作为唯一表格。
goals: goal_id, objective, metric_id, definition, baseline_n, baseline_d, baseline_rate, baseline_status, target_n, target_d, target_rate, target_kind, owner, due_period, acceptance, source_ref。
actions: action_id, outcome, method, goal_ids, action, owner, start_period, end_period, depends_on, status, acceptance, source_ref。
动作每行写一个outcome，同一action_id可在多个成果行重复，method对应本行outcome；拆分同一outcome可以使用多个不同action_id，但该成果方法一致。动作ID不得与O1-O8重复，以免依赖歧义。额外业务动作可使用其他outcome编号，但仍需计入资源和依赖。
loads: action_id, outcome, period, PM, OPS, ANALYST。
decisions: decision_id, status, owner, review_period, disposition, source_ref。
goals的baseline_status用verified或unknown；G1-G3的target_kind用proposed，G4用measurement_only。动作status用planned或conditional。depends_on可使用动作ID或成果outcome编号，多个值用逗号/分号/空格分隔。loads以action_id+outcome+period唯一，不允许用负工时抵扣。
baseline_rate和target_rate是分子/分母的计算列，分子分母改变后应更新；比率以数值0..1或百分比单元格存储，分子分母是数字。G4的比率与数值目标留空或明确unknown，不用0代替缺失。目标、动作、验收必须能关联；说明文档解释依据、假设、未知、依赖和取舍，不把行动计划说成已执行结果。
source_ref使用baseline.csv的id+period或constraints.md的C01-C06、strategy_notes.docx的N1-N5；可以写多个真实定位。explanation.docx附一张简短事实核对表，列fact_id/value：M1基线、M2基线、M3基线、M4基线、Q1状态、O5方法；接受百分数、数值比率或unknown等价表示。正文语言自由，取舍合理性由独立审阅判断。
