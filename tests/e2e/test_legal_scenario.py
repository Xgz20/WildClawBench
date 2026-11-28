"""Legal catalog identity, General runtime routing, and frozen GT isolation."""
from pathlib import Path
import unittest

from src.case_catalog import document, index
from src.e2e.dataset_assets import maintained_releases
from src.e2e.protocol import catalog, resolve

REPO = Path(__file__).resolve().parents[2]


class LegalScenarioTests(unittest.TestCase):
    def plan(self, *, frozen=True):
        selection = {'scenario': 'legal', 'library_dataset': 'xiaofa-legal'}
        if frozen:
            selection['dataset'] = 'xiaofa-legal30-v1'
        return {'batch_id': 'legal-validation', 'selection': selection,
                'units': [{'harness': 'astronstudio', 'model': 'spark-x2.6'}]}

    def test_current_and_frozen_catalog_keep_legal_scene_and_thirty_cases(self):
        for release in (None, 'xiaofa-legal30-v1'):
            group = index(REPO, 'xiaofa-legal', release)['datasets'][0]
            self.assertEqual(group['scene'], 'legal')
            self.assertEqual(len(group['cases']), 30)
            self.assertEqual({row['scene'] for row in group['cases']}, {'legal'})
        self.assertEqual(set(maintained_releases(REPO, scenario='legal')), {'xiaofa-legal30-v1'})
        self.assertNotIn('xiaofa-legal30-v1', maintained_releases(REPO, scenario='general'))

    def test_frozen_and_working_legal_tasks_use_general_contract(self):
        for frozen in (False, True):
            plan, tasks, members, manifest, _ = resolve(REPO, self.plan(frozen=frozen))
            self.assertEqual(plan['selection']['scenario'], 'legal')
            self.assertEqual(len(tasks), 30)
            self.assertEqual({row['scene'] for row in tasks}, {'general'})
            self.assertEqual({row['metric_profile'] for row in tasks}, {'general-e2e-contract-v1'})
            self.assertEqual(manifest['task_count'], 30)
            for task in tasks:
                public = members[task['bundle']['execution_contract_path']].data.decode('utf-8')
                self.assertNotIn('gt/oracle.json', public)
                self.assertTrue(any(path.startswith('tasks/' + task['task_id'] + '/private-scoring/')
                                    for path in members))

    def test_library_scenario_and_direct_release_cannot_cross_scenes(self):
        plan = self.plan()
        plan['selection']['scenario'] = 'general'
        with self.assertRaisesRegex(ValueError, 'CASE_LIBRARY_MODE_UNSUPPORTED'):
            resolve(REPO, plan)
        del plan['selection']['library_dataset']
        with self.assertRaisesRegex(ValueError, 'CASE_LIBRARY_SCENARIO_MISMATCH'):
            resolve(REPO, plan)
        with self.assertRaisesRegex(ValueError, 'CASE_LIBRARY_SCENARIO_MISMATCH'):
            catalog(REPO, 'legal', 'general-custom70-v6')

    def test_frozen_material_preview_reads_real_input_without_exposing_gt(self):
        task = '01_Legal_Intake_task_001_case_registration'
        result = document(REPO, 'xiaofa-legal', task, 'xiaofa-legal30-v1')
        self.assertTrue(result)
        scan = document(REPO, 'xiaofa-legal', task, 'xiaofa-legal30-v1', material='scan.png')
        self.assertTrue(scan.startswith(b'\x89PNG'))
        with self.assertRaisesRegex(ValueError, 'CASE_LIBRARY_MATERIAL_UNKNOWN'):
            document(REPO, 'xiaofa-legal', task, 'xiaofa-legal30-v1', material='../gt/oracle.json')

    def test_managed_case_source_cannot_override_legal_or_frozen_selection(self):
        for selection in ({'scenario':'legal'}, {'scenario':'general','dataset':'xiaofa-legal30-v1'},
                          {'scenario':'general','library_dataset':'xiaofa-legal'}):
            plan = self.plan()
            plan['selection'] = {**selection, 'case_source':{'path':'/must-not-be-read','sha256':'a'*64}}
            with self.assertRaisesRegex(ValueError,'MANAGED_CASE_SOURCE_SELECTION_CONFLICT'):
                resolve(REPO,plan)


if __name__ == '__main__':
    unittest.main()
