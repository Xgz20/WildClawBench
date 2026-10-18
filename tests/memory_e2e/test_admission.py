"""Prerequisites must block dispatch and preserve unscored planned episodes."""
import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from eval_memory_e2e.admission import channel_template, exact_response, import_channel_review, response_json
from eval_memory_e2e.batch import load_batch, prepare
from eval_memory_e2e.dataset import load_dataset
from eval_memory_e2e.fixture_driver import respond
from eval_memory_e2e.io import MemoryEvaluationError, events, publish, read_json
from eval_memory_e2e.report import aggregate
from eval_memory_e2e.runner import advance, import_receipt, next_action, register_intent
from eval_memory_e2e.scoring import review_template
from eval_memory_e2e.worker import run_worker

DATA = Path(__file__).resolve().parents[2] / 'tasks/memory-e2e/canaries/scoped-forgetting-v3.json'


class AdmissionTests(unittest.TestCase):
    def test_tolerant_cleanup_rejects_a_forgotten_value_leaked_outside_the_json(self):
        from eval_memory_e2e.cleanup import cleanup_layers
        from eval_memory_e2e.batch import operation_id
        from eval_memory_e2e.io import archive
        self.prepare(read_json(DATA.with_name('scoped-forgetting-v3.1.json')))
        manifest=load_batch(self.root);item=manifest['episodes'][1]
        case=read_json(self.root/'private/scenarios.json')[item['private_key']]
        receipts={}
        for step,text in [('before',json.dumps({'target':self.facts['target_value'],'keep':self.facts['keep_value']})),
                          ('after','旧值 '+self.facts['target_value'].lower()+'\n'+json.dumps({'target':'未知','keep':self.facts['keep_value']}))]:
            source=publish(self.base/(step+'.txt'),text.encode())
            receipts[operation_id(manifest,item['id'],step)]={'status':'completed','artifacts':{'final_response':archive(self.root,source)}}
        result=cleanup_layers(self.root,manifest,item,case,receipts)
        self.assertTrue(result['formation_recall']['passed'])
        self.assertEqual(result['behavior'][0]['status'],'failed')
        self.assertTrue(result['behavior'][0]['target_leaked_in_response'])

    def test_explicit_object_format_handles_prose_and_unclosed_fences_but_rejects_ambiguity(self):
        value={'target':'ERASE-A','keep':'KEEP-B'}
        for text in ['说明：\n```json\n'+json.dumps(value), json.dumps(value)+'\n以上是结果。']:
            self.assertEqual(response_json(text,'single_json_object'),value)
            with self.assertRaises(MemoryEvaluationError):response_json(text)
        for text in ['{"target":"A"} {"target":"B"}', '[{"target":"A"}]',
                     '{"target":"A","target":"B"}', '{"target":NaN}', 'target=A keep=B']:
            with self.subTest(text=text), self.assertRaises(MemoryEvaluationError):response_json(text,'single_json_object')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve(); self.root = self.base / 'batch'

    def prepare(self, data=None):
        path = DATA
        if data is not None:
            path = publish(self.base / 'dataset.json', data)
        prepare(self.root, batch_id='admission', seed='admission', mode='fixture', dataset_path=path, harnesses=['WorkBuddy'])
        manifest = load_batch(self.root)
        self.cold, self.warm = [i['id'] for i in manifest['episodes']]
        self.facts = read_json(self.root / 'private/scenarios.json')['MEM-cleanup-001/r01']['facts']

    def handoff(self, episode, answer=None, workspace_memory=False):
        request = register_intent(self.root, episode)
        reply = respond({**request, 'transport_action': 'dispatch'})
        if answer is not None:
            path = publish(self.base / (request['operation_id'] + '.answer'), json.dumps(answer, ensure_ascii=False).encode())
            reply['final_response'] = str(path)
        if workspace_memory:
            publish(Path(request['workspace']) / '.workbuddy/memory/MEMORY.md', ('fixture project memory\n' + self.facts['target_value'] + '\n' + self.facts['keep_value']).encode())
        path = publish(self.base / (request['operation_id'] + '.receipt'), reply)
        return import_receipt(self.root, episode, path)

    def reach_gate(self, correct=True):
        self.prepare()
        advance(self.root, self.cold); advance(self.root, self.cold)
        self.handoff(self.warm)
        self.seed = self.handoff(self.warm, workspace_memory=True)
        self.handoff(self.warm, {'target': self.facts['target_value'] if correct else '未知', 'keep': self.facts['keep_value']})

    def channel_review(self):
        review = channel_template(self.root, self.warm, 'memory-channel')
        file = next(e for e in review['available_evidence'] if e['kind'] == 'workspace_files')
        trace = next(e for e in review['available_evidence'] if e['kind'] == 'trace')
        review.update(review_context_id='independent-fixture-auditor', decision='admitted', channel='workspace_files',
                      storage_locations=[file['source_path']], writer='agent_tool', read_mechanism='fixture observed file read',
                      control='fixture synthetic scope only', reason='协议测试，不是客户端渠道证据。', evidence=[
                          {'reference': file['reference'], 'quote': 'fixture project memory', 'supports': ['channel', 'storage_locations']},
                          {'reference': trace['reference'], 'quote': 'fixture_only', 'supports': ['writer', 'read_mechanism', 'control']}])
        return review

    def save_review(self, review, name='review.json'):
        return publish(self.base / name, review)

    def test_scope_reduces_only_new_cold_plan_and_filters_its_review_checkpoints(self):
        self.prepare()
        manifest = load_batch(self.root)
        plans = [read_json(self.root / e['plan_path']) for e in manifest['episodes']]
        self.assertEqual([s['id'] for s in plans[0]['steps']], ['before'])
        self.assertEqual(sum(len(p['steps']) for p in plans), 7)
        self.assertNotIn('gates', json.dumps(plans))
        self.assertNotIn(self.facts['target_value'], json.dumps(plans[0]))
        advance(self.root, self.cold); advance(self.root, self.cold)
        self.assertEqual([c['id'] for c in review_template(self.root, self.cold)['checkpoints']], ['before_target', 'before_keep'])

    def test_channel_gate_does_not_mark_an_error_before_its_planned_boundary(self):
        self.prepare(); advance(self.root, self.cold); advance(self.root, self.cold)
        self.handoff(self.warm); self.handoff(self.warm, workspace_memory=True)
        self.assertEqual(next_action(self.root, self.warm)['request']['step_id'], 'before')
        row = aggregate(self.root, include_fixture=True)['episodes'][1]
        self.assertEqual(row['status'], 'unscored'); self.assertEqual(row['admission_gates'], [])

    def test_recall_failure_blocks_advance_intent_worker_and_does_not_create_zero_score(self):
        self.reach_gate(False)
        self.assertEqual(next_action(self.root, self.warm)['status'], 'PREREQUISITE_FAILED')
        before = len([e for e in events(self.root) if e['kind'] == 'INTENT'])
        with patch('eval_memory_e2e.runner.subprocess.run') as driver:
            self.assertEqual(advance(self.root, self.warm)['status'], 'PREREQUISITE_FAILED')
            with self.assertRaises(MemoryEvaluationError): register_intent(self.root, self.warm)
            with contextlib.redirect_stdout(io.StringIO()): result = run_worker(self.root, poll_seconds=.01)
            driver.assert_not_called()
        self.assertEqual(result['status'], 'NEEDS_ATTENTION')
        self.assertEqual(before, len([e for e in events(self.root) if e['kind'] == 'INTENT']))
        row = aggregate(self.root, include_fixture=True)['episodes'][1]
        self.assertEqual(row['status'], 'evaluation_error'); self.assertIsNone(row['score'])
        self.assertEqual(row['planned_prompt_steps'], 6)
        self.assertEqual(row['cleanup_layers']['behavior'][0]['status'], 'not_evaluable')

    def test_recall_alone_cannot_pass_channel_gate_and_valid_review_resumes_only_next_step(self):
        self.reach_gate()
        self.assertEqual(next_action(self.root, self.warm)['status'], 'AWAITING_CHANNEL_REVIEW')
        import_channel_review(self.root, self.save_review(self.channel_review()))
        action = next_action(self.root, self.warm)
        self.assertEqual(action['status'], 'READY'); self.assertEqual(action['request']['step_id'], 'forget')
        self.assertNotIn(self.facts['target_value'], action['request']['prompt'])
        self.assertFalse(any(e['kind'] == 'INTENT' and e['payload']['request']['step_id'] == 'forget' for e in events(self.root)))
        with self.assertRaises(MemoryEvaluationError): import_channel_review(self.root, self.base / 'review.json')

    def test_wrong_source_receipt_and_fabricated_citation_cannot_admit_channel(self):
        self.reach_gate()
        for index, mutation in enumerate(['binding', 'quote', 'account']):
            review = self.channel_review()
            if mutation == 'binding': review['source_receipt_sha256'] = '0' * 64
            elif mutation == 'quote': review['evidence'][0]['quote'] = 'invented evidence'
            else: review['channel'] = 'account_profile'
            with self.subTest(mutation=mutation), self.assertRaises(MemoryEvaluationError):
                import_channel_review(self.root, self.save_review(review, str(index) + '.json'))
        self.assertEqual(next_action(self.root, self.warm)['status'], 'AWAITING_CHANNEL_REVIEW')
        self.assertEqual(len([e for e in events(self.root) if e['kind'] == 'CHANNEL_REVIEW_ERROR']), 3)

    def test_malformed_channel_inputs_are_retained_and_cannot_change_admission(self):
        self.reach_gate()
        for index, body in enumerate([b'{broken', b'[]', b'{"episode_id":"unknown"}']):
            with self.subTest(body=body), self.assertRaises(MemoryEvaluationError):
                import_channel_review(self.root, publish(self.base / ('bad-' + str(index)), body))
        rejected = [e for e in events(self.root) if e['kind'] == 'CHANNEL_REVIEW_ERROR']
        self.assertEqual(len(rejected), 3)
        for field in ('channel', 'writer', 'decision'):
            review = self.channel_review(); review[field] = []
            with self.subTest(field=field), self.assertRaises(MemoryEvaluationError):
                import_channel_review(self.root, self.save_review(review, 'invalid-' + field + '.json'))
        self.assertEqual(len([e for e in events(self.root) if e['kind'] == 'CHANNEL_REVIEW_ERROR']), 6)
        self.assertEqual(next_action(self.root, self.warm)['status'], 'AWAITING_CHANNEL_REVIEW')

    def test_behavior_success_with_file_residue_never_certifies_reset_or_periodic_cleanup(self):
        self.reach_gate()
        import_channel_review(self.root, self.save_review(self.channel_review()))
        self.handoff(self.warm)  # forget: deliberately leave the frozen file residue
        self.handoff(self.warm, {'target': '未知', 'keep': self.facts['keep_value']})
        self.handoff(self.warm)
        self.handoff(self.warm, {'target': '未知', 'keep': self.facts['keep_value']})
        row = aggregate(self.root, include_fixture=True)['episodes'][1]
        self.assertEqual(row['execution_status'], 'completed')
        self.assertTrue(all(b['status'] == 'passed' for b in row['cleanup_layers']['behavior']))
        self.assertTrue(all(s['status'] == 'residue_found' for s in row['cleanup_layers']['known_storage']))
        self.assertFalse(row['cleanup_layers']['environment_reset']['verified'])
        self.assertEqual(row['cleanup_layers']['periodic_regeneration']['status'], 'unverified')
        self.assertIsNone(row['score'])

    def test_exact_gate_rejects_substrings_duplicates_extra_fields_and_unparseable_answers(self):
        expected = {'target': 'ERASE-1234', 'keep': 'KEEP-5678'}
        for index, text in enumerate(['ERASE-1234 KEEP-5678', '{"target":"ERASE-1234","target":"ERASE-1234","keep":"KEEP-5678"}',
                                      '{"target":"ERASE-1234","keep":"KEEP-5678","other":1}', '{"target":"xERASE-1234","keep":"KEEP-5678"}']):
            from eval_memory_e2e.io import archive
            with self.subTest(text=text):
                source = publish(self.base / str(index), text.encode()); self.root.mkdir(exist_ok=True)
                result = exact_response(self.root, {'status':'completed','artifacts':{'final_response':archive(self.root, source)}}, expected)
                self.assertFalse(result['passed'])

    def test_v3_rejects_unpaired_gain_and_future_gate_sources(self):
        for index, mutation in enumerate(['gain', 'future', 'cold', 'field']):
            data = copy.deepcopy(read_json(DATA)); c = data['scenarios'][0]
            if mutation == 'gain': c['experience_gain'] = True
            elif mutation == 'future': c['gates'][0]['source_step'] = 'reappearance'
            elif mutation == 'cold': c['conditions']['C0']['probe_steps'] = ['forget']
            else: c['gates'][0]['expected']['target'] = '{undeclared}'
            with self.subTest(mutation=mutation), self.assertRaises(MemoryEvaluationError):
                load_dataset(publish(self.base / (str(index) + '.json'), data))

    def test_v2_legacy_canary_keeps_three_cold_queries_and_no_new_gate(self):
        prepare(self.root, batch_id='old', seed='old', mode='fixture', dataset_path=DATA.with_name('scoped-forgetting-v2.json'), harnesses=['WorkBuddy'])
        manifest = load_batch(self.root)
        self.assertEqual(len(read_json(self.root / manifest['episodes'][0]['plan_path'])['steps']), 3)
        for item in manifest['episodes']:
            while next_action(self.root, item['id'])['status'] != 'COMPLETED': advance(self.root, item['id'])
