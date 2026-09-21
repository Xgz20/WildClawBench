#!/usr/bin/env python3
"""Validate selected General E2E returns and generate reproducible reports."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import Any, Iterable, Mapping, Sequence


REPORT_CONFIG_SCHEMA = "wildclawbench.general-e2e-report-config/v1"
IMPORT_INDEX_SCHEMA = "wildclawbench.general-e2e-import-index/v1"
PACKAGE_SCHEMA = "urn:wildclawbench:schema:general-e2e:package-manifest:v1"
RETURN_SCHEMA = "urn:wildclawbench:schema:general-e2e:return-package:v1"
SCORE_SCHEMA = "urn:wildclawbench:schema:general-e2e:score:v1"
SUBMISSION_SCHEMA = "urn:wildclawbench:schema:general-e2e:submission:v1"
EXECUTION_SCHEMA = "urn:wildclawbench:schema:general-e2e:execution-record:v1"
RESOURCE_SCHEMA = "urn:wildclawbench:schema:general-e2e:resource-metrics:v1"
RECEIPT_SCHEMA = "urn:wildclawbench:schema:general-e2e:receipt:v1"
REPORT_DATA_SCHEMA = "wildclawbench.general-e2e-report-data/v1"
REPORT_RECEIPT_UNIT_ID = "batch"
CLI_ADAPTER_SCHEMA = "wildclawbench.general-e2e-cli-adapter/v1"

RESOURCE_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("input_tokens", "usage", "输入 Token"),
    ("output_tokens", "usage", "输出 Token"),
    ("total_tokens", "usage", "总 Token"),
    ("cache_read_input_tokens", "usage", "缓存读取输入 Token"),
    ("cache_creation_input_tokens", "usage", "缓存写入输入 Token"),
    ("reasoning_output_tokens", "usage", "推理输出 Token"),
    ("request_count", "requests", "模型请求数"),
    ("request_attempt_count", "requests", "HTTP 尝试数"),
    ("call_count", "tools", "工具调用数"),
    ("duration_seconds", "timing", "流程耗时（秒）"),
    ("agent_duration_seconds", "timing", "智能体耗时（秒）"),
)
RESOURCE_LABELS = {key: label for key, _, label in RESOURCE_FIELDS}
RESOURCE_GROUPS = {key: group for key, group, _ in RESOURCE_FIELDS}
EXECUTION_STATUSES = (
    "completed",
    "candidate_error",
    "timeout",
    "infrastructure_error",
    "cancelled",
)
SCORE_STATUSES = ("valid", "evaluation_error", "unscored")


class ReportError(ValueError):
    """Stable failure for invalid, incomplete, or drifting report inputs."""


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def pretty_json_bytes(value: object) -> bytes:
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


def return_package_id(document: Mapping[str, Any]) -> str:
    return sha256_bytes(
        canonical_json_bytes(
            {
                "identity": document.get("identity"),
                "sources": document.get("sources"),
                "entries": document.get("entries"),
            }
        )
    )


def read_json(path: Path, code: str = "JSON_INVALID") -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReportError(f"{code}: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ReportError(f"{code}: {path}: top level must be object")
    return value


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pretty_json_bytes(value))


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def safe_relative(value: object, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value or "\0" in value:
        raise ReportError(f"RELATIVE_PATH_INVALID: {label}: {value!r}")
    relative = PurePosixPath(value)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise ReportError(f"RELATIVE_PATH_INVALID: {label}: {value!r}")
    return relative


def inside(root: Path, target: Path) -> bool:
    try:
        target.relative_to(root)
    except ValueError:
        return False
    return True


def resolve_file(root: Path, relative: object, label: str) -> Path:
    normalized = safe_relative(relative, label)
    path = root.joinpath(*normalized.parts)
    resolved = path.resolve()
    if (
        not inside(root.resolve(), resolved)
        or path.is_symlink()
        or not path.is_file()
    ):
        raise ReportError(f"FILE_INVALID: {label}: {normalized.as_posix()}")
    return path


def numeric(value: object) -> float | int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(float(value)) or value < 0:
        return None
    return value


def normalize_reasoning_effort(value: object) -> object:
    """Normalize UI display casing for the logical reasoning-effort identity."""

    if isinstance(value, str):
        return value.strip().casefold()
    return value


def mean(values: Iterable[float | int]) -> float | None:
    items = [float(value) for value in values]
    return sum(items) / len(items) if items else None


def parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _contract_validator():
    skill_root = Path(__file__).resolve().parents[1]
    vendored = skill_root / "vendor/e2e-shared/general-contracts/validator.py"
    candidates = [vendored]
    # Development fallback; deterministic Skill packages always use the vendored copy.
    for parent in skill_root.parents:
        candidate = parent / "eval_general_e2e/contracts/validator.py"
        if candidate.is_file():
            candidates.append(candidate)
            break
    path = next((item for item in candidates if item.is_file()), None)
    if path is None:
        raise ReportError("GENERAL_CONTRACTS_UNAVAILABLE")
    spec = importlib.util.spec_from_file_location("general_e2e_report_contracts", path)
    if spec is None or spec.loader is None:
        raise ReportError("GENERAL_CONTRACTS_UNAVAILABLE")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CONTRACTS = _contract_validator()


def validate_contract(path: Path, schema_id: str) -> dict[str, Any]:
    document = read_json(path, "CONTRACT_JSON_INVALID")
    try:
        CONTRACTS.validate_contract(document, expected_schema_id=schema_id)
    except Exception as exc:
        raise ReportError(f"CONTRACT_INVALID: {path}: {exc}") from exc
    return document


def validate_batch_inputs(batch_root: Path) -> dict[str, Any]:
    batch_root = batch_root.expanduser().resolve()
    if not batch_root.is_dir() or batch_root.is_symlink():
        raise ReportError(f"BATCH_ROOT_INVALID: {batch_root}")
    manifest_path = batch_root / "manifest.json"
    config_path = batch_root / "report-config.json"
    index_path = batch_root / ".general-e2e/run-general-e2e-import-index.json"
    manifest = read_json(manifest_path, "BATCH_MANIFEST_INVALID")
    config = read_json(config_path, "REPORT_CONFIG_INVALID")
    index = read_json(index_path, "IMPORT_INDEX_INVALID")
    if (
        manifest.get("schema_id") != PACKAGE_SCHEMA
        or manifest.get("schema_version") != 1
        or manifest.get("manifest_kind") != "batch"
    ):
        raise ReportError("BATCH_MANIFEST_INCOMPATIBLE")
    if config.get("schema_version") != REPORT_CONFIG_SCHEMA:
        raise ReportError("REPORT_CONFIG_INCOMPATIBLE")
    if (
        index.get("schema_version") != IMPORT_INDEX_SCHEMA
        or index.get("revision") != 1
        or index.get("batch_id") != manifest.get("batch_id")
        or not isinstance(index.get("units"), dict)
    ):
        raise ReportError("IMPORT_INDEX_INCOMPATIBLE")
    for source, label in ((config, "report config"),):
        if (
            source.get("batch_id") != manifest.get("batch_id")
            or source.get("dataset") != manifest.get("dataset")
            or source.get("release") != manifest.get("release")
            or source.get("units") != manifest.get("units")
        ):
            raise ReportError(f"BATCH_IDENTITY_MISMATCH: {label}")
    task_ids = manifest.get("task_ids")
    units = manifest.get("units")
    if (
        not isinstance(task_ids, list)
        or not task_ids
        or len(task_ids) != len(set(task_ids))
        or not isinstance(units, list)
        or not units
    ):
        raise ReportError("BATCH_SCOPE_INVALID")

    selected: list[dict[str, Any]] = []
    for unit in units:
        if not isinstance(unit, dict) or not isinstance(unit.get("unit_id"), str):
            raise ReportError("BATCH_UNIT_INVALID")
        unit_id = unit["unit_id"]
        indexed = index["units"].get(unit_id)
        if not isinstance(indexed, dict):
            raise ReportError(f"IMPORT_UNIT_MISSING: {unit_id}")
        package_id = indexed.get("selected_package_id")
        imports = indexed.get("imports")
        if not isinstance(package_id, str) or not isinstance(imports, list):
            raise ReportError(f"IMPORT_SELECTION_REQUIRED: {unit_id}")
        matches = [item for item in imports if isinstance(item, dict) and item.get("package_id") == package_id]
        if len(matches) != 1:
            raise ReportError(f"IMPORT_SELECTION_INVALID: {unit_id}")
        resolved = validate_selected_return(
            batch_root, manifest, unit, package_id, matches[0]
        )
        if indexed.get("logical_identity_sha256") != sha256_bytes(
            canonical_json_bytes(resolved["package_manifest"]["identity"])
        ):
            raise ReportError(f"IMPORT_LOGICAL_IDENTITY_DRIFT: {unit_id}")
        selected.append(resolved)
    return {
        "batch_root": batch_root,
        "manifest_path": manifest_path,
        "config_path": config_path,
        "index_path": index_path,
        "manifest": manifest,
        "config": config,
        "index": index,
        "selected": selected,
    }


def validate_return_entries(root: Path, package_manifest: Mapping[str, Any]) -> None:
    entries = package_manifest.get("entries")
    if not isinstance(entries, list) or package_manifest.get("entry_count") != len(entries):
        raise ReportError("RETURN_ENTRY_COUNT_INVALID")
    seen: set[str] = set()
    for row in entries:
        if not isinstance(row, dict):
            raise ReportError("RETURN_ENTRY_INVALID")
        relative = safe_relative(row.get("path"), "return entry").as_posix()
        if relative in seen:
            raise ReportError(f"RETURN_ENTRY_DUPLICATE: {relative}")
        seen.add(relative)
        path = root.joinpath(*PurePosixPath(relative).parts)
        if not inside(root.resolve(), path.parent.resolve()):
            raise ReportError(f"RETURN_ENTRY_ESCAPE: {relative}")
        kind = row.get("kind")
        try:
            mode = f"{stat.S_IMODE(path.lstat().st_mode):04o}"
        except OSError as exc:
            raise ReportError(f"RETURN_ENTRY_MISSING: {relative}") from exc
        if kind == "directory":
            valid = path.is_dir() and not path.is_symlink()
            data = b""
        elif kind == "file":
            valid = path.is_file() and not path.is_symlink()
            data = path.read_bytes() if valid else b""
        elif kind == "symlink":
            valid = path.is_symlink()
            data = os.readlink(path).encode("utf-8", errors="surrogateescape") if valid else b""
            if valid and row.get("link_target") != os.readlink(path):
                valid = False
        else:
            valid = False
            data = b""
        if (
            not valid
            or row.get("mode") != mode
            or row.get("size") != len(data)
            or row.get("sha256") != sha256_bytes(data)
        ):
            raise ReportError(f"RETURN_ENTRY_DRIFT: {relative}")
    expected = set(seen) | {
        "package-manifest.json",
        "receipts/package-receipt.json",
        "receipts/import-return-receipt.json",
    }
    for relative in list(expected):
        parent = PurePosixPath(relative).parent
        while parent.parts:
            expected.add(parent.as_posix())
            parent = parent.parent
    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
    }
    unexpected = sorted(actual - expected)
    missing = sorted(expected - actual)
    if unexpected or missing:
        raise ReportError(
            f"RETURN_MEMBER_SET_MISMATCH: unexpected={unexpected}, missing={missing}"
        )


def validate_selected_return(
    batch_root: Path,
    batch_manifest: Mapping[str, Any],
    unit: Mapping[str, Any],
    package_id: str,
    indexed: Mapping[str, Any],
) -> dict[str, Any]:
    target_relative = safe_relative(indexed.get("target"), "import target")
    target = batch_root.joinpath(*target_relative.parts)
    if not target.is_dir() or target.is_symlink() or not inside(batch_root, target.resolve()):
        raise ReportError(f"IMPORT_TARGET_INVALID: {unit['unit_id']}")
    package_manifest_path = target / "package-manifest.json"
    package_manifest = read_json(package_manifest_path, "RETURN_MANIFEST_INVALID")
    identity = package_manifest.get("identity")
    if (
        package_manifest.get("schema_id") != RETURN_SCHEMA
        or package_manifest.get("schema_version") != 1
        or package_manifest.get("package_kind") != "return"
        or package_manifest.get("package_id") != package_id
        or package_manifest.get("package_id") != return_package_id(package_manifest)
        or not isinstance(identity, dict)
        or identity.get("batch_id") != batch_manifest.get("batch_id")
        or identity.get("unit_id") != unit.get("unit_id")
        or identity.get("dataset") != batch_manifest.get("dataset")
        or identity.get("release") != batch_manifest.get("release")
        or identity.get("task_ids") != unit.get("task_ids")
    ):
        raise ReportError(f"RETURN_IDENTITY_MISMATCH: {unit['unit_id']}")
    validate_return_entries(target, package_manifest)
    supplements = target / "unit/evidence/resource-supplements"
    if supplements.exists() and (
        unit.get("harness", {}).get("id") != "workbuddy"
        or any(p.name not in unit["task_ids"] or not p.is_dir() or p.is_symlink() for p in supplements.iterdir())
    ):
        raise ReportError("RESOURCE_SUPPLEMENT_SCOPE_INVALID")
    sources = package_manifest.get("sources") or {}
    unit_manifest_path = target / "unit/manifest.json"
    collect_receipt_path = target / "unit/receipts/collect-evidence-receipt.json"
    submission_path = target / "scoring/submission.json"
    package_receipt_path = target / "receipts/package-receipt.json"
    import_receipt_path = target / "receipts/import-return-receipt.json"
    if (
        sources.get("unit_manifest_sha256") != sha256_file(unit_manifest_path)
        or sources.get("collect_receipt_sha256") != sha256_file(collect_receipt_path)
        or sources.get("submission_sha256") != sha256_file(submission_path)
    ):
        raise ReportError(f"RETURN_SOURCE_DRIFT: {unit['unit_id']}")
    unit_manifest = read_json(unit_manifest_path, "UNIT_MANIFEST_INVALID")
    if (
        unit_manifest.get("schema_id") != PACKAGE_SCHEMA
        or unit_manifest.get("manifest_kind") != "execution"
        or unit_manifest.get("batch_id") != identity["batch_id"]
        or unit_manifest.get("unit_id") != identity["unit_id"]
        or unit_manifest.get("dataset") != identity["dataset"]
        or unit_manifest.get("release") != identity["release"]
        or unit_manifest.get("task_ids") != identity["task_ids"]
        or unit_manifest.get("unit") != unit
    ):
        raise ReportError(f"UNIT_MANIFEST_IDENTITY_MISMATCH: {unit['unit_id']}")
    tasks = unit_manifest.get("tasks")
    if not isinstance(tasks, list) or [item.get("task_id") for item in tasks if isinstance(item, dict)] != unit["task_ids"]:
        raise ReportError(f"UNIT_TASK_METADATA_INVALID: {unit['unit_id']}")
    submission = validate_contract(submission_path, SUBMISSION_SCHEMA)
    collect_receipt = validate_contract(collect_receipt_path, RECEIPT_SCHEMA)
    package_receipt = validate_contract(package_receipt_path, RECEIPT_SCHEMA)
    import_receipt = validate_contract(import_receipt_path, RECEIPT_SCHEMA)
    expected_scope = {"batch_id": identity["batch_id"], "unit_id": identity["unit_id"]}
    expected_dataset = {"id": identity["dataset"]["id"], "digest": identity["dataset"]["digest"]}
    if (
        submission.get("scope") != expected_scope
        or submission.get("dataset") != expected_dataset
        or submission.get("task_ids") != identity["task_ids"]
        or not submission.get("integrity", {}).get("valid")
        or collect_receipt.get("stage") != "collect-evidence"
        or collect_receipt.get("status") != "completed"
        or collect_receipt.get("scope") != expected_scope
        or collect_receipt.get("dataset") != expected_dataset
        or collect_receipt.get("task_ids") != identity["task_ids"]
        or not collect_receipt.get("integrity", {}).get("valid")
        or package_receipt.get("stage") != "package"
        or package_receipt.get("status") != "completed"
        or package_receipt.get("scope") != expected_scope
        or package_receipt.get("dataset") != expected_dataset
        or package_receipt.get("task_ids") != identity["task_ids"]
        or not package_receipt.get("integrity", {}).get("valid")
        or import_receipt.get("stage") != "import-return"
        or import_receipt.get("status") != "completed"
        or import_receipt.get("scope") != expected_scope
        or import_receipt.get("dataset") != expected_dataset
        or import_receipt.get("task_ids") != identity["task_ids"]
        or not import_receipt.get("integrity", {}).get("valid")
    ):
        raise ReportError(f"RETURN_CONTROL_IDENTITY_MISMATCH: {unit['unit_id']}")
    package_artifacts = {
        item.get("path"): item
        for item in package_receipt.get("artifacts", [])
        if isinstance(item, dict)
    }
    for relative, path in (
        ("package-manifest.json", package_manifest_path),
        ("scoring/submission.json", submission_path),
    ):
        artifact = package_artifacts.get(relative)
        if (
            artifact is None
            or artifact.get("sha256") != sha256_file(path)
            or artifact.get("size") != path.stat().st_size
        ):
            raise ReportError(f"PACKAGE_RECEIPT_ARTIFACT_DRIFT: {unit['unit_id']}:{relative}")
    for artifact in import_receipt.get("artifacts", []):
        if not isinstance(artifact, dict):
            raise ReportError(f"IMPORT_RECEIPT_ARTIFACT_INVALID: {unit['unit_id']}")
        artifact_path = resolve_file(batch_root, artifact.get("path"), "import receipt artifact")
        if (
            artifact.get("sha256") != sha256_file(artifact_path)
            or artifact.get("size") != artifact_path.stat().st_size
        ):
            raise ReportError(f"IMPORT_RECEIPT_ARTIFACT_DRIFT: {unit['unit_id']}")
    receipt_index_path = safe_relative(indexed.get("receipt"), "import receipt")
    if batch_root.joinpath(*receipt_index_path.parts).resolve() != import_receipt_path.resolve():
        raise ReportError(f"IMPORT_RECEIPT_INDEX_MISMATCH: {unit['unit_id']}")
    return {
        "unit": dict(unit),
        "root": target,
        "package_id": package_id,
        "package_manifest_path": package_manifest_path,
        "package_manifest": package_manifest,
        "unit_manifest_path": unit_manifest_path,
        "unit_manifest": unit_manifest,
        "submission_path": submission_path,
        "submission": submission,
        "collect_receipt_path": collect_receipt_path,
        "collect_receipt": collect_receipt,
        "package_receipt_path": package_receipt_path,
        "package_receipt": package_receipt,
        "import_receipt_path": import_receipt_path,
        "import_receipt": import_receipt,
        "archive_sha256": indexed.get("archive_sha256"),
    }


def metric_observation(metrics: Mapping[str, Any] | None, field: str) -> dict[str, Any]:
    unavailable = {
        "value": None,
        "known_subtotal": None,
        "status": "unavailable",
        "complete": False,
        "coverage": {"known": 0, "total": None, "unit": None},
        "basis": "resource metrics unavailable",
    }
    if metrics is None:
        return unavailable
    group = RESOURCE_GROUPS[field]
    metric = ((metrics.get("metrics") or {}).get(group) or {}).get(field)
    coverage = ((metrics.get("collection") or {}).get("coverage") or {}).get(field)
    if not isinstance(metric, dict) or not isinstance(coverage, dict):
        return unavailable
    value = numeric(metric.get("value"))
    known = coverage.get("known")
    total = coverage.get("total")
    status = metric.get("status") if isinstance(metric.get("status"), str) else "unavailable"
    complete = (
        value is not None
        and isinstance(known, int)
        and isinstance(total, int)
        and known == total
        and status in {"observed", "inferred"}
    )
    known_subtotals = (metrics.get("collection") or {}).get("known_subtotals") or {}
    known_subtotal = value if complete else numeric(known_subtotals.get(field))
    if known_subtotal is None and status == "partial":
        known_subtotal = value
    return {
        "value": value if complete else None,
        "known_subtotal": known_subtotal,
        "status": status,
        "complete": complete,
        "coverage": {
            "known": known if isinstance(known, int) else 0,
            "total": total if isinstance(total, int) else None,
            "unit": coverage.get("unit") if isinstance(coverage.get("unit"), str) else None,
        },
        "basis": metric.get("basis") if isinstance(metric.get("basis"), str) else "",
    }


def workbuddy_resource_supplement(root: Path, task_id: str, execution_path: Path) -> dict[str, Any] | None:
    unit_root = root / "unit"
    directory = unit_root / "evidence/resource-supplements" / task_id
    if not directory.exists():
        return None
    script = Path(__file__).resolve().parents[1] / "vendor/e2e-shared/workbuddy-jsonl-metrics/index.mjs"
    if not script.is_file():
        # Source checkout only; standalone Skill packages use the frozen vendor.
        repo_script = Path(__file__).resolve().parents[4] / "e2e-shared/workbuddy-jsonl-metrics/index.mjs"
        if repo_script.is_file():
            script = repo_script
    try:
        run = subprocess.run(
            [os.environ.get("GENERAL_E2E_NODE", "node"), str(script), "--verify-supplement",
             str(unit_root), task_id, str(execution_path)],
            capture_output=True, text=True, timeout=30, check=False,
        )
        if run.returncode:
            raise ReportError(f"RESOURCE_SUPPLEMENT_INVALID: {task_id}: {run.stderr[-1000:]}")
        result = json.loads(run.stdout)
        if result.get("status") != "PASS":
            raise ValueError("supplement verifier did not pass")
        return result
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        raise ReportError(f"RESOURCE_SUPPLEMENT_INVALID: {task_id}: {exc}") from exc


def build_task_row(selected: Mapping[str, Any], task_meta: Mapping[str, Any], submission_task: Mapping[str, Any]) -> dict[str, Any]:
    root = selected["root"]
    unit = selected["unit"]
    task_id = task_meta["task_id"]
    execution_path = root / "scoring/execution-records" / f"{task_id}.json"
    execution = validate_contract(execution_path, EXECUTION_SCHEMA)
    expected_identity = {
        "batch_id": selected["package_manifest"]["identity"]["batch_id"],
        "unit_id": unit["unit_id"],
        "task_id": task_id,
        "attempt_id": submission_task["execution_attempt_id"],
    }
    if (
        execution.get("identity") != expected_identity
        or execution.get("execution", {}).get("business_status") != submission_task["execution_status"]
        or execution.get("dataset") != selected["submission"]["dataset"]
        or execution.get("harness") != unit["harness"]
        or execution.get("model", {}).get("requested_id") != unit["model"]["requested_id"]
        or normalize_reasoning_effort(
            execution.get("model", {}).get("reasoning_effort")
        )
        != normalize_reasoning_effort(unit["model"].get("reasoning_effort"))
    ):
        raise ReportError(f"EXECUTION_IDENTITY_MISMATCH: {unit['unit_id']}:{task_id}")
    score: dict[str, Any] | None = None
    score_path: Path | None = None
    if submission_task["score_status"] != "unscored":
        score_path = resolve_file(root / "scoring", submission_task["score_path"], "score path")
        if sha256_file(score_path) != submission_task["score_sha256"]:
            raise ReportError(f"SCORE_SHA_MISMATCH: {unit['unit_id']}:{task_id}")
        score = validate_contract(score_path, SCORE_SCHEMA)
        score_identity = score.get("identity") or {}
        if (
            score_identity.get("batch_id") != expected_identity["batch_id"]
            or score_identity.get("unit_id") != expected_identity["unit_id"]
            or score_identity.get("task_id") != expected_identity["task_id"]
            or score_identity.get("attempt_id") != submission_task["scoring_attempt_id"]
            or score.get("dataset") != selected["submission"]["dataset"]
            or score.get("execution", {}).get("attempt_id") != expected_identity["attempt_id"]
            or score.get("execution", {}).get("record_sha256") != sha256_file(execution_path)
            or score.get("execution", {}).get("business_status") != submission_task["execution_status"]
            or score.get("judge", {}).get("protocol") != submission_task["judge_protocol"]
        ):
            raise ReportError(f"SCORE_IDENTITY_MISMATCH: {unit['unit_id']}:{task_id}")
        score_valid = bool(score.get("result", {}).get("valid"))
        total_score = score.get("result", {}).get("total_score")
        if submission_task["score_status"] == "valid":
            if not score_valid or numeric(total_score) is None or score.get("evaluation", {}).get("status") != "completed":
                raise ReportError(f"VALID_SCORE_INVALID: {unit['unit_id']}:{task_id}")
        elif score_valid or total_score is not None or score.get("evaluation", {}).get("status") != "evaluation_error":
            raise ReportError(f"EVALUATION_ERROR_SCORE_INVALID: {unit['unit_id']}:{task_id}")

    metrics: dict[str, Any] | None = None
    metrics_path: Path | None = None
    resource_relative = execution.get("resource_metrics_path")
    if resource_relative is not None:
        metrics_path = resolve_file(root / "unit", resource_relative, "resource metrics path")
        metrics = validate_contract(metrics_path, RESOURCE_SCHEMA)
        if metrics.get("identity") != expected_identity:
            raise ReportError(f"RESOURCE_IDENTITY_MISMATCH: {unit['unit_id']}:{task_id}")
    supplement = None
    if (root / "unit/evidence/resource-supplements" / task_id).exists():
        original_record = resolve_file(
            root / "unit", f"evidence/tasks/{task_id}/{expected_identity['attempt_id']}/execution-record.json",
            "supplement original execution record",
        )
        if sha256_file(original_record) != sha256_file(execution_path):
            raise ReportError("RESOURCE_SUPPLEMENT_EXECUTION_DRIFT")
        supplement = workbuddy_resource_supplement(root, task_id, original_record)
        metrics_path = Path(supplement["resource_metrics_path"])
        metrics = validate_contract(metrics_path, RESOURCE_SCHEMA)
        if metrics.get("identity") != expected_identity:
            raise ReportError("RESOURCE_SUPPLEMENT_IDENTITY_MISMATCH")
    if metrics and unit["harness"]["id"] == "workbuddy" and supplement is None:
        request_metric = metrics.get("metrics", {}).get("requests", {}).get("request_count", {})
        if request_metric.get("basis") == "One exact WorkBuddy native request is bound":
            # Older collectors counted the user turn, not model responses.
            request_metric.update(value=None, status="unavailable", basis="Legacy WorkBuddy top-level request count is not a model response count; JSONL supplement required")
            metrics["collection"].setdefault("coverage", {})["request_count"] = {"known": 0, "total": None, "unit": "model_response"}
            metrics["collection"].get("known_subtotals", {}).pop("request_count", None)
    resource = {field: metric_observation(metrics, field) for field, _, _ in RESOURCE_FIELDS}
    judge = score.get("judge") if score else None
    components = score.get("components") if score else None
    evaluation = score.get("evaluation") if score else None
    result = score.get("result") if score else None
    return {
        "run_id": f"{unit['unit_id']}::{task_id}",
        "unit_id": unit["unit_id"],
        "task_id": task_id,
        "task_name": task_meta.get("name"),
        "category": task_meta.get("category"),
        "difficulty": task_meta.get("difficulty"),
        "modality": task_meta.get("modality"),
        "execution_mode": unit.get("execution_mode"),
        "harness": execution["harness"],
        "model": execution["model"],
        "human_assistance": execution["human_assistance"],
        "execution_attempt_id": expected_identity["attempt_id"],
        "execution_phase": execution["phase"],
        "execution_status": submission_task["execution_status"],
        "execution_started_at": execution["execution"]["started_at"],
        "execution_finished_at": execution["execution"]["finished_at"],
        "evidence_completeness": execution["evidence"]["completeness"],
        "score_status": submission_task["score_status"],
        "scoring_attempt_id": submission_task["scoring_attempt_id"],
        "judge": judge,
        "components": components,
        "evaluation": evaluation,
        "total_score": result.get("total_score") if result else None,
        "invalid_reason": result.get("invalid_reason") if result else None,
        "resource_collection_status": (metrics.get("collection") or {}).get("status") if metrics else "unavailable",
        "resource": resource,
        "lineage": {
            "package_id": selected["package_id"],
            "package_manifest_sha256": sha256_file(selected["package_manifest_path"]),
            "import_receipt_sha256": sha256_file(selected["import_receipt_path"]),
            "submission_sha256": sha256_file(selected["submission_path"]),
            "execution_record_sha256": sha256_file(execution_path),
            "score_sha256": sha256_file(score_path) if score_path else None,
            "resource_metrics_sha256": sha256_file(metrics_path) if metrics_path else None,
            "resource_supplement_sha256": supplement["supplement_sha256"] if supplement else None,
            "base_resource_metrics_sha256": supplement["base_resource_sha256"] if supplement else None,
        },
    }


def score_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    valid = [row for row in rows if row["score_status"] == "valid"]
    scores = [float(row["total_score"]) for row in valid]
    return {
        "frozen_task_run_count": len(rows),
        "valid_score_count": len(valid),
        "evaluation_error_count": sum(row["score_status"] == "evaluation_error" for row in rows),
        "unscored_count": sum(row["score_status"] == "unscored" for row in rows),
        "valid_zero_score_count": sum(row["total_score"] == 0 for row in valid),
        "mean_score": mean(scores),
        "score_sum": sum(scores) if scores else None,
        "score_denominator": len(scores),
        "execution_status_counts": {status: sum(row["execution_status"] == status for row in rows) for status in EXECUTION_STATUSES},
    }


def grouped_score(rows: Sequence[Mapping[str, Any]], key: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get(key) or "unknown")].append(row)
    return [
        {key: group, **score_summary(group_rows)}
        for group, group_rows in sorted(grouped.items())
    ]


def judge_groups(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, Any, Any], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        judge = row.get("judge") or {}
        key = (judge.get("protocol"), judge.get("model"), judge.get("reasoning_effort"))
        grouped[key].append(row)
    output = []
    for key, group_rows in sorted(grouped.items(), key=lambda item: tuple(str(v or "") for v in item[0])):
        output.append(
            {
                "protocol": key[0],
                "model": key[1],
                "reasoning_effort": key[2],
                **score_summary(group_rows),
            }
        )
    return output


def resource_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for field, _, label in RESOURCE_FIELDS:
        observations = [row["resource"][field] for row in rows]
        complete_values = [item["value"] for item in observations if item["complete"]]
        known_values = [item["known_subtotal"] for item in observations if item["known_subtotal"] is not None]
        complete_cases = len(complete_values)
        total_cases = len(observations)
        source_known = sum(item["coverage"]["known"] for item in observations)
        source_totals = [item["coverage"]["total"] for item in observations]
        unknown_source_denominators = sum(value is None for value in source_totals)
        status = "complete" if total_cases and complete_cases == total_cases else ("partial" if known_values else "unavailable")
        output[field] = {
            "label": label,
            "status": status,
            "total": sum(complete_values) if complete_cases == total_cases and total_cases else None,
            "known_subtotal": sum(known_values) if known_values else None,
            "coverage": {"known": complete_cases, "total": total_cases, "unit": "task_run"},
            "source_coverage": {
                "known": source_known,
                "total": sum(value for value in source_totals if value is not None) if not unknown_source_denominators else None,
                "unknown_denominator_cases": unknown_source_denominators,
            },
            "partial_case_count": sum(item["status"] == "partial" for item in observations),
            "status_counts": dict(sorted(Counter(item["status"] for item in observations).items())),
        }
    return output


def timing_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    starts = [parse_timestamp(row.get("execution_started_at")) for row in rows]
    finishes = [parse_timestamp(row.get("execution_finished_at")) for row in rows]
    observed_pairs = [(start, finish) for start, finish in zip(starts, finishes) if start and finish and finish >= start]
    wall_clock = None
    if len(observed_pairs) == len(rows) and observed_pairs:
        wall_clock = (max(finish for _, finish in observed_pairs) - min(start for start, _ in observed_pairs)).total_seconds()
    return {
        "batch_wall_clock_seconds": wall_clock,
        "batch_wall_clock_coverage": {"known": len(observed_pairs), "total": len(rows), "unit": "task_run"},
        "task_duration_sum": resource_summary(rows)["duration_seconds"],
        "note": "批次壁钟按最早任务开始至最晚任务结束计算；任务耗时之和独立展示，二者不可互换。",
    }


def unit_summary(rows: Sequence[Mapping[str, Any]], unit: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "unit_id": unit["unit_id"],
        "harness": unit["harness"],
        "model": unit["model"],
        "execution_mode": unit["execution_mode"],
        "score": score_summary(rows),
        "categories": grouped_score(rows, "category"),
        "difficulties": grouped_score(rows, "difficulty"),
        "judge_groups": judge_groups(rows),
        "resources": resource_summary(rows),
        "timing": timing_summary(rows),
    }


def aggregate(validated: Mapping[str, Any], generated_at: str) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    units = []
    for selected in validated["selected"]:
        metadata = {item["task_id"]: item for item in selected["unit_manifest"]["tasks"]}
        submissions = {item["task_id"]: item for item in selected["submission"]["tasks"]}
        unit_rows = [build_task_row(selected, metadata[task_id], submissions[task_id]) for task_id in selected["unit"]["task_ids"]]
        rows.extend(unit_rows)
        units.append(unit_summary(unit_rows, selected["unit"]))
    manifest = validated["manifest"]
    config = validated["config"]
    unique_task_ids = list(manifest["task_ids"])
    selected_imports = [
        {
            "unit_id": item["unit"]["unit_id"],
            "package_id": item["package_id"],
            "archive_sha256": item["archive_sha256"],
            "package_manifest_sha256": sha256_file(item["package_manifest_path"]),
            "submission_sha256": sha256_file(item["submission_path"]),
            "import_receipt_sha256": sha256_file(item["import_receipt_path"]),
        }
        for item in validated["selected"]
    ]
    return {
        "schema_version": REPORT_DATA_SCHEMA,
        "generated_at": generated_at,
        "title": config.get("report", {}).get("title") or "通用场景端到端自动化评测报告",
        "batch_id": manifest["batch_id"],
        "dataset": manifest["dataset"],
        "release": manifest["release"],
        "scope": {
            "unique_task_count": len(unique_task_ids),
            "task_run_count": len(rows),
            "unit_count": len(units),
            "task_ids": unique_task_ids,
        },
        "overall": {
            "score": score_summary(rows),
            "categories": grouped_score(rows, "category"),
            "difficulties": grouped_score(rows, "difficulty"),
            "judge_groups": judge_groups(rows),
            "resources": resource_summary(rows),
            "timing": timing_summary(rows),
        },
        "units": units,
        "tasks": rows,
        "lineage": {
            "batch_manifest_sha256": sha256_file(validated["manifest_path"]),
            "report_config_sha256": sha256_file(validated["config_path"]),
            "import_index_sha256": sha256_file(validated["index_path"]),
            "selected_imports": selected_imports,
        },
        "semantics": {
            "score_denominator": "仅 score_status=valid 的真实能力分；有效 0 分保留。",
            "evaluation_errors": "evaluation_error 与 unscored 不进入能力均值，也不补零。",
            "resource_missing": "字段仅在全部 task run 完整覆盖时提供 total；否则为 null，并提供 known_subtotal 与 coverage。",
            "judge_grouping": "按 protocol、model、reasoning_effort 分组，不做无提示合并。",
        },
    }


def shown(value: object, digits: int = 4) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.{digits}f}".rstrip("0").rstrip(".")
    return str(value)


def markdown_table(headers: Sequence[str], rows: Sequence[Sequence[object]]) -> list[str]:
    output = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        output.append("| " + " | ".join(shown(value).replace("|", "\\|").replace("\n", " ") for value in row) + " |")
    return output


def render_markdown(data: Mapping[str, Any]) -> str:
    overall = data["overall"]
    score = overall["score"]
    lines = [
        f"# {data['title']}",
        "",
        f"- 批次：`{data['batch_id']}`",
        f"- 数据集：`{data['dataset']['id']}`",
        f"- 唯一任务：{data['scope']['unique_task_count']}；任务运行：{data['scope']['task_run_count']}；单元：{data['scope']['unit_count']}",
        f"- 生成时间：{data['generated_at']}",
        "",
        "## 总览",
        "",
        *markdown_table(
            ["冻结任务运行", "有效评分", "评测异常", "未评分", "有效 0 分", "有效均分"],
            [[score["frozen_task_run_count"], score["valid_score_count"], score["evaluation_error_count"], score["unscored_count"], score["valid_zero_score_count"], score["mean_score"]]],
        ),
        "",
        "评测异常和未评分不会补为 0；均分只使用有效评分，真实有效 0 分保留。",
        "",
        "### 执行状态",
        "",
        *markdown_table(["状态", "数量"], [[key, value] for key, value in score["execution_status_counts"].items()]),
        "",
        "## 分类与难度",
        "",
        "### 六类能力",
        "",
        *markdown_table(
            ["分类", "冻结运行", "有效分母", "有效均分", "评测异常", "未评分"],
            [[row["category"], row["frozen_task_run_count"], row["valid_score_count"], row["mean_score"], row["evaluation_error_count"], row["unscored_count"]] for row in overall["categories"]],
        ),
        "",
        "### 难度",
        "",
        *markdown_table(
            ["难度", "冻结运行", "有效分母", "有效均分", "评测异常", "未评分"],
            [[row["difficulty"], row["frozen_task_run_count"], row["valid_score_count"], row["mean_score"], row["evaluation_error_count"], row["unscored_count"]] for row in overall["difficulties"]],
        ),
        "",
        "## 裁判协议分组",
        "",
        *markdown_table(
            ["协议", "模型", "推理强度", "冻结运行", "有效分母", "有效均分", "评测异常"],
            [[row["protocol"], row["model"], row["reasoning_effort"], row["frozen_task_run_count"], row["valid_score_count"], row["mean_score"], row["evaluation_error_count"]] for row in overall["judge_groups"]],
        ),
        "",
        "不同协议、模型或推理强度保持分组展示；`not-required` 自动规则任务不会被语义后端配置阻止。",
        "",
        "## 资源覆盖",
        "",
        *markdown_table(
            ["指标", "状态", "完整总量", "已知小计", "完整覆盖", "来源状态"],
            [[item["label"], item["status"], item["total"], item["known_subtotal"], f"{item['coverage']['known']}/{item['coverage']['total']}", ", ".join(f"{k}:{v}" for k, v in item["status_counts"].items())] for item in overall["resources"].values()],
        ),
        "",
        f"- 批次壁钟：{shown(overall['timing']['batch_wall_clock_seconds'])} 秒，覆盖 {overall['timing']['batch_wall_clock_coverage']['known']}/{overall['timing']['batch_wall_clock_coverage']['total']} 个任务运行。",
        f"- 任务流程耗时之和：{shown(overall['resources']['duration_seconds']['total'])} 秒；已知小计 {shown(overall['resources']['duration_seconds']['known_subtotal'])} 秒。",
        "",
        "批次壁钟和任务耗时之和是不同口径，不相互替代。",
        "",
        "## 用例明细",
        "",
        *markdown_table(
            ["运行 ID", "分类", "难度", "执行状态", "评分状态", "总分", "裁判协议", "评分 attempt"],
            [[row["run_id"], row["category"], row["difficulty"], row["execution_status"], row["score_status"], row["total_score"], (row["judge"] or {}).get("protocol"), row["scoring_attempt_id"]] for row in data["tasks"]],
        ),
        "",
        "## 可复算与谱系",
        "",
        f"- 批次 manifest SHA-256：`{data['lineage']['batch_manifest_sha256']}`",
        f"- 报告配置 SHA-256：`{data['lineage']['report_config_sha256']}`",
        f"- 导入选择索引 SHA-256：`{data['lineage']['import_index_sha256']}`",
        "- 本 Markdown 与 Excel 均由同目录报告 JSON 生成。",
        "",
    ]
    return "\n".join(lines)


def cli_task_documents(row: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    score = {
        "schema_version": CLI_ADAPTER_SCHEMA,
        "task_id": row["task_id"],
        "unit_id": row["unit_id"],
        "score_status": row["score_status"],
        "overall_score": row["total_score"],
        "evaluation_error": row["score_status"] == "evaluation_error",
        "legacy_zero_filled": False,
        "source_score_sha256": row["lineage"]["score_sha256"],
    }
    usage_metrics = {}
    for field, _, _ in RESOURCE_FIELDS:
        observation = row["resource"][field]
        usage_metrics[field] = {
            "value": observation["value"],
            "known_subtotal": observation["known_subtotal"],
            "status": observation["status"],
            "coverage": observation["coverage"],
        }
    usage = {
        "schema_version": CLI_ADAPTER_SCHEMA,
        "task_id": row["task_id"],
        "unit_id": row["unit_id"],
        "metrics": usage_metrics,
        "missing_values_are_zero": False,
        "source_resource_metrics_sha256": row["lineage"]["resource_metrics_sha256"],
    }
    execution_status = {
        "schema_version": CLI_ADAPTER_SCHEMA,
        "task_id": row["task_id"],
        "unit_id": row["unit_id"],
        "status": row["execution_status"],
        "phase": row["execution_phase"],
        "attempt_id": row["execution_attempt_id"],
        "evidence_completeness": row["evidence_completeness"],
        "source_execution_record_sha256": row["lineage"]["execution_record_sha256"],
    }
    task_output = {
        "schema_version": CLI_ADAPTER_SCHEMA,
        "task_id": row["task_id"],
        "unit_id": row["unit_id"],
        "execution_status": row["execution_status"],
        "score_status": row["score_status"],
        "overall_score": row["total_score"],
        "evaluation_error_is_capability_zero": False,
        "package_id": row["lineage"]["package_id"],
    }
    return {
        "score.json": score,
        "usage.json": usage,
        "execution_status.json": execution_status,
        "task_output.json": task_output,
    }


def write_cli_adapter(output_root: Path, data: Mapping[str, Any]) -> Path:
    root = output_root / "cli-adapter"
    manifest_rows = []
    for row in data["tasks"]:
        task_root = root / "units" / row["unit_id"] / row["task_id"]
        for filename, document in cli_task_documents(row).items():
            path = task_root / filename
            write_json(path, document)
            manifest_rows.append({
                "run_id": row["run_id"],
                "path": path.relative_to(output_root).as_posix(),
                "sha256": sha256_file(path),
                "size": path.stat().st_size,
            })
    manifest = {
        "schema_version": CLI_ADAPTER_SCHEMA,
        "batch_id": data["batch_id"],
        "source_report_data_sha256": None,
        "legacy_zero_filled": False,
        "artifacts": manifest_rows,
    }
    path = root / "manifest.json"
    write_json(path, manifest)
    return path


def render_excel(
    input_path: Path,
    output_path: Path,
    preview_dir: Path,
    *,
    node: str,
    node_modules: Path,
    skip_preview: bool,
) -> dict[str, Any]:
    renderer = Path(__file__).with_name("render_general_e2e_excel.mjs")
    node_modules = node_modules.expanduser().resolve()
    if not renderer.is_file() or not node_modules.is_dir():
        raise ReportError("EXCEL_RUNTIME_INVALID")
    with tempfile.TemporaryDirectory(prefix="general-e2e-report-xlsx-") as temp_dir:
        runtime = Path(temp_dir)
        runtime_renderer = runtime / renderer.name
        shutil.copy2(renderer, runtime_renderer)
        link = runtime / "node_modules"
        try:
            os.symlink(node_modules, link, target_is_directory=True)
        except OSError as exc:
            if os.name != "nt":
                raise ReportError(f"EXCEL_RUNTIME_LINK_FAILED: {exc}") from exc
            completed = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(link), str(node_modules)],
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode != 0:
                raise ReportError(f"EXCEL_RUNTIME_LINK_FAILED: {completed.stderr.strip()}")
        command = [
            node,
            str(runtime_renderer),
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--preview-dir",
            str(preview_dir),
            "--skip-preview",
            "true" if skip_preview else "false",
        ]
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise ReportError(f"EXCEL_RENDER_FAILED: {completed.stderr.strip() or completed.stdout.strip()}")
    json_lines = [line for line in completed.stdout.splitlines() if line.lstrip().startswith("{")]
    try:
        result = json.loads(json_lines[-1] if json_lines else "")
    except json.JSONDecodeError as exc:
        raise ReportError(f"EXCEL_RENDER_OUTPUT_INVALID: {completed.stdout}") from exc
    if result.get("status") != "PASS" or not output_path.is_file():
        raise ReportError("EXCEL_RENDER_INCOMPLETE")
    Path(f"{output_path}.inspect.ndjson").unlink(missing_ok=True)
    return result


def build_report_receipt(
    data: Mapping[str, Any],
    output_root: Path,
    artifacts: Sequence[Path],
    *,
    staged_output_root: Path | None = None,
    published_output_root: Path | None = None,
) -> dict[str, Any]:
    if (staged_output_root is None) != (published_output_root is None):
        raise ReportError("REPORT_RECEIPT_PUBLISH_ROOTS_INCOMPLETE")

    def published_path(path: Path) -> Path:
        if staged_output_root is None or published_output_root is None:
            return path
        try:
            relative = path.relative_to(staged_output_root)
        except ValueError as exc:
            raise ReportError(f"REPORT_ARTIFACT_OUTSIDE_STAGING: {path}") from exc
        return published_output_root / relative

    return {
        "schema_id": RECEIPT_SCHEMA,
        "schema_version": 1,
        "scope": {"batch_id": data["batch_id"], "unit_id": REPORT_RECEIPT_UNIT_ID},
        "dataset": {"id": data["dataset"]["id"], "digest": data["dataset"]["digest"]},
        "stage": "report",
        "status": "completed",
        "created_at": data["generated_at"],
        "task_ids": list(data["scope"]["task_ids"]),
        "tasks": [
            {"task_id": task_id, "attempt_id": "report-v1", "status": "completed"}
            for task_id in data["scope"]["task_ids"]
        ],
        "artifacts": [
            {
                "path": published_path(path).relative_to(output_root).as_posix(),
                "sha256": sha256_file(path),
                "size": path.stat().st_size,
            }
            for path in artifacts
        ],
        "integrity": {
            "scope_matches": True,
            "identities_match": True,
            "hashes_verified": True,
            "valid": True,
        },
        "error": None,
    }


def generated_at_value(value: str | None) -> str:
    if value:
        parsed = parse_timestamp(value)
        if parsed is None:
            raise ReportError("GENERATED_AT_INVALID")
        return value
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def command_validate(args: argparse.Namespace) -> dict[str, Any]:
    validated = validate_batch_inputs(Path(args.batch_root))
    return {
        "status": "PASS",
        "batch_id": validated["manifest"]["batch_id"],
        "unit_count": len(validated["selected"]),
        "task_count": len(validated["manifest"]["task_ids"]),
        "selected_packages": [
            {"unit_id": item["unit"]["unit_id"], "package_id": item["package_id"]}
            for item in validated["selected"]
        ],
    }


def command_generate(args: argparse.Namespace) -> dict[str, Any]:
    validated = validate_batch_inputs(Path(args.batch_root))
    generated_at = generated_at_value(args.generated_at)
    data = aggregate(validated, generated_at)
    output_root = Path(args.output_dir).expanduser().resolve()
    batch_root = validated["batch_root"]
    if output_root == batch_root or not inside(batch_root, output_root):
        raise ReportError(
            f"OUTPUT_OUTSIDE_BATCH: report output must be below {batch_root}"
        )
    output_root.parent.mkdir(parents=True, exist_ok=True)
    if output_root.exists():
        if output_root.is_symlink() or not output_root.is_dir() or any(output_root.iterdir()):
            raise ReportError(f"OUTPUT_NOT_EMPTY: {output_root}")
        output_root.rmdir()
    staging = Path(tempfile.mkdtemp(prefix=f".{output_root.name}.pending-", dir=output_root.parent))
    try:
        data_path = staging / "general_e2e_report_data.json"
        markdown_path = staging / "通用场景端到端自动化评测报告.md"
        excel_path = staging / "通用场景端到端自动化评测报告.xlsx"
        preview_dir = staging / "previews"
        write_json(data_path, data)
        write_text(markdown_path, render_markdown(data))
        cli_manifest_path = write_cli_adapter(staging, data)
        cli_manifest = read_json(cli_manifest_path)
        cli_manifest["source_report_data_sha256"] = sha256_file(data_path)
        write_json(cli_manifest_path, cli_manifest)
        excel_result = render_excel(
            data_path,
            excel_path,
            preview_dir,
            node=args.node,
            node_modules=Path(args.node_modules),
            skip_preview=args.skip_preview,
        )
        validation_path = Path(excel_result["validation"])
        receipt_path = staging / "receipts/report-receipt.json"
        receipt = build_report_receipt(
            data,
            batch_root,
            [data_path, markdown_path, excel_path, cli_manifest_path, validation_path],
            staged_output_root=staging,
            published_output_root=output_root,
        )
        try:
            CONTRACTS.validate_contract(receipt, expected_schema_id=RECEIPT_SCHEMA)
        except Exception as exc:
            raise ReportError(f"REPORT_RECEIPT_INVALID: {exc}") from exc
        write_json(receipt_path, receipt)
        os.replace(staging, output_root)
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    data_path = output_root / "general_e2e_report_data.json"
    markdown_path = output_root / "通用场景端到端自动化评测报告.md"
    excel_path = output_root / "通用场景端到端自动化评测报告.xlsx"
    receipt_path = output_root / "receipts/report-receipt.json"
    cli_manifest_path = output_root / "cli-adapter/manifest.json"
    excel_result["output"] = str(excel_path)
    excel_result["validation"] = str(output_root / "previews/excel-validation.json")
    return {
        "status": "PASS",
        "batch_id": data["batch_id"],
        "output_dir": str(output_root),
        "report_data": str(data_path),
        "markdown": str(markdown_path),
        "excel": str(excel_path),
        "receipt": str(receipt_path),
        "cli_adapter_manifest": str(cli_manifest_path),
        "excel_validation": excel_result,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="General E2E 独立报告生成器")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate-inputs", help="校验批次、导入选择与回传内容")
    validate.add_argument("--batch-root", required=True)
    validate.set_defaults(handler=command_validate)

    generate = subparsers.add_parser("generate", help="生成同源 JSON、Markdown、Excel 和 CLI 适配产物")
    generate.add_argument("--batch-root", required=True)
    generate.add_argument("--output-dir", required=True)
    generate.add_argument("--generated-at")
    generate.add_argument("--node", default=os.environ.get("GENERAL_E2E_NODE", "node"))
    generate.add_argument(
        "--node-modules",
        default=os.environ.get("GENERAL_E2E_NODE_MODULES"),
        required=os.environ.get("GENERAL_E2E_NODE_MODULES") is None,
        help="包含 @oai/artifact-tool 的 node_modules 目录",
    )
    generate.add_argument("--skip-preview", action="store_true")
    generate.set_defaults(handler=command_generate)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = args.handler(args)
    except ReportError as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
