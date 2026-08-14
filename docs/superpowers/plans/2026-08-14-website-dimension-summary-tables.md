# Website Dimension Summary Tables Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `站点评测指标` Sheet 的一级、二级维度改为两张支持多模型横向比较、双层表头和红黄绿色阶的汇总表。

**Architecture:** 保留现有维度聚合函数和结果/效率指标表。新增二级维度到一级维度的兼容归属映射，并在 `write_website_metrics_sheet` 中按一级、二级分别写入横表；所有数值继续使用百分比原始数值，由现有 `add_color_scale` 添加条件格式。

**Tech Stack:** Python 3.11、openpyxl、unittest/pytest、WildClawBench 现有报告生成器。

---

### Task 1: 锁定一级维度横向表契约

**Files:**
- Modify: `tools/report/tests/test_analysis_pipeline.py`
- Test: `tools/report/tests/test_analysis_pipeline.py`

- [ ] **Step 1: 写入一级维度布局失败测试**

在网站报告测试区域构造包含三个一级维度的 Web task，生成工作簿后定位 `一级维度汇总` 标题行，并断言：

```python
primary_title_row = first_column.index("一级维度汇总") + 1
self.assertEqual(
    [sheet.cell(primary_title_row + 1, column).value for column in range(1, 5)],
    ["模型@Harness", "内容与结构", "交互与功能", "视觉与布局"],
)
self.assertEqual(
    [sheet.cell(primary_title_row + 2, column).value for column in range(1, 5)],
    ["Model@Harness", 90.0, 80.0, 70.0],
)
self.assertTrue(any(
    str(item.sqref) == (
        f"B{primary_title_row + 2}:D{primary_title_row + 2}"
    )
    for item in sheet.conditional_formatting
))
```

- [ ] **Step 2: 运行测试确认当前实现失败**

Run:

```bash
/Users/gzx/.local/bin/uv run --with pytest --python .venv/bin/python -m pytest \
  tools/report/tests/test_analysis_pipeline.py::AnalysisPipelineTest::test_website_dimension_summaries_use_horizontal_grouped_tables -q
```

Expected: FAIL，原因是当前不存在单一 `一级维度汇总` 横表。

### Task 2: 锁定二级维度双层表头与兼容归属

**Files:**
- Modify: `tools/report/tests/test_analysis_pipeline.py`
- Test: `tools/report/tests/test_analysis_pipeline.py`

- [ ] **Step 1: 扩展同一测试的二级维度断言**

测试数据包含内容、交互、视觉各两个二级维度；另增加一个未知二级维度，验证其不会丢失。断言：

```python
secondary_title_row = first_column.index("二级维度汇总") + 1
group_row = secondary_title_row + 1
label_row = secondary_title_row + 2
self.assertEqual(sheet.cell(group_row, 1).value, "模型@Harness")
self.assertIn(
    f"A{group_row}:A{label_row}",
    {str(item) for item in sheet.merged_cells.ranges},
)
self.assertEqual(
    [sheet.cell(group_row, column).value for column in (2, 4, 6)],
    ["内容与结构", "交互与功能", "视觉与布局"],
)
self.assertEqual(
    [sheet.cell(label_row, column).value for column in range(2, 8)],
    ["基础内容", "信息组织", "页面导航", "操作反馈", "视觉风格", "页面布局"],
)
self.assertIn("其他", [sheet.cell(group_row, column).value for column in range(2, sheet.max_column + 1)])
```

- [ ] **Step 2: 再次运行测试确认失败点仍是布局缺失**

运行 Task 1 的单测命令，Expected: FAIL，且失败来自二级分组表头或未知维度缺失。

### Task 3: 实现横向维度汇总表

**Files:**
- Modify: `tools/report/scripts/generate_eval_report.py`
- Test: `tools/report/tests/test_analysis_pipeline.py`

- [ ] **Step 1: 增加旧结果兼容映射**

在 `WEBSITE_SECONDARY_ZH` 后增加 `WEBSITE_SECONDARY_PRIMARY`，将内容类、交互类和视觉类二级维度映射到现有三个一级键：

```python
WEBSITE_SECONDARY_PRIMARY = {
    "basic_content": "content_structure",
    "information_organization": "content_structure",
    "lists_tables": "content_structure",
    "detail_display": "content_structure",
    "data_visualization": "content_structure",
    "page_navigation": "interaction_function",
    "content_switching": "interaction_function",
    "form_validation": "interaction_function",
    "operation_feedback": "interaction_function",
    "state_persistence": "interaction_function",
    "cross_region_linkage": "interaction_function",
    "filtering_sorting": "interaction_function",
    "popup_overlay": "interaction_function",
    "search": "interaction_function",
    "content_editing": "interaction_function",
    "visual_style": "visual_layout",
    "page_layout": "visual_layout",
    "component_style": "visual_layout",
}
```

- [ ] **Step 2: 增加二级维度归属收集函数**

扫描所有 Web task 的 `metric_dimensions.secondary`，优先读取每个条目的 `primary`，字段缺失时查 `WEBSITE_SECONDARY_PRIMARY`。返回 `{secondary_key: primary_key}`；没有已知归属的键返回空字符串，写表时进入“其他”组。

- [ ] **Step 3: 用单一横表替换一级维度逐块循环**

按 `WEBSITE_PRIMARY_ZH` 的定义顺序收集实际出现的维度，写入标题、表头和每个 unit 的得分行。缺失值写 `-`，对数值单元格调用 `apply_pct_format`，最后调用：

```python
add_color_scale(ws, data_start, data_end, 2, 1 + len(dimensions))
```

- [ ] **Step 4: 写入二级双层表头横表**

按照一级维度顺序排列二级维度；未知一级归属最后放入“其他”。第一列跨两行合并，每个非空一级分组按列数合并第一层表头，第二层写二级中文名。数据行和色阶规则与一级表一致。

- [ ] **Step 5: 运行聚焦测试确认变绿**

Run:

```bash
/Users/gzx/.local/bin/uv run --with pytest --python .venv/bin/python -m pytest \
  tools/report/tests/test_analysis_pipeline.py::AnalysisPipelineTest::test_website_dimension_summaries_use_horizontal_grouped_tables -q
```

Expected: PASS。

### Task 4: 更新旧断言并执行报告回归

**Files:**
- Modify: `tools/report/tests/test_analysis_pipeline.py`
- Verify: `tools/report/scripts/generate_eval_report.py`

- [ ] **Step 1: 更新依赖旧纵向小表的断言**

将 `一级维度汇总：内容与结构` 和三列 `模型@Harness/平均分/任务数` 的断言改为新的横表标题、维度列和值；结果与效率指标的既有断言保持不变。

- [ ] **Step 2: 运行完整报告测试文件**

Run:

```bash
/Users/gzx/.local/bin/uv run --with pytest --python .venv/bin/python -m pytest -q \
  tools/report/tests/test_analysis_pipeline.py
```

Expected: 全部 PASS。

- [ ] **Step 3: 运行格式和编译检查**

Run:

```bash
.venv/bin/python -m compileall -q tools/report/scripts/generate_eval_report.py
git diff --check
```

Expected: exit 0，无输出。

### Task 5: 生成并验收实际 Excel

**Files:**
- Output: `eval_out_debug/website-dimension-summary-validation/...xlsx`

- [ ] **Step 1: 用现有网站评测结果生成新报告**

复用仓库中当前可用的 Web round 结果和 `generate_eval_report.py` 正式 CLI，输出新文件，不覆盖历史报告。

- [ ] **Step 2: 程序化检查工作簿结构**

读取 `站点评测指标`，检查一级表头、二级合并单元格、条件格式范围、百分比格式和数值；检查 `_站点评测指标口径` 仍为隐藏状态。

- [ ] **Step 3: 渲染并目视检查**

将 `站点评测指标` 的关键区域渲染为图片，确认表头未截断、一级分组边界清晰、红黄绿色阶覆盖正确，且逐任务明细仍位于两个汇总表之后。

- [ ] **Step 4: 运行发布前审计**

对新报告执行现有 audit 脚本；只有审计结果与本次范围一致时才报告完成，不覆盖或发布历史报告。
