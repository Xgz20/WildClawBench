---
name: low-score-report
description: Generate a comprehensive root-cause report for WildClawBench low-score tasks, with five-layer attribution analysis (L1a/L1b/L2/L3/L4) plus an uncertain status, an infrastructure-failure section, and deep dive into failure mechanisms. Triggers on "生成低分任务报告""根因共性分析报告""low score report". Reads low-score-analysis results and produces a well-structured markdown report with clear hierarchy and detailed code-level analysis.
---

# 低分任务根因共性分析报告生成 Skill（WildClawBench 版）

基于 `low-score-analysis` Skill 的输出，为一个 `(模型, harness)` 单元生成**格式规范、层次分明、根因深入**的根因共性分析报告（Markdown）。

## 核心特性

1. **五层归因框架 + 待确认状态**：L1a（模型基础推理能力）、L1b（模型 Agent 能力）、L2（Harness 运行与工具编排）、L3（评测环境与推理服务基础设施）、L4（评测系统、任务与 Grader）；`uncertain` 仅表示证据不足待确认，不是第六层
2. **深度根因分析**：不止步于"抛出错误"，追溯到**具体代码/命令逻辑问题**
3. **主口径 + 执行失效专项**：低分主体是"模型真实表现不佳"的任务；**根本没跑起来**（外部服务故障、流控、网络问题或评测框架初始化失败）的任务单列专项——它们不反映模型能力，混入正文会把根因分布夸大成"能力差"
4. **层次化排版、通俗易懂**：序号、缩进、分点陈述，用事实说话；措辞须遵守下方「文风红线」

## 文风红线（与 eval-report Skill 同一套标准，最容易返工的一环）

报告要**通俗易懂、给结论、摆事实**。两个方向的坑都要避开：

1. **禁 AI 味**：不用"值得注意的是/总而言之/综上所述/深入剖析/赋能/抓手"等套话；不堆排比句；不滥用加粗（每段最多突出 1–2 处关键数字/结论）；不用 emoji；不写"首先/其次/再次/最后"式的机械展开。
2. **禁过度口语**：不用"干到一半就不干了/挡箭牌/两头夹击/救回/一枝独秀/戛然而止"等表达 → 改为"任务中途中止/不构成差距来源/双重叠加/回收/唯一领先/随即终止"。
3. **禁反问句和设问句**："为什么 X 能领先？因为…" → "X 领先的原因在于…"；"能不能排除环境因素？答案是…" → "结论为：…"。
4. **结论前置**：每章、每个根因类别的第一句就是判断，证据只做支撑；不铺垫、不卖关子。
5. **通俗**：专业术语首次出现给一句白话解释（如"落盘 = 把结果写入指定文件"、"L1b 模型 Agent 能力 = 模型能否规划并完成多步任务"、"L2 Harness = 工具和会话是否被正确编排"）。
6. 说明性文字统一用 `> **备注**`，不用"读法"。
7. 环境/判分问题必须与模型能力剥离表述，显式标注"非模型能力问题"。

正反例：
- ❌ "最扎眼的不是分数，是请求数……差距一目了然" → ✅ "请求数差异是本轮最突出的特征：X 106 次、Y 1665 次，相差逾十倍"
- ❌ "别拿 401 当挡箭牌" → ✅ "401 为各模型共担的环境因素，不解释模型间差距"

## 低分口径（重要）

- **主口径（正文主体）**：单轮 `overall_score < 60%` 且非环境失效。包含超时任务——超时可能是模型循环不收敛（能力问题），定性依据 LLM 分析结果。
- **执行失效专项（独立章节）**：`usage.request_count == 0`（一次都没跑起来）或存在非超时的执行层错误。用 `report_utils.split_tasks_by_bucket()` 分桶；该分桶可能同时包含 L3 外部服务故障和 L4 评测框架故障，不等于 L3。
- 双层错误信号：`error_execution`（执行层）/ `error_grading`（判分层），是分桶与定性的依据。

## 输入

### 必需输入

1. **评测结果 unit 目录**：如 `eval_out/all_suite/round1/gpt-5.5-pro/codex`
2. **低分任务清单**：`<round>/report-workspace/_failed_tasks_<model>@<harness>__<scope>.json`
3. **根因分析结果**：`<round>/report-workspace/analysis_<model>@<harness>__<scope>.json`

manifest 与 analysis 必须使用同一个 scope。默认报告口径使用 `lt60`；可按用户要求使用 `lt80`、`gte60_lt80` 或 `imperfect`，并从 manifest 的 `selection_label` 在报告头准确说明范围。`all` 含满分成功对照，不得直接用于低分根因分布；如需全量对照报告，应明确拆分 `analysis_type=success_control` 后另设对照章节。

生成报告前必须执行 `low-score-analysis/scripts/validate_analysis.py`。分析只覆盖 manifest 子集时，允许生成增量报告，但报告头必须标注 `partial` 覆盖状态和“已分析 X/Y 个任务”；根因分类、五层分布和典型案例只能使用已分析任务，未分析任务不能计入任何根因统计，也不能写成“未发现问题”。校验为 `FAIL` 时禁止生成正式报告；`REVIEW` 可生成内部/增量报告。

### 可选输入（元信息）

- 轮次标识（如 `round1`）、评测特殊配置（如 `"reasoning effort: none"`）、对比目标（明确指定才包含对比信息）

## 输出

**报告文件**：`<result-root>/低分任务根因分析报告_<model>@<harness>.md`

## 报告结构

### 标题与开头信息

用 `report_utils.generate_report_header(..., selection_label=<manifest中的范围说明>)` 生成：标题 `# WildClawBench <unit> 低分任务根因分析报告`，含被测模型/harness、评测轮次（用 `extract_eval_metadata()` 从 summary_all_*.json 取 task_count/global_avg，`format_round_description()` 生成描述）、分析样本、数据来源、五层维度定义。

**术语**：所有 "provider" 统一写作"推理服务"。

### 一、执行摘要

- 全 0 分任务列表；各套件低分任务分布（`suite_avg_table()`）
- 一句话归因（五层分布）；核心结论（默认独立分析，不提其他轮次；用户明确要求对比时才写对比）

### 二、根因分类

- 2.1 根因 × 归属层主表（`classify_root_causes()` + `extract_layer_attribution()`）
- 2.2 五层归属汇总表
- （如适用）2.3 跨层根因说明

### 三、按根因分类详述（仅主口径低分任务）

每个根因类别（工具调用协议不兼容、超时或循环不收敛、产物未落盘、代码错误等）包含：

1. 主导归属层标注
2. 归因置信度和明确证据（来源、关键原文/事实、支持该层的理由）
3. 共性机制（分层说明）
4. 该类任务详表（`format_task_table()`）
5. **典型案例深析**（2-3 个）：必须包含深度根因分析（见下文）

### 归因证据强制规则

- 任何 L1a/L1b/L2/L3/L4 归因都必须给出证据，不能只根据错误字符串、得分或经验判断。
- `unsupported call` 只能证明某次调用没有成功，不能单独证明 Harness 没有暴露工具。必须继续核对模型请求体/响应体中的工具清单、Harness 工具契约、工具注册/调度日志和工具结果回传记录。
- L1a 至少引用模型输出/执行轨迹与对应检查点；L1b 至少引用模型的工具选择、规划、重复执行或交付行为，并核对当时可用工具；L2 至少同时有已声明工具契约和 Harness 注册、调度、回传或会话控制证据；L3 使用结构化环境/推理服务错误或共享基础设施证据；L4 使用任务判分代码、Grader 日志或可复现的判分差异证据。
- 关键证据缺失时，不强行归因：`attribution_layer=uncertain`、`attribution_confidence=unconfirmed`，并明确写出“缺少什么证据，无法区分具体是模型问题还是 Harness 问题”。

### 五层边界与待确认状态

`attribution_layer` 的正式层级只有 L1a、L1b、L2、L3、L4；`uncertain` 是“待确认”状态，不是第六层，不参与五层归因统计。`none` 只用于满分成功对照。主导层只记录主要责任方，协同因素放在根因和证据中，避免把 Harness 兜底建议误写成 Harness 根因。

| 边界场景 | 推荐归因 | 判定要求 |
|---|---|---|
| 模型调用了可用工具清单中没有的 `bash`、`read` 等工具 | `L1b` | 必须有请求体/响应体中的工具清单和模型调用证据；Harness 增加拒绝或替代工具仅是改进建议 |
| 只有 `unsupported call`，看不到工具清单或 Harness 契约 | `uncertain` | 只能确认调用失败；明确写缺少哪些证据，不能直接判为模型或 Harness |
| 工具已声明可用，但 Harness 未注册、映射、调度或回传 | `L2` | 必须同时有工具契约和 Harness 运行日志/调度结果 |
| 工具正常执行，但模型工具选择、规划、验证或交付错误 | `L1b` | 用完整 transcript、工具结果和产物检查点证明 |
| 单步理解、代码逻辑或内容生成错误 | `L1a` | 用模型输出、执行结果和对应检查点证明 |
| 外部大模型服务调不通、认证失败、流控/限流、网络不通或模型专属视觉服务故障 | `L3` | 有 API/服务错误、限流响应、网络诊断、端点和影响范围证据；标注“非模型能力问题” |
| 评测 Runner、容器生命周期、框架创建/挂载 Workspace、框架控制的进程终止、任务定义、判分代码或 Grader 导致执行/得分失真 | `L4` | 有 Runner/容器/Workspace 生命周期日志、timeout 配置、任务/评分代码或 Grader 证据 |
| Harness 会话、工具调度或 Harness 自身产物回收失败 | `L2` | 有 Harness 契约、会话/调度/回收日志；不能只凭最终文件缺失判断 |
| 统一任务 deadline 到期且模型未完成 | `L1b` | transcript 显示循环、反复报错、未验证或未交付；Runner 最终结束进程只是执行机制，不改变归因 |
| 超时但无法确认终止方或执行机会 | `uncertain` | 缺少 transcript、Runner/Harness 终止事件或外部服务证据时不强行归层 |

归因置信度统一为：`confirmed` 需有直接证据且排除主要替代解释；`probable` 允许保留一个未闭环因素，但现有证据已支持当前判断；`unconfirmed` 表示关键证据缺失，不能可靠归因。`unconfirmed` 通常与 `uncertain` 配套，不能据此输出模型侧或 Harness 侧能力结论。

### 归因分层的使用范围

建议保留五层归因，但只作为内部诊断、有效性治理和改进建议的依据。它的价值是把模型能力、Harness 执行、外部服务和评测框架问题分开；副作用是日志不完整时会制造过度确定的责任判断。因此报告必须保留证据和置信度，缺证据就使用 `uncertain/unconfirmed`，不继续扩展更多层，也不把 L3/L4 写入模型或 Harness 能力结论。

### 四、执行失效专项（独立章节）

针对 `split_tasks_by_bucket()` 分出的执行失效专项（代码变量仍称 `infra`）：

1. `format_infra_table()` 生成详表（得分、请求数、执行层错误摘要）
2. 说明共性机制（如外部 API 额度耗尽、认证 401、网络不通、Runner 创建 Workspace 失败或容器生命周期异常），明确标注**非模型能力问题**，并继续区分 L3 外部服务与 L4 评测框架
3. 与主口径的关系：这些任务不计入正文根因统计，单列于此避免把基础设施故障算成模型短板
4. 给出修复与重跑建议（哪些用例修复环境后必须重跑才可比）

### 五、跨任务关键发现

例如：某类检查点的系统性失分模式、判分脚本刚性/否定式检查漏洞（agent 没跑也得分）、跨套件的能力维度共性。

### 六、改进建议

按层归类（L1a、L1b、L2、L3、L4），每层 3-5 条具体建议。L2 只收 Harness 自身的工具暴露、协议适配、调度、会话状态、重试/超时控制和产物回收问题；模型未规划好或未完成多步任务仍归 L1b。

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
