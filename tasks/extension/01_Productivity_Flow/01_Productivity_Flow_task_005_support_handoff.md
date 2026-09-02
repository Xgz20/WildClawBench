---
id: 01_Productivity_Flow_task_005_support_handoff
name: Overnight support handoff
category: 01_Productivity_Flow
timeout_seconds: 300
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L2
grading_type: hybrid
grading_weights:
  automated: 0.7
  llm_judge: 0.3
tags:
  - custom
---

# Overnight support handoff

## Prompt

I’m taking over the support queue tonight. The ticket export is in `/tmp_workspace/tickets.csv`, recent comments are in `/tmp_workspace/comments.json`, and the priority/SLA rules are in `/tmp_workspace/priority_rules.md`.

Please merge duplicate ticket records, use the latest valid status and comment, exclude resolved items, and create `/tmp_workspace/results/handoff.csv` with these exact columns: `ticket_id,customer,owner,priority,due_at_utc,status,blocker,next_action`. Use `UNASSIGNED` when the source has no owner, and sort according to the rules.

Also write a short Slack-ready handoff to `/tmp_workspace/results/handoff_note.md`. Don’t invent customer commitments or owners. Do not modify the inputs, use the network, or create other result files.

## Expected Behavior

The Agent should consolidate duplicate records by valid timestamp, exclude the resolved ticket, use the latest valid comment, calculate priority and UTC deadlines from the policy, and preserve missing ownership. The handoff note should prioritize P1 and P2 tickets, include actionable ownership and blockers, and avoid unsupported promises.

## Grading Criteria

### Automated group

- [ ] `ticket_facts_normalized`: active ticket facts, owners, blockers and next actions are accurate
- [ ] `dedupe_and_status_correct`: duplicates are merged, latest valid status is used and resolved tickets are excluded
- [ ] `priority_and_sla_correct`: priorities, deadlines and sort order follow the policy
- [ ] `delivery_correct`: exact CSV structure, output scope and input integrity are preserved

### Judge group

- [ ] `handoff_note_quality`: the Slack handoff is concise, complete, actionable and makes no unsupported commitment

## Automated Checks

```python
def grade(transcript: list, workspace_path: str) -> dict:
    import csv
    import hashlib
    import json
    from pathlib import Path

    keys = [
        "ticket_facts_normalized",
        "dedupe_and_status_correct",
        "priority_and_sla_correct",
        "delivery_correct",
        "overall_score",
    ]
    scores = {key: 0.0 for key in keys}
    root = Path(workspace_path)

    def mean(flags):
        return sum(1.0 if flag else 0.0 for flag in flags) / len(flags)

    def regular(path):
        return path.is_file() and not path.is_symlink() and not path.parent.is_symlink()

    try:
        expected = json.loads((root / "gt" / "expected.json").read_text(encoding="utf-8"))
        for relative, digest in expected["exec_file_sha256"].items():
            path = root / relative
            if not regular(path) or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                return scores
        csv_path = root / "results" / "handoff.csv"
        note_path = root / "results" / "handoff_note.md"
        if not regular(csv_path) or not regular(note_path):
            return scores
        with csv_path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            header = reader.fieldnames or []
            rows = list(reader)
    except (OSError, UnicodeError, csv.Error, json.JSONDecodeError, KeyError):
        return scores

    actual = {row.get("ticket_id"): row for row in rows if isinstance(row, dict)}
    wanted = {row["ticket_id"]: row for row in expected["active_rows"]}
    rows_are_well_formed = all(
        isinstance(row, dict)
        and set(row) == set(expected["csv_header"])
        and None not in row
        and all(value is not None for value in row.values())
        for row in rows
    )
    fact_flags = [set(actual) == set(wanted)]
    for ticket_id, target in wanted.items():
        row = actual.get(ticket_id, {})
        fact_flags.extend(row.get(field) == target[field] for field in ("customer", "owner", "blocker", "next_action"))
    scores["ticket_facts_normalized"] = mean(fact_flags)

    scores["dedupe_and_status_correct"] = mean([
        len(rows) == len(wanted),
        len(actual) == len(rows),
        all(actual.get(ticket_id, {}).get("status") == target["status"] for ticket_id, target in wanted.items()),
        all(ticket_id not in actual for ticket_id in expected["excluded_ticket_ids"]),
    ])

    priority_flags = []
    for ticket_id, target in wanted.items():
        row = actual.get(ticket_id, {})
        priority_flags.extend([
            row.get("priority") == target["priority"],
            row.get("due_at_utc") == target["due_at_utc"],
        ])
    priority_flags.append([row.get("ticket_id") for row in rows] == [row["ticket_id"] for row in expected["active_rows"]])
    scores["priority_and_sla_correct"] = mean(priority_flags)

    results = root / "results"
    result_files = sorted(path.name for path in results.iterdir() if path.is_file() or path.is_symlink()) if results.is_dir() else []
    scores["delivery_correct"] = mean([
        header == expected["csv_header"] and rows_are_well_formed,
        result_files == ["handoff.csv", "handoff_note.md"],
        regular(csv_path),
        regular(note_path),
    ])
    scores["overall_score"] = round(
        0.30 * scores["ticket_facts_normalized"]
        + 0.25 * scores["dedupe_and_status_correct"]
        + 0.30 * scores["priority_and_sla_correct"]
        + 0.15 * scores["delivery_correct"],
        6,
    )
    return {key: round(value, 6) for key, value in scores.items()}
```

## LLM Judge Rubric

### Criterion 1: Slack handoff quality (key: handoff_note_quality, weight: 1.0)

Judge only `/tmp_workspace/results/handoff_note.md` against the supplied records and policy. Do not add an overall-impression criterion.

**Score 1.0**: The note leads with both P1/P2 tickets and gives each ticket’s owner or `UNASSIGNED`, deadline, blocker and next action; it is concise and scannable, mentions lower-priority work proportionately, and contains no invented customer commitment.

**Score 0.75**: All active tickets and both high-priority tickets are accurate, but one secondary field is missing or the note is slightly repetitive; no unsupported commitment is made.

**Score 0.5**: The main urgent tickets are present, but two material owner, deadline, blocker or next-action details are missing, or lower-priority work is poorly organized.

**Score 0.25**: The note is generic, omits an urgent ticket, guesses an owner, or presents a proposed action as a customer commitment.

**Score 0.0**: A critical fact is wrong, resolved work is presented as active, customer commitments are fabricated, or no usable handoff note is delivered.

## Workspace Path

```
workspace/extension/01_Productivity_Flow/task_005_support_handoff
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

- Auto组内四个检查点等权，整体占70%；Judge整体占30%。
- 输入中的无效时间评论是干扰项，评分以`valid`和可解析时间共同判断。
