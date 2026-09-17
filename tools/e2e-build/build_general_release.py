#!/usr/bin/env python3
"""Build and verify a deterministic, checkout-independent General E2E release."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
from typing import Any, Sequence
import zipfile


CONTRACT_VERSION = "general-e2e-contract-v1"
BUNDLE_PROTOCOL = "general-e2e-package-v1"
CATALOG_SCHEMA_ID = "urn:wildclawbench:schema:general-e2e:release-catalog:v1"
CATALOG_DIGEST_ALGORITHM = "wildclawbench.release-catalog-sha256/v1"
RELEASE_MANIFEST_SCHEMA = "wildclawbench.general-e2e-release-manifest/v1"
FIXED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

GENERAL_SKILL_NAMES = (
    "prepare-general-e2e-workspaces",
    "execute-general-e2e",
    "collect-general-e2e",
    "orchestrate-general-e2e",
    "score-general-e2e",
    "report-general-e2e",
    "run-general-e2e",
)

SCHEMA_FILES = (
    "release-catalog-v1.schema.json",
    "package-manifest-v1.schema.json",
    "prepare-config-v1.schema.json",
)


class ReleaseError(ValueError):
    """Stable validation error for release construction or verification."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def pretty_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative(value: object, *, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value or "\0" in value:
        raise ReleaseError(f"INVALID_RELATIVE_PATH: {label}: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ReleaseError(f"INVALID_RELATIVE_PATH: {label}: {value!r}")
    return path


def _load_json_bytes(data: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ReleaseError(f"JSON_INVALID: {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise ReleaseError(f"JSON_TOP_LEVEL_NOT_OBJECT: {label}")
    return value


def _load_skill_builder(repo_root: Path):
    path = repo_root / "tools/e2e-build/build_skill_packages.py"
    spec = importlib.util.spec_from_file_location("wildclawbench_e2e_skill_builder", path)
    if spec is None or spec.loader is None:
        raise ReleaseError(f"SKILL_BUILDER_UNAVAILABLE: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=FIXED_ZIP_TIMESTAMP)
    info.create_system = 3
    info.compress_type = zipfile.ZIP_STORED
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    info.flag_bits |= 0x800
    return info


def _write_suite_zip(root: Path, release_id: str, destination: Path) -> None:
    files = sorted(path for path in root.rglob("*") if path.is_file())
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_STORED) as archive:
        for path in files:
            relative = path.relative_to(root).as_posix()
            archive.writestr(
                _zip_info(f"general-e2e-suite-{release_id}/{relative}"),
                path.read_bytes(),
            )


def _catalog_digest(catalog: dict[str, Any]) -> str:
    digest_input = dict(catalog)
    digest_input.pop("catalog_digest", None)
    return sha256_bytes(canonical_json_bytes(digest_input))


def _install_text(release_id: str) -> bytes:
    return (
        "# General E2E Skill Suite\n\n"
        f"Release: `{release_id}`\n\n"
        "本套件包含七个相互独立的 Skill ZIP、release catalog 与契约 schema。"
        "先校验 suite，再按 `release-catalog.json` 中的 SHA-256 安装所需 Skill。\n\n"
        "`prepare-general-e2e-workspaces` 可直接消费 dataset bundle 和本 suite；"
        "其余标记为 `interface_only` 的 Skill 仅提供已冻结接口，不得当作可运行实现。\n"
    ).encode("utf-8")


def _skill_metadata(repo_root: Path, name: str) -> dict[str, Any]:
    path = (
        repo_root
        / "tools/report/skills/general-e2e"
        / name
        / "skill-metadata.json"
    )
    return _load_json_bytes(path.read_bytes(), label=str(path))


def build_general_release(
    repo_root: Path,
    output_dir: Path,
    *,
    release_id: str,
    source_revision: str | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    output_dir = output_dir.resolve()
    if not ID_RE.fullmatch(release_id):
        raise ReleaseError(f"RELEASE_ID_INVALID: {release_id}")
    if output_dir.exists():
        raise ReleaseError(f"OUTPUT_EXISTS: {output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    builder = _load_skill_builder(repo_root)
    revision = source_revision or builder.git_revision(repo_root)
    if not isinstance(revision, str) or not REVISION_RE.fullmatch(revision):
        raise ReleaseError("SOURCE_REVISION_INVALID")

    schema_source = (
        repo_root
        / "tools/report/skills/general-e2e/prepare-general-e2e-workspaces/references"
    )
    with tempfile.TemporaryDirectory(
        prefix="general-e2e-release-", dir=output_dir.parent
    ) as temp_dir:
        staging = Path(temp_dir) / "release"
        skills_dir = staging / "skills"
        schemas_dir = staging / "schemas"
        skills_dir.mkdir(parents=True)
        schemas_dir.mkdir(parents=True)

        build_manifest = builder.build_skill_packages(
            repo_root,
            skills_dir,
            skill_names=GENERAL_SKILL_NAMES,
            source_revision=revision,
        )
        build_rows = {row["name"]: row for row in build_manifest["skills"]}

        schema_rows = []
        for name in SCHEMA_FILES:
            source = schema_source / name
            data = source.read_bytes()
            schema = _load_json_bytes(data, label=str(source))
            target = schemas_dir / name
            target.write_bytes(data)
            schema_rows.append(
                {
                    "schema_id": schema.get("$id"),
                    "path": f"schemas/{name}",
                    "sha256": sha256_bytes(data),
                    "size": len(data),
                }
            )

        catalog_rows = []
        for name in GENERAL_SKILL_NAMES:
            row = build_rows[name]
            metadata = _skill_metadata(repo_root, name)
            if (
                metadata.get("contract_version") != CONTRACT_VERSION
                or metadata.get("bundle_protocol") != BUNDLE_PROTOCOL
            ):
                raise ReleaseError(f"SKILL_CONTRACT_MISMATCH: {name}")
            catalog_rows.append(
                {
                    **row,
                    "archive": f"skills/{row['archive']}",
                    "contract_version": metadata["contract_version"],
                    "bundle_protocol": metadata["bundle_protocol"],
                    "implementation_status": metadata["implementation_status"],
                    "stages": metadata["stages"],
                }
            )

        catalog = {
            "schema_id": CATALOG_SCHEMA_ID,
            "schema_version": 1,
            "contract_version": CONTRACT_VERSION,
            "bundle_protocol": BUNDLE_PROTOCOL,
            "scene": "general-e2e",
            "release_id": release_id,
            "source_revision": revision,
            "catalog_digest_algorithm": CATALOG_DIGEST_ALGORITHM,
            "catalog_digest": "",
            "schemas": schema_rows,
            "skill_count": len(catalog_rows),
            "skills": catalog_rows,
        }
        catalog["catalog_digest"] = _catalog_digest(catalog)
        catalog_bytes = pretty_json_bytes(catalog)
        (staging / "release-catalog.json").write_bytes(catalog_bytes)
        (staging / "INSTALL.md").write_bytes(_install_text(release_id))

        suite_name = f"general-e2e-suite-{release_id}.zip"
        suite_temp = Path(temp_dir) / suite_name
        _write_suite_zip(staging, release_id, suite_temp)
        suite_sha256 = sha256_file(suite_temp)

        artifacts = []
        for path in sorted(item for item in staging.rglob("*") if item.is_file()):
            relative = path.relative_to(staging).as_posix()
            data = path.read_bytes()
            artifacts.append(
                {"path": relative, "sha256": sha256_bytes(data), "size": len(data)}
            )
        artifacts.append(
            {
                "path": suite_name,
                "sha256": suite_sha256,
                "size": suite_temp.stat().st_size,
            }
        )
        release_manifest = {
            "schema_version": RELEASE_MANIFEST_SCHEMA,
            "release_id": release_id,
            "source_revision": revision,
            "catalog_digest": catalog["catalog_digest"],
            "catalog_sha256": sha256_bytes(catalog_bytes),
            "suite": {
                "path": suite_name,
                "sha256": suite_sha256,
                "size": suite_temp.stat().st_size,
            },
            "artifacts": artifacts,
        }
        (staging / "general-e2e-release-manifest.json").write_bytes(
            pretty_json_bytes(release_manifest)
        )
        shutil.copy2(suite_temp, staging / suite_name)
        os.replace(staging, output_dir)

    verification = verify_release_directory(output_dir, builder=builder)
    return {
        "status": "PASS",
        "release_id": release_id,
        "source_revision": revision,
        "release_root": str(output_dir),
        "catalog_digest": catalog["catalog_digest"],
        "catalog_sha256": sha256_bytes(catalog_bytes),
        "suite_path": str(output_dir / suite_name),
        "suite_sha256": verification["suite_sha256"],
        "skill_count": verification["skill_count"],
    }


def _read_release_archive(archive_path: Path) -> tuple[str, dict[str, bytes]]:
    try:
        archive = zipfile.ZipFile(archive_path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ReleaseError(f"RELEASE_SUITE_INVALID: {archive_path}") from exc
    with archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        duplicates = sorted(name for name, count in Counter(names).items() if count > 1)
        if duplicates:
            raise ReleaseError(f"ARCHIVE_DUPLICATE_PATH: {duplicates}")
        roots: set[str] = set()
        members: dict[str, bytes] = {}
        for info in infos:
            relative = _safe_relative(info.filename.rstrip("/"), label="suite member")
            roots.add(relative.parts[0])
            mode = info.external_attr >> 16
            if info.is_dir() or stat.S_ISDIR(mode) or stat.S_ISLNK(mode):
                raise ReleaseError(f"SUITE_MEMBER_TYPE_INVALID: {info.filename}")
            if mode and not stat.S_ISREG(mode):
                raise ReleaseError(f"SUITE_MEMBER_TYPE_INVALID: {info.filename}")
            members[relative.as_posix()] = archive.read(info)
        if len(roots) != 1:
            raise ReleaseError(f"SUITE_ROOT_INVALID: {sorted(roots)}")
        root = next(iter(roots))
        prefix = f"{root}/"
        return root, {name[len(prefix):]: data for name, data in members.items()}


def _verify_catalog(catalog: dict[str, Any]) -> None:
    if (
        catalog.get("schema_id") != CATALOG_SCHEMA_ID
        or catalog.get("schema_version") != 1
        or catalog.get("contract_version") != CONTRACT_VERSION
        or catalog.get("bundle_protocol") != BUNDLE_PROTOCOL
        or catalog.get("scene") != "general-e2e"
    ):
        raise ReleaseError("RELEASE_CATALOG_CONTRACT_MISMATCH")
    if catalog.get("catalog_digest_algorithm") != CATALOG_DIGEST_ALGORITHM:
        raise ReleaseError("RELEASE_CATALOG_DIGEST_ALGORITHM_MISMATCH")
    digest = catalog.get("catalog_digest")
    if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
        raise ReleaseError("RELEASE_CATALOG_DIGEST_INVALID")
    if digest != _catalog_digest(catalog):
        raise ReleaseError("RELEASE_CATALOG_DIGEST_MISMATCH")
    if not ID_RE.fullmatch(str(catalog.get("release_id") or "")):
        raise ReleaseError("RELEASE_ID_INVALID")
    if not REVISION_RE.fullmatch(str(catalog.get("source_revision") or "")):
        raise ReleaseError("SOURCE_REVISION_INVALID")
    skills = catalog.get("skills")
    if not isinstance(skills, list) or catalog.get("skill_count") != len(skills):
        raise ReleaseError("RELEASE_SKILL_SCOPE_INVALID")
    if tuple(row.get("name") for row in skills if isinstance(row, dict)) != GENERAL_SKILL_NAMES:
        raise ReleaseError("RELEASE_SKILL_ORDER_INVALID")
    schemas = catalog.get("schemas")
    if not isinstance(schemas, list) or len(schemas) != len(SCHEMA_FILES):
        raise ReleaseError("RELEASE_SCHEMA_SCOPE_INVALID")


def verify_release_suite(
    archive_path: Path,
    *,
    builder=None,
) -> dict[str, Any]:
    archive_path = archive_path.resolve()
    root, members = _read_release_archive(archive_path)
    try:
        catalog_bytes = members["release-catalog.json"]
        members["INSTALL.md"]
        build_manifest_bytes = members["skills/skills-build-manifest.json"]
    except KeyError as exc:
        raise ReleaseError(f"SUITE_REQUIRED_MEMBER_MISSING: {exc.args[0]}") from exc
    catalog = _load_json_bytes(catalog_bytes, label="release-catalog.json")
    _verify_catalog(catalog)
    expected_root = f"general-e2e-suite-{catalog['release_id']}"
    if root != expected_root:
        raise ReleaseError(f"SUITE_ROOT_MISMATCH: expected={expected_root}, actual={root}")

    expected_members = {"release-catalog.json", "INSTALL.md", "skills/skills-build-manifest.json"}
    for row in catalog["schemas"]:
        if not isinstance(row, dict):
            raise ReleaseError("RELEASE_SCHEMA_ENTRY_INVALID")
        relative = _safe_relative(row.get("path"), label="schema path").as_posix()
        expected_members.add(relative)
        try:
            data = members[relative]
        except KeyError as exc:
            raise ReleaseError(f"RELEASE_SCHEMA_MISSING: {relative}") from exc
        if row.get("sha256") != sha256_bytes(data) or row.get("size") != len(data):
            raise ReleaseError(f"RELEASE_SCHEMA_DIGEST_MISMATCH: {relative}")
        schema = _load_json_bytes(data, label=relative)
        if schema.get("$id") != row.get("schema_id"):
            raise ReleaseError(f"RELEASE_SCHEMA_ID_MISMATCH: {relative}")

    build_manifest = _load_json_bytes(
        build_manifest_bytes, label="skills/skills-build-manifest.json"
    )
    build_rows = build_manifest.get("skills")
    if (
        build_manifest.get("source_revision") != catalog["source_revision"]
        or not isinstance(build_rows, list)
        or build_manifest.get("skill_count") != len(build_rows)
    ):
        raise ReleaseError("SKILL_BUILD_MANIFEST_MISMATCH")
    build_by_name = {
        row.get("name"): row for row in build_rows if isinstance(row, dict)
    }
    if set(build_by_name) != set(GENERAL_SKILL_NAMES):
        raise ReleaseError("SKILL_BUILD_SCOPE_MISMATCH")

    if builder is None:
        # Verification from the release builder itself; installed prepare has its own
        # source-independent verifier and does not import this module.
        repo_root = Path(__file__).resolve().parents[2]
        builder = _load_skill_builder(repo_root)
    verified_skills = []
    with tempfile.TemporaryDirectory(prefix="general-e2e-release-verify-") as temp_dir:
        temp_root = Path(temp_dir)
        for row in catalog["skills"]:
            name = row["name"]
            relative = _safe_relative(row.get("archive"), label=f"{name}.archive").as_posix()
            expected_members.add(relative)
            try:
                data = members[relative]
            except KeyError as exc:
                raise ReleaseError(f"SKILL_ARCHIVE_MISSING: {name}") from exc
            if row.get("zip_sha256") != sha256_bytes(data):
                raise ReleaseError(f"SKILL_ARCHIVE_DIGEST_MISMATCH: {name}")
            build_row = build_by_name[name]
            comparable = {
                key: row.get(key)
                for key in build_row
            }
            comparable["archive"] = PurePosixPath(relative).name
            if comparable != build_row:
                raise ReleaseError(f"SKILL_CATALOG_BUILD_MISMATCH: {name}")
            nested = temp_root / PurePosixPath(relative).name
            nested.write_bytes(data)
            verification = builder.verify_skill_package(nested, row)
            verified_skills.append(
                {"name": name, "version": row["version"], "status": verification["status"]}
            )

    unexpected = sorted(set(members) - expected_members)
    missing = sorted(expected_members - set(members))
    if unexpected or missing:
        raise ReleaseError(
            f"SUITE_MEMBER_SET_MISMATCH: unexpected={unexpected}, missing={missing}"
        )
    return {
        "status": "PASS",
        "release_id": catalog["release_id"],
        "source_revision": catalog["source_revision"],
        "catalog": catalog,
        "catalog_sha256": sha256_bytes(catalog_bytes),
        "suite_path": str(archive_path),
        "suite_sha256": sha256_file(archive_path),
        "skill_count": len(verified_skills),
        "skills": verified_skills,
    }


def verify_release_directory(
    release_root: Path,
    *,
    builder=None,
) -> dict[str, Any]:
    release_root = release_root.resolve()
    if not release_root.is_dir() or release_root.is_symlink():
        raise ReleaseError(f"RELEASE_ROOT_INVALID: {release_root}")
    for path in release_root.rglob("*"):
        if path.is_symlink():
            raise ReleaseError(
                f"RELEASE_FILESYSTEM_SYMLINK_NOT_ALLOWED: "
                f"{path.relative_to(release_root).as_posix()}"
            )
    manifest_path = release_root / "general-e2e-release-manifest.json"
    manifest = _load_json_bytes(manifest_path.read_bytes(), label=str(manifest_path))
    if manifest.get("schema_version") != RELEASE_MANIFEST_SCHEMA:
        raise ReleaseError("RELEASE_MANIFEST_SCHEMA_MISMATCH")
    release_id = str(manifest.get("release_id") or "")
    if not ID_RE.fullmatch(release_id):
        raise ReleaseError("RELEASE_MANIFEST_ID_INVALID")
    suite = manifest.get("suite")
    artifacts = manifest.get("artifacts")
    if not isinstance(suite, dict) or not isinstance(artifacts, list):
        raise ReleaseError("RELEASE_MANIFEST_SCOPE_INVALID")
    suite_relative = _safe_relative(suite.get("path"), label="release suite").as_posix()
    suite_path = release_root / suite_relative
    if (
        suite.get("sha256") != sha256_file(suite_path)
        or suite.get("size") != suite_path.stat().st_size
    ):
        raise ReleaseError("RELEASE_SUITE_DIGEST_MISMATCH")
    verification = verify_release_suite(suite_path, builder=builder)
    if verification["release_id"] != release_id:
        raise ReleaseError("RELEASE_SUITE_ID_MISMATCH")

    catalog_path = release_root / "release-catalog.json"
    catalog_bytes = catalog_path.read_bytes()
    if (
        manifest.get("catalog_digest") != verification["catalog"]["catalog_digest"]
        or manifest.get("catalog_sha256") != sha256_bytes(catalog_bytes)
        or catalog_bytes
        != pretty_json_bytes(verification["catalog"])
    ):
        raise ReleaseError("RELEASE_CATALOG_LOCK_MISMATCH")

    artifact_paths: list[str] = []
    for row in artifacts:
        if not isinstance(row, dict):
            raise ReleaseError("RELEASE_ARTIFACT_ENTRY_INVALID")
        relative = _safe_relative(row.get("path"), label="release artifact").as_posix()
        artifact_paths.append(relative)
        path = release_root / relative
        if not path.is_file() or path.is_symlink():
            raise ReleaseError(f"RELEASE_ARTIFACT_MISSING: {relative}")
        if row.get("sha256") != sha256_file(path) or row.get("size") != path.stat().st_size:
            raise ReleaseError(f"RELEASE_ARTIFACT_DIGEST_MISMATCH: {relative}")
    duplicates = sorted(
        path for path, count in Counter(artifact_paths).items() if count > 1
    )
    if duplicates:
        raise ReleaseError(f"RELEASE_ARTIFACT_DUPLICATE: {duplicates}")
    actual_files = {
        path.relative_to(release_root).as_posix()
        for path in release_root.rglob("*")
        if path.is_file()
    }
    expected_files = set(artifact_paths) | {"general-e2e-release-manifest.json"}
    unexpected = sorted(actual_files - expected_files)
    missing = sorted(expected_files - actual_files)
    if unexpected or missing:
        raise ReleaseError(
            f"RELEASE_FILE_SET_MISMATCH: unexpected={unexpected}, missing={missing}"
        )
    return {**verification, "release_root": str(release_root)}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="build a General E2E release")
    build.add_argument("--repo-root", type=Path, default=Path.cwd())
    build.add_argument("--output-dir", type=Path, required=True)
    build.add_argument("--release-id", required=True)
    build.add_argument("--source-revision")
    verify = subparsers.add_parser("verify", help="verify a General E2E release or suite")
    verify_input = verify.add_mutually_exclusive_group(required=True)
    verify_input.add_argument("--suite", type=Path)
    verify_input.add_argument("--release-root", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "build":
            result = build_general_release(
                args.repo_root,
                args.output_dir,
                release_id=args.release_id,
                source_revision=args.source_revision,
            )
        elif args.suite:
            result = verify_release_suite(args.suite)
        else:
            result = verify_release_directory(args.release_root)
    except (ReleaseError, OSError, zipfile.BadZipFile, ValueError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
