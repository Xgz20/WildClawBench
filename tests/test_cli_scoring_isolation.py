import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from src.cli_scoring import (copy_workspace, docker_judge, freeze_input, input_inventory, judge_prompt,
                             score, verify_desktop_candidate, workspace_inventory)
from src.e2e.artifacts import inventory
from src.e2e.common import atomic_json


def linked_workspace(root):
    (root / 'cleanup_area/cache').mkdir(parents=True)
    (root / 'outside_guard').mkdir()
    (root / 'outside_guard/sentinel.txt').write_text('protected original')
    (root / 'cleanup_area/cache/link_to_outside').symlink_to('../../outside_guard/sentinel.txt')
    (root / 'empty').mkdir()
    return root


class CliScoringLinksTests(unittest.TestCase):
    def test_freeze_preserves_real_relative_link_and_scores_original_input_format(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); workspace = linked_workspace(root / 'native')
            output = root / 'output'; output.mkdir()

            def docker(*args, **kwargs):
                if args[0] == 'cp':
                    if args[1].endswith(':/tmp_workspace/.'):
                        shutil.copytree(workspace, args[2], symlinks=True)
                    else:
                        Path(args[2]).write_text('original transcript')
                elif args[0] == 'inspect':
                    return '[{"Image":"frozen-image"}]'

            task = {'task_id': 'bounded', 'automated_checks': 'fixture', 'grading_type': 'automated'}
            with patch('src.cli_scoring.docker', side_effect=docker):
                freeze_input('native-container', output, task, '/tmp/trace.jsonl')
            source = output / 'scoring-input'
            manifest = json.loads((source / 'manifest.json').read_text())
            link = next(row for row in manifest['files'] if row['kind'] == 'symlink')
            self.assertEqual(link['path'], 'workspace/cleanup_area/cache/link_to_outside')
            self.assertEqual(link['target'], '../../outside_guard/sentinel.txt')
            self.assertTrue((source / link['path']).is_symlink())
            self.assertEqual([row for row in input_inventory(source) if row['path'] != 'manifest.json'], manifest['files'])
            with patch('src.cli_scoring.docker'), patch('src.utils.grading.run_grading', return_value={'overall_score': 1.0}):
                result = score(source, root / 'score', {'transport': 'docker-cli', 'harness': 'codex', 'model': 'fixture', 'timeout_seconds': 60})
            self.assertEqual(result['overall_score'], 1)
            self.assertTrue((source / 'workspace/empty').is_dir())

    def test_file_only_legacy_inventory_remains_byte_for_byte_compatible(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / 'workspace').mkdir()
            (root / 'workspace/answer.txt').write_text('original')
            self.assertEqual(input_inventory(root), inventory(root))

    def test_copy_and_desktop_verification_preserve_link_type_and_reject_retargeting(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); linked_workspace(root / 'original')
            copy_workspace(root / 'original', root / 'copy')
            verify_desktop_candidate(root / 'original', root / 'copy', root / 'proof.json')
            link = root / 'copy/cleanup_area/cache/link_to_outside'
            link.unlink(); link.symlink_to('../../outside_guard/other.txt')
            with self.assertRaisesRegex(RuntimeError, 'CANDIDATE_DRIFT'):
                verify_desktop_candidate(root / 'original', root / 'copy', root / 'proof.json')

    def test_workspace_link_may_not_escape_into_package_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / 'workspace').mkdir()
            (root / 'transcript.jsonl').write_text('private trace')
            (root / 'workspace/escape').symlink_to('../transcript.jsonl')
            # At package level this link is inside the root. Workspace-level
            # validation must still reject it before copying or running Docker.
            self.assertTrue(workspace_inventory(root))
            with self.assertRaisesRegex(ValueError, 'WORKSPACE_LINK_TARGET_OUTSIDE'):
                input_inventory(root)
            with patch('src.cli_scoring.docker') as docker:
                with self.assertRaisesRegex(ValueError, 'WORKSPACE_LINK_TARGET_OUTSIDE'):
                    copy_workspace(root / 'workspace', root / 'copy')
                docker.assert_not_called()

    def test_scoring_rejects_changed_link_or_materialized_link_before_docker(self):
        for change in ('retarget', 'materialize'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temp:
                root = Path(temp); linked_workspace(root / 'workspace')
                atomic_json(root / 'task.json', {})
                (root / 'transcript.jsonl').write_text('')
                atomic_json(root / 'manifest.json', {'image': 'frozen', 'files': input_inventory(root)})
                link = root / 'workspace/cleanup_area/cache/link_to_outside'; link.unlink()
                if change == 'retarget':
                    link.symlink_to('../../outside_guard/other.txt')
                else:
                    link.write_text('protected original')
                with patch('src.cli_scoring.docker') as docker:
                    with self.assertRaisesRegex(RuntimeError, 'INPUT_DRIFT'):
                        score(root, root / 'score', {'transport': 'api'})
                    docker.assert_not_called()


class CliJudgeIsolationTests(unittest.TestCase):
    def test_runtime_instructions_only_apply_to_the_transport_with_a_prepared_runtime(self):
        self.assertIn('冻结副本', judge_prompt({}))
        self.assertNotIn('当前目录中的 candidate/ 是原执行工作区的运行副本', judge_prompt({}))
        self.assertIn('当前目录中的 candidate/ 是原执行工作区的运行副本', judge_prompt({}, runtime_copy=True))

    def prepare(self, root):
        linked_workspace(root / 'candidate')
        (root / 'candidate/project').mkdir()
        (root / 'candidate/project/pipeline.py').write_text('answer = 1\n')
        (root / 'candidate/project/pipeline.py').chmod(0o444)
        atomic_json(root / 'judge-request.json', {'messages': []})
        (root / 'PROMPT.md').write_text('frozen rubric')
        return {'harness': 'codex', 'image_id': 'frozen-image', 'timeout_seconds': 60}

    def test_cached_verification_changes_runtime_only_and_docker_mounts_original_readonly(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); config = self.prepare(root)
            expected = workspace_inventory(root / 'candidate'); calls = []; secrets = []

            def docker(config, *args, **kwargs):
                calls.append(args)
                if args[0] != 'run':
                    return
                secrets.append(Path(args[args.index('--env-file') + 1]))
                self.assertIn(f'type=bind,src={root / "candidate"},dst=/job/candidate,readonly', args)
                self.assertIn('PYTHONDONTWRITEBYTECODE=1', args)
                self.assertIn('Path("/job/runtime")', args[-1])
                runtime = root / 'runtime/candidate'
                self.assertTrue((runtime / 'cleanup_area/cache/link_to_outside').is_symlink())
                self.assertTrue((runtime / 'project/pipeline.py').stat().st_mode & 0o200)
                (runtime / 'project/__pycache__').mkdir()
                (runtime / 'project/__pycache__/pipeline.cpython-311.pyc').write_bytes(b'cache')
                atomic_json(root / 'runtime/judge-response.json', {'scores': {'C1': 1}})

            with patch.dict(os.environ, {'E2E_SCORER_API_KEY': 'synthetic'}), patch('src.e2e.headless.docker', side_effect=docker):
                response = docker_judge(root, config)
            self.assertEqual(json.loads(response)['scores']['C1'], 1)
            self.assertEqual(workspace_inventory(root / 'candidate'), expected)
            self.assertTrue(json.loads((root / 'candidate-integrity.json').read_text())['valid'])
            self.assertEqual(calls[-1][0], 'rm')
            self.assertTrue(secrets and all(not path.exists() for path in secrets))

    def test_original_file_byte_mode_or_link_changes_remain_fatal(self):
        for change in ('bytes', 'mode', 'link'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temp:
                root = Path(temp); config = self.prepare(root)
                def docker(config, *args, **kwargs):
                    if args[0] != 'run': return
                    if change == 'bytes':
                        (root / 'candidate/project/pipeline.py').chmod(0o644)
                        (root / 'candidate/project/pipeline.py').write_text('answer = 2\n')
                        (root / 'candidate/project/pipeline.py').chmod(0o444)
                    elif change == 'mode':
                        (root / 'candidate/project/pipeline.py').chmod(0o644)
                    else:
                        link = root / 'candidate/cleanup_area/cache/link_to_outside'
                        link.unlink(); link.symlink_to('../../outside_guard/other.txt')
                with patch('src.e2e.headless.docker', side_effect=docker):
                    with self.assertRaisesRegex(RuntimeError, 'CANDIDATE_DRIFT'):
                        docker_judge(root, config)
                self.assertFalse(json.loads((root / 'candidate-integrity.json').read_text())['valid'])

    def test_managed_runtime_contains_context_media_and_readonly_candidate(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = self.prepare(root)
            atomic_json(root / 'scoring-context.json', {'custom_instructions': 'FROZEN_TEMPLATE'})
            (root / 'media-evidence').mkdir()
            (root / 'media-evidence/page.png').write_bytes(b'frozen-media')
            def docker(config, *args, **kwargs):
                if args[0] != 'run':
                    return
                self.assertEqual((root / 'runtime/scoring-context.json').read_bytes(), (root / 'scoring-context.json').read_bytes())
                self.assertEqual((root / 'runtime/media-evidence/page.png').read_bytes(), b'frozen-media')
                for relative in ('candidate', 'scoring-context.json', 'judge-request.json', 'media-evidence'):
                    self.assertIn(f'type=bind,src={root / relative},dst=/job/runtime/{relative},readonly', args)
                atomic_json(root / 'runtime/judge-response.json', {'scores': {'correct': 1}})
            with patch('src.e2e.headless.docker', side_effect=docker):
                self.assertEqual(json.loads(docker_judge(root, config))['scores']['correct'], 1)

    def test_worker_failure_still_records_integrity_removes_container_and_secret(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); config = self.prepare(root); removed = []; secrets = []
            def docker(config, *args, **kwargs):
                if args[0] == 'run':
                    secrets.append(Path(args[args.index('--env-file') + 1]))
                    raise RuntimeError('SCORING_AGENT_TIMEOUT')
                removed.append(args[0])
            with patch('src.e2e.headless.docker', side_effect=docker):
                with self.assertRaisesRegex(RuntimeError, 'SCORING_AGENT_TIMEOUT'):
                    docker_judge(root, config)
            self.assertEqual(removed, ['rm'])
            self.assertTrue(json.loads((root / 'candidate-integrity.json').read_text())['valid'])
            self.assertTrue(secrets and all(not path.exists() for path in secrets))
