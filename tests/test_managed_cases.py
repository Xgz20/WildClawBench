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
