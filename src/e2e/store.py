"""Transactional batch state and crash-safe ownership for execution and scoring."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import socket
import sqlite3
import uuid

from .common import E2EError, atomic_json, digest, read_json, utc_now


CONTROLLER_LEASE_SECONDS = 120


def _lease_times():
    now = datetime.now(timezone.utc)
    return {"heartbeat_at": now.isoformat(),
            "lease_expires_at": (now + timedelta(seconds=CONTROLLER_LEASE_SECONDS)).isoformat()}


def _lease_status(lease):
    if lease is None:
        return None
    status = "unknown"
    if lease.get("released_at"):
        status = "released"
    elif lease.get("lease_expires_at"):
        try:
            deadline = datetime.fromisoformat(lease["lease_expires_at"])
            status = "fresh" if deadline > datetime.now(timezone.utc) else "stale"
        except (TypeError, ValueError):
            status = "invalid"
    return {**lease, "lease_status": status}


def refresh_controller_heartbeat(batch_root: Path, owner: dict, name="execution"):
    path = batch_root / "control" / (name + "-owner.json")
    current = read_json(path)
    if current.get("instance_id") != owner["instance_id"] or current.get("released_at"):
        raise E2EError("CONTROLLER_HEARTBEAT_OWNER_MISMATCH")
    owner.update(_lease_times())
    atomic_json(path, owner)


@contextmanager
def controller_lock(batch_root: Path, name="execution"):
    directory = batch_root / "control"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (name + ".lock")
    with path.open("a+b") as stream:
        if stream.tell() == 0:
            stream.write(b"\0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise E2EError(f"CONTROLLER_ALREADY_RUNNING: {name}") from error
        owner = {"pid": os.getpid(), "host": socket.gethostname(), "instance_id": uuid.uuid4().hex,
                 "started_at": utc_now(), **_lease_times()}
        atomic_json(directory / (name + "-owner.json"), owner)
        try:
            yield owner
        finally:
            released_at = utc_now()
            atomic_json(directory / (name + "-owner.json"), {**owner, "released_at": released_at, "lease_expires_at": released_at})
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


class BatchStore:
    def __init__(self, root: Path):
        self.root = root
        self.path = root / "control/state.sqlite"

    @contextmanager
    def transaction(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self, plan: dict, items: list[dict]):
        with self.transaction() as db:
            db.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS executions (key TEXT PRIMARY KEY, unit_id TEXT NOT NULL, run_index INTEGER NOT NULL, task_id TEXT NOT NULL, ordinal INTEGER NOT NULL, phase TEXT NOT NULL, resource_held INTEGER NOT NULL DEFAULT 0, data TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS events (sequence INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, kind TEXT NOT NULL, item_key TEXT, data TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS scoring (key TEXT PRIMARY KEY REFERENCES executions(key), source_sha256 TEXT NOT NULL, phase TEXT NOT NULL, data TEXT NOT NULL)")
            existing = db.execute("SELECT value FROM metadata WHERE key='plan_sha256'").fetchone()
            if existing:
                if existing[0] != digest(plan):
                    raise E2EError("BATCH_PLAN_CONFLICT")
                return
            db.execute("INSERT INTO metadata VALUES ('schema',?)", ("wildclawbench.e2e-store/v1",))
            db.execute("INSERT INTO metadata VALUES ('plan_sha256',?)", (digest(plan),))
            for order, item in enumerate(items):
                db.execute("INSERT INTO executions VALUES (?,?,?,?,?,'PENDING',0,?)", (
                    item["key"], item["unit_id"], item["run_index"], item["task_id"], order, json.dumps(item)))

    def rows(self) -> list[dict]:
        with self.transaction() as db:
            return [self._row(row) for row in db.execute("SELECT * FROM executions ORDER BY ordinal")]

    @staticmethod
    def _row(row) -> dict:
        return {**json.loads(row["data"]), "phase": row["phase"], "resource_held": bool(row["resource_held"])}

    def get(self, key: str) -> dict:
        with self.transaction() as db:
            row = db.execute("SELECT * FROM executions WHERE key=?", (key,)).fetchone()
            if row is None:
                raise E2EError("EXECUTION_KEY_UNKNOWN")
            return self._row(row)

    def update(self, key: str, phase: str, *, resource_held: bool | None = None, **fields) -> dict:
        with self.transaction() as db:
            row = db.execute("SELECT * FROM executions WHERE key=?", (key,)).fetchone()
            if row is None:
                raise E2EError("EXECUTION_KEY_UNKNOWN")
            data = json.loads(row["data"])
            data.update(fields, updated_at=utc_now())
            held = row["resource_held"] if resource_held is None else int(resource_held)
            db.execute("UPDATE executions SET phase=?,resource_held=?,data=? WHERE key=?",
                       (phase, held, json.dumps(data), key))
            db.execute("INSERT INTO events(at,kind,item_key,data) VALUES (?,?,?,?)",
                       (utc_now(), phase, key, json.dumps(fields)))
            return {**data, "phase": phase, "resource_held": bool(held)}

    def publish_ready(self, key: str, ready: dict):
        with self.transaction() as db:
            existing = db.execute("SELECT source_sha256 FROM scoring WHERE key=?", (key,)).fetchone()
            source_sha = ready["backup_sha256"]
            if existing:
                if existing[0] != source_sha:
                    raise E2EError("SCORING_SOURCE_CONFLICT")
                return
            db.execute("INSERT INTO scoring VALUES (?,?,'READY',?)", (key, source_sha, json.dumps(ready)))
            db.execute("INSERT INTO events(at,kind,item_key,data) VALUES (?,?,?,?)",
                       (utc_now(), "SCORING_READY", key, json.dumps({"backup_sha256": source_sha})))

    def scoring_rows(self) -> list[dict]:
        with self.transaction() as db:
            return [{**json.loads(row["data"]), "key": row["key"], "phase": row["phase"]}
                    for row in db.execute("SELECT * FROM scoring ORDER BY rowid")]

    def pipeline_owner(self, owner: str):
        with self.transaction() as db:
            existing = db.execute("SELECT value FROM metadata WHERE key='pipeline_owner'").fetchone()
            if existing and existing[0] != owner:
                active = db.execute("SELECT COUNT(*) FROM scoring WHERE phase IN ('CLAIMED','RUNNING','NEEDS_ATTENTION')").fetchone()[0]
                lease = db.execute("SELECT value FROM metadata WHERE key='pipeline_owner_lease'").fetchone()
                current = _lease_status(json.loads(lease[0])) if lease else None
                if active or (current and current["lease_status"] != "stale"):
                    raise E2EError("PIPELINE_CONTROLLER_OWNER_CONFLICT")
            db.execute("INSERT OR REPLACE INTO metadata VALUES ('pipeline_owner',?)", (owner,))
            lease = {"owner": owner, **_lease_times()}
            db.execute("INSERT OR REPLACE INTO metadata VALUES ('pipeline_owner_lease',?)", (json.dumps(lease),))

    def check_claim_owner(self, key: str, claim_id: str, owner: str):
        with self.transaction() as db:
            row = db.execute("SELECT data FROM scoring WHERE key=?", (key,)).fetchone()
            data = json.loads(row[0]) if row else {}
            if data.get("claim_id") != claim_id or data.get("owner") != owner:
                raise E2EError("SCORING_CLAIM_OWNER_MISMATCH")

    def transfer_pipeline_owner(self, previous: str, owner: str, reason: str):
        if not reason.strip() or previous == owner:
            raise E2EError("PIPELINE_TAKEOVER_REASON_REQUIRED")
        with self.transaction() as db:
            existing = db.execute("SELECT value FROM metadata WHERE key='pipeline_owner'").fetchone()
            if not existing or existing[0] != previous:
                raise E2EError("PIPELINE_PREVIOUS_OWNER_MISMATCH")
            for row in db.execute("SELECT * FROM scoring WHERE phase IN ('CLAIMED','RUNNING','NEEDS_ATTENTION')").fetchall():
                data = json.loads(row["data"])
                if data.get("owner") != previous:
                    raise E2EError("PIPELINE_ACTIVE_OWNER_MISMATCH")
                data.setdefault("controller_history", []).append({"owner": previous, "transferred_at": utc_now(), "reason": reason})
                data.update(owner=owner, takeover_requires_reconciliation=bool(data.get("orchestration")))
                db.execute("UPDATE scoring SET data=? WHERE key=?", (json.dumps(data), row["key"]))
            db.execute("UPDATE metadata SET value=? WHERE key='pipeline_owner'", (owner,))
            lease = {"owner": owner, **_lease_times()}
            db.execute("INSERT OR REPLACE INTO metadata VALUES ('pipeline_owner_lease',?)", (json.dumps(lease),))
            db.execute("INSERT INTO events(at,kind,item_key,data) VALUES (?,?,NULL,?)",
                       (utc_now(), "PIPELINE_OWNER_TRANSFER", json.dumps({"previous": previous, "owner": owner, "reason": reason})))

    def claim_score(self, owner: str, slots: int, *, mode: str) -> dict | None:
        with self.transaction() as db:
            controller = db.execute("SELECT value FROM metadata WHERE key='pipeline_owner'").fetchone()
            if controller and controller[0] != owner:
                raise E2EError("PIPELINE_CONTROLLER_OWNER_CONFLICT")
            if mode == "batch" and db.execute("SELECT COUNT(*) FROM executions WHERE phase NOT IN ('COMPLETED','FAILED','CANCELLED')").fetchone()[0]:
                return None
            active = db.execute("SELECT COUNT(*) FROM scoring WHERE phase IN ('CLAIMED','RUNNING','NEEDS_ATTENTION')").fetchone()[0]
            if active >= slots:
                return None
            row = db.execute("SELECT * FROM scoring WHERE phase='READY' ORDER BY rowid LIMIT 1").fetchone()
            if row is None:
                return None
            data = json.loads(row["data"])
            data.update(owner=owner, claim_id=uuid.uuid4().hex, claimed_at=utc_now())
            db.execute("UPDATE scoring SET phase='CLAIMED',data=? WHERE key=?", (json.dumps(data), row["key"]))
            return {**data, "key": row["key"], "phase": "CLAIMED"}

    def score_update(self, key: str, claim_id: str, phase: str, **fields):
        if phase not in {"CLAIMED", "RUNNING", "SCORED", "FAILED", "NEEDS_ATTENTION"}:
            raise E2EError("SCORING_PHASE_INVALID")
        with self.transaction() as db:
            row = db.execute("SELECT * FROM scoring WHERE key=?", (key,)).fetchone()
            if row is None:
                raise E2EError("SCORING_KEY_UNKNOWN")
            data = json.loads(row["data"])
            if data.get("claim_id") != claim_id:
                raise E2EError("SCORING_CLAIM_MISMATCH")
            if row["phase"] == "SCORED" and phase != "SCORED":
                raise E2EError("SCORING_RESULT_ALREADY_RECORDED")
            data.update(fields, updated_at=utc_now())
            db.execute("UPDATE scoring SET phase=?,data=? WHERE key=?", (phase, json.dumps(data), key))

    def events(self, after: int = 0) -> list[dict]:
        with self.transaction() as db:
            return [{"sequence": r["sequence"], "at": r["at"], "type": r["kind"], "key": r["item_key"],
                     "details": json.loads(r["data"])} for r in db.execute("SELECT * FROM events WHERE sequence>? ORDER BY sequence", (after,))]

    def export_events(self):
        rows = self.events()
        target = self.root / "control/events.jsonl"
        temporary = target.with_name(".events-" + uuid.uuid4().hex + ".tmp")
        temporary.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
        temporary.replace(target)

    def summary(self) -> dict:
        rows = self.rows()
        counts = {}
        for row in rows:
            counts[row["phase"]] = counts.get(row["phase"], 0) + 1
        owner_path = self.root / "control/execution-owner.json"
        execution_owner = read_json(owner_path) if owner_path.exists() else None
        with self.transaction() as db:
            metadata = dict(db.execute("SELECT key,value FROM metadata WHERE key IN ('pipeline_owner','pipeline_owner_lease')"))
        pipeline_owner = json.loads(metadata["pipeline_owner_lease"]) if metadata.get("pipeline_owner_lease") else (
            {"owner": metadata["pipeline_owner"]} if metadata.get("pipeline_owner") else None)
        return {"schema": "wildclawbench.e2e-batch-summary/v1", "executions": rows,
                "phase_counts": counts, "resource_held": sum(row["resource_held"] for row in rows),
                "scoring": self.scoring_rows(), "observed_at": utc_now(),
                "controllers": {"execution": _lease_status(execution_owner), "pipeline": _lease_status(pipeline_owner)}}
