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
    source_view=source
    extra_locks=[]
    selected_source=getattr(args,'source_selection_root',None)
    if selected_source is not None:
        source_view=selected_source.resolve(strict=True)
        lineage_file=source_view/'selection-lineage.json'
        lineage=json.loads(lineage_file.read_text(encoding='utf-8'))
        if (lineage.get('kind') not in {'explicit-full-scope-native-context-correction/v1',
                                      'explicit-complete-scope-score-selection/v1',
                                      'explicit-full-scope-rescore-selection/v1'}
                or Path(lineage.get('source_orchestration','')).resolve()!=source
                or lineage.get('submission_sha256')!=digest(source_view/'submission.json')
                or lineage.get('old_files_unchanged') is not True or lineage.get('scope_shrunk') is not False):
            raise ValueError('VALIDATED_SOURCE_SELECTION_REQUIRED')
        for lock in lineage.get('source_locks',[]):
            if digest(Path(lock['path']))!=lock['sha256']:raise ValueError('SOURCE_SELECTION_LINEAGE_DRIFT')
        extra_locks=copy.deepcopy(lineage.get('source_locks',[]))+[{'path':str(f),'sha256':digest(f)} for f in [lineage_file,source_view/'submission.json']]
    partial = json.loads((source_view / "submission.json").read_text(encoding="utf-8"))
    frozen._validate_contract(partial,expected_schema_id=frozen.SUBMISSION_SCHEMA)
    if (partial['scope']!={'batch_id':state['identity']['batch_id'],'unit_id':state['identity']['unit_id']}
            or partial['dataset']!={k:state['identity']['dataset'][k] for k in ['id','digest']}):
        raise ValueError('SOURCE_SELECTION_IDENTITY_MISMATCH')
    repair=getattr(args,'allow_scoring_infrastructure_repair',False)
    reason=getattr(args,'infrastructure_repair_reason',None)
    if repair and (not isinstance(reason,str) or len(reason.strip())<8):
        raise ValueError('EXPLICIT_INFRASTRUCTURE_REPAIR_REASON_REQUIRED')
    if (not set(partial['task_ids'])<=set(expected)
            or (not repair and not set(partial["task_ids"]) < set(expected))):
        raise ValueError("STRICT_PARTIAL_SCOPE_REQUIRED")
    skill = frozen._score_skill_lock(args.score_skill_dir, python_runtime=state["score_skill"].get("python"))
    rows = {r["task_id"]: copy.deepcopy(r) for r in partial["tasks"]}
    roots = {r["task_id"]: source_view.joinpath(*PurePosixPath(r["score_path"]).parts).parent
             for r in partial["tasks"] if r["score_path"] is not None}
    extra_records = {}
    locks = [{"path": str(p), "sha256": digest(p)} for p in [unit_file, source / "orchestration-state.json", source / "submission.json"]]+extra_locks
    seen=set();repaired=[];state_tasks={t['task_id']:t for t in state['tasks']}
    for selector in args.additional_attempt:
        task, value = selector.split("=", 1)
        if task not in expected or task in seen or (task in rows and not repair):
            raise ValueError("EXPLICIT_UNIQUE_MISSING_TASK_REQUIRED")
        seen.add(task)
        root = Path(value).resolve(strict=True)
        frozen._run_score_command(skill, ["verify-score", "--attempt-root", str(root), "--archived"])
        score = json.loads((root / "score.json").read_text(encoding="utf-8"))
        attempt = json.loads((root / "attempt-manifest.json").read_text(encoding="utf-8"))
        record = root / attempt["paths"]["execution_record"]
        execution = json.loads(record.read_text(encoding="utf-8"))
        identity = score["identity"]
        previous=copy.deepcopy(rows.get(task))
        if previous is not None:
            if previous['score_status']=='valid':raise ValueError('VALID_SOURCE_SCORE_REQUIRES_RESCORE_SELECTION')
            original=state_tasks.get(task)
            if original is None:raise ValueError('INFRASTRUCTURE_SOURCE_TASK_MISSING')
            if previous['score_status']=='evaluation_error':
                source_score=roots[task]/'score.json'
                frozen._run_score_command(skill,['verify-score','--attempt-root',str(source_score.parent),'--archived'])
                lineage=attempt.get('lineage',{})
                if (lineage.get('kind')!='rescore' or lineage.get('source_score_sha256')!=previous['score_sha256']
                        or lineage.get('source_scoring_attempt_id')!=previous['scoring_attempt_id']):
                    raise ValueError('INFRASTRUCTURE_RESCORE_LINEAGE_REQUIRED')
            elif (previous['score_status']!='unscored'
                    or original.get('scoring_error',{}).get('kind') not in {'dataset-rule-evaluation-error/v1',
                        'evaluator-public-context-setup-error/v1','office001-declared-numeric-review/v1'}):
                raise ValueError('DECLARED_RULE_INFRASTRUCTURE_FAILURE_REQUIRED')
            if (score['execution']['attempt_id']!=previous['execution_attempt_id']
                    or execution['candidate']['frozen_sha256']!=previous['candidate_sha256']):
                raise ValueError('INFRASTRUCTURE_FROZEN_CANDIDATE_MISMATCH')
        if (identity["task_id"] != task or identity["batch_id"] != partial["scope"]["batch_id"]
                or identity["unit_id"] != partial["scope"]["unit_id"] or score["dataset"] != partial["dataset"]
                or attempt["source"]["scoring_package_sha256"] != state["sources"]["scoring_package_sha256"]
                or (score["judge"].get("protocol") != "not-required"
                    and any(score["judge"].get(k) != state["judge"].get(k) for k in ["protocol", "model", "reasoning_effort"]))
                or digest(record) != score["execution"]["record_sha256"]):
            raise ValueError("ADDITIONAL_SCORE_IDENTITY_OR_INPUT_MISMATCH")
        originals = ([source/state_tasks[task]['execution_record_path']] if task in state_tasks
                     else list((unit / "evidence/tasks" / task).glob("*/execution-record.json")))
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
        if previous is not None:
            repaired.append({'task_id':task,'previous':previous,'replacement_score_sha256':digest(root/'score.json'),
                             'replacement_attempt':str(root),'reason':reason})
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
    shutil.copytree(source_view / "execution-records", stage / "execution-records")
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
        frozen._run_score_command(skill,['verify-score','--attempt-root',str(roots[task]),'--archived'])
        source_score=json.loads((roots[task]/'score.json').read_text(encoding='utf-8'))
        if (source_score['identity']!={'batch_id':partial['scope']['batch_id'],'unit_id':partial['scope']['unit_id'],
                                     'task_id':task,'attempt_id':row['scoring_attempt_id']}
                or source_score['dataset']!=partial['dataset']
                or source_score['execution']['attempt_id']!=row['execution_attempt_id']):
            raise ValueError('SELECTED_SOURCE_SCORE_IDENTITY_MISMATCH')
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
    if selected_source is not None:lineage['source_selection']=str(source_view)
    if repair:
        lineage.update(infrastructure_correction_profile='explicit-scoring-infrastructure-repair/v1',
                       infrastructure_repair_reason=reason,selected_infrastructure_repairs=repaired)
    for lock in locks:
        if digest(Path(lock["path"])) != lock["sha256"]:
            raise ValueError("SOURCE_CHANGED_DURING_COMPOSITION")
    (stage / "selection-lineage.json").write_text(json.dumps(lineage, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    stage.rename(output)
    return {"status": "PASS", "output_root": str(output), "task_count": len(expected), "scope_shrunk": False}
