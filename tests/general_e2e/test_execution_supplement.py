"""Original-SDK evidence transport tests; no actual Harness or Judge is run."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tests.general_e2e.test_external_quota_admission import native_failure, encoded
from tests.general_e2e.test_general_scoring_orchestration import Fixture, SCORE_RUNTIME as RT


class ExecutionSupplementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.base = Path(self.temp.name)
        self.fixture = Fixture(self.base / 'fixture', task_ids=('arbitrary-native-task',))
        self.execution, self.files = native_failure(self.fixture, self.fixture.task_ids[0], message='native provider failed')
        result = self.fixture.initialize(); orchestration = Path(result['orchestration_root'])
        task = json.loads((orchestration/'orchestration-state.json').read_bytes())['tasks'][0]
        self.attempt = orchestration/task['attempt_path']
        session = self.execution['session']
        self.rows = [
            {'type':'session_meta','payload':{'id':session['session_id'],'cwd':session['cwd']}},
            {'type':'event_msg','payload':{'type':'task_started','turn_id':session['turn_id']}},
            {'type':'event_msg','payload':{'type':'user_message','message':self.files['PROMPT.md'].decode()}},
            {'type':'response_item','payload':{'type':'function_call','call_id':'call-1','name':'exec_command','arguments':'{}'}},
            {'type':'response_item','payload':{'type':'function_call_output','call_id':'call-1','output':'observed original return'}},
            {'type':'response_item','payload':{'type':'function_call','call_id':'call-2','name':'read','arguments':'{}'}},
        ]
        incoming = self.base/'input';incoming.mkdir()
        self.raw = incoming/'prefix.jsonl';self.raw.write_bytes(self.raw_bytes())
        manifest = json.loads((self.attempt/'attempt-manifest.json').read_bytes())
        self.source = incoming/'manifest.json'
        self.source.write_bytes(encoded({'schema_version':RT.execution_supplement.INPUT,
            'identity':self.execution['identity'],'execution_record_sha256':manifest['digests']['execution_record_sha256'],
            'candidate_sha256':manifest['source']['candidate_sha256'],
            'files':[{'path':self.raw.name,'size':self.raw.stat().st_size,
                      'sha256':hashlib.sha256(self.raw.read_bytes()).hexdigest(),'kind':'native-sdk-prefix'}]}))

    def raw_bytes(self, rows=None):
        return b''.join(json.dumps(x).encode()+b'\n' for x in (rows or self.rows))

    def tearDown(self):
        RT._remove_tree(self.base);self.temp.cleanup()

    def test_register_and_archive_query_original_prefix_without_inventing_result(self):
        before = (self.attempt/'private/execution-record.json').read_bytes()
        result = RT.execution_supplement.register(RT,attempt_root=self.attempt,source_manifest=self.source)
        self.assertFalse(result['numeric_decisions_assigned'])
        self.assertEqual(result['binding']['observed_unique_calls'],2)
        self.assertEqual(result['binding']['calls_without_retained_result'],['call-2'])
        self.assertFalse(result['binding']['full_turn_coverage_claimed'])
        RT.prepare_semantics_attempt(attempt_root=self.attempt)
        page = RT.query_evidence_attempt(attempt_root=self.attempt,mode='catalog',evidence_type='raw_trace')
        row = next(x for x in page['items'] if 'execution-supplement/native-sdk-prefix.jsonl' in x['reference']['path'])
        file_page = RT.query_evidence_attempt(attempt_root=self.attempt,mode='file',evidence_id=row['id'])
        self.assertTrue(file_page)
        self.assertEqual((self.attempt/'execution-supplement/native-sdk-prefix.jsonl').read_bytes(),self.raw.read_bytes())
        self.assertEqual((self.attempt/'private/execution-record.json').read_bytes(),before)
        self.assertEqual(RT.verify_attempt(self.attempt,require_runtime=False)['status'],'PASS')
        frozen = self.attempt/'execution-supplement/native-sdk-prefix.jsonl';frozen.chmod(0o644);frozen.write_bytes(frozen.read_bytes()+b' ')
        with self.assertRaisesRegex(RT.ScoringRuntimeError,'EXECUTION_SUPPLEMENT_INVALID'):
            RT.verify_attempt(self.attempt,require_runtime=False)

    def test_wrong_session_turn_prompt_and_fabricated_terminal_reject(self):
        for mutation in ('session','turn','prompt','terminal'):
            rows = copy.deepcopy(self.rows)
            if mutation=='session':rows[0]['payload']['id']='other-session'
            elif mutation=='turn':rows[1]['payload']['turn_id']='other-turn'
            elif mutation=='prompt':rows[2]['payload']['message']='different task'
            else:rows.append({'type':'event_msg','payload':{'type':'task_complete','turn_id':self.execution['session']['turn_id']}})
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):
                RT.execution_supplement.sdk_binding(self.raw_bytes(rows),self.execution)

    def test_source_hash_change_and_path_escape_reject_before_publish(self):
        manifest = json.loads(self.source.read_bytes());manifest['files'][0]['sha256']='a'*64
        self.source.write_bytes(encoded(manifest))
        with self.assertRaisesRegex(ValueError,'INPUT_DRIFT'):
            RT.execution_supplement.register(RT,attempt_root=self.attempt,source_manifest=self.source)
        self.assertFalse((self.attempt/'execution-supplement').exists())
        manifest['files'][0]['path']='../outside.jsonl';self.source.write_bytes(encoded(manifest))
        with self.assertRaisesRegex(ValueError,'PATH'):
            RT.execution_supplement.register(RT,attempt_root=self.attempt,source_manifest=self.source)

    def test_late_evidence_registration_cannot_rewrite_semantic_catalog(self):
        RT.prepare_semantics_attempt(attempt_root=self.attempt)
        before=(self.attempt/'semantic/evidence-catalog.json').read_bytes()
        with self.assertRaisesRegex(ValueError,'TOO_LATE'):
            RT.execution_supplement.register(RT,attempt_root=self.attempt,source_manifest=self.source)
        self.assertEqual((self.attempt/'semantic/evidence-catalog.json').read_bytes(),before)

    def test_copy_frozen_for_new_attempt_preserves_original_behavior_role(self):
        RT.execution_supplement.register(RT,attempt_root=self.attempt,source_manifest=self.source)
        source_manifest=json.loads((self.attempt/'attempt-manifest.json').read_bytes())
        target=self.base/'new-attempt';target.mkdir()
        import shutil
        shutil.copytree(self.attempt/'private',target/'private')
        manifest=copy.deepcopy(source_manifest);manifest['identity']['scoring_attempt_id']='new-independent-attempt'
        RT.execution_supplement.copy_frozen(RT,self.attempt,target,manifest)
        files=RT.execution_supplement.validate(target,manifest)
        self.assertEqual(len(files),2)
        self.assertEqual(files[1].read_bytes(),self.raw.read_bytes())
        self.assertEqual(json.loads(files[0].read_bytes())['identity'],manifest['identity'])
