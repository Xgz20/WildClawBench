---
id: 05_Creative_Synthesis_task_007_survey_campaign_pack
name: 调研驱动的两周内容活动方案
category: 05_Creative_Synthesis
timeout_seconds: 300
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L3
grading_type: hybrid
grading_weights:
  automated: 0.4
  llm_judge: 0.6
tags:
  - custom
---

# 调研驱动的两周内容活动方案

## Prompt

用户调研、产品brief和语气规范分别在 `/tmp_workspace/user_research.csv`、`/tmp_workspace/product_brief.md` 和 `/tmp_workspace/tone_guide.md`。帮我做一个两周活动方案：先确定一个活动主线，再排10条内容。每个洞察都要标调研记录ID，每个产品主张都要标feature ID，不能写材料里没有的效果或数据，也不用在交付物里重复禁止清单。

请输出：

1. `/tmp_workspace/results/campaign_plan.md`：说明活动主线、两类受众、从调研归纳的四个主要洞察、洞察与功能的对应关系，以及两周内容节奏。洞察和功能旁保留对应ID。
2. `/tmp_workspace/results/content_calendar.csv`：UTF-8 CSV，列严格为 `date,channel,audience,topic,copy,source_ids`，共10条内容。日期从brief指定的发布日期开始，均落在活动周期内并按升序排列；渠道使用brief中的名称。`source_ids`用英文分号分隔，每行至少包含一个调研ID和一个feature ID。

中文内容为主，文案遵守语气规范。不要联网，不要修改输入文件，不要创建这两个结果之外的交付文件。

## Expected Behavior

Agent应综合12条调研记录为四个有证据的主题，用F-101至F-104的已确认功能回应相应情境，形成连贯的两周活动主线和10条可直接排期的中文内容。所有日期、渠道、受众、主张和来源ID均应与附件一致，不添加量化效果、安全等级或价格承诺。

## Grading Criteria

- [ ] 两个文件、CSV列、10条内容和活动日期正确 — 10%
- [ ] 洞察与产品主张使用有效调研ID和feature ID — 20%
- [ ] 未出现brief禁止的效果、数据和承诺 — 10%
- [ ] 准确综合四个调研主题 — 20%
- [ ] 活动主线与两周内容节奏连贯 — 15%
- [ ] 内容适配两类受众及语气规范 — 15%
- [ ] 内容日历可直接使用 — 10%

前三项由规则评分，后四项由LLM Judge按下方明确档位评分。

## Automated Checks

```python
def grade(transcript: list, workspace_path: str) -> dict:
    import csv
    import hashlib
    import json
    import re
    from datetime import date
    from pathlib import Path

    root = Path(workspace_path)
    keys = [
        "schema_and_dates",
        "source_id_coverage",
        "forbidden_claims_absent",
    ]
    scores = {key: 0.0 for key in keys}

    def mean(flags):
        return sum(1.0 if flag else 0.0 for flag in flags) / len(flags)

    try:
        expected = json.loads(
            (root / "gt" / "expected.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, json.JSONDecodeError):
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

    plan_path = root / "results" / "campaign_plan.md"
    calendar_path = root / "results" / "content_calendar.csv"
    if (
        plan_path.is_symlink()
        or calendar_path.is_symlink()
        or plan_path.parent.is_symlink()
        or not plan_path.is_file()
        or not calendar_path.is_file()
    ):
        return {**scores, "overall_score": 0.0}

    try:
        plan = plan_path.read_text(encoding="utf-8")
        with calendar_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = reader.fieldnames or []
            rows = list(reader)
    except (OSError, UnicodeError, csv.Error):
        return {**scores, "overall_score": 0.0}

    expected_columns = expected["expected_calendar_columns"]
    exact_columns = fieldnames == expected_columns and all(
        set(row) == set(expected_columns) and None not in row
        for row in rows
    )
    nonempty_rows = all(
        all(isinstance(row.get(column), str) and row[column].strip()
            for column in expected_columns)
        for row in rows
    )

    parsed_dates = []
    try:
        parsed_dates = [date.fromisoformat(row["date"].strip()) for row in rows]
    except (KeyError, TypeError, ValueError):
        parsed_dates = []
    launch = date.fromisoformat(expected["launch_date"])
    campaign_end = date.fromisoformat(expected["campaign_end_date"])
    dates_valid = bool(parsed_dates) and all(
        launch <= item <= campaign_end for item in parsed_dates
    )
    dates_ordered = parsed_dates == sorted(parsed_dates)
    dates_span_campaign = (
        len(parsed_dates) == expected["expected_calendar_rows"]
        and parsed_dates[0] == launch
        and parsed_dates[-1] >= date(2026, 9, 14)
    )
    allowed_channels = set(expected["allowed_channels"])
    channels_valid = all(row.get("channel", "").strip() in allowed_channels for row in rows)
    scores["schema_and_dates"] = mean([
        exact_columns and nonempty_rows,
        len(rows) == expected["expected_calendar_rows"],
        dates_valid and dates_ordered and dates_span_campaign,
        channels_valid,
    ])

    allowed_research = set(expected["research_ids"])
    allowed_features = set(expected["feature_ids"])
    id_pattern = re.compile(r"\b[RF]-\d{3}\b", flags=re.I)
    delivery_text = plan + "\n" + "\n".join(
        " ".join(str(value) for value in row.values()) for row in rows
    )
    delivery_ids = {value.upper() for value in id_pattern.findall(delivery_text)}
    all_ids_known = delivery_ids <= (allowed_research | allowed_features)

    row_references_valid = True
    for row in rows:
        source_ids = {
            value.upper() for value in id_pattern.findall(row.get("source_ids", ""))
        }
        row_references_valid = row_references_valid and bool(source_ids & allowed_research)
        row_references_valid = row_references_valid and bool(source_ids & allowed_features)
        row_references_valid = row_references_valid and source_ids <= (
            allowed_research | allowed_features
        )

    theme_coverage = all(
        delivery_ids & set(theme["research_ids"])
        for theme in expected["insight_themes"].values()
    )
    feature_coverage = allowed_features <= delivery_ids
    plan_has_traceability = (
        len(allowed_research & {value.upper() for value in id_pattern.findall(plan)}) >= 4
        and allowed_features
        <= {value.upper() for value in id_pattern.findall(plan)}
    )
    scores["source_id_coverage"] = mean([
        row_references_valid and len(rows) == expected["expected_calendar_rows"],
        theme_coverage,
        feature_coverage,
        plan_has_traceability and all_ids_known,
    ])

    compact_delivery = re.sub(r"\s+", "", delivery_text).lower()
    forbidden_absent = all(
        re.sub(r"\s+", "", phrase).lower() not in compact_delivery
        for phrase in expected["forbidden_claim_patterns"]
    )
    unsupported_number_claim = re.search(
        r"(?:提升|提高|增长|减少|降低|节省)[^。\n]{0,10}"
        r"\d+(?:\.\d+)?\s*(?:%|倍|小时|分钟)",
        delivery_text,
    )
    scores["forbidden_claims_absent"] = 1.0 if (
        forbidden_absent and unsupported_number_claim is None
    ) else 0.0

    scores = {key: round(value, 4) for key, value in scores.items()}
    scores["overall_score"] = round(
        0.25 * scores["schema_and_dates"]
        + 0.50 * scores["source_id_coverage"]
        + 0.25 * scores["forbidden_claims_absent"],
        4,
    )
    return scores
```

## LLM Judge Rubric

### Criterion 1: 调研洞察综合 (key: insight_synthesis, weight: 0.333333)

判据：交付物是否准确综合附件中的四个主题：主动缩小当天重点且不施压、离线记录与跨设备延续、可控制的安静时段、不带评分或排名的每周回看；是否用相关调研ID和feature ID建立可追溯联系。

**Score 1.0**: 四个主题均准确、有实质综合并与相关调研和功能相连；没有把个体观察扩大为普遍效果，也没有虚构材料外事实。

**Score 0.75**: 四个主题均出现且总体准确，仅一个主题的综合较弱、证据联系略显孤立，或有一处不影响主张的轻微概括偏差。

**Score 0.5**: 至少两个主题得到准确综合，但遗漏一个以上主题，或有一项实质误读；交付物仍以附件证据为主要依据。

**Score 0.25**: 只准确处理一个主题，主要罗列功能而未综合调研，或多处把个体观察写成普遍结论。

**Score 0.0**: 核心洞察与附件冲突、主要内容无依据、伪造调研事实，或没有可评价的交付物。

### Criterion 2: 活动连贯性 (key: campaign_coherence, weight: 0.25)

判据：是否形成一个清晰活动主线，并让两周节奏和10条内容共同支持该主线。

**Score 1.0**: 主线清晰，两周内容存在可理解的展开顺序，主题、受众、功能和行动建议互相一致，无逻辑断裂、矛盾或无关内容。

**Score 0.75**: 主线和两周推进均清楚，仅一条内容轻微重复、位置不理想或与主线联系偏弱。

**Score 0.5**: 有可辨认主线，但日历更像松散内容集合；存在一处重大断裂或两至三处重复、跳转问题，整体仍可理解。

**Score 0.25**: 主线只停留在标题，多数内容缺乏顺序或相互矛盾，需要大幅重组。

**Score 0.0**: 没有活动主线，内容不可理解、明显偏题或彼此冲突。

### Criterion 3: 受众与语气适配 (key: audience_fit, weight: 0.25)

判据：内容是否分别适配通勤上班族和小团队负责人，并遵守平静、具体、克制、不施压的中文语气规范。

**Score 1.0**: 两类受众的情境和表达均有区分，中文内容自然具体，全程尊重用户选择，不制造焦虑、不评价自律或效率，也不把个人功能说成团队监控工具。

**Score 0.75**: 整体适配两类受众和语气，仅一处文案对象不够明确、用词略带内部术语或局部语气偏强。

**Score 0.5**: 内容对一般用户仍可用，但两类受众区分较弱，或有多处模板化、施压式表达需要修改。

**Score 0.25**: 大部分内容面向错误对象、语气与规范明显不符，或使用焦虑和效率羞辱推动行动。

**Score 0.0**: 与指定受众和语气相反，包含歧视、威胁、禁止主张，或没有面向用户的内容。

### Criterion 4: 日历可直接使用性 (key: calendar_usability, weight: 0.166667)

判据：10条日历内容是否在选题、文案、渠道、受众和来源上具体完整，可直接进入内容排期。

**Score 1.0**: 每条都有明确且有区别的主题和可发布文案，渠道与受众匹配，来源可追溯，并与活动方案一致，无需实质修改即可排期。

**Score 0.75**: 10条内容均完整可用，仅一条需要轻微调整措辞、渠道或行动建议。

**Score 0.5**: 日历基本完整，但多条文案仍是内部提纲、内容重复，或有一个核心组成需要补充，需多处修改后才能排期。

**Score 0.25**: 大部分行只有主题词或占位文案，渠道和受众选择随意，需要重写。

**Score 0.0**: 没有可用日历，或交付物无法作为内容排期使用。

## Workspace Path

```
workspace/extension/05_Creative_Synthesis/task_007_survey_campaign_pack
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

- 自动评分只检查文件、日期、ID和明确禁止主张；内容综合、主线、受众适配与可用性由声明式Judge评分。
- Auto组内权重为0.25、0.50、0.25；Judge组内权重为0.333333、0.25、0.25、0.166667。
- 输入附件的SHA-256记录在ground truth中，输入发生变化时自动评分为零。
