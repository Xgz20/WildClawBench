"""Regression tests for chart helper columns alongside a Data011 summary."""

import importlib.util
from pathlib import Path
import unittest


MODULE = Path(__file__).resolve().parents[2] / (
    "tools/report/skills/general-e2e/score-general-e2e/scripts/funnel_summary_tables.py"
)
SPEC = importlib.util.spec_from_file_location("funnel_summary_tables_test", MODULE)
PROFILE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROFILE)


class SummaryTableTests(unittest.TestCase):
    def test_helper_blank_cannot_overwrite_required_business_value(self):
        fields = PROFILE.REQUIRED_FIELDS["留存汇总"]
        headers = [*fields, "", "留存周期", "自然访问"]
        row = ["内容推荐", "D1", 660, 357, 0, 0, 0.54, None, None, None]
        selected = PROFILE._ge2e_funnel_summary_columns(headers, fields)
        self.assertEqual(dict(zip(headers, row))["留存周期"], None)
        self.assertEqual({headers[i]: row[i] for i in selected}["留存周期"], "D1")
        helper_only_row = [None] * 8 + ["D7", 0.35]
        self.assertFalse(any(helper_only_row[i] is not None for i in selected))

    def test_does_not_choose_between_competing_or_duplicate_business_tables(self):
        fields = PROFILE.REQUIRED_FIELDS["漏斗汇总"]
        self.assertEqual(PROFILE._ge2e_funnel_summary_columns([*fields, "", *fields], fields), ())
        self.assertEqual(PROFILE._ge2e_funnel_summary_columns([*fields, "步骤名称"], fields), ())

    def test_keeps_original_shape_without_duplicate_required_heading(self):
        fields = PROFILE.REQUIRED_FIELDS["漏斗汇总"]
        headers = [*fields, "", "图表数据"]
        self.assertEqual(PROFILE._ge2e_funnel_summary_columns(headers, fields), tuple(range(len(headers))))


if __name__ == "__main__":
    unittest.main()
