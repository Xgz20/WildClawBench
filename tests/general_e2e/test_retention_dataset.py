"""Guard the retention task's discriminating data and execution boundary."""
from pathlib import Path
import csv
import datetime as dt
import hashlib
import json
import runpy
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

from eval_general_e2e.datasets.bundle import _task_contracts
from tools.report.lib.eval_dataset.task_files import parse_task_document

ROOT = Path(__file__).resolve().parents[2]
ID = 'general_hard_data_analysis_task_005_retention_cohort'
WORK = ROOT / 'datasets/general-hard/workspace/data_analysis' / ID
TASK = ROOT / 'datasets/general-hard/tasks/data_analysis' / (ID + '.md')


class RetentionDatasetTests(unittest.TestCase):
    def test_source_receipts_expose_wrong_day_bucketing_without_changing_business_truth(self):
        expected = json.loads((WORK / 'gt/expected.json').read_text(encoding='utf-8'))
        protected = json.loads((WORK / 'gt/protected_received_v2.json').read_text(encoding='utf-8'))
        source = WORK / 'exec/events.csv'
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), protected['events.csv'])
        with source.open(encoding='utf-8', newline='') as stream:
            records = {r['record_id']: r for r in csv.DictReader(stream)}
        active = [records[r['record_id']] for r in expected['audit'] if r['decision'] == 'active']
        timezone = dt.timezone(dt.timedelta(hours=8))
        def day(value):
            return dt.datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(timezone).date().isoformat()
        actual = {(r['user_id'].strip().upper(), day(r['occurred_at'])) for r in active}
        receipt = {(r['user_id'].strip().upper(), day(r['received_at'])) for r in active}
        self.assertEqual(actual, {(r['user_id'], r['activity_date']) for r in expected['user_days']})
        self.assertNotEqual(actual, receipt)
        self.assertEqual(sum(day(r['occurred_at']) != day(r['received_at']) for r in active), 12)
        self.assertTrue(any(day(r['occurred_at']) == '2026-09-15' and day(r['received_at']) > '2026-09-15' for r in active))

    def test_complete_static_workbook_is_a_valid_alternative_to_formulas(self):
        source = WORK / 'gt/reference/results/cohorts.xlsx'
        ns = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
        with tempfile.TemporaryDirectory() as tmp:
            static = Path(tmp) / 'complete-static.xlsx'
            with zipfile.ZipFile(source) as incoming, zipfile.ZipFile(static, 'w') as outgoing:
                for item in incoming.infolist():
                    data = incoming.read(item)
                    if item.filename.startswith('xl/worksheets/') and item.filename.endswith('.xml'):
                        root = ET.fromstring(data)
                        for cell in root.iter(ns + 'c'):
                            formula = cell.find(ns + 'f')
                            if formula is not None:
                                cell.remove(formula)
                        data = ET.tostring(root)
                    outgoing.writestr(item, data)
            api = runpy.run_path(str(WORK / 'gt/h021_ledger.py'))
            expected = json.loads((WORK / 'gt/expected.json').read_text(encoding='utf-8'))
            contract = json.loads((WORK / 'gt/runtime_contract.json').read_text(encoding='utf-8'))
            source_map = json.loads((WORK / 'gt/source_bindings.json').read_text(encoding='utf-8'))['records']
            result = api['ledger'](api['T']['read_book'](static), expected, contract, source_map)
            self.assertTrue(result['complete_detail'])
            for key in ['summary_score', 'members_score', 'user_day_score', 'evidence_score', 'boundary_score']:
                self.assertEqual(result[key], 1.0, key)

    def test_scoring_runtime_and_private_helpers_are_not_exposed_in_execution_contract(self):
        doc = parse_task_document(TASK)
        self.assertFalse(doc.frontmatter_error)
        execution, scoring = _task_contracts(ID, doc.metadata, doc.sections, {'sha256': 'a' * 64}, {'sha256': 'b' * 64})
        self.assertNotIn('scoring_runtime', execution)
        self.assertEqual(scoring['scoring_runtime'], {'office': True, 'html_render': True})
        self.assertNotIn('expected.json', json.dumps(execution))
        self.assertNotIn('gt/grader.py', json.dumps(execution))
        self.assertIn('gt/grader.py', scoring['automated_checks'])


if __name__ == '__main__':
    unittest.main()
