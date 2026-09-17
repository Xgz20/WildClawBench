"""Exact legacy score helpers used while the old CLI remains supported."""

from __future__ import annotations

import json
import math
from typing import Any


def parse_grade_stdout(stdout: str) -> dict | None:
    try:
        return json.loads(stdout.strip())
    except json.JSONDecodeError:
        for line in reversed(stdout.strip().splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
    return None


def _format_score_values(values: list[float]) -> str:
    return json.dumps(values, ensure_ascii=False, separators=(",", ":"))


def _format_received_score(value: object) -> str:
    rendered = repr(value)
    return rendered if len(rendered) <= 160 else rendered[:157] + "..."


def validate_legacy_rubric_scores(
    raw: dict, rubric_criteria: list[dict],
) -> tuple[dict[str, float] | None, str]:
    raw_scores = raw.get("scores") if isinstance(raw, dict) else None
    if not isinstance(raw_scores, dict):
        return None, "scores must be a JSON object"

    expected_keys = [str(criterion["key"]) for criterion in rubric_criteria]
    if len(expected_keys) != len(set(expected_keys)):
        return None, "rubric declares duplicate criterion keys"
    actual_keys = set(raw_scores)
    expected_key_set = set(expected_keys)
    errors: list[str] = []
    criteria_by_key = {
        str(criterion["key"]): criterion for criterion in rubric_criteria
    }
    for key in expected_keys:
        if key not in actual_keys:
            allowed = criteria_by_key[key].get("allowed_scores")
            suffix = (
                f"; allowed values: {_format_score_values(allowed)}"
                if isinstance(allowed, list) and allowed
                else "; allowed range: [0.0,1.0]"
            )
            errors.append(f"missing score {key!r}{suffix}")
    for key in sorted(actual_keys - expected_key_set, key=str):
        errors.append(
            f"unexpected score {key!r}={_format_received_score(raw_scores[key])}"
        )

    normalized: dict[str, float] = {}
    for criterion in rubric_criteria:
        key = str(criterion["key"])
        if key not in raw_scores:
            continue
        value = raw_scores[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            errors.append(
                f"score {key!r}={_format_received_score(value)} must be a finite number"
            )
            continue
        numeric = float(value)
        if not math.isfinite(numeric):
            errors.append(
                f"score {key!r}={_format_received_score(value)} must be a finite number"
            )
            continue
        allowed = criterion.get("allowed_scores")
        if isinstance(allowed, list) and allowed:
            match = next((
                float(candidate)
                for candidate in allowed
                if isinstance(candidate, (int, float))
                and not isinstance(candidate, bool)
                and math.isfinite(float(candidate))
                and math.isclose(numeric, float(candidate), rel_tol=0.0, abs_tol=1e-9)
            ), None)
            if match is None:
                errors.append(
                    f"score {key!r}={_format_received_score(value)}; allowed values: "
                    f"{_format_score_values(allowed)}"
                )
                continue
            normalized[key] = match
        elif 0.0 <= numeric <= 1.0:
            normalized[key] = numeric
        else:
            errors.append(
                f"score {key!r}={_format_received_score(value)}; "
                "allowed range: [0.0,1.0]"
            )
    if errors:
        return None, "; ".join(errors)
    return normalized, ""


def align_legacy_rubric_scores(
    raw: dict, rubric_criteria: list[dict],
) -> tuple[float, dict[str, float], str]:
    breakdown, validation_error = validate_legacy_rubric_scores(raw, rubric_criteria)
    if breakdown is None:
        raise ValueError(validation_error)
    total_weight = sum(criterion["weight"] for criterion in rubric_criteria)
    if total_weight > 0:
        score = sum(
            breakdown[criterion["key"]] * criterion["weight"]
            for criterion in rubric_criteria
        ) / total_weight
    else:
        score = sum(breakdown.values()) / len(breakdown) if breakdown else 0.0
    notes = str(raw.get("notes", "")) if isinstance(raw, dict) else ""
    return score, breakdown, notes


def combine_legacy_v2_scores(
    auto_score: float | None,
    auto_breakdown: dict,
    llm_score: float,
    llm_breakdown: dict,
    llm_notes: str,
    grading_weights: dict,
) -> dict:
    w_auto = float(grading_weights.get("automated", 0.5))
    w_llm = float(grading_weights.get("llm_judge", 0.5))
    if auto_score is None:
        overall = llm_score
        w_auto = 0.0
    else:
        total_weight = w_auto + w_llm
        if total_weight <= 0:
            w_auto = w_llm = 0.5
            total_weight = 1.0
        overall = (auto_score * w_auto + llm_score * w_llm) / total_weight
    scores: dict[str, Any] = {}
    for key, value in auto_breakdown.items():
        scores[f"automated.{key}"] = value
    for key, value in llm_breakdown.items():
        scores[f"llm_judge.{key}"] = value
    scores["_grading"] = {
        "mode": "v2_hybrid" if auto_score is not None else "v2_llm_only",
        "automated_score": round(auto_score, 5) if auto_score is not None else None,
        "llm_judge_score": round(llm_score, 5),
        "weights": {"automated": w_auto, "llm_judge": w_llm},
    }
    if llm_notes:
        scores["_grading"]["llm_notes"] = llm_notes
    scores["overall_score"] = round(max(0.0, min(1.0, overall)), 4)
    return scores
