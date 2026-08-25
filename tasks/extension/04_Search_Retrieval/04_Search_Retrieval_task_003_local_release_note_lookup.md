---
id: 04_Search_Retrieval_task_003_local_release_note_lookup
name: pip覆盖选项首次版本检索
category: 04_Search_Retrieval
timeout_seconds: 300
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L1
grading_type: automated
grading_weights:
  automated: 1.0
  llm_judge: 0.0
tags:
  - custom
---

## Prompt

Our Debian build note says pip 23.0 blocked editable installs in an `EXTERNALLY-MANAGED` environment. I copied the official release-note sections for nearby pip releases into `/tmp_workspace/pip_news/NEWS_excerpt.rst`.

Without using the network, find the first release in that file that documents an override. Save a UTF-8 JSON object to `/tmp_workspace/results/lookup.json` with exactly these fields and types:

```json
{
  "version": "release version",
  "release_date": "YYYY-MM-DD",
  "option": "option name",
  "purpose": "exact purpose wording without reStructuredText markup",
  "reference": "#number",
  "evidence_file": "path relative to /tmp_workspace",
  "evidence_quote": "one continuous exact sentence from the notes"
}
```

Use the earliest release in the supplied notes that contains the feature. Preserve the option spelling and evidence sentence exactly, use the documented purpose wording, and identify the referenced GitHub item. The result must be a regular file, not a symlink. Do not modify the release notes.

## Expected Behavior

Agent searches the four fixed pip release-note excerpts locally, identifies pip 23.0.1 dated 2023-02-17 as the first release documenting `--break-system-packages`, records its documented purpose and reference `#11780`, and quotes the feature sentence without changing its wording.

## Grading Criteria

- [ ] `first_matching_release`：版本和发布日期正确 — 35%（`retrieval_verification`、`reasoning_planning`）
- [ ] `feature_details`：选项、用途和引用正确 — 25%（`retrieval_verification`、`data_processing`）
- [ ] `evidence_traceable`：连续原文可在指定附件中定位 — 25%（`retrieval_verification`）
- [ ] `delivery_and_input_integrity`：JSON结构、路径和输入完整性正确 — 15%（`verification_delivery`）

The exact schema, regular-file requirement, and input hashes are output-validity requirements. A schema error, symlink, unreadable result, or modified input makes every checkpoint zero and does not create an additional checkpoint.

## Automated Checks

```python
def grade(**kwargs) -> dict:
    import hashlib
    import json
    import re
    from pathlib import Path

    root = Path(kwargs.get("workspace_path", "/tmp_workspace"))
    keys = [
        "first_matching_release",
        "feature_details",
        "evidence_traceable",
        "delivery_and_input_integrity",
    ]
    scores = {key: 0.0 for key in keys}

    def mean(flags):
        return sum(1.0 if flag else 0.0 for flag in flags) / len(flags)

    def normalize_space(value):
        return re.sub(r"\s+", " ", str(value or "")).strip()

    result_path = root / "results" / "lookup.json"
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
        "version": str,
        "release_date": str,
        "option": str,
        "purpose": str,
        "reference": str,
        "evidence_file": str,
        "evidence_quote": str,
    }
    exact_schema = set(answer) == set(required_types) and all(
        type(answer.get(field)) is expected_type
        for field, expected_type in required_types.items()
    )
    if not exact_schema:
        return {**scores, "overall_score": 0.0}

    evidence_file = root / answer["evidence_file"]
    try:
        evidence_text = evidence_file.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        evidence_text = ""

    scores["first_matching_release"] = mean([
        answer["version"] == expected["version"],
        answer["release_date"] == expected["release_date"],
    ])
    scores["feature_details"] = mean([
        answer["option"] == expected["option"],
        normalize_space(answer["purpose"]) == normalize_space(expected["purpose"]),
        answer["reference"] == expected["reference"],
    ])
    expected_quote = normalize_space(expected["evidence_quote"])
    actual_quote = normalize_space(answer["evidence_quote"])
    scores["evidence_traceable"] = mean([
        actual_quote == expected_quote,
        bool(expected_quote) and expected_quote in normalize_space(evidence_text),
    ])
    scores["delivery_and_input_integrity"] = mean([
        answer["evidence_file"] == expected["evidence_file"],
        evidence_file.is_file() and not evidence_file.is_symlink(),
        result_path.is_file() and not result_path.is_symlink(),
    ])

    scores = {key: round(value, 4) for key, value in scores.items()}
    scores["overall_score"] = round(
        0.35 * scores["first_matching_release"]
        + 0.25 * scores["feature_details"]
        + 0.25 * scores["evidence_traceable"]
        + 0.15 * scores["delivery_and_input_integrity"],
        4,
    )
    return scores
```

## LLM Judge Rubric

This task uses automated grading only.

## Workspace Path

```
workspace/extension/04_Search_Retrieval/task_003_local_release_note_lookup
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
