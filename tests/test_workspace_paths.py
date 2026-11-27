from pathlib import Path
import base64
import importlib.util
import json
import runpy
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from src.wildclawbench_workspace import (rewrite_root, relative_workspace_path, environment_note,
                                         PROFILE, WINDOWS_ROOT, WINDOWS_ALIAS)
from src.wildclawbench_workspace.rules import canonical_field, rule_path_aliases, PARSERS
from src.e2e.workspace_environment import prepare
from src.e2e.common import E2EError

REPO = Path(__file__).resolve().parents[1]
SKILLS = REPO / 'tools/report/skills'


def load(path):
    spec = importlib.util.spec_from_file_location('_test_path_module', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class WorkspacePathsTests(unittest.TestCase):
    def test_chinese_boundaries_and_literal_windows_replacement(self):
        for suffix in ('的材料', '绝对路径', '为根', '/input/a.csv', ' 下'):
            value, mapping = rewrite_root('/tmp_workspace' + suffix, r'C:\tmp\1')
            self.assertEqual(value, r'C:\tmp\1' + suffix)
            self.assertEqual(mapping, {'/tmp_workspace': r'C:\tmp\1'})
        for value in ('/tmp_workspace_backup/a', '/tmp_workspace-backup/a', '/tmp_workspace_eval/a',
                      '/parent/tmp_workspace/a', 'https://host/tmp_workspace/a'):
            self.assertEqual(rewrite_root(value, '.')[0], value)

    def test_linux_windows_members_and_traversal(self):
        for prefix in ('/tmp_workspace', WINDOWS_ROOT, WINDOWS_ALIAS, 'c:/programdata/wgui/workspace/project'):
            self.assertEqual(relative_workspace_path(prefix + '/results/a.json'), 'results/a.json')
        self.assertEqual(relative_workspace_path('./results/a.json'), 'results/a.json')
        for value in (r'C:\other\results\a.json', r'\\server\share\a.json', '/etc/passwd',
                      '/tmp_workspace/../outside', r'C:\tmp_workspace\..\outside', 'C:results/a',
                      '/tmp_workspace_backup/results/a', 'results/../../outside'):
            self.assertIsNone(relative_workspace_path(value), value)

    def test_canonical_field_is_narrow_and_preserves_linux_bytes(self):
        self.assertEqual(canonical_field(r'C:\tmp_workspace\input\a.csv'), '/tmp_workspace/input/a.csv')
        self.assertEqual(canonical_field('/tmp_workspace/input/a.csv'), '/tmp_workspace/input/a.csv')
        for value in (r'C:\other\a', r'C:\tmp_workspace_backup\a', 'source:R01', r'input\a.csv'):
            self.assertEqual(canonical_field(value), value)
        self.assertEqual(canonical_field('C:/tmp_workspace/a#R1;C:/tmp_workspace/b#R2'),
                         '/tmp_workspace/a#R1;/tmp_workspace/b#R2')

    def test_all_preparers_share_complete_root_matching(self):
        general = load(SKILLS / 'general-e2e/prepare-general-e2e-workspaces/scripts/prepare_general_e2e_workspaces.py')
        web = load(SKILLS / 'web-e2e/prepare-web-e2e-workspaces/scripts/prepare_web_e2e_workspaces.py')
        value = '/tmp_workspace的材料 /tmp_workspace/input /tmp_workspace-backup/a'
        self.assertEqual(general.map_prompt_workspace(value)[0], '.的材料 ./input /tmp_workspace-backup/a')
        self.assertEqual(web.rewrite_execution_text(value)[0], './workspace的材料 ./workspace/input /tmp_workspace-backup/a')
        self.assertEqual(web.rewrite_scoring_text('/tmp_workspace_eval的材料 /tmp_workspace_eval/input /tmp_workspace/input'),
                         './private-scoring/fixtures的材料 ./private-scoring/fixtures/input ./workspace/input')

    def test_environment_note_preserves_task_command_examples(self):
        self.assertIn('Linux', environment_note('linux'))
        self.assertIn('PowerShell', environment_note('windows'))
        self.assertIn('python3', environment_note('windows'))

    def test_frozen_h040_parser_normalizes_native_paths_and_restores_hook(self):
        source = REPO / 'workspace/general/challenge/04_File_Operations/04_File_Operations_task_006_visual_file_mapping/gt/check_visual_mapping.py'
        original = runpy.run_path
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / 'gt').mkdir()
            target = root / 'gt' / source.name
            shutil.copyfile(source, target)
            with rule_path_aliases(root) as receipts:
                module = runpy.run_path(str(target))
                relative = module['relative']
                self.assertEqual(relative(WINDOWS_ROOT + r'\source_tree\a.txt', root, 'source_tree'), 'source_tree/a.txt')
                self.assertEqual(relative(WINDOWS_ALIAS + r'\results\selected_files\a.txt', root, 'target'), 'selected_files/a.txt')
                self.assertIsNone(relative(r'C:\other\source_tree\a.txt', root, 'source_tree'))
                self.assertIsNone(relative(WINDOWS_ROOT + r'\..\source_tree\a.txt', root, 'source_tree'))
                self.assertEqual(sum(r['adapted_calls'] for r in receipts.values()), 3)
            self.assertIs(runpy.run_path, original)
            target.write_text(target.read_text() + '\n# drift\n')
            with rule_path_aliases(root) as receipts:
                self.assertIsNone(runpy.run_path(str(target))['relative'](WINDOWS_ROOT + '/source_tree/a.txt', root, 'source_tree'))
                self.assertEqual(receipts, {})

    def test_no_hook_outside_selected_private_directory_even_if_hash_matches(self):
        source = REPO / 'workspace/general/challenge/04_File_Operations/04_File_Operations_task_006_visual_file_mapping/gt/check_visual_mapping.py'
        with tempfile.TemporaryDirectory() as temp, rule_path_aliases(Path(temp)) as receipts:
            runpy.run_path(str(source))
            self.assertEqual(receipts, {})

    def test_every_reviewed_frozen_parser_keeps_linux_windows_equivalence(self):
        cases = [
            ('04_File_Operations', '006_visual_file_mapping', 'check_visual_mapping.py', 'relative', '/source_tree/a.txt', ('source_tree',)),
            ('04_File_Operations', '001_cleanup_plan', 'native_io.py', 'npath', '/incoming/a.txt', ()),
            ('04_File_Operations', '002_versioned_archive', 'native_io.py', 'path_value', '/results/archive/a.txt', ('archive',)),
            ('04_File_Operations', '003_nested_archives', 'native_io.py', 'path_value', '/results/a.txt', ('target',)),
            ('04_File_Operations', '004_resumable_inventory', 'native_io.py', 'path_value', '/results/archive/a.txt', ('archive',)),
            ('04_File_Operations', '005_split_bundle_restore', 'native_io.py', 'relative', '/results/restored/a.txt', ('restored',)),
            ('02_Data_Analysis', '004_financial_reconcile', 'financial_io.py', 'source_path', '/statements/a.csv', ()),
            ('01_Office_Documents', '008_bilingual_revision', 'structured_io.py', 'tokens', '/source.docx#R1', ()),
            ('01_Office_Documents', '004_bid_compliance', 'structured_io.py', 'parse_refs', '/requirements.docx#R001', ('requirement_refs', {'empty_markers': ['-']})),
            ('01_Office_Documents', '012_visual_redlines', 'structured_io.py', 'image_name', '/signed_pages/scan_01.png', ()),
            ('01_Office_Documents', '011_linked_report_update', 'common_io.py', 'output_path', '/results/a.docx', ()),
        ]
        self.assertEqual(len(cases), len(PARSERS))
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / 'gt').mkdir()
            for category, stem, file, name, suffix, args in cases:
                with self.subTest(parser=stem):
                    source = REPO / 'workspace/general/challenge' / category / (category + '_task_' + stem) / 'gt' / file
                    target = root / 'gt' / file
                    for sibling in source.parent.glob('*.py'):
                        shutil.copyfile(sibling, root / 'gt' / sibling.name)
                    parameters = (root, *args) if file == 'check_visual_mapping.py' else args
                    baseline = runpy.run_path(str(source))[name]('/tmp_workspace' + suffix, *parameters)
                    self.assertTrue(baseline)
                    with rule_path_aliases(root) as receipts:
                        parser = runpy.run_path(str(target))[name]
                        for prefix in (WINDOWS_ROOT, WINDOWS_ALIAS, '/tmp_workspace'):
                            self.assertEqual(parser(prefix + suffix, *parameters), baseline)
                    self.assertTrue(receipts)

    def test_common_windows_preparation_requires_verified_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            driver = SimpleNamespace(client=Mock(), staging=Path(temp))
            proof = dict(profile=PROFILE, platform='windows', workspace=WINDOWS_ROOT, alias=WINDOWS_ALIAS,
                         alias_verified=True, python=dict(executable='C:/python.exe', version=[3,12,10]))
            driver.client.windows_execute.return_value = {'output': base64.b64encode(json.dumps(proof).encode()).decode()}
            self.assertEqual(prepare(driver, 'sid', lambda s:s), proof)
            self.assertTrue((driver.staging / 'metadata/workspace-environment.json').is_file())
            driver.client.windows_execute.return_value = {'output': '{"error":"unreachable"}'}
            with self.assertRaisesRegex(E2EError, 'WINDOWS_WORKSPACE_ENVIRONMENT_UNVERIFIED'):
                prepare(driver, 'sid', lambda s:s)

    def test_isolated_scoring_worker_binds_path_profile_and_reports_adapter(self):
        source = REPO / 'workspace/general/challenge/04_File_Operations/04_File_Operations_task_006_visual_file_mapping/gt/check_visual_mapping.py'
        worker = SKILLS / 'general-e2e/score-general-e2e/scripts/rule_worker.py'
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / 'workspace/gt').mkdir(parents=True)
            shutil.copyfile(source, root / 'workspace/gt' / source.name)
            code = '''def grade(transcript, workspace_path):
    import runpy
    from pathlib import Path
    root = Path(workspace_path)
    parser = runpy.run_path(str(root/'gt/check_visual_mapping.py'))['relative']
    return {'overall_score': float(parser('C:/tmp_workspace/source_tree/a.txt', root, 'source_tree') == 'source_tree/a.txt')}
'''
            request = dict(schema_version='wildclawbench.general-e2e-rule-worker-request/v1',
                           automated_checks=code, workspace_path=str(root / 'workspace'), transcript=[],
                           workspace_path_profile='wildclawbench.frozen-rule-path-aliases/v1')
            request_path=root/'request.json'; result_path=root/'result.json'
            request_path.write_text(json.dumps(request))
            subprocess.run([sys.executable, '-I', str(worker), '--request', str(request_path), '--result', str(result_path)],
                           check=True, capture_output=True, text=True)
            result=json.loads(result_path.read_text())
            self.assertEqual(result['result']['overall_score'], 1.)
            self.assertEqual(result['workspace_path_aliases']['parsers'][0]['adapted_calls'], 1)


if __name__ == '__main__':
    unittest.main()
