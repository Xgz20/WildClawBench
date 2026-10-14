import argparse
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.general_e2e.test_report_general_e2e import REPORT, Fixture
import maas_model_timing as M
import leader_report


SID1 = 'cht0001@request1'
SID2 = 'cht0002@request2'


def cache_hit(sid, perf, result='success', **extra):
    return {'_index': 'cube-log-test', '_id': sid + str(perf), '_source': {
        'sid': sid, 'model': 'spark-x2.5', 'serviceName': 'maas_cube', 'perf': perf,
        'result': result, 'request_time': 100, 'response_time': 100 + float(perf) if isinstance(perf, (int, float)) else 101, **extra}}


def cache(hits, sids=None):
    return {'schema_version': M.CACHE_SCHEMA, 'profile': M.PROFILE, 'model': 'spark-x2.5',
            'service': 'maas_cube', 'query_complete': True, 'requested_sids': sids or [SID1, SID2], 'documents': hits}


class ModelTimingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def source(self, *, gateway=None, errors=False, compaction=False, count=1):
        unit = self.root / 'unit'; directory = unit / 'evidence/tasks/task/attempt'
        raw = directory / 'trace/raw'; raw.mkdir(parents=True, exist_ok=True)
        identity = {'task_id': 'task', 'attempt_id': 'attempt', 'unit_id': 'unit'}
        ex = {'identity': identity, 'session': {'verified': True, 'turn_id': 'turn', 'thread_id': 'session', 'session_id': 'session', 'cwd': '/candidate'},
              'evidence': {'trace_index_path': 'evidence/tasks/task/attempt/trace/trace-index.json'}}
        record = directory / 'execution-record.json'; M.save(record, ex)
        events = [{'type': 'session_meta', 'payload': {'id': 'session', 'cwd': '/candidate'}},
                  {'type': 'event_msg', 'payload': {'type': 'task_started', 'turn_id': 'turn'}},
                  {'type': 'response_item', 'payload': {'type': 'reasoning', 'id': 'rs_' + SID1 + '_0'}},
                  {'type': 'response_item', 'payload': {'type': 'message', 'role': 'assistant', 'id': 'resp_' + SID1 + '_1'}},
                  {'type': 'response_item', 'payload': {'type': 'message', 'role': 'assistant', 'id': 'resp_' + SID1 + '_1'}}]
        if errors: events.append({'type': 'event_msg', 'payload': {'type': 'stream_error'}})
        if compaction: events.append({'type': 'compacted', 'payload': {}})
        events += [{'type': 'event_msg', 'payload': {'type': 'turn_aborted'}}]
        rollout = raw / 'astronstudio-rollout.jsonl'
        rollout.write_text('\n'.join(json.dumps(e) for e in events) + '\n')
        refs = []
        if gateway is not None:
            provider = raw / 'astronstudio-provider-events.jsonl'
            p = {'thread_id': 'session', 'turn_id': 'turn', 'event': {'type': 'turn.gateway-usage.updated', 'payload': {'requests': gateway}}}
            provider.write_text(json.dumps(p) + '\n' + json.dumps(p) + '\n')
            refs = [{'path': 'raw/astronstudio-provider-events.jsonl', 'sha256': M.digest(provider)}]
        trace = directory / 'trace/trace-index.json'; M.save(trace, {'identity': identity, 'raw_trace': refs})
        return {'unit_id': 'unit', 'task_id': 'task', 'execution_attempt_id': 'attempt', 'harness': {'id': 'astronstudio'},
                'resource': {'request_count': {'complete': count is not None, 'value': count}, 'agent_duration_seconds': {'value': 1}},
                'lineage': {'source_unit_root': str(unit), 'source_execution_record': str(record), 'execution_record_sha256': M.digest(record)},
                'tool_calls': {'rollout_path': rollout.relative_to(unit).as_posix(), 'rollout_sha256': M.digest(rollout), 'trace_index_sha256': M.digest(trace)}}

    def test_bound_reasoning_output_pair_and_duplicate_items_count_once(self):
        r = M.extract_requests(self.source())
        self.assertTrue(r['complete']); self.assertEqual(len(r['requests']), 1)
        self.assertEqual(len(r['requests'][0]['rollout_refs']), 3)

    def test_gateway_retries_and_compaction_are_included_and_notifications_deduplicated(self):
        requests = [{'requestId': 'r1', 'responseId': SID1, 'requestKind': 'turn', 'status': 'completed', 'effectiveModel': 'spark-x2.5'},
                    {'requestId': 'r2', 'responseId': SID2, 'requestKind': 'compaction', 'status': 'usage_missing', 'effectiveModel': 'spark-x2.5'}]
        r = M.extract_requests(self.source(gateway=requests, errors=True, compaction=True, count=None))
        self.assertTrue(r['complete']); self.assertEqual(len(r['requests']), 2)
        self.assertEqual(r['requests'][1]['request_kind'], 'compaction')
        requests[1]['responseId'] = None
        self.assertFalse(M.extract_requests(self.source(gateway=requests))['complete'])

    def test_legacy_errors_and_compaction_prevent_claiming_full_request_coverage(self):
        self.assertFalse(M.extract_requests(self.source(errors=True))['complete'])
        self.assertFalse(M.extract_requests(self.source(compaction=True))['complete'])
        self.assertFalse(M.extract_requests(self.source(count=2))['complete'])

    def test_tampered_source_and_wrong_ownership_fail_closed(self):
        row = self.source(); Path(row['lineage']['source_execution_record']).write_text('{}')
        with self.assertRaisesRegex(M.ModelTimingError, 'SHA_MISMATCH'): M.request_ledger({'tasks': [row]})
        row = self.source(); row['execution_attempt_id'] = 'other'
        with self.assertRaisesRegex(M.ModelTimingError, 'IDENTITY_MISMATCH'): M.request_ledger({'tasks': [row]})

    def test_sid_shared_by_two_tasks_cannot_be_attributed_twice(self):
        source = M.extract_requests(self.source()); other = {**source, 'task_id': 'other'}
        with patch.object(M, 'extract_requests', side_effect=[source, other]):
            ledger = M.request_ledger({'tasks': [source, other]})
        self.assertTrue(all(not r['complete'] for r in ledger['tasks']))
        self.assertTrue(all(r['ambiguous_sids'] == [SID1] for r in ledger['tasks']))

    def test_same_service_semantic_duplicates_conflicts_and_true_zero(self):
        hit = cache_hit(SID1, 0); duplicate = {**hit, '_id': 'dup'}
        result = M.normalize_cache(cache([hit, duplicate]))[SID1]
        self.assertEqual(result['status'], 'matched'); self.assertEqual(result['record']['perf_ms'], '0')
        self.assertEqual(M.normalize_cache(cache([hit, cache_hit(SID1, 1)]))[SID1]['status'], 'ambiguous')
        for invalid in [-1, None, True, 'NaN', 'bad']:
            self.assertEqual(M.normalize_cache(cache([cache_hit(SID1, invalid)]))[SID1]['status'], 'invalid')
        with self.assertRaisesRegex(M.ModelTimingError, 'SCOPE_MISMATCH'):
            M.normalize_cache(cache([cache_hit(SID1, 1, serviceName='aigate-frontend')]))

    def test_enrichment_cumulative_failure_cancelled_and_partial_preserve_frozen_values(self):
        row = self.source(); original = copy.deepcopy(row)
        ledger = {'tasks': [{**M.extract_requests(row), 'requests': [{'sid': SID1}, {'sid': SID2}], 'complete': True}]}
        path = self.root / 'cache.json'; M.save(path, cache([cache_hit(SID1, 2000, 'failed'), cache_hit(SID2, 0, 'client_cancelled')]))
        data = {'tasks': [row]}; M.enrich(data, path, ledger=ledger)
        self.assertEqual(row['model_timing']['value'], 2)
        self.assertIn('CUMULATIVE_MODEL_TIME_EXCEEDS_NATIVE_TASK_TIME', row['model_timing']['warnings'])
        self.assertEqual({k:v for k,v in row.items() if k != 'model_timing'}, original)
        M.save(path, cache([cache_hit(SID1, 2000, 'failed')]))
        M.enrich(data, path, ledger=ledger)
        self.assertIsNone(row['model_timing']['value']); self.assertEqual(row['model_timing']['known_subtotal'], 2)
        self.assertEqual(row['model_timing']['coverage'], {'known': 1, 'total': 2, 'unit': 'model_request'})

    def test_exact_sid_query_paginates_and_retains_only_minimal_fields(self):
        calls = []
        pages = [{'hits': {'total': {'value': 2, 'relation': 'eq'}, 'hits': [cache_hit(sid, 1)]}, '_shards': {'failed': 0}} for sid in [SID1, SID2]]
        pages[0]['hits']['hits'][0]['_source']['sensitive_prompt'] = 'must not persist'
        def response(request, **kwargs):
            calls.append(json.loads(request.data)); return io.StringIO(json.dumps(pages[len(calls)-1]))
        with patch.object(M, 'urlopen', side_effect=response), patch.object(M, 'auth_header', return_value=None):
            result = M.fetch_cache({'sids': [SID1, SID2]}, {'es_url': 'https://es.example', 'page_size': 1}, self.root/'cache.json')
        self.assertEqual([c['from'] for c in calls], [0,1])
        self.assertEqual(calls[0]['query']['bool']['filter'][0], {'term': {'model.keyword': 'spark-x2.5'}})
        self.assertNotIn('sensitive_prompt', result['documents'][0]['_source'])
        pages[0]['timed_out'] = True
        with patch.object(M, 'urlopen', return_value=io.StringIO(json.dumps(pages[0]))), patch.object(M, 'auth_header', return_value=None):
            with self.assertRaisesRegex(M.ModelTimingError, 'INCOMPLETE_QUERY'):
                M.fetch_cache({'sids': [SID1]}, {'es_url': 'https://es.example'}, self.root/'bad-cache.json')
        self.assertFalse((self.root/'bad-cache.json').exists())

    def test_task_model_quantiles_share_over_100_and_common_scope(self):
        fixture = Fixture(self.root/'fixture')
        data = REPORT.aggregate(REPORT.validate_batch_inputs(fixture.batch), '2026-09-21T00:00:00Z')
        for row, value in zip(data['tasks'], [1,2,3,100]):
            row['resource']['agent_duration_seconds'].update(value=value, known_subtotal=value, complete=True, status='observed')
            row['model_timing'] = {'complete': True, 'value': value*2, 'known_subtotal': value*2, 'coverage': {'known':1,'total':1}}
        data['units'][0]['resources'] = REPORT.resource_summary(data['tasks'])
        view = REPORT.report_views.task_timing_comparison(data, data['presentation']['unit_labels'])
        self.assertEqual(view['rows'][0][1:8], [106,212,2,26.5,53,2.5,5])
        self.assertEqual(view['rows'][0][9], 141.8)
        data['tasks'] = data['tasks'][:3]; data['units'][0]['resources'] = REPORT.resource_summary(data['tasks'])
        view = REPORT.report_views.task_timing_comparison(data, data['presentation']['unit_labels'])
        self.assertEqual(view['rows'][0][1:8], [6,12,2,2,4,2,4])
        data['tasks'][0]['model_timing']['complete'] = False
        view = REPORT.report_views.task_timing_comparison(data, data['presentation']['unit_labels'])
        self.assertTrue(all(view['rows'][0][i] is None for i in [2,3,5,7,9]))

    def test_report_stage_options_and_target_narrative_use_correct_columns(self):
        fixture = Fixture(self.root/'fixture')
        data = REPORT.aggregate(REPORT.validate_batch_inputs(fixture.batch), '2026-09-21T00:00:00Z')
        uid = data['units'][0]['unit_id']; label = data['presentation']['unit_labels'][uid]
        view = data['presentation']['tables']['效率对比']['timing_table']
        view['rows'][0] = [label,100,80,.8,25,20,10,8,40,32]
        narrative = leader_report.render_task_timing_summary({'target':{'label':label}, 'tables':{'效率对比':{'timing_table':view}}})
        self.assertIn('25.000 秒', narrative); self.assertIn('20.000 秒', narrative); self.assertIn('80.00%', narrative)
        args = REPORT.build_parser().parse_args(['generate', '--batch-root', str(fixture.batch), '--output-dir',str(self.root/'out'), '--node-modules', str(self.root), '--maas-es-cache', str(self.root/'cache')])
        self.assertEqual(args.maas_es_cache, self.root/'cache')
        path = self.root/'cache.json'; M.save(path, cache([], []))
        M.apply_options(data, argparse.Namespace(maas_es_cache=path, maas_es_config=None), self.root/'report')
        self.assertTrue((self.root/'report/model-timing/coverage.json').exists())

    def test_online_query_failure_keeps_baseline_report_and_explicit_unknowns(self):
        row = self.source(); data = {'tasks': [row], 'units': [{'unit_id': 'unit'}]}
        before = copy.deepcopy(row); config = self.root/'config.json'; M.save(config, {'es_url':'https://es.example'})
        with patch.object(M, 'fetch_cache', side_effect=M.ModelTimingError('ES_HTTP_ERROR_503')):
            artifacts = M.apply_options(data,argparse.Namespace(maas_es_cache=None,maas_es_config=config),self.root/'report')
        self.assertEqual(len(artifacts),3)
        self.assertFalse(data['model_timing_provenance']['query_complete'])
        self.assertEqual(data['model_timing_provenance']['query_error_code'],'ES_HTTP_ERROR_503')
        self.assertIsNone(row['model_timing']['value'])
        self.assertEqual({k:v for k,v in row.items() if k!='model_timing'},before)


if __name__ == '__main__':
    unittest.main()
