import json
from pathlib import Path
import tempfile
import unittest
from src.managed_cases import contracts as c,bundle as b


def fixture():
    return {'metadata':{'id':'user_case_1','name':'示例','category':'custom','difficulty':'L1','modality':'pure-text','grading_type':'llm_judge','timeout_seconds':300},
            'sections':{'Prompt':'读取 /tmp_workspace/inputs/in.txt，输出 /tmp_workspace/results/out.txt','Unknown Section':'preserve'},
            'assets':[{'role':'input','path':'inputs/in.txt','file':'files/in.txt','sha256':c.sha(b'input')}],
            'outputs':['results/out.txt'],'criteria':[{'key':'correct','weight':1,'description':'结果正确'}]}


class ManagedCasesTests(unittest.TestCase):
    def test_roundtrip_keeps_extension_fields_and_bom(self):
        value=fixture();value['metadata']['extension']={'a':1}
        raw=c.render_markdown(value,'workspace/custom/user_case_1')
        parsed=c.parse_markdown(('\ufeff'+raw.replace('\n','\r\n')).encode())
        self.assertEqual(parsed['metadata']['extension'],{'a':1})
        self.assertEqual(parsed['sections']['Unknown Section'],'preserve')
        self.assertTrue(c.validate(value)['valid'])
    def test_paths_gt_and_templates_fail_closed(self):
        value=fixture();value['sections']['Prompt']+=' /tmp_workspace/gt/answer.txt'
        self.assertFalse(c.validate(value)['valid'])
        for path in ['../x','C:/x','/x','a/CON.txt','a\\b']:
            with self.assertRaises(ValueError):c.safe_path(path)
        with self.assertRaises(ValueError):c.validate_template({'common':'{{env.TOKEN}}'})
        self.assertEqual(c.render_template({'common':'{{task.name}}'},'api',{'task.name':'测试'}),'测试')
    def test_archive_compiles_without_repo_mutation_and_detects_drift(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source.zip'
            receipt=b.write_archive({'dataset_id':'managed-test','cases':[{'document':fixture()}],'scene':{'base_contract':'general'}},{'files/in.txt':b'input'},source)
            compiled,tasks=b.cli_tasks(source,receipt['sha256'],root/'compiled')
            self.assertEqual(len(tasks),1)
            self.assertIn('Criterion 1',tasks[0]['llm_judge_rubric'])
            self.assertFalse((root/'compiled/sources/workspace/custom/user_case_1/exec/gt').exists())
            rows,members,manifest=b.e2e_tasks(source,receipt['sha256'],root/'compiled')
            self.assertEqual(rows[0]['task_id'],'user_case_1')
            self.assertEqual(manifest['dataset_digest'],compiled['dataset_digest'])
            with self.assertRaises(ValueError):b.load(source,'a'*64)


class ManagedScoringTests(unittest.TestCase):
    def test_context_template_override_is_frozen_and_transport_specific(self):
        from src.managed_cases.scoring import context_for
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'data.txt').write_text('candidate')
            task={'task_id':'test','prompt':'ORIGINAL_PROMPT','llm_judge_rubric':'RUBRIC','rubric_criteria':[],
                'managed_scoring':{'source_sha256':'a'*64,'config':{'template':{'common':'OLD'}},'scene':{}}}
            config={'transport':'api','judge_instructions':{'template':{'common':'NEW {{task.prompt}}','api':'API_ONLY'}}}
            value,prompt=context_for(task,root,'trajectory',{},config)
            self.assertIn('NEW ORIGINAL_PROMPT',prompt);self.assertIn('API_ONLY',prompt)
            self.assertNotIn('OLD',prompt);self.assertEqual(value['scoring'],config['judge_instructions'])
            self.assertEqual(task['managed_scoring']['config']['template']['common'],'OLD')
    def test_rules_container_has_no_credentials_socket_or_network(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        from src.managed_cases.scoring import run_rules
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);candidate=root/'candidate';candidate.mkdir();output=root/'rules'
            def run(command,**kwargs):
                if 'rm' in command:return SimpleNamespace(returncode=0,stdout='',stderr='')
                self.assertIn('none',command);self.assertIn('--cap-drop=ALL',command)
                self.assertNotIn('--env',command);self.assertNotIn('--env-file',command)
                self.assertNotIn('docker.sock',' '.join(command));self.assertNotIn('SECRET',' '.join(command))
                (output/'rules.json').write_text('{"overall_score":0}')
                return SimpleNamespace(returncode=0,stdout='',stderr='')
            with patch('src.managed_cases.scoring.subprocess.run',run):
                value=run_rules({'automated_checks':'def grade(**kwargs): return {"overall_score":0}'},candidate,output,{'rule_image_id':'sha256:fixed','timeout_seconds':10})
                self.assertEqual(value,{'overall_score':0})
    def test_invalid_semantic_response_is_not_zero(self):
        from unittest.mock import patch
        from src.managed_cases.scoring import score
        from src.e2e.artifacts import inventory
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'input';source.mkdir();(source/'workspace').mkdir()
            task={'task_id':'t','prompt':'p','grading_type':'llm_judge','rubric_criteria':[{'key':'correct','weight':1,'allowed_scores':[0,1]}],
                  'managed_scoring':{'source_sha256':'a'*64,'config':{},'scene':{}},'llm_judge_rubric':'correct'}
            (source/'task.json').write_text(json.dumps(task));(source/'transcript.jsonl').write_text('trace')
            (source/'manifest.json').write_text(json.dumps({'image':'test','files':inventory(source)}))
            with patch('src.managed_cases.scoring.api_judge',return_value='{"scores":{"wrong":1}}'):
                with self.assertRaisesRegex(ValueError,'KEYS_INVALID'):score(source,root/'out',{'transport':'api'})
            self.assertFalse((root/'out/score.json').exists())


class ManagedIntegrityTests(unittest.TestCase):
    def test_duplicate_yaml_and_forged_cache_are_rejected(self):
        with self.assertRaisesRegex(ValueError,'重复'):
            c.parse_markdown('---\nid: a\nid: b\n---\n## Prompt\na')
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source.zip'
            receipt=b.write_archive({'dataset_id':'managed-cache','cases':[{'document':fixture()}],'scene':{'base_contract':'general'}},{'files/in.txt':b'input'},source)
            b.compile_source(source,receipt['sha256'],root/'compiled')
            p=root/'compiled/source-receipt.json';value=json.loads(p.read_text());value['compiled_files']={};p.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError,'缓存清单'):
                b.compile_source(source,receipt['sha256'],root/'compiled')
    def test_capability_and_material_collision_fail_before_dispatch(self):
        with self.assertRaisesRegex(ValueError,'CAPABILITY_MISSING'):
            c.validate_capabilities({'required_capabilities':['browser_interaction']},'api')
        value=fixture();value['assets'].append({**value['assets'][0],'role':'gt','path':'expected.txt'})
        self.assertFalse(c.validate(value)['valid'])


class ManagedTransportTests(unittest.TestCase):
    def test_all_transports_receive_exact_instructions_and_verify_original_scores(self):
        from unittest.mock import patch
        from src.managed_cases import scoring
        from src.e2e.artifacts import inventory
        for transport,target in [('api','src.managed_cases.scoring.api_judge'),('docker-cli','src.cli_scoring.docker_judge'),('agentcube-desktop','src.cli_scoring.desktop_judge')]:
            with self.subTest(transport=transport),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);source=root/'input';source.mkdir();(source/'workspace').mkdir();(source/'workspace/out.txt').write_text('candidate')
                task={'task_id':'t','prompt':'p','grading_type':'llm_judge','grading_weights':{'automated':0,'llm_judge':1},
                    'rubric_criteria':[{'key':'correct','weight':1,'allowed_scores':[0,1]}],
                    'managed_scoring':{'source_sha256':'a'*64,'config':{'template':{'common':'CASE'}},'scene':{'base_contract':'general'}},'llm_judge_rubric':'correct'}
                (source/'task.json').write_text(json.dumps(task));(source/'transcript.jsonl').write_text('original trace')
                (source/'manifest.json').write_text(json.dumps({'image':'test','files':inventory(source)}))
                config={'transport':transport,'judge_instructions':{'template':{'common':'NEW {{task.prompt}}',transport:'CHANNEL'}}}
                def judge(context,*args):
                    text=json.dumps(context) if isinstance(context,dict) else (context/'PROMPT.md').read_text()
                    self.assertIn('NEW p',text);self.assertIn('CHANNEL',text)
                    self.assertNotIn('CASE',text)
                    return '{"scores":{"correct":1},"notes":"verified"}'
                with patch(target,judge):self.assertEqual(scoring.score(source,root/'grade',config)['overall_score'],1)
                self.assertEqual(scoring.verify_score(source,root/'grade')['status'],'PASS')
                response=root/'grade/judge/judge-response.json';response.write_text('{"scores":{"correct":0}}')
                with self.assertRaisesRegex(ValueError,'TOTAL_INVALID'):scoring.verify_score(source,root/'grade')


class ManagedSealedBatchTests(unittest.TestCase):
    def test_sealed_execution_adapts_private_gt_and_resumes_without_rescoring(self):
        from unittest.mock import patch
        from src.managed_cases.scoring import score_batch
        from src.e2e.common import atomic_json
        from src.e2e.engine import run_batch
        from src.e2e.store import BatchStore
        from src.e2e.artifacts import inventory
        from tests.e2e.test_scheduler import SchedulerTests
        harness=SchedulerTests();harness.setUp();self.addCleanup(harness.tearDown)
        root=Path(harness.temp.name)/'managed';root.mkdir()
        manifest=harness.manifest;manifest['plan'].update(batch_id='managed',selection={'case_source':{'path':'source.zip','sha256':'a'*64}})
        manifest['tasks']=manifest['tasks'][:1];manifest['units'][0].update(task_ids=['t0'],scene='general')
        task=manifest['tasks'][0];task.update(input_root='inputs/t0',scene='general',dataset={'id':'managed','digest':'a'*64})
        (root/'inputs/t0/execution/workspace').mkdir(parents=True)
        private=root/'inputs/t0/private-scoring/gt';private.mkdir(parents=True);(private/'secret.txt').write_text('PRIVATE_GT')
        body={'metadata':{'id':'t0','name':'sealed','category':'test','grading_type':'automated','managed_scoring':{'source_sha256':'a'*64,'config':{},'scene':{'base_contract':'general'}}},
            'sections':{'Prompt':'task 0','Automated Checks':'def grade(**kwargs): return {"overall_score":1}'}}
        (root/'inputs/t0/task.md').write_text(c.render_markdown(body,'inputs/t0'))
        task['materials']={'execution':{'entries':[]},'private_scoring':{'entries':inventory(private)}}
        atomic_json(root/'batch.json',manifest)
        items=[{'key':'unit/run-0001/t0','unit_id':'unit','task_id':'t0','run_index':1,'attempt_id':'exec-t0','execution_root':'units/unit/t0/executions/exec-t0'}]
        BatchStore(root).initialize(manifest,items)
        run_batch(root,harness.config,driver_factory=harness.factory)
        calls=[]
        def rules(task,candidate,output,config):
            self.assertEqual((candidate/'gt/secret.txt').read_text(),'PRIVATE_GT');calls.append(1)
            output.mkdir();(output/'rules.json').write_text('{"overall_score":1}')
            return {'overall_score':1}
        with patch('src.managed_cases.scoring.run_rules',rules):
            result=score_batch(root,root/'scoring',{'transport':'api','concurrency':2})
            self.assertEqual(result['summary']['valid'],1,result)
            again=score_batch(root,root/'scoring',{'transport':'api','concurrency':2})
            self.assertEqual(result,again);self.assertEqual(len(calls),1)
        entry=result['executions'][0]
        self.assertTrue(Path(entry['score_path']).is_file());self.assertEqual(entry['verification']['status'],'PASS')
        self.assertFalse((root/items[0]['execution_root']/'staging/collect/workspace/gt').exists())
        from src.e2e.general_reports import build_report
        from src.e2e.common import file_sha256
        source={'id':'1','unit_id':'unit','run_index':1,'result_file':str(root/'scoring/result.json'),'result_sha256':file_sha256(root/'scoring/result.json')}
        report_root=root/'report';report_root.mkdir()
        report=build_report({'id':'synthetic','name':'Managed report','sources':[source]},report_root)
        self.assertEqual(report['units'][0]['score']['mean_score'],1)


import os
@unittest.skipUnless(os.environ.get('WCB_MANAGED_TEST_IMAGE'),'requires an explicit local scoring image')
class ManagedContainerAcceptance(unittest.TestCase):
    def temporary(self):
        directory=Path(__file__).resolve().parents[1]/'.agents/test-managed-runtime';directory.mkdir(parents=True,exist_ok=True)
        return tempfile.TemporaryDirectory(dir=directory)
    def config(self):return {'rule_image_id':os.environ['WCB_MANAGED_TEST_IMAGE'],'docker_context':os.environ.get('WCB_MANAGED_TEST_CONTEXT','colima'),'timeout_seconds':60,'transport':'api'}
    def test_real_rules_cannot_read_host_credentials_socket_or_other_cases(self):
        from src.managed_cases.scoring import run_rules
        with self.temporary() as folder:
            root=Path(folder);candidate=root/'candidate';candidate.mkdir();(candidate/'gt').mkdir();(candidate/'gt/expected.txt').write_text('GT')
            task={'automated_checks':'''def grade(**kwargs):
    import os,socket
    from pathlib import Path
    assert 'E2E_SCORER_API_KEY' not in os.environ
    assert not Path('/var/run/docker.sock').exists()
    assert not Path('/host-secret').exists()
    assert Path('/tmp_workspace/gt/expected.txt').read_text()=='GT'
    try:
        socket.create_connection(('1.1.1.1',443),timeout=1)
        raise AssertionError('network unexpectedly available')
    except OSError: pass
    return {'isolation':1,'overall_score':1}
'''}
            original=os.environ.get('E2E_SCORER_API_KEY');os.environ['E2E_SCORER_API_KEY']='synthetic-host-secret'
            try:self.assertEqual(run_rules(task,candidate,root/'rules',self.config())['isolation'],1)
            finally:
                if original is None:os.environ.pop('E2E_SCORER_API_KEY',None)
                else:os.environ['E2E_SCORER_API_KEY']=original
    def test_real_office_and_web_media_evidence(self):
        import subprocess
        from src.managed_cases.scoring import media_evidence
        with self.temporary() as folder:
            root=Path(folder);workspace=root/'candidate';workspace.mkdir()
            (workspace/'index.html').write_text('<!doctype html><html><head><meta charset="utf-8"><title>Synthetic</title></head><body><h1>Rendered evidence</h1><button onclick="this.innerText=\'clicked\'">Click</button></body></html>')
            script='from docx import Document; p=Document();p.add_paragraph("Office evidence");p.save("/out/test.docx")'
            config=self.config()
            subprocess.run(['docker','--context',config['docker_context'],'run','--rm','--network','none','--mount',f'type=bind,src={workspace},dst=/out','--entrypoint','/opt/scoring-runtime/bin/python',config['rule_image_id'],'-c',script],check=True,capture_output=True)
            rows=media_evidence(workspace,root/'evidence',config,'web')
            office=next(row for row in rows if row['path']=='test.docx');web=next(row for row in rows if row['path']=='index.html')
            self.assertEqual(len(office['images']),1);self.assertIn('Office evidence',office['text'])
            self.assertEqual(len(web['images']),2);self.assertEqual(web['browser']['viewports'][1]['width'],390)
            self.assertIn('Rendered evidence',web['browser']['viewports'][0]['text'])


class ManagedAPIWireTests(unittest.TestCase):
    def test_custom_instruction_is_in_actual_api_payload(self):
        from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
        import threading
        from unittest.mock import patch
        from src.managed_cases.scoring import api_judge
        seen=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                seen.append((self.path,json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
                result={'choices':[{'message':{'content':'{"scores":{"ok":1}}'}}]}
                self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(json.dumps(result).encode())
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with patch.dict(os.environ,{'E2E_SCORER_API_KEY':'synthetic-local-test'}):
                value=api_judge({'fixed_instructions':'FIXED','custom_instructions':'CUSTOM_IN_WIRE','supplement':'EXTRA','evidence':[]},
                    {'base_url':f'http://127.0.0.1:{server.server_port}/v1','transport':'api','model':'synthetic','timeout_seconds':5})
            self.assertIn('"ok":1',value)
            self.assertEqual(seen[0][0],'/v1/chat/completions')
            self.assertIn('CUSTOM_IN_WIRE',seen[0][1]['messages'][0]['content'])
            self.assertIn('EXTRA',seen[0][1]['messages'][0]['content'])
        finally:server.shutdown();server.server_close()
