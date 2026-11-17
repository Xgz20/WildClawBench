"""Reconcile a timed-out create after an operator identifies a destroyed session."""
from datetime import datetime
from pathlib import Path

from .agentcube import AgentCubeClient, AgentCubeConfig
from .artifacts import seal_execution, verify_execution
from .common import E2EError, atomic_json, file_sha256, identifier, inside, read_json, utc_now
from .engine import load_batch
from .store import BatchStore, controller_lock


def _time(value):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise E2EError("CREATION_OBSERVATION_TIMEZONE_REQUIRED")
    return parsed.timestamp()


def _write_once(path, value):
    if path.exists():
        if read_json(path) != value:
            raise E2EError("CREATION_OBSERVATION_CONFLICT")
    else:
        atomic_json(path, value, create=True)


def reconcile_absent_creation(root: Path, key: str, proof_path: Path, expected_sha256: str,
                              config: AgentCubeConfig, client_factory=AgentCubeClient):
    if file_sha256(proof_path) != expected_sha256:
        raise E2EError("CREATION_OBSERVATION_SHA256_MISMATCH")
    proof = read_json(proof_path)
    load_batch(root)
    store = BatchStore(root)
    with controller_lock(root):
        item = store.get(key)
        identity = {"batch_id": root.name + f"-r{item['run_index']:04d}",
                    "unit_id": item["unit_id"], "task_id": item["task_id"], "attempt_id": item["attempt_id"]}
        runtime = item.get("runtime", {})
        if item.get("dispatch_armed_at") or item.get("jobs") or item.get("report"):
            raise E2EError("DISPATCHED_EXECUTION_CANNOT_RECONCILE_AS_ABSENT_CREATION")
        if item["phase"] not in {"NEEDS_ATTENTION", "FAILED"} or not item.get("creation_intent_at"):
            raise E2EError("EXECUTION_IS_NOT_AN_UNRESOLVED_CREATION")
        prior = item.get("creation_reconciliation")
        if (proof.get("schema") != "wildclawbench.agentcube-creation-observation/v1"
                or proof.get("identity") != identity or proof.get("observed_state") != "destroyed"
                or proof.get("creation_intent_at") != item["creation_intent_at"]
                or not isinstance(proof.get("source_url"), str) or not proof["source_url"]
                or type(proof.get("matching_session_count")) is not int or proof["matching_session_count"] != 1
                or any(proof.get(field) != runtime.get(field) for field in ["app_id", "user_id", "namespace", "template"])):
            raise E2EError("CREATION_OBSERVATION_IDENTITY_MISMATCH")
        sid = identifier(proof["session_id"], "session_id")
        if item.get("session_id") not in {None, sid} or (prior and prior.get("proof_sha256") != expected_sha256):
            raise E2EError("CREATION_OBSERVATION_CONFLICT")
        if item["phase"] == "FAILED" and not prior:
            raise E2EError("EXECUTION_IS_NOT_AN_UNRESOLVED_CREATION")
        if (int(_time(proof["created_at"])) != int(_time(item["creation_intent_at"]))
                or not _time(proof["created_at"]) <= _time(proof["destroyed_at"]) <= _time(proof["observed_at"])):
            raise E2EError("CREATION_OBSERVATION_TIME_MISMATCH")
        if config.app_id != runtime.get("app_id") or config.user_id != runtime.get("user_id"):
            raise E2EError("CREATION_RECONCILIATION_ACCOUNT_MISMATCH")
        frozen = AgentCubeConfig(**{**runtime, "auth_token": config.auth_token})
        client = client_factory(frozen)
        try:
            absence = client.confirm_session_absent(sid)
        finally:
            client.close()
        if absence.get("confirmed") is not True or absence.get("session_id") != sid:
            raise E2EError("SESSION_ABSENCE_NOT_CONFIRMED")
        execution = inside(root, item["execution_root"])
        if prior and (execution / "backups/backup-receipt.json").exists():
            receipt = verify_execution(execution)
            if receipt["identity"] != identity:
                raise E2EError("CREATION_OBSERVATION_IDENTITY_MISMATCH")
            failure = read_json(execution / "original/metadata/failure.json")
            if failure.get("reconciliation_proof_sha256") != expected_sha256:
                raise E2EError("CREATION_OBSERVATION_CONFLICT")
            if item["phase"] == "FAILED" and not item["resource_held"]:
                return store.summary()
        else:
            original = execution / "original"
            metadata = (original if original.exists() else execution / "staging") / "metadata"
            failure_path = metadata / "failure.json"
            failure = read_json(failure_path) if failure_path.exists() else {
                "code": "SESSION_CREATION_TERMINATED_BEFORE_DISPATCH", "fault_domain": "agentcube",
                "message": "平台确认原创建会话已销毁，未派发题目。", "prior_error": item.get("error"),
                "reconciliation_proof_sha256": expected_sha256}
            if failure.get("reconciliation_proof_sha256") != expected_sha256:
                raise E2EError("CREATION_OBSERVATION_CONFLICT")
            _write_once(metadata / "creation-observation.json", proof)
            _write_once(metadata / "creation-absence.json", absence)
            _write_once(failure_path, failure)
            store.update(key, "NEEDS_ATTENTION", session_id=sid, creation_reconciliation={
                "proof_sha256": expected_sha256, "source_url": proof["source_url"], "session_id": sid})
            seal_execution(execution, identity)
        store.update(key, "FAILED", resource_held=False, cleanup=absence, error=failure,
                     finished_at=item.get("finished_at") or utc_now())
        store.export_events()
        return store.summary()
