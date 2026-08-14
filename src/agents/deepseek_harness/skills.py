from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yaml


DSH_SKILLS_DIR = "/root/.dsh/skills"
_DSH_SKILL_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_NON_ALPHANUMERIC = re.compile(r"[^a-z0-9]+")


class DshSkillError(ValueError):
    """Raised when a declared task skill cannot be installed for DSH."""


@dataclass(frozen=True)
class _SkillBundle:
    source: Path
    normalized_name: str


def normalize_dsh_skill_name(name: str) -> str:
    normalized = _NON_ALPHANUMERIC.sub("-", name.strip().lower()).strip("-")
    if not normalized or not _DSH_SKILL_NAME.fullmatch(normalized):
        raise DshSkillError(f"skill name {name!r} cannot be normalized for DSH")
    return normalized


def build_dsh_prompt(base_prompt: str, skill_names: list[str]) -> str:
    if not skill_names:
        return base_prompt
    gestures = "\n".join(f"/{name}" for name in skill_names)
    return f"{gestures}\n\n{base_prompt}"


def _parse_skill(path: Path) -> tuple[dict[str, object], str]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DshSkillError(f"failed to read skill file {path}: {exc}") from exc

    lines = raw.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise DshSkillError(f"skill file {path} is missing YAML frontmatter")
    closing_index = next(
        (index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"),
        None,
    )
    if closing_index is None:
        raise DshSkillError(f"skill file {path} has unterminated YAML frontmatter")

    try:
        metadata = yaml.safe_load("".join(lines[1:closing_index]))
    except yaml.YAMLError as exc:
        raise DshSkillError(f"skill file {path} has invalid YAML frontmatter: {exc}") from exc
    if not isinstance(metadata, dict):
        raise DshSkillError(f"skill file {path} frontmatter must be a YAML mapping")
    name = metadata.get("name")
    description = metadata.get("description")
    if not isinstance(name, str) or not name.strip():
        raise DshSkillError(f"skill file {path} frontmatter requires a string name")
    if not isinstance(description, str) or not description.strip():
        raise DshSkillError(f"skill file {path} frontmatter requires a string description")
    return metadata, "".join(lines[closing_index + 1 :])


def _render_staged_skill(
    metadata: dict[str, object],
    body: str,
    normalized_name: str,
    container_bundle_dir: str,
) -> str:
    staged_metadata = dict(metadata)
    staged_metadata["name"] = normalized_name
    frontmatter = yaml.safe_dump(
        staged_metadata,
        allow_unicode=True,
        sort_keys=False,
    ).rstrip()
    staged = f"---\n{frontmatter}\n---\n{body}"
    return staged.replace("{baseDir}", container_bundle_dir)


def _resolve_bundle(skills_root: Path, declaration: str) -> tuple[Path, Path]:
    relative = declaration.replace("\\", "/").strip("/")
    if not relative:
        raise DshSkillError("skill declaration must not be empty")
    source = (skills_root / relative).resolve()
    try:
        source.relative_to(skills_root)
    except ValueError as exc:
        raise DshSkillError(
            f"skill declaration {declaration!r} escapes skills root {skills_root}"
        ) from exc
    skill_file = source / "SKILL.md"
    if not source.is_dir() or not skill_file.is_file():
        raise DshSkillError(f"declared skill bundle not found: {source}")
    return source, skill_file


def _docker_run(command: list[str], operation: str) -> None:
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        suffix = f": {detail}" if detail else ""
        raise DshSkillError(f"{operation} failed{suffix}")


def install_dsh_skills(
    task_id: str,
    skills: str,
    skills_path: str,
    *,
    container_skills_root: str = DSH_SKILLS_DIR,
) -> list[str]:
    skills_root = Path(skills_path).expanduser().resolve()
    bundles: list[_SkillBundle] = []
    seen: dict[str, str] = {}

    for declaration in (line.strip() for line in skills.splitlines()):
        if not declaration:
            continue
        source, skill_file = _resolve_bundle(skills_root, declaration)
        metadata, _ = _parse_skill(skill_file)
        declared_name = str(metadata["name"])
        normalized_name = normalize_dsh_skill_name(declared_name)
        previous = seen.get(normalized_name)
        if previous is not None:
            raise DshSkillError(
                "normalized skill name collision "
                f"{normalized_name!r}: {previous!r} and {declaration!r}"
            )
        seen[normalized_name] = declaration
        bundles.append(_SkillBundle(source, normalized_name))

    if not bundles:
        return []

    container_root = container_skills_root.rstrip("/")
    _docker_run(
        ["docker", "exec", task_id, "mkdir", "-p", container_root],
        "DSH skills root creation",
    )
    with tempfile.TemporaryDirectory(prefix="wildclaw-dsh-skills-") as temp_dir:
        staging_root = Path(temp_dir)
        for bundle in bundles:
            staged_bundle = staging_root / bundle.normalized_name
            shutil.copytree(bundle.source, staged_bundle, symlinks=True)
            metadata, body = _parse_skill(staged_bundle / "SKILL.md")
            container_bundle_dir = f"{container_root}/{bundle.normalized_name}"
            (staged_bundle / "SKILL.md").write_text(
                _render_staged_skill(
                    metadata,
                    body,
                    bundle.normalized_name,
                    container_bundle_dir,
                ),
                encoding="utf-8",
            )
            _docker_run(
                ["docker", "exec", task_id, "mkdir", "-p", container_bundle_dir],
                f"DSH skill directory creation for {bundle.normalized_name}",
            )
            _docker_run(
                [
                    "docker",
                    "cp",
                    f"{staged_bundle}/.",
                    f"{task_id}:{container_bundle_dir}/",
                ],
                f"DSH skill install for {bundle.normalized_name}",
            )

    return [bundle.normalized_name for bundle in bundles]
