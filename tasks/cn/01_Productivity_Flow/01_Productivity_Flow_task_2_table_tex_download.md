---
id: 01_Productivity_Flow_task_2_table_tex_download
name: 从 arXiv 源码还原表格 TeX
category: 01_生产力工作流
timeout_seconds: 900
modality: pure-text
difficulty: L2
grading_type: automated
---
## Prompt

我想从一篇 arXiv 论文中恢复出原始的 LaTeX 表格源码。

请处理这篇论文：

- Paper URL: `https://arxiv.org/abs/2501.07888`

你的任务是找到对应的原始 arXiv 源码包，将其下载，并从**论文源码中提取所有 table 环境**。提取完成后应删除源码包。

将结果保存到 `/tmp_workspace/results`。

- 将每个恢复出的表格保存为单独的文件，命名为 `1.tex`、`2.tex`、`3.tex`、……
- 文件编号按照表格在论文中出现的顺序排列
- 每个文件必须恰好包含一个从源码包中复制的原始 LaTeX `table` 环境
- 尽可能保留原始的表格内容和格式
- 不要将多个表格合并到一个文件中
- 不要用额外的说明、markdown 或散文包裹表格
- 不要在序号中跳号
- 只生成所需的输出文件

## Expected Behavior

agent 应当：

1. 将论文 URL 解析到对应的 arXiv 源码包
2. 下载原始源码压缩包
3. 识别属于该论文的每一个 table 环境
4. 按正确顺序将每个表格保存为单独的带编号的 `.tex` 文件
5. 只保存评分所需的带编号 `.tex` 文件

agent 可以使用网页访问、压缩包下载、shell 命令或脚本，但最终得分取决于下载的表格源码是否与原始源码表格一致。

## Grading Criteria

- [ ] 带编号的 `.tex` 文件已按要求的命名约定创建
- [ ] 归一化后，`n.tex` 与第 n 个 ground-truth 表格完全一致
- [ ] 严格有序匹配率较高
- [ ] 无序精确匹配的召回率较高
- [ ] 无序精确匹配的精确率较高
- [ ] 无序精确匹配的 F1 较高

## Automated Checks

```python
def grade(**kwargs) -> dict:
    """
    Grade the table-tex extraction task.

    Args:

    Returns:
        Dict mapping criterion names to scores (0.0 to 1.0)
    """
    from pathlib import Path
    import re

    workspace = Path("/tmp_workspace/results")
    gt_dir = Path("/tmp_workspace") / "gt"

    def normalize_tex(text: str) -> str:
        text = text.strip()
        text = re.sub(r"%[^\n]*", "", text)
        text = re.sub(r"\s+", " ", text)
        text = text.strip()
        return text

    if not gt_dir.exists() or not gt_dir.is_dir():
        return {"error": f"gt_dir does not exist or is not a directory: {gt_dir}"}

    gt_files = sorted(gt_dir.glob("*.tex"), key=lambda p: int(p.stem))
    gt_contents = [normalize_tex(f.read_text(encoding="utf-8")) for f in gt_files]
    num_gt = len(gt_contents)

    if num_gt == 0:
        return {"error": f"no .tex files found under gt_dir: {gt_dir}"}

    ALL_CRITERIA = (
        ["files_created"]
        + [f"ordered_match_{i}" for i in range(1, num_gt + 1)]
        + ["strict_ordered_ratio", "unordered_recall", "unordered_precision", "unordered_f1", "overall_score"]
    )

    if not workspace.exists() or not workspace.is_dir():
        return {k: 0.0 for k in ALL_CRITERIA} | {"error": f"workspace not found: {workspace}"}

    pred_files = sorted(
        [p for p in workspace.glob("*.tex") if p.stem.isdigit()],
        key=lambda p: int(p.stem),
    )
    pred_contents = [normalize_tex(f.read_text(encoding="utf-8")) for f in pred_files]
    num_pred = len(pred_contents)
    scores = {}

    scores["files_created"] = 1.0 if num_pred > 0 else 0.0

    for i in range(1, num_gt + 1):
        key = f"ordered_match_{i}"
        if i - 1 < num_pred and i - 1 < num_gt:
            scores[key] = 1.0 if pred_contents[i - 1] == gt_contents[i - 1] else 0.0
        else:
            scores[key] = 0.0

    ordered_correct = 0
    for i in range(min(num_pred, num_gt)):
        if pred_contents[i] == gt_contents[i]:
            ordered_correct += 1
    scores["strict_ordered_ratio"] = round(ordered_correct / num_gt, 4)

    gt_matched = set()
    pred_matched = set()
    for pi, pc in enumerate(pred_contents):
        for gi, gc in enumerate(gt_contents):
            if gi not in gt_matched and pc == gc:
                gt_matched.add(gi)
                pred_matched.add(pi)
                break

    recall = len(gt_matched) / num_gt if num_gt > 0 else 0.0
    precision = len(pred_matched) / num_pred if num_pred > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    scores["unordered_recall"] = round(recall, 4)
    scores["unordered_precision"] = round(precision, 4)
    scores["unordered_f1"] = round(f1, 4)

    scores["overall_score"] = round(
        0.7 * scores["strict_ordered_ratio"] + 0.3 * scores["unordered_f1"], 4
    )

    return scores
```
## Workspace Path

```
workspace/01_Productivity_Flow/task_2_table_tex_download
```

## Skills

```
self-improving-agent-3.0.5
agent-browser
```

## Env

```
```

## Warmup
```
npm install -g agent-browser
```
