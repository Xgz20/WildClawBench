# 私有参考答案：钙钛矿稳定性实验

本文件仅供执行结束后的裁判。题目所求“正文报告的测试时长和效率保持指标”与图注T95可同时列出，但不得互换。相对初始PCE的保持率不是绝对光电转换效率。

## 一手论文身份

A. Yang et al. *One-stone-for-two-birds strategy to attain beyond 25% perovskite solar cells*. Nature Communications 14, 839 (15 February 2023). DOI [10.1038/s41467-023-36229-1](https://doi.org/10.1038/s41467-023-36229-1)。[出版方全文](https://www.nature.com/articles/s41467-023-36229-1)，[PMC全文](https://pmc.ncbi.nlm.nih.gov/articles/PMC9932071/)。目标为3AP器件，环境存放是Fig.5c，MPP是Fig.5d。

B. Yao et al. *Oriented wide-bandgap perovskites for monolithic silicon-based tandems with over 1000 hours operational stability*. Nature Communications 16, 40 (**2 January 2025**). DOI [10.1038/s41467-024-55377-6](https://doi.org/10.1038/s41467-024-55377-6)。[出版方全文](https://www.nature.com/articles/s41467-024-55377-6)，[原版PDF](https://www.nature.com/articles/s41467-024-55377-6.pdf)，[PMC全文](https://pmc.ncbi.nlm.nih.gov/articles/PMC11696550/)。DOI含024不代表正式发表于2024年。目标为TOPO处理/(111)取向的钙钛矿/硅叠层：Fig.5b n-i-p，5c p-i-n，5d高温champion p-i-n。不得换成Fig.5a半透明单结或S24补充实验。

## 条件和正文结果唯一事实表

| 指定实验 | 封装 | 温度 | 湿度 | 光源 | 光强 | 正文测试时长 | 正文效率保持指标 |
|---|---|---|---|---|---|---|---|
| A：3AP环境存放，Fig.5c | 未封装 | 25°C | 空气，30–40% RH | 该存放实验未披露具体光源 | 该存放实验未披露 | 5000 h | PCE较初始下降8%，即保留92% |
| A：3AP MPP，Fig.5d | 封装 | 25°C | 空气，30–40% RH | 连续白光LED | 100 mW cm⁻² | 510 h | 较初始下降5%，即保留95% |
| B：目标n-i-p叠层，Fig.5b | 未封装 | 25°C | 氮气，<0.01% RH | LED；Methods细化为白光LED | 1 sun | 约1400 h | 仍高于初始PCE的95% |
| B：目标p-i-n叠层，Fig.5c | 未封装 | 25°C | 氮气，<0.01% RH | LED；Methods细化为白光LED | 1 sun | 约1400 h | 仍高于初始PCE的95% |
| B：目标(111)取向p-i-n叠层，Fig.5d | 未封装，见图内文字 | 80°C | 氮气；该高温实验未单列数值RH | LED；Methods细化为白光LED | 1 sun | 1000 h MPP | 仍高于初始PCE的90% |

## 原文定位与范围边界

A的Results小节“Stability enhancement of solar cells”分别叙述环境存放和MPP，给出上述时长和相对下降值；Fig.5c、5d图注确认封装、温湿度，5d图注明确白光LED及100 mW cm⁻²。Methods中光伏表征对MPP条件提供支持。正文先写的“dark air”明确描述Fig.5a裸薄膜的74天相稳定性实验，不是Fig.5c完整器件的光照披露。不得据此把5c写成确定暗存、0 mW cm⁻²或固定LED。Fig.5b的85°C、氮气、500h、保留83%是另一热实验，不是本题的环境存放或MPP。

B的Results“Device stability”，原版PDF第7页：Fig.5b/c共同句给未封装、25°C、氮气<0.01%RH、LED 1-sun；下一句给两类target tandem在约1400h后均保留>95%。Fig.5d对应正文给80°C、N₂、LED 1-sun、1000h后保留>90%。同页图5d图内说明写Unencapsulated；图内也说明AM1.5G，但并未给该高温实验独立数值RH。Methods“Stability test”中tandem MPP用氮气箱和one-Sun-equivalent white LED；前面的单结器件氙灯+405nm UV截止滤片不适用于本题叠层。该Methods以及后续正文中另有封装的开路/ISOS实验，不得替代Fig.5d。

B的Fig.5图注（PDF第7页）另报：b为T95>1200h，c为T95>1300h，d为T95≈1000h。正文的约1400h后>95%与图注寿命下界可以并列；d的正文>90%与图注T95≈1000h是不同指标表达，不能静默换算。接受准确注明图注的附加信息，不要求专门分析其一致性；仅给图注而遗漏正文要求的结果不能通过对应端点单元。

## 等价、容差与未披露字段

- 3AP-based、3AP、图中的with 3API目标器件可视为同一研究处理组；第二篇target/TOPO/(111)-oriented可等价，但须对应指定叠层结构和图号。不要求解释添加剂化学机理。
- 温度25/80°C接受±0.1°C显示舍入；RH区间端点接受原值，不可用室温/低湿替代数值；<0.01%不可写成等于0.01%或绝对无水。湿度未知可写“未单列数值，氮气环境”；无须据装置常识推定。
- 1 sun与100 mW cm⁻²、1000 W m⁻²按标准太阳辐照等价，光源身份须另列，不把1 sun当作氙灯。LED、白光LED可接受；A的5d白光限定可通过对照图注定位。对应实验没有披露的光源/光强写“未披露”或“正文、图注未给该存放实验”即可。仅写“无”不能证明未披露。
- 时间按正文数值。A需5000/510h；仅从摘要给“超过500h”不能替代正文510h。B室温“约1400h”不可精化为无条件精确寿命；“约1400小时后仍>95%”与“在约1400小时测试后损失<5%”等价。高温1000h后>90%与损失<10%等价。>、超过、高于必须保留，不接受默认为等号。A明确下降8%/5%与保留92%/95%等价，不能解释为下降8/5个百分点的绝对PCE。
- 宽泛“93–95%”不能替代指定正文保持率；不从图像目测结果代替作者正文报告。无需报告控制组、器件面积、认证PCE、寿命标准编号或论文发布日期；若主动用DOI年份认定发表年错误，只在确实造成来源版本错绑时记独立来源错误，不设置隐藏发布日期考点。
- 同一共同条件只评分一次；b/c共享行可覆盖两项端点。事实错误不同时作为来源错误处罚。明确已核查但未披露与“没能访问，未核实”不同：后者诚实但并未完成对应字段，且不自动触发关键错误。
