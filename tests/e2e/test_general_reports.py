from pathlib import Path
import tempfile
import unittest
from src.e2e.general_reports import markdown, standalone_html, xlsx, score_column, cell_text


def report():
    return {'title':'<script>not code</script>','dataset':{'id':'fixture'},'scope':{'unit_count':2,'task_run_count':3},
      'presentation':{'sheet_order':['总览','分类对比'],'tables':{
        '总览':{'headers':['模型@Harness','总平均分','用例数'],'rows':[['=bad-formula',0.0,1],['unknown',None,2]],'formats':{'1':'0.00'},'notes':['异常不补零']},
        '分类对比':{'headers':['模型@Harness','总体均分','分类'],'rows':[['unit',88.125,None]],'formats':{'1':'0.00'}}}}}


class GeneralReportExportTests(unittest.TestCase):
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
