---
id: 04_Search_Retrieval_task_006_rfc_http_obsolescence
name: HTTP RFC replacement mapping
category: 04_Search_Retrieval
timeout_seconds: 600
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

# HTTP RFC replacement mapping

## Prompt

Our internal HTTP guide still cites RFC 7230 and RFC 7231. I need a precise replacement note, not a general web search. Use only these fixed RFC Editor records:

- https://www.rfc-editor.org/info/rfc7230
- https://www.rfc-editor.org/info/rfc7231
- https://www.rfc-editor.org/info/rfc9110
- https://www.rfc-editor.org/info/rfc9112

Create `/tmp_workspace/results/rfc_replacement_map.json` with exactly two top-level fields: `records,source_urls`. `records` must contain one object for each old RFC with fields `old_rfc,replacements`; every item in `replacements` must use `rfc,publication_month,scope,source_url`. Use `YYYY-MM` for publication months and preserve the source URL spelling above. Keep the records in old-RFC order and replacement entries in RFC-number order.

Then write `/tmp_workspace/results/migration_note.md` explaining which new RFC our guide should cite for HTTP semantics and which it should cite for HTTP/1.1 message syntax. Do not save copies of the pages, use other sources, edit the guide, or create other result files.

## Expected Behavior

Agent should map RFC 7230 to RFC 9110 and RFC 9112, map RFC 7231 to RFC 9110, identify both replacements as published in 2022-06, and distinguish HTTP semantics from HTTP/1.1 message syntax. The note should translate those relationships into an actionable documentation update without expanding either RFC's scope.

## Grading Criteria

### Automated group

- [ ] `source_identity`：four RFC identities and fixed URLs are correct — 20%
- [ ] `replacement_map`：7230 maps to 9110 and 9112; 7231 maps to 9110 — 35%
- [ ] `scope_and_dates`：replacement scopes and 2022-06 publication months are correct — 25%
- [ ] `structured_delivery`：JSON shape, array cardinality, two outputs, and snapshot boundary are correct — 20%

### Judge group

- [ ] `replacement_reasoning`：both replacement relationships and the semantics/message-syntax split follow the RFC records — 60%
- [ ] `migration_note_usability`：the documentation owner receives an actionable, scope-accurate citation change — 40%

## Automated Checks

```python
def grade(**kwargs) -> dict:
    import json
    from pathlib import Path

    root = Path(kwargs.get("workspace_path", "/tmp_workspace"))
    keys = ["source_identity", "replacement_map", "scope_and_dates", "structured_delivery"]
    scores = {key: 0.0 for key in keys}

    def mean(flags):
        return sum(1.0 if flag else 0.0 for flag in flags) / len(flags)

    def regular(path):
        return path.is_file() and not path.is_symlink() and not path.parent.is_symlink()

    try:
        expected = json.loads((root / "gt" / "expected.json").read_text(encoding="utf-8"))
        json_path = root / "results" / "rfc_replacement_map.json"
        note_path = root / "results" / "migration_note.md"
        if not regular(json_path) or not regular(note_path):
            raise ValueError("regular result files required")
        answer = json.loads(json_path.read_text(encoding="utf-8"))
        note_path.read_text(encoding="utf-8")
        if not isinstance(answer, dict):
            raise ValueError("JSON object required")
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        return {**scores, "overall_score": 0.0}

    records = answer.get("records")
    exact_schema = (
        set(answer) == {"records", "source_urls"}
        and type(records) is list
        and type(answer.get("source_urls")) is list
        and len(records) == 2
        and all(
            type(record) is dict
            and set(record) == {"old_rfc", "replacements"}
            and type(record["old_rfc"]) is str
            and type(record["replacements"]) is list
            and all(
                type(item) is dict
                and set(item) == {"rfc", "publication_month", "scope", "source_url"}
                and all(type(item[k]) is str for k in item)
                for item in record["replacements"]
            )
            for record in records
        )
    )
    if not exact_schema:
        return {**scores, "overall_score": 0.0}

    scores["source_identity"] = mean([
        answer["source_urls"] == expected["source_urls"],
        [record["old_rfc"] for record in records] == ["RFC 7230", "RFC 7231"],
        {item["rfc"] for record in records for item in record["replacements"]}
        == {"RFC 9110", "RFC 9112"},
    ])
    actual_map = {
        record["old_rfc"]: [item["rfc"] for item in record["replacements"]]
        for record in records
    }
    expected_map = {
        record["old_rfc"]: [item["rfc"] for item in record["replacements"]]
        for record in expected["records"]
    }
    scores["replacement_map"] = mean([
        actual_map.get("RFC 7230") == expected_map["RFC 7230"],
        actual_map.get("RFC 7231") == expected_map["RFC 7231"],
    ])
    expected_items = {
        (record["old_rfc"], item["rfc"]): item
        for record in expected["records"] for item in record["replacements"]
    }
    actual_items = {
        (record["old_rfc"], item["rfc"]): item
        for record in records for item in record["replacements"]
    }
    scores["scope_and_dates"] = mean([
        actual_items.get(key, {}).get("publication_month") == wanted["publication_month"]
        and actual_items.get(key, {}).get("scope") == wanted["scope"]
        and actual_items.get(key, {}).get("source_url") == wanted["source_url"]
        for key, wanted in expected_items.items()
    ])

    try:
        files = sorted(p.name for p in (root / "results").iterdir() if p.is_file() or p.is_symlink())
    except OSError:
        files = []
    forbidden = [
        p for p in root.rglob("*")
        if p.is_file()
        and "gt" not in p.parts
        and "exec" not in p.parts
        and p.suffix.lower() in {".html", ".htm", ".mhtml", ".pdf", ".warc"}
    ]
    scores["structured_delivery"] = mean([
        exact_schema,
        [len(record["replacements"]) for record in records] == [2, 1],
        files == expected["result_files"],
        regular(json_path) and regular(note_path),
        not forbidden,
    ])
    scores = {key: round(value, 6) for key, value in scores.items()}
    scores["overall_score"] = round(
        0.20 * scores["source_identity"]
        + 0.35 * scores["replacement_map"]
        + 0.25 * scores["scope_and_dates"]
        + 0.20 * scores["structured_delivery"],
        6,
    )
    return scores
```

## LLM Judge Rubric

Judge only `/tmp_workspace/results/migration_note.md` against the four fixed RFC Editor records and `rfc_replacement_map.json`. Do not add an overall-impression criterion. Equivalent technical phrasing is acceptable. Each score must be one of `1.0 / 0.75 / 0.5 / 0.25 / 0.0`.

### Criterion 1: Replacement reasoning (key: replacement_reasoning, weight: 0.60)

Evaluate whether the note explains the replacement graph and scope split supported by the records.

**Score 1.0**: Explains that RFC 7230 is replaced by RFC 9110 plus RFC 9112, RFC 7231 is replaced by RFC 9110, and accurately distinguishes semantics from HTTP/1.1 message syntax.

**Score 0.75**: All mappings are correct, but one secondary scope or publication detail is stated only implicitly.

**Score 0.5**: Identifies RFC 9110 but incompletely handles RFC 9112 or one old-RFC mapping; the main migration direction remains understandable.

**Score 0.25**: Makes a broad statement that both old RFCs are replaced only by RFC 9110, or otherwise loses the scope split.

**Score 0.0**: Treats the old RFCs as current, cites a nonexistent replacement, materially reverses the mapping, or provides no explanation.

### Criterion 2: Migration-note usability (key: migration_note_usability, weight: 0.40)

Evaluate whether a documentation owner can directly apply the citation changes without overextending either new RFC.

**Score 1.0**: Gives explicit citation changes for semantics and message-syntax passages, preserves the fixed source links, and does not claim that either RFC alone replaces every HTTP document.

**Score 0.75**: The recommended changes are actionable, with one minor citation or scope qualification omitted.

**Score 0.5**: The right RFCs are named, but the owner must infer where each citation belongs or one link is missing.

**Score 0.25**: Provides a generic standards summary rather than an actionable update, or substantially overstates scope.

**Score 0.0**: Recommends incorrect citations, relies on another source, or omits the migration note.

## Workspace Path

```
workspace/extension/04_Search_Retrieval/task_006_rfc_http_obsolescence
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

- Auto group weights are 20%, 35%, 25%, and 20%; the group is 70% of the task.
- Judge group weights are 60% and 40%; the group is 30% of the task.
