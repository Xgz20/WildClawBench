from copy import deepcopy
import hashlib
import unittest
from tests.general_e2e.test_procurement_explicit_labels import ProcurementExplicitLabelsTests
from tests.general_e2e.test_local_scoring_runtime import RUNTIME

class ProcurementCategorySubtotalTests(unittest.TestCase):
    def setUp(self):
        fixture=ProcurementExplicitLabelsTests();fixture.setUp();self.fixture=fixture
        self.manifest=deepcopy(fixture.manifest)
        self.manifest['dataset']=RUNTIME.procurement_annotation_formula.DATASET
        self.manifest['runtime']['procurement_explicit_labels_profile']=RUNTIME.procurement_explicit_labels.marker(fixture.contract,RUNTIME.procurement_explicit_labels.CONTRACT)
        self.manifest['runtime']['procurement_signed_summary_profile']=RUNTIME.procurement_signed_summary.marker(fixture.contract,RUNTIME.procurement_explicit_labels.CONTRACT,self.manifest['dataset'])
        self.profile=RUNTIME.procurement_category_subtotals
        self.manifest['runtime']['procurement_category_subtotal_profile']=self.profile.marker(fixture.contract,RUNTIME.procurement_explicit_labels.CONTRACT,self.manifest['dataset'])
        self.source,self.receipt=RUNTIME._effective_rule_source(self.manifest,fixture.source)
        self.scope={};exec(self.source,self.scope)
        self.scope['_pcs_previous_view']=lambda tables,*args:(deepcopy(tables),{}, {}, [])
    def table(self):
        return {'sheet':'汇总','kind':'summary','rows':[
            {'row':6,'values':['成功匹配笔数(订单↔入库)',7]},
            {'row':9,'values':['异常类别','笔数','金额差额合计(元)','说明']},
            {'row':10,'values':['数量差异',2]},
            {'row':11,'values':['金额差异',3,-4,'保留原始说明']},
            {'row':12,'values':['未入库订单',4,12,'订单金额合计']},
            {'row':13,'values':['无对应订单入库',5,8,'入库金额合计']},
            {'row':14,'values':['异常合计',99,-4,'金额差异净额；两类未匹配金额需单独核对']},
            {'row':20,'values':['未入库订单金额','1,234.50 元',None,'明细共4笔']},
            {'row':21,'values':['无对应订单入库金额','8.00 元',None,'明细共5笔']}]}
    def view(self,table):return self.scope['_pl_matrix_view']([table],{}, {}, {}, {})
    def test_original_values_locations_notes_and_wrong_subtotal_are_preserved(self):
        table=self.table();before=deepcopy(table);tables,expected,locations,audit=self.view(table)
        self.assertEqual(table,before);self.assertEqual(expected['pcs_literal_category_count'],14)
        rows=tables[0]['rows'];total=[r for r in rows if r['row']==14]
        self.assertEqual([r['values'][1] for r in total],[99,-4])
        self.assertEqual([self.scope['summary_key'](r['values'][0]) for r in total],['pcs_literal_category_count','net_amount'])
        money=next(r for r in rows if r['row']==20)
        self.assertEqual(money['values'][1],'1,234.50');self.assertEqual(money['values'][3],'明细共4笔')
        self.assertEqual(locations[('汇总',14,total[1]['values'][0])]['value_location'],'汇总!C14')
        self.assertEqual(self.receipt['correction_id'],self.profile.PROFILE)
        self.assertFalse(self.receipt['candidate_rewritten']);self.assertTrue(audit)
    def test_ambiguous_missing_hidden_section_and_non_yuan_currency_remain_unresolved(self):
        for change in ['missing','ambiguous','hidden']:
            table=self.table()
            if change=='missing':table['rows'].pop(2)
            elif change=='ambiguous':table['rows'][6]['values'][3]='全部异常订单数'
            else:table['rows'][1]['hidden_columns']=[1]
            _,expected,_,_=self.view(table)
            with self.subTest(change=change):self.assertNotIn('pcs_literal_category_count',expected)
        table=self.table();table['rows'][-1]['values'][1]='8.00 USD'
        rows=self.view(table)[0][0]['rows'];self.assertEqual(next(r for r in rows if r['row']==21)['values'],table['rows'][-1]['values'])
    def test_scope_and_predecessor_drift_are_rejected(self):
        self.assertIsNone(self.profile.marker(self.fixture.contract,'0'*64,self.manifest['dataset']))
        prior=self.receipt['prior_correction'];base=self.source[:-len(self.profile.BRIDGE)]
        self.assertEqual(hashlib.sha256(base.encode()).hexdigest(),prior['effective_source_sha256'])
        with self.assertRaises(ValueError):self.profile.effective_source(self.manifest,self.fixture.source,base+'\n',prior)

if __name__=='__main__':unittest.main()
