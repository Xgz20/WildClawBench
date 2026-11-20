---
id: 01_Office_Documents_task_001_policy_crosswalk
name: 多版本制度适用与差异说明
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
    - path: results/applicability.xlsx
      role: candidate_deliverable
    - path: results/handoff.docx
      role: candidate_deliverable
scoring_runtime:
  office: true
dataset_report: {"category": "office_documents", "category_name": "文档与办公交付", "category_order": 0, "checkpoint_capabilities": {"automated.boundary_cases": ["reasoning_planning"], "automated.business_correctness": ["data_processing"], "automated.delivery_integrity": ["verification_delivery"], "automated.evidence_binding": ["verification_delivery"], "llm_judge.decision_grounding": ["data_processing"], "llm_judge.usable_handoff": ["verification_delivery"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-challenge"}
---

# 多版本制度适用与差异说明

## Prompt

请为研修资助经办人员核对不同制度的适用关系，并形成可直接交接的审核材料。

输入是 /tmp_workspace/policies/v1.docx（旧制度8条）、/tmp_workspace/policies/v2.pdf（新制度8条及2条过渡条款，可提取文本）、/tmp_workspace/cases.csv（18个申请实例）。仅依据这些材料离线完成，不联网补充制度或个人信息。

材料核验基准日为2027-03-01。允许在开课前预登记；CSV中的approval、completion、invoice均为基准日经办核验快照。制度版本和在岗年限仍按原始apply_date判定，不按核验日或今天推定。days为已核定的含首尾课程自然日数。空字段表示未知，yes/no表示明确的是/否；未知不能补成0或no。过渡条款的范围和优先顺序以原文为准。

交付 /tmp_workspace/results/applicability.xlsx：在一个主明细表中覆盖全部case_id且每例一行，逐例保留以下业务字段。允许任意工作表名、表头行和列顺序，可增加辅助表；表头采用下列英文key或括号内中文名：

- case_id（案例ID）；rule_set（规则组合）：V1、V2、V1-T01、V2-T02、未覆盖或待核实。
- status（办理状态）：可资助、不资助、待核实、待补正或未覆盖。
- rate（资助比例）、cap_cny（金额上限或金额上限 元）、grant_cny（核定金额或核定金额 元）：金额单位人民币元、精确到分，比例用小数或百分数。未知/未覆盖的金额或比例留空或标n.a./N/A/相应待办状态，不能用0代替；已知不资助的核定金额为0。
- clause_ids（依据条款）、evidence（证据定位）：保留实际条款ID，并用policies/v1.docx#V1-03或policies/v2.pdf#V2-T01这样的路径#条款ID定位，可另补页号或段落号。需要多个依据时逐项列出。
- pending_inputs（待确认事项）：缺什么事实或材料；无待办可留空。next_action（下一步）：经办人员可继续执行的动作。

允许正确常数或等价公式；公式须能在统一离线重算环境中正确计算，不以存储缓存代替结果。不要把重复的全量明细分散为多个竞争版本。

交付 /tmp_workspace/results/handoff.docx：说明一般制度差异、两类过渡适用范围及优先关系；区分明确拒绝、材料待补正、事实待核实和制度未覆盖，列出具体案例、缺项及下一步。关键结论须对应条款，文档和表格中的状态与金额应一致。不能仅在聊天中说明。

输入文件保持原字节不变，不覆盖或删除。所有交付和临时文件写入results或系统临时目录，不访问真实账号或发送消息。正式评分从候选副本独立重算公式；无需在被测工作区安装评分端引擎。

## Expected Behavior

以18个独立标注实例覆盖制度生效边界、自然月年限、两类过渡和材料优先关系。逐例输出正确版本、状态、比例/上限和金额及可追溯依据；DOCX解释差异与具体待办。XLSX从无缓存副本由可信Calc实际重算，允许等价布局、常数与公式；缺GT或重算环境作为评测异常。

## Grading Criteria

### Automated group

- [ ] `business_correctness`: 依据独立18例标签核对版本、状态、比例、上限与可信重算后的核定金额。
- [ ] `boundary_cases`: 按生效日/年限、过渡范围/优先、已知零/未知/拒绝优先三组独立实例核对，不只检索关键词。
- [ ] `delivery_integrity`: 核对原生产物可解析、主表案例集唯一完整、逐例下一步及输入未改；跨产物语义一致性由Judge评价。
- [ ] `evidence_binding`: 声明的条款及路径能解析到实际冻结源文件，且至少包含一项相关依据；充分性由Judge评价。

### Judge group

- [ ] `decision_grounding`: 独立读取实际制度、expected.json和逐例产物，核对版本选择、过渡范围、状态及金额，特别检查T01优先、T02仅放宽年限、未知与已知零、拒绝优先。规则分不能代替语义判断。证据定位须实际支持结论，不能只列条款号。
- [ ] `usable_handoff`: 核对两份原生产物是否包含所需业务字段和差异解释、具体待办对象与动作。检查数据内容和原生结构；有渲染预览时另检查可读性，不能仅凭文本投影声称原生视觉可用性。

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

### Criterion 1: 制度适用与结论依据 (key: decision_grounding, weight: 0.7)

判据：独立读取实际制度、expected.json和逐例产物，核对版本选择、过渡范围、状态及金额，特别检查T01优先、T02仅放宽年限、未知与已知零、拒绝优先。规则分不能代替语义判断。证据定位须实际支持结论，不能只列条款号。

**Score 1.0**: 所有关键制度差异、逐例适用、过渡优先与限制均有充分可定位依据；待确认事项忠实于材料，无虚构或跨产物矛盾。

**Score 0.5**: 主要适用、过渡和金额结论成立且无关键矛盾，仅遗漏一处不影响办理的解释或定位。

**Score 0.0**: 制度适用、过渡范围、状态或金额存在影响办理的错误，虚构缺失事实/依据，或未完成核心逐例判定。

### Criterion 2: 可复核的经办交接 (key: usable_handoff, weight: 0.3)

判据：核对两份原生产物是否包含所需业务字段和差异解释、具体待办对象与动作。检查数据内容和原生结构；有渲染预览时另检查可读性，不能仅凭文本投影声称原生视觉可用性。

**Score 1.0**: DOCX及XLSX可解析，案例、状态/金额、依据与动作可对应，文档清楚解释差异和待办，下游无需聊天补充即可复核并继续办理。

**Score 0.5**: 两份主要产物可使用且无核心矛盾，但缺一项非关键交接说明或定位，不影响主要办理。

**Score 0.0**: 核心原生产物缺失/不可用，重要案例或动作无法对应，跨产物矛盾，或关键解释只在聊天中。

## Workspace Path

```
workspace/general/challenge/01_Office_Documents/01_Office_Documents_task_001_policy_crosswalk
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- H001；L2为设计预估。所有制度和案例均为合成，仅沿用经清洗线上需求原型的方法形态，不含用户原文、附件或个人信息。
- 规则权重业务0.55、边界0.25、交付0.15、证据0.05。业务按18例等权，例内版本/状态/比例/上限/金额权重0.2/0.3/0.1/0.1/0.3；比例容差1e-8，金额0.005元。边界按3族等权，各族内等权，case IDs及字段在私有counterexamples.json。
- 交付按主表结构完整、DOCX可解析、完整且唯一案例集、逐例动作、输入未变五项等权。缺失或重复歧义表头只令对应字段不可判，不抹掉其它已标明业务字段；缺列不等于已知空值。输入改变时边界/交付/证据为0。缺表和缺文档按任务契约失分，不冒充评分异常。
- 证据规则只核实际条款/源文件SHA绑定及至少一项相关依据；充分性、推理、缺项说明和跨产物一致性由独立语义Judge核验。允许任意工作表名、表头行、列顺序和等价计算；不按参考版式匹配。
- 评分前冻结可信LibreOffice实际程序/版本/SHA；原件不写回，清空公式缓存后重算，派生文件与回执写Worker证据目录。评分引擎缺失、漂移、超时或失败不能用缓存兜底。
- 作者参考原型、独立calendar/Decimal模型和正负控制见私有GT；规则作者验证不代表独立语义裁判、人工复核、四端执行或实测难度通过。
