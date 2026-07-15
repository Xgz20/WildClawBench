# WildClawBench 报告工具（tools/report）

评测完成后的**分析与报告链路**三件套（本目录只放工具，产物一律写到评测结果侧的 `report-workspace/`）：

| 组件 | 位置 | 用途 |
|---|---|---|
| 低分任务根因分析 Skill | `skills/low-score-analysis/` | 筛出低分任务，LLM 结合判分明细 + transcript 逐任务找失分根因，产出 `analysis_<unit>.json` |
| 根因分析报告 Skill | `skills/low-score-report/` | 基于分析结果生成 Markdown 根因共性分析报告（四层归因 + 环境失效专项） |
| 评测报告 Excel 脚本 | `scripts/generate_eval_report.py` | 多单元（`model@harness`）对比 Excel，支持把根因分析回填到详情 Sheet |

## 工作流

```
eval_out/all_suite/round1/<model>/<harness>/           ← 评测结果
        │
        ▼ ① skills/low-score-analysis（筛选 + LLM 分析）
report-workspace/_failed_tasks_<model>@<harness>.json
report-workspace/analysis_<model>@<harness>.json
        │
        ├─▼ ② skills/low-score-report
        │  <result-root>/低分任务根因分析报告_<model>@<harness>.md
        └─▼ ③ scripts/generate_eval_report.py --analysis ...
           report-workspace/output/report_<N>units_<ts>.xlsx
```

分析单元统一为 `(模型, harness)` 二元组，全链路命名 `<model>@<harness>`（如 `gpt-5.5-pro@codex`）。

## 快速开始

```bash
# 1. 生成低分任务清单（默认阈值 60 分）
python3 tools/report/skills/low-score-analysis/scripts/generate_failed_tasks_manifest.py \
  --result-root /path/to/eval_out/all_suite/round1 \
  --model gpt-5.5-pro --harness codex

# 2. 根因分析：在 Claude Code 中调用 /low-score-analysis（见 SKILL.md）

# 3. Markdown 报告：在 Claude Code 中调用 /low-score-report（见 SKILL.md）

# 4. Excel 报告（可不带 --analysis 先出对比报告）
python3 tools/report/scripts/generate_eval_report.py \
  --result-root /path/to/eval_out/all_suite/round1 \
  --analysis /path/to/report-workspace/analysis_gpt-5.5-pro@codex.json
```

## 安装 Skill（软链到 .claude/skills）

```bash
mkdir -p .claude/skills
ln -snf ../../tools/report/skills/low-score-analysis .claude/skills/low-score-analysis
ln -snf ../../tools/report/skills/low-score-report .claude/skills/low-score-report
```

## 依赖

- Python 3.9+
- `openpyxl`（仅 Excel 脚本）：`pip install openpyxl`
- 根因分析 Skill 依赖 Claude Code 的 Workflow 工具

设计文档见 [docs/design.md](docs/design.md)。
