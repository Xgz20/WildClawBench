"""Resolve registered dataset families and explicitly selected releases."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from datetime import datetime
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping, Sequence

import yaml

from .definition import DATASETS, DEFAULT_DEFINITION, DatasetDefinition


ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_]*_task_[0-9]{3,}_[a-z0-9_]+$")


class CatalogError(ValueError):
    """The source catalog cannot be resolved without guessing."""


class _UniqueLoader(yaml.SafeLoader):
    pass


def _unique_mapping(loader: yaml.SafeLoader, node: yaml.MappingNode) -> dict:
    loader.flatten_mapping(node)
    values: dict = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        try:
            if key in values:
                raise CatalogError(f"duplicate YAML key: {key!r}")
            values[key] = loader.construct_object(value_node)
        except TypeError as exc:
            raise CatalogError("YAML mapping keys must be scalar") from exc
    return values


_UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)


def load_mapping(path: Path) -> dict[str, Any]:
    try:
        value = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueLoader)
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise CatalogError(f"cannot read dataset definition: {path}") from exc
    if not isinstance(value, dict):
        raise CatalogError(f"dataset YAML must be a mapping: {path}")
    return value


def repository_path(root: Path, value: object, *, label: str) -> Path:
    if not isinstance(value, str) or not value or "\\" in value or "\0" in value:
        raise CatalogError(f"invalid repository-relative {label}")
    parts = value.split("/")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in parts):
        raise CatalogError(f"invalid repository-relative {label}: {value!r}")
    target = (root.resolve() / Path(*path.parts)).resolve()
    if not target.is_relative_to(root.resolve()):
        raise CatalogError(f"{label} escapes repository root")
    return target


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CatalogError(f"{label} must be a nonempty string")
    return value.strip()


def _id(value: object, label: str) -> str:
    value = _text(value, label)
    if not ID_RE.fullmatch(value):
        raise CatalogError(f"invalid {label}: {value!r}")
    return value


def _strings(value: object, label: str, *, empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list) or (not empty and not value):
        raise CatalogError(f"{label} must be a {'possibly empty ' if empty else 'nonempty '}list")
    result = tuple(_text(item, label) for item in value)
    if len(result) != len(set(result)):
        raise CatalogError(f"duplicate {label}")
    return result


def _counts(value: object, label: str, expected_total: int) -> dict[str, int]:
    if not isinstance(value, dict) or not value:
        raise CatalogError(f"{label} must be a nonempty mapping")
    result: dict[str, int] = {}
    for key, count in value.items():
        key = _text(key, label)
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise CatalogError(f"{label} values must be nonnegative integers")
        result[key] = count
    if sum(result.values()) != expected_total:
        raise CatalogError(f"{label} does not sum to task_count")
    return result


def _schema_one(value: object) -> bool:
    return type(value) is int and value == 1


def _constraints(value: object, count: int) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CatalogError("release constraints must be a mapping")
    allowed = {"multimodal_exact", "multimodal_max_ratio", "production_backed_min",
               "coding_primary_max", "controlled_network_max", "research_retrieval_group_counts"}
    if set(value) - allowed:
        raise CatalogError(f"unknown release constraints: {sorted(set(value) - allowed)}")
    for key, item in value.items():
        if key == "multimodal_max_ratio":
            if type(item) not in {float, int} or not 0 <= item <= 1:
                raise CatalogError(f"{key} must be a ratio in [0, 1]")
        elif key == "research_retrieval_group_counts":
            if (not isinstance(item, dict) or not item
                    or set(item) - {"open_search", "directed_web_retrieval", "local_evidence"}
                    or any(type(n) is not int or n < 0 for n in item.values())
                    or sum(item.values()) > count):
                raise CatalogError("invalid research_retrieval_group_counts")
        elif type(item) is not int or not 0 <= item <= count:
            raise CatalogError(f"{key} must be an integer in [0, task_count]")
    return value


@dataclass(frozen=True)
class RegisteredDataset:
    series_id: str
    definition: DatasetDefinition
    definition_path: Path | None
    manifest_path: Path
    status: str
    kind: str = "family"


def _family_release(root: Path, series_id: str, path: Path, release_id: str | None) -> RegisteredDataset:
    data = load_mapping(path)
    if not _schema_one(data.get("schema_version")) or data.get("series_id") != series_id:
        raise CatalogError(f"dataset schema/series mismatch: {path}")
    base = path.parent
    paths: dict[str, str] = {}
    layout_root = data.get("layout_root")
    if layout_root is not None:
        parts = Path(_text(layout_root, "dataset layout root")).parts
        if len(parts) != 2 or any(not ID_RE.fullmatch(part) for part in parts):
            raise CatalogError("layout_root must be <scene>/<dataset>")
        if base != root / "datasets" / layout_root:
            raise CatalogError("dataset definition and layout_root must correspond")
    for key in ("task_root", "workspace_root", "source_registry", "capability_map"):
        target = repository_path(root, data.get(key), label=key)
        if layout_root and key in {"task_root", "workspace_root"}:
            prefix_root = "tasks" if key == "task_root" else "workspace"
            if target != root / prefix_root / layout_root:
                raise CatalogError(f"{key} must match its canonical layout_root")
        elif not target.is_relative_to(base) or target == base:
            raise CatalogError(f"{key} must stay inside its dataset directory")
        paths[key] = target.relative_to(root).as_posix()
    task_root, workspace_root = [root / paths[k] for k in ("task_root", "workspace_root")]
    if task_root.is_relative_to(workspace_root) or workspace_root.is_relative_to(task_root):
        raise CatalogError("task_root and workspace_root must be separate trees")
    if paths["source_registry"] == paths["capability_map"]:
        raise CatalogError("source registry and capability map must be different files")
    for key in ("source_registry", "capability_map"):
        if any((root / paths[key]).is_relative_to(tree) for tree in (task_root, workspace_root)):
            raise CatalogError(f"{key} must stay outside the task and workspace trees")
    categories = data.get("categories")
    if not isinstance(categories, dict) or not categories:
        raise CatalogError("dataset categories must be a nonempty mapping")
    labels: dict[str, str] = {}
    for category, entry in categories.items():
        category = _id(category, "category")
        labels[category] = _text(entry.get("name") if isinstance(entry, dict) else entry, "category name")
    releases = data.get("releases")
    if not isinstance(releases, dict) or not releases:
        raise CatalogError("dataset releases must be a nonempty mapping")
    selected = _id(release_id or data.get("default_release"), "release ID")
    release = releases.get(selected)
    if not isinstance(release, dict):
        raise CatalogError(f"release {selected!r} is not registered for {series_id}")
    status = release.get("status")
    if status not in {"building", "ready", "frozen"}:
        raise CatalogError("release status must be building, ready or frozen")
    manifest = repository_path(root, release.get("manifest"), label="manifest")
    if not manifest.is_relative_to(base / "manifests") or manifest.suffix != ".json":
        raise CatalogError("release manifest must be a JSON file in the dataset manifests directory")
    task_ids = _strings(release.get("task_ids"), "release task IDs")
    prefix = _text(data.get("task_id_prefix"), "task ID prefix")
    if prefix != series_id.replace("-", "_").replace(".", "_") + "_":
        raise CatalogError("task ID prefix must be derived from its unique series ID")
    legacy_prefixes = _strings(data.get("legacy_task_id_prefixes", []), "legacy task ID prefixes", empty=True)
    prefixes = (prefix, *legacy_prefixes)
    if (len(set(prefixes)) != len(prefixes) or any(not re.fullmatch(r"[a-z][a-z0-9_]*_", p) for p in prefixes)
            or any(not TASK_ID_RE.fullmatch(task_id) for task_id in task_ids)):
        raise CatalogError("release task IDs must use the declared namespace")
    statistics = release.get("expected_statistics")
    if not isinstance(statistics, dict):
        raise CatalogError("release expected_statistics must be a mapping")
    count = statistics.get("task_count")
    if not isinstance(count, int) or isinstance(count, bool) or count < 1 or count != len(task_ids):
        raise CatalogError("release task_count must match its explicit task IDs")
    category_counts = _counts(statistics.get("category_counts"), "category_counts", count)
    if set(category_counts) - set(labels):
        raise CatalogError("release contains an unregistered category")
    directories = release.get("category_directories", data.get("category_directories", {}))
    if (not isinstance(directories, dict)
            or any(not isinstance(directory, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_]*", directory)
                   or not isinstance(category, str) or category not in labels
                   for directory, category in directories.items())
            or len({directory.casefold() for directory in directories}) != len(directories)
            or len(set(directories.values())) != len(directories)
            or len({name.casefold() for name in (*directories, *(labels.keys() - directories.values()))})
               != len(labels)):
        raise CatalogError("category_directories must map distinct relative directories to distinct category keys")
    task_id_style = release.get("task_id_style", data.get("task_id_style", "series_prefix"))
    if task_id_style not in ("series_prefix", "category_directory"):
        raise CatalogError("task_id_style must be series_prefix or category_directory")
    if task_id_style == "category_directory" and set(directories.values()) != set(labels):
        raise CatalogError("category-directory task IDs require a directory for every category")
    include = _strings(data.get("required_tags"), "required tags")
    exclude = _strings(data.get("exclude_tags", ["invalid"]), "exclude tags", empty=True)
    if any(tag != tag.lower() or "," in tag for tag in (*include, *exclude)) or set(include) & set(exclude):
        raise CatalogError("tags must be lowercase, atomic and nonconflicting")
    created_at = _text(release.get("created_at"), "release created_at")
    try:
        if datetime.fromisoformat(created_at).utcoffset() is None:
            raise ValueError("timezone missing")
    except ValueError as exc:
        raise CatalogError("release created_at must be an ISO datetime with timezone") from exc
    scope = (*paths.values(), path.relative_to(root).as_posix())
    definition = DatasetDefinition(
        dataset_id=selected,
        created_at=created_at,
        include_tags=include,
        exclude_tags=exclude,
        expected_task_count=count,
        expected_category_counts=category_counts,
        expected_grading_type_counts=_counts(statistics.get("grading_type_counts"), "grading_type_counts", count),
        expected_difficulty_counts=_counts(statistics.get("difficulty_counts"), "difficulty_counts", count),
        expected_timeout_counts=_counts(statistics.get("timeout_counts"), "timeout_counts", count),
        task_root=paths["task_root"], workspace_root=paths["workspace_root"],
        registry_path=paths["source_registry"], capability_map_path=paths["capability_map"],
        manifest_path=manifest.relative_to(root).as_posix(), revision_scope=scope,
        task_ids=task_ids, task_id_prefix=prefix, legacy_task_id_prefixes=legacy_prefixes,
        category_directories=tuple(directories.items()),
        category_directory_task_ids=task_id_style == "category_directory",
        series_id=series_id, category_labels=labels,
        constraints=_constraints(release.get("constraints", {}), count),
    )
    allowed_stems = {stem for category in category_counts for stem in definition.task_id_stems(category)}
    for task_id in task_ids:
        if task_id.split("_task_", 1)[0] not in allowed_stems:
            raise CatalogError(f"release task ID has an unregistered category or namespace: {task_id}")
    if status == "frozen":
        try:
            locked = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise CatalogError("frozen release manifest is missing or invalid") from exc
        revision = (locked.get("source") or {}).get("revision")
        if locked.get("dataset_id") != selected or not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
            raise CatalogError("frozen release manifest identity/source revision mismatch")
        definition = replace(definition, source_revision=revision)
    return RegisteredDataset(series_id, definition, path, manifest, status)


def load_catalog(repo_root: Path) -> dict[str, dict[str, Any]]:
    root = repo_root.resolve()
    data = load_mapping(root / "datasets/catalog.yaml")
    if not _schema_one(data.get("schema_version")) or not isinstance(data.get("datasets"), dict):
        raise CatalogError("dataset catalog must declare schema_version 1 and a datasets mapping")
    result: dict[str, dict[str, Any]] = {}
    for key, entry in data["datasets"].items():
        key = _id(key, "catalog dataset ID")
        if not isinstance(entry, dict):
            raise CatalogError("catalog entries must be mappings")
        if entry.get("kind") in {"legacy", "builtin"}:
            definition = DATASETS.get(key)
            if (definition is None or entry.get("manifest") != definition.manifest_path
                    or entry.get("kind") == "legacy" and key != DEFAULT_DEFINITION.dataset_id):
                raise CatalogError("builtin entry must reference its existing frozen manifest")
        elif entry.get("kind") == "alias":
            if entry.get("default_release") not in DATASETS:
                raise CatalogError("series alias must select an existing builtin release")
            allowed = _strings(entry.get("releases"), "alias releases")
            if entry["default_release"] not in allowed or any(release not in DATASETS for release in allowed):
                raise CatalogError("series alias has an invalid release")
        else:
            path = repository_path(root, entry.get("definition"), label="definition")
            if entry.get("kind") not in {None, "family"}:
                raise CatalogError(f"unknown catalog entry kind: {entry.get('kind')!r}")
            if not path.is_relative_to(root / "datasets") or path.name != "dataset.yaml":
                raise CatalogError("a family definition must be a dataset.yaml inside datasets/")
            expected_prefix = key.replace("-", "_").replace(".", "_") + "_"
            for other in result:
                if expected_prefix == other.replace("-", "_").replace(".", "_") + "_":
                    raise CatalogError("catalog families must have unique task ID namespaces")
        result[key] = entry
    return result


def load_registered_dataset(repo_root: Path, dataset_id: str, *, release_id: str | None = None) -> RegisteredDataset:
    root = repo_root.resolve()
    catalog = load_catalog(root)
    entry = catalog.get(dataset_id)
    if entry is not None and entry.get("kind") == "alias":
        selected = release_id or entry["default_release"]
        if selected not in entry["releases"]:
            raise CatalogError(f"release {selected!r} does not belong to {dataset_id}")
        return replace(load_registered_dataset(root, selected), series_id=dataset_id)
    if entry is not None and entry.get("kind") in {"legacy", "builtin"}:
        if release_id and release_id != dataset_id:
            raise CatalogError("the builtin entry has only its frozen release")
        definition = DATASETS[dataset_id]
        manifest = repository_path(root, entry["manifest"], label="builtin manifest")
        data = json.loads(manifest.read_text(encoding="utf-8"))
        if data.get("dataset_id") != dataset_id:
            raise CatalogError("builtin manifest dataset ID mismatch")
        revision = (data.get("source") or {}).get("revision")
        if (not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision)
                or definition.source_revision and revision != definition.source_revision):
            raise CatalogError("builtin manifest source revision mismatch")
        definition = replace(definition, task_ids=tuple(t["task_id"] for t in data["tasks"]),
                             source_revision=revision)
        return RegisteredDataset(dataset_id, definition, None, manifest, "frozen", entry["kind"])
    if entry is not None:
        path = repository_path(root, entry["definition"], label="definition")
        return _family_release(root, dataset_id, path, release_id)
    # A published release ID is also an unambiguous selector.
    matches: list[RegisteredDataset] = []
    for series, candidate in catalog.items():
        if candidate.get("kind") in {"legacy", "builtin", "alias"}:
            continue
        path = repository_path(root, candidate["definition"], label="definition")
        if dataset_id in (load_mapping(path).get("releases") or {}):
            matches.append(load_registered_dataset(root, series, release_id=dataset_id))
    if len(matches) != 1 or release_id:
        raise CatalogError(f"dataset/release ID is unknown or ambiguous: {dataset_id!r}")
    return matches[0]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--dataset-id")
    parser.add_argument("--release-id")
    args = parser.parse_args(argv)
    if args.release_id and not args.dataset_id:
        parser.error("--release-id requires --dataset-id")
    ids = [args.dataset_id] if args.dataset_id else list(load_catalog(args.repo_root))
    records = []
    for dataset_id in ids:
        item = load_registered_dataset(args.repo_root, dataset_id, release_id=args.release_id)
        records.append({"series_id": item.series_id, "release_id": item.definition.dataset_id,
                        "status": item.status, "task_root": item.definition.task_root,
                        "workspace_root": item.definition.workspace_root,
                        "expected_task_count": item.definition.expected_task_count,
                        "manifest_exists": item.manifest_path.is_file()})
    print(json.dumps({"datasets": records}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
