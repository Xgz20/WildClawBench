---
id: 01_Productivity_Flow_task_9_scp_crawl
name: 抓取 SCP-001 至 050 全量内容
category: 01_生产力工作流
timeout_seconds: 1200
modality: pure-text
difficulty: L3
grading_type: automated
---
## Prompt

请访问 `https://scp-wiki.wikidot.com/`，抓取编号 `001` 到 `050` 的 SCP 条目页面，并将结果保存到本地。

输出要求如下：

1. 创建目录 `/tmp_workspace/results/`。
2. 对于每个条目 `SCP-001` 到 `SCP-050`，创建对应子目录：
   - `/tmp_workspace/results/scp-001/`
   - `/tmp_workspace/results/scp-002/`
   - ...
   - `/tmp_workspace/results/scp-050/`
3. 对每个条目，将该页面的正文文本部分保存到：
   - `/tmp_workspace/results/scp-XXX/text.md`
4. 对每个条目，将该页面正文中的图片内容另存为：
   - `/tmp_workspace/results/scp-XXX/1.jpg`
   - `/tmp_workspace/results/scp-XXX/2.jpg`
   - ...
5. 如果某个页面正文中没有图片，也仍然要创建对应目录和 `text.md`，只是不要创建图片文件。
6. 同时，将所有条目的统计结果保存为一个 JSONL 文件：
   - `/tmp_workspace/results/summary.jsonl`
7. `/tmp_workspace/results/summary.jsonl` 中每行对应一个条目，格式如下：

```python
{
    "item": "SCP-010",
    "class": "Safe",
    "n_mask": 1
}
# This is just a Python dict for illustration; actual file must be JSONL
```

补充规则：

1. `class` 字段规则如下：
   - 页面有标准 `Object Class` 时，使用它。
   - 如果没有 `Object Class` 但有 `Containment Class`，使用 `Containment Class`。
   - 如果两者都没有，写 `"Unknown"`。
2. `n_mask` 表示正文中的逻辑隐藏块数量。每个可折叠/可展开块只计数一次。
3. 统计 `n_mask` 时，如果正文中的 Licensing / Citation 区块本身也是折叠块，也要计入。
4. 图片只统计正文中的条目图片，不要把站点导航图标、头像、社交媒体图标等页面装饰性图片算进去。
5. `text.md` 需要保留页面主要正文内容；格式可以是 markdown 或纯文本，但不能只写摘要，也不能只保存很小一段内容。



## Expected Behavior

Agent 应当：

1. 访问 SCP Wiki 上 `scp-001` 到 `scp-050` 的页面。
2. 为每个页面创建 `/tmp_workspace/results/scp-XXX/`。
3. 提取正文文本并保存为 `text.md`。
4. 识别属于 SCP 页面正文本身的条目图片，排除头像、导航图标、社交图标等页面装饰元素。
5. 将这些条目图片按顺序保存为条目目录下命名为 `1.jpg`、`2.jpg`……的 JPEG 文件。
6. 生成 `/tmp_workspace/results/summary.jsonl`，每个条目对应一个 JSON object，包含：
   - 规范化的条目 id
   - 遵循 `Object Class -> Containment Class -> Unknown` 回退规则得到的 class 值
   - 正文中可折叠块的逻辑计数

可接受的解法可以使用浏览器工具、直接 HTTP 抓取、HTML 解析，或它们的组合。最终得分取决于本地保存的产物结构是否完整，以及 summary、文本提取和图片提取是否与基于同一批线上页面构建的固定隐藏参考答案一致。

## Grading Criteria

- [ ] `/tmp_workspace/results` 存在
- [ ] 全部 50 个条目目录 `scp-001` 到 `scp-050` 均已创建
- [ ] `/tmp_workspace/results/summary.jsonl` 存在
- [ ] `summary.jsonl` 是有效的 JSONL，每个条目对应一行
- [ ] `summary.jsonl` 中的条目覆盖范围正确
- [ ] 提取的 `class` 值正确
- [ ] 提取的 `n_mask` 值正确
- [ ] 每个条目目录都包含一个非空的 `text.md`
- [ ] 保存的文本内容与对应的 SCP 页面内容一致
- [ ] 保存的图片数量与文件名正确
- [ ] 保存的图片文件是有效的 JPEG 文件

## Automated Checks

```python
def grade(**kwargs) -> dict:
    """
    Grade the SCP crawling task.

    Returns:
        Dict mapping criterion names to scores (0.0 to 1.0)
    """
    import json
    import re
    from pathlib import Path

    gt_file = Path("/tmp_workspace") / "gt" / "ground_truth.json"
    output_root = Path("/tmp_workspace/results")
    summary_file = output_root / "summary.jsonl"

    ALL_CRITERIA = {
        "output_root_exists": 0.0,
        "item_directories_created": 0.0,
        "summary_exists": 0.0,
        "summary_valid_jsonl": 0.0,
        "summary_item_coverage": 0.0,
        "summary_class_accuracy": 0.0,
        "summary_n_mask_accuracy": 0.0,
        "text_files_present": 0.0,
        "text_anchor_recall": 0.0,
        "image_count_accuracy": 0.0,
        "jpeg_file_validity": 0.0,
        "overall_score": 0.0,
    }

    if not gt_file.exists():
        return ALL_CRITERIA | {"error": f"missing gt file: {gt_file}"}

    gt = json.loads(gt_file.read_text(encoding="utf-8"))
    by_item = gt.get("by_item", {})
    expected_items = sorted(by_item.keys())
    expected_item_set = set(expected_items)

    def normalize_space(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()

    def normalize_item(text: str) -> str:
        text = normalize_space(str(text)).upper()
        m = re.search(r"SCP[-\s]*0*([1-9]\d*|0)", text)
        if not m:
            return ""
        return f"SCP-{int(m.group(1)):03d}"

    def normalize_class(text: str) -> str:
        text = normalize_space(str(text)).lower()
        text = text.replace("object class:", "").replace("containment class:", "")
        return re.sub(r"[^a-z0-9]+", "", text)

    def looks_like_jpeg(path: Path) -> bool:
        try:
            data = path.read_bytes()
        except Exception:
            return False
        return len(data) >= 4 and data[:2] == b"\xff\xd8" and data[-2:] == b"\xff\xd9"

    scores = dict(ALL_CRITERIA)

    if not output_root.exists() or not output_root.is_dir():
        return scores | {"error": f"output dir not found: {output_root}"}

    scores["output_root_exists"] = 1.0

    existing_dirs = {
        p.name for p in output_root.iterdir()
        if p.is_dir() and re.fullmatch(r"scp-\d{3}", p.name)
    }
    dir_hits = len(existing_dirs & {item.lower() for item in expected_items})
    scores["item_directories_created"] = round(dir_hits / len(expected_items), 4)

    if summary_file.exists() and summary_file.is_file():
        scores["summary_exists"] = 1.0
    else:
        scores["overall_score"] = round(
            0.10 * scores["item_directories_created"],
            4,
        )
        return scores | {"error": f"missing summary file: {summary_file}"}

    lines = [line for line in summary_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    parsed = []
    for idx, line in enumerate(lines, start=1):
        try:
            parsed.append(json.loads(line))
        except Exception as exc:
            return scores | {"error": f"invalid json on line {idx}: {exc}"}

    scores["summary_valid_jsonl"] = 1.0

    predicted = {}
    duplicate_items = set()
    malformed_rows = 0

    for row in parsed:
        if not isinstance(row, dict):
            malformed_rows += 1
            continue
        item = normalize_item(row.get("item", ""))
        if not item:
            malformed_rows += 1
            continue

        raw_class = row.get("class")
        raw_mask = row.get("n_mask")
        try:
            n_mask = int(raw_mask)
        except Exception:
            malformed_rows += 1
            continue

        entry = {
            "class": normalize_class(raw_class),
            "n_mask": n_mask,
        }
        if item in predicted:
            duplicate_items.add(item)
        predicted[item] = entry

    pred_item_set = set(predicted.keys())
    tp_items = len(pred_item_set & expected_item_set)
    item_recall = tp_items / len(expected_item_set) if expected_item_set else 0.0
    item_precision = tp_items / len(pred_item_set) if pred_item_set else 0.0
    item_f1 = (
        2 * item_recall * item_precision / (item_recall + item_precision)
        if (item_recall + item_precision) else 0.0
    )
    if duplicate_items or malformed_rows:
        item_f1 *= 0.0
    scores["summary_item_coverage"] = round(item_f1, 4)

    class_correct = 0
    mask_correct = 0
    for item in expected_items:
        pred = predicted.get(item)
        target = by_item[item]
        if pred and pred["class"] == normalize_class(target["class"]):
            class_correct += 1
        if pred and pred["n_mask"] == int(target["n_mask"]):
            mask_correct += 1

    total_items = len(expected_items) or 1
    scores["summary_class_accuracy"] = round(class_correct / total_items, 4)
    scores["summary_n_mask_accuracy"] = round(mask_correct / total_items, 4)

    text_present = 0
    anchor_total = 0
    anchor_hits = 0
    image_count_ok = 0
    expected_jpeg_files = 0
    valid_jpeg_files = 0

    for item in expected_items:
        item_dir = output_root / item.lower()
        target = by_item[item]

        text_file = item_dir / "text.md"
        if text_file.exists() and text_file.is_file():
            content = text_file.read_text(encoding="utf-8", errors="ignore").strip()
            if content:
                text_present += 1
                normalized_content = normalize_space(content).lower()
                anchors = target.get("text_anchors", [])
                for anchor in anchors:
                    anchor_total += 1
                    if normalize_space(anchor).lower() in normalized_content:
                        anchor_hits += 1
            else:
                anchor_total += len(target.get("text_anchors", []))
        else:
            anchor_total += len(target.get("text_anchors", []))

        expected_image_count = int(target.get("image_count", 0))
        expected_names = {f"{idx}.jpg" for idx in range(1, expected_image_count + 1)}
        actual_names = set()
        if item_dir.exists() and item_dir.is_dir():
            for path in item_dir.iterdir():
                if path.is_file() and path.name != "text.md":
                    actual_names.add(path.name)

        if actual_names == expected_names:
            image_count_ok += 1

        for idx in range(1, expected_image_count + 1):
            expected_jpeg_files += 1
            img_path = item_dir / f"{idx}.jpg"
            if img_path.exists() and img_path.is_file() and looks_like_jpeg(img_path):
                valid_jpeg_files += 1

    scores["text_files_present"] = round(text_present / total_items, 4)
    scores["text_anchor_recall"] = round(anchor_hits / anchor_total, 4) if anchor_total else 1.0
    scores["image_count_accuracy"] = round(image_count_ok / total_items, 4)
    scores["jpeg_file_validity"] = (
        round(valid_jpeg_files / expected_jpeg_files, 4) if expected_jpeg_files else 1.0
    )

    scores["overall_score"] = round(
        0.10 * scores["item_directories_created"]
        + 0.02 * scores["summary_exists"]
        + 0.05 * scores["summary_valid_jsonl"]
        + 0.10 * scores["summary_item_coverage"]
        + 0.15 * scores["summary_class_accuracy"]
        + 0.20 * scores["summary_n_mask_accuracy"]
        + 0.05 * scores["text_files_present"]
        + 0.10 * scores["text_anchor_recall"]
        + 0.10 * scores["image_count_accuracy"]
        + 0.13 * scores["jpeg_file_validity"],
        4,
    )

    notes = []
    if duplicate_items:
        notes.append(f"duplicate_items={sorted(duplicate_items)[:10]}")
    if malformed_rows:
        notes.append(f"malformed_rows={malformed_rows}")
    if notes:
        scores["warning"] = "; ".join(notes)

    return scores
```

## Workspace Path

```
workspace/01_Productivity_Flow/task_9_scp_crawl
```

## Skills

```
agent-browser
```

## Env

```
```

## Warmup

```
command -v agent-browser >/dev/null 2>&1 || npm install -g agent-browser
```
