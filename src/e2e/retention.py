"""Durable retention of sealed failed attempts, independent of execution slots."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from .common import E2EError, digest, redact, utc_now

CAPABILITY = "failed-sandbox-retention-v1"
DEFAULT_SECONDS = 1800
HELD_STATES = {"retained", "release_pending", "release_failed"}
PUBLIC_FIELDS = {"attempt_id", "execution_key", "session_id", "status", "retained_at",
                 "destroy_after", "released_at", "last_release_at", "error", "evidence_sealed",
                 "client_state", "screenshot", "namespace", "template"}


def public_record(value):
    return {key: item for key, item in value.items() if key in PUBLIC_FIELDS}


def retained(row):
    value = row.get("sandbox_retention") or {}
    return (row.get("phase", row.get("stage")) == "FAILED" and value.get("evidence_sealed") is True
            and value.get("status") in HELD_STATES)


def execution_held(row):
    return bool(row["resource_held"] and not retained(row))


def preserve_failure(store, key, runtime, seconds, *, failure, preservation, screenshot=None, now=None):
    """Register failure and its retention atomically, only after immutable sealing."""
    from .artifacts import verify_execution
    from .common import inside
    row = store.get(key)
    if not row.get("session_id") or not row["resource_held"] or not seconds:
        return False
    if type(seconds) is not int or not 0 < seconds <= 86400:
        raise E2EError("FAILURE_RETENTION_SECONDS_INVALID")
    verify_execution(inside(store.root, row["execution_root"]))
    if not preservation.get("complete"):
        raise E2EError("FAILURE_RETENTION_REQUIRES_SEALED_EVIDENCE")
    clock = now or datetime.now(timezone.utc)
    value = {"attempt_id": row["attempt_id"], "execution_key": key, "session_id": row["session_id"],
             "status": "retained", "retained_at": clock.isoformat(),
             "destroy_after": (clock + timedelta(seconds=seconds)).isoformat(),
             "evidence_sealed": True, "client_state": "stopped" if row.get("dispatch_armed_at") else "not_dispatched",
             "namespace": runtime["namespace"], "template": runtime["template"], "runtime": runtime}
    if screenshot:
        value["screenshot"] = screenshot
    store.retain_failure(key, value, error=failure, preservation=preservation,
                         preservation_error=None, finished_at=clock.isoformat())
    return True


def reap(root: Path, config, *, attempt_id=None, force=False, client_factory=None, now=None):
    """Retry exact-session deletion; a 202/unknown receipt never means released."""
    from .agentcube import AgentCubeClient, AgentCubeConfig
    from .artifacts import verify_backup
    from .common import inside
    from .engine import load_batch
    from .store import BatchStore, controller_lock
    load_batch(root)
    if force and not attempt_id:
        raise E2EError("RETENTION_FORCE_REQUIRES_ATTEMPT")
    store = BatchStore(root)
    records = store.retentions()
    if attempt_id and attempt_id not in {value["attempt_id"] for value in records}:
        raise E2EError("RETAINED_ATTEMPT_UNKNOWN")
    clock = now or datetime.now(timezone.utc)
    output = []
    for value in records:
        if attempt_id and value["attempt_id"] != attempt_id:
            continue
        if value["status"] == "released":
            output.append(public_record(value))
            continue
        if not force and value["status"] == "retained" and datetime.fromisoformat(value["destroy_after"]) > clock:
            continue
        if not force and value.get("next_release_at") and datetime.fromisoformat(value["next_release_at"]) > clock:
            continue
        try:
            with controller_lock(root, "retention-" + digest(value["attempt_id"])[:20]):
                value = next(item for item in store.retentions() if item["attempt_id"] == value["attempt_id"])
                if value["status"] == "released":
                    output.append(public_record(value))
                    continue
                runtime = value["runtime"]
                if runtime["user_id"] != config.user_id or runtime["app_id"] != config.app_id:
                    raise E2EError("RETENTION_CLEANUP_ACCOUNT_MISMATCH")
                client = (client_factory or AgentCubeClient)(AgentCubeConfig(**{**runtime, "auth_token": config.auth_token}))
                fields = {"status": "release_pending", "last_release_at": clock.isoformat(),
                          "next_release_at": (clock + timedelta(seconds=30)).isoformat()}
                store.update_retention(value["attempt_id"], **fields)
                try:
                    source = store.get_version(value["execution_key"], value["attempt_id"])
                    receipt, _ = verify_backup(inside(root, source["execution_root"]))
                    if receipt["identity"]["attempt_id"] != value["attempt_id"]:
                        raise E2EError("RETENTION_BACKUP_IDENTITY_MISMATCH")
                    receipt = client.delete_session(value["session_id"])
                    fields.update(cleanup=receipt, error=None)
                    if receipt["confirmed"]:
                        fields.update(status="released", released_at=clock.isoformat(), next_release_at=None)
                except Exception as error:
                    fields.update(status="release_failed", error=str(redact(str(error), config.auth_token))[:1000])
                finally:
                    client.close()
                output.append(public_record(store.update_retention(value["attempt_id"], **fields)))
        except E2EError as error:
            if "CONTROLLER_ALREADY_RUNNING" not in str(error):
                raise
    store.export_events()
    return {"retentions": output, "observed_at": utc_now()}
