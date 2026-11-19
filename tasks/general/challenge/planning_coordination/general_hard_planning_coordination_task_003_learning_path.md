---
id: general_hard_planning_coordination_task_003_learning_path
name: 时间预算约束下的成长路径
category: planning_coordination
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
    - path: results/learning_plan.xlsx
      role: candidate_deliverable
    - path: results/portfolio.docx
      role: candidate_deliverable
scoring_runtime:
  office: true
  office_render: true
dataset_report: {"category": "planning_coordination", "category_name": "规划决策与项目协作", "category_order": 5, "checkpoint_capabilities": {"automated.boundary_cases": ["reasoning_planning"], "automated.business_correctness": ["reasoning_planning"], "automated.delivery_integrity": ["verification_delivery"], "automated.evidence_binding": ["verification_delivery"], "llm_judge.decision_grounding": ["reasoning_planning"], "llm_judge.usable_handoff": ["verification_delivery"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-challenge"}
---

# 时间预算约束下的成长路径

## Prompt

请形成2027-01至2028-12两年按月成长计划，满足课程/项目先修、逐周时间与费用上限，把学习、作品、实习准备和实践串成可检查里程碑。不要创建定时提醒、自动任务或日历事件。

只读输入：/tmp_workspace/profile.md（起点、目标、选择与未知）；/tmp_workspace/courses.csv（17个活动的先修、时长、费用及班期/期限）；/tmp_workspace/availability.xlsx（96给定规划周、24月的时间与费用上限）；/tmp_workspace/milestones.md（M01-M04作品验收、调整与数据交接）。每月固定4个给定规划周，不用真实月历补充时间。考试周0是不可用，不能用月平均掩盖周峰值。

只在/tmp_workspace/results交付learning_plan.xlsx和portfolio.docx。以P1/P2/P3/J1/L1的作品与交接为可检查机会，逐项核对必要时间/小时是否在真实周预算内得到提供，并区分先修顺序与能力证据。完整保留mandatory活动，MODEL_ONE与PRACTICE_ONE各选一项，按实际分配推导起止周，先修必须前一周或更早完成；允许材料支持的不同资源、排期、并行与有依据的额外小时。费用在首次正时间投入月一次记入，遵守月度、年度700/500及两年900上限。Q1机会/Q2资格未知，I1及依赖L1保留conditional且计完整时间；F1只是内部实践，不是实习经历，J1仍保留。课程/小时数/证书不能直接证明能力。

按M03保留activities/allocations/weekly/monthly/milestones/settings有表头原生记录及字段，可同页/多页、页名与列序自由。中文/英文列名均可：activity_id=活动编号，name=名称，kind=类型，first_week=首次规划周，last_week=末次规划周，hours_required=材料小时，planned_hours=计划小时，fee=费用，status=状态，prerequisites=先修，acceptance=验收，source_ref=依据，week_id=规划周编号，hours=小时，week_order=规划周序号，month=月份，hours_cap=小时上限，remaining_hours=剩余小时，overload_hours=超出小时，year_fee=当年累计费用，cumulative_fee=两年累计费用，total_fee_remaining=总费用余额，focus=月度重点，criteria=标准编号，evidence_status=证据状态，capability_status=能力状态，adjustment_trigger=调整触发，next_action=下一步，key=键，value=值。首末周可用源周ID或全局1-96序号；无正时间显示unknown，不以0代缺失。完整24个月和96周，含0投入月/周；周小时、余额/超额、活动总小时/起止、月度/年度/两年费用均由原始分配与一次费用驱动，修改小时、正时间端点和费用后应更新。可用辅助列和不同公式，不要求固定模板或参考月份。

portfolio.docx解释作品如何验收、何时调整、资源与时间取舍，以及未知实习条件/内部备选；覆盖M01五项和R01-R12、M04八项fact_id/value事实核对表。evidence_status当前not_assessed、capability_status=not_yet_verified，真实作品能否证明目标能力仍需未来审阅。设置offline_proposal/not_created是计划声明，不能冒充实际动作证据。

source_ref可用profile.md#P01-P05、courses.csv#活动ID、availability.xlsx#weekly@周ID或#monthly@YYYY-MM、milestones.md#M01-M04的真实定位。仅读本题exec映射到/tmp_workspace的材料，不读GT/评分说明、不扫描真实用户目录；原输入不删除、移动、覆盖，所有新交付只放results。离线，不访问账号、不发消息、不投递、不付费或联网安装。事实、推断与未知分开，不虚构测评、实习或就业结果。

## Expected Behavior

在两年24月/96规划周中按先修和真实周/费用上限连接学习、作品与实习准备/条件性实践，给可计算原生计划与有据验收/调整；课程不等于能力，不建提醒。L3仅设计预估。

## Grading Criteria

### Automated group

- [ ] `business_correctness`: 形成两年按月成长计划，满足课程前置、周时间与费用上限；把学习、作品和实习串为可检查里程碑，不创建定时提醒。
- [ ] `boundary_cases`: 逐项识别并正确处理：按月堆任务超时；缺前置；完成课程等同具备能力。以独立反例验证，不只检索关键词。
- [ ] `delivery_integrity`: 全部要求的产物可解析/可使用，跨产物关键事实一致；保护文件与输入未改变。
- [ ] `evidence_binding`: 来源/验证记录定位到实际材料、产物或最终候选源码；自述已运行不能代替独立验证。

### Judge group

- [ ] `decision_grounding`: 针对“时间预算约束下的成长路径”的结论、取舍和未决项是否由本题材料/独立oracle支持。
- [ ] `usable_handoff`: 下游能否据交付物复核和继续办理本题业务，而非依赖聊天中的未落盘解释。

## Automated Checks

```python
def grade(**kwargs) -> dict:
    from pathlib import Path
    import hashlib, runpy
    root = Path(kwargs.get("workspace_path") or "/tmp_workspace")
    for name, digest in {'grader.py': 'edbdd2c40f8d825d0010dd48d4141bdd19f87695168f1f838f2a2a0de12c5fbe', 'trusted_files.json': '05966c6bf1444a8d500a1a99dd64af0b3721b03bb82661c13ec0d4e9aef2bfa4'}.items():
        p = root / "gt" / name
        if p.is_symlink() or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != digest:
            raise RuntimeError("H055_TRUSTED_RULE_MISSING_OR_DRIFT: " + name)
    result = runpy.run_path(str(root / "gt/grader.py"))["grade"](**kwargs)
    return {key: result[key] for key in ("business_correctness", "boundary_cases", "delivery_integrity", "evidence_binding", "overall_score")}
```

## LLM Judge Rubric

### Criterion 1: 成长路径依据与取舍 (key: decision_grounding, weight: 0.7)

判据：针对“时间预算约束下的成长路径”的结论、取舍和未决项是否由本题材料/独立oracle支持。 核验作品/验收和调整是否真能支持目标能力，不把课程完成、小时数或标签当作能力证据；核查实习未知/内部备选是否坦诚可用。自动字段与数字结果不是本项语义评分，不匹配作者参考措辞或月份。

**Score 1.0**: 所有关键结论可定位到支持证据，正确处理本题冲突与限制，无禁止主张。

**Score 0.5**: 主结论成立且无关键矛盾，但遗漏一项非关键解释或定位。

**Score 0.0**: 关键结论被材料反驳、虚构证据，或未完成核心业务判定。

### Criterion 2: 作品验收与后续交接 (key: usable_handoff, weight: 0.3)

判据：下游能否据交付物复核和继续办理本题业务，而非依赖聊天中的未落盘解释。 核验作品/验收和调整是否真能支持目标能力，不把课程完成、小时数或标签当作能力证据；核查实习未知/内部备选是否坦诚可用。自动字段与数字结果不是本项语义评分，不匹配作者参考措辞或月份。

**Score 1.0**: 对象、状态/动作、依据和限制均可在规定产物中对应查得，下一步清楚。

**Score 0.5**: 产物可使用但缺一项非关键定位/交接说明，不影响主要办理。

**Score 0.0**: 主要对象/动作无法对应，跨产物矛盾或核心交付不可用。

## Workspace Path

```
workspace/general/challenge/planning_coordination/general_hard_planning_coordination_task_003_learning_path
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- 完整order55四输入两输出、两年24月/96周；L3预估、pure-text/offline/noncoding-primary。
- Hybrid .75/.25及自动.55/.25/.15/.05不变；作者baseline仅自动组件，不代替作品语义Judge，不造hybrid成绩。
- 源先行原生XLSX/CSV/MD双路原始计算；四课程×实践选择均可行，不匹配唯一月份/费用模板，允许有据多解。
- 周时间与计算/记录属business，先修/费用/能力假定/未知实习属boundary；输入保护只扣delivery子项。
- 缺GT/运行环境/合法未支持复杂表示为typed异常，无候选零分。
- 不运行真实候选Harness/model/Judge/finalize、不建提醒/消息/账户操作/网络安装；模型复核非人类专家。
- 四客户端requires_preflight，难度/区分度未实测；900仅任务元数据，不设置候选总执行截止。
