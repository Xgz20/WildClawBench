---
id: general_hard_research_verification_task_001_open_mineral_fact_discovery
name: 开放搜索：矿产年报版本与指标口径
category: research_verification
timeout_seconds: 900
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L2
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
    - path: results/findings.xlsx
      role: candidate_deliverable
    - path: results/source_ledger.json
      role: candidate_deliverable
    - path: results/answer.md
      role: candidate_deliverable
scoring_runtime:
  office: true
  research_sources: true
dataset_report: {"category": "research_verification", "category_name": "研究检索与证据核验", "category_order": 2, "checkpoint_capabilities": {"automated.citation_resolution": ["retrieval_verification"], "automated.protected_delivery": ["verification_delivery"], "automated.record_contract": ["verification_delivery"], "automated.time_and_scope": ["retrieval_verification"], "llm_judge.bounded_conclusions": ["reasoning_planning"], "llm_judge.coverage_and_independence": ["retrieval_verification", "reasoning_planning"], "llm_judge.factual_support": ["retrieval_verification"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-challenge"}
---

# 开放搜索：矿产年报版本与指标口径

## Prompt

请自主检索并核验USGS稀土年度摘要中的世界矿山产量与储量，交付可复算、可回查的比较结果。

只读取本地输入 /tmp_workspace/research_request.md、/tmp_workspace/as_of.json 和 /tmp_workspace/answer_contract.json；按三份材料完成。本题所指是按年发布、包含World Mine Production and Reserves表的稀土摘要，要求找到截至2026-09-30（Asia/Shanghai，含当日）的最新年度版和上一年度版，采用各版在截止日以前最新公开修订。题面不给答案网址或来源候选名单，也不指定首条搜索Query、语言或工具名称。可使用可用公开搜索、浏览、站内导航及正文读取方式；不得登录真实账号、发送消息或使用真实付费接口。

分别核对储量与每版最新产量统计年的已公布数值国家行前三名（不把Other/World当国家、不把NA当0），说明统计年、REO单位、脚注与未知。计算中国/世界占比，保留原文上下界与约数；储量年未明确时不猜。对两版共用产量统计年，逐行对照所有国家、Other及World，包括未变行，计算新版减旧版的修订差额，比较同年重述前后中国占比；世界总计使用报告原数，不用国家行求和替代。说明所用章节的版本更正及可比性边界，不以当前搜索排序、网页Updated或HTTP时间替代首次发布/修订记录，不编造逐国修订原因。

将以下三份实际交付写入/tmp_workspace/results，每份不超过5MiB：
1. findings.xlsx：原生可编辑、自包含且核心表可见；按answer_contract.json的versions、rankings、shares、revisions四类语义表交付，允许不同Sheet名/坐标/行列顺序/分表合表、清楚中文别名及辅助列。各对象唯一。版本表2条、排名表两版各两指标的前三名、占比表含两版两指标及新版对共用年的产量比、修订表覆盖共用年的全部原表行。静态正确表或实际可重算公式均接受，不要求公式数量或动态模型；不带宏/外部数据连接。比例用0至1数值并保留分子/分母与关系；正常百分比两位小数舍入允许0.00005比例绝对误差（0.005个百分点），不改变界限方向。空白/未知与真实0区分。
2. source_ledger.json：按answer_contract.json记录真实searches、sources和limitations。保留发现候选与实际读取状态、来源ID/URL/访问时间/身份；每个citation含唯一ID、原文quote及实际locator，PDF页与印刷页分开，HTML/文本给实际标题或行段。表格和文字通过citation ID对应。未读、只见摘要、不可用、单源/转载与无法核实之处均明确，不把候选自写快照当独立证据，不虚构检索调用或已读全文。
3. answer.md：主要结论、算式/版本选择、同年修订与跨年变化的区别、范围/脚注、未知与来源限制；和工作簿一致，并引用稳定citation ID。

原输入保持字节不变、不删除/覆盖；所有新交付在results内。不要访问GT或评分材料。此题只需可提取文本的资料与本地文件读写，不要求图像理解。

## Expected Behavior

自主发现并逐项核验截止日前最新年度/修订及上一版，以独立原文支持两指标排名、占比界限和共同统计年逐行重述，保留未知和单源边界；L2为设计预估。

## Grading Criteria

### Automated group

- [ ] `record_contract`: 四类可见原生表和检索/来源账本具必要字段；未知按题意保留，不以文件存在替代事实。
- [ ] `time_and_scope`: 与独立官方元数据oracle核两年度版的首次发布/截止日前最新修订、产量统计年、储量年未知与REO单位；不以候选自填日期自证。
- [ ] `citation_resolution`: 引用ID、独立取得的真实来源原字节、完整投影、实际页/段定位及原文片段可对应。机械解析不证明原文支持主张；池外有效来源按相同标准判断，不按URL名单。
- [ ] `protected_delivery`: 原输入SHA未改、三交付可读、核心表可见且跨表比例/差额可复算。若使用公式，须清除缓存后实际Office重算；静态正确表与合理舍入同样接受。

### Judge group

- [ ] `factual_support`: 实际读取候选原生XLSX/可信原生投影、answer.md、source_ledger及评分侧独立取得的来源正文和元数据，逐项核两年度版与最新修订、两指标前三名/数值/REO单位、储量统计年未知、世界总计和中国占比、共同统计年逐行修订。将带脚注的数字、NA、真实0、资源/储量、不同储量定义分开。不能只看引用域名/URL或候选自己写的日期/源快照；quote存在不等于支持主张。对参考池外的正文、DOI/等价页面或完整卷用同一事实标准，不能因不在参考URL列表而扣分。所需来源未独立取得、历史身份不能核实或提供方输入缺关键原文时记unresolved/评测异常，不补能力零分。
- [ ] `coverage_and_independence`: 依据交付和可观测完整轨迹核是否自主发现两年度资料、选择截止日前最新修订，并覆盖两个指标、所有共用年国家/Other/World行及版本历史。不要把同一工作不同URL、官方页面和章PDF算成独立统计机构；摘要、正文、转载、同源与独立支持分清。允许不同搜索/导航方式、不同合格来源和诚实的单源边界。轨迹缺失时保留unknown，不能凭工具次数或只见最终答案推定未搜索；完整轨迹明确未完成必要检索时按实际缺口判断。
- [ ] `bounded_conclusions`: 核结论区分报告年、最新产量统计年、未明确的储量年、同年重述与跨年变化；世界储量为下限时只能得占比上界，世界产量用报告总数而非国家求和替代。版本修订不自行推为实际储量消耗或因果。原文数字/脚注/说明互有差异时据表列清事实和待核项，不补造原因；原始资料取得晚于截止日时说明官方历史记录与当前字节的证据边界。

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
        "overall_score": (0.2 * scores["record_contract"] + 0.25 * scores["time_and_scope"]
                          + 0.4 * scores["citation_resolution"] + 0.15 * scores["protected_delivery"]),
    }
```

## LLM Judge Rubric

### Criterion 1: 事实与正文支持 (key: factual_support, weight: 0.5)

判据：实际读取候选原生XLSX/可信原生投影、answer.md、source_ledger及评分侧独立取得的来源正文和元数据，逐项核两年度版与最新修订、两指标前三名/数值/REO单位、储量统计年未知、世界总计和中国占比、共同统计年逐行修订。将带脚注的数字、NA、真实0、资源/储量、不同储量定义分开。不能只看引用域名/URL或候选自己写的日期/源快照；quote存在不等于支持主张。对参考池外的正文、DOI/等价页面或完整卷用同一事实标准，不能因不在参考URL列表而扣分。所需来源未独立取得、历史身份不能核实或提供方输入缺关键原文时记unresolved/评测异常，不补能力零分。

**Score 1.0**: 关键版本、范围、数值、排名与同年修订均有实际原文支持；上下界和未知处理正确，源脚注没有造成数量或口径误读。

**Score 0.75**: 主要版本/指标/统计年/数值及界限均正确，只有少量不改变结论的非关键定位或脚注说明缺口；明确列出受影响对象和证据。

**Score 0.5**: 能从实际正文支持主要分支，但一个版本、指标或同年修订存在关键遗漏/错数；不得用结构正确或漂亮表格抵消事实错误。

**Score 0.25**: 只有少数可信事实，多个关键版本、统计年、单位、数值、NA/0或界限被误读/无依据；具体指出被原文反驳的主张。

**Score 0.0**: 必要评分材料齐全，但核心事实核验未完成、关键结论整体被正文反驳或捏造来源/已读全文。评分侧缺来源本身不使用此档替代异常。

### Criterion 2: 检索覆盖与来源强度 (key: coverage_and_independence, weight: 0.3)

判据：依据交付和可观测完整轨迹核是否自主发现两年度资料、选择截止日前最新修订，并覆盖两个指标、所有共用年国家/Other/World行及版本历史。不要把同一工作不同URL、官方页面和章PDF算成独立统计机构；摘要、正文、转载、同源与独立支持分清。允许不同搜索/导航方式、不同合格来源和诚实的单源边界。轨迹缺失时保留unknown，不能凭工具次数或只见最终答案推定未搜索；完整轨迹明确未完成必要检索时按实际缺口判断。

**Score 1.0**: 两版和最新修订选择有依据；全部必要分支覆盖、同年18行核对完整，真实检索/读取可追溯，来源家族和单源限制说明准确。

**Score 0.5**: 覆盖主范围并有可核实发现/读源过程，但漏非关键分支或部分逐行修订；没有用转载/重复URL冒充独立支持或虚构过程。

**Score 0.0**: 核心年度/指标/同年修订或必要发现缺失，主要依赖不合格摘要或重复来源凑数，或在必要证据齐全时可证实捏造检索过程。

### Criterion 3: 口径与可复核结论 (key: bounded_conclusions, weight: 0.2)

判据：核结论区分报告年、最新产量统计年、未明确的储量年、同年重述与跨年变化；世界储量为下限时只能得占比上界，世界产量用报告总数而非国家求和替代。版本修订不自行推为实际储量消耗或因果。原文数字/脚注/说明互有差异时据表列清事实和待核项，不补造原因；原始资料取得晚于截止日时说明官方历史记录与当前字节的证据边界。

**Score 1.0**: 算式、口径、界限、同源/时点与未知均清楚，原生工作簿和文字一致，同事可沿citation ID回查；没有超出证据的增长、因果或精确占比主张。

**Score 0.5**: 主结论有依据且可复核，但漏一项非关键可比性、精度或时点说明，没有反向界限或无条件外推。

**Score 0.0**: 主要解释混淆报告/统计年份或同年/跨年，丢失上下界、NA/0或以国家和替世界原数，并据此作出被证据反驳的主要结论；或核心交接矛盾不可复核。

## Workspace Path

```
workspace/general/challenge/research_verification/general_hard_research_verification_task_001_open_mineral_fact_discovery
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- USGS官方表与修订历史独立获取；两名隔离模型研究者各自主发现/读取，120字段一致、另35项SQLite/Decimal核算；模型复核非人工专家，无正式候选语义分。
- 题面不含答案URL；参考池不是唯一合法来源。所有来源身份、正文支持、检索诚实性与未知解释由独立Judge核验，自动组件1.0不能当混合总分。
- 评分须score-general-e2e0.24.0及兼容入口：prepare后collect-research-sources独立取得候选实际引用的公共来源，按GT policy冻结只读source bundle/lock；run-rules与prepare-semantics共同使用，不能修改原始GT或候选。缺来源包、取回/提取/预算/身份供证不足为unresolved/评测异常，不补能力零分。
- 评分source bundle公共URL限定逐跳global DNS钉住、TLS/原字节/提取回执；不以HTTP头证明历史首次发布，正文与历史记录需另外判断。仅代理可达的网络、动态/扫描内容或非UTF-8未支持的来源需按预检/供证异常处理。
- 自动内权重.2/.25/.4/.15，外层自动.4/语义.6，语义.5/.3/.2；结构与引用可解析不证明事实语义。
- 作者参考/静态/受管Worker验收均不代表候选Harness表现、实测L2或组合区分度；900为元数据，不作为候选总执行截止或能力扣分。
