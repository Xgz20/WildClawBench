# 裁判参考：上期所合约名义价值与套保保证金

仅供执行结束后的裁判使用。核验日期2026-10-27。数据均已与上海期货交易所原始行情、合约文本和指定日期结算参数核对。

## 固定事实与计算

口径：2025-02-10收盘价，元（人民币）/吨；合约均为2506，交易单位为吨/手；每手名义价值=收盘价×交易单位。按公开上下文，“当期一般套期保值最低保证金比例”指该日日终交易所“套保持仓”保证金率，不含期货公司加收，不是“一般持仓”字段。

| 合约 | 收盘价（元/吨） | 交易单位（吨/手） | 名义价值（元/手） |
|---|---:|---:|---:|
| 螺纹钢2506 / rb2506 | 3333 | 10 | 33330 |
| 铝2506 / al2506 | 20600 | 5 | 103000 |
| 铜2506 / cu2506 | 77690 | 5 | 388450 |
| 锡2506 / sn2506 | 258770 | 1 | 258770 |

最高为铜2506（cu2506），交易单位5吨/手；当日交易所套保持仓买、卖保证金率均为8%。锡的每吨收盘价最高，但每手名义价值不是最高。

## 原始行情

[上期所2025-02-10日行情原始数据](https://www.shfe.com.cn/data/tradedata/future/dailydata/kx20250210.dat)；[对应官方查询页面](https://www.shfe.com.cn/reports/tradedata/dailyandweeklydata/?query_date=20250210&query_options=1&query_params=kx)。

report_date=20250210；读取o_curinstrument，按PRODUCTID和DELIVERYMONTH=2506选择唯一记录。PRODUCTID分别rb_f、al_f、cu_f、sn_f；使用CLOSEPRICE。官方页面将该字段标为“收盘价”；SETTLEMENTPRICE是“结算价”，不是本题价格。原件SHA256：586cc389e402d08d2a1e653df717b3c40db1e22b1604264fd7b20a9586ddcf07。

## 交易单位

四份官方合约文本的pageList[0].ContractSize为交易单位，PriceQuotation均为元（人民币）/吨。合约文本发布日期均早于2025-02-10：

| 品种 | 官方合约原文 | 文本发布日期 | ContractSize |
|---|---|---|---|
| 螺纹钢 | [螺纹钢期货合约](https://www.shfe.com.cn/products/futures/metal/ferrousandpreciousmetal/rb_f/) | 2024-09-24 | 10吨/手 |
| 铝 | [铝期货合约](https://www.shfe.com.cn/products/futures/metal/nonferrousmetal/al_f/) | 2024-07-12 | 5吨/手 |
| 铜 | [铜期货合约](https://www.shfe.com.cn/products/futures/metal/nonferrousmetal/cu_f/) | 2023-03-29 | 5吨/手 |
| 锡 | [锡期货合约](https://www.shfe.com.cn/products/futures/metal/nonferrousmetal/sn_f/) | 2023-03-29 | 1吨/手 |

网页原文包含合约文本数据及其渲染模板，可以核对显示标签与字段。DeliveryUnit是交割单位，不能替代ContractSize。

## 指定日期套保保证金

[2025-02-10结算参数原始数据](https://www.shfe.com.cn/data/tradedata/future/dailydata/js20250210.dat)；[对应官方查询页面](https://www.shfe.com.cn/reports/tradedata/dailyandweeklydata/?query_date=20250210&query_options=1&query_params=js&query_product_code=cu_f)。

原件o_code=0000、report_date=20250210、update_date=20250210 15:28:26；o_cursor内INSTRUMENTID=cu2506唯一。原件SHA256：9425530f5edd02e2863c0d7677a0ef7f9edcd4a9b12a6ba14bc3e79abb3d897a。

| 原始字段 | 官方显示标签 | 原始比例 | 显示百分数 |
|---|---|---:|---:|
| HEDGLONGMARGINRATIO | 套保持仓买交易保证金率(%) | 0.08 | 8% |
| HEDGSHORTMARGINRATIO | 套保持仓卖交易保证金率(%) | 0.08 | 8% |
| SPECLONGMARGINRATIO | 一般持仓买交易保证金率(%) | 0.09 | 9% |
| SPECSHORTMARGINRATIO | 一般持仓卖交易保证金率(%) | 0.09 | 9% |

官方页面将这些原始比例乘100显示。8%回答目标正确；9%属于一般持仓，不能当作所问套保比例。静态合约页MinimumTradeMargin=合约价值的5%，是合约文本最低交易保证金字段，不是该日动态套保持仓保证金参数。引用静态页的交易单位正确，不代表同页5%可以替代题定8%。

## 可接受表达与排除项

合约代码大小写、铜2506/cu2506、5吨/手/每手5吨、8%/0.08等无歧义等价表达接受。保证金比例须准确，无百分点评价容差；不要求分别重复买卖两侧。四项输入可由共享表头、最终说明及已明确采用的公开证据绑定，不强制特定表格。

行情日期、合约、收盘价和交易单位按原始精度核对。名义价值可为准确元/手值，也可按万元/手保留至少两位小数合理四舍五入，换算后绝对误差不超过50元且比较顺序不变；单位换算必须清楚。不得因小数尾零、千位分隔或等价单位排版判错。

不要求计算保证金金额、收益率、杠杆倍数、交易成本或交割成本；这些不另设评分点。赢家交易单位属于contract_inputs中的铜单位单元，不在highest_contract重复计分。不能以单价排序代替每手名义价值排序，不能以期货公司加收比例、静态5%、一般持仓9%或其他日期参数替代当日套保持仓8%。

上游输入错误被正确乘算和排序沿用，只扣对应输入单元；下游登记inherited_error并列明偏差，不重复扣。错误输入或独立比较错误使赢家选错，但正确查得该候选赢家的当日套保持仓比例时，保证金差异属于继承，不扣hedging_margin、不触发margin_substitution，不因正确关联该赢家的套保原件再扣来源。只有该候选赢家的保证金比例、日期、合约或套保口径另有独立错误才扣保证金。赢家错误本身仍按其原业务owner评分。

正确来源被误读只扣核心业务；来源身份、对象、版本或定位另有独立错误才扣来源业务。同根因错误保留唯一error_id及业务owner。source_binding的能力分独立评价实际绑定行为，不因业务豁免得满分；例如把一般持仓9%误读为套保持仓，铜组来源能力单元失败，但同根因来源业务豁免。原文若出现可证实的新版本冲突，先复核参考版本，不把参考缺陷算成候选错误。
