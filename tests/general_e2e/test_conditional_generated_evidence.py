import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tests.general_e2e.test_local_scoring_runtime import RUNTIME

ABSENCE=RUNTIME.conditional_generated_evidence

class ConditionalGeneratedEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        (self.root/'candidate').mkdir();self.workspace=self.root/'runtime';self.workspace.mkdir()
        (self.workspace/'evaluator_evidence').mkdir();(self.root/'worker').mkdir()
        self.manifest={'paths':{'candidate_original':'candidate','runtime_workspace':'runtime'},
                       'runtime':{'workspace_argument':'runtime'}}
        self.marker={'profile':ABSENCE.PROFILE,'contract_sha256':ABSENCE.CONTRACT,
                     'source_sha256':ABSENCE.SOURCE,'conditional_pattern':ABSENCE.PATTERN}
        self.status={'candidate_status':'missing','candidates':[],'reference_verified':True,
          'native_probe_is_grader_action_not_agent_self_check':True,'native_editable_page_ratio':0.0,
          'delivery_usable':0.0,'evidence_files':['01_reference.json'],'evidence_complete_within_collector_budget':True}
        self.write(self.status)
        self.patch=patch.object(ABSENCE,'marker',return_value=self.marker);self.patch.start()
    def tearDown(self):self.patch.stop();self.temp.cleanup()
    def write(self,status):
        (self.workspace/'evaluator_evidence/00_status.json').write_text(json.dumps(status),encoding='utf-8')
        (self.root/'worker/result.json').write_text(json.dumps({'ok':True,'raw_result':{'diagnostics':status},
           'result':{'delivery_usable':0.0,'overall_score':0.0}}),encoding='utf-8')
    def proof(self):return ABSENCE.absence(self.root,self.workspace,ABSENCE.PATTERN,self.manifest,{})
    def test_missing_pages_stay_absent_and_status_is_not_candidate_content(self):
        proof=self.proof();self.assertEqual(proof['candidate_deck_count'],0)
        self.assertFalse(proof['placeholder_created']);self.assertFalse(proof['numeric_decisions_assigned'])
        self.assertEqual(list((self.workspace/'evaluator_evidence').glob('02_candidate_*.json')),[])
    def test_unknown_nonmissing_partial_reference_and_false_counts_are_rejected(self):
        for key,value in [('candidate_status','invalid_package'),('candidate_status','unsafe_output_path'),
                          ('candidates',[{'path':'results/deck.pptx'}]),('reference_verified',False),
                          ('delivery_usable',False),('delivery_usable',1.0),
                          ('evidence_files',[]),('evidence_complete_within_collector_budget',False)]:
            status=copy.deepcopy(self.status);status[key]=value;self.write(status)
            with self.subTest(key=key,value=value):self.assertIsNone(self.proof())
    def test_original_or_runtime_deck_and_conflicting_worker_are_rejected(self):
        for base in [self.root/'candidate',self.workspace]:
            (base/'results').mkdir();p=base/'results/deck.PPTX';p.write_bytes(b'broken')
            self.assertIsNone(self.proof());p.unlink()
        worker=json.loads((self.root/'worker/result.json').read_text());worker['raw_result']['diagnostics']={}
        (self.root/'worker/result.json').write_text(json.dumps(worker));self.assertIsNone(self.proof())
    def test_profile_drift_and_other_patterns_are_not_admitted(self):
        self.manifest['runtime']['conditional_generated_evidence_profile']={'profile':'unknown'}
        with self.assertRaises(ValueError):self.proof()
        self.manifest['runtime'].pop('conditional_generated_evidence_profile')
        self.assertIsNone(ABSENCE.absence(self.root,self.workspace,'evaluator_evidence/other_*.json',self.manifest,{}))

if __name__=='__main__':unittest.main()
