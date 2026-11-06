from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.general_e2e.test_report_general_e2e import REPORT, Fixture, write_json, sha256

AUDIT = REPORT.report_run_audit


class ReportRunAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.fixture = Fixture(self.root)
        self.data = REPORT.aggregate(REPORT.validate_batch_inputs(self.fixture.batch), '2026-09-18T02:00:00Z')
        self.evidence = self.root / 'native-observation.json'
        write_json(self.evidence, {'native_observation': 'fixture'})
        self.ref = {'path': str(self.evidence), 'sha256': sha256(self.evidence)}
        rows = self.data['tasks']
        execution = [{'task_id': row['task_id'], 'attempt_id': row['execution_attempt_id'],
                      'started_at': row['execution_started_at'], 'finished_at': row['execution_finished_at'],
                      'evidence': [self.ref]} for row in rows]
        native = [row for row in rows if (row.get('judge') or {}).get('protocol') == 'codex-agent-judge-v1']
        scoring = [{'task_id': row['task_id'], 'attempt_id': row['scoring_attempt_id'],
                    'started_at': '2026-09-18T01:10:00Z', 'finished_at': '2026-09-18T01:10:05Z',
                    'evidence': [self.ref]} for row in native]
        self.ledger = {'schema_version': AUDIT.SCHEMA, 'batch_id': self.data['batch_id'],
            'dataset': self.data['dataset'], 'units': [{
                'unit_id': rows[0]['unit_id'],
                'task_bindings': [{key: row[key] for key in ('task_id', 'execution_attempt_id', 'scoring_attempt_id')} for row in rows],
                'execution': {'configured_slots': 3, 'method': 'Bound native task events',
                              'configuration_evidence': [self.ref], 'intervals': execution},
                'scoring': {'configured_slots': 3, 'method': 'Verified Codex native task events',
                            'configuration_evidence': [self.ref], 'intervals': scoring,
                            'missing_reason': 'No native judge interval for rules-only or unscored runs'},
                'controller_holds': [{'started_at': '2026-09-18T01:00:01Z', 'finished_at': '2026-09-18T01:00:03Z',
                                      'duration_seconds': 2, 'task_ids': [rows[0]['task_id']],
                                      'native_processes_paused': False, 'evidence': [self.ref]}],
            }]}
        self.path = self.root / 'run-audit-input.json'

    def tearDown(self):
        self.temp.cleanup()

    def load(self):
        write_json(self.path, self.ledger)
        return AUDIT.load(self.path, self.data)

    def test_known_peak_is_from_intervals_and_missing_does_not_become_zero(self):
        audit = self.load()
        unit = audit['units'][0]
        self.assertEqual(unit['execution']['configured_slots'], 3)
        self.assertEqual(unit['execution']['observed_peak'], 1)
        self.assertEqual(unit['execution']['interval_coverage'], {'known': 4, 'total': 4})
        self.assertEqual(unit['scoring']['coverage_status'], 'partial')
        self.ledger['units'][0]['scoring']['intervals'] = []
        self.assertIsNone(self.load()['units'][0]['scoring']['observed_peak'])
        self.assertEqual(AUDIT.overlap([
            {'started_at': '2026-01-01T00:00:00Z', 'finished_at': '2026-01-01T00:00:01Z'},
            {'started_at': '2026-01-01T00:00:01Z', 'finished_at': '2026-01-01T00:00:02Z'}]), 1)

    def test_rejects_scope_attempt_evidence_and_hold_drift(self):
        mutations = [
            lambda v: v['units'][0]['task_bindings'].pop(),
            lambda v: v['units'][0]['task_bindings'][0].update(execution_attempt_id='another'),
            lambda v: v['units'][0]['execution']['intervals'][0].update(attempt_id='another'),
            lambda v: v['units'][0]['execution']['intervals'].append(copy.deepcopy(v['units'][0]['execution']['intervals'][0])),
            lambda v: v['units'][0]['execution']['intervals'][0].update(started_at='2026-09-17T00:00:00Z'),
            lambda v: v['units'][0]['execution']['configuration_evidence'][0].update(sha256='f' * 64),
            lambda v: v['units'][0]['controller_holds'][0].update(duration_seconds=3),
            lambda v: v['units'][0]['controller_holds'][0].update(native_processes_paused=True),
            lambda v: v['units'][0]['controller_holds'][0].update(
                started_at='2026-09-19T01:00:01Z', finished_at='2026-09-19T01:00:03Z'),
            lambda v: v['units'][0]['scoring'].update(missing_reason=None),
        ]
        original = copy.deepcopy(self.ledger)
        for mutate in mutations:
            self.ledger = copy.deepcopy(original)
            mutate(self.ledger)
            with self.subTest(mutation=mutate), self.assertRaisesRegex(ValueError, 'REPORT_RUN_AUDIT_INVALID'):
                self.load()

    def test_stage_rechecks_evidence_and_all_views_preserve_scores_and_timing(self):
        before = copy.deepcopy(self.data)
        write_json(self.path, self.ledger)
        self.assertTrue(AUDIT.prepare(self.data, argparse.Namespace(run_audit=self.path)))
        self.data['presentation'] = REPORT.report_views.build_views(self.data, REPORT.report_views.load_references())
        artifacts = AUDIT.stage(self.data, self.root / 'published')
        self.assertEqual(len(artifacts), 1)
        self.assertEqual(self.data['tasks'], before['tasks'])
        self.assertEqual(self.data['overall'], before['overall'])
        self.assertEqual(self.data['units'], before['units'])
        markdown = REPORT.render_markdown(self.data)
        self.assertIn('执行配置3，原生区间重叠峰值1', markdown)
        self.assertIn('控制审阅暂停2.000000秒', markdown)
        self.assertIn('运行编排与控制介入', REPORT.render_audit_markdown(self.data))
        view = self.data['presentation']['tables']['效率对比']
        last_note = view.get('header_row', 1) + len(view['rows']) + 2 + len(view['notes'])
        self.assertGreater(view['timing_table']['header_row'], last_note)
        self.evidence.write_text('changed')
        with self.assertRaisesRegex(ValueError, 'evidence SHA mismatch'):
            AUDIT.stage(self.data, self.root / 'drifted')

    def test_generation_seals_same_audit_and_receipt_before_publication(self):
        write_json(self.path, self.ledger)
        output = self.fixture.batch / 'reports/with-run-audit'

        def render(_input, workbook, previews, **_kwargs):
            workbook.write_bytes(b'fixture-workbook')
            validation = previews / 'excel-validation.json'
            write_json(validation, {'status': 'PASS', 'sheets': ['fixture'], 'formula_errors': []})
            return {'status': 'PASS', 'validation': str(validation)}

        with patch.object(REPORT, 'render_excel', side_effect=render):
            result = REPORT.command_generate(argparse.Namespace(batch_root=self.fixture.batch,
                output_dir=output, generated_at='2026-09-18T02:00:00Z', node='node', node_modules=self.root,
                skip_preview=True, run_audit=self.path, seal_output_dir=self.root / 'sealed'))
        receipt = json.loads(Path(result['receipt']).read_text())
        audit = output / 'data/run-audit.json'
        self.assertTrue(audit.is_file())
        self.assertIn(sha256(audit), [item['sha256'] for item in receipt['artifacts']])
        self.assertTrue(Path(result['canonical_report_archive']).is_file())
        data = json.loads((output / 'general_e2e_report_data.json').read_text())
        self.assertEqual(data['lineage']['run_audit_sha256'], sha256(audit))
        self.assertEqual(data['scope']['task_run_count'], 4)
        self.assertEqual(data['tasks'], self.data['tasks'])

    def test_composite_seal_checks_declared_run_audit_bytes(self):
        import seal_report
        self.data['run_audit'] = self.load()
        folder = self.root / 'composite'
        audit = AUDIT.stage(self.data, folder)[0]
        self.data['artifact_filenames'] = {'excel': 'fixture.xlsx'}
        workbook = folder / 'fixture.xlsx'
        workbook.write_bytes(b'fixture-workbook')
        report_data = folder / 'general_e2e_report_data.json'
        write_json(report_data, self.data)
        receipt = folder / 'composite-report-receipt.json'
        write_json(receipt, {'source_json_sha256': sha256(report_data), 'excel_sha256': sha256(workbook),
                            'run_audit_artifacts': [{'path': 'data/run-audit.json', 'sha256': sha256(audit)}]})
        self.assertEqual(seal_report.seal_report(folder, self.root / 'sealed-composite')['status'], 'PASS')
        audit.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'REPORT_SEAL_RUN_AUDIT_DRIFT'):
            seal_report.seal_report(folder, self.root / 'rejected-seal')


if __name__ == '__main__':
    unittest.main()
