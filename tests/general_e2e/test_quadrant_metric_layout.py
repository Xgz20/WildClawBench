import unittest

from tests.general_e2e.test_local_scoring_runtime import RUNTIME, REPO_ROOT
from eval_general_e2e.datasets.bundle import _strip_codeblock
from tests.general_e2e.frozen_sources import parse_frozen_task_source as _parse_task_source

LAYOUT = RUNTIME.quadrant_metric_layout


class QuadrantMetricLayoutTests(unittest.TestCase):
    def namespace(self):
        _, sections, _ = _parse_task_source(next((REPO_ROOT/'tasks/general_e2e').rglob(LAYOUT.TASK+'.md')))
        source = _strip_codeblock(sections['Automated Checks'])
        profile = LAYOUT.marker({'task_id': LAYOUT.TASK, 'automated_checks': source}, LAYOUT.CONTRACT_SHA, LAYOUT.DATASET)
        self.assertIsNotNone(profile)
        manifest = {'identity': {'task_id': LAYOUT.TASK}, 'digests': {'contract_sha256': LAYOUT.CONTRACT_SHA},
            'dataset': LAYOUT.DATASET, 'runtime': {'quadrant_metric_layout_profile': profile}}
        fixed, receipt = RUNTIME._effective_rule_source(manifest, source)
        namespace = {}
        exec(compile(fixed, '<quadrant-layout>', 'exec'), namespace)
        return namespace,receipt

    def test_visible_bullet_value_before_current_label_and_budget_synonyms(self):
        ns,receipt=self.namespace()
        examples={'touch':'● 18,420 人次  本季触达', 'repeat':'● 23.4% 回访人群占比',
            'days':'● 5.8 天 中位办理时长', 'backlog':'● 312 件 期末积压', 'split':'● 27.6% 复杂件分流占比',
            'spend':'● 62% 已执行预算', 'commit':'● 74% 已承诺未支付'}
        for _,key,label,value,unit in ns['FACTS']:
            with self.subTest(key=key):self.assertTrue(ns['number_fact'](examples[key],label,value,unit))
        self.assertFalse(receipt['candidate_rewritten'])

    def test_old_target_forecast_or_unrelated_number_does_not_supply_current_value(self):
        ns,_=self.namespace()
        for key,text in [('touch','● 18,420 人次 上季触达'),('days','● 5.8 天 目标中位办理时长'),
                         ('spend','● 62% 下季预测已执行预算'),('commit','● 74% 已承诺未支付（目标）'),
                         ('touch','● 999 人次 本季触达；参考18420人次')]:
            _,_,label,value,unit=next(f for f in ns['FACTS'] if f[1]==key)
            with self.subTest(text=text):self.assertFalse(ns['number_fact'](text,label,value,unit))


if __name__=='__main__':unittest.main()
