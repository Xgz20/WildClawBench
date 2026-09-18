#!/usr/bin/env python3
"""Prepare and execute the Docker-free General E2E local scoring runtime."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from typing import Any
import uuid
import zipfile


ATTEMPT_SCHEMA = "wildclawbench.general-e2e-local-scoring-attempt/v1"
AUDIT_SCHEMA = "wildclawbench.general-e2e-rule-runtime-audit/v1"
JUDGE_CONFIG_SCHEMA = "wildclawbench.general-e2e-judge-config/v1"
SEMANTIC_CATALOG_SCHEMA = "wildclawbench.general-e2e-semantic-evidence-catalog/v1"
SEMANTIC_REQUEST_SCHEMA = "wildclawbench.general-e2e-semantic-request/v1"
SEMANTIC_RESPONSE_SCHEMA = "wildclawbench.general-e2e-codex-judge-response/v1"
SEMANTIC_QUERY_LOG_SCHEMA = "wildclawbench.general-e2e-semantic-query-log/v1"
SEMANTIC_AUDIT_SCHEMA = "wildclawbench.general-e2e-semantic-audit/v1"
SCORE_AUDIT_SCHEMA = "wildclawbench.general-e2e-score-audit/v1"
SCORE_SCHEMA_ID = "urn:wildclawbench:schema:general-e2e:score:v1"
SEMANTIC_PROMPT_PROTOCOL = "wildclawbench.general-e2e-codex-judge-prompt/v1"
RUNTIME_LOCK_SCHEMA = "wildclawbench.general-e2e-rule-runtime-lock/v1"
RUNTIME_MARKER_SCHEMA = "wildclawbench.general-e2e-rule-runtime-marker/v1"
WORKER_REQUEST_SCHEMA = "wildclawbench.general-e2e-rule-worker-request/v1"
WORKER_RESULT_SCHEMA = "wildclawbench.general-e2e-rule-worker-result/v1"
PACKAGE_SCHEMA = "urn:wildclawbench:schema:general-e2e:package-manifest:v1"
CANDIDATE_SCHEMA = "wildclawbench.general-e2e-candidate-artifact/v1"
TREE_HASH_ALGORITHM = "wildclawbench.workspace-tree-sha256/v1"
DATASET_TREE_HASH_ALGORITHM = "wildclawbench.dataset-tree-sha256/v1"
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
MAX_PACKAGE_MEMBER_BYTES = 64 * 1024 * 1024
MAX_PACKAGE_TOTAL_BYTES = 512 * 1024 * 1024
MAX_PACKAGE_MEMBERS = 20_000
MAX_WORKER_LOG_BYTES = 4 * 1024 * 1024
MAX_WORKER_RESULT_BYTES = 16 * 1024 * 1024
MAX_EVIDENCE_TEXT_PAGE_CHARS = 256 * 1024
SEMANTIC_PROTOCOLS = {"codex-agent-judge-v1", "api-judge-v1"}
REASONING_EFFORTS = {
    "none",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
    "ultra",
}
_RUBRIC_HEADING_RE = re.compile(r"^###\s+(.*?)\s*\((.*?)\)\s*$")
_RUBRIC_METADATA_RE = re.compile(
    r"(?:^|,)\s*(key|weight)\s*:\s*([^,]+)\s*"
)
_RUBRIC_SCORE_RE = re.compile(
    r"^\s*(?:\*\*\s*)?Score\s+"
    r"([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*(?:\*\*)?\s*[:：]",
    re.IGNORECASE,
)


class ScoringRuntimeError(ValueError):
    """Stable failure raised by the local scoring runtime."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _pretty_json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _absolute_executable(path: Path, code: str) -> Path:
    absolute = Path(os.path.abspath(path.expanduser()))
    if not absolute.is_file():
        raise ScoringRuntimeError(code, str(absolute))
    return absolute


def _read_json(path: Path, *, code: str = "JSON_INVALID") -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ScoringRuntimeError(code, f"{path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ScoringRuntimeError(code, f"{path}: top-level value must be an object")
    return value


def _write_new_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(_pretty_json_bytes(value))
    except FileExistsError as exc:
        raise ScoringRuntimeError("OUTPUT_EXISTS", str(path)) from exc


def _publish_new_files(files: Mapping[Path, bytes]) -> None:
    """Publish a small terminal artifact set without leaving normal partial writes."""

    published: list[Path] = []
    try:
        for path, payload in files.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                with path.open("xb") as handle:
                    handle.write(payload)
            except FileExistsError as exc:
                raise ScoringRuntimeError("OUTPUT_EXISTS", str(path)) from exc
            published.append(path)
    except BaseException:
        for path in reversed(published):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        raise


def _atomic_write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.tmp-{uuid.uuid4().hex}"
    try:
        with temporary.open("xb") as handle:
            handle.write(_pretty_json_bytes(value))
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise ScoringRuntimeError("IDENTIFIER_INVALID", f"{label}={value!r}")
    return value


def _required_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ScoringRuntimeError("STRING_INVALID", f"{label}={value!r}")
    return value.strip()


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise ScoringRuntimeError("SHA256_INVALID", f"{label}={value!r}")
    return value


def _safe_relative(value: object, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value or "\0" in value:
        raise ScoringRuntimeError("RELATIVE_PATH_INVALID", f"{label}={value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ScoringRuntimeError("RELATIVE_PATH_INVALID", f"{label}={value!r}")
    return path


def _resolve_within(root: Path, relative: object, label: str) -> Path:
    rel = _safe_relative(relative, label)
    candidate = root.joinpath(*rel.parts)
    try:
        resolved_parent = candidate.parent.resolve(strict=True)
        root_resolved = root.resolve(strict=True)
    except OSError as exc:
        raise ScoringRuntimeError("PATH_UNAVAILABLE", f"{label}: {exc}") from exc
    if resolved_parent != root_resolved and root_resolved not in resolved_parent.parents:
        raise ScoringRuntimeError("PATH_ESCAPE", f"{label}: {relative}")
    return candidate


def _safe_symlink_target(relative: PurePosixPath, target: str) -> str:
    if not target or "\\" in target or "\0" in target:
        raise ScoringRuntimeError("SYMLINK_TARGET_INVALID", target)
    target_path = PurePosixPath(target)
    if target_path.is_absolute():
        raise ScoringRuntimeError("SYMLINK_TARGET_INVALID", target)
    parts: list[str] = list(relative.parent.parts)
    for part in target_path.parts:
        if part in {"", "."}:
            continue
        if part == "..":
            if not parts:
                raise ScoringRuntimeError("SYMLINK_TARGET_ESCAPE", target)
            parts.pop()
        else:
            parts.append(part)
    return target


def _mode_string(path: Path) -> str:
    return f"{stat.S_IMODE(path.lstat().st_mode):04o}"


def _inventory_tree(root: Path) -> tuple[list[dict[str, Any]], str]:
    if not root.is_dir() or root.is_symlink():
        raise ScoringRuntimeError("WORKSPACE_INVALID", str(root))
    entries: list[dict[str, Any]] = []

    def walk(directory: Path, prefix: PurePosixPath | None = None) -> None:
        try:
            children = sorted(directory.iterdir(), key=lambda item: item.name)
        except OSError as exc:
            raise ScoringRuntimeError("WORKSPACE_READ_FAILED", str(exc)) from exc
        for child in children:
            relative = (
                PurePosixPath(child.name)
                if prefix is None
                else prefix / child.name
            )
            info = child.lstat()
            if stat.S_ISDIR(info.st_mode):
                entries.append({
                    "path": relative.as_posix(),
                    "type": "directory",
                    "sha256": None,
                    "size": 0,
                    "mode": f"{stat.S_IMODE(info.st_mode):04o}",
                })
                walk(child, relative)
            elif stat.S_ISREG(info.st_mode):
                entries.append({
                    "path": relative.as_posix(),
                    "type": "file",
                    "sha256": _sha256_file(child),
                    "size": info.st_size,
                    "mode": f"{stat.S_IMODE(info.st_mode):04o}",
                })
            elif stat.S_ISLNK(info.st_mode):
                target = os.readlink(child)
                _safe_symlink_target(relative, target)
                entries.append({
                    "path": relative.as_posix(),
                    "type": "symlink",
                    "sha256": _sha256_bytes(target.encode("utf-8")),
                    "size": len(target),
                    "mode": f"{stat.S_IMODE(info.st_mode):04o}",
                    "target": target,
                })
            else:
                raise ScoringRuntimeError(
                    "WORKSPACE_ENTRY_UNSUPPORTED", relative.as_posix()
                )

    walk(root)
    digest = hashlib.sha256()
    for entry in entries:
        if entry["type"] == "directory":
            continue
        digest.update(entry["path"].encode("utf-8"))
        digest.update(b"\0")
        digest.update(entry["type"].encode("ascii"))
        digest.update(b"\0")
        digest.update(entry["sha256"].encode("ascii"))
        digest.update(b"\n")
    return entries, digest.hexdigest()


def _compare_candidate_entries(
    actual: Sequence[Mapping[str, Any]],
    expected: object,
    *,
    compare_mode: bool = True,
) -> None:
    if not isinstance(expected, list):
        raise ScoringRuntimeError("CANDIDATE_ARTIFACT_INVALID", "entries")
    normalized: list[dict[str, Any]] = []
    for item in expected:
        if not isinstance(item, dict):
            raise ScoringRuntimeError("CANDIDATE_ARTIFACT_INVALID", "entry")
        normalized.append({
            "path": item.get("path"),
            "type": item.get("type"),
            "sha256": item.get("sha256"),
            "size": item.get("size"),
            **(
                {"mode": item.get("mode")}
                if compare_mode and os.name != "nt"
                else {}
            ),
        })
    observed = [
        {
            "path": item.get("path"),
            "type": item.get("type"),
            "sha256": item.get("sha256"),
            "size": item.get("size"),
            **(
                {"mode": item.get("mode")}
                if compare_mode and os.name != "nt"
                else {}
            ),
        }
        for item in actual
    ]
    if observed != normalized:
        raise ScoringRuntimeError("CANDIDATE_ENTRY_MISMATCH")


def _assert_read_only_tree(root: Path) -> None:
    for path in (root, *root.rglob("*")):
        if path.is_symlink():
            continue
        if stat.S_IMODE(path.stat().st_mode) & 0o222:
            raise ScoringRuntimeError(
                "CANDIDATE_ORIGINAL_WRITABLE",
                path.relative_to(root).as_posix() if path != root else ".",
            )


def _remove_tree(path: Path) -> None:
    def make_writable_and_retry(function: Any, target: str, _error: object) -> None:
        try:
            os.chmod(target, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
            function(target)
        except OSError:
            pass

    if path.exists():
        shutil.rmtree(path, onerror=make_writable_and_retry)


def _copy_inventory(
    source: Path,
    destination: Path,
    entries: Sequence[Mapping[str, Any]],
) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    directory_modes: list[tuple[Path, int]] = []
    for item in entries:
        relative = _safe_relative(item.get("path"), "candidate entry")
        target = destination.joinpath(*relative.parts)
        kind = item.get("type")
        if kind == "directory":
            target.mkdir(parents=True, exist_ok=False)
        elif kind == "file":
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source.joinpath(*relative.parts), target, follow_symlinks=False)
        elif kind == "symlink":
            target.parent.mkdir(parents=True, exist_ok=True)
            link_target = os.readlink(source.joinpath(*relative.parts))
            _safe_symlink_target(relative, link_target)
            os.symlink(link_target, target)
        else:
            raise ScoringRuntimeError("CANDIDATE_ENTRY_UNSUPPORTED", str(kind))
        mode_text = item.get("mode")
        if kind == "directory" and isinstance(mode_text, str):
            directory_modes.append((target, int(mode_text, 8)))
        elif kind != "symlink" and isinstance(mode_text, str):
            os.chmod(target, int(mode_text, 8))
    for target, mode in reversed(directory_modes):
        os.chmod(target, mode)


def _make_read_only(root: Path) -> None:
    paths = sorted(root.rglob("*"), key=lambda path: len(path.parts), reverse=True)
    for path in paths:
        if path.is_symlink():
            continue
        mode = stat.S_IMODE(path.stat().st_mode)
        os.chmod(path, mode & ~0o222)
    os.chmod(root, stat.S_IMODE(root.stat().st_mode) & ~0o222)


def _zip_kind(info: zipfile.ZipInfo) -> str:
    mode = info.external_attr >> 16
    if stat.S_ISLNK(mode):
        return "symlink"
    if info.is_dir() or stat.S_ISDIR(mode):
        return "directory"
    if mode == 0 or stat.S_ISREG(mode):
        return "file"
    return "unsupported"


def _read_scoring_package(
    path: Path,
) -> tuple[str, dict[str, tuple[zipfile.ZipInfo, bytes]], dict[str, Any]]:
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ScoringRuntimeError("SCORING_PACKAGE_INVALID", str(exc)) from exc
    with archive:
        members: dict[str, tuple[zipfile.ZipInfo, bytes]] = {}
        roots: set[str] = set()
        total_bytes = 0
        if len(archive.infolist()) > MAX_PACKAGE_MEMBERS:
            raise ScoringRuntimeError(
                "SCORING_PACKAGE_TOO_MANY_MEMBERS", str(len(archive.infolist()))
            )
        for info in archive.infolist():
            if "\\" in info.filename or "\0" in info.filename:
                raise ScoringRuntimeError("SCORING_PACKAGE_PATH_INVALID", info.filename)
            raw = PurePosixPath(info.filename)
            if raw.is_absolute() or any(part in {"", ".", ".."} for part in raw.parts):
                raise ScoringRuntimeError("SCORING_PACKAGE_PATH_INVALID", info.filename)
            roots.add(raw.parts[0])
            relative = PurePosixPath(*raw.parts[1:]).as_posix()
            if not relative:
                continue
            normalized = relative.rstrip("/")
            if normalized in members:
                raise ScoringRuntimeError("SCORING_PACKAGE_MEMBER_DUPLICATE", normalized)
            if info.file_size > MAX_PACKAGE_MEMBER_BYTES:
                raise ScoringRuntimeError("SCORING_PACKAGE_MEMBER_TOO_LARGE", normalized)
            kind = _zip_kind(info)
            if kind == "unsupported":
                raise ScoringRuntimeError(
                    "SCORING_PACKAGE_MEMBER_TYPE_UNSUPPORTED", normalized
                )
            total_bytes += info.file_size
            if total_bytes > MAX_PACKAGE_TOTAL_BYTES:
                raise ScoringRuntimeError(
                    "SCORING_PACKAGE_TOTAL_TOO_LARGE", str(total_bytes)
                )
            data = b"" if kind == "directory" else archive.read(info)
            members[normalized] = (info, data)
        if len(roots) != 1:
            raise ScoringRuntimeError("SCORING_PACKAGE_ROOT_INVALID", repr(sorted(roots)))
        root = next(iter(roots))
        manifest_name = ".general-e2e/scoring-package-manifest.json"
        try:
            manifest = json.loads(members[manifest_name][1].decode("utf-8"))
        except (KeyError, UnicodeError, json.JSONDecodeError) as exc:
            raise ScoringRuntimeError("SCORING_PACKAGE_MANIFEST_INVALID", str(exc)) from exc
        if not isinstance(manifest, dict) or manifest.get("schema_id") != PACKAGE_SCHEMA:
            raise ScoringRuntimeError("SCORING_PACKAGE_MANIFEST_INVALID", "schema")
        if manifest.get("manifest_kind") != "scoring":
            raise ScoringRuntimeError("SCORING_PACKAGE_MANIFEST_INVALID", "kind")
        if root != f"{manifest.get('batch_id')}__{manifest.get('unit_id')}":
            raise ScoringRuntimeError("SCORING_PACKAGE_IDENTITY_MISMATCH")
        return root, members, manifest


def _task_package_materials(
    members: Mapping[str, tuple[zipfile.ZipInfo, bytes]],
    manifest: Mapping[str, Any],
    task_id: str,
) -> tuple[dict[str, Any], bytes, bytes, list[tuple[dict[str, Any], bytes]]]:
    rows = [row for row in manifest.get("tasks", []) if row.get("task_id") == task_id]
    if len(rows) != 1:
        raise ScoringRuntimeError("SCORING_TASK_MISSING_OR_DUPLICATE", task_id)
    task = rows[0]
    expected_members: set[str] = set()

    def material(name: str) -> bytes:
        item = task.get(name)
        if not isinstance(item, dict):
            raise ScoringRuntimeError("SCORING_TASK_INVALID", name)
        relative = _safe_relative(item.get("path"), name).as_posix()
        expected_members.add(relative)
        try:
            info, data = members[relative]
        except KeyError as exc:
            raise ScoringRuntimeError("SCORING_MATERIAL_MISSING", relative) from exc
        if _zip_kind(info) != "file" or _sha256_bytes(data) != item.get("sha256"):
            raise ScoringRuntimeError("SCORING_MATERIAL_DIGEST_MISMATCH", relative)
        return data

    contract = material("contract")
    task_markdown = material("task")
    private = task.get("private_scoring")
    if not isinstance(private, dict) or not isinstance(private.get("entries"), list):
        raise ScoringRuntimeError("SCORING_PRIVATE_MATERIAL_INVALID")
    private_root = _safe_relative(private.get("path"), "private_scoring.path")
    gt_entries: list[tuple[dict[str, Any], bytes]] = []
    for item in private["entries"]:
        if not isinstance(item, dict):
            raise ScoringRuntimeError("SCORING_PRIVATE_MATERIAL_INVALID", "entry")
        relative = _safe_relative(item.get("path"), "private_scoring.entry")
        member_name = (private_root / relative).as_posix()
        expected_members.add(member_name)
        try:
            info, data = members[member_name]
        except KeyError as exc:
            raise ScoringRuntimeError("SCORING_GT_MEMBER_MISSING", member_name) from exc
        kind = item.get("kind")
        if kind not in {"file", "directory", "symlink"} or _zip_kind(info) != kind:
            raise ScoringRuntimeError("SCORING_GT_MEMBER_TYPE_MISMATCH", member_name)
        if kind == "file":
            if item.get("sha256") != _sha256_bytes(data) or item.get("size") != len(data):
                raise ScoringRuntimeError("SCORING_GT_MEMBER_DIGEST_MISMATCH", member_name)
        elif kind == "symlink":
            try:
                target = data.decode("utf-8", errors="surrogateescape")
            except UnicodeError as exc:
                raise ScoringRuntimeError("SCORING_GT_SYMLINK_INVALID", member_name) from exc
            _safe_symlink_target(relative, target)
            if (
                item.get("link_target") != target
                or item.get("sha256") != _sha256_bytes(data)
                or item.get("size") != len(data)
            ):
                raise ScoringRuntimeError(
                    "SCORING_GT_MEMBER_DIGEST_MISMATCH", member_name
                )
        gt_entries.append((dict(item), data))
    tree_input = {
        "algorithm": DATASET_TREE_HASH_ALGORITHM,
        "entries": [item for item, _ in gt_entries],
    }
    if _sha256_bytes(_canonical_json_bytes(tree_input)) != private.get("tree_sha256"):
        raise ScoringRuntimeError("SCORING_GT_TREE_MISMATCH", task_id)
    task_prefix = f"score/tasks/{task_id}/private-scoring/"
    unexpected = sorted(
        name for name in members if name.startswith(task_prefix) and name not in expected_members
    )
    if unexpected:
        raise ScoringRuntimeError("SCORING_TASK_MEMBER_UNEXPECTED", repr(unexpected))
    return dict(task), contract, task_markdown, gt_entries


def _write_gt(root: Path, entries: Sequence[tuple[Mapping[str, Any], bytes]]) -> None:
    root.mkdir(parents=True, exist_ok=False)
    for item, data in entries:
        relative = _safe_relative(item.get("path"), "gt entry")
        target = root.joinpath(*relative.parts)
        kind = item.get("kind")
        if kind == "directory":
            target.mkdir(parents=True, exist_ok=False)
        elif kind == "file":
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as handle:
                handle.write(data)
        elif kind == "symlink":
            target.parent.mkdir(parents=True, exist_ok=True)
            link_target = data.decode("utf-8", errors="surrogateescape")
            _safe_symlink_target(relative, link_target)
            os.symlink(link_target, target)
        else:
            raise ScoringRuntimeError("SCORING_GT_MEMBER_TYPE_MISMATCH", str(kind))
        mode_text = item.get("mode")
        if kind != "symlink" and isinstance(mode_text, str):
            os.chmod(target, int(mode_text, 8))


def _validate_transcript(path: Path) -> int:
    return len(_read_transcript(path))


def _read_transcript(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ScoringRuntimeError(
                    "TRANSCRIPT_INVALID", f"line {line_number}: {exc}"
                ) from exc
            if not isinstance(value, dict):
                raise ScoringRuntimeError("TRANSCRIPT_INVALID", f"line {line_number}")
            events.append(value)
    return events


def _load_runtime_lock(path: Path) -> tuple[dict[str, Any], str]:
    value = _read_json(path, code="RUNTIME_LOCK_INVALID")
    if value.get("schema_version") != RUNTIME_LOCK_SCHEMA:
        raise ScoringRuntimeError("RUNTIME_LOCK_INVALID", "schema")
    python = value.get("python")
    dependencies = value.get("dependencies")
    if not isinstance(python, dict) or not isinstance(dependencies, list):
        raise ScoringRuntimeError("RUNTIME_LOCK_INVALID", "shape")
    if not isinstance(python.get("major"), int) or not isinstance(python.get("minor"), int):
        raise ScoringRuntimeError("RUNTIME_LOCK_INVALID", "python")
    roots: set[str] = set()
    for item in dependencies:
        if not isinstance(item, dict):
            raise ScoringRuntimeError("RUNTIME_LOCK_INVALID", "dependency")
        if not isinstance(item.get("distribution"), str) or not isinstance(item.get("version"), str):
            raise ScoringRuntimeError("RUNTIME_LOCK_INVALID", "dependency identity")
        import_roots = item.get("import_roots")
        if not isinstance(import_roots, list) or not import_roots:
            raise ScoringRuntimeError("RUNTIME_LOCK_INVALID", "import_roots")
        for root in import_roots:
            if not isinstance(root, str) or root in roots:
                raise ScoringRuntimeError("RUNTIME_LOCK_INVALID", "duplicate import root")
            roots.add(root)
        runtime_assets = item.get("runtime_assets", [])
        if not isinstance(runtime_assets, list):
            raise ScoringRuntimeError("RUNTIME_LOCK_INVALID", "runtime_assets")
        for asset in runtime_assets:
            if (
                not isinstance(asset, dict)
                or not isinstance(asset.get("name"), str)
                or not isinstance(asset.get("revision"), str)
                or not isinstance(asset.get("version"), str)
            ):
                raise ScoringRuntimeError("RUNTIME_LOCK_INVALID", "runtime asset")
    requirements = value.get("requirements")
    if (
        not isinstance(requirements, dict)
        or requirements.get("path") != "scoring-runtime-requirements.txt"
        or not SHA256_RE.fullmatch(str(requirements.get("sha256") or ""))
    ):
        raise ScoringRuntimeError("RUNTIME_LOCK_INVALID", "requirements")
    return value, _sha256_file(path)


def prepare_attempt(
    *,
    unit_root: Path,
    execution_record_path: Path,
    scoring_package: Path,
    task_id: str,
    scoring_attempt_id: str,
    output_root: Path,
    runtime_lock_path: Path,
    judge_protocol: str | None = None,
    judge_model: str | None = None,
    judge_reasoning_effort: str | None = None,
    judge_attempt_id: str | None = None,
) -> dict[str, Any]:
    unit_root = unit_root.expanduser().resolve(strict=True)
    if not unit_root.is_dir() or unit_root.is_symlink():
        raise ScoringRuntimeError("UNIT_ROOT_INVALID", str(unit_root))
    task_id = _identifier(task_id, "task_id")
    scoring_attempt_id = _identifier(scoring_attempt_id, "scoring_attempt_id")
    execution_record_path = execution_record_path.expanduser().resolve(strict=True)
    if unit_root != execution_record_path and unit_root not in execution_record_path.parents:
        raise ScoringRuntimeError("EXECUTION_RECORD_OUTSIDE_UNIT", str(execution_record_path))
    execution = _read_json(execution_record_path, code="EXECUTION_RECORD_INVALID")
    identity = execution.get("identity")
    candidate = execution.get("candidate")
    dataset = execution.get("dataset")
    if not isinstance(identity, dict) or not isinstance(candidate, dict) or not isinstance(dataset, dict):
        raise ScoringRuntimeError("EXECUTION_RECORD_INVALID", "required objects")
    if identity.get("task_id") != task_id:
        raise ScoringRuntimeError("EXECUTION_TASK_MISMATCH")
    if (
        execution.get("phase") != "COMPLETED"
        or not isinstance(execution.get("execution"), dict)
        or execution["execution"].get("business_status") != "completed"
        or not isinstance(execution.get("evidence"), dict)
        or execution["evidence"].get("completeness") != "complete"
    ):
        raise ScoringRuntimeError("EXECUTION_NOT_SCORABLE")
    batch_id = _identifier(identity.get("batch_id"), "batch_id")
    unit_id = _identifier(identity.get("unit_id"), "unit_id")
    execution_attempt_id = _identifier(identity.get("attempt_id"), "execution_attempt_id")
    if candidate.get("drift_status") != "stable":
        raise ScoringRuntimeError("CANDIDATE_NOT_STABLE")
    candidate_sha = _sha256(candidate.get("frozen_sha256"), "candidate.frozen_sha256")
    candidate_path = _resolve_within(unit_root, candidate.get("path"), "candidate.path")
    if not candidate_path.is_dir() or candidate_path.is_symlink():
        raise ScoringRuntimeError("CANDIDATE_PATH_INVALID", str(candidate_path))
    artifact_path = candidate_path.parent / "candidate-artifact.json"
    artifact = _read_json(artifact_path, code="CANDIDATE_ARTIFACT_INVALID")
    if artifact.get("schema_version") != CANDIDATE_SCHEMA:
        raise ScoringRuntimeError("CANDIDATE_ARTIFACT_INVALID", "schema")
    if artifact.get("hash_algorithm") != TREE_HASH_ALGORITHM:
        raise ScoringRuntimeError("CANDIDATE_ARTIFACT_INVALID", "hash algorithm")
    if artifact.get("identity") != identity or artifact.get("expected_sha256") != candidate_sha:
        raise ScoringRuntimeError("CANDIDATE_IDENTITY_MISMATCH")
    entries, observed_candidate_sha = _inventory_tree(candidate_path)
    if observed_candidate_sha != candidate_sha:
        raise ScoringRuntimeError(
            "CANDIDATE_DIGEST_MISMATCH",
            f"expected={candidate_sha} actual={observed_candidate_sha}",
        )
    _compare_candidate_entries(entries, artifact.get("entries"))

    unit_manifest = _read_json(unit_root / "manifest.json", code="UNIT_MANIFEST_INVALID")
    if unit_manifest.get("batch_id") != batch_id or unit_manifest.get("unit_id") != unit_id:
        raise ScoringRuntimeError("UNIT_IDENTITY_MISMATCH")
    if task_id not in unit_manifest.get("task_ids", []):
        raise ScoringRuntimeError("UNIT_TASK_MISMATCH")

    _, package_members, scoring_manifest = _read_scoring_package(scoring_package)
    if scoring_manifest.get("batch_id") != batch_id or scoring_manifest.get("unit_id") != unit_id:
        raise ScoringRuntimeError("SCORING_PACKAGE_IDENTITY_MISMATCH")
    scoring_dataset = scoring_manifest.get("dataset")
    if not isinstance(scoring_dataset, dict):
        raise ScoringRuntimeError("SCORING_PACKAGE_MANIFEST_INVALID", "dataset")
    if (
        scoring_dataset.get("id") != dataset.get("id")
        or scoring_dataset.get("digest") != dataset.get("digest")
        or unit_manifest.get("dataset") != scoring_dataset
        or unit_manifest.get("release") != scoring_manifest.get("release")
    ):
        raise ScoringRuntimeError("SCORING_PACKAGE_LOCK_MISMATCH")
    scoring_task, contract_bytes, task_bytes, gt_entries = _task_package_materials(
        package_members, scoring_manifest, task_id
    )
    try:
        contract = json.loads(contract_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ScoringRuntimeError("SCORING_CONTRACT_INVALID", str(exc)) from exc
    if not isinstance(contract, dict) or contract.get("task_id") != task_id:
        raise ScoringRuntimeError("SCORING_CONTRACT_INVALID", "task_id")

    transcript_source: Path | None = None
    transcript_count = 0
    evidence = execution["evidence"]
    transcript_relative = evidence.get("transcript_path")
    if transcript_relative is not None:
        transcript_source = _resolve_within(unit_root, transcript_relative, "transcript_path")
        if not transcript_source.is_file() or transcript_source.is_symlink():
            raise ScoringRuntimeError("TRANSCRIPT_PATH_INVALID", str(transcript_source))
        transcript_count = _validate_transcript(transcript_source)

    runtime_lock, runtime_lock_sha = _load_runtime_lock(runtime_lock_path)
    judge_values = (
        judge_protocol,
        judge_model,
        judge_reasoning_effort,
        judge_attempt_id,
    )
    if any(value is not None for value in judge_values) and not all(
        value is not None for value in judge_values
    ):
        raise ScoringRuntimeError(
            "JUDGE_CONFIG_INCOMPLETE",
            "protocol, model, reasoning effort and attempt ID must be supplied together",
        )
    judge_config: dict[str, Any] | None = None
    if all(value is not None for value in judge_values):
        protocol = _required_string(judge_protocol, "judge_protocol")
        if protocol not in SEMANTIC_PROTOCOLS:
            raise ScoringRuntimeError("JUDGE_PROTOCOL_UNSUPPORTED", protocol)
        model = _required_string(judge_model, "judge_model")
        if model.lower().startswith("unconfigured"):
            raise ScoringRuntimeError("JUDGE_MODEL_UNCONFIGURED", model)
        reasoning_effort = _required_string(
            judge_reasoning_effort, "judge_reasoning_effort"
        )
        if reasoning_effort not in REASONING_EFFORTS:
            raise ScoringRuntimeError(
                "JUDGE_REASONING_EFFORT_UNSUPPORTED", reasoning_effort
            )
        judge_config = {
            "schema_version": JUDGE_CONFIG_SCHEMA,
            "protocol": protocol,
            "model": model,
            "reasoning_effort": reasoning_effort,
            "attempt_id": _identifier(judge_attempt_id, "judge_attempt_id"),
        }
    destination = (
        output_root.expanduser().resolve()
        / f"{batch_id}__{unit_id}"
        / task_id
        / scoring_attempt_id
    )
    if destination.exists():
        raise ScoringRuntimeError("SCORING_ATTEMPT_EXISTS", str(destination))
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.parent / f".{destination.name}.staging-{uuid.uuid4().hex}"
    staging.mkdir(parents=False, exist_ok=False)
    try:
        original_workspace = staging / "candidate-original/workspace"
        runtime_workspace = staging / "runtime/workspace"
        private_root = staging / "private"
        private_root.mkdir(parents=True)
        _copy_inventory(candidate_path, original_workspace, entries)
        copied_entries, copied_sha = _inventory_tree(original_workspace)
        if copied_sha != candidate_sha:
            raise ScoringRuntimeError("CANDIDATE_COPY_DIGEST_MISMATCH")
        _compare_candidate_entries(copied_entries, artifact.get("entries"))
        shutil.copyfile(artifact_path, staging / "candidate-original/candidate-artifact.json")
        _make_read_only(staging / "candidate-original")

        _copy_inventory(original_workspace, runtime_workspace, entries)
        if os.path.lexists(runtime_workspace / "gt"):
            raise ScoringRuntimeError("RUNTIME_GT_COLLISION")
        gt_private = private_root / "gt"
        _write_gt(gt_private, gt_entries)
        shutil.copytree(gt_private, runtime_workspace / "gt", symlinks=True)
        private_gt_entries, private_gt_sha = _inventory_tree(gt_private)
        _, runtime_initial_sha = _inventory_tree(runtime_workspace)
        (private_root / "contract.json").write_bytes(contract_bytes)
        (private_root / "task.md").write_bytes(task_bytes)
        shutil.copyfile(runtime_lock_path, private_root / "runtime-lock.json")
        judge_config_sha: str | None = None
        if judge_config is not None:
            _write_new_json(private_root / "judge-config.json", judge_config)
            judge_config_sha = _sha256_file(private_root / "judge-config.json")

        transcript_sha: str | None = None
        transcript_target: Path | None = None
        if transcript_source is not None:
            transcript_target = private_root / "transcript.jsonl"
            shutil.copyfile(transcript_source, transcript_target)
            transcript_sha = _sha256_file(transcript_target)

        shutil.copyfile(execution_record_path, private_root / "execution-record.json")
        manifest = {
            "schema_version": ATTEMPT_SCHEMA,
            "created_at": _now(),
            "identity": {
                "batch_id": batch_id,
                "unit_id": unit_id,
                "task_id": task_id,
                "execution_attempt_id": execution_attempt_id,
                "scoring_attempt_id": scoring_attempt_id,
            },
            "dataset": {
                "id": dataset.get("id"),
                "digest": dataset.get("digest"),
            },
            "grading": {
                "type": scoring_task.get("grading_type"),
                "weights": scoring_task.get("grading_weights"),
                "automated_checks_present": bool(
                    isinstance(contract.get("automated_checks"), str)
                    and contract.get("automated_checks", "").strip()
                ),
            },
            "source": {
                "execution_record_sha256": _sha256_file(execution_record_path),
                "candidate_sha256": candidate_sha,
                "scoring_package_sha256": _sha256_file(scoring_package),
            },
            "paths": {
                "candidate_original": "candidate-original/workspace",
                "candidate_artifact": "candidate-original/candidate-artifact.json",
                "runtime_workspace": "runtime/workspace",
                "contract": "private/contract.json",
                "task": "private/task.md",
                "gt": "private/gt",
                "transcript": "private/transcript.jsonl" if transcript_target else None,
                "runtime_lock": "private/runtime-lock.json",
                "execution_record": "private/execution-record.json",
                "judge_config": (
                    "private/judge-config.json" if judge_config is not None else None
                ),
            },
            "digests": {
                "candidate_original_sha256": candidate_sha,
                "candidate_artifact_sha256": _sha256_file(artifact_path),
                "contract_sha256": _sha256_bytes(contract_bytes),
                "task_sha256": _sha256_bytes(task_bytes),
                "private_scoring_tree_sha256": scoring_task["private_scoring"]["tree_sha256"],
                "private_gt_workspace_sha256": private_gt_sha,
                "runtime_initial_sha256": runtime_initial_sha,
                "transcript_sha256": transcript_sha,
                "runtime_lock_sha256": runtime_lock_sha,
                "execution_record_sha256": _sha256_file(execution_record_path),
                "judge_config_sha256": judge_config_sha,
            },
            "transcript_event_count": transcript_count,
            "private_scoring": {
                "entries": scoring_task["private_scoring"]["entries"],
                "workspace_entries": private_gt_entries,
            },
            "runtime": {
                "kind": "local-managed-python-worker",
                "logical_workspace_root": "/tmp_workspace",
                "workspace_argument": "runtime/workspace",
                "gt_injected_after_execution": True,
                "docker_required": False,
                "lock": runtime_lock,
            },
            "judge": (
                {
                    "protocol": judge_config["protocol"],
                    "model": judge_config["model"],
                    "reasoning_effort": judge_config["reasoning_effort"],
                    "attempt_id": judge_config["attempt_id"],
                }
                if judge_config is not None
                else None
            ),
        }
        _write_new_json(staging / "attempt-manifest.json", manifest)
        os.replace(staging, destination)
    except BaseException:
        _remove_tree(staging)
        raise
    return {
        "status": "PASS",
        "attempt_root": str(destination),
        "manifest": manifest,
    }


def verify_attempt(attempt_root: Path) -> dict[str, Any]:
    root = attempt_root.expanduser().resolve(strict=True)
    manifest = _read_json(root / "attempt-manifest.json", code="ATTEMPT_MANIFEST_INVALID")
    if manifest.get("schema_version") != ATTEMPT_SCHEMA:
        raise ScoringRuntimeError("ATTEMPT_MANIFEST_INVALID", "schema")
    paths = manifest.get("paths")
    digests = manifest.get("digests")
    if not isinstance(paths, dict) or not isinstance(digests, dict):
        raise ScoringRuntimeError("ATTEMPT_MANIFEST_INVALID", "shape")
    original = _resolve_within(root, paths.get("candidate_original"), "candidate_original")
    entries, candidate_sha = _inventory_tree(original)
    if candidate_sha != digests.get("candidate_original_sha256"):
        raise ScoringRuntimeError("CANDIDATE_ORIGINAL_DRIFT")
    artifact_path = _resolve_within(
        root, paths.get("candidate_artifact"), "candidate_artifact"
    )
    if (
        not artifact_path.is_file()
        or artifact_path.is_symlink()
        or _sha256_file(artifact_path) != digests.get("candidate_artifact_sha256")
    ):
        raise ScoringRuntimeError("CANDIDATE_ARTIFACT_DRIFT")
    artifact = _read_json(artifact_path, code="CANDIDATE_ARTIFACT_INVALID")
    if (
        artifact.get("schema_version") != CANDIDATE_SCHEMA
        or artifact.get("hash_algorithm") != TREE_HASH_ALGORITHM
        or artifact.get("expected_sha256") != candidate_sha
    ):
        raise ScoringRuntimeError("CANDIDATE_ARTIFACT_INVALID", "identity")
    _compare_candidate_entries(
        entries, artifact.get("entries"), compare_mode=False
    )
    _assert_read_only_tree(root / "candidate-original")
    for key, digest_key in (
        ("contract", "contract_sha256"),
        ("task", "task_sha256"),
        ("runtime_lock", "runtime_lock_sha256"),
        ("execution_record", "execution_record_sha256"),
    ):
        path = _resolve_within(root, paths.get(key), key)
        if not path.is_file() or path.is_symlink() or _sha256_file(path) != digests.get(digest_key):
            raise ScoringRuntimeError("ATTEMPT_PRIVATE_MATERIAL_DRIFT", key)
    judge_config_relative = paths.get("judge_config")
    if judge_config_relative is not None:
        judge_config_path = _resolve_within(
            root, judge_config_relative, "judge_config"
        )
        if (
            not judge_config_path.is_file()
            or judge_config_path.is_symlink()
            or _sha256_file(judge_config_path)
            != digests.get("judge_config_sha256")
        ):
            raise ScoringRuntimeError(
                "ATTEMPT_PRIVATE_MATERIAL_DRIFT", "judge_config"
            )
        judge_config = _read_json(
            judge_config_path, code="JUDGE_CONFIG_INVALID"
        )
        if (
            judge_config.get("schema_version") != JUDGE_CONFIG_SCHEMA
            or manifest.get("judge")
            != {
                "protocol": judge_config.get("protocol"),
                "model": judge_config.get("model"),
                "reasoning_effort": judge_config.get("reasoning_effort"),
                "attempt_id": judge_config.get("attempt_id"),
            }
        ):
            raise ScoringRuntimeError("JUDGE_CONFIG_INVALID", "manifest mismatch")
    elif manifest.get("judge") is not None or digests.get("judge_config_sha256") is not None:
        raise ScoringRuntimeError("JUDGE_CONFIG_INVALID", "incomplete manifest lock")
    transcript = paths.get("transcript")
    if transcript is not None:
        path = _resolve_within(root, transcript, "transcript")
        if _sha256_file(path) != digests.get("transcript_sha256"):
            raise ScoringRuntimeError("ATTEMPT_PRIVATE_MATERIAL_DRIFT", "transcript")
        if _validate_transcript(path) != manifest.get("transcript_event_count"):
            raise ScoringRuntimeError("TRANSCRIPT_EVENT_COUNT_MISMATCH")
    private_scoring = manifest.get("private_scoring")
    if not isinstance(private_scoring, dict):
        raise ScoringRuntimeError("ATTEMPT_MANIFEST_INVALID", "private_scoring")
    private_gt = _resolve_within(root, paths.get("gt"), "gt")
    private_gt_entries, private_gt_sha = _inventory_tree(private_gt)
    if private_gt_sha != digests.get("private_gt_workspace_sha256"):
        raise ScoringRuntimeError("ATTEMPT_PRIVATE_MATERIAL_DRIFT", "gt")
    _compare_candidate_entries(
        private_gt_entries,
        private_scoring.get("workspace_entries"),
        compare_mode=os.name != "nt",
    )
    runtime = _resolve_within(root, paths.get("runtime_workspace"), "runtime_workspace")
    if not runtime.is_dir() or runtime.is_symlink() or not (runtime / "gt").is_dir():
        raise ScoringRuntimeError("RUNTIME_WORKSPACE_INVALID")
    return {
        "status": "PASS",
        "attempt_root": str(root),
        "candidate_sha256": candidate_sha,
        "entry_count": len(entries),
    }


def _sanitized_environment(
    runtime_python: Path,
    *,
    playwright_browsers_path: Path | None = None,
) -> dict[str, str]:
    env: dict[str, str] = {
        "PATH": str(runtime_python.parent),
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUTF8": "1",
    }
    if os.name == "nt":
        for name in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP", "COMSPEC", "PATHEXT"):
            value = os.environ.get(name)
            if value:
                env[name] = value
    else:
        env["LC_ALL"] = os.environ.get("LC_ALL", "C.UTF-8")
        env["LANG"] = os.environ.get("LANG", "C.UTF-8")
        for name in ("TMPDIR", "TMP", "TEMP"):
            value = os.environ.get(name)
            if value:
                env[name] = value
    if playwright_browsers_path is not None:
        env["PLAYWRIGHT_BROWSERS_PATH"] = str(
            playwright_browsers_path.expanduser().resolve(strict=True)
        )
    return env


def _bootstrap_environment(
    runtime_python: Path | None = None,
    *,
    playwright_browsers_path: Path | None = None,
) -> dict[str, str]:
    executable = runtime_python or Path(sys.executable)
    env = _sanitized_environment(
        executable,
        playwright_browsers_path=playwright_browsers_path,
    )
    for name in (
        "HOME",
        "XDG_CACHE_HOME",
        "UV_CACHE_DIR",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "no_proxy",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "REQUESTS_CA_BUNDLE",
        "CURL_CA_BUNDLE",
        "NODE_EXTRA_CA_CERTS",
    ):
        value = os.environ.get(name)
        if value:
            env[name] = value
    return env


def _runtime_browser_path(
    runtime_python: Path, explicit: Path | None
) -> Path | None:
    if explicit is not None:
        path = explicit.expanduser().resolve(strict=True)
        if not path.is_dir() or path.is_symlink():
            raise ScoringRuntimeError("RUNTIME_BROWSER_PATH_INVALID", str(path))
        return path
    venv_root = runtime_python.parent.parent
    marker_path = venv_root / "general-e2e-runtime.json"
    if not marker_path.is_file() or marker_path.is_symlink():
        return None
    marker = _read_json(marker_path, code="RUNTIME_MARKER_INVALID")
    if marker.get("schema_version") != RUNTIME_MARKER_SCHEMA:
        raise ScoringRuntimeError("RUNTIME_MARKER_INVALID", "schema")
    relative = marker.get("playwright_browsers_path")
    if relative is None:
        return None
    path = _resolve_within(venv_root, relative, "playwright_browsers_path")
    if not path.is_dir() or path.is_symlink():
        raise ScoringRuntimeError("RUNTIME_BROWSER_PATH_INVALID", str(path))
    return path.resolve(strict=True)


def _runtime_probe_source() -> str:
    return r'''
import importlib.metadata as metadata
import importlib
import json
from pathlib import Path
import sys

request = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
dependencies = {}
imports = []
for item in request["dependencies"]:
    distribution = item["distribution"]
    dependencies[distribution] = metadata.version(distribution)
    for root in item["import_roots"]:
        importlib.import_module(root)
        imports.append(root)
browser = None
if request.get("browser_smoke"):
    import playwright
    browsers_file = Path(playwright.__file__).resolve().parent / "driver" / "package" / "browsers.json"
    browser_manifest = json.loads(browsers_file.read_text(encoding="utf-8"))
    chromium = next(item for item in browser_manifest["browsers"] if item["name"] == "chromium")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as manager:
        instance = manager.chromium.launch(headless=True)
        try:
            page = instance.new_page()
            page.goto("data:text/html,<title>general-e2e-runtime</title>")
            title = page.title()
            runtime_version = instance.version
        finally:
            instance.close()
    browser = {"name": "chromium", "revision": chromium["revision"], "version": chromium["browserVersion"], "runtime_version": runtime_version, "smoke_title": title}
print(json.dumps({
    "python": {"major": sys.version_info.major, "minor": sys.version_info.minor, "patch": sys.version_info.micro, "executable": sys.executable, "in_virtualenv": sys.prefix != sys.base_prefix},
    "dependencies": dependencies,
    "imports": sorted(imports),
    "browser": browser,
}, sort_keys=True))
'''.strip()


def probe_runtime(
    *,
    runtime_python: Path,
    runtime_lock_path: Path,
    required_import_roots: Sequence[str] | None = None,
    playwright_browsers_path: Path | None = None,
    browser_smoke: bool = True,
) -> dict[str, Any]:
    runtime_python = _absolute_executable(
        runtime_python, "RUNTIME_PYTHON_UNAVAILABLE"
    )
    lock, lock_sha = _load_runtime_lock(runtime_lock_path)
    required = None if required_import_roots is None else set(required_import_roots)
    dependencies = [
        item
        for item in lock["dependencies"]
        if required is None or required.intersection(item["import_roots"])
    ]
    browser_items = [
        asset
        for item in dependencies
        for asset in item.get("runtime_assets", [])
        if isinstance(asset, dict) and asset.get("name") == "chromium"
    ]
    if browser_items and browser_smoke and playwright_browsers_path is None:
        raise ScoringRuntimeError("RUNTIME_BROWSER_PATH_REQUIRED")
    request = {
        "dependencies": dependencies,
        "browser_smoke": bool(browser_items) and browser_smoke,
    }
    with tempfile.TemporaryDirectory(prefix="general-e2e-runtime-probe-") as temp_dir:
        request_path = Path(temp_dir) / "request.json"
        request_path.write_bytes(_pretty_json_bytes(request))
        try:
            completed = subprocess.run(
                [
                    str(runtime_python),
                    "-I",
                    "-c",
                    _runtime_probe_source(),
                    str(request_path),
                ],
                cwd=temp_dir,
                env=_sanitized_environment(
                    runtime_python,
                    playwright_browsers_path=playwright_browsers_path,
                ),
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
            )
        except subprocess.TimeoutExpired as exc:
            raise ScoringRuntimeError("RUNTIME_PROBE_TIMEOUT") from exc
    if completed.returncode != 0:
        raise ScoringRuntimeError(
            "RUNTIME_PROBE_FAILED", completed.stderr.strip() or completed.stdout.strip()
        )
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ScoringRuntimeError("RUNTIME_PROBE_INVALID", completed.stdout[:500]) from exc
    python = result.get("python", {})
    if (
        python.get("major") != lock["python"]["major"]
        or python.get("minor") != lock["python"]["minor"]
        or not python.get("in_virtualenv")
    ):
        raise ScoringRuntimeError("RUNTIME_PYTHON_MISMATCH", repr(python))
    observed_dependencies = result.get("dependencies", {})
    for item in dependencies:
        if observed_dependencies.get(item["distribution"]) != item["version"]:
            raise ScoringRuntimeError(
                "RUNTIME_DEPENDENCY_MISMATCH",
                f"{item['distribution']}={observed_dependencies.get(item['distribution'])!r}",
            )
    expected_imports = sorted(
        root for item in dependencies for root in item["import_roots"]
    )
    if result.get("imports") != expected_imports:
        raise ScoringRuntimeError(
            "RUNTIME_IMPORT_MISMATCH", repr(result.get("imports"))
        )
    if browser_items and browser_smoke:
        expected = browser_items[0]
        observed = result.get("browser")
        if not isinstance(observed, dict) or (
            str(observed.get("revision")) != str(expected.get("revision"))
            or observed.get("version") != expected.get("version")
            or observed.get("runtime_version") != expected.get("version")
            or observed.get("smoke_title") != "general-e2e-runtime"
        ):
            raise ScoringRuntimeError("RUNTIME_BROWSER_MISMATCH", repr(observed))
    return {
        "status": "PASS",
        "runtime_lock_sha256": lock_sha,
        "probe": result,
    }


def _terminate_process_tree(
    process: subprocess.Popen[Any], grace_seconds: float = 2.0
) -> dict[str, Any]:
    actions: list[str] = []
    if os.name == "nt":
        script = (
            "$root=[int]$args[0];"
            "$all=Get-CimInstance Win32_Process;"
            "$ids=@($root);"
            "do{$before=$ids.Count;$ids+=@($all|Where-Object{$ids -contains [int]$_.ParentProcessId}|ForEach-Object{[int]$_.ProcessId});$ids=@($ids|Sort-Object -Unique)}while($ids.Count -gt $before);"
            "$ids|Sort-Object -Descending|ForEach-Object{Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue}"
        )
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script, str(process.pid)],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        actions.append(f"powershell-stop-tree:{completed.returncode}")
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            actions.append("SIGTERM")
        except ProcessLookupError:
            return {"actions": actions, "remaining": False}
        except PermissionError:
            return {
                "actions": [*actions, "SIGTERM-permission-denied"],
                "remaining": True,
            }
        try:
            process.wait(timeout=grace_seconds)
        except subprocess.TimeoutExpired:
            pass
        deadline = time.monotonic() + grace_seconds
        while time.monotonic() < deadline:
            try:
                os.killpg(process.pid, 0)
            except ProcessLookupError:
                return {"actions": actions, "remaining": False}
            except PermissionError:
                return {
                    "actions": [*actions, "check-permission-denied"],
                    "remaining": True,
                }
            time.sleep(0.05)
        try:
            os.killpg(process.pid, signal.SIGKILL)
            actions.append("SIGKILL")
        except ProcessLookupError:
            return {"actions": actions, "remaining": False}
        except PermissionError:
            return {
                "actions": [*actions, "SIGKILL-permission-denied"],
                "remaining": True,
            }
        try:
            process.wait(timeout=grace_seconds)
        except subprocess.TimeoutExpired:
            pass
        deadline = time.monotonic() + grace_seconds
        while time.monotonic() < deadline:
            try:
                os.killpg(process.pid, 0)
            except ProcessLookupError:
                return {"actions": actions, "remaining": False}
            except PermissionError:
                return {
                    "actions": [*actions, "final-check-permission-denied"],
                    "remaining": True,
                }
            time.sleep(0.05)
        return {"actions": actions, "remaining": True}
    return {"actions": actions, "remaining": process.poll() is None}


class _WorkerExecutor:
    def __init__(
        self,
        *,
        attempt_root: Path,
        runtime_python: Path,
        runtime_lock_path: Path,
        timeout_seconds: float,
        playwright_browsers_path: Path | None,
    ) -> None:
        self.attempt_root = attempt_root
        self.runtime_python = runtime_python
        self.runtime_lock_path = runtime_lock_path
        self.timeout_seconds = timeout_seconds
        self.playwright_browsers_path = playwright_browsers_path
        self.audit: dict[str, Any] = {}

    def __call__(self, source: str, context: Mapping[str, Any]) -> Mapping[str, Any]:
        dependency_roots = [
            item["import_root"] for item in context["dependencies"].get("external", [])
        ]
        probe = probe_runtime(
            runtime_python=self.runtime_python,
            runtime_lock_path=self.runtime_lock_path,
            required_import_roots=dependency_roots,
            playwright_browsers_path=self.playwright_browsers_path,
        )
        work_root = self.attempt_root / "worker"
        work_root.mkdir(parents=False, exist_ok=False)
        request_path = work_root / "request.json"
        result_path = work_root / "result.json"
        stdout_path = work_root / "stdout.log"
        stderr_path = work_root / "stderr.log"
        request = {
            "schema_version": WORKER_REQUEST_SCHEMA,
            "automated_checks": source,
            "workspace_path": context["workspace_path"],
            "transcript": context["transcript"],
        }
        request_path.write_bytes(_pretty_json_bytes(request))
        worker_path = Path(__file__).with_name("rule_worker.py").resolve(strict=True)
        env = _sanitized_environment(
            self.runtime_python,
            playwright_browsers_path=self.playwright_browsers_path,
        )
        creationflags = 0
        popen_kwargs: dict[str, Any] = {"start_new_session": os.name != "nt"}
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            popen_kwargs = {"creationflags": creationflags}
        started = time.monotonic()
        timed_out = False
        log_too_large = False
        with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
            process = subprocess.Popen(
                [
                    str(self.runtime_python),
                    "-I",
                    str(worker_path),
                    "--request",
                    str(request_path),
                    "--result",
                    str(result_path),
                ],
                cwd=context["workspace_path"],
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                **popen_kwargs,
            )
            deadline = started + self.timeout_seconds
            return_code: int | None = None
            while return_code is None:
                return_code = process.poll()
                if return_code is not None:
                    break
                if time.monotonic() >= deadline:
                    timed_out = True
                    break
                if (
                    stdout_path.stat().st_size > MAX_WORKER_LOG_BYTES
                    or stderr_path.stat().st_size > MAX_WORKER_LOG_BYTES
                ):
                    log_too_large = True
                    break
                time.sleep(0.05)
            cleanup = _terminate_process_tree(process)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            if return_code is None:
                return_code = process.returncode
        duration = round(time.monotonic() - started, 6)
        self.audit = {
            "runtime_probe": probe,
            "worker_pid": process.pid,
            "return_code": return_code,
            "timed_out": timed_out,
            "log_too_large": log_too_large,
            "timeout_seconds": self.timeout_seconds,
            "duration_seconds": duration,
            "process_tree_cleanup": cleanup,
            "environment_keys": sorted(env),
            "request_sha256": _sha256_file(request_path),
            "stdout_sha256": _sha256_file(stdout_path),
            "stderr_sha256": _sha256_file(stderr_path),
        }
        if timed_out:
            raise ScoringRuntimeError("RULE_WORKER_TIMEOUT")
        if log_too_large:
            raise ScoringRuntimeError("RULE_WORKER_LOG_TOO_LARGE")
        if cleanup.get("remaining"):
            raise ScoringRuntimeError("RULE_WORKER_PROCESS_TREE_REMAINING")
        if not result_path.is_file():
            raise ScoringRuntimeError("RULE_WORKER_RESULT_MISSING", f"exit={return_code}")
        if result_path.stat().st_size > MAX_WORKER_RESULT_BYTES:
            raise ScoringRuntimeError("RULE_WORKER_RESULT_TOO_LARGE")
        result = _read_json(result_path, code="RULE_WORKER_RESULT_INVALID")
        if result.get("schema_version") != WORKER_RESULT_SCHEMA:
            raise ScoringRuntimeError("RULE_WORKER_RESULT_INVALID", "schema")
        if not result.get("ok"):
            error = result.get("error")
            detail = error.get("message") if isinstance(error, dict) else repr(error)
            raise ScoringRuntimeError("RULE_WORKER_FAILED", str(detail))
        raw = result.get("result")
        if not isinstance(raw, dict):
            raise ScoringRuntimeError("RULE_WORKER_RESULT_INVALID", "result")
        return raw


def _import_grading_core() -> tuple[Any, Any]:
    vendor_root = Path(__file__).resolve().parents[1] / "vendor/e2e-shared"
    if vendor_root.is_dir() and str(vendor_root) not in sys.path:
        sys.path.insert(0, str(vendor_root))
    try:
        from wildclawbench_grading_core import (  # type: ignore
            GradingCoreError,
            run_rules,
        )
    except ImportError as exc:
        raise ScoringRuntimeError(
            "GRADING_CORE_UNAVAILABLE",
            "install the packaged vendor/e2e-shared directory on PYTHONPATH",
        ) from exc
    return run_rules, GradingCoreError


def run_rules_attempt(
    *,
    attempt_root: Path,
    runtime_python: Path,
    timeout_seconds: float,
    playwright_browsers_path: Path | None = None,
) -> dict[str, Any]:
    attempt_root = attempt_root.expanduser().resolve(strict=True)
    verify_attempt(attempt_root)
    if timeout_seconds <= 0:
        raise ScoringRuntimeError("RULE_TIMEOUT_INVALID")
    manifest = _read_json(attempt_root / "attempt-manifest.json")
    contract_path = _resolve_within(attempt_root, manifest["paths"]["contract"], "contract")
    contract = _read_json(contract_path, code="SCORING_CONTRACT_INVALID")
    automated_checks = contract.get("automated_checks")
    if not isinstance(automated_checks, str):
        raise ScoringRuntimeError("SCORING_CONTRACT_INVALID", "automated_checks")
    runtime_workspace = _resolve_within(
        attempt_root, manifest["paths"]["runtime_workspace"], "runtime_workspace"
    ).resolve(strict=True)
    _, runtime_initial_sha = _inventory_tree(runtime_workspace)
    if runtime_initial_sha != manifest["digests"].get("runtime_initial_sha256"):
        raise ScoringRuntimeError("RUNTIME_WORKSPACE_DRIFT")
    runtime_lock_path = _resolve_within(
        attempt_root, manifest["paths"]["runtime_lock"], "runtime_lock"
    )
    runtime_python = _absolute_executable(
        runtime_python, "RUNTIME_PYTHON_UNAVAILABLE"
    )
    playwright_browsers_path = _runtime_browser_path(
        runtime_python, playwright_browsers_path
    )
    if (attempt_root / "rule-component.json").exists() or (attempt_root / "rule-audit.json").exists():
        raise ScoringRuntimeError("RULE_ATTEMPT_ALREADY_TERMINAL")
    executor = _WorkerExecutor(
        attempt_root=attempt_root,
        runtime_python=runtime_python,
        runtime_lock_path=runtime_lock_path,
        timeout_seconds=timeout_seconds,
        playwright_browsers_path=playwright_browsers_path,
    )
    run_rules, grading_error_type = _import_grading_core()
    transcript_relative = manifest["paths"].get("transcript")
    transcript = (
        _read_transcript(
            _resolve_within(attempt_root, transcript_relative, "transcript")
        )
        if transcript_relative is not None
        else []
    )
    if len(transcript) != manifest.get("transcript_event_count"):
        raise ScoringRuntimeError("TRANSCRIPT_EVENT_COUNT_MISMATCH")
    started_at = _now()
    try:
        component = run_rules(
            automated_checks,
            executor=executor if automated_checks.strip() else None,
            workspace_path=str(runtime_workspace),
            transcript=transcript,
            expected_keys=None,
        )
        status = "completed"
        error = None
    except BaseException as exc:
        status = "failed"
        if isinstance(exc, ScoringRuntimeError):
            error = {"code": exc.code, "detail": exc.detail}
        elif isinstance(exc, grading_error_type):
            cause = exc.__cause__
            if isinstance(cause, ScoringRuntimeError):
                error = {"code": cause.code, "detail": cause.detail}
            else:
                error = exc.as_dict()
        else:
            error = {"code": "RULE_EXECUTION_UNEXPECTED", "detail": str(exc)}
        component = None
    try:
        _, runtime_final_sha = _inventory_tree(runtime_workspace)
    except ScoringRuntimeError:
        runtime_final_sha = None
    audit = {
        "schema_version": AUDIT_SCHEMA,
        "identity": manifest["identity"],
        "started_at": started_at,
        "finished_at": _now(),
        "status": status,
        "runtime_kind": "local-managed-python-worker",
        "docker_used": False,
        "worker": executor.audit or None,
        "runtime_workspace": {
            "initial_sha256": runtime_initial_sha,
            "final_sha256": runtime_final_sha,
            "drifted": runtime_final_sha != runtime_initial_sha,
        },
        "error": error,
    }
    if component is not None:
        _write_new_json(attempt_root / "rule-component.json", component)
    _write_new_json(attempt_root / "rule-audit.json", audit)
    if error is not None:
        raise ScoringRuntimeError(error.get("code", "RULE_EXECUTION_FAILED"), str(error))
    return {
        "status": "PASS",
        "attempt_root": str(attempt_root),
        "rule_component": component,
        "audit": audit,
    }


def _import_semantic_grading_core() -> tuple[Any, Any, Any, Any]:
    vendor_root = Path(__file__).resolve().parents[1] / "vendor/e2e-shared"
    if vendor_root.is_dir() and str(vendor_root) not in sys.path:
        sys.path.insert(0, str(vendor_root))
    try:
        from wildclawbench_grading_core import (  # type: ignore
            GradingCoreError,
            build_evidence_index,
            evaluate_semantics,
            finalize_score,
        )
    except ImportError as exc:
        raise ScoringRuntimeError(
            "GRADING_CORE_UNAVAILABLE",
            "install the packaged vendor/e2e-shared directory on PYTHONPATH",
        ) from exc
    return build_evidence_index, evaluate_semantics, finalize_score, GradingCoreError


def _parse_semantic_criteria(rubric_text: object) -> list[dict[str, Any]]:
    if not isinstance(rubric_text, str) or not rubric_text.strip():
        return []
    criteria: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    body: list[str] = []
    for line in rubric_text.splitlines():
        heading = _RUBRIC_HEADING_RE.match(line.strip())
        metadata = (
            {
                key: value.strip()
                for key, value in _RUBRIC_METADATA_RE.findall(heading.group(2))
            }
            if heading
            else {}
        )
        key = metadata.get("key", "")
        try:
            weight = float(metadata.get("weight", ""))
        except ValueError:
            weight = None
        if heading and ID_RE.fullmatch(key) and weight is not None:
            if current is not None:
                current["rubric"] = "\n".join(body).strip()
                current["allowed_scores"] = sorted(
                    {
                        float(match.group(1))
                        for rubric_line in current["rubric"].splitlines()
                        if (match := _RUBRIC_SCORE_RE.match(rubric_line))
                    }
                )
                criteria.append(current)
            name = re.sub(
                r"^(?:Criterion\s+\d+\s*[:：]\s*)?", "", heading.group(1)
            ).strip()
            current = {
                "key": key,
                "name": name,
                "weight": weight,
                "rubric": "",
                "not_applicable_allowed": False,
            }
            body = [line]
        elif current is not None:
            body.append(line)
    if current is not None:
        current["rubric"] = "\n".join(body).strip()
        current["allowed_scores"] = sorted(
            {
                float(match.group(1))
                for rubric_line in current["rubric"].splitlines()
                if (match := _RUBRIC_SCORE_RE.match(rubric_line))
            }
        )
        criteria.append(current)
    keys = [item["key"] for item in criteria]
    if len(keys) != len(set(keys)):
        raise ScoringRuntimeError("SEMANTIC_RUBRIC_INVALID", "duplicate criterion key")
    if any(
        not item["allowed_scores"]
        or item["weight"] < 0
        or item["weight"] > 1
        for item in criteria
    ):
        raise ScoringRuntimeError(
            "SEMANTIC_RUBRIC_INVALID", "missing score anchors or invalid weight"
        )
    if criteria and abs(sum(item["weight"] for item in criteria) - 1.0) > 1e-6:
        raise ScoringRuntimeError(
            "SEMANTIC_RUBRIC_INVALID", "criterion weights must sum to 1.0"
        )
    return criteria


def _regular_evidence_files(root: Path) -> list[Path]:
    return sorted(
        (
            path
            for path in root.rglob("*")
            if path.is_file() and not path.is_symlink()
        ),
        key=lambda path: path.relative_to(root).as_posix(),
    )


def _semantic_paths(root: Path) -> dict[str, Path]:
    semantic = root / "semantic"
    return {
        "root": semantic,
        "catalog": semantic / "evidence-catalog.json",
        "request": semantic / "request.json",
        "template": semantic / "response-template.json",
        "query_log": semantic / "query-log.json",
        "response": semantic / "response.json",
        "component": semantic / "semantic-component.json",
        "audit": semantic / "semantic-audit.json",
    }


def _semantic_reference_inputs(
    attempt_root: Path,
    manifest: Mapping[str, Any],
    transcript: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    references: list[dict[str, Any]] = []
    event_locations: dict[str, dict[str, Any]] = {}

    def add_file(evidence_type: str, path: Path) -> None:
        references.append(
            {
                "type": evidence_type,
                "path": path.relative_to(attempt_root).as_posix(),
                "sha256": _sha256_file(path),
            }
        )

    add_file("task_definition", attempt_root / manifest["paths"]["task"])
    add_file("scoring_contract", attempt_root / manifest["paths"]["contract"])
    add_file(
        "execution_record", attempt_root / manifest["paths"]["execution_record"]
    )
    add_file(
        "candidate_manifest", attempt_root / manifest["paths"]["candidate_artifact"]
    )
    candidate = attempt_root / manifest["paths"]["candidate_original"]
    for path in _regular_evidence_files(candidate):
        add_file("candidate_file", path)
    private_gt = attempt_root / manifest["paths"]["gt"]
    for path in _regular_evidence_files(private_gt):
        add_file("private_reference", path)
    rule_component = attempt_root / "rule-component.json"
    if rule_component.is_file() and not rule_component.is_symlink():
        add_file("rule_result", rule_component)
    rule_audit = attempt_root / "rule-audit.json"
    if rule_audit.is_file() and not rule_audit.is_symlink():
        add_file("rule_audit", rule_audit)
    transcript_relative = manifest["paths"].get("transcript")
    if transcript_relative is not None:
        transcript_path = attempt_root / transcript_relative
        transcript_sha = _sha256_file(transcript_path)
        seen: set[str] = set()
        for line_number, event in enumerate(transcript, start=1):
            event_id = _required_string(event.get("event_id"), "transcript.event_id")
            if event_id in seen:
                raise ScoringRuntimeError("TRANSCRIPT_EVENT_ID_DUPLICATE", event_id)
            seen.add(event_id)
            references.append(
                {
                    "type": "transcript_event",
                    "path": transcript_relative,
                    "event_ids": [event_id],
                    "sha256": transcript_sha,
                }
            )
            event_locations[event_id] = {
                "line": line_number,
                "path": transcript_relative,
            }
    return references, event_locations


def _load_judge_config(root: Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    relative = manifest.get("paths", {}).get("judge_config")
    if relative is None:
        raise ScoringRuntimeError("JUDGE_CONFIG_REQUIRED")
    config = _read_json(
        _resolve_within(root, relative, "judge_config"), code="JUDGE_CONFIG_INVALID"
    )
    if config.get("schema_version") != JUDGE_CONFIG_SCHEMA:
        raise ScoringRuntimeError("JUDGE_CONFIG_INVALID", "schema")
    return config


def prepare_semantics_attempt(*, attempt_root: Path) -> dict[str, Any]:
    root = attempt_root.expanduser().resolve(strict=True)
    verify_attempt(root)
    paths = _semantic_paths(root)
    if paths["root"].exists():
        raise ScoringRuntimeError("SEMANTIC_PREPARATION_EXISTS", str(paths["root"]))
    manifest = _read_json(root / "attempt-manifest.json")
    contract = _read_json(
        root / manifest["paths"]["contract"], code="SCORING_CONTRACT_INVALID"
    )
    grading_type = manifest.get("grading", {}).get("type")
    if grading_type not in {"automated", "hybrid", "llm_judge"}:
        raise ScoringRuntimeError("GRADING_TYPE_INVALID", repr(grading_type))
    rich_criteria = (
        []
        if grading_type == "automated"
        else _parse_semantic_criteria(contract.get("llm_judge_rubric"))
    )
    if grading_type != "automated" and not rich_criteria:
        raise ScoringRuntimeError("SEMANTIC_RUBRIC_INVALID", "no criteria parsed")
    transcript_relative = manifest["paths"].get("transcript")
    transcript = (
        _read_transcript(root / transcript_relative)
        if transcript_relative is not None
        else []
    )
    references, event_locations = _semantic_reference_inputs(
        root, manifest, transcript
    )
    build_evidence_index, evaluate_semantics, _, grading_error_type = (
        _import_semantic_grading_core()
    )
    event_ids = list(event_locations)
    try:
        evidence_index = build_evidence_index(
            references,
            base_dir=root,
            known_event_ids=event_ids,
        )
    except grading_error_type as exc:
        raise ScoringRuntimeError(exc.code, exc.message) from exc
    evidence_by_event: dict[str, str] = {}
    for entry in evidence_index["entries"]:
        for event_id in entry["reference"].get("event_ids", []):
            evidence_by_event[event_id] = entry["id"]
    for event_id, location in event_locations.items():
        location["evidence_id"] = evidence_by_event[event_id]
    catalog = {
        "schema_version": SEMANTIC_CATALOG_SCHEMA,
        "identity": manifest["identity"],
        "created_at": _now(),
        "evidence_index": evidence_index,
        "transcript": {
            "path": transcript_relative,
            "event_count": len(transcript),
            "event_locations": event_locations,
        },
    }
    staging = root / f".semantic.staging-{uuid.uuid4().hex}"
    staging.mkdir(parents=False, exist_ok=False)
    try:
        _write_new_json(staging / "evidence-catalog.json", catalog)
        catalog_sha = _sha256_file(staging / "evidence-catalog.json")
        if grading_type == "automated":
            try:
                component = evaluate_semantics(
                    [],
                    evaluator=None,
                    evidence_index=evidence_index,
                    protocol="not-required",
                )
            except grading_error_type as exc:
                raise ScoringRuntimeError(exc.code, exc.message) from exc
            audit = {
                "schema_version": SEMANTIC_AUDIT_SCHEMA,
                "identity": manifest["identity"],
                "status": "completed",
                "protocol": "not-required",
                "model": None,
                "reasoning_effort": None,
                "evidence_catalog_sha256": catalog_sha,
                "request_sha256": None,
                "response_sha256": None,
                "query_log_sha256": None,
                "component_sha256": _sha256_bytes(_pretty_json_bytes(component)),
                "counterevidence_policy": "not-required",
                "docker_used": False,
                "error": None,
            }
            _write_new_json(staging / "semantic-component.json", component)
            _write_new_json(staging / "semantic-audit.json", audit)
        else:
            judge = _load_judge_config(root, manifest)
            if judge.get("protocol") != "codex-agent-judge-v1":
                raise ScoringRuntimeError(
                    "SEMANTIC_PROTOCOL_UNSUPPORTED",
                    f"G3-04 accepts codex-agent-judge-v1, got {judge.get('protocol')!r}",
                )
            rubric_text = _required_string(
                contract.get("llm_judge_rubric"), "llm_judge_rubric"
            )
            request = {
                "schema_version": SEMANTIC_REQUEST_SCHEMA,
                "prompt_protocol": SEMANTIC_PROMPT_PROTOCOL,
                "identity": manifest["identity"],
                "judge": {
                    "protocol": judge["protocol"],
                    "model": judge["model"],
                    "reasoning_effort": judge["reasoning_effort"],
                    "attempt_id": judge["attempt_id"],
                },
                "grading": manifest["grading"],
                "rubric": {
                    "text": rubric_text,
                    "sha256": _sha256_bytes(rubric_text.encode("utf-8")),
                    "criteria": rich_criteria,
                },
                "evidence": {
                    "catalog_path": "semantic/evidence-catalog.json",
                    "catalog_sha256": catalog_sha,
                    "index_digest": evidence_index["digest"],
                    "transcript_event_count": len(transcript),
                },
                "requirements": {
                    "score_each_declared_criterion": True,
                    "cite_only_frozen_evidence_ids": True,
                    "check_supporting_evidence": True,
                    "check_contradicting_evidence": True,
                    "absence_claim_requires_complete_transcript_coverage": True,
                    "unresolved_is_not_zero": True,
                },
            }
            _write_new_json(staging / "request.json", request)
            request_sha = _sha256_file(staging / "request.json")
            response_locks = {
                "request_sha256": request_sha,
                "evidence_catalog_sha256": catalog_sha,
                "evidence_index_digest": evidence_index["digest"],
                "rubric_sha256": request["rubric"]["sha256"],
            }
            template = {
                "schema_version": SEMANTIC_RESPONSE_SCHEMA,
                "identity": manifest["identity"],
                "judge": request["judge"],
                "locks": response_locks,
                "criteria": [
                    {
                        "key": criterion["key"],
                        "status": "unresolved",
                        "score": None,
                        "reason": "尚未完成证据核验。",
                        "evidence_ids": [],
                        "review": {
                            "query_ids": [],
                            "supporting_evidence_checked": False,
                            "contradicting_evidence_checked": False,
                            "absence_claim": False,
                            "complete_event_range_checked": False,
                        },
                    }
                    for criterion in rich_criteria
                ],
                "notes": "",
            }
            query_log = {
                "schema_version": SEMANTIC_QUERY_LOG_SCHEMA,
                "identity": manifest["identity"],
                "queries": [],
            }
            _write_new_json(staging / "response-template.json", template)
            _write_new_json(staging / "query-log.json", query_log)
        os.replace(staging, paths["root"])
    except BaseException:
        _remove_tree(staging)
        raise
    result = {
        "status": "PASS",
        "attempt_root": str(root),
        "grading_type": grading_type,
        "evidence_catalog": str(paths["catalog"]),
    }
    if grading_type == "automated":
        result["semantic_status"] = "not_required"
    else:
        result.update(
            {
                "semantic_status": "awaiting_response",
                "request": str(paths["request"]),
                "response_template": str(paths["template"]),
            }
        )
    return result


def _load_semantic_catalog(root: Path) -> dict[str, Any]:
    paths = _semantic_paths(root)
    catalog = _read_json(paths["catalog"], code="SEMANTIC_CATALOG_INVALID")
    if catalog.get("schema_version") != SEMANTIC_CATALOG_SCHEMA:
        raise ScoringRuntimeError("SEMANTIC_CATALOG_INVALID", "schema")
    return catalog


def _append_semantic_query(
    root: Path,
    *,
    mode: str,
    filters: Mapping[str, Any],
    offset: int,
    limit: int,
    total: int,
    returned_evidence_ids: Sequence[str],
    returned_event_ids: Sequence[str],
    coverage: Mapping[str, Any] | None,
    result: Mapping[str, Any],
) -> str:
    paths = _semantic_paths(root)
    if paths["audit"].exists():
        raise ScoringRuntimeError("SEMANTIC_ATTEMPT_ALREADY_TERMINAL")
    log = _read_json(paths["query_log"], code="SEMANTIC_QUERY_LOG_INVALID")
    if log.get("schema_version") != SEMANTIC_QUERY_LOG_SCHEMA or not isinstance(
        log.get("queries"), list
    ):
        raise ScoringRuntimeError("SEMANTIC_QUERY_LOG_INVALID", "shape")
    query_id = f"query-{len(log['queries']) + 1:04d}"
    log["queries"].append(
        {
            "query_id": query_id,
            "at": _now(),
            "mode": mode,
            "filters": dict(filters),
            "offset": offset,
            "limit": limit,
            "total_matches": total,
            "returned_count": len(result.get("items", [])),
            "returned_evidence_ids": list(dict.fromkeys(returned_evidence_ids)),
            "returned_event_ids": list(dict.fromkeys(returned_event_ids)),
            "coverage": dict(coverage) if coverage is not None else None,
            "result_sha256": _sha256_bytes(_canonical_json_bytes(result)),
        }
    )
    _atomic_write_json(paths["query_log"], log)
    return query_id


def query_evidence_attempt(
    *,
    attempt_root: Path,
    mode: str,
    offset: int = 0,
    limit: int = 50,
    evidence_id: str | None = None,
    evidence_type: str | None = None,
    event_id: str | None = None,
    call_id: str | None = None,
    path_contains: str | None = None,
    text: str | None = None,
    max_chars: int = 65536,
) -> dict[str, Any]:
    root = attempt_root.expanduser().resolve(strict=True)
    verify_attempt(root)
    if mode not in {"catalog", "transcript", "file"}:
        raise ScoringRuntimeError("SEMANTIC_QUERY_MODE_INVALID", mode)
    if offset < 0 or limit < 1 or limit > 1000:
        raise ScoringRuntimeError("SEMANTIC_QUERY_PAGE_INVALID")
    if max_chars < 1 or max_chars > MAX_EVIDENCE_TEXT_PAGE_CHARS:
        raise ScoringRuntimeError("SEMANTIC_QUERY_SIZE_INVALID")
    catalog = _load_semantic_catalog(root)
    index_entries = catalog.get("evidence_index", {}).get("entries")
    if not isinstance(index_entries, list):
        raise ScoringRuntimeError("SEMANTIC_CATALOG_INVALID", "entries")
    by_id = {entry.get("id"): entry for entry in index_entries}
    filters = {
        key: value
        for key, value in {
            "evidence_id": evidence_id,
            "evidence_type": evidence_type,
            "event_id": event_id,
            "call_id": call_id,
            "path_contains": path_contains,
            "text": text,
        }.items()
        if value is not None
    }
    allowed_filters = {
        "catalog": {"evidence_id", "evidence_type", "path_contains"},
        "transcript": {"event_id", "call_id", "path_contains", "text"},
        "file": {"evidence_id"},
    }[mode]
    unsupported_filters = sorted(set(filters) - allowed_filters)
    if unsupported_filters:
        raise ScoringRuntimeError(
            "SEMANTIC_QUERY_FILTER_INVALID",
            f"mode={mode} unsupported={unsupported_filters}",
        )
    returned_evidence_ids: list[str] = []
    returned_event_ids: list[str] = []
    coverage: dict[str, Any] | None = None
    if mode == "catalog":
        matches = []
        for entry in index_entries:
            reference = entry.get("reference", {})
            if evidence_id is not None and entry.get("id") != evidence_id:
                continue
            if evidence_type is not None and reference.get("type") != evidence_type:
                continue
            if path_contains is not None and path_contains not in str(reference.get("path", "")):
                continue
            matches.append(entry)
        items = matches[offset : offset + limit]
        returned_evidence_ids = [str(item["id"]) for item in items]
    elif mode == "transcript":
        manifest = _read_json(root / "attempt-manifest.json")
        relative = manifest.get("paths", {}).get("transcript")
        events = _read_transcript(root / relative) if relative is not None else []
        event_locations = catalog.get("transcript", {}).get("event_locations", {})
        matches = []
        for line_number, item in enumerate(events, start=1):
            item_event_id = item.get("event_id")
            serialized = json.dumps(item, ensure_ascii=False, sort_keys=True)
            item_call_id = (
                item.get("tool", {}).get("call_id")
                if isinstance(item.get("tool"), dict)
                else None
            )
            if event_id is not None and item_event_id != event_id:
                continue
            if call_id is not None and item_call_id != call_id:
                continue
            if path_contains is not None and path_contains not in serialized:
                continue
            if text is not None and text.casefold() not in serialized.casefold():
                continue
            location = event_locations.get(item_event_id, {})
            matches.append(
                {
                    "event": item,
                    "locator": {
                        "path": relative,
                        "line": line_number,
                        "event_id": item_event_id,
                        "evidence_id": location.get("evidence_id"),
                    },
                }
            )
        items = matches[offset : offset + limit]
        returned_event_ids = [str(item["locator"]["event_id"]) for item in items]
        returned_evidence_ids = [
            str(item["locator"]["evidence_id"])
            for item in items
            if item["locator"].get("evidence_id") is not None
        ]
        unfiltered = all(
            value is None for value in (event_id, call_id, path_contains, text)
        )
        coverage = {
            "kind": "transcript-range",
            "unfiltered": unfiltered,
            "start": offset,
            "end": offset + len(items),
            "total": len(events),
        }
    else:
        if evidence_id is None or evidence_id not in by_id:
            raise ScoringRuntimeError(
                "SEMANTIC_EVIDENCE_ID_UNKNOWN", repr(evidence_id)
            )
        reference = by_id[evidence_id].get("reference", {})
        relative = reference.get("path")
        if not isinstance(relative, str):
            raise ScoringRuntimeError("SEMANTIC_EVIDENCE_FILE_REQUIRED", evidence_id)
        path = _resolve_within(root, relative, "semantic evidence file")
        selected_lines: list[tuple[int, str, bool]] = []
        total_lines = 0
        emitted_chars = 0
        truncated_by_chars = False
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    total_lines = line_number
                    if (
                        line_number <= offset
                        or len(selected_lines) >= limit
                        or truncated_by_chars
                    ):
                        continue
                    normalized = line.rstrip("\n")
                    remaining = max_chars - emitted_chars
                    if len(normalized) > remaining:
                        truncated_by_chars = True
                        if not selected_lines and remaining > 0:
                            selected_lines.append(
                                (line_number, normalized[:remaining], True)
                            )
                        continue
                    selected_lines.append((line_number, normalized, False))
                    emitted_chars += len(normalized)
        except UnicodeDecodeError as exc:
            raise ScoringRuntimeError(
                "SEMANTIC_EVIDENCE_NOT_UTF8", relative
            ) from exc
        items = [
            {
                "line": line_number,
                "text": line,
                "text_truncated": text_truncated,
                "evidence_id": evidence_id,
                "path": relative,
            }
            for line_number, line, text_truncated in selected_lines
        ]
        returned_evidence_ids = [evidence_id] if items else []
        coverage = {
            "kind": "file-lines",
            "path": relative,
            "start_line": offset + 1,
            "end_line": selected_lines[-1][0] if selected_lines else offset,
            "total_lines": total_lines,
            "truncated_by_chars": truncated_by_chars,
        }
    total_matches = len(matches) if mode != "file" else total_lines
    result_payload = {
        "mode": mode,
        "offset": offset,
        "limit": limit,
        "total_matches": total_matches,
        "returned_count": len(items),
        "has_more": offset + len(items) < total_matches,
        "items": items,
    }
    query_id = _append_semantic_query(
        root,
        mode=mode,
        filters=filters,
        offset=offset,
        limit=limit,
        total=total_matches,
        returned_evidence_ids=returned_evidence_ids,
        returned_event_ids=returned_event_ids,
        coverage=coverage,
        result=result_payload,
    )
    return {
        "status": "PASS",
        "query_id": query_id,
        **result_payload,
    }


def _queries_cover_complete_transcript(
    queries: Sequence[Mapping[str, Any]], query_ids: Sequence[str], total: int
) -> bool:
    selected = {query.get("query_id"): query for query in queries}
    ranges: list[tuple[int, int]] = []
    for query_id in query_ids:
        coverage = selected.get(query_id, {}).get("coverage")
        if (
            isinstance(coverage, Mapping)
            and coverage.get("kind") == "transcript-range"
            and coverage.get("unfiltered") is True
            and coverage.get("total") == total
            and isinstance(coverage.get("start"), int)
            and isinstance(coverage.get("end"), int)
        ):
            ranges.append((coverage["start"], coverage["end"]))
    cursor = 0
    for start, end in sorted(ranges):
        if start > cursor:
            return False
        cursor = max(cursor, end)
    return cursor >= total


def record_semantics_attempt(
    *, attempt_root: Path, response_path: Path
) -> dict[str, Any]:
    root = attempt_root.expanduser().resolve(strict=True)
    verify_attempt(root)
    paths = _semantic_paths(root)
    if paths["audit"].exists() or paths["component"].exists() or paths["response"].exists():
        raise ScoringRuntimeError("SEMANTIC_ATTEMPT_ALREADY_TERMINAL")
    supplied_response_path = Path(
        os.path.abspath(response_path.expanduser())
    )
    if supplied_response_path.is_symlink() or not supplied_response_path.is_file():
        raise ScoringRuntimeError(
            "SEMANTIC_RESPONSE_PATH_INVALID", str(supplied_response_path)
        )
    response_path = supplied_response_path.resolve(strict=True)
    if (
        response_path == paths["response"]
        or response_path == root
        or root not in response_path.parents
    ):
        raise ScoringRuntimeError("SEMANTIC_RESPONSE_PATH_INVALID", str(response_path))
    raw_bytes = response_path.read_bytes()
    raw_sha = _sha256_bytes(raw_bytes)
    try:
        response = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        response = None
        parse_error: BaseException | None = ScoringRuntimeError(
            "SEMANTIC_RESPONSE_INVALID", str(exc)
        )
    else:
        parse_error = None
    manifest = _read_json(root / "attempt-manifest.json")
    request = _read_json(paths["request"], code="SEMANTIC_REQUEST_INVALID")
    catalog = _load_semantic_catalog(root)
    query_log = _read_json(paths["query_log"], code="SEMANTIC_QUERY_LOG_INVALID")
    query_log_sha = _sha256_file(paths["query_log"])
    build_evidence_index, evaluate_semantics, _, grading_error_type = (
        _import_semantic_grading_core()
    )
    del build_evidence_index
    error: dict[str, str] | None = None
    component: dict[str, Any] | None = None
    try:
        if parse_error is not None:
            raise parse_error
        if not isinstance(response, dict) or response.get("schema_version") != SEMANTIC_RESPONSE_SCHEMA:
            raise ScoringRuntimeError("SEMANTIC_RESPONSE_INVALID", "schema")
        expected_locks = {
            "request_sha256": _sha256_file(paths["request"]),
            "evidence_catalog_sha256": _sha256_file(paths["catalog"]),
            "evidence_index_digest": catalog["evidence_index"]["digest"],
            "rubric_sha256": request["rubric"]["sha256"],
        }
        if (
            response.get("identity") != manifest["identity"]
            or response.get("judge") != request["judge"]
            or response.get("locks") != expected_locks
        ):
            raise ScoringRuntimeError("SEMANTIC_RESPONSE_LOCK_MISMATCH")
        rows = response.get("criteria")
        if not isinstance(rows, list):
            raise ScoringRuntimeError("SEMANTIC_RESPONSE_INVALID", "criteria")
        expected_keys = [item["key"] for item in request["rubric"]["criteria"]]
        if [item.get("key") for item in rows if isinstance(item, dict)] != expected_keys:
            raise ScoringRuntimeError("SEMANTIC_RESPONSE_KEYS_MISMATCH")
        entries = catalog["evidence_index"]["entries"]
        evidence_by_id = {entry["id"]: entry["reference"] for entry in entries}
        queries = query_log.get("queries")
        if not isinstance(queries, list):
            raise ScoringRuntimeError("SEMANTIC_QUERY_LOG_INVALID", "queries")
        query_by_id = {query.get("query_id"): query for query in queries}
        backend_rows: list[dict[str, Any]] = []
        for row in rows:
            status = row.get("status")
            evidence_ids = row.get("evidence_ids")
            review = row.get("review")
            if (
                not isinstance(evidence_ids, list)
                or len(evidence_ids) != len(set(evidence_ids))
                or not isinstance(review, dict)
            ):
                raise ScoringRuntimeError("SEMANTIC_RESPONSE_INVALID", row.get("key", ""))
            unknown_evidence = [item for item in evidence_ids if item not in evidence_by_id]
            if unknown_evidence:
                raise ScoringRuntimeError(
                    "SEMANTIC_EVIDENCE_ID_UNKNOWN", repr(unknown_evidence)
                )
            query_ids = review.get("query_ids")
            if not isinstance(query_ids, list) or len(query_ids) != len(set(query_ids)):
                raise ScoringRuntimeError("SEMANTIC_REVIEW_INVALID", "query_ids")
            unknown_queries = [item for item in query_ids if item not in query_by_id]
            if unknown_queries:
                raise ScoringRuntimeError(
                    "SEMANTIC_QUERY_ID_UNKNOWN", repr(unknown_queries)
                )
            queried_evidence = {
                evidence
                for query_id in query_ids
                for evidence in query_by_id[query_id].get(
                    "returned_evidence_ids", []
                )
            }
            if not set(evidence_ids).issubset(queried_evidence):
                raise ScoringRuntimeError(
                    "SEMANTIC_CITATION_NOT_QUERIED", row["key"]
                )
            if status == "judged":
                if (
                    not query_ids
                    or review.get("supporting_evidence_checked") is not True
                    or review.get("contradicting_evidence_checked") is not True
                ):
                    raise ScoringRuntimeError(
                        "SEMANTIC_COUNTEREVIDENCE_CHECK_REQUIRED", row["key"]
                    )
                if review.get("absence_claim") is True:
                    total = catalog.get("transcript", {}).get("event_count", 0)
                    if (
                        review.get("complete_event_range_checked") is not True
                        or not _queries_cover_complete_transcript(
                            queries, query_ids, total
                        )
                    ):
                        raise ScoringRuntimeError(
                            "SEMANTIC_ABSENCE_COVERAGE_REQUIRED", row["key"]
                        )
            backend_rows.append(
                {
                    "key": row.get("key"),
                    "status": status,
                    "score": row.get("score"),
                    "reason": row.get("reason"),
                    "evidence": [evidence_by_id[item] for item in evidence_ids],
                }
            )

        core_criteria = [
            {
                "key": item["key"],
                "weight": item["weight"],
                "allowed_scores": item["allowed_scores"],
                "not_applicable_allowed": item["not_applicable_allowed"],
            }
            for item in request["rubric"]["criteria"]
        ]

        def evaluator(_criteria: object, _evidence: object) -> dict[str, Any]:
            return {
                "criteria": backend_rows,
                "notes": response.get("notes", ""),
            }

        component = evaluate_semantics(
            core_criteria,
            evaluator=evaluator,
            evidence_index=catalog["evidence_index"],
            protocol=request["judge"]["protocol"],
        )
    except BaseException as exc:
        if isinstance(exc, ScoringRuntimeError):
            error = {"code": exc.code, "message": exc.detail or exc.code}
        elif isinstance(exc, grading_error_type):
            error = {"code": exc.code, "message": exc.message}
        else:
            error = {
                "code": "SEMANTIC_RECORD_UNEXPECTED",
                "message": str(exc) or type(exc).__name__,
            }
    audit = {
        "schema_version": SEMANTIC_AUDIT_SCHEMA,
        "identity": manifest["identity"],
        "status": "completed" if error is None else "failed",
        "protocol": request["judge"]["protocol"],
        "model": request["judge"]["model"],
        "reasoning_effort": request["judge"]["reasoning_effort"],
        "evidence_catalog_sha256": _sha256_file(paths["catalog"]),
        "request_sha256": _sha256_file(paths["request"]),
        "response_sha256": raw_sha,
        "query_log_sha256": query_log_sha,
        "component_sha256": (
            _sha256_bytes(_pretty_json_bytes(component)) if component is not None else None
        ),
        "counterevidence_policy": "per-criterion-declaration-and-query-proof/v1",
        "docker_used": False,
        "error": error,
    }
    terminal_files = {
        paths["response"]: raw_bytes,
        paths["audit"]: _pretty_json_bytes(audit),
    }
    if component is not None:
        terminal_files[paths["component"]] = _pretty_json_bytes(component)
    _publish_new_files(terminal_files)
    if error is not None:
        raise ScoringRuntimeError(error["code"], error["message"])
    return {
        "status": "PASS",
        "attempt_root": str(root),
        "semantic_component": component,
        "audit": audit,
    }


def _evaluation_error_component(error: Mapping[str, Any]) -> dict[str, Any]:
    code = str(error.get("code") or "COMPONENT_FAILED")
    message = str(error.get("message") or error.get("detail") or code)
    return {
        "status": "evaluation_error",
        "score": None,
        "criteria": [],
        "error": {"code": code, "message": message},
    }


def _load_rule_component_for_final(
    root: Path, grading_type: str
) -> dict[str, Any]:
    if grading_type == "llm_judge":
        return {
            "status": "not_required",
            "score": None,
            "criteria": [],
            "error": None,
        }
    component_path = root / "rule-component.json"
    if component_path.is_file():
        return _read_json(component_path, code="RULE_COMPONENT_INVALID")
    audit_path = root / "rule-audit.json"
    if audit_path.is_file():
        audit = _read_json(audit_path, code="RULE_AUDIT_INVALID")
        if audit.get("status") == "failed" and isinstance(audit.get("error"), dict):
            return _evaluation_error_component(audit["error"])
    raise ScoringRuntimeError("RULE_COMPONENT_MISSING")


def _load_semantic_component_for_final(
    root: Path, grading_type: str
) -> dict[str, Any]:
    paths = _semantic_paths(root)
    if grading_type == "automated":
        if not paths["component"].is_file():
            raise ScoringRuntimeError("SEMANTIC_COMPONENT_MISSING")
        return _read_json(paths["component"], code="SEMANTIC_COMPONENT_INVALID")
    if paths["component"].is_file():
        return _read_json(paths["component"], code="SEMANTIC_COMPONENT_INVALID")
    if paths["audit"].is_file():
        audit = _read_json(paths["audit"], code="SEMANTIC_AUDIT_INVALID")
        if audit.get("status") == "failed" and isinstance(audit.get("error"), dict):
            return _evaluation_error_component(audit["error"])
    raise ScoringRuntimeError("SEMANTIC_COMPONENT_MISSING")


def _score_evidence_reference(path: Path, root: Path, evidence_type: str) -> dict[str, Any]:
    return {
        "type": evidence_type,
        "path": path.relative_to(root).as_posix(),
        "sha256": _sha256_file(path),
    }


def _standard_score_criteria(
    root: Path,
    *,
    grading_type: str,
    final: Mapping[str, Any],
    rules: Mapping[str, Any],
    semantics: Mapping[str, Any],
) -> list[dict[str, Any]]:
    criteria: list[dict[str, Any]] = []
    weights = final["weights"]
    if grading_type in {"automated", "hybrid"}:
        if (root / "rule-component.json").is_file():
            rule_evidence = _score_evidence_reference(
                root / "rule-component.json", root, "rule_result"
            )
        else:
            rule_evidence = _score_evidence_reference(
                root / "rule-audit.json", root, "rule_audit"
            )
        rule_status = "judged" if rules.get("status") == "completed" else "unresolved"
        criteria.append(
            {
                "key": "automated_component",
                "weight": weights["automated"],
                "status": rule_status,
                "score": rules.get("score") if rule_status == "judged" else None,
                "reason": (
                    "冻结自动规则组件已通过受管 Worker 执行和契约校验。"
                    if rule_status == "judged"
                    else str((rules.get("error") or {}).get("message") or "自动规则未形成有效组件。")
                ),
                "evidence": [rule_evidence],
            }
        )
    if grading_type in {"hybrid", "llm_judge"}:
        semantic_rows = semantics.get("criteria")
        if not semantic_rows:
            request = _read_json(
                _semantic_paths(root)["request"], code="SEMANTIC_REQUEST_INVALID"
            )
            audit_ref = _score_evidence_reference(
                _semantic_paths(root)["audit"], root, "semantic_audit"
            )
            semantic_rows = [
                {
                    "key": item["key"],
                    "weight": item["weight"],
                    "status": "unresolved",
                    "score": None,
                    "reason": str(
                        (semantics.get("error") or {}).get("message")
                        or "语义评分未形成有效组件。"
                    ),
                    "evidence": [audit_ref],
                }
                for item in request["rubric"]["criteria"]
            ]
        for row in semantic_rows:
            criteria.append(
                {
                    "key": row["key"],
                    "weight": row["weight"] * weights["llm_judge"],
                    "status": row["status"],
                    "score": row.get("score"),
                    "reason": row["reason"],
                    "evidence": row.get("evidence", []),
                }
            )
    return criteria


def _validate_standard_score_document(score: Mapping[str, Any]) -> None:
    if score.get("schema_id") != SCORE_SCHEMA_ID or score.get("schema_version") != 1:
        raise ScoringRuntimeError("SCORE_DOCUMENT_INVALID", "schema")
    evaluation = score.get("evaluation")
    result = score.get("result")
    if not isinstance(evaluation, Mapping) or not isinstance(result, Mapping):
        raise ScoringRuntimeError("SCORE_DOCUMENT_INVALID", "shape")
    criteria = evaluation.get("criteria")
    if not isinstance(criteria, list) or not criteria:
        raise ScoringRuntimeError("SCORE_DOCUMENT_INVALID", "criteria")
    keys = [row.get("key") for row in criteria if isinstance(row, Mapping)]
    if len(keys) != len(criteria) or len(keys) != len(set(keys)):
        raise ScoringRuntimeError("SCORE_DOCUMENT_INVALID", "criterion keys")
    try:
        weights = [float(row.get("weight", -1)) for row in criteria]
    except (TypeError, ValueError) as exc:
        raise ScoringRuntimeError("SCORE_DOCUMENT_INVALID", "criterion weights") from exc
    if (
        any(not math.isfinite(weight) or weight < 0 for weight in weights)
        or abs(sum(weights) - 1.0) > 1e-6
    ):
        raise ScoringRuntimeError("SCORE_DOCUMENT_INVALID", "criterion weights")
    valid = result.get("valid")
    if not isinstance(valid, bool):
        raise ScoringRuntimeError("SCORE_DOCUMENT_INVALID", "result validity")
    if valid:
        try:
            total_score = float(result.get("total_score"))
        except (TypeError, ValueError) as exc:
            raise ScoringRuntimeError("SCORE_DOCUMENT_INVALID", "valid result") from exc
        if (
            not math.isfinite(total_score)
            or not 0 <= total_score <= 1
            or evaluation.get("status") != "completed"
        ):
            raise ScoringRuntimeError("SCORE_DOCUMENT_INVALID", "valid result")
    elif result.get("total_score") is not None:
        raise ScoringRuntimeError("SCORE_DOCUMENT_INVALID", "invalid result must use null")


def _score_source_digests(root: Path) -> dict[str, str | None]:
    semantic_paths = _semantic_paths(root)

    def digest_if_file(path: Path) -> str | None:
        return _sha256_file(path) if path.is_file() and not path.is_symlink() else None

    return {
        "attempt_manifest_sha256": _sha256_file(root / "attempt-manifest.json"),
        "rule_component_sha256": digest_if_file(root / "rule-component.json"),
        "rule_audit_sha256": digest_if_file(root / "rule-audit.json"),
        "semantic_component_sha256": digest_if_file(semantic_paths["component"]),
        "semantic_audit_sha256": digest_if_file(semantic_paths["audit"]),
    }


def _verify_semantic_terminal(
    root: Path, manifest: Mapping[str, Any]
) -> dict[str, Any]:
    paths = _semantic_paths(root)
    audit = _read_json(paths["audit"], code="SEMANTIC_AUDIT_INVALID")
    if (
        audit.get("schema_version") != SEMANTIC_AUDIT_SCHEMA
        or audit.get("identity") != manifest.get("identity")
        or audit.get("docker_used") is not False
        or audit.get("evidence_catalog_sha256") != _sha256_file(paths["catalog"])
    ):
        raise ScoringRuntimeError("SEMANTIC_AUDIT_INVALID", "identity or source")
    grading_type = manifest.get("grading", {}).get("type")
    if grading_type == "automated":
        expected_judge = ("not-required", None, None)
        if any(
            audit.get(key) is not None
            for key in ("request_sha256", "response_sha256", "query_log_sha256")
        ):
            raise ScoringRuntimeError("SEMANTIC_AUDIT_INVALID", "automated source")
    else:
        judge = _load_judge_config(root, manifest)
        expected_judge = (
            judge["protocol"],
            judge["model"],
            judge["reasoning_effort"],
        )
        for key, path_key in (
            ("request_sha256", "request"),
            ("response_sha256", "response"),
            ("query_log_sha256", "query_log"),
        ):
            if audit.get(key) != _sha256_file(paths[path_key]):
                raise ScoringRuntimeError("SEMANTIC_AUDIT_INVALID", key)
    if (
        (
            audit.get("protocol"),
            audit.get("model"),
            audit.get("reasoning_effort"),
        )
        != expected_judge
    ):
        raise ScoringRuntimeError("SEMANTIC_AUDIT_INVALID", "judge")
    component_sha = (
        _sha256_file(paths["component"])
        if paths["component"].is_file() and not paths["component"].is_symlink()
        else None
    )
    if audit.get("component_sha256") != component_sha:
        raise ScoringRuntimeError("SEMANTIC_AUDIT_INVALID", "component")
    status = audit.get("status")
    if (
        status == "completed"
        and (component_sha is None or audit.get("error") is not None)
    ) or (
        status == "failed"
        and (component_sha is not None or not isinstance(audit.get("error"), dict))
    ) or status not in {"completed", "failed"}:
        raise ScoringRuntimeError("SEMANTIC_AUDIT_INVALID", "terminal status")
    return audit


def _build_standard_score(
    root: Path,
    manifest: Mapping[str, Any],
    *,
    finalize_score: Any,
) -> dict[str, Any]:
    grading_type = manifest["grading"]["type"]
    rules = _load_rule_component_for_final(root, grading_type)
    semantics = _load_semantic_component_for_final(root, grading_type)
    final = finalize_score(
        grading_type=grading_type,
        grading_weights=manifest["grading"].get("weights"),
        rules=rules,
        semantics=semantics,
    )
    criteria = _standard_score_criteria(
        root,
        grading_type=grading_type,
        final=final,
        rules=rules,
        semantics=semantics,
    )
    execution = _read_json(
        root / manifest["paths"]["execution_record"],
        code="EXECUTION_RECORD_INVALID",
    )
    semantic_error = semantics.get("error") if isinstance(semantics, Mapping) else None
    rule_error = rules.get("error") if isinstance(rules, Mapping) else None
    final_error = semantic_error or rule_error
    if not final["result"]["valid"] and not isinstance(final_error, Mapping):
        final_error = {
            "code": "FINAL_SCORE_INVALID",
            "message": final["result"]["invalid_reason"] or "score is invalid",
        }
    if grading_type == "automated":
        judge = {
            "protocol": "not-required",
            "model": None,
            "reasoning_effort": None,
            "attempt_id": "judge-not-required",
        }
    else:
        judge_config = _load_judge_config(root, manifest)
        judge = {
            "protocol": judge_config["protocol"],
            "model": judge_config["model"],
            "reasoning_effort": judge_config["reasoning_effort"],
            "attempt_id": judge_config["attempt_id"],
        }
    score = {
        "schema_id": SCORE_SCHEMA_ID,
        "schema_version": 1,
        "identity": {
            "batch_id": manifest["identity"]["batch_id"],
            "unit_id": manifest["identity"]["unit_id"],
            "task_id": manifest["identity"]["task_id"],
            "attempt_id": manifest["identity"]["scoring_attempt_id"],
        },
        "dataset": manifest["dataset"],
        "execution": {
            "record_path": manifest["paths"]["execution_record"],
            "record_sha256": manifest["digests"]["execution_record_sha256"],
            "attempt_id": manifest["identity"]["execution_attempt_id"],
            "business_status": execution["execution"]["business_status"],
        },
        "judge": judge,
        "components": final["components"],
        "evaluation": {
            "status": final["evaluation"]["status"],
            "criteria": criteria,
            "error": dict(final_error) if isinstance(final_error, Mapping) else None,
        },
        "result": final["result"],
    }
    _validate_standard_score_document(score)
    return score


def finalize_score_attempt(*, attempt_root: Path) -> dict[str, Any]:
    root = attempt_root.expanduser().resolve(strict=True)
    verify_attempt(root)
    score_path = root / "score.json"
    audit_path = root / "score-audit.json"
    if score_path.exists() or audit_path.exists():
        raise ScoringRuntimeError("SCORE_ATTEMPT_ALREADY_TERMINAL")
    manifest = _read_json(root / "attempt-manifest.json")
    grading_type = manifest["grading"]["type"]
    _, _, finalize_score, grading_error_type = _import_semantic_grading_core()
    try:
        _verify_semantic_terminal(root, manifest)
        score = _build_standard_score(
            root, manifest, finalize_score=finalize_score
        )
        score_bytes = _pretty_json_bytes(score)
        audit = {
            "schema_version": SCORE_AUDIT_SCHEMA,
            "identity": manifest["identity"],
            "created_at": _now(),
            "status": "completed",
            "grading_type": grading_type,
            "source": _score_source_digests(root),
            "score_schema_validation": "passed",
            "score_sha256": _sha256_bytes(score_bytes),
            "docker_used": False,
            "error": None,
        }
        _publish_new_files(
            {
                score_path: score_bytes,
                audit_path: _pretty_json_bytes(audit),
            }
        )
    except BaseException as exc:
        if isinstance(exc, ScoringRuntimeError):
            error = {"code": exc.code, "message": exc.detail or exc.code}
        elif isinstance(exc, grading_error_type):
            error = {"code": exc.code, "message": exc.message}
        else:
            error = {"code": "SCORE_FINALIZE_UNEXPECTED", "message": str(exc)}
        failure_audit = {
            "schema_version": SCORE_AUDIT_SCHEMA,
            "identity": manifest["identity"],
            "created_at": _now(),
            "status": "failed",
            "grading_type": grading_type,
            "source": {},
            "score_schema_validation": "not_available",
            "score_sha256": None,
            "docker_used": False,
            "error": error,
        }
        if not audit_path.exists():
            _write_new_json(audit_path, failure_audit)
        raise ScoringRuntimeError(error["code"], error["message"])
    return {
        "status": "PASS",
        "attempt_root": str(root),
        "score": score,
        "audit": audit,
    }


def verify_score_attempt(attempt_root: Path) -> dict[str, Any]:
    root = attempt_root.expanduser().resolve(strict=True)
    verify_attempt(root)
    score = _read_json(root / "score.json", code="SCORE_DOCUMENT_INVALID")
    audit = _read_json(root / "score-audit.json", code="SCORE_AUDIT_INVALID")
    _validate_standard_score_document(score)
    manifest = _read_json(
        root / "attempt-manifest.json", code="ATTEMPT_MANIFEST_INVALID"
    )
    if (
        audit.get("schema_version") != SCORE_AUDIT_SCHEMA
        or audit.get("status") != "completed"
        or audit.get("identity") != manifest.get("identity")
        or audit.get("grading_type") != manifest.get("grading", {}).get("type")
        or audit.get("score_schema_validation") != "passed"
        or audit.get("error") is not None
        or audit.get("score_sha256") != _sha256_file(root / "score.json")
        or audit.get("docker_used") is not False
    ):
        raise ScoringRuntimeError("SCORE_AUDIT_INVALID", "terminal lock mismatch")
    expected_source = _score_source_digests(root)
    if audit.get("source") != expected_source:
        raise ScoringRuntimeError("SCORE_SOURCE_DRIFT", "source digest mismatch")
    semantic_audit = _verify_semantic_terminal(root, manifest)
    if semantic_audit.get("query_log_sha256") is not None and semantic_audit.get(
        "query_log_sha256"
    ) != _sha256_file(_semantic_paths(root)["query_log"]):
        raise ScoringRuntimeError("SCORE_SOURCE_DRIFT", "semantic query log")
    _, _, finalize_score, grading_error_type = _import_semantic_grading_core()
    try:
        expected_score = _build_standard_score(
            root, manifest, finalize_score=finalize_score
        )
    except grading_error_type as exc:
        raise ScoringRuntimeError(exc.code, exc.message) from exc
    if score != expected_score:
        raise ScoringRuntimeError("SCORE_RECOMPUTE_MISMATCH")
    return {
        "status": "PASS",
        "attempt_root": str(root),
        "score_valid": score["result"]["valid"],
        "score_sha256": audit["score_sha256"],
    }


def _default_lock_path() -> Path:
    return Path(__file__).resolve().parents[1] / "references/scoring-runtime-lock.json"


def _default_requirements_path() -> Path:
    return Path(__file__).resolve().parents[1] / "references/scoring-runtime-requirements.txt"


def bootstrap_runtime(
    *,
    venv_root: Path,
    uv_command: str,
    offline: bool,
    install_browser: bool,
) -> dict[str, Any]:
    lock_path = _default_lock_path()
    lock, lock_sha = _load_runtime_lock(lock_path)
    requirements = _default_requirements_path()
    if (
        not requirements.is_file()
        or _sha256_file(requirements) != lock["requirements"]["sha256"]
    ):
        raise ScoringRuntimeError("RUNTIME_REQUIREMENTS_DIGEST_MISMATCH")
    uv_executable = shutil.which(uv_command)
    if uv_executable is None:
        raise ScoringRuntimeError("RUNTIME_UV_UNAVAILABLE", uv_command)
    destination = venv_root.expanduser().resolve()
    if destination.exists():
        raise ScoringRuntimeError("RUNTIME_ENV_EXISTS", str(destination))
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.parent / f".{destination.name}.staging-{uuid.uuid4().hex}"
    try:
        command = [
            uv_executable,
            "venv",
            "--python",
            f"{lock['python']['major']}.{lock['python']['minor']}",
            str(staging),
        ]
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            env=_bootstrap_environment(),
        )
        if completed.returncode != 0:
            raise ScoringRuntimeError("RUNTIME_BOOTSTRAP_FAILED", completed.stderr.strip())
        python = staging / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        install = [
            uv_executable,
            "pip",
            "install",
            "--python",
            str(python),
            "-r",
            str(requirements),
        ]
        if offline:
            install.append("--offline")
        completed = subprocess.run(
            install,
            check=False,
            capture_output=True,
            text=True,
            env=_bootstrap_environment(python),
        )
        if completed.returncode != 0:
            raise ScoringRuntimeError("RUNTIME_BOOTSTRAP_FAILED", completed.stderr.strip())
        browser_root = staging / "playwright-browsers"
        if install_browser:
            browser_root.mkdir()
            completed = subprocess.run(
                [str(python), "-m", "playwright", "install", "chromium"],
                check=False,
                capture_output=True,
                text=True,
                env=_bootstrap_environment(
                    python, playwright_browsers_path=browser_root
                ),
            )
            if completed.returncode != 0:
                raise ScoringRuntimeError("RUNTIME_BROWSER_INSTALL_FAILED", completed.stderr.strip())
        probe = probe_runtime(
            runtime_python=python,
            runtime_lock_path=lock_path,
            required_import_roots=[
                root
                for item in lock["dependencies"]
                for root in item["import_roots"]
            ],
            playwright_browsers_path=browser_root if install_browser else None,
            browser_smoke=install_browser,
        )
        marker_probe = json.loads(json.dumps(probe["probe"]))
        marker_probe["python"]["executable"] = (
            "Scripts/python.exe" if os.name == "nt" else "bin/python"
        )
        marker = {
            "schema_version": RUNTIME_MARKER_SCHEMA,
            "created_at": _now(),
            "runtime_lock_sha256": lock_sha,
            "playwright_browsers_path": (
                "playwright-browsers" if install_browser else None
            ),
            "probe": marker_probe,
        }
        _write_new_json(staging / "general-e2e-runtime.json", marker)
        os.replace(staging, destination)
    except BaseException:
        _remove_tree(staging)
        raise
    return {
        "status": "PASS",
        "venv_root": str(destination),
        "runtime_lock_sha256": lock_sha,
    }


def _print_result(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prepare and run Docker-free General E2E rule scoring."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--unit-root", required=True, type=Path)
    prepare.add_argument("--execution-record", required=True, type=Path)
    prepare.add_argument("--scoring-package", required=True, type=Path)
    prepare.add_argument("--task-id", required=True)
    prepare.add_argument("--scoring-attempt-id", required=True)
    prepare.add_argument("--output-root", required=True, type=Path)
    prepare.add_argument("--runtime-lock", type=Path, default=_default_lock_path())
    prepare.add_argument("--judge-protocol")
    prepare.add_argument("--judge-model")
    prepare.add_argument("--judge-reasoning-effort")
    prepare.add_argument("--judge-attempt-id")

    verify = subparsers.add_parser("verify")
    verify.add_argument("--attempt-root", required=True, type=Path)

    run = subparsers.add_parser("run-rules")
    run.add_argument("--attempt-root", required=True, type=Path)
    run.add_argument("--runtime-python", required=True, type=Path)
    run.add_argument("--timeout-seconds", type=float, default=120.0)
    run.add_argument("--playwright-browsers-path", type=Path)

    prepare_semantics = subparsers.add_parser("prepare-semantics")
    prepare_semantics.add_argument("--attempt-root", required=True, type=Path)

    query_evidence = subparsers.add_parser("query-evidence")
    query_evidence.add_argument("--attempt-root", required=True, type=Path)
    query_evidence.add_argument(
        "--mode", required=True, choices=("catalog", "transcript", "file")
    )
    query_evidence.add_argument("--offset", type=int, default=0)
    query_evidence.add_argument("--limit", type=int, default=50)
    query_evidence.add_argument("--evidence-id")
    query_evidence.add_argument("--evidence-type")
    query_evidence.add_argument("--event-id")
    query_evidence.add_argument("--call-id")
    query_evidence.add_argument("--path-contains")
    query_evidence.add_argument("--text")
    query_evidence.add_argument("--max-chars", type=int, default=65536)

    record_semantics = subparsers.add_parser("record-semantics")
    record_semantics.add_argument("--attempt-root", required=True, type=Path)
    record_semantics.add_argument("--response", required=True, type=Path)

    finalize = subparsers.add_parser("finalize")
    finalize.add_argument("--attempt-root", required=True, type=Path)

    verify_score = subparsers.add_parser("verify-score")
    verify_score.add_argument("--attempt-root", required=True, type=Path)

    probe = subparsers.add_parser("probe-runtime")
    probe.add_argument("--runtime-python", required=True, type=Path)
    probe.add_argument("--runtime-lock", type=Path, default=_default_lock_path())
    probe.add_argument("--import-root", action="append", default=[])
    probe.add_argument("--playwright-browsers-path", type=Path)

    bootstrap = subparsers.add_parser("bootstrap-runtime")
    bootstrap.add_argument("--venv-root", required=True, type=Path)
    bootstrap.add_argument("--uv-command", default="uv")
    bootstrap.add_argument("--offline", action="store_true")
    bootstrap.add_argument("--skip-browser", action="store_true")

    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare_attempt(
                unit_root=args.unit_root,
                execution_record_path=args.execution_record,
                scoring_package=args.scoring_package,
                task_id=args.task_id,
                scoring_attempt_id=args.scoring_attempt_id,
                output_root=args.output_root,
                runtime_lock_path=args.runtime_lock,
                judge_protocol=args.judge_protocol,
                judge_model=args.judge_model,
                judge_reasoning_effort=args.judge_reasoning_effort,
                judge_attempt_id=args.judge_attempt_id,
            )
        elif args.command == "verify":
            result = verify_attempt(args.attempt_root)
        elif args.command == "run-rules":
            result = run_rules_attempt(
                attempt_root=args.attempt_root,
                runtime_python=args.runtime_python,
                timeout_seconds=args.timeout_seconds,
                playwright_browsers_path=args.playwright_browsers_path,
            )
        elif args.command == "prepare-semantics":
            result = prepare_semantics_attempt(attempt_root=args.attempt_root)
        elif args.command == "query-evidence":
            result = query_evidence_attempt(
                attempt_root=args.attempt_root,
                mode=args.mode,
                offset=args.offset,
                limit=args.limit,
                evidence_id=args.evidence_id,
                evidence_type=args.evidence_type,
                event_id=args.event_id,
                call_id=args.call_id,
                path_contains=args.path_contains,
                text=args.text,
                max_chars=args.max_chars,
            )
        elif args.command == "record-semantics":
            result = record_semantics_attempt(
                attempt_root=args.attempt_root,
                response_path=args.response,
            )
        elif args.command == "finalize":
            result = finalize_score_attempt(attempt_root=args.attempt_root)
        elif args.command == "verify-score":
            result = verify_score_attempt(args.attempt_root)
        elif args.command == "probe-runtime":
            result = probe_runtime(
                runtime_python=args.runtime_python,
                runtime_lock_path=args.runtime_lock,
                required_import_roots=args.import_root,
                playwright_browsers_path=args.playwright_browsers_path,
            )
        else:
            result = bootstrap_runtime(
                venv_root=args.venv_root,
                uv_command=args.uv_command,
                offline=args.offline,
                install_browser=not args.skip_browser,
            )
        _print_result(result)
        return 0
    except ScoringRuntimeError as exc:
        print(
            json.dumps(
                {"status": "FAIL", "error": {"code": exc.code, "detail": exc.detail}},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
