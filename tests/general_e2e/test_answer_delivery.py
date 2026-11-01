import hashlib
import unittest

from tests.general_e2e.test_local_scoring_runtime import RUNTIME, REPO_ROOT
from eval_general_e2e.datasets.bundle import _parse_task_source, _strip_codeblock

DELIVERY = RUNTIME.answer_delivery


class AnswerDeliveryTests(unittest.TestCase):
    def extractor(self):
        _, sections, _ = _parse_task_source(next((REPO_ROOT/'tasks/general_e2e').rglob(DELIVERY.TASK+'.md')))
        original = _strip_codeblock(sections['Automated Checks'])
        marker = DELIVERY.marker({'task_id': DELIVERY.TASK, 'automated_checks': original}, DELIVERY.CONTRACT_SHA, DELIVERY.DATASET)
        self.assertIsNotNone(marker)
        manifest = {'identity': {'task_id': DELIVERY.TASK}, 'digests': {'contract_sha256': DELIVERY.CONTRACT_SHA},
            'dataset': DELIVERY.DATASET, 'runtime': {'answer_delivery_profile': marker}}
        fixed, receipt = RUNTIME._effective_rule_source(manifest, original)
        namespace = {}
        exec(compile(fixed, '<completed-answer-delivery>', 'exec'), namespace)
        return namespace['_final_answer'], receipt

    def test_full_delivery_is_not_erased_by_bookkeeping_and_corrections_are_preserved(self):
        extract, receipt = self.extractor()
        rows = [{'role':'user','content':'question'}, {'role':'assistant','content':'完整答复：A=10'},
                {'type':'function_call','name':'update_plan'}, {'role':'assistant','content':'更正A=11；处理完毕。'},
                {'type':'task_complete','last_agent_message':'更正A=11；处理完毕。'}]
        answer, proof = extract(rows)
        self.assertIn('A=10', answer)
        self.assertIn('更正A=11', answer)
        self.assertEqual(proof['message_event_indices'], [1,3])
        self.assertEqual(proof['terminal_last_message_sha256'], hashlib.sha256(rows[3]['content'].encode()).hexdigest())
        self.assertFalse(receipt['numeric_decisions_assigned'])

    def test_explicit_final_only_hidden_analysis_and_other_user_turn_are_excluded(self):
        extract, _ = self.extractor()
        rows = [{'role':'assistant','content':'earlier turn'}, {'role':'user','content':'new question'},
                {'role':'assistant','channel':'analysis','content':'secret'},
                {'role':'assistant','content':'draft'}, {'role':'assistant','channel':'final','content':'final'},
                {'type':'task_complete','last_agent_message':'final'}]
        answer, proof = extract(rows)
        self.assertEqual(answer, 'final')
        self.assertEqual(proof['status'], 'explicit_final')

    def test_missing_completion_or_mismatched_receipt_is_infrastructure_failure(self):
        extract, _ = self.extractor()
        with self.assertRaisesRegex(ValueError, 'final answer cannot be determined'):
            extract([{'role':'user','content':'q'}, {'role':'assistant','content':'unfinished'}])
        with self.assertRaisesRegex(ValueError, 'terminal/public-answer mismatch'):
            extract([{'role':'user','content':'q'}, {'role':'assistant','content':'actual'},
                     {'type':'task_complete','last_agent_message':'different'}])

    def test_messages_after_terminal_do_not_enter_the_completed_window(self):
        extract,_=self.extractor()
        answer,proof=extract([{'role':'user','content':'q'}, {'role':'assistant','content':'delivered'},
            {'type':'task_complete','last_agent_message':'delivered'},
            {'role':'assistant','channel':'final','content':'unbound later message'}])
        self.assertIn('delivered',answer)
        self.assertNotIn('unbound later message',answer)

    def test_derived_last_message_flag_does_not_masquerade_as_native_final_channel(self):
        extract,_=self.extractor()
        original=[{'role':'user','content':'q'},
            {'type':'assistant_message','role':'assistant','content':'完整答复A=10','final':False},
            {'type':'assistant_message','role':'assistant','content':'处理完毕','final':True},
            {'type':'task_complete','last_agent_message':'处理完毕'}]
        legacy=RUNTIME._canonical_rule_view(original)
        actual=RUNTIME._canonical_rule_view(original,preserve_native_channels=True)
        self.assertEqual(legacy[2]['channel'],'final')
        self.assertNotIn('channel',actual[2])
        answer,proof=extract(actual)
        self.assertIn('完整答复A=10',answer)
        self.assertIn('处理完毕',answer)
        self.assertEqual(proof['status'],'completed_public_delivery_window')



if __name__ == '__main__':
    unittest.main()
