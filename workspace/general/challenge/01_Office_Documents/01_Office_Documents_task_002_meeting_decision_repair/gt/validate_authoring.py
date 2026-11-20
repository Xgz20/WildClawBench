"""Reproducible author controls; does not assign semantic Judge scores."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re
import runpy
import shutil
import tempfile


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def mutate(path, name):
    with path.open(encoding='utf-8', newline='') as handle:
        reader = csv.DictReader(handle)
        fields, rows = list(reader.fieldnames), list(reader)
    by_id = {row['issue_id']: row for row in rows}
    if name == 'promote_proposals':
        for issue, owner, role, due in [('A16', 'U06', '平台负责人', '2026-11-09'), ('A17', 'U03', '运营经理', '2026-11-10')]:
            by_id[issue].update(status='待办', owner_id=owner, owner_role=role, due_date=due)
    elif name == 'forget_withdrawals':
        for issue in ('A13', 'A14', 'A15'):
            by_id[issue]['status'] = '待办'
    elif name == 'swap_same_name':
        by_id['A02'].update(owner_id='U03', owner_role='运营经理')
        by_id['A04'].update(owner_id='U02', owner_role='研发接口负责人')
    elif name == 'apply_unauthorized':
        by_id['A04'].update(owner_id='U02', owner_role='研发接口负责人', evidence_ids='S022;E05')
        by_id['A09'].update(due_date='2026-11-20', evidence_ids='S047;E06')
    elif name == 'file_order':
        by_id['A03'].update(due_date='2026-11-04', evidence_ids='S017;E01')
    elif name == 'never_reinstate':
        by_id['A12'].update(status='撤回', due_date='2026-11-02', evidence_ids='S060;S062')
    elif name == 'stale_evidence':
        for number, row in enumerate(rows):
            row['evidence_ids'] = f'S{number*5+4:03d}'
    elif name == 'duplicate_issue':
        rows.append(dict(rows[0]))
    elif name in {'missing_field', 'missing_owner_column'}:
        missing = 'next_step' if name == 'missing_field' else 'owner_id'
        fields.remove(missing)
        for row in rows:
            row.pop(missing)
    elif name == 'equivalent_csv':
        fields.reverse()
        rows.reverse()
        fields.append('comment')
        for row in rows:
            row['status'] = {'待办': 'active', '撤回': 'cancelled', '待定': 'pending'}[row['status']]
            row['due_date'] = row['due_date'].replace('-', '/')
            if not row['owner_id']:
                for key in ('owner_id', 'owner_role', 'due_date'):
                    row[key] = 'N/A'
            row['comment'] = 'Equivalent order and UTF-8 BOM'
    encoding = 'utf-8-sig' if name == 'equivalent_csv' else 'utf-8'
    with path.open('w', encoding=encoding, newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator='\n')
        writer.writeheader(); writer.writerows(rows)


def validate(exec_root, gt_root, task_path=None):
    exec_root, gt_root = Path(exec_root).resolve(), Path(gt_root).resolve()
    expected = json.loads((gt_root / 'expected.json').read_text(encoding='utf-8'))
    folded = runpy.run_path(str(gt_root / 'decision_model.py'))['fold'](exec_root, gt_root, expected['cutoff'])
    for label in expected['issues']:
        state = folded['issues'][label['issue_id']]
        assert all(state[key] == label[key] for key in ('status', 'owner_id', 'owner_role', 'due_date'))
        assert set(state['field_evidence'].values()) == set(label['evidence_ids'].split(';'))
    assert dict(Counter(row['status'] for row in expected['issues'])) == expected['counts']
    variants = ['reference', 'equivalent_csv', 'promote_proposals', 'forget_withdrawals', 'swap_same_name', 'apply_unauthorized',
                'file_order', 'never_reinstate', 'stale_evidence', 'duplicate_issue', 'missing_field', 'missing_owner_column', 'malformed_csv',
                'missing_minutes', 'missing_actions', 'protected_change', 'missing_gt']
    results = {}
    with tempfile.TemporaryDirectory(prefix='h002-author-') as temporary:
        base = Path(temporary)
        for name in variants:
            root = base / name
            shutil.copytree(exec_root, root)
            shutil.copytree(gt_root, root / 'gt', ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'authoring_validation.json'))
            shutil.copytree(gt_root / 'reference/results', root / 'results')
            actions = root / 'results/actions.csv'
            if name in {'equivalent_csv', 'promote_proposals', 'forget_withdrawals', 'swap_same_name', 'apply_unauthorized',
                        'file_order', 'never_reinstate', 'stale_evidence', 'duplicate_issue', 'missing_field', 'missing_owner_column'}:
                mutate(actions, name)
            elif name == 'malformed_csv':
                header = actions.read_text(encoding='utf-8').splitlines()[0]
                actions.write_text(header + '\n"unterminated', encoding='utf-8')
            elif name == 'missing_minutes':
                (root / 'results/minutes.docx').unlink()
            elif name == 'missing_actions':
                actions.unlink()
            elif name == 'protected_change':
                with (root / 'corrections.jsonl').open('a', encoding='utf-8') as handle:
                    handle.write('\n')
            elif name == 'missing_gt':
                (root / 'gt/expected.json').unlink()
            before = {path.name: sha(path) for path in (root / 'results').iterdir()}
            try:
                evaluated = runpy.run_path(str(root / 'gt/grader.py'))['evaluate'](root)
            except FileNotFoundError:
                assert name == 'missing_gt'
                results[name] = {'status': 'evaluation_error', 'error': 'FileNotFoundError', 'score': None}
                continue
            assert before == {path.name: sha(path) for path in (root / 'results').iterdir()}, 'grader wrote candidate outputs'
            scores = evaluated['scores']
            if name in {'reference', 'equivalent_csv'}:
                assert abs(scores['overall_score'] - 1) < 1e-9, (name, scores)
            else:
                assert scores['overall_score'] < .999, (name, scores)
            if name == 'stale_evidence':
                assert scores['evidence_binding'] == 0
            if name == 'missing_field':
                assert scores['business_correctness'] == scores['boundary_cases'] == scores['evidence_binding'] == 1
                assert scores['delivery_integrity'] < 1
            if name == 'missing_owner_column':
                assert abs(scores['business_correctness'] - .8) < 1e-9
                assert not evaluated['observations']['case_checks']['A16']['owner_id']
            if name == 'protected_change':
                assert scores['boundary_cases'] == scores['delivery_integrity'] == scores['evidence_binding'] == 0
            if name in {'promote_proposals', 'forget_withdrawals', 'swap_same_name', 'apply_unauthorized', 'file_order', 'never_reinstate'}:
                assert scores['business_correctness'] < 1 and scores['boundary_cases'] < 1
            results[name] = scores
        if task_path:
            root = base / 'actual-md'
            shutil.copytree(exec_root, root)
            shutil.copytree(gt_root, root / 'gt', ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'authoring_validation.json'))
            shutil.copytree(gt_root / 'reference/results', root / 'results')
            section = Path(task_path).read_text(encoding='utf-8').split('## Automated Checks', 1)[1].split('## LLM Judge Rubric', 1)[0]
            source = re.search(r'```python\s*\n(.*?)```', section, re.S)[1]
            namespace = {}
            exec(compile(source, 'frozen-h002-task-md', 'exec'), namespace)
            results['actual_md_reference'] = namespace['grade'](workspace_path=str(root))
            assert abs(results['actual_md_reference']['overall_score'] - 1) < 1e-9
    hashes = {path.relative_to(gt_root).as_posix(): sha(path) for path in sorted(gt_root.rglob('*')) if path.is_file()
              and path.name != 'authoring_validation.json' and path.suffix != '.pyc' and '__pycache__' not in path.parts}
    return {'schema_version': 'h002-author-validation/v1', 'status': 'PASS', 'controls': results, 'gt_sha256': hashes,
            'state_fold_audit': folded['audit'], 'limit': 'Author controls and source-bound state calculation, not independent human annotation, semantic Judge or four-Harness calibration.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--exec-root', required=True, type=Path)
    parser.add_argument('--gt-root', required=True, type=Path)
    parser.add_argument('--task-path', type=Path)
    args = parser.parse_args()
    result = validate(args.exec_root, args.gt_root, args.task_path)
    (args.gt_root / 'authoring_validation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': result['status'], 'controls': result['controls']}, ensure_ascii=False))
