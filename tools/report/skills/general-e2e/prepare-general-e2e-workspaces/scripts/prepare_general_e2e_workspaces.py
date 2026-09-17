#!/usr/bin/env python3
"""Prepare and verify checkout-independent General E2E execution/scoring packages."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tempfile
from typing import Any, Iterable, Mapping, Sequence
import zipfile


CONTRACT_VERSION = "general-e2e-contract-v1"
BUNDLE_PROTOCOL = "general-e2e-package-v1"
CONFIG_SCHEMA_ID = "urn:wildclawbench:schema:general-e2e:prepare-config:v1"
CATALOG_SCHEMA_ID = "urn:wildclawbench:schema:general-e2e:release-catalog:v1"
PACKAGE_SCHEMA_ID = "urn:wildclawbench:schema:general-e2e:package-manifest:v1"
CATALOG_DIGEST_ALGORITHM = "wildclawbench.release-catalog-sha256/v1"
FIXED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
PROMPT_WORKSPACE = "/tmp_workspace"
PROMPT_WORKSPACE_RE = re.compile(re.escape(PROMPT_WORKSPACE) + r"(?![\w-])")

GENERAL_SKILL_NAMES = (
    "prepare-general-e2e-workspaces",
    "execute-general-e2e",
    "collect-general-e2e",
    "orchestrate-general-e2e",
    "score-general-e2e",
    "report-general-e2e",
    "run-general-e2e",
)
EXECUTION_SKILLS = (
    "execute-general-e2e",
    "collect-general-e2e",
    "run-general-e2e",
)
SCORING_SKILLS = (
    "orchestrate-general-e2e",
    "score-general-e2e",
    "run-general-e2e",
)
SCHEMA_PATHS = (
    "schemas/release-catalog-v1.schema.json",
    "schemas/package-manifest-v1.schema.json",
    "schemas/prepare-config-v1.schema.json",
)


class PrepareError(ValueError):
    """Stable, user-facing input or integrity failure."""


@dataclass(frozen=True)
class ZipEntry:
    name: str
    data: bytes
    kind: str = "file"
    mode: int = 0o644


@dataclass(frozen=True)
class ReadEntry:
    data: bytes
    kind: str
    mode: int


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
        raise PrepareError(f"INVALID_RELATIVE_PATH: {label}: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise PrepareError(f"INVALID_RELATIVE_PATH: {label}: {value!r}")
    return path


def _load_json_bytes(data: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PrepareError(f"JSON_INVALID: {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise PrepareError(f"JSON_TOP_LEVEL_NOT_OBJECT: {label}")
    return value


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return _load_json_bytes(path.read_bytes(), label=str(path))
    except OSError as exc:
        raise PrepareError(f"INPUT_UNREADABLE: {path}: {exc}") from exc


def _exact_keys(value: Mapping[str, Any], expected: set[str], *, label: str) -> None:
    actual = set(value)
    if actual != expected:
        raise PrepareError(
            f"CONFIG_KEYS_INVALID: {label}: missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )


def _require_id(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise PrepareError(f"CONFIG_ID_INVALID: {label}: {value!r}")
    return value


def _require_string(value: object, *, label: str, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not value:
        raise PrepareError(f"CONFIG_STRING_INVALID: {label}")
    return value


def _load_dataset_module():
    skill_root = Path(__file__).resolve().parents[1]
    vendored = skill_root / "vendor/e2e-shared/dataset-bundle/verify.py"
    if vendored.is_file():
        name = "wildclawbench_vendored_dataset_bundle_verify"
        spec = importlib.util.spec_from_file_location(name, vendored)
        if spec is None or spec.loader is None:
            raise PrepareError("DATASET_VERIFIER_UNAVAILABLE")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
    try:
        from eval_general_e2e.shared.dataset_bundle import verify as module
    except ImportError as exc:
        raise PrepareError("DATASET_VERIFIER_UNAVAILABLE") from exc
    return module


def _entry_type(info: zipfile.ZipInfo) -> str:
    mode = info.external_attr >> 16
    if info.is_dir() or stat.S_ISDIR(mode):
        return "directory"
    if stat.S_ISLNK(mode):
        return "symlink"
    if mode and not stat.S_ISREG(mode):
        return "unsupported"
    return "file"


def _read_zip(
    archive_path: Path,
    *,
    label: str,
    allow_symlinks: bool,
) -> tuple[str, dict[str, ReadEntry]]:
    try:
        archive = zipfile.ZipFile(archive_path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise PrepareError(f"{label}_INVALID: {archive_path}") from exc
    with archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        duplicates = sorted(name for name, count in Counter(names).items() if count > 1)
        if duplicates:
            raise PrepareError(f"ARCHIVE_DUPLICATE_PATH: {label}: {duplicates}")
        roots: set[str] = set()
        members: dict[str, ReadEntry] = {}
        for info in infos:
            relative = _safe_relative(info.filename.rstrip("/"), label=f"{label} member")
            roots.add(relative.parts[0])
            kind = _entry_type(info)
            if kind == "unsupported" or (kind == "symlink" and not allow_symlinks):
                raise PrepareError(f"ARCHIVE_MEMBER_TYPE_INVALID: {label}: {info.filename}")
            data = archive.read(info)
            if kind == "directory" and data:
                raise PrepareError(f"ARCHIVE_DIRECTORY_NOT_EMPTY: {label}: {info.filename}")
            mode = (info.external_attr >> 16) & 0o777
            members[relative.as_posix()] = ReadEntry(data, kind, mode)
        if len(roots) != 1:
            raise PrepareError(f"ARCHIVE_ROOT_INVALID: {label}: {sorted(roots)}")
        root = next(iter(roots))
        prefix = f"{root}/"
        stripped = {
            name[len(prefix):]: entry
            for name, entry in members.items()
            if name.startswith(prefix)
        }
        if len(stripped) != len(members):
            raise PrepareError(f"ARCHIVE_ROOT_INVALID: {label}")
        return root, stripped


def _catalog_digest(catalog: dict[str, Any]) -> str:
    digest_input = dict(catalog)
    digest_input.pop("catalog_digest", None)
    return sha256_bytes(canonical_json_bytes(digest_input))


def _tree_hash(entries: Iterable[tuple[str, bytes]]) -> str:
    digest = hashlib.sha256()
    for relative, data in sorted(entries):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(sha256_bytes(data)))
    return digest.hexdigest()


def _verify_skill_zip(data: bytes, row: Mapping[str, Any], temp_root: Path) -> None:
    name = str(row.get("name") or "")
    archive_path = temp_root / f"{name}.zip"
    archive_path.write_bytes(data)
    root, members = _read_zip(
        archive_path,
        label=f"SKILL_{name}",
        allow_symlinks=False,
    )
    if root != name:
        raise PrepareError(f"SKILL_ROOT_MISMATCH: {name}: {root}")
    if row.get("file_count") != len(members):
        raise PrepareError(f"SKILL_FILE_COUNT_MISMATCH: {name}")
    content_entries = [(path, entry.data) for path, entry in members.items()]
    if row.get("content_sha256") != _tree_hash(content_entries):
        raise PrepareError(f"SKILL_CONTENT_DIGEST_MISMATCH: {name}")
    try:
        metadata = _load_json_bytes(members["skill-metadata.json"].data, label=name)
        bundled = _load_json_bytes(members["bundled-components.json"].data, label=name)
    except KeyError as exc:
        raise PrepareError(f"SKILL_REQUIRED_MEMBER_MISSING: {name}: {exc.args[0]}") from exc
    if (
        metadata.get("name") != name
        or metadata.get("version") != row.get("version")
        or metadata.get("implementation_status") != row.get("implementation_status")
        or metadata.get("stages") != row.get("stages")
    ):
        raise PrepareError(f"SKILL_METADATA_MISMATCH: {name}")
    if (
        bundled.get("skill_name") != name
        or bundled.get("source_revision") != row.get("source_revision")
        or bundled.get("components") != row.get("components")
        or bundled.get("development_repository_references")
        != row.get("development_repository_references")
    ):
        raise PrepareError(f"SKILL_COMPONENT_MANIFEST_MISMATCH: {name}")
    for component in row.get("components", []):
        vendor_root = _safe_relative(
            component.get("vendor_root"), label=f"{name}.component.vendor_root"
        ).as_posix()
        prefix = f"{vendor_root}/"
        component_entries = [
            (path[len(prefix):], entry.data)
            for path, entry in members.items()
            if path.startswith(prefix)
        ]
        if not component_entries:
            raise PrepareError(f"SKILL_COMPONENT_MISSING: {name}: {vendor_root}")
        if component.get("content_sha256") != _tree_hash(component_entries):
            raise PrepareError(f"SKILL_COMPONENT_DIGEST_MISMATCH: {name}: {vendor_root}")


def verify_release_suite(suite_path: Path) -> dict[str, Any]:
    root, members = _read_zip(
        suite_path.resolve(), label="RELEASE_SUITE", allow_symlinks=False
    )
    try:
        catalog_bytes = members["release-catalog.json"].data
        members["INSTALL.md"]
        build_manifest_bytes = members["skills/skills-build-manifest.json"].data
    except KeyError as exc:
        raise PrepareError(f"RELEASE_REQUIRED_MEMBER_MISSING: {exc.args[0]}") from exc
    catalog = _load_json_bytes(catalog_bytes, label="release-catalog.json")
    if (
        catalog.get("schema_id") != CATALOG_SCHEMA_ID
        or catalog.get("schema_version") != 1
        or catalog.get("contract_version") != CONTRACT_VERSION
        or catalog.get("bundle_protocol") != BUNDLE_PROTOCOL
        or catalog.get("scene") != "general-e2e"
        or catalog.get("catalog_digest_algorithm") != CATALOG_DIGEST_ALGORITHM
    ):
        raise PrepareError("RELEASE_CATALOG_CONTRACT_MISMATCH")
    if catalog.get("catalog_digest") != _catalog_digest(catalog):
        raise PrepareError("RELEASE_CATALOG_DIGEST_MISMATCH")
    release_id = _require_id(catalog.get("release_id"), label="release_id")
    if root != f"general-e2e-suite-{release_id}":
        raise PrepareError("RELEASE_SUITE_ROOT_MISMATCH")
    skills = catalog.get("skills")
    if (
        not isinstance(skills, list)
        or catalog.get("skill_count") != len(skills)
        or tuple(row.get("name") for row in skills if isinstance(row, dict))
        != GENERAL_SKILL_NAMES
    ):
        raise PrepareError("RELEASE_SKILL_SCOPE_INVALID")
    schemas = catalog.get("schemas")
    if not isinstance(schemas, list) or len(schemas) != len(SCHEMA_PATHS):
        raise PrepareError("RELEASE_SCHEMA_SCOPE_INVALID")

    expected = {"release-catalog.json", "INSTALL.md", "skills/skills-build-manifest.json"}
    for row in schemas:
        if not isinstance(row, dict):
            raise PrepareError("RELEASE_SCHEMA_ENTRY_INVALID")
        path = _safe_relative(row.get("path"), label="release schema").as_posix()
        expected.add(path)
        try:
            data = members[path].data
        except KeyError as exc:
            raise PrepareError(f"RELEASE_SCHEMA_MISSING: {path}") from exc
        if row.get("sha256") != sha256_bytes(data) or row.get("size") != len(data):
            raise PrepareError(f"RELEASE_SCHEMA_DIGEST_MISMATCH: {path}")
        schema = _load_json_bytes(data, label=path)
        if schema.get("$id") != row.get("schema_id"):
            raise PrepareError(f"RELEASE_SCHEMA_ID_MISMATCH: {path}")

    build_manifest = _load_json_bytes(build_manifest_bytes, label="skills-build-manifest.json")
    build_rows = build_manifest.get("skills")
    if not isinstance(build_rows, list) or build_manifest.get("skill_count") != len(build_rows):
        raise PrepareError("SKILL_BUILD_MANIFEST_INVALID")
    by_name = {row.get("name"): row for row in build_rows if isinstance(row, dict)}
    if set(by_name) != set(GENERAL_SKILL_NAMES):
        raise PrepareError("SKILL_BUILD_SCOPE_INVALID")

    skill_archives: dict[str, bytes] = {}
    with tempfile.TemporaryDirectory(prefix="general-e2e-skill-verify-") as temp_dir:
        temp_root = Path(temp_dir)
        for row in skills:
            name = row["name"]
            archive_path = _safe_relative(row.get("archive"), label=f"{name}.archive").as_posix()
            expected.add(archive_path)
            try:
                data = members[archive_path].data
            except KeyError as exc:
                raise PrepareError(f"SKILL_ARCHIVE_MISSING: {name}") from exc
            if row.get("zip_sha256") != sha256_bytes(data):
                raise PrepareError(f"SKILL_ARCHIVE_DIGEST_MISMATCH: {name}")
            build_row = by_name[name]
            comparable = {key: row.get(key) for key in build_row}
            comparable["archive"] = PurePosixPath(archive_path).name
            if comparable != build_row:
                raise PrepareError(f"SKILL_CATALOG_BUILD_MISMATCH: {name}")
            _verify_skill_zip(data, row, temp_root)
            skill_archives[name] = data

    unexpected = sorted(set(members) - expected)
    missing = sorted(expected - set(members))
    if unexpected or missing:
        raise PrepareError(
            f"RELEASE_MEMBER_SET_MISMATCH: unexpected={unexpected}, missing={missing}"
        )
    return {
        "catalog": catalog,
        "catalog_bytes": catalog_bytes,
        "catalog_sha256": sha256_bytes(catalog_bytes),
        "suite_sha256": sha256_file(suite_path.resolve()),
        "skill_archives": skill_archives,
    }


def validate_config(config: dict[str, Any], dataset_manifest: Mapping[str, Any]) -> dict[str, Any]:
    _exact_keys(
        config,
        {
            "schema_id",
            "schema_version",
            "contract_version",
            "bundle_protocol",
            "batch_id",
            "task_ids",
            "units",
            "judge",
            "report",
        },
        label="root",
    )
    if (
        config.get("schema_id") != CONFIG_SCHEMA_ID
        or config.get("schema_version") != 1
        or config.get("contract_version") != CONTRACT_VERSION
        or config.get("bundle_protocol") != BUNDLE_PROTOCOL
    ):
        raise PrepareError("CONFIG_CONTRACT_MISMATCH")
    batch_id = _require_id(config.get("batch_id"), label="batch_id")
    dataset_tasks = [task["task_id"] for task in dataset_manifest["tasks"]]
    dataset_set = set(dataset_tasks)
    task_ids = config.get("task_ids")
    if not isinstance(task_ids, list) or not task_ids or len(task_ids) != len(set(task_ids)):
        raise PrepareError("CONFIG_TASK_SCOPE_INVALID")
    if any(not isinstance(task_id, str) or task_id not in dataset_set for task_id in task_ids):
        raise PrepareError("CONFIG_TASK_UNKNOWN")
    expected_order = [task_id for task_id in dataset_tasks if task_id in set(task_ids)]
    if task_ids != expected_order:
        raise PrepareError("CONFIG_TASK_ORDER_MISMATCH")

    raw_units = config.get("units")
    if not isinstance(raw_units, list) or not raw_units:
        raise PrepareError("CONFIG_UNITS_INVALID")
    units = []
    seen_units: set[str] = set()
    covered: set[str] = set()
    for index, unit in enumerate(raw_units):
        if not isinstance(unit, dict):
            raise PrepareError(f"CONFIG_UNIT_INVALID: {index}")
        _exact_keys(
            unit,
            {"unit_id", "task_ids", "harness", "model", "execution_mode"},
            label=f"units[{index}]",
        )
        unit_id = _require_id(unit.get("unit_id"), label=f"units[{index}].unit_id")
        if unit_id in seen_units:
            raise PrepareError(f"CONFIG_UNIT_DUPLICATE: {unit_id}")
        seen_units.add(unit_id)
        unit_tasks = unit.get("task_ids")
        if (
            not isinstance(unit_tasks, list)
            or not unit_tasks
            or len(unit_tasks) != len(set(unit_tasks))
            or any(task_id not in set(task_ids) for task_id in unit_tasks)
        ):
            raise PrepareError(f"CONFIG_UNIT_TASK_SCOPE_INVALID: {unit_id}")
        ordered = [task_id for task_id in task_ids if task_id in set(unit_tasks)]
        if unit_tasks != ordered:
            raise PrepareError(f"CONFIG_UNIT_TASK_ORDER_MISMATCH: {unit_id}")
        covered.update(unit_tasks)
        harness = unit.get("harness")
        model = unit.get("model")
        if not isinstance(harness, dict) or not isinstance(model, dict):
            raise PrepareError(f"CONFIG_UNIT_RUNTIME_INVALID: {unit_id}")
        _exact_keys(harness, {"id", "platform", "version"}, label=f"{unit_id}.harness")
        _exact_keys(model, {"requested_id", "reasoning_effort"}, label=f"{unit_id}.model")
        normalized = {
            "unit_id": unit_id,
            "task_ids": list(unit_tasks),
            "harness": {
                "id": _require_id(harness.get("id"), label=f"{unit_id}.harness.id"),
                "platform": _require_id(
                    harness.get("platform"), label=f"{unit_id}.harness.platform"
                ),
                "version": _require_string(
                    harness.get("version"), label=f"{unit_id}.harness.version", nullable=True
                ),
            },
            "model": {
                "requested_id": _require_string(
                    model.get("requested_id"), label=f"{unit_id}.model.requested_id"
                ),
                "reasoning_effort": _require_string(
                    model.get("reasoning_effort"),
                    label=f"{unit_id}.model.reasoning_effort",
                    nullable=True,
                ),
            },
            "execution_mode": unit.get("execution_mode"),
        }
        if normalized["execution_mode"] not in {"automatic", "human_assisted"}:
            raise PrepareError(f"CONFIG_EXECUTION_MODE_INVALID: {unit_id}")
        units.append(normalized)
    if covered != set(task_ids):
        raise PrepareError(f"CONFIG_TASKS_UNASSIGNED: {sorted(set(task_ids) - covered)}")

    judge = config.get("judge")
    report = config.get("report")
    if not isinstance(judge, dict) or not isinstance(report, dict):
        raise PrepareError("CONFIG_REPORT_OR_JUDGE_INVALID")
    _exact_keys(judge, {"protocol", "model", "reasoning_effort"}, label="judge")
    _exact_keys(report, {"title"}, label="report")
    if judge.get("protocol") not in {"codex-agent-judge-v1", "api-judge-v1"}:
        raise PrepareError("CONFIG_JUDGE_PROTOCOL_INVALID")
    return {
        "schema_id": CONFIG_SCHEMA_ID,
        "schema_version": 1,
        "contract_version": CONTRACT_VERSION,
        "bundle_protocol": BUNDLE_PROTOCOL,
        "batch_id": batch_id,
        "task_ids": list(task_ids),
        "units": units,
        "judge": {
            "protocol": judge["protocol"],
            "model": _require_string(judge.get("model"), label="judge.model"),
            "reasoning_effort": _require_string(
                judge.get("reasoning_effort"),
                label="judge.reasoning_effort",
                nullable=True,
            ),
        },
        "report": {"title": _require_string(report.get("title"), label="report.title")},
    }


def _zip_info(entry: ZipEntry) -> zipfile.ZipInfo:
    name = entry.name
    if entry.kind == "directory" and not name.endswith("/"):
        name += "/"
    info = zipfile.ZipInfo(name, date_time=FIXED_ZIP_TIMESTAMP)
    info.create_system = 3
    info.compress_type = zipfile.ZIP_STORED
    info.flag_bits |= 0x800
    if entry.kind == "directory":
        info.external_attr = (stat.S_IFDIR | entry.mode) << 16 | 0x10
    elif entry.kind == "symlink":
        info.external_attr = (stat.S_IFLNK | entry.mode) << 16
    else:
        info.external_attr = (stat.S_IFREG | entry.mode) << 16
    return info


def _write_zip(entries: Sequence[ZipEntry], destination: Path) -> None:
    names = [entry.name.rstrip("/") for entry in entries]
    if len(names) != len(set(names)):
        raise PrepareError("OUTPUT_MEMBER_DUPLICATE")
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_STORED) as archive:
        for entry in sorted(entries, key=lambda item: item.name):
            _safe_relative(entry.name.rstrip("/"), label="output member")
            archive.writestr(_zip_info(entry), entry.data)


def _dataset_member(
    archive: zipfile.ZipFile,
    dataset_root: str,
    relative: str,
) -> tuple[zipfile.ZipInfo, bytes]:
    name = f"{dataset_root}/{relative}"
    try:
        info = archive.getinfo(name)
    except KeyError as exc:
        raise PrepareError(f"DATASET_MEMBER_MISSING: {relative}") from exc
    return info, archive.read(info)


def _required_skill_rows(catalog: Mapping[str, Any], names: Sequence[str]) -> list[dict[str, Any]]:
    by_name = {row["name"]: row for row in catalog["skills"]}
    return [
        {
            "name": name,
            "version": by_name[name]["version"],
            "implementation_status": by_name[name]["implementation_status"],
            "content_sha256": by_name[name]["content_sha256"],
            "zip_sha256": by_name[name]["zip_sha256"],
        }
        for name in names
    ]


def map_prompt_workspace(prompt: str) -> tuple[str, list[dict[str, str]]]:
    mapped, count = PROMPT_WORKSPACE_RE.subn("./workspace", prompt)
    mapping = [{"from": PROMPT_WORKSPACE, "to": "./workspace"}] if count else []
    return mapped, mapping


def _package_identity(
    dataset: Mapping[str, Any],
    release: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    return dict(dataset), dict(release)


def _copy_execution_tree(
    archive: zipfile.ZipFile,
    dataset_root: str,
    unit_root: str,
    task: Mapping[str, Any],
) -> tuple[list[ZipEntry], list[dict[str, Any]]]:
    tree = task["materials"]["execution"]
    output_entries: list[ZipEntry] = []
    manifest_entries: list[dict[str, Any]] = []
    for item in tree["entries"]:
        relative = item["path"]
        kind = item["kind"]
        dataset_path = f"{tree['root']}/{relative}"
        suffix = "/" if kind == "directory" else ""
        info, data = _dataset_member(archive, dataset_root, dataset_path + suffix)
        if _entry_type(info) != kind:
            raise PrepareError(f"DATASET_MEMBER_TYPE_MISMATCH: {dataset_path}")
        target = f"{unit_root}/execution/tasks/{task['task_id']}/workspace/{relative}{suffix}"
        mode = int(str(item.get("mode") or "0644"), 8)
        output_entries.append(ZipEntry(target, data, kind, mode))
        manifest_entries.append(dict(item))
    return output_entries, manifest_entries


def _copy_scoring_tree(
    archive: zipfile.ZipFile,
    dataset_root: str,
    unit_root: str,
    task: Mapping[str, Any],
) -> tuple[list[ZipEntry], list[dict[str, Any]]]:
    tree = task["materials"]["private_scoring"]
    output_entries: list[ZipEntry] = []
    manifest_entries: list[dict[str, Any]] = []
    for item in tree["entries"]:
        relative = item["path"]
        kind = item["kind"]
        dataset_path = f"{tree['root']}/{relative}"
        suffix = "/" if kind == "directory" else ""
        info, data = _dataset_member(archive, dataset_root, dataset_path + suffix)
        if _entry_type(info) != kind:
            raise PrepareError(f"DATASET_MEMBER_TYPE_MISMATCH: {dataset_path}")
        target = f"{unit_root}/score/tasks/{task['task_id']}/private-scoring/gt/{relative}{suffix}"
        mode = int(str(item.get("mode") or "0644"), 8)
        output_entries.append(ZipEntry(target, data, kind, mode))
        manifest_entries.append(dict(item))
    return output_entries, manifest_entries


def _unit_packages(
    archive: zipfile.ZipFile,
    dataset_root: str,
    dataset_manifest: Mapping[str, Any],
    unit: Mapping[str, Any],
    batch_id: str,
    dataset_ref: Mapping[str, Any],
    release_ref: Mapping[str, Any],
    catalog: Mapping[str, Any],
    output_root: Path,
) -> tuple[Path, Path]:
    unit_id = unit["unit_id"]
    unit_root = f"{batch_id}__{unit_id}"
    task_by_id = {task["task_id"]: task for task in dataset_manifest["tasks"]}
    execution_entries = [
        ZipEntry(f"{unit_root}/evidence/", b"", "directory", 0o755),
        ZipEntry(f"{unit_root}/receipts/", b"", "directory", 0o755),
        ZipEntry(f"{unit_root}/score/", b"", "directory", 0o755),
        ZipEntry(f"{unit_root}/.general-e2e/", b"", "directory", 0o755),
    ]
    scoring_entries: list[ZipEntry] = []
    execution_tasks = []
    scoring_tasks = []

    for task_id in unit["task_ids"]:
        task = task_by_id[task_id]
        execution_contract_path = task["bundle"]["execution_contract_path"]
        _, execution_contract_bytes = _dataset_member(
            archive, dataset_root, execution_contract_path
        )
        execution_contract = _load_json_bytes(
            execution_contract_bytes, label=execution_contract_path
        )
        original_prompt = execution_contract.get("prompt")
        if not isinstance(original_prompt, str):
            raise PrepareError(f"DATASET_PROMPT_INVALID: {task_id}")
        mapped_prompt, prompt_mapping = map_prompt_workspace(original_prompt)
        prompt_path = f"execution/tasks/{task_id}/PROMPT.md"
        execution_entries.append(
            ZipEntry(f"{unit_root}/{prompt_path}", mapped_prompt.encode("utf-8"))
        )
        workspace_entries, workspace_manifest_entries = _copy_execution_tree(
            archive, dataset_root, unit_root, task
        )
        execution_entries.extend(workspace_entries)
        execution_tasks.append(
            {
                "task_id": task_id,
                "order": task["order"],
                "name": task["name"],
                "category": task["category"],
                "difficulty": task["difficulty"],
                "modality": task["modality"],
                "timeout_seconds": task["timeout_seconds"],
                "prompt": {
                    "path": prompt_path,
                    "source_sha256": task["digests"]["prompt_sha256"],
                    "original_sha256": sha256_bytes(original_prompt.encode("utf-8")),
                    "mapping": prompt_mapping,
                    "sent_sha256": sha256_bytes(mapped_prompt.encode("utf-8")),
                },
                "workspace": {
                    "path": f"execution/tasks/{task_id}/workspace",
                    "tree_sha256": task["digests"]["workspace_exec_sha256"],
                    "entries": workspace_manifest_entries,
                },
            }
        )

        scoring_contract_path = task["bundle"]["scoring_contract_path"]
        _, scoring_contract_bytes = _dataset_member(
            archive, dataset_root, scoring_contract_path
        )
        task_path = task["bundle"]["task_path"]
        _, task_bytes = _dataset_member(archive, dataset_root, task_path)
        private_root = f"score/tasks/{task_id}/private-scoring"
        scoring_entries.extend(
            [
                ZipEntry(f"{unit_root}/{private_root}/contract.json", scoring_contract_bytes),
                ZipEntry(f"{unit_root}/{private_root}/task.md", task_bytes),
            ]
        )
        gt_entries, gt_manifest_entries = _copy_scoring_tree(
            archive, dataset_root, unit_root, task
        )
        scoring_entries.extend(gt_entries)
        scoring_tasks.append(
            {
                "task_id": task_id,
                "order": task["order"],
                "grading_type": task["grading_type"],
                "grading_weights": task["grading_weights"],
                "contract": {
                    "path": f"{private_root}/contract.json",
                    "sha256": task["digests"]["scoring_contract_sha256"],
                },
                "task": {
                    "path": f"{private_root}/task.md",
                    "sha256": task["digests"]["task_sha256"],
                },
                "private_scoring": {
                    "path": f"{private_root}/gt",
                    "tree_sha256": task["digests"]["private_scoring_sha256"],
                    "entries": gt_manifest_entries,
                },
            }
        )

    dataset_value, release_value = _package_identity(dataset_ref, release_ref)
    execution_manifest = {
        "schema_id": PACKAGE_SCHEMA_ID,
        "schema_version": 1,
        "manifest_kind": "execution",
        "contract_version": CONTRACT_VERSION,
        "bundle_protocol": BUNDLE_PROTOCOL,
        "batch_id": batch_id,
        "unit_id": unit_id,
        "dataset": dataset_value,
        "release": release_value,
        "task_ids": list(unit["task_ids"]),
        "unit": dict(unit),
        "tasks": execution_tasks,
        "required_skills": _required_skill_rows(catalog, EXECUTION_SKILLS),
    }
    execution_entries.append(
        ZipEntry(f"{unit_root}/manifest.json", pretty_json_bytes(execution_manifest))
    )
    scoring_manifest = {
        "schema_id": PACKAGE_SCHEMA_ID,
        "schema_version": 1,
        "manifest_kind": "scoring",
        "contract_version": CONTRACT_VERSION,
        "bundle_protocol": BUNDLE_PROTOCOL,
        "batch_id": batch_id,
        "unit_id": unit_id,
        "dataset": dict(dataset_ref),
        "release": dict(release_ref),
        "task_ids": list(unit["task_ids"]),
        "unit": dict(unit),
        "tasks": scoring_tasks,
        "required_skills": _required_skill_rows(catalog, SCORING_SKILLS),
    }
    scoring_entries.append(
        ZipEntry(
            f"{unit_root}/.general-e2e/scoring-package-manifest.json",
            pretty_json_bytes(scoring_manifest),
        )
    )

    execution_path = output_root / f"{unit_root}__execution.zip"
    scoring_path = output_root / f"{unit_root}__scoring.zip"
    _write_zip(execution_entries, execution_path)
    _write_zip(scoring_entries, scoring_path)
    return execution_path, scoring_path


def prepare_batch(
    dataset_bundle: Path,
    release_suite: Path,
    config_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    dataset_module = _load_dataset_module()
    try:
        verified_dataset = dataset_module.load_verified_dataset_bundle(dataset_bundle)
    except (ValueError, OSError, zipfile.BadZipFile) as exc:
        raise PrepareError(f"DATASET_BUNDLE_INVALID: {exc}") from exc
    release = verify_release_suite(release_suite)
    config = validate_config(_load_json(config_path), verified_dataset.manifest)
    batch_id = config["batch_id"]
    output_dir = output_dir.resolve()
    batch_root = output_dir / batch_id
    if batch_root.exists():
        raise PrepareError(f"OUTPUT_EXISTS: {batch_root}")
    output_dir.mkdir(parents=True, exist_ok=True)

    dataset_ref = {
        "id": verified_dataset.manifest["dataset_id"],
        "digest": verified_dataset.manifest["dataset_digest"],
        "bundle_sha256": verified_dataset.bundle_sha256,
    }
    catalog = release["catalog"]
    release_ref = {
        "id": catalog["release_id"],
        "catalog_digest": catalog["catalog_digest"],
        "catalog_sha256": release["catalog_sha256"],
        "suite_sha256": release["suite_sha256"],
    }

    with tempfile.TemporaryDirectory(prefix=f"general-e2e-{batch_id}-", dir=output_dir) as temp_dir:
        staging = Path(temp_dir) / batch_id
        packages = staging / "packages"
        packages.mkdir(parents=True)
        (staging / "release-catalog.json").write_bytes(release["catalog_bytes"])

        skill_artifacts = []
        by_name = {row["name"]: row for row in catalog["skills"]}
        for name in GENERAL_SKILL_NAMES:
            row = by_name[name]
            archive_name = PurePosixPath(row["archive"]).name
            data = release["skill_archives"][name]
            (packages / archive_name).write_bytes(data)
            skill_artifacts.append(
                {
                    "name": name,
                    "path": f"packages/{archive_name}",
                    "sha256": sha256_bytes(data),
                    "size": len(data),
                }
            )

        artifacts = []
        with zipfile.ZipFile(verified_dataset.path) as dataset_archive:
            for unit in config["units"]:
                execution_path, scoring_path = _unit_packages(
                    dataset_archive,
                    verified_dataset.archive_root,
                    verified_dataset.manifest,
                    unit,
                    batch_id,
                    dataset_ref,
                    release_ref,
                    catalog,
                    packages,
                )
                for role, path in (("execution", execution_path), ("scoring", scoring_path)):
                    artifacts.append(
                        {
                            "unit_id": unit["unit_id"],
                            "role": role,
                            "path": f"packages/{path.name}",
                            "sha256": sha256_file(path),
                            "size": path.stat().st_size,
                        }
                    )

        report_config = {
            "schema_version": "wildclawbench.general-e2e-report-config/v1",
            "batch_id": batch_id,
            "dataset": dataset_ref,
            "release": release_ref,
            "judge": config["judge"],
            "report": config["report"],
            "units": config["units"],
        }
        (staging / "report-config.json").write_bytes(pretty_json_bytes(report_config))
        batch_manifest = {
            "schema_id": PACKAGE_SCHEMA_ID,
            "schema_version": 1,
            "manifest_kind": "batch",
            "contract_version": CONTRACT_VERSION,
            "bundle_protocol": BUNDLE_PROTOCOL,
            "batch_id": batch_id,
            "dataset": dataset_ref,
            "release": release_ref,
            "task_ids": config["task_ids"],
            "units": config["units"],
            "required_skills": _required_skill_rows(catalog, GENERAL_SKILL_NAMES),
            "skill_artifacts": skill_artifacts,
            "artifacts": artifacts,
        }
        (staging / "manifest.json").write_bytes(pretty_json_bytes(batch_manifest))
        os.replace(staging, batch_root)

    verification = verify_batch(batch_root)
    return {
        "status": "PASS",
        "batch_id": batch_id,
        "batch_root": str(batch_root),
        "dataset_id": dataset_ref["id"],
        "dataset_digest": dataset_ref["digest"],
        "release_id": release_ref["id"],
        "unit_count": len(config["units"]),
        "task_count": len(config["task_ids"]),
        "artifact_count": len(verification["artifacts"]),
    }


def _verify_execution_archive(path: Path, batch_manifest: Mapping[str, Any]) -> dict[str, Any]:
    root, members = _read_zip(path, label="EXECUTION_PACKAGE", allow_symlinks=True)
    try:
        manifest = _load_json_bytes(members["manifest.json"].data, label="execution manifest")
    except KeyError as exc:
        raise PrepareError("EXECUTION_MANIFEST_MISSING") from exc
    if manifest.get("manifest_kind") != "execution" or root != (
        f"{manifest.get('batch_id')}__{manifest.get('unit_id')}"
    ):
        raise PrepareError("EXECUTION_PACKAGE_IDENTITY_MISMATCH")
    if manifest.get("dataset") != batch_manifest.get("dataset") or manifest.get("release") != batch_manifest.get("release"):
        raise PrepareError("EXECUTION_PACKAGE_LOCK_MISMATCH")
    expected = {
        "manifest.json",
        "evidence",
        "receipts",
        "score",
        ".general-e2e",
    }
    for task in manifest.get("tasks", []):
        task_id = task["task_id"]
        prompt = task["prompt"]
        prompt_path = _safe_relative(prompt["path"], label="prompt path").as_posix()
        expected.add(prompt_path)
        data = members.get(prompt_path)
        if data is None or data.kind != "file" or prompt.get("sent_sha256") != sha256_bytes(data.data):
            raise PrepareError(f"EXECUTION_PROMPT_DIGEST_MISMATCH: {task_id}")
        try:
            sent_prompt = data.data.decode("utf-8")
        except UnicodeError as exc:
            raise PrepareError(f"EXECUTION_PROMPT_UTF8_INVALID: {task_id}") from exc
        if PROMPT_WORKSPACE_RE.search(sent_prompt):
            raise PrepareError(f"EXECUTION_PROMPT_MAPPING_INCOMPLETE: {task_id}")
        workspace = task["workspace"]
        workspace_root = _safe_relative(workspace["path"], label="workspace path").as_posix()
        tree_entries = []
        for entry in workspace["entries"]:
            suffix = "/" if entry["kind"] == "directory" else ""
            relative = f"{workspace_root}/{entry['path']}{suffix}"
            normalized = relative.rstrip("/")
            expected.add(normalized)
            actual = members.get(normalized)
            if actual is None or actual.kind != entry["kind"]:
                raise PrepareError(f"EXECUTION_WORKSPACE_MEMBER_MISMATCH: {task_id}: {relative}")
            if entry["kind"] != "directory":
                if entry.get("sha256") != sha256_bytes(actual.data) or entry.get("size") != len(actual.data):
                    raise PrepareError(f"EXECUTION_WORKSPACE_DIGEST_MISMATCH: {task_id}: {relative}")
            tree_entries.append(dict(entry))
        digest_input = {"algorithm": "wildclawbench.dataset-tree-sha256/v1", "entries": tree_entries}
        if workspace.get("tree_sha256") != sha256_bytes(canonical_json_bytes(digest_input)):
            raise PrepareError(f"EXECUTION_WORKSPACE_TREE_MISMATCH: {task_id}")
    forbidden = [
        name
        for name in members
        if "/private-scoring/" in f"/{name}/" or name.endswith("/task.md")
    ]
    if forbidden:
        raise PrepareError(f"EXECUTION_PRIVATE_MATERIAL_LEAK: {forbidden}")
    unexpected = sorted(set(members) - expected)
    missing = sorted(expected - set(members))
    if unexpected or missing:
        raise PrepareError(
            f"EXECUTION_MEMBER_SET_MISMATCH: unexpected={unexpected}, missing={missing}"
        )
    return manifest


def _verify_scoring_archive(path: Path, batch_manifest: Mapping[str, Any]) -> dict[str, Any]:
    root, members = _read_zip(path, label="SCORING_PACKAGE", allow_symlinks=True)
    manifest_path = ".general-e2e/scoring-package-manifest.json"
    try:
        manifest = _load_json_bytes(members[manifest_path].data, label="scoring manifest")
    except KeyError as exc:
        raise PrepareError("SCORING_MANIFEST_MISSING") from exc
    if manifest.get("manifest_kind") != "scoring" or root != (
        f"{manifest.get('batch_id')}__{manifest.get('unit_id')}"
    ):
        raise PrepareError("SCORING_PACKAGE_IDENTITY_MISMATCH")
    if manifest.get("dataset") != batch_manifest.get("dataset") or manifest.get("release") != batch_manifest.get("release"):
        raise PrepareError("SCORING_PACKAGE_LOCK_MISMATCH")
    expected = {manifest_path}
    for task in manifest.get("tasks", []):
        task_id = task["task_id"]
        for key in ("contract", "task"):
            item = task[key]
            relative = _safe_relative(item["path"], label=f"scoring {key}").as_posix()
            expected.add(relative)
            actual = members.get(relative)
            if actual is None or actual.kind != "file" or item.get("sha256") != sha256_bytes(actual.data):
                raise PrepareError(f"SCORING_MATERIAL_DIGEST_MISMATCH: {task_id}: {key}")
        private = task["private_scoring"]
        private_root = _safe_relative(private["path"], label="private scoring path").as_posix()
        tree_entries = []
        for entry in private["entries"]:
            suffix = "/" if entry["kind"] == "directory" else ""
            relative = f"{private_root}/{entry['path']}{suffix}"
            normalized = relative.rstrip("/")
            expected.add(normalized)
            actual = members.get(normalized)
            if actual is None or actual.kind != entry["kind"]:
                raise PrepareError(f"SCORING_GT_MEMBER_MISMATCH: {task_id}: {relative}")
            if entry["kind"] != "directory":
                if entry.get("sha256") != sha256_bytes(actual.data) or entry.get("size") != len(actual.data):
                    raise PrepareError(f"SCORING_GT_DIGEST_MISMATCH: {task_id}: {relative}")
            tree_entries.append(dict(entry))
        digest_input = {"algorithm": "wildclawbench.dataset-tree-sha256/v1", "entries": tree_entries}
        if private.get("tree_sha256") != sha256_bytes(canonical_json_bytes(digest_input)):
            raise PrepareError(f"SCORING_GT_TREE_MISMATCH: {task_id}")
    forbidden = [
        name for name in members if "/workspace/" in f"/{name}/" or name.endswith("/PROMPT.md")
    ]
    if forbidden:
        raise PrepareError(f"SCORING_EXECUTION_MATERIAL_LEAK: {forbidden}")
    unexpected = sorted(set(members) - expected)
    missing = sorted(expected - set(members))
    if unexpected or missing:
        raise PrepareError(
            f"SCORING_MEMBER_SET_MISMATCH: unexpected={unexpected}, missing={missing}"
        )
    return manifest


def verify_batch(batch_root: Path) -> dict[str, Any]:
    batch_root = batch_root.resolve()
    if not batch_root.is_dir() or batch_root.is_symlink():
        raise PrepareError(f"BATCH_ROOT_INVALID: {batch_root}")
    for path in batch_root.rglob("*"):
        if path.is_symlink():
            raise PrepareError(
                f"BATCH_FILESYSTEM_SYMLINK_NOT_ALLOWED: "
                f"{path.relative_to(batch_root).as_posix()}"
            )
    manifest = _load_json(batch_root / "manifest.json")
    if (
        manifest.get("schema_id") != PACKAGE_SCHEMA_ID
        or manifest.get("schema_version") != 1
        or manifest.get("manifest_kind") != "batch"
        or manifest.get("contract_version") != CONTRACT_VERSION
        or manifest.get("bundle_protocol") != BUNDLE_PROTOCOL
    ):
        raise PrepareError("BATCH_MANIFEST_CONTRACT_MISMATCH")
    if batch_root.name != manifest.get("batch_id"):
        raise PrepareError("BATCH_ROOT_IDENTITY_MISMATCH")
    task_ids = manifest.get("task_ids")
    units = manifest.get("units")
    if (
        not isinstance(task_ids, list)
        or not task_ids
        or len(task_ids) != len(set(task_ids))
        or not isinstance(units, list)
        or not units
    ):
        raise PrepareError("BATCH_SCOPE_INVALID")
    unit_ids = [unit.get("unit_id") for unit in units if isinstance(unit, dict)]
    if len(unit_ids) != len(units) or len(unit_ids) != len(set(unit_ids)):
        raise PrepareError("BATCH_UNIT_SCOPE_INVALID")
    units_by_id = {unit["unit_id"]: unit for unit in units}
    catalog_bytes = (batch_root / "release-catalog.json").read_bytes()
    catalog = _load_json_bytes(catalog_bytes, label="release-catalog.json")
    if (
        catalog.get("schema_id") != CATALOG_SCHEMA_ID
        or catalog.get("schema_version") != 1
        or catalog.get("contract_version") != CONTRACT_VERSION
        or catalog.get("bundle_protocol") != BUNDLE_PROTOCOL
        or catalog.get("catalog_digest_algorithm") != CATALOG_DIGEST_ALGORITHM
        or catalog.get("catalog_digest") != _catalog_digest(catalog)
    ):
        raise PrepareError("BATCH_CATALOG_DIGEST_MISMATCH")
    release = manifest.get("release") or {}
    if (
        release.get("id") != catalog.get("release_id")
        or release.get("catalog_digest") != catalog.get("catalog_digest")
        or release.get("catalog_sha256") != sha256_bytes(catalog_bytes)
    ):
        raise PrepareError("BATCH_RELEASE_LOCK_MISMATCH")
    report_config = _load_json(batch_root / "report-config.json")
    if (
        report_config.get("batch_id") != manifest.get("batch_id")
        or report_config.get("dataset") != manifest.get("dataset")
        or report_config.get("release") != manifest.get("release")
        or report_config.get("units") != units
    ):
        raise PrepareError("REPORT_CONFIG_BATCH_MISMATCH")

    expected_files = {"manifest.json", "report-config.json", "release-catalog.json"}
    skill_artifacts = manifest.get("skill_artifacts")
    if (
        not isinstance(skill_artifacts, list)
        or [row.get("name") for row in skill_artifacts if isinstance(row, dict)]
        != list(GENERAL_SKILL_NAMES)
    ):
        raise PrepareError("BATCH_SKILL_SCOPE_INVALID")
    for artifact in skill_artifacts:
        relative = _safe_relative(artifact.get("path"), label="skill artifact").as_posix()
        expected_files.add(relative)
        path = batch_root / relative
        if artifact.get("sha256") != sha256_file(path) or artifact.get("size") != path.stat().st_size:
            raise PrepareError(f"BATCH_SKILL_ARTIFACT_MISMATCH: {relative}")
    by_name = {row["name"]: row for row in catalog["skills"]}
    if tuple(by_name) != GENERAL_SKILL_NAMES:
        raise PrepareError("BATCH_CATALOG_SKILL_SCOPE_INVALID")
    with tempfile.TemporaryDirectory(prefix="general-e2e-batch-skill-verify-") as temp_dir:
        temp_root = Path(temp_dir)
        for artifact in skill_artifacts:
            row = by_name.get(artifact["name"])
            expected_path = f"packages/{PurePosixPath(row['archive']).name}" if row else None
            if (
                row is None
                or row.get("zip_sha256") != artifact.get("sha256")
                or artifact.get("path") != expected_path
            ):
                raise PrepareError(f"BATCH_SKILL_CATALOG_MISMATCH: {artifact['name']}")
            _verify_skill_zip(
                (batch_root / artifact["path"]).read_bytes(),
                row,
                temp_root,
            )

    verified_artifacts = []
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise PrepareError("BATCH_ARTIFACT_SCOPE_INVALID")
    artifact_keys = [
        (artifact.get("unit_id"), artifact.get("role"))
        for artifact in artifacts
        if isinstance(artifact, dict)
    ]
    expected_keys = [
        (unit_id, role)
        for unit_id in unit_ids
        for role in ("execution", "scoring")
    ]
    if artifact_keys != expected_keys:
        raise PrepareError(
            f"BATCH_ARTIFACT_SCOPE_INVALID: expected={expected_keys}, actual={artifact_keys}"
        )
    for artifact in artifacts:
        relative = _safe_relative(artifact.get("path"), label="batch artifact").as_posix()
        expected_files.add(relative)
        path = batch_root / relative
        if artifact.get("sha256") != sha256_file(path) or artifact.get("size") != path.stat().st_size:
            raise PrepareError(f"BATCH_ARTIFACT_DIGEST_MISMATCH: {relative}")
        if artifact.get("role") == "execution":
            package_manifest = _verify_execution_archive(path, manifest)
        elif artifact.get("role") == "scoring":
            package_manifest = _verify_scoring_archive(path, manifest)
        else:
            raise PrepareError(f"BATCH_ARTIFACT_ROLE_INVALID: {relative}")
        unit_id = artifact.get("unit_id")
        expected_name = f"{manifest['batch_id']}__{unit_id}__{artifact['role']}.zip"
        if (
            package_manifest.get("unit_id") != unit_id
            or package_manifest.get("unit") != units_by_id.get(unit_id)
            or package_manifest.get("task_ids") != units_by_id[unit_id].get("task_ids")
            or PurePosixPath(relative).name != expected_name
        ):
            raise PrepareError(f"BATCH_ARTIFACT_UNIT_MISMATCH: {relative}")
        verified_artifacts.append(
            {"unit_id": artifact["unit_id"], "role": artifact["role"], "path": relative}
        )

    actual_files = {
        path.relative_to(batch_root).as_posix()
        for path in batch_root.rglob("*")
        if path.is_file()
    }
    unexpected = sorted(actual_files - expected_files)
    missing = sorted(expected_files - actual_files)
    if unexpected or missing:
        raise PrepareError(
            f"BATCH_FILE_SET_MISMATCH: unexpected={unexpected}, missing={missing}"
        )
    return {
        "status": "PASS",
        "batch_id": manifest["batch_id"],
        "batch_root": str(batch_root),
        "task_count": len(manifest["task_ids"]),
        "unit_count": len(manifest["units"]),
        "artifacts": verified_artifacts,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare", help="prepare execution/scoring packages")
    prepare.add_argument("--dataset-bundle", type=Path, required=True)
    prepare.add_argument("--release-suite", type=Path, required=True)
    prepare.add_argument("--config", type=Path, required=True)
    prepare.add_argument("--output-dir", type=Path, required=True)
    release = subparsers.add_parser("verify-release", help="verify a release suite")
    release.add_argument("--release-suite", type=Path, required=True)
    batch = subparsers.add_parser("verify-batch", help="verify a prepared batch")
    batch.add_argument("--batch-root", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare_batch(
                args.dataset_bundle,
                args.release_suite,
                args.config,
                args.output_dir,
            )
        elif args.command == "verify-release":
            release = verify_release_suite(args.release_suite)
            result = {
                "status": "PASS",
                "release_id": release["catalog"]["release_id"],
                "catalog_digest": release["catalog"]["catalog_digest"],
                "catalog_sha256": release["catalog_sha256"],
                "suite_sha256": release["suite_sha256"],
                "skill_count": len(release["catalog"]["skills"]),
            }
        else:
            result = verify_batch(args.batch_root)
    except (PrepareError, OSError, ValueError, zipfile.BadZipFile) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
