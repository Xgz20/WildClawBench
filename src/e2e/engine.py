"""Bounded multi-unit execution with durable remote job identities."""
from __future__ import annotations

from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
import re
import threading
import time

from .agentcube import AgentCubeClient, AgentCubeConfig, PlatformError
from .artifacts import execution_source, seal_execution, verify_backup, verify_execution
from .backend import DRIVERS, ObservationPaused
from .common import E2EError, atomic_json, digest, file_sha256, inside, read_json, redact, utc_now
from .store import BatchStore, controller_lock, refresh_controller_heartbeat
from .trace import resource_metrics, write_trace
from .retention import execution_held, retained, preserve_failure, reap


READY_SCHEMA = "wildclawbench.task-execution-handoff/v1"
HEARTBEAT_INTERVAL_SECONDS = 5


def _error_record(error):
    value = {"code": type(error).__name__, "message": str(error)}
    if str(error) == 'EXECUTION_RUNTIME_CONFIGURATION_DRIFT':
        value['fault_scope'] = 'batch'
    if isinstance(error, PlatformError):
        value["fault_domain"] = "agentcube"
        if error.platform_code:
            value["platform_code"] = error.platform_code
        if (error.platform_code == "USER_QUOTA_NOT_ACTIVE"
                or re.fullmatch(r"[A-Z_]+_HTTP_(401|403)", str(error).split(":", 1)[0])):
            value["fault_scope"] = "batch"
    return value


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
    prompt_metadata = store.get(item["key"]).get("prompt")
    if prompt_metadata:
        if (prompt_metadata.get("base_prompt_sha256") != task["prompt_sha256"]
                or prompt_metadata.get("effective_prompt_sha256") != binding["prompt_sha256"]):
            raise E2EError("EXECUTION_PROMPT_BINDING_MISMATCH")
        proof.update(base_prompt_sha256=task["prompt_sha256"],
                     prompt_sha256=prompt_metadata["effective_prompt_sha256"], prompt=prompt_metadata)
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
    witness = _prompt_plugin_provenance(root, item, execution / "original")
    return {"schema": READY_SCHEMA, "identity": outcome["identity"], "parent_batch_id": root.name,
             **({"prompt_plugins_sha256": witness} if witness else {}),
             "parent_batch_sha256": digest(manifest), "unit_id": unit["unit_id"], "run_index": item["run_index"],
             "task_id": task["task_id"], "parent_task_ids": unit["task_ids"],
             "execution_root": item["execution_root"], "workspace": outcome["workspace"],
             "backup_sha256": receipt["archive_sha256"], "backup_receipt_sha256": file_sha256(execution / "backups/backup-receipt.json"),
             "native_session": binding["session"], "actual_model": binding["actual_model"],
             "reasoning_effort": binding["reasoning_effort"], "max_mode": binding.get("max_mode"), "trace_status": "partial" if binding["missing"] else "complete",
             "scoring_allowed": True, "created_at": utc_now()}


def _prompt_plugin_provenance(root, item, original):
    from .preprocessing import frozen_prompt_directives, requires_plugin_witness
    names = frozen_prompt_directives(root, item["unit_id"], item["task_id"])["plugin_mentions"]
    if not names or not requires_plugin_witness(root, item["unit_id"]):
        return None
    path = original / "metadata/prompt-plugins.json"
    if not path.is_file() or path.is_symlink():
        raise E2EError("PROMPT_PLUGIN_WITNESS_MISSING")
    witness = read_json(path)
    proof = read_json(original / "trace/bindings/execution-proof.json")
    if (witness.get("status") != "passed" or witness.get("verified_after_execution") is not True
            or witness.get("attempt_id") != item["attempt_id"] or witness.get("plugin_mentions") != names
            or not witness.get("session_id") or witness["session_id"] != proof.get("session_id")):
        raise E2EError("PROMPT_PLUGIN_WITNESS_DRIFT")
    return file_sha256(path)


def _reconcile_sealed(root, store, item, manifest, unit, task):
    from .trace import normalize_rollout
    execution = inside(root, item["execution_root"])
    receipt = verify_execution(execution)
    original = execution / "original"
    outcome = read_json(original / "metadata/result.json")
    from .preprocessing import execution_prompt
    base_prompt = (inside(root, task["input_root"]) / "execution/PROMPT.md").read_bytes()
    prompt = execution_prompt(original, base_prompt, item.get("prompt")).decode("utf-8")
    if unit["harness"]=="workbuddy":
        from .workbuddy_trace import normalize_workbuddy
        archived=read_json(original/"metadata/native-binding.json")
        binding=normalize_workbuddy(inside(original,outcome["native_path"]),identity=outcome["identity"],prompt=prompt,guest_cwd=archived["session"]["cwd"],
            requested_model=unit["model"],requested_max_mode=unit.get("max_mode",False),report=outcome["report"],**{k:archived["controller_binding"][k] for k in ["product_report","diagnostics"]})
    else:
        binding = normalize_rollout(inside(original, outcome["native_path"]), identity=outcome["identity"], prompt=prompt,
                                    guest_cwd=outcome["binding_cwd"] if "binding_cwd" in outcome else
                                    read_json(original / "metadata/native-binding.json")["session"]["cwd"],
                                    requested_model=unit["model"], requested_effort=unit.get("reasoning_effort"), report=outcome["report"],
                                    desktop=unit["harness"] == "chatgpt-desktop")
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
    witness = _prompt_plugin_provenance(root, item, original)
    if witness and ready.get("prompt_plugins_sha256") != witness:
        raise E2EError("PROMPT_PLUGIN_WITNESS_DRIFT")
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
            if retained(current):
                return
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
                         error=_error_record(error),
                         observer_paused=isinstance(error, ObservationPaused))
        else:
            _failure(root, store, item, driver, error)
    except Exception as error:
        row = store.get(item["key"])
        binding_failure = (isinstance(error, E2EError)
                           and str(error).split(":", 1)[0] == "TASK_NATIVE_BINDING_AMBIGUOUS")
        if row.get("report", {}).get("status") == "completed" and binding_failure:
            # A deterministic parser rejection is not an unknown remote job.
            # The failure path must stop the owned processes, collect and seal
            # diagnostic evidence before retention can free the execution slot.
            # Any incomplete salvage still becomes NEEDS_ATTENTION below.
            _failure(root, store, item, driver, error)
        elif row.get("report", {}).get("status") == "completed":
            store.update(item["key"], "NEEDS_ATTENTION", error=_error_record(error))
        else:
            _failure(root, store, item, driver, error)
    finally:
        _reconcile_attention_resource(store, item['key'], driver)
        driver.client.close()


def _reconcile_attention_resource(store, key, driver):
    row = store.get(key)
    confirm = getattr(driver.client, 'confirm_session_absent', None)
    if (row['phase'] != 'NEEDS_ATTENTION' or not row['resource_held'] or not row.get('session_id')
            or row.get('runtime') != driver.config.public() or not callable(confirm)):
        return
    try:
        proof = confirm(row['session_id'])
        if (isinstance(proof, dict) and proof.get('confirmed') is True
                and proof.get('session_id') == row['session_id']):
            store.update(key, 'NEEDS_ATTENTION', resource_held=False, cleanup=proof)
    except (PlatformError, OSError, ValueError):
        # A missing file, timeout or rejected lookup is not proof of absence.
        pass


def _failure(root, store, item, driver, error, *, final_phase="FAILED"):
    row = store.get(item["key"])
    message = str(redact(str(error), driver.config.auth_token))
    failure = {**_error_record(error), "message": message, "report_status": row.get("report", {}).get("status")}
    if failure["report_status"] == "completed" and message.split(":", 1)[0] == "TASK_NATIVE_BINDING_AMBIGUOUS":
        failure["failure_stage"] = "native_trace_validation"
    if isinstance(error,PlatformError):
        failure["fault_domain"]="agentcube"
        if error.platform_code:failure["platform_code"]=error.platform_code
    if final_phase == "CANCELLED":
        failure["execution_phase"] = final_phase
    try:
        capture = getattr(type(driver), "capture_failure_scene", None)
        if final_phase == "FAILED" and capture and load_batch(root)["plan"].get("failure_retention_seconds", 0):
            driver.capture_failure_scene()
        preservation = driver.salvage()
        atomic_json(driver.staging / "metadata/failure.json", failure)
        if row.get("dispatch_armed_at") and not preservation.get("complete"):
            store.update(item["key"], "NEEDS_ATTENTION", error=failure, preservation=preservation,
                         preservation_error="FAILED_EXECUTION_COLLECTION_INCOMPLETE")
            return
        seal_execution(driver.root, {"batch_id": root.name + f"-r{item['run_index']:04d}", "unit_id": item["unit_id"],
                                     "task_id": item["task_id"], "attempt_id": item["attempt_id"]})
        screenshot = driver.root / "original/evidence/failure-screen.png"
        if final_phase == "FAILED" and preserve_failure(store, item["key"], driver.config.public(),
                load_batch(root)["plan"].get("failure_retention_seconds", 0), failure=failure, preservation=preservation,
                screenshot=screenshot.relative_to(root).as_posix() if screenshot.is_file() else None):
            return
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
              task_ids: list[str] | None = None, driver_factory=None, progress=None, rerun_case: dict | None = None,
              cancel_before_dispatch: bool = False, recovery: dict | None = None,
              rerun_selection: dict | None = None) -> dict:
    if rerun_selection is not None and (rerun_case is not None or unit_ids or task_ids):
        raise E2EError("RERUN_SELECTION_SCOPE_CONFLICT")
    manifest = load_batch(root)
    store = BatchStore(root)
    units = {unit["unit_id"]: unit for unit in manifest["units"]}
    tasks = {task["task_id"]: task for task in manifest["tasks"]}
    if unit_ids and set(unit_ids) - set(units):
        raise E2EError("UNIT_SELECTION_UNKNOWN")
    selected = set(unit_ids or units)
    selected_tasks = set(task_ids or ())
    selected_keys = set()
    if selected_tasks and not selected_tasks <= {task for unit_id in selected for task in units[unit_id]['task_ids']}:
        raise E2EError('TASK_RESUME_SELECTION_UNKNOWN')

    def selected_row(row):
        return (row['unit_id'] in selected and (not selected_tasks or row['task_id'] in selected_tasks)
                and (not selected_keys or row['key'] in selected_keys))
    stop = threading.Event()
    with controller_lock(root) as owner:
        if recovery is not None:
            if rerun_case is not None or rerun_selection is not None or unit_ids or task_ids:
                raise E2EError("RECOVERY_MUST_PRESERVE_BATCH_SCOPE")
            from .recovery import register_recovery
            with controller_lock(root, "scoring-queue"):
                register_recovery(root, recovery)
        if rerun_case is not None or rerun_selection is not None:
            with controller_lock(root, "scoring-queue"):
                receipt = (store.rerun_selected(**rerun_selection) if rerun_selection is not None
                           else store.rerun_case(**rerun_case))
            selected_keys.update(receipt["attempts"])
            if cancel_before_dispatch:
                for item in store.rows():
                    if item["key"] in selected_keys and item["phase"] == "PENDING":
                        store.update(item["key"], "CANCELLED", resource_held=False,
                                     cancellation_requested_at=utc_now(), finished_at=utc_now())
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
                    # Unknown jobs retain their own resource reservation. They
                    # must not block unrelated cases with available capacity.
                    batch_blocked = any(row["key"] in seen and (row.get("error") or {}).get("fault_scope") == "batch"
                                        for row in rows)
                    held = sum(execution_held(row) for row in rows)
                    active_units = Counter(unit for _, unit in futures.values())
                    held_units = Counter(row["unit_id"] for row in rows if execution_held(row))
                    for row in rows:
                        key, unit_id = row["key"], row["unit_id"]
                        if not selected_row(row) or key in seen or stop.is_set():
                            continue
                        resumable = row["phase"] in {"RESERVED", "CREATING", "PREPARING", "RUNNING", "COLLECTING", "SEALING", "NEEDS_ATTENTION"} or execution_held(row)
                        if row["phase"] != "PENDING" and not resumable:
                            continue
                        if len(futures) >= capacity or active_units[unit_id] >= units[unit_id]["max_concurrency"]:
                            continue
                        if row["phase"] == "PENDING" and (batch_blocked or held >= capacity
                                or held_units[unit_id] >= units[unit_id]["max_concurrency"]):
                            continue
                        seen.add(key)
                        if row["phase"] == "PENDING":
                            row = store.update(key, "RESERVED", resource_held=True)
                            held += 1
                            held_units[unit_id] += 1
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
                       status="NEEDS_ATTENTION" if summary["execution_resources_held"] or any(
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
        for retained_item in store.retentions():
            reap(root, config, attempt_id=retained_item["attempt_id"], force=True)
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
        for retained_item in store.retentions():
            reap(root, config, attempt_id=retained_item["attempt_id"], force=True)
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
