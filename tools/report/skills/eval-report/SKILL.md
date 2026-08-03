---
name: eval-report
description: Use when generating or regenerating WildClawBench Excel reports, leader-facing Markdown reports, or complete evaluation-report publication artifacts for a target model and Harness.
---

# WildClawBench 评测报告生成

## 目标

围绕指定目标模型与目标 Harness，生成可复算、可审计、能分别指导模型侧和 Harness 侧改进的报告：

1. scoped 根因分析 JSON；
2. 带友好名称、成本和控制变量复制视图的 Excel；
3. 领导版 Markdown；
4. 有效性检查与发布前审计结果。

内部匹配始终使用模型 ID、Harness ID 和 `<model>@<harness>`。对外只使用实体注册表中的展示名称。

## 模式

- **`preview`（预览模式）**：评测完成后快速发布，含各维度得分与对比分析，**不含**低分任务根因分析与典型案例。用于快速决策下一步动作（如是否需要重跑、优先分析哪些单元）。产物文件名带 `_preview` 后缀。

- **`full`（完整模式，默认）**：含根因分析、典型案例、有效性检查与改进建议，用于正式归档与对外发布。

**典型工作流**：
1. 评测完成 → 生成 **preview** 报告 → 相关方快速查看维度表现 → 决策是否需要补测/重跑；
2. 根因分析完成 → 生成 **full** 报告 → 补充典型案例与改进建议 → 正式发布与归档。

Preview 与 full 的维度数据完全一致（同样的 Excel 维度 Sheet、同样的控制变量表），差异仅在根因列与典型案例节的有无。

## 必需输入

- round 根目录；
- 参评模型 ID 列表与参评 Harness ID 列表；
- 目标模型 ID；
- 目标 Harness ID；
- 实体注册表，默认 `tools/report/data/entities.yaml`；
- 定价日期 `YYYY-MM-DD`；
- **报告模式**：`preview` 或 `full`（默认 `full`）；
- 需要回填的 scoped analysis JSON（仅 full 模式需要）。

目标模型和目标 Harness 是变量，禁止把 `xsparkx2agent`、`astroncode` 等当前验证值写死在流程或结论中。

## 0. 有效性门禁

检查范围必须与 Excel 一致：

```bash
python3 tools/report/skills/validate-eval-results/scripts/validate_eval_results.py \
  --result-root <round> \
  --models <model-id...> \
  --harnesses <harness-id...> \
  --fail-on never
```

- `PASS`：继续。
- `REVIEW`：完成归因并记录处置，未闭环前不得发布。
- `FAIL`：修复、重跑或重新判分，禁止在报告层掩盖问题。

### L3/L4 发布边界

L3 评测环境和 L4 评测系统/任务/Grader 保留在内部根因数据中，用于有效性治理，不是模型或 Harness 能力分类。

- 确认影响得分的 L3/L4 必须修复并重跑或重新判分；旧 run 通过 `supersedes_run` 退出正式统计。
- 未闭环 L3/L4 阻断 `PASS`。用户明确接受风险时，只能进入独立的”评测有效性与剔除说明”。
- L3/L4 不得进入典型低分案例，不得写入模型侧或 Harness 侧能力结论。
- 模型 API、模型专属视觉通道、Harness 工具协议或 Harness 进程异常按实际责任归属，不能因表面像环境错误就自动归入 L3/L4。

## 流程

### Preview 模式

1. ~~scoped 根因分析~~（跳过）
2. 生成 Excel（不传 `--analysis`，评分详情表根因列为空）
3. ~~有效性检查~~（跳过）
4. 领导版 Markdown（只含总览与各维度分析，不含典型案例节）
5. 发布前审计（只检查显示名反查、成本复算、表头完整性，跳过有效性门禁与根因覆盖率检查）

产物文件名带 `_preview` 后缀，如 `report_7units_20260803_preview.xlsx`、`评测报告_GLM-5.1_AstronCode_round4_preview.md`。

### Full 模式（默认）

完整五步流程（有效性检查 → 根因分析 → Excel → 领导报告 → 审计），产物不带后缀。

## 1. scoped 根因分析（仅 full 模式）

按需要回填的 unit 调用 `low-score-analysis`。清单、批次和合并结果统一放在 `<round>/report-workspace`。

```bash
python3 tools/report/skills/low-score-analysis/scripts/generate_failed_tasks_manifest.py \
  --result-root <unit-dir> --threshold 60
```

分析时先读任务 Markdown 的判分代码，再读完整 transcript。输出必须包含 `task_id`、`result_analysis`、`root_cause_analysis`，并标记 L1a/L1b/L3/L4 或 Harness 责任。合并后校验任务集合 1:1 对齐且两个分析字段非空。

## 2. 生成 Excel

**Preview 模式**：不传 `--analysis`，评分详情表的”结果分析”与”根因分析”列为空。

**Full 模式**：传入所有 unit 的 `--analysis` 参数。

```bash
python3 tools/report/scripts/generate_eval_report.py \
  --result-root <round> \
  --models <model-id...> \
  --harnesses <harness-id...> \
  --target-model <target-model-id> \
  --target-harness <target-harness-id> \
  --entities tools/report/data/entities.yaml \
  --pricing-date <YYYY-MM-DD> \
  --analysis “<unit>=<analysis-json>” ...  # 仅 full 模式传入
```

必须生成新文件，不覆盖历史报告。生成后检查：

- `总览` 第 1 行表头和全部原有列保持不变；
- 所有可见模型、Harness 和 unit 使用展示名称；
- `_报告元数据` 为隐藏 Sheet，能反查 raw ID、目标组合、定价档案、汇率与成本状态；
- `分类对比`、`Agent能力对比`、`Agent能力对比·去污染`、`难度对比`、`模态对比` 顶部保留全量原表；
- 五个维度 Sheet 下方均有”固定目标 Harness：模型对比”和”固定目标模型：Harness 对比”两张连续、带配色、可直接复制的表；
- 评分详情仍使用 raw unit 命名，analysis 回填条数与 JSON 一致（preview 模式下为 0）。

### 成本口径

`总成本(USD)` 是按实体注册表、定价日期和逐请求 token 重算的估算值，不代表供应商最终账单。GPT 分档定价必须逐请求判断；人民币模型按注册表中不晚于定价日期的汇率换算。缺价格、缺逐请求证据、token 语义不明或缓存写入无单价时显示 `-`，不得按 0 处理。

## 3. 提取领导版数据

禁止从 Excel 手抄或凭印象填数字。先运行：

```bash
python3 tools/report/skills/eval-report/scripts/extract_leader_report_data.py \
  --excel <new-report.xlsx> \
  --output <new-report_leader_data.json>
```

提取器按列名和控制变量视图标题读取。领导版报告的每个数字都来自该 JSON；出稿后逐格对照最新 Excel。

## 4. 领导版 Markdown

**Preview 模式章节顺序**：

1. 总览；
2. 二、分类维度；
3. 三、Agent能力；
4. 四、难度等级；
5. 五、模态对比；
6. ~~六、典型低分案例~~（跳过）；
7. 总结与改进建议（仅基于维度分差，不含案例证据）。

**Full 模式章节顺序**（包含典型案例）：

1. 总览；
2. 二、分类维度；
3. 三、Agent能力；
4. 四、难度等级；
5. 五、模态对比；
6. 六、典型低分案例；
7. 总结与改进建议。

### 总览

总览保留全部列，列名、顺序和值与 Excel `总览` 完全一致，不删减 tokens、请求数、耗时、成本或可选工具指标。目标组合先给定位，再说明最关键的效果、可靠性或效率信号。

### 维度表规则

分类、Agent能力、难度和模态不展示同时改变模型与 Harness 的全量混合矩阵。每个维度固定按以下顺序：

1. 维度总判断；
2. 固定目标 Harness 的模型侧总结；
3. `model_view` 表；
4. 固定目标模型的 Harness 侧总结；
5. `harness_view` 表；
6. 必要的口径备注。

固定目标 Harness 时，先说明已有优势、接近项或相对稳定项，再指出差距集中的场景或能力和模型侧优先提升方向。必须区分“目标模型内部最高项”和“相对参照模型已具竞争力的强项”，不能把内部最高项直接写成对外优势。

固定目标模型时，先说明不同 Harness 表现接近的维度，再指出对 Harness 选择较敏感的维度和 Harness 侧优先排查方向。只有 transcript 或根因分析有直接证据时才能确定归因；仅凭分差相关性时必须写“优先排查”，不能写成已确认原因。

Agent 原始 7 维必须进入报告。去污染 3 维只有在会改变强弱判断或改进优先级时才展示，并紧邻对应 Agent 控制变量表说明变化。

### 结论长度与证据

每张控制变量表上方的总结最多 2 句话，合计不超过 3 个关键数字。第一句先写已有基础、接近项或相对优势，再写差距集中位置；第二句给改进方向或必要边界。

数字用于支撑判断，不承担整段叙述。优先使用分差、区间或“除主要差异项外，其余维度分差均在某一区间”等概括，不逐项播报谁高谁低。能用 0–2 个关键数字说清时，不使用第 3 个数字。

- 分类与难度优先写样本量大、分差大、影响总分的项目。
- 模型侧建议落到训练数据、规划、工具结果理解、验证和长程收敛等可执行能力。
- Harness 侧建议落到提示组装、工具参数、结果解析、错误恢复、状态管理和产物校验。
- 不逐项复述表格，不用无证据因果。

### 典型低分案例（仅 full 模式）

选 5–6 个证据完整、机制不重复的 L1a、L1b 或 Harness 责任案例。案例必须包含任务、得分、实际执行证据、失分机制、责任归属和可执行改进。默认不选环境、任务、Grader 或统计框架问题。

若有效性门禁要求披露 L3/L4，在典型案例之前增加独立的”评测有效性与剔除说明”，只写影响范围、处置与是否计入统计。

**Preview 模式跳过本节**。

### 文风

- 结论前置，通俗、短句、陈述句。
- 能力结论优先使用”已有一定基础””与参照对象处于同一水平区间””整体较为接近””差距主要集中在””仍处于追赶阶段””对 Harness 选择较敏感””可优先补充或优先排查”。
- 避免使用”排名末位””全面落后””均未达到””整体偏弱””明显落后””短板覆盖全部场景””不具竞争力”等硬评价。
- 有效性门禁、已确认故障和发布阻断保持准确、直接，不因语气要求弱化事实。
- 禁用”持续优化””进一步提升””全面加强””值得注意的是””综上所述”等空话。
- 禁用反问、排比、夸张比喻和无依据判断。
- 每条建议必须对应表格分差或案例证据，并明确模型侧或 Harness 侧责任。
- **Preview 模式**：总结与改进建议仅基于维度分差，不依赖案例证据；改进方向更概括，如”代码智能场景优先补充/优先排查”而非具体到某个失败模式。

模板见 `references/report_template.md`。

## 5. 发布前审计

**Preview 模式审计范围**：
- 显示名反查（模型/Harness 展示名能否反查到注册表）；
- 成本复算（独立重算 `总成本(USD)` 列，与 Excel 值对比）；
- 表头完整性（`总览` 列名、顺序与预期一致）；
- ~~有效性门禁~~（跳过）；
- ~~根因覆盖率~~（跳过）。

**Full 模式审计范围**：全部检查项。

```bash
python3 tools/report/skills/audit-eval-report/scripts/audit_eval_report.py \
  --result-root <round> \
  --excel <new-report.xlsx> \
  --models <model-id...> \
  --harnesses <harness-id...> \
  --entities tools/report/data/entities.yaml \
  --pricing-date <YYYY-MM-DD> \
  --validity <round>/report-workspace/validity/eval_result_validity.json \  # preview 模式不传
  --fail-on never
```

审核显示名反查、全部原始表指标、独立成本复算和有效性结论。`FAIL` 必须修复并重生成；`REVIEW` 必须记录证据、解释和风险接受结论。未达到 `PASS` 时不得声称报告可发布。

## 产物

```text
<round>/report-workspace/validity/eval_result_validity.{json,md}
<round>/report-workspace/analysis_<unit>__<scope>.json
<round>/report-workspace/output/report_<N>units_<ts>.xlsx
<round>/report-workspace/output/report_<N>units_<ts>_leader_data.json
<round>/report-workspace/audit/report_audit_<xlsx-stem>.{json,md}
<round>/评测报告_<目标模型展示名>_<目标Harness展示名>_<round>_<ts>.md
```
