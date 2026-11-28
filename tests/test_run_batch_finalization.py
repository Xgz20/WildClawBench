import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from eval import run_batch
from src.agents.base import AgentExecution


class BatchFinalizationTests(unittest.TestCase):
    def test_freeze_error_preserves_native_outcome_collects_evidence_and_always_cleans_up(self):
        for usage_fails in (False, True):
            with self.subTest(usage_fails=usage_fails), tempfile.TemporaryDirectory() as temp:
                root = Path(temp); events = []; gateway = Mock(); agent = Mock()
                backend = SimpleNamespace(transcript_container_path='/tmp/transcript.jsonl', expects_gateway=True)

                def execute(spec):
                    (spec.output_dir / 'execution_status.json').write_text(json.dumps({'status': 'finished', 'exit_code': 0}))
                    return AgentExecution(1.0, gateway_proc=gateway, agent_proc=agent)

                def freeze(*args, **kwargs):
                    events.append('freeze')
                    raise RuntimeError('FREEZE_INPUT_FAILED')

                def usage(**kwargs):
                    events.append('usage')
                    if usage_fails: raise ValueError('USAGE_UNAVAILABLE')
                    return {'total_tokens': 0, 'request_count': 0, 'usage_complete': False}

                backend.run_task = execute; backend.collect_usage = usage
                task = dict(task_id='case', category='category', workspace_path=str(root / 'workspace'),
                            prompt='original task', timeout_seconds=60)
                with patch.dict('os.environ', {'WCB_DEFER_SCORING': '1'}), \
                        patch.object(run_batch, '_task_provenance_or_unavailable', return_value={}), \
                        patch.object(run_batch, 'grade_the_task', side_effect=freeze), \
                        patch.object(run_batch, 'collect_task_output', side_effect=lambda *a, **k: events.append('collect')), \
                        patch.object(run_batch, 'scan_run_dir', return_value={'has_validity_failure': False, 'needs_review': False, 'items': []}), \
                        patch.object(run_batch, 'close_proc_log') as close, \
                        patch.object(run_batch, 'remove_container', side_effect=lambda _: events.append('remove')):
                    with self.assertRaisesRegex(RuntimeError, 'FREEZE_INPUT_FAILED'):
                        run_batch.run_single_task(task, 'model', backend, root)
                self.assertEqual(events, ['freeze', 'usage', 'collect', 'remove'])
                gateway.terminate.assert_called_once(); self.assertEqual(close.call_count, 2)
                failure = json.loads(next(root.rglob('post-execution-errors.json')).read_text())
                self.assertEqual(failure['errors'][0]['stage'], 'freeze_scoring_input')
                if usage_fails:
                    self.assertEqual(failure['errors'][1]['stage'], 'collect_usage')
                else:
                    self.assertEqual(len(failure['errors']), 1)
                    self.assertFalse(json.loads(next(root.rglob('usage.json')).read_text())['usage_complete'])
                status = json.loads(next(root.rglob('execution_status.json')).read_text())
                self.assertEqual(status, {'status': 'finished', 'exit_code': 0})
                self.assertFalse(list(root.rglob('score.json')))

    def test_output_collection_failure_cannot_skip_cleanup_after_valid_grading(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            backend = SimpleNamespace(run_task=lambda _: AgentExecution(1.5), expects_gateway=False,
                                      transcript_container_path='', collect_usage=lambda **kw: {'request_count': 0})
            task = dict(task_id='case', category='category', workspace_path=str(root), prompt='task', timeout_seconds=60)
            with patch.object(run_batch, '_task_provenance_or_unavailable', return_value={}), \
                    patch.object(run_batch, 'grade_the_task', side_effect=lambda *args, **kw: args[4]), \
                    patch.object(run_batch, 'collect_task_output', side_effect=OSError('collection failed')), \
                    patch.object(run_batch, 'scan_run_dir', return_value={'has_validity_failure': False, 'needs_review': False, 'items': []}), \
                    patch.object(run_batch, 'remove_container') as remove:
                result = run_batch.run_single_task(task, 'model', backend, root)
            remove.assert_called_once()
            self.assertEqual(result['elapsed_time'], 1.5)
            self.assertIsNone(result['error'])
