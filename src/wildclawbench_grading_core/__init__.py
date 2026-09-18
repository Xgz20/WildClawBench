"""Runtime-neutral scoring primitives for WildClawBench General E2E."""

from .errors import GradingCoreError
from .evidence import build_evidence_index
from .finalize import finalize_score
from .rules import inspect_rule_dependencies, run_rules
from .semantics import evaluate_semantics

CORE_VERSION = "0.1.1"

__all__ = (
    "CORE_VERSION",
    "GradingCoreError",
    "build_evidence_index",
    "evaluate_semantics",
    "finalize_score",
    "inspect_rule_dependencies",
    "run_rules",
)
