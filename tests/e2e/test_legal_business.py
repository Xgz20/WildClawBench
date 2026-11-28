import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('legal_business', ROOT / 'tools/report/skills/general-e2e/report-general-e2e/scripts/legal_business.py')
legal = importlib.util.module_from_spec(spec); spec.loader.exec_module(legal)
POLICY = json.loads((ROOT / 'tools/report/data/legal_acceptance_policy.json').read_text())


class LegalBusinessTests(unittest.TestCase):
    def setUp(self):
        self.row = {'unit_id':'u', 'task_id':POLICY['dataset']['tasks'][0]['task_id'], 'total_score':.93,
            'score_status':'valid', 'execution_status':'completed', 'execution_attempt_id':'exec1',
            'scoring_attempt_id':'score1', 'lineage':{'score_sha256':'a'*64},
            'checkpoints':{'values':{m['key']:1 for m in POLICY['metrics']}}}
        self.data = {'dataset':{k: POLICY['dataset'][k] for k in ('id','digest')}, 'units':[{'unit_id':'u'}], 'tasks':[self.row]}

    def review(self, status='none', actor='1', **changes):
        return {'task_id':self.row['task_id'], 'execution_attempt_id':'exec1', 'scoring_attempt_id':'score1',
            'score_sha256':'a'*64, 'policy_sha256':'b'*64, 'status':status,
            'error_types':['fabricated_law_or_fact'] if status=='present' else [],
            'evidence':[{'path':'delivery.docx','locator':'第2页核验段落'}],
            'reviewer':{'id':actor,'name':'复核人','role':'legal'}, 'reviewed_at':'2026-11-28T10:00:00+08:00', **changes}

    def build(self, reviews=None):
        return legal.build(self.data,POLICY,reviews or [],{'u':'unit'},'b'*64)

    def test_partial_coverage_is_not_acceptance_and_unknown_is_not_zero(self):
        result = self.build(); unit = result['units'][0]
        self.assertEqual((unit['valid_scores'],unit['dataset_tasks'],unit['accepted'],unit['not_selected']),(1,30,0,29))
        self.assertEqual(unit['pending_review'],1); self.assertIsNone(unit['serious_errors_total'])
        self.assertEqual(result['categories'][0]['task_count'],5)
        self.assertEqual(result['metrics'][0]['known'],1)
        self.assertEqual(result['cases'][0]['quality_score'],.93)

    def test_none_accepts_present_vetoes_and_reset_requires_review(self):
        self.assertEqual(self.build([self.review()])['cases'][0]['acceptance_status'],'accepted')
        result = self.build([self.review(),self.review('present',actor='2')])
        self.assertEqual(result['cases'][0]['acceptance_status'],'serious_error')
        self.assertEqual(result['units'][0]['serious_error_type_counts'],{'fabricated_law_or_fact':1})
        reset=self.review('unreviewed',reviewed_at='2026-11-28T03:00:00Z')
        self.assertEqual(self.build([self.review(),reset])['cases'][0]['acceptance_status'],'pending_review')

    def test_zero_failed_and_missing_metric_remain_distinct(self):
        self.row['total_score']=0
        self.assertEqual(self.build([self.review()])['cases'][0]['acceptance_status'],'quality_below_threshold')
        self.row['score_status']='evaluation_error'
        result=self.build();self.assertEqual(result['cases'][0]['acceptance_status'],'evaluation_error')
        self.assertIsNone(result['metrics'][0]['mean']);self.assertIsNone(result['units'][0]['quality_mean'])

    def test_every_round_must_be_reviewed_and_meet_threshold(self):
        child=copy.deepcopy(self.row); child.update(execution_attempt_id='exec2',scoring_attempt_id='score2',lineage={'score_sha256':'c'*64})
        self.data['tasks']=[{**self.row,'rounds':[self.row,child]}]
        self.assertEqual(self.build([self.review()])['cases'][0]['acceptance_status'],'pending_review')
        other=self.review(execution_attempt_id='exec2',scoring_attempt_id='score2',score_sha256='c'*64)
        self.assertEqual(self.build([self.review(),other])['cases'][0]['acceptance_status'],'accepted')
        child['total_score']=.79
        self.assertEqual(self.build([self.review(),other])['cases'][0]['acceptance_status'],'quality_below_threshold')

    def test_stale_forged_missing_and_conflicting_reviews_reject(self):
        for change in ({'policy_sha256':'d'*64},{'score_sha256':'c'*64},{'execution_attempt_id':'old'},
                       {'evidence':[]},{'error_types':[{}]}):
            with self.subTest(change=change), self.assertRaises(ValueError): self.build([self.review(**change)])
        with self.assertRaisesRegex(ValueError,'CONFLICT'): self.build([self.review(),self.review('present')])
        self.data['dataset']['digest']='d'*64
        with self.assertRaisesRegex(ValueError,'DRIFT'): self.build()

    def test_units_are_not_pooled(self):
        self.data['units'].append({'unit_id':'v'})
        self.data['tasks'].append({**self.row,'unit_id':'v','task_id':POLICY['dataset']['tasks'][5]['task_id'],'lineage':{}})
        result=self.build(); self.assertEqual([u['valid_scores'] for u in result['units']],[1,1])
        self.assertEqual(result['scope']['observed_unique_tasks'],2)

if __name__=='__main__': unittest.main()
