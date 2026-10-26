"""Discover source tasks only after checking an explicit frozen release."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .bundle import compile_dataset, load_manifest_lock
from .catalog import load_registered_dataset
from eval_general_e2e.shared.dataset_bundle.verify import _validate_manifest, sha256_file
from src.utils.task_parser import parse_task_md


@dataclass(frozen=True)
class FrozenTaskSelection:
    identity: dict[str, str]
    tasks: tuple[dict[str, Any], ...]


def discover_frozen_tasks(repo_root: Path, dataset_id: str, *, release_id: str | None = None) -> FrozenTaskSelection:
    root = repo_root.resolve()
    registered = load_registered_dataset(root, dataset_id, release_id=release_id)
    if registered.status != "frozen":
        raise ValueError("dataset execution requires a frozen release; building/ready sources are not runnable as a release")
    manifest = load_manifest_lock(registered.manifest_path)
    _validate_manifest(manifest)
    compiled, _ = compile_dataset(root, definition=registered.definition, source_revision=manifest["source"]["revision"])
    if compiled != manifest:
        raise ValueError("dataset sources differ from the frozen manifest; publish a new release")
    identity = {"series_id": registered.series_id, "release_id": registered.definition.dataset_id,
                "dataset_digest": manifest["dataset_digest"],
                "task_root": registered.definition.task_root,
                "workspace_root": registered.definition.workspace_root,
                "manifest_sha256": sha256_file(registered.manifest_path)}
    tasks = []
    for record in manifest["tasks"]:
        task = parse_task_md(root / record["source"]["task_path"], repo_root=root)
        task["dataset_selection"] = dict(identity)
        tasks.append(task)
    return FrozenTaskSelection(identity, tuple(tasks))
