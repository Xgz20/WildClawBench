"""Single-task compatibility packages for the existing General and Web Skills."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid
import zipfile

from .artifacts import _protect, copy_stream_readonly, extract_zip, inventory, quarantine_local_metadata, remove_temporary_tree, restore_execution
from .common import E2EError, atomic_json, digest, file_sha256, inside, load_script, read_json, utc_now
from .compatibility import verify_installed
from .engine import load_batch, verify_ready
from .store import BatchStore
from .trace import ADAPTER, ensure_resource_coverage


def _artifact(path: Path, root: Path, *, typed=False):
    row = {"path": path.relative_to(root).as_posix(), "sha256": file_sha256(path), "size": path.stat().st_size}
    if typed:
        row["type"] = "file"
    return row


def _copy(source: Path, target: Path, *, protect=True):
    if target.exists():
        raise E2EError("HANDOFF_COPY_TARGET_EXISTS")
    expected_files = {path.relative_to(source).as_posix() for path in source.rglob("*") if path.is_file()}
    def copy_file(source_file, destination_file):
        with Path(source_file).open("rb") as input_file:
            copy_stream_readonly(input_file, Path(destination_file))
        return str(destination_file)

    shutil.copytree(source, target, copy_function=copy_file if protect else shutil.copyfile)
    if protect:
        _protect(target)
    quarantine_local_metadata(target, expected_files, target.parent / ".local-metadata" / uuid.uuid4().hex)


def _general_inventory(score_root: Path, candidate: Path):
    code = """import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import score_general_e2e
entries,sha=score_general_e2e._inventory_tree(Path(sys.argv[2]))
print(json.dumps({'entries':entries,'sha256':sha},ensure_ascii=False))
"""
    result = subprocess.run([sys.executable, "-X", "utf8", "-c", code, str(score_root / "scripts"), str(candidate)],
                            capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(result.stdout)


def _general_context(batch: Path, temporary: Path, manifest: dict, item: dict, task: dict, unit: dict, ready: dict,
                     restored: Path, verification_skill: Path | None = None):
    assets = manifest["compatibility"]["general"]
    verify_installed(batch, "general", assets)
    installed = inside(batch, assets["installed_skills"])
    prepare = load_script(installed / "prepare-general-e2e-workspaces/scripts/prepare_general_e2e_workspaces.py", "sandbox_frozen_general_prepare")
    dataset = inside(batch, assets["dataset_bundle"])
    if file_sha256(dataset) != assets["dataset_bundle_sha256"]:
        raise E2EError("FROZEN_DATASET_BUNDLE_DRIFT")
    suite = inside(batch, assets["release_suite"])
    if file_sha256(suite) != assets["release_suite_sha256"]:
        raise E2EError("FROZEN_RELEASE_SUITE_DRIFT")
    release = prepare.verify_release_suite(suite)
    catalog = release["catalog"]
    dataset_ref = {**task["dataset"], "bundle_sha256": assets["dataset_bundle_sha256"]}
    release_ref = {"id": catalog["release_id"], "catalog_digest": catalog["catalog_digest"],
                   "catalog_sha256": release["catalog_sha256"], "suite_sha256": release["suite_sha256"]}
    identity = ready["identity"]
    diagnostics = read_json(restored / "collect/evidence/diagnostics.json")
    public_unit = {"unit_id": unit["unit_id"], "task_ids": [task["task_id"]],
                   "harness": {"id": unit["harness"], "platform": "windows-x86_64", "version": diagnostics.get("product_version")},
                   "model": {"requested_id": unit["model"], "reasoning_effort": unit.get("reasoning_effort")},
                   "execution_mode": "automatic"}
    packages = temporary / "packages"
    packages.mkdir()
    with zipfile.ZipFile(dataset) as archive:
        execution_zip, scoring_zip = prepare._unit_packages(archive, task["dataset"]["id"], assets["dataset_manifest"],
            public_unit, identity["batch_id"], dataset_ref, release_ref, catalog, packages)
    unit_root = temporary / "unit"
    extract_zip(execution_zip, unit_root, strip_root=True)
    public_task = unit_root / "execution/tasks" / task["task_id"]
    if file_sha256(public_task / "PROMPT.md") != task["prompt_sha256"]:
        raise E2EError("SCORING_PACKAGE_PROMPT_DRIFT")
    shutil.rmtree(public_task / "workspace")
    _copy(restored / ready["workspace"], public_task / "workspace")
    evidence_relative = f"evidence/tasks/{task['task_id']}/{item['attempt_id']}"
    evidence = unit_root / evidence_relative
    _copy(restored / "trace", evidence / "trace")
    _copy(public_task / "workspace", evidence / "candidate/workspace")
    score_root = installed / "score-general-e2e"
    candidate = _general_inventory(score_root, evidence / "candidate/workspace")
    source = _general_inventory(score_root, public_task / "workspace")
    if candidate["sha256"] != source["sha256"]:
        raise E2EError("CANDIDATE_COPY_DRIFT")
    entries, candidate_sha = candidate["entries"], candidate["sha256"]
    file_count = sum(row["type"] != "directory" for row in entries)
    total_bytes = sum(row["size"] for row in entries if row["type"] != "directory")
    frozen_at = utc_now()
    artifact = {"schema_version": "wildclawbench.general-e2e-candidate-artifact/v1", "identity": identity,
                "hash_algorithm": "wildclawbench.workspace-tree-sha256/v1", "expected_sha256": candidate_sha,
                "frozen_at": frozen_at, "policy": {"schema_version": "wildclawbench.general-e2e-candidate-policy/v1",
                    "policy_source": "sealed-agentcube-execution", "ignored_directories": [], "forbidden_directories": []},
                "runtime_directory_policy": None,
                "source_workspace": {"path": f"execution/tasks/{task['task_id']}/workspace", "sha256": source["sha256"],
                    "file_count": file_count, "total_bytes": total_bytes,
                    "snapshot_before_sha256": source["sha256"], "snapshot_after_stability_sha256": source["sha256"],
                    "snapshot_after_copy_sha256": source["sha256"], "stability_window_milliseconds": 0,
                    "ignored_runtime_directories": [], "forbidden_directories": []},
                "candidate": {"path": evidence_relative + "/candidate/workspace", "sha256": candidate_sha,
                              "file_count": file_count, "total_bytes": total_bytes}, "entries": entries}
    atomic_json(evidence / "candidate/candidate-artifact.json", artifact)
    proof = read_json(evidence / "trace/bindings/execution-proof.json")
    atomic_json(evidence / "execution/automation-state.json", proof)
    shutil.copyfile(public_task / "PROMPT.md", evidence / "execution/PROMPT.md")
    resources = read_json(restored / "resource-metrics.json")
    if resources["collection"]["collector"] == ADAPTER and "coverage" not in resources["collection"]:
        ensure_resource_coverage(resources)
        resources["collection"]["warnings"].append(
            "agentcube-resource-coverage/v1 derived from sealed per-field status; source_sha256="
            + file_sha256(restored / "resource-metrics.json"))
    atomic_json(evidence / "resource-metrics.json", resources)
    (evidence / "metadata").mkdir(exist_ok=True)
    shutil.copyfile(restored / "metadata/report.json", evidence / "metadata/report.json")
    shutil.copyfile(restored / "final-response.md", evidence / "final-response.md")
    atomic_json(evidence / "process-cleanup.json", {**proof["process_cleanup"], "identity": identity,
                                                  "candidate_workspace": f"execution/tasks/{task['task_id']}/workspace"})
    binding = proof["native_binding"]
    # Preserve native clock values. Flow duration stays unavailable because the
    # guest timestamps have not been calibrated against the controller clock.
    native_path = next((evidence / "trace/raw").glob("rollout-*.jsonl"))
    native_rows = [json.loads(line) for line in native_path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    users = [row for row in native_rows if row.get("payload", {}).get("type") == "user_message"]
    terminals = [row for row in native_rows if row.get("payload", {}).get("type") == "task_complete"]
    record = {"schema_id": "urn:wildclawbench:schema:general-e2e:execution-record:v1", "schema_version": 1,
              "identity": identity, "dataset": task["dataset"], "phase": "COMPLETED", "harness": public_unit["harness"],
              "model": {"requested_id": unit["model"], "actual_id": ready["actual_model"],
                        "reasoning_effort": ready["reasoning_effort"], "verification_status": "verified"},
              "execution": {"business_status": "completed", "started_at": users[0].get("timestamp"),
                            "finished_at": terminals[0].get("timestamp"), "duration_seconds": None,
                            "agent_duration_seconds": (binding["native_duration_ms"] / 1000
                                if isinstance(binding.get("native_duration_ms"), (int, float)) else None), "error": None},
              "prompt": {"sha256": task["prompt_sha256"], "send_status": "sent", "sent_at": users[0].get("timestamp")},
              "session": {key: binding["session"][key] for key in ("thread_id", "turn_id", "session_id", "cwd")},
              "evidence": {"completeness": "partial", "transcript_path": evidence_relative + "/trace/transcript.jsonl",
                           "trace_index_path": evidence_relative + "/trace/trace-index.json",
                           "final_response_path": evidence_relative + "/final-response.md",
                           "missing": ["resource_metrics_complete_coverage"]},
              "candidate": {"path": artifact["candidate"]["path"], "frozen_sha256": candidate_sha,
                            "frozen_at": frozen_at, "drift_status": "stable"},
              "resource_metrics_path": evidence_relative + "/resource-metrics.json",
              "human_assistance": {"mode": "automatic", "operation_count": 0, "semantic_intervention_count": 0}}
    record["session"]["verified"] = True
    atomic_json(evidence / "execution-record.json", record)
    artifacts = [_artifact(path, unit_root, typed=True) for path in evidence.rglob("*")
                 if path.is_file() and path not in {evidence / "evidence-manifest.json", evidence / "execution-record.json"}]
    artifacts.sort(key=lambda row: row["path"])
    evidence_manifest = {"schema_version": "wildclawbench.general-e2e-evidence-manifest/v1", "identity": identity,
                         "dataset": task["dataset"], "collected_at": frozen_at,
                         "collection": {"collector": "agentcube-controller-v2", "version": "0.1.0", "stage_status": "completed",
                                        "business_status": "completed", "process_cleanup_path": evidence_relative + "/process-cleanup.json",
                                        "candidate_artifact_path": evidence_relative + "/candidate/candidate-artifact.json",
                                        "execution_record_path": evidence_relative + "/execution-record.json"}, "artifacts": artifacts}
    atomic_json(evidence / "evidence-manifest.json", evidence_manifest)
    receipt_paths = [evidence / relative for relative in ("candidate/candidate-artifact.json", "evidence-manifest.json",
                                                        "execution-record.json", "process-cleanup.json")]
    receipt = {"schema_id": "urn:wildclawbench:schema:general-e2e:receipt:v1", "schema_version": 1,
               "scope": {"batch_id": identity["batch_id"], "unit_id": identity["unit_id"]}, "dataset": task["dataset"],
               "stage": "collect-evidence", "status": "completed", "created_at": frozen_at,
               "task_ids": [task["task_id"]], "tasks": [{"task_id": task["task_id"], "attempt_id": item["attempt_id"], "status": "completed"}],
               "artifacts": [_artifact(path, unit_root) for path in receipt_paths],
               "integrity": {"scope_matches": True, "identities_match": True, "hashes_verified": True, "valid": True}, "error": None}
    atomic_json(unit_root / "receipts/collect-evidence-receipt.json", receipt)
    judge = {"protocol": "codex-agent-judge-v1", "model": "gpt-6.1-sol", "reasoning_effort": "high"}
    atomic_json(temporary / "report-config.json", {"schema_version": "wildclawbench.general-e2e-report-config/v1",
                "batch_id": identity["batch_id"], "dataset": dataset_ref, "release": release_ref,
                "judge": judge, "report": {"title": "General E2E 沙箱执行评测"}, "units": [public_unit]})
    from eval_general_e2e.contracts.validator import validate_contract
    for value in (record, receipt, read_json(evidence / "trace/trace-index.json"), read_json(evidence / "resource-metrics.json")):
        validate_contract(value)
    collector = installed / "collect-general-e2e/scripts/finalize_astronstudio_execution.mjs"
    verifier = None
    if verification_skill is not None:
        metadata = read_json(verification_skill / "skill-metadata.json")
        if metadata.get("name") != "collect-general-e2e" or metadata.get("contract_version") != "general-e2e-contract-v1":
            raise E2EError("SUPPLEMENTAL_COLLECTOR_INCOMPATIBLE")
        inventory(verification_skill)
        copied = temporary / "verification-skill/collect-general-e2e"
        _copy(verification_skill, copied, protect=False)
        verifier = {"path": "verification-skill/collect-general-e2e", "version": metadata["version"],
                    "inventory_sha256": digest(inventory(copied)), "source": str(verification_skill)}
        collector = copied / "scripts/finalize_astronstudio_execution.mjs"
    verification = subprocess.run(["node", str(collector), "--verify-only", "--unit-root", str(unit_root), "--task-id", task["task_id"]],
                                  capture_output=True, text=True, encoding="utf-8")
    if verification.returncode != 0:
        raise E2EError("GENERAL_HANDOFF_VERIFICATION_FAILED: " + verification.stderr[-2000:])
    return {"scene": "general", "unit_root": "unit", "execution_record": (evidence / "execution-record.json").relative_to(temporary).as_posix(),
            "scoring_package": scoring_zip.relative_to(temporary).as_posix(), "report_config": "report-config.json",
            "installed_skills": str(installed),
            "supplemental_verifier": verifier,
            "verification": {"status": json.loads(verification.stdout)["status"], "candidate_sha256": candidate_sha}}


def _web_context(batch: Path, temporary: Path, manifest: dict, item: dict, task: dict, unit: dict, ready: dict,
                 restored: Path, verification_skill: Path | None = None):
    if verification_skill is not None:
        raise E2EError("SUPPLEMENTAL_GENERAL_COLLECTOR_REQUIRES_GENERAL_SCENE")
    assets = manifest["compatibility"]["web"]
    verify_installed(batch, "web", assets)
    installed = inside(batch, assets["installed_skills"])
    prepare = load_script(installed / "prepare-web-e2e-workspaces/scripts/prepare_web_e2e_workspaces.py", "sandbox_frozen_web_prepare")
    scoring_prepare = load_script(installed / "prepare-web-e2e-workspaces/scripts/prepare_scoring_workspace.py", "sandbox_frozen_web_scoring_prepare")
    source = read_json(inside(batch, task["input_root"]) / "private-scoring/web-task-source.json")
    identity = ready["identity"]
    package = temporary / "unit"
    execution_task = package / "execution/tasks" / task["task_id"]
    _copy(restored / ready["workspace"], execution_task / "workspace")
    public_prompt = inside(batch, task["input_root"]) / "execution/PROMPT.md"
    shutil.copyfile(public_prompt, execution_task / "PROMPT.md")
    _copy(restored / "trace", execution_task / "trace")
    shutil.copyfile(restored / "final-response.md", execution_task / "final-response.md")
    shutil.copyfile(restored / "resource-metrics.json", execution_task / "resource-metrics.json")
    (execution_task / "metadata").mkdir()
    shutil.copyfile(restored / "metadata/report.json", execution_task / "metadata/report.json")
    resources = read_json(restored / "resource-metrics.json")
    record = prepare.execution_record(identity["batch_id"], unit["harness"], "AstronStudio", ready["actual_model"], task["task_id"])
    record["execution"].update(status="completed", agent_duration_seconds=resources["metrics"]["timing"]["agent_duration_seconds"]["value"])
    record["usage"].update({key: metric["value"] for group in ("usage", "requests")
                            for key, metric in resources["metrics"][group].items()})
    record["tools"]["call_count"] = resources["metrics"]["tools"]["call_count"]["value"]
    record["usage"]["collection"] = {
        **resources["collection"], "schema_version": "wildclawbench.web-e2e-resource-collection/v1",
        "scope": "primary-task", "session_id": ready["native_session"]["session_id"],
        "attempt_id": item["attempt_id"], "background_operations": [],
        "metrics": {key: {"status": metric["status"], "basis": metric["basis"]}
                    for group in resources["metrics"].values() for key, metric in group.items()}}
    record["artifacts"]["harness_transcript"] = "trace/transcript.jsonl"
    record["reasoning_effort"] = ready["reasoning_effort"]
    atomic_json(execution_task / "execution_record.json", record)
    snapshot = scoring_prepare.snapshot_workspace(execution_task / "workspace")
    if snapshot["forbidden_directories"]:
        raise E2EError("WEB_CANDIDATE_FORBIDDEN_DIRECTORIES")
    web_manifest = {"schema_version": prepare.SCHEMA_VERSION, "skill_version": prepare.SKILL_VERSION,
                    "batch_id": identity["batch_id"], "source_revision": manifest["source_revision"],
                    "metric_profile": task["metric_profile"], "created_at": utc_now(),
                    "scoring_skill": prepare.load_score_skill_metadata(installed / "score-web-e2e"),
                    "execution_record_included": True,
                    "harness": {"id": unit["harness"], "display_name": "AstronStudio"},
                    "scoring_archive": "scoring.zip", "tasks": [{"task_id": task["task_id"], "task_name": task["name"],
                        "difficulty": source["difficulty"], "metric_profile": task["metric_profile"],
                        "execution_dir": "execution/tasks/" + task["task_id"],
                        "task_sha256": source["task_sha256"], "workspace_exec_sha256": source["workspace_sha256"],
                        "prompt_rewrite_map": task["prompt_mapping"],
                        "prompt_file": f"execution/tasks/{task['task_id']}/PROMPT.md"}]}
    atomic_json(package / "manifest.json", web_manifest)
    selected = {"mode": "explicit", "requested_model": unit["model"], "actual_model": ready["actual_model"],
                "method": "bound-native-turn-context"}
    receipt = {"schema_version": "wildclawbench.web-e2e-execution-receipt/v1", "batch_id": identity["batch_id"],
               "harness": web_manifest["harness"], "generated_at": utc_now(), "run_id": item["attempt_id"],
               "model": {"id": ready["actual_model"], "display_name": ready["actual_model"]},
               "runtime_directory_policy": scoring_prepare.runtime_directory_policy(),
               "integrity": {"valid": True}, "tasks": [{"task_id": task["task_id"], "attempt_id": item["attempt_id"],
                    "automation_phase": "SUCCEEDED", "execution_status": "completed", "model_selection": selected,
                    "workspace": {"final_sha256": snapshot["sha256"]}}]}
    atomic_json(package / "execution-receipt.json", receipt)
    overlay = temporary / "overlay"
    private = overlay / "score/tasks" / task["task_id"] / "private-scoring"
    private.mkdir(parents=True)
    contract = prepare.task_contract(identity["batch_id"], manifest["source_revision"], unit["harness"], "AstronStudio", source)
    atomic_json(private / "task_contract.json", contract)
    fixtures = inside(batch, task["input_root"]) / "private-scoring/fixtures"
    if fixtures.is_dir():
        _copy(fixtures, private / "fixtures")
    (private.parent / ".web-e2e-scoring-ready").write_text(identity["batch_id"] + "\n" + task["task_id"] + "\n", encoding="utf-8")
    with zipfile.ZipFile(package / "scoring.zip", "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(overlay.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(overlay).as_posix())
    scoring_prepare.prepare_scoring_workspace(package, package / "scoring.zip")
    shutil.rmtree(overlay)
    return {"scene": "web", "unit_root": "unit", "installed_skills": str(installed),
            "score_task_root": f"unit/score/tasks/{task['task_id']}", "scoring_package": "unit/scoring.zip",
            "candidate_sha256": snapshot["sha256"]}


def prepare_scoring_context(batch: Path, key: str, claim_id: str, *, verification_skill: Path | None = None) -> dict:
    manifest = load_batch(batch)
    store = BatchStore(batch)
    item = store.get(key)
    claims = [row for row in store.scoring_rows() if row["key"] == key and row.get("claim_id") == claim_id]
    if len(claims) != 1:
        raise E2EError("SCORING_CLAIM_MISMATCH")
    claim = claims[0]
    ready = verify_ready(batch, item, manifest)
    unit = next(unit for unit in manifest["units"] if unit["unit_id"] == item["unit_id"])
    task = next(task for task in manifest["tasks"] if task["task_id"] == item["task_id"])
    execution = inside(batch, item["execution_root"])
    destination = execution.parent.parent / "scoring" / ("score-" + claim_id)
    if destination.exists():
        if verification_skill is not None:
            raise E2EError("EXISTING_CONTEXT_VERIFIER_IS_ALREADY_FROZEN")
        source = read_json(destination / "source.json")
        if source.get("backup_sha256") != ready["backup_sha256"] or source.get("claim_id") != claim_id:
            raise E2EError("EXISTING_SCORING_CONTEXT_CONFLICT")
        result = {"context_root": str(destination), **read_json(destination / "handoff.json")}
        store.score_update(key, claim_id, claim["phase"], context=result)
        return result
    result = _materialize_context(batch, manifest, item, task, unit, ready, destination, claim_id,
                                  verification_skill=verification_skill)
    store.score_update(key, claim_id, "CLAIMED", context=result)
    return result


def export_scoring_context(batch: Path, key: str, destination: Path) -> dict:
    manifest = load_batch(batch)
    item = BatchStore(batch).get(key)
    ready = verify_ready(batch, item, manifest)
    unit = next(unit for unit in manifest["units"] if unit["unit_id"] == item["unit_id"])
    task = next(task for task in manifest["tasks"] if task["task_id"] == item["task_id"])
    supplemental = None
    claims = [row for row in BatchStore(batch).scoring_rows() if row["key"] == key and row.get("context")]
    if claims:
        context = claims[0]["context"]
        verifier = context.get("supplemental_verifier")
        if verifier:
            supplemental = inside(Path(context["context_root"]), verifier["path"])
            if digest(inventory(supplemental)) != verifier["inventory_sha256"]:
                raise E2EError("SUPPLEMENTAL_COLLECTOR_DRIFT")
    return _materialize_context(batch, manifest, item, task, unit, ready, destination, None,
                                verification_skill=supplemental)


def _materialize_context(batch, manifest, item, task, unit, ready, destination, claim_id, *, verification_skill=None):
    execution = inside(batch, item["execution_root"])
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name("." + destination.name + ".preparing-" + uuid.uuid4().hex)
    temporary.mkdir()
    try:
        restored = temporary / "execution-source"
        restore_execution(execution, restored)
        method = _general_context if task["scene"] == "general" else _web_context
        result = method(batch, temporary, manifest, item, task, unit, ready, restored, verification_skill)
        source = {"schema": "wildclawbench.task-execution-handoff/v1", "identity": ready["identity"],
                  "parent_batch_id": batch.name, "parent_batch_sha256": digest(manifest),
                  "parent_task_ids": unit["task_ids"], "run_index": item["run_index"],
                  "backup_sha256": ready["backup_sha256"], "claim_id": claim_id,
                  "supplemental_verifier": result.get("supplemental_verifier"),
                  "execution_ready_sha256": file_sha256(execution / "execution-ready.json")}
        atomic_json(temporary / "source.json", source)
        atomic_json(temporary / "handoff.json", result)
        temporary.rename(destination)
    except BaseException:
        if temporary.exists():
            remove_temporary_tree(temporary)
        raise
    result = {"context_root": str(destination), **result}
    return result
