#!/usr/bin/env python3
"""Persist Web E2E stage state and validate offline handoffs."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


STATE_SCHEMA = "wildclawbench.run-web-e2e/v1"
RETURN_SCHEMA = "wildclawbench.web-e2e-return-receipt/v1"
IMPORT_SCHEMA = "wildclawbench.web-e2e-import-receipt/v1"
SUBMISSION_SCHEMA = "wildclawbench.web-e2e-submission/v1"
RUNTIME_DIRECTORY_POLICY_SCHEMA = "wildclawbench.web-e2e-runtime-directory-policy/v1"
ALL_STAGES = ("prepare", "execute", "score", "package", "collect", "report")
SCOPE_STAGES = {
    "batch": ("prepare", "collect", "report"),
    "unit": ("execute", "score", "package"),
}
PRESETS = {
    "admin": {"batch": SCOPE_STAGES["batch"], "unit": ()},
    "worker": {"batch": (), "unit": SCOPE_STAGES["unit"]},
    "full-local": {"batch": SCOPE_STAGES["batch"], "unit": SCOPE_STAGES["unit"]},
}
STAGE_STATUSES = {
    "NOT_SELECTED", "PENDING", "RUNNING", "WAITING_HANDOFF",
    "COMPLETED", "NEEDS_ATTENTION", "FAILED",
}
SECRET_NAMES = {
    ".env", ".env.local", ".env.production", "id_rsa", "id_ed25519",
    "credentials.json", "secrets.json", "my_api.json",
}
SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx")
IGNORED_RUNTIME_DIRS = {"node_modules", ".cache", ".vite"}
FORBIDDEN_DIRS = {".git", "runtime-workspace"}
EXCLUDED_DIRS = FORBIDDEN_DIRS | IGNORED_RUNTIME_DIRS | {".run-web-e2e", "__pycache__"}
EXCLUDED_FILES = {".DS_Store"}


def runtime_directory_policy() -> dict:
    return {
        "schema_version": RUNTIME_DIRECTORY_POLICY_SCHEMA,
        "ignored_directories": sorted(IGNORED_RUNTIME_DIRS),
        "forbidden_directories": [".git"],
        "scoring_copy": "exclude-ignored-directories",
        "return_archive": "exclude-ignored-directories",
    }


def validate_runtime_directory_policy(value: object) -> bool:
    if value is None:
        return False
    expected = runtime_directory_policy()

    def same_string_set(actual: object, wanted: list[str]) -> bool:
        return (
            isinstance(actual, list)
            and all(isinstance(item, str) for item in actual)
            and len(actual) == len(set(actual))
            and set(actual) == set(wanted)
        )

    valid = (
        isinstance(value, dict)
        and set(value) == set(expected)
        and value.get("schema_version") == expected["schema_version"]
        and same_string_set(value.get("ignored_directories"), expected["ignored_directories"])
        and same_string_set(value.get("forbidden_directories"), expected["forbidden_directories"])
        and value.get("scoring_copy") == expected["scoring_copy"]
        and value.get("return_archive") == expected["return_archive"]
    )
    if not valid:
        schema = value.get("schema_version") if isinstance(value, dict) else None
        raise ValueError(f"候选运行时目录策略不兼容: {schema or 'missing'}")
    return True


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON 顶层必须是对象: {path}")
    return value


def write_json_atomic(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def state_path(root: Path, scope: str) -> Path:
    return root / ".run-web-e2e" / ("batch-state.json" if scope == "batch" else "unit-state.json")


def parse_stages(values: list[str]) -> list[str]:
    stages: list[str] = []
    for raw in values:
        for item in raw.split(","):
            stage = item.strip().lower()
            if stage and stage not in stages:
                stages.append(stage)
    unknown = [stage for stage in stages if stage not in ALL_STAGES]
    if unknown:
        raise ValueError(f"未知阶段: {', '.join(unknown)}")
    return stages


def selected_stages(args: argparse.Namespace) -> tuple[list[str], str]:
    explicit = parse_stages(args.stage)
    if explicit:
        return [stage for stage in ALL_STAGES if stage in explicit], "explicit_stages"
    if args.preset:
        return list(PRESETS[args.preset][args.scope]), f"preset:{args.preset}"
    return [], "none"


def validate_scope_stages(scope: str, stages: list[str]) -> None:
    illegal = [stage for stage in stages if stage not in SCOPE_STAGES[scope]]
    if illegal:
        raise ValueError(
            f"{scope} 状态不允许阶段 {', '.join(illegal)}；允许值: {', '.join(SCOPE_STAGES[scope])}"
        )


def manifest_for(root: Path, scope: str) -> tuple[Path, dict]:
    path = root / ("batch_manifest.json" if scope == "batch" else "manifest.json")
    if not path.is_file():
        raise FileNotFoundError(f"缺少{scope} manifest: {path}")
    manifest = read_json(path)
    task_ids = manifest.get("task_ids") if scope == "batch" else [item.get("task_id") for item in manifest.get("tasks", [])]
    if not manifest.get("batch_id") or not isinstance(task_ids, list) or not task_ids or any(not item for item in task_ids):
        raise ValueError(f"manifest 身份或 task IDs 无效: {path}")
    if len(task_ids) != len(set(task_ids)):
        raise ValueError(f"manifest task IDs 重复: {path}")
    return path, manifest


def identity_from_manifest(manifest: dict, scope: str) -> dict:
    task_ids = manifest["task_ids"] if scope == "batch" else [item["task_id"] for item in manifest["tasks"]]
    identity = {
        "batch_id": manifest["batch_id"],
        "source_revision": manifest.get("source_revision"),
        "metric_profile": manifest.get("metric_profile"),
        "task_ids": task_ids,
    }
    if scope == "batch":
        identity["harnesses"] = manifest.get("harnesses") or []
    else:
        identity["harness"] = manifest.get("harness") or {}
    return identity


def validate_state(state: dict, scope: str, root: Path) -> None:
    if state.get("schema_version") != STATE_SCHEMA or state.get("scope") != scope:
        raise ValueError(f"运行状态 schema/scope 不兼容: {state_path(root, scope)}")
    selected = state.get("selected_stages")
    stages = state.get("stages")
    if not isinstance(selected, list) or not isinstance(stages, dict):
        raise ValueError("运行状态 selected_stages/stages 无效")
    validate_scope_stages(scope, selected)
    if set(stages) != set(ALL_STAGES) or any(value not in STAGE_STATUSES for value in stages.values()):
        raise ValueError("运行状态 stages 无效")
    for stage in ALL_STAGES:
        expected_selected = stage in selected
        if expected_selected == (stages[stage] == "NOT_SELECTED"):
            raise ValueError(f"运行状态阶段选择不一致: {stage}")
    _, manifest = manifest_for(root, scope)
    if state.get("identity") != identity_from_manifest(manifest, scope):
        raise ValueError("运行状态与当前 manifest 身份不一致")


def load_state(root: Path, scope: str) -> dict:
    path = state_path(root, scope)
    if not path.is_file():
        raise FileNotFoundError(f"缺少运行状态: {path}")
    state = read_json(path)
    validate_state(state, scope, root)
    return state


def save_state(root: Path, scope: str, state: dict) -> None:
    state["updated_at"] = utc_now()
    write_json_atomic(state_path(root, scope), state)


def init_state(args: argparse.Namespace) -> dict:
    root = Path(args.root).expanduser().resolve()
    path = state_path(root, args.scope)
    stages, source = selected_stages(args)
    if path.exists():
        state = load_state(root, args.scope)
        if not stages:
            return {"created": False, "state": state}
        validate_scope_stages(args.scope, stages)
        if stages != state["selected_stages"]:
            raise ValueError("运行计划已冻结；扩大范围请使用 add-stage，不能用 init 覆盖")
        return {"created": False, "state": state}
    if not stages:
        return {
            "created": False,
            "reason": "no_stages_selected",
            "allowed_stages": list(SCOPE_STAGES[args.scope]),
        }
    validate_scope_stages(args.scope, stages)
    _, manifest = manifest_for(root, args.scope)
    now = utc_now()
    state = {
        "schema_version": STATE_SCHEMA,
        "revision": 1,
        "scope": args.scope,
        "selection_source": source,
        "selected_stages": stages,
        "stages": {stage: ("PENDING" if stage in stages else "NOT_SELECTED") for stage in ALL_STAGES},
        "identity": identity_from_manifest(manifest, args.scope),
        "artifacts": {},
        "errors": {},
        "created_at": now,
        "updated_at": now,
    }
    write_json_atomic(path, state)
    return {"created": True, "state": state}


def add_stages(args: argparse.Namespace) -> dict:
    root = Path(args.root).expanduser().resolve()
    state = load_state(root, args.scope)
    additions = parse_stages(args.stage)
    if not additions:
        raise ValueError("add-stage 至少提供一个 --stage")
    validate_scope_stages(args.scope, additions)
    changed = False
    for stage in additions:
        if stage not in state["selected_stages"]:
            state["selected_stages"].append(stage)
            state["stages"][stage] = "PENDING"
            changed = True
    if changed:
        ordered = [stage for stage in ALL_STAGES if stage in state["selected_stages"]]
        state["selected_stages"] = ordered
        state["revision"] += 1
        state["selection_source"] = "add_stage"
        save_state(root, args.scope, state)
    return {"changed": changed, "state": state}


def set_stage(args: argparse.Namespace) -> dict:
    root = Path(args.root).expanduser().resolve()
    state = load_state(root, args.scope)
    if args.stage not in state["selected_stages"]:
        raise ValueError(f"阶段未选择，不能更新: {args.stage}")
    if args.status == "NOT_SELECTED":
        raise ValueError("不能用 set-stage 取消已冻结阶段")
    current = state["stages"][args.stage]
    transitions = {
        "PENDING": {"RUNNING", "WAITING_HANDOFF", "COMPLETED", "NEEDS_ATTENTION", "FAILED"},
        "RUNNING": {"RUNNING", "WAITING_HANDOFF", "COMPLETED", "NEEDS_ATTENTION", "FAILED"},
        "WAITING_HANDOFF": {"RUNNING", "WAITING_HANDOFF", "COMPLETED", "NEEDS_ATTENTION", "FAILED"},
        "NEEDS_ATTENTION": {"RUNNING", "WAITING_HANDOFF", "COMPLETED", "NEEDS_ATTENTION", "FAILED"},
        "FAILED": {"RUNNING", "NEEDS_ATTENTION", "FAILED"},
        "COMPLETED": {"COMPLETED"},
    }
    if args.status not in transitions[current]:
        raise ValueError(f"非法阶段状态迁移: {args.stage}: {current} -> {args.status}")
    state["stages"][args.stage] = args.status
    if args.error:
        state["errors"][args.stage] = {"message": args.error, "recorded_at": utc_now()}
    elif args.status not in {"FAILED", "NEEDS_ATTENTION"}:
        state["errors"].pop(args.stage, None)
    state["revision"] += 1
    save_state(root, args.scope, state)
    return {"state": state}


def validate_execution_receipt(root: Path, manifest: dict) -> Path | None:
    path = root / "execution-receipt.json"
    if not path.is_file():
        return None
    receipt = read_json(path)
    expected_tasks = [item["task_id"] for item in manifest["tasks"]]
    actual_tasks = [item.get("task_id") for item in receipt.get("tasks", [])]
    if (
        receipt.get("schema_version") != "wildclawbench.web-e2e-execution-receipt/v1"
        or receipt.get("batch_id") != manifest["batch_id"]
        or (receipt.get("harness") or {}).get("id") != (manifest.get("harness") or {}).get("id")
        or actual_tasks != expected_tasks
        or not (receipt.get("integrity") or {}).get("valid")
    ):
        raise ValueError(f"execution-receipt.json 身份、范围或完整性无效: {path}")
    validate_runtime_directory_policy(receipt.get("runtime_directory_policy"))
    return path


def validate_submission(root: Path, manifest: dict) -> tuple[Path, dict] | None:
    path = root / "submission.json"
    if not path.is_file():
        return None
    submission = read_json(path)
    expected_tasks = [item["task_id"] for item in manifest["tasks"]]
    unit = submission.get("unit") or {}
    if (
        submission.get("schema_version") != SUBMISSION_SCHEMA
        or submission.get("batch_id") != manifest["batch_id"]
        or submission.get("source_revision") != manifest.get("source_revision")
        or submission.get("metric_profile") != manifest.get("metric_profile")
        or unit.get("harness_id") != (manifest.get("harness") or {}).get("id")
        or submission.get("task_ids") != expected_tasks
        or len(submission.get("tasks") or []) != len(expected_tasks)
        or any(not item.get("valid") for item in submission.get("candidate_artifacts") or [])
        or len(submission.get("candidate_artifacts") or []) != len(expected_tasks)
    ):
        raise ValueError(f"submission.json 身份、范围或候选完整性无效: {path}")
    return path, submission


def valid_import_receipts(root: Path, manifest: dict) -> list[dict]:
    receipt_dir = root / ".run-web-e2e" / "imports"
    receipts: list[dict] = []
    for path in sorted(receipt_dir.glob("*.json")) if receipt_dir.is_dir() else []:
        item = read_json(path)
        if item.get("schema_version") != IMPORT_SCHEMA or item.get("batch_id") != manifest["batch_id"]:
            raise ValueError(f"导入回执无效: {path}")
        receipts.append(item)
    return receipts


def sync_state(root: Path, scope: str, report_output: str = "") -> dict:
    state = load_state(root, scope)
    _, manifest = manifest_for(root, scope)
    if scope == "unit":
        execution = validate_execution_receipt(root, manifest)
        if execution:
            state["artifacts"]["execution_receipt"] = str(execution)
            if "execute" in state["selected_stages"]:
                state["stages"]["execute"] = "COMPLETED"
        submission_result = validate_submission(root, manifest)
        if submission_result:
            submission_path, _ = submission_result
            state["artifacts"]["submission"] = str(submission_path)
            if "score" in state["selected_stages"]:
                state["stages"]["score"] = "COMPLETED"
        package = state.get("artifacts", {}).get("return_package") or {}
        if "package" in state["selected_stages"] and package:
            archive = Path(package.get("archive", ""))
            receipt = Path(package.get("receipt", ""))
            if archive.is_file() and receipt.is_file() and sha256_file(archive) == package.get("sha256"):
                state["stages"]["package"] = "COMPLETED"
            else:
                raise ValueError("已记录的离线回传包缺失或发生漂移")
    else:
        if "prepare" in state["selected_stages"]:
            state["stages"]["prepare"] = "COMPLETED"
            state["artifacts"]["batch_manifest"] = str(root / "batch_manifest.json")
        receipts = valid_import_receipts(root, manifest)
        expected_harnesses = manifest.get("harnesses") or []
        imported = [item.get("harness", {}).get("id") for item in receipts]
        if (
            "collect" in state["selected_stages"]
            and expected_harnesses
            and len(imported) == len(expected_harnesses)
            and set(imported) == set(expected_harnesses)
        ):
            state["stages"]["collect"] = "COMPLETED"
            state["artifacts"]["imports"] = [item.get("archive") for item in receipts]
        output = Path(report_output).expanduser().resolve() if report_output else root / "report"
        required = [
            output / "web_e2e_report_data.json",
            output / "Web站点端到端评测领导版.md",
            output / "Web站点端到端评测报告.xlsx",
        ]
        if "report" in state["selected_stages"] and all(path.is_file() for path in required):
            state["stages"]["report"] = "COMPLETED"
            state["artifacts"]["report"] = [str(path) for path in required]
    save_state(root, scope, state)
    return state


def recommended_actions(state: dict) -> list[dict]:
    actions: list[dict] = []
    status = state["stages"]
    for stage in state["selected_stages"]:
        if status[stage] in {"COMPLETED", "RUNNING", "WAITING_HANDOFF"}:
            continue
        blocked_by = None
        if stage == "score" and status["execute"] != "COMPLETED" and not state["artifacts"].get("execution_receipt"):
            blocked_by = "execution-receipt.json"
        elif stage == "package" and status["score"] != "COMPLETED" and not state["artifacts"].get("submission"):
            blocked_by = "submission.json"
        elif stage == "report" and "collect" in state["selected_stages"] and status["collect"] != "COMPLETED":
            blocked_by = "完整离线回传导入"
        actions.append({
            "stage": stage,
            "status": status[stage],
            "action": "WAIT_FOR_PREREQUISITE" if blocked_by else f"RUN_{stage.upper()}",
            "blocked_by": blocked_by,
        })
    return actions


def command_status(args: argparse.Namespace, sync: bool = False) -> dict:
    root = Path(args.root).expanduser().resolve()
    state = sync_state(root, args.scope, args.report_output) if sync else load_state(root, args.scope)
    return {"state": state, "recommended_actions": recommended_actions(state)}


def check_export_tree(root: Path, *, allow_ignored_execution_runtime_directories: bool = False) -> None:
    for path in root.rglob("*"):
        rel = path.relative_to(root)
        ignored_indexes = [index for index, part in enumerate(rel.parts) if part in IGNORED_RUNTIME_DIRS]
        if ignored_indexes:
            first_ignored = ignored_indexes[0]
            in_execution_workspace = (
                len(rel.parts) >= 5
                and rel.parts[0] == "execution"
                and rel.parts[1] == "tasks"
                and rel.parts[3] == "workspace"
                and first_ignored >= 4
            )
            if path.is_symlink() and first_ignored == len(rel.parts) - 1:
                raise ValueError(f"回传目录包含符号链接: {rel.as_posix()}")
            if not allow_ignored_execution_runtime_directories or not in_execution_workspace:
                raise ValueError(f"回传目录包含未获策略允许的运行时/依赖目录: {rel.as_posix()}")
            continue
        if path.is_symlink():
            raise ValueError(f"回传目录包含符号链接: {rel.as_posix()}")
        if any(part in FORBIDDEN_DIRS for part in rel.parts):
            raise ValueError(f"回传目录包含禁止目录: {rel.as_posix()}")
        name = path.name.lower()
        if path.is_file() and (name in SECRET_NAMES or name.startswith(".env.") or name.endswith(SECRET_SUFFIXES)):
            raise ValueError(f"回传目录包含敏感文件: {rel.as_posix()}")


def should_exclude(relative: Path) -> bool:
    return (
        any(part in EXCLUDED_DIRS for part in relative.parts)
        or relative.name in EXCLUDED_FILES
        or relative.suffix == ".pyc"
    )


def export_return(args: argparse.Namespace) -> dict:
    root = Path(args.package_root).expanduser().resolve()
    output = Path(args.output_dir).expanduser().resolve()
    _, manifest = manifest_for(root, "unit")
    execution = validate_execution_receipt(root, manifest)
    submission_result = validate_submission(root, manifest)
    if execution is None or submission_result is None:
        raise ValueError("离线回传要求有效 execution-receipt.json 和 submission.json")
    _, submission = submission_result
    receipt = read_json(execution)
    allow_ignored_execution_runtime_directories = validate_runtime_directory_policy(
        receipt.get("runtime_directory_policy")
    )
    check_export_tree(
        root,
        allow_ignored_execution_runtime_directories=allow_ignored_execution_runtime_directories,
    )
    harness = submission["unit"]["harness_id"]
    base = f"{submission['batch_id']}__{harness}"
    archive_path = output / f"{base}__return.zip"
    receipt_path = output / f"{base}__return-receipt.json"
    if archive_path.exists() or receipt_path.exists():
        raise FileExistsError(f"回传目标已存在，拒绝覆盖: {archive_path} / {receipt_path}")
    output.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        files = 0
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            relative = path.relative_to(root)
            if should_exclude(relative):
                continue
            archive.write(path, PurePosixPath(root.name, relative.as_posix()).as_posix())
            files += 1
    receipt = {
        "schema_version": RETURN_SCHEMA,
        "created_at": utc_now(),
        "archive": {
            "filename": archive_path.name,
            "sha256": sha256_file(archive_path),
            "size_bytes": archive_path.stat().st_size,
            "file_count": files,
        },
        "batch_id": submission["batch_id"],
        "source_revision": submission.get("source_revision"),
        "metric_profile": submission["metric_profile"],
        "unit": submission["unit"],
        "task_ids": submission["task_ids"],
    }
    write_json_atomic(receipt_path, receipt)
    state_file = state_path(root, "unit")
    if state_file.is_file():
        state = load_state(root, "unit")
        if "package" in state["selected_stages"]:
            state["stages"]["package"] = "COMPLETED"
            state["artifacts"]["return_package"] = {
                "archive": str(archive_path),
                "receipt": str(receipt_path),
                "sha256": receipt["archive"]["sha256"],
            }
            state["revision"] += 1
            save_state(root, "unit", state)
    return {"archive": str(archive_path), "receipt": str(receipt_path), "identity": receipt}


def validate_zip_members(archive: zipfile.ZipFile) -> str:
    top_levels: set[str] = set()
    submission_members: list[str] = []
    for info in archive.infolist():
        raw = info.filename
        path = PurePosixPath(raw)
        if not raw or raw.startswith("/") or "\\" in raw or ".." in path.parts:
            raise ValueError(f"ZIP 包含不安全路径: {raw}")
        if stat.S_ISLNK(info.external_attr >> 16):
            raise ValueError(f"ZIP 包含符号链接: {raw}")
        if path.parts:
            top_levels.add(path.parts[0])
        if path.name == "submission.json":
            submission_members.append(raw)
    if len(top_levels) != 1:
        raise ValueError("ZIP 必须且只能包含一个顶层 Harness 根目录")
    if len(submission_members) != 1 or len(PurePosixPath(submission_members[0]).parts) != 2:
        raise ValueError("ZIP 顶层 Harness 根目录必须恰好包含一个 submission.json")
    return next(iter(top_levels))


def validate_return_identity(receipt: dict, submission: dict, batch_manifest: dict) -> None:
    harness = submission.get("unit") or {}
    expected = {
        "batch_id": batch_manifest.get("batch_id"),
        "source_revision": batch_manifest.get("source_revision"),
        "metric_profile": batch_manifest.get("metric_profile"),
        "task_ids": batch_manifest.get("task_ids"),
    }
    actual = {
        "batch_id": submission.get("batch_id"),
        "source_revision": submission.get("source_revision"),
        "metric_profile": submission.get("metric_profile"),
        "task_ids": submission.get("task_ids"),
    }
    if receipt.get("schema_version") != RETURN_SCHEMA or submission.get("schema_version") != SUBMISSION_SCHEMA:
        raise ValueError("return receipt 或 submission schema 不兼容")
    if actual != expected:
        raise ValueError(f"回传包批次、revision、Profile 或 task IDs 不匹配: {actual} != {expected}")
    if receipt.get("batch_id") != actual["batch_id"] or receipt.get("source_revision") != actual["source_revision"]:
        raise ValueError("return receipt 与 submission 身份不一致")
    if receipt.get("metric_profile") != actual["metric_profile"] or receipt.get("task_ids") != actual["task_ids"]:
        raise ValueError("return receipt 与 submission Profile/task IDs 不一致")
    if receipt.get("unit") != submission.get("unit"):
        raise ValueError("return receipt 与 submission unit 不一致")
    harness_id = harness.get("harness_id")
    if not harness_id or harness_id not in (batch_manifest.get("harnesses") or []):
        raise ValueError(f"回传 Harness 不属于本批次: {harness_id}")


def import_return(args: argparse.Namespace) -> dict:
    batch_root = Path(args.batch_root).expanduser().resolve()
    archive_path = Path(args.archive).expanduser().resolve()
    receipt_path = Path(args.receipt).expanduser().resolve()
    _, batch_manifest = manifest_for(batch_root, "batch")
    receipt = read_json(receipt_path)
    archive_meta = receipt.get("archive") or {}
    digest = sha256_file(archive_path)
    if archive_meta.get("filename") != archive_path.name or archive_meta.get("sha256") != digest:
        raise ValueError("回传 ZIP 文件名或 SHA-256 与 receipt 不一致")
    if archive_meta.get("size_bytes") != archive_path.stat().st_size:
        raise ValueError("回传 ZIP 大小与 receipt 不一致")
    returns_root = batch_root / "returns"
    returns_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".run-web-e2e-import-", dir=returns_root) as tmp:
        temporary = Path(tmp)
        with zipfile.ZipFile(archive_path) as archive:
            top_level = validate_zip_members(archive)
            archive.extractall(temporary)
        extracted = temporary / top_level
        if not extracted.is_dir():
            raise ValueError("ZIP 顶层 Harness 根目录不存在")
        submission = read_json(extracted / "submission.json")
        validate_return_identity(receipt, submission, batch_manifest)
        harness_id = submission["unit"]["harness_id"]
        target = returns_root / harness_id
        import_receipt_path = batch_root / ".run-web-e2e" / "imports" / f"{harness_id}.json"
        if target.exists() or import_receipt_path.exists():
            if target.is_dir() and import_receipt_path.is_file():
                existing = read_json(import_receipt_path)
                if existing.get("archive_sha256") == digest:
                    return {"imported": False, "idempotent": True, "target": str(target), "receipt": existing}
            raise FileExistsError(f"Harness 回传目标已存在且内容不一致，拒绝覆盖: {target}")
        published = returns_root / f".{harness_id}.{os.getpid()}.pending"
        if published.exists():
            raise FileExistsError(f"存在未收口的导入暂存目录: {published}")
        shutil.move(str(extracted), published)
        os.replace(published, target)
    import_receipt = {
        "schema_version": IMPORT_SCHEMA,
        "imported_at": utc_now(),
        "batch_id": submission["batch_id"],
        "source_revision": submission.get("source_revision"),
        "metric_profile": submission["metric_profile"],
        "harness": {"id": submission["unit"]["harness_id"], "display_name": submission["unit"].get("harness_display_name")},
        "model": {"id": submission["unit"].get("model_id"), "display_name": submission["unit"].get("model_display_name")},
        "task_ids": submission["task_ids"],
        "archive": str(archive_path),
        "archive_sha256": digest,
        "target": str(target),
    }
    write_json_atomic(import_receipt_path, import_receipt)
    batch_state = state_path(batch_root, "batch")
    if batch_state.is_file():
        sync_state(batch_root, "batch")
    return {"imported": True, "idempotent": False, "target": str(target), "receipt": import_receipt}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="动态组合并恢复 Web E2E 阶段")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_state_args(subparser: argparse.ArgumentParser, *, selection: bool = False) -> None:
        subparser.add_argument("--scope", required=True, choices=("batch", "unit"))
        subparser.add_argument("--root", required=True)
        if selection:
            subparser.add_argument("--stage", action="append", default=[])
            subparser.add_argument("--preset", choices=tuple(PRESETS))

    init = subparsers.add_parser("init")
    add_state_args(init, selection=True)
    add = subparsers.add_parser("add-stage")
    add_state_args(add, selection=True)
    add.set_defaults(preset=None)
    status_parser = subparsers.add_parser("status")
    add_state_args(status_parser)
    status_parser.add_argument("--report-output", default="")
    sync_parser = subparsers.add_parser("sync")
    add_state_args(sync_parser)
    sync_parser.add_argument("--report-output", default="")
    resume_parser = subparsers.add_parser("resume")
    add_state_args(resume_parser)
    resume_parser.add_argument("--report-output", default="")
    set_parser = subparsers.add_parser("set-stage")
    add_state_args(set_parser)
    set_parser.add_argument("--stage", required=True, choices=ALL_STAGES)
    set_parser.add_argument("--status", required=True, choices=tuple(sorted(STAGE_STATUSES - {"NOT_SELECTED"})))
    set_parser.add_argument("--error", default="")
    export_parser = subparsers.add_parser("export-return")
    export_parser.add_argument("--package-root", required=True)
    export_parser.add_argument("--output-dir", required=True)
    import_parser = subparsers.add_parser("import-return")
    import_parser.add_argument("--batch-root", required=True)
    import_parser.add_argument("--archive", required=True)
    import_parser.add_argument("--receipt", required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        if args.command == "init":
            result = init_state(args)
        elif args.command == "add-stage":
            result = add_stages(args)
        elif args.command == "set-stage":
            result = set_stage(args)
        elif args.command == "status":
            result = command_status(args, sync=False)
        elif args.command in {"sync", "resume"}:
            result = command_status(args, sync=True)
        elif args.command == "export-return":
            result = export_return(args)
        elif args.command == "import-return":
            result = import_return(args)
        else:
            raise ValueError(f"未知命令: {args.command}")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (FileNotFoundError, FileExistsError, ValueError, zipfile.BadZipFile) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False, indent=2), file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
