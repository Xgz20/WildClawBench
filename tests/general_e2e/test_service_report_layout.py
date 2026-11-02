from copy import deepcopy
import unittest

from tests.general_e2e.test_local_scoring_runtime import RUNTIME, REPO_ROOT
from eval_general_e2e.datasets.bundle import _strip_codeblock
from tests.general_e2e.frozen_sources import parse_frozen_task_source as _parse_task_source

LAYOUT = RUNTIME.service_report_layout


class ServiceReportLayoutTests(unittest.TestCase):
    def namespace(self):
        _, sections, _ = _parse_task_source(next((REPO_ROOT/'tasks/general_e2e').rglob(LAYOUT.TASK+'.md')))
        original = _strip_codeblock(sections['Automated Checks'])
        marker = LAYOUT.marker({'task_id': LAYOUT.TASK, 'automated_checks': original}, LAYOUT.CONTRACT_SHA, LAYOUT.DATASET)
        self.assertIsNotNone(marker)
        manifest = {'identity': {'task_id': LAYOUT.TASK}, 'digests': {'contract_sha256': LAYOUT.CONTRACT_SHA},
            'dataset': LAYOUT.DATASET, 'runtime': {'service_report_layout_profile': marker}}
        fixed, receipt = RUNTIME._effective_rule_source(manifest, original)
        ns = {}
        exec(compile(fixed, '<service-layout>', 'exec'), ns)
        return ns, original, fixed, receipt, manifest

    def sample(self):
        return '''# Report
| 工单 | 状态（进展） | 下一步动作 | 要核实的结果 |
| --- | --- | --- | --- |
| TCK-CS-3101 | resolved（100%） | 复核 | 正常 |

| 归一事项标识 | 受理编号 | 日报状态 | 进展 | 采用更新时间 |
| --- | --- | --- | --- | --- |
| east:TCK-CS-3101 | TCK-CS-3101 | resolved | 100% | 2026-05-18 17:40:03 |

| record_id | source_row | 归一事项标识 | occurred_at | event_type |
| --- | --- | --- | --- | --- |
| R-003 | row-003 | east:TCK-CS-3101 | 2026-05-18 17:40:03 | status_update |
'''

    def test_followup_is_not_duplicate_ticket_and_explicit_appendix_is_joined(self):
        ns, _, _, receipt, _ = self.namespace()
        detail, _, _, audit = ns['parse_report'](self.sample(), include_audit=True)
        self.assertEqual(len(detail), 1)
        self.assertEqual(len(audit), 1)
        links = ns['_service_bind_event_appendix'](detail, audit, {}, {'TCK-CS-3101': 'east:TCK-CS-3101'})
        self.assertEqual(detail[0]['records'], 'R-003')
        self.assertEqual(detail[0]['sources'], 'row-003')
        self.assertEqual(len(links), 1)
        self.assertFalse(receipt['candidate_rewritten'])

    def test_missing_or_duplicate_main_and_missing_source_are_not_guessed(self):
        ns, _, _, _, _ = self.namespace()
        detail, _, _, audit = ns['parse_report'](self.sample(), include_audit=True)
        for mains, events in [([], audit), ([deepcopy(detail[0]), deepcopy(detail[0])], audit),
                              (detail, [{**audit[0], 'sources': ''}])]:
            self.assertEqual(ns['_service_bind_event_appendix'](mains, events, {}, {'TCK-CS-3101': 'east:TCK-CS-3101'}), [])

    def test_legacy_profile_is_opt_in_and_wrong_dataset_fails(self):
        _, original, _, _, manifest = self.namespace()
        self.assertEqual(RUNTIME._effective_rule_source({}, original), (original, None))
        bad = deepcopy(manifest)
        bad['dataset']['digest'] = '0'*64
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError, 'SERVICE_REPORT_LAYOUT_PROFILE_MISMATCH'):
            RUNTIME._effective_rule_source(bad, original)

    def test_explanatory_headline_counts_are_read_without_inference_or_forecasts(self):
        ns,original,_,_,manifest=self.namespace()
        text='''- 记录量：报告日内符合服务台与通道的更新条数＝**50** 条。
- 工单量：按归一后事项标识（normalized_ticket_key，含 key_aliases 归并）计数＝**19** 件。
'''
        _,metrics,_=ns['parse_report'](text)
        self.assertTrue(metrics['candidate'])
        self.assertTrue(metrics['unique'])
        self.assertTrue(all(x['value']==50 for x in metrics['candidate']))
        self.assertTrue(all(x['value']==19 for x in metrics['unique']))
        _,bad,_=ns['parse_report']('- 工单量：预计明日计数＝**19** 件。')
        self.assertFalse(bad.get('unique'))
        legacy=deepcopy(manifest)
        legacy['runtime']['service_report_layout_profile']['profile']=LAYOUT.LEGACY_PROFILE
        fixed,receipt=RUNTIME._effective_rule_source(legacy,original)
        self.assertNotIn('def _service_headline_counts',fixed)
        self.assertEqual(receipt['correction_id'],LAYOUT.LEGACY_PROFILE)


if __name__ == '__main__':
    unittest.main()
