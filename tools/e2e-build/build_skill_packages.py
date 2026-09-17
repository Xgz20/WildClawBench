#!/usr/bin/env python3
"""Build and verify deterministic, independently installable E2E Skill ZIPs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tempfile
from typing import Sequence
import zipfile


BUILD_PLAN_SCHEMA = "wildclawbench.e2e-build-plan/v1"
SOURCE_CATALOG_SCHEMA = "wildclawbench.e2e-shared-source-catalog/v1"
BUNDLED_COMPONENTS_SCHEMA = "wildclawbench.e2e-bundled-components/v1"
BUILD_MANIFEST_SCHEMA = "wildclawbench.e2e-skill-build-manifest/v1"
CONTENT_HASH_ALGORITHM = "wildclawbench.skill-content-sha256/v1"
COMPONENT_HASH_ALGORITHM = "wildclawbench.component-content-sha256/v1"
ZIP_HASH_ALGORITHM = "sha256"
FIXED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
ARCHIVE_EXECUTABLE_SUFFIXES = frozenset({".command", ".sh"})
SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
GIT_REVISION_RE = re.compile(r"^[a-f0-9]{40}$")
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
JS_IMPORT_RE = re.compile(
    r"(?:\bfrom\s+|\bimport\s*\(\s*|\bimport\s+)[\"']([^\"']+)[\"']"
)
CODE_SUFFIXES = frozenset({".cjs", ".js", ".mjs"})
IGNORED_NAMES = frozenset({".DS_Store"})
IGNORED_PARTS = frozenset({"__pycache__", "node_modules"})
SOURCE_VENDOR_PREFIX = PurePosixPath("vendor/e2e-shared")
SKILL_SOURCE_EXCLUDED_PARTS = frozenset({"test", "tests"})
REPOSITORY_PATH_MARKERS = (b"/Users/", b"C:\\Users\\", b"tools/report/skills/")
EXPECTED_DEVELOPMENT_REPOSITORY_REFERENCES = {
    "prepare-web-e2e-workspaces": ["scripts/prepare_web_e2e_workspaces.py"],
}


class BuildError(ValueError):
    """Stable validation failure for build inputs or package contents."""


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BuildError(f"JSON_INVALID: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise BuildError(f"JSON_TOP_LEVEL_NOT_OBJECT: {path}")
    return value


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
            "utf-8"
        )
    )


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_ignored(relative: PurePosixPath) -> bool:
    return relative.name in IGNORED_NAMES or any(part in IGNORED_PARTS for part in relative.parts)


def regular_files(root: Path) -> list[Path]:
    if not root.is_dir() or root.is_symlink():
        raise BuildError(f"ROOT_NOT_DIRECTORY: {root}")
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        relative = PurePosixPath(path.relative_to(root).as_posix())
        if _is_ignored(relative):
            continue
        if path.is_symlink():
            raise BuildError(f"SYMLINK_NOT_ALLOWED: {relative}")
        if path.is_file():
            files.append(path)
    return files


def tree_content_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in regular_files(root):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(sha256_file(path)))
    return digest.hexdigest()


def git_revision(repo_root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    revision = completed.stdout.strip()
    if completed.returncode != 0 or not GIT_REVISION_RE.fullmatch(revision):
        raise BuildError("SOURCE_REVISION_UNAVAILABLE")
    return revision


def _validate_relative_path(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise BuildError(f"INVALID_RELATIVE_PATH: {field}")
    if "\\" in value or "\0" in value:
        raise BuildError(f"INVALID_RELATIVE_PATH: {field}: {value}")
    relative = PurePosixPath(value)
    if relative.is_absolute() or ".." in relative.parts or "." in relative.parts:
        raise BuildError(f"INVALID_RELATIVE_PATH: {field}: {value}")
    return relative.as_posix()


def _load_configuration(repo_root: Path) -> tuple[dict[str, dict], dict[str, dict]]:
    catalog_path = repo_root / "tools/report/e2e-shared/components.json"
    plan_path = repo_root / "tools/e2e-build/skill-bundles.json"
    catalog = read_json(catalog_path)
    plan = read_json(plan_path)
    if catalog.get("schema_version") != SOURCE_CATALOG_SCHEMA:
        raise BuildError("SOURCE_CATALOG_SCHEMA_MISMATCH")
    if plan.get("schema_version") != BUILD_PLAN_SCHEMA:
        raise BuildError("BUILD_PLAN_SCHEMA_MISMATCH")

    components: dict[str, dict] = {}
    for item in catalog.get("components", []):
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            raise BuildError("INVALID_COMPONENT_ENTRY")
        name = item["name"]
        if name in components:
            raise BuildError(f"DUPLICATE_COMPONENT: {name}")
        version = item.get("version")
        if not isinstance(version, str) or not SEMVER_RE.fullmatch(version):
            raise BuildError(f"INVALID_COMPONENT_VERSION: {name}")
        source_root = _validate_relative_path(item.get("source_root"), f"{name}.source_root")
        vendor_root = _validate_relative_path(item.get("vendor_root"), f"{name}.vendor_root")
        if not vendor_root.startswith(f"{SOURCE_VENDOR_PREFIX.as_posix()}/"):
            raise BuildError(f"INVALID_COMPONENT_VENDOR_ROOT: {name}")
        entrypoints = item.get("entrypoints")
        if not isinstance(entrypoints, list) or not entrypoints:
            raise BuildError(f"INVALID_COMPONENT_ENTRYPOINTS: {name}")
        normalized_entrypoints = [
            _validate_relative_path(entrypoint, f"{name}.entrypoints")
            for entrypoint in entrypoints
        ]
        component_root = repo_root / source_root
        for entrypoint in normalized_entrypoints:
            if not (component_root / entrypoint).is_file():
                raise BuildError(f"COMPONENT_ENTRYPOINT_MISSING: {name}: {entrypoint}")
        components[name] = {
            **item,
            "source_root": source_root,
            "vendor_root": vendor_root,
            "entrypoints": normalized_entrypoints,
        }

    skills: dict[str, dict] = {}
    for item in plan.get("skills", []):
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            raise BuildError("INVALID_SKILL_ENTRY")
        name = item["name"]
        if name in skills:
            raise BuildError(f"DUPLICATE_SKILL: {name}")
        source_root = _validate_relative_path(item.get("source_root"), f"{name}.source_root")
        source = repo_root / source_root
        if source.name != name or not (source / "SKILL.md").is_file():
            raise BuildError(f"SKILL_SOURCE_INVALID: {name}")
        scene = item.get("scene")
        if scene not in {"web-e2e", "general-e2e"}:
            raise BuildError(f"SKILL_SCENE_INVALID: {name}")
        requested_components = item.get("components")
        if not isinstance(requested_components, list) or len(requested_components) != len(set(requested_components)):
            raise BuildError(f"SKILL_COMPONENTS_INVALID: {name}")
        unknown = sorted(set(requested_components) - set(components))
        if unknown:
            raise BuildError(f"SKILL_COMPONENT_UNKNOWN: {name}: {unknown}")
        development_references = item.get("development_repository_references", [])
        if (
            not isinstance(development_references, list)
            or len(development_references) != len(set(development_references))
        ):
            raise BuildError(f"SKILL_DEVELOPMENT_REFERENCES_INVALID: {name}")
        normalized_development_references = [
            _validate_relative_path(
                reference,
                f"{name}.development_repository_references",
            )
            for reference in development_references
        ]
        expected_development_references = (
            EXPECTED_DEVELOPMENT_REPOSITORY_REFERENCES.get(name, [])
        )
        if normalized_development_references != expected_development_references:
            raise BuildError(
                f"SKILL_DEVELOPMENT_REFERENCES_UNAPPROVED: {name}: "
                f"{normalized_development_references}"
            )
        for reference in normalized_development_references:
            if not (source / reference).is_file():
                raise BuildError(
                    f"SKILL_DEVELOPMENT_REFERENCE_MISSING: {name}: {reference}"
                )
        skills[name] = {
            **item,
            "source_root": source_root,
            "components": requested_components,
            "development_repository_references": normalized_development_references,
        }

    discovered = {
        path.name
        for scene in ("web-e2e", "general-e2e")
        for path in (repo_root / "tools/report/skills" / scene).iterdir()
        if path.is_dir()
    }
    if set(skills) != discovered:
        raise BuildError(
            f"BUILD_PLAN_SKILL_SET_MISMATCH: missing={sorted(discovered - set(skills))}, "
            f"extra={sorted(set(skills) - discovered)}"
        )
    return components, skills


def _skill_version(source: Path, expected_name: str) -> str:
    metadata = read_json(source / "skill-metadata.json")
    if metadata.get("name") != expected_name:
        raise BuildError(f"SKILL_METADATA_NAME_MISMATCH: {expected_name}")
    version = metadata.get("version")
    if not isinstance(version, str) or not SEMVER_RE.fullmatch(version):
        raise BuildError(f"SKILL_METADATA_VERSION_INVALID: {expected_name}")
    return version


def _copy_regular_tree(
    source: Path,
    destination: Path,
    *,
    omit_source_vendor: bool = False,
    excluded_parts: frozenset[str] = frozenset(),
) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for path in regular_files(source):
        relative = PurePosixPath(path.relative_to(source).as_posix())
        if any(part in excluded_parts for part in relative.parts):
            continue
        if omit_source_vendor and (
            relative == SOURCE_VENDOR_PREFIX
            or relative.as_posix().startswith(f"{SOURCE_VENDOR_PREFIX.as_posix()}/")
        ):
            continue
        target = destination / relative.as_posix()
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def _component_manifest_row(
    repo_root: Path,
    component: dict,
    source_revision: str,
) -> dict:
    source_root = repo_root / component["source_root"]
    return {
        "name": component["name"],
        "version": component["version"],
        "source_revision": source_revision,
        "source_root": component["source_root"],
        "vendor_root": component["vendor_root"],
        "entrypoints": list(component["entrypoints"]),
        "content_hash_algorithm": COMPONENT_HASH_ALGORITHM,
        "content_sha256": tree_content_sha256(source_root),
    }


def stage_skill(
    repo_root: Path,
    destination: Path,
    skill: dict,
    components: dict[str, dict],
    source_revision: str,
) -> dict:
    source = repo_root / skill["source_root"]
    version = _skill_version(source, skill["name"])
    _copy_regular_tree(
        source,
        destination,
        omit_source_vendor=True,
        excluded_parts=SKILL_SOURCE_EXCLUDED_PARTS,
    )

    component_rows = []
    for name in skill["components"]:
        component = components[name]
        component_source = repo_root / component["source_root"]
        component_target = destination / component["vendor_root"]
        _copy_regular_tree(component_source, component_target)
        component_rows.append(_component_manifest_row(repo_root, component, source_revision))

    bundled_components = {
        "schema_version": BUNDLED_COMPONENTS_SCHEMA,
        "skill_name": skill["name"],
        "skill_version": version,
        "source_revision": source_revision,
        "components": component_rows,
        "development_repository_references": list(
            skill["development_repository_references"]
        ),
    }
    write_json(destination / "bundled-components.json", bundled_components)
    validate_dependency_closure(
        destination,
        allowed_repository_references=skill["development_repository_references"],
        forbidden_repository_roots=(repo_root,),
    )
    return bundled_components


def _resolve_relative_import(source_file: Path, specifier: str) -> Path | None:
    target = source_file.parent / specifier
    candidates = [target]
    if not target.suffix:
        candidates.extend(target.with_suffix(suffix) for suffix in (".js", ".mjs", ".json"))
        candidates.extend(target / f"index{suffix}" for suffix in (".js", ".mjs"))
    return next((candidate for candidate in candidates if candidate.is_file()), None)


def validate_dependency_closure(
    skill_root: Path,
    *,
    allowed_repository_references: Sequence[str] = (),
    forbidden_repository_roots: Sequence[Path] = (),
) -> dict:
    root = skill_root.resolve()
    allowed = {
        _validate_relative_path(item, "allowed_repository_references")
        for item in allowed_repository_references
    }
    used_repository_references: set[str] = set()
    path_markers = list(REPOSITORY_PATH_MARKERS)
    for repository_root in forbidden_repository_roots:
        resolved_root = repository_root.expanduser().resolve()
        for value in {str(resolved_root), resolved_root.as_posix()}:
            encoded = value.encode("utf-8")
            if encoded and encoded not in path_markers:
                path_markers.append(encoded)
    checked_imports = 0
    for source_file in regular_files(root):
        if source_file.suffix not in CODE_SUFFIXES:
            continue
        text = source_file.read_text(encoding="utf-8")
        for specifier in JS_IMPORT_RE.findall(text):
            if not specifier.startswith("."):
                continue
            checked_imports += 1
            resolved = _resolve_relative_import(source_file, specifier)
            if resolved is None:
                raise BuildError(
                    f"RELATIVE_IMPORT_MISSING: {source_file.relative_to(root).as_posix()}: {specifier}"
                )
            try:
                resolved.resolve().relative_to(root)
            except ValueError as exc:
                raise BuildError(
                    f"RELATIVE_IMPORT_ESCAPES_SKILL: {source_file.relative_to(root).as_posix()}: {specifier}"
                ) from exc

    for source_file in regular_files(root):
        if source_file.name == "bundled-components.json":
            continue
        if source_file.suffix not in CODE_SUFFIXES | {".py", ".ps1", ".sh", ".cmd"}:
            continue
        data = source_file.read_bytes()
        for marker in path_markers:
            if marker in data:
                relative = source_file.relative_to(root).as_posix()
                if marker == b"tools/report/skills/" and relative in allowed:
                    used_repository_references.add(relative)
                    continue
                raise BuildError(f"REPOSITORY_PATH_REFERENCE: {relative}: {marker.decode(errors='replace')}")
    unused = sorted(allowed - used_repository_references)
    if unused:
        raise BuildError(f"UNUSED_REPOSITORY_PATH_EXCEPTIONS: {unused}")
    return {
        "status": "PASS",
        "checked_relative_imports": checked_imports,
        "development_repository_references": sorted(used_repository_references),
    }


def _zip_info(archive_name: str, mode: int) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(archive_name, date_time=FIXED_ZIP_TIMESTAMP)
    info.create_system = 3
    # Stored entries avoid zlib-version drift between macOS and Windows.
    info.compress_type = zipfile.ZIP_STORED
    info.external_attr = ((stat.S_IFREG | mode) & 0xFFFF) << 16
    return info


def write_deterministic_zip(skill_root: Path, destination: Path) -> int:
    destination.parent.mkdir(parents=True, exist_ok=True)
    files = regular_files(skill_root)
    with zipfile.ZipFile(
        destination,
        "w",
        compression=zipfile.ZIP_STORED,
    ) as archive:
        for path in files:
            relative = path.relative_to(skill_root).as_posix()
            archived = PurePosixPath(skill_root.name, relative).as_posix()
            mode = 0o755 if path.suffix.lower() in ARCHIVE_EXECUTABLE_SUFFIXES else 0o644
            archive.writestr(_zip_info(archived, mode), path.read_bytes())
    return len(files)


def build_skill_package(
    repo_root: Path,
    output_dir: Path,
    skill_name: str,
    *,
    source_revision: str,
    replace: bool = False,
) -> dict:
    components, skills = _load_configuration(repo_root)
    try:
        skill = skills[skill_name]
    except KeyError as exc:
        raise BuildError(f"UNKNOWN_SKILL: {skill_name}") from exc
    source = repo_root / skill["source_root"]
    version = _skill_version(source, skill_name)
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / f"{skill_name}-skill-v{version}.zip"
    if destination.exists() and not replace:
        raise BuildError(f"OUTPUT_EXISTS: {destination}")

    with tempfile.TemporaryDirectory(prefix=f"e2e-build-{skill_name}-", dir=output_dir) as temp_dir:
        temp_root = Path(temp_dir)
        staged_skill = temp_root / skill_name
        component_manifest = stage_skill(
            repo_root,
            staged_skill,
            skill,
            components,
            source_revision,
        )
        content_sha256 = tree_content_sha256(staged_skill)
        temporary_zip = temp_root / destination.name
        file_count = write_deterministic_zip(staged_skill, temporary_zip)
        zip_sha256 = sha256_file(temporary_zip)
        if destination.exists():
            destination.unlink()
        os.replace(temporary_zip, destination)

    return {
        "name": skill_name,
        "scene": skill["scene"],
        "version": version,
        "source_revision": source_revision,
        "archive": destination.name,
        "file_count": file_count,
        "content_hash_algorithm": CONTENT_HASH_ALGORITHM,
        "content_sha256": content_sha256,
        "zip_hash_algorithm": ZIP_HASH_ALGORITHM,
        "zip_sha256": zip_sha256,
        "components": component_manifest["components"],
        "development_repository_references": component_manifest[
            "development_repository_references"
        ],
    }


def build_skill_packages(
    repo_root: Path,
    output_dir: Path,
    *,
    skill_names: Sequence[str] | None = None,
    source_revision: str | None = None,
    replace: bool = False,
) -> dict:
    _, skills = _load_configuration(repo_root)
    selected = list(skill_names) if skill_names else list(skills)
    if len(selected) != len(set(selected)):
        raise BuildError("DUPLICATE_SKILL_SELECTION")
    unknown = sorted(set(selected) - set(skills))
    if unknown:
        raise BuildError(f"UNKNOWN_SKILLS: {unknown}")
    revision = source_revision or git_revision(repo_root)
    if not isinstance(revision, str) or not GIT_REVISION_RE.fullmatch(revision):
        raise BuildError("SOURCE_REVISION_INVALID")

    rows = [
        build_skill_package(
            repo_root,
            output_dir,
            name,
            source_revision=revision,
            replace=replace,
        )
        for name in selected
    ]
    manifest = {
        "schema_version": BUILD_MANIFEST_SCHEMA,
        "source_revision": revision,
        "skill_count": len(rows),
        "skills": rows,
    }
    manifest_path = output_dir / "skills-build-manifest.json"
    if manifest_path.exists() and not replace:
        raise BuildError(f"OUTPUT_EXISTS: {manifest_path}")
    write_json(manifest_path, manifest)
    return manifest


def _safe_extract(archive_path: Path, destination: Path) -> Path:
    with zipfile.ZipFile(archive_path) as archive:
        roots: set[str] = set()
        names: set[str] = set()
        for info in archive.infolist():
            if "\\" in info.filename or "\0" in info.filename:
                raise BuildError(f"UNSAFE_ARCHIVE_PATH: {info.filename}")
            relative = PurePosixPath(info.filename)
            if relative.is_absolute() or ".." in relative.parts or not relative.parts:
                raise BuildError(f"UNSAFE_ARCHIVE_PATH: {info.filename}")
            normalized = relative.as_posix()
            if normalized in names:
                raise BuildError(f"ARCHIVE_DUPLICATE_PATH: {info.filename}")
            names.add(normalized)
            roots.add(relative.parts[0])
            file_type = (info.external_attr >> 16) & 0o170000
            if file_type == stat.S_IFLNK:
                raise BuildError(f"ARCHIVE_SYMLINK_NOT_ALLOWED: {info.filename}")
            if info.is_dir():
                continue
            target = destination.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(info))
            mode = (info.external_attr >> 16) & 0o777
            if mode:
                target.chmod(mode)
    if len(roots) != 1:
        raise BuildError(f"ARCHIVE_TOP_LEVEL_INVALID: {sorted(roots)}")
    skill_root = destination / next(iter(roots))
    if not skill_root.is_dir():
        raise BuildError("ARCHIVE_SKILL_ROOT_MISSING")
    return skill_root


def _verify_component_contents(
    skill_root: Path,
    manifest: dict,
    source_revision: str,
) -> None:
    components = manifest.get("components")
    if not isinstance(components, list):
        raise BuildError("BUNDLED_COMPONENTS_INVALID")
    seen: set[str] = set()
    for item in components:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            raise BuildError("BUNDLED_COMPONENT_ENTRY_INVALID")
        name = item["name"]
        if name in seen:
            raise BuildError(f"BUNDLED_COMPONENT_DUPLICATE: {name}")
        seen.add(name)
        version = item.get("version")
        if not isinstance(version, str) or not SEMVER_RE.fullmatch(version):
            raise BuildError(f"BUNDLED_COMPONENT_VERSION_INVALID: {name}")
        if item.get("source_revision") != source_revision:
            raise BuildError(f"BUNDLED_COMPONENT_REVISION_MISMATCH: {name}")
        _validate_relative_path(item.get("source_root"), f"{name}.source_root")
        vendor_root = _validate_relative_path(item.get("vendor_root"), f"{name}.vendor_root")
        if not vendor_root.startswith(f"{SOURCE_VENDOR_PREFIX.as_posix()}/"):
            raise BuildError(f"BUNDLED_COMPONENT_VENDOR_ROOT_INVALID: {name}")
        if item.get("content_hash_algorithm") != COMPONENT_HASH_ALGORITHM:
            raise BuildError(f"BUNDLED_COMPONENT_HASH_ALGORITHM_INVALID: {name}")
        content_sha256 = item.get("content_sha256")
        if not isinstance(content_sha256, str) or not SHA256_RE.fullmatch(content_sha256):
            raise BuildError(f"BUNDLED_COMPONENT_HASH_INVALID: {name}")
        component_root = skill_root / vendor_root
        if tree_content_sha256(component_root) != content_sha256:
            raise BuildError(f"BUNDLED_COMPONENT_CONTENT_MISMATCH: {name}")
        entrypoints = item.get("entrypoints")
        if (
            not isinstance(entrypoints, list)
            or not entrypoints
            or len(entrypoints) != len(set(entrypoints))
        ):
            raise BuildError(f"BUNDLED_COMPONENT_ENTRYPOINTS_INVALID: {name}")
        for entrypoint in entrypoints:
            relative = _validate_relative_path(entrypoint, f"{name}.entrypoints")
            if not (component_root / relative).is_file():
                raise BuildError(f"BUNDLED_COMPONENT_ENTRYPOINT_MISSING: {name}: {relative}")


def verify_skill_package(archive_path: Path, expected: dict | None = None) -> dict:
    archive_path = archive_path.resolve()
    if not archive_path.is_file():
        raise BuildError(f"ARCHIVE_MISSING: {archive_path}")
    zip_sha256 = sha256_file(archive_path)
    if expected is not None and zip_sha256 != expected.get("zip_sha256"):
        raise BuildError(f"ZIP_HASH_MISMATCH: {archive_path.name}")

    with tempfile.TemporaryDirectory(prefix="e2e-verify-") as temp_dir:
        skill_root = _safe_extract(archive_path, Path(temp_dir))
        bundled = read_json(skill_root / "bundled-components.json")
        if bundled.get("schema_version") != BUNDLED_COMPONENTS_SCHEMA:
            raise BuildError("BUNDLED_COMPONENTS_SCHEMA_MISMATCH")
        if bundled.get("skill_name") != skill_root.name:
            raise BuildError("BUNDLED_COMPONENTS_SKILL_MISMATCH")
        source_revision = bundled.get("source_revision")
        if not isinstance(source_revision, str) or not GIT_REVISION_RE.fullmatch(
            source_revision
        ):
            raise BuildError("BUNDLED_COMPONENTS_REVISION_INVALID")
        metadata = read_json(skill_root / "skill-metadata.json")
        if metadata.get("name") != skill_root.name or metadata.get("version") != bundled.get("skill_version"):
            raise BuildError("BUNDLED_COMPONENTS_METADATA_MISMATCH")
        _verify_component_contents(skill_root, bundled, source_revision)
        development_references = bundled.get("development_repository_references")
        if not isinstance(development_references, list):
            raise BuildError("BUNDLED_DEVELOPMENT_REFERENCES_INVALID")
        if development_references != EXPECTED_DEVELOPMENT_REPOSITORY_REFERENCES.get(
            skill_root.name,
            [],
        ):
            raise BuildError("BUNDLED_DEVELOPMENT_REFERENCES_UNAPPROVED")
        closure = validate_dependency_closure(
            skill_root,
            allowed_repository_references=development_references,
        )
        content_sha256 = tree_content_sha256(skill_root)
        if expected is not None:
            if expected.get("name") != skill_root.name:
                raise BuildError("BUILD_MANIFEST_SKILL_MISMATCH")
            if expected.get("content_sha256") != content_sha256:
                raise BuildError(f"CONTENT_HASH_MISMATCH: {skill_root.name}")
            if expected.get("version") != metadata.get("version"):
                raise BuildError(f"VERSION_MISMATCH: {skill_root.name}")
            if expected.get("source_revision") != source_revision:
                raise BuildError(f"SOURCE_REVISION_MISMATCH: {skill_root.name}")
            if expected.get("content_hash_algorithm") != CONTENT_HASH_ALGORITHM:
                raise BuildError(f"CONTENT_HASH_ALGORITHM_MISMATCH: {skill_root.name}")
            if expected.get("zip_hash_algorithm") != ZIP_HASH_ALGORITHM:
                raise BuildError(f"ZIP_HASH_ALGORITHM_MISMATCH: {skill_root.name}")
            if expected.get("components") != bundled.get("components"):
                raise BuildError(f"COMPONENT_MANIFEST_MISMATCH: {skill_root.name}")
            if expected.get("development_repository_references", []) != development_references:
                raise BuildError(
                    f"DEVELOPMENT_REFERENCE_MANIFEST_MISMATCH: {skill_root.name}"
                )
        file_count = len(regular_files(skill_root))
        if expected is not None and expected.get("file_count") != file_count:
            raise BuildError(f"FILE_COUNT_MISMATCH: {skill_root.name}")
    return {
        "status": "PASS",
        "name": bundled["skill_name"],
        "version": bundled["skill_version"],
        "archive": archive_path.name,
        "file_count": file_count,
        "content_sha256": content_sha256,
        "zip_sha256": zip_sha256,
        "checked_relative_imports": closure["checked_relative_imports"],
        "development_repository_references": closure[
            "development_repository_references"
        ],
    }


def verify_build_manifest(manifest_path: Path, package_dir: Path | None = None) -> dict:
    manifest = read_json(manifest_path)
    if manifest.get("schema_version") != BUILD_MANIFEST_SCHEMA:
        raise BuildError("BUILD_MANIFEST_SCHEMA_MISMATCH")
    rows = manifest.get("skills")
    if not isinstance(rows, list) or manifest.get("skill_count") != len(rows):
        raise BuildError("BUILD_MANIFEST_SCOPE_INVALID")
    source_revision = manifest.get("source_revision")
    if not isinstance(source_revision, str) or not GIT_REVISION_RE.fullmatch(
        source_revision
    ):
        raise BuildError("BUILD_MANIFEST_REVISION_INVALID")
    root = package_dir.resolve() if package_dir else manifest_path.resolve().parent
    results = []
    names: set[str] = set()
    archives: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise BuildError("BUILD_MANIFEST_ENTRY_INVALID")
        name = row.get("name")
        if not isinstance(name, str) or not name or name in names:
            raise BuildError(f"BUILD_MANIFEST_SKILL_INVALID: {name}")
        names.add(name)
        if row.get("source_revision") != source_revision:
            raise BuildError(f"BUILD_MANIFEST_REVISION_MISMATCH: {name}")
        archive = row.get("archive")
        if not isinstance(archive, str) or PurePosixPath(archive).name != archive:
            raise BuildError("BUILD_MANIFEST_ARCHIVE_INVALID")
        if archive in archives:
            raise BuildError(f"BUILD_MANIFEST_ARCHIVE_DUPLICATE: {archive}")
        archives.add(archive)
        results.append(verify_skill_package(root / archive, row))
    return {
        "schema_version": "wildclawbench.e2e-skill-build-verification/v1",
        "status": "PASS",
        "source_revision": source_revision,
        "skill_count": len(results),
        "skills": results,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="build deterministic Skill ZIPs")
    build.add_argument("--repo-root", type=Path, default=Path.cwd())
    build.add_argument("--output-dir", type=Path, required=True)
    build.add_argument("--skill", action="append", dest="skills")
    build.add_argument("--source-revision")
    build.add_argument("--replace", action="store_true")

    verify = subparsers.add_parser("verify", help="verify a build manifest and its ZIPs")
    verify.add_argument("--manifest", type=Path, required=True)
    verify.add_argument("--package-dir", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "build":
            result = build_skill_packages(
                args.repo_root.resolve(),
                args.output_dir.resolve(),
                skill_names=args.skills,
                source_revision=args.source_revision,
                replace=args.replace,
            )
        else:
            result = verify_build_manifest(args.manifest, args.package_dir)
    except (BuildError, OSError, zipfile.BadZipFile) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
