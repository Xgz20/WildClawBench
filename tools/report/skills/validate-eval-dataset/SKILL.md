---
name: validate-eval-dataset
description: 校验 WildClawBench 评测任务的 Markdown/frontmatter、评分契约、Workspace、Skills、Env 和 Warmup 预置条件；当用户要求检查新增评测集、任务 ID、任务目录或评测框架兼容性时使用。
---

# Validate Eval Dataset

使用仓库内脚本做确定性静态校验。默认扫描 `<repo>/tasks`（包含 `tasks/extension`），也可重复指定 `--task-dir`、`--task-path`、`--task-id`；`--task-id @file` 按行读取 ID 清单。

```bash
python3 .agents/skills/validate-eval-dataset/scripts/validate_eval_dataset.py
python3 .agents/skills/validate-eval-dataset/scripts/validate_eval_dataset.py \
  --task-dir tasks/extension --output-dir /tmp/wcb-static-validation
```

脚本只读取任务和仓库资源，不执行评分代码或宿主机 Warmup。它会检查 frontmatter/章节、`grade()` AST、rubric key/weight、Workspace 引用、`skills/<name>/SKILL.md`、Env 名称和当前环境中的存在性，以及 Warmup 命令的静态危险模式和引用文件。只有显式 `--smoke` 才在一次性 Docker 容器中运行 Warmup；缺少镜像或 Docker 输出 `SMOKE_UNAVAILABLE`。

报告使用 `PASS`、`REVIEW`、`FAIL`：确定性契约/文件/变量问题为 `FAIL`，统计或 smoke 不可用为 `REVIEW`（可用 `--fail-on review` 升级门禁）。JSON 的 `summary.action_summary` 和 Markdown 的“结论摘要”会按 task ID 列出需要修改、需要人工审核和未发现问题的用例，并给出修复建议。默认写入 `<repo>/report-workspace/eval-dataset/static/<timestamp>_<scope-hash>/report.{json,md}`；Env 只输出变量名和 `present/missing`，不输出值。

详细规则见 [references/checklist.md](references/checklist.md)。
