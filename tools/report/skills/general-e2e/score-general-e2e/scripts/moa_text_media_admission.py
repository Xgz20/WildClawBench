"""Admit two reviewed text-sufficient executions without treating missing images as observed."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ADMISSION = "reviewed-native-moa-text-with-missing-media/v1"
AUTHORIZATION = "reviewed-media-authorization.json"
VERIFIER = "reviewed-text-media-proof.mjs"
CASES = {
    "01_Information_Search_Organization_task_015_boc_mortgage_repricing_comparison": (
        "native-sdk-tool-image-source-http-blocked", "origin-http-security-block", 1,
        "0b747db7-c8c5-4c40-862b-7ea12e917b4b", 16, 14,
        ("https://www.boc.cn/pbservice/bi2/202410/t20241012_25170827.html", "重定价日", "不变")),
    "01_Information_Search_Organization_task_018_urban_rural_cpi_sign_screening": (
        "native-sdk-tool-image-private-source-not-requested", "private-source-not-requested", 2,
        "5a4d1891-121b-4262-a16d-051b51290c86", 59, 47,
        ("季度同比价格指数等于该季度各月定基价格指数的简单算术平均",
         "与上年同期各月定基价格指数的简单算术平均的比值",
         "各月同比价格指数的简单算术平均近似计算")),
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def candidate(execution):
    case = CASES.get(execution.get("identity", {}).get("task_id"))
    evidence = execution.get("evidence", {})
    return bool(case and execution.get("harness", {}).get("id") == "doubaowork"
                and execution.get("phase") == "COMPLETED"
                and execution.get("execution", {}).get("business_status") == "completed"
                and execution.get("session", {}).get("verified") is True
                and evidence.get("completeness") == "partial"
                and set(evidence.get("missing") or ()) == {case[0], "resource_metrics_complete_coverage"}
                and all(evidence.get(key) for key in ("trace_index_path", "transcript_path", "final_response_path")))


def _verifier():
    skill = Path(__file__).resolve().parents[1]
    packaged = skill / "vendor/e2e-shared/doubaowork" / VERIFIER
    if packaged.is_file():
        return packaged
    for parent in skill.parents:
        source = parent / "tools/report/e2e-shared/doubaowork" / VERIFIER
        if (parent / ".git").exists() and source.is_file():
            return source
    raise ValueError("reviewed native media verifier unavailable")


def validate(execution, record_bytes, contract_bytes, files):
    _require(candidate(execution), "unexpected native media evidence scope")
    identity = execution["identity"]
    gap, reason, images, call_id, line, call_count, anchors = CASES[identity["task_id"]]
    authority = json.loads(files[AUTHORIZATION])
    _require(authority.get("schema_version") == ADMISSION and bool(authority.get("authorization_reference")),
             "reviewed media authorization missing")
    rows = [r for r in authority["tasks"] if r["identity"] == identity]
    _require(len(rows) == 1, "execution not uniquely authorized")
    row = rows[0]
    index = json.loads(files["trace-index.json"])
    trajectory = files["raw/trajectory.jsonl"]
    _require(row["execution_record_sha256"] == sha(record_bytes)
             and row["contract_sha256"] == sha(contract_bytes)
             and row["trace_index_sha256"] == sha(files["trace-index.json"])
             and row["trajectory_sha256"] == sha(trajectory), "reviewed media binding drift")
    _require(index["completeness"]["missing"] == [gap], "unexpected missing trace scope")
    raw_lines = trajectory.splitlines()
    affected = json.loads(raw_lines[line - 1])
    _require(affected.get("tool_call_id") == call_id and len(affected["image_link_list"]) == images,
             "unexpected affected tool result")
    supporting_lines = [json.loads(raw_lines[13])] if images == 1 else [affected]
    _require(all(token in supporting_lines[0]["content"] for token in anchors),
             "required retained official text anchor missing")
    script = _verifier()
    node = shutil.which("node")
    _require(node, "Node runtime unavailable")
    with tempfile.TemporaryDirectory(prefix="moa-reviewed-text-media-") as directory:
        root = Path(directory)
        for name, data in files.items():
            relative = Path(name)
            _require(not relative.is_absolute() and ".." not in relative.parts, "invalid evidence path")
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        record = root / "bound-execution.json"
        record.write_bytes(record_bytes)
        run = subprocess.run([node, str(script), str(root), str(record)], capture_output=True, timeout=60)
        _require(run.returncode == 0, run.stderr.decode(errors="replace")[-1800:])
        proof = json.loads(run.stdout)
    _require(proof["native_call_count"] == call_count and len(proof["missing_media"]) == images
             and all(m["reason"] == reason and m["call_id"] == call_id and m["result_line"] == line
                     for m in proof["missing_media"]), "unexpected media or call coverage")
    return {
        "schema_version": ADMISSION, "profile": ADMISSION, "identity": identity,
        "authorization_reference": authority["authorization_reference"], "proof": proof,
        "original_evidence_completeness": "partial", "original_missing": execution["evidence"]["missing"],
        "criterion_evidence_audit": row["criterion_evidence_audit"],
        "scoreability": "review retained text and all available originals; retain unresolved if a required image dependency emerges",
        "unavailable_images_count_as_observed": False, "original_execution_changed": False,
        "verifier_sha256": sha(script.read_bytes()),
        "files": [{"path": name, "sha256": sha(data), "size": len(data)} for name, data in sorted(files.items())],
    }
