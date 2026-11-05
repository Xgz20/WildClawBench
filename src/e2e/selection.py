"""Compose locked single-task submissions in the frozen unit/run order."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

from .common import E2EError, atomic_json, digest, file_sha256, inside, load_script, read_json, utc_now
from .engine import load_batch, verify_ready
from .store import BatchStore, controller_lock


def _locked_submission(batch, item, claim, manifest):
    receipt = claim.get("submission")
    if not receipt:
        raise E2EError("SCORING_SUBMISSION_NOT_RECORDED")
    path = Path(receipt["path"]).resolve()
    if not path.is_relative_to(batch.resolve()) or file_sha256(path) != receipt["sha256"]:
        raise E2EError("SELECTED_SUBMISSION_DRIFT")
    document = read_json(path)
    ready = verify_ready(batch, item, manifest)
    if document.get("task_ids") != [item["task_id"]] or receipt["identity"] != ready["identity"]:
        raise E2EError("SELECTED_SUBMISSION_IDENTITY_INVALID")
    return path, document


def _general_submission(batch, stage, unit, items, claims, manifest):
    task_defs = {task["task_id"]: task for task in manifest["tasks"]}
    dataset = {key: task_defs[unit["task_ids"][0]]["dataset"][key] for key in ("id", "digest")}
    rows = []
    for item in items:
        claim = claims.get(item["key"], {})
        if claim.get("phase") == "SCORED":
            path, child = _locked_submission(batch, item, claim, manifest)
            expected_scope = {"batch_id": batch.name + f"-r{item['run_index']:04d}", "unit_id": unit["unit_id"]}
            if child.get("scope") != expected_scope or child.get("dataset") != dataset:
                raise E2EError("SELECTED_GENERAL_SUBMISSION_SCOPE_INVALID")
            row = dict(child["tasks"][0])
            if row["execution_attempt_id"] != item["attempt_id"]:
                raise E2EError("SELECTED_EXECUTION_ATTEMPT_INVALID")
            if row.get("score_path"):
                skills = inside(batch, manifest["compatibility"]["general"]["installed_skills"])
                copier = load_script(skills / "orchestrate-general-e2e/scripts/compose_rescore_selection.py", "sandbox_copy_scoring_attempt")
                verifier = skills / "score-general-e2e/scripts/score_general_e2e.py"
                source = inside(path.parent, row["score_path"])
                if file_sha256(source) != row["score_sha256"]:
                    raise E2EError("SELECTED_SCORE_DRIFT")
                relative = f"attempts/{item['task_id']}/{row['scoring_attempt_id']}"
                target = inside(stage, relative)
                copier.copy_attempt(source.parent, target)
                result = subprocess.run([sys.executable, "-X", "utf8", str(verifier), "verify-score",
                                         "--attempt-root", str(target), "--archived"],
                                        capture_output=True, text=True, encoding="utf-8")
                if result.returncode != 0:
                    raise E2EError("COMPOSED_SCORE_VERIFICATION_FAILED: " + (result.stderr or result.stdout)[-2000:])
                if file_sha256(target / "score.json") != row["score_sha256"]:
                    raise E2EError("COMPOSED_SCORE_COPY_DRIFT")
                row["score_path"] = relative + "/score.json"
        else:
            status = "cancelled" if item["phase"] == "CANCELLED" else "infrastructure_error"
            if item.get("report", {}).get("status") == "task_timeout":
                status = "timeout"
            row = {"task_id": item["task_id"], "execution_attempt_id": item["attempt_id"],
                   "execution_status": "completed" if item["phase"] == "COMPLETED" else status,
                   "scoring_attempt_id": None, "judge_protocol": None, "score_status": "unscored",
                   "score_path": None, "score_sha256": None, "candidate_sha256": None, "evidence_sha256": None}
        rows.append(row)
    document = {"schema_id": "urn:wildclawbench:schema:general-e2e:submission:v1", "schema_version": 1,
                "scope": {"batch_id": batch.name + f"-r{items[0]['run_index']:04d}", "unit_id": unit["unit_id"]},
                "dataset": dataset, "created_at": utc_now(), "task_count": len(rows),
                "task_ids": unit["task_ids"], "tasks": rows,
                "integrity": {"scope_matches": True, "identities_match": True, "hashes_verified": True, "valid": True}}
    from eval_general_e2e.contracts.validator import validate_contract
    validate_contract(document)
    return document


def _web_submission(batch, items, claims, manifest):
    if any(claims.get(item["key"], {}).get("phase") != "SCORED" for item in items):
        return None
    children = [_locked_submission(batch, item, claims[item["key"]], manifest)[1] for item in items]
    first = children[0]
    if any(any(child.get(key) != first.get(key) for key in ("schema_version", "batch_id", "unit", "metric_profile"))
           for child in children):
        raise E2EError("SELECTED_WEB_SUBMISSION_SCOPE_INVALID")
    return {**first, "created_at": utc_now(), "task_ids": [item["task_id"] for item in items],
            "tasks": [child["tasks"][0] for child in children],
            "candidate_artifacts": [row for child in children for row in child.get("candidate_artifacts", [])]}


def compose_results(batch: Path) -> dict:
    manifest = load_batch(batch)
    store = BatchStore(batch)
    with controller_lock(batch, "scoring-queue"), controller_lock(batch, "selection"):
        items = store.rows()
        claims = {row["key"]: row for row in store.scoring_rows()}
        if any(item["phase"] not in {"COMPLETED", "FAILED", "CANCELLED"} or item["resource_held"] for item in items):
            raise E2EError("EXECUTION_SCOPE_NOT_TERMINAL")
        if any(row["phase"] not in {"SCORED", "FAILED"} for row in claims.values()):
            raise E2EError("SCORING_SCOPE_NOT_TERMINAL")
        selected = []
        locks = []
        for item in items:
            claim = claims.get(item["key"], {})
            row = {"execution_key": item["key"], "task_id": item["task_id"], "unit_id": item["unit_id"],
                   "run_index": item["run_index"], "execution_attempt_id": item["attempt_id"],
                   "execution_phase": item["phase"], "score_status": "unscored", "error": item.get("error") or claim.get("error")}
            if claim.get("phase") in {"SCORED", "FAILED"} and claim.get("submission"):
                path, document = _locked_submission(batch, item, claim, manifest)
                row.update(submission_path=path.relative_to(batch).as_posix(), submission_sha256=file_sha256(path),
                           claim_id=claim["claim_id"], score_status=(document["tasks"][0].get("score_status", "scored")
                                                                    if claim["phase"] == "SCORED" else "unscored"))
                locks.append({"path": row["submission_path"], "sha256": row["submission_sha256"]})
            selected.append(row)
        source_sha = digest({"parent": digest(manifest), "selected": selected})
        output = batch / "selected-results.json"
        if output.exists():
            existing = read_json(output)
            if existing.get("source_sha256") != source_sha:
                raise E2EError("COMPOSED_SELECTION_SOURCE_CHANGED")
            for artifact in existing["artifacts"]:
                if file_sha256(inside(batch, artifact["path"])) != artifact["sha256"]:
                    raise E2EError("COMPOSED_SUBMISSION_DRIFT")
            return existing
        artifacts = []
        for unit in manifest["units"]:
            for run_index in range(1, manifest["plan"]["runs"] + 1):
                scoped = [item for item in items if item["unit_id"] == unit["unit_id"] and item["run_index"] == run_index]
                if [item["task_id"] for item in scoped] != unit["task_ids"]:
                    raise E2EError("COMPOSED_FULL_SCOPE_REQUIRED")
                destination = batch / "units" / unit["unit_id"] / "runs" / f"run-{run_index:04d}" / "submission"
                stage = destination.with_name(".submission-" + uuid.uuid4().hex)
                stage.mkdir(parents=True)
                try:
                    document = (_general_submission(batch, stage, unit, scoped, claims, manifest) if unit["scene"] == "general"
                                else _web_submission(batch, scoped, claims, manifest))
                    scoped_rows = [row for row in selected if row["unit_id"] == unit["unit_id"] and row["run_index"] == run_index]
                    atomic_json(stage / "selected-results.json", {"source_sha256": source_sha, "tasks": scoped_rows})
                    if document is not None:
                        atomic_json(stage / "submission.json", document)
                    if destination.exists():
                        previous = read_json(destination / "selected-results.json")
                        if previous != read_json(stage / "selected-results.json"):
                            raise E2EError("COMPOSED_SCOPE_CONFLICT")
                        if document is not None:
                            previous_submission = read_json(destination / "submission.json")
                            comparable = lambda value: {key: data for key, data in value.items() if key != "created_at"}
                            if comparable(previous_submission) != comparable(document):
                                raise E2EError("COMPOSED_SUBMISSION_DRIFT")
                            if unit["scene"] == "general":
                                for task in document["tasks"]:
                                    if task.get("score_path") and file_sha256(inside(destination, task["score_path"])) != task["score_sha256"]:
                                        raise E2EError("COMPOSED_SCORE_COPY_DRIFT")
                    else:
                        stage.rename(destination)
                    for name in ("selected-results.json", "submission.json"):
                        path = destination / name
                        if path.exists():
                            artifacts.append({"path": path.relative_to(batch).as_posix(), "sha256": file_sha256(path)})
                finally:
                    if stage.exists():
                        shutil.rmtree(stage)
        for lock in locks:
            if file_sha256(inside(batch, lock["path"])) != lock["sha256"]:
                raise E2EError("SELECTED_SOURCE_CHANGED_DURING_COMPOSITION")
        result = {"schema": "wildclawbench.sandbox-selected-results/v1", "parent_batch_id": batch.name,
                  "parent_batch_sha256": digest(manifest), "source_sha256": source_sha, "created_at": utc_now(),
                  "task_count": len(selected), "tasks": selected, "status_counts": dict(Counter(row["score_status"] for row in selected)),
                  "artifacts": artifacts}
        atomic_json(output, result, create=True)
        return result
