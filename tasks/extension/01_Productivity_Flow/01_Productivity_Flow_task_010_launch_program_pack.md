---
id: 01_Productivity_Flow_task_010_launch_program_pack
name: Atlas phased launch program pack
category: 01_Productivity_Flow
timeout_seconds: 600
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

# Atlas phased launch program pack

## Prompt

I’ve put the milestone estimates, budget limits, RACI, stakeholder notes, and release policy in `/tmp_workspace/milestone_plan.csv`, `/tmp_workspace/budget_limits.json`, `/tmp_workspace/raci.csv`, `/tmp_workspace/stakeholder_notes.md`, and `/tmp_workspace/release_policy.md`.

Build one workable phased launch plan. Respect the hard budget and deadline, preserve required dependencies, and do not schedule production before security sign-off, a successful rollback rehearsal, pilot acceptance, and Release Manager approval. Where a stakeholder request conflicts with a hard gate, record the decision and its source instead of silently choosing.

Deliver these files under `/tmp_workspace/results/`:

1. `launch_plan.csv` with exact columns `phase,milestone_id,milestone_name,start_date,end_date,owner,dependencies,planned_cost_usd,acceptance_gate,status`.
2. `risk_register.csv` with exact columns `risk_id,risk,trigger,owner,response,severity` and at least three concrete risks.
3. `decision_log.md` covering the requested launch date, optional spend and controlling gates.
4. `comms_draft.md`, ready for stakeholders but explicit about what is still conditional.

Use calendar-day durations as defined in the policy. This is planning only: do not deploy, approve spending, contact anyone, modify the inputs, or create other result files.

## Expected Behavior

The Agent should construct a dependency-valid seven-milestone plan within USD 180,000 and before 2026-11-20. It should reject the optional analytics package because required work already totals USD 175,000, treat the requested 2026-11-06 launch as unapproved, and schedule production only after all release gates. Risks, decisions and communications should form an actionable, bounded program pack.

## Grading Criteria

### Automated group

- [ ] `hard_constraints_satisfied`：预算、截止日期、生产发布门槛和任务范围均满足
- [ ] `dependencies_dates_consistent`：七个里程碑的持续时间、依赖、日期、负责人和成本一致
- [ ] `required_delivery_present`：四个输出、CSV结构、风险数量和输入完整性正确

### Judge group

- [ ] `program_plan_quality`：阶段、验收门槛、决策依据和责任闭环完整
- [ ] `risk_rollback_and_comms`：风险、回滚边界和利益相关方沟通具体且不越权

## Automated Checks

```python
def grade(transcript: list, workspace_path: str) -> dict:
    import csv
    import hashlib
    import json
    from datetime import date, timedelta
    from pathlib import Path

    keys = [
        "hard_constraints_satisfied",
        "dependencies_dates_consistent",
        "required_delivery_present",
    ]
    scores = {key: 0.0 for key in keys}
    root = Path(workspace_path)

    def mean(flags):
        return sum(1.0 if flag else 0.0 for flag in flags) / len(flags)

    def regular(path):
        return path.is_file() and not path.is_symlink() and not path.parent.is_symlink()

    plan_path = root / "results" / "launch_plan.csv"
    risk_path = root / "results" / "risk_register.csv"
    decision_path = root / "results" / "decision_log.md"
    comms_path = root / "results" / "comms_draft.md"
    try:
        expected = json.loads((root / "gt" / "expected.json").read_text(encoding="utf-8"))
        for relative, digest in expected["exec_file_sha256"].items():
            path = root / relative
            if not regular(path) or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                return scores
        if not all(regular(path) for path in (plan_path, risk_path, decision_path, comms_path)):
            return scores
        with plan_path.open(encoding="utf-8-sig", newline="") as handle:
            plan_reader = csv.DictReader(handle)
            plan_header = plan_reader.fieldnames or []
            plan_rows = list(plan_reader)
        with risk_path.open(encoding="utf-8-sig", newline="") as handle:
            risk_reader = csv.DictReader(handle)
            risk_header = risk_reader.fieldnames or []
            risk_rows = list(risk_reader)
        with (root / "milestone_plan.csv").open(encoding="utf-8", newline="") as handle:
            source_rows = {row["milestone_id"]: row for row in csv.DictReader(handle)}
    except (OSError, UnicodeError, csv.Error, json.JSONDecodeError, KeyError):
        return scores

    actual = {row.get("milestone_id"): row for row in plan_rows if isinstance(row, dict)}
    required = expected["required_milestones"]
    parsed = {}
    for milestone_id, row in actual.items():
        try:
            parsed[milestone_id] = {
                "start": date.fromisoformat(row["start_date"]),
                "end": date.fromisoformat(row["end_date"]),
                "cost": int(row["planned_cost_usd"]),
                "dependencies": [value for value in row.get("dependencies", "").split(";") if value],
            }
        except (KeyError, TypeError, ValueError):
            pass

    total_cost = sum(item["cost"] for item in parsed.values())
    production = parsed.get("M7", {})
    gate_ids = ("M3", "M5", "M6")
    scores["hard_constraints_satisfied"] = mean([
        set(actual) == set(required) and len(plan_rows) == len(required),
        total_cost == expected["planned_total_cost"] and total_cost <= expected["hard_budget"],
        isinstance(production.get("end"), date) and production["end"] <= date.fromisoformat(expected["production_deadline"]),
        all(
            isinstance(production.get("start"), date)
            and gate_id in parsed
            and production["start"] > parsed[gate_id]["end"]
            for gate_id in gate_ids
        ),
        expected["rejected_optional_request"] not in actual,
        all(actual.get(mid, {}).get("status") == "planned" for mid in required),
    ])

    consistency_flags = []
    for milestone_id in required:
        row = actual.get(milestone_id, {})
        item = parsed.get(milestone_id)
        source = source_rows.get(milestone_id, {})
        if item is None:
            consistency_flags.extend([False, False, False, False, False])
            continue
        duration = int(source["duration_calendar_days"])
        source_dependencies = [value for value in source.get("dependencies", "").split(";") if value]
        consistency_flags.extend([
            item["start"] >= date.fromisoformat(source["earliest_start"]),
            item["end"] == item["start"] + timedelta(days=duration - 1),
            item["dependencies"] == source_dependencies,
            row.get("owner") == source["owner"],
            item["cost"] == int(source["planned_cost_usd"]),
        ])
        consistency_flags.extend(
            dependency in parsed and item["start"] > parsed[dependency]["end"]
            for dependency in source_dependencies
        )
    scores["dependencies_dates_consistent"] = mean(consistency_flags)

    results = root / "results"
    result_files = sorted(path.name for path in results.iterdir() if path.is_file() or path.is_symlink()) if results.is_dir() else []
    risk_rows_valid = len(risk_rows) >= 3 and all(
        all(isinstance(row.get(field), str) and row[field].strip() for field in expected["risk_register_header"])
        for row in risk_rows
    )
    scores["required_delivery_present"] = mean([
        plan_header == expected["launch_plan_header"],
        risk_header == expected["risk_register_header"],
        risk_rows_valid,
        result_files == sorted(expected["required_output_files"]),
        all(regular(path) for path in (plan_path, risk_path, decision_path, comms_path)),
        decision_path.stat().st_size > 100 and comms_path.stat().st_size > 100,
    ])
    return {key: round(value, 6) for key, value in scores.items()}
```

## LLM Judge Rubric

### Criterion 1: Program plan quality (key: program_plan_quality, weight: 0.5)

Judge the four deliverables together against all supplied inputs. Do not add an overall-impression criterion.

**Score 1.0**: The seven milestones form a coherent phased plan with correct owners, dependencies, acceptance gates and decision points; the USD 175,000 total, optional-spend rejection, requested-date conflict and controlling evidence are explicit; every material conflict has an actionable owner or approval path.

**Score 0.75**: All hard constraints and major decisions are correct, but one non-critical milestone has a weak acceptance gate, or one decision lacks a secondary owner or evidence reference.

**Score 0.5**: The main phases and hard gates are present, but dependency rationale, ownership, cost decision or conflict documentation has one substantial gap; the plan remains recoverable.

**Score 0.25**: The output mostly restates inputs, leaves several gates or owners undefined, silently chooses between conflicting requests, or requires major restructuring.

**Score 0.0**: The plan exceeds budget or deadline, schedules production before a mandatory gate, treats an unapproved request as authorized, or does not provide a workable plan.

### Criterion 2: Risk, rollback and communication quality (key: risk_rollback_and_comms, weight: 0.5)

判据：风险登记、回滚边界和沟通稿是否包含具体触发条件、负责人、响应方式及准确的不确定性说明。

**Score 1.0**: Risks include concrete triggers, owners and responses for schedule/gate, migration or load, rollback and stakeholder expectation risks; rollback success remains a hard launch gate; communications state the conditional plan, next decision point and current non-commitment without claiming deployment, approval or spend occurred.

**Score 0.75**: Risks and communication are accurate and usable, with only one secondary trigger, owner or follow-up detail missing.

**Score 0.5**: A usable risk register and draft exist, but rollback, escalation, stakeholder expectation or uncertainty handling is materially incomplete.

**Score 0.25**: Risks are generic, communications imply the requested date is committed, or responsibility and triggers are mostly absent.

**Score 0.0**: Rollback is omitted as a gate, the draft makes a false production or approval commitment, unauthorized spending is presented as approved, or required risk/communication files are unusable.

## Workspace Path

```
workspace/extension/01_Productivity_Flow/task_010_launch_program_pack
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

- Auto组内三个检查点等权，整体占40%；两个Judge检查点等权，整体占60%。
- 输出仅为计划和草稿，不代表部署、审批、支出或对外联系已发生。
