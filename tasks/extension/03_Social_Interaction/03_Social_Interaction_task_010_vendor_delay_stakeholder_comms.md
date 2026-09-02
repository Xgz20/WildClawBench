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

    # The prompt publishes the top-level contract, but does not require every
    # nested explanatory field to use one particular representation. Normalize
    # the business facts first so a nested, well-evidenced plan is not treated
    # as incorrect merely because it is richer than expected.json.
    import re

    timeline = plan.get("source_timeline")
    expected_timeline = expected["source_timeline"]
    missing = object()

    def pick(mapping, names):
        if not isinstance(mapping, dict):
            return missing
        for name in names:
            if name in mapping:
                return mapping[name]
        return missing

    def token(value):
        if not isinstance(value, str):
            return ""
        return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")

    def normalize_ship_window(value):
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            dates = re.findall(r"20\d{2}-\d{2}-\d{2}", value)
            if len(dates) >= 2:
                return dates[:2]
        return value

    def normalize_timeline(value):
        if not isinstance(value, dict):
            return {}
        normalized = {}

        batches = []
        first = {}
        remaining = {}
        for key in ("batches", "supplier_batches", "vendor_batches"):
            candidate = value.get(key)
            if isinstance(candidate, list):
                batches.extend(item for item in candidate if isinstance(item, dict))
            elif isinstance(candidate, dict):
                for batch_id, item in candidate.items():
                    if not isinstance(item, dict):
                        continue
                    # Preserve a map key such as batch_1/batch_2 when the
                    # nested object itself does not repeat the identifier.
                    if not any(name in item for name in ("batch", "batch_id", "name")):
                        item = {"batch": batch_id, **item}
                    batches.append(item)

        for key in ("first_batch", "batch_1"):
            candidate = value.get(key)
            if isinstance(candidate, dict):
                first = candidate
        for key in ("remaining_batch", "batch_2", "second_batch"):
            candidate = value.get(key)
            if isinstance(candidate, dict):
                remaining = candidate

        for batch in batches:
            raw_label = batch.get("batch") or batch.get("batch_id") or batch.get("name")
            # Some agents serialize the batch number as JSON integer 1/2.
            label = token(raw_label if isinstance(raw_label, str) else str(raw_label or ""))
            if label in {"first", "first_batch", "batch_1", "1"} or "first" in label:
                first = batch
            elif label in {"remaining", "remaining_batch", "second", "second_batch", "batch_2", "2"} or "remaining" in label:
                remaining = batch

        # A latest-update record may carry both batches as flat fields rather
        # than exposing two nested batch objects. Keep those fields as a
        # fallback while allowing an explicitly identified batch to win.
        flat_first = {}
        flat_remaining = {}
        for batch in batches:
            for name in (
                "first_batch_quantity",
                "first_batch_ship_date",
                "first_batch_estimated_arrival",
            ):
                if name in batch:
                    flat_first[name] = batch[name]
            for name in (
                "remaining_quantity",
                "remaining_ship_window",
                "remaining_ship_window_start",
                "remaining_ship_window_end",
                "remaining_arrival_date",
            ):
                if name in batch:
                    flat_remaining[name] = batch[name]
        first = {**flat_first, **first}
        remaining = {**flat_remaining, **remaining}

        def assign(name, mapping, names):
            found = pick(mapping, names)
            if found is not missing and name not in normalized:
                normalized[name] = found

        assign("first_batch_quantity", value, ["first_batch_quantity"])
        assign("first_batch_quantity", first, ["first_batch_quantity", "quantity", "units"])
        assign("first_batch_ship_date", value, ["first_batch_ship_date"])
        assign("first_batch_ship_date", first, ["first_batch_ship_date", "ship_date", "ship_date_start"])
        assign("first_batch_estimated_arrival", value, ["first_batch_estimated_arrival"])
        assign(
            "first_batch_estimated_arrival",
            first,
            [
                "first_batch_estimated_arrival",
                "estimated_arrival",
                "estimated_arrival_date",
                "arrival_date",
            ],
        )
        assign("remaining_quantity", value, ["remaining_quantity"])
        assign("remaining_quantity", remaining, ["remaining_quantity", "quantity", "units"])
        assign("remaining_ship_window", value, ["remaining_ship_window"])
        if "remaining_ship_window" not in normalized:
            start = pick(value, ["remaining_ship_window_start"])
            end = pick(value, ["remaining_ship_window_end"])
            if start is not missing and end is not missing:
                normalized["remaining_ship_window"] = [start, end]
        if "remaining_ship_window" not in normalized:
            start = pick(remaining, ["ship_window_start", "remaining_ship_window_start"])
            end = pick(remaining, ["ship_window_end", "remaining_ship_window_end"])
            if start is not missing and end is not missing:
                normalized["remaining_ship_window"] = [start, end]
        if "remaining_ship_window" not in normalized:
            normalized["remaining_ship_window"] = normalize_ship_window(
                pick(remaining, ["ship_window", "shipping_window"])
            )
        if normalized.get("remaining_ship_window") is missing:
            normalized.pop("remaining_ship_window", None)
        elif "remaining_ship_window" in normalized:
            normalized["remaining_ship_window"] = normalize_ship_window(
                normalized["remaining_ship_window"]
            )

        remaining_arrival = pick(value, ["remaining_arrival_date"])
        if remaining_arrival is missing:
            remaining_arrival = pick(
                remaining,
                [
                    "remaining_arrival_date",
                    "arrival_date",
                    "estimated_arrival",
                    "estimated_arrival_date",
                    "committed_arrival_date",
                ],
            )
        if remaining_arrival is missing:
            commitment = pick(remaining, ["arrival_committed", "arrival_commitment"])
            state = token(remaining.get("status")) if isinstance(remaining, dict) else ""
            if commitment is False or any(
                marker in state
                for marker in ("no_committed_arrival", "uncommitted", "unconfirmed", "no_arrival")
            ):
                remaining_arrival = None
        if remaining_arrival is not missing:
            normalized["remaining_arrival_date"] = remaining_arrival

        inventory = value.get("inventory")
        assign("usable_launch_inventory", value, ["usable_launch_inventory"])
        if "usable_launch_inventory" not in normalized:
            assign("usable_launch_inventory", inventory, ["usable_launch_units", "usable_launch_inventory"])
        assign("reserved_support_inventory", value, ["reserved_support_inventory"])
        if "reserved_support_inventory" not in normalized:
            assign("reserved_support_inventory", inventory, ["reserved_support_units", "reserved_support_inventory"])
        assign(
            "qa_duration_calendar_days",
            value,
            ["qa_duration_calendar_days", "qa_duration_calendar_days_after_arrival"],
        )
        if "qa_duration_calendar_days" not in normalized:
            assign(
                "qa_duration_calendar_days",
                inventory,
                ["qa_duration_calendar_days", "qa_duration_calendar_days_after_arrival"],
            )

        requirements = pick(value, ["milestone_requirements", "milestone_demands"])
        if isinstance(requirements, dict):
            requirement_map = {}
            for milestone_id, item in requirements.items():
                if isinstance(item, dict):
                    units = pick(item, ["cumulative_units_required", "required_units", "units_required"])
                    requirement_map[milestone_id] = item if units is missing else units
                else:
                    requirement_map[milestone_id] = item
            normalized["milestone_requirements"] = requirement_map
        elif isinstance(requirements, list):
            requirement_map = {}
            for item in requirements:
                if not isinstance(item, dict):
                    continue
                milestone_id = item.get("milestone_id") or item.get("milestone")
                if not isinstance(milestone_id, str):
                    continue
                units = pick(item, ["cumulative_units_required", "required_units", "units_required"])
                if units is not missing:
                    requirement_map[milestone_id] = units
            normalized["milestone_requirements"] = requirement_map
        return normalized

    normalized_timeline = normalize_timeline(timeline)
    scores["source_timeline_and_quantities"] = mean([
        plan.get("purchase_order_id") == expected["purchase_order_id"],
        normalized_timeline.get("first_batch_quantity") == expected_timeline["first_batch_quantity"],
        normalized_timeline.get("first_batch_ship_date") == expected_timeline["first_batch_ship_date"],
        normalized_timeline.get("first_batch_estimated_arrival") == expected_timeline["first_batch_estimated_arrival"],
        normalized_timeline.get("remaining_quantity") == expected_timeline["remaining_quantity"],
        normalized_timeline.get("remaining_ship_window") == expected_timeline["remaining_ship_window"],
        "remaining_arrival_date" in normalized_timeline
        and normalized_timeline["remaining_arrival_date"] is None,
        normalized_timeline.get("usable_launch_inventory") == 120
        and normalized_timeline.get("reserved_support_inventory") == 120,
        normalized_timeline.get("qa_duration_calendar_days") == 2,
        normalized_timeline.get("milestone_requirements") == expected_timeline["milestone_requirements"],
    ])

    def normalize_milestones(value):
        result = {}
        if isinstance(value, list):
            items = value
        elif isinstance(value, dict):
            items = []
            for milestone_id, item in value.items():
                if isinstance(item, dict):
                    items.append({"milestone_id": milestone_id, **item})
        else:
            items = []
        for item in items:
            if isinstance(item, dict) and isinstance(item.get("milestone_id"), str):
                result[item["milestone_id"]] = item
        return result

    def canonical_status(milestone_id, value):
        state = token(value)
        if milestone_id == "pilot":
            if state in {
                "reduced_to_120",
                "reduced_pending_approval",
                "conditional_reduced",
                "conditional_reduced_to_120",
                "conditional_reduced_to_120_pending_program_director_approval",
                "at_risk",
                "at_risk_reduced",
                "at_risk_reduce_to_120",
                "at_risk_recommended_reduction",
                "conditional_on_reduced_scope",
                "conditional_on_program_director_approval",
                "conditional_ok",
                "on_track_reduced_to_120_pending_program_director_approval",
            }:
                return "reduced_to_120"
        elif milestone_id == "regional_launch":
            if state in {
                "conditional_pending_approvals",
                "conditional",
                "conditional_ready",
                "conditional_on_approvals",
                "conditional_on_approvals_and_qa",
                "conditional_on_approvals_and_first_batch_arrival",
                "conditional_on_approvals_920_units_projected",
                "conditional_ok",
            }:
                return "conditional_pending_approvals"
        elif milestone_id == "general_availability":
            if state in {
                "date_not_committed",
                "cannot_commit",
                "cannot_commit_remaining_batch_arrival_unconfirmed",
                "not_committed",
                "not_committable",
                "delayed_not_committed",
                "at_risk_remaining_batch_arrival_uncommitted",
                "uncommitted",
                "blocked",
                "pending_blocked_by_remaining_batch",
                "uncertain_pending_second_batch_arrival",
                "at_risk",
            }:
                return "date_not_committed"
        return None

    milestones = plan.get("milestones")
    normalized_milestones = normalize_milestones(milestones)
    expected_statuses = {
        "pilot": "reduced_to_120",
        "regional_launch": "conditional_pending_approvals",
        "general_availability": "date_not_committed",
    }
    expected_dates = {
        milestone_id: item["date"] for milestone_id, item in expected["milestones_by_id"].items()
    } if "milestones_by_id" in expected else {
        item["milestone_id"]: item["date"] for item in expected["milestones"]
    }

    def milestone_ok(milestone_id):
        item = normalized_milestones.get(milestone_id)
        if not isinstance(item, dict):
            return False
        if item.get("date") != expected_dates[milestone_id]:
            return False
        if canonical_status(milestone_id, item.get("status")) != expected_statuses[milestone_id]:
            return False
        units = item.get("available_units")
        if milestone_id == "pilot":
            return type(units) is int and units == 120
        if milestone_id == "regional_launch":
            return type(units) is int and units == 920
        if units is None or (type(units) is int and units == 920):
            return True
        return isinstance(units, str) and token(units) in {
            "dependent_on_second_batch",
            "dependent_on_remaining_batch",
            "not_available",
            "not_committed",
            "unconfirmed",
            "unknown",
            "tbd",
        }

    milestones_complete = (
        isinstance(milestones, list)
        and len(milestones) == 3
        and set(normalized_milestones) == set(expected_statuses)
        and all(milestone_ok(milestone_id) for milestone_id in expected_statuses)
    )
    scores["critical_path_impact"] = mean([
        milestones_complete,
        milestone_ok("pilot"),
        milestone_ok("regional_launch"),
        milestone_ok("general_availability"),
    ])

    def selected_option_ids(value):
        if not isinstance(value, list):
            return []
        selected = []
        rejected_states = {"rejected", "excluded", "not_recommended", "forbidden"}
        for item in value:
            if isinstance(item, str):
                selected.append(item)
                continue
            if not isinstance(item, dict):
                continue
            if item.get("selected") is False or item.get("included") is False:
                continue
            state = token(item.get("status"))
            if state in rejected_states or any(
                state.startswith(prefix)
                for prefix in ("not_recommended_", "excluded_", "forbidden_")
            ):
                continue
            option_id = item.get("option_id") or item.get("id")
            if isinstance(option_id, str):
                selected.append(option_id)
        return selected

    def normalized_approval_ids(value):
        if isinstance(value, dict):
            # Accept both a list of approval records and a role-keyed map
            # such as {"CFO": {"status": "pending"}}.
            value = list(value.keys()) + list(value.values())
        if not isinstance(value, list):
            return set()
        result = set()
        for item in value:
            candidate = item if isinstance(item, str) else pick(
                item, ["approver", "approval", "role", "owner", "approver_id"]
            )
            normalized = token(candidate)
            if normalized in {"program_director", "programdirector"}:
                result.add("PROGRAM_DIRECTOR")
            elif normalized == "cfo":
                result.add("CFO")
            elif normalized in {"release_manager", "releasemanager"}:
                result.add("RELEASE_MANAGER")
        return result

    def flatten_text(value):
        if isinstance(value, dict):
            return " ".join(flatten_text(key) + " " + flatten_text(item) for key, item in value.items())
        if isinstance(value, list):
            return " ".join(flatten_text(item) for item in value)
        return str(value)

    def has_date(text, month, day):
        month_text = f"{month:02d}"
        day_text = f"{day:02d}"
        return any(
            marker in text
            for marker in (
                f"2026-{month_text}-{day_text}",
                f"2026_{month_text}_{day_text}",
                f"2026/{month_text}/{day_text}",
                f"{month_text}-{day_text}",
                f"{month_text}_{day_text}",
                f"{month_text}/{day_text}",
                f"{month}月{day}日",
                f"october {day}",
                f"oct {day}",
            )
        )

    def trigger_coverage(value):
        if isinstance(value, list):
            entries = [flatten_text(item).lower() for item in value]
        elif isinstance(value, dict):
            entries = [flatten_text(value).lower()]
        else:
            entries = [flatten_text(value).lower()]

        def any_entry(predicate):
            return any(predicate(text, token(text)) for text in entries)

        def is_first_batch(text):
            return "first batch" in text or "first_batch" in text or "首批" in text or "第一批" in text

        def is_remaining_batch(text):
            return (
                "remaining batch" in text
                or "remaining_batch" in text
                or "second batch" in text
                or "second_batch" in text
                or "余下批次" in text
                or "第二批" in text
            )

        def has_miss_language(text):
            return any(
                marker in text
                for marker in (
                    "miss",
                    "after",
                    "late",
                    "slip",
                    "delay",
                    "not arrive",
                    "错过",
                    "未按时",
                    "超过",
                    "延迟",
                )
            )

        def has_ship_language(text):
            return "ship" in text or "发货" in text

        def has_arrival_language(text):
            return "arriv" in text or "到货" in text

        def has_qa_language(text):
            return any(marker in text for marker in ("qa", "quality", "质检", "质量"))

        return [
            any_entry(
                lambda text, compact: "first_batch_ship_after_2026_10_10" in compact
                or (
                    is_first_batch(text)
                    and has_date(text, 10, 10)
                    and has_ship_language(text)
                    and has_miss_language(text)
                )
            ),
            any_entry(
                lambda text, compact: "first_batch_arrival_after_2026_10_13" in compact
                or (
                    is_first_batch(text)
                    and has_date(text, 10, 13)
                    and has_arrival_language(text)
                    and has_miss_language(text)
                )
            ),
            any_entry(
                lambda text, compact: "first_batch_qa_after_2026_10_15" in compact
                or (
                    is_first_batch(text)
                    and has_date(text, 10, 15)
                    and has_qa_language(text)
                    and has_miss_language(text)
                )
            ),
            any_entry(
                lambda text, compact: "remaining_arrival_uncommitted_by_2026_10_16" in compact
                or (
                    is_remaining_batch(text)
                    and has_date(text, 10, 16)
                    and any(
                        marker in text
                        for marker in (
                            "uncommitted",
                            "unconfirmed",
                            "no committed",
                            "no arrival",
                            "未承诺",
                            "未确认",
                            "无承诺",
                            "无到货",
                            "null",
                        )
                    )
                )
            ),
        ]

    options = plan.get("recommended_options")
    selected_options = selected_option_ids(options)
    approvals = normalized_approval_ids(plan.get("required_approvals"))
    available_by_regional_launch = plan.get("available_by_regional_launch")
    if type(available_by_regional_launch) is int:
        available_units = available_by_regional_launch
    elif isinstance(available_by_regional_launch, dict):
        available_units = pick(
            available_by_regional_launch,
            [
                "units_qa_cleared_by_2026_10_16",
                "qa_cleared_units_available",
                "total_qa_cleared_units",
                "with_recommended_options_units",
                "best_case",
                "total",
            ],
        )
        if available_units is missing:
            available_units = None
    else:
        available_units = None
    trigger_flags = trigger_coverage(plan.get("trigger_conditions"))
    cost = plan.get("total_incremental_cost_cny")
    scores["contingency_math_and_constraints"] = mean([
        sorted(selected_options) == sorted(expected["recommended_options"]),
        cost == expected["total_incremental_cost_cny"],
        available_units == expected["available_by_regional_launch"],
        {"PROGRAM_DIRECTOR", "CFO"}.issubset(approvals),
        all(trigger_flags),
        "borrow_support_inventory" not in selected_options,
        type(cost) is int and cost <= 15000,
    ])
    required_milestone_fields = {"milestone_id", "date", "status", "available_units"}
    exact_schema = (
        set(plan) == set(expected["plan_fields"])
        and isinstance(milestones, list)
        and len(milestones) == 3
        and all(
            isinstance(item, dict)
            and required_milestone_fields.issubset(set(item))
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
