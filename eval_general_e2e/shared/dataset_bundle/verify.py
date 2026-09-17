"""Verify a General E2E dataset ZIP without consulting a source checkout."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
from typing import Any, Mapping
import zipfile


SCHEMA_ID = "urn:wildclawbench:schema:general-e2e:dataset-manifest:v1"
SCHEMA_VERSION = 1
CONTRACT_VERSION = "general-e2e-contract-v1"
BUNDLE_PROTOCOL = "general-e2e-package-v1"
TREE_HASH_ALGORITHM = "wildclawbench.dataset-tree-sha256/v1"
DATASET_DIGEST_ALGORITHM = "wildclawbench.dataset-manifest-sha256/v1"


@dataclass(frozen=True)
class VerifiedDatasetBundle:
    path: Path
    archive_root: str
    manifest: dict[str, Any]
    bundle_sha256: str


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def safe_relative_path(value: str, *, label: str) -> PurePosixPath:
    if not value or "\\" in value or "\0" in value:
        raise ValueError(f"{label} must be a non-empty POSIX relative path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"{label} is unsafe: {value!r}")
    return path


def _validate_manifest(manifest: Mapping[str, Any]) -> None:
    if (
        manifest.get("schema_id") != SCHEMA_ID
        or manifest.get("schema_version") != SCHEMA_VERSION
    ):
        raise ValueError("unsupported dataset manifest schema")
    if manifest.get("contract_version") != CONTRACT_VERSION:
        raise ValueError("unsupported General E2E contract version")
    if manifest.get("bundle_protocol") != BUNDLE_PROTOCOL:
        raise ValueError("unsupported General E2E bundle protocol")
    if manifest.get("digest_algorithm") != DATASET_DIGEST_ALGORITHM:
        raise ValueError("unsupported dataset digest algorithm")
    dataset_id = str(manifest.get("dataset_id") or "")
    safe_relative_path(dataset_id, label="dataset_id")
    tasks = manifest.get("tasks")
    if not isinstance(tasks, list) or manifest.get("task_count") != len(tasks):
        raise ValueError("manifest task_count does not match tasks")
    task_ids = [
        str(task.get("task_id") or "") for task in tasks if isinstance(task, dict)
    ]
    if len(task_ids) != len(tasks) or len(set(task_ids)) != len(task_ids):
        raise ValueError("manifest tasks must be objects with unique task IDs")
    expected_digest = manifest.get("dataset_digest")
    digest_input = dict(manifest)
    digest_input.pop("dataset_digest", None)
    if expected_digest != canonical_sha256(digest_input):
        raise ValueError("dataset_digest mismatch")


def archive_member_type(info: zipfile.ZipInfo) -> str:
    mode = info.external_attr >> 16
    if info.is_dir() or stat.S_ISDIR(mode):
        return "directory"
    if stat.S_ISLNK(mode):
        return "symlink"
    if mode and not stat.S_ISREG(mode):
        return "unsupported"
    return "file"


def _verify_tree(
    archive: zipfile.ZipFile,
    archive_root: str,
    tree: Mapping[str, Any],
    expected_names: set[str],
) -> None:
    entries = tree.get("entries")
    if tree.get("algorithm") != TREE_HASH_ALGORITHM or not isinstance(entries, list):
        raise ValueError("unsupported or malformed material tree")
    digest_input = {"algorithm": TREE_HASH_ALGORITHM, "entries": entries}
    if tree.get("sha256") != canonical_sha256(digest_input):
        raise ValueError(f"material tree digest mismatch: {tree.get('root')}")
    root = str(tree.get("root") or "")
    safe_relative_path(root, label="material root")
    seen_entries: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("material entries must be objects")
        relative = str(entry.get("path") or "")
        safe_relative_path(relative, label="material entry path")
        if relative in seen_entries:
            raise ValueError(f"duplicate material entry: {root}/{relative}")
        seen_entries.add(relative)
        kind = str(entry.get("kind") or "")
        if kind not in {"directory", "file", "symlink"}:
            raise ValueError(f"unsupported material entry kind: {kind}")
        suffix = "/" if kind == "directory" else ""
        name = f"{archive_root}/{root}/{relative}{suffix}"
        expected_names.add(name)
        try:
            info = archive.getinfo(name)
        except KeyError as exc:
            raise ValueError(f"bundle material is missing: {name}") from exc
        if archive_member_type(info) != kind:
            raise ValueError(f"bundle material type mismatch: {name}")
        data = archive.read(info)
        if kind == "directory":
            if data:
                raise ValueError(f"directory bundle member is not empty: {name}")
            continue
        if entry.get("size") != len(data) or entry.get("sha256") != sha256_bytes(data):
            raise ValueError(f"bundle material digest mismatch: {name}")
        if kind == "symlink":
            target = data.decode("utf-8", errors="surrogateescape")
            if entry.get("link_target") != target:
                raise ValueError(f"bundle symlink target mismatch: {name}")


def load_verified_dataset_bundle(bundle_path: Path) -> VerifiedDatasetBundle:
    bundle_path = bundle_path.expanduser().resolve()
    try:
        archive = zipfile.ZipFile(bundle_path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError(f"invalid dataset bundle: {bundle_path}") from exc
    with archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            raise ValueError("dataset bundle contains duplicate members")
        for info in infos:
            safe_relative_path(info.filename.rstrip("/"), label="archive member")
            if archive_member_type(info) == "unsupported":
                raise ValueError(f"dataset bundle member type is unsupported: {info.filename}")
        manifest_names = [
            name
            for name in names
            if name.count("/") == 1 and name.endswith("/manifest.json")
        ]
        if len(manifest_names) != 1:
            raise ValueError(
                "dataset bundle must contain exactly one top-level manifest.json"
            )
        manifest_name = manifest_names[0]
        archive_root = manifest_name.rsplit("/", 1)[0]
        try:
            manifest = json.loads(archive.read(manifest_name).decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("dataset manifest is not valid UTF-8 JSON") from exc
        if not isinstance(manifest, dict):
            raise ValueError("dataset manifest must be an object")
        _validate_manifest(manifest)
        if archive_root != manifest["dataset_id"]:
            raise ValueError("archive root does not match dataset_id")

        expected_names = {manifest_name}
        schema = manifest.get("schema") or {}
        schema_path = str(schema.get("path") or "")
        safe_relative_path(schema_path, label="schema path")
        schema_name = f"{archive_root}/{schema_path}"
        expected_names.add(schema_name)
        if schema.get("sha256") != sha256_bytes(archive.read(schema_name)):
            raise ValueError("bundled schema digest mismatch")

        source = manifest.get("source") or {}
        registry_path = str(source.get("task_registry_path") or "")
        safe_relative_path(registry_path, label="task registry path")
        registry_name = f"{archive_root}/{registry_path}"
        expected_names.add(registry_name)
        if source.get("task_registry_sha256") != sha256_bytes(
            archive.read(registry_name)
        ):
            raise ValueError("bundled task registry digest mismatch")

        for task in manifest["tasks"]:
            task_id = task["task_id"]
            bundle = task.get("bundle") or {}
            digests = task.get("digests") or {}
            for path_key, digest_key in (
                ("task_path", "task_sha256"),
                ("execution_contract_path", "execution_contract_sha256"),
                ("scoring_contract_path", "scoring_contract_sha256"),
            ):
                relative = str(bundle.get(path_key) or "")
                safe_relative_path(relative, label=f"{task_id} {path_key}")
                name = f"{archive_root}/{relative}"
                expected_names.add(name)
                try:
                    data = archive.read(name)
                except KeyError as exc:
                    raise ValueError(f"bundle task material is missing: {name}") from exc
                if digests.get(digest_key) != sha256_bytes(data):
                    raise ValueError(f"{task_id} {digest_key} mismatch")
            try:
                execution_contract = json.loads(
                    archive.read(
                        f"{archive_root}/{bundle['execution_contract_path']}"
                    ).decode("utf-8")
                )
                scoring_contract = json.loads(
                    archive.read(
                        f"{archive_root}/{bundle['scoring_contract_path']}"
                    ).decode("utf-8")
                )
            except (KeyError, UnicodeError, json.JSONDecodeError) as exc:
                raise ValueError(f"task contract is invalid: {task_id}") from exc
            if (
                execution_contract.get("task_id") != task_id
                or scoring_contract.get("task_id") != task_id
            ):
                raise ValueError(f"task contract identity mismatch: {task_id}")
            if digests.get("prompt_sha256") != sha256_bytes(
                str(execution_contract.get("prompt") or "").encode("utf-8")
            ):
                raise ValueError(f"prompt digest mismatch: {task_id}")
            execution_tree = (task.get("materials") or {}).get("execution") or {}
            scoring_tree = (
                (task.get("materials") or {}).get("private_scoring") or {}
            )
            _verify_tree(archive, archive_root, execution_tree, expected_names)
            _verify_tree(archive, archive_root, scoring_tree, expected_names)
            if digests.get("workspace_exec_sha256") != execution_tree.get("sha256"):
                raise ValueError(f"workspace exec digest mismatch: {task_id}")
            if digests.get("private_scoring_sha256") != scoring_tree.get("sha256"):
                raise ValueError(f"private scoring digest mismatch: {task_id}")

        if set(names) != expected_names:
            unexpected = sorted(set(names) - expected_names)
            missing = sorted(expected_names - set(names))
            raise ValueError(
                f"bundle member set mismatch: unexpected={unexpected}, missing={missing}"
            )
    return VerifiedDatasetBundle(
        path=bundle_path,
        archive_root=archive_root,
        manifest=manifest,
        bundle_sha256=sha256_file(bundle_path),
    )


def verify_dataset_bundle(bundle_path: Path) -> dict[str, Any]:
    verified = load_verified_dataset_bundle(bundle_path)
    return {
        "dataset_id": verified.manifest["dataset_id"],
        "dataset_digest": verified.manifest["dataset_digest"],
        "task_count": verified.manifest["task_count"],
        "bundle_path": str(verified.path),
        "bundle_sha256": verified.bundle_sha256,
    }
