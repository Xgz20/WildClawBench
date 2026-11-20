"""Locate current task sources and recognize pre-migration paths."""

from __future__ import annotations

import json
from pathlib import Path


def load_layout(repo: Path) -> dict:
    path = repo / "datasets/layout.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _relative(repo: Path, path: Path) -> str | None:
    if not path.is_absolute():
        return path.as_posix()
    return path.relative_to(repo).as_posix() if path.is_relative_to(repo) else None


def relocated_task(repo: Path, path: Path) -> Path:
    """Resolve an old task argument to the canonical repository file."""
    destination = load_layout(repo).get("task_paths", {}).get(_relative(repo, path))
    return repo / destination if destination else (path if path.is_absolute() else repo / path)


def relocated_category(repo: Path, layout: dict, directory: str) -> Path | None:
    """Resolve a category alias only when its original files share a current directory."""
    targets = {Path(new).parent for old, new in layout.get("task_paths", {}).items()
               if Path(old).parent.as_posix() == directory}
    return repo / targets.pop() if len(targets) == 1 else None


def current_task_id(repo: Path, task_id: str) -> str:
    return load_layout(repo).get("task_id_aliases", {}).get(task_id, task_id)


def task_id_conflicts(tasks_root: Path, excluded_root: Path, task_ids: set[str]) -> list[Path]:
    ids = {task_id.casefold() for task_id in task_ids}
    return sorted(path for path in tasks_root.rglob("*_task_*.md")
                  if path.stem.casefold() in ids and not path.is_relative_to(excluded_root)
                  and not is_reading_or_archived_task(tasks_root, path))


def workspace_for_task(repo: Path, path: Path) -> Path:
    """Use the current workspace, with fallback for upstream downloaded inputs."""
    layout = load_layout(repo)
    mappings = layout.get("workspace_paths", {})
    relative = _relative(repo, path)
    current = mappings.get(relative, relative)
    if current is None:
        return path
    target = repo / current
    if current.startswith(("workspace/general/wildclawbench/en/", "workspace/web/artifactsbench/")) and not target.exists():
        original = next((old for old, new in mappings.items() if new == current), None)
        if original and (repo / original).is_dir():
            return repo / original
    return target


def is_reading_or_archived_task(tasks_root: Path, path: Path, *, include_translations: bool = False) -> bool:
    if not path.is_relative_to(tasks_root):
        return False
    folders = path.relative_to(tasks_root).parts[:-1]
    return "_archive" in folders or ("cn" in folders and not include_translations)


def cli_category_paths(tasks_root: Path, category: str) -> list[Path]:
    """Keep the legacy category as the original upstream + extension selection."""
    if category.startswith("/") or "\\" in category or any(p in {"", ".", ".."} for p in category.split("/")):
        raise ValueError(f"invalid task category: {category!r}")
    layout = load_layout(tasks_root.parent)
    if not layout or tasks_root.name != "tasks":
        roots = [tasks_root / category, tasks_root / "extension" / category]
    elif "/" in category:
        root = tasks_root / category
        if category.startswith("general/challenge/") and not root.is_dir():
            relocated = relocated_category(tasks_root.parent, layout, f"tasks/{category}")
            root = relocated or root
        return sorted(p for p in root.rglob("*task_*.md")
                      if not is_reading_or_archived_task(tasks_root, p))
    elif category == "07_Website_Generation":
        roots = [tasks_root / "web/artifactsbench" / category, tasks_root / "web/custom" / category]
    else:
        roots = [tasks_root / prefix / category
                 for prefix in ("general/wildclawbench/en", "general/regression", "ppt/custom")]
        # The old extension category sorted the baseline and PPT tasks together.
        return sorted(roots[0].glob("*task_*.md")) + sorted(
            (p for root in roots[1:] for p in root.glob("*task_*.md")), key=lambda p: p.name)
    return [p for root in roots for p in sorted(root.glob("*task_*.md"))]


def cli_task_path(repo: Path, tasks_root: Path, argument: str) -> Path:
    path = Path(argument).expanduser()
    if path.is_file():
        path = path.absolute()
    candidate = relocated_task(repo, path)
    if not candidate.is_file() and path.name == argument and path.suffix != ".md":
        task_id = current_task_id(repo, argument)
        matches = [p for p in tasks_root.rglob(f"{task_id}.md")
                   if p.stem == task_id and not is_reading_or_archived_task(tasks_root, p)]
        if len(matches) > 1:
            raise ValueError(f"ambiguous task ID: {argument}")
        if matches:
            candidate = matches[0]
    if not candidate.is_file():
        raise ValueError(f"task file not found: {argument}")
    candidate = candidate.resolve()
    if is_reading_or_archived_task(tasks_root.resolve(), candidate):
        raise ValueError(f"task is a reading copy or archived: {argument}")
    return candidate
