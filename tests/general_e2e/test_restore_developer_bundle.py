"""Synthetic byte-preserving recovery of a host-modified developer directory."""
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
import zipfile

SCRIPTS = Path(__file__).resolve().parents[2] / 'tools/report/skills/general-e2e/run-general-e2e/scripts'
sys.path.insert(0, str(SCRIPTS))
import restore_developer_bundle as RESTORE


def digest(data):
    return hashlib.sha256(data).hexdigest()


class RestoreDeveloperBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.addCleanup(self.dispose_own_fixture)

    def dispose_own_fixture(self):
        for base, dirs, files in os.walk(self.root, followlinks=False):
            Path(base).chmod(0o755)
            dirs[:] = [n for n in dirs if not (Path(base) / n).is_symlink()]
            for name in files:
                path = Path(base) / name
                if sys.platform == 'darwin' and not path.is_symlink():
                    os.chflags(path, path.stat().st_flags & ~stat.UF_IMMUTABLE)

    def archive(self, filename='bundle.zip', *, change=None):
        files = {'TASK_INDEX.json': b'{"tasks":[]}', 'SELECTION.json': b'{"selected_runs":0}',
                 'VERIFY.py': b'raise RuntimeError("archived verifier must not execute")\n',
                 'nested/book.xlsx': b'synthetic-frozen-workbook', 'nested/payload.bin': b'opaque-bytes'}
        entries = [{'path': 'nested', 'kind': 'directory', 'mode': '0555', 'size': 0}]
        entries += [{'path': p, 'kind': 'file', 'mode': '0640', 'size': len(data), 'sha256': digest(data)}
                    for p, data in files.items()]
        link = b'nested/book.xlsx'
        entries.append({'path': 'alias', 'kind': 'symlink', 'mode': '0777', 'size': len(link),
                        'sha256': digest(link), 'link_target': link.decode()})
        files['alias'] = link
        if change:
            change(entries, files)
        path = self.root / filename
        with zipfile.ZipFile(path, 'w') as archive:
            for row in entries:
                info = zipfile.ZipInfo('general-e2e-synthetic/' + row['path'] + ('/' if row['kind'] == 'directory' else ''))
                info.create_system = 3
                info.external_attr = ({'directory': stat.S_IFDIR, 'file': stat.S_IFREG, 'symlink': stat.S_IFLNK}[row['kind']] | int(row['mode'], 8)) << 16
                archive.writestr(info, b'' if row['kind'] == 'directory' else files[row['path']])
            info = zipfile.ZipInfo('general-e2e-synthetic/INTEGRITY.json')
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, json.dumps({'schema_version': 'general-e2e-developer-bundle/v1', 'entries': entries}))
        return path, RESTORE.sha256_file(path)

    def test_restores_bytes_readonly_directory_and_link_without_executing_archived_code(self):
        archive, before = self.archive()
        result = RESTORE.restore(archive, before, self.root / 'output')
        directory = Path(result['bundle_directory'])
        self.assertEqual(result['directory_verification']['status'], 'PASS')
        self.assertEqual(result['zip_verification']['status'], 'PASS')
        self.assertFalse(result['archived_verifier_executed'])
        self.assertEqual((directory / 'nested/book.xlsx').read_bytes(), b'synthetic-frozen-workbook')
        self.assertEqual(stat.S_IMODE((directory / 'nested').stat().st_mode), 0o555)
        self.assertEqual(stat.S_IMODE((directory / 'nested/book.xlsx').stat().st_mode), 0o640)
        self.assertEqual(os.readlink(directory / 'alias'), 'nested/book.xlsx')
        self.assertEqual(stat.S_IMODE((directory / 'alias').lstat().st_mode), 0o777)
        self.assertEqual(RESTORE.sha256_file(archive), before)
        if sys.platform == 'darwin':
            for path in directory.joinpath('nested').iterdir():
                self.assertTrue(path.stat().st_flags & stat.UF_IMMUTABLE)
                with self.assertRaises(PermissionError):
                    path.write_bytes(b'host rewrite')

    def test_existing_host_variant_requires_explicit_preservation_and_keeps_old_integrity(self):
        archive, before = self.archive()
        output = self.root / 'output'
        first = RESTORE.restore(archive, before, output)
        directory = Path(first['bundle_directory'])
        workbook = directory / 'nested/book.xlsx'
        manifest_before = (directory / 'INTEGRITY.json').read_bytes()
        if sys.platform == 'darwin':
            os.chflags(workbook, workbook.stat().st_flags & ~stat.UF_IMMUTABLE)
        workbook.write_bytes(b'synthetic-host-variant')
        with self.assertRaisesRegex(ValueError, 'OUTPUT_EXISTS'):
            RESTORE.restore(archive, before, output)
        result = RESTORE.restore(archive, before, output, preserve_existing=True)
        old = Path(result['preserved_host_variant'])
        self.assertEqual((old / 'nested/book.xlsx').read_bytes(), b'synthetic-host-variant')
        self.assertEqual((old / 'INTEGRITY.json').read_bytes(), manifest_before)
        self.assertEqual((directory / 'INTEGRITY.json').read_bytes(), manifest_before)
        self.assertEqual(workbook.read_bytes(), b'synthetic-frozen-workbook')
        self.assertEqual([r['path'] for r in result['host_differences']], ['nested/book.xlsx'])
        self.assertEqual(RESTORE.sha256_file(archive), before)

    def test_rejects_wrong_archive_hash_before_creating_output(self):
        archive, _ = self.archive()
        output = self.root / 'rejected'
        with self.assertRaisesRegex(ValueError, 'ARCHIVE_SHA'):
            RESTORE.restore(archive, '0' * 64, output)
        self.assertFalse(output.exists())

    def test_unrelated_existing_directory_is_never_renamed(self):
        archive, before = self.archive()
        output = self.root / 'output'
        existing = output / 'general-e2e-synthetic'
        existing.mkdir(parents=True)
        (existing / 'INTEGRITY.json').write_text('{}')
        (existing / 'keep.txt').write_bytes(b'untouched')
        with self.assertRaisesRegex(ValueError, 'IDENTITY_MISMATCH'):
            RESTORE.restore(archive, before, output, preserve_existing=True)
        self.assertEqual((existing / 'keep.txt').read_bytes(), b'untouched')
        self.assertEqual(list(output.glob('*.host-variant-*')), [])

    def test_rejects_bad_hash_escaping_link_and_traversal_before_writing(self):
        def bad_hash(entries, files):
            files['nested/book.xlsx'] += b'changed'
        def bad_link(entries, files):
            row = entries[-1]
            target = b'../../outside'
            row.update(size=len(target), sha256=digest(target), link_target=target.decode())
            files['alias'] = target
        def traversal(entries, files):
            row = entries[1]
            files['../outside'] = files.pop(row['path'])
            row['path'] = '../outside'
        for index, change in enumerate([bad_hash, bad_link, traversal]):
            with self.subTest(index=index):
                archive, before = self.archive(f'bad-{index}.zip', change=change)
                output = self.root / f'rejected-{index}'
                with self.assertRaises((ValueError, AssertionError)):
                    RESTORE.restore(archive, before, output)
                self.assertFalse(output.exists())

    def test_rejects_duplicate_members_and_zip_mode_drift_before_writing(self):
        archive, _ = self.archive()
        duplicate = self.root / 'duplicate.zip'
        with zipfile.ZipFile(archive) as source, zipfile.ZipFile(duplicate, 'w') as target:
            for info in source.infolist():
                target.writestr(info, source.read(info))
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', UserWarning)
                target.writestr('general-e2e-synthetic/alias', b'other')
        output = self.root / 'rejected'
        with self.assertRaisesRegex(ValueError, 'DUPLICATE'):
            RESTORE.restore(duplicate, RESTORE.sha256_file(duplicate), output)
        self.assertFalse(output.exists())
        drift = self.root / 'mode-drift.zip'
        with zipfile.ZipFile(archive) as source, zipfile.ZipFile(drift, 'w') as target:
            for info in source.infolist():
                if info.filename.endswith('/alias'):
                    info.external_attr = (stat.S_IFREG | 0o777) << 16
                target.writestr(info, source.read(info))
        with self.assertRaisesRegex(ValueError, 'MEMBER_MODE'):
            RESTORE.restore(drift, RESTORE.sha256_file(drift), output)
        self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
