"""Materialize verified bundle workspaces without reading mutable source trees."""
from __future__ import annotations

import errno
import hashlib
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
from typing import Any, Mapping, Sequence

from eval_general_e2e.shared.dataset_bundle.verify import (
    _validate_bounded_symlink, safe_relative_path, sha256_file,
)


class FrozenWorkspaceError(ValueError):
    """A frozen workspace cannot be safely created or reused."""


def _component(value: Any, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value):
        raise FrozenWorkspaceError(f"FROZEN_WORKSPACE_INVALID_{label}")
    return value


def frozen_workspace_path(manifest: Mapping[str, Any], cache_root: Path, task_id: str | None = None) -> Path:
    """Return cache_root/dataset_id/digest[/task_id] without creating it."""
    dataset_id = _component(manifest.get("dataset_id"), "DATASET_ID")
    digest = manifest.get("dataset_digest")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise FrozenWorkspaceError("FROZEN_WORKSPACE_INVALID_DIGEST")
    target = Path(cache_root).absolute() / dataset_id / digest
    return target / _component(task_id, "TASK_ID") if task_id is not None else target


def _expected_workspaces(manifest: Mapping[str, Any], members: Sequence[Any]):
    indexed = {}
    for member in members:
        name = member.path.rstrip("/")
        if name in indexed:
            raise FrozenWorkspaceError("FROZEN_WORKSPACE_DUPLICATE_BUNDLE_MEMBER")
        indexed[name] = member
    expected: dict[str, dict[str, Any]] = {"": {"kind": "directory", "mode": 0o755}}
    payloads = {}

    def add(path: str, row: dict[str, Any]) -> None:
        if path in expected and expected[path] != row:
            raise FrozenWorkspaceError("FROZEN_WORKSPACE_PATH_COLLISION: " + path)
        expected[path] = row
        parent = Path(path).parent
        while parent != Path("."):
            key = parent.as_posix()
            directory = {"kind": "directory", "mode": 0o755}
            if key in expected and expected[key] != directory:
                raise FrozenWorkspaceError("FROZEN_WORKSPACE_PATH_COLLISION: " + key)
            expected[key] = directory
            parent = parent.parent

    seen = set()
    for task in manifest["tasks"]:
        task_id = _component(task["task_id"], "TASK_ID")
        if task_id in seen:
            raise FrozenWorkspaceError("FROZEN_WORKSPACE_DUPLICATE_TASK")
        seen.add(task_id)
        for key, tree_name, bundle_tree in (("execution", "exec", "execution/exec"),
                                           ("private_scoring", "gt", "private-scoring/gt")):
            base = f"{task_id}/{tree_name}"
            add(base, {"kind": "directory", "mode": 0o755})
            tree = task["materials"][key]
            source_root = f"tasks/{task_id}/{bundle_tree}"
            if tree["root"] != source_root:
                raise FrozenWorkspaceError("FROZEN_WORKSPACE_MATERIAL_ROOT_MISMATCH")
            for entry in tree["entries"]:
                relative = safe_relative_path(entry["path"], label="workspace material").as_posix()
                target = f"{base}/{relative}"
                kind = entry["kind"]
                mode = int(entry["mode"], 8)
                if kind not in {"file", "directory", "symlink"} or mode not in {0o644, 0o755, 0o777}:
                    raise FrozenWorkspaceError("FROZEN_WORKSPACE_UNSUPPORTED_MATERIAL")
                member = indexed.get(f"{source_root}/{relative}")
                if member is None or member.kind != kind or member.mode != mode:
                    raise FrozenWorkspaceError("FROZEN_WORKSPACE_BUNDLE_MEMBER_MISMATCH: " + target)
                row = {"kind": kind, "mode": mode}
                if kind in {"file", "symlink"}:
                    if len(member.data) != entry["size"] or hashlib.sha256(member.data).hexdigest() != entry["sha256"]:
                        raise FrozenWorkspaceError("FROZEN_WORKSPACE_BUNDLE_BYTES_MISMATCH: " + target)
                    row.update(size=entry["size"], sha256=entry["sha256"])
                    payloads[target] = member.data
                if kind == "symlink":
                    link_target = member.data.decode("utf-8")
                    _validate_bounded_symlink(relative, link_target)
                    if link_target != entry["link_target"]:
                        raise FrozenWorkspaceError("FROZEN_WORKSPACE_LINK_TARGET_MISMATCH: " + target)
                    row.update(link_target=link_target, tree_root=base)
                add(target, row)
    if not seen:
        raise FrozenWorkspaceError("FROZEN_WORKSPACE_NO_TASKS")
    return expected, payloads


def _verify_workspace(root: Path, expected: Mapping[str, Mapping[str, Any]]) -> None:
    seen = set()

    def visit(path: Path, relative: str) -> None:
        row = expected.get(relative)
        if row is None:
            raise FrozenWorkspaceError("FROZEN_WORKSPACE_EXTRA_PATH: " + relative)
        info = path.lstat()
        actual_kind = ("symlink" if stat.S_ISLNK(info.st_mode) else "directory" if stat.S_ISDIR(info.st_mode)
                       else "file" if stat.S_ISREG(info.st_mode) else "unsupported")
        if actual_kind != row["kind"]:
            raise FrozenWorkspaceError("FROZEN_WORKSPACE_KIND_DRIFT: " + relative)
        if actual_kind != "symlink" and stat.S_IMODE(info.st_mode) != row["mode"]:
            raise FrozenWorkspaceError("FROZEN_WORKSPACE_MODE_DRIFT: " + relative)
        seen.add(relative)
        if actual_kind == "directory":
            for child in sorted(path.iterdir(), key=lambda item: item.name):
                visit(child, f"{relative}/{child.name}" if relative else child.name)
        elif actual_kind == "symlink":
            target = os.readlink(path)
            if target != row["link_target"] or hashlib.sha256(target.encode("utf-8")).hexdigest() != row["sha256"]:
                raise FrozenWorkspaceError("FROZEN_WORKSPACE_LINK_DRIFT: " + relative)
            try:
                resolved = path.resolve()
            except (OSError, RuntimeError) as exc:
                raise FrozenWorkspaceError("FROZEN_WORKSPACE_LINK_INVALID: " + relative) from exc
            if not resolved.is_relative_to(root.resolve() / row["tree_root"]):
                raise FrozenWorkspaceError("FROZEN_WORKSPACE_LINK_ESCAPE: " + relative)
        elif info.st_nlink != 1 or info.st_size != row["size"] or sha256_file(path) != row["sha256"]:
            raise FrozenWorkspaceError("FROZEN_WORKSPACE_BYTES_DRIFT: " + relative)

    try:
        visit(root, "")
    except OSError as exc:
        raise FrozenWorkspaceError("FROZEN_WORKSPACE_UNREADABLE") from exc
    if seen != set(expected):
        raise FrozenWorkspaceError("FROZEN_WORKSPACE_MISSING_PATH")


def materialize_verified_workspaces(manifest: Mapping[str, Any], members: Sequence[Any], cache_root: Path) -> Path:
    """Publish task_id/{exec,gt} atomically and verify every byte before reuse.

    The caller must first compare the compiled manifest with its frozen lock.
    Only explicitly locked, bounded symlinks are supported; unexpected links,
    extra paths and cache drift fail closed instead of falling back to sources.
    """
    target = frozen_workspace_path(manifest, cache_root)
    expected, payloads = _expected_workspaces(manifest, members)
    cache_root = Path(cache_root).absolute()
    for directory in (cache_root, target.parent):
        if directory.is_symlink():
            raise FrozenWorkspaceError("FROZEN_WORKSPACE_CACHE_LINK")
        directory.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        _verify_workspace(target, expected)
        return target
    temporary = Path(tempfile.mkdtemp(prefix=f".{target.name}.", dir=target.parent))
    try:
        temporary.chmod(0o755)
        for relative, row in sorted(expected.items(), key=lambda item: (item[0].count("/"), item[0])):
            if not relative:
                continue
            path = temporary / relative
            if row["kind"] == "directory":
                path.mkdir(exist_ok=True)
                path.chmod(row["mode"])
            elif row["kind"] == "symlink":
                path.symlink_to(row["link_target"])
            else:
                with path.open("xb") as stream:
                    stream.write(payloads[relative])
                path.chmod(row["mode"])
        _verify_workspace(temporary, expected)
        try:
            os.rename(temporary, target)
        except OSError as exc:
            if exc.errno not in {errno.EEXIST, errno.ENOTEMPTY}:
                raise
            _verify_workspace(target, expected)
        return target
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
