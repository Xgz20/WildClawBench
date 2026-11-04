import ast,hashlib,json,tempfile,unittest
from pathlib import Path
import openpyxl
from tests.general_e2e.test_local_scoring_runtime import RUNTIME,REPO_ROOT
from src.utils.task_parser import parse_task_md as _parse_task_md
from eval_general_e2e.datasets.source_history import frozen_v2_task_path

def parse_task_md(path):
    # These regressions exercise the immutable v2 correction profiles.
    return _parse_task_md(frozen_v2_task_path(path))

import sterilization_quote_domain as P

class QuoteFieldDomainTests(unittest.TestCase):
    def fixed(self):
        source=parse_task_md(REPO_ROOT/'tasks/general_e2e/02_Office'/f'{P.TASK}.md')['automated_checks']
        dataset={'id':'general-custom70-v2','digest':'001016f24b4bc20f96733592ea4aabe6a3b8e1e5bfd0dbc9052254ea36430c0e'}
        m={'identity':{'task_id':P.TASK},'digests':{'contract_sha256':P.CONTRACT},'dataset':dataset,
            'runtime':{'sterilization_quote_layout_profile':P.marker({'task_id':P.TASK,'automated_checks':source},P.CONTRACT,dataset)}}
        fixed,r=RUNTIME._effective_rule_source(m,source);return source,fixed,r
    def test_exact_identity_and_all_math_functions_are_unchanged(self):
        source,fixed,r=self.fixed();self.assertEqual(hashlib.sha256(source.encode()).hexdigest(),P.SOURCE)
        manifest=json.loads((REPO_ROOT/'eval_general_e2e/datasets/manifests/general-custom70-v2.json').read_text())
        self.assertEqual(next(t for t in manifest['tasks'] if t['task_id']==P.TASK)['digests']['scoring_contract_sha256'],P.CONTRACT)
        before,after=ast.parse(source),ast.parse(fixed)
        for node in before.body:
            if isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.name not in {'role','grade'}:
                other=next(n for n in after.body if isinstance(n,type(node)) and n.name==node.name)
                self.assertEqual(ast.dump(node),ast.dump(other))
        self.assertFalse(r['numeric_decisions_assigned']);self.assertFalse(r['candidate_rewritten'])
    def test_explicit_country_keeps_wrong_and_conflicting_values_without_selecting_gt(self):
        _,fixed,_=self.fixed();scope={};exec(compile(fixed,'<quote-domain>','exec'),scope)
        for label,role in P.HEADINGS.items():self.assertEqual(scope['role'](label),role)
        self.assertIsNone(scope['role']('Possibly estimated value'))
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'candidate.xlsx'
            for countries in [['Lebanon'],['Jordan'],['Lebanon','Jordan']]:
                w=openpyxl.Workbook();s=w.active;s.title='Quotation';s['A1']='Destination country:';s['A2']=countries[0]
                if len(countries)>1:s['C1']='Country of destination';s['D1']=countries[1]
                t=w.create_sheet('Transport Comparison');t.append(['Destination','Beirut International Airport (BEY)']);w.save(path);w.close()
                book=scope['Book'](path)
                try:
                    values=scope['_ge2e_quote_country_values'](book)
                    self.assertEqual([v['value'] for v in values],countries)
                finally:book.w.close();book.cache.close()
