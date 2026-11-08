"""Only the complete bound projection repair can replace its old admission failure."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from tests.general_e2e.test_general_scoring_orchestration import ORCHESTRATOR
import compose_full_scope_selection as composition


class PresentationRepairSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);(self.root/'private').mkdir()
        self.profile='bound-native-moa-presentation-completeness/v1'
        self.original={'execution':{'scorable':False,'failure':{'code':'EXECUTION_NOT_SCORABLE'}}}
        self.execution={'harness':{'id':'doubaowork'}}
        self.manifest={'evidence_admission':self.profile}
        self.receipt={'profile':self.profile,'original_execution_changed':False,'original_trace_changed':False,
            'proof':{'all_display_blocks_accounted':True,'original_evidence_completeness':'partial',
                     'original_missing':['resource_metrics_complete_coverage','unmapped-native-message-block']}}
        self.save()

    def save(self):
        p=self.root/'private/evidence-admission.json';p.write_text(json.dumps(self.receipt))
        self.manifest['reviewed_evidence_receipt_sha256']=hashlib.sha256(p.read_bytes()).hexdigest()

    def check(self):
        return composition.verified_presentation_admission_repair(self.original,self.manifest,self.execution,self.root)

    def test_only_the_explicit_projection_admission_failure_is_recognized(self):
        self.assertTrue(self.check())
        self.original['execution']['scorable']=True
        self.assertFalse(self.check())
        self.original['execution']['scorable']=False
        self.original['execution']['failure']['code']='QUOTA'
        self.assertFalse(self.check())

    def test_media_gap_or_unresolved_projection_cannot_use_this_route(self):
        self.receipt['proof']['original_missing'].append('multimodal-tool-result-content-unverified');self.save()
        self.assertFalse(self.check())
        self.receipt['proof']['original_missing']=['unmapped-native-message-block']
        self.receipt['proof']['all_display_blocks_accounted']=False;self.save()
        self.assertFalse(self.check())

    def test_receipt_drift_or_rewritten_originals_are_rejected(self):
        (self.root/'private/evidence-admission.json').write_text('{}')
        self.assertFalse(self.check())
        self.receipt['original_trace_changed']=True;self.save()
        self.assertFalse(self.check())


if __name__=='__main__':unittest.main()
