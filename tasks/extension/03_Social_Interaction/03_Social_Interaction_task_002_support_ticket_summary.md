---
id: 03_Social_Interaction_task_002_support_ticket_summary
name: 客服工单摘要与回复草稿
category: 03_Social_Interaction
timeout_seconds: 300
modality: pure-text
difficulty: L1
grading_type: automated
tags:
  - custom
---

## Prompt

读取 `/tmp_workspace/support_ticket.json` 中的简短客服线程。以最新消息为准总结当前状态，并生成一段中文客户回复草稿。不要发送回复；在客户复测前，不要声称问题已经解决。

将UTF-8 JSON对象保存到 `/tmp_workspace/results/support_summary.json`，字段必须如下：

```json
{
  "ticket_id": "...",
  "product": "...",
  "priority": "...",
  "affected_users": 0,
  "status_code": "...",
  "next_action_code": "...",
  "issue_summary": "...",
  "customer_reply_draft": "..."
}
```

输出必须是普通文件，不得是符号链接。

如果线程内容支持，应使用 `awaiting_customer_retest` 作为当前状态，使用 `ask_customer_retest` 作为下一步操作。

## Expected Behavior

Agent提取固定工单事实，使用工程师的最新更新，区分“配置已修正”和“问题已确认解决”，并生成简洁的复测请求。

## Grading Criteria

- [ ] 正确提取工单事实 — 27%（`data_processing`）
- [ ] 正确识别最新状态和下一步操作 — 17%（`data_processing`）
- [ ] 内部摘要保留关键问题和状态 — 36%（`content_generation`）
- [ ] 客户回复准确、可执行且不虚假声称问题已解决 — 20%（`content_generation`）

结果必须是普通JSON文件，并且顶层字段与要求完全一致。结果文件为符号链接、缺少字段、包含额外字段或字段JSON类型错误时，结果无效。在客户复测前，肯定声称问题已解决、修复完成或服务恢复正常将无法获得满分；明确表示尚未、不能或无法确认解决的语句可以通过。这些规则不增加第五个检查点。

## Automated Checks

```python
def grade(**kwargs) -> dict:
    import hashlib
    import json
    import re
    from pathlib import Path

    root = Path(kwargs.get("workspace_path", "/tmp_workspace"))
    keys = ["facts_extracted", "latest_status_and_action", "summary_completeness", "reply_draft_quality"]
    scores = {key: 0.0 for key in keys}

    def mean(flags):
        return sum(1.0 if flag else 0.0 for flag in flags) / len(flags)

    result_path = root / "results" / "support_summary.json"
    if result_path.is_symlink() or result_path.parent.is_symlink():
        return {**scores, "overall_score": 0.0}

    try:
        expected = json.loads((root / "gt" / "expected.json").read_text(encoding="utf-8"))
        answer = json.loads(result_path.read_text(encoding="utf-8"))
        if not isinstance(answer, dict):
            raise ValueError("answer must be an object")
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {**scores, "overall_score": 0.0}

    for relative, expected_hash in expected.get("exec_file_sha256", {}).items():
        input_path = root / relative
        try:
            if (
                input_path.is_symlink()
                or not input_path.is_file()
                or hashlib.sha256(input_path.read_bytes()).hexdigest() != expected_hash
            ):
                return {**scores, "overall_score": 0.0}
        except OSError:
            return {**scores, "overall_score": 0.0}

    required_types = {
        "ticket_id": str,
        "product": str,
        "priority": str,
        "affected_users": int,
        "status_code": str,
        "next_action_code": str,
        "issue_summary": str,
        "customer_reply_draft": str,
    }
    exact_schema = set(answer) == set(required_types) and all(
        type(answer.get(field)) is expected_type
        for field, expected_type in required_types.items()
    )
    if not exact_schema:
        return {**scores, "overall_score": 0.0}

    scores["facts_extracted"] = mean([
        answer.get("ticket_id") == expected["ticket_id"],
        answer.get("product") == expected["product"],
        answer.get("priority") == expected["priority"],
        answer.get("affected_users") == expected["affected_users"],
    ])
    scores["latest_status_and_action"] = mean([
        answer.get("status_code") == expected["status_code"],
        answer.get("next_action_code") == expected["next_action_code"],
    ])
    summary = str(answer.get("issue_summary", ""))
    reply = str(answer.get("customer_reply_draft", ""))

    def makes_forbidden_resolution_claim(text):
        compact = re.sub(r"\s+", "", str(text or ""))
        clauses = re.findall(r"[^。！？!?；;，,\n]+[。！？!?；;，,]?", compact)
        for claim in expected["forbidden_resolution_claims"]:
            for clause in clauses:
                clause_body = re.sub(r"[。！？!?；;，,]+$", "", clause)
                clause_is_question = clause.endswith(("？", "?"))
                start = 0
                while True:
                    index = clause_body.find(claim, start)
                    if index < 0:
                        break
                    prefix = clause_body[max(0, index - 24):index]
                    suffix = clause_body[index + len(claim):index + len(claim) + 16]
                    prefix_negated = any(
                        term in prefix
                        for term in expected["resolution_negation_prefixes"]
                    )
                    suffix_negated = any(
                        suffix.startswith(term)
                        for term in expected["resolution_negation_suffixes"]
                    )
                    interrogative = clause_is_question or any(
                        term in prefix
                        for term in expected["resolution_interrogative_prefixes"]
                    )
                    if not prefix_negated and not suffix_negated and not interrogative:
                        return True
                    start = index + len(claim)
        return False

    def requests_retest(text):
        return any(term in text for term in (
            "复测", "重新测试", "重新尝试", "再次尝试", "再试", "重新登录", "再次登录",
        ))

    scores["summary_completeness"] = mean([
        all(term.lower() in summary.lower() for term in expected["issue_terms"]),
        "配置" in summary and ("修正" in summary or "调整" in summary),
        requests_retest(summary),
        not makes_forbidden_resolution_claim(summary),
    ])
    scores["reply_draft_quality"] = mean([
        requests_retest(reply),
        "回复" in reply or "跟进" in reply,
        not makes_forbidden_resolution_claim(reply),
        len(reply.strip()) >= 35,
    ])
    scores = {key: round(value, 4) for key, value in scores.items()}
    scores["overall_score"] = round(
        0.27 * scores["facts_extracted"]
        + 0.17 * scores["latest_status_and_action"]
        + 0.36 * scores["summary_completeness"]
        + 0.20 * scores["reply_draft_quality"], 4
    )
    return scores
```

## Workspace Path

```
workspace/extension/03_Social_Interaction/task_002_support_ticket_summary
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
