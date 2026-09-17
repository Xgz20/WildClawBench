"""Dependency-free semantic validation for General E2E contract v1.

JSON Schema files describe interchange shapes.  These validators additionally
enforce cross-field invariants such as explicit missing evidence and the
difference between an observed zero and an unavailable metric.
"""

from __future__ import annotations

import json
import math
import re
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, Optional, Sequence


SCHEMA_PREFIX = "urn:wildclawbench:schema:general-e2e"
KNOWN_SCHEMAS = {
    f"{SCHEMA_PREFIX}:execution-record:v1": "execution-record-v1.schema.json",
    f"{SCHEMA_PREFIX}:transcript-event:v1": "transcript-event-v1.schema.json",
    f"{SCHEMA_PREFIX}:trace-index:v1": "trace-index-v1.schema.json",
    f"{SCHEMA_PREFIX}:resource-metrics:v1": "resource-metrics-v1.schema.json",
    f"{SCHEMA_PREFIX}:score:v1": "score-v1.schema.json",
    f"{SCHEMA_PREFIX}:submission:v1": "submission-v1.schema.json",
    f"{SCHEMA_PREFIX}:receipt:v1": "receipt-v1.schema.json",
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
STAGE_STATES = {
    "NOT_SELECTED",
    "PENDING",
    "RUNNING",
    "NEEDS_HUMAN",
    "NEEDS_ATTENTION",
    "COMPLETED",
    "FAILED",
}
BUSINESS_STATUSES = {
    "completed",
    "candidate_error",
    "timeout",
    "infrastructure_error",
    "cancelled",
}
METRIC_STATUSES = {
    "observed",
    "inferred",
    "partial",
    "masked",
    "unverified",
    "unavailable",
}
INTEGER_METRICS = {
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
    "reasoning_output_tokens",
    "request_count",
    "request_attempt_count",
    "call_count",
}
RESOURCE_METRIC_FIELDS = (
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
    "reasoning_output_tokens",
    "request_count",
    "request_attempt_count",
    "call_count",
    "duration_seconds",
    "agent_duration_seconds",
)


class ContractValidationError(ValueError):
    """A stable machine-readable contract validation failure."""

    def __init__(self, code: str, path: str, message: str):
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code} at {path}: {message}")


def _fail(code: str, path: str, message: str) -> None:
    raise ContractValidationError(code, path, message)


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        _fail("TYPE_ERROR", path, "must be an object")
    return value


def _list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        _fail("TYPE_ERROR", path, "must be an array")
    return value


def _required(value: Mapping[str, Any], key: str, path: str) -> Any:
    if key not in value:
        _fail("REQUIRED_FIELD", f"{path}.{key}", "field is required")
    return value[key]


def _string(value: Any, path: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        _fail("TYPE_ERROR", path, "must be a non-empty string")
    return value


def _nullable_string(value: Any, path: str) -> Optional[str]:
    if value is None:
        return None
    return _string(value, path)


def _boolean(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        _fail("TYPE_ERROR", path, "must be a boolean")
    return value


def _integer(value: Any, path: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        _fail("TYPE_ERROR", path, f"must be an integer >= {minimum}")
    return value


def _number(value: Any, path: str, *, minimum: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail("TYPE_ERROR", path, "must be a number")
    number = float(value)
    if not math.isfinite(number) or number < minimum:
        _fail("INVALID_VALUE", path, f"must be finite and >= {minimum}")
    return number


def _nullable_number(value: Any, path: str) -> Optional[float]:
    if value is None:
        return None
    return _number(value, path)


def _enum(value: Any, allowed: set[str], path: str) -> str:
    text = _string(value, path)
    if text not in allowed:
        _fail("INVALID_VALUE", path, f"unsupported value {text!r}")
    return text


def _sha256(value: Any, path: str) -> str:
    text = _string(value, path)
    if not SHA256_RE.fullmatch(text):
        _fail("HASH_INVALID", path, "must be a lowercase SHA-256 hex digest")
    return text


def _nullable_sha256(value: Any, path: str) -> Optional[str]:
    if value is None:
        return None
    return _sha256(value, path)


def _relative_path(value: Any, path: str) -> str:
    text = _string(value, path)
    if "\\" in text:
        _fail("PATH_INVALID", path, "must use POSIX separators")
    candidate = PurePosixPath(text)
    if candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
        _fail("PATH_INVALID", path, "must be a safe relative path")
    return text


def _nullable_relative_path(value: Any, path: str) -> Optional[str]:
    if value is None:
        return None
    return _relative_path(value, path)


def _timestamp(value: Any, path: str) -> str:
    text = _string(value, path)
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ContractValidationError("TIMESTAMP_INVALID", path, str(exc)) from exc
    if parsed.tzinfo is None:
        _fail("TIMESTAMP_INVALID", path, "timezone offset is required")
    return text


def _nullable_timestamp(value: Any, path: str) -> Optional[str]:
    if value is None:
        return None
    return _timestamp(value, path)


def _validate_header(document: Mapping[str, Any], expected_schema_id: Optional[str]) -> str:
    schema_id = _string(_required(document, "schema_id", "$"), "$.schema_id")
    version = _required(document, "schema_version", "$")
    if schema_id not in KNOWN_SCHEMAS or version != 1:
        _fail(
            "SCHEMA_UNSUPPORTED",
            "$.schema_id",
            f"unsupported schema identity {schema_id!r} version {version!r}",
        )
    if expected_schema_id and schema_id != expected_schema_id:
        _fail(
            "SCHEMA_UNSUPPORTED",
            "$.schema_id",
            f"expected {expected_schema_id!r}, got {schema_id!r}",
        )
    return schema_id


def _validate_task_identity(value: Any, path: str = "$.identity") -> Mapping[str, Any]:
    identity = _mapping(value, path)
    for field in ("batch_id", "unit_id", "task_id", "attempt_id"):
        _string(_required(identity, field, path), f"{path}.{field}")
    return identity


def _validate_batch_scope(value: Any, path: str = "$.scope") -> Mapping[str, Any]:
    scope = _mapping(value, path)
    for field in ("batch_id", "unit_id"):
        _string(_required(scope, field, path), f"{path}.{field}")
    return scope


def _validate_dataset(value: Any, path: str = "$.dataset") -> Mapping[str, Any]:
    dataset = _mapping(value, path)
    _string(_required(dataset, "id", path), f"{path}.id")
    _sha256(_required(dataset, "digest", path), f"{path}.digest")
    return dataset


def _validate_artifact(value: Any, path: str) -> Mapping[str, Any]:
    artifact = _mapping(value, path)
    _relative_path(_required(artifact, "path", path), f"{path}.path")
    _sha256(_required(artifact, "sha256", path), f"{path}.sha256")
    _integer(_required(artifact, "size", path), f"{path}.size")
    return artifact


def _validate_evidence(value: Any, path: str) -> Mapping[str, Any]:
    evidence = _mapping(value, path)
    _string(_required(evidence, "type", path), f"{path}.type")
    artifact_path = evidence.get("path")
    event_ids = evidence.get("event_ids")
    if artifact_path is None and not event_ids:
        _fail("EVIDENCE_MISSING", path, "evidence needs a path or event_ids")
    if artifact_path is not None:
        _relative_path(artifact_path, f"{path}.path")
    if event_ids is not None:
        values = _list(event_ids, f"{path}.event_ids")
        if not values:
            _fail("EVIDENCE_MISSING", f"{path}.event_ids", "must not be empty")
        for index, event_id in enumerate(values):
            _string(event_id, f"{path}.event_ids[{index}]")
    _nullable_sha256(evidence.get("sha256"), f"{path}.sha256")
    return evidence


def _validate_execution_record(document: Mapping[str, Any]) -> None:
    _validate_task_identity(_required(document, "identity", "$"))
    _validate_dataset(_required(document, "dataset", "$"))
    phase = _enum(_required(document, "phase", "$"), STAGE_STATES, "$.phase")
    harness = _mapping(_required(document, "harness", "$"), "$.harness")
    for field in ("id", "platform"):
        _string(_required(harness, field, "$.harness"), f"$.harness.{field}")
    _nullable_string(_required(harness, "version", "$.harness"), "$.harness.version")
    model = _mapping(_required(document, "model", "$"), "$.model")
    _string(_required(model, "requested_id", "$.model"), "$.model.requested_id")
    _nullable_string(_required(model, "actual_id", "$.model"), "$.model.actual_id")
    _enum(
        _required(model, "verification_status", "$.model"),
        {"verified", "unverified", "unknown"},
        "$.model.verification_status",
    )
    _nullable_string(
        _required(model, "reasoning_effort", "$.model"), "$.model.reasoning_effort"
    )

    execution = _mapping(_required(document, "execution", "$"), "$.execution")
    business_status = _required(execution, "business_status", "$.execution")
    if business_status is not None:
        business_status = _enum(business_status, BUSINESS_STATUSES, "$.execution.business_status")
    if phase in {"COMPLETED", "FAILED"} and business_status is None:
        _fail("REQUIRED_FIELD", "$.execution.business_status", "terminal phase needs a business status")
    _nullable_timestamp(
        _required(execution, "started_at", "$.execution"), "$.execution.started_at"
    )
    _nullable_timestamp(
        _required(execution, "finished_at", "$.execution"), "$.execution.finished_at"
    )
    _nullable_number(
        _required(execution, "duration_seconds", "$.execution"),
        "$.execution.duration_seconds",
    )
    _nullable_number(
        _required(execution, "agent_duration_seconds", "$.execution"),
        "$.execution.agent_duration_seconds",
    )
    error = _required(execution, "error", "$.execution")
    if error is not None:
        error_value = _mapping(error, "$.execution.error")
        _string(_required(error_value, "code", "$.execution.error"), "$.execution.error.code")
        _string(_required(error_value, "message", "$.execution.error"), "$.execution.error.message")

    prompt = _mapping(_required(document, "prompt", "$"), "$.prompt")
    _sha256(_required(prompt, "sha256", "$.prompt"), "$.prompt.sha256")
    send_status = _enum(
        _required(prompt, "send_status", "$.prompt"),
        {"not_sent", "intent_persisted", "sent", "uncertain"},
        "$.prompt.send_status",
    )
    sent_at = _nullable_timestamp(
        _required(prompt, "sent_at", "$.prompt"), "$.prompt.sent_at"
    )
    if send_status == "sent" and sent_at is None:
        _fail("REQUIRED_FIELD", "$.prompt.sent_at", "sent prompt needs sent_at")

    session = _mapping(_required(document, "session", "$"), "$.session")
    verified = _boolean(_required(session, "verified", "$.session"), "$.session.verified")
    native_ids = [
        _nullable_string(_required(session, field, "$.session"), f"$.session.{field}")
        for field in ("thread_id", "turn_id", "session_id")
    ]
    cwd = _nullable_string(_required(session, "cwd", "$.session"), "$.session.cwd")
    if verified and (not any(native_ids) or cwd is None):
        _fail("IDENTITY_INVALID", "$.session", "verified session needs a native ID and cwd")

    evidence = _mapping(_required(document, "evidence", "$"), "$.evidence")
    completeness = _enum(
        _required(evidence, "completeness", "$.evidence"),
        {"complete", "partial", "unavailable"},
        "$.evidence.completeness",
    )
    _nullable_relative_path(
        _required(evidence, "transcript_path", "$.evidence"),
        "$.evidence.transcript_path",
    )
    _nullable_relative_path(
        _required(evidence, "trace_index_path", "$.evidence"),
        "$.evidence.trace_index_path",
    )
    final_response = _nullable_relative_path(
        _required(evidence, "final_response_path", "$.evidence"),
        "$.evidence.final_response_path",
    )
    missing = _list(_required(evidence, "missing", "$.evidence"), "$.evidence.missing")
    for index, item in enumerate(missing):
        _string(item, f"$.evidence.missing[{index}]")
    if completeness == "complete" and missing:
        _fail("INVALID_VALUE", "$.evidence.missing", "complete evidence cannot list missing items")

    candidate = _mapping(_required(document, "candidate", "$"), "$.candidate")
    _nullable_relative_path(
        _required(candidate, "path", "$.candidate"), "$.candidate.path"
    )
    candidate_sha = _nullable_sha256(
        _required(candidate, "frozen_sha256", "$.candidate"),
        "$.candidate.frozen_sha256",
    )
    _nullable_timestamp(
        _required(candidate, "frozen_at", "$.candidate"), "$.candidate.frozen_at"
    )
    _enum(
        _required(candidate, "drift_status", "$.candidate"),
        {"not_frozen", "stable", "drifted", "unverified"},
        "$.candidate.drift_status",
    )
    _nullable_relative_path(
        _required(document, "resource_metrics_path", "$"), "$.resource_metrics_path"
    )

    assistance = _mapping(_required(document, "human_assistance", "$"), "$.human_assistance")
    _enum(
        _required(assistance, "mode", "$.human_assistance"),
        {"automatic", "human_assisted"},
        "$.human_assistance.mode",
    )
    _integer(_required(assistance, "operation_count", "$.human_assistance"), "$.human_assistance.operation_count")
    _integer(
        _required(assistance, "semantic_intervention_count", "$.human_assistance"),
        "$.human_assistance.semantic_intervention_count",
    )
    if business_status == "completed":
        if completeness == "unavailable":
            _fail("EVIDENCE_MISSING", "$.evidence", "completed execution cannot have unavailable evidence")
        if candidate_sha is None and final_response is None:
            _fail(
                "EVIDENCE_MISSING",
                "$.candidate",
                "completed execution needs a frozen candidate or final response",
            )


def _validate_transcript_event(document: Mapping[str, Any]) -> None:
    _validate_task_identity(_required(document, "identity", "$"))
    _string(_required(document, "event_id", "$"), "$.event_id")
    _integer(_required(document, "sequence", "$"), "$.sequence")
    _nullable_timestamp(_required(document, "occurred_at", "$"), "$.occurred_at")
    event_type = _enum(
        _required(document, "type", "$"),
        {"user_message", "assistant_message", "tool_call", "tool_result", "error", "status", "usage"},
        "$.type",
    )
    source = _mapping(_required(document, "source", "$"), "$.source")
    _string(_required(source, "adapter", "$.source"), "$.source.adapter")
    _nullable_string(_required(source, "raw_ref", "$.source"), "$.source.raw_ref")
    _boolean(_required(source, "redacted", "$.source"), "$.source.redacted")
    if event_type in {"user_message", "assistant_message"}:
        expected_role = "user" if event_type == "user_message" else "assistant"
        if document.get("role") != expected_role:
            _fail("INVALID_VALUE", "$.role", f"must be {expected_role!r}")
        _string(_required(document, "content", "$"), "$.content", allow_empty=True)
    elif event_type in {"tool_call", "tool_result"}:
        tool = _mapping(_required(document, "tool", "$"), "$.tool")
        _string(_required(tool, "call_id", "$.tool"), "$.tool.call_id")
        if event_type == "tool_call":
            _string(_required(tool, "name", "$.tool"), "$.tool.name")
            _required(tool, "arguments", "$.tool")
        else:
            _enum(
                _required(tool, "status", "$.tool"),
                {"success", "error", "unknown"},
                "$.tool.status",
            )
            _required(tool, "result", "$.tool")


def _validate_trace_index(document: Mapping[str, Any]) -> None:
    _validate_task_identity(_required(document, "identity", "$"))
    if "adapter" in document:
        adapter = _mapping(document["adapter"], "$.adapter")
        _string(_required(adapter, "id", "$.adapter"), "$.adapter.id")
        version = _string(_required(adapter, "version", "$.adapter"), "$.adapter.version")
        if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
            _fail("INVALID_VALUE", "$.adapter.version", "must be a semantic version")
        _string(_required(adapter, "source", "$.adapter"), "$.adapter.source")
    if "session" in document:
        session = _mapping(document["session"], "$.session")
        for field in ("thread_id", "turn_id", "session_id", "cwd", "lifecycle_generation"):
            _string(_required(session, field, "$.session"), f"$.session.{field}")
    transcript = _validate_artifact(_required(document, "transcript", "$"), "$.transcript")
    event_count = _integer(_required(transcript, "event_count", "$.transcript"), "$.transcript.event_count")
    completeness = _mapping(_required(document, "completeness", "$"), "$.completeness")
    status_value = _enum(
        _required(completeness, "status", "$.completeness"),
        {"complete", "partial", "unavailable"},
        "$.completeness.status",
    )
    omitted = _integer(
        _required(completeness, "omitted_event_count", "$.completeness"),
        "$.completeness.omitted_event_count",
    )
    if status_value == "complete" and omitted != 0:
        _fail("INVALID_VALUE", "$.completeness.omitted_event_count", "complete trace must omit zero events")
    if event_count == 0 and status_value == "complete":
        _fail("INVALID_VALUE", "$.transcript.event_count", "complete trace cannot be empty")
    missing = _list(
        _required(completeness, "missing", "$.completeness"),
        "$.completeness.missing",
    )
    for index, item in enumerate(missing):
        _string(item, f"$.completeness.missing[{index}]")
    if status_value == "complete" and missing:
        _fail("INVALID_VALUE", "$.completeness.missing", "complete trace cannot list missing items")
    raw_trace = _list(_required(document, "raw_trace", "$"), "$.raw_trace")
    if status_value == "complete" and not raw_trace:
        _fail("EVIDENCE_MISSING", "$.raw_trace", "complete trace needs a raw archive")
    for index, artifact in enumerate(raw_trace):
        _validate_artifact(artifact, f"$.raw_trace[{index}]")
    if "raw_event_range" in document:
        event_range = _mapping(document["raw_event_range"], "$.raw_event_range")
        first_sequence = _integer(
            _required(event_range, "first_sequence", "$.raw_event_range"),
            "$.raw_event_range.first_sequence",
        )
        last_sequence = _integer(
            _required(event_range, "last_sequence", "$.raw_event_range"),
            "$.raw_event_range.last_sequence",
        )
        native_event_count = _integer(
            _required(event_range, "event_count", "$.raw_event_range"),
            "$.raw_event_range.event_count",
            minimum=1,
        )
        if last_sequence < first_sequence:
            _fail("INVALID_VALUE", "$.raw_event_range", "last_sequence precedes first_sequence")
    else:
        native_event_count = None
    if "normalization" in document:
        normalization = _mapping(document["normalization"], "$.normalization")
        normalized_native_count = _integer(
            _required(normalization, "native_event_count", "$.normalization"),
            "$.normalization.native_event_count",
            minimum=1,
        )
        normalized_event_count = _integer(
            _required(normalization, "normalized_event_count", "$.normalization"),
            "$.normalization.normalized_event_count",
            minimum=1,
        )
        filtered_native_count = _integer(
            _required(normalization, "filtered_native_event_count", "$.normalization"),
            "$.normalization.filtered_native_event_count",
        )
        profiles = _list(
            _required(normalization, "compatibility_profiles", "$.normalization"),
            "$.normalization.compatibility_profiles",
        )
        for index, profile in enumerate(profiles):
            _string(profile, f"$.normalization.compatibility_profiles[{index}]")
        if not profiles or len(profiles) != len(set(profiles)):
            _fail("INVALID_VALUE", "$.normalization.compatibility_profiles", "must be non-empty and unique")
        if normalized_event_count != event_count:
            _fail(
                "INVALID_VALUE",
                "$.normalization.normalized_event_count",
                "must equal transcript.event_count",
            )
        if native_event_count is not None and normalized_native_count != native_event_count:
            _fail(
                "INVALID_VALUE",
                "$.normalization.native_event_count",
                "must equal raw_event_range.event_count",
            )
        if normalized_event_count + filtered_native_count != normalized_native_count:
            _fail(
                "INVALID_VALUE",
                "$.normalization.filtered_native_event_count",
                "normalized plus filtered counts must equal native_event_count",
            )
    call_ids: set[str] = set()
    for index, call in enumerate(_list(_required(document, "calls", "$"), "$.calls")):
        item = _mapping(call, f"$.calls[{index}]")
        call_id = _string(_required(item, "call_id", f"$.calls[{index}]"), f"$.calls[{index}].call_id")
        if call_id in call_ids:
            _fail("IDENTITY_INVALID", f"$.calls[{index}].call_id", "duplicate call_id")
        call_ids.add(call_id)
        call_sequence = _integer(
            _required(item, "call_sequence", f"$.calls[{index}]"),
            f"$.calls[{index}].call_sequence",
        )
        if call_sequence >= event_count:
            _fail("INVALID_VALUE", f"$.calls[{index}].call_sequence", "outside transcript range")
        result_sequence = item.get("result_sequence")
        if result_sequence is not None:
            result_sequence = _integer(
                result_sequence, f"$.calls[{index}].result_sequence"
            )
            if result_sequence <= call_sequence or result_sequence >= event_count:
                _fail(
                    "INVALID_VALUE",
                    f"$.calls[{index}].result_sequence",
                    "must follow the call and remain inside transcript range",
                )


def _validate_metric(value: Any, path: str, metric_name: str) -> None:
    metric = _mapping(value, path)
    status_value = _enum(_required(metric, "status", path), METRIC_STATUSES, f"{path}.status")
    raw_value = _required(metric, "value", path)
    basis = _string(_required(metric, "basis", path), f"{path}.basis")
    if not basis:
        _fail("REQUIRED_FIELD", f"{path}.basis", "metric basis is required")
    if status_value in {"masked", "unavailable"}:
        if raw_value is not None:
            _fail(
                "METRIC_STATUS_VALUE_MISMATCH",
                f"{path}.value",
                f"{status_value} metric must use null, not {raw_value!r}",
            )
        return
    if status_value in {"observed", "inferred", "unverified"} and raw_value is None:
        _fail(
            "METRIC_STATUS_VALUE_MISMATCH",
            f"{path}.value",
            f"{status_value} metric needs a numeric value",
        )
    if raw_value is not None:
        if metric_name in INTEGER_METRICS:
            _integer(raw_value, f"{path}.value")
        else:
            _number(raw_value, f"{path}.value")


def _validate_resource_metrics(document: Mapping[str, Any]) -> None:
    _validate_task_identity(_required(document, "identity", "$"))
    collection = _mapping(_required(document, "collection", "$"), "$.collection")
    _string(_required(collection, "collector", "$.collection"), "$.collection.collector")
    _string(_required(collection, "version", "$.collection"), "$.collection.version")
    _enum(
        _required(collection, "status", "$.collection"),
        {"complete", "partial", "unavailable"},
        "$.collection.status",
    )
    _timestamp(_required(collection, "collected_at", "$.collection"), "$.collection.collected_at")
    for index, artifact in enumerate(_list(_required(collection, "sources", "$.collection"), "$.collection.sources")):
        _validate_artifact(artifact, f"$.collection.sources[{index}]")
    for index, warning in enumerate(_list(_required(collection, "warnings", "$.collection"), "$.collection.warnings")):
        _string(warning, f"$.collection.warnings[{index}]")
    for index, item in enumerate(
        _list(
            _required(collection, "excluded_scope", "$.collection"),
            "$.collection.excluded_scope",
        )
    ):
        _string(item, f"$.collection.excluded_scope[{index}]")
    metrics = _mapping(_required(document, "metrics", "$"), "$.metrics")
    groups = {
        "usage": (
            "input_tokens", "output_tokens", "total_tokens",
            "cache_read_input_tokens", "cache_creation_input_tokens", "reasoning_output_tokens",
        ),
        "requests": ("request_count", "request_attempt_count"),
        "tools": ("call_count",),
        "timing": ("duration_seconds", "agent_duration_seconds"),
    }
    metric_values: dict[str, Mapping[str, Any]] = {}
    for group_name, fields in groups.items():
        group = _mapping(_required(metrics, group_name, "$.metrics"), f"$.metrics.{group_name}")
        for field in fields:
            metric_value = _mapping(
                _required(group, field, f"$.metrics.{group_name}"),
                f"$.metrics.{group_name}.{field}",
            )
            _validate_metric(
                metric_value,
                f"$.metrics.{group_name}.{field}",
                field,
            )
            metric_values[field] = metric_value

    if "coverage" in collection:
        coverage = _mapping(collection["coverage"], "$.collection.coverage")
        for field in RESOURCE_METRIC_FIELDS:
            item = _mapping(
                _required(coverage, field, "$.collection.coverage"),
                f"$.collection.coverage.{field}",
            )
            known = _integer(
                _required(item, "known", f"$.collection.coverage.{field}"),
                f"$.collection.coverage.{field}.known",
            )
            total_value = _required(item, "total", f"$.collection.coverage.{field}")
            total = None if total_value is None else _integer(
                total_value,
                f"$.collection.coverage.{field}.total",
            )
            _string(
                _required(item, "unit", f"$.collection.coverage.{field}"),
                f"$.collection.coverage.{field}.unit",
            )
            if total is not None and known > total:
                _fail(
                    "INVALID_VALUE",
                    f"$.collection.coverage.{field}",
                    "known coverage cannot exceed total",
                )
            status_value = metric_values[field]["status"]
            if status_value in {"observed", "inferred"} and (total is None or known != total):
                _fail(
                    "METRIC_COVERAGE_MISMATCH",
                    f"$.collection.coverage.{field}",
                    f"{status_value} metric needs complete coverage",
                )
            if status_value in {"masked", "unavailable"} and known != 0:
                _fail(
                    "METRIC_COVERAGE_MISMATCH",
                    f"$.collection.coverage.{field}.known",
                    f"{status_value} metric cannot claim known observations",
                )

    known_subtotals = _mapping(
        collection.get("known_subtotals", {}),
        "$.collection.known_subtotals",
    )
    for field, subtotal in known_subtotals.items():
        if field not in RESOURCE_METRIC_FIELDS:
            _fail(
                "INVALID_VALUE",
                f"$.collection.known_subtotals.{field}",
                "unknown metric",
            )
        if field in INTEGER_METRICS:
            _integer(subtotal, f"$.collection.known_subtotals.{field}")
        else:
            _number(subtotal, f"$.collection.known_subtotals.{field}")
        if metric_values[field]["status"] not in {"partial", "unverified"}:
            _fail(
                "METRIC_STATUS_VALUE_MISMATCH",
                f"$.collection.known_subtotals.{field}",
                "known subtotal is only valid for partial or unverified metrics",
            )

    if "metric_sources" in collection:
        metric_sources = _mapping(collection["metric_sources"], "$.collection.metric_sources")
        for field in RESOURCE_METRIC_FIELDS:
            refs = _list(
                _required(metric_sources, field, "$.collection.metric_sources"),
                f"$.collection.metric_sources.{field}",
            )
            if not refs:
                _fail(
                    "EVIDENCE_MISSING",
                    f"$.collection.metric_sources.{field}",
                    "metric needs at least one source reference",
                )
            seen_refs: set[str] = set()
            for index, ref in enumerate(refs):
                source_ref = _string(
                    ref,
                    f"$.collection.metric_sources.{field}[{index}]",
                )
                if source_ref in seen_refs:
                    _fail(
                        "INVALID_VALUE",
                        f"$.collection.metric_sources.{field}[{index}]",
                        "duplicate source reference",
                    )
                seen_refs.add(source_ref)


def _validate_score_component(value: Any, path: str) -> None:
    component = _mapping(value, path)
    status_value = _enum(
        _required(component, "status", path),
        {"completed", "not_required", "evaluation_error"},
        f"{path}.status",
    )
    score = _required(component, "score", path)
    if status_value == "completed":
        number = _number(score, f"{path}.score")
        if number > 1:
            _fail("INVALID_VALUE", f"{path}.score", "score must be <= 1")
    elif score is not None:
        _fail("INVALID_VALUE", f"{path}.score", f"{status_value} component must use null")


def _validate_score(document: Mapping[str, Any]) -> None:
    _validate_task_identity(_required(document, "identity", "$"))
    _validate_dataset(_required(document, "dataset", "$"))
    execution = _mapping(_required(document, "execution", "$"), "$.execution")
    _relative_path(_required(execution, "record_path", "$.execution"), "$.execution.record_path")
    _sha256(_required(execution, "record_sha256", "$.execution"), "$.execution.record_sha256")
    _string(
        _required(execution, "attempt_id", "$.execution"),
        "$.execution.attempt_id",
    )
    _enum(
        _required(execution, "business_status", "$.execution"),
        BUSINESS_STATUSES,
        "$.execution.business_status",
    )
    judge = _mapping(_required(document, "judge", "$"), "$.judge")
    _enum(
        _required(judge, "protocol", "$.judge"),
        {"codex-agent-judge-v1", "api-judge-v1", "not-required"},
        "$.judge.protocol",
    )
    _nullable_string(judge.get("model"), "$.judge.model")
    _nullable_string(judge.get("reasoning_effort"), "$.judge.reasoning_effort")
    _string(_required(judge, "attempt_id", "$.judge"), "$.judge.attempt_id")

    components = _mapping(_required(document, "components", "$"), "$.components")
    _validate_score_component(_required(components, "rules", "$.components"), "$.components.rules")
    _validate_score_component(_required(components, "semantics", "$.components"), "$.components.semantics")

    evaluation = _mapping(_required(document, "evaluation", "$"), "$.evaluation")
    evaluation_status = _enum(
        _required(evaluation, "status", "$.evaluation"),
        {"completed", "partial", "evaluation_error"},
        "$.evaluation.status",
    )
    criteria = _list(_required(evaluation, "criteria", "$.evaluation"), "$.evaluation.criteria")
    seen: set[str] = set()
    total_weight = 0.0
    for index, criterion_value in enumerate(criteria):
        path = f"$.evaluation.criteria[{index}]"
        criterion = _mapping(criterion_value, path)
        key = _string(_required(criterion, "key", path), f"{path}.key")
        if key in seen:
            _fail("IDENTITY_INVALID", f"{path}.key", "duplicate criterion key")
        seen.add(key)
        weight = _number(_required(criterion, "weight", path), f"{path}.weight")
        total_weight += weight
        status_value = _enum(
            _required(criterion, "status", path),
            {"judged", "not_applicable", "unresolved"},
            f"{path}.status",
        )
        score = _required(criterion, "score", path)
        _string(
            _required(criterion, "reason", path),
            f"{path}.reason",
            allow_empty=True,
        )
        evidence = _list(_required(criterion, "evidence", path), f"{path}.evidence")
        if status_value == "judged":
            number = _number(score, f"{path}.score")
            if number > 1:
                _fail("INVALID_VALUE", f"{path}.score", "score must be <= 1")
            if not evidence:
                _fail("EVIDENCE_MISSING", f"{path}.evidence", "judged criterion needs evidence")
        elif score is not None:
            _fail("INVALID_VALUE", f"{path}.score", f"{status_value} criterion must use null")
        for evidence_index, item in enumerate(evidence):
            _validate_evidence(item, f"{path}.evidence[{evidence_index}]")
    if criteria and abs(total_weight - 1.0) > 1e-6:
        _fail("INVALID_VALUE", "$.evaluation.criteria", "criterion weights must sum to 1")
    error = _required(evaluation, "error", "$.evaluation")
    if error is not None:
        error_value = _mapping(error, "$.evaluation.error")
        _string(_required(error_value, "code", "$.evaluation.error"), "$.evaluation.error.code")
        _string(_required(error_value, "message", "$.evaluation.error"), "$.evaluation.error.message")

    result = _mapping(_required(document, "result", "$"), "$.result")
    valid = _boolean(_required(result, "valid", "$.result"), "$.result.valid")
    total_score = _required(result, "total_score", "$.result")
    invalid_reason = _required(result, "invalid_reason", "$.result")
    if valid:
        if not criteria:
            _fail("EVIDENCE_MISSING", "$.evaluation.criteria", "valid score needs criteria evidence")
        number = _number(total_score, "$.result.total_score")
        if number > 1:
            _fail("INVALID_VALUE", "$.result.total_score", "total_score must be <= 1")
        if invalid_reason is not None or evaluation_status != "completed":
            _fail("INVALID_VALUE", "$.result", "valid score needs completed evaluation and no invalid_reason")
        unresolved = [item for item in criteria if item.get("status") == "unresolved"]
        if unresolved:
            _fail("EVIDENCE_MISSING", "$.evaluation.criteria", "valid score cannot contain unresolved criteria")
    else:
        if total_score is not None:
            _fail("INVALID_VALUE", "$.result.total_score", "invalid score must use null, not zero")
        _string(invalid_reason, "$.result.invalid_reason")


def _validate_submission(document: Mapping[str, Any]) -> None:
    _validate_batch_scope(_required(document, "scope", "$"))
    _validate_dataset(_required(document, "dataset", "$"))
    _timestamp(_required(document, "created_at", "$"), "$.created_at")
    task_ids = _list(_required(document, "task_ids", "$"), "$.task_ids")
    normalized_ids = [_string(value, f"$.task_ids[{index}]") for index, value in enumerate(task_ids)]
    if len(normalized_ids) != len(set(normalized_ids)):
        _fail("SCOPE_MISMATCH", "$.task_ids", "task IDs must be unique")
    tasks = _list(_required(document, "tasks", "$"), "$.tasks")
    if _integer(_required(document, "task_count", "$"), "$.task_count", minimum=1) != len(tasks):
        _fail("SCOPE_MISMATCH", "$.task_count", "does not match tasks")
    item_ids: list[str] = []
    for index, task_value in enumerate(tasks):
        path = f"$.tasks[{index}]"
        task = _mapping(task_value, path)
        item_ids.append(_string(_required(task, "task_id", path), f"{path}.task_id"))
        _string(_required(task, "execution_attempt_id", path), f"{path}.execution_attempt_id")
        _enum(
            _required(task, "execution_status", path),
            BUSINESS_STATUSES,
            f"{path}.execution_status",
        )
        score_status = _enum(
            _required(task, "score_status", path),
            {"valid", "evaluation_error", "unscored"},
            f"{path}.score_status",
        )
        score_path = _required(task, "score_path", path)
        score_sha = _required(task, "score_sha256", path)
        scoring_attempt_id = _required(task, "scoring_attempt_id", path)
        judge_protocol = _required(task, "judge_protocol", path)
        if score_status in {"valid", "evaluation_error"}:
            _relative_path(score_path, f"{path}.score_path")
            _sha256(score_sha, f"{path}.score_sha256")
            _string(scoring_attempt_id, f"{path}.scoring_attempt_id")
            _enum(
                judge_protocol,
                {"codex-agent-judge-v1", "api-judge-v1", "not-required"},
                f"{path}.judge_protocol",
            )
        elif any(
            value is not None
            for value in (score_path, score_sha, scoring_attempt_id, judge_protocol)
        ):
            _fail("INVALID_VALUE", path, "unscored task must not claim a score attempt or artifact")
        _nullable_sha256(
            _required(task, "candidate_sha256", path), f"{path}.candidate_sha256"
        )
        _nullable_sha256(
            _required(task, "evidence_sha256", path), f"{path}.evidence_sha256"
        )
    if item_ids != normalized_ids:
        _fail("SCOPE_MISMATCH", "$.tasks", "task order/scope must exactly match task_ids")
    integrity = _mapping(_required(document, "integrity", "$"), "$.integrity")
    flags = [
        _boolean(_required(integrity, key, "$.integrity"), f"$.integrity.{key}")
        for key in ("scope_matches", "identities_match", "hashes_verified")
    ]
    valid = _boolean(_required(integrity, "valid", "$.integrity"), "$.integrity.valid")
    if valid != all(flags):
        _fail("INVALID_VALUE", "$.integrity.valid", "must equal all integrity checks")


def _validate_receipt(document: Mapping[str, Any]) -> None:
    _validate_batch_scope(_required(document, "scope", "$"))
    _validate_dataset(_required(document, "dataset", "$"))
    stage = _enum(
        _required(document, "stage", "$"),
        {"execution", "collect-evidence", "scoring", "package", "import-return", "report"},
        "$.stage",
    )
    status_value = _enum(
        _required(document, "status", "$"),
        {"completed", "failed", "partial", "needs_attention"},
        "$.status",
    )
    _timestamp(_required(document, "created_at", "$"), "$.created_at")
    task_ids = [
        _string(item, f"$.task_ids[{index}]")
        for index, item in enumerate(_list(_required(document, "task_ids", "$"), "$.task_ids"))
    ]
    if len(task_ids) != len(set(task_ids)):
        _fail("SCOPE_MISMATCH", "$.task_ids", "task IDs must be unique")
    task_receipts = _list(_required(document, "tasks", "$"), "$.tasks")
    receipt_ids: list[str] = []
    for index, item_value in enumerate(task_receipts):
        path = f"$.tasks[{index}]"
        item = _mapping(item_value, path)
        receipt_ids.append(_string(_required(item, "task_id", path), f"{path}.task_id"))
        _string(_required(item, "attempt_id", path), f"{path}.attempt_id")
        _enum(
            _required(item, "status", path),
            {"completed", "failed", "partial", "needs_attention"},
            f"{path}.status",
        )
    if receipt_ids != task_ids:
        _fail("SCOPE_MISMATCH", "$.tasks", "task receipt scope/order must match task_ids")
    for index, artifact in enumerate(_list(_required(document, "artifacts", "$"), "$.artifacts")):
        _validate_artifact(artifact, f"$.artifacts[{index}]")
    integrity = _mapping(_required(document, "integrity", "$"), "$.integrity")
    flags = [
        _boolean(_required(integrity, key, "$.integrity"), f"$.integrity.{key}")
        for key in ("scope_matches", "identities_match", "hashes_verified")
    ]
    valid = _boolean(_required(integrity, "valid", "$.integrity"), "$.integrity.valid")
    if valid != all(flags):
        _fail("INVALID_VALUE", "$.integrity.valid", "must equal all integrity checks")
    if status_value == "completed" and not valid:
        _fail("INVALID_VALUE", "$.status", f"completed {stage} receipt requires valid integrity")
    error = _required(document, "error", "$")
    if status_value == "failed" and error is None:
        _fail("REQUIRED_FIELD", "$.error", "failed receipt needs an error")
    if error is not None:
        error_value = _mapping(error, "$.error")
        _string(_required(error_value, "code", "$.error"), "$.error.code")
        _string(_required(error_value, "message", "$.error"), "$.error.message")


VALIDATORS: Mapping[str, Callable[[Mapping[str, Any]], None]] = {
    f"{SCHEMA_PREFIX}:execution-record:v1": _validate_execution_record,
    f"{SCHEMA_PREFIX}:transcript-event:v1": _validate_transcript_event,
    f"{SCHEMA_PREFIX}:trace-index:v1": _validate_trace_index,
    f"{SCHEMA_PREFIX}:resource-metrics:v1": _validate_resource_metrics,
    f"{SCHEMA_PREFIX}:score:v1": _validate_score,
    f"{SCHEMA_PREFIX}:submission:v1": _validate_submission,
    f"{SCHEMA_PREFIX}:receipt:v1": _validate_receipt,
}


def validate_contract(
    document: Mapping[str, Any], *, expected_schema_id: Optional[str] = None
) -> Mapping[str, Any]:
    value = _mapping(document, "$")
    schema_id = _validate_header(value, expected_schema_id)
    VALIDATORS[schema_id](value)
    return value


def load_contract(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContractValidationError("JSON_INVALID", "$", str(exc)) from exc
    return _mapping(value, "$")


def validate_contract_file(
    path: Path, *, expected_schema_id: Optional[str] = None
) -> Mapping[str, Any]:
    return validate_contract(load_contract(path), expected_schema_id=expected_schema_id)


def validate_transcript_jsonl(path: Path) -> list[Mapping[str, Any]]:
    schema_id = f"{SCHEMA_PREFIX}:transcript-event:v1"
    events: list[Mapping[str, Any]] = []
    seen_ids: set[str] = set()
    previous_sequence = -1
    identity: Optional[Mapping[str, Any]] = None
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise ContractValidationError("JSON_INVALID", "$", str(exc)) from exc
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ContractValidationError("JSON_INVALID", f"line {line_number}", str(exc)) from exc
        validate_contract(event, expected_schema_id=schema_id)
        event_id = event["event_id"]
        sequence = event["sequence"]
        if event_id in seen_ids:
            _fail("IDENTITY_INVALID", f"line {line_number}.event_id", "duplicate event_id")
        if sequence <= previous_sequence:
            _fail("INVALID_VALUE", f"line {line_number}.sequence", "must be strictly increasing")
        if identity is None:
            identity = event["identity"]
        elif event["identity"] != identity:
            _fail("IDENTITY_INVALID", f"line {line_number}.identity", "transcript identity changed")
        seen_ids.add(event_id)
        previous_sequence = sequence
        events.append(event)
    if not events:
        _fail("EVIDENCE_MISSING", "$", "transcript JSONL contains no events")
    return events


def schema_path(schema_id: str) -> Path:
    filename = KNOWN_SCHEMAS.get(schema_id)
    if filename is None:
        _fail("SCHEMA_UNSUPPORTED", "schema_id", f"unknown schema {schema_id!r}")
    return Path(__file__).resolve().parent / "schemas" / filename
