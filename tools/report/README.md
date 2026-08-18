# WildClawBench 报告工具（tools/report）

评测完成后的**检查、分析、生成、审核链路**（本目录只放工具，产物一律写到评测结果侧的 `report-workspace/`）：

| 组件 | 位置 | 用途 |
|---|---|---|
| 评测结果有效性检查 Skill | `skills/validate-eval-results/` | 报告生成前检查完整性、环境异常、指标完整性和跨 unit 可比性 |
| 跨单元逐用例分析 Skill | `skills/cross-eval-analysis/` | 固定模型或 Harness 对齐共同有效任务，结合两侧轨迹分析分差机制并生成证据化 Markdown |
| 评测用例/低分根因分析 Skill | `skills/low-score-analysis/` | 支持阈值、区间、未满分、全量对照及指定任务分析，产出 scoped analysis JSON |
| 根因分析报告 Skill | `skills/low-score-report/` | 基于分析结果生成 Markdown 根因共性分析报告（五层归因 + 执行失效专项） |
| 评测报告 Excel 脚本 | `scripts/generate_eval_report.py` | 多单元对比 Excel，提供实体展示名、成本重算、根因回填和控制变量复制视图 |
| 领导版数据提取脚本 | `skills/eval-report/scripts/extract_leader_report_data.py` | 从 Excel 全量总览和控制变量视图提取稳定 JSON |
| 评测报告审核 Skill | `skills/audit-eval-report/` | 从 raw 独立复算 Excel 指标，检查反常统计和发布结论 |

## 工作流

```
eval_out/all_suite/round1/<model>/<harness>/           ← 评测结果
        │
        ▼ ⓪ skills/validate-eval-results（前置门禁）
<round>/report-workspace/validity/eval_result_validity.{json,md}
        │
        ▼ ① skills/low-score-analysis（筛选 + LLM 分析）
<round>/report-workspace/_failed_tasks_<model>@<harness>__lt60.json
<round>/report-workspace/analysis_<model>@<harness>__lt60.json
<round>/report-workspace/analysis_<model>@<harness>__lt60.quality.json
        │
        ├─▼ ② skills/low-score-report
        │  <result-root>/低分任务根因分析报告_<model>@<harness>.md
        └─▼ ③ scripts/generate_eval_report.py --analysis ...
           report-workspace/output/report_<N>units_<ts>.xlsx
           report-workspace/output/report_<N>units_<ts>.analysis_quality.json
                │
                ▼ ④ skills/audit-eval-report（发布前门禁）
                   report-workspace/audit/report_audit_<xlsx-stem>.{json,md}
```

分析单元统一为 `(模型, harness)` 二元组，全链路命名 `<model>@<harness>`（如 `gpt-5.5-pro@codex`）。

跨单元逐用例分析使用共同有效任务交集，不能把不同模型和不同 Harness 混在同一个控制变量结论中：

```bash
uv run python tools/report/skills/cross-eval-analysis/scripts/build_cross_eval_manifest.py \
  --result-root /path/to/eval_out/all_suite/round1 \
  --axis model \
  --fixed-harness astroncode \
  --models xsparkx2agent xopglm52 gpt-5.5 \
  --target-model xsparkx2agent \
  --tasks-dir /path/to/WildClawBench/tasks \
  --output /path/to/round1/report-workspace/cross_eval_model_manifest.json

# Workflow 读取 manifest 和两侧原始轨迹，输出 cross_eval_model_analysis.json 后：
uv run python tools/report/skills/cross-eval-analysis/scripts/validate_cross_eval.py \
  --manifest /path/to/round1/report-workspace/cross_eval_model_manifest.json \
  --analysis /path/to/round1/report-workspace/cross_eval_model_analysis.json
uv run python tools/report/skills/cross-eval-analysis/scripts/render_cross_eval_report.py \
  --manifest /path/to/round1/report-workspace/cross_eval_model_manifest.json \
  --analysis /path/to/round1/report-workspace/cross_eval_model_analysis.json \
  --output /path/to/round1/report-workspace/cross_eval_model_report.md

# 固定模型比较 Harness 时，将 --axis 改为 harness：
uv run python tools/report/skills/cross-eval-analysis/scripts/build_cross_eval_manifest.py \
  --result-root /path/to/eval_out/all_suite/round1 \
  --axis harness \
  --fixed-model xsparkx2agent \
  --harnesses astroncode opencode \
  --target-harness astroncode \
  --tasks-dir /path/to/WildClawBench/tasks \
  --output /path/to/round1/report-workspace/cross_eval_harness_manifest.json
```

## 快速开始

```bash
# 0. 检查原始评测结果
python3 tools/report/skills/validate-eval-results/scripts/validate_eval_results.py \
  --result-root /path/to/eval_out/all_suite/round1 \
  --models xsparkx2agent xopglm52 gpt-5.5 \
  --harnesses astroncode opencode

# 1. 生成低分任务清单（默认阈值 60 分）
python3 tools/report/skills/low-score-analysis/scripts/generate_failed_tasks_manifest.py \
  --result-root /path/to/eval_out/all_suite/round1 \
  --model gpt-5.5-pro --harness codex

# 2. 根因分析：在 Claude Code 中调用 /low-score-analysis（见 SKILL.md）

# 3. Markdown 报告：在 Claude Code 中调用 /low-score-report（见 SKILL.md）

# 4. Excel 报告（可不带 --analysis 先出对比报告）
python3 tools/report/scripts/generate_eval_report.py \
  --result-root /path/to/eval_out/all_suite/round1 \
  --models xsparkx2agent xopglm52 gpt-5.5 \
  --harnesses astroncode opencode \
  --target-model xsparkx2agent \
  --target-harness astroncode \
  --entities tools/report/data/entities.yaml \
  --pricing-date 2026-07-30 \
  --analysis "xsparkx2agent@astroncode=/path/to/round1/report-workspace/analysis_xsparkx2agent@astroncode__lt60.json"

# 5. 提取领导版报告数据
python3 tools/report/skills/eval-report/scripts/extract_leader_report_data.py \
  --excel /path/to/round1/report-workspace/output/report_6units_<ts>.xlsx \
  --output /path/to/round1/report-workspace/output/report_6units_<ts>_leader_data.json

# 6. 独立复算并审核报告
python3 tools/report/skills/audit-eval-report/scripts/audit_eval_report.py \
  --result-root /path/to/eval_out/all_suite/round1 \
  --excel /path/to/round1/report-workspace/output/report_6units_<ts>.xlsx \
  --models xsparkx2agent xopglm52 gpt-5.5 \
  --harnesses astroncode opencode \
  --entities tools/report/data/entities.yaml \
  --pricing-date 2026-07-30
```

## 实体与成本配置

`data/entities.yaml` 是版本化实体注册表。模型和 Harness 的 `display_name` 用于对外展示，raw ID 继续作为分析与审计主键。模型定价档案和人民币汇率按 `effective_from` 选择不晚于 `--pricing-date` 的最新版本；新增供应商、思考强度支持或 Harness 稳定属性时扩展对应实体对象，不使用平铺 `id -> name` 映射。

Excel `总成本(USD)` 是报告侧估算值。分档模型按逐请求上下文选择价格；无法确认 token 语义、档位或缓存写入价格时显示 `-`，不按 0 处理。

## 安装 Skill（软链到 .claude/skills）

```bash
mkdir -p .claude/skills
ln -snf ../../tools/report/skills/low-score-analysis .claude/skills/low-score-analysis
ln -snf ../../tools/report/skills/low-score-report .claude/skills/low-score-report
ln -snf ../../tools/report/skills/validate-eval-results .claude/skills/validate-eval-results
ln -snf ../../tools/report/skills/audit-eval-report .claude/skills/audit-eval-report
ln -snf ../../tools/report/skills/cross-eval-analysis .claude/skills/cross-eval-analysis
```

## 依赖

- Python 3.10+
- `openpyxl`（仅 Excel 脚本）：`pip install openpyxl`
- 根因分析 Skill 依赖 Claude Code 的 Workflow 工具

设计文档见 [docs/design.md](docs/design.md)。
