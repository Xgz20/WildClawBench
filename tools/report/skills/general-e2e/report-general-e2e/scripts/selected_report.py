#!/usr/bin/env python3
"""Validate and report an explicit per-task selection across frozen source batches.

Original batch/attempt/release identities remain in each task's lineage. A
selected report does not fabricate a complete single-source collect receipt.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse, copy, hashlib, json, os, shutil, stat, subprocess, sys, uuid
sys.path.insert(0,str(Path(__file__).resolve().parent))
import report_general_e2e as report
import leader_report
ROOT=BATCH=None
load=lambda p:json.loads(Path(p).read_text(encoding="utf-8"))
def sha(p): return report.sha256_file(Path(p))
def require(ok,code):
    if not ok: raise ValueError(code)
def safe_file(path,parent=None):
    path=Path(path);require(path.is_file() and not path.is_symlink(),f"SELECTION_FILE_UNSAFE:{path}")
    if parent is not None: require(path.resolve().is_relative_to(Path(parent).resolve()),"SELECTION_FILE_OUTSIDE_ROOT")
    return path

def verify_source_package(root,expected,unit_id,task_ids):
    root=Path(root).resolve();require(root.is_relative_to(ROOT),"SELECTION_PACKAGE_OUTSIDE_ROOT")
    p=safe_file(root/"package-manifest.json",ROOT);require(sha(p)==expected,"SELECTION_PACKAGE_MANIFEST_DRIFT")
    manifest=load(p);require(manifest["identity"]["unit_id"]==unit_id and manifest["identity"]["task_ids"]==task_ids,"SELECTION_PACKAGE_SCOPE")
    members={}
    for e in manifest["entries"]:
        rel=report.safe_relative(e["path"],"package member").as_posix();require(rel not in members,"SELECTION_DUPLICATE_MEMBER")
        q=root/rel;mode=q.lstat().st_mode
        if e["kind"]=="directory":require(stat.S_ISDIR(mode),"SELECTION_DIRECTORY");b=b""
        elif e["kind"]=="symlink":
            require(stat.S_ISLNK(mode),"SELECTION_SYMLINK");b=os.readlink(q).encode("utf-8",errors="surrogateescape")
            require(b.decode("utf-8",errors="surrogateescape")==e["link_target"],"SELECTION_LINK_DRIFT")
        else:
            require(e["kind"]=="file" and stat.S_ISREG(mode) and q.resolve().is_relative_to(root),"SELECTION_FILE")
            require(q.stat().st_size==e["size"] and sha(q)==e["sha256"],"SELECTION_MEMBER_SHA_DRIFT")
            members[rel]=e;continue
        require(len(b)==e["size"] and hashlib.sha256(b).hexdigest()==e["sha256"],"SELECTION_MEMBER_SHA_DRIFT")
        members[rel]=e
    return manifest,members

def apply_external_resources(row,args,ref,manifest_sha):
    root=args.resource_root.resolve();path=safe_file(root/ref["path"],root)
    require(sha(path)==ref["sha256"],"SELECTION_RESOURCE_SUPPLEMENT_DRIFT")
    for artifact in ref["artifacts"]:
        p=safe_file(root/report.safe_relative(artifact["path"],"supplement").as_posix(),root)
        require(p.stat().st_size==artifact["size"] and sha(p)==artifact["sha256"],"SELECTION_RESOURCE_ARTIFACT_DRIFT")
    script=Path(__file__).resolve().parents[1]/"vendor/e2e-shared/general-resource-supplements/index.mjs"
    if not script.is_file():script=Path(__file__).resolve().parents[4]/"e2e-shared/general-resource-supplements/index.mjs"
    command=[args.node,str(script),"verify-external","--unit-root",row["lineage"]["source_unit_root"],
             "--execution-record",row["lineage"]["source_execution_record"],"--directory",str(path.parent),"--workspace-root",str(ROOT)]
    if (root/"SOURCE_MAP.json").is_file():command += ["--source-map",str(root/"SOURCE_MAP.json")]
    run=subprocess.run(command,capture_output=True,text=True,timeout=180)
    require(run.returncode==0,"SELECTION_RESOURCE_REPLAY_FAILED:"+run.stderr[-1000:]);verified=json.loads(run.stdout)
    require(verified["status"]=="PASS","SELECTION_RESOURCE_REPLAY_FAILED")
    original=copy.deepcopy(row["resource"])
    for group in verified["metrics"]["metrics"].values():
        for field in group:row["resource"][field]=report.metric_observation(verified["metrics"],field)
    row["tool_calls"].update(verified["tool_counts"])
    row["resource_collection_status"]=verified["metrics"]["collection"]["status"]
    if (path.parent/"trace/transcript.jsonl").is_file():
        row["tool_calls"]["transcript_path"]="ResourceSupplements/"+(path.parent/"trace/transcript.jsonl").relative_to(root).as_posix()
    row["lineage"]["resource_supplement"]={"path":"ResourceSupplements/"+ref["path"],"sha256":ref["sha256"],
        "manifest_sha256":manifest_sha,"original_resource":original,"original_execution_and_score_preserved":True}

def checked_metric_path(unit_root: Path, execution: dict, record_path: Path) -> Path | None:
    relative = execution.get("resource_metrics_path")
    if relative is None:
        return None
    metric_path = safe_file(report.resolve_file(unit_root, relative, "resource metrics"), unit_root)
    ident = execution["identity"]
    evidence_manifest = safe_file(unit_root / "evidence/tasks" / ident["task_id"]
                                  / ident["attempt_id"] / "evidence-manifest.json", unit_root)
    manifest = load(evidence_manifest)
    entries = [x for x in manifest["artifacts"] if x.get("path") == relative]
    require(len(entries) == 1 and entries[0].get("sha256") == sha(metric_path),
            f"RESOURCE_METRIC_SHA_DRIFT:{execution['identity']['task_id']}")
    return metric_path


def selected_task_row(*, unit: dict, meta: dict, unit_root: Path, record_path: Path,
                 record_sha: str, score_path: Path | None, score_sha: str | None,
                 score_status: str, scoring_attempt_id: str | None,
                 lineage: dict) -> dict:
    task_id = meta["task_id"]
    record_path = safe_file(record_path, ROOT)
    require(sha(record_path) == record_sha, f"EXECUTION_SHA_DRIFT:{task_id}")
    execution = report.validate_contract(record_path, report.EXECUTION_SCHEMA)
    identity = execution["identity"]
    require(identity["task_id"] == task_id and identity["unit_id"] == unit["unit_id"]
            and execution["dataset"]["digest"] == load(BATCH / "manifest.json")["dataset"]["digest"],
            f"EXECUTION_IDENTITY_DRIFT:{task_id}")
    score = None
    if score_status != "unscored":
        require(score_path is not None and score_sha is not None and scoring_attempt_id is not None,
                f"SCORE_MISSING:{task_id}")
        safe_file(score_path, ROOT)
        require(sha(score_path) == score_sha, f"SCORE_SHA_DRIFT:{task_id}")
        score = report.validate_contract(score_path, report.SCORE_SCHEMA)
        require(score["identity"]["task_id"] == task_id
                and score["identity"]["unit_id"] == unit["unit_id"]
                and score["identity"]["batch_id"] == identity["batch_id"]
                and score["identity"]["attempt_id"] == scoring_attempt_id
                and score["execution"]["attempt_id"] == identity["attempt_id"]
                and score["execution"]["record_sha256"] == record_sha,
                f"SCORE_IDENTITY_DRIFT:{task_id}")
        if score_status == "valid":
            require(score["result"]["valid"] is True
                    and score["result"]["total_score"] is not None,
                    f"SCORE_INVALID:{task_id}")
        else:
            require(score_status == "evaluation_error" and score["result"]["total_score"] is None,
                    f"SCORE_STATUS_DRIFT:{task_id}")
    else:
        require(score_path is None and score_sha is None and scoring_attempt_id is None,
                f"UNSCORED_HAS_SCORE:{task_id}")
    metric_path = checked_metric_path(unit_root, execution, record_path)
    metrics = load(metric_path) if metric_path else None
    if metrics:
        require(metrics["identity"] == identity, f"RESOURCE_IDENTITY_DRIFT:{task_id}")
    if unit["harness"]["id"] == "workbuddy":
        for timing in (False, True):
            verified = report.workbuddy_resource_supplement(unit_root.parent, task_id, record_path, timing=timing)
            if verified:
                metric_path = Path(verified["resource_metrics_path"])
                metrics = report.validate_contract(metric_path, report.RESOURCE_SCHEMA)
    resource_adjustments = []
    timing_clock_comparable = unit["harness"]["id"] != "doubaowork"
    if metrics and unit["harness"]["id"] == "doubaowork":
        metrics, resource_adjustments, timing_clock_comparable = report.doubao_resource_projection(
            unit_root, execution, metrics, metric_path)
    resource = {field: report.metric_observation(metrics, field) for field, _, _ in report.RESOURCE_FIELDS}
    try:
        checkpoint_values = report.report_views.checkpoints(score, score_path, report.resolve_file, report.sha256_file)
        tool_calls = report.report_views.trace_tools(unit_root, execution, report.resolve_file, report.sha256_file)
        task_definition = report.report_case_views.frozen_task_definition(
            meta, execution, score, score_path, report.resolve_file, report.sha256_file)
    except (ValueError, KeyError, OSError) as exc:
        raise RuntimeError(f"REPORT_EVIDENCE_INVALID:{task_id}:{exc}") from exc
    return {"run_id": f"{unit['unit_id']}::{task_id}",
            "unit_id": unit["unit_id"], "task_id": task_id,
            "task_name": meta.get("name"), "category": meta.get("category"),
            "difficulty": meta.get("difficulty"), "modality": meta.get("modality"),
            "execution_mode": unit.get("execution_mode"),
            "harness": execution["harness"], "model": execution["model"],
            "human_assistance": execution["human_assistance"],
            "execution_attempt_id": identity["attempt_id"],
            "execution_phase": execution["phase"],
            "execution_status": execution["execution"]["business_status"],
            "execution_error": execution["execution"].get("error"),
            "execution_started_at": execution["execution"]["started_at"],
            "execution_finished_at": execution["execution"]["finished_at"],
            "timing_clock_comparable": timing_clock_comparable,
            "evidence_completeness": execution["evidence"]["completeness"],
            "score_status": score_status, "scoring_attempt_id": scoring_attempt_id,
            "judge": score.get("judge") if score else None,
            "components": score.get("components") if score else None,
            "evaluation": score.get("evaluation") if score else None,
            "total_score": score["result"]["total_score"] if score else None,
            "invalid_reason": score["result"].get("invalid_reason") if score else None,
            "resource_collection_status": metrics.get("collection", {}).get("status") if metrics else "unavailable",
            "resource": resource, "checkpoints": checkpoint_values,
            "tool_calls": tool_calls, "task_definition": task_definition,
            "lineage": {**lineage, "execution_record_sha256": record_sha,
                        "score_sha256": score_sha,
                        "resource_metrics_sha256": sha(metric_path) if metric_path else None,
                        "report_resource_adjustments": resource_adjustments}}


def main(argv=None):
    global ROOT,BATCH
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ["workspace-root","batch-root","source-index","task-index"]:parser.add_argument("--"+name,type=Path,required=True)
    parser.add_argument("--resource-root",type=Path);parser.add_argument("--display-config",type=Path)
    parser.add_argument("--target-unit");parser.add_argument("--output-dir",type=Path)
    parser.add_argument("--node",default=os.environ.get("GENERAL_E2E_NODE","node"));parser.add_argument("--node-modules",type=Path)
    args=parser.parse_args(argv);ROOT=args.workspace_root.resolve();BATCH=args.batch_root.resolve()
    batch=load(safe_file(BATCH/"manifest.json",ROOT));source=load(safe_file(args.source_index,ROOT));selection=load(safe_file(args.task_index,ROOT))
    require(selection["source_index_sha256"]==sha(args.source_index),"SELECTION_SOURCE_INDEX_DRIFT")
    canonical=batch["task_ids"];units={u["unit_id"]:u for u in batch["units"]}
    require(set(source["imports"])<=set(units) and source["imports"],"SELECTION_UNIT_SCOPE")
    selected={(r["unit_id"],r["task_id"]):r for r in selection["selected_tasks"]}
    expected={(u,t) for u in source["imports"] for t in canonical}
    require(len(selected)==len(selection["selected_tasks"]) and set(selected)==expected,"SELECTION_TASK_SCOPE")
    supplements={};supplement_sha=None
    if args.resource_root:
        p=args.resource_root/"supplement-manifest.json";m=load(safe_file(p,ROOT));supplement_sha=sha(p)
        require(m["source_execution_selection_sha256"]==sha(args.task_index),"SELECTION_RESOURCE_SCOPE_DRIFT")
        supplements={(r["unit_id"],r["task_id"]):r for r in m["supplements"]}
        require(len(supplements)==len(m["supplements"]) and set(supplements)<=expected,"SELECTION_RESOURCE_DUPLICATE_OR_SCOPE")
    rows=[];summaries=[];imports=[]
    for uid,item in source["imports"].items():
        package=Path(item["target"]).resolve();manifest,members=verify_source_package(package,item["package_manifest_sha256"],uid,canonical)
        unit_root=package/"unit"
        unit_manifest=unit_root/"manifest.json"
        metas={t["task_id"]:t for t in load(unit_manifest)["tasks"]} if unit_manifest.is_file() else None
        if metas is not None: require(set(metas)==set(canonical),"SELECTION_METADATA_SCOPE")
        current=[]
        for tid in canonical:
            chosen=selected[(uid,tid)];rp=safe_file(Path(chosen["execution_record"]),package);sp=Path(chosen["score_file"]) if chosen.get("score_file") else None
            if metas is None:
                source_manifest=safe_file(rp.parent/"execution/unit-manifest.json",package)
                require(source_manifest.relative_to(package).as_posix() in members,"SELECTION_METADATA_NOT_IN_PACKAGE")
                matching=[t for t in load(source_manifest)["tasks"] if t["task_id"]==tid]
                require(len(matching)==1,"SELECTION_METADATA_AMBIGUOUS")
                meta=matching[0]
            else: meta=metas[tid]
            require(rp.relative_to(package).as_posix() in members,"SELECTION_RECORD_NOT_IN_PACKAGE")
            record_sha=members[rp.relative_to(package).as_posix()]["sha256"]
            score_sha=None;scoring_id=None;score_status="unscored"
            if sp:
                safe_file(sp,package);require(sp.relative_to(package).as_posix() in members,"SELECTION_SCORE_NOT_IN_PACKAGE")
                score_sha=members[sp.relative_to(package).as_posix()]["sha256"];score=load(sp)
                score_status="valid" if score["result"]["valid"] else "evaluation_error";scoring_id=score["identity"]["attempt_id"]
            row=selected_task_row(unit=units[uid],meta=meta,unit_root=unit_root,record_path=rp,record_sha=record_sha,
                score_path=sp,score_sha=score_sha,score_status=score_status,scoring_attempt_id=scoring_id,
                lineage={"package_id":item["package_id"],"source_unit_root":str(unit_root),"source_execution_record":str(rp),
                         "source_batch_id":load(rp)["identity"]["batch_id"],"package_manifest_sha256":item["package_manifest_sha256"]})
            if (uid,tid) in supplements:apply_external_resources(row,args,supplements[(uid,tid)],supplement_sha)
            current.append(row)
        rows.extend(current);summaries.append(report.unit_summary(current,units[uid]));imports.append({"unit_id":uid,**item})
    generated=report.generated_at_value(None)
    data={"schema_version":report.REPORT_DATA_SCHEMA,"generated_at":generated,"title":"通用场景端到端自动化评测报告",
        "batch_id":batch["batch_id"],"dataset":batch["dataset"],"release":batch["release"],
        "scope":{"unique_task_count":len(canonical),"task_run_count":len(rows),"unit_count":len(summaries),"task_ids":canonical},
        "overall":{"score":report.score_summary(rows),"categories":report.grouped_score(rows,"category"),"difficulties":report.grouped_score(rows,"difficulty"),
                   "judge_groups":report.judge_groups(rows),"resources":report.resource_summary(rows),"timing":report.timing_summary(rows)},
        "units":summaries,"tasks":rows,"lineage":{"batch_manifest_sha256":sha(BATCH/"manifest.json"),"report_config_sha256":sha(BATCH/"report-config.json"),
            "import_index_sha256":sha(args.source_index),"selected_imports":imports,"selection_manifest_sha256":sha(args.task_index),
            "source_mode":"explicit-per-task-multi-source","resource_supplement_manifest_sha256":supplement_sha},
        "semantics":{"score_denominator":"仅有效评分，真实零分保留，评测异常和未评分不补零。","source_selection":"逐题显式选择，原执行批次及attempt身份不改写。"}}
    if args.display_config:
        data["display_overrides"]=load(safe_file(args.display_config,ROOT))
        for entry in data["display_overrides"].get("unit_model_labels",{}).values():entry.setdefault("reason",entry.get("source"))
    data["presentation"]=report.report_views.build_views(data,report.report_views.load_references())
    if args.target_unit:require(args.target_unit in data["presentation"]["unit_labels"],"SELECTION_TARGET_UNKNOWN")
    if args.output_dir:
        require(args.node_modules and args.node_modules.is_dir(),"SELECTION_EXCEL_RUNTIME_REQUIRED")
        out=args.output_dir.resolve();require(out.is_relative_to(BATCH) and not out.exists(),"SELECTION_OUTPUT_UNSAFE_OR_EXISTS")
        stage=out.with_name('.'+out.name+'.'+uuid.uuid4().hex+'.staging');stage.mkdir(parents=True)
        try:
            name=report.excel_report_filename(generated);data["artifact_filenames"]={"excel":name,"leader_markdown":"通用场景端到端自动化评测报告.md","audit_markdown":"通用场景端到端评测审计.md"}
            report.write_json(stage/"general_e2e_report_data.json",data)
            report.write_text(stage/"通用场景端到端评测审计.md",report.render_audit_markdown(data))
            report.render_excel(stage/"general_e2e_report_data.json",stage/name,stage/"previews",node=args.node,node_modules=args.node_modules,skip_preview=False)
            if args.target_unit:
                leader=leader_report.extract(stage/name,data,args.target_unit);report.write_json(stage/"general_e2e_leader_data.json",leader)
                md=leader_report.render(leader)
            else:md=report.render_markdown(data)
            report.write_text(stage/"通用场景端到端自动化评测报告.md",md)
            report.write_json(stage/"composite-report-receipt.json",{"source_json_sha256":sha(stage/"general_e2e_report_data.json"),"excel_sha256":sha(stage/name),
                "markdown_sha256":sha(stage/"通用场景端到端自动化评测报告.md"),"composite_import_index_sha256":sha(args.source_index),
                "selection_manifest_sha256":sha(args.task_index),"resource_supplement_manifest_sha256":supplement_sha,"source_mode":data["lineage"]["source_mode"]})
            shutil.copy2(args.source_index,stage/"developer-source-index.json");shutil.copy2(args.task_index,stage/"developer-task-index.json")
            stage.rename(out)
        except BaseException:shutil.rmtree(stage);raise
    return data

if __name__=="__main__":
    try:
        data=main();print(json.dumps({"status":"PASS","scope":data["scope"],"scores":data["overall"]["score"]},ensure_ascii=False))
    except Exception as error:
        print(str(error),file=sys.stderr);raise SystemExit(1)
