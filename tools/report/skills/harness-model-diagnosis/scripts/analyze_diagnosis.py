"""Reproducible paired resource slices; outputs observations, never root causes."""
from __future__ import annotations

import argparse
from collections import defaultdict
from itertools import combinations
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_diagnosis_profile import (contract_state, finite, fingerprint, load,
                                     nonnegative, summarize, token_components, write_json)


def verify_profile(profile):
    count = 0
    for row in profile["records"]:
        for name, wanted in row.get("source_sha256", {}).items():
            path = row.get("sources", {}).get(name)
            if not path or not Path(path).is_file() or fingerprint(path) != wanted:
                raise ValueError(f"source changed/missing: {row['key']} / {name}")
            count += 1
    missing = sum(not r.get("source_sha256") or bool(set(r.get("sources", {}))-set(r.get("source_sha256", {})))
                  for r in profile["records"])
    return {"verified_files": count, "missing_fingerprint_runs": missing}


def resource_values(summary):
    return {"total_tokens": summary["tokens"]["total"],
            "input_including_cache": summary["tokens"]["input_including_cache"],
            "uncached_input": summary["tokens"]["uncached_input"], "output_tokens": summary["tokens"]["output"],
            "elapsed_seconds_sum": summary["elapsed_seconds_sum"], "requests": summary["requests"]}


def difference(a, b):
    return {k: {"delta": a[k]-b[k] if finite(a[k]) and finite(b[k]) else None,
                "relative_pct": (a[k]/b[k]-1)*100 if finite(a[k]) and finite(b[k]) and b[k] > 0 else None}
            for k in a}


def paired_slice(a, b, task_ids):
    task_ids = sorted(task_ids)
    sa, sb = (summarize([index[t] for t in task_ids]) for index in (a, b))
    return {"task_ids": task_ids, "tasks": len(task_ids), "target": sa, "comparison": sb,
            "changes": difference(resource_values(sa), resource_values(sb)),
            "contract_states": {state: sum(contract_state([a[t],b[t]]) == state for t in task_ids)
                                for state in ("same", "different", "unknown")},
            "run_pairs": [{"task_id": t, "target_run_id": a[t]["run_id"], "comparison_run_id": b[t]["run_id"],
                           "target_run_dir": a[t]["run_dir"], "comparison_run_dir": b[t]["run_dir"]} for t in task_ids]}


def oriented_pairs(profile, by_unit, target_unit=None):
    if target_unit and target_unit not in by_unit:
        raise ValueError("target-unit is not in the profile")
    for u, v in combinations(sorted(by_unit), 2):
        a, b = by_unit[u][0], by_unit[v][0]
        same_model = a["model"] == b["model"] and a["harness"] != b["harness"]
        same_harness = a["harness"] == b["harness"] and a["model"] != b["model"]
        if not (same_model or same_harness):
            continue
        if target_unit:
            if target_unit not in (u, v):
                continue
            first, second = (u,v) if u == target_unit else (v,u)
        else:
            key, wanted = (("harness", profile.get("target_harness")) if same_model
                           else ("model", profile.get("target_model")))
            if wanted is None or (a[key] != wanted and b[key] != wanted):
                continue
            first, second = (u,v) if a[key] == wanted else (v,u)
        yield first, second, "same_model" if same_model else "same_harness"


def analyze(profile, *, target_unit=None, exclude_task_ids=None, tail_count=3):
    if not isinstance(tail_count, int) or isinstance(tail_count, bool) or tail_count < 0:
        raise ValueError("tail_count must be a nonnegative integer")
    by_unit = defaultdict(list)
    for original in profile["records"]:
        # Accept legacy profile rows, but recompute metrics with current validation.
        row = dict(original, run_id=original.get("run_id") or Path(original["run_dir"]).name,
                   tokens=token_components(original["usage"]))
        by_unit[row["unit"]].append(row)
    excluded = set(exclude_task_ids or [])
    known_tasks = {r["task_id"] for rs in by_unit.values() for r in rs}
    if excluded-known_tasks:
        raise ValueError("exclude-task-ids contains tasks outside the profile")
    pairs = []
    for u, v, kind in oriented_pairs(profile, by_unit, target_unit):
        groups = []
        for unit in (u,v):
            g = defaultdict(list)
            for r in by_unit[unit]:
                g[r["task_id"]].append(r)
            groups.append(g)
        ga,gb = groups
        common = set(ga)&set(gb)
        ambiguous = sorted(t for t in common if len(ga[t]) != 1 or len(gb[t]) != 1)
        tasks = common-set(ambiguous)
        a,b = ({t:g[t][0] for t in tasks} for g in groups)
        scored = {t for t in tasks if a[t]["usable"] and b[t]["usable"]
                  and finite(a[t]["score"]) and finite(b[t]["score"])
                  and 0 <= a[t]["score"] <= 1 and 0 <= b[t]["score"] <= 1}
        ranking = sorted((t for t in tasks if nonnegative(a[t]["usage"].get("elapsed_time"))
                          and nonnegative(b[t]["usage"].get("elapsed_time"))
                          and a[t]["usage"]["elapsed_time"] > b[t]["usage"]["elapsed_time"]),
                         key=lambda t: (-(a[t]["usage"]["elapsed_time"]-b[t]["usage"]["elapsed_time"]),t))
        tails = ranking[:tail_count]
        selections = {
            "all_paired": tasks,
            "same_contract": {t for t in tasks if contract_state([a[t],b[t]]) == "same"},
            "equal_score": {t for t in scored if abs(a[t]["score"]-b[t]["score"]) < 1e-7},
            "both_perfect": {t for t in scored if a[t]["score"] == b[t]["score"] == 1},
            "paired_finished": {t for t in tasks if a[t]["execution"].get("status") == b[t]["execution"].get("status") == "finished"},
            "without_explicit_tasks": tasks-excluded,
            "without_elapsed_tails": tasks-set(tails),
        }
        pairs.append({"target_unit": u, "comparison_unit": v, "kind": kind,
                      "target_only_tasks": sorted(set(ga)-set(gb)), "comparison_only_tasks": sorted(set(gb)-set(ga)),
                      "ambiguous_multi_run_tasks": ambiguous,
                      "tail_selection": {"metric": "positive_target_minus_comparison_elapsed_seconds", "count": tail_count,
                                         "selected_task_ids": tails, "post_hoc": True},
                      "explicit_exclusions": sorted(excluded&tasks),
                      "slices": {name:paired_slice(a,b,ids) for name,ids in selections.items()}})
    return {"schema_version": 2, "metric_definitions": profile.get("metric_definitions", {}),
            "units": {u:summarize(rs) for u,rs in sorted(by_unit.items())}, "pairs": pairs,
            "interpretation": "Paired by task, not randomization; slices and exclusions are post-hoc associations. Missing totals and zero denominators have null changes."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target-unit")
    parser.add_argument("--exclude-task-ids", nargs="+", default=[])
    parser.add_argument("--tail-count", type=int, default=3)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    try:
        profile = load(args.profile)
        verification = verify_profile(profile)
        result = analyze(profile, target_unit=args.target_unit, exclude_task_ids=args.exclude_task_ids, tail_count=args.tail_count)
        result.update(profile_source=str(args.profile.resolve()), profile_sha256=fingerprint(args.profile), verification=verification)
        write_json(args.output, result, args.overwrite)
    except ValueError as exc:
        parser.error(str(exc))
    print(f"paired comparisons: {len(result['pairs'])}; output: {args.output}")


if __name__ == "__main__":
    main()
