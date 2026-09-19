#!/usr/bin/env python3
"""Persist General E2E flow state and exchange verified return packages."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
from typing import Any, Mapping, Sequence
import uuid
import zipfile


STATE_SCHEMA = "wildclawbench.run-general-e2e/v1"
STATE_REVISION = 1
RETURN_SCHEMA = "urn:wildclawbench:schema:general-e2e:return-package:v1"
IMPORT_INDEX_SCHEMA = "wildclawbench.general-e2e-import-index/v1"
PACKAGE_SCHEMA = "urn:wildclawbench:schema:general-e2e:package-manifest:v1"
SUBMISSION_SCHEMA = "urn:wildclawbench:schema:general-e2e:submission:v1"
RECEIPT_SCHEMA = "urn:wildclawbench:schema:general-e2e:receipt:v1"
CONTRACT_VERSION = "general-e2e-contract-v1"
BUNDLE_PROTOCOL = "general-e2e-package-v1"
FIXED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
ROLE_RE = re.compile(r"^[a-z][a-z0-9._-]*$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

ALL_STAGES = (
    "prepare",
    "execute",
    "collect-evidence",
    "score",
    "package",
    "import-return",
    "report",
)
SCOPE_STAGES = {
    "batch": ("prepare", "import-return", "report"),
    "unit": ("execute", "collect-evidence", "score", "package"),
}
STAGE_STATUSES = {
    "NOT_SELECTED",
    "PENDING",
    "RUNNING",
    "NEEDS_HUMAN",
    "NEEDS_ATTENTION",
    "COMPLETED",
    "FAILED",
}
RECEIPT_STAGE_MAP = {
    "collect-evidence": "collect-evidence",
    "report": "report",
}
EXECUTION_STATE_SCHEMA = "wildclawbench.general-e2e-astronstudio-execution-state/v1"
GENERAL_EXECUTION_STATE_SCHEMA = "wildclawbench.general-e2e-execution-state/v1"
EXECUTION_TERMINAL_PHASES = {"COMPLETED", "FAILED"}
EXECUTION_BUSINESS_STATUSES = {
    "completed",
    "candidate_error",
    "timeout",
    "infrastructure_error",
    "cancelled",
}
SECRET_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    "credentials.json",
    "secrets.json",
    "id_rsa",
    "id_ed25519",
}
SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx")
EXCLUDED_NAMES = {".DS_Store", "__pycache__"}


class FlowError(ValueError):
    """Stable user-facing workflow or integrity failure."""


@dataclass(frozen=True)
class PackageEntry:
    path: str
    kind: str
    mode: int
    data: bytes
    link_target: str | None = None

    def manifest_row(self) -> dict[str, Any]:
        row: dict[str, Any] = {
            "path": self.path,
            "kind": self.kind,
            "mode": f"{self.mode:04o}",
            "sha256": sha256_bytes(self.data),
            "size": len(self.data),
        }
        if self.link_target is not None:
            row["link_target"] = self.link_target
        return row


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def pretty_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path, *, code: str = "JSON_INVALID") -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FlowError(f"{code}: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise FlowError(f"{code}: JSON 顶层必须是对象: {path}")
    return value


def write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    temporary.write_bytes(pretty_json_bytes(value))
    os.replace(temporary, path)


def write_new_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(pretty_json_bytes(value))
    except FileExistsError as exc:
        raise FlowError(f"OUTPUT_EXISTS: {path}") from exc


def identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise FlowError(f"IDENTITY_INVALID: {label}: {value!r}")
    return value


def safe_relative(value: object, label: str) -> PurePosixPath:
    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or "\0" in value
    ):
        raise FlowError(f"RELATIVE_PATH_INVALID: {label}: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise FlowError(f"RELATIVE_PATH_INVALID: {label}: {value!r}")
    return path


def _inside(root: Path, target: Path) -> bool:
    return target == root or root in target.parents


def resolve_regular_file(path: Path, code: str) -> Path:
    try:
        resolved = path.expanduser().resolve(strict=True)
    except OSError as exc:
        raise FlowError(f"{code}: {path}: {exc}") from exc
    if resolved.is_symlink() or not resolved.is_file():
        raise FlowError(f"{code}: {resolved}")
    return resolved


def resolve_directory(path: Path, code: str) -> Path:
    try:
        resolved = path.expanduser().resolve(strict=True)
    except OSError as exc:
        raise FlowError(f"{code}: {path}: {exc}") from exc
    if resolved.is_symlink() or not resolved.is_dir():
        raise FlowError(f"{code}: {resolved}")
    return resolved


def load_contract_validator(module_file: str = "validator.py"):
    skill_root = Path(__file__).resolve().parents[1]
    vendored = skill_root / "vendor/e2e-shared/general-contracts" / module_file
    candidates = [vendored]
    # Source-checkout fallback; released Skill packages always use the vendored copy.
    for parent in skill_root.parents:
        candidate = parent / "eval_general_e2e/contracts" / module_file
        if candidate.is_file():
            candidates.append(candidate)
            break
    module_path = next((path for path in candidates if path.is_file()), None)
    if module_path is None:
        raise FlowError("GENERAL_CONTRACT_VALIDATOR_UNAVAILABLE")
    module_name = f"wildclawbench_vendored_general_contracts_{Path(module_file).stem}"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise FlowError("GENERAL_CONTRACT_VALIDATOR_UNAVAILABLE")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def validate_contract(document: Mapping[str, Any], schema_id: str) -> None:
    try:
        load_contract_validator().validate_contract(
            document, expected_schema_id=schema_id
        )
    except ValueError as exc:
        raise FlowError(f"CONTRACT_INVALID: {schema_id}: {exc}") from exc


def parse_stages(values: Sequence[str]) -> list[str]:
    selected: list[str] = []
    for raw in values:
        for part in raw.split(","):
            stage = part.strip().lower()
            if stage and stage not in selected:
                selected.append(stage)
    unknown = sorted(set(selected) - set(ALL_STAGES))
    if unknown:
        raise FlowError(f"STAGE_UNKNOWN: {', '.join(unknown)}")
    return [stage for stage in ALL_STAGES if stage in selected]


def validate_scope_stages(scope: str, stages: Sequence[str]) -> None:
    illegal = [stage for stage in stages if stage not in SCOPE_STAGES[scope]]
    if illegal:
        raise FlowError(
            f"STAGE_SCOPE_INVALID: {scope}: {', '.join(illegal)}; "
            f"allowed={','.join(SCOPE_STAGES[scope])}"
        )


def manifest_for(root: Path, scope: str) -> tuple[Path, dict[str, Any]]:
    root = root.expanduser().resolve()
    path = root / "manifest.json"
    if not path.is_file() or path.is_symlink():
        raise FlowError(f"MANIFEST_MISSING: {path}")
    manifest = read_json(path, code="MANIFEST_INVALID")
    expected_kind = "batch" if scope == "batch" else "execution"
    if (
        manifest.get("schema_id") != PACKAGE_SCHEMA
        or manifest.get("schema_version") != 1
        or manifest.get("contract_version") != CONTRACT_VERSION
        or manifest.get("bundle_protocol") != BUNDLE_PROTOCOL
        or manifest.get("manifest_kind") != expected_kind
    ):
        raise FlowError(f"MANIFEST_INCOMPATIBLE: {path}")
    identifier(manifest.get("batch_id"), "batch_id")
    task_ids = manifest.get("task_ids")
    if (
        not isinstance(task_ids, list)
        or not task_ids
        or len(task_ids) != len(set(task_ids))
        or not all(isinstance(item, str) and item for item in task_ids)
    ):
        raise FlowError(f"MANIFEST_TASK_SCOPE_INVALID: {path}")
    dataset = manifest.get("dataset")
    release = manifest.get("release")
    if (
        not isinstance(dataset, dict)
        or not isinstance(dataset.get("id"), str)
        or not SHA256_RE.fullmatch(str(dataset.get("digest") or ""))
        or not isinstance(release, dict)
        or not isinstance(release.get("id"), str)
    ):
        raise FlowError(f"MANIFEST_LOCK_INVALID: {path}")
    if scope == "unit":
        identifier(manifest.get("unit_id"), "unit_id")
        unit = manifest.get("unit")
        if not isinstance(unit, dict) or unit.get("task_ids") != task_ids:
            raise FlowError(f"MANIFEST_UNIT_INVALID: {path}")
    else:
        units = manifest.get("units")
        if not isinstance(units, list) or not units:
            raise FlowError(f"MANIFEST_UNITS_INVALID: {path}")
        unit_ids = [item.get("unit_id") for item in units if isinstance(item, dict)]
        if len(unit_ids) != len(units) or len(unit_ids) != len(set(unit_ids)):
            raise FlowError(f"MANIFEST_UNITS_INVALID: {path}")
    return path, manifest


def identity_from_manifest(manifest: Mapping[str, Any], scope: str) -> dict[str, Any]:
    value: dict[str, Any] = {
        "batch_id": manifest["batch_id"],
        "dataset": manifest["dataset"],
        "release": manifest["release"],
        "task_ids": manifest["task_ids"],
    }
    if scope == "unit":
        value["unit_id"] = manifest["unit_id"]
        value["unit"] = manifest["unit"]
    else:
        value["units"] = manifest["units"]
    return value


def parse_input_locks(values: Sequence[str]) -> dict[str, dict[str, Any]]:
    locks: dict[str, dict[str, Any]] = {}
    for raw in values:
        role, separator, path_value = raw.partition("=")
        if not separator or not ROLE_RE.fullmatch(role) or role in locks:
            raise FlowError(f"INPUT_SPEC_INVALID: {raw!r}; expected unique role=/path")
        path = resolve_regular_file(Path(path_value), "INPUT_FILE_INVALID")
        locks[role] = {
            "path": str(path),
            "sha256": sha256_file(path),
            "size": path.stat().st_size,
        }
    return locks


def manifest_artifact_locks(
    root: Path, manifest: Mapping[str, Any], scope: str
) -> list[dict[str, Any]]:
    if scope != "batch":
        return []
    rows = [*(manifest.get("skill_artifacts") or []), *(manifest.get("artifacts") or [])]
    locks: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(rows):
        if not isinstance(item, dict):
            raise FlowError(f"MANIFEST_ARTIFACT_INVALID: {index}")
        relative = safe_relative(item.get("path"), "batch artifact").as_posix()
        if relative in seen:
            raise FlowError(f"MANIFEST_ARTIFACT_DUPLICATE: {relative}")
        seen.add(relative)
        path = root.joinpath(*PurePosixPath(relative).parts)
        if (
            not _inside(root, path.resolve())
            or path.is_symlink()
            or not path.is_file()
            or path.stat().st_size != item.get("size")
            or sha256_file(path) != item.get("sha256")
        ):
            raise FlowError(f"MANIFEST_ARTIFACT_DRIFT: {relative}")
        locks.append(
            {
                "relative_path": relative,
                "sha256": item["sha256"],
                "size": item["size"],
            }
        )
    return locks


def state_path(root: Path) -> Path:
    return root / ".general-e2e/run-general-e2e-state.json"


def validate_file_lock(lock: Mapping[str, Any], label: str) -> None:
    path_value = lock.get("path")
    if not isinstance(path_value, str):
        raise FlowError(f"INPUT_LOCK_INVALID: {label}")
    path = resolve_regular_file(Path(path_value), "INPUT_LOCK_MISSING")
    if path.stat().st_size != lock.get("size") or sha256_file(path) != lock.get("sha256"):
        raise FlowError(f"INPUT_DRIFT: {label}: {path}")


def validate_state(root: Path, state: Mapping[str, Any]) -> None:
    if state.get("schema_version") != STATE_SCHEMA or state.get("revision") != STATE_REVISION:
        raise FlowError("STATE_INCOMPATIBLE")
    scope = state.get("scope")
    if scope not in SCOPE_STAGES:
        raise FlowError("STATE_SCOPE_INVALID")
    selected = state.get("selected_stages")
    stages = state.get("stages")
    if not isinstance(selected, list) or not isinstance(stages, dict):
        raise FlowError("STATE_SHAPE_INVALID")
    validate_scope_stages(scope, selected)
    if set(stages) != set(ALL_STAGES) or any(
        value not in STAGE_STATUSES for value in stages.values()
    ):
        raise FlowError("STATE_STAGE_STATUS_INVALID")
    for stage in ALL_STAGES:
        if (stage in selected) == (stages[stage] == "NOT_SELECTED"):
            raise FlowError(f"STATE_STAGE_SELECTION_INVALID: {stage}")
    manifest_path, manifest = manifest_for(root, scope)
    manifest_lock = state.get("manifest")
    if not isinstance(manifest_lock, dict):
        raise FlowError("STATE_MANIFEST_LOCK_MISSING")
    expected_manifest = {
        "path": str(manifest_path),
        "sha256": sha256_file(manifest_path),
        "size": manifest_path.stat().st_size,
    }
    if manifest_lock != expected_manifest:
        raise FlowError("MANIFEST_DRIFT")
    if state.get("identity") != identity_from_manifest(manifest, scope):
        raise FlowError("STATE_IDENTITY_DRIFT")
    inputs = state.get("inputs")
    if not isinstance(inputs, dict):
        raise FlowError("STATE_INPUT_LOCKS_INVALID")
    for role, lock in inputs.items():
        if not isinstance(role, str) or not isinstance(lock, dict):
            raise FlowError("STATE_INPUT_LOCKS_INVALID")
        validate_file_lock(lock, role)
    expected_artifacts = manifest_artifact_locks(root, manifest, scope)
    if state.get("manifest_artifacts") != expected_artifacts:
        raise FlowError("MANIFEST_ARTIFACT_LOCK_DRIFT")


def load_state(root: Path) -> dict[str, Any]:
    root = root.expanduser().resolve()
    path = state_path(root)
    if not path.is_file() or path.is_symlink():
        raise FlowError(f"STATE_MISSING: {path}")
    state = read_json(path, code="STATE_INVALID")
    validate_state(root, state)
    return state


def save_state(root: Path, state: dict[str, Any]) -> None:
    root = root.expanduser().resolve()
    state["updated_at"] = utc_now()
    write_json_atomic(state_path(root), state)


def initialize_state(args: argparse.Namespace) -> dict[str, Any]:
    root = resolve_directory(Path(args.root), "ROOT_INVALID")
    stages = parse_stages(args.stage)
    if not stages:
        raise FlowError("STAGE_SELECTION_REQUIRED")
    validate_scope_stages(args.scope, stages)
    path = state_path(root)
    if path.exists() or path.is_symlink():
        state = load_state(root)
        requested_inputs = parse_input_locks(args.input)
        if (
            state["scope"] != args.scope
            or state["selected_stages"] != stages
            or state["inputs"] != requested_inputs
        ):
            raise FlowError("STATE_PLAN_FROZEN")
        return {"created": False, "state": state, "recommended_actions": recommended_actions(state)}
    manifest_path, manifest = manifest_for(root, args.scope)
    now = utc_now()
    statuses = {
        stage: ("PENDING" if stage in stages else "NOT_SELECTED")
        for stage in ALL_STAGES
    }
    if args.scope == "batch" and "prepare" in stages:
        statuses["prepare"] = "COMPLETED"
    state = {
        "schema_version": STATE_SCHEMA,
        "revision": STATE_REVISION,
        "scope": args.scope,
        "selected_stages": stages,
        "stages": statuses,
        "identity": identity_from_manifest(manifest, args.scope),
        "manifest": {
            "path": str(manifest_path),
            "sha256": sha256_file(manifest_path),
            "size": manifest_path.stat().st_size,
        },
        "inputs": parse_input_locks(args.input),
        "manifest_artifacts": manifest_artifact_locks(root, manifest, args.scope),
        "artifacts": {},
        "errors": {},
        "created_at": now,
        "updated_at": now,
    }
    write_new_json(path, state)
    return {"created": True, "state": state, "recommended_actions": recommended_actions(state)}


def set_stage(args: argparse.Namespace) -> dict[str, Any]:
    root = resolve_directory(Path(args.root), "ROOT_INVALID")
    state = load_state(root)
    stage = args.stage
    if stage not in state["selected_stages"]:
        raise FlowError(f"STAGE_NOT_SELECTED: {stage}")
    if args.status == "COMPLETED":
        raise FlowError("COMPLETED_REQUIRES_VERIFIED_ARTIFACT")
    current = state["stages"][stage]
    transitions = {
        "PENDING": {"RUNNING", "NEEDS_HUMAN", "NEEDS_ATTENTION", "FAILED"},
        "RUNNING": {"RUNNING", "NEEDS_HUMAN", "NEEDS_ATTENTION", "FAILED"},
        "NEEDS_HUMAN": {"RUNNING", "NEEDS_HUMAN", "NEEDS_ATTENTION", "FAILED"},
        "NEEDS_ATTENTION": {"RUNNING", "NEEDS_HUMAN", "NEEDS_ATTENTION", "FAILED"},
        "FAILED": {"RUNNING", "NEEDS_ATTENTION", "FAILED"},
        "COMPLETED": set(),
    }
    if args.status not in transitions[current]:
        raise FlowError(f"STAGE_TRANSITION_INVALID: {stage}: {current} -> {args.status}")
    state["stages"][stage] = args.status
    if args.error:
        state["errors"][stage] = {"message": args.error, "recorded_at": utc_now()}
    elif args.status not in {"FAILED", "NEEDS_ATTENTION"}:
        state["errors"].pop(stage, None)
    save_state(root, state)
    return {"state": state, "recommended_actions": recommended_actions(state)}


def expected_scope(state: Mapping[str, Any]) -> tuple[dict[str, str], dict[str, str], list[str]]:
    identity = state["identity"]
    scope = {"batch_id": identity["batch_id"]}
    if state["scope"] == "unit":
        scope["unit_id"] = identity["unit_id"]
    else:
        scope["unit_id"] = "batch"
    dataset = {"id": identity["dataset"]["id"], "digest": identity["dataset"]["digest"]}
    return scope, dataset, list(identity["task_ids"])


def validate_receipt_artifacts(root: Path, receipt: Mapping[str, Any]) -> None:
    for item in receipt.get("artifacts", []):
        relative = safe_relative(item.get("path"), "receipt artifact")
        path = root.joinpath(*relative.parts)
        if not _inside(root, path.resolve()) or path.is_symlink() or not path.is_file():
            raise FlowError(f"RECEIPT_ARTIFACT_MISSING: {relative.as_posix()}")
        if path.stat().st_size != item.get("size") or sha256_file(path) != item.get("sha256"):
            raise FlowError(f"RECEIPT_ARTIFACT_DRIFT: {relative.as_posix()}")


def validate_receipt_for_state(
    root: Path, state: Mapping[str, Any], receipt: Mapping[str, Any], stage: str
) -> None:
    validate_contract(receipt, RECEIPT_SCHEMA)
    scope, dataset, task_ids = expected_scope(state)
    if (
        receipt.get("stage") != RECEIPT_STAGE_MAP[stage]
        or receipt.get("status") != "completed"
        or receipt.get("scope") != scope
        or receipt.get("dataset") != dataset
        or receipt.get("task_ids") != task_ids
        or not (receipt.get("integrity") or {}).get("valid")
    ):
        raise FlowError(f"RECEIPT_IDENTITY_INVALID: {stage}")
    validate_receipt_artifacts(root, receipt)


def record_receipt(args: argparse.Namespace) -> dict[str, Any]:
    root = resolve_directory(Path(args.root), "ROOT_INVALID")
    state = load_state(root)
    if args.stage not in RECEIPT_STAGE_MAP:
        raise FlowError(f"RECEIPT_STAGE_UNSUPPORTED: {args.stage}")
    if args.stage not in state["selected_stages"]:
        raise FlowError(f"STAGE_NOT_SELECTED: {args.stage}")
    receipt_path = resolve_regular_file(Path(args.receipt), "RECEIPT_MISSING")
    if not _inside(root, receipt_path):
        raise FlowError("RECEIPT_OUTSIDE_ROOT")
    receipt = read_json(receipt_path, code="RECEIPT_INVALID")
    validate_receipt_for_state(root, state, receipt, args.stage)
    state["artifacts"][args.stage] = {
        "path": str(receipt_path),
        "sha256": sha256_file(receipt_path),
        "size": receipt_path.stat().st_size,
    }
    state["stages"][args.stage] = "COMPLETED"
    if args.stage == "collect-evidence" and "execute" in state["selected_stages"]:
        state["stages"]["execute"] = "COMPLETED"
        state["errors"].pop("execute", None)
    state["errors"].pop(args.stage, None)
    save_state(root, state)
    return {"state": state, "recommended_actions": recommended_actions(state)}


def record_execution_states(args: argparse.Namespace) -> dict[str, Any]:
    root = resolve_directory(Path(args.root), "ROOT_INVALID")
    state = load_state(root)
    if state["scope"] != "unit" or "execute" not in state["selected_stages"]:
        raise FlowError("EXECUTE_STAGE_NOT_SELECTED")
    paths = [resolve_regular_file(Path(value), "EXECUTION_STATE_MISSING") for value in args.state]
    if not paths:
        raise FlowError("EXECUTION_STATE_REQUIRED")
    by_task: dict[str, tuple[Path, dict[str, Any], str, int]] = {}
    expected_dataset = {
        "id": state["identity"]["dataset"]["id"],
        "digest": state["identity"]["dataset"]["digest"],
    }
    for path in paths:
        if not _inside(root, path):
            raise FlowError(f"EXECUTION_STATE_OUTSIDE_ROOT: {path}")
        state_bytes = path.read_bytes()
        state_sha = sha256_bytes(state_bytes)
        try:
            document = json.loads(state_bytes)
        except (ValueError, UnicodeDecodeError) as exc:
            raise FlowError(f"EXECUTION_STATE_INVALID: {path}") from exc
        if not isinstance(document, dict):
            raise FlowError(f"EXECUTION_STATE_INVALID: {path}")
        schema = document.get("schema_version")
        if schema == GENERAL_EXECUTION_STATE_SCHEMA:
            try:
                load_contract_validator("execution_state.py").validate_terminal_execution_state(
                    document, unit_root=root, manifest=manifest_for(root, "unit")[1]
                )
            except (ValueError, OSError) as exc:
                raise FlowError(str(exc)) from exc
        elif schema == EXECUTION_STATE_SCHEMA:
            harness = state["identity"].get("unit", {}).get("harness", {})
            platform = harness.get("platform", "")
            if (harness.get("id") != "astronstudio"
                    or not (platform == "macos" or platform.startswith("macos-"))):
                raise FlowError("EXECUTION_DRIVER_BINDING_MISMATCH: legacy state is AstronStudio macOS only")
        else:
            raise FlowError(f"EXECUTION_STATE_SCHEMA_UNSUPPORTED: {schema}")
        if sha256_file(path) != state_sha:
            raise FlowError(f"EXECUTION_STATE_CHANGED: {path}")
        current_identity = document.get("identity")
        execution = document.get("execution")
        send = document.get("send")
        prompt = document.get("prompt")
        if (
            not isinstance(current_identity, dict)
            or current_identity.get("batch_id") != state["identity"]["batch_id"]
            or current_identity.get("unit_id") != state["identity"]["unit_id"]
            or current_identity.get("task_id") not in state["identity"]["task_ids"]
            or not isinstance(current_identity.get("attempt_id"), str)
            or not current_identity["attempt_id"]
            or document.get("dataset") != expected_dataset
            or document.get("phase") not in EXECUTION_TERMINAL_PHASES
            or not isinstance(execution, dict)
            or execution.get("business_status") not in EXECUTION_BUSINESS_STATUSES
            or not execution.get("finished_at")
            or not isinstance(send, dict)
            or send.get("dispatch_attempt_count") not in {0, 1}
            or not isinstance(prompt, dict)
        ):
            raise FlowError(f"EXECUTION_STATE_NOT_TERMINAL: {path}")
        if (
            (prompt.get("send_status") == "sent" and send.get("dispatch_attempt_count") != 1)
            or (send.get("dispatch_attempt_count") == 1 and prompt.get("send_status") != "sent")
        ):
            raise FlowError(f"EXECUTION_DISPATCH_INVARIANT_INVALID: {path}")
        task_id = current_identity["task_id"]
        if task_id in by_task:
            raise FlowError(f"EXECUTION_STATE_TASK_DUPLICATE: {task_id}")
        by_task[task_id] = (path, document, state_sha, len(state_bytes))
    if list(by_task) != state["identity"]["task_ids"]:
        raise FlowError(
            "EXECUTION_STATE_SCOPE_MISMATCH: "
            f"expected={state['identity']['task_ids']}, actual={list(by_task)}"
        )
    state["artifacts"]["execute"] = {
        "states": [
            {
                "task_id": task_id,
                "attempt_id": by_task[task_id][1]["identity"]["attempt_id"],
                "phase": by_task[task_id][1]["phase"],
                "business_status": by_task[task_id][1]["execution"]["business_status"],
                "path": str(by_task[task_id][0]),
                "sha256": by_task[task_id][2],
                "size": by_task[task_id][3],
            }
            for task_id in state["identity"]["task_ids"]
        ]
    }
    state["stages"]["execute"] = "COMPLETED"
    state["errors"].pop("execute", None)
    save_state(root, state)
    return {"state": state, "recommended_actions": recommended_actions(state)}


def validate_submission(
    submission_path: Path,
    *,
    identity: Mapping[str, Any],
    require_score_files: bool = True,
) -> dict[str, Any]:
    submission_path = resolve_regular_file(submission_path, "SUBMISSION_MISSING")
    submission = read_json(submission_path, code="SUBMISSION_INVALID")
    validate_contract(submission, SUBMISSION_SCHEMA)
    expected_scope = {
        "batch_id": identity["batch_id"],
        "unit_id": identity["unit_id"],
    }
    expected_dataset = {
        "id": identity["dataset"]["id"],
        "digest": identity["dataset"]["digest"],
    }
    if (
        submission.get("scope") != expected_scope
        or submission.get("dataset") != expected_dataset
        or submission.get("task_ids") != identity["task_ids"]
        or submission.get("task_count") != len(identity["task_ids"])
        or not (submission.get("integrity") or {}).get("valid")
    ):
        raise FlowError("SUBMISSION_IDENTITY_INVALID")
    if require_score_files:
        root = submission_path.parent
        for task in submission["tasks"]:
            score_path = task.get("score_path")
            score_sha = task.get("score_sha256")
            if score_path is None:
                if score_sha is not None or task.get("score_status") != "unscored":
                    raise FlowError(f"SUBMISSION_SCORE_REFERENCE_INVALID: {task['task_id']}")
                continue
            relative = safe_relative(score_path, "submission score_path")
            path = root.joinpath(*relative.parts)
            if not _inside(root, path.resolve()) or path.is_symlink() or not path.is_file():
                raise FlowError(f"SUBMISSION_SCORE_MISSING: {task['task_id']}")
            if sha256_file(path) != score_sha:
                raise FlowError(f"SUBMISSION_SCORE_DRIFT: {task['task_id']}")
    return submission


def record_submission(args: argparse.Namespace) -> dict[str, Any]:
    root = resolve_directory(Path(args.root), "ROOT_INVALID")
    state = load_state(root)
    if state["scope"] != "unit" or "score" not in state["selected_stages"]:
        raise FlowError("SCORE_STAGE_NOT_SELECTED")
    path = resolve_regular_file(Path(args.submission), "SUBMISSION_MISSING")
    submission = validate_submission(path, identity=state["identity"])
    state["artifacts"]["score"] = {
        "path": str(path),
        "sha256": sha256_file(path),
        "size": path.stat().st_size,
        "status_counts": dict(Counter(item["score_status"] for item in submission["tasks"])),
    }
    state["stages"]["score"] = "COMPLETED"
    state["errors"].pop("score", None)
    save_state(root, state)
    return {"state": state, "recommended_actions": recommended_actions(state)}


def verify_recorded_artifacts(root: Path, state: dict[str, Any]) -> None:
    for stage, artifact in list(state.get("artifacts", {}).items()):
        if stage == "imports":
            continue
        if stage == "execute" and isinstance(artifact, dict):
            states = artifact.get("states")
            if not isinstance(states, list) or not states:
                raise FlowError("EXECUTION_STATE_LOCK_INVALID")
            for item in states:
                if not isinstance(item, dict):
                    raise FlowError("EXECUTION_STATE_LOCK_INVALID")
                validate_file_lock(item, f"execute:{item.get('task_id')}")
            continue
        if not isinstance(artifact, dict) or not isinstance(artifact.get("path"), str):
            if stage == "package" and isinstance(artifact, dict):
                archive = Path(str(artifact.get("archive", "")))
                receipt = Path(str(artifact.get("receipt", "")))
                if (
                    not archive.is_file()
                    or not receipt.is_file()
                    or sha256_file(archive) != artifact.get("archive_sha256")
                    or sha256_file(receipt) != artifact.get("receipt_sha256")
                ):
                    raise FlowError("PACKAGE_ARTIFACT_DRIFT")
                continue
            raise FlowError(f"STATE_ARTIFACT_INVALID: {stage}")
        validate_file_lock(artifact, stage)


def recommended_actions(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    statuses = state["stages"]
    artifacts = state.get("artifacts", {})
    for stage in state["selected_stages"]:
        status_value = statuses[stage]
        if status_value == "COMPLETED":
            continue
        if status_value == "NEEDS_HUMAN":
            actions.append({"stage": stage, "status": status_value, "action": "WAIT_FOR_HUMAN"})
            continue
        if status_value == "RUNNING":
            actions.append({"stage": stage, "status": status_value, "action": "RESUME_STAGE"})
            continue
        blocked_by = None
        if stage == "collect-evidence" and "execute" in state["selected_stages"] and statuses["execute"] != "COMPLETED":
            blocked_by = "execute receipt"
        elif stage == "score" and statuses.get("collect-evidence") != "COMPLETED" and not artifacts.get("collect-evidence"):
            blocked_by = "collect-evidence receipt"
        elif stage == "package" and statuses.get("score") != "COMPLETED" and not artifacts.get("score"):
            blocked_by = "submission.json"
        elif stage == "report" and "import-return" in state["selected_stages"] and statuses["import-return"] != "COMPLETED":
            blocked_by = "selected imports for every unit"
        actions.append(
            {
                "stage": stage,
                "status": status_value,
                "action": "WAIT_FOR_PREREQUISITE" if blocked_by else f"RUN_{stage.upper().replace('-', '_')}",
                "blocked_by": blocked_by,
            }
        )
    return actions


def command_status(args: argparse.Namespace) -> dict[str, Any]:
    root = resolve_directory(Path(args.root), "ROOT_INVALID")
    state = load_state(root)
    verify_recorded_artifacts(root, state)
    if state["scope"] == "batch":
        sync_import_stage(root, state)
    return {"state": state, "recommended_actions": recommended_actions(state)}


def safe_symlink_target(member_path: PurePosixPath, target: str) -> None:
    if not target or "\\" in target or "\0" in target:
        raise FlowError(f"SYMLINK_TARGET_INVALID: {member_path}: {target!r}")
    target_path = PurePosixPath(target)
    if target_path.is_absolute():
        raise FlowError(f"SYMLINK_TARGET_INVALID: {member_path}: absolute target")
    parts = list(member_path.parent.parts)
    for part in target_path.parts:
        if part in {"", "."}:
            continue
        if part == "..":
            if not parts:
                raise FlowError(f"SYMLINK_TARGET_ESCAPE: {member_path}: {target}")
            parts.pop()
        else:
            parts.append(part)


def reject_secret(path: Path) -> None:
    lowered = path.name.casefold()
    if lowered in SECRET_NAMES or lowered.startswith(".env.") or lowered.endswith(SECRET_SUFFIXES):
        raise FlowError(f"SENSITIVE_FILE_REJECTED: {path}")


def package_entry(source: Path, archive_path: PurePosixPath) -> PackageEntry:
    archive_text = safe_relative(archive_path.as_posix(), "package entry").as_posix()
    info = source.lstat()
    mode = stat.S_IMODE(info.st_mode)
    if stat.S_ISLNK(info.st_mode):
        target = os.readlink(source)
        safe_symlink_target(archive_path, target)
        data = target.encode("utf-8", errors="surrogateescape")
        return PackageEntry(archive_text, "symlink", mode or 0o777, data, target)
    if stat.S_ISDIR(info.st_mode):
        return PackageEntry(archive_text, "directory", mode or 0o755, b"")
    if stat.S_ISREG(info.st_mode):
        reject_secret(source)
        return PackageEntry(archive_text, "file", mode or 0o644, source.read_bytes())
    raise FlowError(f"PACKAGE_ENTRY_TYPE_UNSUPPORTED: {source}")


def walk_tree(
    source: Path,
    archive_prefix: PurePosixPath,
    *,
    exclude_runtime: bool = False,
) -> list[PackageEntry]:
    if source.is_symlink():
        return [package_entry(source, archive_prefix)]
    if not source.exists():
        return []
    if source.is_file():
        return [package_entry(source, archive_prefix)]
    entries: list[PackageEntry] = [package_entry(source, archive_prefix)]

    def visit(directory: Path, prefix: PurePosixPath, depth: int) -> None:
        try:
            children = sorted(os.scandir(directory), key=lambda item: item.name)
        except OSError as exc:
            raise FlowError(f"PACKAGE_TREE_UNREADABLE: {directory}: {exc}") from exc
        for child in children:
            if child.name in EXCLUDED_NAMES or child.name.endswith(".pyc"):
                continue
            if exclude_runtime and depth == 0 and child.name == "runtime":
                continue
            child_path = Path(child.path)
            child_prefix = prefix / child.name
            entry = package_entry(child_path, child_prefix)
            entries.append(entry)
            if entry.kind == "directory":
                visit(child_path, child_prefix, depth + 1)

    visit(source, archive_prefix, 0)
    return entries


def collect_package_entries(
    unit_root: Path,
    orchestration_root: Path,
    submission: Mapping[str, Any],
) -> list[PackageEntry]:
    entries: list[PackageEntry] = []
    for relative in ("manifest.json", "receipts", "evidence"):
        source = unit_root / relative
        if not source.exists() and relative in {"manifest.json", "receipts"}:
            raise FlowError(f"PACKAGE_SOURCE_MISSING: {source}")
        entries.extend(walk_tree(source, PurePosixPath("unit") / relative))
    entries.extend(
        walk_tree(
            orchestration_root / "submission.json",
            PurePosixPath("scoring/submission.json"),
        )
    )
    execution_records = orchestration_root / "execution-records"
    if not execution_records.is_dir() or execution_records.is_symlink():
        raise FlowError(f"PACKAGE_EXECUTION_RECORDS_MISSING: {execution_records}")
    entries.extend(walk_tree(execution_records, PurePosixPath("scoring/execution-records")))
    attempt_roots: set[PurePosixPath] = set()
    for task in submission["tasks"]:
        score_path = task.get("score_path")
        if score_path is None:
            continue
        relative = safe_relative(score_path, "submission score path")
        if len(relative.parts) < 3 or relative.parts[0] != "attempts":
            raise FlowError(f"SUBMISSION_SCORE_PATH_INVALID: {relative}")
        attempt_roots.add(PurePosixPath(*relative.parts[:2]))
    for relative in sorted(attempt_roots, key=lambda item: item.as_posix()):
        source = orchestration_root.joinpath(*relative.parts)
        if not source.is_dir() or source.is_symlink():
            raise FlowError(f"PACKAGE_ATTEMPT_MISSING: {relative}")
        entries.extend(
            walk_tree(source, PurePosixPath("scoring") / relative, exclude_runtime=True)
        )
    paths = [entry.path for entry in entries]
    duplicates = sorted(path for path, count in Counter(paths).items() if count > 1)
    if duplicates:
        raise FlowError(f"PACKAGE_ENTRY_DUPLICATE: {duplicates}")
    return sorted(entries, key=lambda item: item.path)


def validate_collect_receipt(unit_root: Path, identity: Mapping[str, Any]) -> tuple[Path, dict[str, Any]]:
    path = unit_root / "receipts/collect-evidence-receipt.json"
    receipt = read_json(path, code="COLLECT_RECEIPT_INVALID")
    validate_contract(receipt, RECEIPT_SCHEMA)
    if (
        receipt.get("stage") != "collect-evidence"
        or receipt.get("status") != "completed"
        or receipt.get("scope") != {"batch_id": identity["batch_id"], "unit_id": identity["unit_id"]}
        or receipt.get("dataset") != {"id": identity["dataset"]["id"], "digest": identity["dataset"]["digest"]}
        or receipt.get("task_ids") != identity["task_ids"]
        or not (receipt.get("integrity") or {}).get("valid")
    ):
        raise FlowError("COLLECT_RECEIPT_IDENTITY_INVALID")
    validate_receipt_artifacts(unit_root, receipt)
    return path, receipt


def return_package_id(document: Mapping[str, Any]) -> str:
    digest_input = {
        "identity": document.get("identity"),
        "sources": document.get("sources"),
        "entries": document.get("entries"),
    }
    return sha256_bytes(canonical_json_bytes(digest_input))


def zip_info(name: str, kind: str, mode: int) -> zipfile.ZipInfo:
    output_name = name + ("/" if kind == "directory" and not name.endswith("/") else "")
    info = zipfile.ZipInfo(output_name, date_time=FIXED_ZIP_TIMESTAMP)
    info.create_system = 3
    info.compress_type = zipfile.ZIP_STORED
    info.flag_bits |= 0x800
    if kind == "directory":
        info.external_attr = (stat.S_IFDIR | mode) << 16 | 0x10
    elif kind == "symlink":
        info.external_attr = (stat.S_IFLNK | mode) << 16
    else:
        info.external_attr = (stat.S_IFREG | mode) << 16
    return info


def write_return_zip(
    path: Path,
    root_name: str,
    entries: Sequence[PackageEntry],
    manifest_bytes: bytes,
    receipt_bytes: bytes,
) -> None:
    with zipfile.ZipFile(path, "x", compression=zipfile.ZIP_STORED) as archive:
        for entry in entries:
            name = f"{root_name}/{entry.path}"
            archive.writestr(zip_info(name, entry.kind, entry.mode), entry.data)
        for relative, data in (
            ("package-manifest.json", manifest_bytes),
            ("receipts/package-receipt.json", receipt_bytes),
        ):
            archive.writestr(zip_info(f"{root_name}/{relative}", "file", 0o644), data)


def build_package_receipt(
    package_manifest: Mapping[str, Any],
    manifest_bytes: bytes,
    submission: Mapping[str, Any],
    submission_bytes: bytes,
) -> dict[str, Any]:
    identity = package_manifest["identity"]
    return {
        "schema_id": RECEIPT_SCHEMA,
        "schema_version": 1,
        "scope": {"batch_id": identity["batch_id"], "unit_id": identity["unit_id"]},
        "dataset": {"id": identity["dataset"]["id"], "digest": identity["dataset"]["digest"]},
        "stage": "package",
        "status": "completed",
        "created_at": submission["created_at"],
        "task_ids": identity["task_ids"],
        "tasks": [
            {
                "task_id": item["task_id"],
                "attempt_id": item["execution_attempt_id"],
                "status": "completed",
            }
            for item in submission["tasks"]
        ],
        "artifacts": [
            {
                "path": "package-manifest.json",
                "sha256": sha256_bytes(manifest_bytes),
                "size": len(manifest_bytes),
            },
            {
                "path": "scoring/submission.json",
                "sha256": sha256_bytes(submission_bytes),
                "size": len(submission_bytes),
            },
        ],
        "integrity": {
            "scope_matches": True,
            "identities_match": True,
            "hashes_verified": True,
            "valid": True,
        },
        "error": None,
    }


def complete_unit_package_state(
    unit_root: Path,
    state: dict[str, Any] | None,
    *,
    collect_path: Path,
    submission_path: Path,
    submission: Mapping[str, Any],
    archive_path: Path,
    receipt_path: Path,
    package_id: str,
) -> None:
    if state is None:
        return
    if "collect-evidence" in state["selected_stages"]:
        state["artifacts"]["collect-evidence"] = {
            "path": str(collect_path),
            "sha256": sha256_file(collect_path),
            "size": collect_path.stat().st_size,
        }
        state["stages"]["collect-evidence"] = "COMPLETED"
    if "execute" in state["selected_stages"]:
        state["stages"]["execute"] = "COMPLETED"
    if "score" in state["selected_stages"]:
        state["artifacts"]["score"] = {
            "path": str(submission_path),
            "sha256": sha256_file(submission_path),
            "size": submission_path.stat().st_size,
            "status_counts": dict(
                Counter(item["score_status"] for item in submission["tasks"])
            ),
        }
        state["stages"]["score"] = "COMPLETED"
    state["artifacts"]["package"] = {
        "archive": str(archive_path),
        "archive_sha256": sha256_file(archive_path),
        "receipt": str(receipt_path),
        "receipt_sha256": sha256_file(receipt_path),
        "package_id": package_id,
    }
    state["stages"]["package"] = "COMPLETED"
    for stage in ("execute", "collect-evidence", "score", "package"):
        state["errors"].pop(stage, None)
    save_state(unit_root, state)


def package_return(args: argparse.Namespace) -> dict[str, Any]:
    unit_root = resolve_directory(Path(args.unit_root), "UNIT_ROOT_INVALID")
    orchestration_root = resolve_directory(
        Path(args.orchestration_root), "ORCHESTRATION_ROOT_INVALID"
    )
    output_dir = Path(args.output_dir).expanduser().resolve()
    _, unit_manifest = manifest_for(unit_root, "unit")
    identity = identity_from_manifest(unit_manifest, "unit")
    collect_path, _ = validate_collect_receipt(unit_root, identity)
    submission_path = orchestration_root / "submission.json"
    submission = validate_submission(submission_path, identity=identity)
    run_state: dict[str, Any] | None = None
    if state_path(unit_root).is_file():
        run_state = load_state(unit_root)
        if run_state["scope"] != "unit" or "package" not in run_state["selected_stages"]:
            raise FlowError("PACKAGE_STAGE_NOT_SELECTED")
        recorded_score = run_state["artifacts"].get("score")
        submission_sha = sha256_file(submission_path)
        if recorded_score is not None and (
            recorded_score.get("path") != str(submission_path)
            or recorded_score.get("sha256") != submission_sha
            or recorded_score.get("size") != submission_path.stat().st_size
        ):
            raise FlowError("PACKAGE_SUBMISSION_STATE_MISMATCH")
    entries = collect_package_entries(unit_root, orchestration_root, submission)
    source_submission = submission_path.read_bytes()
    document: dict[str, Any] = {
        "schema_id": RETURN_SCHEMA,
        "schema_version": 1,
        "contract_version": CONTRACT_VERSION,
        "bundle_protocol": BUNDLE_PROTOCOL,
        "package_kind": "return",
        "package_id": None,
        "identity": {
            "batch_id": identity["batch_id"],
            "unit_id": identity["unit_id"],
            "dataset": identity["dataset"],
            "release": identity["release"],
            "task_ids": identity["task_ids"],
        },
        "sources": {
            "unit_manifest_sha256": sha256_file(unit_root / "manifest.json"),
            "collect_receipt_sha256": sha256_file(collect_path),
            "submission_sha256": sha256_bytes(source_submission),
        },
        "entry_count": len(entries),
        "entries": [entry.manifest_row() for entry in entries],
    }
    document["package_id"] = return_package_id(document)
    manifest_bytes = pretty_json_bytes(document)
    receipt = build_package_receipt(document, manifest_bytes, submission, source_submission)
    validate_contract(receipt, RECEIPT_SCHEMA)
    receipt_bytes = pretty_json_bytes(receipt)
    root_name = f"{identity['batch_id']}__{identity['unit_id']}__return__{document['package_id'][:16]}"
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / f"{root_name}.zip"
    receipt_path = output_dir / f"{root_name}__package-receipt.json"
    if archive_path.exists() or receipt_path.exists():
        if archive_path.is_file() and (
            not receipt_path.exists()
            or (receipt_path.is_file() and receipt_path.read_bytes() == receipt_bytes)
        ):
            verified = inspect_return_archive(
                archive_path, receipt_path if receipt_path.is_file() else None
            )
            if verified["receipt_bytes"] != receipt_bytes:
                raise FlowError(f"OUTPUT_CONFLICT: {archive_path}")
            if not receipt_path.exists():
                write_new_json(receipt_path, receipt)
            complete_unit_package_state(
                unit_root,
                run_state,
                collect_path=collect_path,
                submission_path=submission_path,
                submission=submission,
                archive_path=archive_path,
                receipt_path=receipt_path,
                package_id=document["package_id"],
            )
            return {
                "created": False,
                "idempotent": True,
                "archive": str(archive_path),
                "archive_sha256": sha256_file(archive_path),
                "receipt": str(receipt_path),
                "package_id": verified["manifest"]["package_id"],
            }
        raise FlowError(f"OUTPUT_EXISTS: {archive_path} / {receipt_path}")
    temporary_archive = output_dir / f".{archive_path.name}.{uuid.uuid4().hex}.tmp"
    try:
        write_return_zip(temporary_archive, root_name, entries, manifest_bytes, receipt_bytes)
        inspect_return_archive(temporary_archive, None)
        os.replace(temporary_archive, archive_path)
        write_new_json(receipt_path, receipt)
    finally:
        temporary_archive.unlink(missing_ok=True)
    complete_unit_package_state(
        unit_root,
        run_state,
        collect_path=collect_path,
        submission_path=submission_path,
        submission=submission,
        archive_path=archive_path,
        receipt_path=receipt_path,
        package_id=document["package_id"],
    )
    return {
        "created": True,
        "idempotent": False,
        "archive": str(archive_path),
        "archive_sha256": sha256_file(archive_path),
        "receipt": str(receipt_path),
        "package_id": document["package_id"],
        "entry_count": len(entries),
    }


def zip_kind(info: zipfile.ZipInfo) -> str:
    mode = info.external_attr >> 16
    if info.is_dir() or stat.S_ISDIR(mode):
        return "directory"
    if stat.S_ISLNK(mode):
        return "symlink"
    if mode and not stat.S_ISREG(mode):
        return "unsupported"
    return "file"


def load_json_bytes(data: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise FlowError(f"JSON_INVALID: {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise FlowError(f"JSON_INVALID: {label}: top level must be object")
    return value


def validate_return_manifest(manifest: Mapping[str, Any]) -> None:
    if (
        manifest.get("schema_id") != RETURN_SCHEMA
        or manifest.get("schema_version") != 1
        or manifest.get("contract_version") != CONTRACT_VERSION
        or manifest.get("bundle_protocol") != BUNDLE_PROTOCOL
        or manifest.get("package_kind") != "return"
    ):
        raise FlowError("RETURN_MANIFEST_INCOMPATIBLE")
    identity = manifest.get("identity")
    sources = manifest.get("sources")
    entries = manifest.get("entries")
    if not isinstance(identity, dict) or not isinstance(sources, dict) or not isinstance(entries, list):
        raise FlowError("RETURN_MANIFEST_INVALID")
    identifier(identity.get("batch_id"), "return.batch_id")
    identifier(identity.get("unit_id"), "return.unit_id")
    task_ids = identity.get("task_ids")
    if not isinstance(task_ids, list) or not task_ids or len(task_ids) != len(set(task_ids)):
        raise FlowError("RETURN_TASK_SCOPE_INVALID")
    if manifest.get("entry_count") != len(entries):
        raise FlowError("RETURN_ENTRY_COUNT_INVALID")
    if manifest.get("package_id") != return_package_id(manifest):
        raise FlowError("RETURN_PACKAGE_ID_MISMATCH")


def inspect_return_archive(
    archive_path: Path, sidecar_receipt: Path | None
) -> dict[str, Any]:
    archive_path = resolve_regular_file(archive_path, "RETURN_ARCHIVE_INVALID")
    try:
        archive = zipfile.ZipFile(archive_path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise FlowError(f"RETURN_ARCHIVE_INVALID: {archive_path}") from exc
    with archive:
        infos = archive.infolist()
        names = [info.filename.rstrip("/") for info in infos]
        duplicates = sorted(name for name, count in Counter(names).items() if count > 1)
        if duplicates:
            raise FlowError(f"ARCHIVE_MEMBER_DUPLICATE: {duplicates}")
        roots: set[str] = set()
        members: dict[str, tuple[zipfile.ZipInfo, bytes]] = {}
        for info in infos:
            raw = info.filename.rstrip("/")
            relative = safe_relative(raw, "archive member")
            roots.add(relative.parts[0])
            kind = zip_kind(info)
            if kind == "unsupported":
                raise FlowError(f"ARCHIVE_MEMBER_TYPE_INVALID: {raw}")
            data = archive.read(info)
            if kind == "directory" and data:
                raise FlowError(f"ARCHIVE_DIRECTORY_NOT_EMPTY: {raw}")
            members[raw] = (info, data)
        if len(roots) != 1:
            raise FlowError("ARCHIVE_ROOT_INVALID")
        root_name = next(iter(roots))
        prefix = f"{root_name}/"
        stripped = {
            name[len(prefix):]: value
            for name, value in members.items()
            if name.startswith(prefix)
        }
        if len(stripped) != len(members):
            raise FlowError("ARCHIVE_ROOT_INVALID")
        try:
            manifest_info, manifest_bytes = stripped["package-manifest.json"]
            receipt_info, receipt_bytes = stripped["receipts/package-receipt.json"]
        except KeyError as exc:
            raise FlowError("RETURN_CONTROL_FILE_MISSING") from exc
        if zip_kind(manifest_info) != "file" or zip_kind(receipt_info) != "file":
            raise FlowError("RETURN_CONTROL_FILE_TYPE_INVALID")
        manifest = load_json_bytes(manifest_bytes, "package-manifest.json")
        receipt = load_json_bytes(receipt_bytes, "package-receipt.json")
        validate_return_manifest(manifest)
        validate_contract(receipt, RECEIPT_SCHEMA)
        identity = manifest["identity"]
        expected_root = (
            f"{identity['batch_id']}__{identity['unit_id']}__return__"
            f"{manifest['package_id'][:16]}"
        )
        if root_name != expected_root:
            raise FlowError(f"ARCHIVE_ROOT_IDENTITY_MISMATCH: {root_name}")
        expected_names = {"package-manifest.json", "receipts/package-receipt.json"}
        seen: set[str] = set()
        for row in manifest["entries"]:
            if not isinstance(row, dict):
                raise FlowError("RETURN_ENTRY_INVALID")
            relative = safe_relative(row.get("path"), "return entry").as_posix()
            if relative in seen:
                raise FlowError(f"RETURN_ENTRY_DUPLICATE: {relative}")
            seen.add(relative)
            expected_names.add(relative)
            try:
                info, data = stripped[relative]
            except KeyError as exc:
                raise FlowError(f"RETURN_ENTRY_MISSING: {relative}") from exc
            kind = zip_kind(info)
            mode = stat.S_IMODE(info.external_attr >> 16)
            if (
                row.get("kind") != kind
                or row.get("mode") != f"{mode:04o}"
                or row.get("size") != len(data)
                or row.get("sha256") != sha256_bytes(data)
            ):
                raise FlowError(f"RETURN_ENTRY_DRIFT: {relative}")
            if kind == "symlink":
                try:
                    target = data.decode("utf-8", errors="surrogateescape")
                except UnicodeError as exc:
                    raise FlowError(f"SYMLINK_TARGET_INVALID: {relative}") from exc
                if row.get("link_target") != target:
                    raise FlowError(f"SYMLINK_TARGET_DRIFT: {relative}")
                safe_symlink_target(PurePosixPath(relative), target)
            elif "link_target" in row:
                raise FlowError(f"RETURN_ENTRY_INVALID: unexpected link_target: {relative}")
        unexpected = sorted(set(stripped) - expected_names)
        missing = sorted(expected_names - set(stripped))
        if unexpected or missing:
            raise FlowError(f"RETURN_MEMBER_SET_MISMATCH: unexpected={unexpected}, missing={missing}")
        if zip_kind(stripped["scoring/submission.json"][0]) != "file":
            raise FlowError("RETURN_SUBMISSION_TYPE_INVALID")
        artifacts = {item["path"]: item for item in receipt.get("artifacts", [])}
        for relative, data in (
            ("package-manifest.json", manifest_bytes),
            ("scoring/submission.json", stripped["scoring/submission.json"][1]),
        ):
            artifact = artifacts.get(relative)
            if (
                artifact is None
                or artifact.get("size") != len(data)
                or artifact.get("sha256") != sha256_bytes(data)
            ):
                raise FlowError(f"PACKAGE_RECEIPT_ARTIFACT_INVALID: {relative}")
        if (
            receipt.get("stage") != "package"
            or receipt.get("status") != "completed"
            or receipt.get("scope") != {"batch_id": identity["batch_id"], "unit_id": identity["unit_id"]}
            or receipt.get("task_ids") != identity["task_ids"]
        ):
            raise FlowError("PACKAGE_RECEIPT_IDENTITY_INVALID")
        if sidecar_receipt is not None:
            sidecar = resolve_regular_file(sidecar_receipt, "PACKAGE_RECEIPT_INVALID")
            if sidecar.read_bytes() != receipt_bytes:
                raise FlowError("PACKAGE_RECEIPT_SIDECAR_MISMATCH")
        submission = load_json_bytes(stripped["scoring/submission.json"][1], "submission.json")
        validate_contract(submission, SUBMISSION_SCHEMA)
        return {
            "archive": archive_path,
            "archive_sha256": sha256_file(archive_path),
            "root_name": root_name,
            "manifest": manifest,
            "manifest_bytes": manifest_bytes,
            "receipt": receipt,
            "receipt_bytes": receipt_bytes,
            "submission": submission,
            "members": stripped,
        }


def validate_return_against_batch(
    verified: Mapping[str, Any], batch_manifest: Mapping[str, Any]
) -> dict[str, Any]:
    identity = verified["manifest"]["identity"]
    units = [
        item
        for item in batch_manifest["units"]
        if isinstance(item, dict) and item.get("unit_id") == identity.get("unit_id")
    ]
    if len(units) != 1:
        raise FlowError(f"RETURN_UNIT_NOT_IN_BATCH: {identity.get('unit_id')}")
    unit = units[0]
    if (
        identity.get("batch_id") != batch_manifest.get("batch_id")
        or identity.get("dataset") != batch_manifest.get("dataset")
        or identity.get("release") != batch_manifest.get("release")
        or identity.get("task_ids") != unit.get("task_ids")
    ):
        raise FlowError("RETURN_BATCH_IDENTITY_MISMATCH")
    submission = verified["submission"]
    if (
        submission.get("scope") != {"batch_id": identity["batch_id"], "unit_id": identity["unit_id"]}
        or submission.get("dataset") != {"id": identity["dataset"]["id"], "digest": identity["dataset"]["digest"]}
        or submission.get("task_ids") != identity["task_ids"]
        or not (submission.get("integrity") or {}).get("valid")
    ):
        raise FlowError("RETURN_SUBMISSION_IDENTITY_MISMATCH")
    return unit


def import_index_path(batch_root: Path) -> Path:
    return batch_root / ".general-e2e/run-general-e2e-import-index.json"


def load_import_index(batch_root: Path, batch_manifest: Mapping[str, Any]) -> dict[str, Any]:
    path = import_index_path(batch_root)
    if not path.is_file():
        return {
            "schema_version": IMPORT_INDEX_SCHEMA,
            "revision": 1,
            "batch_id": batch_manifest["batch_id"],
            "units": {},
            "updated_at": utc_now(),
        }
    index = read_json(path, code="IMPORT_INDEX_INVALID")
    if (
        index.get("schema_version") != IMPORT_INDEX_SCHEMA
        or index.get("revision") != 1
        or index.get("batch_id") != batch_manifest["batch_id"]
        or not isinstance(index.get("units"), dict)
    ):
        raise FlowError("IMPORT_INDEX_INCOMPATIBLE")
    return index


def extract_verified_return(verified: Mapping[str, Any], destination: Path) -> None:
    members = verified["members"]
    rows = {item["path"]: item for item in verified["manifest"]["entries"]}
    directory_modes: list[tuple[Path, int]] = []
    control = {
        "package-manifest.json": ("file", verified["manifest_bytes"], 0o644, None),
        "receipts/package-receipt.json": ("file", verified["receipt_bytes"], 0o644, None),
    }
    for relative, (kind, data, mode, target) in control.items():
        target_path = destination.joinpath(*PurePosixPath(relative).parts)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with target_path.open("xb") as handle:
            handle.write(data)
        os.chmod(target_path, mode)
    for relative in sorted(rows, key=lambda item: (len(PurePosixPath(item).parts), item)):
        row = rows[relative]
        info, data = members[relative]
        kind = row["kind"]
        target_path = destination.joinpath(*PurePosixPath(relative).parts)
        if not _inside(destination, target_path.parent.resolve()):
            raise FlowError(f"IMPORT_PATH_ESCAPE: {relative}")
        if kind == "directory":
            target_path.mkdir(parents=True, exist_ok=False)
            # Keep directories writable until all descendants and symlinks are
            # materialized.  Return packages intentionally contain read-only
            # candidate trees (for example 0555); applying those modes during
            # the depth-first extraction prevents later child files from
            # being created on POSIX hosts.
            directory_modes.append(
                (target_path, stat.S_IMODE(info.external_attr >> 16))
            )
        elif kind == "file":
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with target_path.open("xb") as handle:
                handle.write(data)
            os.chmod(target_path, stat.S_IMODE(info.external_attr >> 16))
    for relative in sorted(rows):
        row = rows[relative]
        if row["kind"] != "symlink":
            continue
        target_path = destination.joinpath(*PurePosixPath(relative).parts)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        safe_symlink_target(PurePosixPath(relative), row["link_target"])
        os.symlink(row["link_target"], target_path)
    for target_path, mode in sorted(
        directory_modes,
        key=lambda item: len(item[0].relative_to(destination).parts),
        reverse=True,
    ):
        os.chmod(target_path, mode)


def import_receipt_document(
    batch_root: Path,
    content_root: Path,
    final_target: Path,
    verified: Mapping[str, Any],
    imported_at: str,
) -> dict[str, Any]:
    identity = verified["manifest"]["identity"]
    package_receipt = verified["receipt"]
    manifest_source = content_root / "package-manifest.json"
    submission_source = content_root / "scoring/submission.json"
    manifest_target = final_target / "package-manifest.json"
    submission_target = final_target / "scoring/submission.json"
    return {
        "schema_id": RECEIPT_SCHEMA,
        "schema_version": 1,
        "scope": {"batch_id": identity["batch_id"], "unit_id": identity["unit_id"]},
        "dataset": {"id": identity["dataset"]["id"], "digest": identity["dataset"]["digest"]},
        "stage": "import-return",
        "status": "completed",
        "created_at": imported_at,
        "task_ids": identity["task_ids"],
        "tasks": package_receipt["tasks"],
        "artifacts": [
            {
                "path": manifest_target.relative_to(batch_root).as_posix(),
                "sha256": sha256_file(manifest_source),
                "size": manifest_source.stat().st_size,
            },
            {
                "path": submission_target.relative_to(batch_root).as_posix(),
                "sha256": sha256_file(submission_source),
                "size": submission_source.stat().st_size,
            },
        ],
        "integrity": {
            "scope_matches": True,
            "identities_match": True,
            "hashes_verified": True,
            "valid": True,
        },
        "error": None,
    }


def import_return(args: argparse.Namespace) -> dict[str, Any]:
    batch_root = resolve_directory(Path(args.batch_root), "BATCH_ROOT_INVALID")
    _, batch_manifest = manifest_for(batch_root, "batch")
    if state_path(batch_root).is_file():
        run_state = load_state(batch_root)
        if run_state["scope"] != "batch" or "import-return" not in run_state["selected_stages"]:
            raise FlowError("IMPORT_STAGE_NOT_SELECTED")
    sidecar = Path(args.receipt) if args.receipt else None
    verified = inspect_return_archive(Path(args.archive), sidecar)
    validate_return_against_batch(verified, batch_manifest)
    identity = verified["manifest"]["identity"]
    unit_id = identity["unit_id"]
    package_id = verified["manifest"]["package_id"]
    archive_sha = verified["archive_sha256"]
    index = load_import_index(batch_root, batch_manifest)
    unit_index = index["units"].setdefault(
        unit_id,
        {"logical_identity_sha256": sha256_bytes(canonical_json_bytes(identity)), "selected_package_id": None, "conflict": False, "imports": []},
    )
    if unit_index.get("logical_identity_sha256") != sha256_bytes(canonical_json_bytes(identity)):
        raise FlowError("IMPORT_LOGICAL_IDENTITY_MISMATCH")
    for item in unit_index["imports"]:
        if item.get("package_id") == package_id and item.get("archive_sha256") != archive_sha:
            raise FlowError("IMPORT_PACKAGE_ID_ARCHIVE_MISMATCH")
        if item.get("archive_sha256") == archive_sha:
            target = batch_root / item["target"]
            if not target.is_dir() or sha256_file(target / "package-manifest.json") != sha256_bytes(verified["manifest_bytes"]):
                raise FlowError("IDEMPOTENT_IMPORT_DRIFT")
            return {
                "imported": False,
                "idempotent": True,
                "conflict": unit_index["conflict"],
                "selected_package_id": unit_index["selected_package_id"],
                "target": str(target),
                "package_id": package_id,
            }
    returns_root = batch_root / "returns" / unit_id
    returns_root.mkdir(parents=True, exist_ok=True)
    target = returns_root / package_id
    imported_at = utc_now()
    if target.exists() or target.is_symlink():
        existing_manifest = target / "package-manifest.json"
        existing_receipt = target / "receipts/import-return-receipt.json"
        if (
            not target.is_dir()
            or target.is_symlink()
            or not existing_manifest.is_file()
            or existing_manifest.is_symlink()
            or existing_manifest.read_bytes() != verified["manifest_bytes"]
            or not existing_receipt.is_file()
            or existing_receipt.is_symlink()
        ):
            raise FlowError(f"IMPORT_TARGET_EXISTS: {target}")
        recovered_receipt = read_json(existing_receipt, code="IMPORT_RECEIPT_INVALID")
        validate_contract(recovered_receipt, RECEIPT_SCHEMA)
        if recovered_receipt.get("stage") != "import-return":
            raise FlowError(f"IMPORT_TARGET_EXISTS: {target}")
        imported_at = recovered_receipt["created_at"]
    else:
        staging = returns_root / f".{package_id}.pending-{uuid.uuid4().hex}"
        staging.mkdir(parents=False, exist_ok=False)
        try:
            extract_verified_return(verified, staging)
            receipt = import_receipt_document(
                batch_root, staging, target, verified, imported_at
            )
            validate_contract(receipt, RECEIPT_SCHEMA)
            write_new_json(staging / "receipts/import-return-receipt.json", receipt)
            os.replace(staging, target)
        except BaseException:
            if staging.exists():
                shutil.rmtree(staging)
            raise
    entry = {
        "package_id": package_id,
        "archive_sha256": archive_sha,
        "target": target.relative_to(batch_root).as_posix(),
        "receipt": (target / "receipts/import-return-receipt.json").relative_to(batch_root).as_posix(),
        "imported_at": imported_at,
    }
    unit_index["imports"].append(entry)
    unit_index["imports"].sort(key=lambda item: item["package_id"])
    if len(unit_index["imports"]) == 1:
        unit_index["selected_package_id"] = package_id
        unit_index["conflict"] = False
    else:
        unit_index["selected_package_id"] = None
        unit_index["conflict"] = True
    index["updated_at"] = imported_at
    write_json_atomic(import_index_path(batch_root), index)
    if state_path(batch_root).is_file():
        state = load_state(batch_root)
        sync_import_stage(batch_root, state)
    return {
        "imported": True,
        "idempotent": False,
        "conflict": unit_index["conflict"],
        "selected_package_id": unit_index["selected_package_id"],
        "target": str(target),
        "package_id": package_id,
    }


def select_import(args: argparse.Namespace) -> dict[str, Any]:
    batch_root = resolve_directory(Path(args.batch_root), "BATCH_ROOT_INVALID")
    _, batch_manifest = manifest_for(batch_root, "batch")
    index = load_import_index(batch_root, batch_manifest)
    unit = index["units"].get(args.unit_id)
    if not isinstance(unit, dict):
        raise FlowError(f"IMPORT_UNIT_UNKNOWN: {args.unit_id}")
    matches = [item for item in unit.get("imports", []) if item.get("package_id") == args.package_id]
    if len(matches) != 1:
        raise FlowError(f"IMPORT_PACKAGE_UNKNOWN: {args.package_id}")
    target = batch_root / matches[0]["target"]
    if not target.is_dir() or not (target / "receipts/import-return-receipt.json").is_file():
        raise FlowError("IMPORT_SELECTION_TARGET_INVALID")
    unit["selected_package_id"] = args.package_id
    unit["conflict"] = len(unit.get("imports", [])) > 1
    index["updated_at"] = utc_now()
    write_json_atomic(import_index_path(batch_root), index)
    if state_path(batch_root).is_file():
        state = load_state(batch_root)
        sync_import_stage(batch_root, state)
    return {
        "unit_id": args.unit_id,
        "selected_package_id": args.package_id,
        "conflict": unit["conflict"],
        "target": str(target),
    }


def sync_import_stage(batch_root: Path, state: dict[str, Any]) -> None:
    if state["scope"] != "batch" or "import-return" not in state["selected_stages"]:
        return
    _, manifest = manifest_for(batch_root, "batch")
    index = load_import_index(batch_root, manifest)
    expected_units = [item["unit_id"] for item in manifest["units"]]
    selected: list[dict[str, Any]] = []
    unresolved: list[str] = []
    for unit_id in expected_units:
        item = index["units"].get(unit_id)
        package_id = item.get("selected_package_id") if isinstance(item, dict) else None
        imports = item.get("imports", []) if isinstance(item, dict) else []
        matches = [entry for entry in imports if entry.get("package_id") == package_id]
        if len(matches) != 1:
            unresolved.append(unit_id)
            continue
        receipt = batch_root / matches[0]["receipt"]
        if not receipt.is_file() or receipt.is_symlink():
            raise FlowError(f"IMPORT_RECEIPT_DRIFT: {unit_id}")
        document = read_json(receipt, code="IMPORT_RECEIPT_INVALID")
        validate_contract(document, RECEIPT_SCHEMA)
        if document.get("stage") != "import-return" or document.get("status") != "completed":
            raise FlowError(f"IMPORT_RECEIPT_INVALID: {unit_id}")
        selected.append(
            {"unit_id": unit_id, "package_id": package_id, "receipt": str(receipt), "sha256": sha256_file(receipt)}
        )
    changed = False
    target_status = "COMPLETED" if not unresolved else (
        "NEEDS_ATTENTION" if any((index["units"].get(item) or {}).get("conflict") for item in unresolved) else "PENDING"
    )
    if state["stages"]["import-return"] != target_status:
        state["stages"]["import-return"] = target_status
        changed = True
    if state["artifacts"].get("imports") != selected:
        state["artifacts"]["imports"] = selected
        changed = True
    if unresolved:
        state["errors"]["import-return"] = {
            "message": f"unresolved units: {', '.join(unresolved)}",
            "recorded_at": utc_now(),
        }
    else:
        state["errors"].pop("import-return", None)
    if changed:
        save_state(batch_root, state)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="串联并恢复 General E2E 阶段")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init")
    init.add_argument("--scope", required=True, choices=tuple(SCOPE_STAGES))
    init.add_argument("--root", required=True)
    init.add_argument("--stage", action="append", default=[])
    init.add_argument("--input", action="append", default=[])

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--root", required=True)
    resume_parser = subparsers.add_parser("resume")
    resume_parser.add_argument("--root", required=True)

    set_parser = subparsers.add_parser("set-stage")
    set_parser.add_argument("--root", required=True)
    set_parser.add_argument("--stage", required=True, choices=ALL_STAGES)
    set_parser.add_argument(
        "--status",
        required=True,
        choices=("RUNNING", "NEEDS_HUMAN", "NEEDS_ATTENTION", "FAILED"),
    )
    set_parser.add_argument("--error", default="")

    receipt_parser = subparsers.add_parser("record-receipt")
    receipt_parser.add_argument("--root", required=True)
    receipt_parser.add_argument("--stage", required=True, choices=tuple(RECEIPT_STAGE_MAP))
    receipt_parser.add_argument("--receipt", required=True)

    submission_parser = subparsers.add_parser("record-submission")
    submission_parser.add_argument("--root", required=True)
    submission_parser.add_argument("--submission", required=True)

    execution_parser = subparsers.add_parser("record-execution")
    execution_parser.add_argument("--root", required=True)
    execution_parser.add_argument("--state", action="append", required=True)

    package_parser = subparsers.add_parser("package-return")
    package_parser.add_argument("--unit-root", required=True)
    package_parser.add_argument("--orchestration-root", required=True)
    package_parser.add_argument("--output-dir", required=True)

    import_parser = subparsers.add_parser("import-return")
    import_parser.add_argument("--batch-root", required=True)
    import_parser.add_argument("--archive", required=True)
    import_parser.add_argument("--receipt")

    select_parser = subparsers.add_parser("select-import")
    select_parser.add_argument("--batch-root", required=True)
    select_parser.add_argument("--unit-id", required=True)
    select_parser.add_argument("--package-id", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init":
            result = initialize_state(args)
        elif args.command in {"status", "resume"}:
            result = command_status(args)
        elif args.command == "set-stage":
            result = set_stage(args)
        elif args.command == "record-receipt":
            result = record_receipt(args)
        elif args.command == "record-submission":
            result = record_submission(args)
        elif args.command == "record-execution":
            result = record_execution_states(args)
        elif args.command == "package-return":
            result = package_return(args)
        elif args.command == "import-return":
            result = import_return(args)
        elif args.command == "select-import":
            result = select_import(args)
        else:
            raise FlowError(f"COMMAND_UNKNOWN: {args.command}")
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (FlowError, FileNotFoundError, FileExistsError, OSError, zipfile.BadZipFile) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
