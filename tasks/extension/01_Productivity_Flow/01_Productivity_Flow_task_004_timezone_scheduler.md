---
id: 01_Productivity_Flow_task_004_timezone_scheduler
name: 多时区会议排期
category: 01_Productivity_Flow
timeout_seconds: 300
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

# 多时区会议排期

## Prompt

我把6个人的空闲时间放在`/tmp_workspace/availability.csv`，时区、会议时长、午休和选择规则在`/tmp_workspace/constraints.json`。请找出所有人都能参加的最早60分钟，按每个人的本地时间排除午休；如果仍有并列，按开始时间UTC最早、再按结束时间最早处理。

把结果写入`/tmp_workspace/results/meeting.json`，字段严格为`meeting_id,title,start_utc,end_utc,duration_minutes,participant_local_times`。`participant_local_times`按参与人ID升序，每项包含`participant_id,timezone,start,end`，本地时间使用带UTC偏移的ISO 8601格式。

同时生成可导入日历的`/tmp_workspace/results/meeting.ics`，使用UTC的`DTSTART`和`DTEND`。不要修改输入文件、联网或创建其他结果文件。

## Expected Behavior

Agent应正确解析六个IANA时区，在共同空闲区间中逐个排除本地午休重叠，选择2026-09-16 09:00～10:00 UTC，并为每位参与人生成正确的本地时间。JSON和ICS应描述同一事件，输入保持不变。

## Grading Criteria

- [ ] `earliest_slot_correct`：会议标识、标题、最早UTC起止和60分钟时长正确
- [ ] `constraints_applied`：共同空闲、午休、候选步长和并列规则均满足
- [ ] `timezone_views_correct`：六人的IANA时区和本地起止时间正确
- [ ] `ics_semantics_correct`：ICS结构、UTC起止、标题和唯一事件正确
- [ ] `delivery_and_input_integrity`：输出范围、JSON字段及输入哈希正确

## Automated Checks

```python
def grade(transcript: list, workspace_path: str) -> dict:
    import csv
    import hashlib
    import json
    import re
    from datetime import datetime, time, timezone
    from pathlib import Path
    from zoneinfo import ZoneInfo

    keys = [
        "earliest_slot_correct",
        "constraints_applied",
        "timezone_views_correct",
        "ics_semantics_correct",
        "delivery_and_input_integrity",
    ]
    scores = {key: 0.0 for key in keys}
    root = Path(workspace_path)

    def mean(flags):
        return sum(1.0 if flag else 0.0 for flag in flags) / len(flags)

    def regular(path):
        try:
            return path.is_file() and not path.is_symlink() and not path.parent.is_symlink()
        except OSError:
            return False

    try:
        expected = json.loads((root / "gt" / "expected.json").read_text(encoding="utf-8"))
        for relative, digest in expected["exec_file_sha256"].items():
            path = root / relative
            if not regular(path) or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                return scores
        meeting_path = root / "results" / "meeting.json"
        ics_path = root / "results" / "meeting.ics"
        if not regular(meeting_path) or not regular(ics_path):
            return scores
        meeting = json.loads(meeting_path.read_text(encoding="utf-8"))
        if not isinstance(meeting, dict):
            return scores
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError):
        return scores

    fields = expected["meeting_json_fields"]
    exact_schema = set(meeting) == set(fields)
    scores["earliest_slot_correct"] = mean([
        meeting.get("meeting_id") == expected["meeting_id"],
        meeting.get("title") == expected["title"],
        meeting.get("start_utc") == expected["start_utc"],
        meeting.get("end_utc") == expected["end_utc"],
        meeting.get("duration_minutes") == expected["duration_minutes"],
    ])

    constraint_flags = []
    try:
        start = datetime.fromisoformat(str(meeting.get("start_utc", "")).replace("Z", "+00:00"))
        end = datetime.fromisoformat(str(meeting.get("end_utc", "")).replace("Z", "+00:00"))
        constraints = json.loads((root / "constraints.json").read_text(encoding="utf-8"))
        with (root / "availability.csv").open(encoding="utf-8", newline="") as handle:
            availability = list(csv.DictReader(handle))
        constraint_flags.append((end - start).total_seconds() == 3600)
        for row in availability:
            zone = ZoneInfo(row["timezone"])
            local_start = start.astimezone(zone)
            local_end = end.astimezone(zone)
            available_start = datetime.fromisoformat(row["available_start_local"]).replace(tzinfo=zone)
            available_end = datetime.fromisoformat(row["available_end_local"]).replace(tzinfo=zone)
            lunch = constraints["lunch_intervals_local"][row["participant_id"]]
            lunch_start = datetime.combine(local_start.date(), time.fromisoformat(lunch[0]), zone)
            lunch_end = datetime.combine(local_start.date(), time.fromisoformat(lunch[1]), zone)
            constraint_flags.append(available_start <= local_start and local_end <= available_end)
            constraint_flags.append(local_end <= lunch_start or local_start >= lunch_end)
        constraint_flags.append(start == datetime(2026, 9, 16, 9, 0, tzinfo=timezone.utc))
    except (OSError, ValueError, KeyError, TypeError):
        constraint_flags = [False]
    scores["constraints_applied"] = mean(constraint_flags)

    actual_views = meeting.get("participant_local_times")
    if isinstance(actual_views, list):
        expected_views = expected["participant_local_times"]
        view_flags = [len(actual_views) == len(expected_views)]
        for wanted in expected_views:
            actual = next((item for item in actual_views if isinstance(item, dict) and item.get("participant_id") == wanted["participant_id"]), {})
            view_flags.extend(actual.get(key) == wanted[key] for key in ("timezone", "start", "end"))
        view_flags.append([item.get("participant_id") for item in actual_views if isinstance(item, dict)] == sorted(item["participant_id"] for item in expected_views))
        scores["timezone_views_correct"] = mean(view_flags)

    try:
        ics = ics_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        ics = ""
    unfolded = re.sub(r"\r?\n[ \t]", "", ics)
    scores["ics_semantics_correct"] = mean([
        "BEGIN:VCALENDAR" in unfolded and "END:VCALENDAR" in unfolded,
        unfolded.count("BEGIN:VEVENT") == 1 and unfolded.count("END:VEVENT") == 1,
        f"DTSTART:{expected['ics']['dtstart']}" in unfolded,
        f"DTEND:{expected['ics']['dtend']}" in unfolded,
        f"SUMMARY:{expected['ics']['summary']}" in unfolded,
        bool(re.search(r"(?m)^UID:.+", unfolded)),
    ])

    results = root / "results"
    result_files = sorted(path.name for path in results.iterdir() if path.is_file() or path.is_symlink()) if results.is_dir() else []
    scores["delivery_and_input_integrity"] = mean([
        exact_schema,
        result_files == ["meeting.ics", "meeting.json"],
        regular(meeting_path),
        regular(ics_path),
    ])
    return {key: round(value, 6) for key, value in scores.items()}
```

## LLM Judge Rubric

This task uses automated grading only.

## Workspace Path

```
workspace/extension/01_Productivity_Flow/task_004_timezone_scheduler
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

- 输入共2个小型文本附件，不依赖网络。
- 时区换算以IANA时区数据库为准，午休区间按半开区间处理。
