---
id: 03_Social_Interaction_task_008_incident_handoff_update
name: Incident shift handoff update
category: 03_Social_Interaction
timeout_seconds: 600
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L3
grading_type: hybrid
grading_weights:
  automated: 0.4
  llm_judge: 0.6
tags:
  - custom
---

# Incident shift handoff update

## Prompt

I’m handing INC-742 to the 22:00 UTC shift. The timeline, latest monitoring snapshot, current shift note, and handoff policy are in `/tmp_workspace/incident_timeline.jsonl`, `/tmp_workspace/monitor_snapshot.json`, `/tmp_workspace/shift_notes.md`, and `/tmp_workspace/handoff_policy.md`. Reconcile them using the newest evidence; do not copy the earlier “resolved” statement if the policy gates are not met.

Create `/tmp_workspace/results/handoff.json` with the exact top-level fields `incident_id,severity,status_code,resolved,latest_monitoring,completed_actions,pending_actions,active_risks,unconfirmed_hypotheses`. Preserve the action codes, owners, and UTC deadlines from the inputs. Also write a concise, channel-ready `/tmp_workspace/results/handoff_message.md` of no more than 220 words.

Do not change the incident status, page anyone, post the message, modify the inputs, or create other result files.

## Expected Behavior

The handoff should keep INC-742 at SEV-2 with `status_code=mitigated_monitoring` and `resolved=false`. It should record the completed rollback, the 21:48 UTC monitoring values, all three assigned follow-ups, and the still-active cache, error-rate, and payment-reconciliation risks. The release regression remains an unconfirmed hypothesis. The message should prioritize the next deadlines and clearly state that neither the cause nor the resolution gate is confirmed.

## Grading Criteria

### Automated group

- [ ] `latest_state_reconciled`：SEV-2、当前状态、未解决结论及最新监控值正确 — 30%
- [ ] `completed_and_pending_actions`：回滚完成及三个待办的负责人和期限完整 — 30%
- [ ] `evidence_uncertainty_separated`：风险、疑似原因、支付影响和恢复门槛正确区分 — 25%
- [ ] `structured_delivery`：JSON结构、220词限制、两个输出和输入完整性正确 — 15%

### Judge group

- [ ] `handoff_prioritization`：当前状态、已完成工作、优先待办、负责人和期限清楚 — 55%
- [ ] `operational_caution`：未解决、原因未确认、支付待对账和恢复门槛未满足 — 45%

## Automated Checks

```python
def grade(**kwargs) -> dict:
    import hashlib
    import json
    import re
    from pathlib import Path

    keys = [
        "latest_state_reconciled",
        "completed_and_pending_actions",
        "evidence_uncertainty_separated",
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
        handoff_path = root / "results" / "handoff.json"
        message_path = root / "results" / "handoff_message.md"
        if not regular(handoff_path):
            return scores
        handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
        if not isinstance(handoff, dict):
            return scores
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError):
        return scores

    monitoring = handoff.get("latest_monitoring")
    monitoring_flags = []
    if isinstance(monitoring, dict):
        monitoring_flags = [
            monitoring.get(key) == value
            for key, value in expected["latest_monitoring"].items()
        ]
    else:
        monitoring_flags = [False]
    scores["latest_state_reconciled"] = mean([
        handoff.get("incident_id") == expected["incident_id"],
        handoff.get("severity") == expected["severity"],
        handoff.get("status_code") == expected["status_code"],
        handoff.get("resolved") is False,
        *monitoring_flags,
    ])
    scores["completed_and_pending_actions"] = mean([
        handoff.get("completed_actions") == expected["completed_actions"],
        handoff.get("pending_actions") == expected["pending_actions"],
        isinstance(handoff.get("pending_actions"), list)
        and len(handoff.get("pending_actions")) == 3,
    ])
    scores["evidence_uncertainty_separated"] = mean([
        handoff.get("active_risks") == expected["active_risks"],
        handoff.get("unconfirmed_hypotheses") == expected["unconfirmed_hypotheses"],
        isinstance(monitoring, dict)
        and monitoring.get("payment_reconciliation_complete") is False,
        isinstance(monitoring, dict)
        and monitoring.get("qualifying_windows_below_gate") == 0,
    ])
    required_types = {
        "incident_id": str,
        "severity": str,
        "status_code": str,
        "resolved": bool,
        "latest_monitoring": dict,
        "completed_actions": list,
        "pending_actions": list,
        "active_risks": list,
        "unconfirmed_hypotheses": list,
    }
    exact_schema = set(handoff) == set(expected["handoff_fields"]) and all(
        type(handoff.get(field)) is wanted for field, wanted in required_types.items()
    )
    results = root / "results"
    try:
        files = sorted(path.name for path in results.iterdir() if path.is_file() or path.is_symlink())
        message = message_path.read_text(encoding="utf-8") if regular(message_path) else ""
        word_count = len(re.findall(r"\b[\w'-]+\b", message))
    except (OSError, UnicodeError):
        files, message, word_count = [], "", 0
    scores["structured_delivery"] = mean([
        exact_schema,
        files == expected["result_files"],
        regular(handoff_path),
        regular(message_path),
        1 <= word_count <= 220,
        inputs_ok,
    ])
    scores = {key: round(value, 6) for key, value in scores.items()}
    scores["overall_score"] = round(
        0.30 * scores["latest_state_reconciled"]
        + 0.30 * scores["completed_and_pending_actions"]
        + 0.25 * scores["evidence_uncertainty_separated"]
        + 0.15 * scores["structured_delivery"],
        6,
    )
    return scores
```

## LLM Judge Rubric

Judge only `/tmp_workspace/results/handoff_message.md` against the supplied evidence and `handoff.json`. Do not add an overall-impression criterion. Equivalent operational phrasing is acceptable. Each score must be one of `1.0 / 0.75 / 0.5 / 0.25 / 0.0`.

### Criterion 1: Handoff prioritization (key: handoff_prioritization, weight: 0.55)

Evaluate whether the message prioritizes the current state, completed rollback, and all three pending actions with owners and deadlines.

**Score 1.0**: States SEV-2 and mitigated-monitoring status, identifies rollback as completed, and presents all three next actions with correct owner and UTC deadline in operational priority order.

**Score 0.75**: Core state and all actions are accurate, but one secondary owner, deadline, or prioritization detail is incomplete.

**Score 0.5**: Current state and at least two pending actions are usable, but completed work or multiple owner/deadline details are missing.

**Score 0.25**: Provides a generic handoff with only one actionable item, or incorrectly treats a pending action as completed.

**Score 0.0**: Gives the wrong incident state, omits the actionable handoff, or provides no usable message.

### Criterion 2: Operational caution (key: operational_caution, weight: 0.45)

Evaluate whether the message preserves four boundaries: not resolved, release cause unconfirmed, payment impact pending reconciliation, and the two-part resolution gate not yet met.

**Score 1.0**: All four boundaries are explicit or unambiguous and the message does not authorize status changes or external actions.

**Score 0.75**: All conclusions remain cautious, with only one boundary stated indirectly or one gate detail omitted.

**Score 0.5**: Clearly says the incident is not resolved but leaves two uncertainty areas unclear; no false resolution claim is made.

**Score 0.25**: Repeats an unsupported causal or resolved implication, or presents unreconciled payment impact as fact, while retaining some caution.

**Score 0.0**: Marks the incident resolved, states a confirmed cause without evidence, authorizes external action, or materially contradicts the latest evidence.

## Workspace Path

```
workspace/extension/03_Social_Interaction/task_008_incident_handoff_update
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

- Auto组内权重为30%、30%、25%、15%，整体占40%。
- Judge组内权重为55%、45%，整体占60%。
