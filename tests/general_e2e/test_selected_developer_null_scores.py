from pathlib import Path
import importlib.util
import sys
import unittest

SCRIPTS=Path(__file__).resolve().parents[2]/'tools/report/skills/general-e2e/run-general-e2e/scripts'
sys.path.insert(0,str(SCRIPTS))
SPEC=importlib.util.spec_from_file_location('selected_developer_null_tested',SCRIPTS/'selected_developer_bundle.py')
EXPORT=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(EXPORT)

class SelectedNullScoreTests(unittest.TestCase):
    def check_result(self, valid, total, status, report_total):
        EXPORT.validate_selected_score_result({'result':{'valid':valid,'total_score':total}},
            {'score_status':status,'total_score':report_total})

    def test_selected_evaluation_error_and_valid_zero_are_preserved(self):
        self.check_result(False,None,'evaluation_error',None)
        self.check_result(True,0.0,'valid',0.0)
        self.check_result(True,0.75,'valid',0.75)

    def test_status_and_total_drift_are_rejected(self):
        for args in [(False,None,'valid',None),(True,0,'evaluation_error',0),
                     (False,0,'evaluation_error',0),(False,None,'unscored',None),
                     (True,None,'valid',None),(True,0.75,'valid',0.5),
                     (1,0.75,'valid',0.75),(True,True,'valid',True)]:
            with self.subTest(args=args),self.assertRaises(AssertionError):self.check_result(*args)

if __name__=='__main__':unittest.main()
