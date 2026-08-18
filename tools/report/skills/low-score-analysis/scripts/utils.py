"""low-score-analysis Skill 工具函数（WildClawBench 版）。

职责：manifest 精简、分批、断点续传、批次结果保存与合并。
全链路以 unit + selection_scope 命名分析产物：
    analysis_<unit>__<scope>.json / analysis_<unit>__<scope>_batch<N>.json
"""

from __future__ import annotations

import json
from pathlib import Path

NOTE_MAX_LEN = 500
ANALYSIS_TEXT_FIELDS = ("result_analysis", "root_cause_analysis")


def simplify_task(task: dict) -> dict:
    """精简 manifest 条目，只保留 LLM 分析所需字段，降低 Workflow 参数体积。"""
    return {
        "task_id": task["task_id"],
        "suite": task.get("suite", ""),
        "unit": task.get("unit", ""),
        "score_pct": task.get("score_pct"),
        "overall_score": task.get("overall_score"),
        "low_score_type": task.get("low_score_type", "low"),
        "analysis_type": task.get("analysis_type", "failure"),
        "selection_scope": task.get("selection_scope", ""),
        "failed_checkpoints": task.get("failed_checkpoints", {}),
        "error_execution": (task.get("error_execution") or "")[:NOTE_MAX_LEN],
        "error_grading": (task.get("error_grading") or "")[:NOTE_MAX_LEN],
        "timed_out": task.get("timed_out", False),
        "status": task.get("status", ""),
        "usage": task.get("usage", {}),
        "task_file": task.get("task_file", ""),
        "transcript": task.get("transcript", ""),
        "agent_log": task.get("agent_log", ""),
        "transcript_kb": task.get("transcript_kb", 0.0),
        "agent_interaction": task.get("agent_interaction", ""),
        "agent_interaction_kb": task.get("agent_interaction_kb", 0.0),
    }


def estimate_json_size(data) -> int:
    return len(json.dumps(data, ensure_ascii=False).encode("utf-8"))


def analyze_data_size(tasks: list[dict]) -> dict:
    original = estimate_json_size(tasks)
    simplified = estimate_json_size([simplify_task(t) for t in tasks])
    return {
        "original_size_mb": original / 1024 / 1024,
        "simplified_size_mb": simplified / 1024 / 1024,
        "reduction_pct": (1 - simplified / original) * 100 if original else 0.0,
    }


def split_into_batches(tasks: list[dict], batch_size: int = 10) -> list[list[dict]]:
    return [tasks[i:i + batch_size] for i in range(0, len(tasks), batch_size)]


def analysis_stem(unit: str, selection_scope: str | None = None) -> str:
    """返回分析文件 stem；scope 为空时兼容旧产物命名。"""
    return f"analysis_{unit}" + (f"__{selection_scope}" if selection_scope else "")


def load_completed_tasks(
    workspace_dir: str | Path,
    unit: str,
    selection_scope: str | None = None,
) -> dict:
    """读取已有分析结果（最终文件 + 批次文件），用于断点续传。"""
    workspace = Path(workspace_dir)
    completed: dict[str, dict] = {}
    stem = analysis_stem(unit, selection_scope)
    candidates = [workspace / f"{stem}.json"]
    candidates += sorted(workspace.glob(f"{stem}_batch*.json"))
    for path in candidates:
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            completed.update({k: v for k, v in data.items() if isinstance(v, dict)})
    return completed


def save_batch_result(
    results: list[dict],
    workspace_dir: str | Path,
    unit: str,
    batch_index: int,
    selection_scope: str | None = None,
) -> Path:
    """把 Workflow 返回的结果列表转成 {task_id: {...}} 并写批次文件。"""
    workspace = Path(workspace_dir)
    workspace.mkdir(parents=True, exist_ok=True)
    stem = analysis_stem(unit, selection_scope)
    path = workspace / f"{stem}_batch{batch_index}.json"
    out: dict[str, dict] = {}
    if path.is_file():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(existing, dict):
                out.update(existing)
        except (OSError, json.JSONDecodeError):
            pass
    for item in results or []:
        if not isinstance(item, dict) or not item.get("task_id"):
            raise ValueError("Workflow 返回了缺少 task_id 的分析项")
        missing = [field for field in ANALYSIS_TEXT_FIELDS
                   if not isinstance(item.get(field), str) or not item[field].strip()]
        if missing:
            raise ValueError(
                f"任务 {item['task_id']} 缺少非空分析字段：{', '.join(missing)}"
            )
        candidate = {
            "result_analysis": item.get("result_analysis", ""),
            "root_cause_analysis": item.get("root_cause_analysis", ""),
            "analysis_type": item.get("analysis_type", "failure"),
        }
        if "checkpoint_analysis" in item:
            candidate["checkpoint_analysis"] = item["checkpoint_analysis"]
        if item.get("attribution_layer"):
            candidate["attribution_layer"] = item["attribution_layer"]
        for field in ("attribution_confidence", "attribution_evidence"):
            if item.get(field):
                candidate[field] = item[field]
        task_id = item["task_id"]
        existing = out.get(task_id)
        if isinstance(existing, dict):
            conflicts = [
                field for field in set(existing) & set(candidate)
                if existing.get(field) and candidate.get(field)
                and existing[field] != candidate[field]
            ]
            if conflicts:
                raise ValueError(
                    f"任务 {task_id} 的批次结果与已有结果冲突：{', '.join(sorted(conflicts))}"
                )
            merged = dict(existing)
            merged.update({key: value for key, value in candidate.items() if value})
            out[task_id] = merged
        else:
            out[task_id] = candidate
    temp_path = path.with_name(f".{path.name}.tmp")
    temp_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(path)
    return path


def merge_all_batches(
    workspace_dir: str | Path,
    unit: str,
    selection_scope: str | None = None,
) -> Path:
    """合并同一选择范围的批次文件与已有最终文件。"""
    workspace = Path(workspace_dir)
    merged = load_completed_tasks(workspace, unit, selection_scope)
    final_path = workspace / f"{analysis_stem(unit, selection_scope)}.json"
    for task_id, item in merged.items():
        if not isinstance(item, dict):
            raise ValueError(f"任务 {task_id} 的分析结果不是对象")
        missing = [field for field in ANALYSIS_TEXT_FIELDS
                   if not isinstance(item.get(field), str) or not item[field].strip()]
        if missing:
            raise ValueError(
                f"任务 {task_id} 缺少非空分析字段：{', '.join(missing)}"
            )
    temp_path = final_path.with_name(f".{final_path.name}.tmp")
    temp_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(final_path)
    return final_path


def print_batch_summary(tasks: list[dict], batch_size: int = 10) -> None:
    info = analyze_data_size(tasks)
    batches = split_into_batches(tasks, batch_size)
    print(f"任务数: {len(tasks)}，分 {len(batches)} 批（每批 ≤{batch_size}）")
    print(f"原始 {info['original_size_mb']:.2f} MB → 精简后 {info['simplified_size_mb']:.2f} MB（减少 {info['reduction_pct']:.1f}%）")
