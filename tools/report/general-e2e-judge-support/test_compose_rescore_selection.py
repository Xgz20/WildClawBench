import copy,unittest
from compose_rescore_selection import plan_selection

class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.source={'scope':{'batch_id':'b','unit_id':'u'},'dataset':{'id':'d','digest':'f'},'task_ids':['a','b'],'tasks':[{'task_id':k,'execution_attempt_id':'exec-'+k,'candidate_sha256':'cand-'+k,'execution_status':'completed','scoring_attempt_id':'old-'+k,'score_status':'valid'} for k in ['a','b']]}
        self.source['tasks'][1]['score_status']='evaluation_error'
        self.replacement=copy.deepcopy(self.source);self.replacement['tasks']=[copy.deepcopy(self.source['tasks'][1])];self.replacement['task_ids']=['b'];self.replacement['tasks'][0].update(scoring_attempt_id='new-b',score_status='valid')
    def test_full_scope_and_order_preserved(self):
        rows=plan_selection(self.source,self.replacement,['b']);self.assertEqual([x['task_id'] for x in rows],['a','b']);self.assertEqual(rows[0],self.source['tasks'][0]);self.assertEqual(self.source['tasks'][1]['score_status'],'evaluation_error')
    def test_explicit_selection_required(self):
        with self.assertRaises(ValueError):plan_selection(self.source,self.replacement,[])
    def test_duplicate_selection_rejected(self):
        with self.assertRaises(ValueError):plan_selection(self.source,self.replacement,['b','b'])
    def test_unselected_replacement_rejected(self):
        with self.assertRaises(ValueError):plan_selection(self.source,self.replacement,['a'])
    def test_changed_dataset_rejected(self):
        self.replacement['dataset']['digest']='other'
        with self.assertRaises(ValueError):plan_selection(self.source,self.replacement,['b'])
    def test_changed_execution_rejected(self):
        self.replacement['tasks'][0]['execution_attempt_id']='other'
        with self.assertRaises(ValueError):plan_selection(self.source,self.replacement,['b'])
    def test_changed_candidate_rejected(self):
        self.replacement['tasks'][0]['candidate_sha256']='other'
        with self.assertRaises(ValueError):plan_selection(self.source,self.replacement,['b'])
    def test_attempt_reuse_rejected(self):
        self.replacement['tasks'][0]['scoring_attempt_id']='old-b'
        with self.assertRaises(ValueError):plan_selection(self.source,self.replacement,['b'])
    def test_null_not_changed_to_zero(self):
        self.replacement['tasks'][0]['score_status']='evaluation_error';self.assertEqual(plan_selection(self.source,self.replacement,['b'])[1]['score_status'],'evaluation_error')

if __name__=='__main__':unittest.main()
