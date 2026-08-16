---
name: audit-eval-dataset-quality
description: 使用一个或多个外部 WildClawBench 评测结果目录，审计任务难度、梯度、模型区分度、Harness 敏感性和多 run 稳定性；当用户要求反推评测集是否合理或比较多模型/多 Harness 结果时使用。
---

# Audit Eval Dataset Quality

结果目录可以在仓库外、任意解压目录，并可重复指定。任务选择参数与静态 Skill 相同；未指定时扫描 `<repo>/tasks`。

```bash
python3 .agents/skills/audit-eval-dataset-quality/scripts/audit_eval_dataset_quality.py \
  --result-root /path/to/unpacked/round1/astroncode
python3 .agents/skills/audit-eval-dataset-quality/scripts/audit_eval_dataset_quality.py \
  --task-dir tasks/extension --result-root /path/to/result-a --result-root /path/to/result-b
```

脚本递归发现 `score.json`，读取相邻的 `execution_status.json`、`usage.json`、`anomalies.json`，复用框架的有效 run 选择规则，保留 0 分有效结果，不读取或复制 transcript。报告给出任务覆盖、均值/满分率/零分率、难度分组、模型分差、Harness 分差和多 run 标准差。

统计异常、单模型/单 Harness、单 run 证据均为 `REVIEW`，不默认阻断；缺任务、缺 score、执行无效和无法解析的输入为 `FAIL`。只有至少两个 Harness 且控制同一模型/任务交集时才会评估 Harness 敏感性；一个 Harness 必须明确写出“无法评估 Harness 敏感性”。可用 `--validity` 合并已有结果有效性 JSON，不能用本 Skill 替代 `validate-eval-results`。

默认输出 `<repo>/report-workspace/eval-dataset/quality/<timestamp>_<scope-hash>/report.{json,md}`。报告只保留路径、计数和截断证据，不写 API key、Bearer token 或 transcript 全文。具体指标边界见 [references/quality-methods.md](references/quality-methods.md)。
