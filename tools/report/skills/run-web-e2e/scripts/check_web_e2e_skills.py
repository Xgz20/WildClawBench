#!/usr/bin/env python3
"""Compare installed Web E2E Skills with a batch skills manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path, PurePosixPath


MANIFEST_SCHEMA = "wildclawbench.web-e2e-skills-manifest/v1"
BATCH_SCHEMA = "wildclawbench.web-e2e-batch/v3"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def skill_files(root: Path) -> list[Path]:
    return [
        path for path in sorted(item for item in root.rglob("*") if item.is_file())
        if "__pycache__" not in path.parts
        and "node_modules" not in path.parts
        and path.suffix != ".pyc"
        and path.name != ".DS_Store"
    ]


def skill_content_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in skill_files(root):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(sha256_file(path)))
    return digest.hexdigest()


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON 顶层不是对象: {path}")
    return value


def resolve_archive(manifest_path: Path, raw: str) -> Path:
    relative = PurePosixPath(raw)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"Skill archive 路径不安全: {raw}")
    return manifest_path.parent.parent.joinpath(*relative.parts)


def find_installed_skill(name: str, roots: list[Path]) -> Path | None:
    for root in roots:
        candidate = root if root.name == name else root / name
        if candidate.is_dir() and (candidate / "SKILL.md").is_file():
            return candidate.resolve()
    return None


def inspect_skills(manifest_path: Path, roots: list[Path]) -> dict:
    manifest_path = manifest_path.expanduser().resolve()
    manifest = read_json(manifest_path)
    schema_version = manifest.get("schema_version")
    if schema_version == MANIFEST_SCHEMA:
        skills = manifest.get("skills")
    elif schema_version == BATCH_SCHEMA:
        skills = manifest.get("required_skills")
    else:
        raise ValueError(f"Skill manifest schema 不兼容: {manifest_path}")
    if not isinstance(skills, list) or not skills:
        raise ValueError(f"Skill manifest 缺少 skills: {manifest_path}")

    rows: list[dict] = []
    for expected in skills:
        name = str(expected.get("name") or "")
        version = str(expected.get("version") or "")
        content_sha256 = str(expected.get("content_sha256") or "")
        archive_sha256 = str(expected.get("sha256") or "")
        archive_raw = str(expected.get("archive") or "")
        if not name or not version or len(content_sha256) != 64:
            raise ValueError(f"Skill manifest 条目缺少名称、版本或内容 SHA-256: {expected}")
        if archive_raw and len(archive_sha256) != 64:
            raise ValueError(f"Skill manifest 条目缺少 ZIP SHA-256: {expected}")

        archive = resolve_archive(manifest_path, archive_raw) if archive_raw else None
        archive_status = "not_provided"
        if archive is not None:
            archive_status = "missing"
            if archive.is_file():
                archive_status = "valid" if sha256_file(archive) == archive_sha256 else "sha256_mismatch"

        installed = find_installed_skill(name, roots)
        row = {
            "name": name,
            "required_version": version,
            "required_content_sha256": content_sha256,
            "archive": str(archive) if archive else None,
            "archive_status": archive_status,
            "installed_path": str(installed) if installed else None,
            "installed_version": None,
            "installed_content_sha256": None,
            "status": "missing",
        }
        if installed is not None:
            metadata_path = installed / "skill-metadata.json"
            if not metadata_path.is_file():
                row["status"] = "metadata_missing"
            else:
                metadata = read_json(metadata_path)
                row["installed_version"] = metadata.get("version")
                if metadata.get("name") != name:
                    row["status"] = "metadata_name_mismatch"
                elif metadata.get("version") != version:
                    row["status"] = "version_mismatch"
                else:
                    installed_digest = skill_content_sha256(installed)
                    row["installed_content_sha256"] = installed_digest
                    row["status"] = "current" if installed_digest == content_sha256 else "content_mismatch"
        if archive_status == "sha256_mismatch":
            row["status"] = "archive_sha256_mismatch"
        rows.append(row)

    install_required = [row["name"] for row in rows if row["status"] != "current"]
    return {
        "schema_version": "wildclawbench.web-e2e-skill-installation-check/v1",
        "batch_id": manifest.get("batch_id"),
        "manifest": str(manifest_path),
        "all_current": not install_required,
        "install_required": install_required,
        "skills": rows,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="检查 Web E2E Skill 是否已安装为批次要求的版本和内容")
    parser.add_argument("--manifest", required=True, help="批次 packages/skills-manifest.json")
    parser.add_argument("--skills-root", action="append", default=[], help="Skill 安装根目录；可重复")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    roots = [Path(item).expanduser().resolve() for item in args.skills_root]
    if not roots:
        roots = [Path.home() / ".codex/skills", Path.home() / ".agents/skills"]
    try:
        result = inspect_skills(Path(args.manifest), roots)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, ensure_ascii=False, indent=2))
        raise SystemExit(2) from exc
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["all_current"]:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
