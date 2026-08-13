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
}

_SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+|bearer\s+)[A-Za-z0-9._~+\-/=]+"),
    re.compile(r"(?i)\b([A-Z0-9_]*(?:API_KEY|ACCESS_TOKEN|AUTH_TOKEN|SECRET)\s*[:=]\s*)[^\s,;]+"),
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
    if key.lower() in _SECRET_KEYS or key.lower().endswith(("_key", "_token", "_secret")):
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
    path.write_text(
        json.dumps(_redact(data), ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


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
