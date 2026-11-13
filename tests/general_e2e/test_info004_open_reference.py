from copy import deepcopy
import ast
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
import unittest
from unittest.mock import patch

from eval_general_e2e.datasets.bundle import (
    DATASETS, DEFAULT_DEFINITION, GENERAL116_DEFINITION, GENERAL70_V2_DEFINITION,
    GENERAL70_V3_DEFINITION, INFO004_OPEN_DEFINITION, INFO004_OPEN_V2_DEFINITION,
    INFO004_OPEN_V3_DEFINITION, compile_dataset,
    dataset_manifest_path, load_manifest_lock, _parse_task_source,
)
from src.utils.task_parser import parse_task_md
from src.utils.workspace_evidence import collect_workspace_evidence
from src.wildclawbench_grading_core.criterion_states import validate_semantic_response, finalize_cli_score
from tests.general_e2e.test_local_scoring_runtime import REPO_ROOT, RUNTIME

TASK = '01_Information_Search_Organization_task_004_luxun_national_character_source_comparison'
RELATIVE = f'tasks/general_e2e/01_Information_Search_Organization/{TASK}.md'


class Info004OpenReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.task = parse_task_md(REPO_ROOT / RELATIVE)
        cls.old = parse_task_md(REPO_ROOT / 'eval_general_e2e/datasets/source-snapshots/general-custom70-v3/files' / RELATIVE)
        cls.workspace = Path(cls.task['workspace_path'])
        cls.manifest, cls.members = compile_dataset(REPO_ROOT, definition=INFO004_OPEN_V3_DEFINITION)

    def grade(self, root):
        shutil.copytree(self.workspace / 'exec', root, dirs_exist_ok=True)
        shutil.copytree(self.workspace / 'gt', root / 'gt')
        namespace = {}
        exec(compile(self.task['automated_checks'], '<info004-open-reference>', 'exec'), namespace)
        return namespace['grade']

    def trace(self, answer):
        return [{'role': 'assistant', 'channel': 'final', 'content': answer},
                {'type': 'task_complete', 'last_agent_message': answer}]

    def test_public_task_difficulty_and_all_score_bands_are_restored(self):
        for key in ['prompt', 'timeout_seconds', 'grading_weights', 'workspace_path', 'judge_evidence']:
            self.assertEqual(self.task[key], self.old[key], key)
        current_metadata, current_sections, _ = _parse_task_source(REPO_ROOT / RELATIVE)
        old_metadata, old_sections, _ = _parse_task_source(Path(self.old['file_path']))
        self.assertEqual(current_metadata, old_metadata)
        self.assertEqual(current_sections['Expected Behavior'], old_sections['Expected Behavior'])
        criteria = lambda task: [(r['key'], r['weight'], r['allowed_scores']) for r in task['rubric_criteria']]
        self.assertEqual(criteria(self.task), criteria(self.old))
        self.assertEqual(sum(r['weight'] for r in self.task['rubric_criteria']), 98.)
        self.assertEqual(len(self.task['rubric_criteria']), 22)
        self.assertNotIn('general-info004-stable-v1', DATASETS)
        self.assertFalse((self.workspace / 'exec/materials').exists())

    def test_original_rule_logic_changes_only_its_reference_hashes(self):
        normalize = lambda code: re.sub(r'(EXPECTED_(?:REFERENCE|SOURCE_INDEX)_SHA256 = )"[a-f0-9]{64}"', r'\1"<reference-sha>"', code)
        self.assertEqual(normalize(self.task['automated_checks']), normalize(self.old['automated_checks']))
        before, after = self.old['llm_judge_rubric'], self.task['llm_judge_rubric']
        addition = re.search(r'\n\n补证只在裁判侧进行：.*?历史结果保留。', after)
        self.assertIsNotNone(addition)
        self.assertEqual(after.replace(addition.group(), ''), before)

    def test_single_case_bundle_keeps_the_old_execution_input_and_semantic_scale(self):
        old = next(r for r in load_manifest_lock(dataset_manifest_path('general-custom70-v3'))['tasks'] if r['task_id'] == TASK)
        current = self.manifest['tasks'][0]
        self.assertEqual(self.manifest['task_count'], 1)
        self.assertEqual(current['digests']['prompt_sha256'], old['digests']['prompt_sha256'])
        self.assertEqual(current['digests']['workspace_exec_sha256'], old['digests']['workspace_exec_sha256'])
        contract = next(json.loads(m.data) for m in self.members if m.path.endswith('/private-scoring/contract.json'))
        # Dataset materialization binds the canonical bundled reference bytes;
        # compare all rule logic exactly while separately checking those hashes.
        normalize = lambda code: re.sub(r'(EXPECTED_(?:REFERENCE|SOURCE_INDEX)_SHA256 = )"[a-f0-9]{64}"', r'\1"<reference-sha>"', code)
        self.assertEqual(normalize(contract['automated_checks']), normalize(self.task['automated_checks']))
        constants = {node.targets[0].id: ast.literal_eval(node.value)
                     for node in ast.parse(contract['automated_checks']).body
                     if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                     and node.targets[0].id in ['EXPECTED_REFERENCE_SHA256', 'EXPECTED_SOURCE_INDEX_SHA256']}
        for name, filename in [('EXPECTED_REFERENCE_SHA256', 'reference_answer.md'),
                               ('EXPECTED_SOURCE_INDEX_SHA256', 'reference_sources.json')]:
            payload = next(m.data for m in self.members if m.path.endswith('/private-scoring/gt/' + filename))
            self.assertEqual(constants[name], hashlib.sha256(payload).hexdigest())
        self.assertEqual(contract['semantic_weight_scale'], 98.)
        native = RUNTIME._parse_semantic_criteria(contract['llm_judge_rubric'], weight_scale=98.)
        self.assertEqual(len(native), 22)

    def test_all_six_historical_datasets_rebuild_without_any_lock_change(self):
        for definition in [DEFAULT_DEFINITION, GENERAL116_DEFINITION, GENERAL70_V2_DEFINITION, GENERAL70_V3_DEFINITION, INFO004_OPEN_DEFINITION, INFO004_OPEN_V2_DEFINITION]:
            with self.subTest(dataset=definition.dataset_id):
                manifest, _ = compile_dataset(REPO_ROOT, definition=definition)
                self.assertEqual(manifest, load_manifest_lock(dataset_manifest_path(definition.dataset_id)))

    def test_non_whitelisted_alternative_link_is_accepted_and_reference_is_exported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = self.grade(root)(self.trace('使用可靠替代研究并注明核验范围。https://example.org/alternative'), str(root))
            self.assertEqual(result['source_link_present'], 1.)
            index = json.loads((root / 'evaluator_evidence/reference_sources.json').read_text())
            self.assertTrue(index['policy']['alternative_sources_allowed'])
            self.assertFalse(index['policy']['required_bibliography'])
            self.assertEqual(index['known_unresolved_claims'], [])
            self.assertEqual({r['claim_id'] for r in index['reference_review_targets']}, {'Y1-C1', 'Y1-C2'})
            self.assertIn('早稻田文集版', index['remaining_reference_limitations'][0])
            self.assertIn('79—92', index['remaining_reference_limitations'][0])
            for row in index['sources']:
                data = (root / 'evaluator_evidence' / row['path']).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), row['sha256'])
            yang = json.loads((root / 'evaluator_evidence/source_evidence/Y1-yang-lianfen.json').read_text())
            self.assertEqual(yang['publication']['cnki_file_id'], 'LXYJ200312003')
            self.assertEqual(yang['excerpt'], '')
            self.assertTrue(yang['fulltext_included'])
            self.assertTrue(yang['primary_document']['full_original_in_source_bundle'])
            self.assertTrue(yang['primary_document']['provided_by_user'])
            self.assertEqual(yang['primary_document']['sha256'], 'd42a5b5dd458469b160f57da3abfde3e27e194a2b107a1c2227b858cface0455')
            self.assertEqual(yang['primary_document']['page_count'], 10)
            self.assertNotIn('杨乾坤', ''.join(row['text'] for row in yang['primary_passages']))
            note = next(row for row in yang['primary_passages'] if row['id'] == 'Y1-p38-note36')
            self.assertEqual(note['pdf_pages'], [10])
            self.assertEqual(note['printed_pages'], [38])
            self.assertIn('随感录·三十八', note['text'])
            self.assertTrue(yang['manual_search_leads']['search_leads_are_not_supporting_evidence'])
            self.assertEqual(yang['secondary_evidence'][0]['does_not_establish'], ['Y1-C1', 'Y1-C2'])

    def test_true_empty_delivery_stays_a_valid_automatic_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(self.grade(root)(self.trace(''), str(root))['source_link_present'], 0.)

    def test_missing_or_changed_reference_never_becomes_a_candidate_zero(self):
        for filename in ['Y1-yang-lianfen.json', 'Y1-yang-lianfen.pdf', 'Y1-yang-lianfen.pages.txt']:
            for mode in ['missing', 'changed']:
                with self.subTest(file=filename, mode=mode), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    grade = self.grade(root)
                    target = root / 'gt/source_evidence' / filename
                    if mode == 'missing':
                        target.unlink()
                    else:
                        target.write_text('changed')
                    with self.assertRaises((ValueError, FileNotFoundError)):
                        grade(self.trace('https://example.org/alternative'), str(root))

    def test_complete_primary_reference_is_available_offline_without_cli_truncation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            grade = self.grade(root)
            with patch('urllib.request.urlopen', side_effect=AssertionError('offline reference must not use network')):
                grade(self.trace('可靠替代来源 https://example.org/alternative'), str(root))
                evidence = collect_workspace_evidence(str(root), self.task['judge_evidence'])
            path = 'evaluator_evidence/source_evidence/Y1-yang-lianfen.pages.txt'
            row = next(r for r in evidence['metadata']['selected'] if r['path'] == path)
            self.assertFalse(row['truncated'])
            self.assertEqual(row['role'], 'evaluator_reference_not_agent_output')
            fulltext = (root / path).read_text()
            self.assertEqual(fulltext.count('===== PDF PAGE'), 10)
            self.assertIn(fulltext, evidence['text'])
            last = fulltext.split('===== PDF PAGE 10')[1]
            self.assertIn('随感录·三十八', last)
            self.assertNotIn('注释商榷两例', last)
            self.assertNotIn('杨乾坤', last)
            pdf = root / 'evaluator_evidence/source_evidence/Y1-yang-lianfen.pdf'
            self.assertEqual(hashlib.sha256(pdf.read_bytes()).hexdigest(), 'd42a5b5dd458469b160f57da3abfde3e27e194a2b107a1c2227b858cface0455')

    def test_original_pdf_is_packaged_only_as_private_scoring_material(self):
        files = {m.path: m.data for m in self.members}
        private = f'tasks/{TASK}/private-scoring/gt/source_evidence/'
        self.assertEqual(hashlib.sha256(files[private + 'Y1-yang-lianfen.pdf']).hexdigest(), 'd42a5b5dd458469b160f57da3abfde3e27e194a2b107a1c2227b858cface0455')
        self.assertIn(b'PDF PAGE 10', files[private + 'Y1-yang-lianfen.pages.txt'])
        execution = [p for p in files if p.startswith(f'tasks/{TASK}/execution/')]
        self.assertTrue(execution)
        self.assertFalse(any('Y1-yang-lianfen' in p for p in execution))

    def test_two_original_dimensions_keep_known_scores_and_unknown_null_in_cli_and_native(self):
        criteria = [{'key': 'known', 'weight': 94., 'allowed_scores': [0., 1.]},
                    {'key': 'scholar_claim_binding', 'weight': 4., 'allowed_scores': [0., .5, 1.]}]
        for statuses, value in [(['supported', 'supported'], 1.), (['contradicted', 'supported'], .5),
                                (['contradicted', 'contradicted'], 0.),
                                (['evaluator_reference_unavailable', 'supported'], None)]:
            with self.subTest(statuses=statuses):
                state = 'evaluator_reference_unavailable' if value is None else 'pass' if value == 1 else 'fail' if value == 0 else 'partial'
                reviews = [{'unit': i, 'claim_id': str(i), 'claim': claim, 'status': status,
                            'evidence_refs': [] if status == 'evaluator_reference_unavailable' else ['evidence-1']}
                           for i, (claim, status) in enumerate(zip(['全部实质研究的主要解释归属', '全部实质研究的论证范围'], statuses), 1)]
                response = {'scores': {'known': 1., 'scholar_claim_binding': value},
                            'criterion_statuses': {'known': {'status': 'pass', 'reason': '已核验。'},
                                'scholar_claim_binding': {'status': state, 'reason': '按原两个维度独立核对。'}},
                            'claim_reviews': {'scholar_claim_binding': reviews}}
                _, scores, _ = validate_semantic_response(response, criteria, claim_review_keys=['scholar_claim_binding'])
                final = finalize_cli_score(1., {}, scores, {'automated': .02, 'llm_judge': .98})
                self.assertEqual(final['_grading']['valid'], value is not None)
                if value is None:
                    self.assertIsNone(final['overall_score'])
                else:
                    self.assertAlmostEqual(final['overall_score'], .96 + .04 * value)
                request = {'rubric': {'criteria': criteria}, 'claim_review_policy': {
                    'profile': 'evidence-aware-v1', 'criterion_keys': ['scholar_claim_binding'],
                    'units': [1, 2], 'unavailable_score': None, 'cite_queried_frozen_evidence': True}}
                native = {'criteria': [{'key': key, 'score': score, 'status': 'unresolved' if score is None else 'judged',
                                       'reason': '按原维度核验。', 'evidence_ids': ['evidence-1']}
                                      for key, score in response['scores'].items()],
                          'claim_reviews': response['claim_reviews']}
                contract = {'judge_evidence': {'claim_review_keys': ['scholar_claim_binding']}}
                RUNTIME._validate_declared_claim_reviews(contract, request, native)
                if value is None:
                    broken = deepcopy(response)
                    broken['scores']['scholar_claim_binding'] = 0.
                    with self.assertRaises(ValueError):
                        validate_semantic_response(broken, criteria, claim_review_keys=['scholar_claim_binding'])
                    native['criteria'][1].update(score=0., status='judged')
                    with self.assertRaises(RUNTIME.ScoringRuntimeError):
                        RUNTIME._validate_declared_claim_reviews(contract, request, native)
