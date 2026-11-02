"""Opt-in semantic evidence states shared by dataset graders and CLI consumers.

An inaccessible reference is neither a wrong answer nor a successful check.
The legacy numeric protocol is unchanged unless the task selects this profile.
"""
from __future__ import annotations

import math
from collections.abc import Mapping

PROFILE = "evidence-aware-v1"
UNRESOLVED = frozenset({"evidence_insufficient", "evaluator_reference_unavailable",
    "evaluator_evidence_missing", "evaluator_error", "blocked_external", "not_observed", "not_applicable"})
JUDGED = frozenset({"pass", "partial", "fail"})


class EvidenceAwareScores(dict):
    def __init__(self, scores, statuses, claim_reviews):
        super().__init__(scores)
        self.statuses = statuses
        self.claim_reviews = claim_reviews


def validate_semantic_response(response, criteria, *, claim_review_keys=()):
    if not isinstance(response, Mapping):
        raise ValueError("SEMANTIC_RESPONSE_INVALID")
    scores, states = response.get("scores"), response.get("criterion_statuses")
    keys = {c["key"] for c in criteria}
    if (len(keys) != len(criteria) or not isinstance(scores, dict) or set(scores) != keys
            or not isinstance(states, dict) or set(states) != keys):
        raise ValueError("SEMANTIC_CRITERION_SCOPE_MISMATCH")
    normalized = {}
    for c in criteria:
        key = c["key"]
        row, value = states[key], scores[key]
        if not isinstance(row, dict) or not isinstance(row.get("reason"), str) or not row["reason"].strip():
            raise ValueError("SEMANTIC_STATE_REASON_REQUIRED: " + key)
        state = row.get("status")
        if state in UNRESOLVED:
            if value is not None:
                raise ValueError("UNRESOLVED_SCORE_MUST_BE_NULL: " + key)
        elif state in JUDGED:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError("JUDGED_SCORE_INVALID: " + key)
            allowed = c.get("allowed_scores")
            if allowed and not any(math.isclose(value, a, abs_tol=1e-9, rel_tol=0) for a in allowed):
                raise ValueError("SEMANTIC_SCORE_ANCHOR_INVALID: " + key)
            if state == "pass" and value != 1 or state == "fail" and value != 0 or state == "partial" and not 0 < value < 1:
                raise ValueError("SEMANTIC_SCORE_STATE_MISMATCH: " + key)
        else:
            raise ValueError("SEMANTIC_STATE_INVALID: " + key)
        normalized[key] = {"status": state, "reason": row["reason"]}
    reviews = response.get("claim_reviews", {})
    if not isinstance(reviews, dict) or set(reviews) - set(claim_review_keys):
        raise ValueError("CLAIM_REVIEW_SCOPE_INVALID")
    for key in claim_review_keys:
        rows = reviews.get(key)
        if not isinstance(rows, list) or not rows:
            raise ValueError("CLAIM_REVIEW_REQUIRED: " + key)
        seen = set()
        for row in rows:
            if (not isinstance(row, dict) or row.get("unit") not in (1, 2)
                    or not isinstance(row.get("claim_id"), str) or not row["claim_id"]
                    or row["claim_id"] in seen or not isinstance(row.get("claim"), str) or not row["claim"]
                    or row.get("status") not in {"supported", "contradicted", "evaluator_reference_unavailable"}):
                raise ValueError("CLAIM_REVIEW_INVALID: " + key)
            seen.add(row["claim_id"])
            refs = row.get("evidence_refs")
            if row["status"] != "evaluator_reference_unavailable" and (
                    not isinstance(refs, list) or not refs or not all(isinstance(r, str) and r.strip() for r in refs)):
                raise ValueError("CLAIM_DECISION_REQUIRES_EVIDENCE: " + key)
        # Each of the two original fixed units is evaluated independently. A
        # proven error can decide a unit even if another claim remains unknown.
        units = []
        for unit in (1, 2):
            subset = [r["status"] for r in rows if r["unit"] == unit]
            if not subset:
                raise ValueError("CLAIM_UNIT_MISSING: " + key)
            units.append(0 if "contradicted" in subset else None if "evaluator_reference_unavailable" in subset else 1)
        expected = None if None in units else sum(units) / 2
        if scores[key] != expected:
            raise ValueError("CLAIM_SCORE_MISMATCH: " + key)
    result = EvidenceAwareScores(scores, normalized, reviews)
    result.criteria = list(criteria)
    total = sum(c["weight"] for c in criteria)
    mean = (sum(scores[c["key"]] * c["weight"] for c in criteria if c["weight"] > 0) / total
            if total > 0 and all(scores[c['key']] is not None for c in criteria if c['weight'] > 0) else None)
    return mean, result, str(response.get("notes", ""))


def finalize_cli_score(auto_score, auto_breakdown, semantic, weights, *, error=None):
    """Preserve all budgets and real zeros; never renormalize away unknowns."""
    w_auto, w_semantic = float(weights.get("automated", .5)), float(weights.get("llm_judge", .5))
    valid_response = isinstance(semantic, EvidenceAwareScores)
    unknown = [c['key'] for c in semantic.criteria if c['weight'] > 0 and semantic[c['key']] is None] if valid_response else []
    valid = not error and valid_response and not unknown
    if w_auto and (isinstance(auto_score, bool) or not isinstance(auto_score, (int, float))
                   or not math.isfinite(auto_score) or not 0 <= auto_score <= 1):
        valid = False
        error = error or "AUTOMATED_COMPONENT_INVALID"
    total_weight = w_auto + w_semantic
    if total_weight <= 0:
        valid = False
        error = error or "GRADING_WEIGHTS_INVALID"
    result = {"automated." + k: v for k, v in auto_breakdown.items()}
    if valid_response:
        result.update({"llm_judge." + k: v for k, v in semantic.items()})
    semantic_weight = sum(c.get("weight", 0) for c in getattr(semantic, "criteria", []))
    sem_score = (sum(semantic[c["key"]] * c["weight"] for c in semantic.criteria if c['weight'] > 0) / semantic_weight
                 if valid and semantic_weight else None)
    valid = valid and sem_score is not None
    result["overall_score"] = ((w_auto * (auto_score or 0) + w_semantic * sem_score) / total_weight) if valid else None
    result["_grading"] = {"mode": PROFILE, "valid": bool(valid), "status": "valid" if valid else "evaluation_error",
        "weights": {"automated": w_auto, "llm_judge": w_semantic}, "unresolved_criteria": unknown,
        "criterion_statuses": semantic.statuses if valid_response else {},
        "claim_reviews": semantic.claim_reviews if valid_response else {}, "unknown_zero_filled": False}
    if not valid:
        result["error"] = error or ("EVALUATOR_EVIDENCE_UNRESOLVED: " + ", ".join(unknown) if unknown else "SEMANTIC_RESPONSE_INVALID")
    return result
