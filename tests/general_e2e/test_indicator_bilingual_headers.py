from pathlib import Path
import tempfile
import unittest

import openpyxl

from eval_general_e2e.datasets.bundle import _parse_task_source, _strip_codeblock
from src.wildclawbench_grading_core.source_repairs import effective_source, profile_entry


TASK = '02_Office_task_025_indicator_window_rules'
SOURCE = Path(__file__).resolve().parents[2] / (
    'eval_general_e2e/datasets/source-snapshots/general-custom116-v1/tasks/general_e2e/02_Office/'
    + TASK + '.md'
)


class IndicatorBilingualHeaderTests(unittest.TestCase):
    def setUp(self):
        original = _strip_codeblock(_parse_task_source(SOURCE)[1]['Automated Checks'])
        repaired, receipt = effective_source(TASK, original)
        profile = profile_entry(receipt['original_source_sha256'])
        self.assertEqual(receipt['effective_source_sha256'], profile['current_source_sha256'])
        scope = {}
        exec(repaired, scope)
        self.read_tables = scope['read_tables']
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'candidate.xlsx'

    def write_workbook(self, issue_header, *, duplicate=False):
        workbook = openpyxl.Workbook()
        issues = workbook.active
        issues.title = 'issues'
        issues.append(['复核事项'])
        headers = [issue_header, 'source_ref\n依据位置', 'impact\n影响字段']
        values = ['I1', '行情!B4', '影响复核范围']
        if duplicate:
            headers.append('事项编号')
            values.append('I2')
        issues.append(headers)
        issues.append(values)
        summary = workbook.create_sheet('summary')
        summary.append(['summary_key\n统计项', 'summary_value\n统计值', 'note\n说明'])
        summary.append(['review_row_count', 0, '说明'])
        workbook.save(self.path)
        workbook.close()

    def test_bilingual_headers_extract_original_candidate_values_and_locations(self):
        self.write_workbook('issue_id\n事项编号')
        tables, _ = self.read_tables(self.path)
        self.assertEqual(tables['issues'], [{
            'issue_id': 'I1', 'source_ref': '行情!B4', 'impact': '影响复核范围',
            '_row': 3, '_sheet': 'issues', '_hidden': False,
        }])
        self.assertEqual(tables['summary'][0]['summary_value'], 0)
        self.assertEqual(tables['summary'][0]['note'], '说明')

    def test_conflicting_labels_and_duplicate_fields_keep_existing_guards(self):
        self.write_workbook('issue_id\n处理意见')
        tables, _ = self.read_tables(self.path)
        self.assertEqual(tables['issues'], [])
        self.write_workbook('issue_id\n事项编号', duplicate=True)
        with self.assertRaisesRegex(ValueError, 'duplicate_headers:issues'):
            self.read_tables(self.path)
