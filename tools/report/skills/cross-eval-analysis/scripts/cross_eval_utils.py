"""跨单元分析的确定性数据加载、比较和输出校验工具。"""

from __future__ import annotations

import re
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[5]
import sys

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.report.lib.eval_dataset.result_files import ResultRecord, discover_results  # noqa: E402
from tools.report.lib.eval_dataset.security import redact_text  # noqa: E402
from tools.report.lib.eval_dataset.task_files import parse_task_document  # noqa: E402


SCHEMA_VERSION = 1
ANALYSIS_SCHEMA_VERSION = 1
CONFIDENCES = {"confirmed", "probable", "unconfirmed"}
REQUIRED_CASE_FIELDS = (
    "task_id",
    "task_name",
    "what_tested",
    "score_summary",
    "problem",
    "evidence_summary",
    "confidence",
    "evidence_refs",
)
REQUIRED_FINDING_FIELDS = (
    "task_id",
    "task_name",
    "mechanism",
    "delta_pct_points",
    "evidence_refs",
)


def _display(registry: Any, kind: str, raw: str) -> str:
    if registry is None:
        return raw
    if kind == "model":
        return registry.model_display(raw)
    return registry.harness_display(raw)


def _task_file(tasks_dir: Path | None, category: str, task_id: str) -> Path | None:
    if tasks_dir is None:
        return None
    candidates = [
        tasks_dir / category / f"{task_id}.md",
        tasks_dir / "extension" / category / f"{task_id}.md",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    for base in (tasks_dir, tasks_dir / "extension"):
        if not base.is_dir():
            continue
        matches = list(base.rglob(f"{task_id}.md"))
        if matches:
            return sorted(matches)[0]
    return None


def _prompt_summary(document: Any) -> str:
    for name in ("Prompt", "任务", "Task", "Description", "任务描述"):
        text = document.section(name)
        if text:
            return " ".join(text.split())[:400]
    return ""


def load_task_metadata(tasks_dir: Path | None, category: str, task_id: str) -> dict[str, Any]:
    path = _task_file(tasks_dir, category, task_id)
    if path is None:
        return {
            "task_id": task_id,
            "task_name": task_id,
            "category": category,
            "difficulty": "",
            "modality": "",
            "tags": [],
            "what_tested": "任务定义文件未找到，无法确认题目考察点",
            "task_file": "",
        }
    try:
        document = parse_task_document(path)
    except (OSError, UnicodeError):
        return {
            "task_id": task_id,
            "task_name": task_id,
            "category": category,
            "difficulty": "",
            "modality": "",
            "tags": [],
            "what_tested": "任务定义文件无法解析，无法确认题目考察点",
            "task_file": str(path),
        }
    metadata = document.metadata
    tags = metadata.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    if not isinstance(tags, list):
        tags = []
    return {
        "task_id": task_id,
        "task_name": str(metadata.get("name") or task_id),
        "category": str(metadata.get("category") or category),
        "difficulty": str(metadata.get("difficulty") or ""),
        "modality": str(metadata.get("modality") or ""),
        "tags": [str(tag) for tag in tags],
        "what_tested": _prompt_summary(document),
        "task_file": str(path),
    }


def _numeric_checkpoints(score_data: dict[str, Any]) -> dict[str, float]:
    return {
        str(key): float(value)
        for key, value in score_data.items()
        if key != "overall_score"
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
    }


def _judge_notes(score_data: dict[str, Any]) -> str:
    lines: list[str] = []

    def visit(prefix: str, value: Any) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                visit(f"{prefix}{key}.", nested)
        elif isinstance(value, str) and value.strip() and re.search(r"reason|error", prefix, re.I):
            lines.append(f"{prefix[:-1]}: {value.strip()}")

    visit("", score_data)
    return redact_text("\n".join(lines), max_length=1600)


def _capability_usable(record: ResultRecord) -> bool:
    if record.score is None:
        return False
    if record.usable:
        return True
    anomaly = record.anomalies
    if not isinstance(anomaly, dict) or anomaly.get("has_validity_failure"):
        return False
    return any(
        isinstance(item, dict)
        and item.get("validity_impact") == "none"
        and item.get("score_reliability") == "valid_capability_outcome"
        and item.get("attribution") in {"model", "harness"}
        for item in anomaly.get("items", [])
    )


def _record_snapshot(record: ResultRecord) -> dict[str, Any]:
    execution = record.execution or {}
    execution_status = str(execution.get("status") or "").lower()
    execution_usable = (
        execution_status in {"finished", "success", "succeeded", "completed"}
        and execution.get("exit_code") in (None, 0)
    )
    return {
        "run_name": record.run_name,
        "run_dir": str(record.run_dir),
        "score_path": str(record.score_path) if record.score_path else "",
        "transcript": next(
            (str(record.run_dir / name) for name in ("chat_openclaw.jsonl", "chat.jsonl")
             if (record.run_dir / name).is_file()),
            "",
        ),
        "agent_interaction": (
            str(record.run_dir / "agent_interaction.jsonl")
            if (record.run_dir / "agent_interaction.jsonl").is_file() else ""
        ),
        "score": record.score,
        "checkpoints": _numeric_checkpoints(record.score_data),
        "judge_notes": _judge_notes(record.score_data),
        "status": execution.get("status") or "",
        "timed_out": bool(execution.get("timed_out")),
        "execution_error": str(execution.get("error") or ""),
        "validity": record.validity,
        "execution_usable": execution_usable,
        "usable": _capability_usable(record),
    }


def _aggregate_records(records: list[ResultRecord]) -> dict[str, Any]:
    usable = [record for record in records if _capability_usable(record)]
    ordered = sorted(records, key=lambda record: record.run_name)
    scores = [float(record.score) for record in usable]
    value = statistics.fmean(scores) if scores else None
    checkpoint_values: dict[str, list[float]] = defaultdict(list)
    for record in usable:
        for key, score in _numeric_checkpoints(record.score_data).items():
            checkpoint_values[key].append(score)
    checkpoints = {
        key: round(statistics.fmean(values), 6)
        for key, values in sorted(checkpoint_values.items())
    }
    return {
        "score": round(value, 6) if value is not None else None,
        "score_pct": round(value * 100, 2) if value is not None else None,
        "run_count": len(usable),
        "run_names": [record.run_name for record in ordered],
        "checkpoints": checkpoints,
        "records": [_record_snapshot(record) for record in ordered],
        "comparable": value is not None,
    }


def _unit_task_records(records: Iterable[ResultRecord]) -> dict[str, dict[str, list[ResultRecord]]]:
    grouped: dict[str, dict[str, list[ResultRecord]]] = defaultdict(lambda: defaultdict(list))
    for record in records:
        grouped[record.unit][record.task_id].append(record)
    return grouped


def _direction(delta: float | None) -> str:
    if delta is None:
        return "not_comparable"
    if abs(delta) < 1e-9:
        return "tie"
    return "target_higher" if delta > 0 else "target_lower"


def build_manifest(
    result_root: str | Path,
    *,
    axis: str,
    fixed_model: str | None = None,
    fixed_harness: str | None = None,
    models: list[str] | None = None,
    harnesses: list[str] | None = None,
    target_model: str | None = None,
    target_harness: str | None = None,
    tasks_dir: str | Path | None = None,
    task_ids: Iterable[str] | None = None,
    registry: Any = None,
) -> dict[str, Any]:
    """构建固定控制变量下的逐用例比较 manifest。"""
    if axis not in {"model", "harness"}:
        raise ValueError("axis 必须是 model 或 harness")
    if axis == "model":
        if not fixed_harness or not models or len(models) < 2:
            raise ValueError("模型对比需要 fixed_harness 和至少两个 models")
        selected_units = [(model, fixed_harness) for model in models]
        if target_model and target_model not in models:
            raise ValueError("target_model 必须包含在 models 中")
        target_unit = f"{target_model or models[0]}@{fixed_harness}"
        fixed = {"harness": fixed_harness}
    else:
        if not fixed_model or not harnesses or len(harnesses) < 2:
            raise ValueError("Harness 对比需要 fixed_model 和至少两个 harnesses")
        selected_units = [(fixed_model, harness) for harness in harnesses]
        if target_harness and target_harness not in harnesses:
            raise ValueError("target_harness 必须包含在 harnesses 中")
        target_unit = f"{fixed_model}@{target_harness or harnesses[0]}"
        fixed = {"model": fixed_model}

    root = Path(result_root).expanduser().resolve()
    discovery = discover_results([root])
    available = {record.unit for record in discovery.records}
    required = {f"{model}@{harness}" for model, harness in selected_units}
    missing_units = sorted(required - available)
    if missing_units:
        raise ValueError(f"结果目录缺少参评单元：{', '.join(missing_units)}")

    task_root = Path(tasks_dir).expanduser().resolve() if tasks_dir else None
    grouped = _unit_task_records(
        record for record in discovery.records if record.unit in required
    )
    selected_locations = {
        str(record.run_dir)
        for record in discovery.records
        if record.unit in required
    }
    selected_records = [record for record in discovery.records if record.unit in required]
    usable_ids = {
        unit: {
            task_id for task_id, records in grouped.get(unit, {}).items()
            if any(_capability_usable(record) for record in records)
        }
        for unit in sorted(required)
    }
    common_ids = set.intersection(*(ids for ids in usable_ids.values())) if usable_ids else set()
    requested_ids = {str(task_id) for task_id in (task_ids or []) if str(task_id).strip()}
    if requested_ids:
        effective_ids = common_ids & requested_ids
        missing_requested = sorted(requested_ids - effective_ids)
        scope_mode = "task_ids_intersection"
        scope_note = f"指定任务与参评单元有效结果交集，共 {len(effective_ids)} 例"
    else:
        effective_ids = common_ids
        missing_requested = []
        scope_mode = "intersection"
        scope_note = f"参评单元有效结果交集，共 {len(effective_ids)} 例"
    if not effective_ids:
        raise ValueError("没有可比较的共同有效任务")

    metadata_cache: dict[tuple[str, str], dict[str, Any]] = {}
    comparisons: list[dict[str, Any]] = []
    ordered_units = [f"{model}@{harness}" for model, harness in selected_units]
    for task_id in sorted(effective_ids):
        category = ""
        for unit in ordered_units:
            records = grouped[unit].get(task_id, [])
            if records:
                category = records[0].category
                break
        metadata_key = (category, task_id)
        metadata_cache.setdefault(
            metadata_key, load_task_metadata(task_root, category, task_id)
        )
        scores = {
            unit: _aggregate_records(grouped[unit][task_id])
            for unit in ordered_units
        }
        target_score = scores[target_unit]["score"]
        pairwise: list[dict[str, Any]] = []
        for reference_unit in ordered_units:
            if reference_unit == target_unit:
                continue
            reference_score = scores[reference_unit]["score"]
            delta = (
                round(target_score - reference_score, 6)
                if target_score is not None and reference_score is not None else None
            )
            pairwise.append({
                "target_unit": target_unit,
                "reference_unit": reference_unit,
                "delta": delta,
                "delta_pct_points": round(delta * 100, 2) if delta is not None else None,
                "direction": _direction(delta),
            })
        comparisons.append({
            **metadata_cache[metadata_key],
            "scores": scores,
            "pairwise": pairwise,
        })

    overall = {
        unit: _aggregate_records(
            [record for task_id in effective_ids for record in grouped[unit].get(task_id, [])]
        )
        for unit in ordered_units
    }
    units = []
    for model, harness in selected_units:
        raw_unit = f"{model}@{harness}"
        units.append({
            "unit": raw_unit,
            "model": model,
            "harness": harness,
            "model_display": _display(registry, "model", model),
            "harness_display": _display(registry, "harness", harness),
            "role": "target" if raw_unit == target_unit else "reference",
        })

    issues: list[dict[str, Any]] = [
        issue.to_dict()
        for issue in discovery.issues
        if (
            not issue.location
            or (
                issue.location in selected_locations
                and not any(
                    str(record.run_dir) == issue.location
                    and _capability_usable(record)
                    for record in selected_records
                )
            )
        )
    ]
    for record in selected_records:
        if (
            _capability_usable(record)
            and record.validity == "capability_outcome"
            and record.execution.get("timed_out")
        ):
            issues.append({
                "code": "CAPABILITY_TIMEOUT_INCLUDED",
                "severity": "warning",
                "message": "任务虽达到超时上限，但异常分析将其判定为可用于能力比较的模型/Harness结果",
                "unit": record.unit,
                "task_id": record.task_id,
                "location": str(record.run_dir),
                "evidence": {
                    "status": record.execution.get("status") or "",
                    "timeout_seconds": record.execution.get("timeout_seconds"),
                    "score_reliability": "valid_capability_outcome",
                },
            })
    if missing_requested:
        issues.append({
            "code": "REQUESTED_TASK_NOT_COMPARABLE",
            "severity": "warning",
            "message": "指定任务缺少参评单元的共同有效结果",
            "task_ids": missing_requested,
        })
    for unit, task_ids_for_unit in usable_ids.items():
        missing = sorted(effective_ids - task_ids_for_unit)
        if missing:
            issues.append({
                "code": "UNIT_TASK_COVERAGE_GAP",
                "severity": "warning",
                "message": f"{unit} 在比较范围内存在无有效得分任务",
                "unit": unit,
                "task_ids": missing,
            })

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "cross_eval_manifest",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "result_root": str(root),
        "axis": axis,
        "fixed": fixed,
        "target_unit": target_unit,
        "units": units,
        "scope": {
            "mode": scope_mode,
            "note": scope_note,
            "task_count": len(comparisons),
            "task_ids": sorted(effective_ids),
            "missing_requested_task_ids": missing_requested,
        },
        "summary": {
            "overall": overall,
            "unit_count": len(units),
        },
        "comparisons": comparisons,
        "issues": issues,
    }


def _evidence_valid(ref: Any) -> bool:
    return (
        isinstance(ref, dict)
        and bool(str(ref.get("source") or "").strip())
        and bool(str(ref.get("locator") or "").strip())
        and bool(str(ref.get("excerpt") or "").strip())
    )


def _field_present(item: dict[str, Any], field: str) -> bool:
    value = item.get(field)
    if value is None:
        return False
    return not isinstance(value, str) or bool(value.strip())


def validate_analysis(manifest: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    """校验 Workflow 输出是否覆盖 manifest 且具备可追溯证据字段。"""
    issues: list[dict[str, Any]] = []
    if not isinstance(manifest, dict) or manifest.get("kind") != "cross_eval_manifest":
        issues.append({"code": "MANIFEST_INVALID", "severity": "error", "message": "manifest 类型无效"})
        return {"schema_version": ANALYSIS_SCHEMA_VERSION, "status": "FAIL", "issues": issues}
    task_ids = set(manifest.get("scope", {}).get("task_ids") or [])
    task_index = {
        str(item.get("task_id")): item
        for item in manifest.get("comparisons", [])
        if isinstance(item, dict) and item.get("task_id")
    }
    units = {str(item.get("unit")) for item in manifest.get("units", []) if item.get("unit")}
    if not isinstance(analysis, dict):
        issues.append({"code": "ANALYSIS_INVALID", "severity": "error", "message": "analysis 顶层必须是对象"})
        return {"schema_version": ANALYSIS_SCHEMA_VERSION, "status": "FAIL", "issues": issues}
    if analysis.get("schema_version") != ANALYSIS_SCHEMA_VERSION:
        issues.append({"code": "ANALYSIS_SCHEMA_VERSION_INVALID", "severity": "error", "message": "analysis schema_version 无效"})
    if not isinstance(analysis.get("executive_summary"), str) or not analysis["executive_summary"].strip():
        issues.append({"code": "EXECUTIVE_SUMMARY_EMPTY", "severity": "error", "message": "缺少 executive_summary"})
    pair_reports = analysis.get("pair_reports")
    if not isinstance(pair_reports, list) or not pair_reports:
        issues.append({"code": "PAIR_REPORTS_EMPTY", "severity": "error", "message": "缺少 pair_reports"})
        pair_reports = []
    expected_pairs = {
        (manifest["target_unit"], unit)
        for unit in units
        if unit != manifest["target_unit"]
    }
    actual_pairs: set[tuple[str, str]] = set()
    for pair in pair_reports:
        if not isinstance(pair, dict):
            issues.append({"code": "PAIR_REPORT_INVALID", "severity": "error", "message": "pair_report 必须是对象"})
            continue
        target = str(pair.get("target_unit") or "")
        reference = str(pair.get("reference_unit") or "")
        actual_pairs.add((target, reference))
        if (target, reference) not in expected_pairs:
            issues.append({"code": "PAIR_OUT_OF_SCOPE", "severity": "error", "message": f"pair 不在 manifest 范围：{target} vs {reference}"})
        if not isinstance(pair.get("summary"), str) or not pair["summary"].strip():
            issues.append({"code": "PAIR_SUMMARY_EMPTY", "severity": "error", "message": "pair 缺少简明总结", "pair": [target, reference]})
        for field in ("strengths", "weaknesses"):
            values = pair.get(field, [])
            if not isinstance(values, list):
                issues.append({"code": "PAIR_FINDINGS_INVALID", "severity": "error", "message": f"{field} 必须是数组", "pair": [target, reference]})
                continue
            for finding in values:
                if not isinstance(finding, dict):
                    issues.append({"code": "FINDING_INVALID", "severity": "error", "message": "强弱项必须是对象", "pair": [target, reference]})
                    continue
                missing = [field for field in REQUIRED_FINDING_FIELDS if not _field_present(finding, field)]
                if missing:
                    issues.append({"code": "FINDING_FIELDS_MISSING", "severity": "error", "message": f"强弱项缺少字段：{', '.join(missing)}", "pair": [target, reference]})
                delta = finding.get("delta_pct_points")
                if not isinstance(delta, (int, float)) or isinstance(delta, bool):
                    issues.append({"code": "FINDING_DELTA_INVALID", "severity": "error", "message": "强弱项 delta_pct_points 必须是数字", "pair": [target, reference]})
                finding_task_id = finding.get("task_id")
                if not isinstance(finding_task_id, str) or finding_task_id not in task_ids:
                    issues.append({"code": "FINDING_TASK_INVALID", "severity": "error", "message": "强弱项必须引用 manifest 中的完整 task_id", "pair": [target, reference]})
                    continue
                expected_name = str(task_index.get(finding_task_id, {}).get("task_name") or "")
                if expected_name and finding.get("task_name") != expected_name:
                    issues.append({"code": "FINDING_TASK_NAME_MISMATCH", "severity": "error", "message": "强弱项 task_name 与 manifest 不一致", "task_id": finding_task_id})
                refs = finding.get("evidence_refs")
                if not isinstance(refs, list) or not refs or not all(_evidence_valid(ref) for ref in refs):
                    issues.append({"code": "FINDING_EVIDENCE_MISSING", "severity": "error", "message": "强弱项缺少 source/locator 证据", "task_id": finding.get("task_id")})
        cases = pair.get("typical_cases", [])
        if not isinstance(cases, list):
            issues.append({"code": "CASES_INVALID", "severity": "error", "message": "typical_cases 必须是数组", "pair": [target, reference]})
            continue
        for case in cases:
            if not isinstance(case, dict):
                issues.append({"code": "CASE_INVALID", "severity": "error", "message": "典型案例必须是对象"})
                continue
            missing = [field for field in REQUIRED_CASE_FIELDS if not _field_present(case, field)]
            if missing:
                issues.append({"code": "CASE_FIELDS_MISSING", "severity": "error", "message": f"典型案例缺少字段：{', '.join(missing)}", "task_id": case.get("task_id", "")})
            case_task_id = case.get("task_id")
            if not isinstance(case_task_id, str) or case_task_id not in task_ids:
                issues.append({"code": "CASE_TASK_OUT_OF_SCOPE", "severity": "error", "message": "典型案例 task_id 不在比较范围", "task_id": case.get("task_id", "")})
            else:
                expected_name = str(task_index.get(case_task_id, {}).get("task_name") or "")
                if expected_name and case.get("task_name") != expected_name:
                    issues.append({"code": "CASE_TASK_NAME_MISMATCH", "severity": "error", "message": "典型案例 task_name 与 manifest 不一致", "task_id": case_task_id})
            refs = case.get("evidence_refs")
            if not isinstance(refs, list) or not refs or not all(_evidence_valid(ref) for ref in refs):
                issues.append({"code": "CASE_EVIDENCE_MISSING", "severity": "error", "message": "典型案例缺少完整证据引用", "task_id": case.get("task_id", "")})
            confidence = case.get("confidence")
            if not isinstance(confidence, str) or confidence not in CONFIDENCES:
                issues.append({"code": "CASE_CONFIDENCE_INVALID", "severity": "error", "message": f"典型案例置信度无效：{confidence}", "task_id": case.get("task_id", "")})
    comparability_analysis = analysis.get("comparability_analysis")
    if comparability_analysis is not None and not isinstance(comparability_analysis, dict):
        issues.append({"code": "COMPARABILITY_ANALYSIS_INVALID", "severity": "error", "message": "comparability_analysis 必须是对象"})
    elif isinstance(comparability_analysis, dict):
        impact_rows = comparability_analysis.get("impact_rows", [])
        if not isinstance(impact_rows, list) or not all(isinstance(item, dict) for item in impact_rows):
            issues.append({"code": "COMPARABILITY_IMPACT_INVALID", "severity": "error", "message": "comparability_analysis.impact_rows 必须是对象数组"})
    if not isinstance(analysis.get("unconfirmed_items"), list):
        issues.append({"code": "UNCONFIRMED_ITEMS_INVALID", "severity": "error", "message": "unconfirmed_items 必须是数组"})
    for pair in sorted(expected_pairs - actual_pairs):
        issues.append({"code": "PAIR_COVERAGE_INCOMPLETE", "severity": "error", "message": f"缺少 Harness/模型配对分析：{pair[0]} vs {pair[1]}"})
    status = "FAIL" if any(item["severity"] == "error" for item in issues) else ("REVIEW" if issues else "PASS")
    return {
        "schema_version": ANALYSIS_SCHEMA_VERSION,
        "status": status,
        "manifest_task_count": len(task_ids),
        "pair_count": len(pair_reports),
        "issues": issues,
    }


def render_markdown(manifest: dict[str, Any], analysis: dict[str, Any]) -> str:
    """把已校验的结构化分析渲染成领导/研发可读的 Markdown。"""
    def cell(value: Any) -> str:
        text = "" if value is None else str(value)
        return " ".join(text.split()).replace("|", "\\|")

    def evidence_text(item: dict[str, Any]) -> str:
        refs = []
        for ref in item.get("evidence_refs", []):
            source = str(ref.get("source", ""))
            source_name = source.replace("\\", "/").rsplit("/", 1)[-1]
            refs.append(
                f"{source_name}（{ref.get('locator', '')}）：{ref.get('excerpt', '')}"
            )
        summary = item.get("evidence_summary", "")
        return cell(summary) + ("<br>" + "<br>".join(cell(ref) for ref in refs) if refs else "")

    def score_cell(value: Any) -> str:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return f"{value:.2f}"
        return cell(value)

    units = {item["unit"]: item for item in manifest.get("units", [])}
    target = manifest.get("target_unit", "")
    target_display = units.get(target, {}).get("model_display", target)
    if units.get(target, {}).get("harness_display"):
        target_display += "@" + units[target]["harness_display"]
    lines = [
        "# WildClawBench 跨单元逐用例对比分析",
        "",
        f"- **分析对象**：{target_display}",
        f"- **控制变量**：{manifest.get('axis', '-')}",
        f"- **比较范围**：{manifest.get('scope', {}).get('note', '-')}",
        "",
        "## 评测结论",
        "",
        str(analysis.get("executive_summary", "")).strip(),
        "",
    ]
    for index, pair in enumerate(analysis.get("pair_reports", []), 1):
        target_name = units.get(pair.get("target_unit"), {}).get("model_display", pair.get("target_unit", ""))
        reference_name = units.get(pair.get("reference_unit"), {}).get("model_display", pair.get("reference_unit", ""))
        if manifest.get("axis") == "model":
            target_name = units.get(pair.get("target_unit"), {}).get("model_display", pair.get("target_unit", ""))
            reference_name = units.get(pair.get("reference_unit"), {}).get("model_display", pair.get("reference_unit", ""))
        else:
            target_name = units.get(pair.get("target_unit"), {}).get("harness_display", pair.get("target_unit", ""))
            reference_name = units.get(pair.get("reference_unit"), {}).get("harness_display", pair.get("reference_unit", ""))
        lines.extend([
            f"## {index}. {target_name} vs {reference_name}",
            "",
            str(pair.get("summary", "")).strip(),
            "",
            "### 逐用例差异摘要",
            "",
            "| 结论 | 用例ID | 用例名称 | 得分变化 | 说明 |",
            "|---|---|---|---:|---|",
        ])
        findings = list(pair.get("strengths", [])) + list(pair.get("weaknesses", []))
        for finding in findings:
            score_delta = finding.get("delta_pct_points", finding.get("delta", "-"))
            lines.append(
                f"| {cell(finding.get('label', '差异'))} | {cell(finding.get('task_id', ''))} | "
                f"{cell(finding.get('task_name', ''))} | {cell(score_delta)} | "
                f"{cell(finding.get('mechanism', finding.get('conclusion', '')))} |"
            )
        lines.extend(["", "### 典型案例", ""])
        for case_index, case in enumerate(pair.get("typical_cases", []), 1):
            lines.extend([
                f"#### 案例{case_index}：{case.get('task_name', '')}（{case.get('task_id', '')}）",
                "",
                "| 项目 | 内容 |",
                "|---|---|",
                f"| 用例ID | {cell(case.get('task_id', ''))} |",
                f"| 用例名称 | {cell(case.get('task_name', ''))} |",
                f"| 题目简述 | {cell(case.get('what_tested', ''))} |",
                f"| 得分对比 | {cell(case.get('score_summary', ''))} |",
                f"| 问题点 | {cell(case.get('problem', ''))} |",
                f"| 证据 | {evidence_text(case)} |",
                f"| 结论置信度 | {cell(case.get('confidence', ''))} |",
                "",
            ])
    comparability_analysis = analysis.get("comparability_analysis") or {}
    unconfirmed_items = analysis.get("unconfirmed_items") or []
    if comparability_analysis or unconfirmed_items:
        lines.extend([
            "## 附录：异常与不可比结果",
            "",
        ])
        summary = str(comparability_analysis.get("summary", "")).strip()
        if summary:
            lines.extend([summary, ""])
        impact_rows = comparability_analysis.get("impact_rows", [])
        if impact_rows:
            lines.extend([
                "### 排除口径对均分的影响",
                "",
                f"| 口径 | 用例数 | {cell(target_name)} | {cell(reference_name)} | 分差 | 说明 |",
                "|---|---:|---:|---:|---:|---|",
            ])
            for row in impact_rows:
                lines.append(
                    f"| {cell(row.get('scope', ''))} | {cell(row.get('task_count', ''))} | "
                    f"{score_cell(row.get('target_score', ''))} | {score_cell(row.get('reference_score', ''))} | "
                    f"{score_cell(row.get('delta_pct_points', ''))} | {cell(row.get('note', ''))} |"
                )
            lines.append("")
        scope_note = str(comparability_analysis.get("scope_note", "")).strip()
        if scope_note:
            lines.extend([scope_note, ""])
        for item_index, item in enumerate(unconfirmed_items, 1):
            task_id = item.get("task_id", "")
            task_name = item.get("task_name") or task_id
            lines.extend([
                f"### A{item_index}. {task_name}（{task_id}）",
                "",
                "| 项目 | 内容 |",
                "|---|---|",
                f"| 归类 | {cell(item.get('label', item.get('status', '待确认')))} |",
                f"| 得分对比 | {cell(item.get('score_summary', ''))} |",
                f"| 判定依据 | {cell(item.get('reason', ''))} |",
                f"| 处理结论 | {cell(item.get('conclusion', ''))} |",
                f"| 证据 | {evidence_text(item)} |",
                "",
            ])
    return "\n".join(lines).rstrip() + "\n"
