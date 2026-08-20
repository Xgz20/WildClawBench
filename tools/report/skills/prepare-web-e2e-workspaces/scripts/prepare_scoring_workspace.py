#!/usr/bin/env python3
"""Create an isolated score/tasks tree from execution/tasks plus a scoring ZIP.

This is an optional fallback for testers whose ZIP application cannot merge the
incremental score overlay. It uses only the Python standard library.
"""
from __future__ import annotations

import argparse
import json
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


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON 顶层必须是对象: {path}")
    return value


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


def prepare_scoring_workspace(package_root: Path, archive_path: Path) -> Path:
    manifest = load_json(package_root / "manifest.json")
    execution_tasks = package_root / "execution" / "tasks"
    score_root = package_root / "score"
    if not execution_tasks.is_dir():
        raise FileNotFoundError(f"缺少执行任务目录: {execution_tasks}")
    task_ids = [str(item.get("task_id") or "") for item in manifest.get("tasks") or []]
    if not task_ids or any(not task_id for task_id in task_ids):
        raise ValueError("manifest.tasks 为空或 task_id 非法")
    if score_root.exists() and (not score_root.is_dir() or any(score_root.iterdir())):
        raise FileExistsError(
            f"目标已包含内容，拒绝覆盖: {score_root}。请先确认其中没有评分结果，再将已有内容移走。"
        )

    with tempfile.TemporaryDirectory(prefix=".web-e2e-score-", dir=package_root) as temporary:
        staging = Path(temporary)
        prepared_score = staging / "score"
        shutil.copytree(execution_tasks, prepared_score / "tasks", symlinks=True)
        extract_overlay(archive_path, staging)
        validate_prepared_score(prepared_score, manifest)
        if score_root.exists():
            score_root.rmdir()
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
