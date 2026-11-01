from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[2]/'tools/report/skills/general-e2e/report-general-e2e/scripts/report_display.py'
SPEC = importlib.util.spec_from_file_location('pending_review_display_test', PATH)
DISPLAY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DISPLAY)


class PendingReviewPresentationTests(unittest.TestCase):
    def fixture(self):
        rows = [{'unit_id':'u','task_id':task,'score_status':status,'total_score':score,'execution_status':'completed'}
                for task,status,score in [('zero','valid',0),('valid','valid',.8),('pending','evaluation_error',None),('unscored','unscored',None)]]
        data = {'tasks':rows,'display_overrides':{'pending_review':[{'task_id':'pending','reason':'参考证据不足'}]}}
        view = {'score_coverage':{'note':'old','valid_task_sets_identical':True},'unit_labels':{'u':'Model@Harness'},
            'tables':{'总览':{'headers':['模型','评测异常数'],'rows':[['Model@Harness',1]],'notes':['old']}},
            'case_comparison':{'headers':['分类','用例ID','Model@Harness 得分'],
                'rows':[['c','pending','总分：-（evaluation_error）']],'notes':[]},
            'score_details':{'detail':{'headers':['分类','用例ID','总得分','评分状态'],
                'rows':[['c','pending',None,'evaluation_error']],'notes':[]}},'score_detail_sheet_names':{'u':'detail'}}
        return data, view

    def test_explicit_pending_keeps_null_and_original_error_status_and_real_zero(self):
        data, view = self.fixture()
        original = deepcopy(data)
        result = DISPLAY.apply_pending_review(data, view)
        self.assertEqual(data, original)
        self.assertIn('2项有效、1项待核验', result['score_coverage']['note'])
        self.assertIn('包含1项真实零分', result['score_coverage']['note'])
        self.assertEqual(result['tables']['总览']['headers'][1], '待核验数')
        self.assertIsNone(result['score_details']['detail']['rows'][0][2])
        self.assertEqual(result['score_details']['detail']['rows'][0][3], '待核验（参考证据不足）')
        self.assertIn('待核验',result['case_comparison']['rows'][0][2])

    def test_cannot_hide_valid_zero_or_unscored_or_unknown_task(self):
        for task in ('zero','valid','unscored','unknown'):
            data, view = self.fixture()
            data['display_overrides']['pending_review'][0]['task_id']=task
            with self.assertRaises(ValueError):DISPLAY.apply_pending_review(data,view)

    def test_other_errors_are_not_renamed_as_pending(self):
        data,view=self.fixture()
        data['tasks'].append({'unit_id':'u','task_id':'error','score_status':'evaluation_error','total_score':None,'execution_status':'completed'})
        result=DISPLAY.apply_pending_review(data,view)
        self.assertEqual(result['tables']['总览']['headers'][1],'评测异常/待核验数')
        self.assertIn('1项其他评测异常',result['score_coverage']['note'])


if __name__=='__main__':unittest.main()
