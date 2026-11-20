"""Read explicitly archived dataset sources without changing historical locks.

Only paths in the SHA-bound index are overridden/excluded. Unregistered files
and current datasets retain ordinary source-drift detection.
"""
from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
import tempfile

from .layout import load_layout, relocated_task


def archived_source_revision(repo: Path, dataset_id: str) -> str | None:
    layout = load_layout(repo)
    if dataset_id not in layout.get("historical_releases", ()):
        return None
    revision = layout.get("historical_source_revision")
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError(f"invalid pre-migration source revision for {dataset_id}")
    return revision


@contextmanager
def pre_migration_sources(repo: Path, definition, *, additional_paths=()):
    """Expose the verified legacy layout as a temporary source tree."""
    revision = archived_source_revision(repo, definition.dataset_id)
    if revision is None:
        yield None
        return
    paths = [definition.task_root, definition.workspace_root, definition.registry_path,
             definition.capability_map_path, *additional_paths]
    if definition.frozen_source_index:
        paths.append(str(_relative(definition.frozen_source_index).parent))
    paths = sorted({_relative(path).as_posix() for path in paths})
    paths = [path for path in paths if not any(path.startswith(parent + "/") for parent in paths)]
    with tempfile.TemporaryDirectory(prefix="wcb-frozen-sources-") as temporary:
        root = Path(temporary)
        archive = root / "source.tar"
        result = subprocess.run(
            ["git", "archive", "--format=tar", f"--output={archive}", revision, "--", *paths],
            cwd=repo, capture_output=True, text=True,
        )
        if result.returncode:
            raise ValueError(f"cannot read historical source tree {revision}; fetch its Git history: "
                             f"{result.stderr.strip()}")
        checkout = root / "checkout"
        with tarfile.open(archive) as stream:
            stream.extractall(checkout, filter="data")
        archive.unlink()
        yield checkout.resolve()


def _relative(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or "\\" in value or any(p in {".", ".."} for p in path.parts):
        raise ValueError("FROZEN_SOURCE_PATH_INVALID")
    return path


class FrozenSources:
    def __init__(self, repo: Path, index: str | None = None, current_paths: tuple[str, ...] = ()):
        self.repo = repo.resolve()
        self.overrides: dict[str, bytes] = {}
        current = tuple(_relative(path) for path in current_paths)

        def use_current(path: PurePosixPath) -> bool:
            return any(path == root or root in path.parents for root in current)

        self.excluded: tuple[PurePosixPath, ...] = ()
        if index is None:
            return
        target = self.repo / _relative(index)
        doc = json.loads(target.read_text(encoding="utf-8"))
        if doc.get("schema_version") != "general-e2e-frozen-source-index/v1":
            raise ValueError("FROZEN_SOURCE_INDEX_INVALID")
        for relative, row in doc["files"].items():
            if use_current(_relative(relative)):
                continue
            snapshot = target.parent / _relative(row["snapshot"])
            if snapshot.is_symlink() or not snapshot.resolve().is_relative_to(target.parent.resolve()):
                raise ValueError("FROZEN_SOURCE_SNAPSHOT_ESCAPE")
            data = snapshot.read_bytes()
            if hashlib.sha256(data).hexdigest() != row["sha256"]:
                raise ValueError("FROZEN_SOURCE_SNAPSHOT_DRIFT: " + relative)
            self.overrides[relative] = data
        excluded = (_relative(path) for path in doc.get("excluded_paths", []))
        self.excluded = tuple(path for path in excluded if not use_current(path))

    def read_bytes(self, path: Path) -> bytes:
        relative = path.resolve().relative_to(self.repo).as_posix()
        return self.overrides[relative] if relative in self.overrides else path.read_bytes()

    def excludes(self, path: Path) -> bool:
        relative = PurePosixPath(path.absolute().relative_to(self.repo).as_posix())
        return any(relative == excluded or excluded in relative.parents for excluded in self.excluded)


def dataset_task_path(
    repo: Path, relative: str, index: str | None = None, current_paths: tuple[str, ...] = (),
) -> Path:
    """Expose the exact archived task to CLI consumers without rewriting it."""
    if index:
        relative = _historical_task_name(repo, relative)
    frozen = FrozenSources(repo, index, current_paths)
    _relative(relative)
    if relative not in frozen.overrides:
        return relocated_task(repo, Path(relative))
    target = repo / _relative(index)
    row = json.loads(target.read_text(encoding='utf-8'))['files'][relative]
    return target.parent / _relative(row['snapshot'])


def _historical_task_name(repo: Path, relative: str) -> str:
    return next((old for old, new in load_layout(repo).get("task_paths", {}).items() if new == relative), relative)


def frozen_v2_task_path(path: Path) -> Path:
    repo = Path(__file__).resolve().parents[2]
    return dataset_task_path(repo, path.resolve().relative_to(repo).as_posix(),
        'eval_general_e2e/datasets/source-snapshots/general-custom70-v2/index.json')


def frozen_task_path(path: Path) -> Path:
    """Explicit v1 fixture path for tests of historical correction profiles."""
    repo = Path(__file__).resolve().parents[2]
    relative = _historical_task_name(repo, path.resolve().relative_to(repo).as_posix())
    root = Path(__file__).with_name("source-snapshots") / "general-custom116-v1"
    index = root / "index.json"
    if index.is_file():
        row = json.loads(index.read_text(encoding="utf-8"))["files"].get(relative)
        if row:
            candidate = root / row["snapshot"]
            if hashlib.sha256(candidate.read_bytes()).hexdigest() != row["sha256"]:
                raise ValueError("FROZEN_SOURCE_SNAPSHOT_DRIFT")
            return candidate
    return relocated_task(repo, path)
