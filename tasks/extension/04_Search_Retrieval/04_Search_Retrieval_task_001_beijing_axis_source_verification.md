---
id: 04_Search_Retrieval_task_001_beijing_axis_source_verification
name: 北京中轴线官方来源核验
category: 04_搜索检索
timeout_seconds: 300
modality: pure-text
difficulty: L1
grading_type: automated
tags:
  - invalid
---

## Prompt

你正在为一份中国旅行资料核验单一事实。候选中文来源及其完整离线文章存档记录在`/tmp_workspace/source_candidates.json`。

请选择属于中国政府部门或中国官方文博机构的候选来源，并核实：

1. 北京中轴线列入《世界遗产名录》的日期；
2. 入选项目的完整中文名称。

百科、商业网站、自媒体和搜索结果摘要不能作为最终依据。只允许使用给定候选来源，并读取所选来源对应的离线存档。`evidence_quote`必须是该存档中的一段连续原文，并同时支持日期和项目名称。

请创建UTF-8 JSON文件`/tmp_workspace/results/verification.json`，字段必须与下面完全一致：

```json
{
  "inscription_date": "YYYY-MM-DD",
  "heritage_name_zh": "完整中文名称",
  "source_id": "候选来源ID",
  "source_url": "候选来源URL",
  "evidence_quote": "连续原文证据"
}
```

不要访问`/tmp_workspace/gt`，不要修改提供的来源文件。

## Expected Behavior

Agent读取候选列表和两份本地存档，识别中国政府网为权威来源，提取两个固定事实，引用官方存档原文，并生成一个合法JSON结果。

本题归为L1：只包含一次来源权威性判断和两个固定事实提取，不包含开放式网络搜索或多阶段综合。

## Grading Criteria

- [ ] 选择中国政府网官方来源（22%）
- [ ] 日期和完整中文名称正确（22%）
- [ ] JSON结构和规范来源URL正确（26%）
- [ ] 连续原文证据能够在官方存档中追溯（30%）

## Automated Checks

```python
def grade(**kwargs) -> dict:
    import hashlib
    import html
    import json
    import re
    from pathlib import Path

    root = Path(kwargs.get("workspace_path", "/tmp_workspace"))
    result_path = root / "results" / "verification.json"
    gt_path = root / "gt" / "expected.json"
    scores = {
        "authoritative_source_selected": 0.0,
        "heritage_facts_correct": 0.0,
        "output_schema_and_url_valid": 0.0,
        "evidence_traceable": 0.0,
    }

    def zero_scores():
        scores["overall_score"] = 0.0
        return scores

    try:
        expected = json.loads(gt_path.read_text(encoding="utf-8"))
    except Exception:
        return zero_scores()

    if not isinstance(expected, dict):
        return zero_scores()

    def exec_sources_intact():
        try:
            expected_hashes = expected.get("exec_file_sha256")
            if not isinstance(expected_hashes, dict) or not expected_hashes:
                return False

            root_real = root.resolve(strict=True)
            candidates_path = root / "source_candidates.json"
            snapshots_root = root / "snapshots"
            if (
                candidates_path.is_symlink()
                or not candidates_path.is_file()
                or snapshots_root.is_symlink()
                or not snapshots_root.is_dir()
            ):
                return False

            actual_files = {"source_candidates.json"}
            for path in snapshots_root.rglob("*"):
                if path.is_symlink():
                    return False
                if path.is_file():
                    actual_files.add(path.relative_to(root).as_posix())
            if actual_files != set(expected_hashes):
                return False

            for relative_path, expected_digest in expected_hashes.items():
                relative = Path(relative_path)
                if (
                    relative.is_absolute()
                    or ".." in relative.parts
                    or not re.fullmatch(r"[0-9a-f]{64}", str(expected_digest))
                ):
                    return False
                path = root / relative
                if path.is_symlink() or not path.is_file():
                    return False
                resolved = path.resolve(strict=True)
                if root_real not in resolved.parents:
                    return False
                digest = hashlib.sha256()
                with path.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
                if digest.hexdigest() != expected_digest:
                    return False
            return True
        except Exception:
            return False

    if not exec_sources_intact():
        return zero_scores()

    try:
        root_real = root.resolve(strict=True)
        results_dir = root / "results"
        if results_dir.is_symlink() or not results_dir.is_dir():
            return zero_scores()
        results_real = results_dir.resolve(strict=True)
        if results_real.parent != root_real:
            return zero_scores()
        if result_path.is_symlink() or not result_path.is_file():
            return zero_scores()
        if result_path.resolve(strict=True).parent != results_real:
            return zero_scores()
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except Exception:
        return zero_scores()

    if not isinstance(result, dict):
        return zero_scores()

    required = {
        "inscription_date",
        "heritage_name_zh",
        "source_id",
        "source_url",
        "evidence_quote",
    }
    schema_valid = set(result) == required and all(
        isinstance(result.get(key), str) for key in required
    )

    scores["authoritative_source_selected"] = float(
        result.get("source_id") == expected["official_source_id"]
        and result.get("source_url") == expected["official_source_url"]
    )

    def normalize_name(value):
        value = re.sub(r"\s+", "", str(value or ""))
        return value.replace("—", "-").replace("－－", "--")

    scores["heritage_facts_correct"] = float(
        result.get("inscription_date") == expected["inscription_date"]
        and normalize_name(result.get("heritage_name_zh"))
        == normalize_name(expected["heritage_name_zh"])
    )
    scores["output_schema_and_url_valid"] = float(
        schema_valid
        and result.get("source_url") == expected["official_source_url"]
        and result.get("source_url", "").startswith("https://www.gov.cn/")
    )

    def visible_text(raw):
        raw = re.sub(r"<script\b[^>]*>.*?</script>", " ", raw, flags=re.I | re.S)
        raw = re.sub(r"<style\b[^>]*>.*?</style>", " ", raw, flags=re.I | re.S)
        raw = re.sub(r"<[^>]+>", " ", raw)
        return re.sub(r"\s+", "", html.unescape(raw))

    try:
        archive = (root / expected["official_snapshot"]).read_text(encoding="utf-8")
        quote_value = result.get("evidence_quote", "")
        quote = re.sub(r"\s+", "", quote_value) if isinstance(quote_value, str) else ""
        archive_text = visible_text(archive)
        fragments_ok = all(
            re.sub(r"\s+", "", item) in quote
            for item in expected["required_evidence_fragments"]
        )
        scores["evidence_traceable"] = float(
            bool(quote) and quote in archive_text and fragments_ok
        )
    except Exception:
        scores["evidence_traceable"] = 0.0

    scores["overall_score"] = (
        0.22 * scores["authoritative_source_selected"]
        + 0.22 * scores["heritage_facts_correct"]
        + 0.26 * scores["output_schema_and_url_valid"]
        + 0.30 * scores["evidence_traceable"]
    )
    return scores
```

## Workspace Path

```
workspace/extension/04_Search_Retrieval/task_001_beijing_axis_source_verification
```

## Skills

```
```

## Env

```
```

## Warmup

```
```
