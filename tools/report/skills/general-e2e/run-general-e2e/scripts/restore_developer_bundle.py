#!/usr/bin/env python3
"""Restore a developer directory from its SHA-bound ZIP, preserving host variants."""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import uuid
import zipfile

import build_developer_bundle as bundle
from developer_bundle_files import sha256_file, write_protected_file


def require(condition, message):
    if not condition:
        raise ValueError(message)


def trusted_verify(target):
    # Never execute VERIFY.py from an input archive or existing host directory.
    namespace = {'__name__': '_trusted_developer_bundle_verify'}
    exec(compile(bundle.VERIFY_SCRIPT, '<shipped developer verifier>', 'exec'), namespace)
    return namespace['check'](target)


def inventory_archive(archive):
    names = archive.namelist()
    require(len(names) == len(set(names)), 'DEVELOPER_ZIP_DUPLICATE')
    manifests = [n for n in names if n.count('/') == 1 and n.endswith('/INTEGRITY.json')]
    require(len(manifests) == 1, 'DEVELOPER_MANIFEST_COUNT')
    root = manifests[0].split('/')[0]
    require(len(bundle.safe_rel(root).parts) == 1 and root != '.', 'DEVELOPER_ZIP_ROOT')
    prefix = root + '/'
    raw_manifest = archive.read(manifests[0])
    manifest = json.loads(raw_manifest)
    require(manifest.get('schema_version') in (1, 'general-e2e-developer-bundle/v1'),
            'DEVELOPER_MANIFEST_SCHEMA')
    entries = manifest['entries']
    by_path = {e['path']: e for e in entries}
    require(len(by_path) == len(entries) and 'INTEGRITY.json' not in by_path,
            'DEVELOPER_MANIFEST_DUPLICATE')
    expected = {prefix + e['path'] + ('/' if e['kind'] == 'directory' else '') for e in entries}
    require(set(names) == expected | {prefix + 'INTEGRITY.json'}, 'DEVELOPER_ZIP_SCOPE')
    for row in entries:
        relative = bundle.safe_rel(row['path'])
        require(relative.parts and relative.as_posix() != '.', 'DEVELOPER_PATH_INVALID')
        require(row['kind'] in ('file', 'directory', 'symlink'), 'DEVELOPER_MEMBER_TYPE')
        for parent in relative.parents:
            if parent.as_posix() != '.':
                require(by_path.get(parent.as_posix(), {}).get('kind') == 'directory',
                        'DEVELOPER_MEMBER_PARENT')
        info = archive.getinfo(prefix + row['path'] + ('/' if row['kind'] == 'directory' else ''))
        mode = info.external_attr >> 16
        expected_type = {'file': stat.S_IFREG, 'directory': stat.S_IFDIR, 'symlink': stat.S_IFLNK}[row['kind']]
        require(stat.S_IFMT(mode) == expected_type and stat.S_IMODE(mode) == int(row['mode'], 8),
                'DEVELOPER_MEMBER_MODE: ' + row['path'])
        payload = archive.read(info)
        require(len(payload) == row['size'], 'DEVELOPER_MEMBER_SIZE: ' + row['path'])
        if row['kind'] != 'directory' or 'sha256' in row:
            require(hashlib.sha256(payload).hexdigest() == row['sha256'],
                    'DEVELOPER_MEMBER_SHA: ' + row['path'])
        if row['kind'] == 'directory':
            require(not payload, 'DEVELOPER_DIRECTORY_PAYLOAD')
        elif row['kind'] == 'symlink':
            target = payload.decode('utf-8', errors='surrogateescape')
            require(target == row['link_target'], 'DEVELOPER_LINK_TARGET')
            # This checks the package boundary, without following the link.
            import run_general_e2e
            run_general_e2e.safe_symlink_target(relative, target)
    control = archive.getinfo(prefix + 'INTEGRITY.json')
    require(stat.S_IFMT(control.external_attr >> 16) == stat.S_IFREG, 'DEVELOPER_MANIFEST_TYPE')
    return root, prefix, entries, raw_manifest, stat.S_IMODE(control.external_attr >> 16)


def host_differences(directory, entries):
    expected = {e['path']: e for e in entries}
    differences = []
    seen = set()
    for base, dirs, files in os.walk(directory, followlinks=False):
        for name in sorted(dirs + files):
            path = Path(base) / name
            relative = path.relative_to(directory).as_posix()
            if relative == 'INTEGRITY.json':
                continue
            seen.add(relative)
            row = expected.get(relative)
            mode = path.lstat().st_mode
            kind = 'symlink' if stat.S_ISLNK(mode) else 'directory' if stat.S_ISDIR(mode) else 'file' if stat.S_ISREG(mode) else 'other'
            actual = {'kind': kind, 'mode': f'{stat.S_IMODE(mode):04o}'}
            if kind == 'file':
                actual.update(size=path.stat().st_size, sha256=sha256_file(path))
            elif kind == 'symlink':
                data = os.readlink(path).encode('utf-8', errors='surrogateescape')
                actual.update(size=len(data), sha256=hashlib.sha256(data).hexdigest(), link_target=os.readlink(path))
            if row is None or any(actual[k] != row.get(k) for k in actual):
                differences.append({'path': relative, 'expected': row, 'observed': actual})
        dirs[:] = [n for n in dirs if not (Path(base) / n).is_symlink()]
    differences += [{'path': p, 'expected': expected[p], 'observed': None} for p in sorted(expected.keys() - seen)]
    return differences


def restore(archive_path, expected_sha256, output_root, *, preserve_existing=False):
    archive_path, output_root = Path(archive_path), Path(output_root)
    require(not archive_path.is_symlink() and archive_path.is_file(), 'DEVELOPER_ARCHIVE_NOT_REGULAR')
    require(re.fullmatch('[0-9a-fA-F]{64}', expected_sha256) is not None, 'DEVELOPER_ARCHIVE_SHA_REQUIRED')
    expected_sha256 = expected_sha256.lower()
    require(sha256_file(archive_path) == expected_sha256, 'DEVELOPER_ARCHIVE_SHA')
    require(not output_root.is_symlink(), 'DEVELOPER_OUTPUT_SYMLINK')
    with zipfile.ZipFile(archive_path) as archive:
        root, prefix, entries, raw_manifest, manifest_mode = inventory_archive(archive)
        # ZIP verification cannot read outside the archive, even if an index is malformed.
        zip_verification = trusted_verify(archive_path)
        destination = output_root / root
        require(not destination.is_symlink(), 'DEVELOPER_OUTPUT_SYMLINK')
        existing = os.path.lexists(destination)
        differences = []
        if existing:
            require(preserve_existing, 'DEVELOPER_OUTPUT_EXISTS')
            require(destination.is_dir(), 'DEVELOPER_OUTPUT_NOT_DIRECTORY')
            manifest_path = destination / 'INTEGRITY.json'
            require(not manifest_path.is_symlink() and manifest_path.is_file() and
                    manifest_path.read_bytes() == raw_manifest, 'DEVELOPER_EXISTING_IDENTITY_MISMATCH')
            differences = host_differences(destination, entries)
        output_root.mkdir(parents=True, exist_ok=True)
        staging = output_root / ('.' + root + '.pending-' + uuid.uuid4().hex)
        staging.mkdir()
        # Keep a failed staging tree for diagnosis; never clean unknown or source directories.
        for row in entries:
            target = staging / row['path']
            target.parent.mkdir(parents=True, exist_ok=True)
            if row['kind'] == 'directory':
                target.mkdir(exist_ok=True)
            elif row['kind'] == 'file':
                write_protected_file(target, archive.read(prefix + row['path']), int(row['mode'], 8))
        write_protected_file(staging / 'INTEGRITY.json', raw_manifest, manifest_mode)
        for row in entries:
            if row['kind'] == 'symlink':
                target = staging / row['path']
                target.symlink_to(row['link_target'])
                bundle._preserve_symlink_mode(target, int(row['mode'], 8))
        bundle.restore_directory_modes(staging, entries)
        directory_verification = trusted_verify(staging)
        require(sha256_file(archive_path) == expected_sha256, 'DEVELOPER_ARCHIVE_CHANGED')
    preserved = None
    if existing:
        preserved = output_root / (root + '.host-variant-' + uuid.uuid4().hex)
        destination.rename(preserved)
    try:
        staging.rename(destination)
    except OSError:
        if preserved is not None and not os.path.lexists(destination):
            preserved.rename(destination)
        raise
    result = {'status': 'PASS', 'created_at': datetime.now().astimezone().isoformat(),
              'archive': str(archive_path.resolve()), 'archive_sha256': expected_sha256,
              'bundle_directory': str(destination.resolve()),
              'preserved_host_variant': str(preserved.resolve()) if preserved else None,
              'host_differences': differences, 'directory_verification': directory_verification,
              'zip_verification': zip_verification,
              'integrity_sha256': hashlib.sha256(raw_manifest).hexdigest(),
              'archive_and_original_receipts_unchanged': True,
              'archived_verifier_executed': False}
    receipt = output_root / (root + '.restoration-' + uuid.uuid4().hex + '.json')
    bundle.write_json(receipt, result)
    return {**result, 'receipt': str(receipt.resolve())}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', required=True, type=Path)
    parser.add_argument('--expected-archive-sha256', required=True)
    parser.add_argument('--output-root', required=True, type=Path)
    parser.add_argument('--preserve-existing', action='store_true',
                        help='Preserve an existing directory with identical INTEGRITY before restoring')
    args = parser.parse_args(argv)
    result = restore(args.archive, args.expected_archive_sha256, args.output_root,
                     preserve_existing=args.preserve_existing)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == '__main__':
    main()
