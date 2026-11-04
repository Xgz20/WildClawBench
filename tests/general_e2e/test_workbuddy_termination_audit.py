import importlib.util,json,tempfile,unittest
from pathlib import Path

SCRIPT=Path(__file__).resolve().parents[2]/'tools/e2e-build/audit_workbuddy_termination.py'
spec=importlib.util.spec_from_file_location('workbuddy_termination_readonly_audit',SCRIPT)
AUDIT=importlib.util.module_from_spec(spec);spec.loader.exec_module(AUDIT)

class NativeTerminationAuditTests(unittest.TestCase):
    def fixture(self,root,*,finish='',wrong_trace=False):
        identity={'conversationRequestId':'request-1','messageId':'message-2','traceId':'trace-1'}
        content=[{'type':'output_text','text':'未完成的正文标题：'}]
        binding={'request_id':'request-1','conversation_id':'session-1','runtime_snapshot':{'request':{
            'state':'completed','assistantMessage':{'content':content}}}}
        sdk={'id':'sdk-message-2','type':'message','role':'assistant','sessionId':'session-1','providerData':identity,'content':content}
        fields={'trace_id':'other' if wrong_trace else 'trace-1','conversation_request_id':'request-1',
            'message_id':'message-2','finish_reason':finish,'prompt_tokens':'0','completion_tokens':'0'}
        for name,value in [('binding.json',binding),('session.jsonl',sdk)]:
            (root/name).write_text(json.dumps(value)+'\n')
        (root/'native.log').write_text('[Info] [SseMonitor#same-prefix] qua.end: '+json.dumps(fields)+'\n')
        return root/'binding.json',root/'session.jsonl',root/'native.log'
    def test_blank_finish_with_native_completed_is_diagnostic_and_does_not_modify_scores(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths=self.fixture(Path(tmp));before=[p.read_bytes() for p in paths]
            result=AUDIT.audit(*paths)
            self.assertEqual(result['warnings'],['missing_model_finish_reason','zero_usage_despite_nonempty_text'])
            self.assertFalse(result['candidate_or_score_modified'])
            self.assertFalse(result['root_cause_upstream_protocol_proven'])
            self.assertEqual([p.read_bytes() for p in paths],before)
    def test_matching_prefix_without_exact_trace_never_binds_another_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths=self.fixture(Path(tmp),wrong_trace=True)
            with self.assertRaisesRegex(ValueError,'NATIVE_TERMINAL_MODEL_MESSAGE_MISSING'):AUDIT.audit(*paths)
    def test_native_api_text_and_sdk_output_text_match_by_message_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths=self.fixture(Path(tmp));data=json.loads(paths[0].read_text())
            data['runtime_snapshot']['request']['assistantMessage']['content'][0].update(type='text',messageId='sdk-message-2')
            paths[0].write_text(json.dumps(data))
            self.assertTrue(AUDIT.audit(*paths)['original_raw_and_runtime_output_equal'])
    def test_raw_and_native_output_disagreement_is_not_hidden(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths=self.fixture(Path(tmp));data=json.loads(paths[0].read_text())
            data['runtime_snapshot']['request']['assistantMessage']['content'][0]['text']='different'
            paths[0].write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'NATIVE_TERMINATION_TEXT_MISMATCH'):AUDIT.audit(*paths)
