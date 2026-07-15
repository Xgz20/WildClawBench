---
name: low-score-analysis
description: Use when the user wants to analyze why a model scored low on WildClawBench evaluation tasks — root-cause analysis of failed/low-score tasks. Also supports analyzing specific tasks regardless of score. Triggers on requests like "分析低分任务""失分根因分析""为什么这个模型在某些任务上得分低""分析指定任务""low score analysis""root cause of failures". Reads score.json checkpoint details + transcript evidence and produces per-task result analysis and root cause analysis JSON.
---

# 低分任务根因分析 Skill（WildClawBench 版）

为 WildClawBench 评测产出**低分任务的根因分析**。分析单元是 `(模型, harness)` 二元组，全链路命名 `<model>@<harness>`（如 `gpt-5.5-pro@codex`）。支持两种模式：

1. **阈值筛选模式**（批量）：筛出 `overall_score` 低于阈值的任务，批量分析失分根因
2. **指定任务模式**（精准）：分析指定任务，不限得分高低（如分析高分任务的微小失分点）

逐个任务用 LLM 结合判分明细（score.json 检查点字典 + 任务 .md 内的判分代码）和执行全过程（chat_openclaw.jsonl）找出失分的**事实依据与根本原因**，结果写入 JSON，可供报告 Skill 与 Excel 脚本消费。

## 核心原则：用证据说话，不臆测

- 任务 .md 文件里的**判分代码是"判决书"**：每个失分检查点（score.json 中 <1.0 的项）对应代码里一个具体检查。分析的正确做法是带着每一个失分检查点去 transcript "案发现场"全量直读找证据，绝不预先有损摘要 transcript。
- **双层错误信号优先判断**：`execution_status.error`（执行层，如超时、workspace 缺失、API 额度耗尽）与 `score.json.error`（判分层）。任务根本没跑起来的（request_count=0、认证失败等）直接定性为**环境/基础设施问题，非模型能力问题**；超时任务必须读 transcript 区分"没机会跑完"还是"模型循环不收敛"。

## 输入

- **评测结果根目录**（`--result-root`）：三种均可
  - round 根目录：`eval_out/all_suite/round1`（多模型多 harness，需 `--model`/`--harness` 定位）
  - 模型目录：`round1/gpt-5.5-pro`（需 `--harness`，若下面只有一个 harness 也需显式指定）
  - unit 目录：`round1/gpt-5.5-pro/codex`（model/harness 自动从路径推断）
- **筛选**：`--threshold`（百分制，默认 60）或 `--task-id`（可重复，支持 `@file.txt`，覆盖阈值筛选，task_id 支持子串匹配）
- **任务定义目录**（`--tasks-dir`）：默认从脚本位置向上自动找 `<repo>/tasks`

## 输出

```
<result-root>/report-workspace/
  ├── _failed_tasks_<model>@<harness>.json    ← 低分任务清单
  └── analysis_<model>@<harness>.json         ← 根因分析结果
```

指定任务模式下文件名追加后缀避免覆盖批量产物：单任务 `__<task_id>`、多任务 `__multi_<N>`。

## 执行流程

### 第 1 步：生成任务清单

```bash
# 批量低分任务（最常用）
python3 tools/report/skills/low-score-analysis/scripts/generate_failed_tasks_manifest.py \
  --result-root eval_out/all_suite/round1 \
  --model gpt-5.5-pro --harness codex \
  --threshold 60

# 指定任务（单个 / 多个 / @文件）
python3 .../generate_failed_tasks_manifest.py \
  --result-root eval_out/all_suite/round1/gpt-5.5-pro/codex \
  --task-id 01_Productivity_Flow_task_10_pdf_digest

python3 .../generate_failed_tasks_manifest.py \
  --result-root ... --task-id @problem_tasks.txt
```

脚本末行输出 `MANIFEST_PATH=<路径>`，并提示后续分析文件的命名（必须含 unit 名 `<model>@<harness>`）。

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
completed = load_completed_tasks('<workspace>', '<model>@<harness>')
completed_ids = list(completed.keys())
```

### 第 3 步：分批调用 Workflow

**关键原则**：调用方（Claude 主对话）自己分批，每次只传一个批次（≤10 个任务）给 Workflow 工具：

- `scriptPath`: `tools/report/skills/low-score-analysis/references/workflow_template.js`
- `args.unit`: `<model>@<harness>`
- `args.tasks`: 当前批次的精简任务列表
- `args.completed_task_ids`: 已完成 task_id 列表

每批返回后立即用 `utils.save_batch_result(results, workspace, unit, batch_index)` 落盘，避免丢失。全部批次完成后合并：

```python
from utils import merge_all_batches
final = merge_all_batches('<workspace>', '<model>@<harness>')
```

输出格式：

```json
{
  "01_Productivity_Flow_task_10_pdf_digest": {
    "result_analysis": "详细分析...",
    "root_cause_analysis": "根因总结（含 L1a/L1b/L3/L4 归属层）..."
  }
}
```

### 第 4 步（可选）：下游消费

- **Markdown 报告**：调用 `low-score-report` Skill（读 `_failed_tasks_*.json` + `analysis_*.json`）
- **Excel 回填**：`tools/report/scripts/generate_eval_report.py --analysis <workspace>/analysis_<unit>.json`，回填到对应 unit 详情 Sheet 的「结果分析」「根因分析」两列。分析文件名必须含 unit 名，或用 `UNIT=<model>@<harness>:<path>` 显式绑定。

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
