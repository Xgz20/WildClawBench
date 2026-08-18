"""低分分析产物的结构、覆盖范围和来源完整性校验。"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any


VALID_ANALYSIS_TYPES = {"failure", "unscored", "success_control"}
VALID_LAYERS = {"L1a", "L1b", "L2", "L3", "L4", "uncertain", "none"}
VALID_CONFIDENCE = {"confirmed", "probable", "unconfirmed", "none"}
REQUIRED_FIELDS = ("result_analysis", "root_cause_analysis")


def _issue(code: str, message: str, *, task_id: str = "", severity: str = "error") -> dict:
    return {
        "code": code,
        "message": message,
        "task_id": task_id,
        "severity": severity,
    }


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _source_snapshot_status(records: list[dict]) -> tuple[str, list[dict]]:
    issues: list[dict] = []
    if not records:
        return "not_available", issues

    missing_snapshot = False
    changed = False
    for record in records:
        task_id = str(record.get("task_id") or "")
        snapshots = record.get("source_fingerprints")
        if not isinstance(snapshots, dict) or not snapshots:
            missing_snapshot = True
            continue
        for source_name, expected in snapshots.items():
            if not isinstance(expected, dict):
                missing_snapshot = True
                continue
            source_path = Path(str(expected.get("path") or ""))
            if not source_path.is_file():
                changed = True
                issues.append(_issue(
                    "SOURCE_FILE_MISSING",
                    f"来源文件不存在：{source_name} -> {source_path}",
                    task_id=task_id,
                ))
                continue
            expected_hash = str(expected.get("sha256") or "")
            if not expected_hash:
                missing_snapshot = True
                continue
            actual_hash = _sha256(source_path)
            if actual_hash != expected_hash:
                changed = True
                issues.append(_issue(
                    "SOURCE_FILE_CHANGED",
                    f"来源文件已变化：{source_name} -> {source_path}",
                    task_id=task_id,
                ))

    if changed:
        return "changed", issues
    if missing_snapshot:
        issues.append(_issue(
            "SOURCE_SNAPSHOT_MISSING",
            "manifest 未包含完整来源文件指纹，无法锁定原始分析输入",
            severity="warning",
        ))
        return "unverified", issues
    return "verified", issues


def validate_analysis(
    analysis: Any,
    *,
    expected: dict[str, dict] | None = None,
    allow_partial: bool = True,
    source_records: list[dict] | None = None,
) -> dict:
    """校验分析结果。

    `expected` 是 manifest 中允许的任务集合。分析结果可以只是该集合的子集，
    此时返回 `partial`/warning，但不会把未分析任务当作已分析任务。
    """
    issues: list[dict] = []
    entries = analysis if isinstance(analysis, dict) else None
    if entries is None:
        issues.append(_issue("ANALYSIS_NOT_OBJECT", "analysis JSON 顶层必须是对象"))
        return {
            "schema_version": 1,
            "status": "FAIL",
            "coverage": {"expected": 0, "analyzed": 0, "ratio": 0.0, "state": "invalid"},
            "issues": issues,
        }

    expected = expected or {}
    allowed_ids = set(expected)
    analyzed_ids: set[str] = set()
    for raw_task_id, item in entries.items():
        task_id = str(raw_task_id)
        if not isinstance(item, dict):
            issues.append(_issue("ANALYSIS_ENTRY_NOT_OBJECT", "任务分析项必须是对象", task_id=task_id))
            continue
        if task_id in analyzed_ids:
            issues.append(_issue("ANALYSIS_TASK_DUPLICATE", "任务出现重复分析项", task_id=task_id))
            continue
        analyzed_ids.add(task_id)
        if allowed_ids and task_id not in allowed_ids:
            issues.append(_issue("ANALYSIS_TASK_OUT_OF_SCOPE", "分析任务不在 manifest 或当前报告范围内", task_id=task_id))

        for field in REQUIRED_FIELDS:
            if not isinstance(item.get(field), str) or not item[field].strip():
                issues.append(_issue("ANALYSIS_FIELD_EMPTY", f"缺少非空字段：{field}", task_id=task_id))

        analysis_type = item.get("analysis_type")
        if analysis_type is not None and analysis_type not in VALID_ANALYSIS_TYPES:
            issues.append(_issue("ANALYSIS_TYPE_INVALID", f"analysis_type 无效：{analysis_type}", task_id=task_id))
        expected_type = expected.get(task_id, {}).get("analysis_type")
        if analysis_type is not None and expected_type and analysis_type != expected_type:
            issues.append(_issue(
                "ANALYSIS_TYPE_MISMATCH",
                f"analysis_type={analysis_type}，manifest={expected_type}",
                task_id=task_id,
            ))

        attribution_fields = {
            key: item.get(key)
            for key in ("attribution_layer", "attribution_confidence", "attribution_evidence")
            if key in item
        }
        if attribution_fields and len(attribution_fields) != 3:
            issues.append(_issue(
                "ATTRIBUTION_FIELDS_INCOMPLETE",
                "归因字段必须同时提供 attribution_layer、attribution_confidence、attribution_evidence",
                task_id=task_id,
            ))
        if attribution_fields and len(attribution_fields) == 3:
            layer = item.get("attribution_layer")
            confidence = item.get("attribution_confidence")
            evidence = item.get("attribution_evidence")
            if layer not in VALID_LAYERS:
                issues.append(_issue("ATTRIBUTION_LAYER_INVALID", f"归因层无效：{layer}", task_id=task_id))
            if confidence not in VALID_CONFIDENCE:
                issues.append(_issue("ATTRIBUTION_CONFIDENCE_INVALID", f"置信度无效：{confidence}", task_id=task_id))
            if not isinstance(evidence, str) or not evidence.strip():
                issues.append(_issue("ATTRIBUTION_EVIDENCE_EMPTY", "归因证据不能为空", task_id=task_id))
            if layer == "none" and confidence != "none":
                issues.append(_issue("ATTRIBUTION_NONE_MISMATCH", "none 归因层必须配套 none 置信度", task_id=task_id))
            if layer == "uncertain" and confidence != "unconfirmed":
                issues.append(_issue("ATTRIBUTION_UNCERTAIN_MISMATCH", "uncertain 必须配套 unconfirmed", task_id=task_id))
            if analysis_type == "success_control" and (layer != "none" or confidence != "none"):
                issues.append(_issue(
                    "SUCCESS_CONTROL_ATTRIBUTION_INVALID",
                    "success_control 必须使用 none/none，不能写成模型或 Harness 失因",
                    task_id=task_id,
                ))
            if analysis_type != "success_control" and (layer == "none" or confidence == "none"):
                issues.append(_issue(
                    "FAILURE_ATTRIBUTION_INVALID",
                    "非成功对照任务必须填写实际归因层和归因置信度",
                    task_id=task_id,
                ))

        if not attribution_fields:
            issues.append(_issue(
                "ANALYSIS_LEGACY_FIELDS",
                "旧分析结果缺少结构化归因字段，结果可回填但未经完整质量校验",
                task_id=task_id,
                severity="warning",
            ))

        checkpoint_analysis = item.get("checkpoint_analysis")
        if checkpoint_analysis is None:
            issues.append(_issue(
                "CHECKPOINT_ANALYSIS_MISSING",
                "缺少逐检查点结构化分析，结果可回填但未经完整证据校验",
                task_id=task_id,
                severity="warning",
            ))
        elif not isinstance(checkpoint_analysis, list):
            issues.append(_issue(
                "CHECKPOINT_ANALYSIS_INVALID",
                "checkpoint_analysis 必须是数组",
                task_id=task_id,
            ))
        else:
            checkpoint_ids: list[str] = []
            expected_checkpoints = expected.get(task_id, {}).get("checkpoints") or {}
            for checkpoint in checkpoint_analysis:
                if not isinstance(checkpoint, dict) or not checkpoint.get("checkpoint"):
                    issues.append(_issue(
                        "CHECKPOINT_ENTRY_INVALID",
                        "逐检查点项必须包含 checkpoint",
                        task_id=task_id,
                    ))
                    continue
                checkpoint_id = str(checkpoint["checkpoint"])
                checkpoint_ids.append(checkpoint_id)
                checkpoint_score = checkpoint.get("score")
                if (
                    isinstance(checkpoint_score, bool)
                    or not isinstance(checkpoint_score, (int, float))
                    or not math.isfinite(float(checkpoint_score))
                ):
                    issues.append(_issue(
                        "CHECKPOINT_SCORE_INVALID",
                        f"检查点 {checkpoint_id} 的 score 必须是有限数值",
                        task_id=task_id,
                    ))
                expected_score = (
                    expected_checkpoints.get(checkpoint_id)
                    if isinstance(expected_checkpoints, dict)
                    else None
                )
                if (
                    expected_score is not None
                    and isinstance(checkpoint_score, (int, float))
                    and not isinstance(checkpoint_score, bool)
                    and not math.isclose(float(checkpoint_score), float(expected_score), abs_tol=1e-9)
                ):
                    issues.append(_issue(
                        "CHECKPOINT_SCORE_MISMATCH",
                        f"检查点 {checkpoint_id} 的 score={checkpoint_score}，manifest/score.json={expected_score}",
                        task_id=task_id,
                    ))
                if not isinstance(checkpoint.get("conclusion"), str) or not checkpoint["conclusion"].strip():
                    issues.append(_issue(
                        "CHECKPOINT_CONCLUSION_EMPTY",
                        f"检查点 {checkpoint_id} 缺少结论",
                        task_id=task_id,
                    ))
                evidence_refs = checkpoint.get("evidence_refs")
                if not isinstance(evidence_refs, list) or not evidence_refs:
                    issues.append(_issue(
                        "CHECKPOINT_EVIDENCE_MISSING",
                        f"检查点 {checkpoint_id} 缺少 evidence_refs",
                        task_id=task_id,
                    ))
                else:
                    for evidence_ref in evidence_refs:
                        if not isinstance(evidence_ref, dict) or not evidence_ref.get("source") or not evidence_ref.get("locator"):
                            issues.append(_issue(
                                "CHECKPOINT_EVIDENCE_INVALID",
                                f"检查点 {checkpoint_id} 的证据引用必须包含 source 和 locator",
                                task_id=task_id,
                            ))
            if len(checkpoint_ids) != len(set(checkpoint_ids)):
                issues.append(_issue(
                    "CHECKPOINT_DUPLICATE",
                    "checkpoint_analysis 存在重复检查点",
                    task_id=task_id,
                ))
            if isinstance(expected_checkpoints, dict):
                missing_checkpoints = sorted(set(expected_checkpoints) - set(checkpoint_ids))
                if missing_checkpoints:
                    issues.append(_issue(
                        "CHECKPOINT_COVERAGE_INCOMPLETE",
                        f"缺少检查点分析：{', '.join(missing_checkpoints)}",
                        task_id=task_id,
                    ))
                extra_checkpoints = sorted(set(checkpoint_ids) - set(expected_checkpoints))
                if extra_checkpoints:
                    issues.append(_issue(
                        "CHECKPOINT_OUT_OF_SCOPE",
                        f"存在 score.json 未定义的检查点：{', '.join(extra_checkpoints)}",
                        task_id=task_id,
                    ))

    missing_ids = sorted(allowed_ids - analyzed_ids)
    if missing_ids:
        severity = "warning" if allow_partial else "error"
        issues.append(_issue(
            "ANALYSIS_PARTIAL_COVERAGE",
            f"manifest 中有 {len(missing_ids)} 个任务尚未分析",
            severity=severity,
        ))

    source_status = "not_available"
    if source_records is not None:
        source_status, source_issues = _source_snapshot_status(source_records)
        issues.extend(source_issues)
        if source_status == "changed":
            source_status = "changed"

    errors = [item for item in issues if item["severity"] == "error"]
    warnings = [item for item in issues if item["severity"] == "warning"]
    ratio = len(analyzed_ids) / len(allowed_ids) if allowed_ids else (1.0 if analyzed_ids == set() else 0.0)
    if errors:
        status = "FAIL"
    elif warnings:
        status = "REVIEW"
    else:
        status = "PASS"
    if not allowed_ids:
        coverage_state = "unknown"
    elif missing_ids:
        coverage_state = "partial"
    else:
        coverage_state = "complete"
    return {
        "schema_version": 1,
        "status": status,
        "coverage": {
            "expected": len(allowed_ids),
            "analyzed": len(analyzed_ids & allowed_ids),
            "missing": len(missing_ids),
            "ratio": round(ratio, 4),
            "state": coverage_state,
        },
        "source_snapshot": source_status,
        "analyzed_task_ids": sorted(analyzed_ids),
        "missing_task_ids": missing_ids,
        "issues": issues,
    }


def load_manifest(path: str | Path) -> list[dict]:
    data = _read_json(Path(path))
    if not isinstance(data, list):
        raise ValueError("manifest 顶层必须是数组")
    return [item for item in data if isinstance(item, dict)]


def load_analysis(path: str | Path) -> dict:
    data = _read_json(Path(path))
    if not isinstance(data, dict):
        raise ValueError("analysis 顶层必须是对象")
    return data
