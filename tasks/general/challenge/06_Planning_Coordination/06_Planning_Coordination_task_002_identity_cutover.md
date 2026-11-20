---
id: 06_Planning_Coordination_task_002_identity_cutover
name: 账号体系切换的依赖与验收排期
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
    - path: results/cutover_plan.xlsx
      role: candidate_deliverable
    - path: results/runbook.docx
      role: candidate_deliverable
    - path: results/risks.json
      role: candidate_deliverable
scoring_runtime:
  office: true
  office_render: true
dataset_report: {"category": "planning_coordination", "category_name": "规划决策与项目协作", "category_order": 5, "checkpoint_capabilities": {"automated.boundary_cases": ["reasoning_planning"], "automated.business_correctness": ["reasoning_planning"], "automated.delivery_integrity": ["verification_delivery"], "automated.evidence_binding": ["verification_delivery"], "llm_judge.decision_grounding": ["reasoning_planning"], "llm_judge.usable_handoff": ["verification_delivery"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-challenge"}
---

# 账号体系切换的依赖与验收排期

## Prompt

请安排账号体系切换的依赖、资源与验收计划，从账号校验、权限融合到跳转、免密、测试、培训和未来退役，给出关键路径、切换/回滚门槛及缓冲。只制作计划，不执行真实账号操作。

输入：/tmp_workspace/work_items.csv（14项工作、身份范围、依赖、连续工作日工期和逐日角色最低小时）；/tmp_workspace/resources.xlsx（逐日角色容量及不可用日期）；/tmp_workspace/acceptance.md（A01-A07身份/环境/切换与回滚/未知批准/保留期及交付结构）；/tmp_workspace/calendar.csv（唯一固定工作日历）。全部只读，不按真实节假日猜补未来日历。

仅在/tmp_workspace/results交付cutover_plan.xlsx、runbook.docx、risks.json。以T04身份授权就绪、T11切换、T12验证、T13交接为四个里程碑，分别核对源材料规定的必需前置和实际日期。缺前置只阻断实际依赖它的里程碑；新增无关声明不能让无关业务归零。条件性排期可满足依赖，不代表当前获得执行批准。完整保留T01-T14，T01-T13有可行排期；T14明确deferred、日期空白及待确认项。覆盖EMP/VENDOR/SERVICE的不同关联和权限边界，区分SANDBOX/TRAINING与未来PROD。所有依赖在前项完成后的下一个给定工作日开始；共享租户不可并行、逐日容量不可平均或跨日借用，待批动作仍预留工时。

按A06保留schedule/loads/cpm三类有表头原生记录和字段。可同页/多页，页名和列序不限，中文/英文列名均可；对应中文为任务编号/任务说明/责任角色/环境/身份群体/开始日期/结束日期/状态/前置依赖/验收/依据，任务编号/日期/角色/小时，任务编号/工期/最早开始偏移/最早完成偏移/最晚开始偏移/最晚完成偏移/总时差/关键标记。CPM用原始T01-T13 DAG和工作日偏移，工期改变后前后推、时差和关键标记应更新；实际日期另核资源、共享租户及窗口，不把DAG偏移直接当真实日期。

risks.json按A06给出窗口可行性、所选窗口、准备与完成缓冲、至少一条真实关键路径、Q1未知批准、Q2/T14退役边界、三类回滚门槛与前置、身份控制和未决责任。可行窗口只表示存在条件性排期，不能据此授予批准；当前必须no_go。runbook.docx交接前置未满足的no-go、切换顺序、任一门槛触发的暂停/回滚、恢复验证及退役不可逆边界，附A07七项fact_id/value事实核对表。不要把计划写成已经执行，不用“必要时回滚”替代门槛。

允许满足源约束的不同排期、合理并行、备选窗口、文案与至少一条有效关键路径，不按参考日期/措辞匹配。日期可原生日期或无歧义ISO文本；JSON可含BOM、字段重排、有限数字字符串与百分比阈值。source_ref定位到真实work_items.csv#Txx、resources.xlsx#capacity@YYYY-MM-DD、calendar.csv#YYYY-MM-DD或acceptance.md#A01-A07。中文JSON键可按下面对照（代码值保持材料规定）使用：mode=模式，current_go=当前执行结论，selected_window=选定窗口，window_feasibility=窗口可行性，ready_buffer_workdays=准备缓冲工作日，completion_buffer_workdays=完成缓冲工作日，critical_paths=关键路径，approval=切换批准，retirement=退役，rollback=回滚，identity_controls=身份控制，unresolved=未决项，window_id=窗口编号，feasible=可行，reason=原因，id=编号，status=状态，owner=责任角色，review_by=复核截止，task_id=任务编号，approval_id=批准编号，approval_status=批准状态，minimum_full_workdays=最少完整工作日，earliest_date_status=最早日期状态，earliest_date=最早日期，max_minutes=最长分钟，interval_minutes=观察间隔分钟，scope=范围，snapshot_required=需快照，validation_task=验证任务，triggers=门槛，metric_id=指标编号，operator=比较符，threshold=阈值，consecutive_checks=连续次数，cohort=身份群体，join_key=关联主键，forbid_email_only_merge=禁止仅邮箱合并，expires_on_contract=随合同到期，inherit_employee_access=继承员工权限，interactive_passwordless=交互免密，owner_review_required=需责任人复核，secret_rotation=秘密轮换，condition=条件，next_action=下一步，source_ref=依据。

仅读本题exec映射到/tmp_workspace的材料，不读GT/评分说明、不扫描真实用户目录。所有新交付只放results，原输入不删除、移动或覆盖。离线，不访问真实账号、不发消息、不调用付费接口，不联网安装依赖。事实、推断和未知分开；缺前置、需确认与可回滚范围不能凭空乐观。

## Expected Behavior

从独立DAG、给定日历和逐日角色容量安排身份/权限、切换、测试和培训；保留未知批准no-go与不可逆退役确认边界，提供可计算关键路径、门槛和跨产物一致交接。L3仅设计预估。

## Grading Criteria

### Automated group

- [ ] `business_correctness`: 安排账号校验到系统切换、测试、培训的依赖计划，给出关键路径、回滚点与每项验收；资源和日期必须可行。
- [ ] `boundary_cases`: 逐项识别并正确处理：先切换后校验权限；资源超配；无回滚门槛。以独立反例验证，不只检索关键词。
- [ ] `delivery_integrity`: 全部要求的产物可解析/可使用，跨产物关键事实一致；保护文件与输入未改变。
- [ ] `evidence_binding`: 来源/验证记录定位到实际材料、产物或最终候选源码；自述已运行不能代替独立验证。

### Judge group

- [ ] `decision_grounding`: 针对“账号体系切换的依赖与验收排期”的结论、取舍和未决项是否由本题材料/独立oracle支持。
- [ ] `usable_handoff`: 下游能否据交付物复核和继续办理本题业务，而非依赖聊天中的未落盘解释。

## Automated Checks

```python
def grade(**kwargs) -> dict:
    from pathlib import Path
    import hashlib, runpy
    root = Path(kwargs.get("workspace_path") or "/tmp_workspace")
    for name, digest in {'grader.py': '925bda850f472d42d025093bb53e289885a3101b9275010f485b5f9e9c4cd55a', 'trusted_files.json': '75baa729fdf3139e95709f05c2969bbc82ab921f097a4275f66cd97ffafcc7ee'}.items():
        p = root / "gt" / name
        if p.is_symlink() or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != digest:
            raise RuntimeError("H054_TRUSTED_RULE_MISSING_OR_DRIFT: " + name)
    result = runpy.run_path(str(root / "gt/grader.py"))["grade"](**kwargs)
    return {key: result[key] for key in ("business_correctness", "boundary_cases", "delivery_integrity", "evidence_binding", "overall_score")}
```

## LLM Judge Rubric

### Criterion 1: 决策依据与取舍 (key: decision_grounding, weight: 0.7)

判据：针对“账号体系切换的依赖与验收排期”的结论、取舍和未决项是否由本题材料/独立oracle支持。 自动字段/约束分项不替代语义判断。检查三身份权限差异、未知批准、动作验收、回滚先后及不可逆边界、资源取舍和继续办理是否清楚；允许源约束下多解，不按参考措辞或排期硬匹配。

**Score 1.0**: 所有关键结论可定位到支持证据，正确处理本题冲突与限制，无禁止主张。

**Score 0.5**: 主结论成立且无关键矛盾，但遗漏一项非关键解释或定位。

**Score 0.0**: 关键结论被材料反驳、虚构证据，或未完成核心业务判定。

### Criterion 2: 切换回滚交接可用性 (key: usable_handoff, weight: 0.3)

判据：下游能否据交付物复核和继续办理本题业务，而非依赖聊天中的未落盘解释。 自动字段/约束分项不替代语义判断。检查三身份权限差异、未知批准、动作验收、回滚先后及不可逆边界、资源取舍和继续办理是否清楚；允许源约束下多解，不按参考措辞或排期硬匹配。

**Score 1.0**: 对象、状态/动作、依据和限制均可在规定产物中对应查得，下一步清楚。

**Score 0.5**: 产物可使用但缺一项非关键定位/交接说明，不影响主要办理。

**Score 0.0**: 主要对象/动作无法对应，跨产物矛盾或核心交付不可用。

## Workspace Path

```
workspace/general/challenge/06_Planning_Coordination/06_Planning_Coordination_task_002_identity_cutover
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- 完整保留order54四输入三输出、14项工作、L3预估、pure-text/offline/noncoding-primary。
- Hybrid .75/.25；自动四项 .55/.25/.15/.05，语义Judge独立；作者baseline不是hybrid成绩。
- source-first两路直接读取CSV/原生资源表/MD，穷举窗口可行性与独立下界/排程见证，不把参考日期作白名单。
- 缺可信GT/Office/合法未支持复杂表示typed异常；输入保护仅所属delivery子项，不全局清零。
- 不运行真实身份、账号、发送消息、网络安装、候选Harness/model/Judge/finalize；模型复核非人类专家。
- 四客户端requires_preflight，难度/区分度未实测；900只为任务元数据，不设置候选总执行截止。
