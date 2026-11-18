"""Independent admission checks for retained Loomy provider failures; no model calls."""
import base64
import copy
import json
import unittest

from tests.general_e2e.test_general_scoring_orchestration import SCORE_RUNTIME as SCORE


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, separators=(',', ':')) + '\n').encode()


class LoomyFailureEvidenceTests(unittest.TestCase):
    def fixture(self, mutate=None):
        module = SCORE.failure_evidence
        prompt = '仅处理本题。'
        identity = {'batch_id': 'batch', 'unit_id': 'loomy', 'task_id': 'arbitrary-task', 'attempt_id': 'attempt'}
        error = {'code': 'LOOMY_NATIVE_HTTP_ERROR', 'message': 'Native primary model HTTP 502 after provider retries'}
        runtime = {'ppid': 99, 'executable': '/app/opencode', 'binary_sha256': 'a' * 64,
                   'database': '/data/opencode.db', 'database_owned': True, 'health_version': '1.14.22'}
        api_error = {'name': 'AI_APICallError', 'url': 'https://loomyad.xunfei.cn/api/v1/chat/completions',
                     'statusCode': 502, 'requestBodyValues': {'model': 'spark-x2.6',
                     'messages': [{'role': 'user', 'content': [{'type': 'text', 'text': prompt}]}]}}
        line = 'ERROR 1970-01-01T00:00:02 +1ms service=llm providerID=imodel modelID=spark-x2.6 session.id=ses_root small=false agent=loomy mode=primary error=' + json.dumps({'error': api_error}, ensure_ascii=False)
        def row(mid, data):
            return {'id': mid, 'session_id': 'ses_root', 'data': json.dumps(data, ensure_ascii=False)}
        native = {'profile': 'loomy-opencode-sqlite/v1', 'snapshot': {'method': 'readonly-source-sqlite-online-backup', 'quick_check': 'ok'},
                  'sessions': [{'id': 'ses_root', 'parent_id': None, 'directory': '/workspace'}],
                  'messages': [row('user', {'role': 'user', 'model': {'providerID': 'imodel', 'modelID': 'spark-x2.6', 'variant': 'high'}}),
                               row('empty', {'role': 'assistant', 'providerID': 'imodel', 'modelID': 'spark-x2.6', 'variant': 'high', 'time': {'created': 1000, 'completed': 3000}})],
                  'parts': [dict(row('prompt', {'type': 'text', 'text': prompt}), message_id='user')]}
        proof = {'profile': 'loomy-native-primary-http-failure/v1', 'identity': identity,
                 'prompt_sha256': module.sha(prompt.encode()), 'session_id': 'ses_root', 'final_message_id': 'empty',
                 'observed_at': '1970-01-01T00:00:04Z',
                 'original_runtime': runtime, 'observed_runtime': copy.deepcopy(runtime), 'runtime_status': {},
                 'source_lines': []}
        if mutate:
            line = mutate(proof, native, line)
        raw = line.encode()
        proof['source_lines'] = [{'bytes_base64': base64.b64encode(raw).decode(), 'sha256': module.sha(raw), 'size': len(raw), 'line_number': 1}]
        config = encoded({'process': {'pid': 99}})
        proof_bytes = encoded(proof)
        binding = {'path': 'native-http-failure.json', 'sha256': module.sha(proof_bytes), 'size': len(proof_bytes)}
        journal = {'identity': identity, 'phase': 'FAILED', 'dispatch_attempt_count': 1, 'send_status': 'sent',
                   'input_locks': {'config': module.sha(config)}, 'native_error': error, 'native_http_failure': binding}
        state = {'identity': identity, 'execution': {'error': error}, 'extensions': {'loomy': {
            'native_http_failure': binding, 'final_message_id': 'empty', 'runtime': runtime}}}
        execution = {'identity': identity, 'execution': {'error': error}, 'prompt': {'sha256': module.sha(prompt.encode())},
                     'session': {'session_id': 'ses_root', 'cwd': '/workspace'}}
        files = {'PROMPT.md': prompt.encode(), 'native-http-failure.json': proof_bytes,
                 'native-scoped-snapshot.json': encoded(native), 'dispatch-journal.json': encoded(journal), 'frozen-run-config.json': config}
        files['original-evidence-manifest.json'] = encoded({'identity': identity, 'artifacts': [
            {'path': 'evidence/trace/raw/' + name, 'sha256': module.sha(files[name]), 'size': len(files[name])}
            for name in ('native-http-failure.json', 'native-scoped-snapshot.json', 'dispatch-journal.json', 'frozen-run-config.json')]})
        return execution, state, files

    def test_validates_primary_failure_without_task_allowlist_or_numeric_score(self):
        SCORE.failure_evidence._validate_loomy_sources(*self.fixture())

    def length_fixture(self, mutate=None):
        module = SCORE.failure_evidence
        execution, state, old = self.fixture()
        native = json.loads(old['native-scoped-snapshot.json'])
        final = json.loads(native['messages'][-1]['data']); final['finish'] = 'length'
        native['messages'][-1]['data'] = json.dumps(final)
        runtime = copy.deepcopy(state['extensions']['loomy']['runtime']); runtime['endpoint'] = 'http://127.0.0.1:5072'
        error = {'code':'LOOMY_NATIVE_OUTPUT_LENGTH_LIMIT','message':'Native primary model ended with finish=length'}
        proof = {'profile':'loomy-native-output-length-failure/v1','identity':execution['identity'],
                 'prompt_sha256':execution['prompt']['sha256'],'session_id':'ses_root','final_message_id':'empty',
                 'runtime':runtime,'runtime_status':{},'runtime_status_scope':{'directory':'/workspace','endpoint':'http://127.0.0.1:5072/session/status?directory=%2Fworkspace'},
                 'observed_at':'1970-01-01T00:00:04Z'}
        if mutate: mutate(proof, native)
        config = encoded({'process':{'pid':99},'runtime':runtime})
        proof_bytes = encoded(proof); binding = {'path':'native-length-failure.json','sha256':module.sha(proof_bytes),'size':len(proof_bytes)}
        journal = {'identity':execution['identity'],'phase':'FAILED','dispatch_attempt_count':1,'send_status':'sent',
                   'input_locks':{'config':module.sha(config)},'native_error':error,'native_length_failure':binding,
                   'runtime_binding':runtime,'final_message_id':'empty'}
        execution['execution']['error'] = error; state['execution']['error'] = error
        state['extensions']['loomy'] = {'native_length_failure':binding,'final_message_id':'empty','runtime':runtime}
        files = {'PROMPT.md':old['PROMPT.md'],'native-length-failure.json':proof_bytes,'native-scoped-snapshot.json':encoded(native),
                 'dispatch-journal.json':encoded(journal),'frozen-run-config.json':config}
        files['original-evidence-manifest.json'] = encoded({'identity':execution['identity'],'artifacts':[
            {'path':'evidence/trace/raw/'+name,'sha256':module.sha(value),'size':len(value)} for name,value in files.items() if name!='PROMPT.md']})
        return execution, state, files

    def test_validates_completed_length_without_turning_it_into_a_success_or_zero(self):
        SCORE.failure_evidence._validate_loomy_sources(*self.length_fixture())

    def terminal_fixture(self, kind='aborted', mutate=None):
        module=SCORE.failure_evidence
        execution,state,old=self.length_fixture();native=json.loads(old['native-scoped-snapshot.json'])
        final=json.loads(native['messages'][-1]['data'])
        if kind=='aborted':final.pop('finish');final['error']={'name':'MessageAbortedError','data':{'message':'Aborted'}}
        else:final['finish']='other'
        native['messages'][-1]['data']=json.dumps(final)
        before=json.loads(old['frozen-run-config.json'])['runtime'];before['pid']=101
        after=copy.deepcopy(before);after['pid']=102;after['endpoint']='http://127.0.0.1:5054'
        assistance={'mode':'automatic','operation_count':None if kind=='aborted' else 0,'semantic_intervention_count':None if kind=='aborted' else 0}
        questions=[]
        if kind=='aborted':
            data={'type':'tool','tool':'question','callID':'q_call','state':{'status':'error','input':{'questions':[]},'error':'Tool execution aborted','metadata':{'interrupted':True},'time':{'start':1000,'end':2999}}}
            row={'id':'q_part','session_id':'ses_root','message_id':'empty','data':json.dumps(data)};native['parts'].append(row)
            questions=[{'part_id':'q_part','message_id':'empty','session_id':'ses_root','call_id':'q_call','native_part_data_sha256':module.sha(row['data'].encode()),'started_at':1000,'finished_at':2999,'outcome':'aborted-without-answer','answer_observed':False,'actor':'unknown'}]
        error={'code':'LOOMY_NATIVE_ABORTED','message':'Native primary session ended with MessageAbortedError'} if kind=='aborted' else {'code':'LOOMY_NATIVE_OTHER_FINISH','message':'Native primary model ended with finish=other'}
        proof={'profile':'loomy-native-terminal-failure/v1','kind':kind,'identity':execution['identity'],'prompt_sha256':execution['prompt']['sha256'],'session_id':'ses_root','final_message_id':'empty','original_runtime':before,'observed_runtime':after,'runtime_status':{},'runtime_status_scope':{'directory':'/workspace','endpoint':'http://127.0.0.1:5054/session/status?directory=%2Fworkspace'},'observed_at':'1970-01-01T00:00:04Z','question_terminations':questions,'human_assistance':assistance}
        if mutate:mutate(proof,native)
        config=encoded({'process':{'pid':99},'runtime':before});proof_bytes=encoded(proof)
        binding={'path':'native-terminal-failure.json','sha256':module.sha(proof_bytes),'size':len(proof_bytes)}
        journal={'identity':execution['identity'],'phase':'FAILED','dispatch_attempt_count':1,'send_status':'sent','input_locks':{'config':module.sha(config)},'native_error':error,'native_terminal_failure':binding,'runtime_binding':after,'runtime_rebindings':[{'previous':before,'current':after}],'final_message_id':'empty','human_assistance':assistance}
        state['human_assistance']=assistance;execution['human_assistance']=assistance
        execution['execution']['error']=error;state['execution']['error']=error
        state['extensions']['loomy']={'native_terminal_failure':binding,'final_message_id':'empty','runtime':after}
        files={'PROMPT.md':old['PROMPT.md'],'native-terminal-failure.json':proof_bytes,'native-scoped-snapshot.json':encoded(native),'dispatch-journal.json':encoded(journal),'frozen-run-config.json':config}
        files['original-evidence-manifest.json']=encoded({'identity':execution['identity'],'artifacts':[{'path':'evidence/trace/raw/'+name,'sha256':module.sha(value),'size':len(value)} for name,value in files.items() if name!='PROMPT.md']})
        return execution,state,files

    def test_replays_aborted_unanswered_question_and_other_finish_with_unknown_counts(self):
        for kind in ['aborted','other-finish']:
            with self.subTest(kind=kind):SCORE.failure_evidence._validate_loomy_sources(*self.terminal_fixture(kind))

    def test_terminal_failure_rejects_answers_quota_busy_and_invented_zero(self):
        def answered(proof,native):
            data=json.loads(native['parts'][-1]['data']);data['state']['status']='completed';data['state']['output']='answer';native['parts'][-1]['data']=json.dumps(data)
        def quota(proof,native):
            data=json.loads(native['messages'][-1]['data']);data['error']={'name':'APIError','data':{'statusCode':402}};native['messages'][-1]['data']=json.dumps(data)
        def busy(proof,native):proof['runtime_status']['ses_root']={'type':'busy'}
        def zero(proof,native):proof['human_assistance']={'mode':'automatic','operation_count':0,'semantic_intervention_count':0}
        for change in [answered,quota,busy,zero]:
            with self.subTest(change=change),self.assertRaises(ValueError):SCORE.failure_evidence._validate_loomy_sources(*self.terminal_fixture(mutate=change))

    def test_rejects_length_with_busy_runtime_wrong_finish_or_open_tools(self):
        def busy(proof, native): proof['runtime_status']['ses_root']={'type':'busy'}
        def wrong_finish(proof, native):
            value=json.loads(native['messages'][-1]['data']);value['finish']='stop';native['messages'][-1]['data']=json.dumps(value)
        def pending(proof, native): native['parts'].append({'id':'pending','session_id':'ses_root','message_id':'empty','data':json.dumps({'type':'tool','tool':'bash','state':{'status':'running'}})})
        def model(proof, native):
            value=json.loads(native['messages'][0]['data']);value['model']['variant']='low';native['messages'][0]['data']=json.dumps(value)
        def wrong_scope(proof, native): proof['runtime_status_scope']['endpoint']='http://127.0.0.1:5072/session/status?directory=%2Fother'
        for change in [busy,wrong_finish,pending,model,wrong_scope]:
            with self.subTest(change=change),self.assertRaises(ValueError): SCORE.failure_evidence._validate_loomy_sources(*self.length_fixture(change))

    def test_rejects_other_requests_busy_runtime_and_nonempty_head(self):
        def change_model(proof, native, line):
            data = json.loads(native['messages'][0]['data']); data['model']['variant'] = 'low'
            native['messages'][0]['data'] = json.dumps(data); return line
        def nonempty(proof, native, line):
            native['parts'].append({'id': 'text', 'message_id': 'empty', 'session_id': 'ses_root', 'data': '{"type":"text","text":"answer"}'})
            return line
        def busy(proof, native, line):
            proof['runtime_status']['ses_root'] = {'type': 'busy'}; return line
        def different_binary(proof, native, line):
            proof['observed_runtime']['binary_sha256'] = 'b' * 64; return line
        mutations = [change_model, nonempty, busy, different_binary,
                     lambda p, n, line: line.replace('session.id=ses_root ', 'session.id=ses_other '),
                     lambda p, n, line: line.replace('agent=loomy ', 'agent=memory_extraction '),
                     lambda p, n, line: line.replace('"statusCode": 502', '"statusCode": 402'),
                     lambda p, n, line: line.replace('仅处理本题。', 'another request')]
        for mutate in mutations:
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                SCORE.failure_evidence._validate_loomy_sources(*self.fixture(mutate))


if __name__ == '__main__':
    unittest.main()
