---
id: 03_Social_Interaction_task_001_meeting_reschedule_draft
name: 会议改期草稿
category: 03_社交互动
timeout_seconds: 300
modality: pure-text
difficulty: L1
grading_type: automated
tags:
  - custom
---

## Prompt

读取 `/tmp_workspace/meeting_request.json`。从候选时段中选择原定日期内所有参与人均可参加的最早时段，并生成一份中文改期草稿。不要发送消息，也不要修改输入文件。

将UTF-8 JSON对象保存到 `/tmp_workspace/results/reschedule.json`，字段必须如下：

```json
{
  "meeting_id": "...",
  "original_start": "ISO 8601时间",
  "proposed_start": "ISO 8601时间",
  "proposed_end": "ISO 8601时间",
  "duration_minutes": 30,
  "selection_reason": "...",
  "subject": "...",
  "body": "..."
}
```

输出必须是普通文件，不得是符号链接。

草稿必须写明原时间和建议时间，简要说明冲突，保持会议时长，并请参与人确认新时间。

## Expected Behavior

Agent读取固定的可用时间数据，选择上海时区2026年8月12日15:00至15:30，并撰写简洁的中文草稿，不联系任何人。

## Grading Criteria

- [ ] 会议和候选时段选择正确 — 34%（`reasoning_planning`）
- [ ] 满足原定日期、时长和全员可参加约束 — 23%（`reasoning_planning`）
- [ ] 草稿包含正确的会议与时间事实 — 28%（`content_generation`）
- [ ] 草稿说明冲突并请求确认 — 15%（`content_generation`）

结果必须是普通JSON文件，并且顶层字段与要求完全一致。结果文件为符号链接、缺少字段、包含额外字段或字段JSON类型错误时，结果无效。这是输出有效性门槛，不增加第五个检查点。

## Automated Checks

```python
def grade(**kwargs) -> dict:
    import hashlib
    import json
    from pathlib import Path

    root = Path(kwargs.get("workspace_path", "/tmp_workspace"))
    keys = ["slot_selection", "schedule_constraints", "draft_factual_completeness", "draft_actionability"]
    scores = {key: 0.0 for key in keys}

    def mean(flags):
        return sum(1.0 if flag else 0.0 for flag in flags) / len(flags)

    result_path = root / "results" / "reschedule.json"
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
        "meeting_id": str,
        "original_start": str,
        "proposed_start": str,
        "proposed_end": str,
        "duration_minutes": int,
        "selection_reason": str,
        "subject": str,
        "body": str,
    }
    exact_schema = set(answer) == set(required_types) and all(
        type(answer.get(field)) is expected_type
        for field, expected_type in required_types.items()
    )
    if not exact_schema:
        return {**scores, "overall_score": 0.0}

    scores["slot_selection"] = mean([
        answer.get("meeting_id") == expected["meeting_id"],
        answer.get("proposed_start") == expected["proposed_start"],
        answer.get("proposed_end") == expected["proposed_end"],
    ])
    reason = str(answer.get("selection_reason", ""))
    scores["schedule_constraints"] = mean([
        answer.get("original_start") == expected["original_start"],
        answer.get("duration_minutes") == expected["duration_minutes"],
        ("最早" in reason) and ("所有" in reason or "全员" in reason or "均可" in reason),
    ])
    subject = str(answer.get("subject", ""))
    body = str(answer.get("body", ""))
    scores["draft_factual_completeness"] = mean([
        expected["title"] in subject + body,
        all(term in body for term in expected["required_body_times"]),
        "8月12日" in body or "2026-08-12" in body,
        "30分钟" in body or "30 分钟" in body,
    ])
    scores["draft_actionability"] = mean([
        "冲突" in body or "客户电话" in body,
        any(term in body for term in ("确认", "是否方便", "请回复")),
        len(body.strip()) >= 45,
    ])
    scores = {key: round(value, 4) for key, value in scores.items()}
    scores["overall_score"] = round(
        0.34 * scores["slot_selection"]
        + 0.23 * scores["schedule_constraints"]
        + 0.28 * scores["draft_factual_completeness"]
        + 0.15 * scores["draft_actionability"], 4
    )
    return scores
```

## Workspace Path

```
workspace/extension/03_Social_Interaction/task_001_meeting_reschedule_draft
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
