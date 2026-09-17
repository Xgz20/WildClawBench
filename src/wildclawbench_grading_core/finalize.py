"""Strict component weighting and final validity decisions."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from ._validation import finite_score
from .errors import GradingCoreError


FINAL_SCORE_SCHEMA = "wildclawbench.general-e2e-core-score/v1"
_GRADING_TYPES = frozenset({"automated", "hybrid", "llm_judge"})


def _component(value: Mapping[str, Any], *, name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise GradingCoreError(
            "SCORE_COMPONENT_INVALID", f"{name} component must be an object"
        )
    status = value.get("status")
    if status not in {"completed", "not_required", "evaluation_error"}:
        raise GradingCoreError(
            "SCORE_COMPONENT_INVALID", f"{name} status is invalid: {status!r}"
        )
    score = value.get("score")
    if status == "completed":
        score = finite_score(score, field=f"{name} component score")
    elif score is not None:
        raise GradingCoreError(
            "SCORE_COMPONENT_INVALID",
            f"{name} {status} component must have score=null",
        )
    criteria = value.get("criteria", [])
    if not isinstance(criteria, list):
        raise GradingCoreError(
            "SCORE_COMPONENT_INVALID", f"{name} criteria must be an array"
        )
    return {
        "status": status,
        "score": score,
        "criteria": list(criteria),
        "error": value.get("error"),
    }


def _weights(grading_type: str, raw: Mapping[str, Any] | None) -> dict[str, float]:
    supplied = dict(raw or {})
    if grading_type == "automated":
        expected = {"automated": 1.0, "llm_judge": 0.0}
    elif grading_type == "llm_judge":
        expected = {"automated": 0.0, "llm_judge": 1.0}
    else:
        if set(supplied) != {"automated", "llm_judge"}:
            raise GradingCoreError(
                "GRADING_WEIGHTS_INVALID",
                "hybrid grading requires automated and llm_judge weights",
            )
        expected = {
            "automated": finite_score(
                supplied["automated"], field="automated weight"
            ),
            "llm_judge": finite_score(
                supplied["llm_judge"], field="llm_judge weight"
            ),
        }
        total = expected["automated"] + expected["llm_judge"]
        if total <= 0 or not math.isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-9):
            raise GradingCoreError(
                "GRADING_WEIGHTS_INVALID", "hybrid weights must sum to 1.0"
            )
        return expected
    if supplied:
        if set(supplied) != {"automated", "llm_judge"}:
            raise GradingCoreError(
                "GRADING_WEIGHTS_INVALID",
                f"{grading_type} grading requires exactly automated and llm_judge weights",
            )
        try:
            normalized = {
                "automated": finite_score(
                    supplied.get("automated"), field="automated weight"
                ),
                "llm_judge": finite_score(
                    supplied.get("llm_judge"), field="llm_judge weight"
                ),
            }
        except GradingCoreError as exc:
            raise GradingCoreError(
                "GRADING_WEIGHTS_INVALID", exc.message
            ) from exc
        if normalized != expected:
            raise GradingCoreError(
                "GRADING_WEIGHTS_INVALID",
                f"{grading_type} grading requires weights {expected}",
            )
    return expected


def finalize_score(
    *,
    grading_type: str,
    grading_weights: Mapping[str, Any] | None,
    rules: Mapping[str, Any],
    semantics: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate both components and produce a non-lossy final score decision."""

    if grading_type not in _GRADING_TYPES:
        raise GradingCoreError(
            "GRADING_TYPE_INVALID", f"unsupported grading_type: {grading_type!r}"
        )
    normalized_rules = _component(rules, name="rules")
    normalized_semantics = _component(semantics, name="semantics")
    weights = _weights(grading_type, grading_weights)
    required = {
        "automated": {"rules": True, "semantics": False},
        "llm_judge": {"rules": False, "semantics": True},
        "hybrid": {"rules": True, "semantics": True},
    }[grading_type]
    invalid: list[str] = []
    for name, component in (
        ("rules", normalized_rules),
        ("semantics", normalized_semantics),
    ):
        if required[name] and component["status"] != "completed":
            invalid.append(f"{name} component is {component['status']}")
        if not required[name] and component["status"] != "not_required":
            invalid.append(f"{name} component must be not_required")
    criteria = normalized_rules["criteria"] + normalized_semantics["criteria"]
    keys = [row.get("key") for row in criteria if isinstance(row, Mapping)]
    if len(keys) != len(criteria) or len(keys) != len(set(keys)):
        raise GradingCoreError(
            "FINAL_CRITERIA_INVALID", "criterion keys must be present and unique"
        )
    if invalid:
        total_score = None
        valid = False
        invalid_reason = "; ".join(invalid)
        evaluation_status = "evaluation_error"
    else:
        total_score = round(
            float(normalized_rules["score"] or 0.0) * weights["automated"]
            + float(normalized_semantics["score"] or 0.0) * weights["llm_judge"],
            4,
        )
        valid = True
        invalid_reason = None
        evaluation_status = "completed"
    return {
        "schema_version": FINAL_SCORE_SCHEMA,
        "grading_type": grading_type,
        "weights": weights,
        "components": {
            "rules": {
                "status": normalized_rules["status"],
                "score": normalized_rules["score"],
            },
            "semantics": {
                "status": normalized_semantics["status"],
                "score": normalized_semantics["score"],
            },
        },
        "evaluation": {
            "status": evaluation_status,
            "criteria": criteria,
        },
        "result": {
            "valid": valid,
            "total_score": total_score,
            "invalid_reason": invalid_reason,
        },
    }
