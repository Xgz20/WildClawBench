"""Runtime-neutral scoring primitives for WildClawBench General E2E."""

from .errors import GradingCoreError
from .evidence import build_evidence_index
from .finalize import finalize_score
from .rules import inspect_rule_dependencies, run_rules
from .semantics import evaluate_semantics
from .native_text import NativeTextError, extract_native_text, is_native_text_format
from .office_runtime import OfficeRuntimeError, create_office_lock, validate_office_lock, recalculate_xlsx
from .office_runtime import create_office_render_lock, validate_office_render_lock, office_render_lock_digest, render_pptx_pdf
from .office_runtime import read_embedded_xlsx, extract_embedded_xlsx

CORE_VERSION = "0.7.0"

__all__ = (
    "CORE_VERSION",
    "GradingCoreError",
    "build_evidence_index",
    "evaluate_semantics",
    "finalize_score",
    "inspect_rule_dependencies",
    "run_rules",
    "NativeTextError",
    "extract_native_text",
    "is_native_text_format",
    "OfficeRuntimeError",
    "create_office_lock",
    "validate_office_lock",
    "recalculate_xlsx",
    "create_office_render_lock",
    "validate_office_render_lock",
    "office_render_lock_digest",
    "render_pptx_pdf",
    "read_embedded_xlsx",
    "extract_embedded_xlsx",
)
