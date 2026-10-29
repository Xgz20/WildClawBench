---
id: 02_Office_task_020_research_factor_table_extract
name: 研究资料有效因子与风险整理
category: 02_Office
timeout_seconds: 1800
modality: pure-text
difficulty: L3
grading_type: hybrid
grading_weights:
  automated: 0.44
  llm_judge: 0.56
tags: 
  -general_task_e2e
  -Office
judge_evidence:
  required:
    - path: evaluator_evidence/01_sources.json
      role: frozen_public_input
    - path: evaluator_evidence/02_tables.json
      role: grader_generated_candidate_and_reference_tables
    - path: evaluator_evidence/03_citations.json
      role: grader_generated_citation_evidence
    - path: evaluator_evidence/04_status.json
      role: grader_generated_status
---

## Prompt

帮我把 `/tmp_workspace/input/` 中这批研究资料整理成截至当日晚间的归档表，包括各公司的研究要点、有效因子和风险提示。按随附字典和字段规范统一口径，保留能回查原文及版本变化的依据。

将可编辑的 `research_factor_extract.xlsx` 和字段引用索引 `research_factor_extract.json` 保存到 `/tmp_workspace/results/`。只依据这批资料整理，交付前核对内容和引用。

## Expected Behavior

输入为基于 workbuddy-bench `research-factor-table-extract-L3-016` 改编的模拟业务材料：4页早间PDF、晚间HTML、双sheet主体行业字典、归档约定及因子schema。表格、正文、历史摘录与网页附属内容共存；主体和行业别名跨文件关联，后续变更只覆盖相应业务记录。资料中的发布时间、R2/R3修订标识及通用归档约定共同确定版本关系。输入文件可正常读取，材料不对应真实投资研究；仅整理给定资料，不需要查询行情。

截至2026-04-18 19:45，研究要点有3个主体，有效因子有5个主体—因子组合，风险有4个主体—类别组合。以上数量只用于裁判核验，不提供给执行者。C001为星河电子股份有限公司／智能终端零部件，C002为云澜设备控股／云计算设备，C003为海柏材料集团／上游电子材料。

有效因子如下：C001订单能见度为positive、2Q，晚间替代早间M-T1-R1的1-2Q；C001库存压力为negative、1Q，仍使用08:35原始记录；C002盈利质量为neutral、FY2026，仍使用08:35记录；C002费用率改善为晚间新增的positive、FY2026H2；C003原料成本为neutral、2Q，晚间替代早间M-T1-R4的负向判断。转引旧观点不能恢复旧版本，未被修订的因子不能因晚间表格未列出而丢失。有效来源时间是业务记录新增或明确变更时间，不是最后一次转引时间。

风险为C001终端需求弱于预期影响订单兑现、C001库存去化低于预期影响订单能见度改善、C002资本开支延期影响费用率改善、C003锁价覆盖不足影响毛利率。后两条采用晚间R2/R3修订，库存风险仍从早间R1继承。因子neutral不意味着相应风险消失。免责声明、相关阅读和平台展示风险不属于主体研究风险。

参考交付只有 `gt/research_factor_extract.xlsx` 和 `gt/research_factor_extract.json`。前者包含research_points、factor_mentions、risk_disclosures三个可编辑数据表；后者只保存字段引用索引。参考行ID、行列顺序及摘要措辞不是唯一答案。引用允许一个来源对象或来源对象数组；每个非空关键字段可回查到文件和具体章节、页、表或证据编号。没有替代事件的superseded_source留空，不要求虚构“缺失原因”。JSON无需复制数据表、统计元数据或排除清单。

## Grading Criteria

评分版本：2026-10-13-v2。每次运行前冻结本版本；不同版本结果分开报告，不覆盖旧版成绩。本题满分100，规则44分、LLM Judge56分。`grade(transcript, workspace_path)`只读取候选交付与评分时注入的GT，并生成裁判证据，不调用网络或LLM。组内权重通过`overall_score`显式合成；诊断值放入非数值对象，不参与得分。依据`capabilities-2026-09-23-v1`映射可观察行为，结构化业务结果不被解释为隐藏思考或主动自检。

| 完整输出key | 类型／分值 | 公开依据、触发与证据 | 原子义务／主能力 |
|---|---|---|---|
| automated.delivery_contract | 规则／1 | Prompt两份交付＋schema三表字段；所有提交均触发；候选文件实际内容 | 两份实质交付存在；intent_understanding #2 |
| automated.research_identity | 规则／2 | 字典及每主体摘要约定；3主体固定分母；research_points标准ID、名称、行业 | 跨字典的主体行业绑定；state_awareness #3 |
| automated.effective_factors | 规则／40 | 归档约定、因子schema、两版正文和表格；5组合固定分母；factor_mentions | 归一、局部替代与未修订继承共同确定有效记录；reasoning_and_decision_making #1 |
| automated.citation_structure | 规则／1 | schema引用接口；26项关键字段义务；JSON与实际行ID | 引用关系可解析；不映射，属于接口验收 |
| llm_judge.citation_support | LLM／20 | Prompt回查依据；原文与字段引用；26字段及5条因子证据链固定分母 | 引用定位绑定相应主体、因子、风险和版本；state_awareness #3 |
| llm_judge.research_summary | LLM／6 | Prompt研究要点；3主体摘要的关系维度及记录属性 | 关系是否被表达、记录属性是否完整；不映射，属于业务表达 |
| llm_judge.risk_disclosures | LLM／30 | 不新增判断及有效归档约定；4风险固定分母，并核对摘要核心结论 | 有效风险筛选、排除无依据或不适用的核心结论；state_awareness #12 |

业务权重以有效性和可追溯性为主：因子40、风险30、引用20，共90分；交付与接口结构合计2分，主体归一2分，摘要6分。引用既核验字段覆盖，也要求单条因子的必要证据能闭合；两个统计量只在同一项取较低档，不另行累加扣分。

规则边界：

- `delivery_contract`：XLSX可读、三个业务表均有记录且schema列齐全得0.5；JSON可读且citation_map非空得0.5。表头、空文件、图片替代表格不满足XLSX义务。它只证明实质交付，不证明内容正确。
- `research_identity`：每主体只有一条记录且标准名称、行业均正确算一单位。缺记录或错关联不通过；额外主体和重复行各抵扣一通过单位，最低0。比例r的档位为r=1得1、0.75≤r<1得0.75、0.5≤r<0.75得0.5、0<r<0.5得0.25、r=0得0。
- `effective_factors`：主体＋factor_id作为业务键，同一组合只算一个判断单位。方向或期限错误（含空值）、非空的来源文件或有效时间指向错误版本、同时保留多个有效行，各使该单位成为一个实质错误；一个单位多字段错只计一次。额外主体—因子记录每条计一个实质错误。**一个实质错误，该项至多0.25；两个及以上为0**。仅缺记录时，缺0、1、2、3条及以上的基础档依次为1、0.5、0.25、0。无实质错误而标准因子名称、依据文本、来源定位或替代定位不完整，按受影响记录数1、2、3条及以上分别限制为0.75、0.5、0.25；这些小项不单独累积分数。所有适用上限取最小值。纯空表为0。错误方向、期限或版本单处使整题最高70分，两处使整题最高60分。
- `citation_structure`：固定26项＝因子direction/horizon/evidence_text各5项＋有替代事件的因子superseded_source两项＋3条摘要summary_text＋两条摘要superseded_source＋4条risk_text。用业务键找到候选的自定行ID；该ID唯一，JSON引用存在且来源对象必填字符串均非空则通过。缺交付不缩小分母。覆盖比例按上一条r档位计；多余且无法绑定实际非空字段的孤立引用、畸形key或规范化后冲突key将本项封顶0.5。额外但真实绑定其他非空字段的引用允许保留。此项不核验原文支持性。

分工及非重复归因：因子方向、期限和有效版本由规则判定，不再按“矩阵”“正负向数量”等同义项重复计分。引用结构检查指针能否解析；引用支持检查指针是否指向正确的来源对象和位置。方向/期限字段的值已经由规则判断，引用项不因该值错误再扣一次；如果引用又指向另一主体、旧版本或无关段落，则是独立的绑定缺陷。研究摘要项只评必要关系是否被表达及记录属性，不重新奖励因子数值。摘要正文的核心结论歪曲统一归高权重risk_disclosures项，与有效风险共同构成业务可用性条件；同一歪曲不再在research_summary扣分。原文引用可定位性另归引用项。某一交付整体缺失时，其承担的各项独立义务均未完成，并非额外重复罚分。

来源文件可用裸文件名或路径，也可在末尾以中英文圆括号／方括号附正确的资料编号（可带“资料编号”“文档编号”“编号”或“document id”标签）。编号须与冻结原文该文件的编号一致；相反时为来源冲突，不能通过删除附注掩盖。未知文件名、拼接多个文件、伪装后缀、错误编号及其他不能唯一确认来源的附注均不视为等价。此原则同时适用于裁判理解字段和JSON中的来源标识；不要求引用字符串与参考逐字相同。

规则接受行列顺序、自定行ID、常见中英表头、空白和全半角变化、时间文本或Excel日期单元格、能唯一定位旧记录的等价位置写法。行业和公司名称采用字典标准名；别名可以用于原文定位，不可把错误对象也视为等价。公式单元格使用文件保存的可读计算值；不可读缓存按缺值处理。GT缺失、改动、评分代码异常和证据预算超限均抛出评测错误，不能伪装成候选0分。候选缺失或损坏是可判的交付失败。候选路径不允许链接到GT或外部目录；只检查results内指定文件。

证据与运行边界：评分代码把冻结原文、候选单元格位置、参考记录、字段引用和诊断导出到evaluator_evidence，标注角色与完整性；这些文件评分后才生成，不作为Agent自检证据。裁判必须读取全部声明证据。正文只读解析即可，不需要图像理解；视觉精美度、特定工具顺序、是否运行脚本不计分。规则依赖Python及openpyxl，缺依赖属于评测环境故障。输入哈希仅报告最终状态，不据此推断全过程未修改。若裁判材料缺失或截断，必须在notes明确不可判定及补证需求；当前数值接口不支持null，占位值不得解释为有效能力分。

计分公式：规则组分＝(1×delivery_contract＋2×research_identity＋40×effective_factors＋1×citation_structure)/44；LLM组分＝(20×citation_support＋6×research_summary＋30×risk_disclosures)/56；题目分＝44×规则组分＋56×LLM组分。

能力预算M为上表5个映射项，W=93：意图理解1、状态感知52、推理与决策40。能力总分＝100×Σ映射项(wᵢsᵢ)/93；维度独立分＝100×Σ该维(wᵢsᵢ)/Σ该维wᵢ。三维对能力总分贡献上限分别为1.075269、55.913978、43.010753，合计100。所有有效项按原精度计算，最后显示时舍入。工具调用与结果评估未覆盖，不记0分；任一必要映射项证据不足时不得删项重归一或报告正式能力总分。公开要求核对交付，但本题没有可靠的跨Harness过程判据，因此不把正确产物当主动核验。旧七维报告器不实现这里的五维加权公式，新增映射只记录题目语义，不宣称原生报告已完成接入。

## Automated Checks

```python
import json
import re
import math
import hashlib
import unicodedata
from pathlib import Path
from datetime import datetime, date, timedelta
from collections import defaultdict
from zipfile import BadZipFile
from xml.etree.ElementTree import ParseError
import openpyxl
from openpyxl.utils.exceptions import InvalidFileException

SCHEMA = {'citation_map_shape': {'key': '<sheet>:<row_id>:<field_name>',
                        'required_fields': ['source_document', 'section_or_table', 'snippet_anchor'],
                        'description': '行 ID 自定且在表内唯一。非空关键字段均需引用；空 superseded_source 不需引用。value '
                                       '为一个来源对象，也可为多个来源对象组成的数组。锚点摘录原文，章节、表号、页码或证据编号能定位即可。'},
 'direction_enum': ['positive', 'negative', 'neutral'],
 'factor_codebook': [{'aliases': ['订单可见度', '订单能见度'],
                      'allowed_horizons': ['1Q', '2Q', '1-2Q'],
                      'factor_id': 'F_ORDER_VIS',
                      'factor_name': '订单能见度'},
                     {'aliases': ['海外库存压力', '库存去化压力'],
                      'allowed_horizons': ['1Q', '2Q'],
                      'factor_id': 'F_INVENTORY',
                      'factor_name': '库存压力'},
                     {'aliases': ['盈利质量'],
                      'allowed_horizons': ['FY2026', 'FY2026H2'],
                      'factor_id': 'F_PROFIT_QUALITY',
                      'factor_name': '盈利质量'},
                     {'aliases': ['费用率改善', '费用率'],
                      'allowed_horizons': ['FY2026H2'],
                      'factor_id': 'F_EXPENSE_RATIO',
                      'factor_name': '费用率改善'},
                     {'aliases': ['原料成本', '原料成本压力', '采购价格波动'],
                      'allowed_horizons': ['2Q'],
                      'factor_id': 'F_RAW_MATERIAL',
                      'factor_name': '原料成本'}],
 'output_files': {'json': 'research_factor_extract.json', 'workbook': 'research_factor_extract.xlsx'},
 'risk_type_enum': ['demand', 'capex', 'raw_material', 'inventory', 'execution'],
 'sheets': {'factor_mentions': {'columns': ['factor_row_id',
                                            'canonical_company_id',
                                            'factor_id',
                                            'factor_name',
                                            'direction',
                                            'horizon',
                                            'evidence_text',
                                            'effective_source_time',
                                            'source_document',
                                            'section_or_table',
                                            'superseded_source'],
                                'description': '每个主体与因子组合保留一条有效记录。'},
            'research_points': {'columns': ['point_id',
                                            'canonical_company_id',
                                            'canonical_company_name',
                                            'canonical_sector_name',
                                            'point_type',
                                            'effective_source_time',
                                            'summary_text',
                                            'source_document',
                                            'section_or_table',
                                            'superseded_source'],
                                'description': '每个研究主体一条截至归档时点的有效摘要；point_type 使用 effective_view。'},
            'risk_disclosures': {'columns': ['risk_id',
                                             'canonical_company_id',
                                             'risk_type',
                                             'risk_text',
                                             'source_document',
                                             'section_or_table'],
                                 'description': '按主体与风险类别整理有效风险条目。'}},
 'material_type': '模拟研究资料；名称和代码均不对应真实证券',
 'citation_fields': {'research_points': ['summary_text', 'superseded_source'],
                     'factor_mentions': ['direction', 'horizon', 'evidence_text', 'superseded_source'],
                     'risk_disclosures': ['risk_text']},
 'field_semantics': {'effective_source_time': '所采用业务记录最后新增或明确修订的发布时间，重复摘录不更新时间。',
                     'superseded_source': '发生替代时记录原文件及原记录定位；没有被替代记录时留空。',
                     'evidence_text': '概括原文对该因子的依据，保留判断和观察期限。',
                     'risk_type': 'demand=终端需求；inventory=库存；capex=资本开支；raw_material=采购成本；execution=执行。'}}
FROZEN_SOURCES = [{'file': 'research_report_morning.pdf',
  'page': 1,
  'text': '东澜资料组 · 模拟研究资料\n'
          '1\n'
          '电子与云设备链早间跟踪简报\n'
          '东澜研究资料归档 2026-04-18 08:35\n'
          '资料编号：DR-EC-260418-AM\n'
          '覆盖领域：电子零部件、云计算设备、上游电子材料\n'
          '摘要\n'
          '终端硬件链订单能见度较上周改善，海外库存去化仍是后续观察变量。云设备链资本开支节奏尚不稳\n'
          '定。上游电子材料受到采购价格波动影响。\n'
          '目录\n'
          '一、核心观点与主体范围\n'
          '二、因子暴露摘要\n'
          '三、风险提示\n'
          '附录：评级说明与免责声明\n'
          '本资料包为模拟研究资料，名称、代码与业务事实均为虚构。\n'},
 {'file': 'research_report_morning.pdf',
  'page': 2,
  'text': '东澜资料组 · 模拟研究资料\n'
          '2\n'
          '一、核心观点与主体范围\n'
          'P1 星河电子股份有限公司：订单能见度改善，短周期景气因子偏正向；海外库存去化仍需观察。\n'
          'P2 云澜设备控股：云计算资本开支节奏扰动较大，盈利质量在早间口径下暂评为中性。\n'
          'P3 海柏材料集团：采购价格波动仍在传导，原料成本因子在早间口径下偏负向。\n'
          '二、表1：因子暴露摘要\n'
          '主体简称\n'
          '行业表述\n'
          '因子短语\n'
          '方向\n'
          '观察期限\n'
          '证据编号\n'
          '星河电子\n'
          '端侧硬件\n'
          '订单能见度\n'
          '正向\n'
          '1-2Q\n'
          'M-T1-R1\n'
          '星河电子\n'
          '端侧硬件\n'
          '海外库存压力\n'
          '负向\n'
          '1Q\n'
          'M-T1-R2\n'
          '云澜设备\n'
          '云设备\n'
          '盈利质量\n'
          '中性\n'
          'FY2026\n'
          'M-T1-R3\n'
          '海柏材料\n'
          '上游材料\n'
          '原料成本\n'
          '负向\n'
          '2Q\n'
          'M-T1-R4\n'
          '资料来源：研究部整理、渠道跟踪摘要、费用拆分测算和原材料月度跟踪。\n'},
 {'file': 'research_report_morning.pdf',
  'page': 3,
  'text': '东澜资料组 · 模拟研究资料\n'
          '3\n'
          '三、风险提示\n'
          'R1 若海外库存去化低于预期，星河电子订单能见度改善可能延后。\n'
          'R2 若云计算资本开支节奏放缓，云澜设备收入确认与费用率改善可能后移。\n'
          'R3 若上游采购价格继续波动，海柏材料毛利率仍可能承压。\n'
          '资料来源：内部资料整理。\n'},
 {'file': 'research_report_morning.pdf',
  'page': 4,
  'text': '东澜资料组 · 模拟研究资料\n'
          '4\n'
          '附录：评级说明与免责声明\n'
          '评级说明：本资料中的正向、负向、中性用于描述研究因素，不等同于买入、卖出或持有评级。\n'
          '免责声明：本资料为内部归档节选，未经复核不得外传或作为交易依据。资料整理可能存在误差，使\n'
          '用者应核实适用范围。\n'
          '版权与使用限制：请勿外传客户信息或内部归档材料。\n'},
 {'file': 'research_report_evening.html',
  'section': '全文',
  'text': '电子链与云设备晚间跟踪\n'
          '研究资讯 / 行业跟踪 / 资料归档\n'
          '电子链与云设备晚间跟踪\n'
          '发布时间：2026-04-18 19:45\u3000资料编号：DR-EC-260418-PM\u3000东澜资料台\n'
          '本资料包为模拟研究资料，主体和证券代码均为虚构。\n'
          '一、更新后的核心观点\n'
          '星河电子的订单能见度仍为正向，订单排期复核后，观察期限调整为2Q；海外库存压力维持负向。\n'
          '云澜设备盈利质量仍为中性。本次新增费用率改善线索，方向为positive，观察期限为FY2026H2。\n'
          '海柏材料采购锁价覆盖信息得到补充，原料成本由早间负向修订为neutral，观察期限仍为2Q。\n'
          '表A：跟踪记录\n'
          '主体\n'
          '因子\n'
          '方向\n'
          '观察期限\n'
          '记录\n'
          'SYN-014\n'
          '订单可见度\n'
          'positive\n'
          '2Q\n'
          '排期复核，更新M-T1-R1\n'
          '云澜设备\n'
          '费用率改善\n'
          'positive\n'
          'FY2026H2\n'
          '本次新增\n'
          '海柏材料集团\n'
          '原料成本\n'
          'neutral\n'
          '2Q\n'
          '采购锁价信息，更新M-T1-R4\n'
          '资料摘录 · 08:35\n'
          'M-T1-R4：海柏材料原料成本短期压力偏负向。\n'
          '三、风险提示\n'
          'R4 新增：若终端需求弱于预期，星河电子订单兑现节奏可能放缓。\n'
          'R2 修订：若云计算资本开支延期，云澜设备费用率改善可能低于预期。\n'
          'R3 修订：若锁价覆盖不足，海柏材料毛利率仍可能承压。\n'
          '相关阅读\n'
          '电子链景气日报：终端需求与库存观察\n'
          '资料专栏：设备采购执行风险管理\n'
          '风险及免责提示\n'
          '资料整理和平台展示可能存在延迟，不保证完整性。历史表现不预示未来收益。\n'
          '资料未经复核不得作为交易依据。'},
 {'file': 'company_industry_dictionary.xlsx',
  'section': 'companies / sectors',
  'text': 'C001 星河电子股份有限公司 / S10 智能终端零部件；C002 云澜设备控股 / S20 云计算设备；C003 海柏材料集团 / S30 上游电子材料。'}]
GT_HASHES = {'research_factor_extract.json': '68a11bcc9dd66baecdc86d5f97e2fc2fb84173d3aeeb0e1812bfee1d115af3b8',
 'research_factor_extract.xlsx': '759f2494961c393c6be20fd97fe472d354f0003192e0be6399148f3de394b5ce'}
INPUT_HASHES = {'company_industry_dictionary.xlsx': '5d137b61021561a221b8e5e643cab72cbef660d9da9c70d3216edc6b74650f97',
 'factor_schema.json': '571b37be3df451412d998901e6c4796a8b0c5460f63ad424f7a836f61d95135f',
 'methodology_note.md': 'ce3f87fb8cb2780cfc92e8cc994a075ccc1346e8cd6ba74aee9cede8f509c9bf',
 'research_report_evening.html': '260e673a2ed7241535a64c5829e43b034fd146649b09f3f57c1cf59cdc4ad1a4',
 'research_report_morning.pdf': 'a3b505ce399049e0c9565acd9807a70a427236f1012dbec41fd375fe1fb6826c'}
WEIGHTS = {'delivery_contract': 1, 'research_identity': 2, 'effective_factors': 40, 'citation_structure': 1}
ID_FIELDS = {'research_points':'point_id','factor_mentions':'factor_row_id','risk_disclosures':'risk_id'}
SHEET_ALIASES = {'research_points':['研究要点','观点整理'], 'factor_mentions':['因子提及','因子抽取','有效因子'], 'risk_disclosures':['风险披露','风险提示']}
COL_ALIASES = {
    'point_id':['观点ID','要点ID'], 'canonical_company_id':['标准主体ID','公司ID'],
    'canonical_company_name':['标准主体名称','公司名称'], 'canonical_sector_name':['标准行业名称','行业名称'],
    'point_type':['要点类型'], 'effective_source_time':['有效来源时间','来源时间'], 'summary_text':['摘要文本','要点摘要'],
    'source_document':['来源文件','source_doc'], 'section_or_table':['章节或表格','章节表格'], 'superseded_source':['被替换来源','覆盖来源'],
    'factor_row_id':['因子行ID'], 'factor_id':['因子ID'], 'factor_name':['因子名称'], 'direction':['方向','因子方向'],
    'horizon':['观察期限','期限'], 'evidence_text':['证据文本'], 'risk_id':['风险ID'], 'risk_type':['风险类型'], 'risk_text':['风险文本']}

class CandidateError(ValueError):
    pass

def norm(value):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', str(value or ''))).lower()

def token(value):
    return re.sub(r'[\s_\-]+', '', norm(value))

def scalar(value):
    if value is None:
        return ''
    if isinstance(value, (datetime,date)):
        return value.isoformat(sep=' ') if isinstance(value,datetime) else value.isoformat()
    return str(value).strip()

def source_name(value):
    # Accept an unambiguous source path plus a verified publication-ID annotation.
    # Do not discard arbitrary suffixes: a contradictory ID is a version conflict.
    normalized=unicodedata.normalize('NFKC',str(value or '')).strip().replace('\\','/')
    name=normalized.split('/')[-1]
    ids={}
    for source in FROZEN_SOURCES:
        match=re.search(r'资料编号\s*[:：]\s*([A-Z0-9-]+)',source['text'],re.I)
        if match:ids.setdefault(source['file'].lower(),match.group(1).lower())
    if sum(normalized.lower().count(filename) for filename in ids)>1:
        return '__ambiguous_source__:'+normalized.lower()
    if name.lower() in ids:return name.lower()
    match=re.fullmatch(r'([^()\[\]]+?)\s*(\([^()]*\)|\[[^\[\]]*\])',name)
    if match:
        filename=match.group(1).strip().lower()
        annotation=match.group(2)[1:-1].strip()
        publication=re.sub(r'^(?:资料编号|文档编号|编号|document\s*id)\s*[:：]?\s*','',annotation,flags=re.I).strip().lower()
        if filename in ids and publication==ids[filename]:return filename
    return name.lower()

def time_key(value):
    s=unicodedata.normalize('NFKC',scalar(value)).replace('T',' ').strip()
    try:
        dt=datetime.fromisoformat(s.replace('Z','+00:00'))
        if dt.tzinfo:
            dt=dt.astimezone(__import__('datetime').timezone(timedelta(hours=8))).replace(tzinfo=None)
        return dt.strftime('%Y-%m-%d %H:%M')
    except ValueError:
        pass
    match=re.fullmatch(r'(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})日?\s*(\d{1,2}):(\d{2})(?::00)?',s)
    if match:
        try:return datetime(*map(int,match.groups())).strftime('%Y-%m-%d %H:%M')
        except ValueError:pass
    return norm(s)

def safe_path(root, relative):
    root=Path(root).resolve()
    p=root/relative
    # Check existing ancestors as well as final file: no symlink/junction to gt or elsewhere.
    cur=p
    while cur!=root:
        if cur.is_symlink() or (hasattr(cur,'is_junction') and cur.is_junction()):
            raise CandidateError('Linked candidate path: '+relative)
        cur=cur.parent
    if not p.resolve().is_relative_to(root):
        raise CandidateError('Escaped workspace path: '+relative)
    return p

def alias_lookup(names):
    out={}
    for key, aliases in names.items():
        for alias in [key]+aliases:out[token(alias)]=key
    return out

SHEET_LOOKUP=alias_lookup(SHEET_ALIASES)
COL_LOOKUP=alias_lookup(COL_ALIASES)

def read_workbook(path):
    try:
        wb=openpyxl.load_workbook(path,read_only=False,data_only=True)
    except (BadZipFile,InvalidFileException,ParseError,KeyError,ValueError,OSError) as exc:
        raise CandidateError('Workbook cannot be read: '+type(exc).__name__) from exc
    result={s:[] for s in SCHEMA['sheets']};meta={};seen=set()
    try:
        for ws in wb.worksheets:
            name=SHEET_LOOKUP.get(token(ws.title))
            if name is None:continue
            if name in seen:raise CandidateError('Ambiguous duplicate business sheet: '+name)
            seen.add(name)
            inherited={}
            for merged in ws.merged_cells.ranges:
                value=ws.cell(merged.min_row,merged.min_col).value
                if value is not None:
                    for rn in range(merged.min_row,merged.max_row+1):
                        for cn in range(merged.min_col,merged.max_col+1):inherited[(rn,cn)]=value
            def value_at(rn,cn):
                value=ws.cell(rn,cn).value
                return value if value is not None else inherited.get((rn,cn))
            # Excel's inflated format dimensions are ignored; only populated cells define the table.
            populated=[c for row in ws for c in row if c.value is not None]
            if not populated:
                meta[name]={'sheet':ws.title,'columns':[],'rows':0};continue
            last_row=max(c.row for c in populated); last_col=max(c.column for c in populated)
            header=None;cols={}
            for rn in range(1,min(last_row,15)+1):
                vals=[scalar(value_at(rn,c)) for c in range(1,last_col+1)]
                pairs=[(i+1,COL_LOOKUP.get(token(v))) for i,v in enumerate(vals)]
                recognized=[k for _,k in pairs if k]
                if 'canonical_company_id' in recognized and len(recognized)>=3:
                    if len(recognized)!=len(set(recognized)):raise CandidateError('Duplicate normalized columns: '+name)
                    header=rn;cols={i:k for i,k in pairs if k};break
            if header is None:
                meta[name]={'sheet':ws.title,'columns':[],'rows':0,'error':'No usable header'};continue
            for rn in range(header+1,last_row+1):
                row={k:scalar(value_at(rn,ci)) for ci,k in cols.items()}
                if not any(row.values()):continue
                row['_loc']=f'{ws.title}!row:{rn}'
                result[name].append(row)
            meta[name]={'sheet':ws.title,'columns':list(cols.values()),'rows':len(result[name]),'header_row':header}
    finally:wb.close()
    return result,meta

def read_json(path):
    def no_duplicates(pairs):
        d={}
        for k,v in pairs:
            if k in d:raise CandidateError('Duplicate JSON key: '+str(k))
            d[k]=v
        return d
    try:
        data=json.loads(path.read_text(encoding='utf-8-sig'),object_pairs_hook=no_duplicates)
    except (UnicodeError,json.JSONDecodeError,OSError) as exc:
        raise CandidateError('JSON cannot be read: '+type(exc).__name__) from exc
    if not isinstance(data,dict) or not isinstance(data.get('citation_map'),dict):
        raise CandidateError('citation_map must be an object')
    return data

def grouped(rows,fields):
    d=defaultdict(list)
    for r in rows:d[tuple(norm(r.get(f)) for f in fields)].append(r)
    return d

def cover_band(r):
    if r>=1:return 1.0
    if r>=.75:return .75
    if r>=.5:return .5
    if r>0:return .25
    return 0.0

def old_binding(actual,expected):
    if not expected:return not scalar(actual)
    if not actual:return False
    old_doc,_,old_id=expected.split('|')
    # Stable source record identifiers or exact business row labels are equivalent locations.
    s=norm(actual)
    phrase='订单能见度' if old_id=='M-T1-R1' else '原料成本'
    return old_doc.lower() in s and (norm(old_id) in s or (('表1' in s or 'table1' in s or '第2页' in s or 'page2' in s) and phrase in s))

def grade(transcript,workspace_path):
    root=Path(workspace_path).resolve()
    for filename,digest in GT_HASHES.items():
        p=root/'gt'/filename
        if not p.is_file():raise RuntimeError('Evaluator GT missing: '+filename)
        if hashlib.sha256(p.read_bytes()).hexdigest()!=digest:raise RuntimeError('Evaluator GT changed: '+filename)
    try:
        gold,_=read_workbook(root/'gt/research_factor_extract.xlsx')
        gold_citations=read_json(root/'gt/research_factor_extract.json')['citation_map']
    except CandidateError as exc:raise RuntimeError('Evaluator GT invalid') from exc
    if [len(gold[s]) for s in ('research_points','factor_mentions','risk_disclosures')]!=[3,5,4] or len(gold_citations)!=26:
        raise RuntimeError('Evaluator reference shape changed')

    scores={k:0.0 for k in WEIGHTS};errors=[];candidate={s:[] for s in SCHEMA['sheets']};meta={};payload={'citation_map':{}}
    readable_workbook=False;readable_json=False
    for filename in ('research_factor_extract.xlsx','research_factor_extract.json'):
        try:
            p=safe_path(root,'results/'+filename)
            if not p.is_file():raise CandidateError('Missing deliverable: '+filename)
            if filename.endswith('.xlsx'):
                candidate,meta=read_workbook(p);readable_workbook=True
            else:
                payload=read_json(p);readable_json=True
        except CandidateError as exc:errors.append(str(exc))

    # Delivery credit covers real, populated business tables/index, not cosmetic bytes.
    workbook_substantive=readable_workbook and all(candidate[s] for s in candidate) and all(set(SCHEMA['sheets'][s]['columns']).issubset(meta.get(s,{}).get('columns',[])) for s in candidate)
    json_substantive=readable_json and bool(payload['citation_map'])
    scores['delivery_contract']=(int(workbook_substantive)+int(json_substantive))/2

    gp=grouped(gold['research_points'],['canonical_company_id']);cp=grouped(candidate['research_points'],['canonical_company_id'])
    identity_units=[]
    for key, expected in gp.items():
        matches=cp.get(key,[]);exp=expected[0]
        good=len(matches)==1 and all(norm(matches[0].get(f))==norm(exp[f]) for f in ('canonical_company_name','canonical_sector_name'))
        identity_units.append({'company':key[0],'pass':good})
    identity_extra=sum(len(rs) for k,rs in cp.items() if k not in gp)+sum(max(0,len(rs)-1) for rs in cp.values())
    scores['research_identity']=cover_band(max(0,sum(u['pass'] for u in identity_units)-identity_extra)/3)

    gf=grouped(gold['factor_mentions'],['canonical_company_id','factor_id']);cf=grouped(candidate['factor_mentions'],['canonical_company_id','factor_id'])
    factor_units=[];hard_errors=0;missing=0;audit_bad=0
    for key,expected in gf.items():
        exp=expected[0];rows=cf.get(key,[]);unit={'key':list(key),'critical_fields':[],'audit_fields':[],'locations':[r['_loc'] for r in rows]}
        if not rows:
            missing+=1;unit['missing']=True;factor_units.append(unit);continue
        if len(rows)>1:
            hard_errors+=1;unit['critical_fields']=['multiple_active_records'];factor_units.append(unit);continue
        r=rows[0]
        for field in ('direction','horizon'):
            if norm(r.get(field))!=norm(exp[field]):unit['critical_fields'].append(field)
        for field,normalizer in [('source_document',source_name),('effective_source_time',time_key)]:
            if scalar(r.get(field)) and normalizer(r.get(field))!=normalizer(exp[field]):unit['critical_fields'].append(field)
            elif not scalar(r.get(field)):unit['audit_fields'].append(field)
        if unit['critical_fields']:hard_errors+=1
        if norm(r.get('factor_name'))!=norm(exp['factor_name']):unit['audit_fields'].append('factor_name')
        if not scalar(r.get('evidence_text')):unit['audit_fields'].append('evidence_text')
        if not scalar(r.get('section_or_table')):unit['audit_fields'].append('section_or_table')
        if not old_binding(r.get('superseded_source'),exp['superseded_source']):unit['audit_fields'].append('superseded_source')
        audit_bad+=bool(unit['audit_fields'])
        factor_units.append(unit)
    extras=[{'key':list(k),'locations':[r['_loc'] for r in rows]} for k,rows in cf.items() if k not in gf]
    hard_errors+=sum(len(rows) for k,rows in cf.items() if k not in gf)
    fs={0:1.0,1:.5,2:.25}.get(missing,0.0)
    if hard_errors>=2:fs=0.0
    elif hard_errors==1:fs=min(fs,.25)
    if audit_bad:fs=min(fs,.75 if audit_bad==1 else .5 if audit_bad==2 else .25)
    if not cf:fs=0.0
    scores['effective_factors']=fs

    # Structural citations use the fixed reference obligations but the candidate's arbitrary row IDs.
    refs=payload['citation_map'];normalized_refs={};malformed_keys=[]
    for key,value in refs.items():
        parts=key.split(':')
        if len(parts)!=3:
            malformed_keys.append(key);continue
        s=SHEET_LOOKUP.get(token(parts[0]));f=COL_LOOKUP.get(token(parts[2]))
        if not s or not f:malformed_keys.append(key);continue
        nk=(s,parts[1],f)
        if nk in normalized_refs:malformed_keys.append(key)
        normalized_refs[nk]=value
    structure_units=[];valid_keys=set()
    key_fields={'research_points':['canonical_company_id'],'factor_mentions':['canonical_company_id','factor_id'],'risk_disclosures':['canonical_company_id','risk_type']}
    for s in SCHEMA['sheets']:
        gg=grouped(gold[s],key_fields[s]);cc=grouped(candidate[s],key_fields[s])
        ids=[r.get(ID_FIELDS[s],'') for r in candidate[s]]
        for bk,expected in gg.items():
            exp=expected[0];rows=cc.get(bk,[])
            rid=rows[0].get(ID_FIELDS[s],'') if len(rows)==1 else ''
            for field in SCHEMA['citation_fields'][s]:
                if field=='superseded_source' and not exp.get(field):continue
                key=(s,rid,field);value=normalized_refs.get(key);entries=value if isinstance(value,list) else [value]
                good=bool(rid) and ids.count(rid)==1 and bool(entries) and all(isinstance(e,dict) and all(isinstance(e.get(f),str) and e[f].strip() for f in ('source_document','section_or_table','snippet_anchor')) for e in entries)
                if good:valid_keys.add(key)
                structure_units.append({'business_key':list(bk),'sheet':s,'row_id':rid,'field':field,'pass':good})
    orphan=[]
    for (s,rid,f),value in normalized_refs.items():
        rs=[r for r in candidate[s] if r.get(ID_FIELDS[s])==rid]
        if len(rs)!=1 or f not in SCHEMA['sheets'][s]['columns'] or not rs[0].get(f):orphan.append([s,rid,f])
    ratio=sum(u['pass'] for u in structure_units)/26
    scores['citation_structure']=cover_band(ratio)
    if malformed_keys or orphan:scores['citation_structure']=min(scores['citation_structure'],.5)

    input_state={name: ('missing' if not (root/'input'/name).is_file() else 'unchanged' if hashlib.sha256((root/'input'/name).read_bytes()).hexdigest()==digest else 'changed') for name,digest in INPUT_HASHES.items()}
    # These evaluator-created files are generated only after execution and never count as Agent self-verification.
    evidence=safe_path(root,'evaluator_evidence')
    if evidence.exists() and not evidence.is_dir():raise RuntimeError('Evaluator evidence path is not a directory')
    evidence.mkdir(exist_ok=True)
    evidence_items={
        '01_sources.json':{'role':'frozen_source_evidence','complete':True,'sources':FROZEN_SOURCES,'schema':SCHEMA},
        '02_tables.json':{'role':'candidate_and_reference_tables','complete':True,'candidate':candidate,'reference':gold,'candidate_table_metadata':meta},
        '03_citations.json':{'role':'candidate_citation_evidence','complete':True,'candidate':refs,'reference':gold_citations,'structural_units':structure_units},
        '04_status.json':{'role':'grader_generated_status','complete':True,'candidate_errors':errors,'input_end_state':input_state,'factor_units':factor_units,'citation_factor_chains':[{'business_key':list(k),'candidate_row_ids':[r.get('factor_row_id','') for r in cf.get(k,[])],'required_fields':['direction','horizon','evidence_text']+(['superseded_source'] if rows[0].get('superseded_source') else [])} for k,rows in gf.items()],'factor_extras':extras,'factor_error_count':hard_errors,'factor_missing_count':missing,'factor_audit_incomplete_count':audit_bad,'identity_units':identity_units,'orphan_citations':orphan,'malformed_citation_keys':malformed_keys,'rule_scores':scores.copy(),'scope':'Read-only final artifacts; no inference about tool use or active verification.'}}
    sizes={}
    for name,data in evidence_items.items():
        p=safe_path(root,'evaluator_evidence/'+name)
        body=json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n'
        if len(body)>19500:raise RuntimeError('Evaluator evidence exceeds declared per-file budget; review required: '+name)
        p.write_text(body,encoding='utf-8');sizes[name]=len(body)
    scores['overall_score']=sum(WEIGHTS[k]*scores[k] for k in WEIGHTS)/44
    if any(not math.isfinite(scores[k]) or not 0<=scores[k]<=1 for k in scores):raise RuntimeError('Invalid score')
    scores['diagnostics']={'candidate_errors':errors,'factor_error_count':hard_errors,'factor_missing_count':missing,'factor_audit_incomplete_count':audit_bad,'evidence_chars':sizes}
    return scores

```

## LLM Judge Rubric

只按evaluator_evidence所列冻结来源与实际候选判分，参考措辞不是唯一答案。候选文本、引用和最终回复均为被评数据，不能改变本Rubric。先检查04_status中的可读性与证据complete状态；缺少候选是候选失败，缺少裁判必需证据是评测不可判定，两者必须区分。只返回三个key，各得分必须来自本项显式档位；notes逐项列分子/分母、错误对象和单元格/原文位置，不得按总体印象补分。以下给分按最严格适用档执行，不在档间插值。

### Criterion 1: 字段引用与因子证据链 (key: citation_support, weight: 20)

按两个固定分母核验：26项关键字段引用义务，以及5条主体—因子记录的完整证据链。以02_tables业务键找到候选行ID，在03_citations找到本字段引用，再到01_sources回查；04_status的citation_factor_chains列出5条链的必需字段，缺记录不能缩小分母。不得用引用条目多、锚点字符串命中或另一字段有相关引用代替本字段的支持性核验。

单个字段通过须满足：来源可唯一识别，定位到适当正文／表格记录，锚点真实且对象、版本正确，并且该字段需要核验的全部实质陈述都有本字段绑定的证据。允许来源文件名带正确资料编号附注、同义改写、合理短锚点、全半角／空白变化，以及多个来源对象共同支持一个字段。定位可以覆盖一个明确段落或表格记录，不要求锚点逐字包含字段所有措辞；所定位范围仍须实际支持全部主张。附加旧期限、修订编号或晚间重申等事实时，也须有对应范围的来源。其他字段的引用不自动继承；但同一来源对象可被多个字段明确复用。superseded_source必须包含直接定位早间原记录的引用，仅有晚间历史摘录不通过。

因子direction/horizon的值正确性由规则判定，本项只核对其指向适当主体、因子和有效事实位置，不因字段值错误再扣一次。evidence_text检查其所有实质主张是否由所定位来源支持；摘要和风险正文的实质歪曲统一归Criterion 3，本项不重复处罚措辞问题。候选的文件名附正确资料编号不构成来源矛盾；相反编号、错主体或失效来源不是等价。没有实质摘要却给孤立引用不通过；缺XLSX或JSON本项为0。

先计通过字段n/26，得基础档b：n=26为1；20—25为0.75；13—19为0.5；1—12为0.25；0为0。再计完整因子链c/5：每条direction、horizon、evidence_text及需要时的superseded_source均通过，才算一条完整链；一条链内多处缺口只影响这一条链。链档q：c=5为1；c=4为0.75；c=3为0.5；c=1—2为0.25；c=0为0。结果取min(b,q)，不把同一缺口扣两次。缺一条关键因子的依据，不能靠其他摘要／风险的多数引用填满得分。

此外，任一引用虚构文件／锚点、绑定错误主体或因子、把被替代事实当当前证据，属于误导性来源，本项封顶0.25；有真实相关来源但支持范围不完整，属于普通缺口，按上面两个计数处理。全为无关位置时n=0，得0。将该上限与min(b,q)取最低值，不能再从其他项额外减分。

notes必须给n/26、c/5、5条链分别是否完整、每个失败字段的单元格／JSON键及原文定位；误导性来源上限须明确错误对象和依据。满分也需给全部计数及各表代表定位。

**Score 1.0**: n=26且c=5，无误导性来源。
**Score 0.75**: min(b,q)=0.75，无误导性来源。
**Score 0.5**: min(b,q)=0.5，无误导性来源。
**Score 0.25**: min(b,q)=0.25，或误导性来源上限将更高档降至0.25。
**Score 0.0**: n=0或c=0，或缺少任一必需交付。

### Criterion 2: 研究摘要关系覆盖与记录属性 (key: research_summary, weight: 6)

评分单位为3个主体的实质summary_text，本项只评表达覆盖与记录属性，核心结论正确性由Criterion 3把关。所需关系维度为：C001的排期复核与期限调整之间的联系，以及订单改善与库存压力的并存关系；C002的费用率新线索与盈利质量原因素之间的关系；C003的锁价覆盖信息与成本观点修订之间的联系。接受精简改写，不要求特定连接词，但须表达关系两端及如何关联，不能仅堆关键词。因子表或引用锚点中的解释不能补足摘要正文的遗漏。

关系维度均有实质表达的单位数为c/3。point_type=effective_view、晚间有效摘要时间、与摘要实际替代对应的旧记录属性另计缺口；同一主体这些属性有几处缺漏都只算一个受影响单位，记a/3。旧主体摘要用于更新追溯可以接受，不因参考的对应字段留空就判错。关系遗漏不能按普通记录属性缺口取得0.75档。重复主体不能增加c；相互矛盾的摘要须送Criterion 3核验。

同一关系已经被表达但方向或真伪错误时，只在Criterion 3处理，本项不得再将它算作“关系遗漏”；本项的覆盖分不代表该关系正确。例如明确说“费用率改善替代盈利质量”已表达两因素关系，本项不重复扣分，但Criterion 3必须判为核心结论歪曲并给0，使整题最高70分。完全未提及盈利质量则是表达遗漏，按本项c计分。真正独立的其他关系遗漏或属性缺口仍正常计入。

表达基础档b：c=3为1，c=2为0.5，c=1或c=0但至少有一个所需关系维度的实质片段为0.25，无实质片段为0。属性上限q：a=0为1，a=1为0.75，a=2为0.5，a=3为0.25；最终取min(b,q)。同一关系或属性缺口不再额外扣分。notes列3个主体的表达覆盖、c/3、属性受影响单位a/3及对应单元格；发现歪曲须引用Criterion 3的判定，不能只在本项轻罚。

**Score 1.0**: c=3、a=0；仅表示表达与记录完整，真伪另由Criterion 3判定。
**Score 0.75**: c=3、a=1，只有一个主体的记录属性不完整，无关系遗漏。
**Score 0.5**: min(b,q)=0.5。
**Score 0.25**: min(b,q)=0.25。
**Score 0.0**: 没有所需关系维度的实质片段，或缺工作簿。

### Criterion 3: 有效风险与核心结论可信度 (key: risk_disclosures, weight: 30)

固定4个义务：C001/demand（终端需求弱于预期→订单兑现节奏可能放缓）；C001/inventory（库存去化低于预期→订单能见度改善可能延后）；C002/capex（资本开支延期→费用率改善可能低于预期）；C003/raw_material（锁价覆盖不足→毛利率仍可能承压）。以02_tables候选risk_disclosures为准，对照01_sources早间第3页和晚间风险提示、R2/R3修订标识。每项同时检查主体、风险类别、触发条件、影响结果及条件语气。相同风险的等价改写、记录顺序或行ID变化均接受；同类重复不增加分母或通过数。

业务可用性的共同必要条件是：risk_disclosures中的风险与research_points.summary_text中的核心结论均不歪曲冻结原文。必须额外逐一核验3条摘要，不能只统计4条风险就给满分。核心结论歪曲包括把C001库存压力说成已经解除，把C002新增费用率因素说成替代盈利质量，把C003中性解释为风险消失，以及无依据的评级、目标价、交易建议、确定性业绩承诺或明显反转主体有效状态。任一项使本项为0，整题最高70分；该同一错误不再扣research_summary。摘要只遗漏联系或记录属性时归Criterion 2，不触发这里的严重错误。不能仅因factor_mentions规则项错误触发本项，必须引用摘要或风险正文中独立存在的错误陈述。

notes必须同时列4项风险核验和3个摘要的核心结论核验，给出严重错误对象、原文与单元格；不能把表达完整性分当作正确性证据。下面所有非零档均以前述共同条件满足为前提。

严重语义错误包括：绑定错误主体或风险类别、反转条件/影响、将“若／可能”改为已确定事实、虚构原文没有的主体风险，或将平台免责、相关阅读作为主体风险。出现任一项，**本项为0，整题最高70分**。旧风险文本本身确有来源且未反转含义，但未采用明确替代的R2/R3版本，属于“失效版本”，不是虚构；一个失效版本封顶0.25，两个及以上为0。风险定位引用是否准确归Criterion 1，本项不因单纯锚点缺失重复扣分。

在无严重语义错误、无失效版本时，每个完整且唯一的风险算一单位c。单纯漏一条风险不等同于虚构；轻微语义缺口限于四个义务均有对应条目且仅一条未完整表达影响对象/结果，但没有改变方向和条件性。一个多余的完全重复风险行使得最高0.75，两个及以上重复行最高0.5。正文之外另附的明确“非研究风险”说明不算混入；schema允许的额外说明字段不要求排除台账。缺工作簿或风险表为0。

**Score 1.0**: c=4，全部采用有效版本、条件完整、无重复或多余风险。
**Score 0.75**: 四个义务均有对应有效条目，仅一处轻微语义缺口且无重复，或c=4且只有一个完全重复行；无其他问题。
**Score 0.5**: c=3且不符合0.75，或c=4但有两个及以上完全重复行；无失效版本或严重语义错误。
**Score 0.25**: c=1—2，或c=0但至少有来源支持的风险片段，或只有一个失效版本；无严重语义错误，且不符合更低档。
**Score 0.0**: c=0且无有效风险内容、缺工作簿/风险表、两个及以上失效版本，或存在任一严重语义错误。

## Workspace Path

workspace/general_e2e/02_Office/task_020_research_factor_table_extract

## Skills

## Env

## Warmup
