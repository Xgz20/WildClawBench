# Web 站点评测报告指标补齐 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 在现有 `站点评测指标` Sheet 补齐 Web 结果、分层、耗时、成本和 Token 指标，并同步到 leader data 与领导版报告模板。

**Architecture:** `TaskRecord` 保存全部有效 run 目录，新增 Web 专属的任务级和运行级聚合函数；Excel 只消费聚合结果。leader data 按固定表头提取该区域，模板按指标是否存在决定是否展示 Web 章节，通用总览和非 Web 报告不变。

**Tech Stack:** Python 3、openpyxl、unittest、现有 `report_entities` 定价模块、`select_effective_run_dirs`

---

### Task 1: Web 任务级与运行级聚合

**Files:**
- Modify: `tools/report/scripts/generate_eval_report.py`
- Test: `tools/report/tests/test_analysis_pipeline.py`

- [x] **Step 1: 写任务结果和运行效率的失败测试**

构造两个带 `difficulty` 的 Web 任务和多个有效 run，断言聚合结果包含严格满分率、L1/L2、平均/P50/P90、平均总/输入/输出 Token；再增加 `supersedes_run` 断言旧 run 被排除。

```python
metrics = excel_report._website_unit_metrics(unit, task_meta)
self.assertEqual(metrics["满分率"].value, 50.0)
self.assertEqual(metrics["L1题目得分率"].value, 100.0)
self.assertEqual(metrics["运行耗时P90"].value, 28.0)
self.assertEqual(metrics["单次运行平均总Token"].value, 150.0)
```

- [x] **Step 2: 运行测试并确认因聚合接口不存在而失败**

Run: `uv run python -m unittest tools.report.tests.test_analysis_pipeline.AnalysisPipelineTest.test_website_unit_metrics_include_result_and_run_efficiency -v`

Expected: `FAIL` 或 `ERROR`，明确指向 `_website_unit_metrics` 尚不存在或缺少新指标。

- [x] **Step 3: 实现最小运行级模型和聚合函数**

在 `TaskRecord` 保存 `effective_run_dirs`；实现确定性线性插值百分位、Web 任务筛选、严格 `score == 1.0`、按 frontmatter 难度分组、逐 run 耗时与 usage 聚合。缺失数值不按 0。

```python
def _linear_percentile(values: list[float], percentile: float) -> float | None:
    ordered = sorted(values)
    if not ordered:
        return None
    position = (len(ordered) - 1) * percentile
    lower, upper = int(position), min(int(position) + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)
```

- [x] **Step 4: 实现逐 run 成本复算**

提取现有 `_estimate_cost` 的共享逻辑为 `_estimate_run_cost`，传入单个 run 的 usage 和目录。单档按 usage 计价，分档按该 run 的逐请求 Token 证据计价；只有全部应计 run 可定价时输出平均成本。

- [x] **Step 5: 运行聚合测试并确认通过**

Run: `uv run python -m unittest tools.report.tests.test_analysis_pipeline.AnalysisPipelineTest.test_website_unit_metrics_include_result_and_run_efficiency tools.report.tests.test_analysis_pipeline.AnalysisPipelineTest.test_website_unit_metrics_exclude_superseded_runs -v`

Expected: `OK`，2 tests passed。

### Task 2: Excel 汇总区域

**Files:**
- Modify: `tools/report/scripts/generate_eval_report.py`
- Test: `tools/report/tests/test_analysis_pipeline.py`

- [x] **Step 1: 写 Excel 区域失败测试**

调用 `write_website_metrics_sheet(wb, units, task_meta)`，定位“结果与效率指标汇总”，断言 14 个指标存在、没有“美观度”、百分比/秒/USD/Token 为数值单元格，并保持原一级维度汇总。

- [x] **Step 2: 运行测试并确认旧签名或缺少区域导致失败**

Run: `uv run python -m unittest tools.report.tests.test_analysis_pipeline.AnalysisPipelineTest.test_website_metrics_sheet_writes_complete_summary -v`

Expected: `FAIL`，缺少“结果与效率指标汇总”或新指标行。

- [x] **Step 3: 扩展 Sheet 写入逻辑并传入 task_meta**

新增列 `模型@Harness / 指标分类 / 指标名称 / 数值 / 样本数 / 计算方法`，对百分比、秒、USD、Token 分别应用稳定格式；保留原一级、二级和逐任务明细区域。主函数改为：

```python
write_website_metrics_sheet(wb, units, task_meta)
```

- [x] **Step 4: 运行 Web Sheet 及旧兼容测试**

Run: `uv run python -m unittest tools.report.tests.test_analysis_pipeline.AnalysisPipelineTest.test_website_metrics_sheet_writes_complete_summary tools.report.tests.test_analysis_pipeline.AnalysisPipelineTest.test_website_metrics_average_tasks_equally_and_write_semantic_scope -v`

Expected: `OK`。

### Task 3: leader data 与报告模板同步

**Files:**
- Modify: `tools/report/skills/eval-report/scripts/extract_leader_report_data.py`
- Modify: `tools/report/skills/eval-report/references/report_template.md`
- Modify: `tools/report/skills/eval-report/SKILL.md`
- Test: `tools/report/tests/test_analysis_pipeline.py`

- [x] **Step 1: 写 leader data 失败测试**

生成包含 Web 汇总区域的工作簿，断言 `extract_workbook()` 返回按 unit 分组的 `website_metrics`，并验证无 Web Sheet 时为 `{}`。

```python
self.assertEqual(payload["website_metrics"]["Model@Harness"]["满分率"]["value"], 50.0)
self.assertEqual(payload_without_web["website_metrics"], {})
```

- [x] **Step 2: 运行测试并确认缺少字段而失败**

Run: `uv run python -m unittest tools.report.tests.test_analysis_pipeline.AnalysisPipelineTest.test_leader_extractor_reads_website_metrics -v`

Expected: `FAIL`，`website_metrics` 不存在。

- [x] **Step 3: 实现提取器并更新模板/Skill**

按标题与固定六列表头提取，返回结构化值；模板增加条件性的“站点评测指标”章节，并明确不得展示美观度、不得从 Excel 手抄数字。Skill 的 Excel 和 Markdown 检查清单同步增加该区域。

- [x] **Step 4: 运行提取器和报告契约测试**

Run: `uv run python -m unittest tools.report.tests.test_analysis_pipeline.AnalysisPipelineTest.test_leader_extractor_reads_website_metrics tools.report.tests.test_analysis_pipeline.AnalysisPipelineTest.test_report_skill_documents_website_metrics -v`

Expected: `OK`。

### Task 4: 全量回归与 round1 重生成

**Files:**
- Generated: `eval_out_debug/website-e2e/round1/report-workspace/output-website-metrics-*/report_1units_*.xlsx`
- Generated: 同目录下 `report_1units_*_leader_data.json`
- Generated: `eval_out_debug/website-e2e/round1/评测报告_GLM-5.2_AstronCode_round1_*_website_metrics.md`

- [x] **Step 1: 运行完整报告测试**

Run: `uv run python -m unittest tools.report.tests.test_analysis_pipeline -v`

Expected: 所有测试 `OK`。

- [x] **Step 2: 使用 round1 数据生成新 Excel**

Run: `uv run python tools/report/scripts/generate_eval_report.py --result-root eval_out_debug/website-e2e/round1 --models xopglm52 --harnesses astroncode --target-model xopglm52 --target-harness astroncode --entities tools/report/data/entities.yaml --pricing-date 2026-08-12 --tasks-dir tasks --output-dir eval_out_debug/website-e2e/round1/report-workspace/output-website-metrics-<timestamp>`

Expected: 输出新的 `.xlsx`，不覆盖旧报告。

- [x] **Step 3: 提取 leader data 并按模板更新领导版 Markdown**

Run: `uv run python tools/report/skills/eval-report/scripts/extract_leader_report_data.py --excel <new.xlsx> --output <new_leader_data.json>`

Expected: JSON 中含目标 unit 的 14 个 Web 指标；Markdown 中展示同一组数值且无美观度。

- [x] **Step 4: 执行有效性门禁和报告审计**

Run: `uv run python tools/report/skills/validate-eval-results/scripts/validate_eval_results.py --result-root eval_out_debug/website-e2e/round1 --models xopglm52 --harnesses astroncode --fail-on never --output-dir <validity-dir>`

Run: `uv run python tools/report/skills/audit-eval-report/scripts/audit_eval_report.py --result-root eval_out_debug/website-e2e/round1 --excel <new.xlsx> --tasks-dir tasks --validity <validity-dir>/eval_result_validity.json --output-dir <audit-dir>`

Expected: 有效性门禁 `PASS`，报告审计 0 error。

- [x] **Step 5: 检查工作簿数值、公式错误和视觉布局**

读取 `站点评测指标` 关键范围核对 14 个指标，扫描 `#REF!/#DIV/0!/#VALUE!/#NAME?/#N/A`，并渲染该 Sheet 检查列宽、换行和数值可读性。

- [x] **Step 6: 检查变更并提交**

Run: `git diff --check && git status --short`

Commit: `feat(report): 补齐站点评测结果与效率指标`
