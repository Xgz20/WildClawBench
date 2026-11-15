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


def validate_valid_rescore(previous, original_manifest, adopted_manifest, adopted_score):
    """Bind an explicit valid rescore to the exact currently selected score."""
    lineage=adopted_manifest.get('lineage',{})
    if (previous.get('score_status')!='valid' or lineage.get('kind')!='rescore'
            or lineage.get('source_score_sha256')!=previous.get('score_sha256')
            or lineage.get('source_scoring_attempt_id')!=previous.get('scoring_attempt_id')
            or lineage.get('source_candidate_sha256')!=previous.get('candidate_sha256')
            or lineage.get('source_attempt_manifest_sha256')!=original_manifest['sha256']):
        raise ValueError('VALID_RESCORE_SELECTED_SOURCE_LINEAGE_MISMATCH')
    original=original_manifest['document']
    for key in ('candidate_artifact_sha256','candidate_original_sha256','contract_sha256',
                'execution_record_sha256','private_gt_workspace_sha256','private_scoring_tree_sha256',
                'task_sha256','transcript_sha256'):
        if (key not in original.get('digests',{}) or key not in adopted_manifest.get('digests',{})
                or original['digests'][key]!=adopted_manifest['digests'][key]
                or key!='transcript_sha256' and not original['digests'][key]):
            raise ValueError('VALID_RESCORE_FROZEN_INPUT_CHANGED:'+key)
    if (adopted_score['execution']['attempt_id']!=previous['execution_attempt_id']
            or adopted_score['identity']['attempt_id']==previous['scoring_attempt_id']):
        raise ValueError('VALID_RESCORE_NEW_ATTEMPT_SAME_EXECUTION_REQUIRED')


def locked_rescore_owner(root, previous, score_sha, *, frozen, native_required=True):
    root=root.resolve(strict=True)
    owners=[parent for parent in root.parents if (parent/'orchestration-state.json').is_file()]
    if not owners:raise ValueError('VALID_RESCORE_LOCKED_OWNER_REQUIRED')
    owner=owners[0];state=frozen._verify_state(owner)
    if state.get('kind')!='rescore' or not state.get('submission'):
        raise ValueError('VALID_RESCORE_LOCKED_SUBMISSION_REQUIRED')
    tasks=[t for t in state['tasks'] if (owner/t['attempt_path']).resolve()==root]
    if len(tasks)!=1:raise ValueError('VALID_RESCORE_OWNER_TASK_MISMATCH')
    task=tasks[0]
    if (task.get('phase')!='SCORE_RECORDED' or (task.get('score') or {}).get('sha256')!=score_sha
            or task.get('source',{}).get('score_sha256')!=previous['score_sha256']
            or task.get('source',{}).get('scoring_attempt_id')!=previous['scoring_attempt_id']
            or native_required and (task.get('thread') or {}).get('status')!='COMPLETED'):
        raise ValueError('VALID_RESCORE_VERIFIED_TERMINAL_REQUIRED')
    return owner


def verified_presentation_admission_repair(original, attempt, execution, root):
    """A replayed complete SDK proof can repair an old projection-only rejection."""
    profile='bound-native-moa-presentation-completeness/v1'
    old=original.get('execution',{})
    if (old.get('scorable') is not False
        or (old.get('failure') or {}).get('code')!='EXECUTION_NOT_SCORABLE'
        or attempt.get('evidence_admission')!=profile
        or execution.get('harness',{}).get('id')!='doubaowork'):
        return False
    path=root/'private/evidence-admission.json'
    if path.is_symlink() or not path.is_file() or digest(path)!=attempt.get('reviewed_evidence_receipt_sha256'):
        return False
    receipt=json.loads(path.read_text(encoding='utf-8'))
    proof=receipt.get('proof',{})
    return (receipt.get('profile')==profile and receipt.get('original_execution_changed') is False
        and receipt.get('original_trace_changed') is False and proof.get('all_display_blocks_accounted') is True
        and proof.get('original_evidence_completeness')=='partial'
        and bool(proof.get('original_missing'))
        and set(proof['original_missing'])<={'unmapped-native-message-block','resource_metrics_complete_coverage'}
        and 'unmapped-native-message-block' in proof['original_missing'])


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
    valid_rescore=getattr(args,'allow_valid_rescore',False)
    valid_reason=getattr(args,'valid_rescore_reason',None)
    if valid_rescore and (not isinstance(valid_reason,str) or len(valid_reason.strip())<8):
        raise ValueError('EXPLICIT_VALID_RESCORE_REASON_REQUIRED')
    reason=getattr(args,'infrastructure_repair_reason',None)
    if repair and (not isinstance(reason,str) or len(reason.strip())<8):
        raise ValueError('EXPLICIT_INFRASTRUCTURE_REPAIR_REASON_REQUIRED')
    if (not set(partial['task_ids'])<=set(expected)
            or (not repair and not valid_rescore and not set(partial["task_ids"]) < set(expected))):
        raise ValueError("STRICT_PARTIAL_SCOPE_REQUIRED")
    verification_python = getattr(args, 'verification_score_python', None)
    runtime = {'executable': str(verification_python.expanduser().absolute())} if verification_python else state['score_skill'].get('python')
    skill = frozen._score_skill_lock(args.score_skill_dir, python_runtime=runtime)
    rows = {r["task_id"]: copy.deepcopy(r) for r in partial["tasks"]}
    roots = {r["task_id"]: source_view.joinpath(*PurePosixPath(r["score_path"]).parts).parent
             for r in partial["tasks"] if r["score_path"] is not None}
    extra_records = {}
    locks = [{"path": str(p), "sha256": digest(p)} for p in [unit_file, source / "orchestration-state.json", source / "submission.json"]]+extra_locks
    seen=set();repaired=[];rescored=[];state_tasks={t['task_id']:t for t in state['tasks']}
    for selector in args.additional_attempt:
        task, value = selector.split("=", 1)
        if task not in expected or task in seen or (task in rows and not repair and not valid_rescore):
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
            if previous['score_status']=='valid':
                if not valid_rescore:raise ValueError('VALID_SOURCE_SCORE_REQUIRES_RESCORE_SELECTION')
                old_manifest=roots[task]/'attempt-manifest.json'
                validate_valid_rescore(previous,{'sha256':digest(old_manifest),'document':json.loads(old_manifest.read_text())},attempt,score)
                owner=locked_rescore_owner(root,previous,digest(root/'score.json'),frozen=frozen,
                    native_required=score['judge'].get('protocol')=='codex-agent-judge-v1')
                for p in (old_manifest,roots[task]/'score.json',owner/'orchestration-state.json',owner/'submission.json'):
                    locks.append({'path':str(p),'sha256':digest(p)})
                rescored.append({'task_id':task,'previous':previous,'replacement_attempt':str(root),
                                 'replacement_orchestration':str(owner),'reason':valid_reason})
            original=state_tasks.get(task)
            if original is None and previous['score_status']!='valid':raise ValueError('INFRASTRUCTURE_SOURCE_TASK_MISSING')
            if previous['score_status']=='valid':
                pass
            elif previous['score_status']=='evaluation_error':
                source_score=roots[task]/'score.json'
                frozen._run_score_command(skill,['verify-score','--attempt-root',str(source_score.parent),'--archived'])
                lineage=attempt.get('lineage',{})
                if (lineage.get('kind')!='rescore' or lineage.get('source_score_sha256')!=previous['score_sha256']
                        or lineage.get('source_scoring_attempt_id')!=previous['scoring_attempt_id']):
                    raise ValueError('INFRASTRUCTURE_RESCORE_LINEAGE_REQUIRED')
            elif (previous['score_status']!='unscored'
                    or (original.get('framework_failure',{}).get('kind') not in frozen.framework_failure_retirement.KINDS
                    and original.get('rule_review_unscored',{}).get('kind') != frozen.unscored_rule_review.ERROR_KIND
                    and not verified_presentation_admission_repair(original,attempt,execution,root)
                    and original.get('scoring_error',{}).get('kind') not in {'dataset-rule-evaluation-error/v1',
                        'evaluator-public-context-setup-error/v1','office001-declared-numeric-review/v1',
                        frozen.private_reference_guard.ERROR_KIND,frozen.generated_evidence_globs.ERROR_KIND,
                        frozen.grade_wrapper_normalization.ERROR_KIND,frozen.typed_rule_diagnostics.ERROR_KIND,
                        frozen.public_text_profiles.ERROR_KIND,frozen.escrow_state_review.ERROR_KIND,
                        frozen.work_order_final_policy.ERROR_KIND,frozen.domain_details_diagnostics.ERROR_KIND})):
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
        if previous is not None and previous['score_status']!='valid':
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
    if verification_python is not None:lineage['verification_score_skill']=skill
    if repair:
        lineage.update(infrastructure_correction_profile='explicit-scoring-infrastructure-repair/v1',
                       infrastructure_repair_reason=reason,selected_infrastructure_repairs=repaired)
    if valid_rescore:
        lineage.update(rescore_selection_profile='explicit-selected-valid-rescore/v1',
                       valid_rescore_reason=valid_reason,selected_valid_rescores=rescored,
                       selection_by_score_value=False)
    for lock in locks:
        if digest(Path(lock["path"])) != lock["sha256"]:
            raise ValueError("SOURCE_CHANGED_DURING_COMPOSITION")
    (stage / "selection-lineage.json").write_text(json.dumps(lineage, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    stage.rename(output)
    return {"status": "PASS", "output_root": str(output), "task_count": len(expected), "scope_shrunk": False}
