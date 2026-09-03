"""Deterministic task-contract fingerprints for evaluation result provenance.

The fingerprints are metadata only: they never change candidate execution or
grading.  Raw task, workspace, and ground-truth contents are not copied into
result directories.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

from .transcript_loader import GRADING_TRANSCRIPT_POLICY_VERSION
from .workspace_evidence import JUDGE_WORKSPACE_EVIDENCE_POLICY_VERSION


PROVENANCE_SCHEMA_VERSION = 1
CONTRACT_HASH_SCHEMA_VERSION = 1
HASH_ALGORITHM = "sha256"
TASK_PROVENANCE_CACHE_KEY = "_contract_provenance"


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _path_tree_sha256(root: Path) -> str:
    """Hash names, entry types, file bytes, and symlink targets without following links."""
    digest = hashlib.sha256()
    digest.update(b"wildclaw-path-tree-v1\0")

    def update_text(value: str) -> None:
        data = value.encode("utf-8", errors="surrogateescape")
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)

    def visit(path: Path, relative: str) -> None:
        update_text(relative)
        if path.is_symlink():
            digest.update(b"L")
            update_text(os.readlink(path))
            return
        if path.is_file():
            digest.update(b"F")
            digest.update(bytes.fromhex(_file_sha256(path)))
            return
        if path.is_dir():
            digest.update(b"D")
            for child in sorted(path.iterdir(), key=lambda item: item.name):
                child_relative = f"{relative}/{child.name}" if relative else child.name
                visit(child, child_relative)
            return
        if not path.exists():
            digest.update(b"M")
            return
        digest.update(b"O")

    visit(root, "")
    return digest.hexdigest()


def _task_source_sha256(task: Mapping[str, Any]) -> str:
    file_path = Path(str(task.get("file_path") or ""))
    if file_path.is_file():
        return _file_sha256(file_path)
    # Keep synthetic/test tasks fingerprintable without pretending the source
    # file existed.  The fallback is still deterministic and remains distinct
    # from a real task-file byte hash through its explicit schema marker.
    return _canonical_sha256({
        "schema": "wildclaw-task-source-fallback-v1",
        "task_id": str(task.get("task_id") or ""),
        "file_path_missing": True,
    })


def _skill_bundles_sha256(task: Mapping[str, Any]) -> str:
    """Hash the declared skill bundles in declaration order."""
    skills_root_raw = str(task.get("skills_path") or "")
    declarations = [
        line.strip()
        for line in str(task.get("skills") or "").splitlines()
        if line.strip()
    ]
    bundles = []
    for declaration in declarations:
        relative = declaration.replace("\\", "/").strip("/")
        tree_sha256 = (
            _path_tree_sha256(Path(skills_root_raw) / relative)
            if skills_root_raw
            else _canonical_sha256({
                "schema": "wildclaw-missing-skills-root-v1",
                "declaration": declaration,
            })
        )
        bundles.append({
            "declaration": declaration,
            "tree_sha256": tree_sha256,
        })
    return _canonical_sha256({
        "schema": "wildclaw-task-skill-bundles-v1",
        "bundles": bundles,
    })


def build_task_provenance(task: Mapping[str, Any]) -> dict[str, Any]:
    """Build whole-task, candidate-execution, and scoring-contract hashes."""
    workspace_raw = str(task.get("workspace_path") or "")
    if workspace_raw:
        workspace_root = Path(workspace_raw)
        exec_sha256 = _path_tree_sha256(workspace_root / "exec")
        tmp_sha256 = _path_tree_sha256(workspace_root / "tmp")
        ground_truth_sha256 = _path_tree_sha256(workspace_root / "gt")
        eval_sha256 = _path_tree_sha256(workspace_root / "eval")
    else:
        exec_sha256 = _canonical_sha256({
            "schema": "wildclaw-missing-workspace-v1",
            "component": "exec",
        })
        tmp_sha256 = _canonical_sha256({
            "schema": "wildclaw-missing-workspace-v1",
            "component": "tmp",
        })
        ground_truth_sha256 = _canonical_sha256({
            "schema": "wildclaw-missing-workspace-v1",
            "component": "gt",
        })
        eval_sha256 = _canonical_sha256({
            "schema": "wildclaw-missing-workspace-v1",
            "component": "eval",
        })
    skill_bundles_sha256 = _skill_bundles_sha256(task)

    execution_contract = {
        "schema_version": CONTRACT_HASH_SCHEMA_VERSION,
        "task_id": str(task.get("task_id") or ""),
        "prompt": str(task.get("prompt") or ""),
        "env": str(task.get("env") or ""),
        "skills": str(task.get("skills") or ""),
        "warmup": str(task.get("warmup") or ""),
        "timeout_seconds": task.get("timeout_seconds"),
        "workspace_exec_sha256": exec_sha256,
        "workspace_tmp_sha256": tmp_sha256,
        "skill_bundles_sha256": skill_bundles_sha256,
    }
    scoring_contract = {
        "schema_version": CONTRACT_HASH_SCHEMA_VERSION,
        "task_id": str(task.get("task_id") or ""),
        "automated_checks": str(task.get("automated_checks") or ""),
        "llm_judge_rubric": str(task.get("llm_judge_rubric") or ""),
        "rubric_criteria": task.get("rubric_criteria") or [],
        "grading_type": str(task.get("grading_type") or ""),
        "grading_weights": task.get("grading_weights") or {},
        "metric_profile": str(task.get("metric_profile") or ""),
        "judge_evidence": task.get("judge_evidence") or {},
        "judge_workspace_evidence_policy": JUDGE_WORKSPACE_EVIDENCE_POLICY_VERSION,
        "grading_transcript_policy": GRADING_TRANSCRIPT_POLICY_VERSION,
        "ground_truth_sha256": ground_truth_sha256,
        "workspace_eval_sha256": eval_sha256,
    }
    return {
        "schema_version": PROVENANCE_SCHEMA_VERSION,
        "provenance_status": "complete",
        "hash_algorithm": HASH_ALGORITHM,
        "contract_hash_schema_version": CONTRACT_HASH_SCHEMA_VERSION,
        "task_id": str(task.get("task_id") or ""),
        "task_sha256": _task_source_sha256(task),
        "execution_contract_sha256": _canonical_sha256(execution_contract),
        "scoring_contract_sha256": _canonical_sha256(scoring_contract),
        "workspace_exec_sha256": exec_sha256,
        "workspace_tmp_sha256": tmp_sha256,
        "skill_bundles_sha256": skill_bundles_sha256,
        "ground_truth_sha256": ground_truth_sha256,
        "workspace_eval_sha256": eval_sha256,
    }


def get_or_build_task_provenance(task: dict[str, Any]) -> dict[str, Any]:
    cached = task.get(TASK_PROVENANCE_CACHE_KEY)
    if isinstance(cached, dict):
        return cached
    provenance = build_task_provenance(task)
    task[TASK_PROVENANCE_CACHE_KEY] = provenance
    return provenance


def write_provenance_file(path: Path, provenance: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.urandom(12).hex()}.tmp")
    try:
        temporary.write_text(
            json.dumps(dict(provenance), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
