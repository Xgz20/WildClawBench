---
name: low-score-analysis
description: Analyze WildClawBench evaluation cases using score.json, task grading code, and transcript evidence. Use for low-score or imperfect-case root-cause analysis, all-case analysis with full-score controls, score-range incremental analysis, or specific cases selected by task ID or evaluation-result path. Produces scoped per-task result/root-cause JSON for low-score reports and Excel backfill. Triggers on "分析低分任务""失分根因分析""分析所有用例""增量分析""分析指定任务""low score analysis""root cause of failures".
---

# 评测用例与低分根因分析 Skill（WildClawBench 版）

为 WildClawBench 评测产出逐用例证据分析。分析单元是 `(模型, harness)` 二元组，全链路命名 `<model>@<harness>`（如 `gpt-5.5-pro@codex`）。支持四种模式：

1. **阈值/区间模式**：筛出 `<N` 或 `[min, max)` 的任务，支持分段增量分析
2. **未满分模式**：按未四舍五入的原始 `overall_score < 1.0` 选择所有失分任务
3. **全量模式**：分析所有任务；满分任务作为成功对照，不编造失分根因
4. **指定任务模式**：按任务 ID 或 task/run/结果文件路径选择，不限得分

逐个任务用 LLM 结合判分明细（score.json 检查点字典 + 任务 .md 内的判分代码）和执行全过程（chat_openclaw.jsonl）找出失分的**事实依据与根本原因**，结果写入 JSON，可供报告 Skill 与 Excel 脚本消费。

## 核心原则：用证据说话，不臆测

- 任务 .md 文件里的**判分代码是"判决书"**：每个失分检查点（score.json 中 <1.0 的项）对应代码里一个具体检查。分析的正确做法是带着每一个失分检查点去 transcript "案发现场"全量直读找证据，绝不预先有损摘要 transcript。
- **双层错误信号优先判断**：`execution_status.error`（执行层，如超时、workspace 缺失、API 额度耗尽）与 `score.json.error`（判分层）。任务根本没跑起来的（request_count=0、认证失败等）直接定性为**环境/基础设施问题，非模型能力问题**；超时任务必须读 transcript 区分"没机会跑完"还是"模型循环不收敛"。

## 输入

- **评测结果根目录**（`--result-root`）：三种均可；仅使用 `--task-path` 时可省略
  - round 根目录：`eval_out/all_suite/round1`（多模型多 harness，需 `--model`/`--harness` 定位）
  - 模型目录：`round1/gpt-5.5-pro`（需 `--harness`，若下面只有一个 harness 也需显式指定）
  - unit 目录：`round1/gpt-5.5-pro/codex`（model/harness 自动从路径推断）
- **筛选**（互斥选择一种）：
  - `--threshold N`（默认 60，等价于 `<N`）
  - `--score-min A --score-max B`（`A <= score < B`）
  - `--imperfect` / `--all`
  - `--task-id` / `--task-path`（均可重复、支持 `@file.txt`；task_id 支持子串匹配）
- **任务定义目录**（`--tasks-dir`）：默认从脚本位置向上自动找 `<repo>/tasks`

`--task-path` 指向具体 run 或其中的文件时，必须分析该 run；指向 task 目录或按
task ID 批量选择时，使用统一有效 run 规则：忽略被可靠性重跑替换的历史 run，
默认分析最新有效 run。同一任务一次不得指定多个不同 run。

## 输出

```
<round>/report-workspace/
  ├── _failed_tasks_<model>@<harness>__<scope>.json
  ├── analysis_<model>@<harness>__<scope>_batch<N>.json
  └── analysis_<model>@<harness>__<scope>.json
```

`scope` 示例：`lt60`、`gte60_lt80`、`imperfect`、`all`、`selected_3_<hash>`。即使 `--result-root` 传 model 或 unit 目录，默认工作区也必须反推并使用 `<round>/report-workspace`；只有用户显式传 `--workspace-dir` 才可改变。

## 执行流程

### 第 1 步：生成任务清单

```bash
# 批量低分任务（最常用）
python3 tools/report/skills/low-score-analysis/scripts/generate_failed_tasks_manifest.py \
  --result-root eval_out/all_suite/round1 \
  --model gpt-5.5-pro --harness codex \
  --threshold 60

# 所有未满分任务 / 全部任务
python3 .../generate_failed_tasks_manifest.py --result-root <round>/<model>/<harness> --imperfect
python3 .../generate_failed_tasks_manifest.py --result-root <round>/<model>/<harness> --all

# 增量分析 60（含）到 80（不含），与 lt60 产物相互隔离
python3 .../generate_failed_tasks_manifest.py \
  --result-root <round>/<model>/<harness> --score-min 60 --score-max 80

# 指定任务（单个 / 多个 / @文件）
python3 .../generate_failed_tasks_manifest.py \
  --result-root eval_out/all_suite/round1/gpt-5.5-pro/codex \
  --task-id 01_Productivity_Flow_task_10_pdf_digest

python3 .../generate_failed_tasks_manifest.py \
  --result-root ... --task-id @problem_tasks.txt

python3 .../generate_failed_tasks_manifest.py \
  --task-path <unit>/<suite>/<task>/<run>/score.json \
  --task-path <unit>/<suite>/<task>/<run>/chat_openclaw.jsonl
```

记录脚本输出的 `WORKSPACE_DIR`、`SELECTION_SCOPE`、`ANALYSIS_PATH` 和 `MANIFEST_PATH`，后续步骤必须原样使用，禁止自行退回 unit 下的 `report-workspace`。

清单条目关键字段：`task_id`（即任务目录名，等于 `tasks/<套件>/<task_id>.md` 的文件名）、`score_pct`、`checkpoints` / `failed_checkpoints`、`error_execution` / `error_grading` / `timed_out` / `status`、`usage`（tokens/请求数）、`task_file`、`transcript`（chat_openclaw.jsonl）、`agent_log`。

### 第 2 步：数据精简与分批（必须）

原始清单含完整 checkpoints、路径列表等冗余字段，直接传给 Workflow 会触发参数体积限制。用 `utils.py` 精简并分批：

```python
import json, sys
sys.path.insert(0, 'tools/report/skills/low-score-analysis/scripts')
from utils import simplify_task, split_into_batches, load_completed_tasks, print_batch_summary

all_tasks = json.load(open('<MANIFEST_PATH>'))
simplified = [simplify_task(t) for t in all_tasks]
print_batch_summary(all_tasks, batch_size=10)
batches = split_into_batches(simplified, batch_size=10)

# 断点续传：已完成的任务跳过
scope = '<SELECTION_SCOPE>'
completed = load_completed_tasks('<WORKSPACE_DIR>', '<model>@<harness>', scope)
completed_ids = list(completed.keys())
```

### 第 3 步：分批调用 Workflow

**关键原则**：调用方（Claude 主对话）自己分批，每次只传一个批次（≤10 个任务）给 Workflow 工具：

- `scriptPath`: `tools/report/skills/low-score-analysis/references/workflow_template.js`
- `args.unit`: `<model>@<harness>`
- `args.tasks`: 当前批次的精简任务列表
- `args.completed_task_ids`: 已完成 task_id 列表

每批返回后立即用 `utils.save_batch_result(results, workspace, unit, batch_index, scope)` 落盘，避免丢失。同一批次文件已存在时会合并而非清空。全部批次完成后合并：

```python
from utils import merge_all_batches
final = merge_all_batches('<WORKSPACE_DIR>', '<model>@<harness>', '<SELECTION_SCOPE>')
```

输出格式：

```json
{
  "01_Productivity_Flow_task_10_pdf_digest": {
    "result_analysis": "详细分析...",
    "root_cause_analysis": "根因总结（含 L1a/L1b/L3/L4 归属层）...",
    "analysis_type": "failure"
  }
}
```

### 第 4 步（可选）：下游消费

- **Markdown 低分报告**：调用 `low-score-report` Skill，并传同一 scope 的 manifest + analysis。该报告默认消费 `lt60`；不要把 `all` 中的满分对照混入低分根因分布。
- **Excel 回填**：显式传 `--analysis "<unit>=<ANALYSIS_PATH>"`。`generate_eval_report.py` 会将 `result_analysis` / `root_cause_analysis` 回填到对应 `评分详情_<unit>` Sheet；带 scope 的文件名仍可识别 unit。
- 同一 Excel 生成命令不要传同一 unit 的多个重叠 scope；如确需合并，先明确覆盖顺序，脚本会对重复 task 发出警告并以后加载者为准。

## transcript（chat_openclaw.jsonl）结构速查

JSONL，每行一个事件：`{"type":"message","message":{"role":...,"content":[...]}}`。content 元素：

- `type=text`：模型输出文本
- `type=tool_use`：工具调用（`name` 如 `exec_command`/`write_stdin`/`update_plan`/`view_image`，`input` 是命令/参数），是模型**实际做的操作**
- `type=tool_result`：工具返回（role=user 行内）

常见失分信号：工具调用协议不兼容（tool_result 大量 `unsupported call` 报错）、只读不写、产物写错路径、代码反复报同一个错、文本声称完成但无对应 tool_use、超时中断。

## 根因分类参考（WildClawBench 版 10 类）

工具调用协议不兼容 / 超时或循环不收敛 / API额度或认证故障 / 视觉通道失效 / 产物未落盘或路径错误 / 代码错误 / 幻觉或编造 / 任务理解偏离 / 判分脚本刚性或评测系统问题 / 能力短板。每条根因须标注主导归属层：L1a（底层推理）/ L1b（长程执行）/ L3（环境基础设施）/ L4（评测系统）。

## 安装（软链接到 .claude/skills）

```bash
mkdir -p .claude/skills
ln -snf ../../tools/report/skills/low-score-analysis .claude/skills/low-score-analysis
```
