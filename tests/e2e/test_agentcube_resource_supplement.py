import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from src.e2e.agentcube import AgentCubeConfig
from src.e2e.artifacts import remove_temporary_tree
from src.e2e.common import read_json, load_script
from src.e2e.engine import run_batch
from src.e2e.handoff import prepare_scoring_context
from src.e2e.preparation import prepare_batch
from src.e2e.store import BatchStore
from src.e2e.trace import normalize_rollout
from tests.e2e.test_scheduler import FakeDriver, Provider, GUEST


class AgentCubeSupplementTests(unittest.TestCase):
    def test_replays_original_bound_usage_and_rejects_rehashed_forged_totals(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            repo = Path(__file__).resolve().parents[2]
            task = '03_Social_Interaction_task_003_colleague_leave_reply'
            batch = prepare_batch(repo, root, {'batch_id': 'resource-replay',
                'selection': {'scenario': 'general', 'dataset': 'general-custom60-v1', 'task_ids': [task]},
                'units': [{'harness': 'astronstudio', 'model': 'spark-x2.6', 'reasoning_effort': 'high'}]})
            provider = Provider()

            class Driver(FakeDriver):
                def execute(self):
                    result = super().execute()
                    result['cleanup'].update(workspace=GUEST, before=[], root_pid=None, disposition='already_exited')
                    path = self.staging / result['native_path']
                    rows = [json.loads(line) for line in path.read_text().splitlines()]
                    rows.insert(1, {'timestamp': rows[0]['timestamp'], 'type': 'event_msg',
                        'payload': {'type': 'task_started', 'turn_id': result['binding']['session']['turn_id']}})
                    usage = next(row for row in rows if row['payload'].get('type') == 'token_count')
                    value = {'input_tokens': 100, 'output_tokens': 10, 'cached_input_tokens': 50,
                             'reasoning_output_tokens': 2, 'total_tokens': 110}
                    usage['payload']['info'] = {'total_token_usage': value, 'last_token_usage': value}
                    rows.insert(-1, json.loads(json.dumps(usage)))  # repeated cumulative snapshot is not a second request
                    path.write_text('\n'.join(json.dumps(row) for row in rows) + '\n')
                    result['binding'] = normalize_rollout(path, identity=result['identity'], prompt=self.task['prompt'],
                        guest_cwd=GUEST, requested_model='spark-x2.6', requested_effort='high', report=result['report'])
                    evidence = self.staging / 'collect/evidence'
                    evidence.mkdir()
                    (evidence / 'diagnostics.json').write_text('{"product_version":"synthetic"}')
                    return result

            def factory(**kwargs):
                prompt = (batch / kwargs['task']['input_root'] / 'execution/PROMPT.md').read_text()
                return Driver(**{**kwargs, 'task': {**kwargs['task'], 'prompt': prompt}}, provider=provider)

            try:
                run_batch(batch, AgentCubeConfig(user_id='synthetic', auth_token='synthetic'), driver_factory=factory)
                store = BatchStore(batch)
                claim = store.claim_score('synthetic', 1, mode='streaming')
                context = prepare_scoring_context(batch, claim['key'], claim['claim_id'])
                unit = Path(context['context_root']) / context['unit_root']
                record = Path(context['context_root']) / context['execution_record']
                original = record.read_bytes()
                metrics_path = unit / read_json(record)['resource_metrics_path']
                original_metrics = metrics_path.read_bytes()
                script = repo / 'tools/report/e2e-shared/general-resource-supplements/index.mjs'
                args = ['--unit-root', str(unit), '--execution-record', str(record), '--task-id', task]
                result = subprocess.run(['node', str(script), 'create-agentcube', *args], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                output = json.loads(result.stdout)
                self.assertEqual(output['metrics']['metrics']['requests']['request_count']['value'], 1)
                self.assertEqual(output['metrics']['metrics']['usage']['total_tokens']['value'], 110)
                self.assertIsNone(output['metrics']['metrics']['usage']['cache_creation_input_tokens']['value'])
                self.assertEqual(record.read_bytes(), original)
                self.assertEqual(metrics_path.read_bytes(), original_metrics)
                supplement = unit / 'evidence/resource-supplements' / task
                report = load_script(repo / 'tools/report/skills/general-e2e/report-general-e2e/scripts/report_general_e2e.py',
                                     'agentcube_resource_report_scope_test')
                scope = {'harness': {'id': 'astronstudio'}, 'task_ids': [task]}
                report.validate_return_supplement_scope(unit, scope)
                report.validate_return_supplement_scope(unit, read_json(unit / 'manifest.json'))
                with self.assertRaisesRegex(report.ReportError, 'RESOURCE_SUPPLEMENT_SCOPE_INVALID'):
                    report.validate_return_supplement_scope(unit, {**scope, 'harness': {'id': 'unknown'}})
                original_manifest = (supplement / 'supplement.json').read_bytes()
                forged_manifest = json.loads(original_manifest)
                forged_manifest['schema_version'] = 'unknown-profile'
                (supplement / 'supplement.json').write_text(json.dumps(forged_manifest))
                with self.assertRaisesRegex(report.ReportError, 'RESOURCE_SUPPLEMENT_SCOPE_INVALID'):
                    report.validate_return_supplement_scope(unit, scope)
                (supplement / 'supplement.json').write_bytes(original_manifest)
                changed = supplement / 'resource-metrics.json'
                data = read_json(changed)
                data['metrics']['usage']['total_tokens']['value'] = 999
                changed.write_text(json.dumps(data))
                manifest = read_json(supplement / 'supplement.json')
                ref = next(row for row in manifest['artifacts'] if row['path'] == changed.name)
                ref.update(size=changed.stat().st_size, sha256=hashlib.sha256(changed.read_bytes()).hexdigest())
                (supplement / 'supplement.json').write_text(json.dumps(manifest))
                result = subprocess.run(['node', str(script), 'verify', *args], capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('AGENTCUBE_RESOURCE_RECOMPUTATION', result.stderr)
            finally:
                remove_temporary_tree(root)
