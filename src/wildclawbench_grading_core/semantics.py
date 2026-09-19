"""Semantic-result validation independent of Codex or API transport."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from ._validation import (
    canonical_json_bytes,
    criterion_key,
    finite_score,
    score_matches_allowed,
)
from .errors import GradingCoreError
from .evidence import evidence_reference_set


SEMANTIC_COMPONENT_SCHEMA = "wildclawbench.general-e2e-semantic-component/v1"
SemanticEvaluator = Callable[
    [Sequence[Mapping[str, Any]], Mapping[str, Any]], Mapping[str, Any]
]
_PROTOCOLS = frozenset({"codex-agent-judge-v1", "api-judge-v1"})


def _contains_chinese_explanation(value: str) -> bool:
    return sum("\u3400" <= character <= "\u9fff" for character in value) >= 4


def _normalize_criteria(criteria: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(criteria, Sequence) or isinstance(criteria, (str, bytes)):
        raise GradingCoreError(
            "SEMANTIC_CONTRACT_INVALID", "criteria must be an array"
        )
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in criteria:
        if not isinstance(raw, Mapping):
            raise GradingCoreError(
                "SEMANTIC_CONTRACT_INVALID", "criterion must be an object"
            )
        key = criterion_key(raw.get("key"))
        if key in seen:
            raise GradingCoreError(
                "SEMANTIC_CONTRACT_INVALID", f"duplicate criterion key: {key}"
            )
        seen.add(key)
        weight = finite_score(raw.get("weight"), field=f"criterion {key!r} weight")
        allowed = raw.get("allowed_scores")
        normalized_allowed: list[float] = []
        if allowed is not None:
            if not isinstance(allowed, list) or not allowed:
                raise GradingCoreError(
                    "SEMANTIC_CONTRACT_INVALID",
                    f"criterion {key!r} allowed_scores must be non-empty",
                )
            normalized_allowed = sorted({
                finite_score(value, field=f"criterion {key!r} allowed score")
                for value in allowed
            })
        normalized.append(
            {
                "key": key,
                "weight": weight,
                "allowed_scores": normalized_allowed,
                "not_applicable_allowed": raw.get("not_applicable_allowed") is True,
            }
        )
    if normalized and sum(item["weight"] for item in normalized) <= 0:
        raise GradingCoreError(
            "SEMANTIC_CONTRACT_INVALID", "criterion weights must have a positive sum"
        )
    return normalized


def evaluate_semantics(
    criteria: Sequence[Mapping[str, Any]],
    *,
    evaluator: SemanticEvaluator | None,
    evidence_index: Mapping[str, Any],
    protocol: str,
) -> dict[str, Any]:
    """Run one injected semantic backend and validate every criterion result."""

    normalized = _normalize_criteria(criteria)
    if not normalized:
        if protocol != "not-required":
            raise GradingCoreError(
                "SEMANTIC_PROTOCOL_INVALID",
                "empty criteria require protocol='not-required'",
            )
        return {
            "schema_version": SEMANTIC_COMPONENT_SCHEMA,
            "protocol": protocol,
            "status": "not_required",
            "score": None,
            "criteria": [],
            "notes": "",
            "error": None,
        }
    if protocol not in _PROTOCOLS:
        raise GradingCoreError(
            "SEMANTIC_PROTOCOL_INVALID", f"unsupported protocol: {protocol!r}"
        )
    if evaluator is None or not callable(evaluator):
        raise GradingCoreError(
            "SEMANTIC_EVALUATOR_REQUIRED", "semantic evaluator is required"
        )
    known_evidence = evidence_reference_set(evidence_index)
    try:
        raw = evaluator(normalized, evidence_index)
    except GradingCoreError:
        raise
    except Exception as exc:
        raise GradingCoreError(
            "SEMANTIC_BACKEND_FAILED", str(exc) or type(exc).__name__
        ) from exc
    if not isinstance(raw, Mapping) or not isinstance(raw.get("criteria"), list):
        raise GradingCoreError(
            "SEMANTIC_RESULT_INVALID", "backend result must contain criteria array"
        )
    rows = raw["criteria"]
    by_key: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise GradingCoreError(
                "SEMANTIC_RESULT_INVALID", "criterion result must be an object"
            )
        key = criterion_key(row.get("key"), field="semantic result key")
        if key in by_key:
            raise GradingCoreError(
                "SEMANTIC_RESULT_INVALID", f"duplicate semantic result: {key}"
            )
        by_key[key] = row
    expected = [item["key"] for item in normalized]
    missing = [key for key in expected if key not in by_key]
    unexpected = sorted(set(by_key) - set(expected))
    if missing or unexpected:
        raise GradingCoreError(
            "SEMANTIC_RESULT_KEYS_MISMATCH",
            f"missing={missing}, unexpected={unexpected}",
        )

    output: list[dict[str, Any]] = []
    unresolved: list[str] = []
    weighted = 0.0
    judged_weight = 0.0
    for contract in normalized:
        key = contract["key"]
        row = by_key[key]
        status = row.get("status")
        reason = row.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            raise GradingCoreError(
                "SEMANTIC_RESULT_INVALID", f"criterion {key!r} requires a reason"
            )
        if not _contains_chinese_explanation(reason):
            raise GradingCoreError(
                "SEMANTIC_REASON_LANGUAGE_INVALID",
                f"criterion {key!r} reason must be a Chinese explanation",
            )
        references = row.get("evidence", [])
        if not isinstance(references, list):
            raise GradingCoreError(
                "SEMANTIC_RESULT_INVALID", f"criterion {key!r} evidence must be an array"
            )
        for reference in references:
            if not isinstance(reference, Mapping) or canonical_json_bytes(reference) not in known_evidence:
                raise GradingCoreError(
                    "SEMANTIC_EVIDENCE_UNKNOWN",
                    f"criterion {key!r} cites evidence outside the frozen index",
                )
        score: float | None
        if status == "judged":
            score = finite_score(row.get("score"), field=f"semantic score {key!r}")
            if not score_matches_allowed(score, contract["allowed_scores"]):
                raise GradingCoreError(
                    "SEMANTIC_SCORE_NOT_ALLOWED",
                    f"criterion {key!r} score {score} is outside its anchors",
                )
            if not references:
                raise GradingCoreError(
                    "SEMANTIC_EVIDENCE_REQUIRED",
                    f"criterion {key!r} requires at least one evidence reference",
                )
            weighted += score * contract["weight"]
            judged_weight += contract["weight"]
        elif status == "unresolved":
            if row.get("score") is not None:
                raise GradingCoreError(
                    "SEMANTIC_RESULT_INVALID",
                    f"unresolved criterion {key!r} must have score=null",
                )
            score = None
            unresolved.append(key)
        elif status == "not_applicable" and contract["not_applicable_allowed"]:
            if row.get("score") is not None:
                raise GradingCoreError(
                    "SEMANTIC_RESULT_INVALID",
                    f"not_applicable criterion {key!r} must have score=null",
                )
            score = None
        else:
            raise GradingCoreError(
                "SEMANTIC_RESULT_INVALID",
                f"criterion {key!r} has unsupported status {status!r}",
            )
        output.append(
            {
                "key": key,
                "weight": contract["weight"],
                "status": status,
                "score": score,
                "reason": reason.strip(),
                "evidence": [dict(reference) for reference in references],
            }
        )
    notes = raw.get("notes", "")
    if not isinstance(notes, str):
        raise GradingCoreError(
            "SEMANTIC_RESULT_INVALID", "notes must be a string"
        )
    if unresolved:
        return {
            "schema_version": SEMANTIC_COMPONENT_SCHEMA,
            "protocol": protocol,
            "status": "evaluation_error",
            "score": None,
            "criteria": output,
            "notes": notes,
            "error": {
                "code": "SEMANTIC_CRITERIA_UNRESOLVED",
                "message": f"unresolved criteria: {unresolved}",
            },
        }
    if judged_weight <= 0:
        return {
            "schema_version": SEMANTIC_COMPONENT_SCHEMA,
            "protocol": protocol,
            "status": "evaluation_error",
            "score": None,
            "criteria": output,
            "notes": notes,
            "error": {
                "code": "SEMANTIC_NO_JUDGED_CRITERIA",
                "message": "semantic evaluation produced no judged criteria",
            },
        }
    score = weighted / judged_weight if judged_weight > 0 else None
    return {
        "schema_version": SEMANTIC_COMPONENT_SCHEMA,
        "protocol": protocol,
        "status": "completed",
        "score": round(score, 5) if score is not None else None,
        "criteria": output,
        "notes": notes,
        "error": None,
    }
