"""Portable relative-link transport. Also runs standalone in the owned Windows VM.

No link is opened or traversed while taking a candidate snapshot. Only relative
links staying inside their workspace are supported; arbitrary reparse points are
never treated as ordinary directories.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import shutil
import stat
import zipfile


SCHEMA = 'wildclawbench.workspace-links/v1'


def plain_windows_ancestors(path):
    if os.name != 'nt':
        return
    for current in (Path(path), *Path(path).parents):
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('WORKSPACE_ROOT_REPARSE_POINT_UNSUPPORTED')


def relative(value):
    if (not isinstance(value, str) or not value or '\\' in value or ':' in value or '\x00' in value
            or value.startswith('/') or any(p in {'', '.', '..'} for p in value.split('/'))):
        raise ValueError('WORKSPACE_LINK_PATH_INVALID: ' + repr(value))
    return PurePosixPath(value)


def target_path(path, target):
    relative(path)
    if (not isinstance(target, str) or not target or '\x00' in target or ':' in target
            or target.startswith(('/', '\\'))):
        raise ValueError('WORKSPACE_LINK_TARGET_INVALID: ' + path)
    normalized = target.replace('\\', '/')
    result = posixpath.normpath(posixpath.join(posixpath.dirname(path), normalized))
    if result == '..' or result.startswith('../') or result.startswith('/'):
        raise ValueError('WORKSPACE_LINK_TARGET_OUTSIDE: ' + path)
    return result


def link_entry(path, target):
    target_path(path, target)
    payload = target.encode('utf-8')
    return {'path': path, 'kind': 'symlink', 'target': target,
            'size': len(payload), 'sha256': hashlib.sha256(payload).hexdigest()}


def file_hash(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def entries(root):
    root = Path(root)
    plain_windows_ancestors(root)
    if root.is_symlink() or not root.is_dir() or getattr(root.lstat(), 'st_file_attributes', 0) & 0x400:
        raise ValueError('WORKSPACE_LINK_ROOT_INVALID')
    result = []
    def visit(directory):
        for child in sorted(directory.iterdir(), key=lambda p: p.name):
            name = child.relative_to(root).as_posix()
            relative(name)
            mode = child.lstat().st_mode
            if stat.S_ISLNK(mode):
                target = os.readlink(child).replace('\\', '/')
                result.append(link_entry(name, target))
            elif getattr(child.lstat(), 'st_file_attributes', 0) & 0x400:
                raise ValueError('WORKSPACE_REPARSE_POINT_UNSUPPORTED: ' + name)
            elif stat.S_ISDIR(mode):
                result.append({'path': name, 'kind': 'directory'})
                visit(child)
            elif stat.S_ISREG(mode):
                result.append({'path': name, 'kind': 'file', 'size': child.stat().st_size, 'sha256': file_hash(child)})
            else:
                raise ValueError('WORKSPACE_SPECIAL_FILE_UNSUPPORTED: ' + name)
            if len(result) > 100000:
                raise ValueError('WORKSPACE_FILE_LIMIT_EXCEEDED')
    visit(root)
    return sorted(result, key=lambda row: row['path'])


def install(root, links):
    root = Path(root)
    plain_windows_ancestors(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('WORKSPACE_LINK_ROOT_INVALID')
    seen = set()
    targets = {row['path']: row['target'] for row in links}
    for row in links:
        path, target = row['path'], row['target']
        target_path(path, target)
        if path in seen:
            raise ValueError('WORKSPACE_LINK_DUPLICATE')
        seen.add(path)
        destination = root.joinpath(*relative(path).parts)
        for parent in destination.parents:
            if parent == root:
                break
            if parent.is_symlink():
                raise ValueError('WORKSPACE_LINK_PARENT_IS_LINK')
        if destination.is_symlink():
            if os.readlink(destination).replace('\\', '/') != target.replace('\\', '/'):
                raise ValueError('WORKSPACE_LINK_ALREADY_CHANGED')
            continue
        if destination.exists():
            raise ValueError('WORKSPACE_LINK_DESTINATION_EXISTS')
        destination.parent.mkdir(parents=True, exist_ok=True)
        is_directory = row.get('target_is_directory')
        if is_directory is None:
            resolved, visited = target_path(path, target), {path}
            while resolved in targets and resolved not in visited:
                visited.add(resolved)
                resolved = target_path(resolved, targets[resolved])
            is_directory = root.joinpath(*PurePosixPath(resolved).parts).is_dir()
        native_target = target.replace('/', '\\') if os.name == 'nt' else target
        os.symlink(native_target, destination, target_is_directory=bool(is_directory))
    observed = [row for row in entries(root) if row['kind'] == 'symlink']
    expected = [link_entry(row['path'], row['target'].replace('\\', '/')) for row in links]
    if observed != sorted(expected, key=lambda row: row['path']):
        raise ValueError('WORKSPACE_LINK_INSTALLATION_MISMATCH')
    return observed


def snapshot(root, destination, receipt, identity):
    root, destination, receipt = Path(root), Path(destination), Path(receipt)
    plain_windows_ancestors(destination)
    plain_windows_ancestors(receipt)
    if destination.resolve().is_relative_to(root.resolve()) or root.resolve().is_relative_to(destination.resolve()):
        raise ValueError('WORKSPACE_SNAPSHOT_ROOT_OVERLAP')
    before = entries(root)
    if receipt.exists():
        previous = json.loads(receipt.read_text(encoding='utf-8'))
        if (previous.get('identity') != identity or previous.get('entries') != before
                or entries(destination) != [row for row in before if row['kind'] != 'symlink']):
            raise ValueError('WORKSPACE_SNAPSHOT_RESUME_DRIFT')
        return previous
    if destination.exists():
        shutil.rmtree(destination)  # Only this owned, unpublished partial snapshot.
    destination.mkdir(parents=True)
    for row in before:
        source = root.joinpath(*relative(row['path']).parts)
        output = destination.joinpath(*relative(row['path']).parts)
        if row['kind'] == 'directory':
            output.mkdir(parents=True, exist_ok=True)
        elif row['kind'] == 'file':
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, output, follow_symlinks=False)
    if before != entries(root) or entries(destination) != [row for row in before if row['kind'] != 'symlink']:
        raise ValueError('WORKSPACE_CHANGED_DURING_SNAPSHOT')
    native = []
    for row in before:
        if row['kind'] == 'symlink':
            path = root.joinpath(*relative(row['path']).parts)
            info = path.lstat()
            native.append({'path': row['path'], 'target': os.readlink(path), 'mode': info.st_mode,
                           'reparse_tag': getattr(info, 'st_reparse_tag', None)})
    result = {'schema': SCHEMA, 'identity': identity, 'source': str(root), 'snapshot': str(destination),
              'entries': before, 'native_links': native}
    receipt.parent.mkdir(parents=True, exist_ok=True)
    temporary = receipt.with_suffix('.tmp')
    temporary.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True), encoding='utf-8')
    temporary.replace(receipt)
    return result


def archive_tree(root, output, *, prefix=''):
    """Write link payloads, never the bytes of their targets, to a portable ZIP."""
    root = Path(root)
    rows = entries(root)
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED, strict_timestamps=False) as archive:
        if prefix:
            relative(prefix)
            archive.write(root, prefix)
        for row in rows:
            name = (prefix + '/' if prefix else '') + row['path']
            if row['kind'] == 'symlink':
                info = zipfile.ZipInfo(name)
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(info, row['target'].encode('utf-8'))
            else:
                archive.write(root.joinpath(*relative(row['path']).parts), name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['install', 'snapshot'])
    parser.add_argument('--root', required=True)
    parser.add_argument('--spec', required=True)
    parser.add_argument('--destination')
    parser.add_argument('--receipt', required=True)
    args = parser.parse_args()
    spec = json.loads(Path(args.spec).read_text(encoding='utf-8'))
    if args.action == 'install':
        result = {'schema': SCHEMA, 'identity': spec['identity'], 'links': install(args.root, spec['links'])}
        Path(args.receipt).write_text(json.dumps(result, ensure_ascii=False, sort_keys=True), encoding='utf-8')
    else:
        snapshot(args.root, args.destination, args.receipt, spec['identity'])


if __name__ == '__main__':
    main()
