#!/usr/bin/env python3
"""Create an isolated score/tasks tree from execution/tasks plus a scoring ZIP.

This is an optional fallback for testers whose ZIP application cannot merge the
incremental score overlay. It uses only the Python standard library.
"""
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
from pathlib import Path, PurePosixPath


FORBIDDEN_OVERLAY_NAMES = {
    "PROMPT.md",
    "execution_record.json",
    "task_manifest.json",
    "workspace",
}
ALLOWED_TASK_OVERLAY_NAMES = {"private-scoring", ".web-e2e-scoring-ready"}
IGNORABLE_SCORE_FILE_NAMES = {
    ".DS_Store",
    ".localized",
    "Thumbs.db",
    "desktop.ini",
}
TREE_HASH_ALGORITHM = "wildclawbench.workspace-tree-sha256/v1"
CANDIDATE_ARTIFACT_SCHEMA = "wildclawbench.web-e2e-candidate-artifact/v1"
EXECUTION_RECEIPT_SCHEMA = "wildclawbench.web-e2e-execution-receipt/v1"
EXCLUDED_TREE_DIRS = {".git", ".cache", ".vite", "node_modules"}


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON 顶层必须是对象: {path}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot_workspace(root: Path, maximum_files: int = 20_000) -> dict:
    """Match execute-web-e2e's snapshotTree candidate hash contract."""
    if root.is_symlink() or not root.is_dir():
        raise ValueError(f"候选 workspace 缺失或为符号链接: {root}")
    entries: list[dict] = []
    excluded_runtime_directories: list[str] = []

    def walk(current: Path, prefix: str = "") -> None:
        children = sorted(os.scandir(current), key=lambda item: item.name)
        for child in children:
            relative = f"{prefix}/{child.name}" if prefix else child.name
            child_path = Path(child.path)
            if child.is_dir(follow_symlinks=False):
                if child.name in EXCLUDED_TREE_DIRS:
                    excluded_runtime_directories.append(relative)
                else:
                    walk(child_path, relative)
                continue
            if len(entries) >= maximum_files:
                raise ValueError(f"候选目录文件数超过上限 {maximum_files}")
            if child.is_symlink():
                target = os.readlink(child_path)
                entries.append({
                    "path": relative,
                    "type": "symlink",
                    "sha256": hashlib.sha256(target.encode("utf-8")).hexdigest(),
                    "size": len(target),
                })
            elif child.is_file(follow_symlinks=False):
                entries.append({
                    "path": relative,
                    "type": "file",
                    "sha256": sha256_file(child_path),
                    "size": child.stat(follow_symlinks=False).st_size,
                })

    walk(root)
    digest = hashlib.sha256()
    for entry in entries:
        digest.update(entry["path"].encode("utf-8"))
        digest.update(b"\0")
        digest.update(entry["type"].encode("utf-8"))
        digest.update(b"\0")
        digest.update(entry["sha256"].encode("utf-8"))
        digest.update(b"\n")
    return {
        "sha256": digest.hexdigest(),
        "file_count": len(entries),
        "total_bytes": sum(entry["size"] for entry in entries),
        "excluded_directories": sorted(EXCLUDED_TREE_DIRS),
        "excluded_runtime_directories": sorted(excluded_runtime_directories),
    }


def load_execution_receipt(package_root: Path, manifest: dict) -> tuple[dict, dict[str, dict]]:
    path = package_root / "execution-receipt.json"
    receipt = load_json(path)
    if receipt.get("schema_version") != EXECUTION_RECEIPT_SCHEMA:
        raise ValueError(f"execution-receipt.json schema 不兼容: {receipt.get('schema_version')}")
    if receipt.get("integrity", {}).get("valid") is not True:
        raise ValueError("execution-receipt.json 的 integrity.valid 不是 true")
    if receipt.get("batch_id") != manifest.get("batch_id"):
        raise ValueError("execution-receipt.json batch_id 与 manifest 不一致")
    if (receipt.get("harness") or {}).get("id") != (manifest.get("harness") or {}).get("id"):
        raise ValueError("execution-receipt.json Harness 与 manifest 不一致")
    tasks = receipt.get("tasks") or []
    by_id = {str(item.get("task_id") or ""): item for item in tasks}
    manifest_ids = [str(item.get("task_id") or "") for item in manifest.get("tasks") or []]
    if len(by_id) != len(tasks) or set(by_id) != set(manifest_ids):
        raise ValueError("execution-receipt.json 任务范围与 manifest 不一致")
    for task_id, task in by_id.items():
        frozen = str((task.get("workspace") or {}).get("final_sha256") or "")
        if len(frozen) != 64:
            raise ValueError(f"execution-receipt.json 缺少最终 workspace SHA-256: {task_id}")
    return receipt, by_id


def verify_workspace(root: Path, expected_sha256: str, label: str) -> dict:
    from datetime import datetime, timezone

    checked_at = datetime.now(timezone.utc).isoformat()
    snapshot = snapshot_workspace(root)
    result = {
        "label": label,
        "checked_at": checked_at,
        "sha256": snapshot["sha256"],
        "file_count": snapshot["file_count"],
        "total_bytes": snapshot["total_bytes"],
        "excluded_runtime_directories": snapshot["excluded_runtime_directories"],
        "valid": snapshot["sha256"] == expected_sha256 and not snapshot["excluded_runtime_directories"],
    }
    if not result["valid"]:
        if snapshot["excluded_runtime_directories"]:
            raise ValueError(
                f"候选产物包含禁止的运行时目录: {label}: "
                f"{', '.join(snapshot['excluded_runtime_directories'])}"
            )
        raise ValueError(
            f"候选产物发生漂移: {label}: 期望 {expected_sha256}，实际 {snapshot['sha256']}"
        )
    return result


def resolve_receipt_model(receipt: dict, receipt_task: dict) -> tuple[dict, dict]:
    selection = receipt_task.get("model_selection") or {}
    requested = str(selection.get("requested_model") or "").strip()
    actual = str(selection.get("actual_model") or "").strip()
    mode = str(selection.get("mode") or ("explicit" if requested else "current")).strip()
    if (
        mode not in {"current", "explicit"}
        or not actual
        or (mode == "explicit" and (not requested or requested != actual))
        or (mode == "current" and bool(requested))
    ):
        raise ValueError(
            f"execution-receipt.json 模型回读无效: {receipt_task.get('task_id')}: "
            f"mode={mode!r}, requested={requested!r}, actual={actual!r}"
        )
    declared = receipt.get("model") or {}
    declared_id = str(declared.get("id") or "").strip()
    declared_display = str(declared.get("display_name") or "").strip()
    if declared_id and actual not in {declared_id, declared_display}:
        raise ValueError(
            f"execution-receipt.json 顶层模型与实际回读不一致: "
            f"{declared_id!r}/{declared_display!r} vs {actual!r}"
        )
    return (
        {"id": declared_id or actual, "display_name": declared_display or actual},
        {
            "mode": mode,
            "requested_model": requested or None,
            "actual_model": actual,
            "method": selection.get("method"),
        },
    )


def bind_scoring_model(task_root: Path, receipt: dict, receipt_task: dict) -> tuple[dict, dict]:
    model, selection = resolve_receipt_model(receipt, receipt_task)
    contract_path = task_root / "private-scoring" / "task_contract.json"
    contract = load_json(contract_path)
    identity = contract.setdefault("identity", {})
    existing = identity.get("model") or contract.get("model") or {}
    existing_id = str(existing.get("id") or "").strip()
    if existing_id and existing_id != model["id"]:
        raise ValueError(
            f"task contract 模型与执行回读不一致: {receipt_task['task_id']}: "
            f"{existing_id!r} vs {model['id']!r}"
        )
    identity["model"] = model
    contract_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    execution_record_path = task_root / "execution_record.json"
    if execution_record_path.is_file():
        execution_record = load_json(execution_record_path)
        execution_model = execution_record.get("model") or {}
        execution_model_id = str(execution_model.get("id") or "").strip()
        if execution_model_id and execution_model_id != model["id"]:
            raise ValueError(
                f"execution record 模型与执行回读不一致: {receipt_task['task_id']}: "
                f"{execution_model_id!r} vs {model['id']!r}"
            )
        execution_record["model"] = model
        execution_record_path.write_text(
            json.dumps(execution_record, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return model, selection


def write_candidate_artifact_lock(
    task_root: Path,
    manifest: dict,
    receipt: dict,
    receipt_task: dict,
    execution_check: dict,
    score_check: dict,
    receipt_sha256: str,
    model: dict,
    model_selection: dict,
) -> Path:
    task_id = str(receipt_task["task_id"])
    lock_path = task_root / "private-scoring" / "candidate_artifact.json"
    payload = {
        "schema_version": CANDIDATE_ARTIFACT_SCHEMA,
        "hash_algorithm": TREE_HASH_ALGORITHM,
        "batch_id": manifest.get("batch_id"),
        "task_id": task_id,
        "harness_id": (manifest.get("harness") or {}).get("id"),
        "model": model,
        "model_selection": model_selection,
        "expected_sha256": receipt_task["workspace"]["final_sha256"],
        "attempt_id": receipt_task.get("attempt_id"),
        "execution_receipt": {
            "schema_version": receipt.get("schema_version"),
            "generated_at": receipt.get("generated_at"),
            "run_id": receipt.get("run_id"),
            "sha256": receipt_sha256,
        },
        "prepared_at": score_check["checked_at"],
        "checks": {
            "execution_before_copy": execution_check,
            "score_after_copy": score_check,
        },
    }
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return lock_path


def find_scoring_archive(package_root: Path, manifest: dict, explicit: str) -> Path:
    if explicit:
        archive = Path(explicit).expanduser().resolve()
        if not archive.is_file():
            raise FileNotFoundError(f"评分包不存在: {archive}")
        return archive
    filename = str(manifest.get("scoring_archive") or "").strip()
    if not filename:
        raise ValueError("manifest.json 缺少 scoring_archive")
    candidates = [package_root.parent / filename, package_root / filename]
    matches = [path for path in candidates if path.is_file()]
    if len(matches) != 1:
        locations = "、".join(str(path) for path in candidates)
        raise FileNotFoundError(f"请把评分包放到 Harness 根目录同级或根目录内: {locations}")
    return matches[0]


def safe_member_path(info: zipfile.ZipInfo) -> PurePosixPath:
    name = info.filename.replace("\\", "/")
    relative = PurePosixPath(name)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise ValueError(f"评分包包含不安全路径: {info.filename}")
    if relative.parts[0] != "score":
        raise ValueError(f"评分包只能包含 score/ 增量目录: {info.filename}")
    mode = (info.external_attr >> 16) & 0o170000
    if mode == stat.S_IFLNK:
        raise ValueError(f"评分包不得包含符号链接: {info.filename}")
    if len(relative.parts) >= 4 and relative.parts[:2] == ("score", "tasks"):
        task_relative = relative.parts[3:]
        if task_relative and task_relative[0] in FORBIDDEN_OVERLAY_NAMES:
            raise ValueError(f"评分包试图覆盖执行产物: {info.filename}")
        if task_relative and task_relative[0] not in ALLOWED_TASK_OVERLAY_NAMES:
            raise ValueError(f"评分包包含非评分材料: {info.filename}")
    return relative


def extract_overlay(archive_path: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive_path) as archive:
        for info in archive.infolist():
            relative = safe_member_path(info)
            target = destination.joinpath(*relative.parts)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                raise FileExistsError(f"评分包与执行副本存在同名文件，拒绝覆盖: {target}")
            with archive.open(info) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)


def validate_prepared_score(score_root: Path, manifest: dict) -> None:
    task_entries = manifest.get("tasks") or []
    task_ids = [str(item.get("task_id") or "") for item in task_entries]
    expected_entries = {str(item["task_id"]): item for item in task_entries}
    actual = sorted(path.name for path in (score_root / "tasks").iterdir() if path.is_dir())
    if actual != sorted(task_ids):
        raise ValueError(f"评分任务范围不一致，期望 {sorted(task_ids)}，实际 {actual}")
    for task_id in task_ids:
        task_root = score_root / "tasks" / task_id
        required = (
            task_root / "workspace",
            task_root / "PROMPT.md",
            task_root / "private-scoring/task_contract.json",
            task_root / ".web-e2e-scoring-ready",
        )
        missing = [path.relative_to(score_root).as_posix() for path in required if not path.exists()]
        if missing:
            raise ValueError(f"评分工作空间缺少文件: {task_id}: {missing}")
        contract = load_json(task_root / "private-scoring/task_contract.json")
        expected = expected_entries[task_id]
        identity = contract.get("identity") or {}
        if identity.get("batch_id") != manifest.get("batch_id") or identity.get("task_id") != task_id:
            raise ValueError(f"task contract 身份不一致: {task_id}")
        if identity.get("source_revision") != manifest.get("source_revision"):
            raise ValueError(f"task contract source_revision 不一致: {task_id}")
        manifest_harness = (manifest.get("harness") or {}).get("id")
        contract_harness = (identity.get("harness") or {}).get("id")
        if manifest_harness != contract_harness:
            raise ValueError(f"task contract harness 不一致: {task_id}")
        expected_task_hash = expected.get("task_sha256")
        expected_workspace_hash = expected.get("workspace_exec_sha256")
        source = contract.get("source") or {}
        if source.get("task_sha256") != expected_task_hash:
            raise ValueError(f"task contract task_sha256 不一致: {task_id}")
        if source.get("workspace_exec_sha256") != expected_workspace_hash:
            raise ValueError(f"task contract workspace_exec_sha256 不一致: {task_id}")
        execution_record_path = task_root / "execution_record.json"
        if execution_record_path.is_file():
            execution_record = load_json(execution_record_path)
            if (
                execution_record.get("batch_id") != manifest.get("batch_id")
                or execution_record.get("task_id") != task_id
                or (execution_record.get("harness") or {}).get("id") != manifest_harness
            ):
                raise ValueError(f"execution record 身份不一致: {task_id}")
        marker = (task_root / ".web-e2e-scoring-ready").read_text(encoding="utf-8").splitlines()
        if marker != [str(manifest.get("batch_id")), task_id]:
            raise ValueError(f"评分就绪标记身份不一致: {task_id}")


def meaningful_score_entries(score_root: Path) -> list[Path]:
    """Return entries that make an existing score directory unsafe to replace."""
    if score_root.is_symlink() or not score_root.is_dir():
        return [score_root]

    meaningful: list[Path] = []
    pending = [score_root]
    while pending:
        directory = pending.pop()
        for entry in directory.iterdir():
            if entry.is_symlink():
                meaningful.append(entry)
            elif entry.is_dir():
                pending.append(entry)
            elif entry.is_file() and (
                entry.name in IGNORABLE_SCORE_FILE_NAMES or entry.name.startswith("._")
            ):
                continue
            else:
                meaningful.append(entry)
    return meaningful


def ensure_score_root_replaceable(score_root: Path) -> None:
    if not score_root.exists() and not score_root.is_symlink():
        return
    meaningful = meaningful_score_entries(score_root)
    if meaningful:
        first = meaningful[0]
        raise FileExistsError(
            f"目标已包含内容，拒绝覆盖: {score_root}（例如 {first}）。"
            "请先确认其中没有评分结果，再将已有内容移走。"
        )


def copy_manifest_execution_tasks(execution_tasks: Path, destination: Path, manifest: dict) -> None:
    """Copy only manifest-declared task directories, never runner control state."""
    destination.mkdir(parents=True, exist_ok=False)
    for entry in manifest.get("tasks") or []:
        task_id = str(entry.get("task_id") or "")
        if not task_id or Path(task_id).name != task_id or task_id in {".", ".."}:
            raise ValueError(f"manifest task_id 非法: {task_id!r}")
        source = execution_tasks / task_id
        if source.is_symlink() or not source.is_dir():
            raise ValueError(f"执行任务目录缺失或为符号链接: {source}")
        shutil.copytree(source, destination / task_id, symlinks=True)


def prepare_scoring_workspace(package_root: Path, archive_path: Path) -> Path:
    manifest = load_json(package_root / "manifest.json")
    receipt, receipt_tasks = load_execution_receipt(package_root, manifest)
    receipt_sha256 = sha256_file(package_root / "execution-receipt.json")
    execution_tasks = package_root / "execution" / "tasks"
    score_root = package_root / "score"
    if not execution_tasks.is_dir():
        raise FileNotFoundError(f"缺少执行任务目录: {execution_tasks}")
    task_ids = [str(item.get("task_id") or "") for item in manifest.get("tasks") or []]
    if not task_ids or any(not task_id for task_id in task_ids):
        raise ValueError("manifest.tasks 为空或 task_id 非法")
    ensure_score_root_replaceable(score_root)

    execution_checks: dict[str, dict] = {}
    for task_id in task_ids:
        execution_checks[task_id] = verify_workspace(
            execution_tasks / task_id / "workspace",
            receipt_tasks[task_id]["workspace"]["final_sha256"],
            f"execution/{task_id}/before-copy",
        )

    with tempfile.TemporaryDirectory(prefix=".web-e2e-score-", dir=package_root) as temporary:
        staging = Path(temporary)
        prepared_score = staging / "score"
        copy_manifest_execution_tasks(execution_tasks, prepared_score / "tasks", manifest)
        extract_overlay(archive_path, staging)
        for task_id in task_ids:
            model, model_selection = bind_scoring_model(
                prepared_score / "tasks" / task_id,
                receipt,
                receipt_tasks[task_id],
            )
            score_check = verify_workspace(
                prepared_score / "tasks" / task_id / "workspace",
                receipt_tasks[task_id]["workspace"]["final_sha256"],
                f"score/{task_id}/after-copy",
            )
            write_candidate_artifact_lock(
                prepared_score / "tasks" / task_id,
                manifest,
                receipt,
                receipt_tasks[task_id],
                execution_checks[task_id],
                score_check,
                receipt_sha256,
                model,
                model_selection,
            )
        validate_prepared_score(prepared_score, manifest)
        for task_id in task_ids:
            verify_workspace(
                execution_tasks / task_id / "workspace",
                receipt_tasks[task_id]["workspace"]["final_sha256"],
                f"execution/{task_id}/before-publish",
            )
            verify_workspace(
                prepared_score / "tasks" / task_id / "workspace",
                receipt_tasks[task_id]["workspace"]["final_sha256"],
                f"score/{task_id}/before-publish",
            )
        ensure_score_root_replaceable(score_root)
        if score_root.exists() or score_root.is_symlink():
            shutil.rmtree(score_root)
        prepared_score.replace(score_root)
    return score_root


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="准备 Web E2E 单题评分工作空间")
    parser.add_argument("--package-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--scoring-archive", default="")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        package_root = Path(args.package_root).expanduser().resolve()
        manifest = load_json(package_root / "manifest.json")
        archive = find_scoring_archive(package_root, manifest, args.scoring_archive)
        score_root = prepare_scoring_workspace(package_root, archive)
    except (OSError, ValueError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    print(f"PASS: 评分工作空间已生成：{score_root}")


if __name__ == "__main__":
    main()
