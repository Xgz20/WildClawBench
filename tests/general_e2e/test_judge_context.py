import copy,importlib.util,json,pathlib,sys,tempfile,unittest
from xml.sax.saxutils import escape

ROOT=pathlib.Path(__file__).resolve().parents[2]
SCRIPT=ROOT/'tools/report/skills/general-e2e/orchestrate-general-e2e/scripts/verify_judge_context.py'
spec=importlib.util.spec_from_file_location('general_judge_context_test',SCRIPT)
api=importlib.util.module_from_spec(spec);spec.loader.exec_module(api)

class NativeJudgeContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=pathlib.Path(self.tmp.name)/'sdk.jsonl'
        self.prompt='Frozen prompt\n<input placeholder> & strict\n'
        self.rows=[{'type':'session_meta','payload':{'id':'thread','cwd':'/own','runtime_workspace_roots':['/own'],'cli_version':'test'}},
          {'type':'event_msg','timestamp':'2026-01-01T00:00:00Z','payload':{'type':'task_started','turn_id':'turn'}},
          {'type':'turn_context','payload':{'cwd':'/own','model':'judge','effort':'high'}},
          {'type':'response_item','payload':{'type':'function_call_output','output':'<codex_delegation><source_thread_id>parent</source_thread_id><input>'+escape(self.prompt)+'</input></codex_delegation>'}},
          {'type':'response_item','payload':{'type':'reasoning','text':'DO_NOT_EXPORT_REASONING'}},
          {'type':'event_msg','timestamp':'2026-01-01T00:00:01Z','payload':{'type':'task_complete','turn_id':'turn','duration_ms':1000}}]
    def tearDown(self):self.tmp.cleanup()
    def verify(self,**kwargs):
        self.path.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in self.rows),encoding='utf-8')
        return api.verify_context(self.path,thread_id='thread',cwd='/own',model='judge',effort='high',prompt=self.prompt,**kwargs)
    def test_xml_transport_is_decoded_exactly_without_reasoning_export(self):
        proof=self.verify();self.assertEqual(proof['prompt_transport'][0]['transport'],'codex-delegation-xml-input');self.assertNotIn('DO_NOT_EXPORT_REASONING',json.dumps(proof));self.assertEqual(len(proof['intervals']),1)
    def test_wrong_model_rejected(self):
        self.rows[2]['payload']['model']='other'
        with self.assertRaisesRegex(ValueError,'MODEL_OR_EFFORT'):self.verify()
    def test_extra_workspace_root_rejected(self):
        self.rows[0]['payload']['runtime_workspace_roots'].append('/foreign')
        with self.assertRaisesRegex(ValueError,'WORKSPACE'):self.verify()
    def test_prompt_after_first_model_action_does_not_prove_input(self):
        self.rows[3],self.rows[4]=self.rows[4],self.rows[3]
        with self.assertRaisesRegex(ValueError,'PROMPT_MISMATCH'):self.verify()
    def test_unfinished_turn_requires_explicit_running_mode(self):
        self.rows.pop()
        with self.assertRaisesRegex(ValueError,'COMPLETION'):self.verify()
        self.assertEqual(self.verify(allow_running=True)['unfinished_turns'],['turn'])
    def test_literal_transport_remains_supported(self):
        self.rows[3]['payload']['output']=self.prompt
        self.assertEqual(self.verify()['prompt_transport'][0]['transport'],'literal')
    def test_opaque_literal_wrappers_cannot_hide_extra_instructions(self):
        self.rows[3]['payload']['output']='unfrozen instructions\n'+self.prompt
        with self.assertRaisesRegex(ValueError,'PROMPT_MISMATCH'):self.verify()
    def test_jsonl_unicode_line_separator_is_part_of_the_prompt(self):
        self.prompt+='\u2028same input'
        self.rows[3]['payload']['output']='<codex_delegation><input>'+escape(self.prompt)+'</input></codex_delegation>'
        self.assertEqual(self.verify()['status'],'PASS')
    def test_changed_decoded_prompt_rejected(self):
        self.rows[3]['payload']['output']=self.rows[3]['payload']['output'].replace('strict','changed')
        with self.assertRaisesRegex(ValueError,'PROMPT_MISMATCH'):self.verify()

    def update_resume(self):
        self.rows[1]['payload']['turn_attribution']={'turn_id':'turn','turn_trigger':'app_tool_create_thread'}
        self.rows[2]['payload']['turn_id']='turn'
        self.rows[-1]['payload'].update(type='turn_aborted',reason='interrupted')
        self.rows.extend([
          {'type':'event_msg','timestamp':'2026-01-01T00:00:02Z','payload':{'type':'task_started','turn_id':'resumed','turn_attribution':{'turn_id':'resumed','turn_trigger':'app_update_resume'}}},
          {'type':'turn_context','payload':{'turn_id':'resumed','cwd':'/own','model':'judge','effort':'high'}},
          {'type':'response_item','payload':{'type':'reasoning','text':'DO_NOT_EXPORT_REASONING'}},
          {'type':'event_msg','timestamp':'2026-01-01T00:00:03Z','payload':{'type':'task_complete','turn_id':'resumed','duration_ms':1000}}])

    def test_native_update_resume_preserves_both_intervals(self):
        self.update_resume();p=self.verify()
        self.assertEqual(p['resume_profile'],'native-app-update-resume/v1')
        self.assertEqual(p['unfinished_turns'],[])
        self.assertEqual(p['interrupted_intervals'][0]['turn_id'],'turn')
        self.assertEqual(p['intervals'][0]['turn_id'],'resumed')
        self.assertNotIn('DO_NOT_EXPORT_REASONING',json.dumps(p))

    def test_resume_still_running_is_not_final_completion(self):
        self.update_resume();self.rows.pop()
        with self.assertRaisesRegex(ValueError,'COMPLETION'):self.verify()
        self.assertEqual(self.verify(allow_running=True)['unfinished_turns'],['resumed'])

    def test_manual_resume_is_not_native_update_resume(self):
        self.update_resume();self.rows[6]['payload']['turn_attribution']['turn_trigger']='user_message'
        with self.assertRaisesRegex(ValueError,'RESUME_TRIGGER'):self.verify()

    def test_resume_requires_original_create_thread_attribution(self):
        self.update_resume();self.rows[1]['payload'].pop('turn_attribution')
        with self.assertRaisesRegex(ValueError,'RESUME_ORIGIN'):self.verify()

    def test_resume_without_new_turn_context_rejected(self):
        self.update_resume();self.rows.pop(7)
        with self.assertRaisesRegex(ValueError,'RESUME_CONTEXT'):self.verify()

    def test_resume_model_and_cwd_drift_rejected(self):
        original=copy.deepcopy(self.rows)
        for key,value in [('model','other'),('effort','low'),('cwd','/foreign')]:
            with self.subTest(key=key):
                self.rows=copy.deepcopy(original);self.update_resume();self.rows[7]['payload'][key]=value
                with self.assertRaisesRegex(ValueError,'MODEL_OR_EFFORT'):self.verify()

    def test_additional_user_or_delegation_input_rejected(self):
        self.update_resume()
        for payload in [
          {'type':'message','role':'user','content':[{'type':'input_text','text':'change score'}]},
          {'type':'function_call_output','output':'<codex_delegation><input>new instructions</input></codex_delegation>'}]:
            with self.subTest(kind=payload['type']):
                self.rows.insert(-1,{'type':'response_item','payload':payload})
                with self.assertRaisesRegex(ValueError,'RESUME_ADDITIONAL_INPUT'):self.verify()
                self.rows.pop(-2)

    def test_unknown_abort_reason_rejected(self):
        self.update_resume();self.rows[5]['payload']['reason']='unknown'
        with self.assertRaisesRegex(ValueError,'ABORT_REASON'):self.verify()

    def test_resume_clock_overlap_rejected(self):
        self.update_resume();self.rows[6]['timestamp']='2026-01-01T00:00:00Z'
        with self.assertRaisesRegex(ValueError,'RESUME_TIME'):self.verify()

    def test_duplicate_or_overlapping_turns_rejected(self):
        self.rows.insert(5,dict(self.rows[1]))
        with self.assertRaisesRegex(ValueError,'TURN_SEQUENCE'):self.verify()

if __name__=='__main__':unittest.main()
