from copy import deepcopy
from pathlib import Path
import base64
import hashlib
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

from tests.general_e2e.test_local_scoring_runtime import RUNTIME,Fixture,REPO_ROOT
from tests.general_e2e.test_public_office_profiles import with_cwm
from tests.general_e2e import test_general_semantic_scoring as semantics
from eval_general_e2e.datasets.bundle import _strip_codeblock
from tests.general_e2e.frozen_sources import parse_frozen_task_source as _parse_task_source

SIDE=RUNTIME.public_snapshot_sidecar
SNAPSHOT=RUNTIME.declared_public_snapshots


class PublicSnapshotSidecarTests(unittest.TestCase):
    def test_exact_new_profile_moves_only_added_audit_preserving_original_budgets_and_legacy_code(self):
        row=next(r for r in SNAPSHOT.registry() if r['task_id']==SIDE.TASK)
        task=next((REPO_ROOT/'tasks/general/work').rglob(SIDE.TASK+'.md'));_,sections,_=_parse_task_source(task)
        source=_strip_codeblock(sections['Automated Checks']);contract={'task_id':SIDE.TASK,'automated_checks':source}
        parent=SNAPSHOT.marker(contract,row['contract_sha256'],row['dataset']);profile=SIDE.marker(contract,row['contract_sha256'],row['dataset'])
        m={'identity':{'task_id':SIDE.TASK},'digests':{'contract_sha256':row['contract_sha256']},'dataset':row['dataset'],
            'runtime':{'declared_public_snapshot_profile':parent,'public_snapshot_audit_sidecar_profile':profile}}
        old=deepcopy(m);old['runtime'].pop('public_snapshot_audit_sidecar_profile')
        legacy,_=RUNTIME._effective_rule_source(old,source);fixed,receipt=RUNTIME._effective_rule_source(m,source)
        self.assertIn('if size>74000:',fixed);self.assertIn('if len(manifest_text)>18000:',fixed)
        self.assertNotIn("output=workspace/_GE2E_SNAPSHOT_PROFILE['evidence_directory']/'00_public_snapshot_variance.json'",fixed)
        self.assertIn("output=workspace/_GE2E_SNAPSHOT_PROFILE['evidence_directory']/'00_public_snapshot_variance.json'",legacy)
        original_required=deepcopy(contract.get('judge_evidence'))
        self.assertIn(SIDE.SIDECAR,RUNTIME._required_generated_evidence(contract,manifest=m))
        self.assertEqual(contract.get('judge_evidence'),original_required)
        self.assertNotIn(SIDE.SIDECAR,RUNTIME._required_generated_evidence(contract,manifest=old))
        self.assertFalse(receipt['candidate_rewritten']);self.assertEqual(receipt['original_total_character_budget'],74000)
        compile(fixed,'<exact-new-sidecar>','exec')
        bad=deepcopy(m);bad['runtime']['public_snapshot_audit_sidecar_profile']['path']='results/forged.json'
        with self.assertRaises(RUNTIME.ScoringRuntimeError):RUNTIME._effective_rule_source(bad,source)

    def test_managed_sidecar_is_frozen_queryable_and_archived_without_changing_original_contract(self):
        row=SNAPSHOT.registry()[0];ref=next(r for r in row['files'] if r['kind']=='office-cwm-only')
        raw=with_cwm(base64.b64decode(ref['base64']))
        helper=Path(SNAPSHOT.office_input_compat.__file__).read_text(encoding='utf-8')
        rule=helper+'\n_GE2E_SNAPSHOT_PROFILE='+repr(row)+'\n'+SNAPSHOT.MATCHER+'\n'
        rule+='def grade(transcript: list, workspace_path: str) -> dict:\n'
        rule+='    root=_ge2e_Path(workspace_path)\n    output=root/"evaluator_evidence_018"\n    output.mkdir()\n'
        rule+='    accepted=_ge2e_declared_public_snapshot_matches(root/'+repr(ref['path'])+','+repr(ref['path'])+','+repr(ref['declared_sha256'])+',root)\n'
        rule+='    (output/"00_manifest.json").write_text("original evidence",encoding="utf-8")\n'
        rule+='    return {"probe":float(accepted),"overall_score":float(accepted)}\n'
        marker={'profile':SIDE.PROFILE,'snapshot_profile':None,'path':SIDE.SIDECAR,'synthetic_fixture':True}
        with tempfile.TemporaryDirectory() as folder,patch.object(SIDE,'marker',return_value=marker):
            root=Path(folder)
            try:
                attempt=Fixture(root,rule=rule,candidate_files={ref['path']:raw},grading_type='hybrid',
                    grading_weights={'automated':.6,'llm_judge':.4},llm_judge_rubric=semantics.RUBRIC,
                    contract_overrides={'judge_evidence':{'required':[{'path':'evaluator_evidence_018/','role':'grader_generated_evidence'}]}}).prepare(protect_runtime_office_inputs=sys.platform=='darwin')
                before=(attempt/'private/contract.json').read_bytes()
                RUNTIME.run_rules_attempt(attempt_root=attempt,runtime_python=Path(sys.executable),timeout_seconds=30)
                self.assertEqual((attempt/'private/contract.json').read_bytes(),before)
                self.assertFalse((attempt/'runtime/workspace/evaluator_evidence_018/00_public_snapshot_variance.json').exists())
                audit=attempt/'runtime/workspace'/SIDE.SIDECAR;self.assertTrue(audit.is_file())
                checksum=hashlib.sha256(audit.read_bytes()).hexdigest()
                response,candidate,transcript=semantics.GeneralSemanticScoringTests()._prepare_and_query(attempt)
                catalog=json.loads((attempt/'semantic/evidence-catalog.json').read_text())
                self.assertIn('evaluator_compatibility_audit',json.dumps(catalog))
                frozen=attempt/'grader-evidence/files'/SIDE.SIDECAR;self.assertEqual(hashlib.sha256(frozen.read_bytes()).hexdigest(),checksum)
                for item,value,evidence,queries in zip(response['criteria'],[1.,.5],[[candidate],[transcript]],[['query-0001'],['query-0002']]):
                    item.update(status='judged',score=value,reason='合成判定仅验证侧边审计冻结与归档传输，不替代正式独立裁判。',evidence_ids=evidence,
                        review={'query_ids':queries,'supporting_evidence_checked':True,'contradicting_evidence_checked':True,'absence_claim':False,'complete_event_range_checked':False})
                path=attempt/'synthetic-response.json';path.write_text(json.dumps(response,ensure_ascii=False),encoding='utf-8')
                RUNTIME.record_semantics_attempt(attempt_root=attempt,response_path=path);RUNTIME.finalize_score_attempt(attempt_root=attempt)
                self.assertTrue(RUNTIME.verify_score_attempt(attempt)['score_valid']);RUNTIME._remove_tree(attempt/'runtime')
                self.assertTrue(RUNTIME.verify_score_attempt(attempt,archived=True)['score_valid'])
            finally:RUNTIME._remove_tree(root)


if __name__=='__main__':unittest.main()
