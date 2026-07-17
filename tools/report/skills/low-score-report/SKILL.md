---
name: low-score-report
description: Generate a comprehensive root-cause report for WildClawBench low-score tasks, with layered attribution analysis (L1a/L1b/L3/L4), an infrastructure-failure section, and deep dive into failure mechanisms. Triggers on "生成低分任务报告""根因共性分析报告""low score report". Reads low-score-analysis results and produces a well-structured markdown report with clear hierarchy and detailed code-level analysis.
---

# 低分任务根因共性分析报告生成 Skill（WildClawBench 版）

基于 `low-score-analysis` Skill 的输出，为一个 `(模型, harness)` 单元生成**格式规范、层次分明、根因深入**的根因共性分析报告（Markdown）。

## 核心特性

1. **四层归因框架**：L1a（底层推理）、L1b（长程执行）、L3（环境基础设施）、L4（评测系统）
2. **深度根因分析**：不止步于"抛出错误"，追溯到**具体代码/命令逻辑问题**
3. **主口径 + 环境失效专项**：低分主体是"模型真实表现不佳"的任务；**根本没跑起来**（额度耗尽、认证故障、workspace 缺失、协议不兼容导致 0 次有效执行）的任务单列专项——它们不反映模型能力，混入正文会把根因分布夸大成"能力差"
4. **层次化排版、通俗易懂**：序号、缩进、分点陈述，用事实说话；措辞须遵守下方「文风红线」

## 文风红线（与 eval-report Skill 同一套标准，最容易返工的一环）

报告要**通俗易懂、给结论、摆事实**。两个方向的坑都要避开：

1. **禁 AI 味**：不用"值得注意的是/总而言之/综上所述/深入剖析/赋能/抓手"等套话；不堆排比句；不滥用加粗（每段最多突出 1–2 处关键数字/结论）；不用 emoji；不写"首先/其次/再次/最后"式的机械展开。
2. **禁过度口语**：不用"干到一半就不干了/挡箭牌/两头夹击/救回/一枝独秀/戛然而止"等表达 → 改为"任务中途中止/不构成差距来源/双重叠加/回收/唯一领先/随即终止"。
3. **禁反问句和设问句**："为什么 X 能领先？因为…" → "X 领先的原因在于…"；"能不能排除环境因素？答案是…" → "结论为：…"。
4. **结论前置**：每章、每个根因类别的第一句就是判断，证据只做支撑；不铺垫、不卖关子。
5. **通俗**：专业术语首次出现给一句白话解释（如"落盘 = 把结果写入指定文件"、"L1b 长程执行 = 会做但没做完的执行链路问题"）。
6. 说明性文字统一用 `> **备注**`，不用"读法"。
7. 环境/判分问题必须与模型能力剥离表述，显式标注"非模型能力问题"。

正反例：
- ❌ "最扎眼的不是分数，是请求数……差距一目了然" → ✅ "请求数差异是本轮最突出的特征：X 106 次、Y 1665 次，相差逾十倍"
- ❌ "别拿 401 当挡箭牌" → ✅ "401 为各模型共担的环境因素，不解释模型间差距"

## 低分口径（重要）

- **主口径（正文主体）**：单轮 `overall_score < 60%` 且非环境失效。包含超时任务——超时可能是模型循环不收敛（能力问题），定性依据 LLM 分析结果。
- **环境/基础设施失效专项（独立章节）**：`usage.request_count == 0`（一次都没跑起来）或存在非超时的执行层错误。用 `report_utils.split_tasks_by_bucket()` 分桶。
- 双层错误信号：`error_execution`（执行层）/ `error_grading`（判分层），是分桶与定性的依据。

## 输入

### 必需输入

1. **评测结果 unit 目录**：如 `eval_out/all_suite/round1/gpt-5.5-pro/codex`
2. **低分任务清单**：`<result-root>/report-workspace/_failed_tasks_<model>@<harness>.json`
3. **根因分析结果**：`<result-root>/report-workspace/analysis_<model>@<harness>.json`

### 可选输入（元信息）

- 轮次标识（如 `round1`）、评测特殊配置（如 `"reasoning effort: none"`）、对比目标（明确指定才包含对比信息）

## 输出

**报告文件**：`<result-root>/低分任务根因分析报告_<model>@<harness>.md`

## 报告结构

### 标题与开头信息

用 `report_utils.generate_report_header()` 生成：标题 `# WildClawBench <unit> 低分任务根因分析报告`，含被测模型/harness、评测轮次（用 `extract_eval_metadata()` 从 summary_all_*.json 取 task_count/global_avg，`format_round_description()` 生成描述）、分析样本、数据来源、四层维度定义。

**术语**：所有 "provider" 统一写作"推理服务"。

### 一、执行摘要

- 全 0 分任务列表；各套件低分任务分布（`suite_avg_table()`）
- 一句话归因（四层分布）；核心结论（默认独立分析，不提其他轮次；用户明确要求对比时才写对比）

### 二、根因分类

- 2.1 根因 × 归属层主表（`classify_root_causes()` + `extract_layer_attribution()`）
- 2.2 四层归属汇总表
- （如适用）2.3 跨层根因说明

### 三、按根因分类详述（仅主口径低分任务）

每个根因类别（工具调用协议不兼容、超时或循环不收敛、产物未落盘、代码错误等）包含：

1. 主导归属层标注
2. 共性机制（分层说明）
3. 该类任务详表（`format_task_table()`）
4. **典型案例深析**（2-3 个）：必须包含深度根因分析（见下文）

### 四、环境/基础设施失效专项（独立章节）

针对 `split_tasks_by_bucket()` 分出的 infra 桶：

1. `format_infra_table()` 生成详表（得分、请求数、执行层错误摘要）
2. 说明共性机制（如 API 额度耗尽的连锁失败、认证 401、workspace 缺失），明确标注**非模型能力问题**
3. 与主口径的关系：这些任务不计入正文根因统计，单列于此避免把基础设施故障算成模型短板
4. 给出修复与重跑建议（哪些用例修复环境后必须重跑才可比）

### 五、跨任务关键发现

例如：某类检查点的系统性失分模式、判分脚本刚性/否定式检查漏洞（agent 没跑也得分）、跨套件的能力维度共性。

### 六、改进建议

按层归类（L1a、L1b、L3、L4），每层 3-5 条具体建议。

## 深度根因分析要求（核心）

对代码类失败（判分检查点为 0、命令报错、格式错误），必须：

1. 用 `report_utils.extract_code_executions(transcript)` 或直读 `chat_openclaw.jsonl`，找到 `type=tool_use`（name 如 `exec_command`）的执行记录
2. **提取失败的命令/代码片段**（`input` 字段）与对应 `tool_result` 报错
3. **分析具体错误原因**：键名错在哪、路径差在哪层目录、格式串少了什么字段、循环为何不收敛
4. **给出正确代码示例或修复方向**

❌ 浅层："脚本反复报 KeyError，最终超时" 
✅ 深度："脚本用 `datetime.strptime(parts[3], '%b %d')` 解析日期，但日志实际是 `'Fri Jun 10'`（多出星期字段），5 次修改格式串均未意识到需先去掉星期，同一错误点重复 5 次后 900 秒超时"

## 使用方式

```
生成 gpt-5.5-pro@codex 的低分任务根因分析报告
基于 eval_out/all_suite/round1
```

带上下文信息 / 对比模式同 PinchBench 版：默认独立分析；用户明确说"对比 xxx"才包含对比。

## 依赖

- `low-score-analysis` Skill 的输出（清单 + 分析 JSON）
- Python 3.9+（`scripts/report_utils.py`）

## 安装（软链接到 .claude/skills）

```bash
mkdir -p .claude/skills
ln -snf ../../tools/report/skills/low-score-report .claude/skills/low-score-report
```
