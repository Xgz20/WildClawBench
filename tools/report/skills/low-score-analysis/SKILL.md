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

逐个任务用 LLM 结合判分明细（score.json 检查点字典 + 任务 .md 内的判分代码）和执行全过程（`chat_openclaw.jsonl`；AstronCode 另有 `agent_interaction.jsonl`）找出失分的**事实依据与根本原因**，结果写入 JSON，可供报告 Skill 与 Excel 脚本消费。

## 核心原则：用证据说话，不臆测

- 任务 .md 文件里的**判分代码是"判决书"**：每个失分检查点（score.json 中 <1.0 的项）对应代码里一个具体检查。分析的正确做法是带着每一个失分检查点去 transcript "案发现场"全量直读找证据，绝不预先有损摘要 transcript。
- **双层错误信号优先判断**：`execution_status.error`（执行层，如超时、Runner/Workspace 失败、API 额度耗尽）与 `score.json.error`（判分层）。执行层错误先按责任边界归因：外部大模型服务、流控、认证或网络故障归 L3；评测 Runner、容器生命周期、框架创建 Workspace 或 Grader 失败归 L4；超时任务必须读 transcript 区分模型未完成、Harness 提前截断和评测框架异常终止。

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

清单条目关键字段：`task_id`（即任务目录名，等于 `tasks/<套件>/<task_id>.md` 的文件名）、`score_pct`、`checkpoints` / `failed_checkpoints`、`error_execution` / `error_grading` / `timed_out` / `status`、`usage`（tokens/请求数）、`task_file`、`transcript`（`chat_openclaw.jsonl`）、`agent_interaction`（AstronCode 的 Harness↔模型原始请求/响应轨迹，可选）、`agent_log`。

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

### 第 4 步：分析产物质量校验（必须）

分析可以只覆盖 manifest 的一部分任务。部分覆盖是合法的增量状态，但未分析任务不能被当作“无问题”或“已分析”。合并后执行：

```bash
python3 tools/report/skills/low-score-analysis/scripts/validate_analysis.py \
  --analysis '<ANALYSIS_PATH>' \
  --manifest '<MANIFEST_PATH>'
```

- `PASS`：结构、任务范围和来源快照均通过。
- `REVIEW`：允许部分覆盖、旧 JSON 缺少结构化归因字段或来源指纹不可用；仍可回填，但下游必须展示覆盖范围，未分析任务保持空白。
- `FAIL`：存在越界 task、空分析字段、归因字段矛盾或原始输入文件发生变化；禁止继续生成正式报告。
- 如确实要求本批次全部完成，可增加 `--require-complete`；日常增量分析不要使用该参数。

`generate_eval_report.py` 在传入 `--analysis` 时也会执行同等的结构和覆盖校验，并在输出目录生成 `*.analysis_quality.json`。它只阻断 `FAIL`，不会阻断合法的 `partial/REVIEW`，因此已完成的部分仍可回填。

输出格式：

```json
{
  "01_Productivity_Flow_task_10_pdf_digest": {
    "result_analysis": "详细分析...",
    "root_cause_analysis": "根因总结（含 L1a/L1b/L2/L3/L4 归属层）...",
    "analysis_type": "failure",
    "checkpoint_analysis": [
      {
        "checkpoint": "check_xxx",
        "score": 0.0,
        "conclusion": "未满足判分代码要求，具体原因见证据。",
        "evidence_refs": [
          {"source": "chat_openclaw.jsonl", "locator": "line 128", "excerpt": "..."}
        ]
      }
    ],
    "attribution_layer": "L1b",
    "attribution_confidence": "confirmed",
    "attribution_evidence": "模型请求体的 tools 列表不包含 read，但 transcript 中模型主动发起 read 调用并收到 unsupported call；没有证据表明 Harness 违反了已声明工具契约。"
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

AstronCode 任务如果清单中存在 `agent_interaction`，必须同时 Read 该文件。它记录 Harness 与模型交互的原始请求/响应事件，优先用来核对：模型请求体实际收到的 `tools` 工具清单、模型响应中的工具调用、Harness 返回的错误或 `unsupported call`，以及请求是否真正发到了目标模型。`agent_interaction` 用于补足协议层证据，不能替代 `chat_openclaw.jsonl` 对实际执行、工具结果和最终交付的核对；两份轨迹不一致时要指出差异并降低归因置信度。

对 `unsupported call` 的判定顺序：先在 `agent_interaction` 的模型请求体中查找可见工具清单，再查响应体中的实际工具调用和返回错误，最后用 `chat_openclaw.jsonl`、Harness 日志核对是否有注册、调度和结果回传。请求体没有该工具而模型主动调用，证据充分时归 L1b；工具已声明但 Harness 未注册、映射、调度或回传，且有对应 Harness 证据时归 L2；只有错误文本而没有上述证据时使用 `uncertain/unconfirmed`。

## 五层归因与待确认状态（正式口径）

根因类别仍可使用“工具调用协议不兼容 / 超时或循环不收敛 / API 额度或认证故障 / 视觉通道失效 / 产物未落盘或路径错误 / 代码错误 / 幻觉或编造 / 任务理解偏离 / 判分脚本刚性或评测系统问题 / 能力短板”。类别描述“发生了什么”，归因层描述“主要由谁负责”；每个失分任务只填写一个主导层，其他协同因素写入 `root_cause_analysis` 和 `attribution_evidence`。

正式归因层只有五层：

| 归因层 | 判定边界 | 至少核对的证据 | 不应直接归入的情况 |
|---|---|---|---|
| `L1a` 模型基础推理能力 | 单步任务理解、事实判断、代码/内容生成或逻辑正确性不足 | 模型输出、执行结果、对应判分检查点 | 多步规划、工具选择、状态保持或交付链路问题 |
| `L1b` 模型 Agent 能力 | 模型的工具选择、任务拆解、多步规划、状态保持、循环收敛、验证或结果交付不足 | 完整 transcript、模型工具调用、工具结果和产物检查点；工具选择问题还要核对可用工具清单 | 只有 Harness 未按已声明契约执行，或共享环境/判分逻辑故障 |
| `L2` Harness 运行与工具编排 | Harness 未按已声明契约完成工具注册、映射、调度、结果回传，会话状态、重试/超时控制或产物回收 | 模型可见工具清单或 Harness 契约，加上注册/适配/调度/回传/生命周期日志中的直接证据 | 模型调用了清单中不存在的工具；Harness 兜底缺失只能作为改进建议 |
| `L3` 评测环境与推理服务基础设施 | 外部大模型服务调不通、服务认证失败、流控/限流、网络不通或模型专属视觉服务故障 | API/服务错误、限流响应、网络诊断、端点和影响范围证据 | 评测 Runner/容器/Workspace 失败、模型循环不收敛、Harness 会话异常 |
| `L4` 评测系统、任务与 Grader | 评测 Runner、容器生命周期、框架创建/挂载 Workspace、框架控制的进程终止、任务定义、判分代码或 Grader 造成执行/得分失真 | Runner/容器/Workspace 生命周期日志、timeout 配置、任务定义、判分代码和 Grader 证据 | 正常任务 deadline 到期且模型没有完成，不因 Runner 最终结束进程就归 L4 |

边界判定的推荐顺序是：先看任务是否真实执行，再看模型实际输出和工具轨迹，最后核对 Harness 契约、评测 Runner 和判分逻辑。特别是模型调用请求体/响应体中**没有提供** `bash`、`read` 等工具，却主动发起调用时，若工具清单证据完整，归 `L1b`；即使 Harness 可以增加拒绝、替代工具或其他兜底，也不改变根因。只有工具已声明可用、调用格式符合契约，但 Harness 未正确注册、映射、调度或回传时，才归 `L2`。

`unsupported call` 只证明某次调用没有成功，不能单独证明是 Harness 未暴露工具。若没有工具清单、Harness 契约或调度日志，不能在模型与 Harness 之间强行二选一，应填写 `attribution_layer=uncertain`，并明确缺少哪些材料。超时的推荐判定是：统一任务 deadline 内模型持续循环或未完成交付归 `L1b`；Harness 在 deadline 前错误截断归 `L2`；评测 Runner/容器异常终止或 timeout 配置错误归 `L4`；外部模型服务或网络没有给模型执行机会归 `L3`。证据不足时保持待确认。

`uncertain` 是待确认状态，不是第六层；它不参与五层归因分布，也不能直接写入模型侧或 Harness 侧能力结论。满分成功对照填写 `attribution_layer=none`、`attribution_confidence=none`。

归因置信度统一定义为：`confirmed` 表示直接证据充分，并排除了主要替代解释；`probable` 表示现有证据支持当前判断，但仍有一个未闭环因素；`unconfirmed` 表示关键证据缺失，无法可靠归因。通常 `unconfirmed` 与 `attribution_layer=uncertain` 配套使用。

## 归因分层是否保留（设计建议）

建议保留，但把它定位为**内部诊断和评测有效性治理工具**，不要把它变成对外报告的第五种能力排名。

- 保留理由：模型/Harness 对比必须区分“模型没有完成”与“Harness 没有正确执行”，同时要把外部服务故障和评测框架故障从能力结论中剥离；没有分层时，低分任务只能按错误文本归类，容易把 L3/L4 错算成模型短板。
- 主要副作用：证据不足时容易制造责任错觉；Runner、容器、Workspace、Harness 会话和外部服务的日志若不完整，五层看似精确但结论不可靠；新增字段和提示词也会影响旧 Workflow 数据。
- 控制副作用：新分析要求 `attribution_layer`、`attribution_confidence`、`attribution_evidence`，旧 JSON 继续走兼容回退；缺证据使用 `uncertain/unconfirmed`，不纳入五层统计；Excel 暂不增加审计列；对外报告只展示模型/Harness 能力结论，L3/L4 单列有效性说明。
- 当前不建议继续细分成更多层。Runner/容器/Workspace 属于 L4，外部模型服务/流控/网络属于 L3，Harness 会话/工具/产物回收属于 L2，先用证据字段描述机制即可。

## 安装（软链接到 .claude/skills）

```bash
mkdir -p .claude/skills
ln -snf ../../tools/report/skills/low-score-analysis .claude/skills/low-score-analysis
```
