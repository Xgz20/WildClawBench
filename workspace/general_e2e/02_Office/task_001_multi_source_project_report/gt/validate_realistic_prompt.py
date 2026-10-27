"""Author regression checks only; never evidence of an evaluated Agent's self-check.

Run with bundled Python -B -X utf8. --refresh-metadata updates this task's two
manifests; no Office source, candidate report, historical run or mapping is edited.
"""
from pathlib import Path
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import patch
from zipfile import ZipFile
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import types
import unittest

import openpyxl
from lxml import etree

GT = Path(__file__).resolve().parent
CASE = GT.parent
ROOT = CASE.parents[3]
TASK = ROOT / 'tasks/general_e2e/02_Office/02_Office_task_001_multi_source_project_report.md'
MAP = ROOT / 'tools/report/data/checkpoint_capability_map7.yaml'
TRIAL = Path('D:/tmp/_evaluation/20260923035438Z')
REVISION = 'realistic-prompt-v2-20260923'
EXPECTED_MAPPING_SHA = 'cd1a5cebf8c197081cc4eacf43eb6b3193787786b1ac093e3707b223d6ff711d'
PARSER_PYTHON = shutil.which('python') or sys.executable


def parser_process(code, *args):
    """Use the installed project-parser dependencies without modifying either runtime."""
    proc = subprocess.run([PARSER_PYTHON, '-B', '-X', 'utf8', '-c', code, *map(str, args)],
                          check=True, capture_output=True, text=True, encoding='utf-8', timeout=30)
    return json.loads(proc.stdout)


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


TEXT = TASK.read_text(encoding='utf-8')
CODE = re.search(r'## Automated Checks\s+.*?```python\n(.*?)\n```', TEXT, re.S)[1]
GRADER = types.ModuleType('office_task_grader')
exec(compile(CODE, str(TASK), 'exec'), GRADER.__dict__)
FACTS = load(GT / 'independent_facts.json')
RUBRIC = TEXT.split('## LLM Judge Rubric\n', 1)[1].split('\n## Workspace Path', 1)[0].strip()
PROMPT = TEXT.split('## Prompt\n', 1)[1].split('\n## Expected Behavior', 1)[0].strip()
REFERENCE = GT / 'reference'


def xml_text(path, member):
    with ZipFile(path) as archive:
        root = etree.fromstring(archive.read(member))
        return '\n'.join(root.xpath('//*[local-name()="t"]/text()'))


def review_items():
    return {
        'atomic_facts': [
            {'fact_id': f'{t["id"]}.{field}', 'verdict': 'supported',
             'citations': [{'evidence_id': 'candidate/project_report.docx', 'locator': t['id']},
                           {'evidence_id': 'independent_facts.json', 'locator': f'{t["id"]}.{field}'}]}
            for t in FACTS for field in ['goal', 'plan', 'owner', 'deadline', 'footnote', 'qualifier']
            if t.get(field)
        ], 'unsupported_assertions': [], 'citations': []
    }


class RevisionTests(unittest.TestCase):
    def test_public_prompt_and_packaging(self):
        self.assertEqual(len(list((CASE / 'exec').iterdir())), 6)
        self.assertFalse((CASE / 'exec/00_材料说明.md').exists())
        for hint in ['24', '隐藏', '奇数', '第5行', '00_材料说明', '132', 'gt/']:
            self.assertNotIn(hint, PROMPT)
        for required in ['完整总结', '来源信息', '复核', '一致性', '/tmp_workspace/results/', 'project_report.docx', 'project_report.pdf']:
            self.assertIn(required, PROMPT)

    def test_task_parser(self):
        parsed = parser_process(
            'import importlib.util,json,sys; from pathlib import Path; '
            'spec=importlib.util.spec_from_file_location("task_parser",sys.argv[1]); '
            'module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); '
            'p=module.parse_task_md(Path(sys.argv[2])); '
            'print(json.dumps({k:p[k] for k in ["prompt","rubric_criteria","automated_checks"]},ensure_ascii=False))',
            ROOT / 'src/utils/task_parser.py', TASK)
        self.assertEqual(parsed['prompt'], PROMPT)
        self.assertEqual(len(parsed['rubric_criteria']), 6)
        self.assertEqual(parsed['automated_checks'], CODE.strip())

    def test_mapping_and_manifest(self):
        self.assertEqual(sha(MAP), EXPECTED_MAPPING_SHA)
        mappings = parser_process('import yaml,json,sys; from pathlib import Path; '
                                  'print(json.dumps(yaml.safe_load(Path(sys.argv[1]).read_text(encoding="utf-8"))[sys.argv[2]]))', MAP, TASK.stem)
        manifest = load(GT / 'checkpoint_manifest.json')
        self.assertEqual(manifest['rubric_revision'], REVISION)
        self.assertEqual(manifest['rubric_sha256'], hashlib.sha256(RUBRIC.encode()).hexdigest())
        for key, (checkpoint, weight, capability) in GRADER.SPECS.items():
            item = manifest['runtime_keys'][key]
            self.assertEqual((item['checkpoint'], item['within_group_weight'], item['capability']),
                             (checkpoint, weight, capability))
            self.assertEqual(mappings.get(key), [capability] if capability else None)

    def test_material_hashes(self):
        for item in load(GT / 'material_manifest.json')['files']:
            path = CASE / 'exec' / item['name']
            self.assertEqual(sha(path), item['sha256'])
            self.assertEqual(path.stat().st_size, item['bytes'])

    def test_business_rules_are_in_sources(self):
        workbook = openpyxl.load_workbook(CASE / 'exec/04_项目工作簿_v1.0.xlsx', data_only=True)
        try:
            tables = {s.title: [r for r in list(s.values)[4:] if r[0]] for s in workbook}
            self.assertEqual(workbook['补录明细'].sheet_state, 'hidden')
            self.assertTrue(all(r[8] == '新增独立记录' for r in tables['补录明细'] if str(r[0]).startswith('S-')))
            self.assertEqual(workbook['阅读说明']['B7'].value, 'v0.9')
            self.assertEqual(workbook['阅读说明']['C7'].value, '2026-09-12')
            self.assertEqual(workbook['阅读说明']['D7'].value, '历史快照')
            self.assertIn('空白字段表示未提供', workbook['阅读说明']['A3'].value)
            self.assertIn('有效性', str(list(workbook['验收记录'].values)[3]))
            counts = {name: sum(str(r[0]).startswith(prefix) for r in tables[name]) for name, prefix in
                      [('任务台账', ('XQ-', 'YL-')), ('指标明细', 'M-'), ('验收记录', 'A-'), ('问题记录', 'IS-'), ('补录明细', 'S-')]}
            self.assertEqual(counts, load(GT / 'material_manifest.json')['counts'])
            for task in FACTS:
                metrics = [r for name in ['指标明细', '补录明细'] for r in tables[name]
                           if r[1] == task['project'] and r[2] == task['id']]
                accepted = [r for r in tables['验收记录'] if r[1] == task['project'] and r[2] == task['id'] and r[7] == '有效']
                problems = [r for r in tables['问题记录'] if r[1] == task['project'] and r[2] == task['id']]
                self.assertEqual(sum(r[5] for r in metrics), task['planned'])
                self.assertEqual(sum(r[6] for r in metrics), task['done'])
                self.assertEqual(sum(r[5] == '通过' for r in accepted), task['accepted'])
                self.assertEqual(len(accepted), task['acceptance_total'])
                self.assertEqual(len({r[0] for r in problems if r[4] == '未关闭'}), task['open_issues'])
                source = xml_text(CASE / 'exec' / task['doc_source'], 'word/document.xml')
                self.assertIn(task['goal'], source)
                self.assertIn(task['issue'], source)
                self.assertIn('优先跟进问题', source)
                self.assertIn('已完成记录量占计划记录量的比例', source)
                self.assertIn('不表示正式任务验收结论', source)
        finally:
            workbook.close()

    def test_materials_keep_facts_without_solver_directions(self):
        forbidden = ['隐藏补录表', '此限定应随对应任务进入报告', '本页演讲者备注',
                     '记录区从第5行开始', '填写 24 项任务', '脚注中的前置条件应随',
                     '本材料的阅读口径', '附录 B 交接口径和归档位置']
        for path in (CASE / 'exec').iterdir():
            with ZipFile(path) as archive:
                for member in archive.namelist():
                    if not member.endswith('.xml'):
                        continue
                    content = ''.join(etree.fromstring(archive.read(member)).xpath('//*[local-name()="t"]/text()'))
                    for hint in forbidden:
                        self.assertNotIn(hint, content, (path.name, member))
        with ZipFile(CASE / 'exec/05_阶段汇报_v1.0.pptx') as archive:
            notes = ''.join(xml_text(CASE / 'exec/05_阶段汇报_v1.0.pptx', member)
                            for member in archive.namelist()
                            if re.fullmatch(r'ppt/notesSlides/notesSlide\d+\.xml', member))
        for task in FACTS:
            self.assertIn(task['footnote'], xml_text(CASE / 'exec' / task['doc_source'], 'word/footnotes.xml'))
            if task.get('qualifier'):
                self.assertIn(task['qualifier'], notes)

    def test_reference_rules(self):
        scores, _ = GRADER.rule_scores(REFERENCE, FACTS)
        for key in ['automated.c1_files', 'automated.c2_task_links', 'automated.c3_numeric_facts', 'automated.c4_unknowns']:
            self.assertEqual(scores[key]['score'], 1, (key, scores[key]))

    def test_acceptance_pair_variants(self):
        for header, value in [('验收通过/总数', '35/40'), ('验收通过数／验收总数（条）', '35 ／ 40'),
                              ('通过数/总数', '35条/40条'), ('验收总数/验收通过数', '40/35')]:
            with self.subTest(header=header):
                row = GRADER.rows_from_tables({'tables': [{'table': 1, 'rows': [['任务ID', header], ['XQ-001', value]]}]})[0]
                self.assertEqual((GRADER.number(row['accepted']), GRADER.number(row['acceptance_total'])), (35, 40))

    def test_actual_trial_combined_column_regression(self):
        candidate = TRIAL / 'deliverables/project_report.docx'
        if not candidate.exists():
            self.skipTest('Optional historical artifact not present on this host')
        # Read the original Office file; only adapt its containing folder, not its contents.
        doc = GRADER.extract_docx(candidate)
        with patch.object(GRADER, 'extract_docx', return_value=doc):
            scores, _ = GRADER.rule_scores(REFERENCE, FACTS)
        self.assertEqual(scores['automated.c3_numeric_facts']['score'], 1)

    def test_pair_errors_are_not_hidden(self):
        doc = GRADER.extract_docx(TRIAL / 'deliverables/project_report.docx') if (TRIAL / 'deliverables/project_report.docx').exists() else None
        if doc is None:
            self.skipTest('Optional historical artifact not present on this host')
        table = next(t for t in doc['tables'] if '验收通过/总数' in t['rows'][0])
        col = table['rows'][0].index('验收通过/总数')
        row = next(r for r in table['rows'][1:] if 'XQ-001' in r)
        for value, status, score in [('99/40', 'partial', 119/120), ('35/40/50', 'undetermined', None)]:
            row[col] = value
            with patch.object(GRADER, 'extract_docx', return_value=doc):
                scores, _ = GRADER.rule_scores(REFERENCE, FACTS)
            self.assertEqual(scores['automated.c3_numeric_facts']['status'], status)
            self.assertEqual(scores['automated.c3_numeric_facts']['score'], score)

    def test_conflicting_separate_and_combined_columns(self):
        row = GRADER.rows_from_tables({'tables': [{'table': 1, 'rows': [
            ['任务ID', '验收通过数', '验收通过/总数'], ['XQ-001', '99', '35/40']]}]})[0]
        self.assertIn('accepted', row['_numeric_conflicts'])

    def test_semantic_coverage_is_continuous(self):
        for omitted in [0, 1, 24, 132]:
            review = review_items()
            for atom in review['atomic_facts'][:omitted]:
                atom['verdict'] = 'omitted'
            actual = GRADER.c3_from_review(review, FACTS)
            self.assertAlmostEqual(actual['score'], (132-omitted)/132)
        review = review_items()
        for atom in review['atomic_facts']:
            if atom['fact_id'].endswith('.goal'):
                atom['verdict'] = 'omitted'
        actual = GRADER.c3_from_review(review, FACTS)
        self.assertAlmostEqual(actual['score'], 108/132)
        self.assertEqual(actual['evidence'][-1]['fact_coverage']['goal_coverage'], 0)

    def test_fabrication_and_missing_evidence(self):
        for verdict, status in [('incorrect', 'fail'), ('undetermined', 'undetermined')]:
            review = review_items()
            review['atomic_facts'][0]['verdict'] = verdict
            self.assertEqual(GRADER.c3_from_review(review, FACTS)['status'], status)
        review = review_items()
        review['unsupported_assertions'] = [{'claim': '全网推广已批准', 'citations': [{'evidence_id': 'candidate/project_report.docx', 'locator': '结论'}]}]
        self.assertEqual(GRADER.c3_from_review(review, FACTS)['score'], 0)

    def test_semantic_denominator_cannot_shrink_or_duplicate(self):
        for change in ['remove', 'duplicate']:
            review = review_items()
            if change == 'remove':
                review['atomic_facts'].pop()
            else:
                review['atomic_facts'][-1] = deepcopy(review['atomic_facts'][0])
            with self.assertRaises(ValueError):
                GRADER.c3_from_review(review, FACTS)

    def test_c7_states_and_nonvisual_scope(self):
        scopes = ['sources', 'facts', 'tables_figures', 'editability', 'docx_pdf_equivalence']
        for available, complete, n, status in [(False, False, 0, 'undetermined'), (True, False, 0, 'undetermined'),
                                               (True, True, 0, 'fail'), (True, True, 3, 'partial'), (True, True, 5, 'pass')]:
            review = {'coverage': {k: i < n for i, k in enumerate(scopes)}, 'citations': []}
            self.assertEqual(GRADER.c7_from_review(review, available, complete)['status'], status)
        self.assertFalse(GRADER.DEFAULT_JUDGE_CONFIG['candidate_visual_inspection_required'])
        self.assertTrue(GRADER.DEFAULT_JUDGE_CONFIG['require_all_visual_pages'])
        self.assertIn('不规定覆盖比例', RUBRIC)
        self.assertIn('单纯读取原材料不自动算复核', RUBRIC)

    def test_continuous_score_aggregation(self):
        scores = {key: GRADER.result('pass', 1) for key in GRADER.SPECS}
        scores['llm_judge.c3_fidelity'] = GRADER.result('partial', 108/132)
        aggregated = GRADER.aggregate(scores)
        self.assertAlmostEqual(aggregated['task_score'], 1 - .4 * .25 * (24/132))
        self.assertEqual(aggregated['capabilities']['state_awareness']['checkpoints'], ['C2', 'C4'])
        self.assertIsNone(aggregated['capabilities']['tool_invocation']['score'])

    def review_fixture(self):
        # Protocol fixtures exercise acceptance/arithmetic, not Judge calibration.
        config = {**GRADER.DEFAULT_JUDGE_CONFIG, 'availability': 'ready', 'independent_calibration_completed': True}
        package = {'rubric_revision': REVISION, 'renders_ready': True, 'page_ids': ['docx/page/1', 'pdf/page/1'],
                   'trace': {'available': True, 'complete': True},
                   'evidence_files': [{'id': 'independent_facts.json', 'path': 'facts.json'},
                                      {'id': 'candidate/project_report.docx', 'path': 'candidate.docx'},
                                      {'id': 'raw_trace', 'path': 'trace.jsonl'}]}
        review = {'rubric_revision': REVISION, 'config_sha256': 'fixture-hash', 'evidence_package_sha256': 'fixture-hash',
                  'reviewer': 'protocol-unit-fixture-not-real-judge', 'independently_calibrated': True, 'checkpoints': {}}
        return config, package, review

    def apply_fixture(self, config, package, review):
        scores = {}
        with patch.object(GRADER, 'sha', return_value='fixture-hash'), patch.object(
                GRADER, 'load', side_effect=lambda p: FACTS if str(p) == 'facts.json' else config):
            GRADER.apply_review(scores, review, package, Path('package.json'), Path('fixture-output'))
        return scores

    def test_review_accepts_and_computes_continuous_coverage(self):
        config, package, review = self.review_fixture()
        item = review_items()
        item.update(status='partial', score=0.5, reason='fixture supplied score must be recomputed',
                    citations=[{'evidence_id': 'candidate/project_report.docx', 'locator': 'all contents'}])
        for atom in item['atomic_facts']:
            if atom['fact_id'].endswith('.goal'):
                atom['verdict'] = 'omitted'
        review['checkpoints']['llm_judge.c3_fidelity'] = item
        scores = self.apply_fixture(config, package, review)
        self.assertAlmostEqual(scores['llm_judge.c3_fidelity']['score'], 108/132)

    def test_review_rejects_old_revision_and_invalid_citations(self):
        config, package, review = self.review_fixture()
        review['rubric_revision'] = 'old'
        with self.assertRaisesRegex(ValueError, 'rubric revision'):
            self.apply_fixture(config, package, review)
        review['rubric_revision'] = REVISION
        item = review_items()
        item.update(status='pass', score=1, citations=[{'evidence_id': 'candidate/project_report.docx', 'locator': 'all contents'}])
        item['atomic_facts'][0]['citations'][0]['evidence_id'] = 'invented-evidence'
        review['checkpoints']['llm_judge.c3_fidelity'] = item
        with self.assertRaisesRegex(ValueError, 'Citation'):
            self.apply_fixture(config, package, review)

    def test_c6_evaluator_visual_coverage_is_separate_from_candidate(self):
        config, package, review = self.review_fixture()
        item = {'status': 'pass', 'score': 1, 'citations': [{'evidence_id': 'candidate/project_report.docx', 'locator': 'pages'}],
                'viewed_pages': ['docx/page/1', 'pdf/page/1']}
        review['checkpoints']['llm_judge.c6_readability'] = item
        self.assertEqual(self.apply_fixture(config, package, review)['llm_judge.c6_readability']['status'], 'pass')
        item['viewed_pages'] = ['docx/page/1']
        self.assertEqual(self.apply_fixture(config, package, review)['llm_judge.c6_readability']['status'], 'undetermined')
        package['renders_ready'] = False
        self.assertEqual(self.apply_fixture(config, package, review)['llm_judge.c6_readability']['status'], 'evaluator_error')


def refresh_metadata():
    materials = load(GT / 'material_manifest.json')
    original = {x['name']: x for x in materials['files'] if x['name'] != '00_材料说明.md'}
    for path in (CASE / 'exec').iterdir():
        assert sha(path) == original[path.name]['sha256'], 'Office input changed unexpectedly: ' + path.name
    materials['files'] = list(original.values())
    materials['public_package_revision'] = REVISION
    materials['removed_public_files'] = ['00_材料说明.md']
    save(GT / 'material_manifest.json', materials)

    m = load(GT / 'checkpoint_manifest.json')
    if m.get('rubric_revision') != REVISION:
        m['historical_revision_validation'] = m.pop('revision_validation', {})
    m['rubric_revision'] = REVISION
    m['rubric_sha256'] = hashlib.sha256(RUBRIC.encode()).hexdigest()
    for key, (c, weight, capability) in GRADER.SPECS.items():
        m['runtime_keys'][key].update(checkpoint=c, within_group_weight=weight, capability=capability)
        if c == 'C4':
            m['runtime_keys'][key]['spec_item'] = '状态感知（沿用已确定映射）'
    m['business_only'] = ['C3', 'C6']
    public = {
        'C1': ['Prompt / 第2、4段'],
        'C2': ['Prompt / 第1、3段', 'exec/06_报告模板.docx / 来源说明', '原始材料的项目、任务与问题 ID'],
        'C3': ['Prompt / 第2、3段', '三部门 DOCX / 各任务目标与安排、脚注', 'XLSX / 原始记录与字段', 'PPTX / 对应备注'],
        'C4': ['Prompt / 第2段', 'exec/06_报告模板.docx / 待确认事项'],
        'C5': ['Prompt / 第4段'],
        'C6': ['Prompt / 第3、4段'],
        'C7': ['Prompt / 第3段'],
    }
    for c, refs in public.items():
        m['checkpoints'][c]['public'] = refs
    m['checkpoints']['C3'].update(
        criterion='有效来源事实正确覆盖数 / 132，单独报告目标正确覆盖数 / 24；接受合并概括。遗漏比例计分，实质矛盾或捏造判 fail，证据不足不计零。',
        scoring={'type': 'continuous', 'formula': 'supported / total', 'goal_coverage': 'supported goals / source goals',
                 'atomic_fields': ['goal', 'plan', 'owner', 'deadline', 'footnote', 'qualifier'],
                 'incorrect_or_unsupported_assertion': 'fail', 'insufficient_evidence': 'undetermined'})
    m['checkpoints']['C4']['spec_item'] = '状态感知（沿用已确定映射）'
    m['checkpoints']['C6']['criterion'] = '评测端全页检查内容、表图与必要说明可读及两版对应；不要求 Agent 看图，不强制原生脚注或固定分页，轻微美观问题不单独扣分。'
    m['checkpoints']['C7']['criterion'] = '同次实际复核五项范围，接受编写过程中的核对、非视觉表图/编辑属性验证及两版有意义抽查；只读材料、只导出成功或自述不算完成检查。'
    m['checkpoints']['C7']['coverage_policy'] = {
        'sources': '保持来源可追溯和实际复核口径；按任务或共用口径核对，允许穿插编写过程',
        'facts': '核对实际报告事实、统计结果或未知信息',
        'tables_figures': '接受非视觉数据、标签、结构或导出内容检查，不要求图像输入',
        'editability': '接受实际可编辑结构检查或副本编辑保存重开；与评测端 C5 区分',
        'docx_pdf_equivalence': '实际比较两版对应内容；允许有意义抽查，不固定深度',
    }
    m['tolerances']['percentage_points'] = '按展示精度四舍五入：±0.5 × 10^(-小数位数) 个百分点；不强制小数位数'
    m['tolerances']['layout'] = '无固定分页、表头或脚注形式；微小美观差异不扣分，仍验收可读性'
    m['packaging']['gt_contents'] = 'truth, manifests, reference deliverables and private revision regression; never distributed to candidate'
    m['packaging']['public_file_count'] = 6
    m['packaging']['fresh_workspace_required'] = 'Do not retain retired 00_材料说明.md from earlier runs'
    m['report_embedded_requirements']['self_verification'] = '实际复核来源、内容与一致性；非视觉方式和有效抽查可接受，不要求独立检查记录'
    m['revision_validation'] = {'revision': REVISION, 'record': 'gt/realistic_prompt_validation.json',
        'scope': 'Author regression only; no new solver trial or semantic Judge calibration',
        'historical_trial_policy': 'Frozen historical runs and scores remain unchanged',
        'mapping_sha256': sha(MAP)}
    save(GT / 'checkpoint_manifest.json', m)


if __name__ == '__main__':
    if GRADER.RUBRIC_REVISION != REVISION:
        raise SystemExit('Historical regression entry: use validate_evaluator_v3.py for the current evaluator. No metadata changed.')
    parser = argparse.ArgumentParser()
    parser.add_argument('--refresh-metadata', action='store_true')
    parser.add_argument('--parser-python', default=PARSER_PYTHON, help='Python with existing PyYAML and python-dotenv')
    args = parser.parse_args()
    PARSER_PYTHON = args.parser_python
    history_paths = [TRIAL / x for x in ['submitted_prompt.txt', 'task_snapshot.md', 'raw_trace.jsonl',
                                        'evaluation/single_run_result.json', 'deliverables/project_report.docx', 'deliverables/project_report.pdf']]
    before = {str(p): sha(p) for p in history_paths if p.is_file()}
    if args.refresh_metadata:
        refresh_metadata()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(RevisionTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    after = {p: sha(Path(p)) for p in before}
    assert before == after, 'Historical evidence changed'
    record = {'revision': REVISION, 'utc': datetime.now(timezone.utc).isoformat(),
              'status': 'pass' if result.wasSuccessful() else 'fail', 'tests_run': result.testsRun,
              'failures': [{'test': str(t), 'detail': e} for t, e in result.failures + result.errors],
              'skipped': [{'test': str(t), 'reason': e} for t, e in result.skipped],
              'task_sha256': sha(TASK), 'rubric_sha256': hashlib.sha256(RUBRIC.encode()).hexdigest(),
              'mapping_sha256': sha(MAP), 'historical_evidence_unchanged': before == after,
              'historical_hashes': before, 'public_files': [x['name'] for x in load(GT / 'material_manifest.json')['files']],
              'office_inputs_changed': False, 'new_agent_trial': 'not_run', 'semantic_judge_calibration': 'not_performed',
              'scope': 'Author regression, source-rule audit and arithmetic validation only; not candidate C7 evidence',
              'limitations': ['C7 semantic evidence examples have not been independently calibrated.',
                             'New prompt has not had a fresh solver trial.',
                             'Common discrete-score Judge and legacy seven-dimension report are not adapted.']}
    save(GT / 'realistic_prompt_validation.json', record)
    if result.wasSuccessful():
        m = load(GT / 'checkpoint_manifest.json')
        m['packaging']['formal_file_count'] = len(list((CASE / 'exec').iterdir())) + 4 + 2 + 2
        m['packaging']['actual_file_count'] = sum(p.is_file() for p in CASE.rglob('*'))
        m['revision_validation']['status'] = 'pass'
        m['revision_validation']['tests_run'] = result.testsRun
        save(GT / 'checkpoint_manifest.json', m)
    sys.exit(0 if result.wasSuccessful() else 1)
