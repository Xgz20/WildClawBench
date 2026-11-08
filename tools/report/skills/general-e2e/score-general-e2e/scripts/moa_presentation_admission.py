"""Prove an unmapped native UI projection from complete frozen SDK evidence."""
from __future__ import annotations
import hashlib,json,os,shutil,subprocess,tempfile
from pathlib import Path
ADMISSION="bound-native-moa-presentation-completeness/v1"
def candidate(execution):
    evidence=execution.get("evidence",{})
    missing=set(evidence.get("missing") or [])
    return (execution.get("harness",{}).get("id")=="doubaowork"
        and evidence.get("completeness")=="partial" and "unmapped-native-message-block" in missing
        and missing <= {"unmapped-native-message-block","resource_metrics_complete_coverage"}
        and all(evidence.get(k) for k in ["trace_index_path","transcript_path","final_response_path"]))
def _sha(b):return hashlib.sha256(b).hexdigest()
def _verifier():
    skill=Path(__file__).resolve().parents[1]
    path=skill/"vendor/e2e-shared/doubaowork/presentation-proof.mjs"
    if path.is_file():return path
    for parent in skill.parents:
        source=parent/"tools/report/e2e-shared/doubaowork/presentation-proof.mjs"
        if (parent/".git").exists() and source.is_file():return source
    raise ValueError("MOA presentation verifier unavailable")
def validate(execution,contract,files):
    if not candidate(execution):raise ValueError("not a projection-only evidence gap")
    node=Path(shutil.which("node") or "").resolve(strict=True)
    if not node.is_file():raise ValueError("Node runtime unavailable")
    version=subprocess.run([str(node),"--version"],capture_output=True,text=True,check=True,timeout=10).stdout.strip()
    if int(version.lstrip("v").split(".")[0])<22:raise ValueError("Node22+ required")
    script=_verifier()
    with tempfile.TemporaryDirectory(prefix="moa-presentation-proof-") as tmp:
        root=Path(tmp)
        for name,body in files.items():
            path=root/name
            if Path(name).is_absolute() or ".." in Path(name).parts:raise ValueError("unsafe source name")
            path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(body)
        record=root/"bound-execution-record.json";record.write_text(json.dumps(execution,ensure_ascii=False),encoding="utf8")
        result=subprocess.run([str(node),str(script),str(root),str(record)],capture_output=True,text=True,encoding="utf8",timeout=60)
        if result.returncode:raise ValueError(result.stderr.strip()[:1500])
        proof=json.loads(result.stdout)
    return {"schema_version":"wildclawbench.native-moa-presentation-admission/v1",
        "identity":execution["identity"],"profile":ADMISSION,
        "record_origin":"deterministic derived proof, not a native event or score",
        "original_execution_changed":False,"original_trace_changed":False,
        "verifier_sha256":_sha(script.read_bytes()),"node":{"path":str(node),"version":version,"sha256":_sha(node.read_bytes())},
        "proof":proof,"files":[{"path":name,"sha256":_sha(body),"size":len(body)} for name,body in sorted(files.items())]}
