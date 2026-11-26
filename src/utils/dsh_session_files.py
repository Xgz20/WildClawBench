"""Standard-library DSH session discovery/reading shared by conversion and reports."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


class DshSessionFormatError(ValueError):
    """A native session cannot be read or converted without losing evidence."""


_ARTIFACT_PATTERN = re.compile(
    r"session(?:\.v(?P<version>[0-9]+))?\.jsonl(?P<compression>\.(?:zst|zstd|gz))?"
)
_SUPPORTED_FILENAMES = frozenset({"session.jsonl", "session.v4.jsonl"})


def _validate_artifact(path: Path) -> None:
    if path.name.endswith((".jsonl.zst", ".jsonl.zstd", ".jsonl.gz")):
        raise DshSessionFormatError(f"compressed session artifact is unsupported: {path}")
    if _ARTIFACT_PATTERN.fullmatch(path.name) and path.name not in _SUPPORTED_FILENAMES:
        raise DshSessionFormatError(f"unsupported versioned session artifact: {path}")


def discover_session_files(session_root: Path) -> list[Path]:
    """Discover supported native files, rejecting unsupported native formats explicitly."""
    session_root = Path(session_root)
    if not session_root.exists():
        raise DshSessionFormatError(f"session root does not exist: {session_root}")
    if session_root.is_file():
        _validate_artifact(session_root)
        candidates = [session_root]
    else:
        candidates = []
        for path in sorted(session_root.rglob("session*.jsonl*")):
            if not path.is_file() or not _ARTIFACT_PATTERN.fullmatch(path.name):
                continue
            _validate_artifact(path)
            candidates.append(path)
    if not candidates:
        raise DshSessionFormatError(
            f"no supported session JSONL found below {session_root} "
            "(expected session.jsonl or session.v4.jsonl)"
        )
    return sorted(candidates, key=lambda path: (len(path.relative_to(session_root).parts), str(path)))


def _read_session(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise DshSessionFormatError(f"cannot read session {path}: {exc}") from exc
    rows = []
    for line_number, raw in enumerate(lines, start=1):
        if not raw.strip():
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise DshSessionFormatError(f"invalid JSON in {path} line {line_number}") from exc
        if not isinstance(value, dict):
            raise DshSessionFormatError(f"session row in {path} line {line_number} is not an object")
        rows.append(value)
    if not rows or rows[0].get("type") != "session":
        raise DshSessionFormatError(f"session header missing in {path}")
    header = rows[0]
    if not isinstance(header.get("version"), int) or isinstance(header.get("version"), bool):
        raise DshSessionFormatError(f"invalid session header version in {path}")
    if path.name == "session.v4.jsonl" and header["version"] != 4:
        raise DshSessionFormatError(f"session artifact/header version mismatch in {path}")
    if not isinstance(header.get("id"), str) or not header["id"]:
        raise DshSessionFormatError(f"invalid session header id in {path}")
    created_at = header.get("createdAt")
    if not isinstance(created_at, int) or isinstance(created_at, bool) or created_at < 0:
        raise DshSessionFormatError(f"invalid session header createdAt in {path}")
    return header, rows[1:]


def load_session_records(session_root: Path) -> list[tuple[dict[str, Any], list[dict[str, Any]]]]:
    """Return metadata/events once per logical session, with duplicate-copy provenance."""
    session_root = Path(session_root)
    sessions = []
    seen: dict[str, tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]] = {}
    for path in discover_session_files(session_root):
        header, events = _read_session(path)
        relative = str(path.relative_to(session_root)) if session_root.is_dir() else path.name
        previous = seen.get(header["id"])
        if previous is not None:
            old_header, old_events, metadata = previous
            if (header, events) != (old_header, old_events):
                raise DshSessionFormatError(
                    f"conflicting duplicate session id {header['id']!r}: "
                    f"{metadata['path']} and {relative}"
                )
            metadata.setdefault("duplicate_paths", []).append(relative)
            continue
        metadata = {**header, "path": relative}
        sessions.append((metadata, events))
        seen[header["id"]] = (header, events, metadata)
    return sessions
