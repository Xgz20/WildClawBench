---
name: audit-eval-dataset-quality
description: 使用一个或多个外部 WildClawBench 评测结果目录，审计任务难度、梯度、模型区分度、Harness 敏感性和多 run 稳定性；当用户要求反推评测集是否合理或比较多模型/多 Harness 结果时使用。
---

# Audit Eval Dataset Quality

结果目录可以在仓库外、任意解压目录，并可重复指定。任务选择参数与静态 Skill 相同；未指定时扫描 `<repo>/tasks`，排除仅供阅读的 `tasks/cn` 副本。需要把中文副本纳入元数据检查时显式加 `--include-doc-copies`；它们没有独立评测结果时不应作为审计覆盖范围。

```bash
python3 .agents/skills/audit-eval-dataset-quality/scripts/audit_eval_dataset_quality.py \
  --result-root /path/to/unpacked/round1/astroncode
python3 .agents/skills/audit-eval-dataset-quality/scripts/audit_eval_dataset_quality.py \
  --task-dir tasks/extension --result-root /path/to/result-a --result-root /path/to/result-b
```

脚本递归发现 `score.json`，读取相邻的 `execution_status.json`、`usage.json`、`anomalies.json`，复用框架的有效 run 选择规则，保留 0 分有效结果。报告除了统计指标，还把处置拆成“结果需要重跑或补齐”“框架/审计输入需要修复”“评测用例需要修改”“评测用例需要人工复核”四类，并列出当前未发现问题的用例；默认只对 `agent.log`/`chat*.jsonl` 做有大小上限的完成、错误和评分契约信号扫描，不复制 transcript 全文。多个 model@harness 有效完成但共同接近 0 分时，会生成“疑似检查点/评分契约过严”的人工审核候选，不会直接进入用例修改清单。

统计异常、单模型/单 Harness、单 run 证据均为 `REVIEW`，不默认阻断；缺任务、缺 score、执行无效和无法解析的输入为 `FAIL`。只有至少两个 Harness 且控制同一模型/任务交集时才会评估 Harness 敏感性；一个 Harness 必须明确写出“无法评估 Harness 敏感性”。可用 `--validity` 直接合并 `validate-eval-results` 输出的 `eval_result_validity.json`，也兼容旧版顶层 `runs` JSON；上游定位到 run 的 error/review 会从能力统计排除，无法定位的顶层问题会单列。不能用本 Skill 替代 `validate-eval-results`。

默认输出 `<repo>/report-workspace/eval-dataset/quality/<timestamp>_<scope-hash>/report.{json,md}`。报告只保留路径、计数和截断证据，不写 API key、Bearer token 或 transcript 全文；如需只做分数统计，可加 `--no-trace-analysis`。具体指标边界见 [references/quality-methods.md](references/quality-methods.md)。
