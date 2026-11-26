"""Audited reader upgrades for an existing batch, without replacing attempts."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from src.release import release_revision
from .common import E2EError, digest, file_sha256, identifier, utc_now
from .store import BatchStore

CAPABILITY = "execution-recovery-upgrade-v1"
SCHEMA = "wildclawbench.execution-recovery/v1"
TERMINAL = {"COMPLETED", "FAILED", "CANCELLED"}


def _check_execution_lock(root):
    path = root / 'control/execution.lock'
    if path.is_symlink():
        raise E2EError('RECOVERY_EXECUTION_LOCK_INVALID')
    if not path.exists():
        return
    with path.open('r+b') as stream:
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise E2EError('RECOVERY_EXECUTION_CONTROLLER_ACTIVE') from error
        if os.name == 'nt':
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _basis(root, manifest, rows):
    return {
        "manifest_sha256": file_sha256(root / "batch.json"),
        "manifest_revision": (manifest.get("engine") or {}).get("revision") or manifest.get("source_revision"),
        "executions": [{"key": row["key"], "attempt_id": row["attempt_id"],
                        "execution_root": row["execution_root"], "phase": row["phase"],
                        "resource_held": row["resource_held"], "session_id": row.get("session_id"),
                        "dispatch_armed_at": row.get("dispatch_armed_at"),
                        "jobs_sha256": digest(row.get("jobs", {})),
                        "runtime_sha256": digest(row.get("runtime"))} for row in rows],
    }


def inspect_recovery(root: Path):
    from .engine import load_batch
    manifest = load_batch(root)
    store = BatchStore(root)
    summary = store.summary()
    if (summary.get("controllers", {}).get("execution") or {}).get("lease_status") == "fresh":
        raise E2EError("RECOVERY_EXECUTION_CONTROLLER_ACTIVE")
    _check_execution_lock(root)
    if any(row["phase"] in {"CLAIMED", "RUNNING", "NEEDS_ATTENTION"} for row in store.scoring_rows()):
        raise E2EError("RECOVERY_SCORING_CONTROLLER_ACTIVE")
    rows = store.rows()
    if all(row["phase"] in TERMINAL for row in rows):
        raise E2EError("RECOVERY_HAS_NO_UNFINISHED_EXECUTIONS")
    basis = _basis(root, manifest, rows)
    return {"schema": SCHEMA, "basis": basis, "basis_sha256": digest(basis),
            "controller_idle": True,
            "target_revision": release_revision(Path(__file__).resolve().parents[2]),
            "completed_count": sum(row["phase"] == "COMPLETED" for row in rows),
            "pending_count": sum(row["phase"] == "PENDING" for row in rows),
            "attention_count": sum(row["phase"] == "NEEDS_ATTENTION" for row in rows)}


def register_recovery(root: Path, request: dict):
    """Called only while the execution and scoring-queue locks are held."""
    from .engine import load_batch
    manifest = load_batch(root)
    required = {'schema', 'recovery_id', 'source_revision', 'target_revision', 'manifest_sha256', 'basis_sha256'}
    if (not isinstance(request, dict) or set(request) != required or request.get("schema") != SCHEMA
            or any(not isinstance(request.get(key), str) or not re.fullmatch(r'[0-9a-f]{40}', request[key])
                   for key in ('source_revision', 'target_revision'))
            or any(not isinstance(request.get(key), str) or not re.fullmatch(r'[0-9a-f]{64}', request[key])
                   for key in ('manifest_sha256', 'basis_sha256'))):
        raise E2EError("RECOVERY_SCHEMA_INVALID")
    identifier(request.get("recovery_id"), "recovery_id")
    target = release_revision(Path(__file__).resolve().parents[2])
    if request.get("target_revision") != target:
        raise E2EError("RECOVERY_EXECUTOR_REVISION_DRIFT")
    if request.get("manifest_sha256") != file_sha256(root / "batch.json"):
        raise E2EError("RECOVERY_MANIFEST_DRIFT")
    store = BatchStore(root)
    with store.transaction() as db:
        key = "execution-recovery:" + request["recovery_id"]
        if db.execute("SELECT 1 FROM scoring WHERE phase IN ('CLAIMED','RUNNING','NEEDS_ATTENTION') LIMIT 1").fetchone():
            raise E2EError("RECOVERY_SCORING_CONTROLLER_ACTIVE")
        existing = db.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
        if existing:
            receipt = json.loads(existing[0])
            if receipt["request_sha256"] != digest(request):
                raise E2EError("RECOVERY_REQUEST_CONFLICT")
            return receipt
        rows = [store._with_retention(db, store._row(row)) for row in
                db.execute("SELECT * FROM executions ORDER BY ordinal")]
        if digest(_basis(root, manifest, rows)) != request.get("basis_sha256"):
            raise E2EError("RECOVERY_EXECUTION_STATE_DRIFT")
        runtimes = {}
        for row in rows:
            if row.get('runtime'):
                runtimes.setdefault(row['unit_id'], {})[digest(row['runtime'])] = row['runtime']
        if any(len(values) > 1 for values in runtimes.values()):
            raise E2EError('RECOVERY_UNIT_RUNTIME_AMBIGUOUS')
        resumed = []
        for row in rows:
            if row["phase"] in TERMINAL:
                continue
            raw = db.execute("SELECT data FROM executions WHERE key=?", (row["key"],)).fetchone()
            data = json.loads(raw[0])
            # A dispatched attempt still belongs to its original executor.
            data.update(recovery_id=request["recovery_id"], collector_revision=target)
            if not row.get("dispatch_armed_at"):
                data["executor_revision"] = target
                if not data.get('runtime') and row['unit_id'] in runtimes:
                    data['runtime'] = next(iter(runtimes[row['unit_id']].values()))
            db.execute("UPDATE executions SET data=? WHERE key=?", (json.dumps(data), row["key"]))
            resumed.append(row["key"])
        receipt = {"schema": SCHEMA, "recovery_id": request["recovery_id"], "source_revision": request["source_revision"],
                   "target_revision": target, "manifest_sha256": request["manifest_sha256"],
                   "request_sha256": digest(request), "execution_keys": resumed, "registered_at": utc_now()}
        db.execute("INSERT INTO metadata VALUES (?,?)", (key, json.dumps(receipt)))
        db.execute("INSERT INTO events(at,kind,item_key,data) VALUES (?,?,NULL,?)",
                   (utc_now(), "EXECUTION_RECOVERY_REGISTERED", json.dumps(receipt)))
        return receipt
