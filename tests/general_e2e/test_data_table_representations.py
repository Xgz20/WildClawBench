from copy import deepcopy
from datetime import datetime, timezone, timedelta
import ast
import unittest

from tests.general_e2e.test_local_scoring_runtime import RUNTIME, REPO_ROOT
from eval_general_e2e.datasets.bundle import _parse_task_source, _strip_codeblock

REP = RUNTIME.data_table_representations


class DataTableRepresentationTests(unittest.TestCase):
    def helpers(self, task):
        _, sections, _ = _parse_task_source(next((REPO_ROOT/'tasks/general_e2e').rglob(task+'.md')))
        source = _strip_codeblock(sections['Automated Checks'])
        entry = REP.REGISTRY[task]
        marker = REP.marker({'task_id': task, 'automated_checks': source}, entry[0], REP.DATASET)
        self.assertIsNotNone(marker)
        manifest = {'identity': {'task_id': task}, 'digests': {'contract_sha256': entry[0]}, 'dataset': REP.DATASET,
                    'runtime': {'data_table_representation_profile': marker}}
        fixed, receipt = RUNTIME._effective_rule_source(manifest, source)
        ns = {}
        exec(compile(fixed, '<field-representations>', 'exec'), ns)
        return ns, source, fixed, receipt, manifest

    def test_date_time_representation_only_in_date_field(self):
        task = next(t for t,e in REP.REGISTRY.items() if e[2]=='date')
        ns, source, fixed, _, manifest = self.helpers(task)
        eq = ns['eq']
        for value in ('2026-08-01 08:00:00', '2026-08-01T08:00:00+08:00', datetime(2026,8,1,8)):
            self.assertTrue(eq(value, '2026-08-01', '起点日期'))
        self.assertFalse(eq('2026-08-02 08:00:00', '2026-08-01', '起点日期'))
        self.assertFalse(eq('2026-08-01 08:00:00', '2026-08-01', '步骤1事件'))
        self.assertFalse(eq('2026-08-01T23:00:00Z', '2026-08-01', '起点日期'))
        self.assertFalse(eq('not-a-date', '2026-08-01', '起点日期'))
        self.assertTrue(eq('50%', .5, '步骤转化率'))
        self.assertFalse(eq('50.01%', .5, '步骤转化率'))
        self.assertEqual(RUNTIME._effective_rule_source({}, source), (source, None))

    def test_attribution_labels_do_not_collapse_unknown_reasons_or_channels(self):
        for task, entry in REP.REGISTRY.items():
            if entry[2] in ('date','voucher','learning_steps'):
                continue
            ns, _, _, receipt, _ = self.helpers(task)
            eq = ns['equal']
            self.assertTrue(eq('已归因', '触点归因', '归因状态'))
            self.assertFalse(eq('已归因', '触点归因', '渠道'))
            self.assertFalse(eq('未知归因', '缺客户编号', '归因状态'))
            self.assertFalse(eq('未知归因', '无合格触点', '归因状态'))
            self.assertFalse(eq('直接访问', '触点归因', '归因状态'))
            self.assertEqual(eq('核销渠道', '核销码优先', '归因状态'), entry[2]=='redemption')
            self.assertFalse(receipt['candidate_rewritten'])

    def test_verified_voucher_label_is_not_a_generic_state_rewrite(self):
        task=next(t for t,e in REP.REGISTRY.items() if e[2]=='voucher')
        ns,_,_,_,_=self.helpers(task)
        self.assertTrue(ns['_ge2e_field_representation']('已核凭证','已提供','凭证状态'))
        self.assertFalse(ns['_ge2e_field_representation']('已核凭证','未提供','凭证状态'))
        self.assertIsNone(ns['_ge2e_field_representation']('已核凭证','已提供','匹配状态'))
        self.assertIsNone(ns['_ge2e_field_representation']('已匹配','确认零额','匹配状态'))

    def test_learning_step_names_follow_the_public_business_definition_only(self):
        task=next(t for t,e in REP.REGISTRY.items() if e[2]=='learning_steps')
        ns,_,_,_,_=self.helpers(task)
        self.assertTrue(ns['eq']('有效学习','学习','步骤名称'))
        self.assertTrue(ns['eq']('测验通过','测验','步骤名称'))
        self.assertFalse(ns['eq']('测验通过','测验','标准事件'))
        self.assertFalse(ns['eq']('达成','完整观察','漏斗状态'))


if __name__ == '__main__':
    unittest.main()
