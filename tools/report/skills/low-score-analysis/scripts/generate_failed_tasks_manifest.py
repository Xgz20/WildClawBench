#!/usr/bin/env python3
"""生成 WildClawBench 评测用例分析清单（manifest）。

数据源为 WildClawBench 评测结果目录（目录扫描为主，summary_all_*.json 仅校验）：

    <result-root>/<model>/<harness>/<suite>/<task_id>/<run_dir>/
        score.json / execution_status.json / usage.json / chat_openclaw.jsonl / agent.log

筛选口径（单轮）：
- threshold/range：按原始 overall_score 筛选分数区间（默认 <60）
- imperfect：所有未满分或无有效分数的任务
- all：所有任务（满分任务作为成功对照）
- specified：--task-id / --task-path 指定任务，不限分数

默认输出到 round 根目录的 report-workspace，并在文件名中包含筛选范围，供
low-score-analysis Workflow 与 low-score-report / generate_eval_report.py 消费。
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO_ROOT))

from src.utils.anomalies import scan_run_dir  # noqa: E402
from src.utils.run_selection import select_effective_run_dirs  # noqa: E402

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
    """任务目录下可能有多个运行目录，取统一选择规则中的最新有效 run。

    运行目录名形如 <model>_<YYYYMMDD>_<HHMM>_<hash>，字典序即时间序。
    """
    run_dirs = sorted(p for p in task_dir.iterdir() if p.is_dir())
    if not run_dirs:
        return None, []
    effective_run_dirs = select_effective_run_dirs(run_dirs, scan_run_dir)
    return effective_run_dirs[-1], [str(p) for p in run_dirs]


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
    selected_run_dir: Path | None = None,
) -> dict | None:
    latest_run_dir, all_run_dirs = find_latest_run_dir(task_dir)
    run_dir = selected_run_dir or latest_run_dir
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
        "overall_score": float(overall) if isinstance(overall, (int, float)) else None,
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
        "task_dir": str(task_dir),
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

def parse_list_values(raw_values: list[str], value_name: str) -> list[str]:
    """展开可重复参数和 @file.txt（每行一个值，# 开头为注释）。"""
    out: list[str] = []
    for item in raw_values:
        if item.startswith("@"):
            path = Path(item[1:])
            if not path.is_file():
                sys.exit(f"错误：{value_name}列表文件不存在：{path}")
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    out.append(line)
        else:
            out.append(item)
    return out


def find_unit_for_result_path(raw_path: str) -> Path:
    """从 task/run/结果文件路径向上定位 unit 目录。"""
    path = Path(raw_path).expanduser().resolve()
    if not path.exists():
        sys.exit(f"错误：指定结果路径不存在：{path}")
    current = path if path.is_dir() else path.parent
    for candidate in (current, *current.parents):
        if list(candidate.glob("summary_all_*.json")):
            return candidate
        # 无 summary 时要求完整的 suite/task/run 三层，避免把名称同样以
        # 两位数字开头的 suite 或 task 目录误判成 unit。
        for suite_dir in candidate.iterdir():
            if not suite_dir.is_dir() or not SUITE_DIR_RE.match(suite_dir.name):
                continue
            for task_dir in suite_dir.iterdir():
                if not task_dir.is_dir():
                    continue
                if any(
                    run_dir.is_dir()
                    and ((run_dir / "score.json").is_file()
                         or (run_dir / "execution_status.json").is_file())
                    for run_dir in task_dir.iterdir()
                ):
                    return candidate
    sys.exit(f"错误：无法从指定结果路径定位 (model, harness) unit：{path}")


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def record_matches_path(record: dict, raw_path: str) -> bool:
    """task 目录、任一 run 目录及其下文件均可定位任务。"""
    path = Path(raw_path).expanduser().resolve()
    task_dir = Path(record["task_dir"]).resolve()
    return path == task_dir or _is_within(path, task_dir)


def apply_task_path_run_overrides(
    records: list[dict],
    task_paths: list[str],
    tasks_dir: Path | None,
) -> list[dict]:
    """路径落在具体 run 内时，让该任务分析指定 run，而不是默认最新 run。"""
    overrides: dict[int, Path] = {}
    for raw_path in task_paths:
        path = Path(raw_path).expanduser().resolve()
        matches = [(index, record) for index, record in enumerate(records)
                   if record_matches_path(record, raw_path)]
        if not matches:
            continue
        index, record = matches[0]
        task_dir = Path(record["task_dir"]).resolve()
        relative = path.relative_to(task_dir)
        if not relative.parts:
            continue  # 指定 task 目录时仍取最新 run。
        run_dir = task_dir / relative.parts[0]
        if not run_dir.is_dir():
            continue
        previous = overrides.get(index)
        if previous is not None and previous != run_dir:
            sys.exit(f"错误：同一任务一次只能分析一个 run：{previous} / {run_dir}")
        overrides[index] = run_dir

    updated = list(records)
    for index, run_dir in overrides.items():
        old = records[index]
        rebuilt = build_task_record(
            old["model"], old["harness"], old["suite"],
            Path(old["task_dir"]), tasks_dir, selected_run_dir=run_dir,
        )
        if rebuilt is not None:
            updated[index] = rebuilt
    return updated


def _format_bound(value: float) -> str:
    return f"{value:g}".replace("-", "neg").replace(".", "p")


def _safe_name(value: str, max_len: int = 64) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._-")
    return (cleaned or "task")[:max_len]


def build_selection(
    *,
    select_all: bool,
    imperfect: bool,
    threshold: float | None,
    score_min: float | None,
    score_max: float | None,
    task_ids: list[str],
    task_paths: list[str],
) -> dict:
    """生成统一选择规则及稳定的产物范围标识。"""
    if task_ids or task_paths:
        selectors = sorted(task_ids) + sorted(str(Path(p).expanduser().resolve()) for p in task_paths)
        digest = hashlib.sha256("\n".join(selectors).encode("utf-8")).hexdigest()[:8]
        if len(task_ids) == 1 and not task_paths:
            scope = f"selected_{_safe_name(task_ids[0])}"
        else:
            scope = f"selected_{len(selectors)}_{digest}"
        return {"kind": "specified", "scope": scope, "label": f"指定任务 {len(selectors)} 项"}
    if select_all:
        return {"kind": "all", "scope": "all", "label": "全部用例"}
    if imperfect:
        return {"kind": "imperfect", "scope": "imperfect", "label": "所有未满分及无有效分数用例"}

    upper = threshold if threshold is not None else score_max
    if upper is None and score_min is None:
        upper = 60.0
    if score_min is None:
        scope = f"lt{_format_bound(upper)}"
        label = f"低于 {upper:g} 分"
    elif upper is None:
        scope = f"gte{_format_bound(score_min)}"
        label = f"大于等于 {score_min:g} 分"
    else:
        scope = f"gte{_format_bound(score_min)}_lt{_format_bound(upper)}"
        label = f"{score_min:g} 分（含）至 {upper:g} 分（不含）"
    return {"kind": "range", "scope": scope, "label": label,
            "score_min": score_min, "score_max": upper}


def select_tasks(
    records: list[dict],
    selection: dict,
    task_ids: list[str],
    task_paths: list[str],
) -> list[dict]:
    kind = selection["kind"]
    if kind == "specified":
        wanted = set(task_ids)
        selected = []
        for r in records:
            id_match = r["task_id"] in wanted or any(t in r["task_id"] for t in wanted)
            path_match = any(record_matches_path(r, p) for p in task_paths)
            if id_match or path_match:
                r["low_score_type"] = "specified"
                selected.append(r)
        found = {r["task_id"] for r in selected}
        for t in wanted:
            if not any(t in f for f in found):
                print(f"  [警告] 指定任务未找到：{t}", file=sys.stderr)
        for p in task_paths:
            if not any(record_matches_path(r, p) for r in selected):
                print(f"  [警告] 指定结果路径未命中任务：{p}", file=sys.stderr)
    elif kind == "all":
        selected = list(records)
    elif kind == "imperfect":
        selected = [
            r for r in records
            if r["overall_score"] is None or r["overall_score"] < 1.0
        ]
    else:
        lower = selection.get("score_min")
        upper = selection.get("score_max")
        selected = []
        for r in records:
            raw = r["overall_score"]
            if raw is None:
                # 默认低分口径纳入无有效得分；显式下界区间不重复纳入。
                if lower is None:
                    selected.append(r)
                continue
            pct = raw * 100
            if (lower is None or pct >= lower) and (upper is None or pct < upper):
                selected.append(r)

    for r in records:
        if r not in selected:
            continue
        raw = r["overall_score"]
        r["selection_scope"] = selection["scope"]
        r["selection_label"] = selection["label"]
        if raw is None:
            r["analysis_type"] = "unscored"
            r.setdefault("low_score_type", "low")
        elif raw >= 1.0:
            r["analysis_type"] = "success_control"
            r.setdefault("low_score_type", "full_score")
        else:
            r["analysis_type"] = "failure"
            r.setdefault("low_score_type", "low")
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
    """分析产物始终集中到 <round>/report-workspace。"""
    del result_root  # 输入可以是 round/model/unit，落位只由已确认的 unit 反推。
    return unit_dir.parent.parent / "report-workspace"


def output_name(unit: str, selection_scope: str) -> str:
    return f"_failed_tasks_{unit}__{selection_scope}.json"


def main() -> None:
    ap = argparse.ArgumentParser(description="生成 WildClawBench 评测用例分析清单")
    ap.add_argument("--result-root", help="round 根目录 / 模型目录 / unit 目录；仅用 --task-path 时可省略")
    ap.add_argument("--model", help="模型目录名（多 unit 时过滤）")
    ap.add_argument("--harness", help="harness 目录名（多 unit 时过滤）")
    ap.add_argument("--threshold", type=float, help="低分阈值（百分制，等价于 --score-max；默认 60）")
    ap.add_argument("--score-min", type=float, help="分数区间下界（含，百分制）")
    ap.add_argument("--score-max", type=float, help="分数区间上界（不含，百分制）")
    ap.add_argument("--imperfect", action="store_true", help="分析所有未满分或无有效分数的用例")
    ap.add_argument("--all", action="store_true", help="分析全部用例，满分用例作为成功对照")
    ap.add_argument("--task-id", action="append", default=[], help="指定任务 ID（可重复，支持 @file.txt）")
    ap.add_argument("--task-path", action="append", default=[],
                    help="指定评测 task/run 目录或其中的结果文件（可重复，支持 @file.txt）")
    ap.add_argument("--workspace-dir", help="工作区目录（默认 <round>/report-workspace）")
    ap.add_argument("--output", help="输出文件路径（默认按 unit 命名）")
    ap.add_argument("--tasks-dir", help="任务定义目录（默认从脚本位置向上找 <repo>/tasks）")
    args = ap.parse_args()

    task_ids = parse_list_values(args.task_id, "任务 ID")
    task_paths = parse_list_values(args.task_path, "任务路径")
    score_mode_count = sum((args.all, args.imperfect, args.threshold is not None,
                            args.score_min is not None, args.score_max is not None))
    if (task_ids or task_paths) and score_mode_count:
        ap.error("--task-id/--task-path 不能与分数筛选参数同时使用")
    if args.all and score_mode_count > 1:
        ap.error("--all 不能与其它分数筛选参数同时使用")
    if args.imperfect and score_mode_count > 1:
        ap.error("--imperfect 不能与其它分数筛选参数同时使用")
    if args.threshold is not None and args.score_max is not None:
        ap.error("--threshold 与 --score-max 含义相同，不能同时使用")
    for name, value in (("--threshold", args.threshold), ("--score-min", args.score_min),
                        ("--score-max", args.score_max)):
        if value is not None and not 0 <= value <= 100:
            ap.error(f"{name} 必须在 0 到 100 之间")
    upper = args.threshold if args.threshold is not None else args.score_max
    if args.score_min is not None and upper is not None and args.score_min >= upper:
        ap.error("分数区间要求 --score-min 小于上界")

    if args.result_root:
        result_root = Path(args.result_root).expanduser().resolve()
    elif task_paths:
        result_root = find_unit_for_result_path(task_paths[0])
    else:
        ap.error("必须提供 --result-root；仅按路径选择时可由 --task-path 自动推断")
    if not result_root.is_dir():
        sys.exit(f"错误：结果目录不存在：{result_root}")

    units = discover_units(result_root)
    if args.model:
        units = [u for u in units if u[0] == args.model]
    if args.harness:
        units = [u for u in units if u[1] == args.harness]
    if task_paths:
        path_unit_dirs = {find_unit_for_result_path(p).resolve() for p in task_paths}
        if len(path_unit_dirs) > 1:
            sys.exit("错误：一次分析只能选择同一个 (model, harness) unit 下的结果路径")
        units = [u for u in units if u[2].resolve() in path_unit_dirs]
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
    if task_paths:
        records = apply_task_path_run_overrides(records, task_paths, tasks_dir)
    print(f"扫描到 {len(records)} 个任务")
    cross_check_summary(unit_dir, records)

    selection = build_selection(
        select_all=args.all,
        imperfect=args.imperfect,
        threshold=args.threshold,
        score_min=args.score_min,
        score_max=args.score_max,
        task_ids=task_ids,
        task_paths=task_paths,
    )
    selected = select_tasks(records, selection, task_ids, task_paths)
    n_err = sum(1 for r in selected if r["error_execution"])
    n_missing_task_file = sum(1 for r in selected if not r["task_file"])
    print(f"选择范围：{selection['label']}；命中 {len(selected)} 个")
    print(f"其中带执行层错误 {n_err} 个" + (f"；task_file 缺失 {n_missing_task_file} 个" if n_missing_task_file else ""))

    workspace = Path(args.workspace_dir) if args.workspace_dir else default_workspace(result_root, unit_dir)
    workspace.mkdir(parents=True, exist_ok=True)
    out_path = Path(args.output) if args.output else workspace / output_name(unit, selection["scope"])
    out_path.write_text(json.dumps(selected, ensure_ascii=False, indent=2), encoding="utf-8")

    analysis_path = workspace / f"analysis_{unit}__{selection['scope']}.json"
    print(f"\n后续分析文件：{analysis_path}")
    print(f"WORKSPACE_DIR={workspace}")
    print(f"SELECTION_SCOPE={selection['scope']}")
    print(f"ANALYSIS_PATH={analysis_path}")
    print(f"MANIFEST_PATH={out_path}")


if __name__ == "__main__":
    main()
