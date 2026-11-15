"""Durable Docker-backed CLI judges over sealed General E2E executions."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib.parse import urlsplit

from .artifacts import inventory, remove_temporary_tree, _protect_office_inode, OFFICE_SUFFIXES
from .common import E2EError, atomic_json, digest, file_sha256, identifier, inside, read_json
from .engine import load_batch, verify_ready
from .handoff import export_scoring_context
from .store import BatchStore, controller_lock, refresh_controller_heartbeat

SCHEMA = 'wildclawbench.headless-score-job/v1'
LABEL = 'org.astron.eval.score-job'
SUPPORTED_HARNESSES = {'codex', 'deepseek-harness'}
CONFIG_KEYS = {'harness', 'model', 'base_url', 'reasoning_effort', 'image', 'image_id',
               'docker_context', 'concurrency', 'timeout_seconds', 'rule_timeout_seconds', 'memory', 'cpus', 'api_format', 'dns_overrides',
               'score_skill_dir', 'score_skill_inventory_sha256'}


def normalize_config(value: dict) -> dict:
    if set(value) - CONFIG_KEYS:
        raise E2EError('HEADLESS_CONFIG_UNKNOWN_FIELDS')
    result = {'dns_overrides': {}, 'reasoning_effort': 'high' if value.get('harness') == 'codex' else 'none', 'docker_context': 'default', 'concurrency': 3,
              'api_format': 'openai_response' if value.get('harness') == 'codex' else 'openai_chat',
              'timeout_seconds': 3600, 'rule_timeout_seconds': 600, 'memory': '4g', 'cpus': '2', **value}
    if result.get('harness') not in SUPPORTED_HARNESSES:
        raise E2EError('HEADLESS_HARNESS_UNSUPPORTED')
    if result['api_format'] not in ({'openai_response'} if result['harness'] == 'codex' else {'openai_chat', 'openai_response'}):
        raise E2EError('HEADLESS_API_FORMAT_UNSUPPORTED')
    for field in ['model', 'base_url', 'image']:
        if not isinstance(result.get(field), str) or not result[field].strip():
            raise E2EError('HEADLESS_CONFIG_REQUIRED_' + field)
    endpoint = urlsplit(result['base_url'])
    if endpoint.scheme not in {'http', 'https'} or not endpoint.netloc or endpoint.username or endpoint.password:
        raise E2EError('HEADLESS_ENDPOINT_INVALID')
    if not isinstance(result['dns_overrides'], dict):
        raise E2EError('HEADLESS_DNS_OVERRIDES_INVALID')
    for host, address in result['dns_overrides'].items():
        if host != endpoint.hostname:
            raise E2EError('HEADLESS_DNS_OVERRIDE_HOST_INVALID')
        try:
            ipaddress.IPv4Address(address)
        except (ValueError, TypeError):
            raise E2EError('HEADLESS_DNS_OVERRIDE_ADDRESS_INVALID')
    if type(result['concurrency']) is not int or not 1 <= result['concurrency'] <= 8:
        raise E2EError('HEADLESS_CONCURRENCY_INVALID')
    for field in ['timeout_seconds', 'rule_timeout_seconds']:
        if type(result[field]) is not int or not 1 <= result[field] <= 14400:
            raise E2EError('HEADLESS_TIMEOUT_INVALID')
    if result['reasoning_effort'] not in {'none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max', 'ultra'}:
        raise E2EError('HEADLESS_REASONING_INVALID')
    if result.get('score_skill_dir'):
        root = Path(result['score_skill_dir']).expanduser().resolve(strict=True)
        metadata = read_json(root / 'skill-metadata.json')
        if metadata.get('name') != 'score-general-e2e' or metadata.get('contract_version') != 'general-e2e-contract-v1':
            raise E2EError('HEADLESS_SCORE_SKILL_INCOMPATIBLE')
        expected = digest(inventory(root))
        if result.get('score_skill_inventory_sha256', expected) != expected:
            raise E2EError('HEADLESS_SCORE_SKILL_DRIFT')
        result.update(score_skill_dir=str(root), score_skill_inventory_sha256=expected)
    elif result.get('score_skill_inventory_sha256'):
        raise E2EError('HEADLESS_SCORE_SKILL_DIRECTORY_REQUIRED')
    return result


def docker(config, *arguments, timeout=60, check=True):
    command = ['docker', '--context', config['docker_context'], *map(str, arguments)]
    result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', timeout=timeout)
    if check and result.returncode:
        raise E2EError('SCORING_DOCKER_ERROR: ' + result.stderr[-1500:])
    return result


def inspect_container(config, name):
    result = docker(config, 'container', 'inspect', name, check=False)
    if result.returncode:
        # Only a confirmed missing name permits creation; daemon errors remain unknown.
        if 'No such container' in result.stderr or 'No such object' in result.stderr:
            return None
        raise E2EError('SCORING_CONTAINER_OBSERVATION_UNKNOWN')
    rows = json.loads(result.stdout)
    if len(rows) != 1:
        raise E2EError('SCORING_CONTAINER_IDENTITY_AMBIGUOUS')
    return rows[0]


def owned(config, name, job_id):
    info = inspect_container(config, name)
    if info and info.get('Config', {}).get('Labels', {}).get(LABEL) != job_id:
        raise E2EError('SCORING_CONTAINER_NOT_OWNED')
    return info


def _check_files(root, entries):
    for name, expected in entries.items():
        path = inside(root, name)
        if not path.is_file() or path.is_symlink() or file_sha256(path) != expected:
            raise E2EError('SCORING_IMMUTABLE_INPUT_DRIFT: ' + name)


def _admit_immutable_inputs(root, entries):
    """Bind-mounted Linux inputs also need the macOS host's inode protection."""
    _check_files(root, entries)
    protected = []
    if sys.platform == 'darwin':
        for name in entries:
            path = inside(root, name)
            if path.suffix.lower() in OFFICE_SUFFIXES:
                if path.stat().st_mode & 0o222:
                    raise E2EError('SCORING_OFFICE_INPUT_PERMISSIONS_CHANGED: ' + name)
                _protect_office_inode(path)
                if path.stat().st_mode & 0o222:
                    raise E2EError('SCORING_OFFICE_INPUT_PERMISSIONS_CHANGED: ' + name)
                protected.append(name)
    _check_files(root, entries)
    return {'schema': 'wildclawbench.headless-host-input-protection/v1',
            'host_platform': sys.platform, 'files': protected, 'original_bytes_unchanged': True}


def _private_environment(path: Path, key: str):
    if not key or '\n' in key or '\r' in key:
        raise E2EError('SCORING_CREDENTIAL_REQUIRED')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as output:
        output.write('E2E_SCORER_API_KEY=' + key + '\n')


def _result_row(item, state, work: Path):
    common = {'execution_key': item['key'], 'task_id': item['task_id'], 'unit_id': item['unit_id'],
              'run_index': item['run_index'], 'execution_attempt_id': item['attempt_id'],
              'work_root': str(work), 'container_released': state.get('container_released', False),
              'scoring_runtime': {key: state.get(key) for key in ['container_id', 'container_started_at', 'container_finished_at']}}
    if (work / 'result.json').is_file() and state.get('verified'):
        result = read_json(work / 'result.json')
        score_file = inside(work, result['score_path'])
        if file_sha256(score_file) != state['score_sha256'] or result['score_sha256'] != state['score_sha256']:
            raise E2EError('SCORING_RESULT_DRIFT')
        score = read_json(score_file)
        return {**common, 'status': 'valid' if score['result']['valid'] else 'evaluation_error',
                'score_path': str(inside(work, result['score_path'])), 'score_sha256': result['score_sha256'],
                'attempt_root': str(inside(work, result['attempt_root'])), 'scoring_attempt_id': score['identity']['attempt_id'],
                'total_score': score['result']['total_score'], 'judge': score.get('judge'),
                'agent_used': result['agent_used'], 'agent_identity': result.get('agent_identity'), 'verification': state['verification'], 'artifacts': state.get('artifacts', {})}
    error = state.get('error')
    status = 'evaluation_error' if error and error != 'SCORING_CANCELLED' else 'unscored'
    return {**common, 'status': status, 'total_score': None, 'error': error or 'SCORING_NOT_FINISHED',
            'agent_used': (work / 'agent-process.json').is_file(), 'artifacts': state.get('artifacts', {})}



def _finish_verification(config, state, work, worker, name, job_id, api_key):
    if file_sha256(work / 'result.json') != state['worker_result_sha256']:
        raise E2EError('SCORING_RESULT_DRIFT')
    previous = owned(config, name + '-verify', job_id)
    if previous:
        if previous['State']['Status'] == 'running':
            docker(config, 'stop', '--time', '15', previous['Id'])
        docker(config, 'rm', previous['Id'])
    _check_files(work, state['immutable'])
    # Independent keyless replay after the model container has exited.
    replay = docker(config, 'run', '--rm', '--name', name + '-verify', '--label', LABEL + '=' + job_id, '--network=none', '--cap-drop=ALL',
                    '--mount', 'type=bind,src=' + str(work) + ',dst=/job',
                    '--mount', 'type=bind,src=' + str(worker) + ',dst=/worker.py,readonly',
                    state['image_id'], 'python', '/worker.py', '--verify-only', timeout=180)
    verification = json.loads(replay.stdout)
    if verification.get('status') != 'PASS':
        raise E2EError('SCORING_VERIFICATION_NOT_PASS')
    final_result = read_json(work / 'result.json')
    final_score = inside(work, final_result['score_path'])
    if file_sha256(final_score) != final_result['score_sha256']:
        raise E2EError('SCORING_RESULT_DRIFT')
    artifacts = {}
    for kind, path in [('score', final_score), ('audit', final_score.parent / 'score-audit.json'), ('log', work / 'judge.log'), ('trace', work / 'judge-native.jsonl')]:
        if path.is_file():
            if api_key.encode() in path.read_bytes():
                raise E2EError('SCORING_CREDENTIAL_IN_OUTPUT')
            artifacts[kind] = {'path': str(path.relative_to(work)), 'sha256': file_sha256(path)}
    state['artifacts'] = artifacts
    state.update(verified=True, verification=verification, phase='completed', score_sha256=file_sha256(final_score))

def score_one(batch: Path, item: dict, manifest: dict, config: dict, root: Path, job_id: str, api_key: str) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    control, work = root / 'control', root / 'work'
    control.mkdir(mode=0o700, exist_ok=True)
    work.mkdir(mode=0o700, exist_ok=True)
    state_file = control / 'state.json'
    state = read_json(state_file) if state_file.exists() else {}
    worker = Path(__file__).with_name('headless_worker.py')
    request_hash = digest({'batch_manifest': digest(manifest), 'execution_key': item['key'], 'attempt': item['attempt_id'],
                           'profile': config, 'worker_sha256': file_sha256(worker)})
    if state and state['request_sha256'] != request_hash:
        raise E2EError('SCORING_FROZEN_REQUEST_DRIFT')
    name = 'astudio-score-' + job_id[-32:]
    if not state:
        state = {'schema': SCHEMA, 'job_id': job_id, 'container_name': name,
                 'request_sha256': request_hash, 'phase': 'preparing', 'container_released': False}
        atomic_json(state_file, state)
    if state.get('phase') == 'completed' and state.get('container_released'):
        verify_ready(batch, item, manifest)
        if digest(inventory(work / 'context')) != state['source_context_sha256'] or digest(inventory(work / 'skills')) != state['skills_sha256']:
            raise E2EError('SCORING_SOURCE_CONTEXT_DRIFT')
        _check_files(work, state['immutable'])
        result = _result_row(item, state, work)
        if result.get('score_path') and file_sha256(Path(result['score_path'])) != result['score_sha256']:
            raise E2EError('SCORING_RESULT_DRIFT')
        return result
    try:
        task = next(row for row in manifest['tasks'] if row['task_id'] == item['task_id'])
        if task['scene'] != 'general':
            raise E2EError('HEADLESS_GENERAL_ONLY')
        verify_ready(batch, item, manifest)
        if not (work / 'context/handoff.json').exists():
            repo = Path(__file__).resolve().parents[2]
            registered = [row.get('context', {}).get('supplemental_verifier')
                          for row in BatchStore(batch).scoring_rows() if row['key'] == item['key']]
            verifier = None if any(registered) else repo / 'tools/report/skills/general-e2e/collect-general-e2e'
            context = export_scoring_context(batch, item['key'], work / 'context',
                       verification_skill=verifier)
            shutil.copytree(context['installed_skills'], work / 'skills', ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.DS_Store'))
            if config.get('score_skill_dir'):
                source = Path(config['score_skill_dir'])
                if digest(inventory(source)) != config['score_skill_inventory_sha256']:
                    raise E2EError('HEADLESS_SCORE_SKILL_DRIFT')
                target = work / 'skills/score-general-e2e'
                # Only this job's unused clone changes; batch Skills and prior attempts stay frozen.
                remove_temporary_tree(target)
                shutil.copytree(source, target, copy_function=shutil.copyfile,
                                ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.DS_Store'))
            request = {**config, 'task_id': item['task_id'], 'scene': 'general',
                       'scoring_attempt_id': 'headless-' + job_id[-32:]}
            atomic_json(work / 'request.json', request, create=True)
            state['source_context_sha256'] = digest(inventory(work / 'context'))
            state['skills_sha256'] = digest(inventory(work / 'skills'))
            atomic_json(state_file, state)
        if digest(inventory(work / 'context')) != state['source_context_sha256'] or digest(inventory(work / 'skills')) != state['skills_sha256']:
            raise E2EError('SCORING_SOURCE_CONTEXT_DRIFT')
        if not state.get('worker_completed'):
            info = owned(config, name, job_id)
            if info is None:
                if state.get('creation_intent'):
                    raise E2EError('SCORING_CONTAINER_DISAPPEARED_AFTER_CREATION_INTENT')
                image = json.loads(docker(config, 'image', 'inspect', config['image']).stdout)[0]
                if config.get('image_id') and image['Id'] != config['image_id']:
                    raise E2EError('SCORER_IMAGE_DRIFT')
                state.update(creation_intent=True, image_id=image['Id'], phase='creating')
                atomic_json(state_file, state)
                credential = control / 'scorer.env'
                _private_environment(credential, api_key)
                try:
                    dns_arguments = [argument for host, address in config['dns_overrides'].items() for argument in ['--add-host', host + ':' + address]]
                    docker(config, 'create', *dns_arguments, '--name', name, '--label', LABEL + '=' + job_id,
                           '--cap-drop=ALL', '--security-opt=no-new-privileges', '--pids-limit=256',
                           '--memory', config['memory'], '--cpus', config['cpus'], '--shm-size=1g',
                           '--env-file', credential, '--mount', 'type=bind,src=' + str(work) + ',dst=/job',
                           '--mount', 'type=bind,src=' + str(work / 'context') + ',dst=/job/context,readonly',
                           '--mount', 'type=bind,src=' + str(work / 'skills') + ',dst=/job/skills,readonly',
                           '--mount', 'type=bind,src=' + str(worker) + ',dst=/worker.py,readonly',
                           image['Id'], 'python', '/worker.py')
                finally:
                    credential.unlink(missing_ok=True)
                info = owned(config, name, job_id)
            if info['State']['Status'] == 'created':
                docker(config, 'start', name)
            info = owned(config, name, job_id)
            state.update(container_id=info['Id'], container_started_at=info['State'].get('StartedAt'))
            atomic_json(state_file, state)
            deadline = time.monotonic() + config['timeout_seconds'] + config['rule_timeout_seconds'] + 900
            while True:
                info = owned(config, name, job_id)
                if not info:
                    raise E2EError('SCORING_CONTAINER_LOST')
                if (root.parent.parent / 'cancel.json').exists():
                    docker(config, 'stop', '--time', '15', info['Id'])
                    raise E2EError('SCORING_CANCELLED')
                if (work / 'preparation.json').is_file() and not state.get('immutable'):
                    prepared = read_json(work / 'preparation.json')
                    protection = _admit_immutable_inputs(work, prepared['immutable'])
                    state.update(immutable=prepared['immutable'], phase='judging',
                                 grading_type=prepared['grading_type'], judge_required=prepared['judge_required'],
                                 host_input_protection=protection)
                    atomic_json(state_file, state)
                    atomic_json(work / 'continue.json', {'request_sha256': request_hash})
                if info['State']['Status'] == 'exited':
                    if info['State']['ExitCode'] != 0 or not (work / 'result.json').is_file():
                        error = read_json(work / 'error.json').get('error') if (work / 'error.json').is_file() else 'SCORING_WORKER_EXIT_' + str(info['State']['ExitCode'])
                        raise E2EError(error)
                    break
                if time.monotonic() > deadline:
                    docker(config, 'stop', '--time', '15', info['Id'])
                    raise E2EError('SCORING_CONTROLLER_TIMEOUT')
                time.sleep(1)
            state['container_finished_at'] = info['State'].get('FinishedAt')
            state.update(worker_completed=True, worker_result_sha256=file_sha256(work / 'result.json'))
            atomic_json(state_file, state)
        _finish_verification(config, state, work, worker, name, job_id, api_key)
    except Exception as error:
        state.update(phase='failed', error=str(error).replace(api_key, '[REDACTED]') if api_key else str(error))
    finally:
        # Shared CLI images are allowed; cleanup is always by this job's exact container ID/label.
        try:
            for container_name in [name, name + '-verify']:
                info = owned(config, container_name, job_id)
                if info:
                    if info['State']['Status'] in {'running', 'paused', 'restarting'}:
                        docker(config, 'stop', '--time', '15', info['Id'])
                    docker(config, 'rm', info['Id'])
            state['container_released'] = True
        except Exception as error:
            state.update(container_released=False, cleanup_error=str(error).replace(api_key, '[REDACTED]') if api_key else str(error))
        if not state.get('verified') and (work / 'judge.log').is_file():
            log = work / 'judge.log'
            if not api_key or api_key.encode() not in log.read_bytes():
                state.setdefault('artifacts', {})['log'] = {'path': 'judge.log', 'sha256': file_sha256(log)}
        atomic_json(state_file, state)
    return _result_row(item, state, work)


def run_headless_score(batch: Path, output: Path, config_value: dict, *, keys: list[str] | None = None) -> dict:
    config = normalize_config(config_value)
    key = os.environ.get('E2E_SCORER_API_KEY', '')
    if not key:
        raise E2EError('SCORING_CREDENTIAL_REQUIRED')
    manifest = load_batch(batch)
    rows = BatchStore(batch).rows()
    if keys and set(keys) - {item['key'] for item in rows}:
        raise E2EError('SCORING_EXECUTION_SELECTION_INVALID')
    selected = [item for item in rows if not keys or item['key'] in keys]
    if not selected:
        raise E2EError('SCORING_EXECUTION_SELECTION_EMPTY')
    output.mkdir(parents=True, exist_ok=True)
    request = {'schema': SCHEMA, 'batch_id': batch.name, 'batch_manifest_sha256': digest(manifest),
               'config': config, 'execution_keys': [item['key'] for item in selected]}
    request_path = output / 'request.json'
    with controller_lock(output) as owner:
        if request_path.exists() and read_json(request_path) != request:
            raise E2EError('SCORING_JOB_REQUEST_DRIFT')
        if not request_path.exists():
            atomic_json(request_path, request, create=True)
        prefix = 's' + digest(str(output))[:16]
        def work(item):
            job_id = prefix + '-' + digest(item['key'])[:16]
            existing_state = output / 'jobs' / job_id / 'control/state.json'
            completed = existing_state.is_file() and read_json(existing_state).get('phase') == 'completed'
            if (output / 'cancel.json').exists() and not completed:
                return {'execution_key': item['key'], 'task_id': item['task_id'], 'unit_id': item['unit_id'],
                        'run_index': item['run_index'], 'execution_attempt_id': item['attempt_id'],
                        'work_root': str(output / 'jobs' / job_id / 'work'), 'container_released': True,
                        'status': 'unscored', 'total_score': None, 'error': 'SCORING_CANCELLED'}
            return score_one(batch, item, manifest, config, output / 'jobs' / job_id, job_id, key)
        with ThreadPoolExecutor(max_workers=config['concurrency']) as pool:
            futures = [pool.submit(work, item) for item in selected]
            pending = set(futures)
            while pending:
                _, pending = wait(pending, timeout=10, return_when=FIRST_COMPLETED)
                refresh_controller_heartbeat(output, owner)
            outcomes = [future.result() for future in futures]
        result = {**request, 'schema': 'wildclawbench.headless-score-set/v1', 'output_root': str(output),
                  'source_batch_root': str(batch), 'executions': outcomes,
                  'summary': {'total': len(outcomes), 'valid': sum(row['status'] == 'valid' for row in outcomes),
                              'evaluation_error': sum(row['status'] == 'evaluation_error' for row in outcomes),
                              'unscored': sum(row['status'] == 'unscored' for row in outcomes),
                              'containers_held': sum(not row['container_released'] for row in outcomes)},
                  'status': 'NEEDS_ATTENTION' if any(not row['container_released'] for row in outcomes) else 'COMPLETED'}
        atomic_json(output / 'result.json', result)
        return result
