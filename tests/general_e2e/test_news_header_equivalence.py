import ast
from copy import deepcopy
from io import BytesIO
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import openpyxl
from tests.general_e2e.test_local_scoring_runtime import RUNTIME
from tests.general_e2e.test_round1_scoring_repairs import source, NEWS

ADAPTER = RUNTIME.news_header_equivalence


class NewsHeaderEquivalenceTests(unittest.TestCase):
    def inputs(self):
        original = source(NEWS, True)
        contract = {'task_id': NEWS, 'automated_checks': original}
        manifest = {'identity': {'task_id': NEWS}, 'dataset': dict(ADAPTER.DATASET),
                    'digests': {'contract_sha256': ADAPTER.CONTRACT_SHA}, 'runtime': {}}
        manifest['runtime']['news_header_equivalence_profile'] = ADAPTER.marker(
            contract, ADAPTER.CONTRACT_SHA, ADAPTER.DATASET)
        return original, contract, manifest

    def scope(self, enabled):
        original, _, manifest = self.inputs()
        current = source(NEWS)
        if enabled:
            current, _ = ADAPTER.effective_source(manifest, original, current, None)
        scope = {}
        exec(current, scope)
        return scope

    def workbook(self, *, equivalents=False, duplicate=False, unknown=False):
        w = openpyxl.Workbook()
        s = w.active; s.title = '主体提及'
        alias = '别名/原文名称' if equivalents else '提及名称/别名'
        s.append(['规范主体', '主体类型', alias, '来源文件', '章节/栏目', '首次提及顺序'])
        s.append(['甲', 'listed_company', '甲公司', 'source.md', '正文', 1])
        if duplicate:
            s.cell(1, 7, '提及名称/别名'); s.cell(2, 7, '冲突值')
        s = w.create_sheet('分类统计')
        fragments = '未登记片段标题' if unknown else '报道片段总数' if equivalents else '报道片段数合计'
        s.append(['类别代码', '事件数', fragments])
        s.append(['policy_update', 2, 3])
        stream = BytesIO(); w.save(stream); w.close(); return stream.getvalue()

    def test_new_names_only_extract_existing_values_and_preserve_complete_cells(self):
        old, new = self.scope(False), self.scope(True)
        data = self.workbook(equivalents=True)
        a, b = old['read_workbook'](data), new['read_workbook'](data)
        self.assertNotIn('alias_seen', a['entity_mentions'][0])
        self.assertNotIn('merged_source_count', a['category_summary'][0])
        self.assertEqual(b['entity_mentions'][0]['alias_seen'], '甲公司')
        self.assertEqual(b['category_summary'][0]['merged_source_count'], 3)
        self.assertEqual(a['_complete_workbook_cells'], b['_complete_workbook_cells'])

    def test_canonical_layout_and_original_scoring_functions_stay_identical(self):
        old, new = self.scope(False), self.scope(True)
        data = self.workbook()
        self.assertEqual(old['read_workbook'](data), new['read_workbook'](data))
        original, _, manifest = self.inputs(); current = source(NEWS)
        effective, receipt = ADAPTER.effective_source(manifest, original, current, None)
        functions = lambda code: {n.name: ast.dump(n) for n in ast.parse(code).body if isinstance(n, ast.FunctionDef)}
        a, b = functions(current), functions(effective)
        for name in ['grade', 'rollup_score', 'mention_identity', 'set_f1', 'capability_scores']:
            self.assertEqual(a[name], b[name])
        self.assertFalse(receipt['candidate_rewritten'])
        self.assertFalse(receipt['rubric_and_weights_changed'])
        self.assertFalse(receipt['numeric_decisions_assigned'])

    def test_duplicates_reject_and_unknown_names_remain_unmapped(self):
        scope = self.scope(True)
        with self.assertRaisesRegex(scope['EvidenceError'], 'Ambiguous explicit news'):
            scope['read_workbook'](self.workbook(equivalents=True, duplicate=True))
        result = scope['read_workbook'](self.workbook(equivalents=True, unknown=True))
        self.assertNotIn('merged_source_count', result['category_summary'][0])

    def test_exact_dataset_contract_source_and_prior_effective_hash_are_required(self):
        original, contract, manifest = self.inputs()
        self.assertIsNotNone(manifest['runtime']['news_header_equivalence_profile'])
        self.assertIsNone(ADAPTER.marker(contract, '0'*64, ADAPTER.DATASET))
        self.assertIsNone(ADAPTER.marker(contract, ADAPTER.CONTRACT_SHA, {**ADAPTER.DATASET, 'id': 'general-custom70-v4'}))
        self.assertIsNone(ADAPTER.marker({**contract, 'automated_checks': original+'\n'}, ADAPTER.CONTRACT_SHA, ADAPTER.DATASET))
        with self.assertRaisesRegex(ValueError, 'PROFILE_MISMATCH'):
            ADAPTER.effective_source(manifest, original, source(NEWS)+'\n', None)
        old = deepcopy(manifest); old['runtime'] = {}
        self.assertEqual(ADAPTER.effective_source(old, original, source(NEWS), {'old': True}), (source(NEWS), {'old': True}))

    def fixture(self, folder):
        p = Path(folder)
        write = lambda name, value: (p/name).write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
        for name in ['worker', 'grader-evidence/files/evaluator_evidence', 'candidate-original/workspace/results']:
            (p/name).mkdir(parents=True)
        (p/'candidate-original/workspace/results/events.xlsx').write_bytes(self.workbook(equivalents=True))
        identity = {'task_id': NEWS, 'scoring_attempt_id': 'synthetic-001'}
        original, contract, manifest = self.inputs()
        manifest['identity'] = identity
        manifest['paths'] = {'candidate_original': 'candidate-original/workspace'}
        manifest['runtime'] = {'shared_rule_source_repair': {
            'profile': 'news-equivalent-headings-and-explicit-rollup-scope/v1',
            'source_sha256': ADAPTER.SOURCE_SHA, 'current_source_sha256': ADAPTER.PRIOR_SOURCE_SHA}}
        write('worker/request.json', {'automated_checks': source(NEWS)})
        write('worker/result.json', {'ok': True})
        write('rule-source-correction.json', {'effective_source_sha256': ADAPTER.PRIOR_SOURCE_SHA})
        sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
        write('rule-audit.json', {'status': 'completed', 'identity': identity,
            'worker': {'return_code': 0, 'process_tree_cleanup': {'remaining': False},
                       'request_sha256': sha(p/'worker/request.json')},
            'source_correction': {'sha256': sha(p/'rule-source-correction.json')}})
        write('rule-component.json', {})
        write('grader-evidence/files/evaluator_evidence/03_other_tables.json', {'tables': {
            'entity_mentions': [{'canonical_entity': '甲', '_location': '主体提及!row2'}],
            'category_summary': [{'category': 'policy_update', '_location': '分类统计!row2'}]}})
        review = {'task_id': NEWS, 'scoring_attempt_id': 'synthetic-001', 'origin': 'evaluator',
            'status': 'NEEDS_ATTENTION', 'frozen_component_preserved': True,
            **{key: False for key in ['formal_score_published', 'semantic_response_imported', 'verify_score_passed',
                'candidate_original_modified', 'rules_rerun', 'harness_rerun']},
            'issues': [{'criterion_key': 'automated.entity_links', 'header': '别名/原文名称', 'candidate_location': '主体提及!C1:C2'},
                       {'criterion_key': 'automated.category_rollup', 'header': '报道片段总数', 'candidate_location': '分类统计!C1:C2'}]}
        write('infrastructure-review.json', review)
        rt = SimpleNamespace(_read_json=lambda path: json.loads(Path(path).read_text()), _sha256_file=sha)
        task = {'thread': {'status': 'COMPLETED'}, 'score': None}
        return p, manifest, contract, rt, task, write

    def test_completed_failure_retirement_proves_omission_without_assigning_scores(self):
        with tempfile.TemporaryDirectory() as folder:
            p, m, c, rt, task, _ = self.fixture(folder)
            proof = ADAPTER.validate_blocker(rt, p, m, c, task)
            self.assertEqual(len(proof['observations']), 2)
            self.assertFalse(proof['numeric_score_assigned'])

    def test_failure_retirement_rejects_active_score_unknown_heading_or_nonmissing_field(self):
        for mutation in ['active', 'score', 'heading', 'field', 'dataset', 'worker', 'range']:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as folder:
                p, m, c, rt, task, write = self.fixture(folder)
                if mutation == 'active': task['thread']['status'] = 'RUNNING'
                elif mutation == 'score': write('score.json', {})
                elif mutation == 'dataset': m['dataset']['digest'] = '0'*64
                elif mutation == 'worker': write('worker/result.json', {'ok': False})
                elif mutation == 'heading':
                    d = rt._read_json(p/'infrastructure-review.json'); d['issues'][0]['header'] = '未知'; write('infrastructure-review.json', d)
                elif mutation == 'range':
                    d = rt._read_json(p/'infrastructure-review.json'); d['issues'][0]['candidate_location'] = '主体提及!C1:C9999'; write('infrastructure-review.json', d)
                else:
                    write('grader-evidence/files/evaluator_evidence/03_other_tables.json', {'tables': {
                        'entity_mentions': [{'alias_seen': '已提取'}], 'category_summary': [{'category': 'policy_update'}]}})
                with self.assertRaises(ValueError): ADAPTER.validate_blocker(rt, p, m, c, task)

    def test_native_prose_sheet_label_is_preserved_and_actual_locator_is_independently_bound(self):
        with tempfile.TemporaryDirectory() as folder:
            p, m, c, rt, task, write = self.fixture(folder)
            d = rt._read_json(p/'infrastructure-review.json')
            d['issues'][0]['candidate_location'] = '事件清单以外的主体提及!C1:C2'
            write('infrastructure-review.json', d)
            observations = ADAPTER.validate_blocker(rt, p, m, c, task)['observations']
            self.assertFalse(observations[0]['native_sheet_label_matches'])
            self.assertEqual(observations[0]['observed_location'], '主体提及!C1:C2')
            write('grader-evidence/files/evaluator_evidence/03_other_tables.json', {'tables': {
                'entity_mentions': [{'canonical_entity': '甲', '_location': '未知表!row2'}],
                'category_summary': [{'category': 'policy_update', '_location': '分类统计!row2'}]}})
            with self.assertRaises(ValueError): ADAPTER.validate_blocker(rt, p, m, c, task)

    def test_retirement_locks_original_draft_and_grader_files_and_replays_native_identity(self):
        scripts = Path(RUNTIME.__file__).parents[2]/'orchestrate-general-e2e/scripts'
        sys.path.insert(0, str(scripts))
        try:
            spec = importlib.util.spec_from_file_location('_news_retirement_test', scripts/'framework_failure_retirement.py')
            retirement = importlib.util.module_from_spec(spec); spec.loader.exec_module(retirement)
            import verify_judge_context
        finally:
            sys.path.remove(str(scripts))
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)/'orchestration'; attempt = root/'case'
            p, manifest, contract, rt, task, write = self.fixture(attempt)
            (p/'private').mkdir(); write('private/contract.json', contract)
            manifest['paths']['contract'] = 'private/contract.json'; write('attempt-manifest.json', manifest)
            write('semantic-response-review-draft.json', {'unpublished': True})
            (root/'prompt.md').write_text('synthetic frozen prompt')
            task.update(task_id=NEWS, attempt_path='case', prompt_path='prompt.md',
                        scoring_attempt_id='synthetic-001', phase='SCORE_VERIFICATION_PENDING',
                        prompt_sha256=rt._sha256_file(root/'prompt.md'), history=[])
            task['thread'].update(thread_id='native-001', host_id='local')
            state = {'judge': {'model': 'gpt-6.1-sol', 'reasoning_effort': 'high'}, 'tasks': [task], 'score_skill': {}}
            rt._state_root = lambda path: Path(path)
            rt._verify_state = lambda path: state
            rt._identifier = lambda value, name: value
            rt._task_by_id = lambda state, identity: state['tasks'][0]
            rt._run_score_command = lambda *args: None
            rt._required_string = lambda value, name: value
            rt._timestamp = lambda value: '2026-11-18T00:00:00Z'
            rt._now = lambda: None
            def write_new(path, value):
                with Path(path).open('x') as stream:
                    json.dump(value, stream)
            rt._write_new_json = write_new
            rt._save = lambda root, state, now: state
            native = {'status': 'PASS', 'unfinished_turns': [], 'thread_id': 'native-001',
                      'model': 'gpt-6.1-sol', 'effort': 'high', 'prompt_sha256': task['prompt_sha256']}
            with patch.object(retirement.aggregation_runtime_failure, 'matches', return_value=False), \
                 patch.object(verify_judge_context, 'verify_context', return_value=native):
                retirement.record(rt, root, task_id=NEWS, reason='registered parser defect', sdk_file=Path('synthetic-sdk'))
                proof = retirement.verify(rt, root, state, task)
                self.assertEqual(task['phase'], 'UNSCORED')
                self.assertTrue(proof['semantic_judging_performed'])
                self.assertFalse(proof['semantic_result_published'])
                self.assertFalse((p/'score.json').exists())
                paths = {row['path'] for row in proof['locks']}
                self.assertIn('case/semantic-response-review-draft.json', paths)
                self.assertIn('case/grader-evidence/files/evaluator_evidence/03_other_tables.json', paths)
                write('semantic-response-review-draft.json', {'changed': True})
                with self.assertRaisesRegex(ValueError, 'PROOF_DRIFT'):
                    retirement.verify(rt, root, state, task)


if __name__ == '__main__':
    unittest.main()
