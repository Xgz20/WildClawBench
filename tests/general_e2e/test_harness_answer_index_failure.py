import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
from tests.general_e2e.test_general_scoring_orchestration import ORCHESTRATOR

FAILURE = ORCHESTRATOR.framework_failure_retirement.harness_answer_index_failure

class HarnessAnswerIndexFailureTests(unittest.TestCase):
    def test_exact_failed_worker_and_negative_scope(self):
        source = 'def f():\n' + FAILURE.GUARD + '\n'
        digest = hashlib.sha256(source.encode()).hexdigest()
        with tempfile.TemporaryDirectory() as directory, patch.object(FAILURE, 'SOURCE', digest):
            root = Path(directory); (root/'worker').mkdir()
            def write(path, value):
                p=root/path;p.write_text(json.dumps(value),encoding='utf-8');return p
            sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
            rt=SimpleNamespace(_read_json=lambda p:json.loads(p.read_text()),_sha256_file=sha)
            expected=source.replace(FAILURE.GUARD,FAILURE.REPLACEMENT)
            request=write('worker/request.json',{'automated_checks':expected})
            correction=write('rule-source-correction.json',{'correction_id':FAILURE.PROFILE,
                'effective_source_sha256':hashlib.sha256(expected.encode()).hexdigest()})
            worker={'ok':False,'result':None,'error':{'type':'KeyError','message':"'event_index'"},'worker':{'pid':123}}
            write('worker/result.json',worker)
            audit={'status':'failed','error':{'code':'RULE_WORKER_FAILED','detail':"'event_index'"},
                'runtime_workspace':{'drifted':False},'worker':{'return_code':1,'timed_out':False,
                'process_tree_cleanup':{'remaining':False},'request_sha256':sha(request),'worker_pid':123},
                'source_correction':{'sha256':sha(correction)}}
            write('rule-audit.json',audit)
            manifest={'dataset':{'id':'general-custom70-v6','digest':'20f9383bd124402703bf106d5d306cf64674cac6f83d1f7daa8e1859c3e03288'},
                'digests':{'contract_sha256':FAILURE.CONTRACT},'evidence_admission':'verified-harness-failure-evidence/v1',
                'runtime':{'interrupted_answer_delivery_profile':{'profile':FAILURE.PROFILE,
                'contract_sha256':FAILURE.CONTRACT,'source_sha256':digest}}}
            contract={'task_id':FAILURE.TASK,'automated_checks':source};task={'phase':'RULES_NEEDS_ATTENTION'}
            self.assertFalse(FAILURE.evidence(rt,root,manifest,contract,task)['numeric_score_assigned'])
            for update in [{'thread':{}},{'score':{}},{'phase':'SCORE_VERIFICATION_PENDING'}]:
                with self.subTest(update=update),self.assertRaises(ValueError):
                    FAILURE.evidence(rt,root,manifest,contract,{**task,**update})
            for key,value in [('type','ValueError'),('message',"'another_key'")]:
                changed=copy.deepcopy(worker);changed['error'][key]=value;write('worker/result.json',changed)
                with self.subTest(key=key),self.assertRaises(ValueError):FAILURE.evidence(rt,root,manifest,contract,task)
            write('worker/result.json',worker)
            write('worker/request.json',{'automated_checks':expected+'\n'})
            with self.assertRaises(ValueError):FAILURE.evidence(rt,root,manifest,contract,task)

if __name__ == '__main__':unittest.main()
