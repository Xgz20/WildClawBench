---
id: 01_Productivity_Flow_task_13_expense_policy_check
name: 报销政策选择与费用审核
category: 01_生产力工作流
timeout_seconds: 300
modality: pure-text
difficulty: L1
grading_type: automated
tags:
  - custom
---
## Prompt

请根据 `/tmp_workspace/policies/` 中的政策文件，审核 `/tmp_workspace/expenses.csv` 中的6条费用记录。

选择状态为有效且有效期覆盖费用日期的政策。严格按照该政策处理：缺少必需票据或金额超过该类别单笔限额时，整笔费用拒绝；否则全额批准。

将UTF-8 JSON保存到 `/tmp_workspace/results/reimbursement.json`，结构如下：

```json
{
  "policy_id": "采用的政策",
  "applied_rules": {
    "类别": {"limit": 0.0, "receipt_required": true}
  },
  "expenses": [
    {
      "expense_id": "E001",
      "decision": "approved或rejected",
      "approved_amount": 0.0,
      "reason_code": "eligible、over_limit或missing_receipt"
    }
  ],
  "approved_total": 0.0,
  "rejected_total": 0.0
}
```

必须包含政策中的4个类别和全部6条费用。`rejected_total`是所有被拒费用原始金额之和。不要访问网络，不要修改输入文件。

## Expected Behavior

Agent应识别适用于2026年6月费用的政策，应用类别限额和票据要求，审核每条费用，计算两项总额，并生成一个合法JSON结果。

## Grading Criteria

- [ ] 适用政策ID正确 — 25%
- [ ] 采用的限额和票据要求正确 — 25%
- [ ] 6条费用的决定、批准金额和原因代码正确 — 25%
- [ ] 批准与拒绝总额正确 — 25%

前两个检查点映射到`retrieval_verification`，后两个映射到`data_processing`。

## Automated Checks

```python
def grade(**kwargs) -> dict:
    import hashlib
    import json
    from pathlib import Path

    keys = [
        "applicable_policy_correct",
        "policy_rules_correct",
        "expense_decisions_correct",
        "totals_correct",
        "overall_score",
    ]
    scores = {key: 0.0 for key in keys}
    workspace = Path(kwargs.get("workspace_path") or "/tmp_workspace")
    result_path = workspace / "results" / "reimbursement.json"
    expected_path = workspace / "gt" / "expected.json"

    if (
        result_path.is_symlink()
        or result_path.parent.is_symlink()
        or not result_path.is_file()
        or not expected_path.is_file()
    ):
        return scores
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
        expected = json.loads(expected_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return scores
    if not isinstance(result, dict) or not isinstance(expected, dict):
        return scores

    for relative, expected_hash in expected.get("exec_file_sha256", {}).items():
        input_path = workspace / relative
        try:
            if (
                input_path.is_symlink()
                or not input_path.is_file()
                or hashlib.sha256(input_path.read_bytes()).hexdigest() != expected_hash
            ):
                return scores
        except OSError:
            return scores

    scores["applicable_policy_correct"] = float(
        result.get("policy_id") == expected.get("policy_id")
    )

    got_rules = result.get("applied_rules")
    exp_rules = expected.get("applied_rules")
    if isinstance(got_rules, dict) and isinstance(exp_rules, dict) and exp_rules:
        matched = 0
        for category, rule in exp_rules.items():
            got = got_rules.get(category)
            try:
                limit_ok = abs(float(got.get("limit")) - float(rule["limit"])) <= 1e-6
            except (AttributeError, TypeError, ValueError):
                limit_ok = False
            receipt_ok = isinstance(got, dict) and (
                got.get("receipt_required") is rule.get("receipt_required")
            )
            matched += int(limit_ok and receipt_ok)
        exact_keys = set(got_rules) == set(exp_rules)
        scores["policy_rules_correct"] = (
            matched / len(exp_rules) if exact_keys else 0.0
        )

    got_expenses = result.get("expenses")
    exp_expenses = expected.get("expenses")
    if isinstance(got_expenses, list) and isinstance(exp_expenses, list) and exp_expenses:
        unique = {
            item.get("expense_id"): item
            for item in got_expenses
            if isinstance(item, dict) and isinstance(item.get("expense_id"), str)
        }
        valid_shape = len(got_expenses) == len(exp_expenses) == len(unique)
        matched = 0
        for exp in exp_expenses:
            got = unique.get(exp["expense_id"], {})
            try:
                amount_ok = abs(
                    float(got.get("approved_amount")) - float(exp["approved_amount"])
                ) <= 1e-6
            except (TypeError, ValueError):
                amount_ok = False
            matched += int(
                got.get("decision") == exp["decision"]
                and got.get("reason_code") == exp["reason_code"]
                and amount_ok
            )
        scores["expense_decisions_correct"] = (
            matched / len(exp_expenses) if valid_shape else 0.0
        )

    total_checks = []
    for field in ("approved_total", "rejected_total"):
        try:
            total_checks.append(
                abs(float(result.get(field)) - float(expected[field])) <= 1e-6
            )
        except (KeyError, TypeError, ValueError):
            total_checks.append(False)
    scores["totals_correct"] = sum(total_checks) / len(total_checks)
    scores["overall_score"] = round(
        0.25 * scores["applicable_policy_correct"]
        + 0.25 * scores["policy_rules_correct"]
        + 0.25 * scores["expense_decisions_correct"]
        + 0.25 * scores["totals_correct"],
        6,
    )
    return scores
```

## Workspace Path

```
workspace/extension/01_Productivity_Flow/task_13_expense_policy_check
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
