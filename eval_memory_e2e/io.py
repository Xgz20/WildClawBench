"""Strict JSON, immutable artifacts and process-scoped journal locking."""

from __future__ import annotations

import contextlib
import hashlib
import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path


class MemoryEvaluationError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def require(condition, code, message):
    if not condition:
        raise MemoryEvaluationError(code, message)


def identifier(value):
    require(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", value),
            "INVALID_ID", f"Invalid identifier: {value!r}")
    return value


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False,
                       separators=(",", ":")) + "\n").encode("utf-8")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def digest(value):
    return sha(encoded(value))


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "DUPLICATE_JSON_KEY", key)
        result[key] = value
    return result


def decode(data):
    def invalid(value):
        raise MemoryEvaluationError("NONFINITE_JSON", value)
    def finite_float(value):
        result = float(value)
        require(math.isfinite(result), "NONFINITE_JSON", value)
        return result
    try:
        return json.loads(data, object_pairs_hook=_pairs, parse_constant=invalid, parse_float=finite_float)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise MemoryEvaluationError("INVALID_JSON", str(exc)) from exc


def read_json(path):
    return decode(Path(path).read_bytes())


def safe_file(path, root=None):
    path = Path(path).absolute()
    for parent in (path, *path.parents):
        require(not parent.is_symlink(), "SYMLINK_REJECTED", str(parent))
    require(path.is_file(), "MISSING_ARTIFACT", str(path))
    path = path.resolve()
    if root is not None:
        require(path.is_relative_to(Path(root).resolve()), "PATH_ESCAPE", str(path))
    return path


def publish(path, value):
    """Exclusive publication: never replace a frozen input or evidence file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    for parent in (path, *path.parents):
        require(not parent.is_symlink(), "SYMLINK_REJECTED", str(parent))
    data = value if isinstance(value, bytes) else encoded(value)
    # A partial exclusive write stays visible as invalid evidence after a crash.
    # It is not silently replaced on a retry.
    try:
        with path.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise MemoryEvaluationError("OUTPUT_EXISTS", str(path)) from exc
    return path


def archive(root, source):
    source = safe_file(source)
    require(source.stat().st_size <= 100 * 1024 * 1024, "ARTIFACT_BUDGET", "Archive per-step evidence, not an unbounded account database")
    data = source.read_bytes()
    checksum = sha(data)
    relative = f"evidence/blobs/{checksum}"
    target = Path(root) / relative
    if target.exists():
        require(sha(safe_file(target, root).read_bytes()) == checksum, "ARTIFACT_DRIFT", relative)
    else:
        publish(target, data)
    return {"path": relative, "sha256": checksum, "size": len(data)}


def verify_artifact(root, item):
    require(isinstance(item, dict) and set(item) == {"path", "sha256", "size"},
            "ARTIFACT_SHAPE", "Artifact must have path, sha256 and size")
    relative = Path(item["path"])
    require(not relative.is_absolute() and ".." not in relative.parts,
            "PATH_ESCAPE", str(relative))
    data = safe_file(Path(root) / relative, root).read_bytes()
    require(sha(data) == item["sha256"] and len(data) == item["size"],
            "ARTIFACT_DRIFT", str(relative))
    return data


@contextlib.contextmanager
def lock(root):
    """fcntl locks release on process death; a stale PID file is never deleted."""
    import fcntl
    path = Path(root) / ".controller.lock"
    require(not path.is_symlink(), "SYMLINK_REJECTED", str(path))
    with path.open("a+b") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise MemoryEvaluationError("CONTROLLER_BUSY", str(root)) from exc
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def events(root):
    path = Path(root) / "events.jsonl"
    if not path.exists():
        return []
    data = safe_file(path, root).read_bytes()
    require(not data or data.endswith(b"\n"), "JOURNAL_TRUNCATED", "Keep original journal for recovery")
    result, previous = [], "0" * 64
    for line in data.splitlines():
        event = decode(line)
        checksum = event.pop("sha256", None)
        require(event.get("sequence") == len(result) and event.get("previous") == previous
                and digest(event) == checksum, "JOURNAL_INTEGRITY", str(len(result)))
        previous = checksum
        event["sha256"] = checksum
        result.append(event)
    return result


def append(root, kind, episode_id, payload):
    history = events(root)
    event = {"sequence": len(history), "previous": history[-1]["sha256"] if history else "0" * 64,
             "time": timestamp(), "kind": kind, "episode_id": episode_id, "payload": payload}
    event["sha256"] = digest(event)
    with (Path(root) / "events.jsonl").open("ab") as stream:
        stream.write(encoded(event))
        stream.flush()
        os.fsync(stream.fileno())
    return event
