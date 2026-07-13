---
id: 01_Productivity_Flow_task_5_wikipedia_biography
name: 抽取维基百科生平章节
category: 01_生产力工作流
timeout_seconds: 900
modality: pure-text
difficulty: L2
grading_type: automated
---
## Prompt
阅读 **Emperor Huan of Han**（汉桓帝）的 **"Biography"** 小节，网址：

- https://zh.wikipedia.org/wiki/%E6%B1%89%E6%A1%93%E5%B8%9D

识别该小节中提到的所有人物，排除汉桓帝本人。

对于每一位在 Wikipedia 上同样拥有 "Biography" 小节的人物，将该小节的内容保存为名为 `{person_name}.md` 的 Markdown 文件。

始终使用每位人物的**本名**（而非其头衔或别名）。

将所有 Markdown 文件保存到 `/tmp_workspace/results/`。

不要生成任何其他文件或目录。

### Output Requirements

你必须在 `/tmp_workspace/results/` 下创建以下输出：

- 一个或多个 Markdown 文件：`{person_name}.md`（均位于 results 目录下）

每个文件必须：

- 使用人物本名命名
- 包含该人物在 Wikipedia 上 "Biography" 小节的完整内容
- 采用 UTF-8 编码
- 使用 Wikipedia 上呈现的 Markdown 格式（包括小节标题、段落等）
- 只包含文本 —— 不要包含 URL 或超链接
- 始终使用简体中文字符
- 除 Biography 小节内容外，不包含说明、注释或多余散文

不要在 results 目录中创建任何其他文件或目录。

### Notes

- 只收录在其 Wikipedia 页面上拥有专门 "Biography"（生平 / 传记）小节的人物
- 排除汉桓帝（Emperor Huan of Han）本人
- 使用人物在标准史料中出现的名字（例如 刘保，而非 汉顺帝）
- 对于引用文本，使用弯双引号 `"` `"`（U+201C/U+201D），而非直角引号 `「` `」`（U+300C/U+300D）


## Expected Behavior

agent 应当：

1. 导航到汉桓帝的 Wikipedia 页面
2. 阅读并解析 "Biography" 小节，提取所有被提及的人物
3. 对每一位被提及的人物，检查其自身的 Wikipedia 页面上是否有 "Biography" 小节
4. 对于有该小节的人物，提取完整的 Biography 小节内容
5. 使用人物本名将每份提取出的 Biography 保存为 `results/{person_name}.md`

agent 可以使用网页浏览、Wikipedia API 或其他工具。最终得分仅取决于生成的 Markdown 文件。

## Grading Criteria

- [ ] `results/` 目录存在
- [ ] 所有预期人物的 Markdown 文件都已在 `results/` 下创建
- [ ] `results/` 下未创建意外或多余的文件
- [ ] 每个文件都以正确的人物姓名命名（例如 `刘协.md`、`梁冀.md`）
- [ ] 归一化后，每个文件的内容与 ground-truth 的 Biography 小节一致
- [ ] 模型输出中不要求包含引用标记（如 `[1]`、`[2]`）；比对时会忽略它们
- [ ] 比对时直引号与弯引号视为等价（`"` `"` `「` `」` → 相同）
- [ ] 比对时忽略开头的 "生平" / "传记" 小节标题
- [ ] 比对前将 Markdown ATX 标题（`##` 标题）转换为纯文本；两种格式均计为正确
- [ ] Agent 输出应只包含文本（不含 URL）；输出中的 URL 会导致内容不匹配

## Automated Checks

```python
def grade(**kwargs) -> dict:
    """
    Grade the Wikipedia Biography extraction task.
    """
    from pathlib import Path
    import re
    import unicodedata

    workspace = Path("/tmp_workspace")

    ALL_CRITERIA = [
        "results_dir_exists",
        "coverage_ratio",
        "content_match_ratio",
        "no_extra_files",
        "hard_constraint_pass",
        "overall_score",
    ]

    ZERO = {k: 0.0 for k in ALL_CRITERIA}
    results_dir = workspace / "results"
    gt_dir = workspace / "gt"

    if not gt_dir.exists() or not gt_dir.is_dir():
        return ZERO

    gt_files = sorted(
        p for p in gt_dir.iterdir()
        if p.is_file() and p.suffix.lower() == ".md"
    )
    if len(gt_files) == 0:
        return ZERO

    expected_names = {p.stem for p in gt_files}
    if not expected_names:
        return ZERO

    def normalize_md_content(text: str) -> str:
        """Normalize markdown content for comparison."""
        text = unicodedata.normalize("NFKC", str(text))
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        # Remove reference markers: [1], [2], etc.
        text = re.sub(r"\[\d+\]", "", text)
        # Treat straight and curved quotes as equivalent: " " 「」 -> "
        text = text.replace("\u201c", '"').replace("\u201d", '"')  # " "
        text = text.replace("\u300c", '"').replace("\u300d", '"')  # 「」
        # Do NOT strip URLs — their presence/absence is part of the evaluation
        # Ignore leading "生平" / "传记" section headers (e.g. "## 生平" or "生平" at start)
        text = re.sub(r"^\s*(#{1,6}\s*)?(生平|传记)\s*\n*", "", text, flags=re.IGNORECASE)
        # Convert markdown ATX headers to normal text: ## 标题 -> 标题 (keep title as plain text for comparison)
        text = re.sub(r"^\s*#{1,6}\s*([^\n]*)", r"\1", text, flags=re.MULTILINE)
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r" *\n *", "\n", text)
        return text.strip()

    def read_and_normalize(path: Path) -> str | None:
        try:
            return normalize_md_content(path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            return None

    scores = dict(ZERO)
    scores["results_dir_exists"] = 1.0 if results_dir.exists() and results_dir.is_dir() else 0.0

    if not results_dir.exists() or not results_dir.is_dir():
        return scores

    pred_md_files = [p for p in results_dir.iterdir() if p.is_file() and p.suffix.lower() == ".md"]
    pred_names = {p.stem for p in pred_md_files}

    coverage = 0
    content_match = 0

    for gt_path in gt_files:
        name = gt_path.stem
        gt_content = read_and_normalize(gt_path)
        if gt_content is None:
            continue

        pred_path = results_dir / f"{name}.md"
        if pred_path.exists() and pred_path.is_file():
            coverage += 1
            pred_content = read_and_normalize(pred_path)
            if pred_content is not None and pred_content == gt_content:
                content_match += 1

    total = len(gt_files)
    scores["coverage_ratio"] = round(coverage / total, 4) if total > 0 else 0.0
    scores["content_match_ratio"] = round(content_match / total, 4) if total > 0 else 0.0

    extra_names = pred_names - expected_names
    extra_count = len(extra_names)
    scores["no_extra_files"] = round(max(0.0, 1.0 - 0.1 * extra_count), 4)

    hard_checks = ["results_dir_exists"]
    hard_pass = all(scores[k] == 1.0 for k in hard_checks)
    scores["hard_constraint_pass"] = 1.0 if hard_pass else 0.0

    if not hard_pass:
        scores["overall_score"] = 0.0
        return scores

    base_score = round(
        0.3 * scores["coverage_ratio"] + 0.7 * scores["content_match_ratio"],
        4,
    )
    scores["overall_score"] = round(base_score * scores["no_extra_files"], 4)
    return scores
```

## Workspace Path

```
workspace/01_Productivity_Flow/task_5_wikipedia_biography
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
npm install -g agent-browser
```
