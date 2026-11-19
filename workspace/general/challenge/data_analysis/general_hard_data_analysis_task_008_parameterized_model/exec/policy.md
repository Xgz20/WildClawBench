# 2026年第三季度提成模型口径

本题为合成工资测算，不是实际发薪、纳税或人事审批。业务月份固定2026-07、2026-08、2026-09，金额CNY。只使用提供的员工、考勤、销售、退款与三套管理参数，不取运行日或外部薪税规则。

## 原始记录与参数

payroll.xlsx含员工12行、考勤36行、销售110行、退款34行。每条ID唯一；员工与考勤、销售、退款按employee_id匹配，退款用original_sale_id匹配原销售。原生月份均表示给定业务月，不是文件日期。保存全部底稿，不因当前无影响先删除行。

先按本季度月份筛选，再检查状态。销售仅posted计入，各员工原月gross_sales是该月posted销售金额之和，真实0保留。void不计，季度外不计。退款仅本季度posted且引用同员工、本季度posted、严格更早月份的原销售才计；cancelled或季度外不计。全部给定有效退款具备正确引用，且本期累计退款不超过被引原销售，不需要猜配。排除行须保留原因；季度外/取消记录不参与本期退款容量。

scenario_inputs.json有scenario_id为1/2/3的Base/Growth/Guardrail三个情景，每个情景按月给8项参数。三情景均为管理测算，原始员工月薪、考勤与销售/退款不因选择情景而改动。参数允许真实0（尤其commission_cap=0就是封顶为0，不是不限额）。tier1_limit和tier2_limit为累计销售额边界且0<tier1_limit<tier2_limit，rate1/2/3为比率；salary_multiplier为月薪系数，full_allowance为满勤月补贴。

## 工资与阶梯

paid_fraction = paid_days / standard_days。base_pay = ROUND_HALF_UP(base_monthly_salary × salary_multiplier × paid_fraction, 2)，allowance = ROUND_HALF_UP(full_allowance × paid_fraction, 2)。两项分别到分，不把月薪再除12，不按自然日重推考勤。标准天数以给定考勤为准，允许半日/四分之一日和0；提成不按paid_fraction二次折减。

对非负销售额S与该情景的原月参数，边际分段函数：

F(S)=MIN(S,tier1_limit)×rate1 + MAX(MIN(S,tier2_limit)-tier1_limit,0)×rate2 + MAX(S-tier2_limit,0)×rate3。

不是整笔套最高档，也不是每张销售单单独取整再相加。commission_raw保留至小数6位（金额分×比率4位），earned_commission = MIN(ROUND_HALF_UP(F(gross_sales),2), commission_cap)。封顶发生在本月正向提成计算后，不能按封顶后的工资总额倒推。各月正向提成使用本月参数；阶梯边界本身没有额外跳档奖励。

## 跨月退款追溯

退款影响原销售月的整月提成，不是当前月销售额抵减，也不是退款×当前月某档比率。先按员工、原销售月份汇总，再在每个发薪月分别计算：

R_before是该原月销售截至本发薪月之前的有效累计退款，R_through是截至本发薪月结束的有效累计退款。两者均按original_sale_id定位，但同员工同原月销售共享阶梯和封顶，不逐单舍入。

C_before = MIN(ROUND_HALF_UP(F(MAX(gross_sales_original - R_before,0)),2), cap_original)。
C_after = MIN(ROUND_HALF_UP(F(MAX(gross_sales_original - R_through,0)),2), cap_original)。

F及cap_original均取同一测算情景的原销售月参数。current_clawback = C_before - C_after。只在发薪月晚于原销售月时计回溯；当月原销售额已在earned_commission计算，不能在当月再减一次。已在更早发薪月扣过的金额不重复扣。原月曾封顶时，小额退款可能仍处于封顶区，回扣可以真实为0；跨过封顶或阶梯后才产生差额。

每个员工每个发薪月：clawback = 对所有更早原月的current_clawback求和；net_commission = earned_commission - clawback；total_pay = base_pay + allowance + net_commission。净提成和测算工资允许负数，不能钳0、挪到别的员工或擅自制造真实发薪动作。不计算税费、社保、银行付款或未提供的余额结转。

## 情景与更新

构建可编辑参数和真实公式，复用同一套口径，三情景不能只换标签或粘贴答案。应能选择情景核对36条员工月度结果和72条员工×原月×截至月的回溯明细（原月≤截至月）；同月current_clawback为0。三情景对比按情景×月份展示全部9行，含六项月合计base_pay、allowance、earned_commission、clawback、net_commission、total_pay及各自较Base的差额。对比必须随相关参数改变而实际重算，不能用保存时静态快照冒充联动。

允许原生敏感性表或其它真实联动的等价设计，不强制作者Sheet/坐标/排序编码或公式数量。原始底稿与可编辑情景参数须可见可维护；可以单一活动情景模型配原生情景对照，也可以复用统一计算逻辑的合理等价实现。保存基线的活动情景为1。改变情景选择时只切换模型/展示，不改源数据；改变后期参数时，相关情景的本月结果和三情景对比应改变，其它情景/月份保留正确值。原月参数变动还必须传播到后期退款追溯。

validation.md说明参数入口、刷新方法、至少一次实际修改再恢复的验证（参数、前后值、受影响员工/月/情景和恢复结果），以及退款/封顶/舍入限制。不要虚构已经运行；独立评分还会在候选副本实际改参数和切换情景。只读取原三份输入，全部新文件写results，离线完成，不发消息、邮件或真实付款。
