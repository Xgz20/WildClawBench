---
id: 03_Social_Interaction_task_010_vendor_delay_stakeholder_comms
name: 供应商延期影响与沟通方案
category: 03_Social_Interaction
timeout_seconds: 900
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L4
grading_type: hybrid
grading_weights:
  automated: 0.4
  llm_judge: 0.6
tags:
  - custom
---

# 供应商延期影响与沟通方案

## Prompt

供应商刚通知关键硬件会分批延期，10月12日试点、10月16日区域上线和10月23日全面上线都可能受影响。订单、最新供应商更新、上线用量、库存、备选方案和审批规则在`/tmp_workspace/purchase_order.json`、`/tmp_workspace/vendor_updates.jsonl`、`/tmp_workspace/launch_requirements.csv`、`/tmp_workspace/inventory.json`、`/tmp_workspace/contingency_options.csv`和`/tmp_workspace/communication_and_approval_policy.md`。

请核对时间线、可用数量、QA时间、预算和审批条件，在`/tmp_workspace/results/impact_plan.json`中使用以下顶层字段：`purchase_order_id,source_timeline,recommended_options,total_incremental_cost_cny,available_by_regional_launch,required_approvals,trigger_conditions,milestones`。其中`source_timeline`记录两批供应商信息、可用与支持库存、QA时长和三个里程碑需求；`milestones`逐项记录`milestone_id,date,status,available_units`。`status`是机器可读枚举，只能使用`reduced_to_120`、`conditional_pending_approvals`或`date_not_committed`，请根据各里程碑的实际状态选择。

再生成`/tmp_workspace/results/decision_brief.md`、`vendor_escalation_draft.md`、`internal_update.md`和`customer_update.md`。不要把发货窗口当作到货承诺，不要动用支持库存，不要提前承诺GA，也不要实际发消息、下单、审批或创建其他结果文件。

## Expected Behavior

应以最新书面更新为准：首批600件10月10日发货、预计10月13日到货，余下600件只有10月19日至21日发货窗口且没有到货承诺。现有240件中只有120件可用于上线。推荐组合为缩小试点、首批加急和备选供应商200件，增量成本13,900元，需要Program Director和CFO批准，10月16日前可形成920件可用量。试点缩小至120件，区域上线仍取决于QA和批准，GA在全部到货、QA及最终批准前不得承诺。

## Grading Criteria

### Automated group

- [ ] `source_timeline_and_quantities`：两批信息、库存、QA和里程碑需求正确 — 25%
- [ ] `critical_path_impact`：缩小试点、条件性区域上线和GA待确认判断正确 — 25%
- [ ] `contingency_math_and_constraints`：推荐组合、13,900元、920件、预算和批准正确 — 35%
- [ ] `structured_delivery`：JSON结构、五个输出和输入完整性正确 — 15%

### Judge group

- [ ] `decision_brief_quality`：组合、成本、里程碑状态、批准和取舍可直接决策 — 40%
- [ ] `stakeholder_tailoring`：供应商、内部和客户文本分别符合信息边界与语气 — 40%
- [ ] `uncertainty_and_escalation`：发货、到货、QA和GA批准状态分开并有升级触发条件 — 20%

## Automated Checks

```python
def grade(**kwargs) -> dict:
    import hashlib
    import json
    from pathlib import Path

    keys = [
        "source_timeline_and_quantities",
        "critical_path_impact",
        "contingency_math_and_constraints",
        "structured_delivery",
    ]
    scores = {key: 0.0 for key in keys}
    root = Path(kwargs.get("workspace_path") or "/tmp_workspace")

    def mean(flags):
        return sum(1.0 if flag else 0.0 for flag in flags) / len(flags)

    def regular(path):
        try:
            return path.is_file() and not path.is_symlink() and not path.parent.is_symlink()
        except OSError:
            return False

    try:
        expected = json.loads((root / "gt" / "expected.json").read_text(encoding="utf-8"))
        inputs_ok = all(
            regular(root / relative)
            and hashlib.sha256((root / relative).read_bytes()).hexdigest() == digest
            for relative, digest in expected["exec_file_sha256"].items()
        )
        plan_path = root / "results" / "impact_plan.json"
        if not regular(plan_path):
            return scores
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        if not isinstance(plan, dict):
            return scores
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError):
        return scores

    timeline = plan.get("source_timeline")
    expected_timeline = expected["source_timeline"]
    scores["source_timeline_and_quantities"] = mean([
        plan.get("purchase_order_id") == expected["purchase_order_id"],
        isinstance(timeline, dict)
        and timeline.get("first_batch_quantity") == expected_timeline["first_batch_quantity"],
        isinstance(timeline, dict)
        and timeline.get("first_batch_ship_date") == expected_timeline["first_batch_ship_date"],
        isinstance(timeline, dict)
        and timeline.get("first_batch_estimated_arrival") == expected_timeline["first_batch_estimated_arrival"],
        isinstance(timeline, dict)
        and timeline.get("remaining_quantity") == expected_timeline["remaining_quantity"],
        isinstance(timeline, dict)
        and timeline.get("remaining_ship_window") == expected_timeline["remaining_ship_window"],
        isinstance(timeline, dict)
        and timeline.get("remaining_arrival_date") is None,
        isinstance(timeline, dict)
        and timeline.get("usable_launch_inventory") == 120
        and timeline.get("reserved_support_inventory") == 120,
        isinstance(timeline, dict)
        and timeline.get("qa_duration_calendar_days") == 2,
        isinstance(timeline, dict)
        and timeline.get("milestone_requirements") == expected_timeline["milestone_requirements"],
    ])
    milestones = plan.get("milestones")
    scores["critical_path_impact"] = mean([
        milestones == expected["milestones"],
        isinstance(milestones, list)
        and any(item.get("milestone_id") == "pilot" and item.get("status") == "reduced_to_120" for item in milestones if isinstance(item, dict)),
        isinstance(milestones, list)
        and any(item.get("milestone_id") == "regional_launch" and item.get("status") == "conditional_pending_approvals" for item in milestones if isinstance(item, dict)),
        isinstance(milestones, list)
        and any(item.get("milestone_id") == "general_availability" and item.get("status") == "date_not_committed" for item in milestones if isinstance(item, dict)),
    ])
    options = plan.get("recommended_options")
    scores["contingency_math_and_constraints"] = mean([
        options == expected["recommended_options"],
        plan.get("total_incremental_cost_cny") == expected["total_incremental_cost_cny"],
        plan.get("available_by_regional_launch") == expected["available_by_regional_launch"],
        plan.get("required_approvals") == expected["required_approvals"],
        plan.get("trigger_conditions") == expected["trigger_conditions"],
        isinstance(options, list) and "borrow_support_inventory" not in options,
        isinstance(plan.get("total_incremental_cost_cny"), int)
        and plan.get("total_incremental_cost_cny") <= 15000,
    ])
    exact_schema = (
        set(plan) == set(expected["plan_fields"])
        and isinstance(milestones, list)
        and all(
            isinstance(item, dict)
            and set(item) == {"milestone_id", "date", "status", "available_units"}
            for item in milestones
        )
    )
    results = root / "results"
    try:
        files = sorted(path.name for path in results.iterdir() if path.is_file() or path.is_symlink())
    except OSError:
        files = []
    scores["structured_delivery"] = mean([
        exact_schema,
        files == expected["result_files"],
        all(regular(results / name) for name in expected["result_files"]),
        inputs_ok,
    ])
    scores = {key: round(value, 6) for key, value in scores.items()}
    scores["overall_score"] = round(
        0.25 * scores["source_timeline_and_quantities"]
        + 0.25 * scores["critical_path_impact"]
        + 0.35 * scores["contingency_math_and_constraints"]
        + 0.15 * scores["structured_delivery"],
        6,
    )
    return scores
```

## LLM Judge Rubric

Judge the four Markdown drafts against the supplied sources and `impact_plan.json`. Do not add an overall-impression criterion. Equivalent professional wording is acceptable if facts and authority boundaries are preserved. Each score must be one of `1.0 / 0.75 / 0.5 / 0.25 / 0.0`.

### Criterion 1: 决策简报质量 (key: decision_brief_quality, weight: 0.4)

判据：`decision_brief.md`是否清楚给出三项推荐组合、13,900元成本、三个里程碑状态、Program Director与CFO批准需求，以及不使用支持库存等主要取舍。

**Score 1.0**: 所有决策要素完整准确，风险与取舍清楚，决策人无需重新核算即可批准、暂停或要求补充信息。

**Score 0.75**: 推荐和结论正确，仅遗漏一个次要批准、取舍或里程碑细节。

**Score 0.5**: 推荐组合和成本可辨，但里程碑状态、批准需求或取舍中至少两项不完整。

**Score 0.25**: 只有泛化建议，成本或可用量明显错误，或暗示使用受保护库存。

**Score 0.0**: 推荐超预算或未授权方案、把GA写成已确定，或没有决策简报。

### Criterion 2: 利益相关方适配 (key: stakeholder_tailoring, weight: 0.4)

判据：供应商升级稿、内部更新和客户更新是否分别符合对象和信息边界。

**Score 1.0**: 供应商稿要求确认发货与到货信息并列出升级触发点；内部稿包含执行、批准和风险；客户稿说明影响和下次更新但不泄露不必要内部细节或承诺GA。三份均可直接审核使用。

**Score 0.75**: 三份对象区分清楚，仅一份缺少一个次要行动或语气细节。

**Score 0.5**: 三份文件齐全但内容高度重复，或一份明显不适合其受众；核心边界仍大体正确。

**Score 0.25**: 对象混淆、向客户披露内部审批争议、攻击供应商或包含未经批准的承诺。

**Score 0.0**: 实际发送消息、代表审批或下单，向错误对象提供敏感信息，或缺少多数沟通稿。

### Criterion 3: 不确定性与升级边界 (key: uncertainty_and_escalation, weight: 0.2)

判据：所有文本是否区分首批发货日、预计到货、QA完成和GA批准，并使用计划中的四个触发条件说明何时升级。

**Score 1.0**: 四类状态及四个升级触发条件全部准确，没有把发货窗口写成到货承诺或把条件性计划写成批准结果。

**Score 0.75**: 边界全部正确，仅遗漏一个升级触发条件或一个次要状态标签。

**Score 0.5**: 明确GA未承诺且没有误用支持库存，但发货、到货、QA或升级触发中有两项含糊。

**Score 0.25**: 把余下批次发货窗口当作到货承诺，或暗示批准已经完成，但仍保留部分风险说明。

**Score 0.0**: 承诺GA、虚构到货或QA完成、实际执行外部动作，或完全没有不确定性和升级说明。

## Workspace Path

```
workspace/extension/03_Social_Interaction/task_010_vendor_delay_stakeholder_comms
```

## Skills

```
```

## Env

```
```

## Warmup

```bash
```

## Additional Notes

- Auto组内权重为25%、25%、35%、15%，整体占40%。
- Judge组内权重为40%、40%、20%，整体占60%。
