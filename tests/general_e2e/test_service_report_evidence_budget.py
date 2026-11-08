from copy import deepcopy
from pathlib import Path
import ast
import hashlib
import json
import tempfile
import unittest

from eval_general_e2e.datasets.bundle import _strip_codeblock
from tests.general_e2e.frozen_sources import parse_frozen_task_source
from tests.general_e2e.test_local_scoring_runtime import RUNTIME, REPO_ROOT

BUDGET=RUNTIME.work_order_evidence_budget

class EvaluationError(Exception):
    pass

class ServiceReportEvidenceBudgetTests(unittest.TestCase):
    def setUp(self):
        task=next((REPO_ROOT/'tasks/general_e2e').rglob(BUDGET.SERVICE_TASK+'.md'))
        _,sections,_=parse_frozen_task_source(task)
        self.source=_strip_codeblock(sections['Automated Checks'])
        # The custom70 bundle freezes the already-reviewed v2 layout repair.
        # Reproduce that versioned source without changing the legacy fixture.
        layout=RUNTIME.service_report_layout
        layout_manifest={'identity':{'task_id':layout.TASK},'dataset':layout.DATASET,
                         'digests':{'contract_sha256':layout.CONTRACT_SHA},
                         'runtime':{'service_report_layout_profile':layout.marker(
                             {'task_id':layout.TASK,'automated_checks':self.source},layout.CONTRACT_SHA,layout.DATASET)}}
        self.source,_=layout.effective_source(layout_manifest,self.source,self.source,None)
        self.source=self.source.rstrip()  # bundle serialization removes the terminal newline
        self.contract={'task_id':BUDGET.SERVICE_TASK,'automated_checks':self.source}
        self.marker=BUDGET.marker(self.contract,BUDGET.SERVICE_CONTRACT)
        self.manifest={'identity':{'task_id':BUDGET.SERVICE_TASK},'digests':{'contract_sha256':BUDGET.SERVICE_CONTRACT},
                       'runtime':{'work_order_evidence_budget_profile':self.marker}}

    def writer(self,source):
        function=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='write_evidence')
        module=ast.Module(body=[function],type_ignores=[])
        namespace={'Path':Path,'json':json,'hashlib':hashlib,'ALIASES':{},'OUTPUT':'results/daily.md',
                   'EVIDENCE':'evaluator_evidence/service-daily','EvaluationError':EvaluationError}
        exec(compile(ast.fix_missing_locations(module),'<synthetic-evidence-writer>','exec'),namespace)
        return namespace['write_evidence']

    def fixed(self):
        return BUDGET.effective_source(self.manifest,self.source,self.source,None)[0]

    def test_exact_frozen_source_and_only_capacity_guard_changes(self):
        self.assertEqual(hashlib.sha256(self.source.encode()).hexdigest(),BUDGET.SERVICE_SOURCE)
        self.assertIsNotNone(self.marker)
        fixed,receipt=BUDGET.effective_source(self.manifest,self.source,self.source,None)
        self.assertEqual(fixed,self.source.replace(BUDGET.SERVICE_OLD,BUDGET.SERVICE_NEW))
        self.assertEqual(receipt['correction_id'],BUDGET.SERVICE_PROFILE)
        self.assertFalse(receipt['candidate_rewritten'])
        legacy=deepcopy(self.manifest);legacy['runtime']={}
        self.assertEqual(BUDGET.effective_source(legacy,self.source,self.source,None),(self.source,None))
        self.assertIsNone(BUDGET.marker(self.contract,'0'*64))
        self.assertIsNone(BUDGET.marker({**self.contract,'automated_checks':self.source+'\n'},BUDGET.SERVICE_CONTRACT))
        bad=deepcopy(self.manifest);bad['runtime']['work_order_evidence_budget_profile']['file_utf8_bytes']=2**30
        with self.assertRaisesRegex(ValueError,'PROFILE_MISMATCH'):
            BUDGET.effective_source(bad,self.source,self.source,None)

    def test_small_evidence_bytes_unchanged_and_large_evidence_complete(self):
        original=self.writer(self.source);fixed=self.writer(self.fixed())
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);old=root/'old';new=root/'new';old.mkdir();new.mkdir()
            for writer,target in [(original,old),(fixed,new)]:
                writer(target,'Synthetic complete report\n',[{'record_id':'R-001'}],{},{'note':'small'},{})
            old_files={p.name:p.read_bytes() for p in (old/'evaluator_evidence/service-daily').iterdir()}
            new_files={p.name:p.read_bytes() for p in (new/'evaluator_evidence/service-daily').iterdir()}
            self.assertEqual(old_files,new_files)
            large=root/'large';large.mkdir();rows=[{'record_id':str(i),'note':'完整内容'*500} for i in range(66)]
            with self.assertRaisesRegex(EvaluationError,'Evidence would be truncated'):
                original(large,'Synthetic report',rows,{}, {'note':'context'*4000},{})
            self.assertFalse(list((large/'evaluator_evidence/service-daily').iterdir()))
            fixed(large,'Synthetic report',rows,{}, {'note':'context'*4000},{})
            folder=large/'evaluator_evidence/service-daily'
            recovered=sum([json.loads((folder/f'sources_{i+1}.json').read_text())['rows'] for i in range(3)],[])
            self.assertEqual(recovered,rows)
            context=json.loads((folder/'judgment_context.json').read_text())
            self.assertEqual(context['diagnostics']['note'],'context'*4000)
            self.assertFalse(context['truncated'])

    def test_new_byte_cap_report_length_and_path_guards_still_fail_closed(self):
        writer=self.writer(self.fixed())
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with self.assertRaisesRegex(EvaluationError,'Evidence would be truncated'):
                writer(root,'report',[],{}, {'large':'中'*400000},{})
            self.assertFalse(list((root/'evaluator_evidence/service-daily').iterdir()))
            with self.assertRaisesRegex(EvaluationError,'Report exceeds evidence capacity'):
                writer(root,'x'*30001,[],{},{},{})
            other=root/'redirected';other.mkdir()
            (root/'evaluator_evidence/service-daily').rmdir()
            (root/'evaluator_evidence/service-daily').symlink_to(other,target_is_directory=True)
            with self.assertRaisesRegex(EvaluationError,'Evidence directory redirects'):
                writer(root,'report',[],{},{},{})

if __name__=='__main__':unittest.main()
