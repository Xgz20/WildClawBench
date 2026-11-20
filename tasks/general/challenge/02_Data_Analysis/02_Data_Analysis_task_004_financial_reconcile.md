---
id: 02_Data_Analysis_task_004_financial_reconcile
name: 三表经营指标口径与重述对账
category: data_analysis
timeout_seconds: 900
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L3
grading_type: hybrid
grading_weights:
  automated: 0.75
  llm_judge: 0.25
tags:
  - custom
  - general-hard
  - general-challenge
judge_evidence:
  required:
    - path: results/comparison.xlsx
      role: candidate_deliverable
    - path: results/memo.docx
      role: candidate_deliverable
    - path: results/sources.csv
      role: candidate_deliverable
scoring_runtime:
  office: true
  office_render: true
dataset_report: {"category": "data_analysis", "category_name": "数据分析与表格建模", "category_order": 1, "checkpoint_capabilities": {"automated.boundary_cases": ["reasoning_planning"], "automated.business_correctness": ["data_processing"], "automated.delivery_integrity": ["verification_delivery"], "automated.evidence_binding": ["verification_delivery"], "llm_judge.decision_grounding": ["data_processing"], "llm_judge.usable_handoff": ["verification_delivery"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-challenge"}
---

# 三表经营指标口径与重述对账

## Prompt

请统一三家公司的三年财务口径，形成可复算且可追溯的经营对标报告。分析时点固定为2026-09-30，比较2023、2024、2025报告年度，不能把文件名中的披露年当作报告年。

读取/tmp_workspace/statements/下九份文本财务摘录、/tmp_workspace/metrics_definition.md和/tmp_workspace/restatements.csv。公司A青川实业、B北辰服务、C澄星制造均为合成练习。按口径定义计算收入同比、简单平均归母ROE、合并经营现金与归母利润比，共27条核心指标；保留四项不可比、真实零值、负现金流和同名次情况。使用分析时点已生效的两项更正，保留前后值、差额及依据。年度、单位、归母/合并/单体、现金流/现金存量不能混用。

交付三份实际文件：
1. /tmp_workspace/results/comparison.xlsx：原生可编辑的生效数据、指标和重述差异。按company_id、period_year发现9条生效数据，含定义中的revenue_wan、parent_profit_wan、cfo_wan、equity_open_wan、equity_close_wan、prior_revenue_wan和scope_comparable入口。金额统一万元；2023上年基数取对照列，后两年上期收入须引用同一生效表的上一报告年，不能抄旧对照。指标按company_id、period_year、metric_id识别，含numerator_wan、denominator_wan、value、rank、change_pp、status、reason七个可重算公式字段，包括返回n/a的情况。比例存比率数值，change_pp存百分点；缺失和不可比不能补0。保留两项重述ID、原值、生效值及差额。
允许Sheet改名、行列重排、平移、分年/分公司表格、清楚的中英文等价表头、普通标量来源公式及合理辅助公式，不要求作者坐标或版式。可保留明确的原披露/基线快照，但实际生效入口与公式结果须可见可复查。改变生效金额或scope标记后应更新相关指标、状态、名次和变化；不要求自动重读财报/CSV、重新选更正版本或改写Word。
2. /tmp_workspace/results/memo.docx：原生可编辑报告，列明27项指标值和各年名次，及2025较2024的百分点变化；解释两项更正和四个不可比结果。为便于逐项核对，用有公司、年度、指标、数值、名次、变化百分点字段的表，或每条记录一个清楚标记的短段落，例如“A 2025 roe: value=18.41%; rank=1; change_pp=0.97”。指标ID也可用明确中文名称。重述可用ID/原值/生效值/差额表，或例如“R-A24：原值=144000万元；生效值=146000万元；差额=2000万元”的独立记录。百分数、比率、倍数和百分点必须清楚，比例至少保留0.01个百分点。给出有数据依据的排序解释、范围限制与下一步复核事项，不把三个比率推成综合优劣、投资价值、因果改善或未来回款结论，不虚构审计、审批或执行。
3. /tmp_workspace/results/sources.csv：UTF-8，按定义保留63条公司/报告年/源字段记录及11个必需字段，包括缺失记录。定位到实际源文件、可见ID、原披露值与单位、生效值和实际更正ID；A2024收入更正还影响A2025的上年收入关联。文件存在或出现正确关键词不等于来源支持事实。列序、行序和BOM不限，可加清楚的附加列。

三份输入集合只读，全部新交付写results，每份不超过5MiB，不要求交付代码。离线完成，不访问真实账号、网络或付费接口，不发消息或执行真实财务业务。保存前核对数字、公式、单位、名次和跨文件一致性。评分将在独立副本中清缓存实际重算、改变已核验的生效数据入口；不改原交付。独立语义裁判还会检查真实结论和限制，自动规则分不能代替这些判断。

## Expected Behavior

按2023至2025报告年度与已生效重述统一万元，三表取数形成27项可重算对标及63条真实来源，保留四不可比、零、负数与并列，交付有材料依据及限制的原生报告。L3仅设计预估。

## Grading Criteria

### Automated group

- [ ] `business_correctness`: 统一单位与报告口径，制作三年对标表，独立标出重述和不可比项目；结论只讨论指标证据。
- [ ] `boundary_cases`: 逐项识别并正确处理：单位错千倍；旧期重述漏用；把缺失变0。以独立反例验证，不只检索关键词。
- [ ] `delivery_integrity`: 全部要求的产物可解析/可使用，跨产物关键事实一致；保护文件与输入未改变。
- [ ] `evidence_binding`: 来源/验证记录定位到实际材料、产物或最终候选源码；自述已运行不能代替独立验证。

### Judge group

- [ ] `decision_grounding`: 独立读取原始财务摘录、口径、更正表、三份真实交付及规则派生证据，核查数值支持、单位/报告期/归母与合并边界、四类不可比和结论限制。
- [ ] `usable_handoff`: 查看真实工作簿、Word、CSV和可信Office预览，判断是否能定位原始金额/更正、维护生效输入并继续复核未决问题。

## Automated Checks

```python
def grade(**kwargs) -> dict:
    from pathlib import Path
    import runpy
    import pypdf
    import pdfplumber
    root=Path(kwargs.get("workspace_path") or "/tmp_workspace")
    scores=runpy.run_path(str(root/"gt/grader.py"))["grade"](root)
    return {key:scores[key] for key in ("business_correctness","boundary_cases","delivery_integrity","evidence_binding","overall_score")}
```

## LLM Judge Rubric

### Criterion 1: 财务口径与结论依据 (key: decision_grounding, weight: 0.7)

判据：独立读取原始财务摘录、口径、更正表、三份真实交付及规则派生证据，核查数值支持、单位/报告期/归母与合并边界、四类不可比和结论限制。

**Score 1.0**: 27项核心结果、各年有效名次及2025较2024变化与材料一致；两项更正正确应用，A2024收入同时更新A2025同比基数，B2023只改归母利润。四项不可比不填零、不整家删除，B2023现金比率零、C2023 ROE零、A2025负现金流正确解释；B/C2025 ROE并列。区分报告期/披露期、归母/合并/单体、经营流量/期末存量和简单平均/加权ROE。解释排名限于定义，保留B并表范围、缺失和分子分母范围限制，不虚构因果、投资优劣、偿债或未来回款、审计/审批/真实执行。

**Score 0.5**: 核心数值、版本、口径、可比状态和结论限制正确，无关键矛盾；仅遗漏一项不改变业务判断的说明或定位细节。

**Score 0.0**: 任一关键数值、版本、字段/单位、排名、可比处理或跨产物结论实质错误；漏历史更正或下一年基数、混归母/合并、把缺失变0、丢负号、用期末权益代替平均、把比率排名推成因果/综合投资判断，或虚构执行均为0。正确表格、关键词或自动规则1.0不能抵消相反正文或缺失的关键推理。

### Criterion 2: 复核与交接可用性 (key: usable_handoff, weight: 0.3)

判据：查看真实工作簿、Word、CSV和可信Office预览，判断是否能定位原始金额/更正、维护生效输入并继续复核未决问题。

**Score 1.0**: 三份原生产物可用、基线一致、实际生效入口和公式结果可见可维护；63条来源正确回查，缺失/更正留痕。读者能复核27项值/名次/变化、识别四不可比和后续所需资料，知道Word/CSV对应保存基线而非自动刷新，也不依赖聊天中的未落盘解释。允许不同合理布局、表或清楚逐记录段落。

**Score 0.5**: 核心产物可复核且跨文件一致，未决项明确，仅缺一项非关键维护/定位说明。

**Score 0.0**: 关键产物缺失/不可读/隐藏、公式模型写死、来源无法回查、跨文件实质冲突，或读者无法分清有效值/不可比及继续办理所需资料。

## Workspace Path

```
workspace/general/challenge/02_Data_Analysis/02_Data_Analysis_task_004_financial_reconcile
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- 来源为已接受线上需求原型，全部公司/数据合成，GDPval仅作方法参考；原118材料和146 SDK绑定保留，正式评分使用新增runtime/scoring_contract及office_runtime_v014。
- 自动规则四项按.55/.25/.15/.05加权，混合总分再按.75/.25合并。只输出自动分不等于完整任务分。
- 自动业务含指标.45、生效数据.20、重述.10、Word事实.25；边界含五组真实依赖.80和基线重要边界.20。每组只评分应改变字段，并要求其余结果正确；基线、公式和可见性先核验，候选源表快照按真实响应寻找驱动入口。
- 来源证据按实际文件/ID/更正绑定及原值/单位/生效值核验；相反正文或虚构动作由独立Judge处理，不能只靠关键词。
- 核心身份、输入源或原生可见性破坏、全静态/常量失效模型触发业务分最高.5；输入改动使边界/交付/证据为0。缺GT/helper/引擎或字体锁漂移、合法但未支持的共享/数组/元数据来源干预保留evaluation_error，不补候选零。
- 规则不改候选产物，Word由可信字体/引擎生成派生PDF核基本可见性；不构成完整视觉评分。四端预检、L3难度及区分度仍待实测，900只作元数据。
