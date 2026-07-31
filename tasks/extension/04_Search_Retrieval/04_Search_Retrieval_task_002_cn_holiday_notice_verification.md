---
id: 04_Search_Retrieval_task_002_cn_holiday_notice_verification
name: 中国2025年春节放假通知核验
category: 04_搜索检索
timeout_seconds: 300
modality: pure-text
difficulty: L1
grading_type: automated
tags:
  - invalid
---

## Prompt

请使用`/tmp_workspace/source_candidates.json`列出的中国网站候选来源及完整离线文章存档，核验中国2025年春节放假安排。

请选择中国政府官方来源，不要把商业网站或自媒体作为最终依据。输出以下信息：

- `YYYY-MM-DD`格式的假期开始日期和结束日期；
- 包含首尾日期的假期总天数；
- 按日期升序排列的两个调休上班日；
- 所选来源ID、规范URL，以及能够同时支持上述信息的一段连续原文。

请创建`/tmp_workspace/results/verification.json`，字段必须与下面完全一致：

```json
{
  "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD",
  "days": 0,
  "adjusted_workdays": ["YYYY-MM-DD", "YYYY-MM-DD"],
  "source_id": "候选来源ID",
  "source_url": "候选来源URL",
  "evidence_quote": "连续原文证据"
}
```

只使用提供的本地存档。不要访问`/tmp_workspace/gt`，不要修改来源文件。

## Expected Behavior

Agent选择中国政府网上的国务院办公厅通知，提取并规范化假期和调休日期，计算包含首尾日期的总天数，并生成带可追溯原文的JSON结果。

本题归为L1：候选来源和字段均已固定，页面出处可以直接判断，只需要一次日期区间计算。

## Grading Criteria

- [ ] 选择官方来源并提供可追溯原文（20%）
- [ ] 假期和调休日期正确（30%）
- [ ] 包含首尾日期的总天数正确（25%）
- [ ] JSON字段、日期格式和排序规范（25%）

## Automated Checks

```python
def grade(**kwargs) -> dict:
    import hashlib
    import html
    import json
    import re
    from datetime import date
    from pathlib import Path

    root = Path(kwargs.get("workspace_path", "/tmp_workspace"))
    scores = {
        "official_source_and_evidence": 0.0,
        "holiday_dates_verified": 0.0,
        "duration_calculated": 0.0,
        "normalized_output": 0.0,
    }

    def zero_scores():
        scores["overall_score"] = 0.0
        return scores

    try:
        expected = json.loads((root / "gt" / "expected.json").read_text(encoding="utf-8"))
    except Exception:
        return zero_scores()

    if not isinstance(expected, dict):
        return zero_scores()

    def exec_sources_intact():
        try:
            expected_hashes = expected.get("exec_file_sha256")
            if not isinstance(expected_hashes, dict) or not expected_hashes:
                return False

            root_real = root.resolve(strict=True)
            candidates_path = root / "source_candidates.json"
            snapshots_root = root / "snapshots"
            if (
                candidates_path.is_symlink()
                or not candidates_path.is_file()
                or snapshots_root.is_symlink()
                or not snapshots_root.is_dir()
            ):
                return False

            actual_files = {"source_candidates.json"}
            for path in snapshots_root.rglob("*"):
                if path.is_symlink():
                    return False
                if path.is_file():
                    actual_files.add(path.relative_to(root).as_posix())
            if actual_files != set(expected_hashes):
                return False

            for relative_path, expected_digest in expected_hashes.items():
                relative = Path(relative_path)
                if (
                    relative.is_absolute()
                    or ".." in relative.parts
                    or not re.fullmatch(r"[0-9a-f]{64}", str(expected_digest))
                ):
                    return False
                path = root / relative
                if path.is_symlink() or not path.is_file():
                    return False
                resolved = path.resolve(strict=True)
                if root_real not in resolved.parents:
                    return False
                digest = hashlib.sha256()
                with path.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
                if digest.hexdigest() != expected_digest:
                    return False
            return True
        except Exception:
            return False

    if not exec_sources_intact():
        return zero_scores()

    result_path = root / "results" / "verification.json"
    try:
        root_real = root.resolve(strict=True)
        results_dir = root / "results"
        if results_dir.is_symlink() or not results_dir.is_dir():
            return zero_scores()
        results_real = results_dir.resolve(strict=True)
        if results_real.parent != root_real:
            return zero_scores()
        if result_path.is_symlink() or not result_path.is_file():
            return zero_scores()
        if result_path.resolve(strict=True).parent != results_real:
            return zero_scores()
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except Exception:
        return zero_scores()

    if not isinstance(result, dict):
        return zero_scores()

    required = {
        "start_date",
        "end_date",
        "days",
        "adjusted_workdays",
        "source_id",
        "source_url",
        "evidence_quote",
    }
    schema_ok = set(result) == required

    def visible_text(raw):
        raw = re.sub(r"<script\b[^>]*>.*?</script>", " ", raw, flags=re.I | re.S)
        raw = re.sub(r"<style\b[^>]*>.*?</style>", " ", raw, flags=re.I | re.S)
        raw = re.sub(r"<[^>]+>", " ", raw)
        return re.sub(r"\s+", "", html.unescape(raw))

    evidence_ok = False
    try:
        archive = (root / expected["official_snapshot"]).read_text(encoding="utf-8")
        quote_value = result.get("evidence_quote", "")
        quote = re.sub(r"\s+", "", quote_value) if isinstance(quote_value, str) else ""
        evidence_ok = (
            bool(quote)
            and quote in visible_text(archive)
            and all(re.sub(r"\s+", "", item) in quote for item in expected["required_evidence_fragments"])
        )
    except Exception:
        evidence_ok = False

    scores["official_source_and_evidence"] = float(
        result.get("source_id") == expected["official_source_id"]
        and result.get("source_url") == expected["official_source_url"]
        and evidence_ok
    )
    scores["holiday_dates_verified"] = float(
        result.get("start_date") == expected["start_date"]
        and result.get("end_date") == expected["end_date"]
        and result.get("adjusted_workdays") == expected["adjusted_workdays"]
    )

    calculated_days = None
    try:
        start = date.fromisoformat(result.get("start_date", ""))
        end = date.fromisoformat(result.get("end_date", ""))
        calculated_days = (end - start).days + 1
    except Exception:
        pass
    scores["duration_calculated"] = float(
        result.get("days") == expected["days"] == calculated_days
    )

    adjusted = result.get("adjusted_workdays")
    normalized = (
        schema_ok
        and type(result.get("days")) is int
        and isinstance(adjusted, list)
        and len(adjusted) == 2
        and all(isinstance(item, str) for item in adjusted)
        and adjusted == sorted(adjusted)
    )
    if normalized:
        try:
            date.fromisoformat(result["start_date"])
            date.fromisoformat(result["end_date"])
            for item in adjusted:
                date.fromisoformat(item)
        except Exception:
            normalized = False
    scores["normalized_output"] = float(normalized)

    scores["overall_score"] = (
        0.20 * scores["official_source_and_evidence"]
        + 0.30 * scores["holiday_dates_verified"]
        + 0.25 * scores["duration_calculated"]
        + 0.25 * scores["normalized_output"]
    )
    return scores
```

## Workspace Path

```
workspace/extension/04_Search_Retrieval/task_002_cn_holiday_notice_verification
```

## Skills

```
```

## Env

```
```

## Warmup

```
```
