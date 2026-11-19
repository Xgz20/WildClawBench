"""Reference implementation for grading validation."""

import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
import zipfile


class ExtractionError(ValueError):
    """Raised when a plugin bundle cannot be installed safely."""


def _validate_limit(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ExtractionError(f"{name} must be a positive integer")


def _assert_no_existing_symlink(path, trusted_root):
    absolute = path.absolute()
    trusted = trusted_root.absolute()
    try:
        relative = absolute.relative_to(trusted)
    except ValueError:
        # The caller may store downloads and installations under separate
        # roots. In that case, at minimum reject the destination and its
        # immediate parent without treating platform aliases such as macOS
        # /tmp -> /private/tmp as attacker-controlled components.
        if absolute.is_symlink() or absolute.parent.is_symlink():
            raise ExtractionError("install path contains a symbolic link")
        return
    cursor = trusted
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ExtractionError("install path contains a symbolic link")
        if not cursor.exists():
            break


def _member_path(info):
    raw = info.filename
    portable = raw.replace("\\", "/")
    if (
        not raw
        or portable.startswith("/")
        or portable.startswith("//")
        or re.match(r"^[A-Za-z]:", portable)
    ):
        raise ExtractionError("absolute archive member path")
    pure = PurePosixPath(portable)
    if any(part == ".." for part in pure.parts):
        raise ExtractionError("archive member escapes destination")
    parts = tuple(part for part in pure.parts if part not in {"", "."})
    if not parts:
        raise ExtractionError("empty archive member path")

    mode = (info.external_attr >> 16) & 0o177777
    file_type = stat.S_IFMT(mode)
    if file_type == stat.S_IFLNK:
        raise ExtractionError("archive symbolic links are forbidden")
    if file_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
        raise ExtractionError("special archive entries are forbidden")
    if info.flag_bits & 0x1:
        raise ExtractionError("encrypted archive entries are unsupported")
    return parts, info.is_dir() or file_type == stat.S_IFDIR


def extract_plugin(
    archive_path,
    install_dir,
    *,
    max_entries=128,
    max_uncompressed_bytes=8 * 1024 * 1024,
):
    """Extract a validated ZIP into a new install directory atomically."""
    _validate_limit(max_entries, "max_entries")
    _validate_limit(max_uncompressed_bytes, "max_uncompressed_bytes")
    archive_path = Path(archive_path)
    install_dir = Path(install_dir)

    _assert_no_existing_symlink(install_dir, archive_path.parent)
    if install_dir.exists() or install_dir.is_symlink():
        raise ExtractionError("install directory already exists")

    try:
        bundle = zipfile.ZipFile(archive_path)
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise ExtractionError("invalid ZIP bundle") from exc

    stage_root = None
    try:
        with bundle:
            members = bundle.infolist()
            if len(members) > max_entries:
                raise ExtractionError("bundle has too many entries")
            if sum(info.file_size for info in members) > max_uncompressed_bytes:
                raise ExtractionError("bundle is too large")

            normalized = []
            seen = {}
            for info in members:
                parts, is_directory = _member_path(info)
                key = "/".join(parts).casefold()
                if key in seen:
                    raise ExtractionError("normalized archive name collision")
                for index in range(1, len(parts)):
                    parent = "/".join(parts[:index]).casefold()
                    if seen.get(parent) is False:
                        raise ExtractionError("file and directory name collision")
                if not is_directory:
                    prefix = key + "/"
                    if any(existing.startswith(prefix) for existing in seen):
                        raise ExtractionError("file and directory name collision")
                seen[key] = is_directory
                normalized.append((info, parts, is_directory))

            install_dir.parent.mkdir(parents=True, exist_ok=True)
            _assert_no_existing_symlink(install_dir, archive_path.parent)
            stage_root = Path(
                tempfile.mkdtemp(prefix=f".{install_dir.name}.stage-", dir=install_dir.parent)
            )
            payload = stage_root / "payload"
            payload.mkdir()
            files = []
            copied = 0
            for info, parts, is_directory in normalized:
                target = payload.joinpath(*parts)
                if is_directory:
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(info, "r") as source, target.open("xb") as output:
                    while True:
                        chunk = source.read(65536)
                        if not chunk:
                            break
                        copied += len(chunk)
                        if copied > max_uncompressed_bytes:
                            raise ExtractionError("expanded data exceeds size limit")
                        output.write(chunk)
                files.append("/".join(parts))

            _assert_no_existing_symlink(install_dir, archive_path.parent)
            if install_dir.exists() or install_dir.is_symlink():
                raise ExtractionError("install directory appeared during extraction")
            os.replace(payload, install_dir)
            return sorted(files)
    except ExtractionError:
        raise
    except (OSError, RuntimeError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise ExtractionError("bundle extraction failed") from exc
    finally:
        if stage_root is not None:
            shutil.rmtree(stage_root, ignore_errors=True)
