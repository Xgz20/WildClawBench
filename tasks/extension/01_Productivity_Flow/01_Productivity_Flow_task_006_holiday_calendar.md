---
id: 01_Productivity_Flow_task_006_holiday_calendar
name: 2025年节假日排班日历
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

# 2025年节假日排班日历

## Prompt

我需要把国务院办公厅《关于2025年部分节假日安排的通知》（国办发明电〔2024〕12号）整理进排班系统。请只使用中国政府网原文：<https://www.gov.cn/zhengce/content/202411/content_6986382.htm>。

将每个放假日和调休上班日逐日写入`/tmp_workspace/results/holidays.csv`，按`date`升序排列，字段严格为`date,type,holiday_name,source_document`。`date`使用`YYYY-MM-DD`，`type`只能是`holiday`或`workday`，`holiday_name`按通知中的节日名称填写，`source_document`统一填写`国办发明电〔2024〕12号`。

再写一份不超过3条的`/tmp_workspace/results/staffing_note.md`，提醒排班负责人需要提前处理的长假和周末上班。不要使用其他来源，不要保存网页副本。

## Expected Behavior

Agent应读取指定的固定政府网原文，识别文号和2025年六组放假安排，将连续日期展开为逐日记录，同时准确标记5个调休上班日。应按约定交付结构化CSV和最多3条可执行的排班提醒，且不落盘网页副本。

## Grading Criteria

### 规则部分

- [ ] `source_identity_correct`：所有预期日期均引用指定文号
- [ ] `holiday_rows_correct`：28个放假日的日期与节日名称正确
- [ ] `makeup_workdays_correct`：5个调休上班日的日期与对应节日正确
- [ ] `csv_delivery_correct`：CSV路径、表头、值域、唯一性和排序正确，且未保存网页副本

### LLM部分

- [ ] `staffing_reminders_quality`：排班提醒在3条内覆盖关键长假和周末上班，日期有依据且动作具体

## Automated Checks

```python
def grade(**kwargs) -> dict:
    import csv
    import json
    from datetime import date
    from pathlib import Path

    keys = [
        "source_identity_correct",
        "holiday_rows_correct",
        "makeup_workdays_correct",
        "csv_delivery_correct",
        "overall_score",
    ]
    scores = {key: 0.0 for key in keys}
    workspace = Path(kwargs.get("workspace_path") or "/tmp_workspace")
    output_path = workspace / "results" / "holidays.csv"
    expected_path = workspace / "gt" / "expected.json"

    def is_regular_delivery(path):
        try:
            root = workspace.resolve(strict=True)
            resolved = path.resolve(strict=True)
            relative = path.relative_to(workspace)
            cursor = workspace
            for part in relative.parts:
                cursor = cursor / part
                if cursor.is_symlink():
                    return False
            return root in resolved.parents and path.is_file()
        except (OSError, RuntimeError, ValueError):
            return False

    if not is_regular_delivery(output_path) or not expected_path.is_file():
        return scores
    try:
        expected = json.loads(expected_path.read_text(encoding="utf-8"))
        if expected.get("exec_file_sha256") != {}:
            return scores
        if output_path.stat().st_size > 131072:
            return scores
        with output_path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            fieldnames = reader.fieldnames or []
            raw_rows = list(reader)
    except (OSError, UnicodeError, csv.Error, json.JSONDecodeError):
        return scores

    header = expected.get("csv_header")
    expected_rows = expected.get("rows")
    if not isinstance(header, list) or not isinstance(expected_rows, list):
        return scores

    rows = []
    for raw in raw_rows:
        if not isinstance(raw, dict):
            continue
        rows.append(
            {
                key: (raw.get(key) or "").strip()
                for key in header
            }
        )

    expected_by_date = {
        row["date"]: row
        for row in expected_rows
        if isinstance(row, dict) and isinstance(row.get("date"), str)
    }
    actual_by_date = {}
    for row in rows:
        actual_by_date.setdefault(row["date"], row)

    source_document = expected.get("source", {}).get("document_number")
    if expected_by_date and isinstance(source_document, str):
        source_hits = sum(
            actual_by_date.get(day, {}).get("source_document") == source_document
            for day in expected_by_date
        )
        scores["source_identity_correct"] = source_hits / len(expected_by_date)

    def row_set(values, row_type):
        return {
            (row.get("date"), row.get("holiday_name"))
            for row in values
            if isinstance(row, dict) and row.get("type") == row_type
        }

    def jaccard(actual, wanted):
        union = actual | wanted
        return len(actual & wanted) / len(union) if union else 1.0

    scores["holiday_rows_correct"] = jaccard(
        row_set(rows, "holiday"), row_set(expected_rows, "holiday")
    )
    scores["makeup_workdays_correct"] = jaccard(
        row_set(rows, "workday"), row_set(expected_rows, "workday")
    )

    delivery = 0.2
    delivery += 0.25 * (fieldnames == header)
    valid_rows = True
    parsed_dates = []
    for row in rows:
        try:
            parsed_dates.append(date.fromisoformat(row["date"]))
        except (TypeError, ValueError):
            valid_rows = False
        if (
            set(row) != set(header)
            or row["type"] not in {"holiday", "workday"}
            or not row["holiday_name"]
            or not row["source_document"]
        ):
            valid_rows = False
    delivery += 0.2 * valid_rows
    unique_sorted = (
        len(parsed_dates) == len(set(parsed_dates))
        and parsed_dates == sorted(parsed_dates)
    )
    delivery += 0.15 * unique_sorted
    delivery += 0.1 * (len(rows) == len(expected_rows))
    web_suffixes = {".html", ".htm", ".mhtml", ".pdf"}
    saved_web_copy = any(
        path.is_file()
        and "gt" not in path.relative_to(workspace).parts
        and path.suffix.lower() in web_suffixes
        for path in workspace.rglob("*")
    )
    delivery += 0.1 * (not saved_web_copy)
    scores["csv_delivery_correct"] = round(delivery, 6)
    scores["overall_score"] = round(
        0.20 * scores["source_identity_correct"]
        + 0.35 * scores["holiday_rows_correct"]
        + 0.25 * scores["makeup_workdays_correct"]
        + 0.20 * scores["csv_delivery_correct"],
        6,
    )
    return scores
```

## LLM Judge Rubric

### Criterion 1: 排班提醒质量 (key: staffing_reminders_quality, weight: 1.0)

判据：评估`results/staffing_note.md`是否在最多3条内，使用指定通知中的日期，准确提醒长假与周末调休上班，并给出排班负责人可执行的提前动作。

**Score 1.0**: 不超过3条，准确聚焦春节和国庆中秋长假以及相关周末上班，并给出至少2项具体排班动作；日期全部来自指定通知。

**Score 0.75**: 日期和关键时段正确，且不超过3条，但遗漏1个相关周末上班提醒，或有1条的排班动作不够具体。

**Score 0.5**: 只覆盖一个主要长假或部分周末上班日，但已有至少1项可执行动作，且未增加通知之外的日期。

**Score 0.25**: 内容主要是泛化提醒，遗漏多数关键时段，超过3条，或包含1个无依据日期，但仍与节假日排班相关。

**Score 0.0**: 主要日期错误，给出多个无依据日期，或未交付`staffing_note.md`。

## Workspace Path

```
workspace/extension/01_Productivity_Flow/task_006_holiday_calendar
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

- 运行时必须访问Prompt中的固定中国政府网页面。
- `exec/`不包含网页快照；页面访问失败视为任务失败。
- 参考真值依据索引号`000014349/2024-00094`和文号`国办发明电〔2024〕12号`的原文逐日展开。
