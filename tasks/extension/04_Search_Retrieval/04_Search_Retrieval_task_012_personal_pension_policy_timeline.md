---
id: 04_Search_Retrieval_task_012_personal_pension_policy_timeline
name: 个人养老金政策时间线核验
category: 04_Search_Retrieval
timeout_seconds: 900
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L4
grading_type: hybrid
grading_weights:
  automated: 0.4
  llm_judge: 0.6
tags:
  - custom
---

# 个人养老金政策时间线核验

## Prompt

我看到有的文章写个人养老金从2022年4月开始，有的写2022年11月，还有的写2024年12月。请只用下面四份中国政府网固定政策原文说明这些日期分别指什么：

- https://www.gov.cn/zhengce/content/2022-04/21/content_5686402.htm
- https://www.gov.cn/zhengce/zhengceku/2022-11/05/content_5724783.htm
- https://www.gov.cn/zhengce/zhengceku/2022-11/25/content_5728839.htm
- https://www.gov.cn/zhengce/zhengceku/202412/content_6992279.htm

生成`/tmp_workspace/results/pension_timeline.csv`，列严格为`stage,document_number,document_date,published_or_effective_date,coverage,source_url`。按时间顺序使用`institutional_framework,implementation_measures,pilot_in_36_cities_or_regions,national_implementation`四个stage值，日期使用`YYYY-MM-DD`。`coverage`使用简洁自然语言准确概括各阶段的覆盖范围与生效方式，不要求固定措辞。

再写`/tmp_workspace/results/answer.md`，区分制度框架、实施办法、36个城市或地区先行实施、全国实施四个节点，并直接回答“到底从什么时候开始”。不要保存网页副本，不要使用媒体摘要或其他来源代替原文，也不要创建其他结果文件。

## Expected Behavior

Agent应建立四节点时间线：国办发〔2022〕7号于2022-04-08成文、2022-04-21发布并建立制度框架；人社部发〔2022〕70号于2022-10-26成文并自印发日起实施；人社厅函〔2022〕169号于2022-11-17成文并在36个城市或地区先行实施；人社部发〔2024〕87号于2024-12-10成文并自2024-12-15起全国实施。回答应说明“开始”取决于所问阶段。

## Grading Criteria

### Automated group

- [ ] `document_identity`：四份政策、文号和固定URL一一对应 — 20%
- [ ] `milestone_dates`：四个阶段的成文、发布或生效日期正确 — 35%
- [ ] `coverage_and_effect`：制度框架、实施规则、36地先行和全国实施范围正确 — 25%
- [ ] `structured_delivery`：CSV四行、列、日期格式、两个输出及网页副本边界正确 — 20%

### Judge group

- [ ] `stage_distinction`：四个日期节点分别对应四份政策及其作用 — 40%
- [ ] `direct_answer_quality`：说明“开始”取决于阶段，并给出先行和全国两个运行节点 — 35%
- [ ] `date_scope_boundary`：不把发布等同全国实施，不扩大36地范围且不遗漏2024-12-15 — 25%

## Automated Checks

```python
def grade(**kwargs) -> dict:
    import csv
    import json
    import re
    from pathlib import Path

    root = Path(kwargs.get("workspace_path", "/tmp_workspace"))
    keys = ["document_identity", "milestone_dates", "coverage_and_effect", "structured_delivery"]
    scores = {key: 0.0 for key in keys}

    def mean(flags):
        return sum(1.0 if flag else 0.0 for flag in flags) / len(flags)

    def regular(path):
        return path.is_file() and not path.is_symlink() and not path.parent.is_symlink()

    def norm(value):
        return re.sub(r"[\s，,。；;、：:（）()]", "", str(value or "")).lower()

    def has_any(text, *tokens):
        return any(token in text for token in tokens)

    def coverage_matches(stage, value):
        text = norm(value)
        if stage == "institutional_framework":
            return (
                "个人养老金" in text
                and has_any(text, "制度", "框架")
                and has_any(text, "建立", "确立", "构建", "框架")
            )
        if stage == "implementation_measures":
            return (
                "账户" in text
                and "流程" in text
                and has_any(text, "管理规则", "管理规范", "管理办法", "监管规则")
                and has_any(text, "印发之日", "印发日起", "发布后", "公布后")
                and has_any(text, "施行", "实施", "生效")
            )
        if stage == "pilot_in_36_cities_or_regions":
            return (
                "36" in text
                and has_any(text, "城市", "地区")
                and has_any(text, "先行", "试点", "率先")
                and not has_any(text, "非36", "不是36", "未在36", "不在36")
            )
        if stage == "national_implementation":
            return (
                "全国" in text
                and has_any(text, "实施", "施行", "落地")
                and not has_any(text, "非全国", "不是全国", "尚未全国", "未在全国", "不在全国")
            )
        return False

    try:
        expected = json.loads((root / "gt" / "expected.json").read_text(encoding="utf-8"))
        csv_path = root / "results" / "pension_timeline.csv"
        answer_path = root / "results" / "answer.md"
        if not regular(csv_path) or not regular(answer_path):
            raise ValueError("regular result files required")
        with csv_path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            fieldnames = reader.fieldnames
            rows = list(reader)
        answer_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError, ValueError, TypeError, csv.Error):
        return {**scores, "overall_score": 0.0}

    columns = ["stage", "document_number", "document_date", "published_or_effective_date", "coverage", "source_url"]
    rows_are_well_formed = all(
        isinstance(row, dict)
        and set(row) == set(columns)
        and None not in row
        and all(value is not None for value in row.values())
        for row in rows
    )
    expected_by_stage = {row["stage"]: row for row in expected["rows"]}
    actual_by_stage = {row.get("stage"): row for row in rows if isinstance(row, dict)}
    stages = [row["stage"] for row in expected["rows"]]
    scores["document_identity"] = mean([
        actual_by_stage.get(stage, {}).get("document_number") == expected_by_stage[stage]["document_number"]
        and actual_by_stage.get(stage, {}).get("source_url") == expected_by_stage[stage]["source_url"]
        for stage in stages
    ])
    date_flags = []
    coverage_flags = []
    for stage in stages:
        actual = actual_by_stage.get(stage, {})
        wanted = expected_by_stage[stage]
        date_flags.extend([
            actual.get("document_date") == wanted["document_date"],
            actual.get("published_or_effective_date") == wanted["published_or_effective_date"],
        ])
        coverage_flags.append(coverage_matches(stage, actual.get("coverage")))
    scores["milestone_dates"] = mean(date_flags)
    scores["coverage_and_effect"] = mean(coverage_flags)

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
    date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    scores["structured_delivery"] = mean([
        fieldnames == columns and rows_are_well_formed,
        [row.get("stage") for row in rows] == stages,
        len(rows) == 4,
        all(date_pattern.fullmatch(row.get("document_date", "")) for row in rows),
        all(date_pattern.fullmatch(row.get("published_or_effective_date", "")) for row in rows),
        files == expected["result_files"],
        regular(csv_path) and regular(answer_path),
        not forbidden,
    ])
    scores = {key: round(value, 6) for key, value in scores.items()}
    scores["overall_score"] = round(
        0.20 * scores["document_identity"]
        + 0.35 * scores["milestone_dates"]
        + 0.25 * scores["coverage_and_effect"]
        + 0.20 * scores["structured_delivery"],
        6,
    )
    return scores
```

## LLM Judge Rubric

Judge only `/tmp_workspace/results/answer.md` against the four fixed policy pages and `pension_timeline.csv`. Do not add an overall-impression criterion. Different clear policy explanations are acceptable. Each score must be one of `1.0 / 0.75 / 0.5 / 0.25 / 0.0`.

### Criterion 1: Stage distinction (key: stage_distinction, weight: 0.40)

Evaluate whether each date is tied to the correct document and policy function.

**Score 1.0**: Distinguishes the April 2022 framework, October 2022 implementation measures, November 2022 pilot in 36 cities or regions, and December 2024 nationwide implementation, with the corresponding document numbers and roles accurate.

**Score 0.75**: All four stages are correctly ordered and characterized, but one secondary document date, number, or role detail is incomplete.

**Score 0.5**: Identifies the pilot and nationwide stages but conflates or underexplains the framework and implementation-measures stages.

**Score 0.25**: Lists several dates without reliably matching them to documents and effects, or materially confuses two stages.

**Score 0.0**: Gives a substantially false timeline, relies on a non-fixed source, or omits the stage explanation.

### Criterion 2: Direct-answer quality (key: direct_answer_quality, weight: 0.35)

Evaluate whether the response directly resolves the user's “when did it start” ambiguity.

**Score 1.0**: Explains that “start” depends on whether the user means the policy framework, implementation rules, operational pilot, or nationwide availability, and directly gives November 2022 for the pilot and 2024-12-15 for nationwide implementation.

**Score 0.75**: Gives the conditional answer and both operational milestones, but one secondary framework or rules date is not emphasized.

**Score 0.5**: Gives one correct operational start date but does not clearly explain why the other dates also appear.

**Score 0.25**: Selects a single date without resolving the ambiguity, though that date belongs to one real stage.

**Score 0.0**: Gives a wrong operational date, claims there is no meaningful distinction, or omits the direct answer.

### Criterion 3: Date and scope boundary (key: date_scope_boundary, weight: 0.25)

Evaluate whether publication, effectiveness, pilot coverage, and nationwide coverage remain distinct.

**Score 1.0**: Does not equate the April publication with nationwide operation, does not expand the 36-location pilot, states the measures' effect accurately, and includes nationwide effectiveness on 2024-12-15.

**Score 0.75**: All material boundaries are correct, with one minor publication/effectiveness qualifier left implicit.

**Score 0.5**: Preserves pilot versus nationwide scope but blurs one framework or implementation publication/effect date.

**Score 0.25**: Materially overstates one stage's coverage or treats a publication date as nationwide operation.

**Score 0.0**: Claims nationwide operation began in April or November 2022, omits the 2024-12-15 effective date, invents coverage, or provides no boundary explanation.

## Workspace Path

```
workspace/extension/04_Search_Retrieval/task_012_personal_pension_policy_timeline
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

- Auto组内权重为20%、35%、25%、20%，整体占40%。
- Judge组内权重为40%、35%、25%，整体占60%。
