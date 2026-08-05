# WildClawBench 报告三件套设计文档

> 状态：已评审通过（2026-07-15）
> 参考实现：PinchBench（astronclaw-eval/eval-framework 的 low-score-analysis / low-score-report Skill 与 generate_eval_report.py）

## 1. 背景与目标

WildClawBench 评测完成后，需要与 PinchBench 同等级的三类产出能力：

1. **低分任务根因分析**（LLM 结合判分明细 + transcript 找失分证据）
2. **低分任务根因分析报告**（Markdown，四层归因 + 深度代码级分析）
3. **评测报告 Excel**（多单元对比 + 用例详情 + 根因回填）

移植策略为**原生适配重写**：按 WildClawBench 的结果结构重写数据加载层，复用 PinchBench 的分析流程设计（Workflow 分批并发、断点续传）与报告框架（四层归因）。

## 2. WildClawBench 评测结果结构（数据源）

```
eval_out/all_suite/round1/<model>/<harness>/          ← 模型×Harness 多对多
  run.log
  summary_all_<provider>_<model>.json                 ← global_avg + results[]
  <suite>/                                            ← 01_Productivity_Flow ... 06_Safety_Alignment
    summary_<provider>_<model>.json                   ← 套件级 results[]（数组）
    <suite>_task_N_<名称>/                             ← 规范 task_id 即此目录名
      <model>_<YYYYMMDD>_<HHMM>_<hash>/               ← 运行目录（可能多个，取最新）
        score.json            ← {检查点: 0~1, ..., overall_score}（或含 error）
        execution_status.json ← status/timed_out/error/elapsed_time
        usage.json            ← tokens/cost/request_count/elapsed_time
        agent.log
        chat_openclaw.jsonl   ← 规范化 transcript（message.content[]: text/tool_use/tool_result）
        chat.jsonl            ← harness 原生日志（codex 事件流）
        codex_sessions/       ← harness 原生会话
```

与 PinchBench 的关键差异：

| 维度 | PinchBench | WildClawBench |
|---|---|---|
| 数据组织 | 每模型一个大 JSON（`tasks[].grading.runs[]`） | 目录层级 + 每任务 score.json |
| 轮次 | 每任务 3 轮（有均分/极差） | 单轮（round 是顶层目录维度） |
| 分析单元 | 模型 | (模型, harness) 二元组，记 `model@harness` |
| 判词 | `grading.runs[].notes` 裁判判词 | 无 notes；判分代码在任务 .md 内，失分点=检查点<1.0 |
| 错误信号 | transcript error 事件 | 双层：`execution_status.error`（执行层）+ `score.json.error`（判分层） |
| 任务元数据 | tasks/*.md + cn/ 双语 + 场景/能力映射 | tasks/<套件>/<task_id>.md 或 tasks/extension/<套件>/<task_id>.md（frontmatter: id/name/category/difficulty/modality/timeout_seconds/grading_type + `## Prompt` + 判分代码） |

**数据源策略**：以目录扫描为主数据源（score.json 等四件 + transcript），`summary_all_*.json` 仅用于校验 global_avg 与元信息。原因：summary 里 task_id 带时间戳后缀（`01_task_10_gpt-5.5-pro_20260713_2140_094b6c`），解析脆弱；目录名才是规范 task_id，且能直接对应任务定义文件。

## 3. 三件套设计

### 3.1 low-score-analysis Skill（`skills/low-score-analysis/`）

**筛选口径**（相对 PinchBench 的变化）：单轮无极差，「高波动专项」通道取消：

- 阈值/区间：按未四舍五入的原始 `overall_score` 选择 `<N` 或 `[min, max)`（默认 `<60`）
- 未满分/全量：`--imperfect` 选择所有未满分与无有效分数任务；`--all` 加入满分成功对照
- 指定任务 `specified`：`--task-id` 或 `--task-path`（可重复、支持 `@file.txt`），不限分数
- 每次选择生成稳定 scope（如 `lt60`、`gte60_lt80`、`all`），用于隔离增量产物
- 每条记录附加双层错误信号：`error_execution` / `error_grading` / `timed_out` / `status`，供下游区分「模型能力问题」与「环境/基础设施失效」

**manifest 条目**：`task_id`、`suite`、`model`、`harness`、`unit`、`overall_score`、`score_pct`、`analysis_type`、`selection_scope`、`selection_label`、`checkpoints`、`failed_checkpoints`、错误/用量字段及 task/run/transcript 路径。

**分析流程**：manifest → `simplify_task` 精简 → 分批（≤10/批）调用 Workflow → 每任务返回 `{task_id, analysis_type, result_analysis, root_cause_analysis}` → 按 unit + scope 保存/合并为 `analysis_<unit>__<scope>.json`。满分任务输出成功路径对照，`root_cause_analysis` 明确“无失分根因”。

**分析 prompt 适配要点**：
1. 读 `task_file`（.md 内含判分代码，等价于 PinchBench 的"判决书"）
2. 逐个失分检查点到 `chat_openclaw.jsonl` 找证据（工具名如 `exec_command`）
3. 单轮语义；双层 error 优先判断（执行层错误 → 标注"非模型能力问题"）；`agent.log` 作补充
4. 根因分类清单（WildClawBench 版 10 类）：工具调用协议不兼容、超时/循环不收敛、API 额度/认证故障、视觉通道失效、产物未落盘、代码错误、幻觉/编造、任务理解偏离、判分脚本刚性/评测系统问题、能力短板

### 3.2 low-score-report Skill（`skills/low-score-report/`）

标题：`# WildClawBench <model>@<harness> 低分任务根因分析报告`。结构沿用 PinchBench 框架，两处适配：

- 「高波动/稳定性专项」→「**环境/基础设施失效专项**」：分桶规则（`split_tasks_by_bucket`）：
  - `infra`：`usage.request_count == 0`（一次都没跑起来），或 `error_execution` 非空且非超时（超时保留在主口径，因为超时可能是模型收敛问题，由 LLM 分析定性）
  - `low`：其余主口径低分任务
- 四层归因保留：L1a（底层推理）/ L1b（长程执行）/ L3（环境基础设施）/ L4（评测系统）
- 深度根因分析要求保留：必须从 transcript 提取失败的 `exec_command` 代码片段，分析到具体代码逻辑，给修复方向

### 3.3 generate_eval_report.py（`scripts/`）

**对比单元**：`model@harness` 扁平单元（方案 A）+「模型×Harness 矩阵」轻量 Sheet。

**CLI**：`--result-root <round目录|unit目录>`、`--models`、`--harnesses`、`--analysis [UNIT=]PATH`（可重复）、`-o/--output-dir`（默认 `<round>/report-workspace/output`）、`--tasks-dir`（默认从脚本位置向上推导 `<repo>/tasks`）。

**Sheet 布局**（7 + N）：

| # | Sheet | 内容 |
|---|---|---|
| 1 | 总览 | 每 unit 一行：模型 \| Harness \| 总平均分 \| 用例数 \| 执行错误数 \| 超时数 \| 各分类均分（中文分类名） \| 总tokens \| 请求数 \| 总耗时 \| 成本 |
| 2 | 模型×Harness矩阵 | 行=模型，列=harness，格=总均分 |
| 3 | 用例对比明细 | 分类（中文） \| 用例ID \| 名称 \| 难度 \| 模态 \| Prompt \| 预期行为 \| 评分标准 \| 检查点（定义驱动：从任务 md 判分代码提取、保持定义序，动态键名由实测键补全；文本型键如 judge_reason 排除） \| 每 unit 一列「总分 + 检查点得分明细」（富文本，检查点按得分着色：满分绿 / 部分黄 / 零分红，语义同能力 Sheet 色阶；单分制任务只显示总分） \| 最优 \| 最大分差 |
| 3.5 | Agent能力对比 | 行=unit：总平均分 \| 7 维能力得分 \| 3 列去落盘污染口径 \| 模型强项/短板（Top3/Bottom3，涉及用例数以单元格批注标注） |
| 4 | 分类对比 | 行=分类（中文名），列=各 unit 均分 + 最佳 + 分差 |
| 5 | 难度对比 | 转置布局：行=unit（按总平均分降序），第 2 列=总平均分，列=难度等级（表头带用例数，如 `L2 平均分(19例)`） |
| 6 | 模态对比 | 转置布局，同难度对比（列=pure-text/multimodal） |
| 7 | 分差矩阵 | unit×unit 总分差值 |
| 8+ | 评分详情_\<unit\> | 分类 \| 用例ID \| 用例名称 \| 难度 \| 超时时间(秒) \| 模态 \| 输入(Prompt) \| 预期行为 \| 评分标准 \| Automated Checks \| 工作目录(Workspace) \| 预置技能(Skills) \| 环境变量(Env) \| 预热(Warmup) \| 状态 \| 总得分 \| 检查点得分明细 \| 失分点 \| 裁判判词 \| 执行错误 \| 总tokens \| 请求数 \| 耗时 \| 执行记录(jsonl，原文超 32000 字符截断) \| 结果分析 \| 根因分析 |

任务元数据同时扫描 `tasks/<套件>/` 与 `tasks/extension/<套件>/`。官方任务展示以中文版 `tasks/cn/<套件>/<task_id>.md` 为准（name/prompt/expected/criteria/checks 等），缺失字段回退英文版 `tasks/`；中文分类名取中文 md frontmatter 的 `category`（如 `01_生产力工作流`）。

**Agent能力对比（7 维）**：依赖 `tools/report/data/checkpoint_capability_map7.yaml`（{task_id: {checkpoint: [维度]}}，LLM 逐任务阅读判分代码标注、与实测检查点全集校验后生成）。7 维与 PinchBench cap7 对齐：代码生成/工具调用/数据处理/检索验证/推理规划/内容生成/验证交付。聚合口径：检查点值归一（`normalize_ckpt_value`：0~1 直取；`X_earned/X_max` 对按比值；`*_max/*_calls/*_attempts` 等诊断计量键排除）→ 任务内映射检查点均值 → 跨任务均值。单分制任务（04 套件、02_task_6、02 拼图）映射键为 `overall_score`。去落盘污染列：仅统计落盘类检查点（exist/created/... 命名）均值 ≥0.5 的用例。映射文件在新增/修改任务后需同步维护，脚本对未映射的实测检查点打覆盖率告警。

**裁判判词列**：从 score.json 递归提取所有裁判判词类字段——键名含 `reason`（覆盖 04 `judge_reason`、02 `image/desc_judge_reason`、03 `llm_judge_reasoning` 与嵌套 `llm_judge.reasoning`/`llm_items.*.reason`、06 `recognized_*_reason`），另以 ⚠ 标注裁判异常（`*_judge_error`/`llm_error`）。已知上游缺口：05 套件与 02 homepage 任务的判分代码只存裁判分数、不存判词文本，如需判词须改任务 md 的判分代码。

**得分口径**：聚合类 Sheet（总览/矩阵/分类/难度/模态/分差）统一为**百分制数值 + Excel 数字格式 `0.0"%"`**（单元格存数值，显示带 %，排序/色阶/筛选均正常；分差矩阵用带符号格式 `+0.0"%"`）；用例级（用例对比明细、评分详情的总得分与检查点）保持 **0~1 原始分**，与 score.json 直接对照。

**排序规则**：unit 全局按总平均分降序——决定总览行序及分类对比/用例对比明细的 unit 列序（最高分在最前）；模型×Harness 矩阵行按模型最高总均分降序、列按 harness 均分降序；难度/模态对比行按总平均分降序；分类对比与用例对比明细的行序保持固定（按分类/用例编号）。

不移植 PinchBench 的场景（S1~S8）与 7 维能力 Sheet（WildClawBench 无对应元数据体系）。样式复用：蓝底白字表头、冻结窗格、自动筛选、色阶、wrap_text、单元格 32000 字符截断。

**--analysis 回填**：key `<model>@<harness>::<task_id>`；兼容 `{task_id: {...}}` 单 unit 格式（unit 从 `UNIT=PATH` 显式绑定或文件名 `analysis_<unit>*.json` 推断），写入对应详情 Sheet 的「结果分析」「根因分析」两列。

## 4. 目录与产物

```
WildClawBench/tools/report/          ← 工具（本目录，未来可平级扩展 tools/token/ 等）
├── README.md
├── docs/design.md                   ← 本文档
├── skills/
│   ├── low-score-analysis/{SKILL.md, scripts/, references/workflow_template.js}
│   └── low-score-report/{SKILL.md, scripts/report_utils.py}
└── scripts/generate_eval_report.py

<round>/report-workspace/            ← 产物集中在 round 层
├── _failed_tasks_<unit>__<scope>.json
├── analysis_<unit>__<scope>.json
└── output/report_<N>units_<ts>.xlsx

<result-root>/低分任务根因分析报告_<unit>.md
```

安装（Claude Code 调用 Skill）：

```bash
mkdir -p .claude/skills
ln -snf ../../tools/report/skills/low-score-analysis .claude/skills/low-score-analysis
ln -snf ../../tools/report/skills/low-score-report .claude/skills/low-score-report
```

## 5. 依赖

- Python 3.9+，`openpyxl`（仅 Excel 脚本需要）
- 分析 Skill 依赖 Claude Code 的 Workflow 工具（LLM 并发分析）
