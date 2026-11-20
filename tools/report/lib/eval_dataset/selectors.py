"""任务目录、文件、ID 和 @清单选择器。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import yaml

from eval_general_e2e.datasets.catalog import load_registered_dataset
from eval_general_e2e.datasets.layout import is_reading_or_archived_task, relocated_task, load_layout
from eval_general_e2e.datasets.source_history import FrozenSources, archived_source_revision
from .contracts import FAIL, Issue


@dataclass
class SelectionResult:
    files: list[Path] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    selectors: list[str] = field(default_factory=list)


def _task_id(path: Path, sources: FrozenSources | None = None) -> str:
    try:
        raw = sources.read_bytes(path) if sources and path.resolve().is_relative_to(sources.repo) else path.read_bytes()
        text = raw.decode("utf-8")
    except (OSError, UnicodeError):
        return path.stem
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if match:
        try:
            metadata = yaml.safe_load(match.group(1)) or {}
            if isinstance(metadata, dict) and metadata.get("id"):
                return str(metadata["id"])
        except yaml.YAMLError:
            pass
    return path.stem


def _markdown_files(directory: Path, *, repo_root: Path, include_doc_copies: bool = False) -> list[Path]:
    return sorted(
        (
            path
            for path in directory.rglob("*.md")
            if path.is_file() and not is_reading_or_archived_task(
                repo_root / "tasks", path.resolve(), include_translations=include_doc_copies)
        ),
        key=lambda path: str(path.resolve()),
    )


def _expand_manifest(value: str, repo_root: Path | None = None) -> list[str]:
    if not value.startswith("@"):
        return [value]
    manifest = Path(value[1:]).expanduser()
    if repo_root is not None and not manifest.is_absolute() and not manifest.exists():
        manifest = repo_root / manifest
    if not manifest.is_file():
        return [value]
    entries: list[str] = []
    for raw in manifest.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            entries.append(line)
    return entries


def select_task_files(
    repo_root: Path,
    *,
    task_dirs: Iterable[str | Path] = (),
    task_paths: Iterable[str | Path] = (),
    task_ids: Iterable[str] = (),
    default_root: str | Path = "tasks",
    include_doc_copies: bool = False,
    dataset_id: str | None = None,
    release_id: str | None = None,
) -> SelectionResult:
    """选择任务文件；默认排除 tasks/cn 阅读副本，ID 多义时不静默合并。"""
    repo_root = Path(repo_root).resolve()
    dirs = [Path(item).expanduser() for item in task_dirs]
    paths = [Path(item).expanduser() for item in task_paths]
    ids: list[str] = []
    for value in task_ids:
        ids.extend(_expand_manifest(str(value), repo_root))

    selected: list[Path] = []
    issues: list[Issue] = []
    selectors: list[str] = []
    registered = None
    sources = None
    historical = False
    layout = load_layout(repo_root)
    aliases = layout.get("task_id_aliases", {})
    release_ids: set[str] = set()
    visible_release_ids: set[str] = set()
    if release_id and not dataset_id:
        return SelectionResult(issues=[Issue(FAIL, "DATASET_DEFINITION_INVALID", "release_id需要dataset_id")])
    if dataset_id:
        historical_roots = {
            "tasks/extension": "tasks/general/regression",
            "tasks/general_e2e": "tasks/general/work",
            "datasets/general-hard/tasks": "tasks/general/challenge",
        }
        try:
            registered = load_registered_dataset(repo_root, dataset_id, release_id=release_id)
            default_root = registered.definition.task_root
            release_ids = set(registered.definition.task_ids)
            historical = archived_source_revision(repo_root, registered.definition.dataset_id) is not None
            visible_release_ids = {aliases.get(task_id, task_id) for task_id in release_ids} if historical else release_ids
            if historical:
                default_root = historical_roots.get(default_root, default_root)
            else:
                sources = FrozenSources(repo_root, registered.definition.frozen_source_index,
                                        registered.definition.current_source_paths)
        except (OSError, ValueError) as exc:
            return SelectionResult(issues=[Issue(FAIL, "DATASET_DEFINITION_INVALID", str(exc))])
        selectors.append(f"dataset:{registered.series_id}/{registered.definition.dataset_id}")
        if not dirs and not paths and not ids:
            ids = list(registered.definition.task_ids)
    if not dirs and not paths and not ids:
        dirs = [Path(default_root)]

    for directory in dirs:
        candidate = directory if directory.is_absolute() else repo_root / directory
        selectors.append(str(candidate.resolve()))
        if not candidate.exists() or not candidate.is_dir():
            if candidate.is_relative_to(repo_root):
                prefix = candidate.relative_to(repo_root).as_posix() + "/"
                relocated = [repo_root / new for old, new in layout.get("task_paths", {}).items()
                             if old.startswith(prefix)]
                if relocated:
                    selected.extend(path for path in relocated if path.is_file()
                                    and not is_reading_or_archived_task(
                                        repo_root / "tasks", path, include_translations=include_doc_copies))
                    continue
            issues.append(Issue(FAIL, "TASK_DIR_NOT_FOUND", f"任务目录不存在: {candidate}", location=str(candidate)))
            continue
        selected.extend(_markdown_files(candidate, repo_root=repo_root, include_doc_copies=include_doc_copies))

    for item in paths:
        candidate = relocated_task(repo_root, item)
        selectors.append(str(candidate.resolve()))
        if not candidate.exists() or not candidate.is_file():
            issues.append(Issue(FAIL, "TASK_PATH_NOT_FOUND", f"任务文件不存在: {candidate}", location=str(candidate)))
        elif candidate.suffix.lower() != ".md":
            issues.append(Issue(FAIL, "TASK_PATH_NOT_MARKDOWN", f"任务文件必须是 Markdown: {candidate}", location=str(candidate)))
        else:
            selected.append(candidate)

    if ids:
        search_files: list[Path] = []
        default_candidate = repo_root / default_root
        if default_candidate.is_dir():
            search_files.extend(_markdown_files(default_candidate, repo_root=repo_root, include_doc_copies=include_doc_copies))
        for directory in dirs:
            candidate = directory if directory.is_absolute() else repo_root / directory
            if candidate.is_dir():
                search_files.extend(_markdown_files(candidate, repo_root=repo_root, include_doc_copies=include_doc_copies))
        for path in paths:
            candidate = path if path.is_absolute() else repo_root / path
            if candidate.is_file():
                search_files.append(candidate)
        all_files = list({str(path.resolve()): path.resolve() for path in search_files}.values())
        matches_by_id: dict[str, list[Path]] = {}
        for path in all_files:
            matches_by_id.setdefault(_task_id(path, sources), []).append(path)
        for raw_id in ids:
            value = Path(raw_id).expanduser()
            if value.suffix.lower() == ".md" or value.exists() or "/" in raw_id:
                candidate = relocated_task(repo_root, value)
                if candidate.is_file():
                    selected.append(candidate)
                    selectors.append(str(candidate.resolve()))
                    continue
            matches = (matches_by_id.get(aliases.get(raw_id, raw_id), [])
                       if not historical or raw_id in release_ids else [])
            selectors.append(raw_id)
            if not matches:
                issues.append(Issue(FAIL, "TASK_ID_NOT_FOUND", f"未找到任务 ID: {raw_id}", task_id=raw_id))
            elif len(matches) > 1:
                issues.append(Issue(FAIL, "TASK_ID_AMBIGUOUS", f"任务 ID 对应多个文件: {raw_id}", task_id=raw_id, evidence={"matches": [str(p) for p in matches]}))
            else:
                selected.append(matches[0])

    unique: dict[str, Path] = {}
    for path in selected:
        if is_reading_or_archived_task(repo_root / "tasks", path.resolve(), include_translations=include_doc_copies):
            issues.append(Issue(FAIL, "TASK_NOT_ACTIVE", "任务是阅读副本或归档题", location=str(path)))
            continue
        if registered:
            root = (repo_root / default_root).resolve()
            if not path.resolve().is_relative_to(root):
                issues.append(Issue(FAIL, "DATASET_TASK_OUTSIDE_ROOT", "任务越出所选数据集根目录", location=str(path)))
                continue
            if _task_id(path, sources) not in visible_release_ids:
                issues.append(Issue(FAIL, "DATASET_TASK_OUT_OF_RELEASE", "任务不在所选冻结版本清单", task_id=_task_id(path, sources), location=str(path)))
                continue
        unique[str(path.resolve())] = path.resolve()
    return SelectionResult(sorted(unique.values(), key=str), issues, selectors)


# 兼容更直观的调用名。
resolve_task_files = select_task_files
