---
id: general_hard_research_verification_task_004_site_search_literature_screening
name: 站点限定搜索：空间组学AI文献发现与筛选
category: research_verification
timeout_seconds: 900
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L3
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
    - path: results/screening.xlsx
      role: candidate_deliverable
    - path: results/protocol.docx
      role: candidate_deliverable
    - path: results/evidence_matrix.json
      role: candidate_deliverable
scoring_runtime:
  office: true
  research_sources: true
dataset_report: {"category": "research_verification", "category_name": "研究检索与证据核验", "category_order": 2, "checkpoint_capabilities": {"automated.citation_resolution": ["retrieval_verification"], "automated.protected_delivery": ["verification_delivery"], "automated.record_contract": ["verification_delivery"], "automated.time_and_scope": ["retrieval_verification"], "llm_judge.bounded_conclusions": ["reasoning_planning"], "llm_judge.coverage_and_independence": ["retrieval_verification", "reasoning_planning"], "llm_judge.factual_support": ["retrieval_verification"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-challenge"}
---

# 站点限定搜索：空间组学AI文献发现与筛选

## Prompt

请为研究团队自行在arXiv和PubMed发现空间组学AI/统计学习方法文献，形成至少6个经作品身份去重的候选工作，实际阅读并纳入至少4个符合范围的公开全文。研究窗口为2021-01-01至2026-09-30，Asia/Shanghai；不提供论文名单、编号、URL或首条query。不要求所有空间组学模态都有覆盖，也不要求两个平台各贡献固定纳入数，但应真实尝试两个平台。

只读本地三输入：/tmp_workspace/research_question.md、/tmp_workspace/inclusion_rules.md、/tmp_workspace/source_policy.md。以它们的公开契约为准；可用站内搜索、搜索工具、浏览器或等效导航，从发现记录跟随公开DOI、出版者、官方全文库及只读元数据。记录实际query/导航、所得线索与不可用情况，不把计划或非空声明当完成过程。

交付到/tmp_workspace/results，单份不超过5MiB：
1. screening.xlsx：原生可见、可编辑的工作筛选与报告版本台账，至少表达work_id、record_id、题名/可识别描述、所读版本、decision及具体理由、报告日期/口径与来源，按ID对应JSON。允许合理中文字段、重排、分表/合表、转置或来源超链接；静态值可接受，公式须可实际重算，不用宏、外部数据连接、图片或单格巨大JSON代替核心表格。
2. protocol.docx：原生可编辑的实际检索和筛选过程、标准、作品/版本去重依据、七项流程计数、范围和限制。只统计真实保留记录，不冒称穷尽搜索或系统综述；不为凑数制造排除项或失败。
3. evidence_matrix.json：按source_policy.md公开结构保存searches、records、works、sources、flow。每个include工作说明研究任务、输入数据、方法、评估条件、实际结果、局限六类内容，分documented/unknown/inference；未知要说明已查范围和原因，推断交代理据。实验数字保留指标、值、单位/无量纲、方向和条件；影响比较的基线、数据划分、参考、先验、硬件等如实披露，不补造精度或误差类型。

区分工作、报告与所读版本：同工作预印本/期刊版或不同修订不凑成多篇。arXiv报告按官方v1 Submitted平台提交口径判窗，不将其称为已证明的首次公众可见；所读vN时间另记，修订不能刷新v1资格。期刊优先first_online，确实不可核时才明示issue_only及online未知；其它预印本按官方原始posted/submitted，不能从DOI/URL日期、收稿、索引、仓储或检索时间猜首发。保留真实日期精度、原时区时间及上海换算；只有年月或年的完整区间在窗内才能确认，否则按规则pending。截止后新增内容不得用于截止前比较。

至少6个真实独立工作、至少4个合格全文；允许实际全纳入、D/U/E/P为0以及超过最低数。保留报告归属，并核对R=D+U+W和W=I+E+P；HTML/PDF载体、搜索操作与来源URL都不当作新工作。三产物的身份、所选报告、结论和计数须一致。

来源账本最多60条。每个实际引文保留唯一citation_id、单一真实来源短引、可提取定位和supports_fields JSON Pointer；块/叶及多目标关联可等价表达，无需重复CID全集或双向record_ids。HTTP200、搜索摘要、登录/验证码或部分下载不证明全文已读；摘要只支持其明确事实。实际不可读、单源、冲突与未知如实说明。公开HTML、文本PDF或身份明确的等价全文都可；元数据不能冒全文。参考池非穷尽，池外文献按同一标准判断，不以题名/域名白名单评分。

比较任务、输入要求和证据条件，不将不同研究的最大分数、单片/汇总、版本、先验或硬件直接拼成排行榜；作者报告结果不称为你已复现。无需读图像像素、下载大型实验数据、执行作者代码或重现实验。

三输入保持原字节，不删除或覆盖；所有新交付写入results，不以聊天代交。不读取GT/评分说明，不登录真实账号、不付费、不发送消息、不调用真实业务或付费API。评分侧独立来源包不由候选创建；来源获取缺失与候选错误分开。完成前核对三交付事实、关系、日期、计数和引用一致。

## Expected Behavior

自主尝试arXiv/PubMed并以真实身份/日期版本形成至少6候选工作、4合格全文；原生三产物、六类证据与计数可追溯，unknown/推断及可比性有界。L3为设计预估。

## Grading Criteria

### Automated group

- [ ] `record_contract`: 公开JSON形态、报告/工作ID图与六类内容、原生筛选台账和协议结构/对应关系；按声明槽且保留最小机会数，不按模板、字数或Sheet坐标评分。
- [ ] `time_and_scope`: 独立原件元数据的身份/日期/版本字面绑定，真实精度、时区、日历与窗口算术，报告归属及七数计数/6候选4纳入最低声明；两平台只核声明记录及跨文件关联，实际搜索/阅读交Judge。内部.30/.25/.30/.15。
- [ ] `citation_resolution`: RFC6901块/叶/多目标指针、独立原件与GET/复用回执、真实quote/locator及六类状态/数字形态；最少24类机会且加真引用不稀释假引用。机械通过不等于语义支持或全文已读。内部.20/.20/.40/.20。
- [ ] `protected_delivery`: 三输入SHA、三交付存在且原生可解析/可编辑；正确静态表接受，公式须实际可信重算。改输入限对应保护机会失分，无总分清零。

### Judge group

- [ ] `factual_support`: 对站点限定搜索：空间组学AI文献发现与筛选的关键事实、数值、版本和判断，逐项独立核验正文/元数据是否真实支持；对池外来源按同一标准判断。 核对真实报告身份、原始日期口径、实际所读版本及六类全文内容；每条实验数字保留影响比较的基线、数据、样本、先验等条件。 必须读取实际三交付和评分侧独立原件/元数据；缺必要供证为评测异常或unresolved，不补候选零分。
- [ ] `coverage_and_independence`: 满足本题实体、主题、时间、版本去重与资料筛选要求；分清一手、转载、独立支持及可比性，不机械按URL数量计覆盖。 真实至少6个独立候选工作、至少4个合格公开全文，按实际绑定轨迹核两平台尝试和相关正文阅读；记录的非空声明及评分侧获取不能自证执行。 必须读取实际三交付和评分侧独立原件/元数据；缺必要供证为评测异常或unresolved，不补候选零分。
- [ ] `bounded_conclusions`: 趋势、选型与建设建议限定在材料可证明范围，区分事实、官方宣称、静态实现、实验和推断；允许有依据的不同结论。 区分作者实验与复现、unknown与否定、作者局限与自己的推断；不把不同任务、切片、版本、参考数据或硬件的绝对数字直接排名。 必须读取实际三交付和评分侧独立原件/元数据；缺必要供证为评测异常或unresolved，不补候选零分。

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

### Criterion 1: 文献身份与事实支持 (key: factual_support, weight: 0.5)

判据：对站点限定搜索：空间组学AI文献发现与筛选的关键事实、数值、版本和判断，逐项独立核验正文/元数据是否真实支持；对池外来源按同一标准判断。 核对真实报告身份、原始日期口径、实际所读版本及六类全文内容；每条实验数字保留影响比较的基线、数据、样本、先验等条件。 必须读取实际三交付和评分侧独立原件/元数据；缺必要供证为评测异常或unresolved，不补候选零分。

**Score 1.0**: 关键事实均被可追溯原文支持，时空口径正确，无捏造来源或实验结果。

**Score 0.5**: 主结论成立但存在非关键字段或支撑缺失，未将未知说成已证实。

**Score 0.0**: 关键结论与原文冲突、捏造出处/事件/全文结果，或没有完成核心事实核验。

### Criterion 2: 筛选覆盖与独立工作 (key: coverage_and_independence, weight: 0.3)

判据：满足本题实体、主题、时间、版本去重与资料筛选要求；分清一手、转载、独立支持及可比性，不机械按URL数量计覆盖。 真实至少6个独立候选工作、至少4个合格公开全文，按实际绑定轨迹核两平台尝试和相关正文阅读；记录的非空声明及评分侧获取不能自证执行。 必须读取实际三交付和评分侧独立原件/元数据；缺必要供证为评测异常或unresolved，不补候选零分。

**Score 1.0**: 所有关键分支有合格覆盖，重复/版本/转载已合并，独立性或无法交叉验证的边界说明准确。

**Score 0.5**: 满足主范围但漏一个非关键分支，未用不合格材料凑数。

**Score 0.0**: 核心分支缺失、反复转载或同一工作版本冒充多项独立结果，无法支撑主要比较。

### Criterion 3: 实验条件与结论边界 (key: bounded_conclusions, weight: 0.2)

判据：趋势、选型与建设建议限定在材料可证明范围，区分事实、官方宣称、静态实现、实验和推断；允许有依据的不同结论。 区分作者实验与复现、unknown与否定、作者局限与自己的推断；不把不同任务、切片、版本、参考数据或硬件的绝对数字直接排名。 必须读取实际三交付和评分侧独立原件/元数据；缺必要供证为评测异常或unresolved，不补候选零分。

**Score 1.0**: 取舍可追溯且限制清楚，不把缺证据当否定或运行保证。

**Score 0.5**: 主要建议有依据，但漏一项非关键条件或后续验证。

**Score 0.0**: 主要建议与证据矛盾、无条件外推，或用不可比排名作关键依据。

## Workspace Path

```
workspace/general/challenge/research_verification/general_hard_research_verification_task_004_site_search_literature_screening
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- 源先行非穷尽文献事实oracle；两名模型初始独立发现、B后续给定URL复核及非盲调和分别留痕。模型复核非人工专家，参考工作名单不是评分白名单。
- 外层自动.40/语义.60、自动内部.20/.25/.40/.15；time内部.30/.25/.30/.15，citation内部.20/.20/.40/.20。缺项/unknown仍保留对应机会，不以加引文稀释假引文。
- 日期token/元数据机械绑定不证明科学日期角色、真实资格/去重或实际全文阅读；声明search记录不自证动作。真实检索/阅读、六类事实及条件必须由独立Judge结合完整轨迹与真实来源核验。
- score0.25.0/core0.15.2或兼容冻结入口；prepare后独立collect公开来源。显式reuse保留原GET时刻/原件与自包含谱系，不冒称当前GET。缺GT/来源锁/投影/Office为评测异常，不补能力零分。
- 公开HTML/PDF/XML/JATS元数据等价路径按真实文本/节点lineage解析，不读图像；完整原件只留外部取证/实际来源包，Git GT只保留必要事实与SHA/定位，不复制完整论文。
- 作者原生参考、机制控制和独立ZIP自动验收不是真实Harness、正式语义Judge或hybrid成绩；900仅任务元数据，难度/区分度待实测校准。
