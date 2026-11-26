"""Canonical POSIX link metadata over real Windows relative symbolic links."""
from contextlib import contextmanager
import os
from pathlib import Path
import stat

_READLINK = os.readlink
WINDOWS = os.name == 'nt'


def readlink(path, *args, **kwargs):
    value = _READLINK(path, *args, **kwargs)
    if WINDOWS:
        return value.replace(b'\\', b'/') if isinstance(value, bytes) else value.replace('\\', '/')
    return value


def symlink(target, destination, *, target_is_directory=False):
    native = target.replace('/', '\\') if WINDOWS else target
    os.symlink(native, destination, target_is_directory=target_is_directory)


def mode(path):
    return 0o777 if WINDOWS and path.is_symlink() else stat.S_IMODE(path.lstat().st_mode)


@contextmanager
def rule_readlinks(workspace):
    """Normalize only link text inside the rule worker's candidate workspace.

    The rule source and checks remain byte-for-byte frozen. Windows separators
    express the same relative target and are canonicalized just like artifact
    inventory paths. No target is resolved, opened, changed or manufactured.
    """
    previous = os.readlink
    root = Path(workspace).absolute()
    def scoped(path, *args, **kwargs):
        if WINDOWS and Path(os.fsdecode(path)).absolute().is_relative_to(root):
            return readlink(path, *args, **kwargs)
        return previous(path, *args, **kwargs)
    if WINDOWS:
        os.readlink = scoped
    try:
        yield
    finally:
        os.readlink = previous
