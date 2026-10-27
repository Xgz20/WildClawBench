# 私有参考答案：2022年人体细胞图谱

本文件仅供执行结束后的裁判使用，不作为Agent公开输入。以指定两篇2022年Science论文主数据集的正文为准。参考只规定事实和口径，不规定回答格式。

## 唯一事实表

| 论文 | 供体数 | 独立组织样本数 | 质控后总数及对象 | 组织状态 |
|---|---:|---:|---|---|
| Tabula Sapiens，eabl4896 | 15 | 59 separate specimens | 483,152个活细胞 | 新鲜组织；取材后立即置冰上送达，分离活细胞 |
| GTEx单核图谱，eabl4290 | 16 | 25 tissue samples | 209,126个细胞核表达谱 | 存档、冻存组织；提取细胞核 |

GTEx乳腺为61.3%，皮肤为93.1%。两比例分别指该组织的细胞核表达谱中来自单个样本的比例，不是同一供体占整个图谱的比例。论文没有要求据此断言两个组织来自同一个人。

## 一手来源与定位

1. The Tabula Sapiens Consortium. *The Tabula Sapiens: A multiple-organ, single-cell transcriptomic atlas of humans*. Science 376(6594), eabl4896 (13 May 2022). DOI [10.1126/science.abl4896](https://doi.org/10.1126/science.abl4896)。[PMC作者存档正文](https://pmc.ncbi.nlm.nih.gov/articles/PMC9812260/)；[加州大学作者论文PDF](https://escholarship.org/content/qt0285358r/qt0285358r.pdf)。正文“Data collection and cell type representation”给出15名供体、59份独立标本及质控后的483,152个细胞，并说明使用活细胞而非分离的细胞核。Materials and methods summary中的取材说明为fresh whole organs或组织片，立即放冰上送至处理实验室。冰上运输不等于冻存组织。供体相关正文对应table S1，数据规模对应table S2；本题不要求重新汇总原始数据。
2. Eraslan et al. *Single-nucleus cross-tissue molecular reference maps toward understanding disease gene function*. Science 376(6594), eabl4290 (13 May 2022). DOI [10.1126/science.abl4290](https://doi.org/10.1126/science.abl4290)。[PMC作者存档正文](https://pmc.ncbi.nlm.nih.gov/articles/PMC9383269/)。Results首节“A multitissue, multi-individual single-nucleus reference atlas from archived, frozen human tissues”首段给出25份存档冻存样本和16名供体；随后描述质控与CellBender的段落给出乳腺61.3%、皮肤93.1%以及保留209,126个细胞核表达谱。正文指向table S1，但正文已直接报告所需比例。

## 别名、容差及裁判边界

- TS、Tabula Sapiens初版、2022主图谱均可；GTEx snRNA-seq图谱、Eraslan等2022图谱均可。需可唯一对应两篇指定论文。标题中文译法不作逐字匹配。
- 供体与独立样本数为整数，容差0。细胞/细胞核总数容差0；千分位、空格、中文万单位精确换算等价。仅写“约50万”“约21万”不满足精确总数。
- 两比例接受61.3%/93.1%、0.613/0.931或等价表述；小数转为百分数后容差0.05个百分点，不能只写多数或约六成/九成。允许小数表示时须清楚比例单位。
- 冻存不限定冻存温度；新鲜不要求额外说明运输温度。无须回答组织类型数、注释类别数、文库数或供体性别；不因缺少这些信息扣分。
- 同一表头或引言已经明确“QC后细胞/细胞核”时，不要求每个数字再重复。正文存档中的版本必须对应正式论文；不接受后续Tabula Sapiens扩充版或GTEx全项目总人数。
- 某一上游对象/版本错误使多字段一起受影响时登记一个error_id和一个核心组owner，标记受影响单元，核心统一上限不再额外逐字段固定罚分。正确来源被误读仅归事实项；不再在来源关联重复处罚。
- 可接受直接短答或表格；无需生物学解释、代码或文件。可核查到正文的DOI、出版方全文、PMC作者存档或机构存档均可，不强制固定URL或页码。搜索摘要可帮助定位，不能替代对正文的依据。

## 核提取方法与性能：正式正文直接可查

GTEx论文Results首节介绍四种方案：CST、NST、TST、EZ。CST使用0.49% CHAPS detergent、salts、Tris buffer；TST使用0.03% Tween 20 detergent、salts、Tris buffer。所问配方只要求去污剂和浓度，不额外要求盐浓度、提取步骤或商业试剂货号。NST含NP-40；EZ为商业核分离试剂盒，二者完整配方不在本题必答范围。

Results的“snRNA-seq protocols perform well across tissues and correspond to scRNA-seq”及Fig. 2A：EZ细胞类型多样性最低；TST跨组织平均最高。EZ较低多样性的线性混合效应量为−1.08，P=5×10⁻¹¹。多样性指标为Shannon entropy。最低/最高是本研究条件下的比较，不是所有组织和实验中永恒最佳的推荐。CST、NST、TST总体多样性可比；不能把TST平均最高说成所有组织必然最高。

这些新增事实在[正式论文作者存档正文](https://pmc.ncbi.nlm.nih.gov/articles/PMC9383269/)可直接定位：首节核提取配方段、协议比较段及Fig. 2A，不强制读取补充ZIP或指定唯一工具。2026-10-27通过PMC的等价入口[文章编号入口](https://pmc.ncbi.nlm.nih.gov/articles/9383269/)重新访问并核验。

配方百分比容差为0；效应量绝对容差0.005；P值接受5e−11、5×10⁻¹¹或精确等价表达，不接受仅写P<0.05。方案名大小写及连接符不影响识别，CHAPS、Tween 20不可互换。主数据集、单样本比例、配方与性能是独立事实，不能用一次只取得摘要的访问宣称全部已取得。
