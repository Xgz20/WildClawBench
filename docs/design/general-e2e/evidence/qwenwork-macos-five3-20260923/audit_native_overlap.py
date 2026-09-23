#!/usr/bin/env python3
"""Recompute QwenWork main-turn overlap from a collected General E2E unit."""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def native_time(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("native event has no timestamp")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("native event timestamp has no timezone")
    return result


def main_interval(unit_root: Path, row: dict, batch_id: str, unit_id: str) -> dict:
    task_id = row["task_id"]
    trace_root = unit_root / ".general-e2e" / "collection" / task_id / "trace"
    index_path = trace_root / "trace-index.json"
    index = read_json(index_path)
    expected_identity = {
        "batch_id": batch_id,
        "unit_id": unit_id,
        "task_id": task_id,
        "attempt_id": row["attempt_id"],
    }
    if index.get("identity") != expected_identity:
        raise ValueError(f"trace identity mismatch: {task_id}")
    if index.get("session", {}).get("session_id") != row.get("session_id"):
        raise ValueError(f"trace session mismatch: {task_id}")

    events = []
    sources = []
    for source in index.get("raw_trace", []):
        relative = source.get("path")
        if not isinstance(relative, str) or not relative.startswith("raw/segments/"):
            continue
        candidate = trace_root / relative
        if candidate.is_symlink():
            raise ValueError(f"unsafe segment path: {task_id}: {relative}")
        path = candidate.resolve()
        try:
            path.relative_to(trace_root.resolve())
        except ValueError as exc:
            raise ValueError(f"unsafe segment path: {task_id}: {relative}") from exc
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"unsafe segment path: {task_id}: {relative}")
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != source.get("sha256") or len(data) != source.get("size"):
            raise ValueError(f"segment digest mismatch: {task_id}: {relative}")
        sources.append({"path": relative, "sha256": source["sha256"], "size": len(data)})
        events.extend(json.loads(line) for line in data.splitlines() if line)
    if not sources:
        raise ValueError(f"no native segments: {task_id}")

    starts = [event for event in events if event.get("type") == "turn.started"
              and not event.get("data", {}).get("is_subagent")]
    if len(starts) != 1 or not starts[0].get("turn_id"):
        raise ValueError(f"main turn start is not unique: {task_id}")
    finishes = [event for event in events if event.get("type") == "turn.finished"
                and event.get("turn_id") == starts[0]["turn_id"]]
    if len(finishes) != 1:
        raise ValueError(f"main turn finish is not unique: {task_id}")
    started = native_time(starts[0].get("ts"))
    finished = native_time(finishes[0].get("ts"))
    if finished <= started:
        raise ValueError(f"main turn has nonpositive duration: {task_id}")
    return {
        "task_id": task_id,
        "attempt_id": row["attempt_id"],
        "session_id": row["session_id"],
        "turn_id": starts[0]["turn_id"],
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "timestamp_delta_seconds": (finished - started).total_seconds(),
        "trace_index": {"path": str(index_path), "sha256": digest(index_path)},
        "segments": sources,
    }


def audit(unit_root: Path, queue_id: str) -> dict:
    queue_root = unit_root / ".general-e2e" / "queues" / "qwenwork"
    state_path = queue_root / f"{queue_id}.json"
    receipt_path = queue_root / f"{queue_id}-receipt.json"
    state = read_json(state_path)
    receipt = read_json(receipt_path)
    rows = state.get("tasks", [])
    if (state.get("phase") != "COMPLETED" or receipt.get("phase") != "COMPLETED"):
        raise ValueError("queue is not complete")
    if receipt.get("identity", {}).get("frozen_sha256") != state.get("frozen_sha256"):
        raise ValueError("queue receipt digest mismatch")
    if len(rows) != len(state.get("frozen", {}).get("task_ids", [])) or len(rows) == 0:
        raise ValueError("queue task scope mismatch")
    if [row.get("task_id") for row in rows] != state["frozen"]["task_ids"]:
        raise ValueError("queue task order mismatch")
    if any(row.get("phase") != "COMPLETED" or row.get("dispatch_attempt_count") != 1
           or not row.get("session_id") for row in rows):
        raise ValueError("queue has an incomplete or duplicate dispatch")

    intervals = [main_interval(unit_root, row, state["frozen"]["batch_id"],
                               state["frozen"]["unit_id"]) for row in rows]
    points = []
    for interval in intervals:
        points.append((native_time(interval["started_at"]), 1, interval["task_id"]))
        points.append((native_time(interval["finished_at"]), -1, interval["task_id"]))
    points.sort(key=lambda point: (point[0], point[1]))
    active: set[str] = set()
    peak = 0
    peak_at = None
    peak_tasks: list[str] = []
    for at, change, task_id in points:
        if change == 1:
            active.add(task_id)
        else:
            active.remove(task_id)
        if len(active) > peak:
            peak = len(active)
            peak_at = at.isoformat()
            peak_tasks = sorted(active)
    return {
        "schema_version": "wildclawbench.qwenwork-main-turn-overlap-audit/v1",
        "batch_id": state["frozen"]["batch_id"],
        "unit_id": state["frozen"]["unit_id"],
        "queue_id": queue_id,
        "requested_slots": state["frozen"]["run_slots"],
        "dispatch_occupancy_peak": receipt["observed_max_concurrency"],
        "native_interval_coverage": {"known": len(intervals), "total": len(rows)},
        "native_peak": peak,
        "native_peak_at": peak_at,
        "native_peak_task_ids": peak_tasks,
        "requested_native_concurrency_observed": peak == min(len(rows), state["frozen"]["run_slots"]),
        "queue_state_sha256": digest(state_path),
        "queue_receipt_sha256": digest(receipt_path),
        "intervals": intervals,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unit-root", type=Path, required=True)
    parser.add_argument("--queue-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.unit_root.resolve(), args.queue_id)
    if args.output.exists():
        raise ValueError(f"output already exists: {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"native_peak": result["native_peak"],
                      "coverage": result["native_interval_coverage"],
                      "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
