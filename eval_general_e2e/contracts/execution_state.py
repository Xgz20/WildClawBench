"""Validate the portable execution-state envelope without third-party packages.

This is an adapter handoff, not a collection receipt. Native trace normalization
and collection remain separate stages. The schema uses only the keywords handled
below; unknown keywords fail closed so schema changes cannot silently bypass it.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping


SCHEMA_VERSION = "wildclawbench.general-e2e-execution-state/v1"
SCHEMA_FILE = Path(__file__).parent / "schemas/general-execution-state-v1.schema.json"
KEYWORDS = {
    "$schema", "$id", "title", "description", "type", "const", "enum",
    "properties", "required", "additionalProperties", "items", "minLength",
    "pattern", "minimum", "maximum", "format",
}


def _fail(code: str, detail: str) -> None:
    raise ValueError(f"{code}: {detail}")


def _timestamp(value: str, path: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _fail("EXECUTION_STATE_SHAPE_INVALID", f"{path}: invalid date-time")
    if parsed.tzinfo is None:
        _fail("EXECUTION_STATE_SHAPE_INVALID", f"{path}: timezone required")
    return parsed


def _shape(value: Any, schema: Mapping[str, Any], path: str = "$") -> None:
    unsupported = set(schema) - KEYWORDS
    if unsupported:
        _fail("EXECUTION_STATE_SCHEMA_UNSUPPORTED", str(sorted(unsupported)))
    types = {
        "null": value is None,
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "boolean": isinstance(value, bool),
        "integer": type(value) is int,
        "number": type(value) in {int, float} and math.isfinite(value),
    }
    declared = schema.get("type")
    if declared is not None and not any(types.get(item, False) for item in (
        declared if isinstance(declared, list) else [declared]
    )):
        _fail("EXECUTION_STATE_SHAPE_INVALID", f"{path}: expected {declared}")
    if "const" in schema and (type(value) is not type(schema["const"]) or value != schema["const"]):
        _fail("EXECUTION_STATE_SHAPE_INVALID", f"{path}: const mismatch")
    if "enum" in schema and not any(type(value) is type(item) and value == item for item in schema["enum"]):
        _fail("EXECUTION_STATE_SHAPE_INVALID", f"{path}: enum mismatch")
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        if set(schema.get("required", [])) - set(value):
            _fail("EXECUTION_STATE_SHAPE_INVALID", f"{path}: required field missing")
        if schema.get("additionalProperties") is False and set(value) - set(properties):
            _fail("EXECUTION_STATE_SHAPE_INVALID", f"{path}: unknown field")
        for key in properties.keys() & value.keys():
            _shape(value[key], properties[key], f"{path}.{key}")
    if isinstance(value, list) and "items" in schema:
        for index, item in enumerate(value):
            _shape(item, schema["items"], f"{path}[{index}]")
    if isinstance(value, str):
        if len(value.strip()) < schema.get("minLength", 0):
            _fail("EXECUTION_STATE_SHAPE_INVALID", f"{path}: empty string")
        if "pattern" in schema and re.fullmatch(schema["pattern"], value) is None:
            _fail("EXECUTION_STATE_SHAPE_INVALID", f"{path}: pattern mismatch")
        if schema.get("format") == "date-time":
            _timestamp(value, path)
    if type(value) in {int, float}:
        if value < schema.get("minimum", -math.inf) or value > schema.get("maximum", math.inf):
            _fail("EXECUTION_STATE_SHAPE_INVALID", f"{path}: out of range")


def _relative_path(root: Path, value: Any, code: str) -> Path:
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        _fail(code, "expected a portable relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in value.split("/")):
        _fail(code, value)
    candidate = root.joinpath(*path.parts)
    for ancestor in (candidate, *candidate.parents):
        if ancestor == root:
            break
        if ancestor.is_symlink():
            _fail(code, f"symbolic link: {value}")
    resolved = candidate.resolve(strict=True)
    if not resolved.is_relative_to(root):
        _fail(code, f"outside unit: {value}")
    return resolved


def _state_path(value: str, expected: Path, code: str) -> None:
    if not Path(value).is_absolute() or Path(value).resolve(strict=True) != expected:
        _fail(code, value)


def validate_terminal_execution_state(
    document: Mapping[str, Any], *, unit_root: Path, manifest: Mapping[str, Any]
) -> None:
    """Validate shape, business identity, workspace, dispatch and hashed evidence."""
    _shape(document, json.loads(SCHEMA_FILE.read_text(encoding="utf-8")))
    root = unit_root.resolve(strict=True)
    harness = manifest.get("unit", {}).get("harness", {})
    driver = document["driver"]
    if driver["harness"] != harness.get("id") or driver["platform"] != harness.get("platform"):
        _fail("EXECUTION_DRIVER_BINDING_MISMATCH", "harness/platform differ from manifest")
    identity = document["identity"]
    if (identity["batch_id"] != manifest.get("batch_id")
            or identity["unit_id"] != manifest.get("unit_id")
            or identity["task_id"] not in manifest.get("task_ids", [])
            or document["dataset"] != {key: manifest.get("dataset", {}).get(key) for key in ("id", "digest")}):
        _fail("EXECUTION_IDENTITY_MISMATCH", "state does not belong to unit")
    tasks = [task for task in manifest.get("tasks", []) if task.get("task_id") == identity["task_id"]]
    if len(tasks) != 1:
        _fail("EXECUTION_TASK_BINDING_MISMATCH", identity["task_id"])
    task = tasks[0]
    workspace = _relative_path(root, task.get("workspace", {}).get("path"), "EXECUTION_WORKSPACE_INVALID")
    task_root = _relative_path(root, f"execution/tasks/{identity['task_id']}", "EXECUTION_TASK_ROOT_INVALID")
    if not workspace.is_dir() or not task_root.is_dir() or not workspace.is_relative_to(task_root):
        _fail("EXECUTION_WORKSPACE_INVALID", "workspace must be inside the task directory")
    _state_path(document["candidate_workspace"], workspace, "EXECUTION_WORKSPACE_MISMATCH")
    _state_path(document["task_root"], task_root, "EXECUTION_TASK_ROOT_MISMATCH")
    prompt = document["prompt"]
    prompt_path = _relative_path(root, task.get("prompt", {}).get("path"), "EXECUTION_PROMPT_PATH_INVALID")
    _state_path(prompt["path"], prompt_path, "EXECUTION_PROMPT_PATH_MISMATCH")
    if not prompt_path.is_file():
        _fail("EXECUTION_PROMPT_PATH_INVALID", "not a regular file")
    prompt_digest = hashlib.sha256(prompt_path.read_bytes()).hexdigest()
    if prompt["sha256"] != prompt_digest or task.get("prompt", {}).get("sent_sha256") != prompt_digest:
        _fail("EXECUTION_PROMPT_HASH_MISMATCH", str(prompt_path))
    execution = document["execution"]
    completed = execution["business_status"] == "completed"
    if (document["phase"] not in {"COMPLETED", "FAILED"}
            or execution["business_status"] is None or execution["finished_at"] is None
            or (document["phase"] == "COMPLETED") != completed):
        _fail("EXECUTION_STATE_NOT_TERMINAL", document["phase"])
    if execution["started_at"] is not None and _timestamp(execution["finished_at"], "finished_at") < _timestamp(execution["started_at"], "started_at"):
        _fail("EXECUTION_TIMING_INVALID", "finished before started")
    dispatched = document["send"]["dispatch_attempt_count"] == 1
    if (prompt["send_status"] not in {"sent", "not_sent"}
            or dispatched != (prompt["send_status"] == "sent")
            or (dispatched and prompt["sent_at"] is None)
            or (not dispatched and (prompt["sent_at"] is not None
                or execution["business_status"] != "infrastructure_error"))):
        _fail("EXECUTION_DISPATCH_INVARIANT_INVALID", "unreconciled send state")
    if execution["business_status"] in {"timeout", "cancelled"} and execution["cancellation_confirmed"] is not True:
        _fail("EXECUTION_CANCELLATION_UNVERIFIED", execution["business_status"])
    session = document["session"]
    if session["cwd"] is not None:
        _state_path(session["cwd"], workspace, "EXECUTION_SESSION_WORKSPACE_MISMATCH")
    if session["verified"] and (session["cwd"] is None or not session["binding_evidence"]
            or not any(session[key] is not None for key in ("thread_id", "turn_id", "session_id"))):
        _fail("EXECUTION_SESSION_BINDING_UNVERIFIED", "verified session needs native identity, cwd and evidence")
    if (dispatched and not session["verified"]) or (completed and (not dispatched or execution["started_at"] is None)):
        _fail("EXECUTION_SESSION_BINDING_UNVERIFIED", "dispatched execution is not verified")
    seen = set()
    for artifact in session["binding_evidence"]:
        path = _relative_path(root, artifact["path"], "EXECUTION_BINDING_EVIDENCE_PATH_INVALID")
        if path in seen or not path.is_file():
            _fail("EXECUTION_BINDING_EVIDENCE_INVALID", artifact["path"])
        seen.add(path)
        data = path.read_bytes()
        if len(data) != artifact["size"] or hashlib.sha256(data).hexdigest() != artifact["sha256"]:
            _fail("EXECUTION_BINDING_EVIDENCE_HASH_MISMATCH", artifact["path"])
