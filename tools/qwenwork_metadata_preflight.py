#!/usr/bin/env python3
"""Read-only preflight for QwenWork native metadata bindings."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterator


SESSION_KEYS = ("sessionId", "session_id", "sessionID")
CWD_KEYS = ("cwd", "workingDirectory", "working_directory")


def _objects(path: Path) -> Iterator[dict[str, Any]]:
    try:
        if path.suffix.lower() == ".jsonl":
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    value = json.loads(line)
                    if isinstance(value, dict):
                        yield value
        elif path.suffix.lower() == ".json":
            value = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                yield value
            elif isinstance(value, list):
                yield from (item for item in value if isinstance(item, dict))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return


def _walk(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _field(row: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _is_segment(row: dict[str, Any]) -> bool:
    marker = str(row.get("type") or row.get("record_type") or row.get("kind") or "").lower()
    return marker in {"segment", "message_segment", "conversation_segment"} or "segmentId" in row or "segment_id" in row


def inspect(root: Path) -> dict[str, Any]:
    root = root.expanduser().resolve()
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")) if root.is_dir() else [root]:
        if path.is_file() and path.suffix.lower() in {".json", ".jsonl"}:
            for parsed in _objects(path):
                rows.extend(_walk(parsed))
    identity_rows = [row for row in rows if not _is_segment(row)] or rows
    sessions = sorted({value for row in identity_rows if (value := _field(row, SESSION_KEYS))})
    cwds = sorted({value for row in identity_rows if (value := _field(row, CWD_KEYS)) and Path(value).is_absolute()})
    session_id = sessions[0] if len(sessions) == 1 else None
    cwd = str(Path(cwds[0]).resolve()) if len(cwds) == 1 else None
    segments = [row for row in rows if _is_segment(row)]

    def binding(keys: tuple[str, ...], expected: str | None, *, absolute: bool = False) -> dict[str, Any]:
        known = total = missing = mismatched = 0
        for row in segments:
            total += 1
            value = _field(row, keys)
            if absolute and value and not Path(value).is_absolute():
                value = None
            if not value:
                missing += 1
            elif expected is not None and (str(Path(value).resolve()) if absolute else value) != expected:
                mismatched += 1
            else:
                known += 1
        return {"known": known, "total": total, "missing": missing, "mismatched": mismatched}

    return {
        "log_root": str(root),
        "sessionId": session_id,
        "cwd": cwd,
        "segments": {
            "session": binding(SESSION_KEYS, session_id),
            "workspace": binding(CWD_KEYS, cwd, absolute=True),
        },
        "usage": None,
        "terminal": None,
        "status": "ready" if segments and session_id and cwd and all(item["missing"] == 0 and item["mismatched"] == 0 for item in (binding(SESSION_KEYS, session_id), binding(CWD_KEYS, cwd, absolute=True))) else "blocked",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="只读核验 QwenWork 原始日志 metadata 绑定")
    parser.add_argument("log_root", type=Path, help="指定原始日志文件或目录")
    args = parser.parse_args()
    print(json.dumps(inspect(args.log_root), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
