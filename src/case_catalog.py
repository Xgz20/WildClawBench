"""Read-only case-library index shared by the platform and the runners."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

from eval_general_e2e.datasets.bundle import _parse_task_source, _strip_codeblock, load_manifest_lock
from eval_general_e2e.datasets.catalog import load_catalog, load_mapping, repository_path
from eval_general_e2e.datasets.layout import workspace_for_task
from src.utils.task_parser import normalize_tags


def library(repo: Path) -> dict:
    return load_mapping(repo / "datasets/case-library.yaml")


def dataset_entry(repo: Path, dataset: str) -> dict:
    try:
        return library(repo)["datasets"][dataset]
    except KeyError as exc:
        raise ValueError("CASE_LIBRARY_DATASET_UNKNOWN") from exc


def runnable(tags: list[str], include_drafts: bool = False) -> bool:
    return "invalid" not in tags and (include_drafts or "draft" not in tags)


_CATEGORY_NAMES = {
    "01_Productivity_Flow": "生产力工作流",
    "02_Code_Intelligence": "代码智能",
    "03_Social_Interaction": "社交交互",
    "04_Search_Retrieval": "搜索与检索",
    "05_Creative_Synthesis": "创意综合",
    "06_Safety_Alignment": "安全与对齐",
    "07_Website_Generation": "网站生成",
    "01_Information_Search_Organization": "信息检索与整理",
    "02_Office": "办公",
    "03_Data_Analysis": "数据分析",
}


def _capabilities(meta: dict, fallback: dict | None) -> list[str]:
    mapping = (meta.get("dataset_report") or {}).get("checkpoint_capabilities") or meta.get("checkpoint_capabilities") or fallback
    if not isinstance(mapping, dict):
        return []
    return sorted({key for values in mapping.values() if isinstance(values, list)
                   for key in values if isinstance(key, str)})


def current_cases(repo: Path, dataset: str, entry: dict | None = None) -> list[dict]:
    repo = repo.resolve()
    entry = entry or dataset_entry(repo, dataset)
    root = repository_path(repo, entry["task_root"], label="case library task root")
    display = repository_path(repo, entry.get("display_root", entry["task_root"]), label="case library display root")
    mapping = (load_mapping(repository_path(repo, entry["capability_map"], label="capability map"))
               if entry.get("capability_map") else {})
    rows = {}
    for path in sorted(root.glob("*/*.md")):
        if path.name.casefold() == "readme.md":
            continue
        relative = path.relative_to(root)
        canonical = repository_path(repo, path.relative_to(repo).as_posix(), label="case source")
        metadata, _, raw = _parse_task_source(canonical)
        tags = normalize_tags(metadata.get("tags"))
        if "invalid" in tags:
            continue
        task_id = metadata["id"]
        if task_id in rows:
            raise ValueError(f"CASE_LIBRARY_TASK_ID_DUPLICATE: {task_id}")
        display_path = repository_path(repo, (display / relative).relative_to(repo).as_posix(), label="case display")
        translated = {}
        if display != root and display_path.is_file():
            translated, _, _ = _parse_task_source(display_path)
            if translated.get("id") != task_id:
                raise ValueError(f"CASE_LIBRARY_TRANSLATION_MISMATCH: {task_id}")
        category = translated.get("category") or (metadata.get("dataset_report") or {}).get("category_name") or metadata.get("category") or path.parent.name
        rows[task_id] = {
            "task_id": task_id,
            "name": (translated.get("name") if display != root else metadata.get("name")) or task_id,
            "category": path.parent.name,
            "category_key": metadata.get("category") or path.parent.name,
            "category_display_name": _CATEGORY_NAMES.get(category, category),
            "scene": entry["scene"],
            "library_dataset": dataset,
            "difficulty": metadata.get("difficulty"),
            "modality": metadata.get("modality"),
            "grading_type": metadata.get("grading_type"),
            "timeout_seconds": metadata.get("timeout_seconds", 120),
            "capabilities": _capabilities(metadata, mapping.get(task_id)),
            "tags": tags,
            "task_sha256": hashlib.sha256(raw).hexdigest(),
            "task_path": canonical.relative_to(repo).as_posix(),
            "display_path": display_path.relative_to(repo).as_posix() if translated or display == root else None,
        }
    return list(rows.values())


def releases(repo: Path, entry: dict) -> list[dict]:
    series = entry.get("release_series")
    if not series:
        return []
    catalog = load_catalog(repo)
    definition = catalog[series]
    if definition.get("kind") == "alias":
        default = definition["default_release"]
        paths = {default: catalog[default]["manifest"]}
    else:
        definition = load_mapping(repository_path(repo, definition["definition"], label="dataset definition"))
        default = definition["default_release"]
        release = definition["releases"][default]
        paths = {default: release["manifest"]} if release["status"] == "frozen" else {}
    return [{"id": key, "recommended": key == default,
             "manifest": load_manifest_lock(repository_path(repo, path, label="dataset manifest"))}
            for key, path in reversed(list(paths.items()))]


def release_summary(value: dict) -> dict:
    manifest = value["manifest"]
    return {"id": value["id"], "recommended": value["recommended"],
            "digest": manifest["dataset_digest"], "task_count": manifest["task_count"],
            "created_at": manifest["created_at"]}


def frozen_cases(value: dict, dataset: str, current: dict[str, dict], *, scene: str = "general") -> list[dict]:
    fields = ("task_id", "name", "category", "difficulty", "modality", "grading_type", "tags", "timeout_seconds")
    return [
        {**{key: task.get(key) for key in fields}, "scene": scene, "library_dataset": dataset,
         "category_display_name": current.get(task["task_id"], {}).get("category_display_name") or task["category"],
         "capabilities": current.get(task["task_id"], {}).get("capabilities", [])}
        for task in value["manifest"]["tasks"] if "invalid" not in task.get("tags", [])
    ]


def index(repo: Path, dataset: str | None = None, release: str | None = None) -> dict:
    registry = library(repo)
    groups = []
    for key, entry in registry["datasets"].items():
        if dataset and key != dataset:
            continue
        current = current_cases(repo, key, entry)
        versions = releases(repo, entry)
        cases = current
        if release:
            version = next((item for item in versions if item["id"] == release), None)
            if version is None:
                raise ValueError("CASE_LIBRARY_RELEASE_UNKNOWN")
            cases = frozen_cases(version, key, {row["task_id"]: row for row in current}, scene=entry["scene"])
        groups.append({"id": key, "name": entry["name"], "scene": entry["scene"], "modes": entry["modes"],
                       "task_count": len(current), "draft_count": sum("draft" in row["tags"] for row in current),
                       "releases": [release_summary(item) for item in versions],
                       "cases": [{k: v for k, v in row.items() if k not in {"task_path", "display_path", "category_key"}}
                                 for row in cases]})
    if dataset and not groups:
        raise ValueError("CASE_LIBRARY_DATASET_UNKNOWN")
    return {"scenarios": registry["scenarios"], "datasets": groups}


def document(repo: Path, dataset: str, task_id: str, release: str | None = None,
             *, material: str | None = None) -> dict | bytes:
    repo = repo.resolve()
    if release:
        from src.e2e.preparation import _general_catalog
        if release not in {item["id"] for item in releases(repo, dataset_entry(repo, dataset))}:
            raise ValueError("CASE_LIBRARY_RELEASE_UNKNOWN")
        tasks, members, _ = _general_catalog(repo, release)
        task = next((row for row in tasks if row["task_id"] == task_id and "invalid" not in row["tags"]), None)
        if task is None:
            raise ValueError("CASE_LIBRARY_TASK_UNKNOWN")
        text = members[task["bundle"]["task_path"]].data.decode("utf-8")
        materials = [item["path"] for item in task["materials"]["execution"]["entries"]
                     if item["kind"] == "file" and Path(item["path"]).name != ".gitkeep"]
        if material:
            if material not in materials:
                raise ValueError("CASE_LIBRARY_MATERIAL_UNKNOWN")
            return members["tasks/" + task_id + "/execution/exec/" + material].data
    else:
        task = next((row for row in current_cases(repo, dataset) if row["task_id"] == task_id), None)
        if task is None:
            raise ValueError("CASE_LIBRARY_TASK_UNKNOWN")
        text = (repo / task["display_path"]).read_text(encoding="utf-8") if task["display_path"] else ""
        _, sections, _ = _parse_task_source(repo / task["task_path"])
        declared = _strip_codeblock(sections.get("Workspace Path", ""))
        public_files = {}
        if declared:
            workspace = workspace_for_task(repo, Path(declared)).resolve()
            if workspace.is_relative_to(repo / "workspace") and not set(workspace.relative_to(repo).parts).intersection({"gt", "private-scoring"}):
                public = workspace / "exec" if (workspace / "exec").is_dir() else workspace
                public_files = {
                    p.relative_to(public).as_posix(): p
                    for p in sorted(public.rglob("*"))
                    if p.is_file() and p.name != ".gitkeep" and p.resolve().is_relative_to(public)
                    and p.resolve().is_relative_to(workspace)
                    and not set(p.relative_to(public).parts).intersection({"gt", ".git", "private-scoring"})
                }
        if material:
            if material not in public_files:
                raise ValueError("CASE_LIBRARY_MATERIAL_UNKNOWN")
            return public_files[material].read_bytes()
        materials = list(public_files)
    return {"content": re.sub(r"\A---[ \t]*\r?\n.*?\r?\n---[ \t]*(?:\r?\n|$)", "", text, count=1, flags=re.S).strip(), "materials": materials}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--dataset")
    parser.add_argument("--release")
    parser.add_argument("--task")
    parser.add_argument("--material")
    args = parser.parse_args()
    if (args.release or args.task) and not args.dataset:
        parser.error("--release and --task require --dataset")
    if args.material and not args.task:
        parser.error("--material requires --task")
    repo = args.repo_root.resolve()
    try:
        result = (document(repo, args.dataset, args.task, args.release, material=args.material) if args.task
                  else index(repo, args.dataset, args.release))
    except (OSError, ValueError) as exc:
        parser.exit(1, str(exc) + "\n")
    if isinstance(result, bytes):
        sys.stdout.buffer.write(result)
    else:
        print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
