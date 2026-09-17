"""Rule-component execution independent of a concrete container runtime."""

from __future__ import annotations

import ast
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from ._validation import criterion_key, finite_score
from .dependencies import inspect_dependencies
from .errors import GradingCoreError


RULE_COMPONENT_SCHEMA = "wildclawbench.general-e2e-rule-component/v1"
RuleExecutor = Callable[[str, Mapping[str, Any]], Mapping[str, Any]]


def inspect_rule_dependencies(
    automated_checks: str,
    *,
    dependency_catalog: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the complete statically discoverable import closure for one rule."""

    if not isinstance(automated_checks, str):
        raise GradingCoreError(
            "RULE_SOURCE_INVALID", "automated_checks must be a string"
        )
    if not automated_checks.strip():
        return {"imports": [], "stdlib": [], "external": []}
    return inspect_dependencies(automated_checks, catalog=dependency_catalog)


def _validate_grade_function(source: str) -> None:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise GradingCoreError(
            "RULE_SOURCE_INVALID",
            f"automated_checks is not valid Python: {exc.msg}",
            details={"line": exc.lineno, "offset": exc.offset},
        ) from exc
    definitions = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "grade"
    ]
    if len(definitions) != 1 or isinstance(definitions[0], ast.AsyncFunctionDef):
        raise GradingCoreError(
            "RULE_ENTRYPOINT_INVALID",
            "automated_checks must define exactly one synchronous grade() function",
        )


def _validate_rule_scores(
    raw: Mapping[str, Any],
    expected_keys: Sequence[str] | None,
) -> tuple[dict[str, float], float]:
    if not isinstance(raw, Mapping):
        raise GradingCoreError(
            "RULE_RESULT_INVALID", "rule executor must return a JSON object"
        )
    if any(not isinstance(key, str) for key in raw):
        raise GradingCoreError(
            "RULE_RESULT_INVALID", "rule result keys must be strings"
        )
    if "overall_score" not in raw:
        raise GradingCoreError(
            "RULE_RESULT_INVALID", "rule result is missing overall_score"
        )
    breakdown: dict[str, float] = {}
    for key, value in raw.items():
        if key == "overall_score":
            continue
        normalized_key = criterion_key(key, field="rule result key")
        breakdown[normalized_key] = finite_score(value, field=f"rule score {key!r}")
    if expected_keys is not None:
        expected = [criterion_key(key) for key in expected_keys]
        if len(expected) != len(set(expected)):
            raise GradingCoreError(
                "RULE_CONTRACT_INVALID", "expected rule keys contain duplicates"
            )
        missing = [key for key in expected if key not in breakdown]
        unexpected = sorted(set(breakdown) - set(expected))
        if missing or unexpected:
            raise GradingCoreError(
                "RULE_RESULT_KEYS_MISMATCH",
                f"missing={missing}, unexpected={unexpected}",
                details={"missing": missing, "unexpected": unexpected},
            )
        breakdown = {key: breakdown[key] for key in expected}
    overall = finite_score(raw["overall_score"], field="overall_score")
    return breakdown, overall


def run_rules(
    automated_checks: str,
    *,
    executor: RuleExecutor | None,
    workspace_path: str,
    transcript: Sequence[Mapping[str, Any]] | None = None,
    expected_keys: Sequence[str] | None = None,
    dependency_catalog: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Audit, execute and validate one task's rule component.

    The core never executes untrusted task code by itself. G3-02 supplies the
    managed-container executor; tests may inject an isolated fixture executor.
    """

    if not isinstance(automated_checks, str):
        raise GradingCoreError(
            "RULE_SOURCE_INVALID", "automated_checks must be a string"
        )
    if not automated_checks.strip():
        return {
            "schema_version": RULE_COMPONENT_SCHEMA,
            "status": "not_required",
            "score": None,
            "criteria": [],
            "raw_scores": {},
            "dependencies": {"imports": [], "stdlib": [], "external": []},
            "error": None,
        }
    if not isinstance(workspace_path, str) or not workspace_path:
        raise GradingCoreError(
            "RULE_CONTEXT_INVALID", "workspace_path must be non-empty"
        )
    if executor is None or not callable(executor):
        raise GradingCoreError(
            "RULE_EXECUTOR_REQUIRED",
            "a managed rule executor is required for non-empty automated checks",
        )
    _validate_grade_function(automated_checks)
    dependencies = inspect_rule_dependencies(
        automated_checks, dependency_catalog=dependency_catalog
    )
    context = {
        "workspace_path": workspace_path,
        "transcript": list(transcript or []),
        "dependencies": dependencies,
    }
    try:
        raw = executor(automated_checks, context)
    except GradingCoreError:
        raise
    except Exception as exc:
        raise GradingCoreError(
            "RULE_EXECUTION_FAILED", str(exc) or type(exc).__name__
        ) from exc
    breakdown, overall = _validate_rule_scores(raw, expected_keys)
    normalized_raw = {**breakdown, "overall_score": overall}
    return {
        "schema_version": RULE_COMPONENT_SCHEMA,
        "status": "completed",
        "score": overall,
        "criteria": [
            {"key": key, "status": "judged", "score": value}
            for key, value in breakdown.items()
        ],
        "raw_scores": normalized_raw,
        "dependencies": dependencies,
        "error": None,
    }
