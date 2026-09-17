"""Repository layout validation for the General E2E integration surface."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Union

from .adapters import inspect_shared_component_layout
from .stages import GENERAL_E2E_SKILLS


LEGACY_EVAL_E2E_FILES = (
    "__init__.py",
    "e2e_manifest.py",
    "prepare_workspaces.py",
    "collect_runs.py",
    "grade_runs.py",
)


def find_repo_root(start: Optional[Union[str, Path]] = None) -> Path:
    """Find the checkout containing both General E2E and report Skill roots."""

    origin = Path(start or __file__).expanduser().resolve()
    current = origin if origin.is_dir() else origin.parent
    for candidate in (current, *current.parents):
        if (
            (candidate / "eval_general_e2e").is_dir()
            and (candidate / "tools/report/skills").is_dir()
        ):
            return candidate
    raise FileNotFoundError(f"cannot locate WildClawBench checkout from {origin}")


def _frontmatter_name(skill_file: Path) -> Optional[str]:
    text = skill_file.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        return None
    for line in lines[1:]:
        if line == "---":
            break
        if line.startswith("name:"):
            return line.split(":", 1)[1].strip().strip('"').strip("'")
    return None


def inspect_repository_layout(repo_root: Union[str, Path]) -> Dict[str, object]:
    """Return a deterministic report for canonical and discovery entries."""

    root = Path(repo_root).expanduser().resolve()
    canonical_root = root / "tools/report/skills/general-e2e"
    discovery_root = root / ".agents/skills"
    errors: List[Dict[str, str]] = []
    skill_rows: List[Dict[str, object]] = []
    expected_names = [spec.name for spec in GENERAL_E2E_SKILLS]

    actual_names = sorted(
        path.name for path in canonical_root.iterdir() if path.is_dir()
    ) if canonical_root.is_dir() else []
    if actual_names != sorted(expected_names):
        errors.append({
            "code": "SKILL_SET_MISMATCH",
            "detail": f"expected {sorted(expected_names)}, got {actual_names}",
        })

    for spec in GENERAL_E2E_SKILLS:
        canonical = canonical_root / spec.name
        skill_file = canonical / "SKILL.md"
        metadata_file = canonical / "skill-metadata.json"
        interface_file = canonical / "agents/openai.yaml"
        discovery = discovery_root / spec.name
        expected_link = f"../../tools/report/skills/general-e2e/{spec.name}"
        row_errors: List[str] = []

        if not skill_file.is_file():
            row_errors.append("missing SKILL.md")
        elif _frontmatter_name(skill_file) != spec.name:
            row_errors.append("frontmatter name mismatch")

        metadata = None
        if not metadata_file.is_file():
            row_errors.append("missing skill-metadata.json")
        else:
            try:
                metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                row_errors.append(f"invalid skill metadata: {exc}")
            if metadata is not None and metadata != spec.metadata():
                row_errors.append("skill metadata does not match locked registry")

        if not interface_file.is_file():
            row_errors.append("missing agents/openai.yaml")
        elif f"${spec.name}" not in interface_file.read_text(encoding="utf-8"):
            row_errors.append("default prompt does not name the Skill")

        if not discovery.is_symlink():
            row_errors.append("discovery entry is not a symbolic link")
        else:
            actual_link = Path(os.readlink(discovery)).as_posix()
            if actual_link != expected_link:
                row_errors.append(
                    f"discovery target mismatch: expected {expected_link}, got {actual_link}"
                )
            elif discovery.resolve() != canonical.resolve():
                row_errors.append("discovery link does not resolve to canonical source")

        legacy_duplicate = root / "tools/report/skills" / spec.name
        if legacy_duplicate.exists() or legacy_duplicate.is_symlink():
            row_errors.append("legacy root contains a duplicate Skill")

        for detail in row_errors:
            errors.append({"code": "SKILL_LAYOUT_INVALID", "skill": spec.name, "detail": detail})
        skill_rows.append({
            "name": spec.name,
            "canonical_path": canonical.relative_to(root).as_posix(),
            "discovery_path": discovery.relative_to(root).as_posix(),
            "implementation_status": spec.implementation_status,
            "valid": not row_errors,
        })

    legacy_root = root / "eval_e2e"
    legacy_missing = [
        name for name in LEGACY_EVAL_E2E_FILES if not (legacy_root / name).is_file()
    ]
    if legacy_missing:
        errors.append({
            "code": "LEGACY_EVAL_E2E_MISSING",
            "detail": f"missing legacy files: {legacy_missing}",
        })

    shared_components = inspect_shared_component_layout(root)
    errors.extend(shared_components["errors"])

    return {
        "schema_version": "wildclawbench.general-e2e-layout-check/v1",
        "status": "PASS" if not errors else "FAIL",
        "repo_root": str(root),
        "expected_skill_count": len(GENERAL_E2E_SKILLS),
        "skills": skill_rows,
        "legacy_eval_e2e": {
            "path": legacy_root.relative_to(root).as_posix(),
            "required_files": list(LEGACY_EVAL_E2E_FILES),
            "missing_files": legacy_missing,
            "preserved": not legacy_missing,
        },
        "shared_components": shared_components,
        "errors": errors,
    }
