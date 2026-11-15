"""Explicit recovery of a completed native turn after controller transport loss.

This never repeats a prompt, edits a candidate, or manufactures a WGUI RunReport.
The separate terminal source and the original transport error remain visible.
"""
from __future__ import annotations

import io
import json
from pathlib import Path
import zipfile

from .artifacts import copy_stream_readonly
from .backend import GUEST_WORKSPACE, NATIVE_ROOT
from .common import E2EError, atomic_json, file_sha256, inside, read_json, relative_path, utc_now
from .engine import _publish, load_batch, verify_ready
from .store import BatchStore, controller_lock
from .trace import normalize_rollout, windows_equal


SCHEMA = "wildclawbench.agentcube-native-terminal-recovery/v1"


def _require(ok, code):
    if not ok:
        raise E2EError(code)


def validate_capsule(capsule: Path, post_path: Path, *, expected_sha256: str, row: dict):
    _require(file_sha256(capsule) == expected_sha256, "RECOVERY_CAPSULE_SHA_MISMATCH")
    _require(capsule.stat().st_size <= 256 * 1024**2, "RECOVERY_CAPSULE_TOO_LARGE")
    post = read_json(post_path)
    _require(post.get("schema") == "astudio.original-session-post-task-cleanup/v1"
             and post.get("original_archive_sha256") == expected_sha256
             and post.get("sut_prompt_repeated") is False, "RECOVERY_POST_SOURCE_INVALID")
    with zipfile.ZipFile(capsule) as archive:
        _require(len(archive.infolist()) <= 10000
                 and sum(i.file_size for i in archive.infolist()) <= 1024**3, "RECOVERY_EXPANSION_LIMIT")
        members = {}
        for info in archive.infolist():
            name = info.filename.replace("\\", "/")
            relative_path(name)
            _require(name not in members and not info.is_dir()
                     and not (info.external_attr >> 16) & 0o170000 == 0o120000,
                     "RECOVERY_MEMBER_INVALID")
            members[name] = info
        _require("recovery-manifest.json" in members, "RECOVERY_MANIFEST_MISSING")
        manifest = json.loads(archive.read(members["recovery-manifest.json"]).decode("utf-8-sig"))
        _require(manifest.get("schema") == "astudio.original-session-readonly-recovery/v1"
                 and manifest.get("sut_prompt_repeated") is False
                 and manifest.get("application_restarted") is False
                 and manifest.get("quiet_observed_milliseconds", 0) >= 5000,
                 "RECOVERY_MANIFEST_INVALID")
        for document in (manifest, post):
            _require(document.get("session_id") == row.get("session_id")
                     and document.get("original_execution_attempt") == row["attempt_id"],
                     "RECOVERY_EXECUTION_IDENTITY_MISMATCH")
        files = manifest.get("files", [])
        _require(files and len({f["path"] for f in files}) == len(files)
                 and set(members) == {"recovery-manifest.json"} | {f["path"] for f in files},
                 "RECOVERY_MEMBER_SET_MISMATCH")
        post_files = {f["path"]: f for f in post.get("files", [])}
        _require(len(post_files) == len(files), "RECOVERY_POST_FILE_SET_MISMATCH")
        data = {}
        for f in files:
            name = f["path"]
            _require(name.startswith(("workspace/project/", "native/")), "RECOVERY_FILE_SCOPE")
            source_root, prefix = ((GUEST_WORKSPACE, "workspace/project/")
                                   if name.startswith("workspace/project/") else (NATIVE_ROOT, "native/"))
            _require(windows_equal(f["source"], source_root + "\\" + name[len(prefix):].replace("/", "\\")),
                     "RECOVERY_GUEST_SOURCE_PATH_MISMATCH")
            b = archive.read(members[name])
            import hashlib
            _require(len(b) == f["size"] and hashlib.sha256(b).hexdigest() == f["sha256"]
                     and post_files.get(name) == {k: f[k] for k in ("path", "size", "sha256")},
                     "RECOVERY_ORIGINAL_FILE_DRIFT")
            data[name] = b
    native = [f for f in files if f["path"].startswith("native/")]
    _require(len(native) == 1 and native[0]["path"].endswith(".jsonl"), "RECOVERY_NATIVE_AMBIGUOUS")
    source = native[0]["source"]
    previous = [f for path, f in row.get("native_before", {}).items() if windows_equal(path, source)]
    _require(not previous or previous[0].get("Sha256") != native[0]["sha256"],
             "RECOVERY_NATIVE_NOT_CHANGED_SINCE_DISPATCH")
    cleanup = post.get("cleanup", {})
    _require(cleanup.get("schema") == "wildclawbench.agentcube-process-cleanup/v1"
             and cleanup.get("phase") == "completed" and cleanup.get("success") is True
             and cleanup.get("supported") is True and cleanup.get("after") == []
             and cleanup.get("quiet_observed_milliseconds", 0) >= 5000
             and windows_equal(cleanup.get("workspace", ""), GUEST_WORKSPACE),
             "RECOVERY_CLEANUP_UNVERIFIED")
    root = next((p for p in cleanup.get("before", []) if p["pid"] == cleanup.get("root_pid")), None)
    _require(root and root["name"].lower() == "astudio.exe" and root.get("path") and root.get("created"),
             "RECOVERY_PROCESS_ROOT_UNVERIFIED")
    return manifest, post, data, native[0]


def recover_native_terminal(root: Path, *, execution_key: str, capsule: Path,
                            post_cleanup: Path, expected_sha256: str) -> dict:
    with controller_lock(root):
        manifest = load_batch(root)
        store = BatchStore(root)
        row = store.get(execution_key)
        _require(row["phase"] == "NEEDS_ATTENTION" and row.get("dispatch_armed_at")
                 and row.get("session_id"), "RECOVERY_EXECUTION_NOT_ELIGIBLE")
        execution = inside(root, row["execution_root"])
        _require(not (execution / "original").exists() and not (execution / "execution-ready.json").exists(),
                 "RECOVERY_ALREADY_SEALED")
        recovered, post, files, native = validate_capsule(
            capsule, post_cleanup, expected_sha256=expected_sha256, row=row)
        task = next(t for t in manifest["tasks"] if t["task_id"] == row["task_id"])
        unit = next(u for u in manifest["units"] if u["unit_id"] == row["unit_id"])
        staging = execution / "staging"
        identity = {"batch_id": root.name + f"-r{row['run_index']:04d}", "unit_id": row["unit_id"],
                    "task_id": row["task_id"], "attempt_id": row["attempt_id"]}
        report = {"schema": SCHEMA, "status": "completed", "terminal_source": "original-native-task_complete",
                  "controller_run_report_available": False, "controller_error": row.get("error"),
                  "capsule_sha256": expected_sha256, "recovered_at": utc_now(),
                  "session_id": row["session_id"], "attempt_id": row["attempt_id"],
                  "sut_prompt_repeated": False}
        native_path = staging / "native/recovered" / Path(native["path"]).name
        native_path.parent.mkdir(parents=True, exist_ok=True)
        with io.BytesIO(files[native["path"]]) as stream:
            copy_stream_readonly(stream, native_path)
        binding = normalize_rollout(native_path, identity=identity,
            prompt=(inside(root, task["input_root"]) / "execution/PROMPT.md").read_text(encoding="utf-8"),
            guest_cwd=GUEST_WORKSPACE, requested_model=unit["model"],
            requested_effort=unit.get("reasoning_effort"), report=report)
        _require(not binding["missing"], "RECOVERY_NATIVE_TRACE_INCOMPLETE")
        collect = staging / "collect/workspace"
        _require(not collect.exists(), "RECOVERY_COLLECTION_ALREADY_EXISTS")
        collect.mkdir(parents=True)
        for name, b in files.items():
            if name.startswith("workspace/project/"):
                path = inside(collect, name[len("workspace/project/"):])
                path.parent.mkdir(parents=True, exist_ok=True)
                with io.BytesIO(b) as stream:
                    copy_stream_readonly(stream, path)
        # WGUI diagnostics were not returned. Preserve that absence; the separate
        # bootstrap receipt is evidence for package version, not PE ProductVersion.
        runtime = read_json(staging / "metadata/astudio-runtime.json")
        atomic_json(staging / "collect/evidence/diagnostics.json", {
            "product_version": None, "source": SCHEMA,
            "product_version_warning": "original WGUI collection diagnostics unavailable",
            "runtime_bootstrap_version": runtime.get("version"),
            "runtime_bootstrap_sha256": file_sha256(staging / "metadata/astudio-runtime.json")})
        # These bytes are included in the sealed trace and rechecked independently
        # by the collector. Existing failed controller metadata is left intact.
        proofs = staging / "trace/bindings/recovery"
        proofs.mkdir(parents=True)
        atomic_json(proofs / "source-manifest.json", recovered)
        with post_cleanup.open("rb") as stream:
            copy_stream_readonly(stream, proofs / "post-cleanup.json")
        with capsule.open("rb") as stream:
            copy_stream_readonly(stream, proofs / "original-capsule.zip")
        atomic_json(staging / "metadata/report.json", report, create=True)
        atomic_json(staging / "metadata/native-binding.json", {k:v for k,v in binding.items() if k != "events"})
        atomic_json(staging / "metadata/process-cleanup.json", post["cleanup"])
        recovery = {"schema": SCHEMA, "capsule_sha256": expected_sha256,
                    "source_manifest": "bindings/recovery/source-manifest.json",
                    "post_cleanup": "bindings/recovery/post-cleanup.json",
                    "capsule": "bindings/recovery/original-capsule.zip",
                    "original_controller_error": row.get("error"),
                    "post_task_collection_only": True, "semantic_intervention_count": 0}
        outcome = {"identity": identity, "report": report, "binding": binding,
                   "native_path": native_path.relative_to(staging).as_posix(),
                   "workspace": "collect/workspace", "cleanup": post["cleanup"], "recovery": recovery}
        prior = {"error": row.get("error"), "phase": row["phase"]}
        _publish(root, store, row, manifest, unit, task, outcome)
        store.update(execution_key, "COMPLETED", original_transport_failure=prior,
                     native_terminal_recovery=recovery, error=None, finished_at=utc_now())
        verify_ready(root, store.get(execution_key), manifest)
        return {"identity": identity, "source": SCHEMA, "ready": True,
                "resource_held": store.get(execution_key)["resource_held"],
                "backup_sha256": read_json(execution / "execution-ready.json")["backup_sha256"]}
