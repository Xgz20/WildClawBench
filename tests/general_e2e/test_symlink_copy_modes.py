import hashlib
import importlib.util
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
BASE = REPO / 'tools/report/skills/general-e2e'


def module(name, relative):
    path = BASE / relative
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


SCORE = module('score_symlink_transport', 'score-general-e2e/scripts/score_general_e2e.py')
RUN = module('run_symlink_transport', 'run-general-e2e/scripts/run_general_e2e.py')
DEV = module('developer_symlink_transport', 'run-general-e2e/scripts/build_developer_bundle.py')
sys.path.insert(0, str(BASE / 'run-general-e2e/scripts'))
SELECTED = module('selected_developer_symlink_transport', 'run-general-e2e/scripts/selected_developer_bundle.py')


class SymlinkTransportTests(unittest.TestCase):
    def fixture(self, root):
        source = root / 'source'
        (source / 'nested').mkdir(parents=True)
        sentinel = source / 'sentinel.txt'
        sentinel.write_bytes(b'synthetic-sentinel')
        sentinel.chmod(0o640)
        link = source / 'nested/link'
        link.symlink_to('../sentinel.txt')
        if hasattr(os, 'lchmod'):
            os.lchmod(link, 0o777)
        self.assertEqual(stat.S_IMODE(link.lstat().st_mode), 0o777)
        return source, sentinel, link

    def assert_target_unchanged(self, sentinel):
        self.assertEqual(sentinel.read_bytes(), b'synthetic-sentinel')
        self.assertEqual(stat.S_IMODE(sentinel.lstat().st_mode), 0o640)

    def test_score_inventory_copy_preserves_link_mode(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            source, sentinel, link = self.fixture(root)
            entries, digest = SCORE._inventory_tree(source)
            SCORE._copy_inventory(source, root / 'copy', entries)
            self.assertEqual(SCORE._inventory_tree(root / 'copy'), (entries, digest))
            self.assertEqual(stat.S_IMODE((root / 'copy/nested/link').lstat().st_mode), 0o777)
            self.assert_target_unchanged(sentinel)
            self.assertEqual(os.readlink(link), '../sentinel.txt')

    def test_private_link_transport_preserves_declared_mode(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value) / 'private'
            SCORE._write_gt(root, [({'path':'sentinel.txt','kind':'file','mode':'0640'}, b'synthetic-sentinel'),
                                   ({'path':'link','kind':'symlink','mode':'0777'}, b'sentinel.txt')])
            self.assertEqual(stat.S_IMODE((root / 'link').lstat().st_mode), 0o777)
            self.assert_target_unchanged(root / 'sentinel.txt')

    def test_return_extraction_preserves_zip_link_mode(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value).resolve() / 'imported'
            rows = [{'path':'unit','kind':'directory','mode':'0755'},
                    {'path':'unit/sentinel.txt','kind':'file','mode':'0640'},
                    {'path':'unit/link','kind':'symlink','mode':'0777','link_target':'sentinel.txt'}]
            members = {r['path']:(RUN.zip_info(r['path'],r['kind'],int(r['mode'],8)),
                        b'synthetic-sentinel' if r['kind']=='file' else b'sentinel.txt' if r['kind']=='symlink' else b'') for r in rows}
            RUN.extract_verified_return({'members':members,'manifest':{'entries':rows},'manifest_bytes':b'{}','receipt_bytes':b'{}'},root)
            self.assertEqual(stat.S_IMODE((root / 'unit/link').lstat().st_mode), 0o777)
            self.assert_target_unchanged(root / 'unit/sentinel.txt')

    def test_private_read_only_directory_is_restored_after_its_children(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value) / 'private'
            try:
                SCORE._write_gt(root, [({'path':'nested','kind':'directory','mode':'0555'}, b''),
                                       ({'path':'nested/sentinel.txt','kind':'file','mode':'0640'}, b'synthetic-sentinel')])
                self.assertEqual(stat.S_IMODE((root / 'nested').lstat().st_mode), 0o555)
                self.assert_target_unchanged(root / 'nested/sentinel.txt')
            finally:
                if (root / 'nested').exists():
                    (root / 'nested').chmod(0o755)

    def test_developer_copy_preserves_selected_link_mode(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            source, sentinel, link = self.fixture(root)
            data = os.readlink(link).encode()
            DEV.copy_verified(source, root / 'exported', {'path':'nested/link','kind':'symlink','mode':'0777',
                               'link_target':'../sentinel.txt','size':len(data),'sha256':hashlib.sha256(data).hexdigest()})
            self.assertEqual(stat.S_IMODE((root / 'exported/nested/link').lstat().st_mode), 0o777)
            self.assert_target_unchanged(sentinel)

    def test_selected_copy_preserves_link_mode_without_target_changes(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            source, sentinel, link = self.fixture(root)
            target = root / 'new-link'
            SELECTED.copy_selected_symlink(link, target)
            self.assertEqual(stat.S_IMODE(target.lstat().st_mode), 0o777)
            self.assertEqual(os.readlink(target), '../sentinel.txt')
            self.assert_target_unchanged(sentinel)

    def test_developer_restores_read_only_directory_after_children(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            source = root / 'source'
            (source / 'nested').mkdir(parents=True)
            file = source / 'nested/sentinel.txt'
            file.write_bytes(b'synthetic-sentinel')
            file.chmod(0o640)
            (source / 'nested').chmod(0o555)
            try:
                rows = [{'path':'nested','kind':'directory','mode':'0555','size':0,'sha256':hashlib.sha256(b'').hexdigest()},
                        {'path':'nested/sentinel.txt','kind':'file','mode':'0640','size':18,'sha256':hashlib.sha256(b'synthetic-sentinel').hexdigest()}]
                for row in rows:
                    DEV.copy_verified(source, root / 'copy', row)
                DEV.restore_directory_modes(root / 'copy', rows)
                self.assertEqual(stat.S_IMODE((root / 'copy/nested').lstat().st_mode), 0o555)
                self.assertEqual(stat.S_IMODE((source / 'nested').lstat().st_mode), 0o555)
                self.assert_target_unchanged(root / 'copy/nested/sentinel.txt')
            finally:
                (source / 'nested').chmod(0o755)
                if (root / 'copy/nested').exists():
                    (root / 'copy/nested').chmod(0o755)


if __name__ == '__main__':
    unittest.main()
