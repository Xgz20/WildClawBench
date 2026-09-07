"""外部评测结果目录发现与 run 归一化。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from src.utils.anomalies import (
    RULESET_VERSION as ANOMALY_RULESET_VERSION,
    SCHEMA_VERSION as ANOMALY_SCHEMA_VERSION,
    scan_run_dir,
)
from src.utils.run_selection import select_effective_run_dirs

from .contracts import FAIL, Issue


@dataclass
class ResultRecord:
    result_root: Path
    run_dir: Path
    score_path: Path | None
    model: str
    harness: str
    category: str
    task_id: str
    run_name: str
    score: float | None = None
    score_data: dict[str, Any] = field(default_factory=dict)
    execution: dict[str, Any] = field(default_factory=dict)
    usage: dict[str, Any] = field(default_factory=dict)
    anomalies: dict[str, Any] = field(default_factory=dict)
    usable: bool = False
    validity: str = "unknown"

    @property
    def unit(self) -> str:
        return f"{self.model}@{self.harness}"


@dataclass
class ResultDiscovery:
    records: list[ResultRecord] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    roots: list[Path] = field(default_factory=list)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}


def _is_current_anomaly_snapshot(value: dict[str, Any]) -> bool:
    """Return whether a persisted anomaly snapshot is safe to reuse as-is."""
    verdict = value.get("validity_verdict")
    items = value.get("items")
    return (
        value.get("schema_version") == ANOMALY_SCHEMA_VERSION
        and value.get("ruleset_version") == ANOMALY_RULESET_VERSION
        and verdict in {"PASS", "REVIEW", "FAIL"}
        and isinstance(value.get("has_validity_failure"), bool)
        and value.get("has_validity_failure") == (verdict == "FAIL")
        and isinstance(items, list)
        and all(isinstance(item, dict) for item in items)
    )


def _failed_anomaly_snapshot(error_type: str) -> dict[str, Any]:
    """Build a fail-closed in-memory snapshot when current rules cannot run."""
    return {
        "schema_version": ANOMALY_SCHEMA_VERSION,
        "ruleset_version": ANOMALY_RULESET_VERSION,
        "validity_verdict": "FAIL",
        "is_anomalous": True,
        "has_error": True,
        "has_validity_failure": True,
        "has_model_or_harness_issue": False,
        "needs_review": False,
        "needs_rerun": False,
        "items": [{
            "id": "ANOMALY_REFRESH_FAILED",
            "stage": "result_discovery",
            "attribution": "evaluation_framework",
            "confidence": "high",
            "validity_impact": "fail",
            "score_reliability": "unreliable",
            "rerun_action": "review_first",
            "description": "无法使用当前异常规则校验该结果",
            "evidence": [{"error_type": error_type}],
        }],
    }


class _CurrentAnomalyLoader:
    """Load current anomaly conclusions once without rewriting result dirs."""

    def __init__(self) -> None:
        self._cache: dict[Path, dict[str, Any]] = {}
        self._failures: dict[Path, dict[str, str]] = {}

    def load(self, run_dir: Path) -> dict[str, Any]:
        run_dir = Path(run_dir)
        if run_dir in self._cache:
            return self._cache[run_dir]

        persisted = _load_json(run_dir / "anomalies.json")
        if _is_current_anomaly_snapshot(persisted):
            snapshot = persisted
        else:
            try:
                snapshot = scan_run_dir(run_dir)
                if not _is_current_anomaly_snapshot(snapshot):
                    raise ValueError(
                        "scan_run_dir returned an invalid current anomaly snapshot"
                    )
            except Exception as exc:  # discovery must fail closed
                self._failures[run_dir] = {
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:500],
                }
                snapshot = _failed_anomaly_snapshot(type(exc).__name__)

        self._cache[run_dir] = snapshot
        return snapshot

    def load_for_selection(self, run_dir: Path) -> dict[str, Any]:
        snapshot = self.load(run_dir)
        if run_dir in self._failures:
            # Loader errors must not be mistaken for implicit supersession.
            # The selected record is then rejected by the fail-closed snapshot.
            raise ValueError("current anomaly refresh failed")
        return snapshot

    def failure_for(self, run_dir: Path) -> dict[str, str] | None:
        return self._failures.get(Path(run_dir))


def _score_value(data: dict[str, Any]) -> float | None:
    for key in ("overall_score", "score", "total_score", "final_score"):
        value = data.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    # Some exports use a nested aggregate.
    for key in ("_grading", "grading", "summary"):
        nested = data.get(key)
        if isinstance(nested, dict):
            value = _score_value(nested)
            if value is not None:
                return value
    return None


def _strip_model(value: str) -> str:
    value = value.strip()
    return re.sub(r"^(?:openrouter|anthropic|openai|google|deepseek)/", "", value)


def _metadata_for_run(run_dir: Path) -> dict[str, Any]:
    return _load_json(run_dir / "run_metadata.json")


def _is_capability_outcome(anomalies: dict[str, Any]) -> bool:
    if not isinstance(anomalies, dict) or anomalies.get("has_validity_failure"):
        return False
    return any(
        isinstance(item, dict)
        and item.get("attribution") in {"model", "harness"}
        and item.get("validity_impact") == "none"
        and item.get("score_reliability") == "valid_capability_outcome"
        for item in anomalies.get("items", [])
    )


def _infer_identity(run_dir: Path, execution: dict[str, Any]) -> tuple[str, str, str, str]:
    task_dir = run_dir.parent
    category_dir = task_dir.parent
    harness_dir = category_dir.parent
    model_dir = harness_dir.parent
    task_id = str(execution.get("task_id") or task_dir.name)
    # The runner's task_id includes a model/timestamp suffix; the directory is
    # the canonical task ID and is used for alignment with tasks/.
    if task_dir.name and task_dir.name != task_id and re.search(r"_\d{8}_\d{4}_", task_id):
        task_id = task_dir.name
    model = _strip_model(str(execution.get("model") or model_dir.name))
    harness = str(execution.get("harness") or harness_dir.name)
    category = str(execution.get("category") or category_dir.name)
    return model, harness, category, task_id


def discover_results(result_roots: Iterable[str | Path]) -> ResultDiscovery:
    discovery = ResultDiscovery()
    anomaly_loader = _CurrentAnomalyLoader()
    groups: dict[tuple[Path, str, str, str, str], list[Path]] = {}
    for raw_root in result_roots:
        root = Path(raw_root).expanduser().resolve()
        discovery.roots.append(root)
        if not root.exists() or not root.is_dir():
            discovery.issues.append(Issue(FAIL, "RESULT_ROOT_NOT_FOUND", f"评测结果目录不存在: {root}", location=str(root)))
            continue
        run_dirs = {path.parent for path in root.rglob("score.json")}
        # A run with execution_status but no score is still evidence of a
        # missing/invalid result and must not silently disappear.
        run_dirs.update(path.parent for path in root.rglob("execution_status.json"))
        for run_dir in sorted(run_dirs):
            execution = _load_json(run_dir / "execution_status.json")
            model, harness, category, task_id = _infer_identity(run_dir, execution)
            key = (root, model, harness, category, task_id)
            groups.setdefault(key, []).append(run_dir)

    for (root, model, harness, category, task_id), run_dirs in sorted(groups.items(), key=lambda item: str(item[0])):
        effective = select_effective_run_dirs(
            run_dirs,
            anomaly_loader=anomaly_loader.load_for_selection,
        )
        for run_dir in effective:
            score_path = run_dir / "score.json"
            score_data = _load_json(score_path)
            execution = _load_json(run_dir / "execution_status.json")
            usage = _load_json(run_dir / "usage.json")
            anomalies = anomaly_loader.load(run_dir)
            score = _score_value(score_data)
            execution_status = str(execution.get("status") or "unknown").lower()
            exit_code = execution.get("exit_code")
            usable_execution = execution_status in {"finished", "success", "succeeded", "completed"} and exit_code in (None, 0)
            grading = score_data.get("_grading")
            grading = grading if isinstance(grading, dict) else {}
            grading_status = str(grading.get("status") or "").lower()
            score_reliability = str(grading.get("score_reliability") or "").lower()
            usable_grading = (
                grading_status not in {"evaluator_failed", "judge_failed"}
                and not score_reliability.startswith("unreliable")
            )
            anomaly_validity_failure = bool(anomalies.get("has_validity_failure"))
            capability_outcome = (
                score is not None
                and usable_grading
                and not anomaly_validity_failure
                and not usable_execution
                and _is_capability_outcome(anomalies)
            )
            usable = score is not None and usable_grading and not anomaly_validity_failure and (
                usable_execution or capability_outcome
            )
            validity = (
                "evaluator_error"
                if not usable_grading
                else "validity_failure"
                if anomaly_validity_failure
                else "valid"
                if usable_execution and score is not None
                else "capability_outcome"
                if capability_outcome
                else "execution_error"
                if not usable_execution
                else "missing_score"
            )
            record = ResultRecord(root, run_dir, score_path if score_path.is_file() else None, model, harness, category, task_id, run_dir.name, score, score_data, execution, usage, anomalies, usable, validity)
            discovery.records.append(record)
            anomaly_refresh_failure = anomaly_loader.failure_for(run_dir)
            if anomaly_refresh_failure:
                discovery.issues.append(Issue(
                    FAIL,
                    "RESULT_ANOMALY_REFRESH_FAILED",
                    f"无法使用当前异常规则校验结果: {run_dir}",
                    task_id=task_id,
                    location=str(run_dir),
                    evidence={
                        "required_schema_version": ANOMALY_SCHEMA_VERSION,
                        "required_ruleset_version": ANOMALY_RULESET_VERSION,
                        **anomaly_refresh_failure,
                    },
                ))
            if score is None:
                discovery.issues.append(Issue(FAIL, "RESULT_SCORE_MISSING", f"结果缺少可解析分数: {run_dir}", task_id=task_id, location=str(run_dir)))
            if not usable_grading:
                discovery.issues.append(Issue(
                    FAIL,
                    "RESULT_EVALUATOR_INVALID",
                    f"结果评分器状态不可用于能力比较: {run_dir}",
                    task_id=task_id,
                    location=str(run_dir),
                    evidence={
                        "grading_status": grading_status,
                        "score_reliability": score_reliability,
                        "partial_overall_score": grading.get("partial_overall_score"),
                    },
                ))
            elif anomaly_validity_failure and not anomaly_refresh_failure:
                anomaly_ids = [
                    str(item.get("id") or item.get("code"))
                    for item in anomalies.get("items", [])
                    if isinstance(item, dict) and (item.get("id") or item.get("code"))
                ]
                discovery.issues.append(Issue(
                    FAIL,
                    "RESULT_VALIDITY_INVALID",
                    f"结果异常检测判定为有效性失败: {run_dir}",
                    task_id=task_id,
                    location=str(run_dir),
                    evidence={
                        "validity_verdict": anomalies.get("validity_verdict"),
                        "needs_rerun": anomalies.get("needs_rerun"),
                        "anomaly_ids": anomaly_ids,
                    },
                ))
            elif not usable_execution and not capability_outcome:
                discovery.issues.append(Issue(FAIL, "RESULT_EXECUTION_INVALID", f"结果执行状态不可用于能力比较: {run_dir}", task_id=task_id, location=str(run_dir), evidence={"status": execution_status, "exit_code": exit_code}))
    return discovery


def effective_records(discovery: ResultDiscovery) -> list[ResultRecord]:
    return [record for record in discovery.records if record.usable and record.score is not None]
