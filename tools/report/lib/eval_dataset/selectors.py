"""任务目录、文件、ID 和 @清单选择器。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import yaml

from .contracts import FAIL, Issue


@dataclass
class SelectionResult:
    files: list[Path] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    selectors: list[str] = field(default_factory=list)


def _task_id(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
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


def _is_doc_copy(path: Path, repo_root: Path) -> bool:
    """判断是否为仅供阅读的中文任务副本。"""
    resolved = path.resolve()
    for copy_root in (repo_root / "tasks" / "cn", repo_root / "tasks" / "extension" / "cn"):
        try:
            resolved.relative_to(copy_root.resolve())
            return True
        except ValueError:
            continue
    return False


def _markdown_files(directory: Path, *, repo_root: Path, include_doc_copies: bool = False) -> list[Path]:
    return sorted(
        (
            path
            for path in directory.rglob("*.md")
            if path.is_file() and (include_doc_copies or not _is_doc_copy(path, repo_root))
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
    if not dirs and not paths and not ids:
        dirs = [Path(default_root)]

    for directory in dirs:
        candidate = directory if directory.is_absolute() else repo_root / directory
        selectors.append(str(candidate.resolve()))
        if not candidate.exists() or not candidate.is_dir():
            issues.append(Issue(FAIL, "TASK_DIR_NOT_FOUND", f"任务目录不存在: {candidate}", location=str(candidate)))
            continue
        selected.extend(_markdown_files(candidate, repo_root=repo_root, include_doc_copies=include_doc_copies))

    for item in paths:
        candidate = item if item.is_absolute() else repo_root / item
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
        for raw_id in ids:
            value = Path(raw_id).expanduser()
            if value.suffix.lower() == ".md" or value.exists() or "/" in raw_id:
                candidate = value if value.is_absolute() else repo_root / value
                if candidate.is_file():
                    selected.append(candidate)
                    selectors.append(str(candidate.resolve()))
                    continue
            matches = [path for path in all_files if _task_id(path) == raw_id]
            selectors.append(raw_id)
            if not matches:
                issues.append(Issue(FAIL, "TASK_ID_NOT_FOUND", f"未找到任务 ID: {raw_id}", task_id=raw_id))
            elif len(matches) > 1:
                issues.append(Issue(FAIL, "TASK_ID_AMBIGUOUS", f"任务 ID 对应多个文件: {raw_id}", task_id=raw_id, evidence={"matches": [str(p) for p in matches]}))
            else:
                selected.append(matches[0])

    unique: dict[str, Path] = {}
    for path in selected:
        unique[str(path.resolve())] = path.resolve()
    return SelectionResult(sorted(unique.values(), key=str), issues, selectors)


# 兼容更直观的调用名。
resolve_task_files = select_task_files
