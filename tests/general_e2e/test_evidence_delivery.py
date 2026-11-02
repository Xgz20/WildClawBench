from pathlib import Path
import contextlib
import copy
import importlib.util
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile

from tests.general_e2e.test_report_general_e2e import Fixture, REPORT, write_json, sha256

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / 'tools/report/skills/general-e2e/run-general-e2e/scripts'
SCRIPTS = ROOT / 'tools/report/skills/general-e2e/report-general-e2e/scripts'
sys.path.insert(0, str(SCRIPTS))
from seal_report import seal_report

spec = importlib.util.spec_from_file_location('developer_delivery_tested', RUN / 'build_developer_bundle.py')
BUNDLE = importlib.util.module_from_spec(spec)
spec.loader.exec_module(BUNDLE)


class SupplementFixture(Fixture):
    def execution(self, task_id, attempt, index, resource_path):
        selected = super().execution(task_id, attempt, index, resource_path)
        selected['evidence']['trace_index_path'] = None
        selected['evidence']['transcript_path'] = None
        if index == 0:
            original = copy.deepcopy(selected)
            original['evidence']['completeness'] = 'partial'
            original['evidence']['missing'] = ['synthetic-original-gap']
            write_json(self.target / 'unit/evidence/tasks' / task_id / attempt / 'execution-record.json', original)
        return selected


class EvidenceDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fixture = SupplementFixture(self.root)

    def report(self):
        validated = REPORT.validate_batch_inputs(self.fixture.batch)
        report = self.fixture.batch / 'reports/new-report'
        report.mkdir(parents=True)
        REPORT.write_developer_indexes(validated, report)
        data = REPORT.aggregate(validated, '2026-10-22T00:00:00Z')
        data['artifact_filenames'] = {'excel': 'synthetic.xlsx'}
        write_json(report / 'general_e2e_report_data.json', data)
        (report / 'synthetic.xlsx').write_bytes(b'synthetic frozen workbook')
        write_json(report / 'composite-report-receipt.json', {
            'source_json_sha256': sha256(report / 'general_e2e_report_data.json'),
            'excel_sha256': sha256(report / 'synthetic.xlsx'),
            'composite_import_index_sha256': sha256(report / 'developer-source-index.json'),
        })
        return report

    def test_indexes_select_score_bound_record_and_preserve_initial_history(self):
        initial = next((self.fixture.target / 'unit/evidence/tasks').rglob('execution-record.json'))
        before = initial.read_bytes()
        report = self.report()
        rows = json.loads((report / 'developer-task-index.json').read_text())['selected_tasks']
        row = next(r for r in rows if r['task_id'] == 'task-zero')
        self.assertIn('scoring/execution-records/', row['execution_record'])
        self.assertEqual(Path(row['original_execution_record']), initial.resolve())
        self.assertNotEqual(row['execution_record_sha256'], row['original_execution_record_sha256'])
        self.assertEqual(initial.read_bytes(), before)

    def test_index_generation_rejects_a_selected_record_not_matching_package(self):
        validated = REPORT.validate_batch_inputs(self.fixture.batch)
        path = self.fixture.target / 'scoring/execution-records/task-zero.json'
        document = json.loads(path.read_text());document['prompt']['sha256'] = 'f' * 64
        write_json(path, document)
        with self.assertRaisesRegex(REPORT.ReportError, 'SELECTED_EXECUTION_DRIFT'):
            REPORT.write_developer_indexes(validated, self.root / 'rejected')

    def test_bundle_preserves_zero_error_unscored_and_canonical_workbook(self):
        report = self.report()
        sealed = seal_report(report, self.root / 'seals')
        original = (report / 'synthetic.xlsx').read_bytes()
        (report / 'synthetic.xlsx').write_bytes(b'independent host variant')
        with contextlib.redirect_stdout(io.StringIO()):
            BUNDLE.main(['--workspace-root', str(self.root), '--report-dir', str(report),
                         '--output-root', str(self.root / 'bundles'), '--canonical-report-archive', sealed['archive']])
        receipt = json.loads((self.root / 'bundles/bundle-receipts/latest-bundle-receipt.json').read_text())
        directory = Path(receipt['bundle_directory'])
        tasks = json.loads((directory / 'TASK_INDEX.json').read_text())['tasks']
        self.assertEqual(len(tasks), 4)
        self.assertEqual(receipt['score_status_counts'], {'valid': 2, 'evaluation_error': 1, 'unscored': 1})
        self.assertEqual(next(r for r in tasks if r['task_id'] == 'task-zero')['score_0_1'], 0.0)
        self.assertIsNone(next(r for r in tasks if r['score_status'] == 'unscored')['score_file'])
        self.assertTrue(all(r['score_0_1'] is None for r in tasks if r['score_status'] != 'valid'))
        self.assertEqual((directory / 'Reports/synthetic.xlsx').read_bytes(), original)
        self.assertEqual((directory / 'HostReportVariants/synthetic.xlsx').read_bytes(), b'independent host variant')
        for target in (directory, Path(receipt['archive'])):
            cp = subprocess.run([sys.executable, str(directory / 'VERIFY.py'), str(target)], capture_output=True, text=True)
            self.assertEqual(cp.returncode, 0, cp.stderr)
            self.assertEqual(json.loads(cp.stdout)['score_status_counts'], receipt['score_status_counts'])

    def test_live_workbook_drift_is_rejected_without_a_canonical_archive(self):
        report = self.report()
        (report / 'synthetic.xlsx').write_bytes(b'changed')
        with self.assertRaises(AssertionError), contextlib.redirect_stdout(io.StringIO()):
            BUNDLE.main(['--workspace-root', str(self.root), '--report-dir', str(report), '--output-root', str(self.root / 'rejected')])

    def test_list_source_index_keeps_complete_scope_and_original_index_bytes(self):
        report=self.report();source_path=report/'developer-source-index.json';task_path=report/'developer-task-index.json'
        source=json.loads(source_path.read_text());selected=json.loads(task_path.read_text())
        for uid,item in list(source['imports'].items()):
            source['imports'][uid]={'packages':[item]}
            for row in selected['selected_tasks']:
                if row['unit_id']==uid:row['source_package_id']=item['package_id']
        write_json(source_path,source);selected['source_index_sha256']=sha256(source_path);write_json(task_path,selected)
        receipt_path=report/'composite-report-receipt.json';receipt=json.loads(receipt_path.read_text());receipt['composite_import_index_sha256']=sha256(source_path);write_json(receipt_path,receipt)
        sealed=seal_report(report,self.root/'list-seal');before=source_path.read_bytes()
        with contextlib.redirect_stdout(io.StringIO()):
            BUNDLE.main(['--workspace-root',str(self.root),'--report-dir',str(report),'--output-root',str(self.root/'list-bundles'),'--canonical-report-archive',sealed['archive']])
        result=json.loads((self.root/'list-bundles/bundle-receipts/latest-bundle-receipt.json').read_text())
        self.assertEqual(result['selected_runs'],4);self.assertEqual(result['score_status_counts'],{'valid':2,'evaluation_error':1,'unscored':1})
        self.assertEqual(source_path.read_bytes(),before)
        self.assertEqual((Path(result['bundle_directory'])/'Reports/developer-source-index.json').read_bytes(),before)

    def test_source_list_never_silently_selects_a_package_or_ignores_task_identity(self):
        package={'package_id':'p1','target':'/source','package_manifest_sha256':'a'*64}
        index={'imports':{'u':{'packages':[package]}}};selected={'selected_tasks':[{'unit_id':'u','source_package_id':'p2'}]}
        with self.assertRaisesRegex(AssertionError,'SELECTED_PACKAGE_ID_MISMATCH'):BUNDLE.single_package_imports(index,selected)
        index['imports']['u']['packages'].append({**package,'package_id':'p2'})
        with self.assertRaisesRegex(AssertionError,'MULTI_PACKAGE_UNIT'):BUNDLE.single_package_imports(index,selected)

    @unittest.skipUnless(sys.platform=='darwin','APFS user-immutable clone semantics')
    def test_readonly_immutable_source_exports_without_chmod_or_unlock(self):
        source=self.root/'immutable-source';source.mkdir();file=source/'reference.xlsx';file.write_bytes(b'frozen reference')
        file.chmod(0o444);os.chflags(file,stat.UF_IMMUTABLE);original=file.stat().st_flags
        target=self.root/'immutable-export';copy=target/'reference.xlsx'
        try:
            BUNDLE.copy_verified(source,target,{'path':'reference.xlsx','kind':'file','mode':'0444',
                'size':file.stat().st_size,'sha256':sha256(file)})
            self.assertEqual(copy.read_bytes(),file.read_bytes());self.assertEqual(stat.S_IMODE(copy.stat().st_mode),0o444)
            self.assertEqual(file.stat().st_flags,original);self.assertTrue(copy.stat().st_flags&stat.UF_IMMUTABLE)
        finally:
            # Only fixture files created by this test are made disposable.
            for own in [file,copy]:
                if own.exists():os.chflags(own,own.stat().st_flags&~stat.UF_IMMUTABLE)

    def test_seal_rejects_preexisting_drift_and_bad_members_without_editing_sources(self):
        report = self.report();sealed = seal_report(report, self.root / 'seals')
        path = report / 'synthetic.xlsx';path.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'ARTIFACT_DRIFT'):
            seal_report(report, self.root / 'later-seal')
        self.assertEqual(path.read_bytes(), b'changed')
        bad = self.root / 'bad.zip'
        with zipfile.ZipFile(sealed['archive']) as original, zipfile.ZipFile(bad, 'w') as output:
            for info in original.infolist():
                output.writestr(info.filename, b'tampered' if info.filename.endswith('.xlsx') else original.read(info))
        with self.assertRaisesRegex(AssertionError, 'member drift'):
            BUNDLE.canonical_report_files(bad)


if __name__ == '__main__':
    unittest.main()
