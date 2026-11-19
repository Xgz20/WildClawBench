---
id: general_hard_office_documents_task_008_bilingual_revision
name: 中越双语修改意见与最终稿
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
    - path: results/final_vi.docx
      role: candidate_deliverable
    - path: results/review_zh.docx
      role: candidate_deliverable
    - path: results/alignment.csv
      role: candidate_deliverable
dataset_report: {"category": "office_documents", "category_name": "文档与办公交付", "category_order": 0, "checkpoint_capabilities": {"automated.boundary_cases": ["reasoning_planning"], "automated.business_correctness": ["data_processing"], "automated.delivery_integrity": ["verification_delivery"], "automated.evidence_binding": ["verification_delivery"], "llm_judge.decision_grounding": ["data_processing"], "llm_judge.usable_handoff": ["verification_delivery"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-challenge"}
---

# 中越双语修改意见与最终稿

## Prompt

请完成中越服务交接条款的双语修订。输入为 /tmp_workspace/baseline_zh.docx 中文基线、/tmp_workspace/draft_vi.docx 越文草稿、/tmp_workspace/review_vi.docx 的12条越文修改意见，以及 /tmp_workspace/terms.csv 固定术语对照。全部机构、姓名、条款和数据均为合成；离线完成。

以中文基线和固定术语为事实与口径上限。越文意见是提案，未获得基线授权的冲突修改不采纳或列待授权，并用中文说明；不能为了满足越文提案去改中文基线。越文允许等价句型，保留主体归属、数值、币种/税口径、日期、工作时间与起算事件、否定及条件，不增造已执行或未知的事实。正确的原有事实与无意见句也要核对。

交付 /tmp_workspace/results/final_vi.docx：完整的16句越文修订稿，保留S01至S16的可见句ID，用原生可编辑段落或表格承载正文。不能只给修改片段、中文重写或图片代替。原文所提业务动作/附件不是要求实际执行或额外生成的依赖。

交付 /tmp_workspace/results/review_zh.docx：对R01至R12逐项用中文写处理与理由，并提供意见编号、句编号、处理结论、依据的原生索引表。可拆表、重排、用对应中文表头；索引和正文按意见ID对应，读者能查回来源及最终句。未采纳提案应说明冲突/待授权，不编造违法、已获批准或已经完成的结论。

交付 /tmp_workspace/results/alignment.csv：覆盖全部16句的UTF-8对齐账本，可带BOM、中文别名及行列重排。列为sentence_id、comment_id、decision、facts_json、term_ids、final_ref、review_ref、source_refs、explanation_zh；逐句事实键、单位、受控值及空值约定见中文基线后附交付契约和字段表。facts_json为本句事实对象，事实键可用所给英文标识或对应中文名；不以缺字段代替未知。多术语/引用用分号分隔，空集合保留列。无对应意见的句仍核对，comment_id及review_ref可空。

final_ref/review_ref用实际Word文件名#可见章节或句/意见ID；不能只引用存在但无关的标题。source_refs用输入文件#句/意见/术语ID，允许基线定义的ZH/DV/RV/T简码，须覆盖对应中文事实、越文原句、适用意见和术语；未采纳冲突还要有权限依据。同句不得有冲突事实，账本、中文说明及实际越文正文一致。账本声明不能替代Word真正修订，术语出现也不代表整句译义正确。

只修订文档，不访问真实账号，不发送消息、发布、退款或修改权限。四个输入原字节保持不变，所有新文件写results，临时材料写results或系统临时目录。

## Expected Behavior

保留中文基线与固定术语，独立比较12项越文提案并完成16句越文修订、12项中文说明与逐句事实/术语账本。按实际正文核数值/日期/单位，处理角色、否定、条件与权限；未知不编为已完成。

## Grading Criteria

### Automated group

- [ ] `business_correctness`: 逐句核对齐事实字段与术语、实际越文正文可观察的金额/币种/日期/工作单位和数量，以及12条意见的CSV和原生中文索引处理结果。完整角色/否定/条件译义由Judge检查。
- [ ] `boundary_cases`: 核主体声明、千分位/单位、未授权日期、工作时限及起算、否定/授权的类型字段、术语漂移和4条无意见控制；不把词项出现当完整翻译正确。
- [ ] `delivery_integrity`: 16句原生越文、12条中文说明及原生索引、16行完整账本可解析且对应；输入未改，缺字段保留其它可判业务项。
- [ ] `evidence_binding`: 逐句来源覆盖实际56条索引记录，最终稿/说明引用位于包含该句或意见正文的章节，中文原生索引自身也绑定同一来源。

### Judge group

- [ ] `decision_grounding`: 独立读取中文基线、越文草稿、12条越文意见与术语，逐句检查最终越文和中文理由。实际主体关系、否定/条件、时限起算、币种税口径、日期/数量及权限与基线一致。账本字段或词项齐全不能替代实际译义，作者参考不是唯一合法措辞。
- [ ] `usable_handoff`: 检查两份实际Word和CSV的完整性、语言、原生可编辑正文、意见到最终句/来源对应，以及跨产物是否一致；允许等价越文句型和原生表/段落布局。

## Automated Checks

```python
def grade(**kwargs):
    from pathlib import Path
    import runpy
    root = Path(kwargs.get("workspace_path") or "/tmp_workspace")
    result = runpy.run_path(str(root / "gt" / "grader.py"))["grade"](root)
    return {"business_correctness": result["business_correctness"], "boundary_cases": result["boundary_cases"],
            "delivery_integrity": result["delivery_integrity"], "evidence_binding": result["evidence_binding"], "overall_score": result["overall_score"]}
```

## LLM Judge Rubric

### Criterion 1: 双语译义与修订裁决 (key: decision_grounding, weight: 0.7)

判据：独立读取中文基线、越文草稿、12条越文意见与术语，逐句检查最终越文和中文理由。实际主体关系、否定/条件、时限起算、币种税口径、日期/数量及权限与基线一致。账本字段或词项齐全不能替代实际译义，作者参考不是唯一合法措辞。

**Score 1.0**: 16句越文完整忠实，12项取舍和理由有正确依据；固定术语和关键事实、条件、否定均对应，无未经授权的改期/改口径/外发/已发送或未知变完成。

**Score 0.5**: 所有关键主体、数值、否定、条件、权限及范围均正确，仅有一项不影响主要理解的非关键措辞/说明/定位遗漏。

**Score 0.0**: 任一关键主体颠倒、否定/条件反转、金额/单位/币种/日期错误、未授权提案被采纳、编造已发送/已验收或未知变完成，或者核心越文修订未完成；即使账本正确也不能给译义分。

### Criterion 2: 越文稿与中文审校交接 (key: usable_handoff, weight: 0.3)

判据：检查两份实际Word和CSV的完整性、语言、原生可编辑正文、意见到最终句/来源对应，以及跨产物是否一致；允许等价越文句型和原生表/段落布局。

**Score 1.0**: 越文稿可作为完整修订稿使用，中文12项说明可复核，ID、索引、事实与来源相互对应；无关键遗漏、矛盾、不可读重音或无法使用的布局。

**Score 0.5**: 主要修订与审校交接可用，无关键跨产物矛盾，仅有一处不影响主要复核的非关键语言/定位/版式问题。

**Score 0.0**: 主要Word缺失/非原生/无法使用，最终稿改成中文或只有片段/账本，中文说明不能对应，正文与账本关键事实矛盾，或主要解释只在聊天中。

## Workspace Path

```
workspace/general/challenge/office_documents/general_hard_office_documents_task_008_bilingual_revision
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- H008；L3为设计预估。保留线上双语审校工作形态，全部机构、内容、数据为自有合成；GDPval仅方法参考，不复制题文或素材。原生Word及评分侧渲染不计视觉输入。
- 规则75%/语义25%。规则内业务0.55、边界0.25、交付0.15、证据0.05；业务为账本事实0.4、实际原生字面值0.25、正文覆盖/术语0.2、意见处理0.15。
- 规则直接检查正文可观察金额/币种、日期集、工作单位/数量及固定术语；它不完整解析角色归属或越文模态/条件。保持同样词项却颠倒角色或遗漏否定的作者边界例仍规则1.0，独立Judge必须核实际译义并拒绝关键矛盾，不将规则满分说成hybrid合格。
- 支持BOM、中文字段/表头、数字/布尔/日期等价表示、NFD重音、越文数词/日期措辞、段落或原生ID正文表及行列重排。不要求越文逐字同参考。未知与缺字段分开；JSON重复事实键拒绝，不能靠后值掩盖冲突。
- 独立计算在参考前完成，物理源核对包括Decimal金额、日期、主体字面映射和17减3，比较提案事实与中文事实；语义源标注仍由作者制作，没有第二专家审校或真实语义结果。
- 规则只用Python标准库，无外部服务/LLM/Office评分依赖。缺GT/helper或规则崩溃保留异常，候选漏交/损坏按可判字段处理。未经四端执行、独立语义评分及难度/区分度校准。
