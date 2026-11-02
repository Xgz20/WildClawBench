---
id: 02_Office_task_013_customer_remediation_pack
name: 会议终端专项质量处置：客户处置包定稿
category: 02_Office
timeout_seconds: 7200
modality: pure-text
difficulty: L4
grading_type: hybrid
grading_weights:
  automated: 0.0
  llm_judge: 1.0
tags:
  -general_task_e2e
  -Office
judge_evidence:
  required:
    - path: evaluator_evidence/
      role: grader_generated_evidence
---

## Prompt

质量部这次专项处置下周要审批，资料和上一版草稿都在 `/tmp_workspace/input/`。帮我整理成一套批下来就能安排执行的客户处置包：Excel列清设备、客户和处理安排，Word放执行方案及供审核的客户通知函稿，PPT讲清建议和需要拍板的事项。重要依据要能回查，暂时定不了的事项留下处理办法，交付前核对三份材料。原件保留，成果放到 `/tmp_workspace/results/`。这次只准备文件，不实际联系客户。

## Expected Behavior

- 以本地模拟材料截至2026-10-30 18:00的事实形成72项设备、18个客户的处置总账、执行和通知函稿及管理会简报；所有来源为虚构业务材料，不依赖联网或真实客户联络。
- 从生产初装、售后事件、拆件周转、逐模组复测证、客户/渠道记录还原每台现状，区分取消、领料未安装、已实际换件、返工排除、待补证、返厂隔离及独立替机。截止后事件不能回写为截止前已完成，不把现装合格的供体和装入问题拆件的受体混为一台。
- 全量72项应为客户侧受影响36、厂内隔离6、已可排除24、身份未定6；66项位于客户侧，18个客户。A/B各18台客户侧受影响、各3台隔离、各3台身份未定。已充分证明排除的设备不再次召回，已明确受影响的设备不能统一留待核验；身份未定设备保留限制、责任和补证闭环。
- 根据有效条款及设备级授权确定停止使用、有限临时措施、合格替换、返厂隔离和通知路径；临时措施仍需最终换件，不自动扩大到同一客户其他设备。C07/C14各三台转售对象经D02通知并追踪最终客户回执，同一客户其他设备保持直营路径，旧机与合格替机保留独立记录。
- SA2仅适配QY-A100，SB2仅适配QY-B200，两者不互换。SA2账面32扣预留5、待检3后可发24；SB2账面22扣预留6、待检4后可发12。SB2已确认11月4日到货12件可作条件式安排，另10件采购草案不能计入现货或必然到货。已确认客户侧需求A/B各18，身份未定上界各3，厂内需求各3；现场、待核上界和厂内处置必须各自保留，不能重复占料。
- 最早发运为10月31日处置包获批后，标准物流为发运后两个自然日；到货不等于安装，计划/预约不等于客户确认，更不等于实施或结案。有限现货可分批安排，不能无依据承诺所有SB2对象同一早期节点完成；缺资源或客户窗口不满足时保留停用、备用服务、责任和补充确认路径。
- C05/C12分别列名三台的临时服务仅允许原机隔离并停止承载业务，由备用端维持服务，至11月6日有效，截止时点现场条件尚待确认。临时服务不免永久换件；到期或条件不成立时原机仍停用。六台身份未定设备核实前停用，按现机模组SN照片/安装信息补证后再判，不当作零风险。
- 问题模组及标准上门免费，不以普通保修期为前提；全额退款、免费整机升级或普遍延保无默认授权。C05已经撤回的24个月延保不得继续承诺，仍有效的借机安排须保留，不扩大客户或设备范围。管理会待批请求可提出，但不能写成已经授权。
- 永久关闭须有整机及新旧模组关联、合格件凭证、实施记录、当前设备复测、客户确认、拆件隔离/处置及责任人复核；厂内隔离是控制状态，仍须批准的库存处理，不能用合格替机交付代替旧机关闭。通知稿按客户和有效联系路径准备，不能向某客户附其他客户全量清单，未发送/未签收不能填成完成。

- 接受所有满足相同约束的等价计划，不要求复刻参考日期、文件名、表头、标题、页数或推荐顺序。未来预约、到货、审批和验证不得写成已完成；未决事项应给出责任、截止及条件失败的处理路径。
- Excel真实组织设备/客户/状态/依据/行动，Word提供执行与供审核的通知函稿，PPT呈现有证据的推荐和决策请求。交付前有可观察的源事实复核、处置与函稿权限核对、资源履约核对和三文件一致性核对；只写“已核对”不等于检查证据。

## Grading Criteria

本题100分全部为LLM语义评分。Automated Checks不设评分点，仅在评分阶段生成确定性证据；返回的规则组overall_score=0配合automated权重0，不贡献分值。Python不调用模型、不按候选文件名/Sheet/标题/列名/状态关键词判断业务，也不执行候选公式、宏或代码。候选正文与公式原文按真实位置导出；冻结事实由作者从输入独立核验后嵌入，与私有参考文件校验关联。

| 完整key | 检查对象、计分与证据 | 题目分值 | 能力映射及依据 |
|---|---|---:|---|
| llm_judge.action_validity | 全部72设备及客户、现装模组、状态、授权、处置和资源安排；80分起按独立根因40/20/8/4扣减，扣至本项0；候选+冻结事实 | 80 | reasoning_and_decision_making#1/#3：规则组合和多约束方案，以实际产物选择为证 |
| llm_judge.evidence_traceability | 设备状态、客户通知、处置资源、临时/商务授权四条证据链；每条2分 | 8 | state_awareness#3：分散事实与对象正确关联 |
| llm_judge.cross_document_consistency | 范围、处置状态、执行条件、商务授权四组独立跨文件关系；每组1分 | 4 | 不映射：独立业务验收义务，不推断隐含自检 |
| llm_judge.delivery_roles | 设备Excel、Word执行、Word函稿、决策PPT四个角色；每个1分 | 4 | intent_understanding#2：多交付要求的完整响应 |
| llm_judge.observable_verification | 同次公开轨迹中的源对象状态、处置/函稿权限、库存履约、三文件一致四个有效核对对象；每个1分 | 4 | result_evaluation#1：可观察的验收条件覆盖 |

设五项0—1分依次为a,e,x,d,v，题目分`T=80a+8e+4x+4d+4v`，LLM组分`T/100`。没有总分封顶、最低项门控、乘法惩罚或负分，严重错误按本项责任码严格扣分，不按正确设备占比稀释。每个事实根因只扣一次；重复传播不多罚，独立缺陷可累计。

能力规范为capabilities-2026-09-23-v1。有效映射预算W=96；能力总分`100×(80a+8e+4d+4v)/96`。推理、状态、意图、结果评估各维独立百分制分别为`100a,100e,100d,100v`，对能力总分的贡献上限分别为83.3333、8.3333、4.1667、4.1667。工具调用未覆盖，不计零；不能从产物存在或正确推断工具调用或主动验收。任一必要映射项不可判定时，不删除分母、不输出正式能力总分，已完整可判的维度可单报。旧七维报告没有实现本题五维加权公式。

证据按候选实际位置完整导出，不生成候选语义摘要，不虚构LLM到Python的自由表格规范化桥接。总文本上限74,000字符、单片17,000字符；超限显式报评分器错误，不截取部分而假装全量核验。原始Office二进制不由普通collector直接读取。私有GT三文件只做哈希及可解析性核验，Judge获得经独立审计的必要冻结事实而非重复文书全文。公式与缓存分别保留；没有缓存本身不等于算错。Word保留表格行列/合并和修订状态，PPT按真实页序并记录隐藏页和所属备注。外链、宏、嵌入对象不执行，图片不渲染；若必要业务内容只存在于无法观察的对象，受影响项不可判定，不能把未见当缺失或评价未观察的视觉布局。

候选完整缺交付、空壳或确实损坏按Rubric判；缺GT、提取异常、无法覆盖的证据预算属于评分器故障。普通框架可能将带error的故障输出记为数值0，不能将该数值解释为有效能力分；本题不为此修改框架。评分后生成的evaluator_evidence不是Agent自检记录。公开轨迹缺失、压缩或截断时，不以“没看到检查”认定未执行。Judge notes应紧凑按key给出扣分码/计数和关键位置，避免冗长重复清单；接口的数值占位不改变不可判定状态。

## Automated Checks

```python
"""Office013 deterministic evidence export. No business scoring or model call."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import math
import os
import re
import zipfile
import xml.etree.ElementTree as ET

INPUT_HASHES = {'input/专项服务约定.docx': '61ff19ffd90779cb8c28748c3afffff6b93c99ceab90f21cdbfc1a636ec90fe6', 'input/到货及预留.xlsx': '29eb518f25f5d076d8c8252f6609ea0316e26364f697aa43a81b03e9ca28b515', 'input/售后履历.xlsx': '65b1ec4077f063d70c8b3e9adc1e37b5118ff6428ce4e54b232e25e012d9a614', 'input/客户与供应往来归档.pdf': 'd92b17a3275831f3c408bf68c2b929d42352860cb08daf815ea115c358c8160e', 'input/客户函稿_1024.docx': '300e9122cb566566ceebd65cf938829888115f181ad1dafb08b53379f479aece', 'input/客户服务协调会_R0.pptx': 'dbceacba254657cdd90a6c19ce956b4116893e27b5b1c8ed79a3a8617d837599', 'input/库存及兼容.xlsx': '39d2e574e3f0038219526d06d6eedd0d5a986fc5d58422140122a246dc113f92', 'input/渠道交付与返厂签收.pdf': 'fde1806bab2b690a0a08ac11776672bbc01b504e9b6d61ec60dc3b87e8f66362', 'input/渠道台账.xlsx': '881453706177912f1d3c6b232fca7d5b90c064c4a1cb65b4502d855a9a0012f0', 'input/生产履历.xlsx': '0f5ae9a7828fcec1da105cf6b97ee88c3ab48d37d5232e6f4166dd3ebad005de', 'input/经营讨论记录.pdf': 'b24de1280fcfbd9b7f96d9c46e80b4760d474997f882229ac93f3a4294752b69', 'input/补充试验及处理批准.pdf': 'da86f1f27e8a3feea094717d060110a19ccf5a2e669c1997e0fae38f73f057ef', 'input/质量调查初报.pdf': '8f4c95a488a807664a69568c8e056fa868128b0266473ed9c72a041b36809370', 'input/部件周转.csv': 'e803d6b90427d9e3a5092b982624c1fa9ea88b2bd9d294022a71199107c61719'}
GT_HASHES = {'customer_actions.xlsx': '125e72076aaecef24f69d513f7365ff1376067281b82b06c772b75091d44ee00', 'customer_execution.docx': '974dbbe9db0a8f6f5a216d4239f177f262ecb92e823abe89b501c5ddb871fc3a', 'management_brief.pptx': 'f613b5019ae1f6b60529bb93e28d5a127bd41389119047ac32535f4bee3a0ded'}
FROZEN_TRUTH = {'basis': {'cutoff': '2026-10-30 18:00:00', 'method': 'independent replay of frozen exported XLSX/CSV', 'technical_rule': 'QTR-261029-02 applies to all asset rows; its common citation is omitted from each source_refs list without changing provenance.'}, 'asset_schema': ['serial', 'model_code', 'customer_id', 'current_module', 'current_lot', 'state_code', 'notice_route', 'source_refs'], 'codes': {'model': {'A': 'QY-A100 / SA2 only', 'B': 'QY-B200 / SB2 only'}, 'route': {'C': '直营', 'F': '厂内服务主管及客户经理同步', 'D02': 'D02转达最终使用方并回收回执'}, 'state': {'A': '客户侧受影响；待永久处置，不断言此刻正在运行', 'Q': '厂内隔离；未修未报废，仍需内部处置', 'X': '已有充分证据排除；保留依据不再召回', 'U': '现机身份未定；核实前停用、补证后再定'}}, 'assets': [['QY2600135', 'A', 'C14', 'M26352135', 'MA2609', 'X', 'C', ['PD-1068', 'CT-1068', 'SV-1068-01']], ['QY2603448', 'A', 'C07', 'M26031990', 'MA2607', 'A', 'C', ['PD-1007', 'CT-1007', 'SV-1007-01', 'SV-1007-02']], ['QY2603682', 'B', 'C06', 'M26017409', 'MB2607', 'A', 'C', ['PD-1060', 'CT-1060']], ['QY2606211', 'A', 'C14', 'M26893032', 'MA2607', 'Q', 'F', ['PD-1032', 'CT-1032', 'SV-1032-01', 'SV-1032-02']], ['QY2606736', 'A', 'C02', 'M26257557', 'MA2607', 'A', 'C', ['PD-1056', 'CT-1056']], ['QY2608031', 'B', 'C12', 'M26429637', 'MB2607', 'A', 'C', ['PD-1030', 'CT-1030', 'SV-1030-01', 'SV-1030-02', 'TR-1030']], ['QY2610891', 'A', 'C03', 'M26088090', 'MA2607', 'A', 'C', ['PD-1003', 'CT-1003', 'SV-1003-01', 'SV-1003-02']], ['QY2613261', 'A', 'C08', 'M26827244', 'MA2607', 'A', 'C', ['PD-1008', 'CT-1008', 'SV-1008-01', 'SV-1008-02']], ['QY2613817', 'A', 'C15', 'M26045488', 'MA2609', 'X', 'C', ['PD-1015', 'CT-1015', 'SV-1015-01', 'SV-1015-02']], ['QY2615434', 'B', 'C17', 'M26059734', 'MB2609', 'X', 'C', ['PD-1071', 'CT-1071', 'SV-1071-01']], ['QY2615472', 'A', 'C09', 'M26794380', 'MA2607', 'A', 'C', ['PD-1027', 'CT-1027', 'SV-1027-01', 'SV-1027-02', 'TR-1027']], ['QY2615719', 'A', 'C13', 'M26642946', 'MA2607', 'X', 'C', ['PD-1049', 'CT-1049', 'RW-1049', 'QC-1049']], ['QY2616976', 'B', 'C11', 'M26014051', 'MB2607', 'A', 'C', ['PD-1029', 'CT-1029', 'SV-1029-01', 'SV-1029-02', 'TR-1029']], ['QY2617044', 'A', 'C05', 'M26078108', 'MA2607', 'A', 'C', ['PD-1043', 'CT-1043', 'SV-1043-01']], ['QY2617455', 'B', 'C18', 'M26940163', 'MB2607', 'Q', 'F', ['PD-1036', 'CT-1036', 'SV-1036-01', 'SV-1036-02']], ['QY2618221', 'B', 'C05', 'M26540270', 'MB2607', 'A', 'C', ['PD-1059', 'CT-1059']], ['QY2621337', 'A', 'C07', 'M26009722', 'MA2607', 'A', 'D02', ['PD-1061', 'CT-1061', 'CH-1061']], ['QY2622123', 'A', 'C07', 'M26330676', 'MA2607', 'A', 'C', ['PD-1025', 'CT-1025', 'SV-1025-01', 'SV-1025-02', 'TR-1025']], ['QY2622658', 'B', 'C12', 'M26588316', 'MB2607', 'A', 'C', ['PD-1046', 'CT-1046', 'SV-1046-01']], ['QY2624310', 'B', 'C06', 'M26342387', 'MB2609', 'X', 'C', ['PD-1024', 'CT-1024', 'SV-1024-01', 'SV-1024-02', 'TR-1024', 'TR-1030']], ['QY2625302', 'A', 'C13', 'M26347672', 'MA2609', 'X', 'C', ['PD-1013', 'CT-1013', 'SV-1013-01', 'SV-1013-02']], ['QY2625544', 'B', 'C11', 'M26941455', 'MB2607', 'A', 'C', ['PD-1011', 'CT-1011', 'SV-1011-01', 'SV-1011-02']], ['QY2626916', 'B', 'C14', 'M26465459', 'MB2607', 'A', 'D02', ['PD-1065', 'CT-1065', 'CH-1065']], ['QY2628376', 'A', 'C13', 'M26696830', 'MA2607', 'Q', 'F', ['PD-1031', 'CT-1031', 'SV-1031-01', 'SV-1031-02']], ['QY2631167', 'A', 'C15', 'M26453146', 'MA2607', 'X', 'C', ['PD-1051', 'CT-1051', 'RW-1051', 'QC-1051']], ['QY2631521', 'B', 'C18', 'M26064700', 'MB2607', 'X', 'C', ['PD-1054', 'CT-1054', 'RW-1054', 'QC-1054']], ['QY2633186', 'B', 'C16', 'M26564908', 'MB2609', 'X', 'C', ['PD-1070', 'CT-1070', 'SV-1070-01']], ['QY2633791', 'B', 'C17', 'M26644688', 'MB2607', 'Q', 'F', ['PD-1035', 'CT-1035', 'SV-1035-01', 'SV-1035-02']], ['QY2639972', 'B', 'C17', 'M26722073', 'MB2607', 'X', 'C', ['PD-1053', 'CT-1053', 'RW-1053', 'QC-1053']], ['QY2640278', 'A', 'C14', 'M26158094', 'MA2609', 'X', 'C', ['PD-1014', 'CT-1014', 'SV-1014-01', 'SV-1014-02']], ['QY2641399', 'B', 'C05', '待核实', '待核实', 'U', 'C', ['PD-1041', 'CT-1041', 'SV-1041-01']], ['QY2643712', 'B', 'C16', 'M26530537', 'MB2609', 'X', 'C', ['PD-1016', 'CT-1016', 'SV-1016-01', 'SV-1016-02']], ['QY2644125', 'A', 'C05', 'M26368292', 'MA2607', 'A', 'C', ['PD-1044', 'CT-1044', 'SV-1044-01']], ['QY2644345', 'A', 'C09', 'M26964814', 'MA2607', 'A', 'C', ['PD-1009', 'CT-1009', 'SV-1009-01', 'SV-1009-02']], ['QY2645320', 'A', 'C07', 'M26296107', 'MA2607', 'A', 'D02', ['PD-1062', 'CT-1062', 'CH-1062']], ['QY2646495', 'A', 'C03', '待核实', '待核实', 'U', 'C', ['PD-1039', 'CT-1039', 'SV-1039-01']], ['QY2646941', 'B', 'C16', 'M26159382', 'MB2607', 'Q', 'F', ['PD-1034', 'CT-1034', 'SV-1034-01', 'SV-1034-02']], ['QY2648624', 'A', 'C05', 'M26726914', 'MA2607', 'A', 'C', ['PD-1045', 'CT-1045', 'SV-1045-01']], ['QY2649315', 'A', 'C03', 'M26298688', 'MA2609', 'X', 'C', ['PD-1021', 'CT-1021', 'SV-1021-01', 'SV-1021-02', 'TR-1027', 'TR-1021']], ['QY2651976', 'A', 'C01', '待核实', '待核实', 'U', 'C', ['PD-1037', 'CT-1037', 'SV-1037-01']], ['QY2652087', 'B', 'C10', 'M26341038', 'MB2607', 'A', 'C', ['PD-1010', 'CT-1010', 'SV-1010-01', 'SV-1010-02']], ['QY2654516', 'A', 'C02', '待核实', '待核实', 'U', 'C', ['PD-1038', 'CT-1038', 'SV-1038-01']], ['QY2656682', 'B', 'C04', '待核实', '待核实', 'U', 'C', ['PD-1040', 'CT-1040', 'SV-1040-01']], ['QY2657823', 'A', 'C01', 'M26654283', 'MA2607', 'A', 'C', ['PD-1001', 'CT-1001', 'SV-1001-01', 'SV-1001-02']], ['QY2658743', 'A', 'C01', 'M26301813', 'MA2609', 'X', 'C', ['PD-1019', 'CT-1019', 'SV-1019-01', 'SV-1019-02', 'TR-1025', 'TR-1019']], ['QY2662573', 'A', 'C14', 'M26298239', 'MA2607', 'X', 'C', ['PD-1050', 'CT-1050', 'RW-1050', 'QC-1050']], ['QY2664782', 'B', 'C05', 'M26438153', 'MB2609', 'X', 'C', ['PD-1023', 'CT-1023', 'SV-1023-01', 'SV-1023-02', 'TR-1023', 'TR-1029']], ['QY2664939', 'B', 'C18', 'M26270649', 'MB2609', 'X', 'C', ['PD-1072', 'CT-1072', 'SV-1072-01']], ['QY2665243', 'A', 'C13', 'M26618871', 'MA2609', 'X', 'C', ['PD-1067', 'CT-1067', 'SV-1067-01']], ['QY2665265', 'B', 'C05', 'M26681419', 'MB2607', 'A', 'C', ['PD-1005', 'CT-1005', 'SV-1005-01', 'SV-1005-02']], ['QY2665800', 'B', 'C04', 'M26005130', 'MB2607', 'A', 'C', ['PD-1004', 'CT-1004', 'SV-1004-01', 'SV-1004-02']], ['QY2669093', 'A', 'C07', 'M26346535', 'MA2607', 'A', 'D02', ['PD-1063', 'CT-1063', 'CH-1063']], ['QY2673236', 'B', 'C16', 'M26459628', 'MB2607', 'X', 'C', ['PD-1052', 'CT-1052', 'RW-1052', 'QC-1052']], ['QY2674168', 'B', 'C14', 'M26914181', 'MB2607', 'A', 'D02', ['PD-1066', 'CT-1066', 'CH-1066']], ['QY2674419', 'A', 'C02', 'M26975860', 'MA2609', 'X', 'C', ['PD-1020', 'CT-1020', 'SV-1020-01', 'SV-1020-02', 'TR-1026', 'TR-1020']], ['QY2674443', 'A', 'C01', 'M26651283', 'MA2607', 'A', 'C', ['PD-1055', 'CT-1055']], ['QY2674599', 'B', 'C04', 'M26697485', 'MB2609', 'X', 'C', ['PD-1022', 'CT-1022', 'SV-1022-01', 'SV-1022-02', 'TR-1028', 'TR-1022']], ['QY2675311', 'B', 'C10', 'M26852482', 'MB2607', 'A', 'C', ['PD-1028', 'CT-1028', 'SV-1028-01', 'SV-1028-02', 'TR-1028']], ['QY2675486', 'A', 'C15', 'M26506457', 'MA2607', 'Q', 'F', ['PD-1033', 'CT-1033', 'SV-1033-01', 'SV-1033-02']], ['QY2676349', 'A', 'C08', 'M26980447', 'MA2607', 'A', 'C', ['PD-1026', 'CT-1026', 'SV-1026-01', 'SV-1026-02', 'TR-1026']], ['QY2678285', 'B', 'C12', 'M26754631', 'MB2607', 'A', 'C', ['PD-1047', 'CT-1047', 'SV-1047-01']], ['QY2678640', 'B', 'C12', 'M26296760', 'MB2607', 'A', 'C', ['PD-1012', 'CT-1012', 'SV-1012-01', 'SV-1012-02']], ['QY2683063', 'A', 'C03', 'M26177202', 'MA2607', 'A', 'C', ['PD-1057', 'CT-1057']], ['QY2685088', 'B', 'C17', 'M26369517', 'MB2609', 'X', 'C', ['PD-1017', 'CT-1017', 'SV-1017-01', 'SV-1017-02']], ['QY2685510', 'B', 'C06', '待核实', '待核实', 'U', 'C', ['PD-1042', 'CT-1042', 'SV-1042-01']], ['QY2691025', 'B', 'C04', 'M26284582', 'MB2607', 'A', 'C', ['PD-1058', 'CT-1058']], ['QY2691154', 'B', 'C12', 'M26268732', 'MB2607', 'A', 'C', ['PD-1048', 'CT-1048', 'SV-1048-01']], ['QY2694296', 'B', 'C06', 'M26314542', 'MB2607', 'A', 'C', ['PD-1006', 'CT-1006', 'SV-1006-01', 'SV-1006-02']], ['QY2696180', 'A', 'C15', 'M26155879', 'MA2609', 'X', 'C', ['PD-1069', 'CT-1069', 'SV-1069-01']], ['QY2696376', 'B', 'C14', 'M26972745', 'MB2607', 'A', 'D02', ['PD-1064', 'CT-1064', 'CH-1064']], ['QY2696492', 'A', 'C02', 'M26638488', 'MA2607', 'A', 'C', ['PD-1002', 'CT-1002', 'SV-1002-01', 'SV-1002-02']], ['QY2696526', 'B', 'C18', 'M26430348', 'MB2609', 'X', 'C', ['PD-1018', 'CT-1018', 'SV-1018-01', 'SV-1018-02']]], 'customers': [['C01', '江湾会展运营'], ['C02', '临浦科创园'], ['C03', '海澄设计中心'], ['C04', '松庭培训服务'], ['C05', '云岚会议服务'], ['C06', '北辰数研中心'], ['C07', '青禾园区运营'], ['C08', '鸿屿咨询'], ['C09', '映河文化交流'], ['C10', '星浦企业服务'], ['C11', '东麓创新中心'], ['C12', '知行远程培训'], ['C13', '锦棠商务服务'], ['C14', '澄岳教育科技'], ['C15', '观澜会务管理'], ['C16', '合溪产业服务'], ['C17', '启明创研中心'], ['C18', '云岸协作空间']], 'replacement_pairs': [['QY2600135', 'QY2606211'], ['QY2615434', 'QY2633791'], ['QY2633186', 'QY2646941'], ['QY2664939', 'QY2617455'], ['QY2665243', 'QY2628376'], ['QY2696180', 'QY2675486']], 'scope': {'total': 72, 'customers': 18, 'customer_side_assets': 66, 'states': {'A': 36, 'Q': 6, 'X': 24, 'U': 6}, 'A_and_B_each': {'A': 18, 'Q': 3, 'U': 3}, 'notification_packets': '18客户20接收路径；C07/C14各有直营+D02。等价分组附件可接受，不强制函件数。'}, 'temporary_serials': [['QY2617044', 'C05'], ['QY2622658', 'C12'], ['QY2644125', 'C05'], ['QY2648624', 'C05'], ['QY2678285', 'C12'], ['QY2691154', 'C12']], 'rules': [['QIR-261024-01 -> QTR-261029-02', '使用有效补充试验及逐模组R3证；原批次命中不等于永远受影响，原批次合格不等于当前模组合格。R3须绑定现装模组且复测通过，其他版本或他机证书不排除。'], ['SVC-2026-01 / service events', '领料、发货、预约、撤销不是已换件。只采截止前实际已完成且未有效撤销的安装和验收；10/31之后的事件不得回写10/30。拆件供体/受体与旧机/替机分开追踪。'], ['AP-TMP-261029 / QTR第3页 / COR-2610-TEMP', '仅所列C05/C12各三台。原机隔离业务网络并停止承载业务、备用端接替至11/06；现场落实回执未齐，不能声称已完成。到期或条件未落实，原机仍停用，由周衡协调备用端与永久换件。临时服务不能结案。'], ['COR-2610-C05-25 -> COR-2610-C05-29', '10/25 C05获24个月延保+借机；10/29 18:10仅撤回延保，借机继续有效，不可撤回全部或保留全部。'], ['SVC-2026-01', '问题模组及标准上门免费，不以普通保修期为前提；退款、整机升级、普遍延保无默认授权。新请求须按权限另审，待批请求不等于已承诺。'], ['COR-2610-C12', '11/06上午为客户服务窗口，预约尚未确认。仍须兼容件到位、服务和现场条件满足；不能作技术处置豁免或无条件保证完成。'], ['COR-2610-D02 / 渠道台账', '仅六台转售资产经D02授权窗口传递、协调最终使用方并追踪回执；C07/C14其余直营设备仍按直营。不能通知历史采购方即视为最终客户已触达。各客户只收到本客户资产清单。'], ['库存及兼容.xlsx', 'SA2:32-5-3=24可发，只适配A；SB2:22-6-4=12可发，只适配B。两料不互换，待检/他项预留不能当现货。客户侧确认需求各18，待核上界各3，厂内各3；总上界各24，不重复占用。'], ['COR-2610-SUP / PO-2611-041', 'SB2 12件确认11/04到货，仍须检收放行；可以据此做有条件安排，不能先算成已在库。'], ['COR-2610-DRAFT / PO-2611-D10', 'SB2 10件11/02采购草案未批准未下单，不可计为可兑现现货/必然到货。'], ['SVC-2026-01 / MIN-261024-01', '处置包审批后最早10/31发运，运输两个自然日，实际签收另确认；发运不等于到达、到达不等于修复、建议窗口不等于客户确认。分批计划可行，条件失败时保留停用和资源补足闭环，不强制唯一排期。'], ['SVC-2026-01 / QTR关闭条件', '客户侧永久关闭：整机/新旧模组SN、合格件、实施记录、功能复测、客户确认、拆件隔离/处置和责任复核。厂内隔离仍需内部修复/复测/放行或报废凭证，不用替机签收或客户验收替代旧机关闭。'], ['SVC-2026-01审批与范围', '沈岚与周衡共同审核后才发放，仍为待审函稿，无实际联系/发信/签收。本客户函不附其他客户资料。原稿失效承诺应修正，原件保留。']], 'equivalence': 'Any action plan satisfying these facts and all relevant conditions is accepted. File names, sheet names, header synonyms, row/column order, summaries and reasonable document splitting are not exact-match requirements. Numeric caches absent alone are not a business error.', 'source_locations': {'decode': 'Sort the unique source_refs appearing in assets lexicographically. Runs consume that ordered ID list in sequence: [zero-based sheet index, exact row numbers]. One row number per ID. XLSX row numbers are worksheet row addresses; CSV is physical file line. This is an exact lossless ID↔file/sheet/row map, not a preferred citation format.', 'sheets': [['渠道台账.xlsx', '流转签收'], ['渠道台账.xlsx', '合同设备登记'], ['生产履历.xlsx', '整机出厂'], ['生产履历.xlsx', '模组检验'], ['售后履历.xlsx', '服务事件'], ['部件周转.csv', 'CSV物理行']], 'runs': [[0, [349, 379, 320, 513, 102, 350]], [1, [634, 647, 726, 438, 742, 522, 341, 301, 468, 537, 364, 571, 70, 150, 583, 114, 216, 611, 308, 600, 139, 531, 593, 300, 604, 218, 209, 695, 391, 516, 488, 272, 446, 720, 508, 307, 106, 63, 772, 92, 658, 298, 511, 141, 526, 496, 290, 650, 412, 323, 123, 11, 310, 427, 159, 21, 499, 225, 203, 390, 247, 208, 616, 651, 326, 691, 622, 497, 380, 373, 125, 65]], [2, [1575, 881, 607, 1441, 398, 1319, 148, 1309, 1815, 1167, 644, 1877, 1317, 353, 777, 1733, 432, 548, 176, 363, 305, 1505, 1414, 966, 1784, 1857, 390, 1166, 331, 1002, 837, 907, 1236, 87, 1274, 50, 1523, 960, 565, 1679, 808, 1606, 263, 558, 511, 314, 316, 1230, 882, 1555, 1422, 1168, 1102, 1712, 900, 600, 1194, 792, 754, 872, 566, 1531, 893, 954, 1326, 602, 1022, 1266, 1846, 1639, 554, 1243]], [3, [682, 690, 713, 362, 814, 443, 682, 690, 713, 362, 814, 443]], [4, [116, 303, 963, 435, 817, 926, 989, 445, 724, 1011, 458, 475, 670, 271, 204, 348, 460, 682, 992, 908, 1081, 1107, 251, 602, 193, 131, 547, 441, 923, 54, 190, 534, 805, 982, 196, 95, 597, 705, 834, 589, 329, 128, 302, 1044, 161, 1028, 290, 554, 412, 321, 718, 358, 1027, 636, 1059, 85, 212, 504, 756, 823, 233, 849, 691, 133, 36, 411, 112, 544, 173, 1069, 330, 423, 798, 163, 611, 1015, 726, 603, 528, 422, 1035, 722, 1050, 265, 522, 686, 110, 187, 1078, 546]], [5, [520, 601, 456, 210, 193, 413, 31, 195, 4, 55, 306, 573]]]}}
VERSION = "office013-customer-remediation-v1"
MAX_TOTAL_TEXT = 74000
MAX_PART_TEXT = 17000
MAX_FILE_BYTES = 16000000
MAX_ZIP_BYTES = 48000000
MAX_XML_BYTES = 10000000
EXPECTED_GT = ("customer_actions.xlsx", "customer_execution.docx", "management_brief.pptx")
OFFICE_SUFFIXES = {".xlsx", ".docx", ".pptx"}
TEXT_SUFFIXES = {".txt", ".md", ".csv", ".tsv", ".json"}
NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
      "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
      "r": "http://schemas.openxmlformats.org/package/2006/relationships"}

class EvaluatorEvidenceError(RuntimeError):
    pass

class CandidateFormatError(ValueError):
    pass


def _j(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _digest(path):
    h = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1048576), b""):
            h.update(chunk)
    return h.hexdigest()


def _within(path, parent):
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _xml(z, name):
    info = z.getinfo(name)
    if info.file_size > MAX_XML_BYTES:
        raise EvaluatorEvidenceError("XML part exceeds safe parser budget: " + name)
    raw = z.read(name)
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise CandidateFormatError("XML entities are not allowed")
    return ET.fromstring(raw)


def _safe_zip(path):
    if path.stat().st_size > MAX_FILE_BYTES:
        raise EvaluatorEvidenceError("file exceeds safe container budget")
    z = zipfile.ZipFile(path)
    infos = z.infolist()
    if len(infos) > 2000 or sum(x.file_size for x in infos) > MAX_ZIP_BYTES:
        z.close()
        raise EvaluatorEvidenceError("archive exceeds safe expansion budget")
    names = [x.filename for x in infos]
    if len(names) != len(set(names)):
        z.close()
        raise CandidateFormatError("duplicate archive member names")
    for info in infos:
        name = info.filename.replace("\\", "/")
        p = PurePosixPath(name)
        symlink = (info.external_attr >> 16) & 0o170000 == 0o120000
        if p.is_absolute() or ".." in p.parts or ":" in name or symlink:
            z.close()
            raise CandidateFormatError("unsafe archive member")
        if info.file_size > 1000000 and info.file_size / max(info.compress_size, 1) > 300:
            z.close()
            raise EvaluatorEvidenceError("archive compression ratio exceeds safe expansion budget")
    return z


def _texts(node, namespace):
    return "".join(x.text or "" for x in node.iter("{" + NS[namespace] + "}t"))


def _sheet_records(z):
    strings = []
    if "xl/sharedStrings.xml" in z.namelist():
        strings = [_texts(si, "s") for si in _xml(z, "xl/sharedStrings.xml")]
    styles = {}
    if "xl/styles.xml" in z.namelist():
        root = _xml(z, "xl/styles.xml")
        fmts = {x.attrib.get("numFmtId"): x.attrib.get("formatCode") for x in root.findall("s:numFmts/s:numFmt", NS)}
        styles = {str(i): fmts.get(x.attrib.get("numFmtId"), "builtin:" + x.attrib.get("numFmtId", "0")) for i, x in enumerate(root.findall("s:cellXfs/s:xf", NS))}
    rels = {x.attrib["Id"]: x.attrib.get("Target", "") for x in _xml(z, "xl/_rels/workbook.xml.rels")}
    wb = _xml(z, "xl/workbook.xml")
    yield ["workbook", {"date1904": wb.find("s:workbookPr", NS).attrib.get("date1904", "0") if wb.find("s:workbookPr", NS) is not None else "0", "number_formats": {k: v for k, v in styles.items() if v not in ("builtin:0", "General")}, "default_number_format": "General"}]
    for sheet in wb.findall("s:sheets/s:sheet", NS):
        rid = sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        target = rels.get(rid, "")
        if target.startswith("/"):
            member = target.lstrip("/")
        else:
            member = "xl/" + target
        if ".." in PurePosixPath(member).parts or member not in z.namelist():
            raise CandidateFormatError("invalid worksheet relationship")
        root = _xml(z, member)
        merges = [x.attrib.get("ref") for x in root.findall("s:mergeCells/s:mergeCell", NS)]
        yield ["sheet", sheet.attrib.get("name"), {"member": member, "state": sheet.attrib.get("state", "visible"), "merged": merges}]
        for row in root.findall("s:sheetData/s:row", NS):
            cells = []
            for cell in row.findall("s:c", NS):
                typ = cell.attrib.get("t", "n")
                value = cell.find("s:v", NS)
                raw = value.text if value is not None else None
                formula = cell.find("s:f", NS)
                if typ == "s" and raw is not None:
                    try:
                        content = strings[int(raw)]
                    except (ValueError, IndexError) as exc:
                        raise CandidateFormatError("invalid shared string index") from exc
                elif typ == "inlineStr":
                    content = _texts(cell, "s")
                else:
                    content = raw
                if formula is not None:
                    content = {"formula": formula.text or "", "cached": content}
                    if formula.attrib:
                        content["formula_attributes"] = formula.attrib
                    if value is None or raw is None:
                        content["cache_present"] = False
                if content is None and formula is None:
                    continue
                item = [cell.attrib.get("r"), content]
                if typ not in ("s", "inlineStr", "str") and formula is None:
                    item.append({"type": typ})
                format_index = cell.attrib.get("s", "0")
                if styles.get(format_index, "builtin:0") not in ("builtin:0", "General"):
                    item.append({"number_format_style": format_index})
                cells.append(item)
            if cells:
                yield ["row", row.attrib.get("r"), cells]
    for name in sorted(z.namelist()):
        if name.startswith("xl/comments") and name.endswith(".xml"):
            for item in _xml(z, name).findall("s:commentList/s:comment", NS):
                yield ["comment", name, item.attrib.get("ref"), _texts(item, "s")]


def _resolve_relationship(source_member, target):
    import posixpath
    if ":" in target or "\\" in target:
        raise CandidateFormatError("unsafe package relationship")
    member = posixpath.normpath(target.lstrip("/") if target.startswith("/") else posixpath.join(posixpath.dirname(source_member), target))
    if member.startswith("../") or member == "..":
        raise CandidateFormatError("package relationship escapes root")
    return member


def _relationships(z, source_member):
    import posixpath
    parent, name = posixpath.split(source_member)
    rel_name = posixpath.join(parent, "_rels", name + ".rels")
    if rel_name not in z.namelist():
        return {}
    return {x.attrib["Id"]: x.attrib for x in _xml(z, rel_name)}


def _word_records(z):
    names = [n for n in z.namelist() if re.fullmatch(r"word/(document|header\d+|footer\d+|footnotes|endnotes|comments)\.xml", n)]
    wtag = lambda name: "{" + NS["w"] + "}" + name
    for member in sorted(names, key=lambda n: (n != "word/document.xml", n)):
        yield ["word_part", member]
        table_counter = [0]
        paragraph_counter = [0]
        def walk(container, location, inherited="effective"):
            for child in container:
                local = child.tag.rsplit("}", 1)[-1]
                if local == "p":
                    paragraph_counter[0] += 1
                    fragments = []
                    def inline(node, context="effective"):
                        kind = node.tag.rsplit("}", 1)[-1]
                        if kind in ("del", "moveFrom"):
                            context = "deleted"
                        elif kind in ("ins", "moveTo"):
                            context = "inserted"
                        if kind == "fldSimple" and node.attrib.get(wtag("instr")):
                            fragments.append(["field_instruction", node.attrib[wtag("instr")]])
                        if kind in ("t", "delText", "instrText") and node.text:
                            label = "field_instruction" if kind == "instrText" else ("deleted" if kind == "delText" else context)
                            fragments.append([label, node.text])
                        elif kind in ("tab", "br", "cr"):
                            fragments.append([context, "\t" if kind == "tab" else "\n"])
                        for nested in node:
                            inline(nested, context)
                    inline(child, inherited)
                    if fragments:
                        merged = []
                        for kind, text in fragments:
                            if merged and merged[-1][0] == kind:
                                merged[-1][1] += text
                            else:
                                merged.append([kind, text])
                        # effective/inserted are current display; deleted/instruction are separately labelled.
                        yield ["p", location.removeprefix("b").replace("/", "") + "p" + str(paragraph_counter[0]), merged[0][1] if len(merged) == 1 and merged[0][0] == "effective" else {"runs": merged}]
                elif local == "tbl":
                    table_counter[0] += 1
                    loc = location + "/t" + str(table_counter[0])
                    grid = [x.attrib.get(wtag("w")) for x in child.findall("w:tblGrid/w:gridCol", NS)]
                    yield ["table", loc.removeprefix("b").replace("/", ""), {"columns": len(grid)}]
                    for ri, row in enumerate(child.findall("w:tr", NS), 1):
                        for ci, cell in enumerate(row.findall("w:tc", NS), 1):
                            cloc = loc + "/r%d/c%d" % (ri, ci)
                            props = {}
                            for prop in ("gridSpan", "vMerge", "hMerge"):
                                element = cell.find("w:tcPr/w:" + prop, NS)
                                if element is not None:
                                    props[prop] = element.attrib.get(wtag("val"), "continue")
                            if props or not any(x.text for x in cell.iter() if x.tag.rsplit("}", 1)[-1] in ("t", "delText", "instrText")):
                                yield ["table_cell", cloc.removeprefix("b").replace("/", ""), props]
                            yield from walk(cell, cloc, inherited)
                elif local not in ("pPr", "tblPr", "tcPr", "sectPr", "tblGrid"):
                    extra = ("/" + local + str(child.attrib.get(wtag("id"), ""))) if local in ("footnote", "endnote", "comment") else ""
                    context = "deleted" if local in ("del", "moveFrom") else ("inserted" if local in ("ins", "moveTo") else inherited)
                    yield from walk(child, location + extra, context)
        yield from walk(_xml(z, member), "b")


def _ppt_records(z):
    pns = {"p": "http://schemas.openxmlformats.org/presentationml/2006/main"}
    yield ["slide_table_encoding", "After slide_table identifies slide/table and column count, tc gives row, column, merge attributes and complete cell paragraphs for that table; table text is not repeated as slide_paragraph."]
    presentation = _xml(z, "ppt/presentation.xml")
    rels = _relationships(z, "ppt/presentation.xml")
    for index, sid in enumerate(presentation.findall("p:sldIdLst/p:sldId", pns), 1):
        rid = sid.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        rel = rels.get(rid, {})
        if rel.get("TargetMode") == "External":
            raise CandidateFormatError("slide relationship is external")
        member = _resolve_relationship("ppt/presentation.xml", rel.get("Target", ""))
        slide = _xml(z, member)
        yield ["slide", index, member, {"hidden": slide.attrib.get("show", "1") == "0"}]
        tables = list(slide.iter("{" + NS["a"] + "}tbl"))
        table_paragraphs = {id(paragraph) for table in tables for paragraph in table.iter("{" + NS["a"] + "}p")}
        for paragraph_index, paragraph in enumerate(slide.iter("{" + NS["a"] + "}p"), 1):
            if id(paragraph) in table_paragraphs:
                continue
            text = _texts(paragraph, "a")
            if text:
                yield ["slide_paragraph", index, paragraph_index, text]
        for table_index, table in enumerate(tables, 1):
            grid = [x.attrib.get("w") for x in table.findall("a:tblGrid/a:gridCol", NS)]
            yield ["slide_table", index, table_index, {"columns": len(grid)}]
            for row_index, row in enumerate(table.findall("a:tr", NS), 1):
                for col_index, cell in enumerate(row.findall("a:tc", NS), 1):
                    paragraphs = [_texts(paragraph, "a") for paragraph in cell.iter("{" + NS["a"] + "}p")]
                    properties = {key: cell.attrib[key] for key in ("gridSpan", "rowSpan", "hMerge", "vMerge") if key in cell.attrib}
                    yield ["tc", row_index, col_index, properties, paragraphs]
        for relationship in _relationships(z, member).values():
            if relationship.get("Type", "").endswith("/notesSlide") and relationship.get("TargetMode") != "External":
                notes_member = _resolve_relationship(member, relationship["Target"])
                for paragraph_index, paragraph in enumerate(_xml(z, notes_member).iter("{" + NS["a"] + "}p"), 1):
                    text = _texts(paragraph, "a")
                    if text:
                        yield ["slide_notes", index, notes_member, paragraph_index, text]
        for shape in slide.iter():
            if shape.tag.rsplit("}", 1)[-1] == "cNvPr" and (shape.attrib.get("descr") or shape.attrib.get("title")):
                yield ["object_alt_text", index, shape.attrib.get("id"), shape.attrib.get("title", ""), shape.attrib.get("descr", "")]


def _office(path):
    result = []
    with _safe_zip(path) as z:
        members = set(z.namelist())
        essential = {".xlsx": "xl/workbook.xml", ".docx": "word/document.xml", ".pptx": "ppt/presentation.xml"}[path.suffix.lower()]
        if "[Content_Types].xml" not in members or essential not in members:
            raise CandidateFormatError("extension does not match an Office package")
        extractor = {".xlsx": _sheet_records, ".docx": _word_records, ".pptx": _ppt_records}[path.suffix.lower()]
        extracted = list(extractor(z))
        from collections import Counter
        if path.suffix.lower() == ".xlsx":
            text_values = [cell[1] for record in extracted if record[0] == "row" for cell in record[2] if isinstance(cell[1], str)]
        elif path.suffix.lower() == ".docx":
            text_values = [record[2] for record in extracted if record[0] == "p" and isinstance(record[2], str)]
        else:
            text_values = []
        counts = Counter(value for value in text_values if len(value) >= 24)
        repeated = {value: index for index, value in enumerate(sorted(value for value, count in counts.items() if count > 1))}
        if repeated:
            result.append(["lossless_text_dictionary", {"meaning": "text_ref is the exact following shared_text entry, not a semantic summary. This dictionary is local to the current candidate_file."}])
            result.extend(["shared_text", index, value] for value, index in repeated.items())
        if path.suffix.lower() == ".xlsx":
            result.append(["grid_encoding", "Each row gives its exact row number and contiguous spans [start_column, values]. Every value advances one column; gaps start another span. Numeric strings carry numeric, formulas preserve formula/cache. General number format is implicit; all other formats retain a style reference."])
            for record in extracted:
                if record[0] != "row":
                    continue
                spans, previous = [], None
                for cell in record[2]:
                    match = re.fullmatch(r"([A-Z]+)([1-9][0-9]*)", cell[0] or "")
                    if not match or match.group(2) != record[1]:
                        raise CandidateFormatError("cell coordinate does not match row")
                    column = 0
                    for letter in match.group(1):
                        column = column * 26 + ord(letter) - 64
                    value = {"text_ref": repeated[cell[1]]} if isinstance(cell[1], str) and cell[1] in repeated else cell[1]
                    for metadata in cell[2:]:
                        if "type" in metadata:
                            value = {"numeric": value} if metadata["type"] == "n" else {"type": metadata["type"], "value": value}
                        if "number_format_style" in metadata:
                            value = {"value": value, "number_format_style": metadata["number_format_style"]}
                    if previous is not None and column == previous + 1:
                        spans[-1][1].append(value)
                    else:
                        spans.append([match.group(1), [value]])
                    previous = column
                record[2] = spans
        elif path.suffix.lower() == ".docx":
            result.append(["word_encoding", "word_part declares the current XML member. p location concatenates tN/rN/cN nesting tokens plus unique pN within that XML part; current text follows; runs distinguishes effective, inserted, deleted and field_instruction. table_cell carries merge properties or records an empty cell. text_ref is an exact shared_text reference."])
            for record in extracted:
                if record[0] == "p" and isinstance(record[2], str) and record[2] in repeated:
                    record[2] = {"text_ref": repeated[record[2]]}
        result.extend(extracted)
        external = []
        for member in sorted(members):
            if member.endswith(".rels"):
                for rel in _xml(z, member):
                    if rel.attrib.get("TargetMode") == "External":
                        external.append([member, rel.attrib.get("Type", "").rsplit("/", 1)[-1], rel.attrib.get("Target")])
        media = [n for n in sorted(members) if "/media/" in n or "/embeddings/" in n or "/charts/" in n]
        macros = [n for n in sorted(members) if n.lower().endswith("vbaproject.bin")]
        if external or media or macros:
            result.append(["unexecuted_objects", {"external_relationships": external, "media_or_embedded": media, "macros": macros, "note": "No external resource, macro, formula, image or embedded object was executed or rendered. If required business evidence is available only inside these unobserved objects, mark the affected criterion undecidable; do not treat unseen content as absent."}])
    return result


def _candidate_records(workspace):
    results = workspace / "results"
    if not results.exists():
        return [["candidate_inventory", "results directory absent"]]
    if results.is_symlink() or not results.is_dir() or not _within(results, workspace):
        return [["candidate_inventory", "results directory is unsafe or not a directory"]]
    output = []
    for root, dirs, files in os.walk(results, followlinks=False):
        dirs.sort()
        for name in list(dirs):
            path = Path(root) / name
            if path.is_symlink():
                output.append(["candidate_omitted", path.relative_to(workspace).as_posix(), "symlink directory not followed"])
                dirs.remove(name)
        for name in sorted(files):
            path = Path(root) / name
            relative = path.relative_to(workspace).as_posix()
            if path.is_symlink() or not _within(path, results):
                output.append(["candidate_omitted", relative, "unsafe path not followed"])
                continue
            output.append(["candidate_file", relative, {"bytes": path.stat().st_size, "sha256": _digest(path)}])
            suffix = path.suffix.lower()
            if suffix in OFFICE_SUFFIXES:
                try:
                    output.extend(_office(path))
                except (CandidateFormatError, zipfile.BadZipFile, ET.ParseError, KeyError, UnicodeError) as exc:
                    output.append(["candidate_parse_failure", relative, type(exc).__name__, str(exc)])
            elif suffix in TEXT_SUFFIXES:
                if path.stat().st_size > MAX_FILE_BYTES:
                    raise EvaluatorEvidenceError("candidate text exceeds bounded evidence budget: " + relative)
                try:
                    text = path.read_text(encoding="utf-8-sig")
                except UnicodeError:
                    output.append(["candidate_parse_failure", relative, "non-UTF8 text; content unavailable"])
                else:
                    output.extend(["text_line", relative, n, line] for n, line in enumerate(text.splitlines(), 1) if line)
            else:
                output.append(["candidate_unread_format", relative, "Content not extracted. If this file carries required business evidence, the affected criterion is not decidable from this bundle; do not infer missing content."])
    return output or [["candidate_inventory", "results directory contains no files"]]


def _write_evidence(workspace, records):
    lines = [_j(item) + "\n" for item in records]
    total = sum(map(len, lines))
    if total > MAX_TOTAL_TEXT:
        raise EvaluatorEvidenceError("EVALUATOR_EVIDENCE_BUDGET_EXCEEDED: " + str(total) + "; no candidate truncation performed")
    chunks, current = [], ""
    for line in lines:
        if len(line) > MAX_PART_TEXT:
            raise EvaluatorEvidenceError("single evidence record exceeds per-file budget; no truncation performed")
        if len(current) + len(line) > MAX_PART_TEXT:
            chunks.append(current)
            current = ""
        current += line
    if current:
        chunks.append(current)
    destination = workspace / "evaluator_evidence"
    if destination.is_symlink() or (destination.exists() and not destination.is_dir()) or not _within(destination, workspace):
        raise EvaluatorEvidenceError("unsafe reserved evidence directory")
    destination.mkdir(exist_ok=True)
    for old in destination.iterdir():
        if old.is_dir() or old.is_symlink():
            raise EvaluatorEvidenceError("unexpected directory/symlink in reserved evidence directory")
        old.unlink()
    for index, chunk in enumerate(chunks):
        (destination / ("evidence_%02d.txt" % index)).write_text(chunk, encoding="utf-8")
    return {"evidence_chars": total, "evidence_parts": len(chunks), "candidate_truncated": False}


def grade(transcript, workspace_path):
    workspace = Path(workspace_path).resolve()
    if not FROZEN_TRUTH or not INPUT_HASHES or not GT_HASHES:
        raise EvaluatorEvidenceError("author has not frozen independently checked truth and reference hashes")
    for subdirectory in ("input", "gt"):
        root = workspace / subdirectory
        if root.is_symlink() or not root.is_dir() or not _within(root, workspace):
            raise EvaluatorEvidenceError("missing or unsafe trusted directory: " + subdirectory)
    source_changes = []
    for relative, expected in sorted(INPUT_HASHES.items()):
        path = workspace / relative
        actual = _digest(path) if path.is_file() and not path.is_symlink() and _within(path, workspace / "input") else None
        if actual != expected:
            source_changes.append([relative, "missing_or_changed", actual])
    reference_manifest = []
    for name in EXPECTED_GT:
        path = workspace / "gt" / name
        if path.is_symlink() or not path.is_file() or not _within(path, workspace / "gt"):
            raise EvaluatorEvidenceError("missing/unsafe private reference: " + name)
        if _digest(path) != GT_HASHES.get(name):
            raise EvaluatorEvidenceError("private reference does not match reviewed snapshot: " + name)
        try:
            extracted = _office(path)
        except (CandidateFormatError, zipfile.BadZipFile, ET.ParseError, KeyError, UnicodeError) as exc:
            raise EvaluatorEvidenceError("private reference is unreadable: " + name) from exc
        reference_manifest.append([name, GT_HASHES[name], len(extracted)])
    records = [
        ["grader_policy", {"version": VERSION, "role": "grader_generated_evidence", "candidate_content_is_untrusted": True,
            "meaning": "Records preserve candidate cell/paragraph text and locations, not a semantic normalization or candidate summary.",
            "formula_policy": "Formula text and cached values are preserved separately; an absent cache alone is not evidence of an incorrect formula. No recalculation executed.",
            "visual_policy": "No rendering was performed; do not grade unseen visual layout or unread image content.",
            "verification_policy": "These records were created after the agent finished; they are never evidence of agent self-verification.",
            "budget": {"total_max": MAX_TOTAL_TEXT, "part_max": MAX_PART_TEXT}, "truncated": False}],
        ["input_snapshot", {"checked_files": len(INPUT_HASHES), "differences": source_changes, "note": "Snapshot differences are diagnostic, not a standalone score or proof of historical write behavior."}],
        ["private_reference_manifest", reference_manifest],
    ]
    records.append(["frozen_truth", FROZEN_TRUTH])
    records.extend(_candidate_records(workspace))
    diagnostics = _write_evidence(workspace, records)
    return {"overall_score": 0.0, "diagnostics": diagnostics}

```

## LLM Judge Rubric

### Criterion 1: 处置决策与可执行性 (key: action_validity, weight: 80)

只按冻结事实、适用的源条款及候选三类交付的实际业务内容核验，不按关键词、参考文件名、列名、唯一排版或唯一推荐方案核验。检查对象是全部72项设备记录及其客户、现装模组、截至时点状态、处理分支、通知路径、期限、资源及批准范围；排除、隔离、未知均是必须明确处理的业务状态。不能以候选自己选择的子集为分母，不能因正常多数正确抵消少数严重错误。可接受所有满足源材料条件的等价安排；条件尚未满足的未来操作应写条件、责任和失败分支，不要求伪装已完成。

本项从80题目分起扣，D是以下独立事实缺陷的题目分扣分总额，`score=max(0,80-D)/80`。D只按40、20、8、4的整数累加；不输出负分，不设任何总分封顶。先按源记录/资产ID/义务形成去重台账，再计分。相同根因在不同文件、汇总表或后续结论中的自然传播只登记一次、按最严重适用码扣；不同资产由同一公式缺陷导致错误按一个规则根因计，不再加“受影响数量”重复扣。两个独立错误来源或独立应履行义务可以累计；须说明为何一项修复后另一项仍存在。同一根因在本项已扣分时，不再因同一错误的自然传播扣后续证据/一致性项；另有独立缺失或互相矛盾可另扣。完整缺少处置内容为未履行本项全部业务义务，得0，不用虚构40分错误凑数。

**严重性与固定责任码**（裁判必须给出实际资产/客户或义务、候选位置、源依据和适用后果；不能用“质量较差”代替事实）：

- A40-UNSAFE（每独立根因扣40）：对至少一台已明确位于客户侧且现装问题模组的设备，给出无需处置/安全排除/正常持续使用等错误放行，或以未满足生效条件的措施当作已解除风险。在最终处置范围实质漏掉此类设备，且无有效通知和后续行动，同样构成本码的未处置后果。单台明确误放行或实质遗漏即适用，不需达到比例门槛；与同根因A40-NOTIFY只取一次。若只是正确识别风险后安排延期而缺少临时措施，按A20而非重复计A40。
- A40-EXECUTION（每独立根因扣40）：最终推荐计划依赖不存在、不能使用或重复占用的关键资源/已被否决条件，且没有有依据的替代路径，导致至少一台已明确受影响的客户侧设备越过公开硬期限或候选已向客户明确承诺的节点仍不能获得所要求的有效处置。仅为局部排期字段缺失但执行路径未被推翻，不适用本码。
- A40-STRATEGY（每独立根因扣40）：材料已充分支持大部分对象判断，却将整个72项范围统一列为待核而不给有证据的分类行动，或普遍要求全部24台已充分排除的设备再次召回，导致用户无法按已知事实审批和推进专项处置。按一个错误策略根因扣40，不按72项重复扣；零星过度处置按A20-SCOPE。合理保留6台身份未定并对其给出停用、补证和责任节点不适用本码。另：完全没有可供审批的实际客户通知内容、仅说以后拟函，或只有设备分类而无逐设备或可明确继承的实际处置安排，也按本码扣40，不能只在交付角色项丢1分。完整通知内容若已经放在Excel等其他载体，业务内容义务可通过，由D3单独评价Word函稿角色。
- A40-NOTIFY（每独立根因扣40）：已确认客户侧受影响设备因通知对象错误，实际完全没有能够到达当前使用方的有效通知和行动路径，例如只向历史采购主体泛发通知即声称触达完成，且未安排D02转达、最终客户回执或等价有效闭环。若只是路由字段或责任节点局部不全，但路径仍有效，按A20-SCOPE或A08-PLAN；不与同一客户关联错误重复扣。
- A20-SCOPE（每独立根因扣20）：漏掉身份未定/厂内隔离/独立替机等应记录对象、以别台证据错关联对象但尚未造成已证实客户侧风险无处置、把独立旧机与替机合并、丢失转售后的通知责任，或把未确认身份直接排除/无依据放行。若已构成明确客户侧受影响设备误放行，升级A40-UNSAFE而不再扣A20-SCOPE。零星对已充分证明排除的设备发起不必要召回，按该错误根因扣20；覆盖整个范围的策略性回避按A40-STRATEGY，不双扣。
- A20-REMEDIATION（每独立根因扣20）：范围判定正确，但必要的客户处理/返厂隔离/追踪补证/临时措施/最终换件/渠道转送及确认义务被省略、替代为无终点的“后续跟进”或遗漏关键失败分支，致方案不能完整关闭该项风险。相同客户通知缺口导致同一处置义务失败只扣一次。
- A40-AUTHORIZATION（每独立根因扣40）：把已撤回的24个月延保、免费整机升级或全额退款普遍写为适用于全部客户的已批准承诺，产生无授权的全量商务义务。按一项扩大承诺策略根因扣40，不按客户数重复扣；仅作为待另报审批的明确请求且未对外承诺不扣。
- A20-AUTHORIZATION（每独立根因扣20）：通知函稿或执行方案作出缺少有效授权的商务承诺，例如对单一客户承诺已经撤回的24个月延保、全额退款/免费整机升级，或把按串号列明设备批准的临时许可扩到该客户其他设备。须指出具体批准范围、撤回事实与候选承诺；全量普遍扩大按A40-AUTHORIZATION不双扣；待管理会批准的明确请求不是擅自承诺，不要求默认批准。若扩大临时许可已构成明确客户侧受影响设备错误放行，按A40-UNSAFE而不重复扣本码。
- A08-COMPUTE（每独立根因扣8）：存在可核实的实质数值、日期、数量、容量、当前状态或汇总关系错误/遗漏，但尚未造成上述40/20分业务后果；例如已正确保留待核分支而某汇总把待核数混入已证实受影响数。不得因公式缓存为空单独判错，公式正确且可复算可接受。
- A08-PLAN（每独立根因扣8）：有合理主体方案，但明确义务的操作人/前置条件/执行日期/关闭证据/异常处理缺失，使相应局部安排还不能直接执行；若已导致整项义务无法履行，按A20，不双扣。
- A04-LOCAL（每独立根因扣4）：局部文字、非关键辅助计算、次要字段或解释存在有证据的偏差，修正不改变设备分类、处置分支、硬期限、资源可行性和审批结论。仅措辞、表头、行列顺序、编号或外观不同不扣。

状态、身份及截止时点错误只按上述实际后果归档：取消维修不能当已换件；拆件供体与受体分别重放；合格替机不改变旧机隔离义务；有效返工复测可排除；临时措施不能取代最终义务；10月31日事件不能写成10月30日已完成。证据欠缺而正确保留待核、给出责任和补证闭环可以合格；不能把所有设备一律待核或一律召回作为替代分析。

缺少某项资料、提取失败、纯图片证据不可见或轨迹不全属于证据可判定边界，不能擅自补猜。候选完整缺交付属于候选失败；GT缺失/来源不一致/提取预算溢出属于评分器故障。notes至少按key给出扣分码、根因数量、扣分合计及最短可回查位置；不要求输出全部正确对象长清单。

**Score 1.0**: D=0，全部本项业务义务满足。
**Score 0.95**: D=4。
**Score 0.9**: D=8。
**Score 0.85**: D=12。
**Score 0.8**: D=16。
**Score 0.75**: D=20。
**Score 0.7**: D=24。
**Score 0.65**: D=28。
**Score 0.6**: D=32。
**Score 0.55**: D=36。
**Score 0.5**: D=40。
**Score 0.45**: D=44。
**Score 0.4**: D=48。
**Score 0.35**: D=52。
**Score 0.3**: D=56。
**Score 0.25**: D=60。
**Score 0.2**: D=64。
**Score 0.15**: D=68。
**Score 0.1**: D=72。
**Score 0.05**: D=76。
**Score 0.0**: D≥80或完全缺少本项业务处置内容。

### Criterion 2: 关键事实的证据链 (key: evidence_traceability, weight: 8)

固定四条链，每条2题目分，完整通过数n，`score=n/4`。按语义、源记录定位和关联是否可复查判，接受文件+表/页/记录ID等可唯一找到事实的等价定位，无须超链接或固定“来源”列。四条为：(E1)设备—现装模组—维修/拆装/撤销/复测记录—当前风险状态；(E2)设备—当前客户/转售渠道/独立替机—具体通知对象与回执责任；(E3)处置方式—有效合同/专项要求—资源及时间条件；(E4)临时措施/借机/延保批准—适用设备—部分撤回—函稿承诺。每条以本题全部适用对象/义务为范围，孤立举一个正确例子不代表全链通过；四条分别评，某条不通过只扣其2分。

通过要求候选提供足以从结论回查到原始材料和对象的定位，且关联属于正确对象/有效版本；不要求逐字复刻GT，也不因同一已正确定位证据被共享使用而扣分。若唯一缺陷已经在action_validity按相同事实根因扣分，该缺陷不重复扣本项；仍可根据独立无定位、错对象来源或证据链断裂评其他链。单纯“详见附件”且不能找到对应记录不算有效来源。源材料缺失/不可读造成不可判定须写明，不能假装来源不存在。

**Score 1.0**: 四条链均通过。
**Score 0.75**: 三条链通过。
**Score 0.5**: 两条链通过。
**Score 0.25**: 一条链通过。
**Score 0.0**: 无链通过，或没有可核验的候选证据链。

### Criterion 3: 三份材料间的独立一致性 (key: cross_document_consistency, weight: 4)

固定四组关系，每组1题目分，合格组数n，`score=n/4`：(X1)设备范围/数量/当前客户；(X2)处置分类/完成与待办状态/通知结论；(X3)执行日期/资源安排/条件和失败分支；(X4)临时措施/商务授权/管理会待拍板事项。只看这些信息在候选Excel、Word、PPT之间是否相容，允许不同粒度、摘要省略和同义表达；摘要未重复所有明细不算矛盾。共享的同一业务错误已在核心项扣分，不再因为三份材料都复制同一错误扣本项。仅当同一对象同一口径被独立写成互不相容的事实，或摘要遗漏限定条件而改成无条件结论时扣相应组；不能用“不够美观/标题不一致”扣分。若某组必要交付缺失，无跨文件关系可核验，该组不通过；需明确这是独立的交付一致性义务缺失。

**Score 1.0**: 四组关系均相容且可核验。
**Score 0.75**: 三组通过。
**Score 0.5**: 两组通过。
**Score 0.25**: 一组通过。
**Score 0.0**: 无组通过。

### Criterion 4: 交付角色与可用内容 (key: delivery_roles, weight: 4)

按真实文件内容而非文件名/Sheet/标题/页数/固定表头判定以下四个独立角色，每个1题目分，覆盖数n，`score=n/4`：(D1)Excel实际列出设备、客户和可追踪处理安排；(D2)Word有能指导分工与推进的执行方案；(D3)Word有供审核的客户通知函稿，明确适用对象和必要行动，不只是“将拟函”的承诺；(D4)PPT能呈现推荐和需审批/拍板事项。业务内容与载体角色是可分离的独立义务：完整正确通知内容在Excel中而Word没有函稿，核心通知内容可通过但D3不通过；Word已有实际函稿而设备动作错误，D3可通过而核心扣分；所有载体均无任何通知实稿时，核心因业务内容缺失扣40，D3因Word函稿角色缺失另丢1分，其他项全满合计59，不再因同一缺失的自然传播额外扣证据/一致性。文件可合并、重命名或合理拆分，但需保持用户要求的Excel/Word/PPT实际可编辑Office格式和相应作用；表头/标题和同义业务表达由LLM认定。可解析包只是内容证据，不代替语义角色。候选某数字错误由核心评分负责，不因相同数字错误再次判该角色不存在；空壳、纯占位、缺实际内容则不通过。未渲染时不评价美观、字体、图形裁切或像素布局。

**Score 1.0**: 四个角色全部有真实内容。
**Score 0.75**: 三个角色有真实内容。
**Score 0.5**: 两个角色有真实内容。
**Score 0.25**: 一个角色有真实内容。
**Score 0.0**: 没有对应真实交付，或均为空壳/占位。

### Criterion 5: 可观察的交付核对 (key: observable_verification, weight: 4)

仅使用同次执行公开轨迹中实际对候选交付进行的读取、重算、关系比较及其结果，不使用隐藏思考、只写“已核对”的声明或评分器生成的evaluator_evidence。四个核对对象各1题目分：(V1)从原始材料复核设备/客户对象覆盖与截至时点状态；(V2)从适用条款与审批记录复核处置依据、临时措施和函稿承诺权限；(V3)从兼容矩阵、实际可用库存、占用和确认到货复核履约安排；(V4)核对三份材料中的范围、数量、承诺和未决事项是否一致。允许一次有效检查覆盖多个对象，也接受生成过程中已完成且此后相关内容未变的检查，不指定工具名/步骤顺序/必须末尾重新打开。

评分依据是已发生的检查是否针对实际最终交付，且方法和结果足以支持判断；打印文件存在/字节数、写入成功、计划中的检查或生成器断言本身都不能替代内容核对。修订后只需重核受影响部分。完整轨迹能明确确认未执行相应核对时，该单元0；记录缺失/压缩/截断导致不能判定时，应在notes写“不可判定”及缺证据，数值占位不能作为有效能力分。候选内容正确不能反推已核验；候选仍有错误不必然证明没有执行过有效但范围有限的核对，按真实覆盖计。

**Score 1.0**: 四个对象均有足够的公开核对证据。
**Score 0.75**: 三个对象有足够证据，余项可确认未完成。
**Score 0.5**: 两个对象有足够证据，余项可确认未完成。
**Score 0.25**: 一个对象有足够证据，余项可确认未完成。
**Score 0.0**: 完整证据确认未覆盖上述对象；若必要轨迹不可得，只是接口占位，notes须明确不可判定，禁止报告正式能力总分。


## Workspace Path

workspace/general_e2e/02_Office/task_013_customer_remediation_pack

## Skills

## Env

## Warmup
