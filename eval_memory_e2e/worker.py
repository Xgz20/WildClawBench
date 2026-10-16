"""Round-robin native progress with a single serialized control/UI call."""
import json
import time

from .batch import load_batch
from .io import MemoryEvaluationError, require, append, lock, events
from .runner import advance, next_action


def accepted_observation_binding(root, action):
    if not action or action.get('status') != 'OBSERVE_ONLY':
        return None
    request = action.get('request', {})
    if request.get('action') != 'execute_step' or not request.get('episode_id'):
        return None
    for event in reversed(events(root)):
        receipt = event['payload']
        if event['kind'] != 'RECEIPT' or event['episode_id'] != request['episode_id'] or receipt.get('operation_id') != request['operation_id']:
            continue
        native = receipt.get('native') or {}
        if native.get('session_id') and native.get('turn_id'):
            return native
    return None


def run_worker(root, harness=None, poll_seconds=2):
    require(0 < poll_seconds <= 30, "POLL_INTERVAL", "Expected 0..30 seconds")
    manifest = load_batch(root, harness=harness)
    targets = [item for item in manifest["episodes"] if harness is None or item["harness"] == harness]
    require(targets, "HARNESS_SCOPE", str(harness))
    groups = {}
    for item in targets:
        groups.setdefault(item['harness'], []).append(item)
    positions = {name: 0 for name in groups}
    blocked, started, previous, completed = {}, set(), {}, 0
    observation_retries = {}
    with lock(root):
        append(root, 'SCHEDULER_START', None, {'policy': 'round_robin_harnesses_single_control_call',
               'harnesses': list(groups), 'poll_seconds': poll_seconds, 'task_deadline': None})
    print(json.dumps({'phase': 'SCHEDULER', 'policy': 'round_robin_harnesses_single_control_call',
                      'harnesses': list(groups), 'task_deadline': None}), flush=True)
    while True:
        pending = [name for name in groups if name not in blocked and positions[name] < len(groups[name])]
        if not pending:
            break
        for name in pending:
            item = groups[name][positions[name]]
            if item['id'] not in started:
                print(json.dumps({"episode": item["id"], "phase": "START"}), flush=True)
                started.add(item['id'])
            action = None
            try:
                action = next_action(root, item["id"])
                if action["status"] == "COMPLETED":
                    print(json.dumps({"episode": item["id"], "phase": "COMPLETED"}), flush=True)
                    positions[name] += 1
                    completed += 1
                    continue
                operation = action["request"]["operation_id"]
                result = advance(root, item["id"])
                observation_retries.pop((name, operation), None)
                key = (operation, result["status"])
                if key != previous.get(name):
                    print(json.dumps(result, ensure_ascii=False), flush=True)
                    previous[name] = key
                if result["status"] in {"needs_attention", "infrastructure_error", "unsupported_product"}:
                    blocked[name] = {'episode': item['id'], 'native_status': result['status']}
            except MemoryEvaluationError as error:
                print(json.dumps({"episode": item["id"], "error": error.code, "detail": str(error)}, ensure_ascii=False), flush=True)
                native = accepted_observation_binding(root, action) if error.code in {'DRIVER_TRANSPORT_TIMEOUT', 'DRIVER_PROCESS_ERROR'} else None
                retry_key = (name, action['request']['operation_id']) if native else None
                if native and observation_retries.get(retry_key, 0) < 3:
                    count = observation_retries.get(retry_key, 0) + 1
                    observation_retries[retry_key] = count
                    retry = {'operation_id': retry_key[1], 'retry': count, 'max_retries': 3,
                             'native': native, 'transport_action': 'observe', 'prompt_resend_authorized': False}
                    with lock(root):
                        append(root, 'OBSERVATION_RETRY', item['id'], retry)
                    print(json.dumps({'phase': 'OBSERVATION_RETRY', **retry}), flush=True)
                    continue
                blocked[name] = {'episode': item['id'], 'error': error.code}
        if any(name not in blocked and positions[name] < len(groups[name]) for name in groups):
            time.sleep(poll_seconds)
    result = {"status": "NEEDS_ATTENTION" if blocked else "EXECUTION_COMPLETED", "episodes": len(targets),
              'completed_episodes': completed, 'blocked_harnesses': blocked, "scoring": "not_started"}
    if harness is not None and harness in blocked:
        result.update(blocked[harness])
    return result
