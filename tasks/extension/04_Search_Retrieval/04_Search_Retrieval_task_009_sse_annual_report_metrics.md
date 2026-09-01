---
id: 04_Search_Retrieval_task_009_sse_annual_report_metrics
name: 贵州茅台年报研发费用口径复核
category: 04_Search_Retrieval
timeout_seconds: 900
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

# 贵州茅台年报研发费用口径复核

## Prompt

同事从贵州茅台2023年年度报告里摘了几个数，我需要按原表复核。只使用上海证券交易所这份固定PDF：

https://static.sse.com.cn/disclosure/listedinfo/announcement/c/new/2024-04-03/600519_20240403_W0YD.pdf

将结果保存到`/tmp_workspace/results/moutai_metrics.json`，顶层字段严格为`security_code,report_year,disclosure_date,unit,total_operating_revenue,net_profit_attributable_to_listed_company_shareholders,research_and_development_expense,ratio_formula,ratio_percent,source_url`。`security_code`使用JSON字符串`"600519"`，`report_year`使用JSON整数`2023`，`unit`写为`"人民币元"`；三个金额和`ratio_percent`使用JSON数字。`ratio_percent`按`research_and_development_expense / total_operating_revenue * 100`计算并保留2位小数；`ratio_formula`可使用这两个字段名或实际金额表示同一运算关系。

再写`/tmp_workspace/results/metric_note.md`，说明这里使用的是合并利润表“研发费用”，不是“研发投入合计”，并标注对应表名或年报页码。不要保存PDF副本，不要使用其他来源，不要给投资建议或创建其他结果文件。

## Expected Behavior

Agent应提取证券代码600519、报告年度2023、披露日期2024-04-03、营业总收入150,560,330,316.45元、归属于上市公司股东的净利润74,734,071,550.75元及合并利润表研发费用157,371,873.01元。指定比率为0.104524%，按2位小数输出0.10%，并与研发投入合计621,507,535.87元及年报0.42%的另一口径区分。

## Grading Criteria

### Automated group

- [ ] `report_identity`：证券代码、报告年度、披露日期和固定URL正确 — 20%
- [ ] `reported_metrics`：营业总收入、归母净利润和研发费用精确到元 — 35%
- [ ] `ratio_calculation`：以研发费用为分子计算并输出0.10% — 25%
- [ ] `structured_delivery`：JSON类型、单位、两个输出及PDF副本边界正确 — 20%

### Judge group

- [ ] `metric_distinction`：利润表研发费用、研发投入合计和营业总收入三种口径不混用 — 60%
- [ ] `note_usability`：表名或页码清楚，说明可直接用于复核记录 — 40%

## Automated Checks

```python
def grade(**kwargs) -> dict:
    import json
    import math
    import re
    from pathlib import Path

    root = Path(kwargs.get("workspace_path", "/tmp_workspace"))
    keys = ["report_identity", "reported_metrics", "ratio_calculation", "structured_delivery"]
    scores = {key: 0.0 for key in keys}

    def mean(flags):
        return sum(1.0 if flag else 0.0 for flag in flags) / len(flags)

    def regular(path):
        return path.is_file() and not path.is_symlink() and not path.parent.is_symlink()

    def number(value):
        return type(value) in (int, float) and math.isfinite(float(value))

    def integer_like(value):
        if type(value) is int:
            return value
        if type(value) is str and re.fullmatch(r"\d+", value.strip()):
            return int(value.strip())
        return None

    def same_number(value, wanted, tolerance=0.0):
        return number(value) and abs(float(value) - float(wanted)) <= tolerance

    try:
        expected = json.loads((root / "gt" / "expected.json").read_text(encoding="utf-8"))
        json_path = root / "results" / "moutai_metrics.json"
        note_path = root / "results" / "metric_note.md"
        if not regular(json_path):
            raise ValueError("regular JSON result required")
        answer = json.loads(json_path.read_text(encoding="utf-8"))
        if not isinstance(answer, dict):
            raise ValueError("JSON object required")
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        return {**scores, "overall_score": 0.0}

    fields = {
        "security_code", "report_year", "disclosure_date", "unit", "total_operating_revenue",
        "net_profit_attributable_to_listed_company_shareholders", "research_and_development_expense",
        "ratio_formula", "ratio_percent", "source_url",
    }
    exact_schema = (
        set(answer) == fields
        and type(answer.get("security_code")) is str
        and type(answer.get("report_year")) is int
        and all(type(answer.get(k)) is str for k in {"disclosure_date", "unit", "ratio_formula", "source_url"})
        and all(number(answer.get(k)) for k in {
            "total_operating_revenue", "net_profit_attributable_to_listed_company_shareholders",
            "research_and_development_expense", "ratio_percent",
        })
    )

    scores["report_identity"] = mean([
        str(answer.get("security_code", "")).strip() == expected["security_code"],
        integer_like(answer.get("report_year")) == expected["report_year"],
        answer.get("disclosure_date") == expected["disclosure_date"],
        answer.get("source_url") == expected["source_url"],
    ])
    scores["reported_metrics"] = mean([
        same_number(answer.get("total_operating_revenue"), expected["total_operating_revenue"], 0.005),
        same_number(
            answer.get("net_profit_attributable_to_listed_company_shareholders"),
            expected["net_profit_attributable_to_listed_company_shareholders"],
            0.005,
        ),
        same_number(answer.get("research_and_development_expense"), expected["research_and_development_expense"], 0.005),
    ])
    formula = re.sub(r"[\s,]", "", str(answer.get("ratio_formula", ""))).replace("÷", "/").replace("×", "*").lower()
    formula_has_operands = (
        ("157371873.01" in formula and "150560330316.45" in formula)
        or (
            "research_and_development_expense" in formula
            and "total_operating_revenue" in formula
        )
    )
    ratio = answer.get("ratio_percent")
    scores["ratio_calculation"] = mean([
        formula_has_operands and "/" in formula,
        same_number(ratio, expected["ratio_percent"], 0.005),
        number(ratio)
        and round(expected["research_and_development_expense"] / expected["total_operating_revenue"] * 100, 2)
        == round(float(ratio), 2),
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
        answer.get("unit") == expected["unit"],
        files == expected["result_files"],
        regular(json_path) and regular(note_path),
        not forbidden,
    ])
    scores = {key: round(value, 6) for key, value in scores.items()}
    scores["overall_score"] = round(
        0.20 * scores["report_identity"]
        + 0.35 * scores["reported_metrics"]
        + 0.25 * scores["ratio_calculation"]
        + 0.20 * scores["structured_delivery"],
        6,
    )
    return scores
```

## LLM Judge Rubric

Judge only `/tmp_workspace/results/metric_note.md` against the fixed SSE annual report and `moutai_metrics.json`. Do not add an overall-impression criterion. Equivalent accounting explanations are acceptable. Each score must be one of `1.0 / 0.75 / 0.5 / 0.25 / 0.0`.

### Criterion 1: Metric distinction (key: metric_distinction, weight: 0.60)

Evaluate whether the note distinguishes the selected income-statement expense from the separate R&D-investment disclosure and denominator.

**Score 1.0**: Identifies 157,371,873.01 yuan as the consolidated income-statement R&D expense, 150,560,330,316.45 yuan as total operating revenue, and 621,507,535.87 yuan/0.42% as the separate R&D-investment disclosure; explains why this task yields 0.10%.

**Score 0.75**: The selected metric and 0.10% conclusion are correct, but one secondary amount, label, or distinction is omitted.

**Score 0.5**: Recognizes that 0.10% and 0.42% use different numerators but does not clearly identify both source rows or the denominator.

**Score 0.25**: Mixes the two R&D measures in a material way while retaining one correct figure.

**Score 0.0**: Uses R&D investment as the required numerator, reports 0.42% as the task result, materially misstates the financial statements, or omits the note.

### Criterion 2: Note usability (key: note_usability, weight: 0.40)

Evaluate whether the note is traceable and ready for a financial-review record.

**Score 1.0**: Gives the relevant consolidated income-statement and R&D-investment table names or page references, states units and rounding, and avoids investment advice or unsupported interpretation.

**Score 0.75**: The note is directly usable, with only one minor table, page, unit, or rounding detail missing.

**Score 0.5**: The figures are usable but require follow-up because source locations or the rounding explanation are incomplete.

**Score 0.25**: Source location is vague, the note contains a substantial unsupported business claim, or the required distinction is difficult to audit.

**Score 0.0**: Gives no traceable source location, relies on another publication, provides investment advice, or omits the review record.

## Workspace Path

```
workspace/extension/04_Search_Retrieval/task_009_sse_annual_report_metrics
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

- Auto组内权重为20%、35%、25%、20%，整体占70%。
- Judge组内权重为60%、40%，整体占30%。
