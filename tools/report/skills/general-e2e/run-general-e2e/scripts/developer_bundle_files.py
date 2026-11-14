"""Preserve bytes of newly materialized developer-bundle files."""
import hashlib
import os
from pathlib import Path
import shutil
import stat
import sys


OFFICE_SUFFIXES = {'.docx', '.xlsx', '.pptx', '.docm', '.xlsm', '.pptm', '.bin'}


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def protect_office_copy(path):
    """Protect only a new regular copy, before recording or checking its hash."""
    path = Path(path)
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError('DEVELOPER_COPY_NOT_REGULAR: ' + str(path))
    if sys.platform == 'darwin' and path.suffix.lower() in OFFICE_SUFFIXES:
        os.chflags(path, path.stat().st_flags | stat.UF_IMMUTABLE, follow_symlinks=False)


def copy_protected_file(source, target):
    """copytree-compatible copy; never unlock or normalize the source."""
    source, target = Path(source), Path(target)
    if not stat.S_ISREG(source.lstat().st_mode) or os.path.lexists(target):
        raise ValueError('DEVELOPER_COPY_UNSAFE: ' + str(source))
    before = sha256_file(source)
    shutil.copy2(source, target)
    protect_office_copy(target)
    if sha256_file(target) != before or sha256_file(source) != before:
        raise ValueError('DEVELOPER_COPY_DRIFT: ' + str(source))
    return str(target)


def write_protected_file(target, payload, mode=0o644):
    target = Path(target)
    with target.open('xb') as stream:
        stream.write(payload)
    target.chmod(mode)
    protect_office_copy(target)
    if sha256_file(target) != hashlib.sha256(payload).hexdigest():
        raise ValueError('DEVELOPER_COPY_DRIFT: ' + str(target))
