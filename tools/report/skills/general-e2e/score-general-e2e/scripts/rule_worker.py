#!/usr/bin/env python3
"""Execute one trusted General E2E rule inside a managed worker process."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import traceback
from typing import Any
import math


REQUEST_SCHEMA = "wildclawbench.general-e2e-rule-worker-request/v1"
RESULT_SCHEMA = "wildclawbench.general-e2e-rule-worker-result/v1"


def adapt_rule_result(raw: dict[str, Any], policy: object) -> dict[str, Any]:
    """Adapt an explicitly frozen imported contract; keep the original in raw_result."""
    if policy is None:
        return raw
    if not isinstance(policy, dict) or policy.get("schema_version") != "wildclawbench.general-e2e-numeric-diagnostics/v1":
        raise ValueError("unsupported rule result adapter")
    diagnostic_keys = policy.get("diagnostic_keys")
    if not isinstance(diagnostic_keys, list) or any(key not in {"diagnostics", "诊断"} for key in diagnostic_keys):
        raise ValueError("invalid diagnostic key policy")
    result = dict(raw)
    for key in diagnostic_keys:
        if key in result:
            if not isinstance(result[key], dict):
                raise ValueError(f"diagnostics must be an object: {key}")
            del result[key]
    if "overall_score" not in result:
        if policy.get("evidence_only") is True and not result:
            # Neutral transport placeholder with a frozen zero scoring weight.
            result["overall_score"] = 0.0
        elif policy.get("default_overall") == "mean" and result:
            values = list(result.values())
            if any(isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) or not 0 <= v <= 1 for v in values):
                raise ValueError("mean aggregation requires numeric checkpoints in [0,1]")
            result["overall_score"] = sum(values) / len(values)
    return result


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("worker request must be a JSON object")
    return value


def _validate_transcript(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("transcript must be an array")
    events: list[dict[str, Any]] = []
    for index, event in enumerate(value):
        if not isinstance(event, dict):
            raise ValueError(f"transcript event {index} must be a JSON object")
        events.append(event)
    return events


def _write_result(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(data)


def execute(request_path: Path, result_path: Path) -> int:
    try:
        request = _read_json(request_path)
        if request.get("schema_version") != REQUEST_SCHEMA:
            raise ValueError("worker request schema mismatch")
        source = request.get("automated_checks")
        workspace_text = request.get("workspace_path")
        transcript_value = request.get("transcript")
        if not isinstance(source, str) or not source.strip():
            raise ValueError("automated_checks must be a non-empty string")
        if not isinstance(workspace_text, str) or not workspace_text:
            raise ValueError("workspace_path must be a non-empty string")

        workspace = Path(workspace_text).resolve(strict=True)
        if not workspace.is_dir() or workspace.is_symlink():
            raise ValueError("workspace_path must be a regular directory")
        transcript = _validate_transcript(transcript_value)

        namespace: dict[str, Any] = {
            "__builtins__": __builtins__,
            "__name__": "__general_e2e_rule__",
        }
        exec(compile(source, "<general-e2e-automated-checks>", "exec"), namespace)
        grade = namespace.get("grade")
        if not callable(grade):
            raise ValueError("automated_checks did not define callable grade()")
        raw = grade(transcript=transcript, workspace_path=str(workspace))
        if not isinstance(raw, dict):
            raise ValueError("grade() must return a JSON object")
        json.dumps(raw, ensure_ascii=False, allow_nan=False)
        adapted = adapt_rule_result(raw, request.get("rule_result_adapter"))
        _write_result(
            result_path,
            {
                "schema_version": RESULT_SCHEMA,
                "ok": True,
                "result": adapted,
                **({"raw_result": raw} if request.get("rule_result_adapter") is not None else {}),
                "error": None,
                "worker": {
                    "pid": os.getpid(),
                    "python": sys.version.split()[0],
                },
            },
        )
        return 0
    except BaseException as exc:  # Worker must serialize rule failures.
        try:
            _write_result(
                result_path,
                {
                    "schema_version": RESULT_SCHEMA,
                    "ok": False,
                    "result": None,
                    "error": {
                        "type": type(exc).__name__,
                        "message": str(exc) or type(exc).__name__,
                        "traceback": traceback.format_exc(limit=20),
                    },
                    "worker": {
                        "pid": os.getpid(),
                        "python": sys.version.split()[0],
                    },
                },
            )
        except BaseException:
            traceback.print_exc(file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    args = parser.parse_args(argv)
    return execute(args.request, args.result)


if __name__ == "__main__":
    raise SystemExit(main())
