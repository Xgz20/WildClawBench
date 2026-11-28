import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from src.utils import judge_shim
from src.cli_scoring import score, desktop_judge, verify_desktop_candidate
from src.e2e.artifacts import inventory
from src.e2e.common import atomic_json


class CliScoringTests(unittest.TestCase):
    def test_pure_rule_score_reports_that_no_desktop_judge_was_called(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source'
            (source / 'workspace').mkdir(parents=True)
            atomic_json(source / 'task.json', {'task_id': 'rule-only', 'automated_checks': 'fixture', 'grading_type': 'automated'})
            (source / 'transcript.jsonl').write_text('')
            atomic_json(source / 'manifest.json', {'schema': 'wildclawbench.cli-scoring-input/v1', 'image': 'frozen', 'files': inventory(source)})
            with patch.dict('os.environ', {}), patch('src.cli_scoring.docker'), patch('src.cli_scoring.desktop_judge') as judge, \
                    patch('src.utils.grading.run_grading', return_value={'overall_score': 1.0}):
                result = score(source, root / 'result', {'transport': 'agentcube-desktop', 'harness': 'astudio', 'model': 'deepseek', 'timeout_seconds': 60})
            judge.assert_not_called()
            self.assertEqual(result['overall_score'], 1)
            data = json.loads((root / 'result/result.json').read_text())
            self.assertEqual(data['scoring']['method'], 'rules')
            self.assertEqual(data['scoring']['rule_execution'], 'docker')
            self.assertEqual(data['scoring']['judge_call_count'], 0)

    def test_desktop_judge_passes_the_real_native_driver_preflight_contract(self):
        from src.e2e.backend import AStudioSandboxDriver
        from src.e2e.agentcube import AgentCubeConfig
        import shutil

        class ProbeDriver(AStudioSandboxDriver):
            def execute(self):
                self.preflight()  # Previously failed on missing definition_inventory.
                self.staging.mkdir(parents=True, exist_ok=True)
                (self.staging / 'native.jsonl').write_text('fixture native trace')
                returned = self.staging / 'returned'
                shutil.copytree(self.batch / 'candidate', returned / 'candidate', symlinks=True)
                (returned / 'candidate/answer.txt').chmod(0o444)
                return {'binding': {'events': [], 'final_response': '{"scores":{"C1":1}}'},
                        'native_path': 'native.jsonl', 'workspace': 'returned'}

        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            (work / 'candidate').mkdir()
            (work / 'candidate/answer.txt').write_text('original')
            (work / 'candidate/nested').mkdir()
            (work / 'candidate/nested/answer-link').symlink_to('../answer.txt')
            atomic_json(work / 'judge-request.json', {'messages': []})
            (work / 'PROMPT.md').write_text('Original scoring instructions')
            with patch('src.e2e.backend.AStudioSandboxDriver', ProbeDriver), \
                    patch.object(AgentCubeConfig, 'load', return_value=AgentCubeConfig(user_id='fixture')):
                response = desktop_judge(work, {'harness': 'astudio', 'model': 'spark-x2.6', 'template': 'fixture',
                    'timeout_seconds': 60, 'reasoning_effort': 'high'}, None)
            self.assertEqual(json.loads(response)['scores']['C1'], 1)
            self.assertTrue((work / 'judge-native.jsonl').is_file())
            self.assertTrue((work / 'input/execution/workspace/candidate/nested/answer-link').is_symlink())
            self.assertTrue(json.loads((work / 'candidate-integrity.json').read_text())['valid'])

    def test_desktop_candidate_integrity_still_rejects_content_and_file_set_changes(self):
        import shutil
        for mutation in ('edit', 'add', 'delete', 'rename', 'type'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                work = Path(directory)
                (work / 'original/nested').mkdir(parents=True)
                (work / 'original/nested/answer.txt').write_text('original')
                shutil.copytree(work / 'original', work / 'returned')
                file = work / 'returned/nested/answer.txt'
                if mutation == 'edit':
                    file.write_text('modified')  # Same size, different bytes.
                elif mutation == 'add':
                    (work / 'returned/extra.txt').write_text('extra')
                elif mutation == 'rename':
                    file.rename(file.with_name('renamed.txt'))
                else:
                    file.unlink()
                    if mutation == 'type':
                        file.mkdir()
                with self.assertRaisesRegex(RuntimeError, 'CLI_JUDGE_CANDIDATE_DRIFT'):
                    verify_desktop_candidate(work / 'original', work / 'returned', work / 'integrity.json')
                self.assertFalse(json.loads((work / 'integrity.json').read_text())['valid'])

    def test_judge_channel_roundtrips_original_messages_and_response(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def responder():
                for _ in range(50):
                    requests = list(root.glob('*.request.json'))
                    if requests:
                        path = requests[0]
                        data = json.loads(path.read_text())
                        self.assertEqual(data['messages'], [{'role': 'user', 'content': '原 Rubric'}])
                        path.with_name(path.name.replace('.request.', '.response.')).write_text(json.dumps({'text': '{"scores":{"C1":0}}', 'model': 'judge'}))
                        return
                    time.sleep(.02)
                raise AssertionError('request missing')
            thread = threading.Thread(target=responder)
            thread.start()
            with patch.dict('os.environ', {'WCB_JUDGE_CHANNEL': str(root)}):
                response = judge_shim.OpenAI().chat.completions.create(model='judge', messages=[{'role': 'user', 'content': '原 Rubric'}])
            thread.join()
            self.assertEqual(json.loads(response.choices[0].message.content)['scores']['C1'], 0)
            self.assertIsNone(response.usage)

    def test_scoring_rejects_modified_frozen_input_before_docker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'manifest.json').write_text(json.dumps({'files': [], 'image': 'frozen'}))
            (root / 'task.json').write_text('{}')
            with patch('src.cli_scoring.docker') as docker:
                with self.assertRaisesRegex(RuntimeError, 'INPUT_DRIFT'):
                    score(root, root / 'result', {'transport': 'api'})
                docker.assert_not_called()

    def test_resume_does_not_execute_again_while_independent_score_is_pending(self):
        from eval.run_batch import _load_resume_result
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / 'category/case/model-x_20261126_1200'
            (run / 'scoring-input').mkdir(parents=True)
            atomic_json(run / 'scoring-input/manifest.json', {'schema': 'wildclawbench.cli-scoring-input/v1', 'files': [], 'image': 'frozen'})
            atomic_json(run / 'execution_status.json', {'status': 'finished', 'model': 'model-x'})
            task = {'task_id': 'case', 'category': 'category'}
            result = _load_resume_result(root, task, 'model-x', False, False)
            self.assertEqual(result['scoring_status'], 'pending')
            self.assertNotIn('_reliability_rerun', task)
