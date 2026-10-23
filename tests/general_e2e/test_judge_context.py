import importlib.util,json,pathlib,sys,tempfile,unittest
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

if __name__=='__main__':unittest.main()
