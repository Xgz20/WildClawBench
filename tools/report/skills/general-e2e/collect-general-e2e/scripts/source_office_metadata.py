"""Audit a live source Office metadata variant while retaining frozen evidence.

Only an explicitly selected proof is accepted. Scoring candidates and all
original receipts keep their original bytes and SHA values.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import time
import xml.etree.ElementTree as ET
import zipfile

PROFILE = "wildclawbench.general-e2e-source-office-metadata-variance/v1"
CWM = re.compile(r"^CWM[0-9a-fA-F]{32}$")
OFFICE = {".docx", ".xlsx", ".pptx", ".docm", ".xlsm", ".pptm"}
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
CP = "http://schemas.openxmlformats.org/officeDocument/2006/custom-properties"
CUSTOM_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/custom-properties"
CUSTOM_TYPE = "application/vnd.openxmlformats-officedocument.custom-properties+xml"
META = {"docProps/custom.xml", "[Content_Types].xml", "_rels/.rels"}

def sha(data): return hashlib.sha256(data).hexdigest()
def load(path): return json.loads(path.read_text(encoding="utf-8"))
def structure(node):
    return (node.tag, tuple(sorted(node.attrib.items())), (node.text or "").strip(), tuple(structure(child) for child in node))

def metadata_view(data, path):
    if data is None:
        if path == "docProps/custom.xml": return (f"{{{CP}}}Properties", (), "", ())
        raise ValueError("required relationship metadata missing")
    node = ET.fromstring(data)
    if path == "docProps/custom.xml":
        if node.tag != f"{{{CP}}}Properties": raise ValueError("custom properties namespace")
        for child in list(node):
            if child.tag == f"{{{CP}}}property" and CWM.fullmatch(child.attrib.get("name", "")):
                if (set(child.attrib) != {"fmtid", "pid", "name"}
                    or child.attrib["fmtid"].upper() != "{D5CDD505-2E9C-101B-9397-08002B2CF9AE}"
                    or not child.attrib["pid"].isdigit()): raise ValueError("unknown marker attributes")
                node.remove(child)
    elif path == "[Content_Types].xml":
        if node.tag != f"{{{CT}}}Types": raise ValueError("content types namespace")
        for child in list(node):
            if child.attrib.get("PartName") == "/docProps/custom.xml":
                if child.tag != f"{{{CT}}}Override" or child.attrib != {"PartName":"/docProps/custom.xml", "ContentType":CUSTOM_TYPE}:
                    raise ValueError("unknown custom content type")
                node.remove(child)
    else:
        if node.tag != f"{{{REL}}}Relationships": raise ValueError("relationships namespace")
        for child in list(node):
            if child.attrib.get("Type") == CUSTOM_REL:
                if child.tag != f"{{{REL}}}Relationship" or set(child.attrib) != {"Id","Type","Target"} or child.attrib["Target"] != "docProps/custom.xml":
                    raise ValueError("unknown custom relationship")
                node.remove(child)
    return structure(node)

def office_delta(before, after):
    with zipfile.ZipFile(BytesIO(before)) as old, zipfile.ZipFile(BytesIO(after)) as new:
        for z in (old,new):
            infos=z.infolist()
            if len(infos)>10000 or any(i.file_size>32*1024*1024 for i in infos) or sum(i.file_size for i in infos)>256*1024*1024:
                raise ValueError("Office diagnostic size limit")
        a,b=set(old.namelist()),set(new.namelist())
        if len(a)!=len(old.infolist()) or len(b)!=len(new.infolist()): raise ValueError("duplicate ZIP member")
        if a-b or not b-a <= {"docProps/custom.xml"}: raise ValueError("non-metadata ZIP member change")
        changed=[n for n in sorted(a&b) if old.read(n)!=new.read(n)]
        if not set(changed)<=META: raise ValueError("business Office member changed")
        props=ET.fromstring(new.read("docProps/custom.xml"))
        names=[p.attrib.get("name") for p in props if CWM.fullmatch(p.attrib.get("name", ""))]
        if not names:raise ValueError("known Office marker absent")
        for name in META:
            if metadata_view(old.read(name) if name in a else None,name)!=metadata_view(new.read(name) if name in b else None,name):
                raise ValueError("unrelated Office metadata changed: "+name)
        return {"added_members":sorted(b-a),"changed_members":changed,"marker_names":names,"business_members_unchanged":True}

def inside(root, relative):
    p=PurePosixPath(relative)
    if p.is_absolute() or not relative or not p.parts or relative!=p.as_posix() or "\\" in relative or any(x in {".",".."} for x in p.parts):raise ValueError("unsafe relative path")
    current=root
    for part in p.parts:
        current=current/part
        if current.is_symlink():raise ValueError("path includes symlink")
    if not current.resolve().is_relative_to(root):raise ValueError("path escaped root")
    return current

def inventory(root):
    rows=[]
    def walk(folder,prefix=""):
        for path in sorted(folder.iterdir(),key=lambda x:x.name):
            name=prefix+path.name;info=path.lstat()
            if stat.S_ISDIR(info.st_mode):walk(path,name+"/")
            elif stat.S_ISLNK(info.st_mode):
                target=os.readlink(path);rows.append({"path":name,"type":"symlink","sha256":sha(target.encode()),"size":len(target.encode("utf-16-le"))//2})
            elif stat.S_ISREG(info.st_mode):
                data=path.read_bytes();after=path.lstat()
                if (info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns):raise ValueError("file changed during read")
                rows.append({"path":name,"type":"file","sha256":sha(data),"size":len(data)})
            else:raise ValueError("unsupported file type")
            if len(rows)>20000:raise ValueError("file count limit")
    walk(root);return rows

def tree_hash(rows):
    h=hashlib.sha256()
    for row in rows:h.update((row["path"]+"\0"+row["type"]+"\0"+row["sha256"]+"\n").encode())
    return h.hexdigest()

def context(unit, task):
    receipt_path=unit/"receipts/collect-evidence-receipt.json";receipt=load(receipt_path)
    selected=[r for r in receipt["tasks"] if r["task_id"]==task]
    if len(selected)!=1:raise ValueError("task receipt ambiguous")
    attempt=selected[0]["attempt_id"];base=inside(unit,f"evidence/tasks/{task}/{attempt}")
    paths={"collect_receipt":receipt_path,"candidate_artifact":base/"candidate/candidate-artifact.json", "execution_record":base/"execution-record.json", "evidence_manifest":base/"evidence-manifest.json"}
    artifact=load(paths["candidate_artifact"]);record=load(paths["execution_record"])
    if (artifact["identity"]!=record["identity"] or record["identity"]["attempt_id"]!=attempt
        or record["identity"]["task_id"]!=task or record.get("phase") not in {"COMPLETED","FAILED"}):raise ValueError("identity or terminal status mismatch")
    for key,path in paths.items():
        if key=="collect_receipt":continue
        refs=[r for r in receipt["artifacts"] if r["path"]==path.relative_to(unit).as_posix()]
        data=path.read_bytes()
        if len(refs)!=1 or refs[0]["sha256"]!=sha(data) or refs[0]["size"]!=len(data):raise ValueError("original receipt binding: "+key)
    policy=artifact["runtime_directory_policy"]
    if policy["ignored_directories"] or policy["forbidden_directories"]:raise ValueError("requires original exact-all policy")
    canonical=inside(unit,artifact["candidate"]["path"]);source=inside(unit,artifact["source_workspace"]["path"])
    if record["session"]["cwd"]!=str(source):raise ValueError("native cwd binding")
    bindings={key:sha(path.read_bytes()) for key,path in paths.items()}
    return artifact,canonical,source,bindings,paths,record["identity"]

def compare(unit, task):
    artifact,canonical,source,bindings,paths,identity=context(unit,task)
    original=inventory(canonical);current=inventory(source)
    if tree_hash(original)!=artifact["expected_sha256"]:raise ValueError("frozen canonical candidate drift")
    old,new={r["path"]:r for r in original},{r["path"]:r for r in current}
    if set(old)!=set(new):raise ValueError("source paths added or removed")
    changes=[];payloads={}
    for name in sorted(old):
        if old[name]==new[name]:continue
        if old[name]["type"]!="file" or new[name]["type"]!="file" or Path(name).suffix.lower() not in OFFICE:raise ValueError("non-Office source change")
        before=inside(canonical,name).read_bytes();after=inside(source,name).read_bytes()
        if sha(before)!=old[name]["sha256"] or sha(after)!=new[name]["sha256"]:raise ValueError("source changed during comparison")
        changes.append({"path":name,"canonical_sha256":sha(before),"source_sha256":sha(after),"canonical_size":len(before),"source_size":len(after),**office_delta(before,after)})
        payloads["canonical/"+name]=before;payloads["source-current/"+name]=after
    if not changes:raise ValueError("source unchanged; use strict default verification")
    if tree_hash(inventory(source))!=tree_hash(current):raise ValueError("source changed after comparison")
    return {"profile":PROFILE,"identity":identity,"bindings":bindings,"canonical_tree_sha256":artifact["expected_sha256"],
        "source_tree_sha256":tree_hash(current),"source_file_count":len(current),"source_total_bytes":sum(r["size"] for r in current),"changes":changes},payloads

def prepare(unit,task,output):
    output=output.resolve();scope=unit/"evidence/source-office-metadata-variances"/task
    if output.exists() or not output.is_relative_to(scope):raise ValueError("new supplement directory must be within the declared task variance scope")
    proof,payloads=compare(unit,task);time.sleep(5)
    after,_=compare(unit,task)
    if after!=proof:raise ValueError("source not stable for supplement")
    output.mkdir(parents=True);archive=output/"variants.zip"
    with zipfile.ZipFile(archive,"x",compression=zipfile.ZIP_STORED) as z:
        for name,data in sorted(payloads.items()):z.writestr(name,data)
    proof.update(created_at=datetime.now(timezone.utc).isoformat(),variant_archive={"path":"variants.zip","sha256":sha(archive.read_bytes())},
        source_workspace_modified=False,original_receipts_modified=False,scoring_decision_made=False,
        producer_entry_sha256=sha(Path(__file__).read_bytes()))
    path=output/"source-office-metadata-supplement.json";path.write_text(json.dumps(proof,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return {"status":"PREPARED","supplement":str(path)}

def verify(unit,task,path):
    if path.is_symlink():raise ValueError("supplement symlink")
    path=path.resolve();scope=unit/"evidence/source-office-metadata-variances"/task
    if not path.is_relative_to(scope):raise ValueError("supplement scope")
    proof=load(path);expected,payloads=compare(unit,task)
    if (proof.get("source_workspace_modified") is not False or proof.get("original_receipts_modified") is not False
        or proof.get("scoring_decision_made") is not False or not re.fullmatch(r"[0-9a-f]{64}",str(proof.get("producer_entry_sha256","")))):
        raise ValueError("supplement provenance")
    for key,value in expected.items():
        if proof.get(key)!=value:raise ValueError("supplement binding or rederived comparison mismatch: "+key)
    archive=inside(path.parent,proof["variant_archive"]["path"])
    if sha(archive.read_bytes())!=proof["variant_archive"]["sha256"]:raise ValueError("variant archive digest")
    with zipfile.ZipFile(archive) as z:
        if len(z.namelist())!=len(payloads) or set(z.namelist())!=set(payloads):raise ValueError("variant archive scope")
        for name,data in payloads.items():
            if z.read(name)!=data:raise ValueError("variant bytes mismatch")
    return {"status":"SOURCE_OFFICE_METADATA_VARIANCE_VERIFIED","valid":True,"raw_source_matches_original":False,
        "profile":PROFILE,"sha256":expected["source_tree_sha256"],"canonical_sha256":expected["canonical_tree_sha256"],
        "file_count":expected["source_file_count"],"total_bytes":expected["source_total_bytes"],
        "supplement_path":str(path.relative_to(unit)),"supplement_sha256":sha(path.read_bytes())}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("command",choices=["prepare","verify"])
    p.add_argument("--unit-root",type=Path,required=True);p.add_argument("--task-id",required=True)
    p.add_argument("--output-root",type=Path);p.add_argument("--supplement",type=Path);a=p.parse_args()
    unit=a.unit_root.resolve(strict=True)
    if a.command=="prepare":
        if a.output_root is None:p.error("prepare requires --output-root")
        result=prepare(unit,a.task_id,a.output_root)
    else:
        if a.supplement is None:p.error("verify requires --supplement")
        result=verify(unit,a.task_id,a.supplement)
    print(json.dumps(result,ensure_ascii=False))
if __name__=="__main__":main()
