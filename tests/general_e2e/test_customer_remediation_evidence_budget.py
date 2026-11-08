from copy import deepcopy
from pathlib import Path
import ast
import hashlib
import importlib.util
import json
import tempfile
import unittest

from eval_general_e2e.datasets.bundle import _strip_codeblock
from tests.general_e2e.frozen_sources import parse_frozen_task_source
from tests.general_e2e.test_local_scoring_runtime import RUNTIME,REPO_ROOT

B=RUNTIME.work_order_evidence_budget
path=REPO_ROOT/'tools/report/skills/general-e2e/orchestrate-general-e2e/scripts/communication_evidence_failure.py'
spec=importlib.util.spec_from_file_location('customer_evidence_failure_test',path)
FAILURE=importlib.util.module_from_spec(spec);spec.loader.exec_module(FAILURE)

class EvaluatorEvidenceError(Exception):pass

class CustomerEvidenceBudgetTests(unittest.TestCase):
    def setUp(self):
        _,sections,_=parse_frozen_task_source(next((REPO_ROOT/'tasks/general_e2e').rglob(B.CUSTOMER_TASK+'.md')))
        self.source=_strip_codeblock(sections['Automated Checks'])
        self.contract={'task_id':B.CUSTOMER_TASK,'automated_checks':self.source}
        self.manifest={'identity':{'task_id':B.CUSTOMER_TASK},'digests':{'contract_sha256':B.CUSTOMER_CONTRACT},
                       'runtime':{'work_order_evidence_budget_profile':B.marker(self.contract,B.CUSTOMER_CONTRACT)}}

    def writer(self,source):
        functions=[n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name in {'_j','_within','_write_evidence'}]
        constants=[n for n in ast.parse(source).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in {'MAX_TOTAL_TEXT','MAX_PART_TEXT'} for t in n.targets)]
        namespace={'Path':Path,'json':json,'EvaluatorEvidenceError':EvaluatorEvidenceError}
        exec(compile(ast.fix_missing_locations(ast.Module(body=constants+functions,type_ignores=[])),'<synthetic-customer-evidence>','exec'),namespace)
        return namespace['_write_evidence']

    def fixed(self):return B.effective_source(self.manifest,self.source,self.source,None)[0]

    def test_exact_source_guard_only_and_complete_original_record_roundtrip(self):
        self.assertEqual(hashlib.sha256(self.source.encode()).hexdigest(),B.CUSTOMER_SOURCE)
        original=self.writer(self.source);fixed=self.writer(self.fixed())
        self.assertEqual(self.fixed(),self.source.replace('MAX_TOTAL_TEXT = 74000','MAX_TOTAL_TEXT = 16777216').replace('    if total > MAX_TOTAL_TEXT:','    if sum(len(line.encode("utf-8")) for line in lines) > MAX_TOTAL_TEXT:'))
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);old=root/'old';new=root/'new';old.mkdir();new.mkdir()
            small=[['record',i,'small'] for i in range(4)]
            self.assertEqual(original(old,small),fixed(new,small))
            self.assertEqual({p.name:p.read_bytes() for p in (old/'evaluator_evidence').iterdir()},
                             {p.name:p.read_bytes() for p in (new/'evaluator_evidence').iterdir()})
            records=[['record',i,'完整内容'*300] for i in range(100)]
            with self.assertRaisesRegex(EvaluatorEvidenceError,'EVALUATOR_EVIDENCE_BUDGET_EXCEEDED'):
                original(old,records)
            result=fixed(new,records)
            recovered=[json.loads(line) for p in sorted((new/'evaluator_evidence').iterdir()) for line in p.read_text().splitlines()]
            self.assertEqual(records,recovered);self.assertFalse(result['candidate_truncated'])
            self.assertEqual(result['evidence_chars'],sum(len(json.dumps(r,ensure_ascii=False,separators=(',',':'),sort_keys=True)+'\n') for r in records))
            with self.assertRaisesRegex(EvaluatorEvidenceError,'single evidence record exceeds'):
                fixed(new,[['record','x'*18000]])
            with self.assertRaisesRegex(EvaluatorEvidenceError,'EVALUATOR_EVIDENCE_BUDGET_EXCEEDED'):
                fixed(new,[['中'*6000000]])

    def test_retirement_only_matches_bound_original_capacity_failure(self):
        audit={'status':'failed','identity':self.manifest['identity'],'runtime_workspace':{'drifted':False},
               'worker':{'return_code':1,'process_tree_cleanup':{'remaining':False}}}
        worker={'ok':False,'result':None,'error':{'type':'EvaluatorEvidenceError','message':'EVALUATOR_EVIDENCE_BUDGET_EXCEEDED: 161553; no candidate truncation performed'}}
        self.assertTrue(FAILURE.customer_failure(self.manifest,self.contract,audit,worker))
        for edit in [lambda a,w:a['runtime_workspace'].update(drifted=True),lambda a,w:a['worker']['process_tree_cleanup'].update(remaining=True),
                     lambda a,w:w['error'].update(type='RuntimeError'),lambda a,w:w['error'].update(message='EVALUATOR_EVIDENCE_BUDGET_EXCEEDED: 100; no candidate truncation performed')]:
            a=deepcopy(audit);w=deepcopy(worker);edit(a,w)
            self.assertFalse(FAILURE.customer_failure(self.manifest,self.contract,a,w))
        changed={**self.contract,'automated_checks':self.source+'\n'}
        self.assertFalse(FAILURE.customer_failure(self.manifest,changed,audit,worker))

if __name__=='__main__':unittest.main()
