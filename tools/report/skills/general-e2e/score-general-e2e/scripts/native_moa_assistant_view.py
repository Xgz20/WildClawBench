"""Hash-bound native assistant rows for semantic review; never rewrite a trace."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

PROFILE = "doubaowork-native-moa-sdk-model-protocol-2.35.15/v1"
VIEW_PROFILE = "bound-native-moa-assistant-rows/v1"


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _bytes(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError("native source is not an ordinary file")
    return path.read_bytes()


def materialize(root: Path, manifest: dict, *, create: bool) -> list[Path]:
    target = root / "native-compatibility"
    view = target / "moa-sdk-assistant-lines.jsonl"
    audit = target / "moa-sdk-assistant-view-audit.json"
    trace = root / "trace"
    index_path = trace / "trace-index.json"
    if not manifest.get("trace_bundle") or not index_path.is_file():
        if target.exists():
            raise ValueError("native view exists without its frozen trace")
        return []
    index = json.loads(_bytes(index_path))
    if PROFILE not in index.get("normalization", {}).get("compatibility_profiles", []):
        if target.exists():
            raise ValueError("native view exists for an unsupported trace")
        return []
    if not create and not target.exists():
        return []
    raw_path = trace / "raw/trajectory.jsonl"
    proof_path = trace / "raw/native-moa-sdk-protocol.json"
    refs = {row["path"]: row for row in index["raw_trace"]}
    raw, proof_bytes = _bytes(raw_path), _bytes(proof_path)
    for name, value in [("raw/trajectory.jsonl", raw), ("raw/native-moa-sdk-protocol.json", proof_bytes)]:
        if refs.get(name, {}).get("sha256") != _sha(value) or refs[name]["size"] != len(value):
            raise ValueError("frozen native source digest mismatch")
    proof = json.loads(proof_bytes)
    if proof.get("profile") != PROFILE or proof.get("source_sha256") != _sha(raw):
        raise ValueError("native SDK proof does not bind the raw trajectory")
    expected = {k: manifest["identity"][k] for k in ["batch_id", "unit_id", "task_id"]}
    expected["attempt_id"] = manifest["identity"]["execution_attempt_id"]
    if index["identity"] != expected:
        raise ValueError("native view task identity mismatch")
    rows, locations = [], []
    for number, line in enumerate(raw.splitlines(keepends=True), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("role") == "assistant":
            rows.append(line)
            locations.append({"view_line": len(rows), "raw_line": number, "raw_line_sha256": _sha(line)})
    body = b"".join(rows)
    document = {"profile": VIEW_PROFILE, "identity": manifest["identity"], "content_origin": "frozen-native-assistant-rows",
                "original_execution_evidence_changed": False, "raw_path": "trace/raw/trajectory.jsonl",
                "raw_sha256": _sha(raw), "sdk_proof_sha256": _sha(proof_bytes), "view_sha256": _sha(body),
                "assistant_row_count": len(rows), "locations": locations,
                "purpose": "Read original assistant content stored beside tool_calls before making process-absence claims."}
    audit_bytes = (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if not target.exists():
        if not create:
            return []
        target.mkdir()
        view.write_bytes(body)
        audit.write_bytes(audit_bytes)
        view.chmod(0o400)
        audit.chmod(0o400)
    if target.is_symlink() or {p.name for p in target.iterdir()} != {view.name, audit.name}:
        raise ValueError("native assistant view member drift")
    if _bytes(view) != body or _bytes(audit) != audit_bytes:
        raise ValueError("native assistant view content drift")
    return [view, audit]
