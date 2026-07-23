# 多轮评测统计实施计划（--runs + mean/std/pass@k/pass^k + 报告跨轮聚合）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 WildClawBench 补齐选型报告 §6 P1「多 run 统计薄弱」：`--runs k` 让每个用例跑 k 轮，summary 产出 mean/std/pass@k/pass^k（无偏组合估计），下游 Excel 报告按 k 轮聚合而非只取最后一轮。前置依赖 `--resume` 已实现（`7e18325`）。

**Architecture:** 多轮执行在 `run_batch.py` 任务分发层加一层 run 循环（k 次调用 `run_single_task`，各自独立 run 目录，天然被现有 `<模型slug>_<ts>_<runid>` 命名容纳）；多轮聚合抽成独立纯函数模块 `src/utils/multirun_stats.py`（输入 = 一个 task 的 k 个 overall_score 列表，输出统计 dict，可单测）；summary 与报告工具都调用它。pass 阈值经 `--pass-threshold`（默认 0.99）配置，写入评分口径权威文档。

**Tech Stack:** Python 3.10+（`math.comb` 算无偏估计，无新依赖）。参考 QwenClawBench `pass_k_stats` / Harbor `utils/pass_at_k.py`。

## Global Constraints

- **默认零变化**：不传 `--runs`（默认 1）时，执行流程、summary 结构、报告全部与现状一致；多轮统计字段仅在 k>1 时出现，且以**新增字段**方式加入 summary，不改动 `results` 数组现有结构
- 无偏估计公式（n=总有效轮数，c=pass 轮数，k=报告的尝试数，取 k=min(runs,n)）：
  - $\text{pass@}k = 1 - \binom{n-c}{k} / \binom{n}{k}$
  - $\text{pass}^k = \binom{c}{k} / \binom{n}{k}$
- pass 判定：`overall_score >= pass_threshold`（默认 0.99，可配）
- 口径同步：本迭代所有口径（pass 阈值、多轮字段语义）落到 `docs/local/design/评测评分口径.md` §6，并把该节从"目标口径"改为"现状"
- 与 resume 的耦合：`--resume` 的"已完成"判定从"最新 run 有效"改为"该 (task,model) 已有 ≥k 条有效 run"
- 每 Task 独立提交；验证用 `python3 -` 内联断言 + 真实多轮冒烟

---

### Task 1: 多轮统计纯函数模块

**Files:**
- Create: `src/utils/multirun_stats.py`

**Interfaces:**
- Produces:
  - `pass_at_k(n, c, k) -> float`：无偏 pass@k
  - `pass_hat_k(n, c, k) -> float`：无偏 pass^k
  - `aggregate_runs(scores: list[float], pass_threshold: float = 0.99) -> dict`：输入一个 task 的 k 个 overall_score，返回 `{"runs","mean","std","pass_count","pass_at_k","pass_hat_k","pass_threshold","scores"}`

- [ ] **Step 1: 写模块**

```python
"""多轮评测统计：mean/std/pass@k/pass^k（无偏组合估计）。

参考 OpenAI HumanEval 的无偏 pass@k，Harbor/QwenClawBench 同源。
纯函数、无副作用、无第三方依赖（仅标准库 math/statistics）。
口径定义见 docs/local/design/评测评分口径.md §6。
"""
from __future__ import annotations

import math
import statistics

DEFAULT_PASS_THRESHOLD = 0.99


def pass_at_k(n: int, c: int, k: int) -> float:
    """n 轮中 c 轮成功，k 次尝试至少成功一次的无偏概率。"""
    if k > n or n <= 0:
        return 0.0
    if c <= 0:
        return 0.0
    if n - c < k:
        return 1.0  # 失败轮不足 k，任取 k 轮必含成功
    return 1.0 - math.comb(n - c, k) / math.comb(n, k)


def pass_hat_k(n: int, c: int, k: int) -> float:
    """n 轮中 c 轮成功，连续 k 次尝试全部成功的无偏概率。"""
    if k > n or n <= 0:
        return 0.0
    if c < k:
        return 0.0
    return math.comb(c, k) / math.comb(n, k)


def aggregate_runs(scores: list[float], pass_threshold: float = DEFAULT_PASS_THRESHOLD) -> dict:
    """聚合一个 task 的多轮 overall_score 列表。

    scores 只应包含**有效轮**的分数（调用方负责剔除无 score.json 的轮；
    执行失败但产出了 0 分 score.json 的轮算有效轮，计入 n 但通常不 pass）。
    """
    n = len(scores)
    if n == 0:
        return {
            "runs": 0, "mean": None, "std": None, "pass_count": 0,
            "pass_at_k": None, "pass_hat_k": None,
            "pass_threshold": pass_threshold, "scores": [],
        }
    c = sum(1 for s in scores if s >= pass_threshold)
    k = n  # 报告口径：用满 n 轮估计 pass@n / pass^n
    return {
        "runs": n,
        "mean": statistics.fmean(scores),
        "std": statistics.pstdev(scores) if n > 1 else 0.0,
        "pass_count": c,
        "pass_at_k": pass_at_k(n, c, k),
        "pass_hat_k": pass_hat_k(n, c, k),
        "pass_threshold": pass_threshold,
        "scores": scores,
    }
```

- [ ] **Step 2: 验证**

```bash
python3 - <<'EOF'
import sys; sys.path.insert(0, '.')
from src.utils.multirun_stats import pass_at_k, pass_hat_k, aggregate_runs
# 10 轮 7 pass：pass@1=0.7、pass@5≈0.9917、pass^5≈0.0833
assert abs(pass_at_k(10,7,1) - 0.7) < 1e-9
assert abs(pass_at_k(10,7,5) - (1 - 0)) > 0.98  # 接近 1
assert abs(pass_hat_k(10,7,5) - (21/252)) < 1e-9  # C(7,5)/C(10,5)=21/252
# 边界
assert pass_at_k(3,0,1) == 0.0 and pass_hat_k(3,0,1) == 0.0
assert pass_at_k(3,3,3) == 1.0 and pass_hat_k(3,3,3) == 1.0
# aggregate
a = aggregate_runs([1.0, 0.0, 1.0, 1.0, 0.0])
assert a["runs"]==5 and a["pass_count"]==3 and abs(a["mean"]-0.6)<1e-9
assert a["std"] > 0
b = aggregate_runs([0.98, 0.995], pass_threshold=0.99)
assert b["pass_count"]==1  # 只有 0.995 过线
print("multirun_stats ok")
EOF
```

- [ ] **Step 3: Commit** — `git add src/utils/multirun_stats.py && git commit -m "feat: 多轮统计纯函数（mean/std/pass@k/pass^k 无偏估计）"`

---

### Task 2: --runs 多轮执行 + --pass-threshold

**Files:**
- Modify: `src/utils/cli_args.py`（`--runs`、`--pass-threshold`）
- Modify: `eval/run_batch.py`（run 循环 + 阈值透传）

**Interfaces:**
- Consumes: `aggregate_runs`（Task 1）

- [ ] **Step 1: CLI 参数**

`cli_args.py` 在 `--parallel` 之后加：

```python
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        metavar="K",
        help="Repeat each task K times for multi-run stats (mean/std/pass@k/pass^k). "
             "Default 1 (single run, current behavior). Each run gets its own run dir.",
    )
    parser.add_argument(
        "--pass-threshold",
        type=float,
        default=0.99,
        metavar="T",
        help="overall_score >= T counts as a 'pass' for pass@k/pass^k. Default 0.99 (full score).",
    )
```

- [ ] **Step 2: 多轮执行循环**

在 `main()` 的 category 分支里，把「单任务执行」改为「按 runs 展开」。当前串行分支（`args.parallel <= 1`）逐 task 调 `run_single_task`；并发分支用 ThreadPoolExecutor。

多轮的最小侵入实现：把「任务列表」展开成「(task, run_idx) 工作项列表」，两个分支都遍历工作项。`run_single_task` 内部已用 `uuid + timestamp` 保证每次 run 目录唯一，**无需给它传 run_idx**（同一 task 的 k 次调用自然落 k 个不同 run 目录）。

串行分支示例：

```python
        results: list[dict] = []
        work_items = [(task, ri) for task in tasks for ri in range(args.runs)]
        if args.parallel <= 1:
            for task, _ri in work_items:
                results.append(run_single_task(task, args.model, backend=backend,
                    output_root=output_root, lobster=lobster,
                    models_config=models_config, thinking=args.thinking))
        else:
            with ThreadPoolExecutor(max_workers=args.parallel) as pool:
                futures = {pool.submit(run_single_task, task, args.model, backend,
                    output_root, lobster, args.thinking, models_config): (task["task_id"], _ri)
                    for task, _ri in work_items}
                for future in as_completed(futures):
                    tid, _ri = futures[future]
                    try:
                        results.append(future.result())
                    except Exception as exc:
                        logger.error("[%s] Thread exception: %s", tid, exc)
                        results.append({"task_id": tid, "scores": {}, "error": str(exc)})
```

单任务分支（`args.task`）同理：`for _ri in range(args.runs): run_single_task(...)`（k 个结果，末尾按需退出码判定用"任一成功"或保持现状）。

把 `args.pass_threshold` 存到模块级（供 summary 用），与 TIMEOUT_* 同款：`main()` 里 `global PASS_THRESHOLD; PASS_THRESHOLD = args.pass_threshold`，模块顶部 `PASS_THRESHOLD = 0.99`。

- [ ] **Step 3: 验证**（真实 2 轮冒烟）

```bash
source docs/local/deploy/export.astroncode.sh
rm -rf /tmp/wcb_mr
OUTPUT_SUBDIR=/tmp/wcb_mr python3 eval/run_batch.py --agent-backend astroncode \
  --task tasks/03_Social_Interaction/03_Social_Interaction_task_2_chat_action_extraction.md \
  --model openrouter/xopglm52 --runs 2
ls -d /tmp/wcb_mr/astroncode/03_Social_Interaction/*/*/ | wc -l   # 应为 2
```
Expected: 生成 2 个 run 目录。

- [ ] **Step 4: Commit** — `git commit -m "feat: --runs K 多轮执行 + --pass-threshold（默认 1 轮，零行为变化）"`

---

### Task 3: summary 多轮聚合

**Files:**
- Modify: `src/utils/grading.py`（`print_summary` / `print_global_summary`）

**Interfaces:**
- Consumes: `aggregate_runs`
- Produces: summary JSON 新增 `multirun` 段（k=1 时不加，保持结构不变）

- [ ] **Step 1: 按 task_id_ori 分组聚合**

summary 当前把每个 result 独立列出。多轮下，同一原始任务有 k 个 result（run 目录名不同，但 `task_id_ori` 相同）。聚合逻辑：

- 从 `output_root/<category>/<task_id_ori>/` 结构反推分组，或用 result 里的信息还原 `task_id_ori`。**推荐**：`run_single_task` 的返回 result 里补一个 `"task_id_ori"` 字段（当前 result["task_id"] 是含时间戳的长名），分组用它。
- 每组收集有效 `overall_score`（有 score.json 且 numeric 里有 overall_score），调 `aggregate_runs(scores, PASS_THRESHOLD)`。
- `print_global_summary`：当 runs>1，`global_avg` 改为「每 task 的 mean 再跨 task 平均」，并在 summary JSON 增加：
  ```json
  "multirun": {
    "runs_per_task": k,
    "pass_threshold": 0.99,
    "per_task": {"<task_id_ori>": {mean,std,pass_at_k,pass_hat_k,...}},
    "macro": {"mean_of_means": ..., "mean_pass_at_k": ..., "mean_pass_hat_k": ...}
  }
  ```
- **k=1 时不加 `multirun` 段**（`if runs > 1`），现有结构与 global_avg 口径完全不变。

- [ ] **Step 2: 让 run_single_task 返回 task_id_ori**

`run_batch.py` `run_single_task`：`result = {"task_id": task_id, "task_id_ori": task_id_ori, "scores": {}, "error": None}`。resume 重建的 result（`_load_resume_result`）也补 `"task_id_ori": task["task_id"]`。

- [ ] **Step 3: 验证** — 用 Task 2 的 2 轮冒烟产物，确认 `summary_all_*.json` 有 `multirun.per_task` 且 pass_at_k 数值正确；再跑一次不带 `--runs` 确认无 `multirun` 段、结构与旧版一致。

- [ ] **Step 4: Commit** — `git commit -m "feat: summary 多轮聚合（mean/std/pass@k/pass^k，k=1 时结构不变）"`

---

### Task 4: 报告工具跨轮聚合

**Files:**
- Modify: `tools/report/scripts/generate_eval_report.py`（`TaskResult.__init__` :156-160 的 `run_dirs[-1]`）

**Interfaces:**
- Consumes: `aggregate_runs`（跨仓库 import：报告工具在 tools/report，需 `sys.path` 能到 src；已有类似 import 则复用，否则内联同款公式）

- [ ] **Step 1: 收集全部 run 而非仅最后一个**

`generate_eval_report.py:159-160` 当前：
```python
        run_dirs = sorted(p for p in task_dir.iterdir() if p.is_dir())
        self.run_dir = run_dirs[-1] if run_dirs else None
```
改为：保留 `self.run_dir = run_dirs[-1]`（展示用最新一轮的 transcript/检查点明细），但**得分聚合**改为读全部 run_dirs 的 `overall_score` 列表，`self.score` 取 mean（多轮）或单值（单轮）。新增 `self.multirun`（k>1 时的 std/pass@k/pass^k）。

- [ ] **Step 2: 报告展示**

- 「总览」Sheet：单轮列不变；k>1 时补充 std/pass@k/pass^k 列（k=1 或字段缺失时留空，兼容旧数据）。
- 其余 Sheet（能力/难度/分类/模态）用 mean 作为该 task 的代表分（与单轮一致，单轮时 mean==单值）。
- 口径注记引用评分口径文档 §6。

- [ ] **Step 3: 验证** — 对 Task 2/3 的 2 轮产物跑 `generate_eval_report.py`，确认总览含 pass@k 列、数值与 summary 的 `multirun` 一致；对历史单轮 round 跑一次确认无回归（不报错、无多余列或列留空）。

- [ ] **Step 4: Commit** — `git commit -m "feat: 报告工具跨轮聚合（mean 代表分 + std/pass@k/pass^k 列）"`

---

### Task 5: resume 与多轮的耦合

**Files:**
- Modify: `eval/run_batch.py`（`_load_resume_result` / resume 过滤逻辑）

- [ ] **Step 1: "已完成"改为"够 k 条有效 run"**

当前 `_find_latest_run` + `_load_resume_result` 判定"最新 run 有效即跳过"。多轮下应：

- 新增 `_count_valid_runs(output_root, task, model, rerun_error, rerun_anomalous) -> int`：数该 (task,model) 下**有效且无需重跑**的 run 数（有可解析 score.json，且按 rerun flag 不该重跑）。
- resume 过滤：`需补跑轮数 = max(0, args.runs - valid_count)`。category 分支里，pending 不再是"整个 task 跳过/执行"的二元，而是把该 task 追加 `需补跑轮数` 个工作项；`resumed_results` 收集已有效的 k' 条用于 summary。
- k=1 时退化为现有行为（够 1 条即跳过），完全兼容。

- [ ] **Step 2: 验证**（关键回归 + 多轮场景）

```bash
# 场景：先跑 2 轮，再 --runs 3 --resume → 应只补第 3 轮
source docs/local/deploy/export.astroncode.sh
rm -rf /tmp/wcb_mrr; T=tasks/03_Social_Interaction/03_Social_Interaction_task_2_chat_action_extraction.md
OUTPUT_SUBDIR=/tmp/wcb_mrr python3 eval/run_batch.py --agent-backend astroncode --task $T --model openrouter/xopglm52 --runs 2
N1=$(ls -d /tmp/wcb_mrr/astroncode/03_Social_Interaction/*/*/ | wc -l)   # 2
OUTPUT_SUBDIR=/tmp/wcb_mrr python3 eval/run_batch.py --agent-backend astroncode --task $T --model openrouter/xopglm52 --runs 3 --resume
N2=$(ls -d /tmp/wcb_mrr/astroncode/03_Social_Interaction/*/*/ | wc -l)   # 3（只补 1 轮）
echo "$N1 -> $N2 (期望 2 -> 3)"
# 单轮回归：--resume 不带 --runs，已有结果应跳过（沿用现有语义）
```

- [ ] **Step 3: Commit** — `git commit -m "refactor: resume 判定适配多轮（够 K 条有效 run 才算完成）"`

---

### Task 6: 口径文档 + 速查更新

**Files:**
- Modify: `docs/local/design/评测评分口径.md`（§6 目标口径 → 现状；补 pass 阈值口径）
- Modify: `docs/local/guide/wildclawbench-评测命令速查.md`（§8 补 --runs 用法）
- Modify: 记忆 `scoring-criteria-doc.md`（多轮从"不支持"更新为"已支持"）

- [ ] **Step 1: 评分口径 §6**
  - 状态行从"当前框架不支持多轮"改为"已支持（`--runs K`，2026-07-xx 起）"。
  - 补 pass 阈值口径：默认 0.99（满分算 pass），`--pass-threshold` 可配；说明为何选满分（对标"能不能完美完成"，部分完成不算 pass）。
  - 补 summary/报告字段位置（`multirun.per_task` / 报告总览新列）。

- [ ] **Step 2: 速查 §8** 补一条：
  ```
  - **多轮统计**：`--runs 3` 每题跑 3 轮，summary 出 mean/std/pass@k/pass^k；
    `--pass-threshold` 调 pass 判定（默认 0.99=满分）。配合 `--resume` 断点续跑：
    已跑够 K 轮的题跳过，只补不足的轮次。多轮 = K 倍机时与 token，按需开启。
  ```

- [ ] **Step 3: 记忆更新** — `scoring-criteria-doc.md` 的"关键事实锚点"里"当前不支持多轮"改为"已支持 --runs"。

- [ ] **Step 4: Commit**（代码类文件已在前面 Task 提交；本 Task 仅 docs/记忆，docs/local 不入库，仅提交若有入库文件）

---

## 验证总表（实现后逐条过）

- [ ] `--runs` 缺省=1，执行/summary/报告与现状零差异（回归）
- [ ] `--runs 2` 真实冒烟生成 2 个 run 目录
- [ ] summary `multirun.per_task` 的 pass_at_k/pass_hat_k 与 multirun_stats 单测数值一致
- [ ] 报告总览多轮列数值 == summary multirun
- [ ] 先 2 轮再 `--runs 3 --resume` 只补 1 轮
- [ ] 历史单轮 round 跑报告无回归
- [ ] 口径文档 §6 状态更新、pass 阈值口径落地
