import contextlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import zipfile

from src.e2e import workspace_links as links
from src.e2e.artifacts import inventory, seal_execution, restore_execution, remove_temporary_tree, _members, extract_zip
from src.e2e.common import E2EError, read_json
from src.e2e.preparation import general_workspace_links
from eval_general_e2e.datasets.bundle import BundleMember

REPO = Path(__file__).resolve().parents[2]
TASK = '06_Safety_Alignment_task_007_bounded_cleanup'
FIXTURE = REPO / 'workspace/general/regression/06_Safety_Alignment' / TASK


@contextlib.contextmanager
def temporary():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        try:
            yield root
        finally:
            if root.exists():
                remove_temporary_tree(root)


def fixture(root):
    shutil.copytree(FIXTURE / 'exec', root, symlinks=True)
    shutil.copytree(FIXTURE / 'gt', root / 'gt')
    return root


def cleanup(root):
    expected = read_json(root / 'gt/expected.json' if (root / 'gt/expected.json').is_file() else FIXTURE / 'gt/expected.json')
    for name in expected['allowed_deleted']:
        (root / 'cleanup_area' / name).unlink()
    (root / 'results').mkdir()
    (root / 'results/cleanup_report.json').write_text(json.dumps({
        'deleted': expected['allowed_deleted'], 'skipped': ['protected', 'symlink'], 'reason': 'only allowlisted paths'}))


def grader():
    source = (REPO / 'tasks/general/regression/06_Safety_Alignment' / (TASK + '.md')).read_text()
    code = source.split('## Automated Checks', 1)[1].split('```python', 1)[1].split('```', 1)[0]
    namespace = {}
    exec(compile(code, '<original-bounded-cleanup-rule>', 'exec'), namespace)
    return namespace['grade']


class WorkspaceLinkTests(unittest.TestCase):
    def test_bounded_case_execution_export_import_and_scoring_handoff_keep_links(self):
        from src.e2e.preparation import prepare_batch
        from src.e2e.engine import run_batch
        from src.e2e.agentcube import AgentCubeConfig
        from src.e2e.packages import export_package, import_package
        from tests.e2e.test_scheduler import FakeDriver, Provider
        import subprocess, sys
        with temporary() as root:
            batch = prepare_batch(REPO, root, {'batch_id': 'bounded-link-handoff',
                'selection': {'scenario': 'general', 'dataset': 'general-custom60-v1', 'task_ids': [TASK]},
                'units': [{'harness': 'astronstudio', 'model': 'spark-x2.6', 'reasoning_effort': 'high'}]})
            provider = Provider()
            class Driver(FakeDriver):
                def execute(self):
                    result = super().execute()
                    workspace = self.staging / 'collect/workspace'
                    shutil.rmtree(workspace)
                    shutil.copytree(FIXTURE / 'exec', workspace, symlinks=True)
                    cleanup(workspace)
                    evidence = self.staging / 'collect/evidence';evidence.mkdir()
                    (evidence / 'diagnostics.json').write_text('{"product_version":"synthetic"}')
                    result['cleanup'].update(workspace=r'C:\ProgramData\WGUI\workspace\project', root_pid=None, disposition='already_exited', before=[])
                    return result
            def factory(**kwargs):
                task = kwargs['task']
                prompt = (batch / task['input_root'] / 'execution/PROMPT.md').read_text()
                return Driver(**{**kwargs, 'task': {**task, 'prompt': prompt}}, provider=provider)
            run_batch(batch, AgentCubeConfig(user_id='fixture', auth_token='fixture'), driver_factory=factory)
            archive = root / 'scoring-result.zip'
            export_package(batch, archive, purpose='scoring')
            imported = import_package(archive, None, root / 'recipient')
            context = imported['scoring_contexts'][0]
            unit = Path(context['context_root']) / 'unit'
            candidates = list(unit.glob('evidence/tasks/*/*/candidate/workspace/cleanup_area/cache/link_to_outside'))
            self.assertEqual(len(candidates), 1)
            self.assertTrue(candidates[0].is_symlink())
            import_package(archive, None, root / 'recipient')
            skill = Path(context['installed_skills'])
            process = subprocess.run([sys.executable, str(skill / 'orchestrate-general-e2e/scripts/orchestrate_general_e2e.py'),
                'init', '--unit-root', str(unit), '--scoring-package', str(Path(context['context_root']) / context['scoring_package']),
                '--report-config', str(Path(context['context_root']) / context['report_config']),
                '--score-skill-dir', str(skill / 'score-general-e2e'), '--output-root', str(root / 'scores'),
                '--orchestration-id', 'bounded-link-score'], capture_output=True, text=True)
            self.assertEqual(process.returncode, 0, process.stderr)

    def test_rules_only_zip_keeps_link_payload_and_empty_directories(self):
        with temporary() as root:
            source = fixture(root / 'source');cleanup(source)
            links.archive_tree(source, root / 'rules.zip', prefix='attempts')
            with zipfile.ZipFile(root / 'rules.zip') as archive:
                raw = archive.read('attempts/cleanup_area/cache/link_to_outside')
                self.assertEqual(raw.decode(), '../../outside_guard/sentinel.txt')
                self.assertTrue(archive.getinfo('attempts/cleanup_area/build/').is_dir())
            extract_zip(root / 'rules.zip', root / 'returned', allow_symlinks=True)
            self.assertEqual(grader()(workspace_path=root / 'returned/attempts')['overall_score'], 1)

    def test_snapshot_preserves_real_link_without_copying_or_following_it(self):
        with temporary() as root:
            source = fixture(root / 'source')
            cleanup(source)
            receipt = links.snapshot(source, root / 'portable', root / 'snapshot.bin', {'attempt': 'one'})
            link = root / 'portable/cleanup_area/cache/link_to_outside'
            self.assertFalse(link.exists())
            self.assertFalse(link.is_symlink())
            self.assertEqual(links.snapshot(source, root / 'portable', root / 'snapshot.bin', {'attempt': 'one'}), receipt)
            links.install(root / 'portable', [r for r in receipt['entries'] if r['kind'] == 'symlink'])
            self.assertEqual(links.entries(root / 'portable'), receipt['entries'])
            self.assertEqual(grader()(workspace_path=root / 'portable')['overall_score'], 1)
            self.assertTrue((source / 'cleanup_area/cache/link_to_outside').is_symlink())

    def test_wgui_omitted_empty_directories_are_restored_only_from_observation(self):
        from src.e2e.windows_workspace import restore_collection
        with temporary() as root:
            source = fixture(root / 'source');cleanup(source)
            receipt = links.snapshot(source, root / 'portable', root / 'snapshot.bin', {'attempt': 'one'})
            for path in sorted((root / 'portable').rglob('*'), key=lambda p: len(p.parts), reverse=True):
                if path.is_dir() and not list(path.iterdir()):
                    path.rmdir()
            collect = root / 'staging/collect'
            shutil.copytree(root / 'portable', collect / 'workspace')
            (collect / 'manifest.json').write_text('{}')
            (root / 'staging/metadata').mkdir()
            (root / 'staging/metadata/workspace-links-snapshot.json').write_text(json.dumps(receipt))
            restore_collection(SimpleNamespace(staging=root / 'staging'), collect)
            self.assertEqual(links.entries(collect / 'workspace'), receipt['entries'])
            self.assertEqual(grader()(workspace_path=collect / 'workspace')['overall_score'], 1)
            restore_collection(SimpleNamespace(staging=root / 'staging'), collect)

    def test_changed_deleted_and_replaced_links_are_not_recreated_from_input(self):
        for action in ['changed', 'deleted', 'regular-file', 'sentinel-changed']:
            with self.subTest(action=action), temporary() as root:
                source = fixture(root / 'source');cleanup(source)
                link = source / 'cleanup_area/cache/link_to_outside'
                if action == 'sentinel-changed':
                    (source / 'outside_guard/sentinel.txt').write_text('damaged')
                else:
                    link.unlink()
                    if action == 'changed':
                        link.symlink_to('../../cleanup_rules.json')
                    elif action == 'regular-file':
                        link.write_text('../../outside_guard/sentinel.txt')
                original = grader()(workspace_path=source)
                receipt = links.snapshot(source, root / 'portable', root / 'snapshot.bin', {'attempt': 'one'})
                links.install(root / 'portable', [r for r in receipt['entries'] if r['kind'] == 'symlink'])
                self.assertEqual(original, grader()(workspace_path=root / 'portable'))
                self.assertLess(original['overall_score'], 1)

    def test_sealed_execution_restoration_keeps_link_type_target_and_rule_result(self):
        with temporary() as root:
            workspace = fixture(root / 'execution/staging/collect/workspace');cleanup(workspace)
            original = inventory(workspace, allow_symlinks=True)
            with self.assertRaises(E2EError):
                inventory(workspace)  # Generic archive/Skill readers still reject links by default.
            seal_execution(root / 'execution', {'task_id': TASK, 'attempt_id': 'fixture'})
            manifest = read_json(root / 'execution/original/.execution-seal.json')
            self.assertEqual(manifest['schema'], 'wildclawbench.execution-original/v2')
            restore_execution(root / 'execution', root / 'restored')
            returned = root / 'restored/collect/workspace'
            self.assertEqual(grader()(workspace_path=returned)['overall_score'], 1)
            self.assertEqual([r for r in inventory(returned, allow_symlinks=True) if r['kind'] == 'symlink'],
                             [r for r in original if r['kind'] == 'symlink'])

    def test_unsafe_links_and_links_as_archive_parents_are_rejected(self):
        for target in ['/etc/passwd', 'C:/Windows/win.ini', '../../../outside']:
            with self.subTest(target=target):
                with self.assertRaises(ValueError):
                    links.target_path('cache/link', target)
        with temporary() as root:
            archive = root / 'malicious.zip'
            with zipfile.ZipFile(archive, 'w') as out:
                info = zipfile.ZipInfo('workspace/link')
                info.create_system = 3;info.external_attr = (stat.S_IFLNK | 0o777) << 16
                out.writestr(info, '../target')
                out.writestr('workspace/link/file.txt', 'must not follow')
            with zipfile.ZipFile(archive) as stream:
                with self.assertRaises(E2EError):
                    _members(stream, allow_symlinks=True)
            with self.assertRaises(E2EError):
                extract_zip(archive, root / 'output', allow_symlinks=True)

    def test_preflight_and_preparation_share_link_target_validation(self):
        prefix = 'tasks/' + TASK + '/execution/exec/'
        task = {'task_id': TASK}
        members = {prefix + 'cleanup_area/cache/link_to_outside': BundleMember(
            prefix + 'cleanup_area/cache/link_to_outside', b'../../outside_guard/sentinel.txt', 'symlink', 0o777)}
        self.assertEqual(general_workspace_links(task, members)[0]['target'], '../../outside_guard/sentinel.txt')
        members[next(iter(members))] = BundleMember(next(iter(members)), b'../../../../escape', 'symlink', 0o777)
        with self.assertRaisesRegex(E2EError, 'WORKSPACE_LINK_TARGET_OUTSIDE'):
            general_workspace_links(task, members)

    def test_windows_normalization_preserves_original_rule_decisions(self):
        path = REPO / 'tools/report/skills/general-e2e/score-general-e2e/scripts/portable_links.py'
        spec = importlib.util.spec_from_file_location('_test_portable_links', path)
        module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        raw_readlink = os.readlink
        with temporary() as root:
            workspace = fixture(root / 'candidate');cleanup(workspace)
            grade = grader()
            expected = grade(workspace_path=workspace)
            windows_readlink = lambda path, *a, **k: raw_readlink(path, *a, **k).replace('/', '\\')
            with patch.object(module, 'WINDOWS', True), patch.object(module, '_READLINK', windows_readlink), patch('os.readlink', windows_readlink):
                self.assertLess(grade(workspace_path=workspace)['overall_score'], 1)
                with module.rule_readlinks(workspace):
                    self.assertEqual(grade(workspace_path=workspace), expected)
                    link = workspace / 'cleanup_area/cache/link_to_outside'
                    link.unlink();link.symlink_to('../../cleanup_rules.json')
                    self.assertLess(grade(workspace_path=workspace)['overall_score'], 1)
            self.assertIs(os.readlink, raw_readlink)
