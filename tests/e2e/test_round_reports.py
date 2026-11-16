import copy
import tempfile
import unittest
from pathlib import Path

from src.e2e.general_reports import report_module, _unavailable_row, markdown, xlsx, standalone_html
from src.e2e.round_reports import aggregate_case, group_round_report


class RoundReportTests(unittest.TestCase):
    def setUp(self):
        self.core, _ = report_module()

    def row(self, task, round_index, score, score_id):
        unit = {'unit_id': 'original', 'harness': 'astronstudio', 'model': 'spark-x2.6'}
        row = _unavailable_row(self.core, {'attempt_id': task + '-r' + str(round_index), 'phase': 'FAILED', 'key': task},
            {'task_id': task, 'name': task, 'category': '02_Office', 'difficulty': 'L1', 'modality': 'pure-text'}, unit, None)
        row.update(unit_id='s' + str(score_id) + '-r' + str(round_index), run_index=round_index,
            score_status='valid' if score is not None else 'evaluation_error', total_score=score,
            execution_status='completed', execution_phase='COMPLETED', evidence_completeness='complete',
            scoring_attempt_id='judge-' + str(score_id) + '-' + task + '-' + str(round_index),
            execution_started_at='2026-11-16T00:00:00+00:00', execution_finished_at='2026-11-16T00:01:00+00:00',
            timing_clock_comparable=True, judge={'protocol': 'test', 'model': 'judge', 'reasoning_effort': 'high'})
        row['model'].update(actual_id='spark-x2.6', verification_status='verified')
        row['resource']['total_tokens'] = {'value': 10, 'known_subtotal': 10, 'complete': True, 'status': 'complete', 'coverage': {'known': 1, 'total': 1}}
        row['checkpoints'] = {'values': {'overall_score': score} if score is not None else {}, 'sources': []}
        row['lineage'].update(source_batch_id='batch', source_unit_id='original', score_operation_id=score_id)
        return row

    def test_case_mean_keeps_zero_excludes_errors_and_retains_original_attempts(self):
        rounds = [self.row('a', 1, 0, 1), self.row('a', 2, 1, 1), self.row('a', 3, None, 1)]
        snapshot = copy.deepcopy(rounds)
        case = aggregate_case(rounds, 'grouped')
        self.assertEqual(case['total_score'], .5)
        self.assertEqual(case['round_coverage'], {'total': 3, 'valid': 2, 'evaluation_error': 1, 'unscored': 0})
        self.assertEqual(len(case['rounds']), 3)
        self.assertIsNone(case['scoring_attempt_id'])
        self.assertEqual(rounds, snapshot)

    def test_grouped_reports_have_two_judges_not_six_round_units_and_deduplicate_resources(self):
        rows, units = [], []
        for judge in [1, 2]:
            for round_index in [1, 2, 3]:
                values = ([0, 1, None][round_index - 1], 1 if round_index == 1 else None) if judge == 1 else (.5, .5)
                chunk = [self.row(task, round_index, score, judge) for task, score in zip(['case-a', 'case-b'], values)]
                rows.extend(chunk)
                unit = self.core.unit_summary(chunk, {'unit_id': chunk[0]['unit_id'], 'harness': chunk[0]['harness'], 'model': chunk[0]['model'], 'execution_mode': 'automatic'})
                unit.update(source={'score_operation_id': judge, 'unit_id': 'original', 'batch_id': 8, 'run_index': round_index, 'agent_invocation_count': 2},
                    scorer={'harness': 'codex' if judge == 1 else 'deepseek-harness', 'model': 'judge', 'reasoning_effort': 'high'})
                units.append(unit)
        data = {'title': '多轮验收', 'dataset': {'id': 'fixture'}, 'scope': {}, 'semantics': {}, 'units': units, 'tasks': rows}
        result = group_round_report(self.core, data)
        self.assertEqual(result['schema_version'], 'wildclawbench.platform-general-report/v2')
        self.assertEqual(result['scope']['unit_count'], 2)
        self.assertEqual(result['scope']['task_run_count'], 12)
        self.assertEqual(result['scope']['unique_execution_count'], 6)
        self.assertEqual(result['scope']['case_result_count'], 4)
        self.assertAlmostEqual(result['units'][0]['score']['mean_score'], .75)
        self.assertAlmostEqual(result['units'][1]['score']['mean_score'], .5)
        self.assertEqual(result['overall']['resources']['total_tokens']['total'], 60)
        self.assertEqual([row[1] for row in result['presentation']['tables']['总览']['rows']], [75, 50])
        self.assertTrue(all('评分#' in label for label in result['presentation']['unit_labels'].values()))
        self.assertEqual(len(result['rounds']), 12)
        self.assertIn('多轮', markdown(result))
        self.assertIn('DATA=', standalone_html(result))
        with tempfile.TemporaryDirectory() as root:
            xlsx(result, Path(root) / 'report.xlsx')
            self.assertTrue((Path(root) / 'report.xlsx').is_file())
