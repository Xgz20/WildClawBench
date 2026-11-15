import copy
import json
from pathlib import Path
import tempfile
import unittest

from src.e2e.common import atomic_json, file_sha256, E2EError
from src.e2e.trace import normalize_rollout, resource_metrics
from src.e2e.general_reports import _native_resource_projection, report_module
from tests.e2e.test_scheduler import native_fixture, GUEST


class NativeResourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / 'rollout.jsonl'
        self.rows = [json.loads(line) for line in native_fixture('prompt', 'session', 'turn').splitlines()]
        self.rows.insert(1, {'type': 'event_msg', 'payload': {'type': 'task_started', 'turn_id': 'turn'}})
        self.identity = {'batch_id': 'b', 'unit_id': 'u', 'task_id': 't', 'attempt_id': 'a'}
        self.usage = {'input_tokens': 100, 'cached_input_tokens': 50, 'output_tokens': 10, 'reasoning_output_tokens': 4, 'total_tokens': 110}
        info = next(row['payload']['info'] for row in self.rows if row['payload'].get('type') == 'token_count')
        info.update(total_token_usage=self.usage, last_token_usage=copy.deepcopy(self.usage))

    def tearDown(self): self.temp.cleanup()

    def binding(self):
        self.path.write_text('\n'.join(json.dumps(row) for row in self.rows)+'\n')
        return normalize_rollout(self.path, identity=self.identity, prompt='prompt', guest_cwd=GUEST,
            requested_model='spark-x2.6', requested_effort='high',
            report={'usage': {'input_tokens': 100, 'cache_tokens': 50, 'output_tokens': 14}})

    def test_native_usage_survives_controller_double_count_without_recounting_snapshots(self):
        duplicate = copy.deepcopy(next(row for row in self.rows if row['payload'].get('type') == 'token_count'))
        self.rows.insert(-1, duplicate)
        binding = self.binding();metrics = resource_metrics(self.identity, binding, [])
        self.assertEqual(metrics['metrics']['usage']['output_tokens']['value'], 10)
        self.assertEqual(metrics['metrics']['usage']['reasoning_output_tokens']['value'], 4)
        self.assertEqual(metrics['metrics']['usage']['total_tokens']['value'], 110)
        self.assertEqual(metrics['metrics']['requests']['request_count']['value'], 1)
        self.assertEqual(binding['native_resources']['usage_reconciliation']['repeated_snapshots'], 1)
        self.assertIsNone(metrics['metrics']['requests']['request_attempt_count']['value'])

    def test_missing_usage_advance_remains_partial_and_reset_never_falls_back_to_controller(self):
        row = copy.deepcopy(next(row for row in self.rows if row['payload'].get('type') == 'token_count'))
        row['payload']['info']['total_token_usage'] = {key: value*3 for key,value in self.usage.items()}
        self.rows.insert(-1, row)
        m=resource_metrics(self.identity,self.binding(),[])
        self.assertIsNone(m['metrics']['usage']['total_tokens']['value'])
        self.assertEqual(m['collection']['known_subtotals']['total_tokens'],220)
        self.assertIsNone(m['metrics']['requests']['request_count']['value'])
        row['payload']['info']['total_token_usage'] = {key: 0 for key in self.usage}
        m=resource_metrics(self.identity,self.binding(),[])
        self.assertIsNone(m['metrics']['usage']['input_tokens']['value'])
        self.assertTrue(any('REPLAY_REJECTED' in warning for warning in m['collection']['warnings']))

    def test_report_supplement_preserves_frozen_files_and_rejects_raw_drift(self):
        binding=self.binding();core,_=report_module()
        unit=self.root/'report/unit';evidence=unit/'evidence/tasks/t/a';raw=evidence/'trace/raw/rollout.jsonl';raw.parent.mkdir(parents=True)
        raw.write_bytes(self.path.read_bytes())
        atomic_json(evidence/'trace/trace-index.json',{'identity':self.identity,'session':binding['session'],
            'raw_trace':[{'path':'raw/rollout.jsonl','sha256':file_sha256(raw),'size':raw.stat().st_size}]})
        prompt=unit/'execution/tasks/t/PROMPT.md';prompt.parent.mkdir(parents=True);prompt.write_text('prompt')
        base=resource_metrics(self.identity,{k:v for k,v in binding.items() if k!='native_resources'},[])
        atomic_json(evidence/'resource-metrics.json',base);atomic_json(evidence/'metadata/report.json',{'usage':{'input_tokens':100,'output_tokens':14,'cache_tokens':50}})
        record={'identity':self.identity,'session':binding['session'],'model':{'requested_id':'spark-x2.6','reasoning_effort':'high'},
            'resource_metrics_path':'evidence/tasks/t/a/resource-metrics.json','evidence':{'trace_index_path':'evidence/tasks/t/a/trace/trace-index.json'}}
        row={'resource':{field:core.metric_observation(base,field) for field,_,_ in core.RESOURCE_FIELDS},'lineage':{}}
        before={p:file_sha256(p) for p in unit.rglob('*') if p.is_file()}
        _native_resource_projection(core,row,record,unit.parent)
        self.assertEqual(row['resource']['request_count']['value'],1)
        self.assertEqual(row['resource']['total_tokens']['value'],110)
        self.assertTrue((unit.parent/'report-resource-supplement.json').is_file())
        self.assertEqual(before,{p:file_sha256(p) for p in before})
        raw.write_text('changed')
        with self.assertRaisesRegex(E2EError,'RESOURCE_DRIFT'):_native_resource_projection(core,row,record,unit.parent)
