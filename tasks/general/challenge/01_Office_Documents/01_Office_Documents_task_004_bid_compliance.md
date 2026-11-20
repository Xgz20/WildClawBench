---
id: 01_Office_Documents_task_004_bid_compliance
name: 采购需求与技术响应覆盖核对
category: office_documents
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
    - path: results/traceability.xlsx
      role: candidate_deliverable
    - path: results/response_revised.docx
      role: candidate_deliverable
    - path: results/gaps.md
      role: candidate_deliverable
scoring_runtime:
  office: true
dataset_report: {"category": "office_documents", "category_name": "文档与办公交付", "category_order": 0, "checkpoint_capabilities": {"automated.boundary_cases": ["reasoning_planning"], "automated.business_correctness": ["data_processing"], "automated.delivery_integrity": ["verification_delivery"], "automated.evidence_binding": ["verification_delivery"], "llm_judge.decision_grounding": ["data_processing"], "llm_judge.usable_handoff": ["verification_delivery"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-challenge"}
---

# 采购需求与技术响应覆盖核对

## Prompt

请核对采购需求与技术响应的覆盖关系，修订成只由给定材料支持的内部核对稿，并列出必须项缺口。

输入：/tmp_workspace/requirements.docx含35项R编号需求及必须/建议等级；/tmp_workspace/response.docx前部是待核初稿D编号，后部F编号是当前配置的已核验事实摘录；/tmp_workspace/certificates.pdf是可提取文本的证书条目。初稿自述不能证明能力。有冲突时对照F事实及证书明确的主体、型号/版本、有效日期，不把建议方案当作已经实施。

投标核验截止为2026-11-05 17:00，时区Asia/Shanghai；证书日期含首尾日。资料快照日期、编稿日期、文件修改时间和今天均不替代核验截止日。不联网查询或假设已经续证、升级或整改。硬件配置、传输TLS、CSV基础格式等不能代替未提供的软件功能证据。

交付 /tmp_workspace/results/traceability.xlsx，覆盖全部R编号。允许任意工作表名、行列顺序，可将不同字段分表并按req_id连接；同一需求的同一字段应有唯一一致的值，不留竞争版本。保留以下英文key或对应中文表头：

- req_id；mandatory（必须项）：是/否，可用required/optional或布尔true/false。requirement（需求说明）、risk（缺口或限制）、next_step（下一步）每项均非空。
- draft_status（初稿状态）：已覆盖、部分覆盖、缺失、过度承诺、证书过期，可用covered/partial/missing/overclaim/expired。它评价原初稿及其所引证据，不能用修订后的状态替代；“证书过期”按投标截止日判断。
- coverage（最终覆盖）：已覆盖/covered表示材料支持全部条件；部分覆盖/partial表示明确只支持一部分、其余有已知限制；不满足/unmet表示材料明确不支持该项；待核实/unverified表示缺少适用证据而无法确认。缺证据、过期或型号不符不能直接推成产品一定不具备，也不能写成已满足。
- certificate_status（证书状态）：有效/valid、过期/expired、范围不符/scope_mismatch、不要求/not_required，必要时可写未生效/not_yet_valid。没有证书要求不等于未核验证书。
- requirement_refs（需求来源）、draft_refs（初稿来源）、fact_refs（核验事实）、certificate_refs（证书来源）、revised_refs（修订定位）：写文件#编号，如requirements.docx#R001、response.docx#D001、response.docx#F001、certificates.pdf#C01、results/response_revised.docx#R001。角色列中也可只写对应编号；多个用分号隔开。初稿确实缺失或本项不要求证书时相应来源留空或N/A，不编造记录。

交付 /tmp_workspace/results/response_revised.docx：保留35项需求编号及真实响应，支持的小节或表格格式均可。每项须有一处明确的“覆盖结论：<coverage枚举>”和实际响应正文；也可用含req_id、coverage、response（响应正文）的原生表。说明已支持部分、限制、未知及依据，删除或纠正原稿中无证据的承诺，不能只改表头状态而正文仍宣称全面满足。

交付 /tmp_workspace/results/gaps.md：用Markdown表req_id、coverage、missing_evidence、proposed_action列出最终仍未全部覆盖的必须项，说明缺什么和下一步。建议项的限制可另写说明，不混入必须项表。能用已有事实补齐的初稿遗漏应在修订稿补齐，不能仍以“初稿没写”当作最终未知。

三份交付的状态、范围、引用和缺口应一致。可用正确常数或等价公式；评分端会清空公式缓存后独立重算XLSX，不以保存缓存兜底。离线完成，输入文件保留原字节，不对外投标、发送消息、访问真实账号或执行整改。新交付写results，临时文件写results或系统临时目录。

## Expected Behavior

独立追踪35项需求，识别4项初稿缺失、3项过度承诺及2项过期证书，并区分适用范围和截止日有效正例。已有F事实可补齐的遗漏要补齐，材料缺失保留未知，不承诺已续证或实现不存在的功能。形成矩阵、实际修订响应和必须项缺口，公式由可信引擎重算。

## Grading Criteria

### Automated group

- [ ] `business_correctness`: 核35项初稿/最终/证书/等级及修订稿显式结论，并核必须项缺口集合和状态；缺一个产物不抹掉其它可判断字段。
- [ ] `boundary_cases`: 分别核软件遗漏不能由硬件替代、证书日期/范围及有效正例、已知部分/不支持/未知的区别。
- [ ] `delivery_integrity`: XLSX字段唯一完整、DOCX逐项响应、缺口表及描述完整，输入未改；缺列不视为已知空值。
- [ ] `evidence_binding`: 需求/初稿/事实/证书/修订五类来源实际存在且与需求对应；真实但不相关的来源也不得当作支持。

### Judge group

- [ ] `decision_grounding`: 独立读取原需求、D初稿、F事实、证书及三份实际产物，核软件功能、并列条件、时点、型号/主体/版本和缺口。自动规则只核显式字段与定位，不能代替正文语义；即使字段正确，正文仍虚构能力或续证也应失分。
- [ ] `usable_handoff`: 核三份原生产物是否可解析且按R编号对应，必须项缺口动作是否具体，响应是否真正修订而非只有正确标签。文本投影不证明版面可用性，必要时检查原生结构和实际预览。

## Automated Checks

```python
def grade(**kwargs):
    from pathlib import Path
    import runpy
    root = Path(kwargs.get("workspace_path") or "/tmp_workspace")
    result = runpy.run_path(str(root / "gt" / "grader.py"))["grade"](root)
    return {
        "business_correctness": result["business_correctness"],
        "boundary_cases": result["boundary_cases"],
        "delivery_integrity": result["delivery_integrity"],
        "evidence_binding": result["evidence_binding"],
        "overall_score": result["overall_score"],
    }
```

## LLM Judge Rubric

### Criterion 1: 真实覆盖与证据边界 (key: decision_grounding, weight: 0.7)

判据：独立读取原需求、D初稿、F事实、证书及三份实际产物，核软件功能、并列条件、时点、型号/主体/版本和缺口。自动规则只核显式字段与定位，不能代替正文语义；即使字段正确，正文仍虚构能力或续证也应失分。

**Score 1.0**: 35项核心响应和限制均有材料支持，正确区分可补齐遗漏、部分能力、明确不支持和未知；不扩大证书范围或假设续证/整改，跨产物无关键矛盾。

**Score 0.5**: 主要覆盖及缺口判断准确，无影响采购判断的虚构承诺或事实错误，仅遗漏一处非关键解释或定位。

**Score 0.0**: 软件功能被无关参数替代、忽略有效期/范围、虚构能力或更新证明，把未知直接判满足/不具备，或有影响采购判断的关键错漏。

### Criterion 2: 可复核的采购交接 (key: usable_handoff, weight: 0.3)

判据：核三份原生产物是否可解析且按R编号对应，必须项缺口动作是否具体，响应是否真正修订而非只有正确标签。文本投影不证明版面可用性，必要时检查原生结构和实际预览。

**Score 1.0**: 矩阵、响应、缺口说明完整可用，读者能定位材料并区分初稿问题与最终能力，下一步明确，不依赖聊天补充。

**Score 0.5**: 主要交接可用且无关键跨产物矛盾，但缺一项非关键说明或定位，不影响主要复核。

**Score 0.0**: 核心产物缺失/不可用、必须项或动作无法对应、报告与实际响应冲突，或主要判断只停留在聊天。

## Workspace Path

```
workspace/general/challenge/01_Office_Documents/01_Office_Documents_task_004_bid_compliance
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- H004；L3为设计预估。按清洗线上需求形态重构全部公司、配置、要求、草稿、事实卡与证明，不含线上用户原文、真实资质或附件。作者标注加独立计算不代表专家人工复核。
- 规则权重业务0.55、边界0.25、交付0.15、证据0.05。业务为35项均值0.85和必须项缺口0.15；每项初稿/最终/证书/等级/修订显式结论权重0.25/0.25/0.15/0.1/0.25。缺口集合0.4、逐项状态与非空依据/动作0.6。
- 边界三族等权：软件缺失不由硬件代替、日期范围与有效正例、部分/不支持/未知区别。自动规则不按正文关键词评分；实际承诺、支持充分性和自然语言跨产物一致性由独立Judge核验。
- 交付按矩阵schema及唯一字段、逐项DOCX结论与正文、Markdown缺口schema、矩阵描述完整性、输入未改五项等权。字段可分表连接；缺列或歧义字段不抹掉其它字段，缺列也不等于已知空值。
- 证据按35项的五类角色绑定等权，初稿确实缺失/不需证书只在列存在且显式为空时得对应分。错误单条引用只影响相关证据点，不放大成其它业务失败。输入改变时边界/交付/证据为0，缺GT或引擎错误保持评测异常。
- 评分前冻结可信Office锁，先清空公式缓存再重算副本，派生XLSX/回执/结构观察写Worker证据目录；原件只读。参考表用Artifact创作并扰动/恢复计数，另用真实Calc复核。原生DOCX/PDF文字可提取，评分预览不使本题成为视觉任务。
- 原文到107条源记录的SHA及定位、35项独立标签/比较模型、作者正负控制均在私有GT。尚未做独立语义评分、专家人工审阅、四端执行或实测区分度校准。
