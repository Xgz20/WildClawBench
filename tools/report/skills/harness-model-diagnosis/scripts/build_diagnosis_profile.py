"""Read-only Harness/model inventory and normalized metrics, not causal findings."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys

REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO))
from tools.report.lib.eval_dataset.result_files import discover_results
from src.utils.tool_metrics import parse_report_tool_metrics

CONTRACT_FIELDS = (
    "task_sha256", "execution_contract_sha256", "scoring_contract_sha256",
    "workspace_exec_sha256", "workspace_tmp_sha256", "ground_truth_sha256",
    "workspace_eval_sha256", "skill_bundles_sha256",
)
TOKEN_FIELDS = ("input_including_cache", "uncached_input", "output", "cache_read", "cache_write", "total")
METRIC_DEFINITIONS = {
    "total_tokens": {"unit": "token", "source": "usage.json", "scope": "sum_selected_runs",
                     "meaning": "含缓存输入+输出；reasoning 不重复相加；不是计费金额"},
    "elapsed_seconds_sum": {"unit": "second", "source": "usage.json:elapsed_time",
                            "scope": "sum_selected_runs",
                            "meaning": "任务累计耗时，非批次墙钟或纯推理时间；runner 计时边界可能不同"},
    "requests": {"unit": "request", "source": "usage.json:request_count",
                 "scope": "sum_selected_runs", "meaning": "Harness 记录口径，不等同于思考轮次"},
}


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8")) if Path(path).is_file() else {}


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def nonnegative(value, integer=False):
    return finite(value) and value >= 0 and (not integer or value == int(value))


def fingerprint(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def aggregate(values, expected=None, integer=False):
    """Incomplete totals are null; explicitly named subtotals remain available."""
    values = list(values)
    expected = len(values) if expected is None else expected
    valid = [v for v in values if nonnegative(v, integer)]
    status = "complete" if expected > 0 and len(valid) == expected else "partial" if valid else "unavailable"
    return {"status": status, "value": sum(valid) if status == "complete" else None,
            "known_subtotal": sum(valid) if valid else None,
            "coverage_runs": len(valid), "expected_runs": expected,
            "missing_or_invalid_runs": expected-len(valid)}


def token_components(usage):
    keys = ("input_tokens", "output_tokens", "total_tokens", "cache_read_tokens", "cache_write_tokens")
    if usage.get("usage_complete") is False or any(not nonnegative(usage.get(k), True) for k in keys):
        return {"status": "unavailable"}
    inp, out, total, read, write = (usage[k] for k in keys)
    if total == inp + out and read + write <= inp:
        mode = "input_includes_cache"
    elif total == inp + out + read + write:
        mode = "input_excludes_cache"
    else:
        return {"status": "inconsistent"}
    return {"status": "ok", "mode": mode, "input_including_cache": total-out,
            "uncached_input": total-out-read-write, "output": out,
            "cache_read": read, "cache_write": write, "total": total}


def contract_state(rows):
    values = [{k: row.get("provenance", {}).get(k) for k in CONTRACT_FIELDS} for row in rows]
    if len(values) < 2 or any(not all(v.values()) for v in values):
        return "unknown"
    return "same" if all(v == values[0] for v in values) else "different"


def summarize(rows):
    by_task = defaultdict(list)
    for row in rows:
        if row["usable"] and finite(row["score"]) and 0 <= row["score"] <= 1:
            by_task[row["task_id"]].append(row["score"])
    means = [statistics.mean(v) for v in by_task.values()]
    usage_rows = [r for r in rows if r["tokens"]["status"] == "ok"]
    token_stats = {k: aggregate([r["tokens"][k] for r in usage_rows], len(rows), True) for k in TOKEN_FIELDS}
    totals = {k: v["value"] for k, v in token_stats.items()}
    totals.update(status=token_stats["total"]["status"], coverage_runs=len(usage_rows),
                  expected_runs=len(rows), known_subtotals={k:v["known_subtotal"] for k,v in token_stats.items()})
    totals["cache_hit_rate"] = (totals["cache_read"]/totals["input_including_cache"]
                               if totals["input_including_cache"] else None)
    elapsed = aggregate(r["usage"].get("elapsed_time") for r in rows)
    requests = aggregate((r["usage"].get("request_count") for r in rows), integer=True)
    valid_elapsed = [r["usage"]["elapsed_time"] for r in rows if nonnegative(r["usage"].get("elapsed_time"))]
    return {"runs": len(rows), "scored_tasks": len(means),
            "mean_score_pct": statistics.mean(means)*100 if means else None,
            "perfect_tasks": sum(v == 1 for v in means), "zero_tasks": sum(v == 0 for v in means),
            "imperfect_tasks": sum(v < 1 for v in means), "tokens": totals,
            "requests": requests["value"], "request_coverage_runs": requests["coverage_runs"],
            "elapsed_seconds_sum": elapsed["value"], "elapsed_coverage_runs": elapsed["coverage_runs"],
            "elapsed_seconds_median": statistics.median(valid_elapsed) if valid_elapsed else None,
            "resource_coverage": {"elapsed": elapsed, "requests": requests, "tokens": token_stats["total"]},
            "versions": dict(Counter(r["execution"].get("harness_version") or "unknown" for r in rows)),
            "execution_status": dict(Counter(r["execution"].get("status", "unknown") for r in rows)),
            "validity": dict(Counter(r.get("validity", "unknown") for r in rows)),
            "anomaly_verdicts": dict(Counter(r.get("anomaly_verdict") or "unknown" for r in rows)),
            "anomalies": dict(Counter(i.get("id", "unknown") for r in rows for i in r["anomaly_items"]))}


def source_snapshot(source_dir):
    if source_dir is None:
        return None
    path = Path(source_dir).resolve()
    if not path.is_dir():
        raise ValueError("source_dir must be an existing directory")
    def git(*args):
        result = subprocess.run(["git", "-C", str(path), *args], text=True, capture_output=True)
        return result.stdout.strip() if result.returncode == 0 else None
    root = git("rev-parse", "--show-toplevel")
    status = git("status", "--porcelain") if root else None
    return {"path": str(path), "vcs_root": root, "commit": git("rev-parse", "HEAD") if root else None,
            "branch": git("branch", "--show-current") if root else None,
            "dirty": bool(status) if status is not None else None,
            "runtime_verified": False, "deployment_match": "unknown"}


def build_profile(root, target_model=None, target_harness=None, *, evidence_scope="target-union",
                  models=None, harnesses=None, task_ids=None, source_dir=None):
    root = Path(root).resolve()
    if not target_model and not target_harness:
        raise ValueError("at least one diagnosis target is required")
    if evidence_scope not in ("target-union", "selected-matrix"):
        raise ValueError("unknown evidence_scope")
    if evidence_scope == "selected-matrix" and (not models or not harnesses):
        raise ValueError("selected-matrix requires explicit models and harnesses")
    if evidence_scope == "target-union" and (models or harnesses):
        raise ValueError("models/harnesses filters require selected-matrix")
    discovery = discover_results([root])
    rows = []
    for rec in discovery.records:
        selected = ((rec.model in models and rec.harness in harnesses) if evidence_scope == "selected-matrix"
                    else ((target_model and rec.model == target_model) or
                          (target_harness and rec.harness == target_harness)))
        if not selected or (task_ids and rec.task_id not in task_ids):
            continue
        run = rec.run_dir
        transcript = next((run/name for name in ("chat_openclaw.jsonl", "chat.jsonl") if (run/name).is_file()), None)
        paths = {name: str(run/name) for name in
                 ("score.json", "usage.json", "execution_status.json", "provenance.json", "agent_interaction.jsonl")
                 if (run/name).is_file()}
        if transcript:
            paths["transcript"] = str(transcript)
        rows.append({"key": f"{rec.unit}/{rec.task_id}/{rec.run_name}", "unit": rec.unit,
                     "run_id": rec.run_name, "execution_task_id": rec.execution.get("task_id"),
                     "model": rec.model, "harness": rec.harness, "task_id": rec.task_id, "category": rec.category,
                     "run_dir": str(run), "score": rec.score,
                     "usable": rec.usable and finite(rec.score) and 0 <= rec.score <= 1,
                     "validity": rec.validity, "execution": rec.execution, "usage": rec.usage,
                     "anomaly_verdict": rec.anomalies.get("validity_verdict", "unknown"),
                     "tokens": token_components(rec.usage), "provenance": load(run/"provenance.json"),
                     "checkpoints": {k:v for k,v in rec.score_data.items() if finite(v) and k != "overall_score"},
                     "judge_notes": rec.score_data.get("_grading", {}).get("llm_notes", ""),
                     "anomaly_items": rec.anomalies.get("items", []), "sources": paths,
                     "source_sha256": {name:fingerprint(path) for name,path in paths.items()},
                     "tool_metrics": parse_report_tool_metrics(transcript, rec.harness, run)})
    if target_model and rows and not any(r["model"] == target_model for r in rows):
        raise ValueError("target model is outside the selected evidence")
    if target_harness and rows and not any(r["harness"] == target_harness for r in rows):
        raise ValueError("target harness is outside the selected evidence")
    versions = defaultdict(set)
    for r in rows:
        versions[r["unit"]].add(str(r["execution"].get("harness_version") or "unknown"))
    for r in rows:
        r["original_unit"] = r["unit"]
        if len(versions[r["unit"]]) > 1:
            r["unit"] += "["+str(r["execution"].get("harness_version") or "unknown")+"]"
    by_unit, by_task = defaultdict(list), defaultdict(list)
    for r in rows:
        by_unit[r["unit"]].append(r)
        by_task[r["task_id"]].append(r)
    # Both same-model and same-Harness evidence must retain contract checks.
    contracts = {t: {"state": contract_state(rs), "run_keys": [r["key"] for r in rs],
                     "differing_fields": [k for k in CONTRACT_FIELDS
                                          if len({str(r["provenance"].get(k)) for r in rs}) > 1]}
                 for t,rs in sorted(by_task.items())}
    wanted = {(m,h) for m in (models or []) for h in (harnesses or [])}
    present = {(r["model"],r["harness"]) for r in rows}
    return {"schema_version": 2, "generated_at": datetime.now(timezone.utc).isoformat(),
            "result_root": str(Path(root).resolve()), "target_model": target_model, "target_harness": target_harness,
            "selection": {"evidence_scope": evidence_scope, "models": models, "harnesses": harnesses,
                          "task_ids": task_ids, "run_policy": "shared_effective_runs"},
            "source_snapshot": source_snapshot(source_dir),
            "discovery_issues": [asdict(i) for i in discovery.issues],
            "scope": {"models": sorted({r["model"] for r in rows}), "harnesses": sorted({r["harness"] for r in rows}),
                      "effective_runs": len(rows), "valid_runs": sum(r["usable"] for r in rows),
                      "missing_matrix_cells": sorted(f"{m}@{h}" for m,h in wanted-present)},
            "metric_definitions": METRIC_DEFINITIONS,
            "units": {u:summarize(rs) for u,rs in sorted(by_unit.items())},
            "contracts": contracts, "records": rows,
            "interpretation": "Observed associations, not causal effects. Known subtotals are not full totals."}


def json_safe(value):
    """Non-finite raw metrics remain unavailable in portable JSON, never zero."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value


def write_json(path, data, overwrite=False):
    path = Path(path)
    if path.exists() and not overwrite:
        raise ValueError(f"output exists (use a new path or explicitly --overwrite): {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w" if overwrite else "x", encoding="utf-8") as stream:
        json.dump(json_safe(data), stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-root", type=Path, required=True)
    parser.add_argument("--target-model")
    parser.add_argument("--target-harness")
    parser.add_argument("--evidence-scope", choices=["target-union", "selected-matrix"], default="target-union")
    parser.add_argument("--models", nargs="+")
    parser.add_argument("--harnesses", nargs="+")
    parser.add_argument("--task-ids", nargs="+")
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    try:
        profile = build_profile(args.result_root.resolve(), args.target_model, args.target_harness,
                                evidence_scope=args.evidence_scope, models=args.models, harnesses=args.harnesses,
                                task_ids=args.task_ids, source_dir=args.source_dir)
        if not profile["records"]:
            raise ValueError("no effective runs match the requested scope")
        write_json(args.output, profile, args.overwrite)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps({"output": str(args.output.resolve()), "scope": profile["scope"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
