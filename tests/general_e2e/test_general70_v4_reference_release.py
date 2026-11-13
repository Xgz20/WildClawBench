"""Full-suite reference distribution without changing the other 69 cases."""
import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest

from eval_general_e2e.datasets.bundle import (
    DATASETS, GENERAL70_V3_DEFINITION, GENERAL70_V4_DEFINITION, compile_dataset,
    dataset_manifest_path, load_manifest_lock,
)
from src.utils.dataset_selection import dataset_task_paths
from src.utils.cli_args import build_run_batch_parser
from src.utils.task_parser import parse_task_md
from tests.general_e2e.test_local_scoring_runtime import REPO_ROOT, RUNTIME

INFO004 = '01_Information_Search_Organization_task_004_luxun_national_character_source_comparison'
sha = lambda data: hashlib.sha256(data).hexdigest()


class General70V4ReferenceReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = load_manifest_lock(dataset_manifest_path('general-custom70-v3'))
        cls.after, members = compile_dataset(REPO_ROOT, definition=GENERAL70_V4_DEFINITION)
        cls.contract_bytes = {json.loads(m.data)['task_id']: m.data for m in members
                              if m.path.endswith('/private-scoring/contract.json')}
        cls.contracts = {k: json.loads(v) for k, v in cls.contract_bytes.items()}
        cls.new_members = {m.path: (m.kind, m.mode, sha(m.data)) for m in members}
        cls.info_members = {m.path: m.data for m in members if m.path.startswith(f'tasks/{INFO004}/')}
        del members
        _, members = compile_dataset(REPO_ROOT, definition=GENERAL70_V3_DEFINITION)
        cls.old_members = {m.path: (m.kind, m.mode, sha(m.data)) for m in members}
        del members
        tree = ast.parse(Path(RUNTIME.__file__).read_text())
        prepare = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'prepare_attempt')
        runtime = next(n for n in ast.walk(prepare) if isinstance(n, ast.Dict)
                       and any(isinstance(k, ast.Constant) and k.value == 'evaluator_input_profile' for k in n.keys))
        cls.profile_expressions = [ast.Expression(value) for key, value in zip(runtime.keys, runtime.values)
                                  if key is None and any(isinstance(k, ast.Constant) and isinstance(k.value, str)
                                                        and (k.value.endswith('_profile') or k.value == 'shared_rule_source_repair')
                                                        for node in ast.walk(value) if isinstance(node, ast.Dict)
                                                        for k in node.keys)]

    def profiles(self, contract_bytes, dataset):
        namespace = dict(RUNTIME.__dict__)
        namespace.update(contract=json.loads(contract_bytes), contract_bytes=contract_bytes,
                         dataset=dataset, judge_config={'protocol': 'codex-agent-judge-v1',
                                                        'model': 'gpt-6.1-sol', 'reasoning_effort': 'high'},
                         protect_runtime_office_inputs=False, validation=None, private_gt_entries=[], evidence_admission=None)
        result = {}
        for expression in self.profile_expressions:
            result.update(eval(compile(expression, '<actual-prepare-profile-expression>', 'eval'), namespace))
        return result

    def test_exact_full_scope_and_only_info004_record_changes(self):
        self.assertEqual(self.after['task_count'], 70)
        self.assertEqual(self.after['statistics'], self.before['statistics'])
        self.assertEqual([r['task_id'] for r in self.after['tasks']], [r['task_id'] for r in self.before['tasks']])
        changed = [b['task_id'] for a, b in zip(self.before['tasks'], self.after['tasks']) if a != b]
        self.assertEqual(changed, [INFO004])
        for a, b in zip(self.before['tasks'], self.after['tasks']):
            for key in ['prompt_sha256', 'workspace_exec_sha256', 'execution_contract_sha256']:
                self.assertEqual(a['digests'][key], b['digests'][key], (a['task_id'], key))
            self.assertEqual(a['grading_weights'], b['grading_weights'])

    def test_every_member_of_the_other_69_cases_is_byte_and_mode_identical(self):
        before = {k: v for k, v in self.old_members.items() if k.startswith('tasks/') and not k.startswith(f'tasks/{INFO004}/')}
        after = {k: v for k, v in self.new_members.items() if k.startswith('tasks/') and not k.startswith(f'tasks/{INFO004}/')}
        self.assertTrue(before)
        self.assertEqual(before, after)

    def test_seven_historical_datasets_still_rebuild_to_their_original_locks(self):
        for definition in DATASETS.values():
            if definition == GENERAL70_V4_DEFINITION:
                continue
            with self.subTest(dataset=definition.dataset_id):
                manifest, _ = compile_dataset(REPO_ROOT, definition=definition)
                self.assertEqual(manifest, load_manifest_lock(dataset_manifest_path(definition.dataset_id)))

    def test_cli_selects_all_70_exact_contract_sources(self):
        parser = build_run_batch_parser('verification-model', 3)
        for name in ['general-custom70-v2', 'general-custom70-v3', 'general-custom70-v4']:
            self.assertEqual(parser.parse_args(['--dataset', name]).dataset, name)
        manifest, groups = dataset_task_paths(REPO_ROOT, 'general-custom70-v4')
        self.assertEqual(manifest, self.after)
        self.assertEqual(sum(len(v) for v in groups.values()), 70)
        for paths in groups.values():
            for path in paths:
                task = parse_task_md(path)
                self.assertEqual(task['automated_checks'], self.contracts[task['task_id']]['automated_checks'])

    def test_complete_pdf_and_text_are_private_only(self):
        single = load_manifest_lock(dataset_manifest_path('general-info004-open-v3'))['tasks'][0]
        full = next(r for r in self.after['tasks'] if r['task_id'] == INFO004)
        self.assertEqual(full['digests'], single['digests'])
        prefix = f'tasks/{INFO004}/private-scoring/gt/source_evidence/'
        self.assertEqual(sha(self.info_members[prefix + 'Y1-yang-lianfen.pdf']),
                         'd42a5b5dd458469b160f57da3abfde3e27e194a2b107a1c2227b858cface0455')
        text = self.info_members[prefix + 'Y1-yang-lianfen.pages.txt'].decode()
        self.assertEqual(text.count('===== PDF PAGE'), 10)
        self.assertNotIn('杨乾坤', text.split('===== PDF PAGE 10')[1])
        self.assertFalse(any('Y1-yang-lianfen' in path for path in self.new_members if '/execution/' in path))

    def test_all_69_runtime_profiles_and_effective_rule_sources_keep_their_meaning(self):
        datasets = [{'id': m['dataset_id'], 'digest': m['dataset_digest']} for m in [self.before, self.after]]
        before_rows = {r['task_id']: r for r in self.before['tasks']}
        self.assertGreater(len(self.profile_expressions), 10)
        for tid, raw in self.contract_bytes.items():
            if tid == INFO004:
                continue
            profiles = [self.profiles(raw, dataset) for dataset in datasets]
            if tid == RUNTIME.sterilization_quote_layout.TASK:
                # This compatibility repair was admitted after the v4 reference release.
                # Compare the original profiles separately from the v4-only repair.
                self.assertNotIn('sterilization_quote_layout_profile', profiles[0])
                marker = profiles[1].pop('sterilization_quote_layout_profile')
                from sterilization_quote_complete_layout import PROFILE
                self.assertEqual(marker['profile'], PROFILE)
            clean = lambda data: {k: ({a: b for a, b in v.items() if a != 'catalog_sha256'} if isinstance(v, dict) else v)
                                  for k, v in data.items()}
            self.assertEqual(clean(profiles[0]), clean(profiles[1]), tid)
            outputs = []
            for dataset, runtime in zip(datasets, profiles):
                manifest = {'identity': {'task_id': tid}, 'dataset': dataset,
                            'digests': {'contract_sha256': before_rows[tid]['digests']['scoring_contract_sha256']},
                            'judge': {'protocol': 'codex-agent-judge-v1'}, 'runtime': runtime}
                outputs.append(RUNTIME._effective_rule_source(manifest, self.contracts[tid]['automated_checks'])[0])
            self.assertEqual(outputs[0], outputs[1], tid)

    def test_v4_filename_globs_are_exact_and_reject_foreign_identity(self):
        rows = RUNTIME.generated_evidence_globs.registry('general-custom70-v4')
        self.assertEqual(len(rows), 4)
        for row in rows:
            manifest = {'identity': {'task_id': row['task_id']}, 'dataset': deepcopy(row['dataset']),
                        'digests': {'contract_sha256': row['contract_sha256']}}
            contract = self.contracts[row['task_id']]
            self.assertIsNotNone(RUNTIME.generated_evidence_globs.descriptor(manifest, contract))
            for field in ['digest', 'id']:
                bad = deepcopy(manifest)
                bad['dataset'][field] = '0' * 64
                self.assertIsNone(RUNTIME.generated_evidence_globs.descriptor(bad, contract))
        self.assertEqual(len(RUNTIME.generated_evidence_globs.registry('general-custom70-v3')), 4)
