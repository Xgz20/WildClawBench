"""Join a locked partial submission and explicit validated scores; never judge or pick best."""
from __future__ import annotations

import copy
import datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import uuid

from compose_rescore_selection import copy_attempt


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compose(args, *, frozen):
    source = args.source_orchestration_root.resolve(strict=True)
    state = frozen._verify_state(source)
    if not state.get("submission"):
        raise ValueError("LOCKED_PARTIAL_SUBMISSION_REQUIRED")
    unit = args.unit_root.resolve(strict=True)
    unit_file = unit / "manifest.json"
    manifest = json.loads(unit_file.read_text(encoding="utf-8"))
    if digest(unit_file) != state["sources"]["unit_manifest_sha256"]:
        raise ValueError("UNIT_MANIFEST_MISMATCH")
    expected = list(manifest["task_ids"])
    partial = json.loads((source / "submission.json").read_text(encoding="utf-8"))
    if not set(partial["task_ids"]) < set(expected):
        raise ValueError("STRICT_PARTIAL_SCOPE_REQUIRED")
    skill = frozen._score_skill_lock(args.score_skill_dir, python_runtime=state["score_skill"].get("python"))
    rows = {r["task_id"]: copy.deepcopy(r) for r in partial["tasks"]}
    roots = {r["task_id"]: source.joinpath(*PurePosixPath(r["score_path"]).parts).parent
             for r in partial["tasks"] if r["score_path"] is not None}
    extra_records = {}
    locks = [{"path": str(p), "sha256": digest(p)} for p in [unit_file, source / "orchestration-state.json", source / "submission.json"]]
    for selector in args.additional_attempt:
        task, value = selector.split("=", 1)
        if task not in expected or task in rows:
            raise ValueError("EXPLICIT_UNIQUE_MISSING_TASK_REQUIRED")
        root = Path(value).resolve(strict=True)
        frozen._run_score_command(skill, ["verify-score", "--attempt-root", str(root), "--archived"])
        score = json.loads((root / "score.json").read_text(encoding="utf-8"))
        attempt = json.loads((root / "attempt-manifest.json").read_text(encoding="utf-8"))
        record = root / attempt["paths"]["execution_record"]
        execution = json.loads(record.read_text(encoding="utf-8"))
        identity = score["identity"]
        if (identity["task_id"] != task or identity["batch_id"] != partial["scope"]["batch_id"]
                or identity["unit_id"] != partial["scope"]["unit_id"] or score["dataset"] != partial["dataset"]
                or attempt["source"]["scoring_package_sha256"] != state["sources"]["scoring_package_sha256"]
                or (score["judge"].get("protocol") != "not-required"
                    and any(score["judge"].get(k) != state["judge"].get(k) for k in ["protocol", "model", "reasoning_effort"]))
                or digest(record) != score["execution"]["record_sha256"]):
            raise ValueError("ADDITIONAL_SCORE_IDENTITY_OR_INPUT_MISMATCH")
        originals = list((unit / "evidence/tasks" / task).glob("*/execution-record.json"))
        if len(originals) != 1 or digest(originals[0]) != digest(record):
            raise ValueError("FROZEN_EXECUTION_RECORD_CHANGED")
        relative = PurePosixPath("attempts") / (identity["batch_id"] + "__" + identity["unit_id"]) / task / identity["attempt_id"] / "score.json"
        catalog = root / "semantic/evidence-catalog.json"
        rows[task] = {"task_id": task, "execution_attempt_id": score["execution"]["attempt_id"],
                      "execution_status": score["execution"]["business_status"], "scoring_attempt_id": identity["attempt_id"],
                      "judge_protocol": score["judge"]["protocol"],
                      "score_status": "valid" if score["result"]["valid"] else "evaluation_error",
                      "score_path": relative.as_posix(), "score_sha256": digest(root / "score.json"),
                      "candidate_sha256": execution["candidate"]["frozen_sha256"],
                      "evidence_sha256": digest(catalog) if catalog.exists() else None}
        roots[task] = root
        extra_records[task] = record
        for p in [root / "attempt-manifest.json", root / "score.json"]:
            locks.append({"path": str(p), "sha256": digest(p)})
    if set(rows) != set(expected):
        raise ValueError("COMPLETE_FROZEN_SCOPE_REQUIRED")
    output = args.output_root.resolve()
    if output.exists():
        raise ValueError("OUTPUT_EXISTS")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = output.parent / ("." + output.name + ".staging-" + uuid.uuid4().hex)
    stage.mkdir()
    shutil.copytree(source / "execution-records", stage / "execution-records")
    for task, path in extra_records.items():
        shutil.copy2(path, stage / "execution-records" / (task + ".json"))
    for task in expected:
        row = rows[task]
        if row["score_path"] is None:
            continue
        relative = PurePosixPath(row["score_path"])
        if relative.is_absolute() or ".." in relative.parts or relative.parts[0] != "attempts":
            raise ValueError("UNSAFE_SCORE_PATH")
        target = stage.joinpath(*relative.parts).parent
        target.parent.mkdir(parents=True, exist_ok=True)
        copy_attempt(roots[task], target)
        frozen._run_score_command(skill, ["verify-score", "--attempt-root", str(target), "--archived"])
        if digest(target / "score.json") != row["score_sha256"]:
            raise ValueError("COPIED_SCORE_SHA_MISMATCH")
    document = copy.deepcopy(partial)
    document.update(created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    task_count=len(expected), task_ids=expected, tasks=[rows[t] for t in expected])
    frozen._validate_contract(document, expected_schema_id=frozen.SUBMISSION_SCHEMA)
    (stage / "submission.json").write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lineage = {"kind": "explicit-complete-scope-score-selection/v1", "source_orchestration": str(source),
               "additional_attempts": args.additional_attempt, "task_count": len(expected), "source_locks": locks,
               "old_files_unchanged": True, "semantic_judging_performed": False, "scope_shrunk": False,
               "submission_sha256": digest(stage / "submission.json")}
    for lock in locks:
        if digest(Path(lock["path"])) != lock["sha256"]:
            raise ValueError("SOURCE_CHANGED_DURING_COMPOSITION")
    (stage / "selection-lineage.json").write_text(json.dumps(lineage, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    stage.rename(output)
    return {"status": "PASS", "output_root": str(output), "task_count": len(expected), "scope_shrunk": False}
