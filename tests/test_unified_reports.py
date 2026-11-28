import copy
import json
from pathlib import Path
import tempfile
import unittest

from src import unified_reports as reports
from src.e2e.common import atomic_json, digest, file_sha256
from src.utils.task_parser import parse_task_md
from src.utils.eval_provenance import _path_tree_sha256
from src.e2e.artifacts import inventory


class UnifiedReportsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.sources = []
        self.task = self.root / 'task.md'
        self.task.write_text('''---
id: task1
name: 测试题
grading_type: automated
---
## Prompt
生成一份结果。
## Workspace Path
workspace/test
## Automated Checks
echo true
''')
        parsed = parse_task_md(self.task)
        self.exec_root, self.gt_root = self.root / 'exec', self.root / 'gt'
        for path in (self.exec_root, self.gt_root):
            path.mkdir();(path / 'data.txt').write_text('frozen input')
        provenance = {'task_id': 'task1', 'provenance_status': 'complete',
            'task_sha256': file_sha256(self.task),
            'workspace_exec_sha256': _path_tree_sha256(self.exec_root), 'ground_truth_sha256': _path_tree_sha256(self.gt_root)}
        parsed['_contract_provenance'] = provenance
        self.provenance = self.root / 'provenance.json';atomic_json(self.provenance, provenance)
        self.cli_task = self.root / 'task.json';atomic_json(self.cli_task, parsed)
        self.manifest = self.root / 'manifest.json'
        atomic_json(self.manifest, {'files': [{'path': 'task.json', 'sha256': file_sha256(self.cli_task)}]})
        for kind in ['cli', 'e2e']:
            rows = []
            for index, value in enumerate([0, 1], 1):
                path = self.root / f'{kind}-{index}.json'
                payload = ({'schema': 'wildclawbench.cli-score/v1', 'scores': {'overall_score': value},
                    'source_manifest_sha256': digest(json.loads(self.manifest.read_text()))} if kind == 'cli' else {
                    'identity': {'task_id': 'task1'}, 'execution': {'attempt_id': 'e-' + str(index)},
                    'result': {'valid': True, 'total_score': value}, 'evaluation': {'status': 'completed'}})
                atomic_json(path, payload)
                task_file = self.cli_task if kind == 'cli' else self.task
                rows.append({'task_id': 'task1', 'run_index': index, 'task_format': 'cli-json' if kind == 'cli' else 'markdown',
                    'task_file': {'path': str(task_file), 'sha256': file_sha256(task_file)},
                    'input_manifest': {'path': str(self.manifest), 'sha256': file_sha256(self.manifest)} if kind == 'cli' else None,
                    'provenance_file': {'path': str(self.provenance), 'sha256': file_sha256(self.provenance)} if kind == 'cli' else None,
                    'materials': {key: {'path': str(path), 'entries': inventory(path)} for key,path in
                        [('workspace_exec_sha256', self.exec_root), ('ground_truth_sha256', self.gt_root)]},
                    'score_file': {'path': str(path), 'sha256': file_sha256(path)}, 'score_status': 'valid', 'total_score': value,
                    'execution_attempt_id': 'e-' + str(index), 'execution_status': 'completed',
                    'metadata': {'category': 'category', 'difficulty': 'L1'}})
            self.sources.append({'id': kind, 'kind': kind, 'label': kind, 'roots': [str(self.root)],
                'dataset': {'id': 'same', 'release': None}, 'harness': {'id': kind, 'version': None},
                'model': {'requested_id': 'model', 'actual_id': None}, 'scorer': {'harness': 'judge'},
                'selection': {'kind': kind}, 'rows': rows})
        self.spec = {'schema': reports.SPEC, 'name': '<script>测试</script>', 'units': self.sources}

    def test_mixed_sources_case_first_mean_and_zero(self):
        snapshot = reports.prepare(self.spec)
        data = reports.build(snapshot)
        self.assertEqual(data['scope']['unit_count'], 2)
        self.assertEqual(data['scope']['task_run_count'], 4)
        self.assertEqual(data['units'][0]['score']['mean_score'], .5)
        self.assertNotIn('mean_score', data['overall']['score'])
        self.assertEqual(data['rounds'][0]['total_score'], 0)
        self.assertEqual(data['presentation']['tables']['用例对比']['rows'][0], ['task1', 50, 50, 0])

    def test_errors_and_missing_never_become_zero(self):
        row = self.sources[0]['rows'][1]
        row.update(score_status='evaluation_error', total_score=None, error='judge failure')
        data = reports.build(reports.prepare(self.spec))
        self.assertEqual(data['units'][0]['score']['mean_score'], 0)
        self.assertIsNone(data['rounds'][1]['total_score'])
        self.assertEqual(data['rounds'][1]['score_status'], 'evaluation_error')

    def test_configuration_discloses_inherited_case_template_identity(self):
        snapshot = reports.prepare(self.spec)
        for unit in snapshot['units']:
            for row in unit['rows']:
                row['judge'] = {'protocol': 'managed-case-score/v1', 'template_revision_id': 2,
                                'template_sha256': 'a' * 64}
        snapshot.pop('snapshot_sha256')
        snapshot['snapshot_sha256'] = digest(snapshot)
        table = reports.build(snapshot)['presentation']['tables']['评分配置']
        self.assertEqual(table['rows'][0][7:9], ['2', 'a' * 64])

    def test_dataset_task_scope_and_contract_conflicts_are_rejected(self):
        self.sources[1]['dataset']['release'] = 'different'
        with self.assertRaisesRegex(ValueError, 'VERSION_MISMATCH'):
            reports.prepare(self.spec)
        self.sources[1]['dataset']['release'] = None
        self.sources[1]['rows'][0]['task_id'] = 'other'
        with self.assertRaisesRegex(ValueError, 'IDENTITY_MISMATCH'):
            reports.prepare(self.spec)
        self.sources[1]['rows'][0]['task_id'] = 'task1'
        task = json.loads(self.cli_task.read_text());task['automated_checks'] = 'changed'
        atomic_json(self.cli_task, task)
        atomic_json(self.manifest, {'files': [{'path': 'task.json', 'sha256': file_sha256(self.cli_task)}]})
        for row in self.sources[0]['rows']:
            row['task_file']['sha256'] = file_sha256(self.cli_task)
            row['input_manifest']['sha256'] = file_sha256(self.manifest)
            receipt = json.loads(Path(row['score_file']['path']).read_text())
            receipt['source_manifest_sha256'] = digest(json.loads(self.manifest.read_text()))
            atomic_json(Path(row['score_file']['path']), receipt)
            row['score_file']['sha256'] = file_sha256(Path(row['score_file']['path']))
        with self.assertRaisesRegex(ValueError, 'RUBRIC_OR_MATERIAL_MISMATCH'):
            reports.prepare(self.spec)

    def test_input_and_snapshot_drift_fail_closed(self):
        snapshot = reports.prepare(self.spec)
        snapshot['units'][0]['rows'][0]['total_score'] = .8
        with self.assertRaisesRegex(ValueError, 'SNAPSHOT_DRIFT'):
            reports.build(snapshot)
        self.task.write_text('changed')
        with self.assertRaisesRegex(ValueError, 'SOURCE_DRIFT'):
            reports.prepare(self.spec)

    def test_duplicate_rounds_and_sources_are_rejected(self):
        self.sources[0]['rows'].append(copy.deepcopy(self.sources[0]['rows'][0]))
        with self.assertRaisesRegex(ValueError, 'ROUND_DUPLICATE'):
            reports.prepare(self.spec)
        self.sources[0]['rows'].pop()
        self.spec['units'].append(copy.deepcopy(self.sources[0]))
        with self.assertRaisesRegex(ValueError, 'SOURCE_DUPLICATE'):
            reports.prepare(self.spec)

    def test_offline_replay_and_artifacts_are_hash_bound(self):
        from openpyxl import load_workbook
        snapshot = reports.prepare(self.spec)
        output = self.root / 'report'
        receipt = reports.generate(snapshot, output)
        self.assertEqual(set(receipt['artifacts']), {'json', 'md', 'html', 'xlsx', 'snapshot'})
        self.assertNotIn('<script>测试</script>', (output / 'report.html').read_text())
        self.assertEqual(load_workbook(output / 'report.xlsx')['总览']['B2'].value, 50)
        self.assertEqual(reports.generate(snapshot, output), receipt)
        # Replay only the normalized frozen snapshot; no mutable originals read.
        self.task.unlink();self.cli_task.unlink()
        replay = self.root / 'replay'
        reports.generate(snapshot, replay)
        first = json.loads((output / 'report.json').read_text())
        second = json.loads((replay / 'report.json').read_text())
        self.assertEqual(first['presentation'], second['presentation'])
        (output / 'report.xlsx').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'ARTIFACT_DRIFT'):
            reports.generate(snapshot, output)


if __name__ == '__main__':
    unittest.main()
