from copy import deepcopy
from pathlib import Path
import ast
import importlib.util
import json
import math
import tempfile
import unittest
from unittest.mock import patch

from eval_general_e2e.datasets.bundle import _parse_task_source,_strip_codeblock
from tests.general_e2e.test_local_scoring_runtime import RUNTIME,REPO_ROOT
from tests.general_e2e import test_general_scoring_orchestration as orchtests

ENTRY=RUNTIME.grade_wrapper_normalization
TYPED=RUNTIME.typed_rule_diagnostics
spec=importlib.util.spec_from_file_location('typed_worker_test',Path(RUNTIME.__file__).with_name('rule_worker.py'))
WORKER=importlib.util.module_from_spec(spec);spec.loader.exec_module(WORKER)


class WrapperAndTypedDiagnosticsTests(unittest.TestCase):
    def source(self,tid):
        task=next((REPO_ROOT/'tasks/general_e2e').rglob(tid+'.md'));_,s,_=_parse_task_source(task);return _strip_codeblock(s['Automated Checks'])

    def test_six_exact_wrappers_keep_every_function_body_and_alias_call(self):
        self.assertEqual(len(ENTRY.registry()),6)
        for row in ENTRY.registry():
            source=self.source(row['task_id']);contract={'task_id':row['task_id'],'automated_checks':source}
            marker=ENTRY.marker(contract,row['contract_sha256'],row['dataset']);self.assertIsNotNone(marker)
            m={'identity':{'task_id':row['task_id']},'dataset':row['dataset'],'digests':{'contract_sha256':row['contract_sha256']},
                'runtime':{'grade_wrapper_normalization_profile':marker}}
            fixed,receipt=RUNTIME._effective_rule_source(m,source)
            before=ast.parse(source);after=ast.parse(fixed)
            first=True
            for node in after.body:
                if isinstance(node,ast.FunctionDef) and node.name=='_ge2e_original_business_grade':node.name='grade'
                if isinstance(node,ast.Assign) and isinstance(node.value,ast.Name) and node.value.id=='_ge2e_original_business_grade':node.value.id='grade'
            self.assertEqual(ast.dump(before),ast.dump(after));self.assertFalse(receipt['evidence_wrapper_removed'])
            self.assertEqual(sum(isinstance(n,ast.FunctionDef) and n.name=='grade' for n in ast.parse(fixed).body),1)
            self.assertEqual(RUNTIME._effective_rule_source({},source),(source,None))

    def test_errors_list_is_diagnostic_and_raw_numeric_values_stay_exact(self):
        source=self.source(TYPED.TASK);contract={'task_id':TYPED.TASK,'automated_checks':source}
        marker=TYPED.marker(contract,TYPED.CONTRACT_SHA);self.assertIsNotNone(marker)
        m={'digests':{'contract_sha256':TYPED.CONTRACT_SHA},'runtime':{'typed_rule_diagnostics_profile':marker}}
        base={'schema_version':'wildclawbench.general-e2e-numeric-diagnostics/v1','diagnostic_keys':['diagnostics','诊断']}
        adapter=TYPED.effective_adapter(m,contract,base)
        raw={'C2':.5,'C3':.75,'C4':1.,'C5':0.,'overall_score':.64,'errors':[]}
        self.assertEqual(WORKER.adapt_rule_result(raw,adapter),{k:v for k,v in raw.items() if k!='errors'})
        self.assertEqual(raw['errors'],[])
        for errors in [False,'',{},['证据提取预算超限:04.json']]:
            with self.subTest(errors=errors),self.assertRaises(ValueError):WORKER.adapt_rule_result(dict(raw,errors=errors),adapter)
        self.assertEqual(WORKER.adapt_rule_result(dict(raw,errors=['候选文件不可读']),adapter)['C3'],.75)
        bad=deepcopy(m);bad['digests']['contract_sha256']='0'*64
        with self.assertRaises(ValueError):TYPED.effective_adapter(bad,contract,base)

    def test_nullable_read_error_stays_raw_metadata_without_discarding_unknown_numeric_keys(self):
        base={'schema_version':'wildclawbench.general-e2e-numeric-diagnostics/v1','diagnostic_keys':['diagnostics','诊断']}
        rows=[r for r in TYPED.registry() if r['diagnostic_nullable_text_keys']]
        self.assertEqual(len(rows),3)
        for row in rows:
            source=self.source(row['task_id']);contract={'task_id':row['task_id'],'automated_checks':source}
            marker=TYPED.marker(contract,row['contract_sha256']);self.assertIsNotNone(marker)
            manifest={'digests':{'contract_sha256':row['contract_sha256']},'runtime':{'typed_rule_diagnostics_profile':marker}}
            policy=TYPED.effective_adapter(manifest,contract,base)
            for error in [None,'候选文件不可读']:
                raw={k:.5 for k in row['numeric_keys']};raw['candidate_read_error']=error
                adapted=WORKER.adapt_rule_result(raw,policy)
                self.assertEqual(adapted,{k:.5 for k in row['numeric_keys']})
                self.assertEqual(raw['candidate_read_error'],error)
                extra=dict(raw,unknown_numeric=.75)
                self.assertEqual(WORKER.adapt_rule_result(extra,policy)['unknown_numeric'],.75)
            with self.assertRaises(ValueError):WORKER.adapt_rule_result(dict(raw,candidate_read_error=[]),policy)

    def test_workerless_entrypoint_failure_can_be_retained_without_fabricating_worker_output(self):
        original=orchtests.ORCHESTRATOR
        rule="def grade(transcript,workspace_path):\n return {'overall_score':1.}\n_old=grade\ndef grade(transcript,workspace_path):\n return _old(transcript,workspace_path)"
        with tempfile.TemporaryDirectory() as folder:
            fixture=orchtests.Fixture(Path(folder),task_ids=('task-entry',),grading_type='hybrid',contract_overrides={'automated_checks':rule})
            view=fixture.initialize();root=Path(view['orchestration_root'])
            direct=orchtests.GeneralScoringOrchestrationTests()._direct_local_score_command
            try:
                with patch.object(original,'_run_score_command',side_effect=direct):
                    with self.assertRaises((original.OrchestrationError,orchtests.SCORE_RUNTIME.ScoringRuntimeError)):
                        original.run_rule_score_task(root,task_id='task-entry',runtime_python=Path(__import__('sys').executable))
                    state=json.loads((root/'orchestration-state.json').read_text());attempt=root/state['tasks'][0]['attempt_path']
                    self.assertFalse((attempt/'worker/result.json').exists())
                    check=lambda m,c,a,w:a.get('status')=='failed' and a.get('error',{}).get('code')=='RULE_ENTRYPOINT_INVALID' and not w
                    with patch.object(ENTRY,'original_failure',side_effect=check):
                        retained=original.record_unscored_rule_error(root,task_id='task-entry',reason='旧冻结代码有明确业务函数和取证包装器，保留未启动Worker的入口错误，新attempt另行修复。')
                        self.assertEqual(retained['unscored_count'],1);self.assertEqual(original.status(root)['unscored_count'],1)
                        original.build_submission(root)
                    self.assertFalse((attempt/'worker/result.json').exists())
            finally:RUNTIME._remove_tree(Path(folder))


if __name__=='__main__':unittest.main()
