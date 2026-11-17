"""Build and verify independently frozen General E2E dataset bundles.

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
from .source_history import FrozenSources

from .catalog import load_mapping, load_registered_dataset, repository_path
from .definition import (
    DATASETS, DEFAULT_DEFINITION, DatasetDefinition, GENERAL116_DEFINITION,
    GENERAL70_V2_DEFINITION, GENERAL70_V3_DEFINITION, GENERAL70_V4_DEFINITION,
    GENERAL70_V5_DEFINITION, GENERAL70_V6_DEFINITION, INFO004_OPEN_DEFINITION,
    INFO004_OPEN_V2_DEFINITION, INFO004_OPEN_V3_DEFINITION,
)
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


def dataset_manifest_path(dataset_id: str) -> Path:
    if dataset_id not in DATASETS:
        raise ValueError(f"unknown dataset: {dataset_id}")
    return Path(__file__).resolve().parent / "manifests" / f"{dataset_id}.json"


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
        # Some imported Office sources use folded YAML '-tag' lines.
        values = [part.lstrip("-") for part in raw.split()] if raw.lstrip().startswith("-") else raw.split(",")
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


def _parse_task_source(path: Path, *, raw: bytes | None = None) -> tuple[dict[str, Any], dict[str, str], bytes]:
    raw = path.read_bytes() if raw is None else raw
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


def _tree_materials(root: Path, bundle_root: str, *, sources: FrozenSources | None = None) -> tuple[dict[str, Any], list[BundleMember]]:
    if not root.is_dir():
        raise ValueError(f"required material directory is missing: {root}")
    entries: list[dict[str, Any]] = []
    members: list[BundleMember] = []

    def visit(directory: Path) -> None:
        for child in sorted(directory.iterdir(), key=lambda item: item.name):
            if sources is not None and sources.excludes(child):
                continue
            # Interpreter/test caches are host-generated, not dataset materials.
            # Filter before traversal so ignored cache trees are never read.
            if child.name == "__pycache__" or child.suffix == ".pyc":
                continue
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
                data = sources.read_bytes(child) if sources is not None else child.read_bytes()
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
    if metadata.get("scoring_runtime") is not None:
        requirements = metadata["scoring_runtime"]
        if (not isinstance(requirements, dict) or set(requirements) - {"office", "office_render", "html_render", "research_sources"}
                or any(type(value) is not bool for value in requirements.values())
                or requirements.get("office_render") and not requirements.get("office")):
            raise ValueError(f"invalid scoring_runtime: {task_id}")
        scoring["scoring_runtime"] = requirements
    if metadata.get("rule_result_adapter") is not None:
        scoring["rule_result_adapter"] = metadata["rule_result_adapter"]
    return execution, scoring


def _adapt_imported_contract(contract: dict[str, Any]) -> None:
    """Freeze transport adapters without rewriting the author's rubric or score budgets."""
    weights = [float(value) for value in re.findall(
        r"^###\s+.*\([^\n]*\bweight:\s*([0-9.]+)\s*\)",
        contract["llm_judge_rubric"], re.MULTILINE)]
    total = sum(weights)
    budget = float(contract["grading_weights"].get("llm_judge", 1.0)) * 100
    if abs(total - 1.0) > 1e-6:
        if not weights or abs(total - budget) > 1e-6 or total <= 0:
            raise ValueError(f"semantic point weights do not match group budget: {contract['task_id']}")
        contract["semantic_weight_scale"] = total
    declared_adapter = contract.get("rule_result_adapter") or {}
    if not isinstance(declared_adapter, dict):
        raise ValueError("rule_result_adapter must be an object")
    contract["rule_result_adapter"] = {
        "schema_version": "wildclawbench.general-e2e-numeric-diagnostics/v1",
        "diagnostic_keys": ["diagnostics", "诊断"],
        "evidence_only": float(contract["grading_weights"].get("automated", 0)) == 0,
        # This source explicitly defines its numeric v2 interface as an equal mean.
        "default_overall": "mean" if contract["task_id"] == "02_Office_task_001_multi_source_project_report" else None,
        **declared_adapter,
    }


def _derive_source_revision(repo_root: Path, scope: Sequence[str] = ("tasks/extension", "workspace/extension")) -> str:
    completed = subprocess.run(
        [
            "git",
            "log",
            "-1",
            "--format=%H",
            "--",
            *scope,
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


def _assert_release_constraints(
    definition: DatasetDefinition,
    parsed: Sequence[tuple[Path, dict[str, Any], dict[str, str], bytes]],
    registry: Mapping[str, Mapping[str, Any]],
) -> None:
    """Check declared authoring attributes; this is not empirical calibration."""
    if not definition.constraints:
        return
    visual = coding = network = production = 0
    groups: Counter[str] = Counter()
    for _, metadata, _, _ in parsed:
        task_id = metadata["id"]
        entry = registry[task_id]
        attrs = entry.get("attributes")
        if not isinstance(attrs, dict):
            raise ValueError(f"release task lacks authoring attributes: {task_id}")
        for field in ("requires_visual_input", "coding_primary"):
            if type(attrs.get(field)) is not bool:
                raise ValueError(f"{task_id}: {field} must be boolean")
        if attrs["requires_visual_input"] != (metadata.get("modality") == "multimodal"):
            raise ValueError(f"{task_id}: visual attribute disagrees with modality")
        network_spec = entry.get("network")
        if not isinstance(network_spec, dict):
            raise ValueError(f"{task_id}: network must be a mapping")
        mode = network_spec.get("mode")
        if mode not in {"offline", "open_public_search", "fixed_url_verification", "site_scoped_search"}:
            raise ValueError(f"{task_id}: unknown network mode")
        group = attrs.get("retrieval_group")
        if group is not None:
            expected = {"open_search": {"open_public_search"},
                        "directed_web_retrieval": {"fixed_url_verification", "site_scoped_search"},
                        "local_evidence": {"offline"}}
            if not isinstance(group, str) or group not in expected or mode not in expected[group]:
                raise ValueError(f"{task_id}: retrieval group/network mode mismatch")
            groups[group] += 1
        origin = entry.get("origin")
        if not isinstance(origin, dict):
            raise ValueError(f"{task_id}: origin must be a mapping")
        refs = origin.get("production_refs", [])
        if not isinstance(refs, list):
            raise ValueError(f"{task_id}: production_refs must be a list")
        accepted = [ref for ref in refs if isinstance(ref, dict)
                    and ref.get("review") == "accepted_intent_prototype"
                    and SHA256_RE.fullmatch(str(ref.get("query_hash", "")))]
        visual += attrs["requires_visual_input"]
        coding += attrs["coding_primary"]
        network += mode != "offline"
        production += bool(accepted)
    values = {"multimodal_exact": visual, "multimodal_max_ratio": visual / len(parsed),
              "production_backed_min": production, "coding_primary_max": coding,
              "controlled_network_max": network,
              "research_retrieval_group_counts": dict(groups)}
    for key, expected in definition.constraints.items():
        actual = values[key]
        ok = actual >= expected if key.endswith("_min") else (
            actual <= expected if key.endswith("_max") or key.endswith("_max_ratio") else actual == expected)
        if not ok:
            raise ValueError(f"release constraint {key} failed: expected={expected!r}, actual={actual!r}")


def _registered_registry_bytes(
    repo_root: Path, definition: DatasetDefinition, registry: Mapping[str, Mapping[str, Any]],
    task_ids: Sequence[str],
) -> bytes:
    """Hash a release projection, so additions to the source pool cannot rewrite it.

    This remains a YAML-compatible source registry inside the existing v1 bundle.
    The definition and capability projection are transitively locked by its digest.
    """
    mapping_path = repository_path(repo_root, definition.capability_map_path, label="capability map")
    mapping = load_mapping(mapping_path)
    selected_map = {}
    for task_id in task_ids:
        if not isinstance(mapping.get(task_id), dict) or not mapping[task_id]:
            raise ValueError(f"selected task lacks capability mapping: {task_id}")
        selected_map[task_id] = mapping[task_id]
    return _json_bytes({
        "schema_version": 1,
        "dataset_contract": {
            "dataset_id": definition.dataset_id, "created_at": definition.created_at,
            "task_root": definition.task_root, "workspace_root": definition.workspace_root,
            "task_id_prefix": definition.task_id_prefix,
            "required_tags": list(definition.include_tags), "exclude_tags": list(definition.exclude_tags),
            "task_ids": list(task_ids),
            "category_labels": {key: definition.category_labels[key]
                                for key in sorted(definition.expected_category_counts)},
            "constraints": dict(definition.constraints),
            "expected_statistics": {
                "task_count": definition.expected_task_count,
                "category_counts": dict(definition.expected_category_counts),
                "grading_type_counts": dict(definition.expected_grading_type_counts),
                "difficulty_counts": dict(definition.expected_difficulty_counts),
                "timeout_counts": dict(definition.expected_timeout_counts),
            },
        },
        "tasks": [registry[task_id] for task_id in task_ids],
        "checkpoint_capability_map7": selected_map,
    })


def compile_dataset(
    repo_root: Path,
    *,
    definition: DatasetDefinition = DEFAULT_DEFINITION,
    source_revision: Optional[str] = None,
) -> tuple[dict[str, Any], list[BundleMember]]:
    """Compile source tasks into a manifest plus deterministic archive members."""
    repo_root = repo_root.resolve()
    sources = FrozenSources(repo_root, definition.frozen_source_index, definition.current_source_paths)
    tasks_root = repository_path(repo_root, definition.task_root, label="task root")
    workspace_base = repository_path(repo_root, definition.workspace_root, label="workspace root")
    registry_path = repository_path(repo_root, definition.registry_path, label="task registry")
    schema_path = default_schema_path()
    if not registry_path.is_file() or not schema_path.is_file():
        raise ValueError("task registry or dataset schema is missing")

    registry_bytes = registry_path.read_bytes()
    registry = _load_yaml(registry_bytes.decode("utf-8"), label=str(registry_path))
    registry_items = registry.get("tasks") if isinstance(registry, dict) else None
    if not isinstance(registry_items, list):
        raise ValueError(f"{definition.registry_path} must contain a tasks list")
    if definition.task_id_prefix:
        registry = load_mapping(registry_path)
        registry_items = registry.get("tasks")
        if not isinstance(registry_items, list):
            raise ValueError("registered task sources must contain a tasks list")
    registry_ids = {
        str(item.get("task_id") or "")
        for item in registry_items
        if isinstance(item, dict)
    }
    if definition.task_id_prefix and (
        "" in registry_ids or len(registry_ids) != len(registry_items)
    ):
        raise ValueError("source registry tasks must be mappings with unique task IDs")
    registry_by_id = {str(item["task_id"]): item for item in registry_items
                      if isinstance(item, dict) and item.get("task_id")}

    include = set(definition.include_tags)
    exclude = set(definition.exclude_tags)
    parsed: list[tuple[Path, dict[str, Any], dict[str, str], bytes]] = []
    expected_ids = set(definition.task_ids)
    if len(expected_ids) != len(definition.task_ids):
        raise ValueError("release task IDs must be unique")
    for task_path in sorted(tasks_root.glob(definition.task_glob)):
        if definition.task_id_prefix and expected_ids and task_path.stem not in expected_ids:
            continue
        _within(task_path, tasks_root, label="task source")
        metadata, sections, raw = _parse_task_source(task_path, raw=sources.read_bytes(task_path))
        if expected_ids and metadata.get("id") not in expected_ids:
            continue
        tags = set(_normalized_tags(metadata.get("tags")))
        if (include.issubset(tags) and not tags.intersection(exclude)
                and (not definition.task_ids or metadata.get("id") in definition.task_ids)):
            parsed.append((task_path, metadata, sections, raw))

    task_ids = [str(item[1].get("id") or "") for item in parsed]
    if len(task_ids) != len(set(task_ids)):
        duplicates = sorted(task_id for task_id, count in Counter(task_ids).items() if count > 1)
        raise ValueError(f"duplicate selected task IDs: {duplicates}")
    if expected_ids and set(task_ids) != expected_ids:
        raise ValueError(f"release tasks missing or excluded by required tags: {sorted(expected_ids - set(task_ids))}")
    missing_registry = sorted(set(task_ids) - registry_ids)
    if missing_registry:
        raise ValueError(f"selected tasks are missing from task_sources.yaml: {missing_registry}")
    if definition.task_id_prefix:
        if not expected_ids:
            raise ValueError("registered datasets require explicit release task IDs")
        _assert_release_constraints(definition, parsed, registry_by_id)
        registry_bytes = _registered_registry_bytes(repo_root, definition, registry_by_id, task_ids)

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
    report_capabilities = json.loads(registry_bytes)["checkpoint_capability_map7"] if definition.task_id_prefix else {}

    for order, (task_path, metadata, sections, raw) in enumerate(parsed, start=1):
        task_id = str(metadata.get("id") or "").strip()
        if not task_id or "/" in task_id or "\\" in task_id:
            raise ValueError(f"invalid task ID: {task_id!r}")
        category = str(metadata.get("category") or "").strip()
        category_directory = task_path.relative_to(tasks_root).parts[0]
        expected_category = dict(definition.category_directories).get(category_directory, task_path.parent.name)
        if category != expected_category:
            raise ValueError(f"category/path mismatch for {task_id}")
        if definition.task_id_prefix:
            if category not in definition.category_labels:
                raise ValueError(f"unregistered category for {task_id}: {category}")
            if (not task_id.startswith(f"{definition.task_id_prefix}{category}_task_")
                    or task_path.name != f"{task_id}.md"):
                raise ValueError(f"task namespace/path mismatch: {task_id}")
            report_contract = metadata.get("dataset_report")
            inline_contract = re.search(r"^dataset_report:[ \t]*(\{[^\n]*\})[ \t]*$", raw.decode("utf-8").split("\n---", 1)[0], re.M)
            if (not isinstance(report_contract, dict)
                    or inline_contract is None
                    or report_contract.get("schema_version") != "wildclawbench.dataset-report-contract/v1"
                    or report_contract.get("category") != category
                    or report_contract.get("category_name") != definition.category_labels[category]
                    or type(report_contract.get("category_order")) is not int
                    or report_contract.get("category_order") != list(definition.category_labels).index(category)
                    or not isinstance(report_contract.get("series_id"), str)
                    or report_contract.get("series_id", "").replace("-", "_").replace(".", "_") + "_" != definition.task_id_prefix
                    or report_contract.get("checkpoint_capabilities") != report_capabilities[task_id]):
                raise ValueError(f"frozen task report metadata disagrees with dataset definition/mapping: {task_id}")
            if json.loads(inline_contract.group(1)) != report_contract:
                raise ValueError(f"task report metadata must use the canonical inline JSON form: {task_id}")
        workspace_text = _strip_codeblock(sections.get("Workspace Path", ""))
        workspace_rel = _safe_relative_path(workspace_text, label="workspace path")
        workspace_root = _within(repo_root / Path(*workspace_rel.parts), repo_root, label="workspace")
        if definition.task_id_prefix:
            expected_workspace = workspace_base / category / task_id
            if (workspace_text != expected_workspace.relative_to(repo_root).as_posix()
                    or workspace_root != expected_workspace
                    or not workspace_root.is_relative_to(workspace_base)):
                raise ValueError(f"workspace must match dataset/category/task ID: {task_id}")
            for tree_name in ("exec", "gt"):
                _within(workspace_root / tree_name, workspace_root, label=f"workspace {tree_name}")
            exec_root, gt_root = [(workspace_root / key).resolve() for key in ("exec", "gt")]
            if exec_root.is_relative_to(gt_root) or gt_root.is_relative_to(exec_root):
                raise ValueError(f"execution and private scoring trees must be separate: {task_id}")

        task_root = f"tasks/{task_id}"
        execution_tree, execution_members = _tree_materials(
            workspace_root / "exec", f"{task_root}/execution/exec", sources=sources
        )
        scoring_tree, scoring_members = _tree_materials(
            workspace_root / "gt", f"{task_root}/private-scoring/gt", sources=sources
        )
        if definition.task_id_prefix and not any(entry["kind"] == "file" and entry["size"] > 0
                                                 and Path(entry["path"]).name != ".gitkeep"
                                                 for entry in scoring_tree["entries"]):
            raise ValueError(f"private scoring materials must not be empty: {task_id}")
        execution_contract, scoring_contract = _task_contracts(
            task_id, metadata, sections, execution_tree, scoring_tree
        )
        if definition.dataset_id in {GENERAL116_DEFINITION.dataset_id, GENERAL70_V2_DEFINITION.dataset_id, GENERAL70_V3_DEFINITION.dataset_id, GENERAL70_V4_DEFINITION.dataset_id, GENERAL70_V5_DEFINITION.dataset_id, GENERAL70_V6_DEFINITION.dataset_id, INFO004_OPEN_DEFINITION.dataset_id, INFO004_OPEN_V2_DEFINITION.dataset_id, INFO004_OPEN_V3_DEFINITION.dataset_id}:
            _adapt_imported_contract(scoring_contract)
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
    revision = source_revision or definition.source_revision or _derive_source_revision(repo_root, definition.revision_scope)
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
            "revision_scope": list(definition.revision_scope),
            "task_registry_path": "provenance/task_sources.yaml",
            "task_registry_sha256": _sha256_bytes(registry_bytes),
        },
        "schema": {
            "path": "schemas/dataset-manifest-v1.schema.json",
            "sha256": _sha256_bytes(schema_bytes),
        },
        "selection": {
            "task_root": definition.task_root,
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


def write_manifest_lock(
    manifest: Mapping[str, Any], path: Optional[Path] = None, *, overwrite: bool = True,
) -> Path:
    target = (path or default_manifest_path()).resolve()
    payload = _json_bytes(dict(manifest))
    if not overwrite and target.exists():
        if target.read_bytes() != payload:
            raise FileExistsError("frozen manifest already exists; publish a new dataset version instead of overwriting it")
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    if overwrite:
        target.write_bytes(payload)
    else:
        with target.open("xb") as stream:
            stream.write(payload)
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
    definition: DatasetDefinition = DEFAULT_DEFINITION,
) -> dict[str, Any]:
    manifest, members = compile_dataset(repo_root, definition=definition)
    locked = load_manifest_lock(manifest_path or dataset_manifest_path(definition.dataset_id))
    if manifest != locked:
        raise ValueError(
            "dataset sources do not match the frozen manifest; review the change and "
            "run the explicit update-lock command for a new accepted snapshot"
        )
    return _write_verified_bundle(locked, members, output_path)


def _write_verified_bundle(
    locked: Mapping[str, Any], members: Sequence[BundleMember], output_path: Path,
) -> dict[str, Any]:
    write_dataset_bundle(locked, members, output_path)
    result = verify_dataset_bundle(output_path)
    checksum_path = output_path.with_suffix(output_path.suffix + ".sha256")
    checksum_path.write_text(
        f"{result['bundle_sha256']}  {output_path.name}\n", encoding="utf-8"
    )
    result["checksum_path"] = str(checksum_path.resolve())
    return result


def build_registered_bundle(
    repo_root: Path, dataset_id: str, output_path: Path, *, release_id: str | None = None,
) -> dict[str, Any]:
    registered = load_registered_dataset(repo_root, dataset_id, release_id=release_id)
    if registered.kind in {"legacy", "builtin"}:
        # Explicit legacy selection is bounded to the frozen manifest IDs too.
        locked = load_manifest_lock(registered.manifest_path)
        manifest, members = compile_dataset(repo_root, definition=registered.definition)
    else:
        if registered.status != "frozen":
            raise ValueError("only a frozen registered release can be distributed")
        locked = load_manifest_lock(registered.manifest_path)
        _validate_manifest(locked)
        # Source additions may postdate this release. Compare every selected
        # byte/contract against its immutable lock without rewriting its revision.
        manifest, members = compile_dataset(repo_root, definition=registered.definition,
                                            source_revision=locked["source"]["revision"])
    if manifest != locked:
        raise ValueError("dataset sources do not match the frozen manifest; publish a new release")
    return _write_verified_bundle(locked, members, output_path)


def freeze_registered_manifest(
    repo_root: Path, dataset_id: str, *, release_id: str | None = None,
    source_revision: str | None = None,
) -> Path:
    registered = load_registered_dataset(repo_root, dataset_id, release_id=release_id)
    if registered.status != "ready" or registered.definition_path is None:
        raise ValueError("only a ready registered release can create a new immutable manifest")
    if registered.manifest_path.exists():
        raise FileExistsError("release manifest already exists; publish a new release instead of overwriting it")
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all", "--", *registered.definition.revision_scope],
        cwd=repo_root, capture_output=True, text=True, check=False,
    )
    if dirty.returncode or dirty.stdout.strip():
        raise ValueError("commit the dataset sources before freezing a release")
    if source_revision:
        if not re.fullmatch(r"[0-9a-f]{40}", source_revision):
            raise ValueError("source_revision must be a full Git commit SHA")
        comparison = subprocess.run(
            ["git", "diff", "--exit-code", source_revision, "--", *registered.definition.revision_scope],
            cwd=repo_root, capture_output=True, text=True, check=False,
        )
        if comparison.returncode:
            raise ValueError("source_revision does not match the committed dataset sources")
    manifest, _ = compile_dataset(repo_root, definition=registered.definition,
                                  source_revision=source_revision)
    _validate_manifest(manifest)
    # Exclusive creation prevents even a concurrent freeze from replacing it.
    registered.manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with registered.manifest_path.open("xb") as stream:
        stream.write(_json_bytes(manifest))
    return registered.manifest_path


def _default_output(repo_root: Path, dataset_id: str = DEFAULT_DEFINITION.dataset_id) -> Path:
    return (
        repo_root
        / "report-workspace/general-e2e/datasets" / dataset_id
        / f"{dataset_id}.dataset.zip"
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    update = subparsers.add_parser("update-lock", help="regenerate the reviewed manifest lock")
    update.add_argument("--repo-root", type=Path, default=_module_root())
    update.add_argument("--dataset", choices=DATASETS)
    update.add_argument("--manifest", type=Path)
    update.add_argument("--source-revision", default="")
    update.add_argument("--dataset-id", help="registered series or frozen release ID")
    update.add_argument("--release-id", help="explicit release of a registered series")

    build = subparsers.add_parser("build", help="build and verify the frozen dataset ZIP")
    build.add_argument("--repo-root", type=Path, default=_module_root())
    build.add_argument("--dataset", choices=DATASETS)
    build.add_argument("--manifest", type=Path)
    build.add_argument("--output", type=Path)
    build.add_argument("--dataset-id", help="registered series or frozen release ID")
    build.add_argument("--release-id", help="explicit release of a registered series")

    verify = subparsers.add_parser("verify", help="verify a bundle without a checkout")
    verify.add_argument("--bundle", type=Path, required=True)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command != "verify" and args.dataset and args.dataset_id:
        parser.error("--dataset and --dataset-id are mutually exclusive")
    if args.command != "verify" and args.release_id and not args.dataset_id:
        parser.error("--release-id requires --dataset-id")
    if args.command != "verify" and args.dataset_id and args.manifest:
        parser.error("registered datasets use their catalog manifest; omit --manifest")
    if args.command == "update-lock":
        if args.dataset_id:
            path = freeze_registered_manifest(args.repo_root, args.dataset_id,
                                              release_id=args.release_id,
                                              source_revision=args.source_revision or None)
            manifest = load_manifest_lock(path)
        else:
            manifest, _ = compile_dataset(
                args.repo_root,
                definition=DATASETS[args.dataset or DEFAULT_DEFINITION.dataset_id],
                source_revision=args.source_revision or None,
            )
            path = write_manifest_lock(
                manifest, args.manifest or dataset_manifest_path(manifest["dataset_id"]), overwrite=False,
            )
        result = {
            "dataset_id": manifest["dataset_id"],
            "dataset_digest": manifest["dataset_digest"],
            "task_count": manifest["task_count"],
            "manifest_path": str(path),
        }
    elif args.command == "build":
        if args.dataset_id:
            registered = load_registered_dataset(args.repo_root, args.dataset_id, release_id=args.release_id)
            output = args.output or _default_output(args.repo_root.resolve(), registered.definition.dataset_id)
            result = build_registered_bundle(args.repo_root, args.dataset_id, output, release_id=args.release_id)
        else:
            definition = DATASETS[args.dataset or DEFAULT_DEFINITION.dataset_id]
            output = args.output or _default_output(args.repo_root.resolve(), definition.dataset_id)
            result = build_default_bundle(args.repo_root, output, manifest_path=args.manifest, definition=definition)
    else:
        result = verify_dataset_bundle(args.bundle)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
