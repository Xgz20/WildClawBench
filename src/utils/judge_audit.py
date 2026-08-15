from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


_SECRET_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "api-key",
    "x-api-key",
    "token",
    "access_token",
    "secret",
    "password",
    "passwd",
    "client_password",
    "env_password",
    "credential",
    "credentials",
}

_SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+|bearer\s+)[A-Za-z0-9._~+\-/=]+"),
    re.compile(r"(?i)\b([A-Z0-9_]*(?:API_KEY|TOKEN|SECRET)\s*[:=]\s*)[^\s,;]+"),
    re.compile(
        r"(?i)\b((?:password|passwd|client_password|env_password|credential|credentials)"
        r"\s*[:=]\s*)[^\s,;\"']+"
    ),
    re.compile(r"(?i)(://[^/\s:@]+:)[^@/\s]+@"),
    re.compile(r"\b(?:sk|key)-[A-Za-z0-9_-]{8,}\b"),
)


def _redact_text(value: str) -> str:
    redacted = value
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub(
            lambda match: (match.group(1) if match.lastindex else "") + "[REDACTED]",
            redacted,
        )
    return redacted


def _redact(value: Any, key: str = "") -> Any:
    if key.lower() in _SECRET_KEYS or key.lower().endswith(
        ("_key", "_token", "_secret", "_password", "_credential")
    ):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k): _redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str) and value.startswith("data:image/"):
        return "[IMAGE_DATA_OMITTED]"
    if isinstance(value, str):
        return _redact_text(value)
    return value


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(path.name + ".tmp")
    temp_path.write_text(
        json.dumps(_redact(data), ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    temp_path.replace(path)


def write_attempt(
    judge_dir: Path,
    attempt: int,
    request_data: dict,
    response_data: dict,
    parsed_data: dict,
) -> Path:
    attempt_dir = judge_dir / f"attempt-{attempt:03d}"
    _write_json(attempt_dir / "request.json", request_data)
    _write_json(attempt_dir / "response.json", response_data)
    _write_json(attempt_dir / "parsed.json", parsed_data)
    return attempt_dir


def write_summary(judge_dir: Path, summary: dict) -> Path:
    path = judge_dir / "summary.json"
    _write_json(path, summary)
    return path


def _refresh_summary(judge_dir: Path, mode: str) -> None:
    attempts = sorted(judge_dir.glob("attempt-*"))
    failed_attempts = 0
    pending_attempts = 0
    schema_mismatches = 0
    requested_models: list[str] = []
    returned_models: list[str] = []
    endpoint_types: list[str] = []
    for existing_dir in attempts:
        request_item = json.loads(
            (existing_dir / "request.json").read_text(encoding="utf-8")
        )
        response_item = json.loads(
            (existing_dir / "response.json").read_text(encoding="utf-8")
        )
        parsed_item = json.loads(
            (existing_dir / "parsed.json").read_text(encoding="utf-8")
        )
        if response_item.get("status") == "failed":
            failed_attempts += 1
        elif response_item.get("status") == "in_progress":
            pending_attempts += 1
        if parsed_item.get("schema_status") in {"mismatch", "parse_error"}:
            schema_mismatches += 1
        for value, target in (
            (
                request_item.get("effective_requested_model")
                or request_item.get("requested_model")
                or request_item.get("model"),
                requested_models,
            ),
            (
                response_item.get("returned_model") or response_item.get("model"),
                returned_models,
            ),
            (request_item.get("endpoint_type"), endpoint_types),
        ):
            if value and value not in target:
                target.append(value)

    if failed_attempts or schema_mismatches:
        status = "failed"
    elif pending_attempts:
        status = "in_progress"
    else:
        status = "success"
    write_summary(judge_dir, {
        "schema_version": 1,
        "mode": mode,
        "status": status,
        "attempt_count": len(attempts),
        "failed_attempt_count": failed_attempts,
        "pending_attempt_count": pending_attempts,
        "schema_mismatch_count": schema_mismatches,
        "requested_models": requested_models,
        "returned_models": returned_models,
        "endpoint_types": endpoint_types,
    })


def begin_attempt(judge_dir: Path, request_data: dict) -> int:
    attempt = len(list(judge_dir.glob("attempt-*"))) + 1
    write_attempt(
        judge_dir,
        attempt,
        request_data,
        {"status": "in_progress", "model": "", "returned_model": "", "usage": {}},
        {"schema_status": "not_available"},
    )
    _refresh_summary(judge_dir, str(request_data.get("mode") or "legacy"))
    return attempt


def finish_attempt(
    judge_dir: Path,
    attempt: int,
    response_data: dict,
    parsed_data: dict,
) -> Path:
    attempt_dir = judge_dir / f"attempt-{attempt:03d}"
    _write_json(attempt_dir / "response.json", response_data)
    _write_json(attempt_dir / "parsed.json", parsed_data)
    request_data = json.loads(
        (attempt_dir / "request.json").read_text(encoding="utf-8")
    )
    _refresh_summary(judge_dir, str(request_data.get("mode") or "legacy"))
    return attempt_dir
