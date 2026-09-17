"""Deterministic evidence-reference validation and indexing."""

from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from ._validation import SHA256_RE, canonical_json_bytes
from .errors import GradingCoreError


EVIDENCE_INDEX_SCHEMA = "wildclawbench.general-e2e-evidence-index/v1"
_EVIDENCE_KEYS = frozenset({"type", "path", "event_ids", "sha256"})


def _safe_relative_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\0" in value:
        raise GradingCoreError("EVIDENCE_PATH_INVALID", f"invalid path: {value!r}")
    relative = PurePosixPath(value)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise GradingCoreError("EVIDENCE_PATH_INVALID", f"unsafe path: {value!r}")
    return relative.as_posix()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_reference(
    raw: Mapping[str, Any],
    *,
    base_dir: Path | None,
    known_event_ids: set[str] | None,
) -> tuple[dict[str, Any], bool, bool]:
    unknown = sorted(set(raw) - _EVIDENCE_KEYS)
    if unknown:
        raise GradingCoreError(
            "EVIDENCE_REFERENCE_INVALID", f"unsupported keys: {unknown}"
        )
    evidence_type = raw.get("type")
    if not isinstance(evidence_type, str) or not evidence_type:
        raise GradingCoreError(
            "EVIDENCE_REFERENCE_INVALID", "type must be non-empty"
        )
    reference: dict[str, Any] = {"type": evidence_type}
    path_verified = False
    if "path" in raw:
        relative = _safe_relative_path(raw.get("path"))
        reference["path"] = relative
        if base_dir is not None:
            target = base_dir.joinpath(*PurePosixPath(relative).parts)
            try:
                target.resolve().relative_to(base_dir.resolve())
            except (OSError, ValueError) as exc:
                raise GradingCoreError(
                    "EVIDENCE_PATH_INVALID", f"path escapes evidence root: {relative}"
                ) from exc
            if not target.is_file() or target.is_symlink():
                raise GradingCoreError(
                    "EVIDENCE_FILE_MISSING", f"evidence file unavailable: {relative}"
                )
            actual_sha = _sha256_file(target)
            declared_sha = raw.get("sha256")
            if declared_sha is not None and declared_sha != actual_sha:
                raise GradingCoreError(
                    "EVIDENCE_DIGEST_MISMATCH", f"sha256 mismatch: {relative}"
                )
            reference["sha256"] = actual_sha
            path_verified = True
        elif "sha256" in raw:
            declared_sha = raw.get("sha256")
            if declared_sha is not None and (
                not isinstance(declared_sha, str) or not SHA256_RE.fullmatch(declared_sha)
            ):
                raise GradingCoreError(
                    "EVIDENCE_REFERENCE_INVALID", "sha256 must be null or lowercase hex"
                )
            reference["sha256"] = declared_sha
    elif "sha256" in raw:
        raise GradingCoreError(
            "EVIDENCE_REFERENCE_INVALID", "sha256 requires path"
        )

    events_verified = False
    if "event_ids" in raw:
        event_ids = raw.get("event_ids")
        if (
            not isinstance(event_ids, list)
            or not event_ids
            or any(not isinstance(event, str) or not event for event in event_ids)
            or len(event_ids) != len(set(event_ids))
        ):
            raise GradingCoreError(
                "EVIDENCE_REFERENCE_INVALID",
                "event_ids must be unique non-empty strings",
            )
        if known_event_ids is not None:
            missing = sorted(set(event_ids) - known_event_ids)
            if missing:
                raise GradingCoreError(
                    "EVIDENCE_EVENT_MISSING",
                    f"unknown transcript event IDs: {missing}",
                )
            events_verified = True
        reference["event_ids"] = list(event_ids)
    if "path" not in reference and "event_ids" not in reference:
        raise GradingCoreError(
            "EVIDENCE_REFERENCE_INVALID", "reference requires path or event_ids"
        )
    return reference, path_verified, events_verified


def build_evidence_index(
    evidence: Sequence[Mapping[str, Any]],
    *,
    base_dir: str | Path | None = None,
    known_event_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Validate evidence references and return a deterministic lookup index."""

    if not isinstance(evidence, Sequence) or isinstance(evidence, (str, bytes)):
        raise GradingCoreError(
            "EVIDENCE_INDEX_INVALID", "evidence must be an array"
        )
    root = Path(base_dir).expanduser().resolve() if base_dir is not None else None
    if root is not None and (not root.is_dir() or root.is_symlink()):
        raise GradingCoreError(
            "EVIDENCE_ROOT_INVALID", f"invalid evidence root: {root}"
        )
    events = set(known_event_ids) if known_event_ids is not None else None
    entries: list[dict[str, Any]] = []
    seen: set[bytes] = set()
    by_type: dict[str, list[str]] = {}
    for index, raw in enumerate(evidence, start=1):
        if not isinstance(raw, Mapping):
            raise GradingCoreError(
                "EVIDENCE_REFERENCE_INVALID", "evidence entries must be objects"
            )
        reference, path_verified, events_verified = _normalize_reference(
            raw, base_dir=root, known_event_ids=events
        )
        key = canonical_json_bytes(reference)
        if key in seen:
            raise GradingCoreError(
                "EVIDENCE_REFERENCE_DUPLICATE", f"duplicate evidence at index {index}"
            )
        seen.add(key)
        evidence_id = f"evidence-{index:04d}"
        entries.append(
            {
                "id": evidence_id,
                "reference": reference,
                "path_verified": path_verified,
                "events_verified": events_verified,
            }
        )
        by_type.setdefault(reference["type"], []).append(evidence_id)
    digest_input = {
        "schema_version": EVIDENCE_INDEX_SCHEMA,
        "entries": entries,
        "by_type": by_type,
    }
    return {
        **digest_input,
        "digest_algorithm": "sha256-canonical-json/v1",
        "digest": hashlib.sha256(canonical_json_bytes(digest_input)).hexdigest(),
    }


def evidence_reference_set(index: Mapping[str, Any]) -> set[bytes]:
    if index.get("schema_version") != EVIDENCE_INDEX_SCHEMA:
        raise GradingCoreError(
            "EVIDENCE_INDEX_INVALID", "evidence index schema mismatch"
        )
    entries = index.get("entries")
    if not isinstance(entries, list):
        raise GradingCoreError(
            "EVIDENCE_INDEX_INVALID", "entries must be an array"
        )
    result: set[bytes] = set()
    for entry in entries:
        if not isinstance(entry, Mapping) or not isinstance(entry.get("reference"), Mapping):
            raise GradingCoreError(
                "EVIDENCE_INDEX_INVALID", "entry reference missing"
            )
        result.add(canonical_json_bytes(entry["reference"]))
    return result
