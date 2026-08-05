---
id: 01_Productivity_Flow_task_007_sec_filing_preread
name: Microsoft 2023 filing preread
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

# Microsoft 2023 filing preread

## Prompt

We have a leadership review tomorrow. Use only Microsoft’s 2023 Form 10-K at SEC accession `0000950170-23-035122`:

<https://www.sec.gov/Archives/edgar/data/789019/000095017023035122/msft-20230630.htm>

Create `/tmp_workspace/results/facts.json` with these top-level fields: `source`, `financials`, and `yoy_percent`.

- `source`: `accession,url,fiscal_year_end,unit`.
- `financials`: use the exact keys `total_revenue_2023,total_revenue_2022,operating_income_2023,net_income_2023,total_assets_2023,full_time_employees_approx,segment_revenue_2023,intelligent_cloud_revenue_2022,research_and_development_2023,research_and_development_2022`. `segment_revenue_2023` is an object keyed by the three reportable-segment names used in the filing.
- `yoy_percent`: use the exact keys `total_revenue,intelligent_cloud_revenue,research_and_development`; calculate each 2023-versus-2022 change from the filing values and round to one decimal.

Financial values must use the filing’s `USD millions` unit. Then write `/tmp_workspace/results/microsoft_2023_preread.md` with exactly three management-relevant observations and two review questions. Cite the accession, distinguish reported facts from interpretation, do not give investment advice, and do not save the webpage or create other result files.

## Expected Behavior

The Agent should retrieve the fixed SEC filing, extract the requested 2023 and comparative values from the correct tables, calculate the three changes from unrounded values, and deliver a structured fact file. The preread should make three bounded observations and two useful leadership questions without treating segment revenue as profit or offering investment advice.

## Grading Criteria

### Automated group

- [ ] `filing_identity_correct`: accession, URL, fiscal year end and unit are correct
- [ ] `financial_workforce_facts`: requested financial, segment and workforce values are accurate
- [ ] `yoy_calculations_correct`: the three one-decimal changes are calculated correctly
- [ ] `structured_delivery_correct`: schema, output scope and no-web-copy requirement are satisfied

### Judge group

- [ ] `preread_quality`: three observations and two questions are accurate, useful and appropriately bounded

## Automated Checks

```python
def grade(transcript: list, workspace_path: str) -> dict:
    import json
    from pathlib import Path

    keys = [
        "filing_identity_correct",
        "financial_workforce_facts",
        "yoy_calculations_correct",
        "structured_delivery_correct",
    ]
    scores = {key: 0.0 for key in keys}
    root = Path(workspace_path)

    def mean(flags):
        return sum(1.0 if flag else 0.0 for flag in flags) / len(flags)

    def regular(path):
        return path.is_file() and not path.is_symlink() and not path.parent.is_symlink()

    facts_path = root / "results" / "facts.json"
    preread_path = root / "results" / "microsoft_2023_preread.md"
    try:
        expected = json.loads((root / "gt" / "expected.json").read_text(encoding="utf-8"))
        if not regular(facts_path) or not regular(preread_path):
            return scores
        facts = json.loads(facts_path.read_text(encoding="utf-8"))
        if not isinstance(facts, dict):
            return scores
    except (OSError, UnicodeError, json.JSONDecodeError):
        return scores

    source = facts.get("source") if isinstance(facts.get("source"), dict) else {}
    wanted_source = expected["source"]
    scores["filing_identity_correct"] = mean([
        source.get("accession") == wanted_source["accession"],
        source.get("url") == wanted_source["url"],
        source.get("fiscal_year_end") == wanted_source["fiscal_year_end"],
        source.get("unit") == wanted_source["unit"],
    ])

    actual = facts.get("financials") if isinstance(facts.get("financials"), dict) else {}
    wanted = expected["financials"]
    simple_fields = [
        "total_revenue_2023", "total_revenue_2022", "operating_income_2023",
        "net_income_2023", "total_assets_2023", "full_time_employees_approx",
        "intelligent_cloud_revenue_2022", "research_and_development_2023",
        "research_and_development_2022",
    ]
    fact_flags = [actual.get(field) == wanted[field] for field in simple_fields]
    actual_segments = actual.get("segment_revenue_2023") if isinstance(actual.get("segment_revenue_2023"), dict) else {}
    fact_flags.extend(actual_segments.get(name) == value for name, value in wanted["segment_revenue_2023"].items())
    scores["financial_workforce_facts"] = mean(fact_flags)

    actual_yoy = facts.get("yoy_percent") if isinstance(facts.get("yoy_percent"), dict) else {}
    scores["yoy_calculations_correct"] = mean([
        isinstance(actual_yoy.get(key), (int, float))
        and not isinstance(actual_yoy.get(key), bool)
        and abs(float(actual_yoy[key]) - value) <= 0.05
        for key, value in expected["yoy_percent"].items()
    ])

    exact_top = set(facts) == {"source", "financials", "yoy_percent"}
    exact_source = set(source) == {"accession", "url", "fiscal_year_end", "unit"}
    exact_financials = set(actual) == set(wanted)
    exact_yoy = set(actual_yoy) == set(expected["yoy_percent"])
    results = root / "results"
    result_files = sorted(path.name for path in results.iterdir() if path.is_file() or path.is_symlink()) if results.is_dir() else []
    web_suffixes = {".html", ".htm", ".mhtml", ".pdf"}
    saved_web_copy = any(
        path.is_file() and "gt" not in path.relative_to(root).parts and path.suffix.lower() in web_suffixes
        for path in root.rglob("*")
    )
    scores["structured_delivery_correct"] = mean([
        exact_top and exact_source and exact_financials and exact_yoy,
        result_files == ["facts.json", "microsoft_2023_preread.md"],
        regular(facts_path) and regular(preread_path),
        not saved_web_copy,
    ])
    return {key: round(value, 6) for key, value in scores.items()}
```

## LLM Judge Rubric

### Criterion 1: Preread quality (key: preread_quality, weight: 1.0)

Judge `/tmp_workspace/results/microsoft_2023_preread.md` only against the fixed filing and ground-truth facts. Do not add an overall-impression criterion.

**Score 1.0**: The preread contains exactly three distinct observations, each supported by requested filing facts with correct period and unit, plus exactly two decision-relevant review questions; it distinguishes revenue, income and segment measures, cites the accession, and gives no investment advice.

**Score 0.75**: The structure and facts are correct, but one observation is mostly descriptive or one question is less decision-relevant; periods, units and boundaries remain accurate.

**Score 0.5**: Most facts are correct, but the note mainly lists numbers, has only one effective question, or contains one material period, unit or measure ambiguity.

**Score 0.25**: Several observations are unsupported, segment revenue is confused with profit, the required structure is substantially incomplete, or the note contains broad investment-oriented interpretation.

**Score 0.0**: The filing or core values are wrong, observations materially contradict the source, explicit buy/sell advice is given, or no usable preread is delivered.

## Workspace Path

```
workspace/extension/01_Productivity_Flow/task_007_sec_filing_preread
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

- 运行时只访问task_sources.yaml登记的固定SEC页面；访问失败视为任务失败。
- `exec/`不保存网页或PDF副本。
