---
id: general_hard_planning_coordination_task_001_measurable_roadmap
name: 模糊工作规划转可衡量行动方案
category: planning_coordination
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
    - path: results/roadmap.xlsx
      role: candidate_deliverable
    - path: results/explanation.docx
      role: candidate_deliverable
scoring_runtime:
  office: true
  office_render: true
dataset_report: {"category": "planning_coordination", "category_name": "规划决策与项目协作", "category_order": 5, "checkpoint_capabilities": {"automated.boundary_cases": ["reasoning_planning"], "automated.business_correctness": ["reasoning_planning"], "automated.delivery_integrity": ["verification_delivery"], "automated.evidence_binding": ["verification_delivery"], "llm_judge.decision_grounding": ["reasoning_planning"], "llm_judge.usable_handoff": ["verification_delivery"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-challenge"}
---

# 模糊工作规划转可衡量行动方案

## Prompt

请把含模糊目标的工作规划改为有目标、基线、动作、责任、验收和时间边界的可衡量季度行动方案。只依据本题材料，不承诺材料无法支持的增长。

输入：/tmp_workspace/strategy_notes.docx 是讨论纪要；/tmp_workspace/baseline.csv 是现状指标和已确认资源；/tmp_workspace/constraints.md 是已批准季度目标、周期、角色容量、成果成本与依赖、许可状态和交付字段。约束C01-C06优先于讨论愿望，先核对原始分子分母和旧口径差异。

交付仅放 /tmp_workspace/results：roadmap.xlsx（原生可编辑Excel）和 explanation.docx（原生Word，说明依据、假设、未知与取舍）。不用交代码，不需要真正开展试点。工作簿覆盖G1-G4及O1-O8，有可测定义、基线、拟议目标、动作、一个牵头角色、验收、分期工时和依赖；未知不能替换为0，未决许可和资源不能默认到位。

保留C06要求的四类有表头记录goals/actions/loads/decisions及字段，页名、列顺序、动作ID和措辞自由，可同页/多页，中文/英文表头均可。业务编号和角色代码按材料保留；中文列名可用目标编号/目标/指标编号/可测定义/基线分子/基线分母/基线比率/基线状态/目标分子/目标分母/目标比率/目标类型/责任角色/截止周期/验收/依据、动作编号/成果编号/方法/关联目标/动作/开始周期/结束周期/前置依赖/状态、周期/项目经理/运营/分析师、决策编号/复核周期/处置。各动作按outcome写行，可拆合、选支持的方法和合理排期，但不能消除最低工作量。前置成果全部完成后的下一周期才能开始，待条件动作仍预留工时。目标比率与基线比率由分子/分母计算，修改这些数字后应更新。说明文档附C06的fact_id/value事实核对表。

source_ref定位为baseline.csv#M1@2026-10-01/2026-10-28等真实指标及期间，或constraints.md#C01至C06、strategy_notes.docx#N1至N5。允许更大合理样本、不同动作拆合/并行/排期和不同措辞，不按参考解排期硬匹配；自然语言动作、验收和取舍须有业务含义，单有格式不代表方案有效。说明未来目标是拟议方向，当前基线、推断与未知分开，计划不等于已执行或已实现。

仅读取本题exec映射到/tmp_workspace的材料，不读GT或评分说明、不扫描真实用户目录。原输入只读，不删除、移动或覆盖；所有新交付只放results。离线完成，不联网安装、不访问真实账号、不发送消息、不调用真实付费接口。

## Expected Behavior

从三份原始材料复算现状、保留未知和冲突边界，形成可测目标与资源/依赖可行的行动方案，支持合理多解；解释依据与取舍。L2仅设计预估。

## Grading Criteria

### Automated group

- [ ] `business_correctness`: 把规划改为有目标、基线、动作、责任、验收和时间边界的行动表；每项指标有可测定义，不承诺材料无法支持的增长。
- [ ] `boundary_cases`: 逐项识别并正确处理：换措辞仍不可验收；虚构基线；动作与目标无关。以独立反例验证，不只检索关键词。
- [ ] `delivery_integrity`: 全部要求的产物可解析/可使用，跨产物关键事实一致；保护文件与输入未改变。
- [ ] `evidence_binding`: 来源/验证记录定位到实际材料、产物或最终候选源码；自述已运行不能代替独立验证。

### Judge group

- [ ] `decision_grounding`: 针对“模糊工作规划转可衡量行动方案”的结论、取舍和未决项是否由本题材料/独立oracle支持。
- [ ] `usable_handoff`: 下游能否据交付物复核和继续办理本题业务，而非依赖聊天中的未落盘解释。

## Automated Checks

```python
def grade(**kwargs) -> dict:
    from pathlib import Path
    import hashlib, runpy
    root = Path(kwargs.get("workspace_path") or "/tmp_workspace")
    for name, digest in {'grader.py': '1b4473da6064b7b9edec868a6c3633dd8c8464d565ac6928f4d541b00abd9ac7', 'trusted_files.json': 'f4dec1b5454b258e30286d772b91e4e7eab3c562ed58c07c4c38a22fb614bcb3'}.items():
        p = root / "gt" / name
        if p.is_symlink() or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != digest:
            raise RuntimeError("H053_TRUSTED_RULE_MISSING_OR_DRIFT: " + name)
    result = runpy.run_path(str(root / "gt/grader.py"))["grade"](**kwargs)
    return {key: result[key] for key in ("business_correctness", "boundary_cases", "delivery_integrity", "evidence_binding", "overall_score")}
```

## LLM Judge Rubric

### Criterion 1: 决策依据与取舍 (key: decision_grounding, weight: 0.7)

判据：针对“模糊工作规划转可衡量行动方案”的结论、取舍和未决项是否由本题材料/独立oracle支持。 自动规则仅核字段、数值与显式约束，不得以作者baseline分项代替本项语义判断。核实可测定义与验收是否真能验收、动作是否解决对应问题、假设和未知是否恰当，允许有依据的多方案；不按参考措辞或排期硬匹配。

**Score 1.0**: 所有关键结论可定位到支持证据，正确处理本题冲突与限制，无禁止主张。

**Score 0.5**: 主结论成立且无关键矛盾，但遗漏一项非关键解释或定位。

**Score 0.0**: 关键结论被材料反驳、虚构证据，或未完成核心业务判定。

### Criterion 2: 可用交接 (key: usable_handoff, weight: 0.3)

判据：下游能否据交付物复核和继续办理本题业务，而非依赖聊天中的未落盘解释。 自动规则仅核字段、数值与显式约束，不得以作者baseline分项代替本项语义判断。核实可测定义与验收是否真能验收、动作是否解决对应问题、假设和未知是否恰当，允许有依据的多方案；不按参考措辞或排期硬匹配。

**Score 1.0**: 对象、状态/动作、依据和限制均可在规定产物中对应查得，下一步清楚。

**Score 0.5**: 产物可使用但缺一项非关键定位/交接说明，不影响主要办理。

**Score 0.0**: 主要对象/动作无法对应，跨产物矛盾或核心交付不可用。

## Workspace Path

```
workspace/general/challenge/planning_coordination/general_hard_planning_coordination_task_001_measurable_roadmap
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- 完整继承蓝图order53，L2设计预估；纯文本，非编码主任务，离线。
- 75%自动规则仅核可复算字段与显式约束，25%独立Judge负责语义质量；作者Worker baseline不是hybrid最终成绩。
- 原生Office实际重算、数值扰动、文档渲染在独立派生目录，缺可信GT/环境/合法未支持表示形成typed评测异常。
- 输入保护只扣所属delivery子项，不全局清零；不可凭最终状态证明没有瞬时越界。
- 四客户端兼容仍requires_preflight，未做真实Harness/model/Judge/finalize；难度/区分度未实测；模型复核不是人类专家。
- 900仅任务元数据，不设置候选总执行截止。
