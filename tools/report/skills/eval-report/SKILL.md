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

- **`full`（完整模式，默认）**：含根因分析、典型案例与有效性检查，用于正式归档与对外发布。

**典型工作流**：
1. 评测完成 → 生成 **preview** 报告 → 相关方快速查看维度表现 → 决策是否需要补测/重跑；
2. 根因分析完成 → 生成 **full** 报告 → 补充典型案例与失分机制归纳 → 正式发布与归档。

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

## 报告范围与目录

### 单 round 正式报告

单 round 报告仍归属于该 round：根因分析、有效性、Excel 和审计放在 `<round>/report-workspace`，领导版 Markdown 放在 `<round>/`。已有调用保持兼容。

### 跨 round 多单元综合报告

跨 round 综合报告不归属于“最新 round”，必须放在所有来源 round 的共同父目录：

```text
<round共同父目录>/reports/cross-round/aggregate/<report-id>/
├── SOURCE_MAP.tsv
├── workspace/
│   ├── results/                 # 合并结果集，优先使用 unit 级相对软链
│   └── analysis/                # 本次报告实际消费的分析快照或引用
└── builds/
    └── <timestamp>_<preview|full>/
        ├── report_<N>units_<timestamp>.xlsx
        ├── report_<N>units_<timestamp>_leader_data.json
        ├── 评测报告_<目标模型>_<目标Harness>_<round范围>_<timestamp>.md
        ├── report_<N>units_<timestamp>.analysis_quality.json
        ├── validity/
        └── audit/
```

- `SOURCE_MAP.tsv` 必须记录每个别名 unit 对应的原始结果目录；Harness 新旧版本必须使用可区分的实体 ID。
- Preview 和 full 各自使用独立 build 目录，不覆盖历史文件。
- Excel、leader data 和领导版 Markdown 必须放在同一个 build 目录，不再复制到某个 round 根目录。
- `round1-round2` 等范围进入报告名和元数据；不得把跨 round 报告简称为 `round2`。
- 原始根因分析仍归属于来源 round。跨 round 工作区只保存本次消费的快照或引用，并记录来源与质量状态。

### 同一单元跨轮趋势

同一 `<model>@<harness>` 的轮次趋势使用 `generate_round_compare_report.py`，默认输出到：

```text
<round共同父目录>/reports/cross-round/trend/<unit>__<round范围>/builds/<timestamp>/
```

逐用例跨模型/Harness 的证据分析属于 `cross-eval-analysis`，不要混入综合报告工作区；其跨 round 输出统一放在 `reports/cross-round/cross-eval/`。

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
- 外部大模型 API、模型专属视觉端点认证/流控/网络故障归 L3；评测 Runner、容器生命周期、框架创建/挂载 Workspace、框架异常杀进程或 Grader 故障归 L4；Harness 工具协议、会话截断或 Harness 自身产物回收异常归 L2。统一任务 deadline 到期且模型未完成归 L1b，不因 Runner/容器最终结束进程而改变归因；模型调用请求体/响应体中未提供的工具归 L1b，Harness 兜底只作为改进方向。

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

分析时先读任务 Markdown 的判分代码，再读完整 `chat_openclaw.jsonl`；如果是 AstronCode 且存在 `agent_interaction.jsonl`，必须再读该 Harness↔模型原始请求/响应轨迹，尤其核对请求体中的工具清单和响应体中的实际工具调用。输出必须包含 `task_id`、`result_analysis`、`root_cause_analysis`、`attribution_layer`、`attribution_confidence` 和 `attribution_evidence`，并标记 L1a（模型基础推理能力）/ L1b（模型 Agent 能力）/ L2（Harness 运行与工具编排）/ L3（评测环境与推理服务基础设施）/ L4（评测系统、任务与 Grader）中的主导层。`uncertain` 是待确认状态，不是第六层，也不参与五层统计；满分成功对照使用 `none`。任何归因都必须给证据；`unsupported call` 不能单独证明 Harness 未暴露工具。证据不足时使用 `uncertain`/`unconfirmed`，明确缺少什么证据、无法区分模型与 Harness。`confirmed` 需排除主要替代解释，`probable` 允许一个未闭环因素，`unconfirmed` 表示关键证据缺失。合并后执行 `validate_analysis.py`：部分覆盖是合法的 `partial/REVIEW`，Excel 和领导版报告仍可生成并回填已分析用例；未分析用例的分析列必须保持空白，不能解释为“无失分”或“未发现问题”。越界任务、空字段、归因字段矛盾或来源快照变化为 `FAIL`，禁止正式发布。

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
- 存在 `web-site-gen` 任务时（无论是 `source_semantic` 还是 `browser_runtime+visual_llm` 证据），`站点评测指标` 的“结果与效率指标汇总”区域使用“结果指标 / 分层分析 / 效率指标”双层合并表头，每个模型与 Harness 组合一行；正式表只展示得分率、严格满分率、L1/L2、三个一级能力维度、耗时平均/P50/P90、平均成本以及平均总/输入/输出 Token 的纯数值，不展示美观度、样本数和计算方法；
- `_站点评测指标口径` 为隐藏 Sheet，按模型与 Harness 组合、指标保存分类、单位、样本数和计算方法；无 Web 指标时不生成这两个 Sheet；
- 五个维度 Sheet 下方有”固定目标 Harness：模型对比”和”固定目标模型：Harness 对比”两张连续、带配色、可直接复制的表；被固定的一侧只有 1 个参评对象时该表不生成（无参照，对比不成立），脚本会打印”仅 1 个参评对象”提示，属预期行为；
- 评分详情仍使用 raw unit 命名，analysis 回填条数与 JSON 一致（preview 模式下为 0）；生成 Excel 时同时产出 `*.analysis_quality.json`，记录每个 unit 的 `complete/partial` 覆盖状态和质量结论。

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

存在 Web 指标时，提取器从正式横表读取数值，从隐藏 `_站点评测指标口径` 读取分类、样本数和计算方法；提取结果的 `website_metrics` 按展示名 unit 和指标名组织，领导版 Markdown 增加“站点评测指标”章节并逐项使用该字段。无 Web 指标时整节省略。

## 4. 领导版 Markdown

**Preview 模式章节顺序**：

1. 总览；
2. 二、分类维度；
3. 三、Agent能力；
4. 四、难度等级；
5. 五、模态对比；
6. ~~六、典型低分案例~~（跳过）；
7. 总结（仅基于维度分差归纳结论，不含案例证据）。

**Full 模式章节顺序**（包含典型案例）：

1. 总览；
2. 二、分类维度；
3. 三、Agent能力；
4. 四、难度等级；
5. 五、模态对比；
6. 六、典型低分案例；
7. 总结。

### 总览

总览保留全部列，列名、顺序和值与 Excel `总览` 完全一致，不删减 tokens、请求数、耗时、成本或可选工具指标。目标组合先给定位，再说明最关键的效果、可靠性或效率信号。

### 维度表规则

分类、Agent能力、难度和模态不展示同时改变模型与 Harness 的全量混合矩阵。

**两侧都适用时**（多模型 × 多 Harness），每个维度按以下顺序：

1. 维度总判断；
2. 固定目标 Harness 的模型侧总结；
3. `model_view` 表；
4. 固定目标模型的 Harness 侧总结；
5. `harness_view` 表；
6. 必要的口径备注。

此处的「维度总判断」是罩在两个子章节之上的一句总纲，作用是在拆成模型侧、Harness 侧之前先给该维度的整体结论。**只有一侧适用时没有需要统领的子章节，这一句不写**（详见下方适用条件）。

**控制变量视图的适用条件（先判断，再决定写不写）**：

控制变量对比要求被固定的那一侧至少有 2 个参评对象，否则没有参照、对比不成立。按 `leader_data.json` 的 `scope` 判断：

| 参评范围 | `model_view`（固定 Harness 比模型） | `harness_view`（固定模型比 Harness） |
|---|---|---|
| 多模型 × 多 Harness | 写 | 写 |
| 多模型 × **单 Harness** | 写 | **整节省略** |
| **单模型** × 多 Harness | **整节省略** | 写 |
| 单模型 × 单 Harness | 整节省略 | 整节省略 |

省略时**不写** `### 固定 X：Y 对比` 这一级小标题，也不写该侧的总结文字与空表——不是留空标题，是整节不出现。Excel 侧同样不会生成该表（会打印"仅 1 个参评对象"提示），`leader_data` 中对应的 `*_view` 为空数组、`*_view_applicable` 为 `false`、`*_view_title` 为 `null`。

**只有一侧适用时**，该维度章节是「**一段**总结 → 唯一那张表 → 必要的口径备注」，不写维度总判断那一句。

这一段合并了原先的「维度总判断」与「该侧总结」两者的职能：仍是最多 2 句、不超过 3 个关键数字，第一句给结论，第二句写差距集中位置或必要边界。它直接陈述该侧结论，不需要交代另一侧为何缺失。

**禁止把同一判断拆成不带数字的一段加带数字的一段**——这是同义重复，不是两个层级。反例：

> ~~GLM-5.1 分类维度整体居中游，生产力工作流最强、安全对齐最弱。~~
>
> ~~生产力工作流 87.5 分为内部最高，安全对齐 70.9 分为最低；搜索检索、创意合成、安全对齐三项均低于总平均分，其中安全对齐与 GPT-5.5 差距 16.1 分。~~

正确写法（一段，判断与数字合在一起）：

> GLM-5.1 分类维度整体居中游：生产力工作流 87.5 为内部最高，安全对齐 70.9 最低且与 GPT-5.5 差距 16.1 分。搜索检索、创意合成、安全对齐三项均低于其总平均分。

若参评范围本身就是单 Harness 或单模型，在报告开头的参评范围说明里写清即可（如"参评范围：4 个模型 × 1 个 Harness"），不必在每个维度章节重复解释。

**重要**：
- **总结必须放在对应表格之前**，不能放在表格之后。两侧都适用时格式为 `### 固定 X：Y 对比` → 总结文字 → 表格；只有一侧适用时不写这级小标题，`## 维度章节` 标题下直接是总结文字 → 表格。
- 每张表上方的总结最多 2 句话，合计不超过 3 个关键数字。第一句先写已有基础、接近项或相对优势，再写差距集中位置；第二句给必要边界。
- 每个维度章节里，同一侧的结论只出现一次。表格上方是唯一的文字段落，不在其他位置复述同一判断。

固定目标 Harness 时（`model_view` 适用），先说明已有优势、接近项或相对稳定项，再指出差距集中的场景或能力和模型侧优先提升方向。必须区分”目标模型内部最高项”和”相对参照模型已具竞争力的强项”，不能把内部最高项直接写成对外优势。参评只有 1 个模型时本段不适用。

固定目标模型时（`harness_view` 适用），先说明不同 Harness 表现接近的维度，再指出对 Harness 选择较敏感的维度与分差。只有 transcript 或根因分析有直接证据时才能把分差写成确定归因；仅凭分差相关性时只陈述相关性（如"该维度对 Harness 选择较敏感"），不写成已确认原因，也不给排查方向。参评只有 1 个 Harness 时本段不适用。

Agent 原始 7 维必须进入报告。去污染 3 维只有在会改变强弱判断或改进优先级时才展示，并紧邻对应 Agent 控制变量表说明变化。

### 结论长度与证据

**评测的职责是给结论、摆事实，不是指导别人怎么改。** 报告只回答"表现如何、差距在哪、和什么因素相关"，不回答"应该补充什么能力、应该排查哪条链路"——具体如何优化、由谁优化是模型侧与 Harness 侧团队的职责，评测不越界指导。

每张控制变量表上方的总结最多 2 句话，合计不超过 3 个关键数字。第一句写强弱格局（哪些项领先/持平/垫底）；第二句写差距集中位置与可观察的关联事实（如"创意合成多为多模态生成任务，与该模型多模态短板一致"）。

数字用于支撑判断，不承担整段叙述。优先使用分差、区间或"除主要差异项外，其余维度分差均在某一区间"等概括，不逐项播报谁高谁低。能用 0–2 个关键数字说清时，不使用第 3 个数字。

- 分类与难度优先写样本量大、分差大、影响总分的项目。
- 可以指出"某项是该 Harness 三者中最低""某项与另一维度短板一致"这类事实与关联；不写"应补充某种能力""应排查某条链路"。
- 不逐项复述表格，不用无证据因果。

**允许的表述**（摆事实、给结论）：

- "GLM-5.1 在搜索检索（72.7）、安全对齐（80.0）两个场景反超更高版本的 GLM-5.2，社交互动基本持平；差距集中在创意合成（43.1 vs 73.5，低 30.4 分）与代码智能（63.0 vs 80.1，低 17.1 分）。"
- "AstronCode 的创意合成（43.1）是三者中最低。"
- "创意合成多为多模态生成任务，与该模型多模态短板一致。"
- "该差距对 Harness 选择较敏感。"

**禁止的表述**（越界指导优化）：

- ~~"模型侧可优先补充图文排版类产物的结构完整性与要素自检。"~~
- ~~"Harness 侧可优先排查产物写入链路与大体积内容的工具参数传递。"~~
- ~~"模型侧可优先补充代码调试中的根因定位能力，避免以掩盖症状的改动替代真实修复。"~~
- ~~"建议引入产物优先落盘与边际收益止损策略。"~~

### 典型低分案例（仅 full 模式）

选 5–6 个证据完整、机制不重复的 L1a、L1b 或 L2 案例。案例必须包含任务、得分、实际执行证据、失分机制、责任归属和可执行改进。默认不选 L3/L4；L2 必须有已声明工具契约、Harness 日志或调度结果证据，模型调用未提供工具的案例归 L1b。

**案例格式**：标题必须带序号，格式为 `### 案例N：<机制概括>（<task_id>，<得分>）`，例如 `### 案例1：代码调试误诊，掩盖症状而非修复根因（02_Code_Intelligence_task_2_sam3_debug，0 分）`。序号从 1 连续递增，便于正文与会上引用。每个案例用表格展示项目与内容：

| 项目 | 内容 |
|---|---|
| 任务 | 简要描述 |
| 执行证据 | transcript 中的关键行为（含关键行号、命令或报错原文） |
| 失分机制 | 判分为何归零或扣分（对应到具体检查点） |
| 责任归属 | L1a 模型基础推理能力 / L1b 模型 Agent 能力 / L2 Harness 运行与工具编排 |

案例只陈述"做了什么、为何失分、责任在哪"，不写"改进方向"或"复测指标"——如何修复由责任方决定。

若有效性门禁要求披露 L3/L4，在典型案例之前增加独立的”评测有效性与剔除说明”，只写影响范围、处置与是否计入统计。

**Preview 模式跳过本节**。

### 文风

- 结论前置，通俗、短句、陈述句。
- 能力结论优先使用"已有一定基础""与参照对象处于同一水平区间""整体较为接近""差距主要集中在""仍处于追赶阶段""对 Harness 选择较敏感""是三者中最低"。
- 避免使用"排名末位""全面落后""均未达到""整体偏弱""明显落后""短板覆盖全部场景""不具竞争力"等硬评价。
- 有效性门禁、已确认故障和发布阻断保持准确、直接，不因语气要求弱化事实。
- 禁用"持续优化""进一步提升""全面加强""值得注意的是""综上所述"等空话。
- **禁用越界指导优化的表述**："可优先补充/补齐某能力""可优先排查某链路""建议引入某策略""应加强某环节"。评测只给结论与事实，不指导责任方如何修复。
- 禁用反问、排比、夸张比喻和无依据判断。
- 每条结论必须对应表格分差或案例证据，并明确责任归属（模型能力 / Harness）。

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

以上是单 round 产物。跨 round 产物使用“报告范围与目录”中的中立 `reports/cross-round/` 结构，禁止落到最后一个 round 的 `report-workspace` 或 round 根目录。
