#!/usr/bin/env python3
"""生成 WildClawBench 低分任务清单（manifest）。

数据源为 WildClawBench 评测结果目录（目录扫描为主，summary_all_*.json 仅校验）：

    <result-root>/<model>/<harness>/<suite>/<task_id>/<run_dir>/
        score.json / execution_status.json / usage.json / chat_openclaw.jsonl / agent.log

筛选口径（单轮）：
- 主口径 low：overall_score*100 < --threshold（默认 60）
- 指定任务 specified：--task-id（可重复，支持 @file.txt），覆盖阈值筛选

输出 <workspace>/_failed_tasks_<model>@<harness>.json，供 low-score-analysis
Workflow 与 low-score-report / generate_eval_report.py 消费。
"""

from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from pathlib import Path

SUITE_DIR_RE = re.compile(r"^\d{2}_")


# ---------------------------------------------------------------------------
# 结果目录发现
# ---------------------------------------------------------------------------

def is_unit_dir(path: Path) -> bool:
    """unit 目录 = 一个 (model, harness) 组合的结果目录。"""
    if not path.is_dir():
        return False
    if list(path.glob("summary_all_*.json")):
        return True
    return any(SUITE_DIR_RE.match(p.name) for p in path.iterdir() if p.is_dir())


def discover_units(result_root: Path) -> list[tuple[str, str, Path]]:
    """返回 [(model, harness, unit_dir)]。

    result_root 可以是：
    - round 根目录（如 eval_out/all_suite/round1）：<root>/<model>/<harness>/
    - 模型目录：<root>/<harness>/
    - unit 目录本身：model/harness 从路径推断
    """
    if is_unit_dir(result_root):
        return [(result_root.parent.name, result_root.name, result_root)]

    units: list[tuple[str, str, Path]] = []
    for child in sorted(result_root.iterdir()):
        if not child.is_dir() or child.name in ("report-workspace", "output"):
            continue
        if is_unit_dir(child):
            # result_root 是模型目录，child 是 harness 目录
            units.append((result_root.name, child.name, child))
            continue
        for grand in sorted(child.iterdir()):
            if grand.is_dir() and is_unit_dir(grand):
                units.append((child.name, grand.name, grand))
    return units


def find_latest_run_dir(task_dir: Path) -> tuple[Path | None, list[str]]:
    """任务目录下可能有多个运行目录（重跑），取名称排序最新的一个。

    运行目录名形如 <model>_<YYYYMMDD>_<HHMM>_<hash>，字典序即时间序。
    """
    run_dirs = sorted(p for p in task_dir.iterdir() if p.is_dir())
    if not run_dirs:
        return None, []
    return run_dirs[-1], [str(p) for p in run_dirs]


# ---------------------------------------------------------------------------
# 任务定义（tasks/<套件>/<task_id>.md）
# ---------------------------------------------------------------------------

def find_tasks_dir(explicit: str | None) -> Path | None:
    if explicit:
        p = Path(explicit).resolve()
        return p if p.is_dir() else None
    # 从脚本位置向上找包含 tasks/<套件目录> 的仓库根
    cur = Path(__file__).resolve().parent
    for _ in range(8):
        cand = cur / "tasks"
        if cand.is_dir() and any(SUITE_DIR_RE.match(p.name) for p in cand.iterdir() if p.is_dir()):
            return cand
        cur = cur.parent
    return None


def locate_task_file(tasks_dir: Path | None, suite: str, task_id: str) -> str:
    if tasks_dir is None:
        return ""
    cand = tasks_dir / suite / f"{task_id}.md"
    return str(cand) if cand.is_file() else ""


# ---------------------------------------------------------------------------
# 单任务记录构建
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def build_task_record(
    model: str,
    harness: str,
    suite: str,
    task_dir: Path,
    tasks_dir: Path | None,
) -> dict | None:
    run_dir, all_run_dirs = find_latest_run_dir(task_dir)
    if run_dir is None:
        print(f"  [警告] 任务无运行目录，跳过：{task_dir}", file=sys.stderr)
        return None

    score = _load_json(run_dir / "score.json")
    status = _load_json(run_dir / "execution_status.json")
    usage = _load_json(run_dir / "usage.json")

    checkpoints = {
        k: v for k, v in score.items()
        if k != "overall_score" and isinstance(v, (int, float))
    }
    overall = score.get("overall_score")
    score_pct = round(float(overall) * 100, 1) if isinstance(overall, (int, float)) else None
    failed = {k: v for k, v in checkpoints.items() if v < 1.0 - 1e-9}

    transcript = ""
    for name in ("chat_openclaw.jsonl", "chat.jsonl"):
        cand = run_dir / name
        if cand.is_file():
            transcript = str(cand)
            break
    transcript_kb = round(Path(transcript).stat().st_size / 1024, 1) if transcript else 0.0
    agent_log = str(run_dir / "agent.log") if (run_dir / "agent.log").is_file() else ""

    error_grading = score.get("error") or ""
    if not score:
        error_grading = "score.json 缺失或不可解析"

    return {
        "task_id": task_dir.name,
        "suite": suite,
        "model": model,
        "harness": harness,
        "unit": f"{model}@{harness}",
        "score_pct": score_pct,
        "checkpoints": checkpoints,
        "failed_checkpoints": failed,
        "error_execution": status.get("error") or "",
        "error_grading": error_grading,
        "timed_out": bool(status.get("timed_out")),
        "status": status.get("status") or "",
        "elapsed_time": status.get("elapsed_time"),
        "usage": {
            "total_tokens": usage.get("total_tokens", 0),
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
            "request_count": usage.get("request_count", 0),
            "cost_usd": usage.get("cost_usd", 0.0),
            "elapsed_time": usage.get("elapsed_time", 0.0),
        },
        "task_file": locate_task_file(tasks_dir, suite, task_dir.name),
        "run_dir": str(run_dir),
        "transcript": transcript,
        "agent_log": agent_log,
        "transcript_kb": transcript_kb,
        "all_run_dirs": all_run_dirs,
    }


def scan_unit(model: str, harness: str, unit_dir: Path, tasks_dir: Path | None) -> list[dict]:
    records: list[dict] = []
    for suite_dir in sorted(unit_dir.iterdir()):
        if not suite_dir.is_dir() or not SUITE_DIR_RE.match(suite_dir.name):
            continue
        for task_dir in sorted(suite_dir.iterdir()):
            if not task_dir.is_dir():
                continue
            rec = build_task_record(model, harness, suite_dir.name, task_dir, tasks_dir)
            if rec is not None:
                records.append(rec)
    return records


# ---------------------------------------------------------------------------
# 筛选
# ---------------------------------------------------------------------------

def parse_task_ids(raw_ids: list[str]) -> list[str]:
    """支持 @file.txt 语法（每行一个 task_id，# 开头为注释）。"""
    out: list[str] = []
    for item in raw_ids:
        if item.startswith("@"):
            path = Path(item[1:])
            if not path.is_file():
                sys.exit(f"错误：任务列表文件不存在：{path}")
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    out.append(line)
        else:
            out.append(item)
    return out


def select_tasks(records: list[dict], threshold: float, task_ids: list[str]) -> list[dict]:
    if task_ids:
        wanted = set(task_ids)
        selected = []
        for r in records:
            if r["task_id"] in wanted or any(t in r["task_id"] for t in wanted):
                r["low_score_type"] = "specified"
                selected.append(r)
        found = {r["task_id"] for r in selected}
        for t in wanted:
            if not any(t in f for f in found):
                print(f"  [警告] 指定任务未找到：{t}", file=sys.stderr)
        return selected

    selected = []
    for r in records:
        pct = r["score_pct"]
        if pct is None or pct < threshold - 1e-9:
            r["low_score_type"] = "low"
            selected.append(r)
    selected.sort(key=lambda r: (r["score_pct"] is not None, r["score_pct"] or 0.0))
    return selected


# ---------------------------------------------------------------------------
# 校验与输出
# ---------------------------------------------------------------------------

def cross_check_summary(unit_dir: Path, records: list[dict]) -> None:
    files = list(unit_dir.glob("summary_all_*.json"))
    if not files:
        return
    summary = _load_json(files[0])
    s_count = summary.get("task_count")
    if s_count is not None and s_count != len(records):
        print(f"  [警告] 目录扫描到 {len(records)} 个任务，summary 记录 {s_count} 个，请检查数据完整性", file=sys.stderr)
    g_avg = summary.get("global_avg")
    scores = [r["score_pct"] / 100 for r in records if r["score_pct"] is not None]
    if g_avg is not None and scores:
        local_avg = sum(scores) / len(records)  # 缺分任务按 0 计，与 summary 口径一致
        if abs(local_avg - g_avg) > 0.005:
            print(f"  [警告] 重算均分 {local_avg:.4f} 与 summary global_avg {g_avg:.4f} 偏差过大", file=sys.stderr)


def default_workspace(result_root: Path, unit_dir: Path) -> Path:
    if result_root == unit_dir:
        return unit_dir / "report-workspace"
    return result_root / "report-workspace"


def output_name(unit: str, task_ids: list[str]) -> str:
    if len(task_ids) == 1:
        return f"_failed_tasks_{unit}__{task_ids[0]}.json"
    if task_ids:
        return f"_failed_tasks_{unit}__multi_{len(task_ids)}.json"
    return f"_failed_tasks_{unit}.json"


def main() -> None:
    ap = argparse.ArgumentParser(description="生成 WildClawBench 低分任务清单")
    ap.add_argument("--result-root", required=True, help="round 根目录 / 模型目录 / unit 目录")
    ap.add_argument("--model", help="模型目录名（多 unit 时过滤）")
    ap.add_argument("--harness", help="harness 目录名（多 unit 时过滤）")
    ap.add_argument("--threshold", type=float, default=60.0, help="低分阈值（百分制，默认 60）")
    ap.add_argument("--task-id", action="append", default=[], help="指定任务（可重复，支持 @file.txt），覆盖阈值筛选")
    ap.add_argument("--workspace-dir", help="工作区目录（默认 <result-root>/report-workspace）")
    ap.add_argument("--output", help="输出文件路径（默认按 unit 命名）")
    ap.add_argument("--tasks-dir", help="任务定义目录（默认从脚本位置向上找 <repo>/tasks）")
    args = ap.parse_args()

    result_root = Path(args.result_root).resolve()
    if not result_root.is_dir():
        sys.exit(f"错误：结果目录不存在：{result_root}")

    units = discover_units(result_root)
    if args.model:
        units = [u for u in units if u[0] == args.model]
    if args.harness:
        units = [u for u in units if u[1] == args.harness]
    if not units:
        sys.exit("错误：未发现任何 (model, harness) 结果单元，请检查 --result-root/--model/--harness")
    if len(units) > 1:
        listing = "\n".join(f"  - {m}@{h}: {d}" for m, h, d in units)
        sys.exit(f"发现多个结果单元，请用 --model/--harness 指定其一：\n{listing}")

    model, harness, unit_dir = units[0]
    unit = f"{model}@{harness}"
    tasks_dir = find_tasks_dir(args.tasks_dir)
    if tasks_dir is None:
        print("[警告] 未找到任务定义目录（tasks/），task_file 将留空；可用 --tasks-dir 指定", file=sys.stderr)

    print(f"结果单元: {unit}")
    print(f"单元目录: {unit_dir}")
    records = scan_unit(model, harness, unit_dir, tasks_dir)
    print(f"扫描到 {len(records)} 个任务")
    cross_check_summary(unit_dir, records)

    task_ids = parse_task_ids(args.task_id)
    selected = select_tasks(records, args.threshold, task_ids)
    n_err = sum(1 for r in selected if r["error_execution"])
    n_missing_task_file = sum(1 for r in selected if not r["task_file"])
    if task_ids:
        print(f"指定任务模式：命中 {len(selected)} 个")
    else:
        print(f"低分任务（<{args.threshold:g} 分）：{len(selected)} 个")
    print(f"其中带执行层错误 {n_err} 个" + (f"；task_file 缺失 {n_missing_task_file} 个" if n_missing_task_file else ""))

    workspace = Path(args.workspace_dir) if args.workspace_dir else default_workspace(result_root, unit_dir)
    workspace.mkdir(parents=True, exist_ok=True)
    out_path = Path(args.output) if args.output else workspace / output_name(unit, task_ids)
    out_path.write_text(json.dumps(selected, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n💡 后续分析文件请命名为 analysis_{unit}.json 并保存到：{workspace}")
    print(f"MANIFEST_PATH={out_path}")


if __name__ == "__main__":
    main()
