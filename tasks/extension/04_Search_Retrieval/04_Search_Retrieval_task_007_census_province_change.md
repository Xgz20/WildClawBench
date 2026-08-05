---
id: 04_Search_Retrieval_task_007_census_province_change
name: 三省两次人口普查变化复核
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

# 三省两次人口普查变化复核

## Prompt

我需要核对广东、浙江、黑龙江在第六次和第七次全国人口普查之间的人口变化。请只使用国家统计局这两份固定公报：

- 2010：https://www.stats.gov.cn/sj/tjgb/rkpcgb/qgrkpcgb/202302/t20230206_1901998.html
- 2020：https://www.stats.gov.cn/sj/zxfb/202302/t20230203_1901083.html

生成`/tmp_workspace/results/province_change.csv`，列严格为`province,population_2010,population_2020,absolute_change,percent_change`，只保留广东、浙江、黑龙江三行并按这个顺序排列。人数使用公报原始整数，`absolute_change`按2020减2010计算，`percent_change`按`(2020-2010)/2010*100`计算并保留2位小数。

再写`/tmp_workspace/results/calculation_note.md`说明公报口径、公式、三省增减方向和两个固定来源。不要保存网页副本，不要使用其他来源，也不要推断变化原因或创建其他结果文件。

## Expected Behavior

Agent应从两份国家统计局公报提取六个人口整数，计算广东增加21,709,378人、20.81%，浙江增加10,140,697人、18.63%，黑龙江减少6,462,136人、16.87%。说明只描述相同公报口径下的数值变化，不作因果解释。

## Grading Criteria

### Automated group

- [ ] `official_sources`：两份人口普查公报身份和固定URL正确 — 20%
- [ ] `population_values`：三省2010和2020人口整数完整正确 — 35%
- [ ] `change_calculations`：三省增减量、符号及两位小数百分比正确 — 30%
- [ ] `structured_delivery`：CSV列、三行、两个输出及网页副本边界正确 — 15%

### Judge group

- [ ] `methodology_and_interpretation`：公报口径、公式、三省增减方向均有依据且无因果推断 — 100%

## Automated Checks

```python
def grade(**kwargs) -> dict:
    import csv
    import json
    import math
    from pathlib import Path

    root = Path(kwargs.get("workspace_path", "/tmp_workspace"))
    keys = ["official_sources", "population_values", "change_calculations", "structured_delivery"]
    scores = {key: 0.0 for key in keys}

    def mean(flags):
        return sum(1.0 if flag else 0.0 for flag in flags) / len(flags)

    def regular(path):
        return path.is_file() and not path.is_symlink() and not path.parent.is_symlink()

    try:
        expected = json.loads((root / "gt" / "expected.json").read_text(encoding="utf-8"))
        csv_path = root / "results" / "province_change.csv"
        note_path = root / "results" / "calculation_note.md"
        if not regular(csv_path) or not regular(note_path):
            raise ValueError("regular result files required")
        with csv_path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            fieldnames = reader.fieldnames
            rows = list(reader)
        note = note_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError, ValueError, TypeError, csv.Error):
        return {**scores, "overall_score": 0.0}

    columns = ["province", "population_2010", "population_2020", "absolute_change", "percent_change"]
    def parse_int(value):
        try:
            if str(int(value)) != str(value).strip():
                return None
            return int(value)
        except (TypeError, ValueError):
            return None

    def parse_float(value):
        try:
            result = float(value)
            return result if math.isfinite(result) else None
        except (TypeError, ValueError):
            return None

    expected_by_name = {row["province"]: row for row in expected["rows"]}
    actual_by_name = {row.get("province"): row for row in rows if isinstance(row, dict)}
    scores["official_sources"] = mean([
        expected["source_urls"][0] in note,
        expected["source_urls"][1] in note,
        "第六次" in note and "第七次" in note and "全国人口普查" in note,
    ])
    population_flags = []
    calculation_flags = []
    for province in ["广东", "浙江", "黑龙江"]:
        actual = actual_by_name.get(province, {})
        wanted = expected_by_name[province]
        population_flags.extend([
            parse_int(actual.get("population_2010")) == wanted["population_2010"],
            parse_int(actual.get("population_2020")) == wanted["population_2020"],
        ])
        percent = parse_float(actual.get("percent_change"))
        calculation_flags.extend([
            parse_int(actual.get("absolute_change")) == wanted["absolute_change"],
            percent is not None and abs(percent - wanted["percent_change"]) <= 0.005,
            percent is not None and f"{percent:.2f}" == str(actual.get("percent_change")).strip().lstrip("+"),
        ])
    scores["population_values"] = mean(population_flags)
    scores["change_calculations"] = mean(calculation_flags)

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
        fieldnames == columns,
        [row.get("province") for row in rows] == ["广东", "浙江", "黑龙江"],
        len(rows) == 3,
        files == expected["result_files"],
        regular(csv_path) and regular(note_path),
        not forbidden,
    ])
    scores = {key: round(value, 6) for key, value in scores.items()}
    scores["overall_score"] = round(
        0.20 * scores["official_sources"]
        + 0.35 * scores["population_values"]
        + 0.30 * scores["change_calculations"]
        + 0.15 * scores["structured_delivery"],
        6,
    )
    return scores
```

## LLM Judge Rubric

Judge only `/tmp_workspace/results/calculation_note.md` against the two fixed National Bureau of Statistics bulletins and `province_change.csv`. Do not add an overall-impression criterion. Different concise explanations are acceptable. Each score must be one of `1.0 / 0.75 / 0.5 / 0.25 / 0.0`.

### Criterion 1: Methodology and interpretation (key: methodology_and_interpretation, weight: 1.00)

Evaluate whether the note explains the comparison basis and calculations and interprets only what the three rows support.

**Score 1.0**: Identifies the sixth- and seventh-census provincial population tables, states both formulas, accurately describes Guangdong and Zhejiang as increases and Heilongjiang as a decrease, and makes no causal claim.

**Score 0.75**: The sources, formulas, and all directions are correct, but one secondary rounding or comparison detail is omitted.

**Score 0.5**: The main trends are correct, but the source scope or one formula is incomplete, or one minor unsupported explanation appears without dominating the note.

**Score 0.25**: Misstates at least one direction or formula, or causal speculation occupies a substantial part of the note.

**Score 0.0**: Materially contradicts the CSV or official bulletins, substitutes another source, bases the answer on unsupported causation, or omits the note.

## Workspace Path

```
workspace/extension/04_Search_Retrieval/task_007_census_province_change
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

- Auto组内权重为20%、35%、30%、15%，整体占70%。
- Judge组只有一个检查点，整体占30%。
