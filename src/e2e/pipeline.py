"""Persistent handoff queue driving the existing Desktop scoring orchestrators."""
from __future__ import annotations

import json
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import time

from .common import E2EError, file_sha256, identifier, inside, read_json, utc_now, digest
from .artifacts import inventory
from .engine import load_batch, verify_ready
from .handoff import prepare_scoring_context
from .store import BatchStore, controller_lock


def _claim(store: BatchStore, key: str, claim_id: str):
    rows = [row for row in store.scoring_rows() if row["key"] == key and row.get("claim_id") == claim_id]
    if len(rows) != 1:
        raise E2EError("SCORING_CLAIM_MISMATCH")
    return rows[0]


def _port(workspace: Path, owner: str) -> int:
    path = workspace / "control/resources.sqlite"
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path, timeout=30) as db:
        db.execute("CREATE TABLE IF NOT EXISTS ports (owner TEXT PRIMARY KEY, port INTEGER UNIQUE NOT NULL)")
        db.execute("BEGIN IMMEDIATE")
        found = db.execute("SELECT port FROM ports WHERE owner=?", (owner,)).fetchone()
        if found:
            return found[0]
        for _ in range(100):
            with socket.socket() as candidate:
                candidate.bind(("127.0.0.1", 0))
                port = candidate.getsockname()[1]
            if db.execute("SELECT 1 FROM ports WHERE port=?", (port,)).fetchone():
                continue
            db.execute("INSERT INTO ports VALUES (?,?)", (owner, port))
            return port
    raise E2EError("SCORING_PORT_UNAVAILABLE")


def _run(argv: list[str]) -> dict:
    result = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        raise E2EError("SCORING_ORCHESTRATOR_ERROR: " + (result.stderr or result.stdout)[-4000:])
    try:
        return json.loads(result.stdout)
    except ValueError as error:
        raise E2EError("SCORING_ORCHESTRATOR_OUTPUT_INVALID") from error


def init_orchestration(batch: Path, key: str, claim_id: str, *, score_python: Path | None = None,
                       score_skill_dir: Path | None = None) -> dict:
    manifest = load_batch(batch)
    store = BatchStore(batch)
    claim = _claim(store, key, claim_id)
    context = prepare_scoring_context(batch, key, claim_id)
    root = Path(context["context_root"])
    skills = Path(context["installed_skills"])
    score_binding = None
    if score_skill_dir is not None:
        source = score_skill_dir.expanduser().resolve(strict=True)
        spec = read_json(source / 'skill-metadata.json')
        if context['scene'] != 'general' or spec.get('name') != 'score-general-e2e' or spec.get('contract_version') != 'general-e2e-contract-v1':
            raise E2EError('SUPPLEMENTAL_SCORE_SKILL_INCOMPATIBLE')
        score_binding = {'root': str(source), 'version': spec['version'], 'inventory_sha256': digest(inventory(source))}
    if claim.get("orchestration") and Path(claim["orchestration"]["state_file"]).exists():
        if score_binding is not None and claim['orchestration'].get('supplemental_score_skill') != score_binding:
            raise E2EError('SCORING_SKILL_ALREADY_FROZEN')
        if score_python is not None:
            state = read_json(Path(claim["orchestration"]["state_file"]))
            if state.get('score_skill', {}).get('python', {}).get('executable') != str(score_python.expanduser().absolute()):
                raise E2EError('SCORING_PYTHON_ALREADY_FROZEN')
        return poll_orchestration(batch, key, claim_id)
    with controller_lock(batch, "scoring-init"):
        item = store.get(key)
        if context["scene"] == "general":
            script = skills / "orchestrate-general-e2e/scripts/orchestrate_general_e2e.py"
            orchestration = root / "orchestrations" / ("pipeline-" + claim_id)
            argv = [str(score_python.expanduser().absolute()) if score_python else sys.executable, "-X", "utf8", str(script), "init", "--unit-root", str(root / context["unit_root"]),
                    "--scoring-package", str(root / context["scoring_package"]), "--report-config", str(root / context["report_config"]),
                    "--score-skill-dir", score_binding['root'] if score_binding else str(skills / "score-general-e2e"), "--output-root", str(orchestration.parent),
                    "--orchestration-id", orchestration.name, "--score-slots", "1", "--task-id", item["task_id"]]
            state_file = orchestration / "orchestration-state.json"
        else:
            if score_python is not None:
                raise E2EError('SCORING_PYTHON_REQUIRES_GENERAL_SCENE')
            script = skills / "orchestrate-web-e2e/scripts/scoring-control.mjs"
            orchestration = root / context["unit_root"]
            port = _port(batch.parent.parent, batch.name + "/" + claim_id)
            argv = ["node", str(script), "init", "--package-root", str(orchestration), "--task-id", item["task_id"],
                    "--score-skill-dir", str(skills / "score-web-e2e"), "--score-slots", "1", "--score-port-base", str(port)]
            state_file = orchestration / "score/.orchestrate-web-e2e/scoring-automation-state.json"
        # Publish the exact intended root before init. A crash resumes the same
        # orchestrator instead of creating another Judge attempt.
        intent = {"scene": context["scene"], "root": str(orchestration), "script": str(script),
                  "state_file": str(state_file), "intent_at": utc_now()}
        if score_binding is not None:
            intent['supplemental_score_skill'] = score_binding
        store.score_update(key, claim_id, "CLAIMED", orchestration=intent)
        if not state_file.exists():
            result = _run(argv)
        else:
            result = poll_orchestration(batch, key, claim_id)
        store.score_update(key, claim_id, "RUNNING", orchestration={**intent, "initialized_at": utc_now()})
        return result


def _reader_script(store, key, claim_id, metadata, directory=None, reason=None):
    registered = metadata.get('supplemental_reader')
    if directory is not None:
        root = directory.expanduser().resolve(strict=True)
        spec = read_json(root / 'skill-metadata.json')
        script = root / 'scripts/orchestrate_general_e2e.py'
        if spec.get('name') != 'orchestrate-general-e2e' or not script.is_file() or script.is_symlink():
            raise E2EError('ORCHESTRATOR_READER_INVALID')
        binding = {'root': str(root), 'script': str(script), 'inventory_sha256': digest(inventory(root))}
        if registered and any(registered[k] != v for k, v in binding.items()):
            raise E2EError('ORCHESTRATOR_READER_CONFLICT')
        if not registered:
            if not reason or not reason.strip():
                raise E2EError('ORCHESTRATOR_READER_REASON_REQUIRED')
            registered = {**binding, 'reason': reason, 'registered_at': utc_now()}
            phase = _claim(store, key, claim_id)['phase']
            store.score_update(key, claim_id, phase, orchestration={**metadata, 'supplemental_reader': registered})
    if registered:
        if digest(inventory(Path(registered['root']))) != registered['inventory_sha256']:
            raise E2EError('ORCHESTRATOR_READER_DRIFT')
        return registered['script']
    return metadata['script']


def poll_orchestration(batch: Path, key: str, claim_id: str, *, reader_dir=None, reason=None) -> dict:
    store = BatchStore(batch)
    claim = _claim(store, key, claim_id)
    metadata = claim.get("orchestration")
    if not metadata:
        raise E2EError("SCORING_ORCHESTRATION_NOT_INITIALIZED")
    if metadata["scene"] == "general":
        script = _reader_script(store, key, claim_id, metadata, reader_dir, reason)
        argv = [sys.executable, "-X", "utf8", script, "status", "--orchestration-root", metadata["root"]]
    else:
        if reader_dir is not None:
            raise E2EError('SUPPLEMENTAL_ORCHESTRATOR_REQUIRES_GENERAL_SCENE')
        argv = ["node", metadata["script"], "status", "--package-root", metadata["root"]]
    return _run(argv)


def record_submission(batch: Path, key: str, claim_id: str, *, reader_dir=None, reason=None) -> dict:
    manifest = load_batch(batch)
    store = BatchStore(batch)
    claim = _claim(store, key, claim_id)
    metadata = claim.get("orchestration")
    if not metadata:
        raise E2EError("SCORING_ORCHESTRATION_NOT_INITIALIZED")
    item = store.get(key)
    ready = verify_ready(batch, item, manifest)
    if metadata["scene"] == "general":
        script = _reader_script(store, key, claim_id, metadata, reader_dir, reason)
        argv = [sys.executable, "-X", "utf8", script, "build-submission", "--orchestration-root", metadata["root"]]
    else:
        if reader_dir is not None:
            raise E2EError('SUPPLEMENTAL_ORCHESTRATOR_REQUIRES_GENERAL_SCENE')
        skills = Path(claim["context"]["installed_skills"])
        argv = ["node", metadata["script"], "build-submission", "--package-root", metadata["root"],
                "--score-skill-dir", str(skills / "score-web-e2e")]
    _run(argv)
    path = Path(metadata["root"]) / "submission.json"
    before = file_sha256(path)
    submission = read_json(path)
    if submission.get("task_ids") != [item["task_id"]]:
        raise E2EError("SINGLE_TASK_SUBMISSION_SCOPE_MISMATCH")
    if metadata["scene"] == "general":
        if submission.get("scope") != {"batch_id": ready["identity"]["batch_id"], "unit_id": item["unit_id"]}:
            raise E2EError("SUBMISSION_IDENTITY_MISMATCH")
        row = submission["tasks"][0]
        if row["execution_attempt_id"] != item["attempt_id"]:
            raise E2EError("SUBMISSION_EXECUTION_ATTEMPT_MISMATCH")
        score_path = inside(Path(metadata["root"]), row["score_path"]) if row.get("score_path") else None
        if score_path and file_sha256(score_path) != row["score_sha256"]:
            raise E2EError("SUBMISSION_SCORE_DRIFT")
    elif submission.get("batch_id") != ready["identity"]["batch_id"]:
        raise E2EError("SUBMISSION_IDENTITY_MISMATCH")
    elif (submission.get("unit", {}).get("model_id") != ready["actual_model"]
          or submission.get("unit", {}).get("harness_id") != "astronstudio"):
        raise E2EError("SUBMISSION_MODEL_HARNESS_MISMATCH")
    if file_sha256(path) != before:
        raise E2EError("SUBMISSION_CHANGED_DURING_ADMISSION")
    receipt = {"path": str(path), "sha256": before, "recorded_at": utc_now(), "identity": ready["identity"]}
    scoring_error = None
    if metadata["scene"] == "web":
        evaluation = submission["tasks"][0].get("evaluation", {})
        if (evaluation.get("status") == "evaluation_error"
                or evaluation.get("aesthetic", {}).get("status") == "evaluation_error"):
            scoring_error = {"code": "SCORING_INFRASTRUCTURE_ERROR", "evaluation_status": evaluation.get("status"),
                             "aesthetic_status": evaluation.get("aesthetic", {}).get("status"),
                             "message": evaluation.get("error")}
            receipt["score_status"] = "unscored"
    # An audit submission may legitimately contain evaluation_error. Preserve
    # it and release the slot without admitting it as a valid scored result.
    store.score_update(key, claim_id, "FAILED" if scoring_error else "SCORED",
                       submission=receipt, error=scoring_error)
    resources = batch.parent.parent / "control/resources.sqlite"
    if resources.exists() and metadata["scene"] == "web":
        with sqlite3.connect(resources, timeout=30) as db:
            db.execute("DELETE FROM ports WHERE owner=?", (batch.name + "/" + claim_id,))
    return receipt


def next_actions(batch: Path, *, owner: str, claim_ready: bool = True, after: int = 0, wait_seconds: float = 0) -> dict:
    identifier(owner, "controller_owner")
    manifest = load_batch(batch)
    store = BatchStore(batch)
    store.pipeline_owner(owner)
    deadline = time.monotonic() + min(max(wait_seconds, 0), 30)
    while True:
        if claim_ready:
            with controller_lock(batch, "scoring-queue"):
                while True:
                    claim = store.claim_score(owner, manifest["plan"]["scoring_concurrency"], mode=manifest["plan"]["scoring_mode"])
                    if claim is None:
                        break
        actions = []
        for row in store.scoring_rows():
            if row.get("owner") != owner or row["phase"] not in {"CLAIMED", "RUNNING"}:
                continue
            common = {"execution_key": row["key"], "claim_id": row["claim_id"]}
            if not row.get("context"):
                actions.append({"action": "PREPARE_SCORING_CONTEXT", **common})
            elif not row.get("orchestration"):
                actions.append({"action": "INIT_EXISTING_ORCHESTRATOR", **common, "context": row["context"]})
            else:
                actions.append({"action": "FOLLOW_EXISTING_ORCHESTRATOR", **common,
                                "orchestration": row["orchestration"], "context": row["context"],
                                "takeover_requires_thread_reconciliation": row.get("takeover_requires_reconciliation", False)})
        events = store.events(after)
        execution_terminal = all(row["phase"] in {"COMPLETED", "FAILED", "CANCELLED"} and not row["resource_held"] for row in store.rows())
        scoring_terminal = all(row["phase"] in {"SCORED", "FAILED"} for row in store.scoring_rows())
        if execution_terminal and scoring_terminal and not (batch / "selected-results.json").exists():
            actions.append({"action": "COMPOSE_SELECTED_RESULTS"})
        if actions or events or time.monotonic() >= deadline:
            return {"schema": "wildclawbench.e2e-pipeline-actions/v1", "batch_id": batch.name,
                    "owner": owner, "recommended_actions": actions, "events": events,
                    "cursor": events[-1]["sequence"] if events else after, "summary": store.summary()}
        time.sleep(0.5)
