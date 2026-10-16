"""Round-robin native progress with a single serialized control/UI call."""
import json
import time

from .batch import load_batch
from .io import MemoryEvaluationError, require, append, lock
from .runner import advance, next_action


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
            try:
                action = next_action(root, item["id"])
                if action["status"] == "COMPLETED":
                    print(json.dumps({"episode": item["id"], "phase": "COMPLETED"}), flush=True)
                    positions[name] += 1
                    completed += 1
                    continue
                operation = action["request"]["operation_id"]
                result = advance(root, item["id"])
                key = (operation, result["status"])
                if key != previous.get(name):
                    print(json.dumps(result, ensure_ascii=False), flush=True)
                    previous[name] = key
                if result["status"] in {"needs_attention", "infrastructure_error", "unsupported_product"}:
                    blocked[name] = {'episode': item['id'], 'native_status': result['status']}
            except MemoryEvaluationError as error:
                print(json.dumps({"episode": item["id"], "error": error.code, "detail": str(error)}, ensure_ascii=False), flush=True)
                blocked[name] = {'episode': item['id'], 'error': error.code}
        if any(name not in blocked and positions[name] < len(groups[name]) for name in groups):
            time.sleep(poll_seconds)
    result = {"status": "NEEDS_ATTENTION" if blocked else "EXECUTION_COMPLETED", "episodes": len(targets),
              'completed_episodes': completed, 'blocked_harnesses': blocked, "scoring": "not_started"}
    if harness is not None and harness in blocked:
        result.update(blocked[harness])
    return result
