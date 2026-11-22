from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from src.e2e.general_reports import markdown, standalone_html, xlsx, score_column, cell_text, _unavailable_row, _source_row


def report():
    return {'title':'<script>not code</script>','dataset':{'id':'fixture'},'scope':{'unit_count':2,'task_run_count':3},
      'presentation':{'sheet_order':['总览','分类对比'],'tables':{
        '总览':{'headers':['模型@Harness','总平均分','用例数'],'rows':[['=bad-formula',0.0,1],['unknown',None,2]],'formats':{'1':'0.00'},'notes':['异常不补零']},
        '分类对比':{'headers':['模型@Harness','总体均分','分类'],'rows':[['unit',88.125,None]],'formats':{'1':'0.00'}}}}}


class GeneralReportExportTests(unittest.TestCase):
    def test_final_attempt_excludes_old_score_and_accepts_failed_score_without_work_root(self):
        core=SimpleNamespace(RESOURCE_FIELDS=[],resolve_file=None,sha256_file=None,
             report_views=SimpleNamespace(checkpoints=lambda *args:{}))
        item={'attempt_id':'exec-new','execution_version':2,'phase':'FAILED','key':'key'}
        unit={'unit_id':'unit','harness':'astronstudio','model':'spark'}
        old={'execution_key':'key','execution_attempt_id':'exec-old','status':'valid','total_score':1,
             'work_root':'/unavailable/historical-scoring'}
        row=_source_row(core,{},item,{'task_id':'task'},unit,{'executions':[old]},Path('unused'))
        self.assertIsNone(row['total_score'])
        self.assertEqual(row['score_status'],'unscored')
        failed={**old,'execution_attempt_id':'exec-new','status':'evaluation_error','error':'judge unavailable'}
        failed.pop('work_root')
        row=_source_row(core,{},item,{'task_id':'task'},unit,{'executions':[failed]},Path('unused'))
        self.assertIsNone(row['total_score'])
        self.assertEqual(row['score_status'],'evaluation_error')

    def unavailable(self, outcome=None, **changes):
        core=SimpleNamespace(RESOURCE_FIELDS=[],resolve_file=None,sha256_file=None,
             report_views=SimpleNamespace(checkpoints=lambda *args:{}))
        item={'attempt_id':'attempt','phase':'FAILED','key':'key',
              'error':{'code':'E2EError','message':'FROZEN_TASK_INPUT_DRIFT'},**changes}
        return _unavailable_row(core,item,{'task_id':'task'},
            {'unit_id':'unit','harness':'astronstudio','model':'spark'},outcome)

    def test_known_predispatch_input_failure_is_infrastructure_without_score_zero(self):
        row=self.unavailable()
        self.assertEqual(row['execution_status'],'infrastructure_error')
        self.assertEqual(row['score_status'],'unscored')
        self.assertEqual(row['invalid_reason'],'FROZEN_TASK_INPUT_DRIFT')
        self.assertIsNone(row['total_score'])

    def test_unproven_or_dispatched_failures_keep_unknown_attribution_and_reason(self):
        for change in [{'dispatch_armed_at':'observed'},{'session_id':'existing'},
                       {'error':{'code':'Other','message':'original error'}}]:
            with self.subTest(change=change):
                row=self.unavailable(**change)
                self.assertEqual(row['execution_status'],'unknown')
                self.assertEqual(row['score_status'],'unscored')
                self.assertIsNotNone(row['invalid_reason'])
                self.assertIsNone(row['total_score'])

    def test_execution_timeout_has_no_evaluator_failure_or_synthetic_score(self):
        reason = 'CONTROLLER_EXECUTION_INCOMPLETE: task_timeout'
        row = self.unavailable(outcome={'execution_not_ready': True, 'error': reason},
                               dispatch_armed_at='observed', error={'message': reason})
        self.assertEqual(row['execution_status'], 'timeout')
        self.assertEqual(row['score_status'], 'unscored')
        self.assertEqual(row['invalid_reason'], reason)
        self.assertIsNone(row['evaluation'])
        self.assertIsNone(row['total_score'])

    def test_zero_null_and_round_half_up_are_distinct(self):
        self.assertEqual(cell_text(0.0,'0.00'),'0.00')
        self.assertEqual(cell_text(None,'0.00'),'-')
        self.assertEqual(cell_text(88.125,'0.00'),'88.13')
        self.assertTrue(score_column('总览','总平均分',1))
        self.assertFalse(score_column('总览','用例数',2))

    def test_exports_preserve_values_and_do_not_execute_candidate_text(self):
        from openpyxl import load_workbook
        data=report()
        self.assertIn('0.00',markdown(data))
        self.assertIn('&lt;script&gt;',markdown(data))
        page=standalone_html(data)
        self.assertNotIn('<script>not code</script>',page)
        self.assertIn('\\u003cscript',page)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'report.xlsx';xlsx(data,path);book=load_workbook(path)
            self.assertEqual(book.sheetnames,['总览','分类对比'])
            sheet=book['总览']
            self.assertEqual(sheet['A2'].value,'=bad-formula')
            self.assertEqual(sheet['A2'].data_type,'s')
            self.assertEqual(sheet['B2'].value,0)
            self.assertEqual(sheet['B3'].value,'-')
            self.assertEqual(sheet.freeze_panes,'B2')
            self.assertTrue(sheet.auto_filter.ref)
            self.assertNotEqual(sheet['B2'].fill.fgColor.rgb,sheet['C2'].fill.fgColor.rgb)
