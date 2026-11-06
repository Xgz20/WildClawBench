#!/usr/bin/env python3
"""Build a self-contained full-70 admin distribution and validate four harnesses."""
from pathlib import Path
from io import BytesIO
import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(Path(__file__).resolve().parent)]
import build_general70_v4 as SNAPSHOT
import build_general_release as RELEASE
from eval_general_e2e.datasets.bundle import GENERAL70_V4_DEFINITION, build_default_bundle

RELEASE_ID = 'general70-v4-20261105'
INFO004 = SNAPSHOT.INFO004
PDF_SHA = 'd42a5b5dd458469b160f57da3abfde3e27e194a2b107a1c2227b858cface0455'


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(part)
    return h.hexdigest()


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + '\n', encoding='utf-8')


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


def extract_skill(suite, name, destination):
    with zipfile.ZipFile(suite) as archive:
        choices = [p for p in archive.namelist() if Path(p).name.startswith(name + '-skill-v') and p.endswith('.zip')]
        assert len(choices) == 1
        with zipfile.ZipFile(BytesIO(archive.read(choices[0]))) as skill:
            for path in skill.namelist():
                assert not Path(path).is_absolute() and '..' not in Path(path).parts
            skill.extractall(destination)
    return destination / name


def verify_harness_packages(dataset, suite, temporary):
    installed = temporary / 'installed'
    prepare_root = extract_skill(suite, 'prepare-general-e2e-workspaces', installed)
    prepare = module('general70_v4_standalone_prepare', prepare_root / 'scripts/prepare_general_e2e_workspaces.py')
    assert Path(prepare._load_dataset_module().__file__).is_relative_to(installed)
    config = json.loads((ROOT / 'tools/e2e-build/examples/general70-v4-four-harness.prepare.json').read_text())
    config['batch_id'] = 'general70-v4-packaging-verification-only'
    for unit in config['units']:
        unit['model']['requested_id'] = 'verification-only-not-executed'
    config_path = temporary / 'prepare-config.json'
    save(config_path, config)
    batch = Path(prepare.prepare_batch(dataset, suite, config_path, temporary / 'prepared')['batch_root'])
    prepare.verify_batch(batch)
    rows = []
    for package in sorted(batch.rglob('*__scoring.zip')):
        with zipfile.ZipFile(package) as archive:
            manifest_name = next(p for p in archive.namelist() if p.endswith('/.general-e2e/scoring-package-manifest.json'))
            manifest = json.loads(archive.read(manifest_name))
            assert len(manifest['task_ids']) == 70
            pdf = next(p for p in archive.namelist() if p.endswith(f'/{INFO004}/private-scoring/gt/source_evidence/Y1-yang-lianfen.pdf'))
            text = next(p for p in archive.namelist() if p.endswith(f'/{INFO004}/private-scoring/gt/source_evidence/Y1-yang-lianfen.pages.txt'))
            assert hashlib.sha256(archive.read(pdf)).hexdigest() == PDF_SHA
            body = archive.read(text).decode()
            assert body.count('===== PDF PAGE') == 10 and '杨乾坤' not in body.split('===== PDF PAGE 10')[1]
            rows.append({'unit_id': manifest['unit_id'], 'task_count': 70,
                         'reference_pdf_sha256': PDF_SHA, 'paged_text_chars': len(body)})
    executions = list(batch.rglob('*__execution.zip'))
    assert len(rows) == len(executions) == 4
    for package in executions:
        with zipfile.ZipFile(package) as archive:
            assert not any('/gt/' in p or '/private-scoring/' in p or 'Y1-yang-lianfen' in p for p in archive.namelist())

    score_root = extract_skill(suite, 'score-general-e2e', installed)
    rt = module('general70_v4_standalone_score', score_root / 'scripts/score_general_e2e.py')
    execution = next(p for p in executions if '__astronstudio-macos__' in p.name)
    scoring = next(batch.rglob('*__astronstudio-macos__scoring.zip'))
    # Controlled synthetic completion: exercise packaging/reading, never a real score.
    with zipfile.ZipFile(execution) as archive:
        for name in archive.namelist():
            if name.endswith('/manifest.json') and name.count('/') == 1 or f'/execution/tasks/{INFO004}/' in name:
                archive.extract(name, temporary / 'unit')
    unit = next((temporary / 'unit').iterdir())
    manifest = json.loads((unit / 'manifest.json').read_text())
    identity = {'batch_id': manifest['batch_id'], 'unit_id': manifest['unit_id'],
                'task_id': INFO004, 'attempt_id': 'synthetic-reference-verification-only'}
    candidate = unit / 'evidence/candidate/workspace'
    shutil.copytree(unit / 'execution/tasks' / INFO004 / 'workspace', candidate)
    entries, candidate_sha = rt._inventory_tree(candidate)
    save(candidate.parent / 'candidate-artifact.json', {'schema_version': rt.CANDIDATE_SCHEMA,
        'identity': identity, 'hash_algorithm': rt.TREE_HASH_ALGORITHM, 'expected_sha256': candidate_sha, 'entries': entries})
    answer = '合成证据分发验证，非真实模型执行或正式评分。https://example.org/reference'
    trace = [{'event_id': 'verification-0001', 'role': 'assistant', 'channel': 'final', 'content': answer},
             {'event_id': 'verification-0002', 'type': 'task_complete', 'last_agent_message': answer}]
    (unit / 'evidence/transcript.jsonl').write_text('\n'.join(json.dumps(v, ensure_ascii=False) for v in trace) + '\n')
    task = next(t for t in manifest['tasks'] if t['task_id'] == INFO004)
    record = unit / 'evidence/execution-record.json'
    save(record, {'identity': identity, 'dataset': manifest['dataset'], 'phase': 'COMPLETED',
                  'execution': {'business_status': 'completed'}, 'evidence': {'completeness': 'complete',
                  'transcript_path': 'evidence/transcript.jsonl'}, 'candidate': {'path': 'evidence/candidate/workspace',
                  'frozen_sha256': candidate_sha, 'drift_status': 'stable'}, 'prompt': {'sha256': task['prompt']['sent_sha256']}})
    attempt = Path(rt.prepare_attempt(unit_root=unit, execution_record_path=record, scoring_package=scoring,
        task_id=INFO004, scoring_attempt_id='synthetic-reference-reader-only', output_root=temporary / 'attempts',
        runtime_lock_path=score_root / 'references/scoring-runtime-lock.json', judge_protocol='codex-agent-judge-v1',
        judge_model='gpt-6.1-sol', judge_reasoning_effort='high', judge_attempt_id='synthetic-reference-reader-only')['attempt_root'])
    rt.run_rules_attempt(attempt_root=attempt, runtime_python=Path(sys.executable), timeout_seconds=30)
    rt.prepare_semantics_attempt(attempt_root=attempt)
    sources = rt.query_evidence_attempt(attempt_root=attempt, mode='catalog', path_contains='Y1-yang-lianfen.pages.txt')['items']
    source = next(row for row in sources if row['reference']['path'].startswith('grader-evidence/'))
    result = rt.query_evidence_attempt(attempt_root=attempt, mode='file', evidence_id=source['id'], limit=1000, max_chars=18000)
    assert not result['has_more'] and result['returned_count'] == result['total_matches']
    assert 'PDF PAGE 10' in '\n'.join(row['text'] for row in result['items'])
    assert not any(row.get('text_truncated') for row in result['items'])
    assert not (attempt / 'score.json').exists()
    return {'status': 'PASS', 'synthetic_verification_only': True, 'real_harness_or_judge_started': False,
            'units': rows, 'private_reference_absent_from_execution_packages': 4,
            'native_reader_full_text_lines': result['returned_count'], 'score_created': False}


def build(output):
    output = output.resolve()
    archive_path = output.with_suffix('.full.zip')
    if output.exists() or archive_path.exists():
        raise ValueError('OUTPUT_EXISTS')
    files, _ = SNAPSHOT.outputs()
    for path, data in files.items():
        if path.read_bytes() != data:
            raise ValueError('REVIEWED_RELEASE_SOURCE_DRIFT:' + str(path))
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    subprocess.run(['git', 'diff', '--exit-code', revision, '--', 'tools/report', 'src',
                    'eval_general_e2e', 'tools/e2e-build',
                    'docs/general-e2e/general70-v4-reference-release-20261105.md'],
                   cwd=ROOT, check=True, capture_output=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='general70-v4-', dir=output.parent) as temp:
        temporary = Path(temp)
        stage = temporary / output.name
        stage.mkdir()
        skill_result = RELEASE.build_general_release(ROOT, stage / 'skill-suite', release_id=RELEASE_ID, source_revision=revision)
        dataset = stage / 'dataset/general-custom70-v4.dataset.zip'
        dataset.parent.mkdir()
        dataset_result = build_default_bundle(ROOT, dataset, definition=GENERAL70_V4_DEFINITION)
        suite = Path(skill_result['suite_path'])
        verification = verify_harness_packages(dataset, suite, temporary / 'verification-work')
        save(stage / 'verification/four-harness-and-reader.json', verification)
        shutil.copyfile(ROOT / 'tools/e2e-build/examples/general70-v4-four-harness.prepare.json', stage / 'prepare-four-harness.example.json')
        shutil.copyfile(ROOT / 'docs/general-e2e/general70-v4-reference-release-20261105.md', stage / 'README.md')
        shutil.copyfile(ROOT / 'eval_general_e2e/datasets/audits/general-custom70-v4-reference-release.json', stage / 'verification/unchanged-69.json')
        records = [{'path': p.relative_to(stage).as_posix(), 'size': p.stat().st_size, 'sha256': digest(p)}
                   for p in sorted(stage.rglob('*')) if p.is_file()]
        document = {'schema_version': 'general70-complete-admin-distribution/v1', 'release_id': RELEASE_ID,
                    'framework_revision': revision, 'dataset_id': GENERAL70_V4_DEFINITION.dataset_id,
                    'dataset_digest': dataset_result['dataset_digest'], 'task_count': 70,
                    'changed_task_ids': [INFO004], 'other_69_unchanged': True,
                    'suite': suite.relative_to(stage).as_posix(), 'files': records}
        save(stage / 'distribution-manifest.json', document)
        all_files = sorted(p for p in stage.rglob('*') if p.is_file())
        (stage / 'SHA256SUMS').write_text(''.join(f'{digest(p)}  {p.relative_to(stage).as_posix()}\n' for p in all_files))
        for row in records:
            assert digest(stage / row['path']) == row['sha256']
        stage.rename(output)
    with zipfile.ZipFile(archive_path, 'x', compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
        for path in sorted(output.rglob('*')):
            if path.is_file(): archive.write(path, f'{output.name}/{path.relative_to(output).as_posix()}')
    checksum = archive_path.with_name(archive_path.name + '.sha256')
    checksum.write_text(digest(archive_path) + '  ' + archive_path.name + '\n')
    return {'status': 'PASS', 'release_root': str(output), 'archive': str(archive_path),
            'archive_sha256': digest(archive_path), 'task_count': 70, 'unchanged_tasks': 69,
            'four_harness_verification': verification}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.output_dir), ensure_ascii=False, indent=2))
