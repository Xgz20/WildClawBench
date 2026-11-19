import ast,hashlib,json,unittest
from copy import deepcopy
from eval_general_e2e.datasets.bundle import _parse_task_source,_strip_codeblock
from tests.general_e2e.test_local_scoring_runtime import RUNTIME,REPO_ROOT

P=RUNTIME.learning_summary_tables
class LearningSummaryTableTests(unittest.TestCase):
    def source(self):
        data=json.loads((REPO_ROOT/'eval_general_e2e/datasets/manifests/general-custom70-v6.json').read_text());task=next(t for t in data['tasks'] if t['task_id']==P.TASK)
        return _strip_codeblock(_parse_task_source(REPO_ROOT/task['source']['task_path'])[1]['Automated Checks'])
    def test_precise_scope_reader_only_and_original_numeric_code_unchanged(self):
        source=self.source();self.assertEqual(hashlib.sha256(source.encode()).hexdigest(),P.SOURCE)
        c={'task_id':P.TASK,'automated_checks':source};m={'identity':{'task_id':P.TASK},'digests':{'contract_sha256':P.CONTRACT},'dataset':P.DATASET,'runtime':{}}
        self.assertEqual(P.effective_source(m,source,source,None),(source,None))
        m['runtime'][P.RUNTIME_KEY]=P.marker(c,P.CONTRACT,P.DATASET);fixed,receipt=RUNTIME._effective_rule_source(m,source)
        self.assertFalse(receipt['candidate_rewritten']);self.assertFalse(receipt['numeric_decisions_assigned']);self.assertFalse(receipt['rubric_and_weights_changed'])
        old=ast.parse(source);new=ast.parse(fixed)
        oldnodes={n.name:ast.dump(n) for n in old.body if isinstance(n,(ast.FunctionDef,ast.ClassDef))};newnodes={n.name:ast.dump(n) for n in new.body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
        for name in oldnodes:
            if P.funnel.OLD_READER not in ast.get_source_segment(source,next(n for n in old.body if getattr(n,'name',None)==name)):
                self.assertEqual(oldnodes[name],newnodes[name],name)
        self.assertIsNone(P.marker(c,'0'*64,P.DATASET));self.assertIsNone(P.marker({**c,'automated_checks':source+'\n'},P.CONTRACT,P.DATASET))
        self.assertIsNone(P.marker(c,P.CONTRACT,{**P.DATASET,'digest':'0'*64}))
    def test_duplicate_chart_helpers_keep_numeric_step_and_exact_retention_key(self):
        helper=P.funnel._ge2e_funnel_summary_columns
        fields=P.funnel.REQUIRED_FIELDS['漏斗汇总'];heads=[*fields,'','步骤','自然访问'];row=['内容推荐',2,'有效学习',10,8,9,.8,.8,None,None,None]
        selected=helper(heads,fields);self.assertEqual(dict(zip(heads,row))['步骤'],None)
        self.assertEqual({heads[i]:row[i] for i in selected}['步骤'],2)
        fields=P.funnel.REQUIRED_FIELDS['留存汇总'];heads=[*fields,'','留存周期','自然访问'];row=['内容推荐','W4',10,5,0,0,.5,None,None,None]
        self.assertEqual({heads[i]:row[i] for i in helper(heads,fields)}['留存周期'],'W4')
        self.assertEqual(helper([*fields,'',*fields],fields),())
    def test_standalone_orchestrator_and_score_copies_are_identical(self):
        base=REPO_ROOT/'tools/report/skills/general-e2e';self.assertEqual((base/'score-general-e2e/scripts/learning_summary_tables.py').read_bytes(),(base/'orchestrate-general-e2e/scripts/learning_summary_tables.py').read_bytes())

if __name__=='__main__':unittest.main()
