---
id: 03_Research_Verification_task_005_open_long_horizon_agent_research
name: 开放深研：长程任务Agent能力与建设取舍
category: research_verification
timeout_seconds: 900
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L4
grading_type: hybrid
grading_weights:
  automated: 0.4
  llm_judge: 0.6
tags:
  - custom
  - general-hard
  - general-challenge
judge_evidence:
  required:
    - path: results/capability_matrix.xlsx
      role: candidate_deliverable
    - path: results/evidence_ledger.json
      role: candidate_deliverable
    - path: results/research_report.docx
      role: candidate_deliverable
    - path: results/coverage.json
      role: candidate_deliverable
scoring_runtime:
  office: true
  research_sources: true
dataset_report: {"category": "research_verification", "category_name": "研究检索与证据核验", "category_order": 2, "checkpoint_capabilities": {"automated.citation_resolution": ["retrieval_verification"], "automated.protected_delivery": ["verification_delivery"], "automated.record_contract": ["verification_delivery"], "automated.time_and_scope": ["retrieval_verification"], "llm_judge.bounded_conclusions": ["reasoning_planning"], "llm_judge.coverage_and_independence": ["retrieval_verification", "reasoning_planning"], "llm_judge.factual_support": ["retrieval_verification"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-challenge"}
---

# 开放深研：长程任务Agent能力与建设取舍

## Prompt

请读取三份只读输入：/tmp_workspace/research_brief.md、/tmp_workspace/business_constraints.md、/tmp_workspace/scope.json，按其中完整公开记录契约完成研究。

# 长程任务Agent能力与建设取舍

请为一个已有本地文件Agent的团队研究：怎样支持需要跨日继续的文档、数据和软件工作流，同时保留权限边界和可核验的交付。研究截至2026-09-30，按Asia/Shanghai解释日期。研究范围和公开记录结构见另外两份输入。不要实施系统、调用真实业务或复现实验。

从主题自行建立检索与筛选方案，发现至少5个代表产品/框架和至少5个论文或benchmark研究工作，不提供对象、论文、域名、URL或首条query名单。选择应能解释本业务需要的规划、记忆、工具、恢复和交付验证五维。不要求某个搜索引擎、语言或工具名；可以组合搜索、站内导航、浏览和fetch。

不同版本或部署方式不能充当多个同组实体；同一贡献的benchmark官网及介绍论文、同一论文预印本/期刊版及修订，不能重复凑研究工作数。一个框架可有相关论文，但两组的身份、选择理由和实际阅读范围仍分别核验。至少5个研究工作须有与所用主张相关的完整可读论文正文或完整官方benchmark协议/主文档。benchmark文档可支持其明确的接口和协议，不冒充已经读过未取得的论文实验。摘要只支持它实际包含的事实。

最低数量指身份、主题及所用版本/报告时点已有依据的合格对象。尚不能确认身份或截止前依据的对象可以保留为unknown/pending并说明，但不用于凑各组最低5个。某个能力格为unknown本身不排除一个已有身份/时点依据的代表对象；不要为了凑满矩阵把未知写成已有能力。五维覆盖评价实际研究与证据，不要求每个框架都拥有五种能力。

形成恰好12项关键结论，覆盖五维并追溯其依据、反驳或限定关系。不要把已有checkpoint、聊天历史、可调用工具、角色分工或文档宣称，直接写成可靠跨日恢复、外部副作用只发生一次或交付必然正确。版本文档/静态代码、官方宣称、作者实验、独立实验和你实际观察的运行须分清；本题不要求制造新的运行实验。研究对象的实际能力与研究中的证据强度也要分开。

对数字保留任务、数据/划分、指标方向、样本/分母、预算、权限、硬件、模型与版本等影响解释的条件。无共同可比条件时比较适用范围和证据强弱，不把不同榜单最高分直接排成统一名次。不要求填满性能数字，不知道可以unknown；unknown要说明实际检查范围和原因，不能把未找到当不存在。

## 交付

仅写入`/tmp_workspace/results/`，每文件不超过5MiB：

1. `capability_matrix.xlsx`：原生可见、可编辑、自包含的代表产品/框架能力矩阵。表达entity_id、名称、选择理由、所读版本、时点依据及五维能力/条件/证据层级，并与JSON关联；可另附论文或benchmark索引。允许合理中文字段、不同Sheet/行列布局、重排、分表/合表、转置和普通来源超链接；静态值接受，使用公式时须可实际重算，不用宏或外部数据连接。不要用截图或单格巨大JSON代替核心矩阵。
2. `evidence_ledger.json`：按`business_constraints.md`记录实际检索、实体、研究工作、12项结论、来源和引文。实际访问或引用的来源最多60条，不截断实际引文，不用重复URL凑独立来源。
3. `research_report.docx`：原生可编辑的比较报告，解释代表选择、五维能力/条件、12项结论、可比性、反例和未决项，提出受约束的建设优先级和可验证假设。实际做过的过程与未来验收建议分别写，不把计划当完成。
4. `coverage.json`：实际研究范围、分支覆盖、真实去重/排除/未决，以及优先级的结构化记录；不冒称穷尽互联网或系统综述。允许实际无排除、无合并、无未决，不为展示流程编造记录。

所有新交付写入results，不以聊天代交。三份输入保持原字节，不修改、删除或覆盖；不读取GT或未提供私有材料。不登录真实账号、不发送消息、不付费、不执行真实业务写入。无需下载大型实验数据、部署框架、训练模型或读图像像素。DOCX/XLSX的格式本身不构成视觉理解要求。

来源应保留实际失败、单源、冲突和未知。HTTP200、空壳、验证码、摘要或部分下载不证明正文可读。评分侧会独立获取和锁定实际引用材料，候选自写快照不能自行成为独立真值；来源获取故障和候选错误分开。已验证旧快照若被评分流程明确复用，要保留原GET时间及复用事实，不写成此次新访问。参考池非穷尽，池外合格对象按同一证据标准核验。

## Expected Behavior

自主发现并核对至少5个产品/框架和5个研究工作，保留五维能力/版本日期、12结论及真实证据，形成原生四产物及有预算/依赖/反例的建设建议。难度为设计预估。

## Grading Criteria

### Automated group

- [ ] `record_contract`: 公开JSON形态、ID图、五维能力矩阵和原生报告的结构/跨文件关联；支持等价中文表头、重排、分表/合表、转置及静态值，不按固定模板评分。
- [ ] `time_and_scope`: 实际原件身份/日期/版本字面绑定、日期精度及时区截止、最低5实体/5研究工作声明和12结论/五维覆盖、1至3优先级预算DAG；语义资格及真实阅读交Judge。内部.40/.25/.20/.15。
- [ ] `citation_resolution`: RFC6901块/叶/多目标指针、原件GET或真实复用谱系、实际quote/locator及状态/数字形态，固定最低能力/结论/元数据机会避免引用padding稀释。机械通过不等于语义支持。内部.20/.20/.40/.20。
- [ ] `protected_delivery`: 三输入原字节保护、四交付齐全且原生可解析/可编辑，公式须真实可信重算；仅对应机会失分。

### Judge group

- [ ] `factual_support`: 对开放深研：长程任务Agent能力与建设取舍的关键事实、数值、版本和判断，逐项独立核验正文/元数据是否真实支持；对池外来源按同一标准判断。 必须读取实际四交付、独立原件和所读版本，核日期角色、五维事实、12结论及数字条件；不以quote匹配代替支持。 缺必要独立来源或轨迹证据时记录评测异常/未决，不补能力零分。
- [ ] `coverage_and_independence`: 满足本题实体、主题、时间、版本去重与资料筛选要求；分清一手、转载、独立支持及可比性，不机械按URL数量计覆盖。 按绑定完整轨迹核自主发现/真实阅读；至少5合格独立产品框架、5完整相关研究正文/协议，排除同工作版本、未确认日期身份凑数。 缺必要独立来源或轨迹证据时记录评测异常/未决，不补能力零分。
- [ ] `bounded_conclusions`: 趋势、选型与建设建议限定在材料可证明范围，区分事实、官方宣称、静态实现、实验和推断；允许有依据的不同结论。 分清官方宣称/静态实现/作者或独立实验与运行观察；不用不同预算榜单作统一排名，优先级上界总计不超60人日，允许有据不同排序并需可证伪验收。 缺必要独立来源或轨迹证据时记录评测异常/未决，不补能力零分。

## Automated Checks

```python
def grade(**kwargs) -> dict:
    from pathlib import Path
    import runpy
    root = Path(kwargs.get("workspace_path") or "/tmp_workspace")
    scores = runpy.run_path(str(root / "gt/grader.py"))["grade"](
        transcript=kwargs.get("transcript") or [], workspace_path=str(root)
    )
    return {
        "record_contract": scores["record_contract"],
        "time_and_scope": scores["time_and_scope"],
        "citation_resolution": scores["citation_resolution"],
        "protected_delivery": scores["protected_delivery"],
        "overall_score": (0.20 * scores["record_contract"] + 0.25 * scores["time_and_scope"]
                          + 0.40 * scores["citation_resolution"] + 0.15 * scores["protected_delivery"]),
    }
```

## LLM Judge Rubric

### Criterion 1: 事实与版本支持 (key: factual_support, weight: 0.5)

判据：对开放深研：长程任务Agent能力与建设取舍的关键事实、数值、版本和判断，逐项独立核验正文/元数据是否真实支持；对池外来源按同一标准判断。 必须读取实际四交付、独立原件和所读版本，核日期角色、五维事实、12结论及数字条件；不以quote匹配代替支持。 缺必要独立来源或轨迹证据时记录评测异常/未决，不补能力零分。

**Score 1.0**: 关键事实均被可追溯原文支持，时空口径正确，无捏造来源或实验结果。

**Score 0.5**: 主结论成立但存在非关键字段或支撑缺失，未将未知说成已证实。

**Score 0.0**: 关键结论与原文冲突、捏造出处/事件/全文结果，或没有完成核心事实核验。

### Criterion 2: 真实检索与独立覆盖 (key: coverage_and_independence, weight: 0.3)

判据：满足本题实体、主题、时间、版本去重与资料筛选要求；分清一手、转载、独立支持及可比性，不机械按URL数量计覆盖。 按绑定完整轨迹核自主发现/真实阅读；至少5合格独立产品框架、5完整相关研究正文/协议，排除同工作版本、未确认日期身份凑数。 缺必要独立来源或轨迹证据时记录评测异常/未决，不补能力零分。

**Score 1.0**: 所有关键分支有合格覆盖，重复/版本/转载已合并，独立性或无法交叉验证的边界说明准确。

**Score 0.5**: 满足主范围但漏一个非关键分支，未用不合格材料凑数。

**Score 0.0**: 核心分支缺失、反复转载或同一工作版本冒充多项独立结果，无法支撑主要比较。

### Criterion 3: 能力边界与建设取舍 (key: bounded_conclusions, weight: 0.2)

判据：趋势、选型与建设建议限定在材料可证明范围，区分事实、官方宣称、静态实现、实验和推断；允许有依据的不同结论。 分清官方宣称/静态实现/作者或独立实验与运行观察；不用不同预算榜单作统一排名，优先级上界总计不超60人日，允许有据不同排序并需可证伪验收。 缺必要独立来源或轨迹证据时记录评测异常/未决，不补能力零分。

**Score 1.0**: 取舍可追溯且限制清楚，不把缺证据当否定或运行保证。

**Score 0.5**: 主要建议有依据，但漏一项非关键条件或后续验证。

**Score 0.0**: 主要建议与证据矛盾、无条件外推，或用不可比排名作关键依据。

## Workspace Path

```
workspace/general/challenge/03_Research_Verification/03_Research_Verification_task_005_open_long_horizon_agent_research
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- 参考池非穷尽；源先行模型独立发现及给定URL复核与非盲调和分别留痕，非人工专家。禁止把参考名单作为评分白名单。
- 自动.4/语义.6；自动四键.20/.25/.40/.15。自动仅核结构、原件绑定与算术，实际搜索/完整阅读、事实支持、证据强度及代表性由独立Judge核验。
- 显式受信本地HTTP CONNECT需score0.28.0/core0.15.3；默认direct v1不变。每跳公网DNS/固定CONNECT与Host/SNI/TLS，proxy_peer不冒充源站socket；已验旧源复用保留原GET时间/原响应。缺源/GT/运行时为评测异常。
- 新作者修订在消费者与格式兼容层修改4文件；原18GT及既有失败/部分分数版本完整保留，科学8、其余14GT、三输入与四参考原字节保持。PDF按明确物理页与实际唯一引文核验；未知版本日期null加原因不编造时间或CID。
- 作者自动控制/独立ZIP验收不是Harness、语义Judge、最终hybrid成绩或难度/区分度校准；900只为任务元数据。
