from copy import deepcopy
from pathlib import Path
import ast
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest

from eval_general_e2e.datasets.bundle import _strip_codeblock
from tests.general_e2e.frozen_sources import parse_frozen_task_source as _parse_task_source
from tests.general_e2e.test_local_scoring_runtime import RUNTIME,REPO_ROOT

LABELS=RUNTIME.procurement_summary_labels


class ProcurementEquivalentSummaryTests(unittest.TestCase):
    def source(self):
        task=next((REPO_ROOT/'tasks/general_e2e').rglob(LABELS.TASK+'.md'))
        _,sections,_=_parse_task_source(task);return _strip_codeblock(sections['Automated Checks'])

    def manifest(self,enabled):
        source=self.source();runtime={'procurement_layout_profile':'procurement-matrix-formulas/v2'}
        if enabled:runtime['procurement_summary_label_profile']=LABELS.marker({'task_id':LABELS.TASK,'automated_checks':source},LABELS.CONTRACT_SHA)
        return {'identity':{'task_id':LABELS.TASK},'digests':{'contract_sha256':LABELS.CONTRACT_SHA},'runtime':runtime}

    def test_only_new_marker_extends_data_alias_and_all_original_functions_stay_identical(self):
        source=self.source();old,old_receipt=RUNTIME._effective_rule_source(self.manifest(False),source)
        fixed,receipt=RUNTIME._effective_rule_source(self.manifest(True),source)
        self.assertEqual(fixed,old+LABELS.BRIDGE)
        functions=lambda code:{n.name:ast.dump(n) for n in ast.parse(code).body if isinstance(n,ast.FunctionDef)}
        self.assertEqual(functions(old),functions(fixed))
        self.assertEqual(receipt['correction_id'],LABELS.PROFILE)
        self.assertEqual(receipt['prior_correction'],old_receipt)
        self.assertFalse(receipt['numeric_claims_invented']);self.assertFalse(receipt['candidate_rewritten'])

    def test_exact_contract_source_guard_rejects_mismatch(self):
        source=self.source();self.assertEqual(hashlib.sha256(source.encode()).hexdigest(),LABELS.SOURCE_SHA)
        for change in [lambda m:m['digests'].update(contract_sha256='0'*64),
                       lambda m:m['runtime']['procurement_summary_label_profile'].update(source_sha256='0'*64)]:
            m=deepcopy(self.manifest(True));change(m)
            with self.assertRaises(RUNTIME.ScoringRuntimeError):RUNTIME._effective_rule_source(m,source)

    def test_managed_worker_equivalent_label_maps_to_original_matched_key_not_other_categories(self):
        source,_=RUNTIME._effective_rule_source(self.manifest(True),self.source())
        source+='''
def grade(transcript,workspace_path):
    return {'equivalent':float(summary_key('已匹配订单（有对应入库）')=='matched'),
            'plain':float(summary_key('已匹配订单')=='matched'),
            'orders_unchanged':float(summary_key('采购订单总数')=='orders'),
            'unknown_retained':float(summary_key('已取消订单') is None)}
'''
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);workspace=root/'workspace';workspace.mkdir()
            path=root/'request.json';out=root/'result.json'
            path.write_text(json.dumps({'schema_version':RUNTIME.WORKER_REQUEST_SCHEMA,'workspace_path':str(workspace),
                'transcript':[],'automated_checks':source}),encoding='utf-8')
            result=subprocess.run([sys.executable,'-I',str(Path(RUNTIME.__file__).with_name('rule_worker.py')),
                '--request',str(path),'--result',str(out)],capture_output=True,timeout=30)
            raw=json.loads(out.read_text());self.assertEqual(result.returncode,0,raw.get('error'))
            self.assertEqual(set(raw['result'].values()),{1.})


if __name__=='__main__':unittest.main()
