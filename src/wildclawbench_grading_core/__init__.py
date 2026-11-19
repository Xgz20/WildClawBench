"""Runtime-neutral scoring primitives for WildClawBench General E2E."""

from .errors import GradingCoreError
from .evidence import build_evidence_index
from .finalize import finalize_score
from .rules import inspect_rule_dependencies, run_rules
from .semantics import evaluate_semantics
from .native_text import NativeTextError, extract_native_text, is_native_text_format
from .office_runtime import OfficeRuntimeError, create_office_lock, validate_office_lock, recalculate_xlsx
from .office_runtime import create_office_render_lock, validate_office_render_lock, office_render_lock_digest, render_pptx_pdf
from .office_runtime import render_docx_pdf
from .office_runtime import office_render_lock_formats
from .office_runtime import read_embedded_xlsx, extract_embedded_xlsx
from .office_runtime import prepare_xlsx_counterfactual, verify_xlsx_counterfactual
from .office_runtime import prepare_xlsx_marker_intervention, verify_xlsx_marker_intervention
from .office_runtime import prepare_xlsx_numeric_intervention, verify_xlsx_numeric_intervention
from .image_evidence import ImageEvidenceError, is_image_evidence_format, read_image_evidence
from .html_runtime import HtmlRuntimeError, create_html_lock, validate_html_lock, html_lock_digest, observe_html, verify_html_observation

CORE_VERSION = "0.16.0"

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
    "render_docx_pdf",
    "office_render_lock_formats",
    "read_embedded_xlsx",
    "extract_embedded_xlsx",
    "prepare_xlsx_counterfactual",
    "verify_xlsx_counterfactual",
    "prepare_xlsx_marker_intervention",
    "verify_xlsx_marker_intervention",
    "prepare_xlsx_numeric_intervention",
    "verify_xlsx_numeric_intervention",
    "ImageEvidenceError",
    "is_image_evidence_format",
    "read_image_evidence",
    "HtmlRuntimeError",
    "create_html_lock",
    "validate_html_lock",
    "html_lock_digest",
    "observe_html",
    "verify_html_observation",
)
