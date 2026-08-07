---
id: 01_Productivity_Flow_task_009_action_reconciliation
name: 订单到实物证据核对
category: 01_Productivity_Flow
timeout_seconds: 300
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L3
grading_type: hybrid
grading_weights:
  automated: 0.7
  llm_judge: 0.3
tags:
  - custom
---

# 订单到实物证据核对

## Prompt

这批订单的系统记录对不上。`/tmp_workspace/order_export.csv`、`/tmp_workspace/print_jobs.csv`、`/tmp_workspace/shipping_labels.csv`、`/tmp_workspace/operator_notes.md`和`/tmp_workspace/evidence_policy.md`都在工作区。

请按证据规则核对订单、打印任务、成品序列号和运单标签，只在整条链路有证据时建立匹配，不确定的不要猜，也不要安排发货。结果放到`/tmp_workspace/results/`：

1. `identity_chain.csv`，列严格为`order_id,job_id,case_serial,label_id,evidence_state`，只放完整验证通过的链路。
2. `exceptions.csv`，列严格为`order_id,conflict_field,evidence_state,blocker,next_owner,next_action`，记录缺证据、冲突和取消订单。
3. `handoff_plan.md`，说明停止条件、缺失证据、责任人和下一步。

不要修改输入、联系外部人员或创建其他结果文件。

## Expected Behavior

Agent应按照证据政策识别两条完整验证链路，保留数量不足、取消订单和序列号冲突三个异常，不推断缺失标识，也不把任何订单表述为已安排发货。交接计划应让对应负责人能够补证或解决冲突。

## Grading Criteria

### Automated group

- [ ] `identity_chain_correct`：完整证据链的订单、任务、序列号和标签正确
- [ ] `conflicts_and_blockers_correct`：三个异常的冲突字段、阻塞、责任人和下一步正确
- [ ] `evidence_labels_correct`：`verified`、`insufficient_evidence`、`canceled`和`conflict`按政策使用
- [ ] `structured_delivery_correct`：CSV结构、输出范围及输入完整性正确

### Judge group

- [ ] `handoff_and_uncertainty_quality`：交接清楚保留不确定性、停止条件和责任闭环

## Automated Checks

```python
def grade(transcript: list, workspace_path: str) -> dict:
    import csv
    import hashlib
    import json
    from pathlib import Path

    keys = [
        "identity_chain_correct",
        "conflicts_and_blockers_correct",
        "evidence_labels_correct",
        "structured_delivery_correct",
        "overall_score",
    ]
    scores = {key: 0.0 for key in keys}
    root = Path(workspace_path)

    def mean(flags):
        return sum(1.0 if flag else 0.0 for flag in flags) / len(flags)

    def regular(path):
        return path.is_file() and not path.is_symlink() and not path.parent.is_symlink()

    identity_path = root / "results" / "identity_chain.csv"
    exceptions_path = root / "results" / "exceptions.csv"
    handoff_path = root / "results" / "handoff_plan.md"
    try:
        expected = json.loads((root / "gt" / "expected.json").read_text(encoding="utf-8"))
        for relative, digest in expected["exec_file_sha256"].items():
            path = root / relative
            if not regular(path) or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                return scores
        if not all(regular(path) for path in (identity_path, exceptions_path, handoff_path)):
            return scores
        with identity_path.open(encoding="utf-8-sig", newline="") as handle:
            identity_reader = csv.DictReader(handle)
            identity_header = identity_reader.fieldnames or []
            identity_rows = list(identity_reader)
        with exceptions_path.open(encoding="utf-8-sig", newline="") as handle:
            exception_reader = csv.DictReader(handle)
            exception_header = exception_reader.fieldnames or []
            exception_rows = list(exception_reader)
    except (OSError, UnicodeError, csv.Error, json.JSONDecodeError, KeyError):
        return scores

    identity_actual = {row.get("order_id"): row for row in identity_rows if isinstance(row, dict)}
    identity_wanted = {row["order_id"]: row for row in expected["identity_chain_rows"]}
    identity_flags = [set(identity_actual) == set(identity_wanted)]
    for order_id, target in identity_wanted.items():
        row = identity_actual.get(order_id, {})
        identity_flags.extend(row.get(field) == target[field] for field in expected["identity_chain_header"])
    scores["identity_chain_correct"] = mean(identity_flags)

    exception_actual = {row.get("order_id"): row for row in exception_rows if isinstance(row, dict)}
    exception_wanted = {row["order_id"]: row for row in expected["exception_rows"]}
    exception_flags = [set(exception_actual) == set(exception_wanted)]
    for order_id, target in exception_wanted.items():
        row = exception_actual.get(order_id, {})
        exception_flags.extend([
            row.get("conflict_field") == target["conflict_field"],
            row.get("next_owner") == target["next_owner"],
            isinstance(row.get("blocker"), str) and bool(row["blocker"].strip()),
            isinstance(row.get("next_action"), str) and bool(row["next_action"].strip()),
        ])
    scores["conflicts_and_blockers_correct"] = mean(exception_flags)

    scores["evidence_labels_correct"] = mean([
        all(row.get("evidence_state") == "verified" for row in identity_rows),
        identity_actual.get("ORD-1001", {}).get("evidence_state") == "verified",
        identity_actual.get("ORD-1002", {}).get("evidence_state") == "verified",
        exception_actual.get("ORD-1003", {}).get("evidence_state") == "insufficient_evidence",
        exception_actual.get("ORD-1004", {}).get("evidence_state") == "canceled",
        exception_actual.get("ORD-1005", {}).get("evidence_state") == "conflict",
        not (set(identity_actual) & set(exception_actual)),
    ])

    results = root / "results"
    result_files = sorted(path.name for path in results.iterdir() if path.is_file() or path.is_symlink()) if results.is_dir() else []
    scores["structured_delivery_correct"] = mean([
        identity_header == expected["identity_chain_header"],
        exception_header == expected["exceptions_header"],
        result_files == ["exceptions.csv", "handoff_plan.md", "identity_chain.csv"],
        all(regular(path) for path in (identity_path, exceptions_path, handoff_path)),
    ])
    scores["overall_score"] = round(
        0.30 * scores["identity_chain_correct"]
        + 0.30 * scores["conflicts_and_blockers_correct"]
        + 0.25 * scores["evidence_labels_correct"]
        + 0.15 * scores["structured_delivery_correct"],
        6,
    )
    return {key: round(value, 6) for key, value in scores.items()}
```

## LLM Judge Rubric

### Criterion 1: 交接与不确定性处理 (key: handoff_and_uncertainty_quality, weight: 1.0)

判据：`handoff_plan.md`是否逐项说明异常的停止条件、缺失或冲突证据、责任人和下一步，并清楚区分事实与待确认项。

**Score 1.0**: ORD-1003、ORD-1004和ORD-1005均有准确的停止条件、证据状态、责任人和可执行下一步；完整链路与异常清楚分离，不推断缺失标识，不声称已安排发货。

**Score 0.75**: 三个异常和停止边界均正确，仅一个异常缺少次要期限、证据说明或确认动作。

**Score 0.5**: 识别主要异常并阻止发货，但至少一个异常缺少责任人或下一步，或事实与假设边界不够清楚。

**Score 0.25**: 多个不确定匹配被当作事实，交接主要是泛化提醒，或没有形成责任闭环。

**Score 0.0**: 安排证据不足或已取消订单发货，虚构序列号，未处理核心身份冲突，或未交付计划。

## Workspace Path

```
workspace/extension/01_Productivity_Flow/task_009_action_reconciliation
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
- 任务只生成核对结果和草稿，不执行发货或外部联系。
