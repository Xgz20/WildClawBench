"""Internal validation helpers shared by the public grading primitives."""

from __future__ import annotations

import json
import math
import re
from typing import Any

from .errors import GradingCoreError


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
KEY_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def finite_score(value: object, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GradingCoreError(
            "SCORE_VALUE_INVALID",
            f"{field} must be a finite number in [0,1]",
        )
    numeric = float(value)
    if not math.isfinite(numeric) or not 0.0 <= numeric <= 1.0:
        raise GradingCoreError(
            "SCORE_VALUE_INVALID",
            f"{field} must be a finite number in [0,1]",
        )
    return numeric


def criterion_key(value: object, *, field: str = "criterion key") -> str:
    if not isinstance(value, str) or not KEY_RE.fullmatch(value):
        raise GradingCoreError(
            "CRITERION_KEY_INVALID",
            f"{field} must match {KEY_RE.pattern}",
        )
    return value


def score_matches_allowed(value: float, allowed: object) -> bool:
    if not isinstance(allowed, list) or not allowed:
        return True
    for candidate in allowed:
        if isinstance(candidate, bool) or not isinstance(candidate, (int, float)):
            continue
        if math.isclose(value, float(candidate), rel_tol=0.0, abs_tol=1e-9):
            return True
    return False
