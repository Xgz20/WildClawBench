# Leader Report Summary Tone Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将领导版报告控制变量总结改为“格局与亮点优先、集中差距与行动在后”的委婉表达，并固化到 Skill 和模板。

**Architecture:** 不修改 Excel、指标或数据提取器。通过现有 Skill 合同测试锁定文风规则，在 `SKILL.md` 和模板中提供结构约束与示例，再按同一规则改写当前领导版 Markdown。

**Tech Stack:** Markdown、Python `unittest`、ripgrep。

---

### Task 1: Add Summary Tone Contract Test

**Files:**
- Modify: `tools/report/tests/test_analysis_pipeline.py:1125`
- Test: `tools/report/tests/test_analysis_pipeline.py`

- [x] **Step 1: Write the failing assertions**

在 `test_eval_report_skill_contract_for_controlled_views` 中增加：

```python
self.assertIn("先说明已有优势", skill)
self.assertIn("数字用于支撑判断", skill)
self.assertIn("对 Harness 选择较敏感", skill)
self.assertIn("避免使用", skill)
self.assertIn("先写已有基础或接近项", template)
self.assertIn("分差均在 5 分以内", template)
```

- [x] **Step 2: Run the focused test and verify RED**

Run:

```bash
python3 -m unittest tools.report.tests.test_analysis_pipeline.AnalysisPipelineTest.test_eval_report_skill_contract_for_controlled_views
```

Expected: `FAIL`，提示 Skill 或模板缺少新文风规则。

### Task 2: Update Skill And Template

**Files:**
- Modify: `tools/report/skills/eval-report/SKILL.md:125`
- Modify: `tools/report/skills/eval-report/references/report_template.md:28`

- [x] **Step 1: Add the controlled-view summary structure**

在 Skill 中明确：

```markdown
每张控制变量表上方的总结先说明已有优势、接近项或相对稳定项，再指出差距集中位置和改进方向。数字用于支撑判断，不承担整段叙述。
```

- [x] **Step 2: Add model and Harness writing rules**

固定目标 Harness 时，先写目标模型与参照模型接近或已有优势的维度，再写差距集中的能力。固定目标模型时，先写不同 Harness 表现接近的维度，再写对 Harness 选择较敏感的维度；只有直接证据才能确认原因。

- [x] **Step 3: Add tone boundaries**

在 Skill 中增加“优先使用”和“避免使用”清单，避免能力结论使用“排名末位、全面落后、均未达到、整体偏弱、明显落后、不具竞争力”。有效性门禁和已确认故障保持直接表达。

- [x] **Step 4: Add concrete template prompts and examples**

模板中的每个控制变量占位说明改为：先写已有基础或接近项，再写集中差距和方向。分类维度加入“除主要差异项外，其余维度分差均在 5 分以内”的 Harness 示例。

- [x] **Step 5: Run the focused test and verify GREEN**

Run:

```bash
python3 -m unittest tools.report.tests.test_analysis_pipeline.AnalysisPipelineTest.test_eval_report_skill_contract_for_controlled_views
```

Expected: `OK`。

### Task 3: Rewrite Current Leader Report

**Files:**
- Modify: `/Users/gzx/Project/GitHub/xgz/ai/evaluate/WildClawBench/eval_out/all_suite/round3_t3600/评测报告_Spark-X2-300B_AstronCode_round3_t3600_20260730_130536.md`

- [x] **Step 1: Rewrite report conclusion and overview tone**

将“排名末位、不具竞争力”等表达改为“当前处于追赶阶段、已有安全对齐基础、差距集中在通用执行与交付链路”，保留有效性门禁原文。

- [x] **Step 2: Rewrite four fixed-Harness summaries**

分类先写安全对齐接近或占优，再写社交互动等通用场景差距；Agent 先写推理规划和验证交付是相对稳定项；难度先写 L2 已有基础并提示 L1 单样本限制；模态先写纯文本基础，再写多模态提升空间。

- [x] **Step 3: Rewrite four fixed-model summaries**

分类先写除社交互动外五类分差均在 5 分内；Agent 先写推理规划接近、AstronCode 代码生成较好，再写工具与交付差异；难度先写 L2 接近，再写复杂任务 Harness 敏感；模态先写两种模态方向一致，再写纯文本差异更明显。

- [x] **Step 4: Scan the report for hard evaluations**

Run:

```bash
rg -n "排名末位|全面落后|均未达到|整体偏弱|明显落后|不具竞争力|短板覆盖" /Users/gzx/Project/GitHub/xgz/ai/evaluate/WildClawBench/eval_out/all_suite/round3_t3600/评测报告_Spark-X2-300B_AstronCode_round3_t3600_20260730_130536.md
```

Expected: 无输出。

### Task 4: Verify And Commit

**Files:**
- Modify: `tools/report/tests/test_analysis_pipeline.py`
- Modify: `tools/report/skills/eval-report/SKILL.md`
- Modify: `tools/report/skills/eval-report/references/report_template.md`

- [x] **Step 1: Run all report tests**

Run:

```bash
python3 -m unittest discover -s tools/report/tests -p 'test_*.py'
```

Expected: 全部测试通过。

- [x] **Step 2: Check diffs and unrelated files**

Run:

```bash
git diff --check
git status --short
```

Expected: 仅 Skill、模板、测试和本计划存在预期变化；`back.env-bak` 保持未跟踪且不纳入提交。

- [x] **Step 3: Commit repository changes**

```bash
git add tools/report/tests/test_analysis_pipeline.py tools/report/skills/eval-report/SKILL.md tools/report/skills/eval-report/references/report_template.md docs/superpowers/plans/2026-07-30-report-summary-tone.md
git commit -m "docs(report): 优化控制变量总结表达"
```
