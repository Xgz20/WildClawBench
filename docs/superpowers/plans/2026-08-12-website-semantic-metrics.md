# Website Semantic Metrics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Website Generation 用例在不启动站点、不执行浏览器点击的第一阶段，能够通过源码语义评测产出原子指标、一级维度、二级维度和总分。

**Architecture:** Rubric 标题继续以 `key` 和 `weight` 驱动现有 v2 LLM Judge，同时增加可选的 `primary`、`secondary` 稳定键。评分器读取有限且排除构建产物的前端源码作为语义证据，原子分保持现有顶层键，维度聚合写入嵌套 `_dimensions`；报告按任务内加权、跨任务等权展示站点一级与二级指标。

**Tech Stack:** Python 3、Markdown/YAML 任务定义、unittest、openpyxl。

---

### Task 1: 扩展 Rubric 元数据解析

**Files:**
- Modify: `src/utils/task_parser.py`
- Create: `tests/test_task_rubric_parser.py`

- [x] 先增加失败测试，覆盖旧 `(key, weight)` 格式及新 `(key, primary, secondary, weight)` 格式。
- [x] 运行 `python -m unittest tests.test_task_rubric_parser -v`，确认新格式测试因缺少维度字段而失败。
- [x] 解析可选 `primary`、`secondary`，旧任务缺少两字段时仍返回空字符串。
- [x] 重跑测试并确认通过。

### Task 2: 修正 Website Generation Rubric 契约

**Files:**
- Modify: `tasks/extension/07_Website_Generation/*.md`
- Modify: `tests/test_website_generation_tasks.py`

- [x] 增加失败契约测试，要求每个 Criterion 都有唯一 `key`、合法一级/二级维度且权重和接近 1。
- [x] 给 5 个任务的 66 个 Criterion 增加稳定英文键，保留所有当前权重和判据正文。
- [x] 运行 `python -m unittest tests.test_website_generation_tasks -v`，确认 5 个任务均能解析全部 Criterion。

### Task 3: 增加源码语义证据和维度聚合

**Files:**
- Modify: `src/utils/grading.py`
- Create: `tests/test_website_semantic_grading.py`

- [x] 增加失败测试，验证前端源码扩展名被纳入、构建目录被排除、一级/二级分按 Criterion 权重在维度内归一。
- [x] Judge prompt 明确 `source_semantic` 证据口径，不得声称真实渲染或点击通过。
- [x] `score.json` 增加 `_dimensions`，包含 `evidence_mode`、一级/二级得分及其任务内权重；总分公式保持不变。
- [x] 运行聚焦测试，确认纯 LLM 任务仍输出 `v2_llm_only`，原子分仍为 `llm_judge.<key>`。

### Task 4: 增加站点评测指标报告

**Files:**
- Modify: `tools/report/scripts/generate_eval_report.py`
- Modify: `tools/report/tests/test_analysis_pipeline.py`

- [x] 增加失败测试，构造两个站点任务且 Criterion 数量不同，验证一级指标跨任务等权而非按 Criterion 数量加权。
- [x] `TaskRecord` 读取 `_dimensions`，新增“站点评测指标”Sheet：一级指标汇总、二级指标汇总和逐任务明细。
- [x] Sheet 标注第一阶段为源码语义评测，不代表真实渲染、启动或点击测试。
- [x] 运行报告测试，确认非站点评测结果不新增空 Sheet。

### Task 5: 完整验证

**Files:**
- Verify only

- [x] 运行新增及相关回归测试。
- [x] 运行 `git diff --check`。
- [x] 检查 5 个任务解析数量、key 唯一性、权重和，以及工作区只包含本次相关改动。

### Task 6: 显式标识专项指标协议

**Files:**
- Modify: `src/utils/task_parser.py`
- Modify: `eval/run_batch.py`
- Modify: `eval_e2e/grade_runs.py`
- Modify: `src/utils/grading.py`
- Modify: `tools/report/scripts/generate_eval_report.py`
- Modify: `tests/test_task_rubric_parser.py`
- Modify: `tests/test_website_semantic_grading.py`
- Modify: `tools/report/tests/test_analysis_pipeline.py`

- [x] 增加失败测试，要求 `web-site-gen` tag 映射为 `metric_profile=web-site-gen`，普通任务保持空值。
- [x] 增加失败测试，要求源码语义取证、网站提示词和维度聚合只由显式 `metric_profile` 启用，不能通过 `primary` 名称反推。
- [x] 将 `metric_profile` 从任务解析结果传递到批量评分和 E2E 补评分入口。
- [x] 在 `_dimensions` 中同时写入 `metric_profile` 与 `evidence_mode`，并让 Excel 按二者识别网站专项指标。
- [x] 运行解析、评分、执行入口和报告回归测试，并执行 `git diff --check`。
