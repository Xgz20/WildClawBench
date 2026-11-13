"""Filesystem and serialization primitives shared by sandbox execution stages."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import uuid


class E2EError(ValueError):
    """A stable error code suitable for CLI and pipeline consumers."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def identifier(value: str, label: str = "id") -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,119}", value):
        raise E2EError(f"INVALID_{label.upper()}")
    return value


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def read_json(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise E2EError(f"JSON_FILE_INVALID: {path}")
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as error:
        raise E2EError(f"JSON_CONTENT_INVALID: {path}") from error
    if not isinstance(result, dict):
        raise E2EError(f"JSON_OBJECT_REQUIRED: {path}")
    return result


def atomic_json(path: Path, value: object, *, create: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    temporary = path.with_name("." + path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if create:
            # Link publishes a completed file exclusively without exposing partial JSON.
            os.link(temporary, path)
        else:
            os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def relative_path(value: str) -> PurePosixPath:
    if (not isinstance(value, str) or not value or "\\" in value or "\x00" in value
            or value.startswith("/") or any(part in {"", ".", ".."} for part in value.split("/"))
            or ":" in value.split("/", 1)[0]):
        raise E2EError(f"RELATIVE_PATH_INVALID: {value!r}")
    return PurePosixPath(value)


def inside(root: Path, relative: str) -> Path:
    target = root.joinpath(*relative_path(relative).parts)
    if not target.resolve().is_relative_to(root.resolve()):
        raise E2EError("PATH_OUTSIDE_ROOT")
    for parent in (target, *target.parents):
        if parent == root:
            break
        if parent.is_symlink():
            raise E2EError("SYMLINK_IN_MANAGED_PATH")
    return target


def redact(value: object, secrets=()) -> object:
    if isinstance(secrets, str):
        secrets = (secrets,)
    if isinstance(value, dict):
        return {key: "[REDACTED]" if re.fullmatch(
            r"(?:authorization|auth_token|api_key|access_token|refresh_token|password|passwd)",
            str(key), re.I) else redact(item, secrets) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(item, secrets) for item in value]
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, "[REDACTED]")
        return re.sub(r"Bearer\s+\S+", "Bearer [REDACTED]", value, flags=re.I)
    return value


def load_script(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise E2EError(f"MODULE_UNAVAILABLE: {path}")
    module = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module
