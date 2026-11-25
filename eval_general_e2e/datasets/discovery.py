"""Discover source tasks only after checking an explicit frozen release."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .bundle import compile_dataset, load_manifest_lock
from .catalog import load_registered_dataset
from eval_general_e2e.shared.dataset_bundle.verify import _validate_manifest, sha256_file
from src.utils.task_parser import parse_task_md
from .source_history import archived_source_revision, dataset_task_path
from .layout import relocated_task
from .workspaces import materialize_verified_workspaces


@dataclass(frozen=True)
class FrozenTaskSelection:
    identity: dict[str, str]
    tasks: tuple[dict[str, Any], ...]


def discover_frozen_tasks(
    repo_root: Path, dataset_id: str, *, release_id: str | None = None,
    workspace_cache: Path | None = None,
) -> FrozenTaskSelection:
    root = repo_root.resolve()
    registered = load_registered_dataset(root, dataset_id, release_id=release_id)
    if registered.status != "frozen":
        raise ValueError("dataset execution requires a frozen release; building/ready sources are not runnable as a release")
    manifest = load_manifest_lock(registered.manifest_path)
    _validate_manifest(manifest)
    published = ((root / ".wildclawbench-assets/index.json").is_file()
                 or (root / ".wildclawbench-revision").is_file())
    if published:
        from src.e2e.dataset_assets import frozen_dataset
        compiled, members = frozen_dataset(root, registered.definition.dataset_id)
    else:
        compiled, members = compile_dataset(root, definition=registered.definition, source_revision=manifest["source"]["revision"])
    if compiled != manifest:
        raise ValueError("dataset sources differ from the frozen manifest; publish a new release")
    historical = published or archived_source_revision(root, manifest["dataset_id"]) is not None
    frozen_root = (materialize_verified_workspaces(manifest, members, workspace_cache, include_task_files=historical)
                   if workspace_cache is not None else None)
    identity = {"series_id": registered.series_id, "release_id": registered.definition.dataset_id,
                "dataset_digest": manifest["dataset_digest"],
                "task_root": registered.definition.task_root,
                "workspace_root": registered.definition.workspace_root,
                "manifest_sha256": sha256_file(registered.manifest_path)}
    tasks = []
    task_text = {member.path: member.data for member in members if member.path.endswith("/task.md")}
    for record in manifest["tasks"]:
        if historical:
            task_path = (frozen_root / record["task_id"] / "task.md" if frozen_root else
                         relocated_task(root, Path(record["source"]["task_path"])))
            task = parse_task_md(task_path, repo_root=root,
                                 raw=task_text[record["bundle"]["task_path"]].decode("utf-8"))
        else:
            task_path = dataset_task_path(root, record["source"]["task_path"],
                                          registered.definition.frozen_source_index,
                                          registered.definition.current_source_paths)
            task = parse_task_md(task_path, repo_root=root)
        task["category"] = record["category"]
        if frozen_root is not None:
            task["workspace_path"] = str(frozen_root / record["task_id"])
        task["dataset_selection"] = dict(identity)
        tasks.append(task)
    return FrozenTaskSelection(identity, tuple(tasks))
