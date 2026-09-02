---
id: 01_Productivity_Flow_task_008_paper_reading_pack
name: Transformer论文组会材料
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

# Transformer论文组会材料

## Prompt

下周组会讨论*Attention Is All You Need*。请只使用固定版本`arXiv:1706.03762v7`：

<https://arxiv.org/abs/1706.03762v7>

在`/tmp_workspace/results/paper_card.json`中记录：`source,title,authors,first_submitted,version_revised,reported_results`。`source`包含`arxiv_id,version,versioned_id,url`，其中`version`规范写为字符串`v7`，`versioned_id`规范写为`arXiv:1706.03762v7`；`first_submitted`和`version_revised`使用`YYYY-MM-DD`。作者按页面顺序列全；`reported_results`使用字段`wmt2014_english_german_bleu,wmt2014_english_french_bleu,english_french_training_days,english_french_training_gpus`。

再写一份中文`/tmp_workspace/results/reading_pack.md`：先用一段话说明论文解决的问题和核心思路，再给出总计60分钟的组会议程和3个具体讨论问题。引用必须明确到v7。不要保存网页或PDF副本，不要使用其他来源或创建其他结果文件。

## Expected Behavior

Agent应从固定arXiv版本核对标题、八位作者、首次提交和v7修订日期，以及摘要中的两项翻译结果与训练信息。阅读材料应准确解释Transformer以注意力机制替代循环和卷积的核心改变，并提供合计60分钟的可执行议程及三个具体问题。

## Grading Criteria

### Automated group

- [ ] `fixed_version_correct`：固定arXiv ID、v7及URL正确
- [ ] `metadata_correct`：标题、全部作者和两个日期正确
- [ ] `reported_results_correct`：英德、英法结果及训练信息正确
- [ ] `structured_delivery_correct`：JSON结构、输出范围和无网页副本要求正确

### Judge group

- [ ] `reading_pack_quality`：中文概述、60分钟议程和三个讨论问题准确且可用

## Automated Checks

```python
def grade(transcript: list, workspace_path: str) -> dict:
    import json
    import re
    from pathlib import Path

    keys = [
        "fixed_version_correct",
        "metadata_correct",
        "reported_results_correct",
        "structured_delivery_correct",
        "overall_score",
    ]
    scores = {key: 0.0 for key in keys}
    root = Path(workspace_path)

    def mean(flags):
        return sum(1.0 if flag else 0.0 for flag in flags) / len(flags)

    def regular(path):
        return path.is_file() and not path.is_symlink() and not path.parent.is_symlink()

    def versioned_id(value):
        return re.sub(r"^arxiv\s*:\s*", "", str(value or "").strip(), flags=re.I)

    def version(value):
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            number = value
        elif isinstance(value, str):
            match = re.fullmatch(r"v?([1-9]\d*)", value.strip(), flags=re.I)
            if not match:
                return None
            number = int(match.group(1))
        else:
            return None
        return f"v{number}"

    def calendar_date(value):
        text = str(value or "").strip()
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:[T ][^\s]+)?", text):
            return None
        return text[:10]

    card_path = root / "results" / "paper_card.json"
    pack_path = root / "results" / "reading_pack.md"
    try:
        expected = json.loads((root / "gt" / "expected.json").read_text(encoding="utf-8"))
        if not regular(card_path) or not regular(pack_path):
            return scores
        card = json.loads(card_path.read_text(encoding="utf-8"))
        if not isinstance(card, dict):
            return scores
    except (OSError, UnicodeError, json.JSONDecodeError):
        return scores

    source = card.get("source") if isinstance(card.get("source"), dict) else {}
    scores["fixed_version_correct"] = mean([
        source.get("arxiv_id") == expected["source"]["arxiv_id"],
        version(source.get("version")) == version(expected["source"]["version"]),
        versioned_id(source.get("versioned_id"))
        == versioned_id(expected["source"]["versioned_id"]),
        source.get("url") == expected["source"]["url"],
    ])

    authors = card.get("authors")
    scores["metadata_correct"] = mean([
        card.get("title") == expected["title"],
        authors == expected["authors"],
        calendar_date(card.get("first_submitted")) == expected["first_submitted"],
        calendar_date(card.get("version_revised")) == expected["version_revised"],
    ])

    actual_results = card.get("reported_results") if isinstance(card.get("reported_results"), dict) else {}
    result_flags = []
    for key, wanted in expected["reported_results"].items():
        value = actual_results.get(key)
        result_flags.append(
            isinstance(value, (int, float)) and not isinstance(value, bool)
            and abs(float(value) - float(wanted)) <= 0.01
        )
    scores["reported_results_correct"] = mean(result_flags)

    exact_schema = set(card) == {"source", "title", "authors", "first_submitted", "version_revised", "reported_results"}
    exact_source = set(source) == set(expected["source"])
    exact_results = set(actual_results) == set(expected["reported_results"])
    canonical_formats = (
        source.get("versioned_id") == expected["source"]["versioned_id"]
        and card.get("first_submitted") == expected["first_submitted"]
        and card.get("version_revised") == expected["version_revised"]
    )
    results = root / "results"
    result_files = sorted(path.name for path in results.iterdir() if path.is_file() or path.is_symlink()) if results.is_dir() else []
    web_suffixes = {".html", ".htm", ".mhtml", ".pdf"}
    saved_web_copy = any(
        path.is_file() and "gt" not in path.relative_to(root).parts and path.suffix.lower() in web_suffixes
        for path in root.rglob("*")
    )
    scores["structured_delivery_correct"] = mean([
        exact_schema and exact_source and exact_results and canonical_formats,
        result_files == ["paper_card.json", "reading_pack.md"],
        regular(card_path) and regular(pack_path),
        not saved_web_copy,
    ])
    scores["overall_score"] = round(
        0.20 * scores["fixed_version_correct"]
        + 0.25 * scores["metadata_correct"]
        + 0.35 * scores["reported_results_correct"]
        + 0.20 * scores["structured_delivery_correct"],
        6,
    )
    return {key: round(value, 6) for key, value in scores.items()}
```

## LLM Judge Rubric

### Criterion 1: 阅读材料质量 (key: reading_pack_quality, weight: 1.0)

判据：`reading_pack.md`是否准确解释论文核心改变，提供合计60分钟的合理议程和三个与机制或实验直接相关的问题。

**Score 1.0**: 中文概述准确说明序列转换背景、仅基于注意力并去除循环和卷积的核心设计及其并行化意义；议程各段有时长且合计60分钟；三个问题具体涉及机制、实验或局限，引用明确到v7。

**Score 0.75**: 概述、总时长和三个问题均正确，仅一个议程环节或问题较弱，或缺少一个次要实验背景。

**Score 0.5**: 核心概述基本正确，但议程较泛化、总时长轻微不符，或只有一至两个有效讨论问题。

**Score 0.25**: 主要复述标题或摘要结果，议程不可执行，多数问题与论文机制无关，或有多处无依据扩展。

**Score 0.0**: 错误解释Transformer核心方法、使用了其他版本导致关键冲突、没有60分钟议程或未交付阅读材料。

## Workspace Path

```
workspace/extension/01_Productivity_Flow/task_008_paper_reading_pack
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

- 运行时只访问task_sources.yaml登记的`arXiv:1706.03762v7`页面；访问失败视为任务失败。
- `exec/`不保存网页或PDF副本。
