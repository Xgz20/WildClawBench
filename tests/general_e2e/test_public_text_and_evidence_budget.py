from copy import deepcopy
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest

from eval_general_e2e.datasets.bundle import _strip_codeblock
from tests.general_e2e.frozen_sources import parse_frozen_task_source as _parse_task_source
from tests.general_e2e.test_local_scoring_runtime import RUNTIME,REPO_ROOT

TEXT=RUNTIME.public_text_profiles
BUDGET=RUNTIME.work_order_evidence_budget


class PublicTextAndBudgetTests(unittest.TestCase):
    def source(self,tid):
        task=next((REPO_ROOT/'tasks/general/work').rglob(tid+'.md'));_,s,_=_parse_task_source(task)
        return _strip_codeblock(s['Automated Checks'])

    def manifest(self,row):
        source=self.source(row['task_id']);contract={'task_id':row['task_id'],'automated_checks':source}
        marker=TEXT.marker(contract,row['contract_sha256'],row['dataset']);self.assertIsNotNone(marker)
        return contract,{'identity':{'task_id':row['task_id']},'dataset':row['dataset'],
            'digests':{'contract_sha256':row['contract_sha256']},'runtime':{
                'public_office_input_profile':RUNTIME.public_office_profiles.marker(contract,row['contract_sha256']),
                'public_text_input_profile':marker}}

    def test_exact_public_text_profile_and_legacy_effective_source_remain_separate(self):
        self.assertEqual(len(TEXT.registry()),2)
        for row in TEXT.registry():
            contract,m=self.manifest(row);source=contract['automated_checks']
            current,receipt=RUNTIME._effective_rule_source(m,source)
            self.assertEqual(receipt['correction_id'],TEXT.PROFILE);self.assertFalse(receipt['candidate_rewritten'])
            old=deepcopy(m);old['runtime'].pop('public_text_input_profile')
            legacy,_=RUNTIME._effective_rule_source(old,source)
            self.assertTrue(current.startswith(legacy));self.assertNotIn('_GE2E_TEXT_FILES=',legacy)
            bad=deepcopy(m);bad['dataset']['digest']='0'*64
            with self.assertRaises(RUNTIME.ScoringRuntimeError):RUNTIME._effective_rule_source(bad,source)

    def test_managed_matcher_accepts_only_original_lf_crlf_bytes_and_keeps_real_sha(self):
        row=TEXT.registry()[0];contract,m=self.manifest(row);source,_=RUNTIME._effective_rule_source(m,contract['automated_checks'])
        ref=row['files'][0]
        original=next((REPO_ROOT/'workspace/general/work').rglob(Path(ref['path']).name))
        raw=original.read_bytes();self.assertEqual(hashlib.sha256(raw).hexdigest(),ref['canonical_sha256'])
        probe=source+"\ndef grade(transcript,workspace_path):\n    path=_ge2e_Path(workspace_path)/"+repr(ref['path'])+"\n    return {'accepted':float(_ge2e_public_office_matches(path,"+repr(ref['declared_sha256'])+",workspace_path))}\n"
        for label,content,expected in [('lf',raw,1.),('crlf',raw.replace(b'\n',b'\r\n'),1.),('changed',raw+b'altered',0.)]:
            with self.subTest(label=label),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);workspace=root/'workspace';workspace.mkdir();(workspace/'evaluator_evidence').mkdir()
                target=workspace/ref['path'];target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(content)
                request={'schema_version':RUNTIME.WORKER_REQUEST_SCHEMA,'workspace_path':str(workspace),'transcript':[],'automated_checks':probe}
                path=root/'request.json';out=root/'result.json';path.write_text(json.dumps(request),encoding='utf-8')
                result=subprocess.run([sys.executable,'-I',str(Path(RUNTIME.__file__).with_name('rule_worker.py')),'--request',str(path),'--result',str(out)],capture_output=True,timeout=30)
                document=json.loads(out.read_text());self.assertEqual(result.returncode,0,document.get('error'))
                self.assertEqual(document['result']['accepted'],expected);self.assertEqual(target.read_bytes(),content)

    def test_work_order_changes_only_total_resource_budget_and_keeps_original_chunker(self):
        source=self.source(BUDGET.TASK);contract={'task_id':BUDGET.TASK,'automated_checks':source}
        marker=BUDGET.marker(contract,BUDGET.CONTRACT_SHA);self.assertIsNotNone(marker)
        m={'identity':{'task_id':BUDGET.TASK},'digests':{'contract_sha256':BUDGET.CONTRACT_SHA},'runtime':{'work_order_evidence_budget_profile':marker}}
        fixed,receipt=RUNTIME._effective_rule_source(m,source)
        old='    total=sum(len(v) for v in serialized.values())\n    if total>70000:'
        expected=source.replace(old,"    total=sum(len(v.encode('utf-8')) for v in serialized.values())\n    if total>16777216:")
        self.assertEqual(fixed,expected);self.assertIn('if len(body)>18500:',fixed)
        self.assertFalse(receipt['evidence_budget']['truncation_allowed'])
        self.assertEqual(RUNTIME._effective_rule_source({},source),(source,None))


if __name__=='__main__':unittest.main()
