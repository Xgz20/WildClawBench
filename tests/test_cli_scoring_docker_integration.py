"""Opt-in, offline Docker checks; no Harness/model calls or production writes.

WCB_RUN_CLI_SCORING_DOCKER_TESTS=1 python -m unittest tests.test_cli_scoring_docker_integration
Optionally set WCB_CLI_REPLAY_ROOT to an investigation package containing
bounded-49..52 and score-error-50-1023/scoring-input/workspace.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import uuid
from contextlib import contextmanager

from src.cli_scoring import docker_judge, freeze_input, input_inventory, score, workspace_inventory
from src.e2e.common import atomic_json
from src.e2e import headless
from src.utils.task_parser import parse_task_md
from tests.e2e.test_workspace_links import REPO, TASK, fixture, cleanup


@contextmanager
def shared_temporary_directory():
    # Colima shares /Users, while macOS's default /private/var/folders temp
    # directory may not be available to Docker bind mounts.
    base = Path(os.environ.get('WCB_DOCKER_TEST_ROOT', str(Path.home() / '.cache/wcb-cli-docker-tests')))
    base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=base) as directory:
        yield directory


@unittest.skipUnless(os.environ.get('WCB_RUN_CLI_SCORING_DOCKER_TESTS') == '1', 'opt-in offline Docker integration')
class CliScoringDockerTests(unittest.TestCase):
    def test_real_docker_freeze_and_rule_grading_keep_link_semantics(self):
        name = 'wcb-cli-links-test-' + uuid.uuid4().hex[:12]
        with shared_temporary_directory() as temp:
            root = Path(temp); native = fixture(root / 'native'); cleanup(native)
            transcript = root / 'trace.jsonl'; transcript.write_text('')
            task = parse_task_md(REPO / 'tasks/general/regression/06_Safety_Alignment' / (TASK + '.md'))
            try:
                subprocess.run(['docker', 'run', '-d', '--name', name, '--network', 'none',
                                'python:3.11-bookworm', 'sleep', '300'], capture_output=True, check=True)
                subprocess.run(['docker', 'cp', str(native), name + ':/tmp_workspace'], capture_output=True, check=True)
                subprocess.run(['docker', 'cp', str(transcript), name + ':/tmp/transcript.jsonl'], capture_output=True, check=True)
                output = root / 'output'; output.mkdir()
                freeze_input(name, output, task, '/tmp/transcript.jsonl')
            finally:
                subprocess.run(['docker', 'rm', '-f', name], capture_output=True)
            source = output / 'scoring-input'
            link = source / 'workspace/cleanup_area/cache/link_to_outside'
            self.assertTrue(link.is_symlink())
            self.assertEqual(str(link.readlink()), '../../outside_guard/sentinel.txt')
            expected = input_inventory(source)
            with patch.dict(os.environ, {}):
                result = score(source, root / 'positive', {'transport': 'docker-cli', 'harness': 'codex',
                    'model': 'no-model-invoked', 'timeout_seconds': 60})
            self.assertEqual(result['overall_score'], 1., result)
            self.assertEqual(input_inventory(source), expected)
            self.assertEqual(json.loads((root / 'positive/result.json').read_text())['scoring']['judge_call_count'], 0)
            # A materialized copy is not equivalent to the required symbolic link.
            invalid = root / 'invalid'; shutil.copytree(source, invalid, symlinks=True)
            bad = invalid / 'workspace/cleanup_area/cache/link_to_outside'
            bad.unlink(); bad.write_bytes((invalid / 'workspace/outside_guard/sentinel.txt').read_bytes())
            (invalid / 'manifest.json').unlink()
            manifest = json.loads((source / 'manifest.json').read_text())
            atomic_json(invalid / 'manifest.json', {**manifest, 'files': input_inventory(invalid)})
            with patch.dict(os.environ, {}):
                result = score(invalid, root / 'negative', {'transport': 'docker-cli', 'harness': 'codex',
                    'model': 'no-model-invoked', 'timeout_seconds': 60})
            self.assertLess(result['overall_score'], 1., result)

    def test_native_python_cache_generation_in_runtime_never_mutates_original(self):
        with shared_temporary_directory() as temp:
            root = Path(temp); candidate = root / 'candidate'
            replay = os.environ.get('WCB_CLI_REPLAY_ROOT')
            replay_path = Path(replay) / 'score-error-50-1023/scoring-input/workspace' if replay else None
            if replay_path and replay_path.is_dir():
                shutil.copytree(replay_path, candidate, symlinks=True)
            else:
                (candidate / 'project').mkdir(parents=True)
                (candidate / 'project/pipeline.py').write_text('answer = 1\n')
                (candidate / 'project/test_pipeline.py').write_text(
                    'import unittest\nfrom pipeline import answer\nclass Probe(unittest.TestCase):\n def test_answer(self): self.assertEqual(answer,1)\n')
            original = workspace_inventory(candidate)
            atomic_json(root / 'judge-request.json', {'messages': []})
            (root / 'PROMPT.md').write_text('offline verification only')
            real_docker = headless.docker
            stub = '''import sys, os, json, errno, subprocess
from pathlib import Path
sys.path.insert(0, '/runner')
import headless_worker as w
def verify_only(config, prompt, attempt):
    assert attempt == Path('/job/runtime')
    assert os.environ['PYTHONDONTWRITEBYTECODE'] == '1'
    try:
        Path('/job/candidate/forbidden-new-file').write_text('must fail')
    except OSError as error:
        assert error.errno == errno.EROFS, error
    else:
        raise AssertionError('original mount is writable')
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='0')
    subprocess.run([sys.executable, '-m', 'unittest', '-v'], cwd=attempt/'candidate/project', env=env, check=True)
    caches = [str(p.relative_to(attempt)) for p in (attempt/'candidate').rglob('*.pyc')]
    assert caches, 'runtime Python test did not create a cache'
    (attempt/'judge-response.json').write_text('{"scores":{"C1":1}}')
    Path('/job/runtime-validation.json').write_text(json.dumps(dict(model_called=False, original_readonly=True, runtime_caches=caches)))
w.launch_agent = verify_only
w.agent_identity = lambda config: None
'''

            def offline(config, *args, **kwargs):
                arguments = list(args)
                if arguments[0] == 'run':
                    arguments[1:1] = ['--network', 'none']
                    arguments[-1] = stub + '\nexec(' + repr(arguments[-1]) + ')'
                return real_docker(config, *arguments, **kwargs)

            with patch.dict(os.environ, {'E2E_SCORER_API_KEY': 'offline-synthetic'}), \
                    patch.object(headless, 'docker', side_effect=offline):
                context = subprocess.check_output(['docker', 'context', 'show'], text=True).strip()
                result = docker_judge(root, {'harness': 'codex', 'image_id': 'python:3.11-bookworm',
                    'docker_context': context, 'timeout_seconds': 60})
            self.assertEqual(json.loads(result)['scores']['C1'], 1)
            self.assertEqual(workspace_inventory(candidate), original)
            self.assertTrue(json.loads((root / 'candidate-integrity.json').read_text())['valid'])
            self.assertFalse(json.loads((root / 'runtime-validation.json').read_text())['model_called'])

    def test_replayed_four_workspaces_can_be_frozen_without_modifying_the_snapshots(self):
        replay = os.environ.get('WCB_CLI_REPLAY_ROOT')
        if not replay:
            self.skipTest('no optional investigation snapshots selected')
        for run_id in range(49, 53):
            source = Path(replay) / f'bounded-{run_id}/scoring-input'
            with self.subTest(run=run_id), shared_temporary_directory() as temp:
                root = Path(temp); before = input_inventory(source)
                name = 'wcb-cli-replay-test-' + uuid.uuid4().hex[:12]
                try:
                    subprocess.run(['docker', 'run', '-d', '--name', name, '--network', 'none',
                                    'python:3.11-bookworm', 'sleep', '60'], capture_output=True, check=True)
                    subprocess.run(['docker', 'cp', str(source / 'workspace'), name + ':/tmp_workspace'], capture_output=True, check=True)
                    subprocess.run(['docker', 'cp', str(source / 'transcript.jsonl'), name + ':/tmp/transcript.jsonl'], capture_output=True, check=True)
                    task = json.loads((source / 'task.json').read_text())
                    freeze_input(name, root, task, '/tmp/transcript.jsonl')
                finally:
                    subprocess.run(['docker', 'rm', '-f', name], capture_output=True)
                self.assertEqual(workspace_inventory(root / 'scoring-input/workspace'), workspace_inventory(source / 'workspace'))
                self.assertEqual(input_inventory(source), before)
                self.assertTrue((root / 'scoring-input/manifest.json').is_file())
