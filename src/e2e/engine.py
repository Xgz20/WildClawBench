"""Bounded multi-unit execution with durable remote job identities."""
from __future__ import annotations

from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
import threading
import time

from .agentcube import AgentCubeClient, AgentCubeConfig, PlatformError
from .artifacts import execution_source, seal_execution, verify_backup, verify_execution
from .backend import DRIVERS, ObservationPaused
from .common import E2EError, atomic_json, digest, file_sha256, inside, read_json, redact, utc_now
from .store import BatchStore, controller_lock, refresh_controller_heartbeat
from .trace import resource_metrics, write_trace


READY_SCHEMA = "wildclawbench.task-execution-handoff/v1"
HEARTBEAT_INTERVAL_SECONDS = 5


def load_batch(root: Path) -> dict:
    manifest = read_json(root / "batch.json")
    if manifest.get("schema") != "wildclawbench.sandbox-batch/v1" or manifest["plan"]["batch_id"] != root.name:
        raise E2EError("BATCH_IDENTITY_INVALID")
    with BatchStore(root).transaction() as db:
        row = db.execute("SELECT value FROM metadata WHERE key='plan_sha256'").fetchone()
    if row is None or row[0] != digest(manifest):
        raise E2EError("BATCH_MANIFEST_DRIFT")
    return manifest


def _artifact(path: Path, root: Path) -> dict:
    return {"path": path.relative_to(root).as_posix(), "size": path.stat().st_size, "sha256": file_sha256(path)}


def _publish(root: Path, store: BatchStore, item: dict, manifest: dict, unit: dict, task: dict, outcome: dict) -> dict:
    execution = inside(root, item["execution_root"])
    staging = execution / "staging"
    binding = outcome["binding"]
    proof = {"schema": "wildclawbench.agentcube-execution-proof/v1", "identity": outcome["identity"],
             "parent_batch_sha256": digest(manifest), "run_index": item["run_index"],
             "session_id": store.get(item["key"]).get("session_id"), "unit": unit,
             "native_binding": {key: value for key, value in binding.items() if key != "events"},
             "report": outcome["report"], "process_cleanup": outcome["cleanup"],
             "public_input_sha256": digest(task["public_inventory"]), "prompt_sha256": task["prompt_sha256"]}
    proof_path = staging / "trace/bindings/execution-proof.json"
    if outcome.get("recovery"):
        proof["native_terminal_recovery"] = outcome["recovery"]
    atomic_json(proof_path, proof)
    index = write_trace(staging / "trace", staging / outcome["native_path"], binding,
                        binding_artifacts=[_artifact(proof_path, staging / "trace")])
    (staging / "final-response.md").write_text(binding["final_response"], encoding="utf-8")
    sources = [_artifact(staging / "metadata/report.json", staging), _artifact(staging / "trace/trace-index.json", staging),
               _artifact(staging / "trace/raw" / Path(outcome["native_path"]).name, staging)]
    atomic_json(staging / "resource-metrics.json", resource_metrics(outcome["identity"], binding, sources))
    atomic_json(staging / "metadata/result.json", {key: value for key, value in outcome.items() if key != "binding"})
    store.update(item["key"], "SEALING", identity=outcome["identity"])
    receipt = seal_execution(execution, outcome["identity"])
    ready = _ready_document(root, item, manifest, unit, task, outcome, binding, receipt)
    atomic_json(execution / "execution-ready.json", ready, create=True)
    store.publish_ready(item["key"], ready)
    (execution / "execution-ready.json").chmod(0o444)
    return ready


def _ready_document(root, item, manifest, unit, task, outcome, binding, receipt):
    execution = inside(root, item["execution_root"])
    return {"schema": READY_SCHEMA, "identity": outcome["identity"], "parent_batch_id": root.name,
             "parent_batch_sha256": digest(manifest), "unit_id": unit["unit_id"], "run_index": item["run_index"],
             "task_id": task["task_id"], "parent_task_ids": unit["task_ids"],
             "execution_root": item["execution_root"], "workspace": outcome["workspace"],
             "backup_sha256": receipt["archive_sha256"], "backup_receipt_sha256": file_sha256(execution / "backups/backup-receipt.json"),
             "native_session": binding["session"], "actual_model": binding["actual_model"],
             "reasoning_effort": binding["reasoning_effort"], "trace_status": "partial" if binding["missing"] else "complete",
             "scoring_allowed": True, "created_at": utc_now()}


def _reconcile_sealed(root, store, item, manifest, unit, task):
    from .trace import normalize_rollout
    execution = inside(root, item["execution_root"])
    receipt = verify_execution(execution)
    original = execution / "original"
    outcome = read_json(original / "metadata/result.json")
    prompt = (inside(root, task["input_root"]) / "execution/PROMPT.md").read_text(encoding="utf-8")
    binding = normalize_rollout(inside(original, outcome["native_path"]), identity=outcome["identity"], prompt=prompt,
                                guest_cwd=outcome["binding_cwd"] if "binding_cwd" in outcome else
                                read_json(original / "metadata/native-binding.json")["session"]["cwd"],
                                requested_model=unit["model"], requested_effort=unit.get("reasoning_effort"), report=outcome["report"])
    if binding["missing"] or outcome["identity"] != receipt["identity"]:
        raise E2EError("SEALED_RESULT_BINDING_INVALID")
    ready = _ready_document(root, item, manifest, unit, task, outcome, binding, receipt)
    atomic_json(execution / "execution-ready.json", ready, create=True)
    store.publish_ready(item["key"], ready)


def verify_ready(root: Path, item: dict, manifest: dict) -> dict:
    execution = inside(root, item["execution_root"])
    ready = read_json(execution / "execution-ready.json")
    original, receipt = execution_source(execution)
    binding = read_json(original / "metadata/native-binding.json")
    outcome = read_json(original / "metadata/result.json")
    index = read_json(original / "trace/trace-index.json")
    unit = next(unit for unit in manifest["units"] if unit["unit_id"] == item["unit_id"])
    expected = {"batch_id": root.name + f"-r{item['run_index']:04d}", "unit_id": item["unit_id"],
                "task_id": item["task_id"], "attempt_id": item["attempt_id"]}
    if (ready.get("schema") != READY_SCHEMA or ready.get("identity") != expected
            or ready.get("parent_batch_sha256") != digest(manifest) or receipt["identity"] != expected
            or ready.get("backup_sha256") != receipt["archive_sha256"]
            or ready.get("backup_receipt_sha256") != file_sha256(execution / "backups/backup-receipt.json")
            or ready.get("parent_task_ids") != unit["task_ids"] or ready.get("unit_id") != item["unit_id"]
            or ready.get("run_index") != item["run_index"] or ready.get("task_id") != item["task_id"]
            or ready.get("actual_model") != binding["actual_model"]
            or ready.get("reasoning_effort") != binding["reasoning_effort"]
            or ready.get("native_session") != binding["session"] or ready.get("workspace") != outcome["workspace"]
            or ready.get("trace_status") != index["completeness"]["status"]
            or binding.get("missing") or outcome["cleanup"].get("success") is not True
            or ready.get("scoring_allowed") is not True):
        raise E2EError("EXECUTION_READY_PROVENANCE_INVALID")
    return ready


def _worker(root: Path, store: BatchStore, item: dict, manifest: dict, unit: dict, task: dict,
            config: AgentCubeConfig, stop, driver_factory=None):
    driver_type = driver_factory or DRIVERS[(unit["backend"], unit["harness"])]
    driver = driver_type(batch_root=root, store=store, item=item, task=task, unit=unit, config=config, stop_event=stop)
    execution = inside(root, item["execution_root"])
    try:
        current = store.get(item["key"])
        if current.get("runtime") and current["runtime"] != driver.config.public():
            raise E2EError("EXECUTION_RUNTIME_CONFIGURATION_DRIFT")
        failure_file = execution / "original/metadata/failure.json"
        if ((execution / "backups/backup-receipt.json").exists() and failure_file.is_file()
                and not (execution / "original/metadata/result.json").exists()):
            receipt = verify_execution(execution)
            expected = {"batch_id": root.name + f"-r{item['run_index']:04d}", "unit_id": item["unit_id"],
                        "task_id": item["task_id"], "attempt_id": item["attempt_id"]}
            if receipt["identity"] != expected:
                raise E2EError("SEALED_FAILURE_IDENTITY_MISMATCH")
            failure = read_json(failure_file)
            final_phase = failure.get("execution_phase", "FAILED")
            current = store.update(item["key"], final_phase, error=failure)
        if current["phase"] in {"FAILED", "CANCELLED"}:
            try:
                cleanup = driver.client.delete_session(current["session_id"])
            except PlatformError as error:
                cleanup = {"confirmed": False, "error": str(error)}
            store.update(item["key"], current["phase"], resource_held=not cleanup["confirmed"], cleanup=cleanup)
            return
        if (execution / "execution-ready.json").exists():
            ready = verify_ready(root, item, manifest)
            store.publish_ready(item["key"], ready)
        else:
            # A completed seal can be resumed into publication without calling run again.
            if (execution / "backups/backup-receipt.json").exists():
                _reconcile_sealed(root, store, item, manifest, unit, task)
            else:
                outcome = driver.execute()
                _publish(root, store, store.get(item["key"]), manifest, unit, task, outcome)
        row = store.get(item["key"])
        cleanup = row.get("cleanup")
        if row.get("resource_held") and row.get("session_id"):
            try:
                cleanup = driver.client.delete_session(row["session_id"])
            except PlatformError as error:
                cleanup = {"confirmed": False, "error": str(error)}
        store.update(item["key"], "COMPLETED", resource_held=bool(row.get("resource_held") and not (cleanup or {}).get("confirmed")),
                     cleanup=cleanup, error=None, observer_paused=False, finished_at=utc_now())
    except (ObservationPaused, PlatformError) as error:
        row = store.get(item["key"])
        uncertain = (isinstance(error, ObservationPaused) or getattr(error, "uncertain", False)
                     or bool(row.get("dispatch_armed_at")) or row.get("report", {}).get("status") == "completed")
        if uncertain:
            phase = "NEEDS_ATTENTION" if row.get("creation_intent_at") else "PENDING"
            store.update(item["key"], phase, resource_held=row["resource_held"] if row.get("creation_intent_at") else False,
                         error={"code": type(error).__name__, "message": str(error)},
                         observer_paused=isinstance(error, ObservationPaused))
        else:
            _failure(root, store, item, driver, error)
    except Exception as error:
        row = store.get(item["key"])
        if row.get("report", {}).get("status") == "completed":
            store.update(item["key"], "NEEDS_ATTENTION", error={"code": type(error).__name__, "message": str(error)})
        else:
            _failure(root, store, item, driver, error)
    finally:
        driver.client.close()


def _failure(root, store, item, driver, error, *, final_phase="FAILED"):
    row = store.get(item["key"])
    message = str(redact(str(error), driver.config.auth_token))
    failure = {"code": type(error).__name__, "message": message, "report_status": row.get("report", {}).get("status")}
    if final_phase == "CANCELLED":
        failure["execution_phase"] = final_phase
    try:
        preservation = driver.salvage()
        atomic_json(driver.staging / "metadata/failure.json", failure)
        if row.get("dispatch_armed_at") and not preservation.get("complete"):
            store.update(item["key"], "NEEDS_ATTENTION", error=failure, preservation=preservation,
                         preservation_error="FAILED_EXECUTION_COLLECTION_INCOMPLETE")
            return
        seal_execution(driver.root, {"batch_id": root.name + f"-r{item['run_index']:04d}", "unit_id": item["unit_id"],
                                     "task_id": item["task_id"], "attempt_id": item["attempt_id"]})
        cleanup = None
        if row.get("session_id"):
            cleanup = driver.client.delete_session(row["session_id"])
        store.update(item["key"], final_phase, resource_held=bool(row.get("session_id") and row.get("resource_held") and not (cleanup or {}).get("confirmed")),
                     error=failure, cleanup=cleanup, preservation=preservation,
                     preservation_error=None, finished_at=utc_now())
    except Exception as backup_error:
        store.update(item["key"], "NEEDS_ATTENTION", error=failure,
                     preservation_error=str(redact(str(backup_error), driver.config.auth_token)))


def run_batch(root: Path, config: AgentCubeConfig, *, unit_ids: list[str] | None = None,
              task_ids: list[str] | None = None, driver_factory=None, progress=None) -> dict:
    manifest = load_batch(root)
    store = BatchStore(root)
    units = {unit["unit_id"]: unit for unit in manifest["units"]}
    tasks = {task["task_id"]: task for task in manifest["tasks"]}
    if unit_ids and set(unit_ids) - set(units):
        raise E2EError("UNIT_SELECTION_UNKNOWN")
    selected = set(unit_ids or units)
    selected_tasks = set(task_ids or ())
    if selected_tasks and not selected_tasks <= {task for unit_id in selected for task in units[unit_id]['task_ids']}:
        raise E2EError('TASK_RESUME_SELECTION_UNKNOWN')

    def selected_row(row):
        return row['unit_id'] in selected and (not selected_tasks or row['task_id'] in selected_tasks)
    stop = threading.Event()
    with controller_lock(root) as owner:
        heartbeat_at = 0

        def heartbeat():
            nonlocal heartbeat_at
            now = time.monotonic()
            if now - heartbeat_at >= HEARTBEAT_INTERVAL_SECONDS:
                refresh_controller_heartbeat(root, owner)
                heartbeat_at = now

        errors = []
        checked = set()
        for item in store.rows():
            heartbeat()
            if not selected_row(item) or item["phase"] in {"COMPLETED", "FAILED", "CANCELLED"}:
                continue
            pair = (item["unit_id"], item["task_id"])
            if pair in checked:
                continue
            checked.add(pair)
            factory = driver_factory or DRIVERS[(units[item["unit_id"]]["backend"], units[item["unit_id"]]["harness"])]
            driver = factory(batch_root=root, store=store, item=item, task=tasks[item["task_id"]],
                             unit=units[item["unit_id"]], config=config, stop_event=stop)
            try:
                driver.preflight()
            except E2EError as error:
                errors.append({"unit_id": item["unit_id"], "task_id": item["task_id"], "error": str(error)})
            finally:
                driver.client.close()
        atomic_json(root / "control/preflight.json", {"valid": not errors, "errors": errors, "at": utc_now()})
        if errors:
            raise E2EError("BATCH_PREFLIGHT_FAILED: " + str(root / "control/preflight.json"))
        capacity = manifest["plan"]["execution_concurrency"]
        seen = set()
        futures = {}
        cursor = 0
        interrupted = False
        with ThreadPoolExecutor(max_workers=capacity) as pool:
            while True:
                try:
                    heartbeat()
                    rows = store.rows()
                    attention = any(row["phase"] == "NEEDS_ATTENTION" and (not selected_tasks or selected_row(row)) for row in rows)
                    held = sum(row["resource_held"] for row in rows)
                    active_units = Counter(unit for _, unit in futures.values())
                    for row in rows:
                        key, unit_id = row["key"], row["unit_id"]
                        if not selected_row(row) or key in seen or stop.is_set():
                            continue
                        resumable = row["phase"] in {"RESERVED", "CREATING", "PREPARING", "RUNNING", "COLLECTING", "SEALING", "NEEDS_ATTENTION"} or row["resource_held"]
                        if row["phase"] != "PENDING" and not resumable:
                            continue
                        if len(futures) >= capacity or active_units[unit_id] >= units[unit_id]["max_concurrency"]:
                            continue
                        if row["phase"] == "PENDING" and (attention or held >= capacity):
                            continue
                        seen.add(key)
                        if row["phase"] == "PENDING":
                            row = store.update(key, "RESERVED", resource_held=True)
                            held += 1
                        future = pool.submit(_worker, root, store, row, manifest, units[unit_id], tasks[row["task_id"]], config, stop, driver_factory)
                        futures[future] = (key, unit_id)
                        active_units[unit_id] += 1
                    if not futures:
                        break
                    done, _ = wait(futures, timeout=1, return_when=FIRST_COMPLETED)
                    for future in done:
                        future.result()
                        futures.pop(future)
                    store.export_events()
                    if progress:
                        for event in store.events(cursor):
                            progress(event)
                            cursor = event["sequence"]
                except KeyboardInterrupt:
                    interrupted = True
                    stop.set()
        summary = store.summary()
        summary.update(batch_id=root.name, interrupted=interrupted,
                       status="NEEDS_ATTENTION" if summary["resource_held"] or any(
                           row["phase"] in {"NEEDS_ATTENTION", "RESERVED", "CREATING", "PREPARING", "RUNNING", "COLLECTING", "SEALING"}
                           for row in summary["executions"]) else "FAILED" if summary["phase_counts"].get("FAILED")
                       else "COMPLETED" if all(row["phase"] == "COMPLETED" for row in summary["executions"]) else "PENDING")
        atomic_json(root / "batch-summary.json", summary)
        store.export_events()
        return summary


def cleanup_batch(root: Path, config: AgentCubeConfig, *, cancel: bool = False) -> dict:
    if cancel:
        return cancel_batch(root, config)
    load_batch(root)
    store = BatchStore(root)
    with controller_lock(root):
        for item in store.rows():
            if not item["resource_held"]:
                continue
            if not item.get("session_id"):
                raise E2EError("UNKNOWN_SESSION_REQUIRES_PLATFORM_RECONCILIATION")
            completed = item["phase"] in {"COMPLETED", "FAILED", "CANCELLED"}
            if not completed and not cancel:
                raise E2EError("ACTIVE_EXECUTION_REQUIRES_EXPLICIT_CANCEL")
            if completed and item["phase"] != "CANCELLED" and not cancel:
                verify_backup(inside(root, item["execution_root"]))
            runtime = AgentCubeConfig(**{**item["runtime"], "auth_token": config.auth_token})
            if runtime.user_id != config.user_id or runtime.app_id != config.app_id:
                raise E2EError("CLEANUP_ACCOUNT_MISMATCH")
            client = AgentCubeClient(runtime)
            try:
                receipt = client.delete_session(item["session_id"])
                store.update(item["key"], item["phase"] if completed else "CANCELLED", resource_held=not receipt["confirmed"],
                             cleanup=receipt, cancellation_requested_at=utc_now() if cancel else None)
            finally:
                client.close()
    return store.summary()


def cancel_batch(root: Path, config: AgentCubeConfig, driver_factory=None) -> dict:
    """Stop new dispatch and seal owned evidence before releasing dispatched VMs."""
    manifest = load_batch(root)
    store = BatchStore(root)
    units = {unit["unit_id"]: unit for unit in manifest["units"]}
    tasks = {task["task_id"]: task for task in manifest["tasks"]}
    stop = threading.Event()
    with controller_lock(root):
        for item in store.rows():
            if not item.get("session_id"):
                if item.get("creation_intent_at"):
                    store.update(item["key"], "NEEDS_ATTENTION", error={"code": "UNKNOWN_SESSION_REQUIRES_PLATFORM_RECONCILIATION"})
                elif item["phase"] not in {"COMPLETED", "FAILED", "CANCELLED"}:
                    store.update(item["key"], "CANCELLED", resource_held=False, cancellation_requested_at=utc_now())
                continue
            if not item["resource_held"]:
                continue
            runtime = item.get("runtime") or config.public()
            if runtime.get("user_id") != config.user_id or runtime.get("app_id") != config.app_id:
                raise E2EError("CLEANUP_ACCOUNT_MISMATCH")
            frozen = AgentCubeConfig(**{**runtime, "auth_token": config.auth_token})
            unit, task = units[item["unit_id"]], tasks[item["task_id"]]
            execution = inside(root, item["execution_root"])
            if (execution / "backups/backup-receipt.json").exists() or item.get("report", {}).get("status") == "completed":
                _worker(root, store, item, manifest, unit, task, frozen, stop, driver_factory)
                continue
            factory = driver_factory or DRIVERS[(unit["backend"], unit["harness"])]
            driver = factory(batch_root=root, store=store, item=item, task=task, unit=unit, config=frozen, stop_event=stop)
            try:
                _failure(root, store, item, driver, E2EError("CANCEL_REQUESTED"), final_phase="CANCELLED")
            finally:
                driver.client.close()
        store.export_events()
    return store.summary()
