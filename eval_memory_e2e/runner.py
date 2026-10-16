"""One controller, durable intent per operation, observation-only recovery.

Drivers exchange JSON over stdin/stdout. Native Drivers must supply raw binding,
response and trace evidence. This protocol deliberately does not reuse General's
single-Prompt journal for multiple sends.
"""

from __future__ import annotations

import subprocess
import os
import sys
from uuid import uuid4
from pathlib import Path

from . import CONTRACT
from .batch import episode, load_batch, operation_id
from .io import (MemoryEvaluationError, append, archive, decode, digest, encoded, events,
                 lock, publish, read_json, require, safe_file, sha, verify_artifact)


def _history(root, episode_id):
    return [event for event in events(root) if event["episode_id"] == episode_id]


def _receipts(root, episode_id):
    results = {}
    for event in _history(root, episode_id):
        if event["kind"] == "RECEIPT":
            record = event["payload"]
            for artifact in record["artifacts"].values():
                verify_artifact(root, artifact)
            for entry in record.get("candidate_snapshot", []):
                verify_artifact(root, entry["artifact"])
            results[record["operation_id"]] = record
    return results


def _initial_config(root, manifest, harness):
    selected = {item["id"] for item in manifest["episodes"] if item["harness"] == harness}
    for event in events(root):
        if event["episode_id"] in selected and event["kind"] == "RECEIPT":
            config = event["payload"].get("actual_config")
            if config:
                return config
    return manifest["profiles"][harness].get("expected_config")


def next_action(root, episode_id):
    manifest = load_batch(root, episode_id=episode_id)
    item = episode(manifest, episode_id)
    history = _history(root, episode_id)
    require(not any(event["kind"] == "EXECUTION_ERROR" for event in history),
            "EXECUTION_FAILED", "Keep this attempt; use a new batch for an authorized replay")
    receipts = _receipts(root, episode_id)
    plan = read_json(Path(root) / item["plan_path"])
    steps = plan["steps"]
    initial_scope = next(iter(item['workspaces']))
    previous_by_scope = {}
    seen_sessions = []
    operation = None
    for step in [{"id": "prepare", "phase": "prepare", "scope": initial_scope, "session": "new", "prompt": None}, *steps]:
        op_id = operation_id(manifest, episode_id, step["id"])
        receipt = receipts.get(op_id)
        if receipt and receipt["status"] == "completed":
            if step["id"] != "prepare":
                previous_by_scope[step["scope"]] = receipt["native"]
                seen_sessions.append(receipt["native"]["session_id"])
            continue
        operation = {"operation_id": op_id, "step": step, "existing_receipt": receipt}
        break
    if operation is None:
        return {"status": "COMPLETED", "episode_id": episode_id}
    intent = next((event for event in history if event["kind"] == "INTENT"
                   and event["payload"]["operation_id"] == operation["operation_id"]), None)
    step = operation["step"]
    request = {"contract": CONTRACT, "mode": manifest["mode"], "batch_id": manifest["batch_id"],
               "experiment_id": manifest["experiment_id"], "execution_attempt_id": "a01",
               "episode_id": episode_id, "harness": item["harness"], "namespace": item["namespace"],
               "profile_id": manifest["profiles"][item["harness"]]["profile_id"],
               "account_policy": "current_signed_in_account", "reset_policy": "synthetic_test_facts_only",
               "baseline": manifest["baseline"], "arm": item["arm"], "scope": step["scope"],
               "memory_channel_policy": manifest["memory_channel_policy"],
               "memory_wait_seconds": manifest["profiles"][item["harness"]].get("memory_wait_seconds", 10),
               "operation_id": operation["operation_id"], "action": "prepare_namespace" if step["id"] == "prepare" else "execute_step",
               "step_id": step["id"], "session_action": step["session"], "prompt": step["prompt"],
               "prompt_sha256": sha(step["prompt"].encode()) if step["prompt"] is not None else None,
               "workspace": item["workspaces"][step["scope"]],
               "previous_native": previous_by_scope.get(step["scope"]),
               "seen_sessions": seen_sessions,
               "expected_config": _initial_config(root, manifest, item["harness"]),
               "required_capabilities": sorted({s["session"] for s in steps})}
    # Public fixture bytes are copied to the candidate only by the explicit
    # controller action below; inspecting `next` never changes candidate state.
    request["materials"] = {path.rsplit("/", 1)[-1]: str(Path(root) / path)
                            for path in manifest["inputs"]
                            if path.startswith(f"public/{episode_id}/materials/")}
    if plan.get('learning'):
        request['learning'] = plan['learning']
        request['step_phase'] = step['phase']
        if step['phase'] in {'seed', 'learn', 'update', 'forget'}:
            request['memory_wait_seconds'] = max(request['memory_wait_seconds'], plan['learning']['formation'].get('minimum_seconds', 0))
    if intent:
        original = intent["payload"]["request"]
        request["expected_config"] = original["expected_config"]
        require(original == request, "REQUEST_DRIFT", operation["operation_id"])
    return {"status": "OBSERVE_ONLY" if intent else "READY", "request": request}


def _validate_reply(request, reply):
    require(isinstance(reply, dict), "DRIVER_REPLY", "Expected a JSON object")
    for field in ("contract", "mode", "experiment_id", "execution_attempt_id", "operation_id", "episode_id", "profile_id", "namespace", "step_id", "prompt_sha256"):
        require(reply.get(field) == request[field], "NATIVE_BINDING_MISMATCH", field)
    require(reply.get("status") in {"completed", "active", "needs_attention", "infrastructure_error", "unsupported_product"},
            "DRIVER_STATUS", "Unknown status")
    require(isinstance(reply.get("binding_evidence"), str), "MISSING_BINDING_EVIDENCE", "Raw binding source is required")
    config = reply.get("actual_config")
    require(isinstance(config, dict) and all(isinstance(config.get(key), str) and config[key].strip()
            for key in ("app_version", "model_display", "permissions", "account_fingerprint")),
            "NATIVE_CONFIG", "Actual client/model/permission and a non-secret logged-in account fingerprint are required")
    if request["expected_config"] is not None:
        require(config == request["expected_config"], "CONFIG_DRIFT", "Actual configuration changed")
    if reply["status"] != "completed":
        require(isinstance(reply.get("reason"), str) and reply["reason"].strip(), "MISSING_REASON", reply["status"])
        return
    if reply.get("background_settled") is not True:
        observation = reply.get("memory_observation", {})
        require(reply.get("background_settled") is None and observation.get("status") == "unobservable"
                and type(observation.get("wait_seconds")) in {int, float}
                and observation["wait_seconds"] >= request["memory_wait_seconds"],
                "BACKGROUND_UNSETTLED", "Known active memory work cannot be finalized; unobservable work needs a frozen observation window")
    if request["action"] == "prepare_namespace":
        admission = reply.get("admission", {})
        require(admission.get("test_scope_only") is True and admission.get("precondition_verified") is True
                and admission.get("account_policy") == "current_signed_in_account",
                "MEMORY_NOT_ADMITTED", "Scoped precondition and cleanup evidence required")
        require(set(request["required_capabilities"]) <= set(admission.get("capabilities", [])),
                "CAPABILITY_MISSING", "Driver cannot perform all steps in the selected chain")
        require(admission.get("isolation") in {"verified_namespace", "shared_account_cold_first"},
                "ISOLATION_UNKNOWN", "A new workspace is not memory isolation")
    else:
        native = reply.get("native", {})
        require(isinstance(native.get("session_id"), str) and native["session_id"]
                and isinstance(native.get("turn_id"), str) and native["turn_id"]
                and native.get("cwd") == request["workspace"], "NATIVE_BINDING_MISMATCH", "session/turn/cwd")
        previous = request["previous_native"]
        if request["session_action"] in {"new", "restart_new"}:
            require(native["session_id"] not in request["seen_sessions"], "SESSION_BOUNDARY", "New session reused an old identity")
        else:
            require(previous is not None, "SESSION_BOUNDARY", "Continuation lacks an original session")
        if previous:
            same = native["session_id"] == previous["session_id"]
            require(same == (request["session_action"] == "continue"), "SESSION_BOUNDARY", request["session_action"])
            require(native["turn_id"] != previous["turn_id"], "TURN_REUSED", native["turn_id"])
        require(isinstance(reply.get("final_response"), str) and isinstance(reply.get("trace"), str),
                "MISSING_TRACE", "Full response and raw trace are required")
        if request["session_action"] == "restart_new":
            require(isinstance(reply.get("restart_evidence"), str), "RESTART_UNVERIFIED", "Process lifecycle evidence required")


def _record(root, request, reply):
    _validate_reply(request, reply)
    manifest = load_batch(root, episode_id=request["episode_id"])
    baseline_config = _initial_config(root, manifest, request["harness"])
    if baseline_config is not None:
        require(reply["actual_config"] == baseline_config, "CONFIG_DRIFT", "Frozen unit configuration changed")
    binding = read_json(safe_file(reply["binding_evidence"]))
    require(isinstance(binding, dict), "BINDING_EVIDENCE_SHAPE", "Expected a JSON object")
    if request["mode"] == "native":
        require(binding.get("fixture_only") is not True, "FIXTURE_NOT_NATIVE", "A fixture cannot become native evidence by changing its label")
        require(binding.get("source_kind") in {"native_memory_binding", "general_e2e_binding"}
                and binding.get("operation_id") == request["operation_id"]
                and binding.get("prompt_sha256") == request["prompt_sha256"]
                and binding.get("actual_config") == reply["actual_config"]
                and binding.get("profile_id") == request["profile_id"]
                and binding.get("namespace") == request["namespace"],
                "BINDING_EVIDENCE_SHAPE", "Native readback must bind this operation and actual Prompt")
        if request["action"] == "execute_step" and reply["status"] == "completed":
            require(binding.get("native") == reply.get("native"), "NATIVE_BINDING_MISMATCH", "Raw and normalized native identity disagree")
    artifacts = {field: archive(root, reply[field])
                 for field in ("binding_evidence", "final_response", "trace", "restart_evidence", "memory_snapshot")
                 if reply.get(field) is not None}
    candidate = []
    if reply["status"] == "completed" and request["action"] == "execute_step":
        workspace = Path(request["workspace"])
        for ancestor in (workspace, *workspace.parents):
            require(not ancestor.is_symlink(), "SYMLINK_REJECTED", str(ancestor))
        files = sorted(workspace.rglob("*"))
        require(len(files) <= 2000, "SNAPSHOT_BUDGET", "Candidate snapshot exceeds 2000 entries")
        size = 0
        for path in files:
            require(not path.is_symlink(), "SYMLINK_REJECTED", str(path))
            if path.is_file():
                size += path.stat().st_size
                require(size <= 100 * 1024 * 1024, "SNAPSHOT_BUDGET", "Candidate snapshot exceeds 100 MiB")
                candidate.append({"workspace_path": str(path.relative_to(workspace)), "artifact": archive(root, path)})
    record = {**reply, "artifacts": artifacts, "candidate_snapshot": candidate, "request_sha256": digest(request)}
    for field in artifacts:
        record.pop(field, None)
    append(root, "RECEIPT", request["episode_id"], record)
    if reply["status"] in {"infrastructure_error", "unsupported_product"}:
        append(root, "EXECUTION_ERROR", request["episode_id"], {"status": reply["status"], "reason": reply["reason"]})
    return record


def _install_materials(request):
    if request["previous_native"] is not None:
        return
    workspace = Path(request["workspace"])
    workspace.mkdir(parents=True, exist_ok=True)
    for ancestor in (workspace, *workspace.parents):
        require(not ancestor.is_symlink(), "SYMLINK_REJECTED", str(ancestor))
    for name, source in request["materials"].items():
        destination = workspace / name
        # Only initialization may install files. Continuing never repairs an
        # agent-modified candidate or changes its previous business state.
        if not destination.exists():
            from .io import publish
            publish(destination, safe_file(source).read_bytes())


def advance(root, episode_id, *, driver_timeout=None, retry_pre_send=False):
    """Perform at most one Driver action; resumption never dispatches again."""
    root = Path(root).absolute()
    with lock(root):
        manifest = load_batch(root, episode_id=episode_id)
        item = episode(manifest, episode_id)
        if driver_timeout is None:
            driver_timeout = manifest["profiles"][item["harness"]].get("driver_timeout_seconds", 60)
        require(type(driver_timeout) in {int, float} and 0 < driver_timeout <= 300,
                "DRIVER_TIMEOUT", "Per-call transport timeout must be 1..300 seconds; it is not a task deadline")
        # One account may have global memory: do not interleave independent
        # chains on the same Harness, or run experienced before its cold arm.
        earlier = [candidate for candidate in manifest["episodes"]
                   if candidate["harness"] == item["harness"]]
        for candidate in earlier:
            if candidate["id"] == episode_id:
                break
            status = next_action(root, candidate["id"])["status"]
            require(status == "COMPLETED", "PREDECESSOR_INCOMPLETE", candidate["id"])
        action = next_action(root, episode_id)
        if action["status"] == "COMPLETED":
            return action
        command = manifest["profiles"][item["harness"]]["driver_command"]
        require(command is not None, "DRIVER_NOT_CONFIGURED", "Native memory Driver must be validated before sending")
        request = action["request"]
        if retry_pre_send:
            require(manifest['mode'] == 'native' and manifest['profiles'][item['harness']].get('pre_send_retry') is True
                    and action['status'] == 'OBSERVE_ONLY', 'PRE_SEND_RETRY_NOT_ADMITTED',
                    'Explicit retry requires a supported native Driver and an existing unresolved operation')
            append(root, 'PRE_SEND_RETRY_INTENT', episode_id, {'operation_id': request['operation_id'],
                   'request_sha256': digest(request), 'request': request, 'retry_id': uuid4().hex, 'unknown_send_replay_allowed': False})
        if action["status"] == "READY":
            if request["action"] == "execute_step":
                _install_materials(request)
            append(root, "INTENT", episode_id, {"operation_id": request["operation_id"], "request": request})
        wire = {**request, "transport_action": "observe" if action["status"] == "OBSERVE_ONLY" else "dispatch"}
        if retry_pre_send:
            wire['transport_action'] = 'retry_pre_send'
        from .observation import capture_state
        capture_state(root, request, 'before' if action['status'] == 'READY' else 'poll')
        try:
            result = subprocess.run(command, input=encoded(wire), stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, timeout=driver_timeout, check=False,
                                    env=dict(os.environ, MEMORY_E2E_PYTHON=sys.executable))
            logs = {}
            for name, data in (("stdout", result.stdout), ("stderr", result.stderr)):
                path = root / ".native-driver-logs" / f"{request['operation_id']}-{uuid4().hex}.{name}"
                publish(path, data)
                logs[name] = archive(root, path)
            append(root, "DRIVER_DIAGNOSTIC", episode_id, {"operation_id": request["operation_id"], "returncode": result.returncode, "artifacts": logs})
            require(result.returncode == 0, "DRIVER_PROCESS_ERROR", f"Driver exit {result.returncode}; stderr sha256={sha(result.stderr)}")
            reply = decode(result.stdout)
            record = _record(root, request, reply)
            if record['status'] == 'completed':
                capture_state(root, request, 'after')
        except subprocess.TimeoutExpired as exc:
            logs = {}
            for name, data in (("stdout", exc.stdout or b""), ("stderr", exc.stderr or b"")):
                path = root / ".native-driver-logs" / f"{request['operation_id']}-{uuid4().hex}.timeout.{name}"
                publish(path, data)
                logs[name] = archive(root, path)
            append(root, "DRIVER_DIAGNOSTIC", episode_id, {"operation_id": request["operation_id"],
                   "returncode": None, "transport_timeout_seconds": driver_timeout, "artifacts": logs})
            append(root, "UNCERTAIN", episode_id, {"operation_id": request["operation_id"], "error_code": "DRIVER_TRANSPORT_TIMEOUT"})
            raise MemoryEvaluationError("DRIVER_TRANSPORT_TIMEOUT", "Driver observation timed out; preserve the same operation and observe only") from exc
        except (OSError, MemoryEvaluationError) as exc:
            append(root, "UNCERTAIN", episode_id, {"operation_id": request["operation_id"],
                                                   "error_code": getattr(exc, "code", type(exc).__name__)})
            raise
        return {"status": record["status"], "episode_id": episode_id,
                "operation_id": request["operation_id"], "next": next_action(root, episode_id)["status"]
                if record["status"] not in {"infrastructure_error", "unsupported_product"} else "FAILED"}


def import_receipt(root, episode_id, receipt_path):
    """Evidence handoff for a separately operated controller; never sends a Prompt."""
    with lock(root):
        action = next_action(root, episode_id)
        require(action["status"] == "OBSERVE_ONLY", "NO_INTENT", "Register a dispatch intent before external operation")
        reply = read_json(receipt_path)
        return _record(root, action["request"], reply)


def register_intent(root, episode_id):
    with lock(root):
        manifest = load_batch(root, episode_id=episode_id)
        item = episode(manifest, episode_id)
        for previous in manifest["episodes"]:
            if previous["id"] == episode_id:
                break
            if previous["harness"] == item["harness"]:
                require(next_action(root, previous["id"])["status"] == "COMPLETED",
                        "PREDECESSOR_INCOMPLETE", previous["id"])
        action = next_action(root, episode_id)
        require(action["status"] == "READY", "ALREADY_ATTEMPTED", "Observe the original operation instead")
        request = action["request"]
        if request["action"] == "execute_step":
            _install_materials(request)
        append(root, "INTENT", episode_id, {"operation_id": request["operation_id"], "request": request})
        return request
