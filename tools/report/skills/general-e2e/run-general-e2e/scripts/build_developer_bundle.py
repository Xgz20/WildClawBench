#!/usr/bin/env python3
"""Package an explicit, report-bound final execution/score selection for R&D."""
import argparse
from collections import Counter
from datetime import datetime
from pathlib import Path, PurePosixPath
from zoneinfo import ZoneInfo
import csv
import hashlib
import html
import io
import json
import os
import shutil
import stat
import subprocess
import sys
from urllib.parse import quote
import zipfile

ROOT = CONTROL = SOURCE_INDEX = TASK_INDEX = REPORT = RESOURCE = OUTPUT_ROOT = None
UNITS = {}
load = lambda p: json.loads(p.read_text(encoding="utf-8"))
digest = lambda b: hashlib.sha256(b).hexdigest()


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for part in iter(lambda: f.read(4 * 1024 * 1024), b""): h.update(part)
    return h.hexdigest()


def safe_rel(value):
    p = PurePosixPath(value)
    assert value and not p.is_absolute() and ".." not in p.parts and "\\" not in value, value
    return p


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def entry_bytes(path, kind):
    mode = path.lstat().st_mode
    if kind == "directory":
        assert stat.S_ISDIR(mode), path
        return b""
    if kind == "symlink":
        assert stat.S_ISLNK(mode), path
        return os.readlink(path).encode("utf-8", errors="surrogateescape")
    assert kind == "file" and stat.S_ISREG(mode), path
    return path.read_bytes()


def copy_verified(source_root, target_root, row):
    rel = safe_rel(row["path"])
    source, target = source_root.joinpath(*rel.parts), target_root.joinpath(*rel.parts)
    # Never traverse a link while copying an original evidence file.
    for parent in source.parents:
        if parent == source_root.parent:
            break
        assert not parent.is_symlink(), source
    if row["kind"] == "file":
        assert source.is_file() and not source.is_symlink()
        assert source.stat().st_size == row["size"] and sha(source) == row["sha256"], source
        target.parent.mkdir(parents=True, exist_ok=True)
        assert not target.exists()
        if sys.platform == "darwin":
            subprocess.run(["/bin/cp", "-c", str(source), str(target)], check=True)
        else:
            shutil.copy2(source, target)
        target.chmod(int(row["mode"], 8))
        assert sha(target) == row["sha256"], target
        return
    payload = entry_bytes(source, row["kind"])
    assert len(payload) == row["size"] and digest(payload) == row["sha256"], source
    if row["kind"] == "directory": target.mkdir(parents=True, exist_ok=True)
    elif row["kind"] == "symlink":
        assert payload.decode("utf-8", errors="surrogateescape") == row["link_target"]
        assert not os.path.isabs(row["link_target"])
        resolved = os.path.normpath(os.path.join(str(rel.parent), row["link_target"]))
        assert not resolved.startswith("../") and resolved != ".."
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(row["link_target"])
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        target.chmod(int(row["mode"], 8))


VERIFY_SCRIPT = r'''#!/usr/bin/env python3
"""Read-only SHA-256 verification of this directory or its ZIP; no dependencies."""
from pathlib import Path, PurePosixPath
import hashlib, json, os, stat, sys, zipfile

def check(target):
    target = Path(target)
    z = zipfile.ZipFile(target) if target.is_file() else None
    if z:
        manifests = [n for n in z.namelist() if n.count('/') == 1 and n.endswith('/INTEGRITY.json')]
        assert len(manifests) == 1, 'manifest count'
        root = manifests[0].split('/')[0] + '/'
        manifest = json.loads(z.read(manifests[0]))
        actual = set()
        for info in z.infolist():
            assert info.filename.startswith(root), 'unexpected root'
            rel = info.filename[len(root):].rstrip('/')
            if rel: actual.add(rel)
        def read(path): return z.read(root + path)
        def kind(path):
            info = z.getinfo(root + path + ('/' if path in dirs else ''))
            mode = info.external_attr >> 16
            return 'directory' if info.is_dir() else 'symlink' if stat.S_ISLNK(mode) else 'file'
        def hash_file(path):
            h = hashlib.sha256()
            with z.open(root + path) as f:
                for chunk in iter(lambda:f.read(4*1024*1024), b''): h.update(chunk)
            return h.hexdigest()
    else:
        manifest = json.loads((target/'INTEGRITY.json').read_text(encoding='utf-8'))
        actual = set()
        for base, ds, fs in os.walk(target, followlinks=False):
            ds[:] = [name for name in ds if name != '__MACOSX']
            for name in ds + fs:
                if name != '.DS_Store' and not name.startswith('._'): actual.add((Path(base)/name).relative_to(target).as_posix())
            ds[:] = [name for name in ds if not (Path(base)/name).is_symlink()]
        def read(path): return (target/path).read_bytes()
        def kind(path):
            m=(target/path).lstat().st_mode
            return 'symlink' if stat.S_ISLNK(m) else 'directory' if stat.S_ISDIR(m) else 'file'
        def hash_file(path):
            h=hashlib.sha256()
            with (target/path).open('rb') as f:
                for chunk in iter(lambda:f.read(4*1024*1024), b''): h.update(chunk)
            return h.hexdigest()
    dirs = {e['path'] for e in manifest['entries'] if e['kind']=='directory'}
    expected = {e['path'] for e in manifest['entries']} | {'INTEGRITY.json'}
    assert len(expected)==len(manifest['entries'])+1, 'duplicate manifest member'
    assert actual == expected, 'member set differs: '+str(sorted(actual ^ expected)[:5])
    files=links=0
    for e in manifest['entries']:
        p=PurePosixPath(e['path'])
        assert not p.is_absolute() and '..' not in p.parts and '\\' not in e['path']
        assert kind(e['path'])==e['kind'], 'type mismatch: '+e['path']
        if e['kind']=='directory': continue
        if e['kind']=='symlink':
            b=read(e['path']) if z else os.readlink(target/e['path']).encode('utf-8', errors='surrogateescape')
            assert len(b)==e['size'] and hashlib.sha256(b).hexdigest()==e['sha256']
            assert b.decode('utf-8',errors='surrogateescape')==e['link_target']; links+=1
        else:
            size=z.getinfo(root+e['path']).file_size if z else (target/e['path']).stat().st_size
            assert size==e['size'] and hash_file(e['path'])==e['sha256'], 'hash mismatch: '+e['path']
            files+=1
    tasks=json.loads(read('TASK_INDEX.json'))['tasks']
    selection=json.loads(read('SELECTION.json'))
    assert len(tasks)==selection['selected_runs'] and len({(r['unit_id'],r['task_id']) for r in tasks})==len(tasks)
    for r in tasks:
        ex=json.loads(read(r['execution_record']));score=json.loads(read(r['score_file']))
        assert ex['identity']['task_id']==score['identity']['task_id']==r['task_id']
        assert ex['identity']['attempt_id']==score['execution']['attempt_id']==r['execution_attempt_id']
        assert score['identity']['attempt_id']==r['scoring_attempt_id']
        assert score['execution']['record_sha256']==hash_file(r['execution_record'])
        assert score['result']['valid'] is True and score['result']['total_score']==r['score_0_1']
    supplement_count=0
    if 'ResourceSupplements/supplement-manifest.json' in actual:
        sm = json.loads(read('ResourceSupplements/supplement-manifest.json'))
        source_map = json.loads(read('ResourceSupplements/SOURCE_MAP.json'))['sources']
        report = json.loads(read('Reports/general_e2e_report_data.json'))
        rows = {r['run_id']:r for r in report['tasks']}
        for ref in sm['supplements']:
            p = 'ResourceSupplements/' + ref['path']
            assert hash_file(p) == ref['sha256']
            sup = json.loads(read(p))
            row = rows[ref['unit_id']+'::'+ref['task_id']]
            assert sup['execution_record_sha256'] == row['lineage']['execution_record_sha256']
            assert row['lineage']['resource_supplement']['sha256'] == hash_file(p)
            assert row['lineage']['resource_supplement']['manifest_sha256'] == hash_file('ResourceSupplements/supplement-manifest.json')
            assert sup['score_changed'] is False
            for key, value in sup['metrics'].items(): assert row['resource'][key]['value'] == value['value']
            for src in sup['sources']:
                mapped = source_map[src['path']]
                assert mapped['sha256'] == src['sha256'] == hash_file(mapped['archive_path'])
            for a in ref['artifacts']: assert hash_file('ResourceSupplements/'+a['path']) == a['sha256']
        supplement_count=len(sm['supplements'])
    if z: z.close()
    return {'status':'PASS','units':len({r['unit_id'] for r in tasks}),'selected_runs':len(tasks),'valid_scores':len(tasks),'verified_files':files,'verified_symlinks':links,'resource_supplements':supplement_count,'archived_transcripts':sum(bool(r['transcript']) for r in tasks)}

if __name__=='__main__':
    result=check(sys.argv[1] if len(sys.argv)>1 else Path(__file__).resolve().parent)
    print(json.dumps(result,ensure_ascii=False,indent=2))
'''


def link(path, label):
    return f'<a href="{quote(path, safe="/")}">{html.escape(label)}</a>' if path else '<span class="muted">未归档</span>'


def build_html(tasks, summaries, report_excel):
    trs = []
    for row in tasks:
        search = html.escape((row["harness"]+" "+row["task_id"]+" "+row["task_name"]).lower(), quote=True)
        status = "执行错误 · 有效评分" if row["execution_status"] == "candidate_error" else "完成 · 有效评分"
        links = [link(row["execution_record"], "执行记录"), link(row["candidate_workspace"]+"/", "产物"),
                 link(row["transcript"], "会话轨迹"), link(row["raw_trace_directory"]+"/" if row["raw_trace_directory"] else None,"原始轨迹"),
                 link(row["score_file"],"评分"), link(row.get("resource_supplement") or row["resource_metrics"],"资源统计"), link(row["grading_contract"],"评分标准"),
                 link(row["scoring_directory"]+"/", "评分过程")]
        if row.get("rollout"):
            links.insert(3, link(row["rollout"], "rollout 原件"))
        trs.append(f'<tr data-unit="{row["harness"]}" data-search="{search}"><td>{row["harness"]}</td><td>{row["ordinal"]:02d}</td>'
                   f'<td><strong>{html.escape(row["task_name"])}</strong><small>{html.escape(row["task_id"])}</small></td>'
                   f'<td>{status}</td><td class="score">{row["score_100"]:.2f}</td><td class="links">'+" · ".join(links)+"</td></tr>")
    cards = "".join(f'<section><b>{x["harness"]}</b><div>{x["selected_runs"]} 题 · {x["valid_scores"]} 个有效评分</div><small>原始轨迹已归档 {x["raw_trace_present"]}/{x["selected_runs"]}</small></section>' for x in summaries)
    return '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>General E2E · 有效评测数据</title><style>
body{font:14px/1.65 system-ui,-apple-system,sans-serif;margin:0;background:#f4f7fb;color:#193047}main{max-width:1560px;margin:auto;padding:28px}h1{font-size:25px;margin:0 0 8px}a{color:#176baf;text-decoration:none}a:hover{text-decoration:underline}.muted,small{color:#61758a}small{display:block}nav{margin:14px 0}.cards{display:flex;gap:12px;flex-wrap:wrap}.cards section{background:white;border:1px solid #d9e3ed;border-radius:8px;padding:14px 22px;flex:1;min-width:200px}.controls{display:flex;gap:12px;align-items:center;margin:20px 0}input,select{font:inherit;padding:8px;border:1px solid #b7c9da;border-radius:5px}input{flex:1}table{border-collapse:collapse;width:100%;background:white}th{background:#235d89;color:white;text-align:left;position:sticky;top:0}td,th{padding:10px 12px;border-bottom:1px solid #e1e8ef;vertical-align:top}td.score{text-align:right;font-variant-numeric:tabular-nums}.links{min-width:265px}tr:hover{background:#edf5fc}.table{overflow-x:auto;border:1px solid #d9e3ed;border-radius:8px}footer{margin-top:20px;color:#61758a}tr[hidden]{display:none}</style>
<main><h1>General E2E · 有效评测数据</h1><div>已核验的最终选择 · 执行、评分、资源及原始轨迹。选择用例后直接查看本包中的执行、评分和原始证据。</div>
<nav>''' + link("README.md", "阅读说明") + " · " + link("TASK_INDEX.csv", "CSV 索引") + " · " + link(report_excel, "Excel 报告") + " · " + link("Reports/通用场景端到端自动化评测报告.md", "领导版报告") + '</nav><div class="cards">' + cards + '''</div>
<div class="controls"><select id="unit"><option value="">全部 Harness</option>''' + "".join(f"<option>{n}</option>" for n in UNITS.values()) + '''</select><input id="search" type="search" placeholder="搜索用例 ID、名称或 Harness"><span id="count">全部用例</span></div>
<div class="table"><table><thead><tr><th>Harness</th><th>序号</th><th>用例</th><th>状态</th><th>得分</th><th>原始数据入口</th></tr></thead><tbody>''' + "\n".join(trs) + '''</tbody></table></div>
<footer>已选择的执行错误和有效0分保留。资源补充证据与原执行、评分分别保留，未知资源仍不可用。分数为百分制。</footer></main>
<script>const rows=[...document.querySelectorAll('tbody tr')],unit=document.querySelector('#unit'),search=document.querySelector('#search');function filter(){let n=0;const q=search.value.trim().toLowerCase();for(const r of rows){r.hidden=!!((unit.value&&r.dataset.unit!==unit.value)||(q&&!r.dataset.search.includes(q)));if(!r.hidden)n++}document.querySelector('#count').textContent=n+' / '+rows.length}unit.addEventListener('change',filter);search.addEventListener('input',filter);filter();</script></html>'''


def main(argv=None):
    global ROOT, CONTROL, SOURCE_INDEX, TASK_INDEX, REPORT, RESOURCE, OUTPUT_ROOT, UNITS
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ["workspace-root", "report-dir", "output-root"]:
        parser.add_argument("--"+flag, type=Path, required=True)
    parser.add_argument("--source-index", type=Path)
    parser.add_argument("--task-index", type=Path)
    parser.add_argument("--resource-root", type=Path, help="Optional explicit external immutable resource-supplement manifest root")
    args=parser.parse_args(argv)
    UNITS = {}
    ROOT=args.workspace_root.resolve(); REPORT=args.report_dir.resolve()
    SOURCE_INDEX=(args.source_index or REPORT/"developer-source-index.json").resolve()
    TASK_INDEX=(args.task_index or REPORT/"developer-task-index.json").resolve()
    OUTPUT_ROOT=args.output_root.resolve(); OUTPUT_ROOT.mkdir(parents=True,exist_ok=True)
    RESOURCE=args.resource_root.resolve() if args.resource_root else None
    CONTROL=OUTPUT_ROOT/"bundle-receipts"
    report_input=load(REPORT/"general_e2e_report_data.json")
    display={"astronstudio":"AstronStudio","workbuddy":"WorkBuddy","qwenwork":"QwenWork","doubaowork":"DoubaoWork"}
    for unit in report_input["units"]:
        key=unit["unit_id"];label=display.get(unit["harness"]["id"],key)
        if label in UNITS.values():label=key
        safe_rel(label);UNITS[key]=label
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    name = "general-e2e-valid_" + now.strftime("%Y%m%d_%H%M%S")
    destination = OUTPUT_ROOT / name
    staging = destination.with_name("." + name + ".pending")
    archive = destination.with_suffix(".zip")
    assert not destination.exists() and not staging.exists() and not archive.exists()
    CONTROL.mkdir(parents=True, exist_ok=True)
    index, selected = load(SOURCE_INDEX), load(TASK_INDEX)
    report = load(REPORT / "general_e2e_report_data.json")
    if (REPORT / "composite-report-receipt.json").is_file():
        receipt = load(REPORT / "composite-report-receipt.json")
    else:
        formal = load(REPORT / "receipts/report-receipt.json")
        def report_artifact(filename):
            matches = [r for r in formal["artifacts"] if PurePosixPath(r["path"]).name == filename]
            assert len(matches) == 1, "report artifact ambiguous: " + filename
            return matches[0]["sha256"]
        assert report_artifact(TASK_INDEX.name) == sha(TASK_INDEX)
        receipt = {"source_json_sha256": report_artifact("general_e2e_report_data.json"),
                   "excel_sha256": report_artifact(report["artifact_filenames"]["excel"]),
                   "composite_import_index_sha256": report_artifact(SOURCE_INDEX.name)}
    assert selected["source_index_sha256"] == sha(SOURCE_INDEX)
    assert receipt["source_json_sha256"] == sha(REPORT / "general_e2e_report_data.json")
    assert receipt["excel_sha256"] == sha(REPORT / report["artifact_filenames"]["excel"])
    assert receipt["composite_import_index_sha256"] == sha(SOURCE_INDEX)
    assert set(index["imports"]) == set(UNITS) and len(selected["selected_tasks"]) == report["scope"]["task_run_count"]
    reports = {x["run_id"]: x for x in report["tasks"]}
    ordinal = {tid:i+1 for i,tid in enumerate(report["scope"]["task_ids"])}
    assert len(ordinal) > 0 and all(x["score_status"] == "valid" for x in reports.values())
    manifests = {}
    for uid, item in index["imports"].items():
        source = Path(item["target"])
        assert source.resolve().is_relative_to(ROOT) and sha(source/"package-manifest.json") == item["package_manifest_sha256"]
        manifests[uid] = load(source/"package-manifest.json")
        assert not any(part == ".DS_Store" or part == "__MACOSX" or part.startswith("._")
                       for e in manifests[uid]["entries"] for part in PurePosixPath(e["path"]).parts)
        assert manifests[uid]["identity"]["unit_id"] == uid
        assert manifests[uid]["identity"]["task_ids"] == report["scope"]["task_ids"]
    estimated = sum(e["size"] for m in manifests.values() for e in m["entries"])
    assert shutil.disk_usage(ROOT).free > estimated * 2 + 100 * 1024 * 1024, "insufficient space"
    staging.mkdir(parents=True)
    source_summary = []
    for uid, harness in UNITS.items():
        source = Path(index["imports"][uid]["target"]); target = staging/harness
        manifest = manifests[uid]
        assert len({e["path"] for e in manifest["entries"]}) == len(manifest["entries"])
        for entry in manifest["entries"]: copy_verified(source,target,entry)
        for rel in ["package-manifest.json","receipts/package-receipt.json","receipts/import-return-receipt.json"]:
            if (source/rel).is_file():
                (target/rel).parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source/rel,target/rel)
        source_summary.append({"unit_id":uid,"harness":harness,"package_id":index["imports"][uid]["package_id"],
                               "package_manifest_sha256":sha(source/"package-manifest.json"),"bundle_directory":harness})
        print(json.dumps({"stage":"source-copied-and-hash-verified","harness":harness,"manifest_entries":len(manifest["entries"])}),flush=True)
    if RESOURCE is not None:
        supplement_manifest = load(RESOURCE / "supplement-manifest.json")
        assert receipt["resource_supplement_manifest_sha256"] == sha(RESOURCE / "supplement-manifest.json")
        resource_target = staging / "ResourceSupplements"
        resource_target.mkdir()
        artifact_lookup = {}
        for ref in supplement_manifest["supplements"]:
            for a in ref["artifacts"]:
                artifact_lookup.setdefault((a["sha256"],a["size"]), "ResourceSupplements/"+a["path"])
        portable_sources = {}
        for ref in supplement_manifest["supplements"]:
            for a in ref["artifacts"]:
                src, dst = RESOURCE / a["path"], resource_target / a["path"]
                assert src.stat().st_size == a["size"] and sha(src) == a["sha256"]
                dst.parent.mkdir(parents=True, exist_ok=True)
                if not dst.exists(): subprocess.run(["/bin/cp", "-c", str(src), str(dst)], check=True)
            supplement = load(RESOURCE / ref["path"])
            for source in supplement["sources"]:
                original = Path(source["path"])
                mapped = None
                for uid, imported in index["imports"].items():
                    package = Path(imported["target"])
                    # A byte-verified frozen copy may replace an actively edited
                    # source directory. Keep the original provenance path as an
                    # explicit alias; the destination SHA is still checked below.
                    for source_root in [package, Path(imported.get("original_target", package))]:
                        if original.is_relative_to(source_root):
                            mapped = (Path(UNITS[uid]) / original.relative_to(source_root)).as_posix()
                            break
                    if mapped is not None:
                        break
                if mapped is None:
                    mapped = artifact_lookup.get((source["sha256"],source["size"]))
                assert mapped and (staging / mapped).is_file(), original
                assert (staging / mapped).stat().st_size == source["size"] and sha(staging / mapped) == source["sha256"]
                portable_sources[str(original)] = {"archive_path": mapped, "sha256": source["sha256"], "size": source["size"]}
        for supplemental_name in ["supplement-manifest.json", "user-policy.json"]:
            if (RESOURCE / supplemental_name).is_file(): shutil.copy2(RESOURCE / supplemental_name, resource_target / supplemental_name)
        write_json(resource_target / "SOURCE_MAP.json", {"schema_version": 1, "sources": portable_sources})
    tasks = []
    for source_row in selected["selected_tasks"]:
        uid, tid = source_row["unit_id"],source_row["task_id"]
        source = Path(index["imports"][uid]["target"]); harness=UNITS[uid]
        r = reports[uid+"::"+tid]
        ex_path, sc_path = Path(source_row["execution_record"]),Path(source_row["score_file"])
        ex, score = load(ex_path),load(sc_path)
        assert sha(ex_path)==r["lineage"]["execution_record_sha256"]==score["execution"]["record_sha256"]
        assert sha(sc_path)==r["lineage"]["score_sha256"]
        assert ex["identity"]["attempt_id"]==r["execution_attempt_id"]==score["execution"]["attempt_id"]
        assert ex["execution"]["business_status"]==score["execution"]["business_status"]==r["execution_status"]
        assert score["identity"]["attempt_id"]==r["scoring_attempt_id"]
        assert score["result"]["valid"] is True and score["result"]["total_score"]==r["total_score"]
        relative = lambda p: (PurePosixPath(harness)/p.relative_to(source).as_posix()).as_posix()
        optional = lambda p: relative(p) if p.is_file() else None
        unit = source/"unit"
        trace = unit/ex["evidence"]["trace_index_path"] if ex["evidence"].get("trace_index_path") else None
        ti = load(trace) if trace else {}
        raw_paths=[]
        for t in ti.get("raw_trace",[]):
            p=trace.parent/t["path"];assert p.is_file() and sha(p)==t["sha256"] and p.stat().st_size==t["size"]
            raw_paths.append(relative(p))
        transcript=unit/ex["evidence"]["transcript_path"] if ex["evidence"].get("transcript_path") else None
        task={"harness":harness,"unit_id":uid,"ordinal":ordinal[tid],"task_id":tid,"task_name":r["task_name"],
              "execution_status":r["execution_status"],"score_status":"valid","score_0_1":r["total_score"],"score_100":r["total_score"]*100,
              "execution_attempt_id":r["execution_attempt_id"],"scoring_attempt_id":r["scoring_attempt_id"],
              "execution_record":relative(ex_path),"score_file":relative(sc_path),"scoring_directory":relative(sc_path.parent),
              "score_audit":optional(sc_path.with_name("score-audit.json")),"grading_contract":optional(sc_path.parent/"private/contract.json"),
              "candidate_workspace":relative(unit/ex["candidate"]["path"]),"transcript":optional(transcript) if transcript else None,
              "trace_index":relative(trace) if trace else None,"raw_trace_directory":relative(trace.parent/"raw") if trace and (trace.parent/"raw").is_dir() else None,
              "raw_trace_files":raw_paths,"trace_completeness":ti.get("completeness",{}),"execution_evidence_completeness":ex["evidence"]["completeness"],
              "resource_metrics":relative(unit/ex["resource_metrics_path"]) if ex.get("resource_metrics_path") else None,
              "execution_record_sha256":sha(ex_path),"score_sha256":sha(sc_path)}
        task["resource_supplement"] = r["lineage"].get("resource_supplement", {}).get("path")
        task["effective_resource"] = r["resource"]
        if task["resource_supplement"] and RESOURCE is not None:
            sup = load(staging / task["resource_supplement"])
            if sup.get("rollout_path"):
                task["rollout"] = (PurePosixPath(task["resource_supplement"]).parent / sup["rollout_path"]).as_posix()
                assert sha(staging/task["rollout"]) == r["tool_calls"]["rollout_sha256"]
                task["raw_trace_files"].append(task["rollout"])
            if sup.get("base_supplement"):
                base_manifest = PurePosixPath(task["resource_supplement"]).parent / safe_rel(sup["base_supplement"]["path"])
                assert sha(staging/base_manifest) == sup["base_supplement"]["sha256"]
                base_trace = base_manifest.parent / "trace/trace-index.json"
                if (staging/base_trace).is_file():
                    base_index = load(staging/base_trace)
                    assert base_index["identity"] == ex["identity"]
                    task["original_transcript"] = task["transcript"]
                    task["original_trace_index"] = task["trace_index"]
                    task["transcript"] = (base_trace.parent / safe_rel(base_index["transcript"]["path"])).as_posix()
                    assert sha(staging/task["transcript"]) == base_index["transcript"]["sha256"]
                    task["trace_index"] = base_trace.as_posix()
                    task["raw_trace_files"] += [(base_trace.parent/safe_rel(a["path"])).as_posix() for a in base_index["raw_trace"]]
                    task["raw_trace_directory"] = (base_trace.parent/"raw").as_posix()
                    task["trace_completeness"] = base_index["completeness"]
            if sup.get("trace_supplement"):
                task["original_transcript"] = task["transcript"]
                task["original_trace_index"] = task["trace_index"]
                portable = lambda p: "ResourceSupplements/" + Path(p).relative_to(RESOURCE).as_posix()
                task["transcript"] = portable(sup["trace_supplement"]["transcript"])
                task["trace_index"] = portable(sup["trace_supplement"]["index"])
                task["raw_trace_files"] = [portable(sup["trace_supplement"]["raw"])]
                task["raw_trace_directory"] = str(PurePosixPath(task["raw_trace_files"][0]).parent)
                task["trace_completeness"] = load(staging / task["trace_index"])["completeness"]
        if r["lineage"].get("general_resource_supplement_sha256"):
            supplemental = unit / "evidence/resource-supplements" / tid
            task["resource_supplement"] = relative(supplemental/"supplement.json")
            task["transcript"] = relative(supplemental/"trace/transcript.jsonl")
            task["trace_index"] = relative(supplemental/"trace/trace-index.json")
            ti = load(supplemental/"trace/trace-index.json")
            task["raw_trace_files"] = [relative(supplemental/"trace"/ref["path"]) for ref in ti["raw_trace"]]
            task["raw_trace_directory"] = relative(supplemental/"trace/raw")
        for field in ["total_tokens", "request_count", "call_count", "agent_duration_seconds", "duration_seconds"]:
            task[field] = r["resource"][field]["value"]
        for field in ["execution_record","score_file","score_audit","grading_contract","candidate_workspace","transcript","trace_index","resource_metrics","resource_supplement"]:
            if task[field]:assert (staging/task[field]).exists(), (tid,field)
        tasks.append(task)
    tasks.sort(key=lambda x:(list(UNITS).index(x["unit_id"]),x["ordinal"]))
    assert len({(x["unit_id"],x["task_id"]) for x in tasks}) == report["scope"]["task_run_count"]
    for uid,h in UNITS.items():
        selected_tasks=[x for x in tasks if x["unit_id"]==uid]
        assert len(selected_tasks)==len(ordinal) and {x["task_id"] for x in selected_tasks}==set(ordinal)
        primary_ex={p.relative_to(staging).as_posix() for p in (staging/h/"unit/evidence/tasks").glob("*/*/execution-record.json")}
        score_files={p.relative_to(staging).as_posix() for p in (staging/h/"scoring/attempts").rglob("score.json")}
        assert primary_ex=={x["execution_record"] for x in selected_tasks}
        assert score_files=={x["score_file"] for x in selected_tasks}
    summaries=[]
    for uid,h in UNITS.items():
        rr=[x for x in tasks if x["unit_id"]==uid]
        summaries.append({"harness":h,"unit_id":uid,"selected_runs":len(rr),"valid_scores":len(rr),
                          "execution_status_counts":dict(Counter(x["execution_status"] for x in rr)),
                          "zero_scores":sum(x["score_0_1"]==0 for x in rr),"transcript_present":sum(bool(x["transcript"]) for x in rr),
                          "raw_trace_present":sum(bool(x["raw_trace_files"]) for x in rr)})
    write_json(staging/"TASK_INDEX.json",{"schema_version":1,"report_version":REPORT.name,"tasks":tasks})
    csv_fields=list(dict.fromkeys(k for row in tasks for k in row
                                  if k not in ["raw_trace_files","trace_completeness","effective_resource"]))
    with (staging/"TASK_INDEX.csv").open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=csv_fields,extrasaction="ignore");writer.writeheader();writer.writerows(tasks)
    write_json(staging/"SELECTION.json",{"schema_version":1,"selection_rule":"one final execution and score per unit/task selected by the supplied report",
                "selected_runs":len(tasks),"unique_tasks":len(ordinal),"units":source_summary,"source_index_sha256":sha(SOURCE_INDEX),
                "source_task_index_sha256":sha(TASK_INDEX),"source_report_sha256":sha(REPORT/"general_e2e_report_data.json"),"summaries":summaries})
    shutil.copytree(REPORT,staging/"Reports",ignore=shutil.ignore_patterns(".DS_Store","__pycache__"))
    assert sha(staging/"Reports/general_e2e_report_data.json")==receipt["source_json_sha256"]
    table="\n".join(f'| {x["harness"]} | {x["selected_runs"]} | {x["valid_scores"]} | {x["transcript_present"]} | {x["raw_trace_present"]} |' for x in summaries)
    readme=f"""# General E2E 研发审阅数据包

生成时间：{now.isoformat()}。本包包含所提供报告显式选择的{len(UNITS)}个单元、{len(tasks)}条运行。每个单元/用例只采用一个执行和评分，保留执行失败的有效零分，不混入被替代轮次。

打开 `INDEX.html` 按客户端和用例筛选，进入执行记录、产物、原始/标准轨迹、资源、评分过程及冻结评分标准。`TASK_INDEX.json/csv` 提供精确相对路径，`SELECTION.json` 记录来源和哈希，`Reports/` 保留同源报告。

| 单元 | 已采用执行 | 有效评分 | 标准轨迹数 | 原始轨迹数 |
| --- | ---: | ---: | ---: | ---: |
{table}

单元目录保留原回传包布局、原始文件字节和相对符号链接。资源补充记录单独保存，未知字段不补零。原件中的历史路径仅用于溯源，跨机器定位以索引相对路径为准。

使用 `python3 VERIFY.py` 校验展开目录，或 `python3 VERIFY.py /path/to/{name}.zip` 校验ZIP。校验覆盖全部载荷、链接、执行/评分身份及资源来源。
"""
    (staging/"README.md").write_text(readme,encoding="utf-8")
    (staging/"VERIFY.py").write_text(VERIFY_SCRIPT,encoding="utf-8")
    (staging/"INDEX.html").write_text(build_html(tasks,summaries,"Reports/"+report["artifact_filenames"]["excel"]),encoding="utf-8")
    write_json(staging/"INPUT_VALIDATION.json",{"status":"PASS","selected_runs":len(tasks),"units":len(UNITS),"original_package_member_hashes_verified":True,
               "original_execution_and_score_hashes_verified_against_report":True,"extra_execution_attempts":0,"extra_scoring_attempts":0,
               "excluded_files":["unselected package versions",".DS_Store","runtime environments already excluded by return protocol"]})
    entries=[]
    for base,dirs,files in os.walk(staging,followlinks=False):
        dirs[:] = [n for n in dirs if n != "__MACOSX" and not n.startswith("._")]
        files = [n for n in files if n != ".DS_Store" and not n.startswith("._")]
        for n in sorted(dirs+files):
            p=Path(base)/n;rel=p.relative_to(staging).as_posix();mode=p.lstat().st_mode
            kind="symlink" if stat.S_ISLNK(mode) else "directory" if stat.S_ISDIR(mode) else "file"
            b=entry_bytes(p,kind) if kind!="file" else None
            e={"path":rel,"kind":kind,"mode":format(stat.S_IMODE(mode),"04o"),"size":len(b) if b is not None else p.stat().st_size,
               "sha256":digest(b) if b is not None else sha(p)}
            if kind=="symlink":e["link_target"]=os.readlink(p)
            entries.append(e)
        dirs[:]=[x for x in dirs if not (Path(base)/x).is_symlink()]
    entries.sort(key=lambda x:x["path"])
    write_json(staging/"INTEGRITY.json",{"schema_version":"general-e2e-developer-bundle/v1","created_at":now.isoformat(),"entries":entries})
    verified=subprocess.run([sys.executable,str(staging/"VERIFY.py"),str(staging)],text=True,capture_output=True)
    assert verified.returncode==0,verified.stdout+verified.stderr
    temporary=archive.with_suffix(".zip.partial")
    zip_entries=entries+[{"path":"INTEGRITY.json","kind":"file","mode":"0644"}]
    print(json.dumps({"stage":"zip-writing","files":sum(e["kind"]=="file" for e in zip_entries),"uncompressed_bytes":sum(e.get("size",0) for e in entries)}),flush=True)
    with zipfile.ZipFile(temporary,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
        for e in zip_entries:
            info=zipfile.ZipInfo(name+"/"+e["path"]+("/" if e["kind"]=="directory" else ""),date_time=now.timetuple()[:6])
            info.create_system=3;type_mode={"file":stat.S_IFREG,"directory":stat.S_IFDIR,"symlink":stat.S_IFLNK}[e["kind"]]
            info.external_attr=(type_mode|int(e["mode"],8))<<16
            info.compress_type=zipfile.ZIP_STORED if e["kind"]=="directory" else zipfile.ZIP_DEFLATED
            if e["kind"]=="directory":z.writestr(info,b"")
            elif e["kind"]=="symlink":z.writestr(info,os.readlink(staging/e["path"]).encode("utf-8",errors="surrogateescape"))
            else:
                with (staging/e["path"]).open("rb") as source,z.open(info,"w",force_zip64=True) as target:shutil.copyfileobj(source,target,4*1024*1024)
    with zipfile.ZipFile(temporary) as root_check:
        assert {p.split("/")[0] for p in root_check.namelist()} == {destination.name}, "archive root differs from bundle name"
    checked=subprocess.run([sys.executable,str(staging/"VERIFY.py"),str(temporary)],text=True,capture_output=True)
    assert checked.returncode==0,checked.stdout+checked.stderr
    staging.rename(destination);temporary.rename(archive)
    archive_sha=sha(archive)
    archive.with_suffix(".zip.sha256").write_text(archive_sha+"  "+archive.name+"\n",encoding="utf-8")
    result={**json.loads(checked.stdout),"created_at":now.isoformat(),"bundle_directory":str(destination),"archive":str(archive),
            "archive_size_bytes":archive.stat().st_size,"archive_sha256":archive_sha,"uncompressed_payload_bytes":sum(e.get("size",0) for e in entries),
            "source_report":REPORT.name,"source_index_sha256":sha(SOURCE_INDEX),"summaries":summaries}
    write_json(archive.with_suffix(".verification.json"),result)
    write_json(CONTROL/"latest-bundle-receipt.json",result)
    print(json.dumps(result,ensure_ascii=False),flush=True)


if __name__=="__main__": main()
