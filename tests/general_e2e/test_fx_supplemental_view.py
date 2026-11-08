"""Supplemental views remain separate from independently parsed core tables."""
import ast
import hashlib
from pathlib import Path
import tempfile
import unittest

import openpyxl

from eval_general_e2e.datasets.bundle import _parse_task_source, _strip_codeblock
from src.wildclawbench_grading_core.source_repairs import effective_source

ROOT=Path(__file__).resolve().parents[2]
TASK='03_Data_Analysis_task_009_cross_currency_receipts_bank_fees'


class FxSupplementalTests(unittest.TestCase):
    def setUp(self):
        p=ROOT/'eval_general_e2e/datasets/source-snapshots/general-custom70-v4/tasks'/(TASK+'.md')
        _,sections,_=_parse_task_source(p)
        self.original=_strip_codeblock(sections['Automated Checks'])
        self.current,self.receipt=effective_source(TASK,self.original)
        self.scope={};exec(self.current,self.scope)
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'candidate.xlsx'
        self.headers={'分类汇总':['汇总键','收款账户','原币','目标币','对账状态']}

    def write(self,*,core=True,partial=False,unknown=False,formula=False):
        w=openpyxl.Workbook();s=w.active;s.title='差异汇总'
        s.append(['optional view'])
        header=['差异类别','收款账户','原币','目标币','数量（批次/记录）','差额合计','跨期到账金额','涉及编号','补证建议','证据位置']
        if unknown:header[-1]='unknown'
        s.append(header)
        s.append(['fee','account','EUR','CNY',1,'=1+1' if formula else 3.7,'不适用','ID1','check','source1'])
        if core:
            c=w.create_sheet('分类汇总')
            c.append(self.headers['分类汇总'][:-1] if partial else self.headers['分类汇总'])
            c.append(['key','account','EUR','CNY'] if partial else ['key','account','EUR','CNY','known'])
        w.save(self.path);w.close()

    def read(self):
        return self.scope['read_candidate'](self.path,self.headers)

    def test_distinct_extra_view_preserves_every_value_without_becoming_core(self):
        self.write()
        tables,evidence,unknown=self.read()
        self.assertEqual(set(tables),{'分类汇总'})
        self.assertEqual(tables['分类汇总'],[{'汇总键':'key','收款账户':'account','原币':'EUR','目标币':'CNY','对账状态':'known','_row':2}])
        view=evidence['补充差异汇总'][0]
        self.assertEqual(view['header_row'],2)
        self.assertEqual(len(view['rows']),3)
        self.assertEqual(view['rows'][-1]['values'],['fee','account','EUR','CNY',1,3.7,'不适用','ID1','check','source1'])
        self.assertEqual(unknown,[])

    def test_extra_view_cannot_replace_missing_or_incomplete_core(self):
        for core,partial in [(False,False),(True,True)]:
            self.write(core=core,partial=partial)
            with self.assertRaises(self.scope['EvaluationReviewRequired']):self.read()

    def test_unknown_headers_and_uncached_extra_formulas_still_require_review(self):
        self.write(unknown=True)
        with self.assertRaises(self.scope['EvaluationReviewRequired']):self.read()
        self.write(formula=True)
        with self.assertRaisesRegex(self.scope['EvaluationReviewRequired'],'公式缓存缺失'):self.read()

    def test_numeric_grading_prefix_and_frozen_task_identity_stay_unchanged(self):
        self.assertEqual(hashlib.sha256(self.original.encode()).hexdigest(),
            '07928b5aaf640eb0f55173fbe1c3d2fec0530b5b7011e74295f526d08bd1fedd')
        def numeric_body(source):
            grade=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='grade')
            body=[]
            for node in grade.body:
                if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='ed' for t in node.targets):break
                body.append(ast.dump(node))
            return body
        self.assertEqual(numeric_body(self.original),numeric_body(self.current))
        self.assertEqual(effective_source(TASK,self.original+'\n'),(self.original+'\n',None))


if __name__=='__main__':unittest.main()
