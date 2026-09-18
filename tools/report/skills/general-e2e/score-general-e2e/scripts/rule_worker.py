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


REQUEST_SCHEMA = "wildclawbench.general-e2e-rule-worker-request/v1"
RESULT_SCHEMA = "wildclawbench.general-e2e-rule-worker-result/v1"


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
        _write_result(
            result_path,
            {
                "schema_version": RESULT_SCHEMA,
                "ok": True,
                "result": raw,
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
