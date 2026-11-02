"""Read explicitly archived dataset sources without changing historical locks.

Only paths in the SHA-bound index are overridden/excluded. Unregistered files
and current datasets retain ordinary source-drift detection.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath


def _relative(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or "\\" in value or any(p in {".", ".."} for p in path.parts):
        raise ValueError("FROZEN_SOURCE_PATH_INVALID")
    return path


class FrozenSources:
    def __init__(self, repo: Path, index: str | None = None):
        self.repo = repo.resolve()
        self.overrides: dict[str, bytes] = {}
        self.excluded: tuple[PurePosixPath, ...] = ()
        if index is None:
            return
        target = self.repo / _relative(index)
        doc = json.loads(target.read_text(encoding="utf-8"))
        if doc.get("schema_version") != "general-e2e-frozen-source-index/v1":
            raise ValueError("FROZEN_SOURCE_INDEX_INVALID")
        for relative, row in doc["files"].items():
            _relative(relative)
            snapshot = target.parent / _relative(row["snapshot"])
            if snapshot.is_symlink() or not snapshot.resolve().is_relative_to(target.parent.resolve()):
                raise ValueError("FROZEN_SOURCE_SNAPSHOT_ESCAPE")
            data = snapshot.read_bytes()
            if hashlib.sha256(data).hexdigest() != row["sha256"]:
                raise ValueError("FROZEN_SOURCE_SNAPSHOT_DRIFT: " + relative)
            self.overrides[relative] = data
        self.excluded = tuple(_relative(p) for p in doc.get("excluded_paths", []))

    def read_bytes(self, path: Path) -> bytes:
        relative = path.resolve().relative_to(self.repo).as_posix()
        return self.overrides[relative] if relative in self.overrides else path.read_bytes()

    def excludes(self, path: Path) -> bool:
        relative = PurePosixPath(path.absolute().relative_to(self.repo).as_posix())
        return any(relative == excluded or excluded in relative.parents for excluded in self.excluded)


def frozen_task_path(path: Path) -> Path:
    """Explicit v1 fixture path for tests of historical correction profiles."""
    repo = Path(__file__).resolve().parents[2]
    relative = path.resolve().relative_to(repo).as_posix()
    root = Path(__file__).with_name("source-snapshots") / "general-custom116-v1"
    index = root / "index.json"
    if index.is_file():
        row = json.loads(index.read_text(encoding="utf-8"))["files"].get(relative)
        if row:
            candidate = root / row["snapshot"]
            if hashlib.sha256(candidate.read_bytes()).hexdigest() != row["sha256"]:
                raise ValueError("FROZEN_SOURCE_SNAPSHOT_DRIFT")
            return candidate
    return path
