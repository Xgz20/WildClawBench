---
id: 05_Creative_Synthesis_task_006_podcast_storyboard
name: 访谈竖屏视频分镜
category: 05_Creative_Synthesis
timeout_seconds: 600
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L2
grading_type: hybrid
grading_weights:
  automated: 0.4
  llm_judge: 0.6
tags:
  - custom
---

# 访谈竖屏视频分镜

## Prompt

`/tmp_workspace/transcript.txt`是访谈逐字稿，`/tmp_workspace/audience_notes.md`是受众和语气要求。请帮我剪成80～100秒的竖屏视频分镜，选6～9个镜头。使用原话时必须逐字保留，并写对应时间码；不要把主持人的话改成嘉宾的话。

把结果保存为`/tmp_workspace/results/storyboard.csv`，使用UTF-8编码，列严格为`shot,start_sec,end_sec,source_timecode,spoken_quote,subtitle,visual_note`。`shot`从1连续编号，`start_sec`和`end_sec`是成片时间轴上的数字。画面建议要能用普通办公室、桌面近景、屏幕录制或简单文字动画完成，不要依赖另外拍摄大型场景。不要修改输入、联网或创建其他结果文件。

## Expected Behavior

Agent应从逐字稿选择6～9段可追溯原话，形成80～100秒、时间连续且有开头—方法—行动收束的分镜。每条原话和source_timecode应逐字对应输入，字幕适合手机竖屏，画面只使用允许的低成本素材，并遵守平静、不施压的受众要求。

## Grading Criteria

### Automated group

- [ ] `storyboard_schema`：输入完整，CSV编码、列、行数和唯一输出正确 — 25%
- [ ] `duration_and_shots`：成片80～100秒、6～9个连续镜头 — 25%
- [ ] `quote_traceability`：每条原话和时间码均能在逐字稿精确定位 — 50%

### Judge group

- [ ] `selection_arc`：选段形成清楚而忠实的叙事推进 — 33.3333%
- [ ] `visual_feasibility`：画面建议均可由允许素材完成 — 25%
- [ ] `subtitle_quality`：字幕适合手机竖屏阅读和指定语气 — 25%
- [ ] `editor_readiness`：分镜信息具体完整，可直接进入剪辑 — 16.6667%

## Automated Checks

```python
def grade(**kwargs) -> dict:
    import csv
    import hashlib
    import json
    from pathlib import Path

    root = Path(kwargs.get("workspace_path") or "/tmp_workspace")
    keys = ["storyboard_schema", "duration_and_shots", "quote_traceability"]
    scores = {key: 0.0 for key in keys}

    def regular(path):
        return path.is_file() and not path.is_symlink() and not path.parent.is_symlink()

    try:
        expected = json.loads((root / "gt" / "expected.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        return {**scores, "overall_score": 0.0}

    inputs_ok = True
    for relative, wanted_hash in expected["exec_file_sha256"].items():
        path = root / relative
        try:
            inputs_ok = inputs_ok and regular(path) and hashlib.sha256(path.read_bytes()).hexdigest() == wanted_hash
        except OSError:
            inputs_ok = False
    if not inputs_ok:
        return {**scores, "overall_score": 0.0}

    result_path = root / "results" / "storyboard.csv"
    try:
        if not regular(result_path):
            raise ValueError("regular storyboard required")
        with result_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            columns = reader.fieldnames or []
            rows = list(reader)
    except (OSError, UnicodeError, ValueError, csv.Error):
        return {**scores, "overall_score": 0.0}

    exact_columns = columns == expected["columns"] and all(
        set(row) == set(expected["columns"]) and None not in row for row in rows
    )
    nonempty = all(
        all(isinstance(row.get(column), str) and row[column].strip() for column in expected["columns"])
        for row in rows
    )
    try:
        result_files = sorted(path.name for path in (root / "results").iterdir() if path.is_file() or path.is_symlink())
    except OSError:
        result_files = []
    row_count_ok = expected["min_shots"] <= len(rows) <= expected["max_shots"]
    scores["storyboard_schema"] = round(sum([
        1.0 if exact_columns else 0.0,
        1.0 if nonempty and row_count_ok else 0.0,
        1.0 if result_files == expected["result_files"] else 0.0,
        1.0 if inputs_ok and regular(result_path) else 0.0,
    ]) / 4, 6)
    if not (exact_columns and nonempty):
        scores["overall_score"] = round(0.25 * scores["storyboard_schema"], 6)
        return scores

    try:
        shots = [int(row["shot"]) for row in rows]
        starts = [float(row["start_sec"]) for row in rows]
        ends = [float(row["end_sec"]) for row in rows]
    except (KeyError, TypeError, ValueError):
        shots, starts, ends = [], [], []
    numbering_ok = shots == list(range(1, len(rows) + 1))
    positive_ok = bool(rows) and all(0 <= start < end for start, end in zip(starts, ends))
    continuous_ok = (
        bool(rows) and len(starts) == len(rows) and starts[0] == 0
        and all(abs(starts[index] - ends[index - 1]) <= 0.01 for index in range(1, len(rows)))
    )
    total_duration = ends[-1] if ends else 0.0
    duration_ok = expected["min_duration_sec"] <= total_duration <= expected["max_duration_sec"]
    scores["duration_and_shots"] = round(sum([
        1.0 if row_count_ok else 0.0,
        1.0 if numbering_ok else 0.0,
        1.0 if positive_ok and continuous_ok else 0.0,
        1.0 if duration_ok else 0.0,
    ]) / 4, 6)

    quotes = expected["quotes"]
    trace_flags = []
    for row in rows:
        timecode = row["source_timecode"].strip()
        wanted = quotes.get(timecode)
        trace_flags.append(
            isinstance(wanted, dict)
            and row["spoken_quote"].strip() == wanted.get("text")
        )
    unique_timecodes = len({row["source_timecode"].strip() for row in rows}) == len(rows)
    source_file_text = (root / "transcript.txt").read_text(encoding="utf-8")
    source_presence = all(
        f'[{row["source_timecode"].strip()}]' in source_file_text
        and row["spoken_quote"].strip() in source_file_text
        for row in rows
    )
    scores["quote_traceability"] = round(sum([
        sum(1.0 if flag else 0.0 for flag in trace_flags) / len(trace_flags) if trace_flags else 0.0,
        1.0 if unique_timecodes and row_count_ok else 0.0,
        1.0 if source_presence else 0.0,
    ]) / 3, 6)

    scores["overall_score"] = round(
        0.25 * scores["storyboard_schema"]
        + 0.25 * scores["duration_and_shots"]
        + 0.50 * scores["quote_traceability"],
        6,
    )
    return scores
```

## LLM Judge Rubric

Judge只评价`storyboard.csv`中通过输入追溯的内容，不增加整体印象分。不同合理选段和画面方案均可接受。每项只能使用`1.0 / 0.75 / 0.5 / 0.25 / 0.0`。

### Criterion 1: 选段叙事推进 (key: selection_arc, weight: 0.333333)

判据：镜头是否从问题或观点引入，经过具体方法，最后给出可执行但不施压的收束，并保持逐字稿原意。

**Score 1.0**: 选段构成清楚的引入—方法—行动推进，主持人与嘉宾关系准确，无断裂、矛盾或无关重复。

**Score 0.75**: 主线完整，仅一个镜头位置略弱、轻微重复或转折不够顺滑。

**Score 0.5**: 有可理解主题，但缺少一个阶段或存在一处重大跳转，仍可经重排形成短片。

**Score 0.25**: 主要是无序摘句，多处断裂或角色关系不清，需要大幅重组。

**Score 0.0**: 选段改变核心原意、角色颠倒，或没有可评价分镜。

### Criterion 2: 画面可行性 (key: visual_feasibility, weight: 0.25)

判据：visual_note是否具体，并且只依赖普通办公室、桌面近景、屏幕录制或简单文字动画。

**Score 1.0**: 每个镜头都有具体可执行的允许画面，镜头间有合理变化，不依赖额外大型制作。

**Score 0.75**: 全部画面可行，仅一个说明略泛或重复。

**Score 0.5**: 多数可行，但有一项需要禁止的大型场景，或多项说明只写“配画面”等占位语。

**Score 0.25**: 大部分依赖演员情景剧、外景或复杂制作，必须重做画面方案。

**Score 0.0**: 没有画面建议，或整体不可能按允许素材制作。

### Criterion 3: 竖屏字幕质量 (key: subtitle_quality, weight: 0.25)

判据：subtitle是否简洁、准确、适合手机竖屏，并遵守平静、不制造自律压力的语气。

**Score 1.0**: 全部字幕准确提炼对应原话、长度便于两行内阅读，语气具体克制且无施压。

**Score 0.75**: 整体适配，仅一条略长、略泛或语气稍强。

**Score 0.5**: 含义基本准确，但多条过长、像标题堆叠或出现模板化效率表达。

**Score 0.25**: 大部分难以在手机阅读、改变原意或制造明显焦虑。

**Score 0.0**: 字幕缺失、与原话冲突或包含攻击性内容。

### Criterion 4: 剪辑可用性 (key: editor_readiness, weight: 0.166667)

判据：每行时间、原话、字幕和画面信息是否相互对应，能直接支持剪辑执行。

**Score 1.0**: 所有行信息明确一致，镜头节奏合理，无需实质补充即可进入剪辑。

**Score 0.75**: 基本可直接使用，仅一行需要轻微调整字幕或画面说明。

**Score 0.5**: 结构完整但多行信息泛化、节奏失衡或对应关系不清，需要多处编辑。

**Score 0.25**: 大部分内容只是提纲或占位，无法直接剪辑。

**Score 0.0**: 没有可用分镜或交付物与请求无关。

## Workspace Path

```
workspace/extension/05_Creative_Synthesis/task_006_podcast_storyboard
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

- Auto组内权重为25%、25%、50%，整体占40%。
- Judge组内权重为33.3333%、25%、25%、16.6667%，整体占60%。
