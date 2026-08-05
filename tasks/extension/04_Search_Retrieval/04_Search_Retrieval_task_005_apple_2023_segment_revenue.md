---
id: 04_Search_Retrieval_task_005_apple_2023_segment_revenue
name: Apple 2023大中华区销售占比复核
category: 04_Search_Retrieval
timeout_seconds: 600
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

# Apple 2023大中华区销售占比复核

## Prompt

我们的简报写着“Apple 2023财年大中华区净销售额约占公司总净销售额的18.9%”。请只用SEC这份固定的Apple 2023 Form 10-K核对，不要引用聚合网站：

https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm

将结果保存到`/tmp_workspace/results/apple_sales_check.json`，顶层字段严格为`fiscal_year,unit,greater_china_net_sales,total_net_sales,share_percent,formula,accession,source_table`。金额沿用年报的`USD millions`，比例按`greater_china_net_sales / total_net_sales * 100`计算并四舍五入到1位小数；`formula`保留实际数字和运算关系。

再写一段`/tmp_workspace/results/brief_correction.md`，说明原句是否成立，并区分地理区域净销售额与产品类别。不要保存网页副本，不要使用其他来源，不要给出投资建议或实际修改简报。

## Expected Behavior

Agent应从固定Form 10-K中识别2023财年Greater China净销售额72,559百万美元及公司总净销售额383,285百万美元，计算18.9308%并按要求输出18.9%。说明应确认原句在指定口径下成立，同时说明Greater China是报告的地理区域而非产品类别。

## Grading Criteria

### Automated group

- [ ] `filing_identity`：Apple 2023 Form 10-K、accession和来源表身份正确 — 20%
- [ ] `sales_values`：大中华区、公司总净销售额及单位正确 — 30%
- [ ] `share_calculation`：公式和四舍五入至1位小数的18.9%正确 — 30%
- [ ] `structured_delivery`：JSON结构、两个输出及网页副本边界正确 — 20%

### Judge group

- [ ] `table_interpretation`：财年、地理区域和公司总额均对应指定表格口径 — 55%
- [ ] `correction_readiness`：直接回答原句是否成立，不混写产品类别或投资判断 — 45%

## Automated Checks

```python
def grade(**kwargs) -> dict:
    import json
    import math
    import re
    from pathlib import Path

    root = Path(kwargs.get("workspace_path", "/tmp_workspace"))
    keys = ["filing_identity", "sales_values", "share_calculation", "structured_delivery"]
    scores = {key: 0.0 for key in keys}

    def mean(flags):
        return sum(1.0 if flag else 0.0 for flag in flags) / len(flags)

    def regular(path):
        return path.is_file() and not path.is_symlink() and not path.parent.is_symlink()

    def number(value):
        return type(value) in (int, float) and math.isfinite(float(value))

    try:
        expected = json.loads((root / "gt" / "expected.json").read_text(encoding="utf-8"))
        json_path = root / "results" / "apple_sales_check.json"
        note_path = root / "results" / "brief_correction.md"
        if not regular(json_path) or not regular(note_path):
            raise ValueError("regular result files required")
        answer = json.loads(json_path.read_text(encoding="utf-8"))
        note_path.read_text(encoding="utf-8")
        if not isinstance(answer, dict):
            raise ValueError("JSON object required")
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        return {**scores, "overall_score": 0.0}

    fields = {
        "fiscal_year", "unit", "greater_china_net_sales", "total_net_sales",
        "share_percent", "formula", "accession", "source_table",
    }
    exact_schema = (
        set(answer) == fields
        and type(answer.get("fiscal_year")) is int
        and all(type(answer.get(k)) is str for k in {"unit", "formula", "accession", "source_table"})
        and all(number(answer.get(k)) for k in {"greater_china_net_sales", "total_net_sales", "share_percent"})
    )
    if not exact_schema:
        return {**scores, "overall_score": 0.0}

    table = answer["source_table"].lower()
    scores["filing_identity"] = mean([
        answer["fiscal_year"] == expected["fiscal_year"],
        answer["accession"] == expected["accession"],
        "net sales" in table and "reportable segment" in table,
    ])
    scores["sales_values"] = mean([
        float(answer["greater_china_net_sales"]) == expected["greater_china_net_sales"],
        float(answer["total_net_sales"]) == expected["total_net_sales"],
        answer["unit"] == expected["unit"],
    ])
    formula = re.sub(r"[\s,]", "", answer["formula"]).replace("÷", "/").replace("×", "*")
    scores["share_calculation"] = mean([
        "72559" in formula and "383285" in formula and "/" in formula,
        abs(float(answer["share_percent"]) - expected["share_percent"]) <= 0.05,
        round(expected["greater_china_net_sales"] / expected["total_net_sales"] * 100, 1)
        == round(float(answer["share_percent"]), 1),
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
        files == expected["result_files"],
        regular(json_path) and regular(note_path),
        not forbidden,
        exact_schema,
    ])
    scores = {key: round(value, 6) for key, value in scores.items()}
    scores["overall_score"] = round(
        0.20 * scores["filing_identity"]
        + 0.30 * scores["sales_values"]
        + 0.30 * scores["share_calculation"]
        + 0.20 * scores["structured_delivery"],
        6,
    )
    return scores
```

## LLM Judge Rubric

Judge only `/tmp_workspace/results/brief_correction.md` against the fixed SEC filing and `apple_sales_check.json`. Do not add an overall-impression criterion. Equivalent concise business wording is acceptable. Each score must be one of `1.0 / 0.75 / 0.5 / 0.25 / 0.0`.

### Criterion 1: Table interpretation (key: table_interpretation, weight: 0.55)

Evaluate whether the note correctly interprets the fiscal year, geographic segment, and company total from the filing.

**Score 1.0**: Correctly identifies FY2023, Greater China net sales as a geographic reporting measure, company total net sales as the denominator, and the USD-millions unit, with no unsupported reinterpretation.

**Score 0.75**: The calculation and geographic interpretation are correct, but one secondary fiscal-year, unit, or table-context detail is implicit.

**Score 0.5**: The 18.9% result is stated, but the geographic segment or denominator context is materially unclear.

**Score 0.25**: Confuses Greater China with a product category, customer nationality, or a profit measure while retaining some correct numbers.

**Score 0.0**: Uses the wrong filing or denominator, materially misstates the table, or provides no usable interpretation.

### Criterion 2: Correction readiness (key: correction_readiness, weight: 0.45)

Evaluate whether the note can be used directly to correct or confirm the briefing statement without adding unsupported claims.

**Score 1.0**: Directly says the statement is supported at 18.9%, gives the short calculation and scope qualification, and avoids product, profit, causal, or investment claims.

**Score 0.75**: The conclusion is ready to use but omits one minor scope or rounding explanation.

**Score 0.5**: Reaches the correct conclusion but needs editing because the calculation, qualification, or source reference is incomplete.

**Score 0.25**: Gives a weak or contradictory recommendation, or adds a substantial unsupported business inference.

**Score 0.0**: States the wrong conclusion, offers investment advice, cites an unapproved source, or omits the correction note.

## Workspace Path

```
workspace/extension/04_Search_Retrieval/task_005_apple_2023_segment_revenue
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

- Auto组内权重为20%、30%、30%、20%，整体占70%。
- Judge组内权重为55%、45%，整体占30%。
