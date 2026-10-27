# 三年经营对标口径

本题为人民币合成练习。分析时点固定为2026-09-30，报告年度为2023、2024、2025，不使用披露年份代替报告期间。全部财报是本题构造的摘录，不连接真实公司或外部数据。

## R-source 单位和版本

金额统一转换为万元，保留真实0、负号和缺失：元乘0.0001，千元乘0.1，万元不变，百万元乘100，亿元乘10000。每份摘录的所有金额沿用其页首单位。

截至分析时点，restatements.csv中的两项后续更正优先于原始财报列。对同一公司、报告年度和字段只使用生效更正，不把多次披露相加。保留原始值、新值、差额、来源与更正ID。A的2024年收入更正同时影响2024本年收入及2025同比所用上年收入；A的2025摘录对照列仍为更正前值。B的2023年仅归母净利润变动，不能改成合并净利润也随之更正。

## R-metrics 三项核心指标

每家公司每年每项保留一条记录，共27条；比例以0至1的比率数值存储，可以用百分比格式显示。指标都由生效万元数据计算。

| metric_id | 名称 | 分子 | 分母 | 可计算条件 |
| --- | --- | --- | --- | --- |
| revenue_yoy | 收入同比 | 本年营业收入 | 上年生效营业收入 | 口径可比、上年收入已披露且大于0；value为分子除分母减1 |
| roe | 归母ROE | 归母净利润 | 期初与期末归母权益的简单平均 | 两项权益已披露、平均数大于0；不抄年报加权ROE |
| cash_to_profit | 经营现金与归母利润比 | 合并经营活动现金流净额 | 归母净利润 | 现金流已披露且归母净利润大于0；允许负或零现金流 |

2023年的上年收入来自该公司摘录CP01对照列。2024、2025年同比必须使用同一生效数据中上一报告年度的营业收入，形成跨年引用；不要各抄一份陈旧对照列。ROE分母必须由期初/期末权益计算。合并净利润、母公司单体现金流、期末现金余额和所有者权益总额均不是对应指标应取的字段。

不可计算的value、rank和change_pp用n/a或不适用，不能补0。status可用ok/not_comparable或正常/不可比，并列reason。原因应区分missing_base（上年收入未披露）、scope_change（收入同比范围变更）、zero_profit（现金比率分母为0）、missing_cash（经营现金流未披露）；这些原因不自动删除整家公司的其它有效指标。其他需要的非法/缺失检查应按对应口径明确处理，不把除零结果伪装为0。

## R-compare 名次与变动

逐报告年、逐metric_id对可计算的公司按value从高到低排名，使用竞赛名次，同值同名次、后续跳号；不可比记录不参加排序。每条记录的change_pp为本年value减上一年该公司同一指标的value，再乘100，单位是百分点；2023或任一期指标不可计算时为n/a。排名反映定义下的数值次序，不代表综合经营质量优劣。

## R-model 工作簿要求

comparison.xlsx须含可回查生效数据、27条指标、两项重述前后值与差额；表名、位置、顺序不限。生效数据按company_id和period_year识别，保留清楚标记的真实可编辑入口：revenue_wan、parent_profit_wan、cfo_wan、equity_open_wan、equity_close_wan、prior_revenue_wan和scope_comparable。prior_revenue_wan只驱动2023年的收入同比；后两年的上期分母链接同一入口表上一年revenue_wan。金额均为数值万元；缺失可留空或n/a。scope_comparable为0/1数值、布尔或普通标量公式，公式/合并入口的独立寻址限制以评分运行时为准；普通金额入口保留可编辑数值。

指标表以company_id,period_year,metric_id定位，至少包含numerator_wan,denominator_wan,value,rank,change_pp,status,reason，允许语义明确中文表头。分子、分母、比率、名次、百分点变化、状态和原因保留可重算公式，包括返回n/a的情况。换基准数后对应结果应更新；不要求自动重读源文件、重新选择重述版本或改写Word与CSV。不要用隐藏表或仅图片代替原生可见数据。

## R-evidence 交付与来源

sources.csv为UTF-8，每个公司每年每个语义源字段一行，共63行。七个field为revenue,parent_profit,cfo,equity_open,equity_close,prior_revenue,scope_comparable。至少包含company_id,period_year,field,source_file,locator,reported_value,unit,effective_value_wan,restatement_id,adjustment_source,adjustment_locator。source_file是statements中的相对路径，locator为材料可见ID；缺失字段也保留行和未披露原文，effective_value_wan留空。scope_comparable的unit写flag，不按金额换算。存在更正时关联实际CSV记录ID；prior_revenue按其对应历史年度查更正。只有文件存在不等于定位和数值正确。

memo.docx须原生可编辑，给出三家公司三年的27个指标值、相应年度名次和2025较2024的百分点变化，核对两项重述差异及四个不可比结果。可用有清楚company_id、年度和metric_id标签的表格；报告比例保留至少0.01个百分点，百分点变化保留至少0.01。结论说明排序、口径变化、缺失、零值、负现金流的实际含义，提出可继续复核的资料或问题，不虚构原因、审批、审计或工具执行。不能据三个自定比率直接断言投资价值、因果改善、偿债能力或未来回款；B的并表范围变化限制经营趋势解释。

全部源输入只读。三份交付写results，不访问网络、真实账户或接口，不执行真实业务。每份不超过5MiB。工作簿更新后核对三份交付的同一基线；公式探针仅在评分副本内运行，不改变原交付。
