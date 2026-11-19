import ast
from datetime import date, datetime, time
from io import BytesIO
import json
import hashlib
import importlib.util
import sys
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import openpyxl
from eval_general_e2e.datasets.source_history import dataset_task_path
from eval_general_e2e.datasets.bundle import _parse_task_source, _strip_codeblock

ROOT = Path(__file__).resolve().parents[2]
NEWS = '02_Office_task_003_news_event_multifile_extract'
HR = '03_Data_Analysis_task_001_hr_worktime_reconciliation'


def source(task, frozen=False):
    path = next((ROOT / 'tasks/general/work').rglob(task + '.md'))
    if frozen:
        index = ROOT / 'eval_general_e2e/datasets/source-snapshots/general-custom70-v4/index.json'
        path = dataset_task_path(ROOT, path.relative_to(ROOT).as_posix(), index.relative_to(ROOT).as_posix())
    return _strip_codeblock(_parse_task_source(path)[1]['Automated Checks'])


class Round1ScoringRepairTests(unittest.TestCase):
    def test_v4_release_text_binding_accepts_only_registered_original_bytes(self):
        path = ROOT / 'tools/report/skills/general-e2e/score-general-e2e/scripts/release_baseline_text.py'
        spec = importlib.util.spec_from_file_location('_round1_release_binding', path)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        task = '02_Office_task_007_release_phase_gate_progression'
        code = source(task)
        contract = {'task_id': task, 'automated_checks': code}
        marker = m.marker(contract, m.V4_CONTRACT, m.V4_DATASET)
        self.assertIsNotNone(marker)
        self.assertIsNone(m.marker({**contract, 'automated_checks': code + '\n'}, m.V4_CONTRACT, m.V4_DATASET))
        self.assertIsNone(m.marker(contract, m.V4_CONTRACT, {**m.V4_DATASET, 'digest': '0' * 64}))
        manifest = {'identity': {'task_id': task}, 'digests': {'contract_sha256': m.V4_CONTRACT},
                    'dataset': m.V4_DATASET, 'runtime': {'release_baseline_text_profile': marker}}
        fixed, receipt = m.effective_source(manifest, code, code, None)
        scope = {}
        exec(fixed, scope)
        self.assertEqual(receipt['original_source_sha256'], m.V4_SOURCE)
        self.assertTrue(all(set(f)=={'path','canonical_sha256','declared_sha256','size'}
                            for f in receipt['original_public_text_identities']))
        marker3 = m.marker(contract, m.V4_CONTRACT, m.V3_DATASET)
        self.assertEqual(marker3, marker)
        fixed3, _ = m.effective_source({**manifest, 'dataset': m.V3_DATASET}, code, code, None)
        self.assertEqual(fixed3, fixed)
        ref = m.registry(m.V4_CONTRACT)['files'][0]
        raw = (ROOT / 'workspace/general/work/02_Office/02_Office_task_007_release_phase_gate_progression/exec' / ref['path']).read_bytes()
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'public-source.json'
            for value in [raw, raw.replace(b'\n', b'\r\n')]:
                p.write_bytes(value)
                self.assertTrue(scope['_ge2e_release_protected_matches'](p, ref['path']))
            p.write_bytes(raw + b' ')
            self.assertFalse(scope['_ge2e_release_protected_matches'](p, ref['path']))
        self.assertEqual(m.effective_source({**manifest, 'runtime': {}}, code, code, None), (code, None))

    def failure_module(self):
        p = ROOT / 'tools/report/skills/general-e2e/orchestrate-general-e2e/scripts/registered_rule_source_failures.py'
        spec = importlib.util.spec_from_file_location('_round1_source_failure_tests', p)
        module = importlib.util.module_from_spec(spec)
        with patch("sys.path", [str(p.parent), *sys.path]):
            spec.loader.exec_module(module)
        return module

    def test_hr_failure_retirement_rejects_changed_identity_error_judge_and_source(self):
        m = self.failure_module()
        original = source(HR, True)
        read = lambda p: json.loads(p.read_text())
        rt = SimpleNamespace(_read_json=read)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            worker = root / 'rule-review/discovery/worker'
            worker.mkdir(parents=True)
            request = {'automated_checks': original, 'rule_review': {
                'schema_version': 'wildclawbench.general-e2e-rule-review-worker/v1',
                'profile': 'hr-fields-and-sources-semantic-review/v1', 'mode': 'discover', 'decisions': {}}}
            result = {'ok': False, 'result': None, 'error': {'type': 'TypeError', 'message': '无法输出证据类型：time'},
                      'worker': {'pid': 123}}
            (worker / 'request.json').write_text(json.dumps(request))
            (worker / 'result.json').write_text(json.dumps(result))
            manifest = {'identity': {'task_id': HR}, 'digests': {'contract_sha256': m.HR_CONTRACT},
                        'dataset': {'id': 'general-custom70-v4',
                                    'digest': '914783354b23efa4f814342187ebe931df76cbcb0b2ea3dd85bd3f5705f485ff'},
                        'runtime': {'rule_review_profile': 'hr-fields-and-sources-semantic-review/v1',
                                    'hr_source_locator_profile': 'hr-equivalent-row-prefix-locators/v1'}}
            task = {'thread': None, 'score': None}
            contract = {'task_id': HR, 'automated_checks': original}
            # Synthetic request source is SHA-bound independently of the actual
            # frozen discovery source, which is replayed by the round diagnostic.
            with patch.object(m, 'HR_REQUEST_SOURCE', hashlib.sha256(original.encode()).hexdigest()):
                self.assertEqual(m.evidence(rt, root, manifest, contract, task), result)
                task['thread'] = {'status': 'RUNNING'}
                with self.assertRaises(ValueError):
                    m.evidence(rt, root, manifest, contract, task)
                task['thread'] = None
                result['error']['message'] = 'unknown failure'
                (worker / 'result.json').write_text(json.dumps(result))
                with self.assertRaises(ValueError):
                    m.evidence(rt, root, manifest, contract, task)
                result['error']['message'] = '无法输出证据类型：time'
                (worker / 'result.json').write_text(json.dumps(result))
                request['automated_checks'] += '\n'
                (worker / 'request.json').write_text(json.dumps(request))
                with self.assertRaises(ValueError):
                    m.evidence(rt, root, manifest, contract, task)
            self.assertEqual(m.expected_phase(HR), 'RULES_RUNNING')
            request['automated_checks'] = original
            result['error']['message'] = 'Object of type time is not JSON serializable'
            self.write_json = lambda p, v: p.write_text(json.dumps(v), encoding='utf-8')
            self.write_json(worker / 'request.json', request)
            self.write_json(worker / 'result.json', result)
            manifest['runtime']['shared_rule_source_repair'] = dict(m.HR_V1_MARKER)
            with patch.object(m, 'HR_V1_REQUEST_SOURCE', hashlib.sha256(original.encode()).hexdigest()):
                self.assertEqual(m.evidence(rt, root, manifest, contract, task), result)
                manifest['runtime']['shared_rule_source_repair']['current_source_sha256'] = '0' * 64
                with self.assertRaisesRegex(ValueError, 'PROFILE'):
                    m.evidence(rt, root, manifest, contract, task)

    def test_partial_hr_resources_are_retained_without_claiming_completeness(self):
        m = self.failure_module()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            p = root / 'rule-review/discovery/runtime/workspace/评分证据'
            p.mkdir(parents=True)
            for name in ['01候选分析全文.json', '02候选核对记录.json', '03部门及身份对照.json']:
                (p / name).write_text('{}')
            self.assertEqual(len(m.partial_evidence_paths(root, HR)), 3)
            (p / 'unexpected.json').write_text('{}')
            with self.assertRaises(ValueError):
                m.partial_evidence_paths(root, HR)

    def test_hr_time_is_serialized_without_changing_dates_or_numeric_functions(self):
        old, new = {}, {}
        exec(source(HR, True), old)
        exec(source(HR), new)
        value = time(9, 30, 1, 2345)
        with self.assertRaisesRegex(TypeError, 'time'):
            json.dumps(value, default=old['to_jsonable'])
        self.assertEqual(json.loads(json.dumps(value, default=new['to_jsonable'])), '09:30:01.002345')
        for value in [date(2026, 4, 1), datetime(2026, 4, 1, 9, 30)]:
            self.assertEqual(old['to_jsonable'](value), new['to_jsonable'](value))
        with self.assertRaisesRegex(TypeError, 'object'):
            new['to_jsonable'](object())
        a = {n.name: ast.dump(n) for n in ast.parse(source(HR, True)).body if isinstance(n, ast.FunctionDef)}
        current_ast = ast.parse(source(HR))
        grade = next(n for n in current_ast.body if isinstance(n, ast.FunctionDef) and n.name == 'grade')
        returned = grade.body[-1]
        self.assertIsInstance(returned, ast.Return)
        self.assertEqual(ast.unparse(returned.value),
                         'json.loads(json.dumps(scores, ensure_ascii=False, allow_nan=False, default=to_jsonable))')
        # Peel only the JSON transport wrapper; all original numeric computation
        # and diagnostic construction must remain structurally identical.
        grade.body[-1] = ast.Return(value=ast.Name(id='scores', ctx=ast.Load()))
        b = {n.name: ast.dump(n) for n in current_ast.body if isinstance(n, ast.FunctionDef)}
        self.assertEqual({k: v for k, v in a.items() if k != 'to_jsonable'},
                         {k: v for k, v in b.items() if k != 'to_jsonable'})
        result = json.loads(json.dumps({'overall_score': 0.25, '诊断': {'clock': value}},
                                       default=new['to_jsonable'], allow_nan=False))
        self.assertEqual(result['overall_score'], 0.25)

    def workbook(self, *, dimension='全期', wrong_count=False, duplicate=False, extra=False):
        w = openpyxl.Workbook()
        s = w.active
        s.title = '事件清单'
        s.append(['事件ID', '事件日期', '类别代码', '类别名称', '规范主体/主题', '核心事实', '报道片段数'])
        s.append(['E1', '2026-04-10', 'policy_update', '政策更新', '主体甲', '事实甲', 1])
        s.append(['E2', '2026-04-11', 'policy_update', '政策更新', '主体乙', '事实乙', 2])
        s = w.create_sheet('主体提及')
        s.append(['规范主体', '主体类型', '提及名称/别名', '来源文件', '章节/栏目', '首次提及顺序'])
        s.append(['主体甲', 'policy_program', '原文甲', 'source.md', '正文', 1])
        s = w.create_sheet('排除记录')
        s.append(['排除ID', '来源文件', '章节/栏目', '排除内容/简短片段', '排除原因'])
        s.append(['X1', 'source.md', '噪声', '片段', 'page_noise'])
        s = w.create_sheet('分类统计')
        s.append(['统计维度', '日期', '类别代码', '类别名称', '事件数', '报道片段数合计'])
        s.append(['日期', '2026-04-10', 'policy_update', '政策更新', 1, 1])
        s.append(['日期', '2026-04-10', '小计', '—', 1, 1])
        cats = ['policy_update', 'company_disclosure', 'macro_data', 'market_movement', 'other_finance']
        for category in cats:
            count, fragments = ((99 if wrong_count else 2), 3) if category == cats[0] else (0, 0)
            s.append([dimension, '—', category, category, count, fragments])
        if duplicate:
            s.append([dimension, '—', 'policy_update', '政策更新', 2, 3])
        if extra:
            s.append([dimension, '—', 'unknown_category', '未知类别', 1, 1])
        s.append([dimension, '—', '合计', '—', 2, 3])
        stream = BytesIO()
        w.save(stream)
        w.close()
        return stream.getvalue()

    def news_scope(self):
        scope = {}
        exec(source(NEWS), scope)
        return scope

    def test_equivalent_headings_keep_values_and_physical_cells(self):
        s = self.news_scope()
        result = s['read_workbook'](self.workbook())
        self.assertEqual(result['events'][0]['category'], 'policy_update')
        self.assertEqual(result['events'][0]['category_zh'], '政策更新')
        self.assertEqual(result['entity_mentions'][0]['alias_seen'], '原文甲')
        self.assertEqual(result['entity_mentions'][0]['source_section'], '正文')
        self.assertEqual(result['unclassified_items'][0]['item_id'], 'X1')
        self.assertEqual(result['unclassified_items'][0]['evidence_snippet'], '片段')
        self.assertEqual(len(result['category_summary']), 5)
        self.assertEqual(s['rollup_score'](result), 1)
        raw = next(t for t in result['_complete_workbook_cells'] if t['sheet'] == '分类统计')
        self.assertEqual(len(raw['rows']), 9)
        self.assertTrue(raw['category_scope_projection']['physical_cells_preserved'])
        self.assertFalse(raw['category_scope_projection']['candidate_values_synthesized'])

    def test_unknown_categories_duplicates_and_wrong_values_still_fail_original_rules(self):
        s = self.news_scope()
        for kwargs in [dict(wrong_count=True), dict(duplicate=True), dict(extra=True)]:
            with self.subTest(kwargs=kwargs):
                self.assertLess(s['rollup_score'](s['read_workbook'](self.workbook(**kwargs))), 1)

    def test_unknown_scope_is_not_guessed(self):
        s = self.news_scope()
        with self.assertRaisesRegex(s['EvidenceError'], 'scope'):
            s['read_workbook'](self.workbook(dimension='未知统计维度'))

    def test_original_news_scoring_functions_and_weights_are_unchanged(self):
        a, b = ast.parse(source(NEWS, True)), ast.parse(source(NEWS))
        for name in ['grade', 'rollup_score', 'event_identity', 'mention_identity', 'set_f1']:
            left = next(n for n in a.body if isinstance(n, ast.FunctionDef) and n.name == name)
            right = next(n for n in b.body if isinstance(n, ast.FunctionDef) and n.name == name)
            self.assertEqual(ast.dump(left), ast.dump(right))


if __name__ == '__main__':
    unittest.main()
