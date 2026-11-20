---
id: 06_Planning_Coordination_task_004_release_go_no_go
name: 发布筹备的多约束决策与备选路径
category: planning_coordination
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
    - path: results/release_plan.xlsx
      role: candidate_deliverable
    - path: results/decision.docx
      role: candidate_deliverable
    - path: results/alternatives.json
      role: candidate_deliverable
scoring_runtime:
  office: true
  office_render: true
dataset_report: {"category": "planning_coordination", "category_name": "规划决策与项目协作", "category_order": 5, "checkpoint_capabilities": {"automated.boundary_cases": ["reasoning_planning"], "automated.business_correctness": ["reasoning_planning"], "automated.delivery_integrity": ["verification_delivery"], "automated.evidence_binding": ["verification_delivery"], "llm_judge.decision_grounding": ["reasoning_planning"], "llm_judge.usable_handoff": ["verification_delivery"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-challenge"}
---

# 发布筹备的多约束决策与备选路径

## Prompt

请完成以下工作：基于最新有效变更给出可执行的发布计划和go/no-go判断，展示关键路径、预算、风险和备选方案；不可行时明确最小阻塞集。

输入材料：
- /tmp_workspace/work_breakdown.csv：18项准备任务与可替代路径
- /tmp_workspace/resources.xlsx：人力、场地和预算
- /tmp_workspace/changes.jsonl：4次需求变更
- /tmp_workspace/gates.md：发布硬门槛和裁决顺序

交付：
- /tmp_workspace/results/release_plan.xlsx：依赖/资源/预算
- /tmp_workspace/results/decision.docx：发布判断及依据
- /tmp_workspace/results/alternatives.json：备选路径与触发条件

约束：
- 仅读取本题exec映射到/tmp_workspace的材料；GT和评分说明不提供给候选。
- 不访问真实账号、不发送消息、不调用真实付费接口；输入和保护文件保持不变。
- 结论区分事实、推断和未知；不得虚构缺失信息。
- 所有新交付写入/tmp_workspace/results；原输入只读，不删除或覆盖。
- 离线完成，不访问网络。

完整遵循gates.md的G01-G07交付契约。18项源任务、4条事件都要裁决；按seq与状态/签署权限折叠，不能把最后一行、最大seq的未批准提案或旧预算当最新有效状态。范围批准和发布执行批准不同。先给原目标W0的当前go/no-go及材料定义的跨路径最小未满足硬门槛集，再给至少一个可排且预算内的后移方案完整排程。六个窗口/路径组合分别判断时间可排性、费用与条件性可行，不能只比较某份参考。T12是否必须及有效工期由变更裁决，不按基础CSV单独判断。

工作簿schedule保留全部18项，所选17项以给定工作日、源先修、逐日最低小时和角色/场地容量排程；未选路径日期留空、工时和费用不纳入，T15-T17保持conditional。同时交loads、cpm、costs、budget表。页名与列序自由，同排表用空白列区分；对应中文表头为：task_id=任务编号，summary=任务说明，owner=责任角色，venue=场地，start_date=开始日期，end_date=结束日期，status=状态，dependencies=前置依赖，acceptance=验收，source_ref=依据，date=日期，role=角色，hours=小时，duration=工期，es=最早开始偏移，ef=最早完成偏移，ls=最晚开始偏移，lf=最晚完成偏移，total_float=总时差，critical=关键标记，selected=选中，fixed_cost=固定费用，extended_cost=计入费用，key=键，value=值。CPM是有效所选源DAG的无资源下界，不能直接当实际日期。工期和固定费用为可计算驱动，相关前后推、时差、关键标记、总费和余额改变时须真实联动。

alternatives.json按G06列有效事件/范围、selected_path/window、current_go、六行window_paths、minimum_blocker_sets、至少一条关键路径、未知批准、两路径触发条件、风险与未决责任。最小集评原目标W0，明确不是最小不可满足子公式；不可用风险清单替代门槛裁决。decision.docx说明no-go依据、方案/预算/关键路径和资源取舍、停止条件与下一步，附G07十项fact_id/value事实表，三产物一致。事实、推断、未知与未来条件性动作区分，不把计划排出当作验收/批准完成。允许不同合法排期、后移窗口及说明，不硬匹配参考措辞。来源定位按G05。不实际发布、支付、创建提醒或发消息，不联网或安装依赖。

## Expected Behavior

按最新有效事件折叠范围和预算，独立核六个路径/窗口，给原目标最小未满足门槛与no-go，交可复算且受源资源/先修/费用约束的后移计划、风险和备选责任。L4仅设计预估。

## Grading Criteria

### Automated group

- [ ] `business_correctness`: 基于最新有效变更给出可执行的发布计划和go/no-go判断，展示关键路径、预算、风险和备选方案；不可行时明确最小阻塞集。
- [ ] `boundary_cases`: 逐项识别并正确处理：忽略后续范围变更；用加班假设掩盖不可行；方案与预算矛盾。以独立反例验证，不只检索关键词。
- [ ] `delivery_integrity`: 全部要求的产物可解析/可使用，跨产物关键事实一致；保护文件与输入未改变。
- [ ] `evidence_binding`: 来源/验证记录定位到实际材料、产物或最终候选源码；自述已运行不能代替独立验证。

### Judge group

- [ ] `decision_grounding`: 针对“发布筹备的多约束决策与备选路径”的结论、取舍和未决项是否由本题材料/独立oracle支持。
- [ ] `usable_handoff`: 下游能否据交付物复核和继续办理本题业务，而非依赖聊天中的未落盘解释。

## Automated Checks

```python
def grade(**kwargs) -> dict:
    from pathlib import Path
    import hashlib, runpy
    root = Path(kwargs.get("workspace_path") or "/tmp_workspace")
    for name, digest in {'grader.py': 'a185665d397349cb6177cd6de8cb14b4356f211c69e6141278f7eb008227189a', 'trusted_files.json': 'e69d3fee6bbf519cc526e28c3f8d7293b2190662332839a8fa0ea8f30ca26f66'}.items():
        p = root / "gt" / name
        if p.is_symlink() or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != digest:
            raise RuntimeError("H056_TRUSTED_RULE_MISSING_OR_DRIFT: " + name)
    result = runpy.run_path(str(root / "gt/grader.py"))["grade"](**kwargs)
    return {key: result[key] for key in ("business_correctness", "boundary_cases", "delivery_integrity", "evidence_binding", "overall_score")}
```

## LLM Judge Rubric

### Criterion 1: 决策依据与取舍 (key: decision_grounding, weight: 0.7)

判据：针对“发布筹备的多约束决策与备选路径”的结论、取舍和未决项是否由本题材料/独立oracle支持。 需检查有效变更、scope批准与执行批准的区分、最小阻塞集定义、无资源CPM和实际资源的区别、预算差额与备选条件/风险责任。结构字段正确不替代语义判断，允许源约束多解。

**Score 1.0**: 所有关键结论可定位到支持证据，正确处理本题冲突与限制，无禁止主张。

**Score 0.5**: 主结论成立且无关键矛盾，但遗漏一项非关键解释或定位。

**Score 0.0**: 关键结论被材料反驳、虚构证据，或未完成核心业务判定。

### Criterion 2: 发布计划交接可用性 (key: usable_handoff, weight: 0.3)

判据：下游能否据交付物复核和继续办理本题业务，而非依赖聊天中的未落盘解释。 需检查有效变更、scope批准与执行批准的区分、最小阻塞集定义、无资源CPM和实际资源的区别、预算差额与备选条件/风险责任。结构字段正确不替代语义判断，允许源约束多解。

**Score 1.0**: 对象、状态/动作、依据和限制均可在规定产物中对应查得，下一步清楚。

**Score 0.5**: 产物可使用但缺一项非关键定位/交接说明，不影响主要办理。

**Score 0.0**: 主要对象/动作无法对应，跨产物矛盾或核心交付不可用。

## Workspace Path

```
workspace/general/challenge/06_Planning_Coordination/06_Planning_Coordination_task_004_release_go_no_go
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- 完整继承order56四输入三输出、18准备任务、4变更、L4设计估计、纯文本离线且非coding-primary。
- Hybrid .75/.25；自动四项.55/.25/.15/.05；作者规则控制不构成语义/hybrid最终分。
- 源先行两路原始CSV/JSONL/原生资源/门槛读取与独立排程/下界证明；参考不是GT白名单。
- 最小阻塞集按公开有限门槛定义，不冒充MUS；字段与文本质量归语义Judge。
- 缺GT/锁定Office/合法未支持表示typed异常；输入保护只扣delivery。
- 无外部安装、网络、真实发布/账号/消息/付款、候选Harness/model/Judge/finalize；四端仍requires_preflight。
