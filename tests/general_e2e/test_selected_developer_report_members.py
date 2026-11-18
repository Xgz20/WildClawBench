from pathlib import Path
import importlib.util
import sys
import unittest

SCRIPTS=Path(__file__).resolve().parents[2]/'tools/report/skills/general-e2e/run-general-e2e/scripts'
sys.path.insert(0,str(SCRIPTS))
SPEC=importlib.util.spec_from_file_location('selected_developer_report_members_tested',SCRIPTS/'selected_developer_bundle.py')
EXPORT=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(EXPORT)

class SelectedDeveloperReportMembersTests(unittest.TestCase):
    def test_native_report_does_not_require_an_unproduced_optional_index(self):
        data={'artifact_filenames':{'excel':'result.xlsx','leader_markdown':'leader.md','audit_markdown':'audit.md'}}
        required={'general_e2e_report_data.json','result.xlsx','leader.md','audit.md','composite-report-receipt.json'}
        self.assertEqual(set(EXPORT.report_artifact_names(data,required)),required)
        optional={'data/score-verification-index.json','receipts/report-receipt.json','general_e2e_leader_data.json'}
        self.assertEqual(set(EXPORT.report_artifact_names(data,required|optional)),required|optional)
        with self.assertRaisesRegex(AssertionError,'canonical report artifact missing'):
            EXPORT.report_artifact_names(data,required-{'result.xlsx'})
        data['run_audit']={'verified':True}
        with self.assertRaisesRegex(AssertionError,'canonical report artifact missing'):
            EXPORT.report_artifact_names(data,required)
        self.assertIn('data/run-audit.json',EXPORT.report_artifact_names(data,required|{'data/run-audit.json'}))

if __name__=='__main__':unittest.main()
