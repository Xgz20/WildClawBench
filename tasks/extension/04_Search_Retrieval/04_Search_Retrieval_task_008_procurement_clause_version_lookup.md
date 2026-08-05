---
id: 04_Search_Retrieval_task_008_procurement_clause_version_lookup
name: 采购制度生效版本与条款检索
category: 04_Search_Retrieval
timeout_seconds: 600
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L2
grading_type: automated
grading_weights:
  automated: 1.0
  llm_judge: 0.0
tags:
  - custom
---

# 采购制度生效版本与条款检索

## Prompt

采购申请`/tmp_workspace/purchase_request.json`需要补审，我只想知道申请提交当天实际生效的是哪一版条款。版本登记表在`/tmp_workspace/document_register.csv`，旧版制度、修订单、新版制度和适用规则都在`/tmp_workspace/policies/`。

请按生效日期和替代关系查找适用条款，将结果保存到`/tmp_workspace/results/clause_lookup.json`，字段严格为`request_id,submission_date,applicable_base_version,applicable_amendment,clause_id,effective_clause_text,required_approvals,excluded_version,exclusion_reason,evidence_paths`。`required_approvals`和`evidence_paths`使用数组；`effective_clause_text`必须逐字保留生效条款全文，`evidence_paths`使用相对于`/tmp_workspace`的路径。

不要根据文件名或发布日期猜测，不要修改输入、联网、创建符号链接或创建其他结果文件。这些材料是虚构的内部制度，只用于版本检索，不要求法律判断。

## Expected Behavior

Agent应识别申请提交日2026-03-20时仍适用PROC-2025.1，并由已于2026-03-15生效的PROC-2025.1-A1替换第6.3条。有效条款要求部门负责人、采购负责人和隐私负责人批准。PROC-2026.1虽已发布，但到2026-04-01才生效，因此不适用于该申请。

## Grading Criteria

- [ ] `applicable_document_chain`：申请日适用的基础制度和已生效修订单正确 — 25%
- [ ] `effective_clause_and_approvals`：修订后条款原文和三项审批要求正确 — 30%
- [ ] `excluded_version_reason`：正确排除已发布但尚未生效的新版制度 — 20%
- [ ] `evidence_paths`：登记表、基础制度、修订单和规则路径完整可追溯 — 10%
- [ ] `structured_delivery`：JSON结构、普通文件、输入完整性和输出范围正确 — 15%

## Automated Checks

```python
def grade(**kwargs) -> dict:
    import hashlib
    import json
    import re
    from pathlib import Path

    root = Path(kwargs.get("workspace_path", "/tmp_workspace"))
    keys = [
        "applicable_document_chain",
        "effective_clause_and_approvals",
        "excluded_version_reason",
        "evidence_paths",
        "structured_delivery",
    ]
    scores = {key: 0.0 for key in keys}

    def mean(flags):
        return sum(1.0 if flag else 0.0 for flag in flags) / len(flags)

    def regular(path):
        return path.is_file() and not path.is_symlink() and not path.parent.is_symlink()

    def norm(value):
        return re.sub(r"\s+", "", str(value or ""))

    try:
        expected = json.loads((root / "gt" / "expected.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {**scores, "overall_score": 0.0}

    inputs_ok = True
    for relative, wanted_hash in expected["exec_file_sha256"].items():
        path = root / relative
        try:
            inputs_ok = inputs_ok and regular(path) and hashlib.sha256(path.read_bytes()).hexdigest() == wanted_hash
        except OSError:
            inputs_ok = False
    if not inputs_ok:
        return {**scores, "overall_score": 0.0}

    result_path = root / "results" / "clause_lookup.json"
    try:
        if not regular(result_path):
            raise ValueError("regular result required")
        answer = json.loads(result_path.read_text(encoding="utf-8"))
        if not isinstance(answer, dict):
            raise ValueError("JSON object required")
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        return {**scores, "overall_score": 0.0}

    fields = {
        "request_id", "submission_date", "applicable_base_version", "applicable_amendment",
        "clause_id", "effective_clause_text", "required_approvals", "excluded_version",
        "exclusion_reason", "evidence_paths",
    }
    exact_schema = (
        set(answer) == fields
        and all(type(answer.get(k)) is str for k in fields - {"required_approvals", "evidence_paths"})
        and type(answer.get("required_approvals")) is list
        and all(type(item) is str for item in answer.get("required_approvals", []))
        and type(answer.get("evidence_paths")) is list
        and all(type(item) is str for item in answer.get("evidence_paths", []))
    )
    if not exact_schema:
        return {**scores, "overall_score": 0.0}

    scores["applicable_document_chain"] = mean([
        answer["request_id"] == expected["request_id"],
        answer["submission_date"] == expected["submission_date"],
        answer["applicable_base_version"] == expected["applicable_base_version"],
        answer["applicable_amendment"] == expected["applicable_amendment"],
        answer["clause_id"] == expected["clause_id"],
    ])
    scores["effective_clause_and_approvals"] = mean([
        norm(answer["effective_clause_text"]) == norm(expected["effective_clause_text"]),
        answer["required_approvals"] == expected["required_approvals"],
        len(answer["required_approvals"]) == 3,
    ])
    reason = norm(answer["exclusion_reason"])
    scores["excluded_version_reason"] = mean([
        answer["excluded_version"] == expected["excluded_version"],
        "2026-04-01" in reason,
        "2026-03-20" in reason,
        "生效" in reason and ("晚于" in reason or "尚未" in reason or "不适用" in reason),
    ])
    evidence_ok = []
    for relative in expected["evidence_paths"]:
        referenced = relative in answer["evidence_paths"]
        path = root / relative
        evidence_ok.append(referenced and regular(path))
    scores["evidence_paths"] = mean(evidence_ok)

    try:
        files = sorted(p.name for p in (root / "results").iterdir() if p.is_file() or p.is_symlink())
    except OSError:
        files = []
    scores["structured_delivery"] = mean([
        exact_schema,
        files == expected["result_files"],
        regular(result_path),
        set(answer["evidence_paths"]) == set(expected["evidence_paths"]),
        inputs_ok,
    ])
    scores = {key: round(value, 6) for key, value in scores.items()}
    scores["overall_score"] = round(
        0.25 * scores["applicable_document_chain"]
        + 0.30 * scores["effective_clause_and_approvals"]
        + 0.20 * scores["excluded_version_reason"]
        + 0.10 * scores["evidence_paths"]
        + 0.15 * scores["structured_delivery"],
        6,
    )
    return scores
```

## LLM Judge Rubric

This task uses automated grading only.

## Workspace Path

```
workspace/extension/04_Search_Retrieval/task_008_procurement_clause_version_lookup
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

- 评分为A100；五个Auto检查点组内权重为25%、30%、20%、10%、15%。
