from copy import deepcopy
import hashlib
import unittest

from eval_general_e2e.datasets.bundle import _parse_task_source,_strip_codeblock
from tests.general_e2e.test_local_scoring_runtime import RUNTIME,REPO_ROOT

P=RUNTIME.procurement_explicit_labels

class ProcurementExplicitLabelsTests(unittest.TestCase):
    def setUp(self):
        task=REPO_ROOT/'eval_general_e2e/datasets/source-snapshots/general-custom70-v4/tasks'/f'{P.TASK}.md'
        _,sections,_=_parse_task_source(task)
        self.source=_strip_codeblock(sections['Automated Checks'])
        self.contract={'task_id':P.TASK,'automated_checks':self.source}
        self.manifest={'identity':{'task_id':P.TASK},'digests':{'contract_sha256':P.CONTRACT},
                       'dataset':{'id':'general-custom70-v4','digest':'914783354b23efa4f814342187ebe931df76cbcb0b2ea3dd85bd3f5705f485ff'},
                       'runtime':{'shared_rule_source_repair':RUNTIME.shared_source_repairs.marker(self.contract)}}

    def test_exact_alias_bridge_preserves_base_and_all_numeric_source(self):
        self.assertEqual(hashlib.sha256(self.source.encode()).hexdigest(),P.SOURCE)
        base,prior=RUNTIME._effective_rule_source(self.manifest,self.source)
        self.assertEqual(hashlib.sha256(base.encode()).hexdigest(),P.BASE)
        marked=deepcopy(self.manifest)
        marked['runtime']['procurement_explicit_labels_profile']=P.marker(self.contract,P.CONTRACT)
        fixed,receipt=RUNTIME._effective_rule_source(marked,self.source)
        self.assertEqual(fixed,base+P.BRIDGE+P.SECTION_BRIDGE)
        self.assertEqual(receipt['correction_id'],P.PROFILE)
        self.assertEqual(receipt['prior_correction'],prior)
        self.assertFalse(receipt['candidate_rewritten']);self.assertFalse(receipt['numeric_decisions_assigned'])
        before={};after={};exec(base,before);exec(fixed,after)
        self.assertIsNone(before['category']('无单入库',[]))
        self.assertEqual(after['category']('无单入库',[]),'orphan')
        for label,key in [('数量差异订单','qty'),('数量差异订单笔数','qty'),('金额差异订单','amount'),('金额差异订单笔数','amount'),('无单入库金额合计（元）','orphan_amount')]:
            self.assertEqual(after['summary_key'](label),key)
        for label in ['匹配成功订单','合计']:
            self.assertIsNone(before['summary_key'](label));self.assertIsNone(after['summary_key'](label))
        for name in ['金额差异','数量差异','未入库订单','说明']:
            self.assertEqual(before['category'](name,[]),after['category'](name,[]))

    def test_unknown_contract_source_or_base_repair_is_rejected(self):
        self.assertIsNone(P.marker(self.contract,'0'*64))
        self.assertIsNone(P.marker({**self.contract,'automated_checks':self.source+'\n'},P.CONTRACT))
        base,prior=RUNTIME._effective_rule_source(self.manifest,self.source)
        self.manifest['runtime']['procurement_explicit_labels_profile']=P.marker(self.contract,P.CONTRACT)
        with self.assertRaisesRegex(ValueError,'PROFILE_MISMATCH'):
            P.effective_source(self.manifest,self.source,base+'\n',prior)

    def test_historical_v1_and_current_v2_keep_separate_exact_base_sources(self):
        legacy=deepcopy(self.manifest)
        legacy['runtime']['shared_rule_source_repair']=RUNTIME.shared_source_repairs.marker(
            self.contract,profile='procurement-date-and-section-extraction/v4')
        old_base,old_prior=RUNTIME._effective_rule_source(legacy,self.source)
        self.assertEqual(hashlib.sha256(old_base.encode()).hexdigest(),P.LEGACY_BASE)
        legacy['runtime']['procurement_explicit_labels_profile']=P.marker(
            self.contract,P.CONTRACT,profile=P.LEGACY_PROFILE)
        old_fixed,old_receipt=RUNTIME._effective_rule_source(legacy,self.source)
        self.assertEqual(old_fixed,old_base+P.BRIDGE)
        self.assertEqual(old_receipt['correction_id'],P.LEGACY_PROFILE)
        self.assertEqual(old_receipt['prior_correction'],old_prior)
        current_base,current_prior=RUNTIME._effective_rule_source(self.manifest,self.source)
        with self.assertRaisesRegex(ValueError,'PROFILE_MISMATCH'):
            P.effective_source(legacy,self.source,current_base,current_prior)
        current=deepcopy(self.manifest)
        current['runtime']['procurement_explicit_labels_profile']=P.marker(self.contract,P.CONTRACT)
        with self.assertRaisesRegex(ValueError,'PROFILE_MISMATCH'):
            P.effective_source(current,self.source,old_base,old_prior)

    def test_previous_v2_replays_priority_v5_without_declared_total_projection(self):
        manifest=deepcopy(self.manifest)
        manifest['runtime']['shared_rule_source_repair']=RUNTIME.shared_source_repairs.marker(
            self.contract,profile='procurement-date-and-section-extraction/v5')
        base,prior=RUNTIME._effective_rule_source(manifest,self.source)
        self.assertEqual(hashlib.sha256(base.encode()).hexdigest(),P.PREVIOUS_BASE)
        manifest['runtime']['procurement_explicit_labels_profile']=P.marker(
            self.contract,P.CONTRACT,profile=P.PREVIOUS_PROFILE)
        fixed,receipt=RUNTIME._effective_rule_source(manifest,self.source)
        self.assertEqual(fixed,base+P.BRIDGE)
        self.assertEqual(receipt['correction_id'],P.PREVIOUS_PROFILE)
        self.assertEqual(receipt['prior_correction'],prior)
        self.assertNotIn('procurement-declared-source-totals/v1',fixed)

if __name__=='__main__':unittest.main()
