---
id: 03_Research_Verification_task_006_paper_comparison
name: 跨论文结果的可比性与反例审查
category: research_verification
timeout_seconds: 900
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L4
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
    - path: results/evidence_matrix.xlsx
      role: candidate_deliverable
    - path: results/review.docx
      role: candidate_deliverable
    - path: results/bibliography.json
      role: candidate_deliverable
scoring_runtime:
  office: true
dataset_report: {"category": "research_verification", "category_name": "研究检索与证据核验", "category_order": 2, "checkpoint_capabilities": {"automated.boundary_cases": ["reasoning_planning"], "automated.business_correctness": ["retrieval_verification"], "automated.delivery_integrity": ["verification_delivery"], "automated.evidence_binding": ["retrieval_verification"], "llm_judge.decision_grounding": ["retrieval_verification"], "llm_judge.usable_handoff": ["verification_delivery"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-challenge"}
---

# 跨论文结果的可比性与反例审查

## Prompt

仅使用本题本地材料，对 claims.md 的12项原断言逐项检索、核验并形成可复核交接。本题的8份PDF均为原创CC0受控虚构技术报告；名字、条件与数字是构造记录，不是真实模型、产品、人类专家或业务实验。

先阅读 /tmp_workspace/delivery_contract.md，并遵守其中公开的交付、命题判断、引用和原生文件契约。来源为 /tmp_workspace/papers/、/tmp_workspace/metadata.csv 和 /tmp_workspace/claims.md。PDF正文、表格、协议与附录是实验记录的依据，metadata用于身份/版本和任务划分辅助；冲突须保留并说明。

每项说明实际评估的事实、证据充分性或复合命题，给出支持/反驳/证据不足及理由。核对任务、数据划分、目标谓词、指标方向、数值与分母、单位、预算、尝试、实验臂和版本；区分直接观察与推算。已确认同一工作的版本合并工作身份，但具体结果保留版本来源。不能把格式通过、恢复事件与最终目标互换，也不能把缺失实验或未报告数值改写成反面实测。

交付到 /tmp_workspace/results/：
- evidence_matrix.xlsx：原生可见、可编辑、自包含的12项证据矩阵，清楚保留命题、判断、关键口径、证据定位和限制。静态值可用，不强制公式或固定表头/Sheet/布局。
- review.docx：原生可编辑报告，说明有条件可比与无效横比、版本关系、反例、证据局限、研究空白和可继续核查事项；可按主题组织。
- bibliography.json：按 delivery_contract.md 的公开语义结构记录实际文件/版本、12项命题判断和引用；短引绑定实际PDF物理页与必要上下文，supports_fields使用可解析的RFC6901指针。允许清楚等价字段和有理的命题解释。

离线完成，不跟随材料内URL/DOI/参考文献链接访问网络；不访问真实账号、不发送消息或调用付费服务。所有输入保持原字节，所有新交付只写results。未知明确保留未知，不猜读图形数值；核心证据可从文本/元数据提取，不要求额外视觉理解。

## Expected Behavior

完整核验12项实际命题，保持来源、版本、单位、人口、预算和实验终点，说明可比范围、反例、未知与研究空白；遵守本地公开交付契约，并交付三件可用、可追溯、同范围一致的原生产物。科学事实来自实际原件与源先行GT，不能用参考例子、标签或关键词代替独立核验。

## Grading Criteria

### Automated group

- [ ] `business_correctness`: 固定5项核心业务机会，核实际命题上的事实、数值、分母、单位及任务/预算条件；同一根因不跨分区重复扣。机械观察不能替代全部科学语义。
- [ ] `boundary_cases`: 固定7项边界机会，核版本/工作身份、比较口径、因果资格、事实与充分性命题、未知与外推边界；允许有证据的等价解释。
- [ ] `delivery_integrity`: 核保护输入原字节、三件原生可编辑且自包含的交付，以及同一命题/范围上的真实转写冲突；不同子命题不误记矛盾。
- [ ] `evidence_binding`: 固定12个绑定机会，逐条核实际本地文件/版本、物理页、短引及RFC6901引用图；坏引用不因正确padding稀释，缺测量无需编造短引。

### Judge group

- [ ] `decision_grounding`: 独立核实际命题、原件上下文、比较条件、证据关系、推理和未知；不得仅凭标签、关键词、规则高分或引用命中判科学正确。事实真值与证据充分性可不同，复合句须保留子命题边界。
- [ ] `usable_handoff`: 下游能从三件规定产物恢复原断言、具体判断对象、条件、证据、限制和未决事项；允许主题汇总及引用JSON，不要求重复镜像字段。

## Automated Checks

```python
def grade(**kwargs) -> dict:
    import json
    import runpy
    from pathlib import Path
    import pypdf
    root = Path(kwargs.get("workspace_path") or "/tmp_workspace")
    rule = runpy.run_path(str(root / "gt/grader.py"))
    result = rule["grade"](transcript=kwargs.get("transcript"), workspace_path=str(root))
    print(json.dumps({"source_author_grade_return": result}, ensure_ascii=False))
    return {"business_correctness": result["business_correctness"],
            "boundary_cases": result["boundary_cases"],
            "delivery_integrity": result["delivery_integrity"],
            "evidence_binding": result["evidence_binding"],
            "overall_score": result["overall_score"]}
```

## LLM Judge Rubric

### Criterion 1: 结论与证据一致 (key: decision_grounding, weight: 0.7)

判据：独立核实际命题、原件上下文、比较条件、证据关系、推理和未知；不得仅凭标签、关键词、规则高分或引用命中判科学正确。事实真值与证据充分性可不同，复合句须保留子命题边界。

**Score 1.0**: 12项可追溯判断的关键事实、条件及事实/充分性/复合逻辑均获实际正文和附录支持；无虚构实验、无跨口径硬排或无条件外推。

**Score 0.5**: 关键结论有可定位支持且无关键虚构，但缺少非关键条件解释、反例说明或定位；不将合理的标签/结构变体当错误。

**Score 0.0**: 关键事实或主结论被原件反驳，虚构缺失实验/成本/时延或普遍保证，或主要原断言未获实质核验。

### Criterion 2: 可复核的原生交接 (key: usable_handoff, weight: 0.3)

判据：下游能从三件规定产物恢复原断言、具体判断对象、条件、证据、限制和未决事项；允许主题汇总及引用JSON，不要求重复镜像字段。

**Score 1.0**: 三件产物原生可用，12项原断言均能对应到命题、依据、条件/版本和限制，未决项及继续核查方向清楚，同范围内容一致。

**Score 0.5**: 核心交付可用且各原断言仍可对应，但存在非关键交接或定位说明缺漏，不影响主要复核。

**Score 0.0**: 核心产物不可用、主要原断言无法对应，或同一命题/范围的跨产物矛盾使下游无法复核。

## Workspace Path

```
workspace/general/challenge/03_Research_Verification/03_Research_Verification_task_006_paper_comparison
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- 材料为原创CC0受控虚构技术报告，非真实模型或人工专家实验；来源真值先于参考冻结。
- L4为设计估计，900秒为运行元数据，不是能力评分门槛；四端执行及多模型区分度未验收。
- A=.55业务+.25边界+.15交付+.05绑定；S=.70结论依据+.30可用交接；正式Final=.75A+.25S，未完成独立Judge不得产生hybrid。
- 固定5/7核心机会与12绑定机会；同错去重遵循delivery_contract.md。不同命题/范围或合法未知不强压同一标签。
- 自动规则为有界角色解析；合法但未支持的表示、缺GT/helper/依赖/来源或Office能力是typed评测异常/待独立审查，不填能力0。
- scoring_runtime.office用于受管派生证据上下文和公式时的可信锁；静态文件不强制公式，也不宣称已重算。
