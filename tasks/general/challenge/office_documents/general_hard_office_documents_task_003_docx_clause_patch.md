---
id: general_hard_office_documents_task_003_docx_clause_patch
name: 合同条款局部修订与交叉引用
category: office_documents
timeout_seconds: 900
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L2
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
    - path: results/contract_revised.docx
      role: candidate_deliverable
    - path: results/changes.json
      role: candidate_deliverable
dataset_report: {"category": "office_documents", "category_name": "文档与办公交付", "category_order": 0, "checkpoint_capabilities": {"automated.boundary_cases": ["reasoning_planning"], "automated.business_correctness": ["data_processing"], "automated.delivery_integrity": ["verification_delivery"], "automated.evidence_binding": ["verification_delivery"], "llm_judge.decision_grounding": ["data_processing"], "llm_judge.usable_handoff": ["verification_delivery"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-challenge"}
---

# 合同条款局部修订与交叉引用

## Prompt

请依据批准清单局部修订一份技术服务合同，并交付可追溯的变更说明。

输入为 /tmp_workspace/contract.docx（5页可编辑原稿，12条、页眉和2张表）及 /tmp_workspace/approved_changes.md（C01至C07已批准修改和P01/P02禁止修改项）。按批准文本完成，不自行扩大范围；尤其不能全局替换相同数字或相近邮箱。中西标点、空白和run拆分可等价，未批准的条款措辞不自行同义改写。

交付 /tmp_workspace/results/contract_revised.docx：可编辑净稿，按最终顺序连续编号，保留“第N条 标题”的编号形式、原有主体/服务期/页眉、2张表及其行列。插入、删除条款后，所有原生REF的显示值、书签目标和实际条号应一致；删除培训条款后不能留下指向它的字段。更新通知邮箱时，同时改显示文字与实际mailto目标。不能以截图替代正文、将REF扁平化为普通数字，或留下待接受的修订。

无需保持ZIP字节、字体、run划分、关系ID、书签名称或分页完全相同；保留有效可核验的原生关系。两表在变更说明中分别称“付款节点”和“服务联系”。

交付 /tmp_workspace/results/changes.json，UTF-8 JSON对象，包含：

- source_sha256：本题原始contract.docx的真实SHA-256；result_sha256：最终contract_revised.docx的真实SHA-256。
- changes：C01至C07每项一条，不漏项或重复。每条有change_id、action、source_locations、result_locations、summary。action使用modify/insert/delete；summary说明真实变更及边界，不只写“已完成”。
- source_locations和result_locations均为字符串数组，定位方式为clause:条款标题，或table:表格名称/首列行名/列名。被删除的结果写absent:已删除条款标题。以条款标题定位可避免重排后旧条号混淆。
- 一项修改涉及正文和表格时，两个位置都列出；新增条款同时映射插入位置与新增条款；删除条款同时映射删除结果及被清理引用的支持条款。定位须能在原稿/修订稿中实际核对。

所有输入保持原字节不变，不覆盖原稿。离线完成，新交付写results，临时文件写results或系统临时目录。不访问真实账号，不发送邮件，不执行合同所述服务或签署行为。

## Expected Behavior

按C01至C07局部修订5页合同，插入交付确认并删除培训后最终12条连续。原生REF、编号书签和mailto目标有效，2表及未授权约定保留；P01/P02不可改。真实文件SHA和每项变更位置对应，独立OOXML检查不能以缓存文字代替关系。

## Grading Criteria

### Automated group

- [ ] `business_correctness`: 逐项核7个批准结果及修改范围；检查付款/验收、插入条款、终止期、支持行、删除条款及真实邮箱链接。
- [ ] `boundary_cases`: 核未授权内容白名单、原生REF/书签/条号关系与2表结构，不只看缓存文字或关键词。
- [ ] `delivery_integrity`: 原生正文可解析、净稿结构与变更JSON完整、输入未变；漏报告不抹掉可核验的合同修改。
- [ ] `evidence_binding`: 原/结果文件SHA及C01至C07的唯一位置映射能回查实际文件；过期哈希不视为最终产物证据。

### Judge group

- [ ] `decision_grounding`: 独立对照原稿、批准清单、修订合同和变更说明，核对7项变更的法律含义与范围。尤其检查确认不替代验收、终止与保密期限区分、单行服务修改、P01/P02及未授权内容。自动规则已核原生图关系，语义不能只采信报告自述或规则总分。
- [ ] `usable_handoff`: 检查可编辑合同、连续条号、表格及变更位置是否支持下游复核。文本投影不能证明REF关系或链接目标；需结合自动规则中绑定实际原件的结构证据，必要时独立检查OOXML，不能据缓存数字声称原生可用性。

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

### Criterion 1: 批准范围与条款依据 (key: decision_grounding, weight: 0.7)

判据：独立对照原稿、批准清单、修订合同和变更说明，核对7项变更的法律含义与范围。尤其检查确认不替代验收、终止与保密期限区分、单行服务修改、P01/P02及未授权内容。自动规则已核原生图关系，语义不能只采信报告自述或规则总分。

**Score 1.0**: 批准项完整准确，无未经批准的实质改写或承诺；原约定、限制及保护条款保留，变更说明与实际差异一致且依据可定位。

**Score 0.5**: 主要变更和边界准确，未改保护条件，无影响履约的错漏，仅遗漏一处非关键变更解释或定位。

**Score 0.0**: 批准项存在影响履约的错误、未授权改写、误改价款/责任上限、虚构确认或删除效果，或核心修订未完成。

### Criterion 2: 可复核的原生合同交接 (key: usable_handoff, weight: 0.3)

判据：检查可编辑合同、连续条号、表格及变更位置是否支持下游复核。文本投影不能证明REF关系或链接目标；需结合自动规则中绑定实际原件的结构证据，必要时独立检查OOXML，不能据缓存数字声称原生可用性。

**Score 1.0**: 净稿与JSON均可用，修改位置及实际结果清楚，结构和引用无已知故障；下游无需聊天补充即可核对并继续审阅。

**Score 0.5**: 主要产物可用、无关键矛盾，但有一处非关键说明或定位缺项，不影响主要复核。

**Score 0.0**: 核心文件缺失/不可用、引用或表格损坏影响使用、报告与原件矛盾，或关键变更只在聊天中。

## Workspace Path

```
workspace/general/challenge/office_documents/general_hard_office_documents_task_003_docx_clause_patch
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- H003；L2为设计预估。合同、主体、示例邮箱、批准计划及GT均自建合成，仅借鉴GDPval的专业办公产物核验方法，不复制开源题文、素材或隐藏答案，不伪装为线上原型题。
- 规则权重业务0.55、边界0.25、交付0.15、证据0.05。7个批准项等权，项内要求等权；C07显示邮箱与实际链接各占一半。边界按保护范围/原生引用/表格结构三族等权；引用族兼顾条号连续与9条期望边。
- 未授权正文或实际存在单元格的措辞越界时，业务和保护范围族为0；缺失列及关系故障分别计分，不抹掉其它已知字段。P01/P02被改时业务及全部边界为0。输入原件被改时边界/交付/证据为0。缺GT抛评分异常，不补候选零分。
- 正文按批准前/后措辞白名单与规范化关系比较，不匹配ZIP、run或ID；接受简单/复杂REF、等价书签名/关系ID、金额格式及实际Office另存。作用中的页眉按first/even/default开关核验；不会因未启用的空偶数页页眉误扣。
- 交付按DOCX可解析、JSON schema与7项完整、最终结构、净稿无已知对象/修订故障、输入未变五项等权。证据按文件哈希0.4、逐项真实位置映射0.6汇总。原生结构观察写Worker stdout并由规则审计绑定。
- GT来自原文和批准清单的独立描述，不从候选或参考DOCX提取答案；另以python-docx/pypdf和真实LibreOffice另存核对原生关系与可读性。作者控制不代表独立法律人工审阅、语义评分、四端执行或实测难度通过。
