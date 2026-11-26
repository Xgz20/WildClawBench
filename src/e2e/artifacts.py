"""Immutable execution originals and verified portable backups."""
from __future__ import annotations

import hashlib
import ctypes
import errno
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import re
import time
import uuid
import zipfile

from .common import E2EError, atomic_json, file_sha256, inside, read_json, relative_path, utc_now


SEAL = ".execution-seal.json"
BACKUP_SCHEMA = "wildclawbench.execution-backup/v2"
MAX_ARCHIVE_BYTES = 8 * 1024**3
OFFICE_SUFFIXES = {'.docx', '.xlsx', '.pptx', '.doc', '.xls', '.ppt', '.odt', '.ods', '.odp'}


def _protect_office_inode(path: Path, descriptor=None):
    # Company host metadata agents can replace a chmod-readonly Office file.
    # A new copy is immutable before its writing descriptor is closed on macOS.
    if sys.platform == 'darwin' and path.suffix.lower() in OFFICE_SUFFIXES:
        observed = path.stat().st_flags
        if observed & stat.UF_IMMUTABLE:
            return
        flags = observed | stat.UF_IMMUTABLE
        if descriptor is not None:
            libc = ctypes.CDLL(None, use_errno=True)
            if libc.fchflags(descriptor, flags) != 0:
                code = ctypes.get_errno()
                raise OSError(code, os.strerror(code), str(path))
        else:
            os.chflags(path, flags, follow_symlinks=False)


def copy_stream_readonly(source, destination: Path, mode=0o444):
    # The importing descriptor can write, while new readers cannot open the
    # inode for writing during population (notably macOS metadata services).
    readonly = (mode | 0o400) & ~0o222
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, readonly)
    with os.fdopen(descriptor, "wb") as output:
        shutil.copyfileobj(source, output)
        output.flush()
        _protect_office_inode(destination, output.fileno())


def inventory(root: Path, *, allow_symlinks=False) -> list[dict]:
    if root.is_symlink() or not root.is_dir():
        raise E2EError("ARTIFACT_ROOT_INVALID")
    rows = []
    for path in sorted(root.rglob("*"), key=lambda p: p.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        relative_path(relative)
        if relative == SEAL:
            continue
        if path.is_symlink() and allow_symlinks:
            from .workspace_links import link_entry
            try:
                row = link_entry(relative, os.readlink(path))
            except (ValueError, RuntimeError) as error:
                raise E2EError(str(error)) from error
            rows.append({**row, 'mode': 0o777})
            continue
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise E2EError(f"UNSUPPORTED_ARTIFACT_TYPE: {relative}")
        row = {"path": relative, "kind": "directory" if path.is_dir() else "file",
               "mode": stat.S_IMODE(path.stat().st_mode)}
        if path.is_file():
            row.update(size=path.stat().st_size, sha256=file_sha256(path))
        rows.append(row)
    return rows


def _verify_tree(root: Path, manifest: dict) -> None:
    actual = inventory(root, allow_symlinks=any(row['kind'] == 'symlink' for row in manifest['entries']))
    # Write permissions may be removed by the explicit readonly protection policy.
    def content(rows):
        return [{key: value for key, value in row.items() if key != "mode"} for row in rows]
    if content(actual) != content(manifest["entries"]):
        raise E2EError("EXECUTION_ORIGINAL_DRIFT")


def _protect(root: Path, *, allow_symlinks=False) -> None:
    for path in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if path.is_symlink():
            if allow_symlinks:
                from .workspace_links import target_path
                target_path(path.relative_to(root).as_posix(), os.readlink(path))
                continue
            raise E2EError("UNSUPPORTED_ARTIFACT_LINK")
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode & 0o222:
            path.chmod(mode & ~0o222)
        if path.is_file():
            _protect_office_inode(path)
    root.chmod(stat.S_IMODE(root.stat().st_mode) & ~0o222)


def remove_temporary_tree(root: Path):
    for attempt in range(3):
        try:
            for path in [root, *root.rglob("*")]:
                if not path.is_symlink():
                    if getattr(path.stat(), 'st_flags', 0) & getattr(stat, 'UF_IMMUTABLE', 0):
                        if path.is_file() and path.stat().st_nlink != 1:
                            raise E2EError('TEMPORARY_IMMUTABLE_HARDLINK_UNSUPPORTED')
                        os.chflags(path, path.stat().st_flags & ~stat.UF_IMMUTABLE, follow_symlinks=False)
                    path.chmod(0o700 if path.is_dir() else 0o600)
            shutil.rmtree(root)
            return
        except OSError as error:
            if error.errno != errno.ENOTEMPTY or attempt == 2:
                raise
            time.sleep(0.05)


def freeze_metadata_files(root: Path):
    for path in root.rglob(".DS_Store"):
        if path.is_symlink():
            raise E2EError("LOCAL_METADATA_LINK_UNSUPPORTED")
        if not path.stat().st_mode & 0o222:
            continue
        temporary = path.with_name(".metadata-snapshot-" + uuid.uuid4().hex)
        mode = stat.S_IMODE(path.parent.stat().st_mode)
        path.parent.chmod(mode | 0o200)
        try:
            with path.open("rb") as source:
                copy_stream_readonly(source, temporary)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
            path.parent.chmod(mode)


def quarantine_local_metadata(root: Path, expected_files: set[str], quarantine: Path, *, allow_symlinks=False) -> list[dict]:
    actual = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file() and (not allow_symlinks or not path.is_symlink())}
    extras = sorted(actual - expected_files)
    if not extras:
        return []
    records = []
    for relative in extras:
        source = inside(root, relative)
        if source.is_symlink():
            raise E2EError("LOCAL_METADATA_LINK_UNSUPPORTED")
        snapshot = relative + ".snapshot"
        destination = inside(quarantine, snapshot)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with source.open("rb") as input_file:
            copy_stream_readonly(input_file, destination)
        record = {"path": relative, "snapshot_path": snapshot,
                  "size": destination.stat().st_size, "sha256": file_sha256(destination)}
        mode = stat.S_IMODE(source.parent.stat().st_mode)
        source.parent.chmod(mode | 0o200)
        try:
            source.unlink()
        finally:
            source.parent.chmod(mode)
        records.append(record)
    atomic_json(quarantine / "quarantine-receipt.json", {
        "schema": "wildclawbench.local-metadata-quarantine/v1", "created_at": utc_now(),
        "source": str(root), "entries": records,
        "basis": "Files absent from the source archive or source tree; preserved outside the candidate payload"})
    if any(Path(row["path"]).name != ".DS_Store" for row in records):
        raise E2EError("UNDECLARED_LOCAL_CONTENT_QUARANTINED")
    actual = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file() and (not allow_symlinks or not path.is_symlink())}
    if actual != expected_files:
        raise E2EError("LOCAL_CONTENT_CHANGED_DURING_QUARANTINE")
    return records


def _members(archive: zipfile.ZipFile, *, allow_symlinks=False) -> dict[str, zipfile.ZipInfo]:
    members = {}
    total = 0
    for info in archive.infolist():
        name = info.filename.rstrip("/")
        relative_path(name)
        kind = stat.S_IFMT(info.external_attr >> 16)
        if name in members or (kind == stat.S_IFLNK and not allow_symlinks):
            raise E2EError("ARCHIVE_DUPLICATE_OR_LINK")
        if kind == stat.S_IFLNK:
            from .workspace_links import target_path
            if info.file_size > 32768:
                raise E2EError('ARCHIVE_LINK_TARGET_TOO_LARGE')
            try:
                target_path(name, archive.read(info).decode('utf-8'))
            except (ValueError, UnicodeError) as error:
                raise E2EError(str(error)) from error
        members[name] = info
        total += info.file_size
        if len(members) > 100_000 or total > MAX_ARCHIVE_BYTES:
            raise E2EError("ARCHIVE_LIMIT_EXCEEDED")
    for name in members:
        for parent in relative_path(name).parents:
            parent_name = parent.as_posix()
            if parent_name != "." and parent_name in members and not members[parent_name].is_dir():
                raise E2EError("ARCHIVE_FILE_AS_PARENT")
    return members


def write_zip_member(archive, root, row):
    if row['kind'] == 'symlink':
        info = zipfile.ZipInfo(row['path'])
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, row['target'].encode('utf-8'))
    else:
        archive.write(inside(root, row['path']), row['path'])


def materialize_zip_links(archive, members, root, *, strip_root=False):
    from .workspace_links import install
    links = []
    for name, info in members.items():
        if stat.S_IFMT(info.external_attr >> 16) == stat.S_IFLNK:
            relative = '/'.join(name.split('/')[1:]) if strip_root else name
            links.append({'path': relative, 'target': archive.read(info).decode('utf-8')})
    if links:
        try:
            install(root, links)
        except ValueError as error:
            raise E2EError(str(error)) from error


def _verify_archive(path: Path, expected_seal_sha: str | None = None) -> dict:
    with zipfile.ZipFile(path) as archive:
        members = _members(archive, allow_symlinks=True)
        if SEAL not in members:
            raise E2EError("ARCHIVE_SEAL_MISSING")
        seal_bytes = archive.read(SEAL)
        if expected_seal_sha and hashlib.sha256(seal_bytes).hexdigest() != expected_seal_sha:
            raise E2EError("ARCHIVE_SEAL_MISMATCH")
        manifest = json.loads(seal_bytes)
        if manifest.get("schema") not in {"wildclawbench.execution-original/v1", "wildclawbench.execution-original/v2"}:
            raise E2EError("ARCHIVE_SEAL_SCHEMA_INVALID")
        entries = manifest["entries"]
        if not isinstance(entries, list) or not isinstance(manifest.get("identity"), dict):
            raise E2EError("ARCHIVE_SEAL_INVALID")
        if manifest['schema'].endswith('/v1') and any(isinstance(row, dict) and row.get('kind') == 'symlink' for row in entries):
            raise E2EError('ARCHIVE_LINK_SCHEMA_REQUIRED')
        for row in entries:
            if (not isinstance(row, dict) or row.get("kind") not in {"file", "directory", "symlink"}
                    or type(row.get("mode")) is not int or not 0 <= row["mode"] <= 0o777):
                raise E2EError("ARCHIVE_ENTRY_INVALID")
            if row["kind"] in {'file', 'symlink'} and (type(row.get("size")) is not int or row["size"] < 0
                    or not re.fullmatch(r"[0-9a-f]{64}", str(row.get("sha256")))):
                raise E2EError("ARCHIVE_ENTRY_CONTENT_INVALID")
        if len({row["path"] for row in entries}) != len(entries):
            raise E2EError("ARCHIVE_SEAL_DUPLICATE_ENTRY")
        if set(members) != {row["path"] for row in entries} | {SEAL}:
            raise E2EError("ARCHIVE_MEMBER_SET_MISMATCH")
        for row in entries:
            relative_path(row["path"])
            info = members[row["path"]]
            if info.is_dir() != (row["kind"] == "directory"):
                raise E2EError("ARCHIVE_MEMBER_TYPE_MISMATCH")
            is_link = stat.S_IFMT(info.external_attr >> 16) == stat.S_IFLNK
            if is_link != (row['kind'] == 'symlink'):
                raise E2EError('ARCHIVE_MEMBER_TYPE_MISMATCH')
            if row['kind'] == 'symlink' and archive.read(info).decode('utf-8') != row.get('target'):
                raise E2EError('ARCHIVE_LINK_TARGET_MISMATCH')
            if row["kind"] in {'file', 'symlink'}:
                if info.file_size != row["size"]:
                    raise E2EError("ARCHIVE_MEMBER_SIZE_MISMATCH")
                h = hashlib.sha256()
                with archive.open(info) as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        h.update(chunk)
                if h.hexdigest() != row["sha256"]:
                    raise E2EError("ARCHIVE_MEMBER_SHA_MISMATCH")
        return manifest


def extract_zip(archive_path: Path, destination: Path, *, strip_root: bool = False, readonly_data: bool = False, allow_symlinks=False):
    if destination.exists():
        raise E2EError("EXTRACT_DESTINATION_EXISTS")
    destination.mkdir(parents=True)
    try:
        with zipfile.ZipFile(archive_path) as archive:
            members = _members(archive, allow_symlinks=allow_symlinks)
            roots = {relative_path(name).parts[0] for name in members}
            if strip_root and len(roots) != 1:
                raise E2EError("ARCHIVE_ROOT_AMBIGUOUS")
            for name, info in members.items():
                if stat.S_IFMT(info.external_attr >> 16) == stat.S_IFLNK:
                    continue
                parts = relative_path(name).parts[1:] if strip_root else relative_path(name).parts
                if not parts:
                    continue
                path = inside(destination, "/".join(parts))
                if info.is_dir():
                    path.mkdir(parents=True, exist_ok=True)
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    mode = stat.S_IMODE(info.external_attr >> 16)
                    protected = readonly_data and (path.name == ".DS_Store" or "workspace" in parts or "execution-source" in parts)
                    if protected:
                        with archive.open(info) as source:
                            copy_stream_readonly(source, path, mode)
                    else:
                        with archive.open(info) as source, path.open("xb") as output:
                            shutil.copyfileobj(source, output)
                        path.chmod(mode | 0o600)
            if allow_symlinks:
                materialize_zip_links(archive, members, destination, strip_root=strip_root)
    except BaseException:
        remove_temporary_tree(destination)
        raise


def seal_execution(execution_root: Path, identity: dict) -> dict:
    staging = execution_root / "staging"
    original = execution_root / "original"
    backups = execution_root / "backups"
    receipt_path = backups / "backup-receipt.json"
    if receipt_path.exists():
        receipt = verify_execution(execution_root)
        if receipt["identity"] != identity:
            raise E2EError("EXECUTION_IDENTITY_CONFLICT")
        _protect(original, allow_symlinks=True)
        return receipt
    if not original.exists():
        if not staging.is_dir():
            raise E2EError("EXECUTION_STAGING_MISSING")
        freeze_metadata_files(staging)
        rows = inventory(staging, allow_symlinks=True)
        version = 2 if any(row['kind'] == 'symlink' for row in rows) else 1
        manifest = {"schema": "wildclawbench.execution-original/v" + str(version), "identity": identity,
                    "created_at": utc_now(), "entries": rows}
        atomic_json(staging / SEAL, manifest, create=True)
        staging.rename(original)
    manifest = read_json(original / SEAL)
    if manifest["identity"] != identity:
        raise E2EError("EXECUTION_IDENTITY_CONFLICT")
    _protect(original, allow_symlinks=True)
    _verify_tree(original, manifest)
    backups.mkdir(exist_ok=True)
    temporary = backups / (".execution-" + uuid.uuid4().hex + ".zip")
    try:
        with zipfile.ZipFile(temporary, "x", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            for row in manifest["entries"]:
                write_zip_member(archive, original, row)
            archive.write(original / SEAL, SEAL)
        seal_sha = file_sha256(original / SEAL)
        _verify_archive(temporary, seal_sha)
        final = backups / "execution-original.zip"
        if final.exists():
            _verify_archive(final, seal_sha)
            temporary.unlink()
        else:
            temporary.rename(final)
        receipt = {"schema": BACKUP_SCHEMA, "identity": identity, "created_at": utc_now(),
                   "archive": "backups/execution-original.zip", "archive_sha256": file_sha256(final),
                   "seal_sha256": seal_sha, "entry_count": len(manifest["entries"])}
        atomic_json(receipt_path, receipt, create=True)
        return receipt
    finally:
        temporary.unlink(missing_ok=True)


def verify_backup(execution_root: Path) -> tuple[dict, dict]:
    receipt = read_json(execution_root / "backups/backup-receipt.json")
    if receipt.get("schema") != BACKUP_SCHEMA:
        raise E2EError("BACKUP_SCHEMA_UNSUPPORTED")
    archive = inside(execution_root, receipt["archive"])
    if file_sha256(archive) != receipt["archive_sha256"]:
        raise E2EError("BACKUP_ARCHIVE_DRIFT")
    manifest = _verify_archive(archive, receipt["seal_sha256"])
    if manifest["identity"] != receipt["identity"]:
        raise E2EError("BACKUP_IDENTITY_MISMATCH")
    return receipt, manifest


def verify_execution(execution_root: Path) -> dict:
    receipt, manifest = verify_backup(execution_root)
    if file_sha256(execution_root / "original" / SEAL) != receipt["seal_sha256"]:
        raise E2EError("EXECUTION_SEAL_DRIFT")
    _verify_tree(execution_root / "original", manifest)
    return receipt


def execution_source(execution_root: Path) -> tuple[Path, dict]:
    receipt, manifest = verify_backup(execution_root)
    task_root = execution_root.parent.parent
    pointer = task_root / "restores/current.json"
    source = execution_root / "original"
    if pointer.exists():
        restoration = read_json(pointer)
        if (restoration.get("identity") != receipt["identity"]
                or restoration.get("source_archive_sha256") != receipt["archive_sha256"]):
            raise E2EError("RESTORE_SOURCE_BINDING_INVALID")
        source = Path(restoration["destination"]).resolve()
        if not source.is_relative_to((task_root / "restores").resolve()):
            raise E2EError("RESTORE_SOURCE_PATH_INVALID")
    if file_sha256(source / SEAL) != receipt["seal_sha256"]:
        raise E2EError("EXECUTION_SEAL_DRIFT")
    _verify_tree(source, manifest)
    return source, receipt


def restore_execution(execution_root: Path, destination: Path) -> dict:
    receipt, manifest = verify_backup(execution_root)
    if destination.exists() or destination.is_symlink():
        raise E2EError("RESTORE_DESTINATION_EXISTS")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name("." + destination.name + ".restoring-" + uuid.uuid4().hex)
    temporary.mkdir()
    try:
        with zipfile.ZipFile(inside(execution_root, receipt["archive"])) as archive:
            for row in manifest["entries"]:
                if row["kind"] == "symlink":
                    continue
                path = inside(temporary, row["path"])
                if row["kind"] == "directory":
                    path.mkdir(parents=True, exist_ok=True)
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(row["path"]) as source:
                        copy_stream_readonly(source, path, row["mode"])
            materialize_zip_links(archive, _members(archive, allow_symlinks=True), temporary)
            with archive.open(SEAL) as source:
                copy_stream_readonly(source, temporary / SEAL)
        _protect(temporary, allow_symlinks=True)
        expected_files = {row["path"] for row in manifest["entries"] if row["kind"] == "file"} | {SEAL}
        quarantine_local_metadata(temporary, expected_files, destination.parent / ".local-metadata" / uuid.uuid4().hex, allow_symlinks=True)
        _verify_tree(temporary, manifest)
        temporary.rename(destination)
    finally:
        if temporary.exists():
            remove_temporary_tree(temporary)
    return {"schema": "wildclawbench.execution-restoration/v1", "identity": receipt["identity"],
            "source_archive_sha256": receipt["archive_sha256"], "destination": str(destination), "readonly": True,
            "created_at": utc_now()}


def export_execution(execution_root: Path, destination: Path) -> dict:
    receipt, _ = verify_backup(execution_root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.with_suffix(destination.suffix + ".json").exists():
        raise E2EError("EXPORT_DESTINATION_EXISTS")
    with inside(execution_root, receipt["archive"]).open("rb") as source, destination.open("xb") as target:
        shutil.copyfileobj(source, target)
    if file_sha256(destination) != receipt["archive_sha256"]:
        raise E2EError("EXPORT_COPY_MISMATCH")
    exported = {**receipt, "archive": destination.name}
    atomic_json(destination.with_suffix(destination.suffix + ".json"), exported, create=True)
    return exported


def import_execution(archive_path: Path, receipt_path: Path, destination: Path) -> dict:
    receipt = read_json(receipt_path)
    if receipt.get("schema") != BACKUP_SCHEMA or file_sha256(archive_path) != receipt["archive_sha256"]:
        raise E2EError("IMPORT_ARCHIVE_INVALID")
    manifest = _verify_archive(archive_path, receipt["seal_sha256"])
    if manifest["identity"] != receipt["identity"]:
        raise E2EError("IMPORT_IDENTITY_MISMATCH")
    if destination.exists():
        existing = verify_execution(destination)
        if existing["identity"] == receipt["identity"] and existing["archive_sha256"] == receipt["archive_sha256"]:
            return {"status": "already_imported", "identity": receipt["identity"]}
        raise E2EError("IMPORT_DESTINATION_CONFLICT")
    temporary = destination.with_name("." + destination.name + ".import-" + uuid.uuid4().hex)
    (temporary / "backups").mkdir(parents=True)
    try:
        shutil.copyfile(archive_path, temporary / "backups/execution-original.zip")
        imported = {**receipt, "archive": "backups/execution-original.zip"}
        atomic_json(temporary / "backups/backup-receipt.json", imported)
        restore_execution(temporary, temporary / "original")
        _protect(temporary / "original", allow_symlinks=True)
        temporary.rename(destination)
    finally:
        if temporary.exists():
            remove_temporary_tree(temporary)
    return {"status": "imported", "identity": receipt["identity"], "destination": str(destination)}
