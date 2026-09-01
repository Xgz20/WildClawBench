---
id: 03_Social_Interaction_task_009_release_expectation_alignment
name: 发布预期对齐
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

# 发布预期对齐

## Prompt

销售、客户和工程现在对上线时间的理解不一致。相关邮件、工程状态、发布规则和负责人在`/tmp_workspace/account_thread.md`、`/tmp_workspace/engineering_status.json`、`/tmp_workspace/release_policy.md`和`/tmp_workspace/owners.csv`。我明天要回复客户，也需要在内部统一口径。

请核对哪些日期只是工作目标、哪些发布门槛还没有通过，将结果写入`/tmp_workspace/results/release_alignment.json`，字段严格为`account_id,commitment_status_code,previous_target_date,conditional_internal_window,next_customer_update_at,release_manager_written_approval,blocking_gates`。在没有已批准客户承诺日期时，`commitment_status_code`使用`date_not_committed`；`release_manager_written_approval`使用JSON布尔值。`blocking_gates`只记录工程状态和负责人文件中三个有明确owner和due_at的执行门槛，每项字段严格为`gate_id,status,owner,due_at`；发布经理书面批准不要作为第四个`blocking_gates`对象。

再写`/tmp_workspace/results/customer_update.md`和`/tmp_workspace/results/internal_alignment.md`。不要把未批准日期写成承诺，不要责怪销售、客户或工程，也不要发送消息、修改输入或创建其他结果文件。

## Expected Behavior

应识别9月18日只是此前工作目标，9月24日20:00只是内部最早条件性窗口。安全审查、4倍负载测试和回滚演练仍为pending，发布经理也未书面批准，因此状态必须为`date_not_committed`。结构化结果应列出三个门槛的负责人、期限和9月18日17:00的下一次客户更新时间。客户稿应承认此前预期并纠正承诺状态，内部稿应中性形成统一说法和责任闭环。

## Grading Criteria

### Automated group

- [ ] `facts_and_gate_state`：工作目标、条件性窗口和三个未完成门槛正确 — 30%
- [ ] `commitment_boundary_decision`：未承诺状态及发布经理批准边界正确 — 30%
- [ ] `actions_owners_dates`：三个门槛负责人、期限和客户更新时间完整 — 25%
- [ ] `structured_delivery`：JSON结构、三个输出和输入完整性正确 — 15%

### Judge group

- [ ] `customer_update_quality`：承认此前预期、不承诺新日期、承诺状态更新时间 — 55%
- [ ] `alignment_note_quality`：中性说明差异并形成门槛、责任人和统一口径闭环 — 45%

## Automated Checks

```python
def grade(**kwargs) -> dict:
    import hashlib
    import json
    import re
    from pathlib import Path

    keys = [
        "facts_and_gate_state",
        "commitment_boundary_decision",
        "actions_owners_dates",
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

    def code(value):
        return re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")

    def commitment_status(value):
        aliases = {
            "target_only_not_committed": "date_not_committed",
            "no_commitment_yet": "date_not_committed",
            "not_committed": "date_not_committed",
        }
        value = code(value)
        return aliases.get(value, value)

    def gate_index(value):
        if not isinstance(value, list):
            return {}
        return {
            item.get("gate_id"): item
            for item in value
            if isinstance(item, dict) and isinstance(item.get("gate_id"), str)
        }

    try:
        expected = json.loads((root / "gt" / "expected.json").read_text(encoding="utf-8"))
        inputs_ok = all(
            regular(root / relative)
            and hashlib.sha256((root / relative).read_bytes()).hexdigest() == digest
            for relative, digest in expected["exec_file_sha256"].items()
        )
        alignment_path = root / "results" / "release_alignment.json"
        if not regular(alignment_path):
            return scores
        alignment = json.loads(alignment_path.read_text(encoding="utf-8"))
        if not isinstance(alignment, dict):
            return scores
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError):
        return scores

    gates = alignment.get("blocking_gates")
    expected_gates = expected["blocking_gates"]
    actual_gates = gate_index(gates)
    scores["facts_and_gate_state"] = mean([
        alignment.get("account_id") == expected["account_id"],
        alignment.get("previous_target_date") == expected["previous_target_date"],
        alignment.get("conditional_internal_window") == expected["conditional_internal_window"],
        all(item["gate_id"] in actual_gates for item in expected_gates),
        all(
            actual_gates.get(item["gate_id"], {}).get("status") == item["status"]
            for item in expected_gates
        ),
    ])
    approval = alignment.get("release_manager_written_approval")
    if type(approval) is not bool:
        legacy_approval = actual_gates.get("release_manager_written_approval", {})
        if code(legacy_approval.get("status")) in {"pending", "not_approved", "false"}:
            approval = False
    scores["commitment_boundary_decision"] = mean([
        commitment_status(alignment.get("commitment_status_code"))
        == expected["commitment_status_code"],
        approval is expected["release_manager_written_approval"],
        alignment.get("conditional_internal_window") != alignment.get("previous_target_date"),
    ])
    action_flags = [
        alignment.get("next_customer_update_at") == expected["next_customer_update_at"]
    ]
    for wanted in expected_gates:
        item = actual_gates.get(wanted["gate_id"], {})
        action_flags.append(
            item.get("owner") == wanted["owner"]
            and item.get("due_at") == wanted["due_at"]
        )
    scores["actions_owners_dates"] = mean(action_flags)
    exact_schema = (
        set(alignment) == set(expected["alignment_fields"])
        and type(alignment.get("release_manager_written_approval")) is bool
        and isinstance(gates, list)
        and len(gates) == len(expected_gates)
        and set(actual_gates) == {item["gate_id"] for item in expected_gates}
        and all(
            isinstance(item, dict) and set(item) == {"gate_id", "status", "owner", "due_at"}
            for item in gates
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
        0.30 * scores["facts_and_gate_state"]
        + 0.30 * scores["commitment_boundary_decision"]
        + 0.25 * scores["actions_owners_dates"]
        + 0.15 * scores["structured_delivery"],
        6,
    )
    return scores
```

## LLM Judge Rubric

Judge the two Markdown drafts against the supplied account thread, engineering state, policy, owners, and JSON result. Do not add an overall-impression criterion. Different neutral business wording is acceptable. Each score must be one of `1.0 / 0.75 / 0.5 / 0.25 / 0.0`.

### Criterion 1: 客户更新质量 (key: customer_update_quality, weight: 0.55)

判据：客户稿是否承认此前9月18日预期，明确当前没有已承诺上线日，不把9月24日写成承诺，并承诺在9月18日17:00前提供下一次状态更新。

**Score 1.0**: 四项边界全部准确，语气对客户负责且不披露内部争议或责怪任何一方。

**Score 0.75**: 承诺边界正确，仅遗漏此前预期或更新时间中的一个次要要素。

**Score 0.5**: 明确没有已承诺日期，但没有妥善承认客户此前理解，或更新时间和条件性窗口表达含糊。

**Score 0.25**: 暗示9月24日很可能保证上线、责怪销售或客户，或没有给出下一次更新时间。

**Score 0.0**: 将9月18日或9月24日写成已承诺上线日，虚构批准状态，或没有客户更新稿。

### Criterion 2: 内部对齐说明质量 (key: alignment_note_quality, weight: 0.45)

判据：内部稿是否中性区分客户理解、工作目标和条件性窗口，并形成三个门槛、负责人、期限及统一外部说法的闭环。

**Score 1.0**: 口径差异表述中性，三个门槛与负责人期限完整，明确统一外部说法和下一次协调动作，可直接供团队执行。

**Score 0.75**: 核心闭环完整，仅一项负责人、期限或统一说法细节不完整。

**Score 0.5**: 能说明不应承诺日期并列出多数门槛，但责任闭环或对外统一说法明显不足。

**Score 0.25**: 主要追究销售或工程责任，只有泛化的“尽快完成测试”，缺少可执行对齐。

**Score 0.0**: 鼓励继续使用未批准日期、虚构门槛完成情况、造成内部对立，或没有内部稿。

## Workspace Path

```
workspace/extension/03_Social_Interaction/task_009_release_expectation_alignment
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
