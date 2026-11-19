# 裁判参考：两项水稻AWD试验

用途：仅供执行结束后的裁判使用，不是候选答案。核验日期2026-10-27。两篇正式原文及指定表格已逐项核对；答案范围固定为Prompt中的研究、年份、处理和施氮条件。要求识别研究并取得指定原文内容；不要求环境效益解释、统计显著性分析或文档产物。

## Lagomarsino等（2016）

*Alternate Wetting and Drying of Rice Reduced CH4 Emissions but Triggered N2O Peaks in a Clayey Soil of Central Italy*，Pedosphere 26(4):533–548，DOI [10.1016/S1002-0160(15)60063-7](https://doi.org/10.1016/S1002-0160(15)60063-7)。[作者机构正式论文PDF](https://linquist.ucdavis.edu/sites/g/files/dgvnsk6581/files/inline-files/Lagomarsino%20et%20al%202016.pdf)。地点Malalbergo，意大利。依据TABLE II（印刷页536，PDF第4页）；方法印刷页535说明复灌阈值相对土表。

| 年份 | AWD复灌水位相对土表 | 施氮量 | PF产量 | AWD产量 |
|---|---|---|---|---|
| 2012 | −15 cm，即土表以下15 cm | 120 kg N ha−1 | 10.35 Mg ha−1 | 6.93 Mg ha−1 |
| 2013 | −5 cm，即土表以下5 cm | 120 kg N ha−1 | 7.89 Mg ha−1 | 6.92 Mg ha−1 |

施氮量对PF与AWD相同。TABLE II的−号表示土表以下，不能只写15/5而不说明方向。摘要的2013减产百分比与TABLE II略有不同；Prompt只问绝对产量，不考减产百分比，不用该差异改变固定值。

## LaHue等（2016）

*Alternate wetting and drying in high yielding direct-seeded rice systems accomplishes multiple environmental and agronomic objectives*，Agriculture, Ecosystems & Environment 229:30–39，DOI [10.1016/j.agee.2016.05.020](https://doi.org/10.1016/j.agee.2016.05.020)。[作者机构正式论文PDF](https://linquist.ucdavis.edu/sites/g/files/dgvnsk6581/files/inline-files/LaHue-et-al.-2016-AEE.pdf)。地点Biggs，加州。以下均来自Table 2（印刷页34，PDF第5页），固定施氮180 kg N ha−1，逐年均值。

| 处理 | 2013产量（Mg ha−1） | 2014产量（Mg ha−1） | 2013生长季GWP（kg CO2-eq ha−1） | 2014生长季GWP（kg CO2-eq ha−1） |
|---|---:|---:|---:|---:|
| WS-C | 10.7 | 8.12 | 5518 | 6553 |
| WS-AWD | 10.1 | 9.24 | 2387 | 2334 |
| DS-AWD | 10.7 | 10.8 | 819 | 987 |

WS-C为水播、常规持续淹水；WS-AWD为水播、干湿交替；DS-AWD为条播、干湿交替。表内括号为标准误，不是所问均值。产量按14%含水率标准化，此细节帮助识别表格，不另设必须写出的评分点。

## 别名、单位、容差与排除项

TABLE II/Table II/表II/表2均可指Lagomarsino第二表；LaHue须绑定其Table 2。WS–C与WS-C、WS–AWD与WS-AWD、DS–AWD与DS-AWD等价；中文解释加无歧义缩写可接受。Mg ha−1、Mg/ha等价；kg N ha−1、kg N/ha等价；kg CO2-eq ha−1、kg CO₂-eq/ha等价。原单位必须保留，可额外给换算值；仅给吨/ha或kg/ha而没有原单位不满足Prompt。数值接受尾随0、千位分隔、科学计数法等精确等价表达；不允许自行减小有效位数。按表载值核对，机器转换仅容许1e−6绝对浮点误差，不把该阈值用来读取任意数字出现。

LaHue的GWP跨年Mean 6035/2361/903不是逐年值；GWP-Y按产量归一，不是每公顷生长季GWP；Table 2的生长季GWP不能由Table 3的全年GWP或休闲季排放替代；本题另问的2014年DS-AWD三项值须从Table 3读取。2012产量、其他施氮量，以及2014年DS-AWD以外的全年GWP不计作必答单元。Lagomarsino不要求补查气体排放、复灌次数、肥料类型或产量标准误；需要补充其GWP方法口径。

原文链接可用出版社、DOI或明确对应全文的作者机构存档；不能以实验室首页或综述替代。必须明确两篇各自表号，不强制页码格式。作者机构PDF本次web工具可读，但普通HTTP下载遇到403；候选工具遇到同类外部限制不算参数错误。评分端无法取得所引原文时标记证据不足，不把作者访问成功视作候选必然可访问。

## 新增的跨表与方法事实

LaHue Table 3（印刷页37、PDF第8页）2014年DS-AWD：休闲季CH₄=25.5 kg CH₄-C ha−1；休闲季N₂O=0.422 kg N₂O-N ha−1；全年GWP=2345 kg CO₂-eq ha−1。括号中的2.82、0.079、303为标准误，不是所问均值。不能把生长季18.4/0.320或全年44.0/0.743混入休闲季，也不能把CH₄-C和N₂O-N直接标成CH₄和N₂O同质量。

两篇均采用100年时间尺度，CH₄的GWP因子34、N₂O的因子298，均相对CO₂。Lagomarsino见Data analysis（印刷页537–538，PDF第5–6页）；LaHue见§2.7 Data analysis（印刷页33，PDF第4页）。因子按气体质量而非C/N元素质量定义；本题不要求从气体排放重算GWP。

识别线索固定为发表年、地点、试验年份/处理，指向上述两项正式研究；允许标题译名或唯一DOI标识，不要求作者拼写格式。只给出正确数字或DOI不能替代实际获取这些页的原文证据。2026-10-27重新访问两篇作者机构全文并核对新增表格和方法。
