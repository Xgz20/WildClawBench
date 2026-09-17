"""Build and verify the frozen ``general-custom60-v1`` dataset bundle.

The build side reads WildClawBench task sources.  The verification side only
reads the produced ZIP, so consumers do not need a repository checkout.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

from eval_general_e2e.shared.dataset_bundle.verify import (
    BUNDLE_PROTOCOL,
    CONTRACT_VERSION,
    DATASET_DIGEST_ALGORITHM,
    SCHEMA_ID,
    SCHEMA_VERSION,
    TREE_HASH_ALGORITHM,
    _validate_manifest,
    canonical_sha256 as _canonical_sha256,
    safe_relative_path as _safe_relative_path,
    sha256_bytes as _sha256_bytes,
    sha256_file as _sha256_file,
    verify_dataset_bundle,
)


GENERATOR_VERSION = "eval_general_e2e.datasets.bundle/1"
FIXED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class DatasetDefinition:
    dataset_id: str
    created_at: str
    include_tags: tuple[str, ...]
    exclude_tags: tuple[str, ...]
    expected_task_count: int
    expected_category_counts: Mapping[str, int]
    expected_grading_type_counts: Mapping[str, int]
    expected_difficulty_counts: Mapping[str, int]
    expected_timeout_counts: Mapping[str, int]


DEFAULT_DEFINITION = DatasetDefinition(
    dataset_id="general-custom60-v1",
    created_at="2026-09-17T00:00:00+08:00",
    include_tags=("custom",),
    exclude_tags=("ppt", "web-site", "web-site-gen", "invalid"),
    expected_task_count=60,
    expected_category_counts={
        "01_Productivity_Flow": 10,
        "02_Code_Intelligence": 10,
        "03_Social_Interaction": 10,
        "04_Search_Retrieval": 10,
        "05_Creative_Synthesis": 10,
        "06_Safety_Alignment": 10,
    },
    expected_grading_type_counts={
        "automated": 19,
        "hybrid": 35,
        "llm_judge": 6,
    },
    expected_difficulty_counts={"L1": 15, "L2": 17, "L3": 18, "L4": 10},
    expected_timeout_counts={"300": 32, "600": 19, "900": 9},
)


@dataclass(frozen=True)
class BundleMember:
    path: str
    data: bytes
    kind: str = "file"
    mode: int = 0o644


def _module_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_manifest_path() -> Path:
    return Path(__file__).resolve().parent / "manifests/general-custom60-v1.json"


def default_schema_path() -> Path:
    return Path(__file__).resolve().parent / "schemas/dataset-manifest-v1.schema.json"


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def _normalized_tags(raw: Any) -> list[str]:
    if raw is None:
        values: Iterable[Any] = []
    elif isinstance(raw, str):
        values = raw.split(",")
    elif isinstance(raw, (list, tuple)):
        values = raw
    else:
        values = [raw]
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        tag = str(value).strip().lower()
        if tag and tag not in seen:
            result.append(tag)
            seen.add(tag)
    return result


def _within(path: Path, root: Path, *, label: str) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"{label} escapes repository root: {path}") from exc
    return resolved


def _load_yaml(text: str, *, label: str) -> Any:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - installation failure path
        raise RuntimeError("building a dataset bundle requires PyYAML") from exc
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML in {label}: {exc}") from exc


def _strip_codeblock(raw: str) -> str:
    value = raw.strip()
    match = re.search(r"```[^\n]*\n(.*?)\n```", value, re.DOTALL)
    if match:
        return match.group(1).strip()
    value = re.sub(r"^```[^\n]*\n?", "", value)
    return re.sub(r"\n?```$", "", value).strip()


def _parse_task_source(path: Path) -> tuple[dict[str, Any], dict[str, str], bytes]:
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", text, re.DOTALL)
    if not match:
        raise ValueError(f"YAML frontmatter not found: {path}")
    metadata = _load_yaml(match.group(1), label=str(path))
    if not isinstance(metadata, dict):
        raise ValueError(f"frontmatter must be a mapping: {path}")
    sections: dict[str, str] = {}
    current: Optional[str] = None
    lines: list[str] = []
    for line in match.group(2).split("\n"):
        heading = re.match(r"^##\s+(.+)$", line)
        if heading:
            if current is not None:
                sections[current] = "\n".join(lines).strip()
            current = heading.group(1).strip()
            lines = []
        else:
            lines.append(line)
    if current is not None:
        sections[current] = "\n".join(lines).strip()
    return metadata, sections, raw


def _normalized_mode(path: Path, kind: str) -> int:
    if kind == "directory":
        return 0o755
    if kind == "symlink":
        return 0o777
    return 0o755 if stat.S_IMODE(path.lstat().st_mode) & 0o111 else 0o644


def _tree_materials(root: Path, bundle_root: str) -> tuple[dict[str, Any], list[BundleMember]]:
    if not root.is_dir():
        raise ValueError(f"required material directory is missing: {root}")
    entries: list[dict[str, Any]] = []
    members: list[BundleMember] = []

    def visit(directory: Path) -> None:
        for child in sorted(directory.iterdir(), key=lambda item: item.name):
            relative = child.relative_to(root).as_posix()
            _safe_relative_path(relative, label="material path")
            if child.is_symlink():
                target = os.readlink(child)
                target_bytes = target.encode("utf-8", errors="surrogateescape")
                candidate = (child.parent / target).resolve(strict=False)
                try:
                    candidate.relative_to(root.resolve())
                except ValueError as exc:
                    raise ValueError(
                        f"material symlink escapes its root: {child} -> {target}"
                    ) from exc
                entry = {
                    "kind": "symlink",
                    "path": relative,
                    "mode": "0777",
                    "size": len(target_bytes),
                    "sha256": _sha256_bytes(target_bytes),
                    "link_target": target,
                }
                entries.append(entry)
                members.append(BundleMember(
                    path=f"{bundle_root}/{relative}",
                    data=target_bytes,
                    kind="symlink",
                    mode=0o777,
                ))
            elif child.is_dir():
                entries.append({
                    "kind": "directory",
                    "path": relative,
                    "mode": "0755",
                })
                members.append(BundleMember(
                    path=f"{bundle_root}/{relative}/",
                    data=b"",
                    kind="directory",
                    mode=0o755,
                ))
                visit(child)
            elif child.is_file():
                data = child.read_bytes()
                mode = _normalized_mode(child, "file")
                entries.append({
                    "kind": "file",
                    "path": relative,
                    "mode": f"{mode:04o}",
                    "size": len(data),
                    "sha256": _sha256_bytes(data),
                })
                members.append(BundleMember(
                    path=f"{bundle_root}/{relative}",
                    data=data,
                    kind="file",
                    mode=mode,
                ))
            else:
                raise ValueError(f"unsupported material entry: {child}")

    visit(root)
    tree = {
        "algorithm": TREE_HASH_ALGORITHM,
        "root": bundle_root,
        "entries": entries,
    }
    tree["sha256"] = _canonical_sha256({
        "algorithm": TREE_HASH_ALGORITHM,
        "entries": entries,
    })
    return tree, members


def _task_contracts(
    task_id: str,
    metadata: Mapping[str, Any],
    sections: Mapping[str, str],
    execution_tree: Mapping[str, Any],
    scoring_tree: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    execution = {
        "contract_version": 1,
        "task_id": task_id,
        "prompt": sections.get("Prompt", "").strip(),
        "env": _strip_codeblock(sections.get("Env", "")),
        "skills": _strip_codeblock(sections.get("Skills", "")),
        "warmup": _strip_codeblock(sections.get("Warmup", "")),
        "timeout_seconds": int(metadata.get("timeout_seconds", 120)),
        "modality": str(metadata.get("modality", "")).strip(),
        "workspace_exec_sha256": execution_tree["sha256"],
    }
    grading_weights = metadata.get("grading_weights") or {}
    if not isinstance(grading_weights, dict):
        raise ValueError(f"grading_weights must be a mapping: {task_id}")
    scoring = {
        "contract_version": 1,
        "task_id": task_id,
        "grading_type": str(metadata.get("grading_type", "")).strip(),
        "grading_weights": grading_weights,
        "expected_behavior": sections.get("Expected Behavior", "").strip(),
        "grading_criteria": sections.get("Grading Criteria", "").strip(),
        "automated_checks": _strip_codeblock(sections.get("Automated Checks", "")),
        "llm_judge_rubric": sections.get("LLM Judge Rubric", "").strip(),
        "judge_evidence": metadata.get("judge_evidence") or {},
        "private_scoring_sha256": scoring_tree["sha256"],
    }
    return execution, scoring


def _derive_source_revision(repo_root: Path) -> str:
    completed = subprocess.run(
        [
            "git",
            "log",
            "-1",
            "--format=%H",
            "--",
            "tasks/extension",
            "workspace/extension",
        ],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    revision = completed.stdout.strip()
    if completed.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError(
            "unable to derive source revision; pass source_revision explicitly"
        )
    return revision


def _assert_expected_statistics(
    statistics: Mapping[str, Any], definition: DatasetDefinition
) -> None:
    expected = {
        "task_count": definition.expected_task_count,
        "category_counts": dict(definition.expected_category_counts),
        "grading_type_counts": dict(definition.expected_grading_type_counts),
        "difficulty_counts": dict(definition.expected_difficulty_counts),
        "timeout_counts": dict(definition.expected_timeout_counts),
    }
    if dict(statistics) != expected:
        raise ValueError(
            "selected task statistics do not match the frozen dataset definition: "
            f"expected={expected!r}, actual={dict(statistics)!r}"
        )


def compile_dataset(
    repo_root: Path,
    *,
    definition: DatasetDefinition = DEFAULT_DEFINITION,
    source_revision: Optional[str] = None,
) -> tuple[dict[str, Any], list[BundleMember]]:
    """Compile source tasks into a manifest plus deterministic archive members."""
    repo_root = repo_root.resolve()
    tasks_root = repo_root / "tasks/extension"
    registry_path = tasks_root / "task_sources.yaml"
    schema_path = default_schema_path()
    if not registry_path.is_file() or not schema_path.is_file():
        raise ValueError("task registry or dataset schema is missing")

    registry_bytes = registry_path.read_bytes()
    registry = _load_yaml(registry_bytes.decode("utf-8"), label=str(registry_path))
    registry_items = registry.get("tasks") if isinstance(registry, dict) else None
    if not isinstance(registry_items, list):
        raise ValueError("tasks/extension/task_sources.yaml must contain a tasks list")
    registry_ids = {
        str(item.get("task_id") or "")
        for item in registry_items
        if isinstance(item, dict)
    }

    include = set(definition.include_tags)
    exclude = set(definition.exclude_tags)
    parsed: list[tuple[Path, dict[str, Any], dict[str, str], bytes]] = []
    for task_path in sorted(tasks_root.glob("*/*_task_*.md")):
        metadata, sections, raw = _parse_task_source(task_path)
        tags = set(_normalized_tags(metadata.get("tags")))
        if include.issubset(tags) and not tags.intersection(exclude):
            parsed.append((task_path, metadata, sections, raw))

    task_ids = [str(item[1].get("id") or "") for item in parsed]
    if len(task_ids) != len(set(task_ids)):
        duplicates = sorted(task_id for task_id, count in Counter(task_ids).items() if count > 1)
        raise ValueError(f"duplicate selected task IDs: {duplicates}")
    missing_registry = sorted(set(task_ids) - registry_ids)
    if missing_registry:
        raise ValueError(f"selected tasks are missing from task_sources.yaml: {missing_registry}")

    schema_bytes = schema_path.read_bytes()
    members = [
        BundleMember("schemas/dataset-manifest-v1.schema.json", schema_bytes),
        BundleMember("provenance/task_sources.yaml", registry_bytes),
    ]
    task_records: list[dict[str, Any]] = []
    category_counts: Counter[str] = Counter()
    grading_counts: Counter[str] = Counter()
    difficulty_counts: Counter[str] = Counter()
    timeout_counts: Counter[str] = Counter()

    for order, (task_path, metadata, sections, raw) in enumerate(parsed, start=1):
        task_id = str(metadata.get("id") or "").strip()
        if not task_id or "/" in task_id or "\\" in task_id:
            raise ValueError(f"invalid task ID: {task_id!r}")
        category = str(metadata.get("category") or "").strip()
        if category != task_path.parent.name:
            raise ValueError(f"category/path mismatch for {task_id}")
        workspace_text = _strip_codeblock(sections.get("Workspace Path", ""))
        workspace_rel = _safe_relative_path(workspace_text, label="workspace path")
        workspace_root = _within(repo_root / Path(*workspace_rel.parts), repo_root, label="workspace")

        task_root = f"tasks/{task_id}"
        execution_tree, execution_members = _tree_materials(
            workspace_root / "exec", f"{task_root}/execution/exec"
        )
        scoring_tree, scoring_members = _tree_materials(
            workspace_root / "gt", f"{task_root}/private-scoring/gt"
        )
        execution_contract, scoring_contract = _task_contracts(
            task_id, metadata, sections, execution_tree, scoring_tree
        )
        execution_bytes = _json_bytes(execution_contract)
        scoring_bytes = _json_bytes(scoring_contract)
        task_bundle_path = f"{task_root}/task.md"
        execution_contract_path = f"{task_root}/execution/contract.json"
        scoring_contract_path = f"{task_root}/private-scoring/contract.json"
        members.extend([
            BundleMember(task_bundle_path, raw),
            BundleMember(execution_contract_path, execution_bytes),
            BundleMember(scoring_contract_path, scoring_bytes),
            *execution_members,
            *scoring_members,
        ])

        tags = _normalized_tags(metadata.get("tags"))
        grading_type = str(metadata.get("grading_type") or "").strip()
        difficulty = str(metadata.get("difficulty") or "").strip()
        timeout_seconds = int(metadata.get("timeout_seconds", 120))
        category_counts[category] += 1
        grading_counts[grading_type] += 1
        difficulty_counts[difficulty] += 1
        timeout_counts[str(timeout_seconds)] += 1
        task_records.append({
            "order": order,
            "task_id": task_id,
            "name": str(metadata.get("name") or "").strip(),
            "category": category,
            "difficulty": difficulty,
            "modality": str(metadata.get("modality") or "").strip(),
            "timeout_seconds": timeout_seconds,
            "grading_type": grading_type,
            "grading_weights": metadata.get("grading_weights") or {},
            "tags": tags,
            "source": {
                "task_path": task_path.relative_to(repo_root).as_posix(),
                "workspace_path": workspace_root.relative_to(repo_root).as_posix(),
            },
            "bundle": {
                "task_path": task_bundle_path,
                "execution_contract_path": execution_contract_path,
                "scoring_contract_path": scoring_contract_path,
            },
            "digests": {
                "task_sha256": _sha256_bytes(raw),
                "prompt_sha256": _sha256_bytes(
                    sections.get("Prompt", "").strip().encode("utf-8")
                ),
                "execution_contract_sha256": _sha256_bytes(execution_bytes),
                "scoring_contract_sha256": _sha256_bytes(scoring_bytes),
                "workspace_exec_sha256": execution_tree["sha256"],
                "private_scoring_sha256": scoring_tree["sha256"],
            },
            "materials": {
                "execution": execution_tree,
                "private_scoring": scoring_tree,
            },
        })

    statistics = {
        "task_count": len(task_records),
        "category_counts": dict(sorted(category_counts.items())),
        "grading_type_counts": dict(sorted(grading_counts.items())),
        "difficulty_counts": dict(sorted(difficulty_counts.items())),
        "timeout_counts": dict(sorted(timeout_counts.items(), key=lambda item: int(item[0]))),
    }
    _assert_expected_statistics(statistics, definition)
    revision = source_revision or _derive_source_revision(repo_root)
    manifest: dict[str, Any] = {
        "schema_id": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "bundle_protocol": BUNDLE_PROTOCOL,
        "dataset_id": definition.dataset_id,
        "created_at": definition.created_at,
        "generated_by": GENERATOR_VERSION,
        "digest_algorithm": DATASET_DIGEST_ALGORITHM,
        "source": {
            "revision": revision,
            "revision_scope": ["tasks/extension", "workspace/extension"],
            "task_registry_path": "provenance/task_sources.yaml",
            "task_registry_sha256": _sha256_bytes(registry_bytes),
        },
        "schema": {
            "path": "schemas/dataset-manifest-v1.schema.json",
            "sha256": _sha256_bytes(schema_bytes),
        },
        "selection": {
            "task_root": "tasks/extension",
            "include_tags": list(definition.include_tags),
            "exclude_tags": list(definition.exclude_tags),
            "ordering": "source_path_posix_ascending",
        },
        "statistics": statistics,
        "task_count": len(task_records),
        "tasks": task_records,
    }
    manifest["dataset_digest"] = _canonical_sha256(manifest)
    return manifest, members


def load_manifest_lock(path: Optional[Path] = None) -> dict[str, Any]:
    target = (path or default_manifest_path()).resolve()
    value = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"dataset manifest lock must be an object: {target}")
    return value


def write_manifest_lock(manifest: Mapping[str, Any], path: Optional[Path] = None) -> Path:
    target = (path or default_manifest_path()).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(_json_bytes(dict(manifest)))
    return target


def _zip_info(member: BundleMember, full_path: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(full_path, FIXED_ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.flag_bits |= 0x800
    if member.kind == "directory":
        info.external_attr = (stat.S_IFDIR | member.mode) << 16 | 0x10
    elif member.kind == "symlink":
        info.external_attr = (stat.S_IFLNK | member.mode) << 16
    else:
        info.external_attr = (stat.S_IFREG | member.mode) << 16
    return info


def write_dataset_bundle(
    manifest: Mapping[str, Any],
    members: Sequence[BundleMember],
    output_path: Path,
) -> Path:
    dataset_id = str(manifest.get("dataset_id") or "")
    _safe_relative_path(dataset_id, label="dataset_id")
    all_members = [BundleMember("manifest.json", _json_bytes(dict(manifest))), *members]
    paths = [member.path for member in all_members]
    if len(paths) != len(set(paths)):
        duplicates = sorted(path for path, count in Counter(paths).items() if count > 1)
        raise ValueError(f"duplicate bundle members: {duplicates}")
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(f".{output_path.name}.{os.getpid()}.tmp")
    try:
        with zipfile.ZipFile(temporary, "w", allowZip64=True) as archive:
            for member in sorted(all_members, key=lambda item: item.path):
                relative = member.path.rstrip("/")
                _safe_relative_path(relative, label="bundle member")
                full_path = f"{dataset_id}/{member.path}"
                archive.writestr(_zip_info(member, full_path), member.data)
        os.replace(temporary, output_path)
    finally:
        temporary.unlink(missing_ok=True)
    return output_path


def build_default_bundle(
    repo_root: Path,
    output_path: Path,
    *,
    manifest_path: Optional[Path] = None,
) -> dict[str, Any]:
    manifest, members = compile_dataset(repo_root, definition=DEFAULT_DEFINITION)
    locked = load_manifest_lock(manifest_path)
    if manifest != locked:
        raise ValueError(
            "dataset sources do not match the frozen manifest; review the change and "
            "run the explicit update-lock command for a new accepted snapshot"
        )
    write_dataset_bundle(locked, members, output_path)
    result = verify_dataset_bundle(output_path)
    checksum_path = output_path.with_suffix(output_path.suffix + ".sha256")
    checksum_path.write_text(
        f"{result['bundle_sha256']}  {output_path.name}\n", encoding="utf-8"
    )
    result["checksum_path"] = str(checksum_path.resolve())
    return result


def _default_output(repo_root: Path) -> Path:
    return (
        repo_root
        / "report-workspace/general-e2e/datasets/general-custom60-v1"
        / "general-custom60-v1.dataset.zip"
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    update = subparsers.add_parser("update-lock", help="regenerate the reviewed manifest lock")
    update.add_argument("--repo-root", type=Path, default=_module_root())
    update.add_argument("--manifest", type=Path, default=default_manifest_path())
    update.add_argument("--source-revision", default="")

    build = subparsers.add_parser("build", help="build and verify the frozen dataset ZIP")
    build.add_argument("--repo-root", type=Path, default=_module_root())
    build.add_argument("--manifest", type=Path, default=default_manifest_path())
    build.add_argument("--output", type=Path)

    verify = subparsers.add_parser("verify", help="verify a bundle without a checkout")
    verify.add_argument("--bundle", type=Path, required=True)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "update-lock":
        manifest, _ = compile_dataset(
            args.repo_root,
            definition=DEFAULT_DEFINITION,
            source_revision=args.source_revision or None,
        )
        path = write_manifest_lock(manifest, args.manifest)
        result = {
            "dataset_id": manifest["dataset_id"],
            "dataset_digest": manifest["dataset_digest"],
            "task_count": manifest["task_count"],
            "manifest_path": str(path),
        }
    elif args.command == "build":
        output = args.output or _default_output(args.repo_root.resolve())
        result = build_default_bundle(
            args.repo_root, output, manifest_path=args.manifest
        )
    else:
        result = verify_dataset_bundle(args.bundle)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
