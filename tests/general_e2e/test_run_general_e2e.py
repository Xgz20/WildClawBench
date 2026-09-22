from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock
import zipfile


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (
    REPO_ROOT
    / "tools/report/skills/general-e2e/run-general-e2e/scripts/run_general_e2e.py"
)
SPEC = importlib.util.spec_from_file_location("run_general_e2e_tested", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


DATASET_DIGEST = "1" * 64
RELEASE_DIGEST = "2" * 64
TASK_ID = "task-one"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def identity() -> dict:
    return {
        "batch_id": "batch-one",
        "unit_id": "astronstudio-macos",
        "dataset": {
            "id": "general-custom60-v1",
            "digest": DATASET_DIGEST,
            "bundle_sha256": "3" * 64,
        },
        "release": {
            "id": "general-release",
            "catalog_digest": RELEASE_DIGEST,
            "catalog_sha256": "4" * 64,
            "suite_sha256": "5" * 64,
        },
        "task_ids": [TASK_ID],
    }


def unit_manifest() -> dict:
    value = identity()
    unit = {
        "unit_id": value["unit_id"],
        "task_ids": value["task_ids"],
        "harness": {"id": "astronstudio", "platform": "macos", "version": "3.3.1"},
        "model": {"requested_id": "model-one", "reasoning_effort": "high"},
        "execution_mode": "automatic",
    }
    return {
        "schema_id": MODULE.PACKAGE_SCHEMA,
        "schema_version": 1,
        "manifest_kind": "execution",
        "contract_version": MODULE.CONTRACT_VERSION,
        "bundle_protocol": MODULE.BUNDLE_PROTOCOL,
        "batch_id": value["batch_id"],
        "unit_id": value["unit_id"],
        "dataset": value["dataset"],
        "release": value["release"],
        "task_ids": value["task_ids"],
        "unit": unit,
        "tasks": [],
        "required_skills": [],
    }


def batch_manifest() -> dict:
    unit = unit_manifest()["unit"]
    value = identity()
    return {
        "schema_id": MODULE.PACKAGE_SCHEMA,
        "schema_version": 1,
        "manifest_kind": "batch",
        "contract_version": MODULE.CONTRACT_VERSION,
        "bundle_protocol": MODULE.BUNDLE_PROTOCOL,
        "batch_id": value["batch_id"],
        "dataset": value["dataset"],
        "release": value["release"],
        "task_ids": value["task_ids"],
        "units": [unit],
        "required_skills": [],
        "skill_artifacts": [],
        "artifacts": [],
    }


def create_unit(root: Path) -> Path:
    unit = root / "unit"
    write_json(unit / "manifest.json", unit_manifest())
    evidence = unit / "evidence/tasks" / TASK_ID / "exec-001"
    evidence.mkdir(parents=True)
    (evidence / "trace.txt").write_text("trace\n", encoding="utf-8")
    artifact = {
        "path": f"evidence/tasks/{TASK_ID}/exec-001/trace.txt",
        "sha256": sha256_bytes(b"trace\n"),
        "size": len(b"trace\n"),
    }
    receipt = {
        "schema_id": MODULE.RECEIPT_SCHEMA,
        "schema_version": 1,
        "scope": {"batch_id": "batch-one", "unit_id": "astronstudio-macos"},
        "dataset": {"id": "general-custom60-v1", "digest": DATASET_DIGEST},
        "stage": "collect-evidence",
        "status": "completed",
        "created_at": "2026-09-18T00:00:00+00:00",
        "task_ids": [TASK_ID],
        "tasks": [{"task_id": TASK_ID, "attempt_id": "exec-001", "status": "completed"}],
        "artifacts": [artifact],
        "integrity": {
            "scope_matches": True,
            "identities_match": True,
            "hashes_verified": True,
            "valid": True,
        },
        "error": None,
    }
    write_json(unit / "receipts/collect-evidence-receipt.json", receipt)
    return unit


def create_orchestration(root: Path, marker: str, *, nested_attempt: bool = False) -> Path:
    orchestration = root / f"orchestration-{marker}"
    attempt_relative = (
        Path("attempts/unit-one/task-one/orch-001")
        if nested_attempt
        else Path("attempts/orch-001")
    )
    score_path = orchestration / attempt_relative / "score.json"
    score_bytes = (json.dumps({"marker": marker}, sort_keys=True) + "\n").encode()
    score_path.parent.mkdir(parents=True)
    score_path.write_bytes(score_bytes)
    runtime = score_path.parent / "runtime"
    runtime.mkdir()
    (runtime / "must-not-return.txt").write_text("temporary", encoding="utf-8")
    candidate = score_path.parent / "candidate-original/workspace"
    candidate.mkdir(parents=True)
    (candidate / "result.txt").write_text(marker, encoding="utf-8")
    os.symlink("result.txt", candidate / "result-link")
    write_json(
        orchestration / f"execution-records/{TASK_ID}.json",
        {"task_id": TASK_ID, "attempt_id": "exec-001"},
    )
    submission = {
        "schema_id": MODULE.SUBMISSION_SCHEMA,
        "schema_version": 1,
        "scope": {"batch_id": "batch-one", "unit_id": "astronstudio-macos"},
        "dataset": {"id": "general-custom60-v1", "digest": DATASET_DIGEST},
        "created_at": "2026-09-18T00:10:00+00:00",
        "task_count": 1,
        "task_ids": [TASK_ID],
        "tasks": [
            {
                "task_id": TASK_ID,
                "execution_attempt_id": "exec-001",
                "execution_status": "completed",
                "scoring_attempt_id": "orch-001",
                "judge_protocol": "codex-agent-judge-v1",
                "score_status": "valid",
                "score_path": (attempt_relative / "score.json").as_posix(),
                "score_sha256": sha256_bytes(score_bytes),
                "candidate_sha256": "6" * 64,
                "evidence_sha256": "7" * 64,
            }
        ],
        "integrity": {
            "scope_matches": True,
            "identities_match": True,
            "hashes_verified": True,
            "valid": True,
        },
    }
    write_json(orchestration / "submission.json", submission)
    return orchestration


def package_args(unit: Path, orchestration: Path, output: Path) -> argparse.Namespace:
    return argparse.Namespace(
        unit_root=str(unit),
        orchestration_root=str(orchestration),
        output_dir=str(output),
    )


def create_execution_state(unit: Path) -> Path:
    path = unit / f".general-e2e/execution/{TASK_ID}/automation-state.json"
    write_json(
        path,
        {
            "schema_version": MODULE.EXECUTION_STATE_SCHEMA,
            "identity": {
                "batch_id": "batch-one",
                "unit_id": "astronstudio-macos",
                "task_id": TASK_ID,
                "attempt_id": "exec-001",
            },
            "dataset": {"id": "general-custom60-v1", "digest": DATASET_DIGEST},
            "phase": "COMPLETED",
            "prompt": {"send_status": "sent"},
            "send": {"dispatch_attempt_count": 1},
            "execution": {
                "business_status": "completed",
                "finished_at": "2026-09-18T00:00:00+00:00",
            },
        },
    )
    return path


def create_general_execution_state(root: Path, harness: str = "workbuddy", platform: str = "macos") -> tuple[Path, Path]:
    unit = create_unit(root)
    task_root = unit / "execution/tasks" / TASK_ID
    workspace = task_root / "workspace"
    workspace.mkdir(parents=True)
    prompt = task_root / "prompt.md"
    prompt.write_text("Create the requested artifact.\n", encoding="utf-8")
    prompt_digest = sha256_bytes(prompt.read_bytes())
    manifest = unit_manifest()
    manifest["unit"]["harness"] = {"id": harness, "platform": platform, "version": "1.0.0"}
    manifest["tasks"] = [{
        "task_id": TASK_ID,
        "workspace": {"path": workspace.relative_to(unit).as_posix()},
        "prompt": {"path": prompt.relative_to(unit).as_posix(), "sent_sha256": prompt_digest},
    }]
    write_json(unit / "manifest.json", manifest)
    path = create_execution_state(unit)
    document = json.loads(path.read_text(encoding="utf-8"))
    binding = path.parent / "session-binding.json"
    write_json(binding, {"native_session_id": "native-session-1", "cwd": str(workspace), "prompt_sha256": prompt_digest})
    document.update({
        "schema_version": MODULE.GENERAL_EXECUTION_STATE_SCHEMA,
        "driver": {"id": f"{harness}-{platform}", "version": "0.1.0", "harness": harness, "platform": platform},
        "task_root": str(task_root), "candidate_workspace": str(workspace),
        "prompt": {"path": str(prompt), "sha256": prompt_digest, "send_status": "sent", "sent_at": "2026-09-18T00:00:00Z"},
        "session": {"thread_id": None, "turn_id": None, "session_id": "native-session-1", "cwd": str(workspace), "verified": True,
                    "binding_evidence": [{"path": binding.relative_to(unit).as_posix(), "sha256": sha256_bytes(binding.read_bytes()), "size": binding.stat().st_size}]},
        "execution": {"business_status": "completed", "started_at": "2026-09-18T00:00:00Z", "finished_at": "2026-09-18T00:01:00Z", "duration_seconds": 60, "error": None, "cancellation_confirmed": None},
        "human_assistance": {"mode": "automatic", "operation_count": 0, "semantic_intervention_count": 0},
    })
    write_json(path, document)
    MODULE.initialize_state(argparse.Namespace(root=str(unit), scope="unit", stage=["execute,collect-evidence"], input=[]))
    return unit, path


class RunGeneralE2ETests(unittest.TestCase):
    def test_general_adapter_terminal_states_preserve_native_null_ids(self) -> None:
        for harness, platform in (("workbuddy", "macos"), ("qwenwork", "macos"), ("astronstudio", "windows")):
            with self.subTest(harness=harness, platform=platform), tempfile.TemporaryDirectory() as temporary:
                unit, path = create_general_execution_state(Path(temporary), harness, platform)
                result = MODULE.record_execution_states(argparse.Namespace(root=str(unit), state=[str(path)]))
                self.assertEqual(result["state"]["stages"]["execute"], "COMPLETED")
                self.assertEqual(result["state"]["stages"]["collect-evidence"], "PENDING")
                self.assertEqual(result["state"]["artifacts"]["execute"]["states"][0]["sha256"], sha256_bytes(path.read_bytes()))
                self.assertIsNone(json.loads(path.read_text())["session"]["turn_id"])

    def test_general_state_rejects_identity_dispatch_and_binding_failures(self) -> None:
        changes = [
            (("schema_version",), "wildclawbench.general-e2e-other/v1", "SCHEMA_UNSUPPORTED"),
            (("driver", "harness"), "qwenwork", "DRIVER_BINDING"),
            (("driver", "platform"), "windows", "DRIVER_BINDING"),
            (("driver", "version"), "dev", "SHAPE_INVALID"),
            (("identity", "batch_id"), "another", "IDENTITY_MISMATCH"),
            (("identity", "task_id"), "../another", "IDENTITY_MISMATCH"),
            (("dataset", "digest"), "f" * 64, "IDENTITY_MISMATCH"),
            (("phase",), "RUNNING", "NOT_TERMINAL"),
            (("prompt", "sha256"), "f" * 64, "PROMPT_HASH"),
            (("send", "dispatch_attempt_count"), 2, "SHAPE_INVALID"),
            (("send", "dispatch_attempt_count"), True, "SHAPE_INVALID"),
            (("prompt", "send_status"), "uncertain", "DISPATCH_INVARIANT"),
            (("session", "verified"), False, "SESSION_BINDING_UNVERIFIED"),
            (("session", "binding_evidence"), [], "SESSION_BINDING_UNVERIFIED"),
            (("session", "session_id"), None, "SESSION_BINDING_UNVERIFIED"),
            (("session", "binding_evidence", 0, "path"), "../escape.json", "EVIDENCE_PATH_INVALID"),
            (("session", "binding_evidence", 0, "path"), "C:/escape.json", "EVIDENCE_PATH_INVALID"),
            (("session", "binding_evidence", 0, "sha256"), "f" * 64, "EVIDENCE_HASH_MISMATCH"),
            (("session", "binding_evidence", 0, "size"), 0, "SHAPE_INVALID"),
        ]
        for keys, value, error in changes:
            with self.subTest(keys=keys, value=value), tempfile.TemporaryDirectory() as temporary:
                unit, path = create_general_execution_state(Path(temporary))
                document = json.loads(path.read_text())
                target = document
                for key in keys[:-1]:
                    target = target[key]
                target[keys[-1]] = value
                write_json(path, document)
                with self.assertRaisesRegex(MODULE.FlowError, error):
                    MODULE.record_execution_states(argparse.Namespace(root=str(unit), state=[str(path)]))
                self.assertEqual(MODULE.load_state(unit)["stages"]["execute"], "PENDING")

    def test_unsent_failure_requires_explicit_not_sent_infrastructure_status(self) -> None:
        for send_status in ("not_sent", "intent_persisted", "uncertain"):
            with self.subTest(send_status=send_status), tempfile.TemporaryDirectory() as temporary:
                unit, path = create_general_execution_state(Path(temporary))
                document = json.loads(path.read_text())
                document["phase"] = "FAILED"
                document["send"]["dispatch_attempt_count"] = 0
                document["prompt"].update(send_status=send_status, sent_at=None)
                document["execution"]["business_status"] = "infrastructure_error"
                document["session"].update(verified=False, cwd=None, session_id=None, binding_evidence=[])
                write_json(path, document)
                if send_status == "not_sent":
                    result = MODULE.record_execution_states(argparse.Namespace(root=str(unit), state=[str(path)]))
                    self.assertEqual(result["state"]["stages"]["execute"], "COMPLETED")
                else:
                    with self.assertRaisesRegex(MODULE.FlowError, "DISPATCH_INVARIANT"):
                        MODULE.record_execution_states(argparse.Namespace(root=str(unit), state=[str(path)]))

    def test_dispatched_failure_requires_verified_session_and_cancellation(self) -> None:
        for status in ("candidate_error", "timeout", "cancelled", "infrastructure_error"):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as temporary:
                unit, path = create_general_execution_state(Path(temporary))
                document = json.loads(path.read_text())
                document["phase"] = "FAILED"
                document["execution"].update(business_status=status, cancellation_confirmed=True)
                document["session"]["verified"] = False
                write_json(path, document)
                with self.assertRaisesRegex(MODULE.FlowError, "SESSION_BINDING_UNVERIFIED"):
                    MODULE.record_execution_states(argparse.Namespace(root=str(unit), state=[str(path)]))
                document["session"]["verified"] = True
                if status in {"timeout", "cancelled"}:
                    document["execution"]["cancellation_confirmed"] = False
                    write_json(path, document)
                    with self.assertRaisesRegex(MODULE.FlowError, "CANCELLATION_UNVERIFIED"):
                        MODULE.record_execution_states(argparse.Namespace(root=str(unit), state=[str(path)]))
                    document["execution"]["cancellation_confirmed"] = True
                write_json(path, document)
                result = MODULE.record_execution_states(argparse.Namespace(root=str(unit), state=[str(path)]))
                self.assertEqual(result["state"]["artifacts"]["execute"]["states"][0]["business_status"], status)

    def test_general_state_paths_and_hashed_files_remain_locked(self) -> None:
        for mutation in ("workspace", "cwd", "prompt", "symlink", "duplicate", "missing-null"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                unit, path = create_general_execution_state(Path(temporary))
                document = json.loads(path.read_text())
                if mutation == "workspace":
                    document["candidate_workspace"] = str(unit)
                elif mutation == "cwd":
                    document["session"]["cwd"] = str(unit)
                elif mutation == "prompt":
                    Path(document["prompt"]["path"]).write_text("changed")
                elif mutation == "symlink":
                    evidence = unit / document["session"]["binding_evidence"][0]["path"]
                    source = unit.parent / "outside.json"
                    source.write_bytes(evidence.read_bytes())
                    evidence.unlink()
                    evidence.symlink_to(source)
                elif mutation == "duplicate":
                    document["session"]["binding_evidence"] *= 2
                else:
                    del document["session"]["turn_id"]
                write_json(path, document)
                with self.assertRaises(MODULE.FlowError):
                    MODULE.record_execution_states(argparse.Namespace(root=str(unit), state=[str(path)]))

    def test_state_hash_records_the_validated_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            unit, path = create_general_execution_state(Path(temporary))
            original = path.read_bytes()
            digest = sha256_bytes(original)
            hash_file = MODULE.sha256_file
            def mutate_after_hash(candidate):
                current = hash_file(candidate)
                if candidate.resolve() == path.resolve():
                    path.write_bytes(original + b" ")
                return current
            with mock.patch.object(MODULE, "sha256_file", side_effect=mutate_after_hash):
                result = MODULE.record_execution_states(argparse.Namespace(root=str(unit), state=[str(path)]))
            artifact = result["state"]["artifacts"]["execute"]["states"][0]
            self.assertEqual(artifact["sha256"], digest)
            self.assertEqual(artifact["size"], len(original))
            self.assertNotEqual(artifact["sha256"], sha256_bytes(path.read_bytes()))

    def test_legacy_state_cannot_impersonate_another_harness(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            unit, path = create_general_execution_state(Path(temporary))
            document = json.loads(path.read_text())
            document["schema_version"] = MODULE.EXECUTION_STATE_SCHEMA
            write_json(path, document)
            with self.assertRaisesRegex(MODULE.FlowError, "DRIVER_BINDING_MISMATCH"):
                MODULE.record_execution_states(argparse.Namespace(root=str(unit), state=[str(path)]))

    def test_extract_defers_read_only_directory_modes_until_children_exist(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = (Path(temp_dir) / "imported").resolve()
            destination.mkdir()
            directory_info = zipfile.ZipInfo("candidate-original/")
            directory_info.external_attr = (stat.S_IFDIR | 0o555) << 16
            file_info = zipfile.ZipInfo("candidate-original/candidate-artifact.json")
            file_info.external_attr = (stat.S_IFREG | 0o444) << 16
            payload = b'{}\n'
            verified = {
                "members": {
                    "candidate-original": (directory_info, b""),
                    "candidate-original/candidate-artifact.json": (
                        file_info,
                        payload,
                    ),
                },
                "manifest": {
                    "entries": [
                        {
                            "path": "candidate-original",
                            "kind": "directory",
                        },
                        {
                            "path": "candidate-original/candidate-artifact.json",
                            "kind": "file",
                        },
                    ]
                },
                "manifest_bytes": b"{}\n",
                "receipt_bytes": b"{}\n",
            }

            try:
                MODULE.extract_verified_return(verified, destination)
                candidate = destination / "candidate-original"
                self.assertEqual(
                    (candidate / "candidate-artifact.json").read_bytes(), payload
                )
                self.assertEqual(stat.S_IMODE(candidate.stat().st_mode), 0o555)
                self.assertEqual(
                    stat.S_IMODE((candidate / "candidate-artifact.json").stat().st_mode),
                    0o444,
                )
            finally:
                candidate = destination / "candidate-original"
                if candidate.exists():
                    os.chmod(candidate, 0o755)

    def test_batch_manifest_artifacts_are_locked_for_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            batch = Path(temp_dir) / "batch"
            package = batch / "packages/unit-execution.zip"
            package.parent.mkdir(parents=True)
            package.write_bytes(b"package-v1")
            manifest = batch_manifest()
            manifest["artifacts"] = [
                {
                    "unit_id": "astronstudio-macos",
                    "role": "execution",
                    "path": "packages/unit-execution.zip",
                    "sha256": sha256_bytes(b"package-v1"),
                    "size": len(b"package-v1"),
                }
            ]
            write_json(batch / "manifest.json", manifest)
            MODULE.initialize_state(
                argparse.Namespace(
                    root=str(batch),
                    scope="batch",
                    stage=["prepare,import-return,report"],
                    input=[],
                )
            )
            package.write_bytes(b"package-v2")
            with self.assertRaisesRegex(MODULE.FlowError, "MANIFEST_ARTIFACT_DRIFT"):
                MODULE.load_state(batch)

    def test_verified_stage_artifacts_drive_unit_state_to_package_completion(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            unit = create_unit(root)
            MODULE.initialize_state(
                argparse.Namespace(
                    root=str(unit),
                    scope="unit",
                    stage=["execute,collect-evidence,score,package"],
                    input=[],
                )
            )
            execution_state = create_execution_state(unit)
            execution = MODULE.record_execution_states(
                argparse.Namespace(root=str(unit), state=[str(execution_state)])
            )
            self.assertEqual(execution["state"]["stages"]["execute"], "COMPLETED")
            self.assertEqual(execution["recommended_actions"][0]["stage"], "collect-evidence")

            MODULE.record_receipt(
                argparse.Namespace(
                    root=str(unit),
                    stage="collect-evidence",
                    receipt=str(unit / "receipts/collect-evidence-receipt.json"),
                )
            )
            orchestration = create_orchestration(root, "state-flow")
            MODULE.record_submission(
                argparse.Namespace(
                    root=str(unit), submission=str(orchestration / "submission.json")
                )
            )
            MODULE.package_return(package_args(unit, orchestration, root / "returns"))
            final_state = MODULE.load_state(unit)
            self.assertTrue(
                all(
                    final_state["stages"][stage] == "COMPLETED"
                    for stage in ("execute", "collect-evidence", "score", "package")
                )
            )

    def test_state_freezes_stage_selection_and_input_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            unit = create_unit(root)
            scoring = root / "scoring.zip"
            scoring.write_bytes(b"scoring-v1")
            args = argparse.Namespace(
                root=str(unit),
                scope="unit",
                stage=["execute,collect-evidence,score,package"],
                input=[f"scoring-package={scoring}"],
            )
            created = MODULE.initialize_state(args)
            self.assertTrue(created["created"])
            self.assertEqual(created["state"]["stages"]["execute"], "PENDING")
            self.assertFalse(MODULE.initialize_state(args)["created"])
            scoring.write_bytes(b"scoring-v2")
            with self.assertRaisesRegex(MODULE.FlowError, "INPUT_DRIFT"):
                MODULE.load_state(unit)

    def test_return_package_is_deterministic_and_excludes_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            unit = create_unit(root)
            orchestration = create_orchestration(root, "one")
            first = MODULE.package_return(package_args(unit, orchestration, root / "out-one"))
            second = MODULE.package_return(package_args(unit, orchestration, root / "out-two"))
            self.assertEqual(first["archive_sha256"], second["archive_sha256"])
            verified = MODULE.inspect_return_archive(
                Path(first["archive"]), Path(first["receipt"])
            )
            names = set(verified["members"])
            self.assertIn(
                "scoring/attempts/orch-001/candidate-original/workspace/result-link",
                names,
            )
            self.assertFalse(any("/runtime/" in f"/{name}/" for name in names))

    def test_return_package_accepts_valid_partial_collection(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            unit = create_unit(root)
            receipt_path = unit / "receipts/collect-evidence-receipt.json"
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            receipt["status"] = "partial"
            receipt["tasks"][0]["status"] = "partial"
            write_json(receipt_path, receipt)
            orchestration = create_orchestration(root, "partial-collection")

            package = MODULE.package_return(
                package_args(unit, orchestration, root / "returns")
            )
            self.assertTrue(Path(package["archive"]).is_file())

    def test_nested_attempt_packages_only_exact_attempt_and_excludes_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            unit = create_unit(root)
            orchestration = create_orchestration(
                root, "nested", nested_attempt=True
            )

            package = MODULE.package_return(
                package_args(unit, orchestration, root / "returns")
            )
            verified = MODULE.inspect_return_archive(
                Path(package["archive"]), Path(package["receipt"])
            )
            names = set(verified["members"])
            score = "scoring/attempts/unit-one/task-one/orch-001/score.json"
            self.assertIn(score, names)
            self.assertFalse(any("/runtime/" in f"/{name}/" for name in names))

    def test_import_is_idempotent_and_conflict_requires_selection(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            unit = create_unit(root)
            batch = root / "batch"
            write_json(batch / "manifest.json", batch_manifest())
            MODULE.initialize_state(
                argparse.Namespace(
                    root=str(batch),
                    scope="batch",
                    stage=["prepare,import-return,report"],
                    input=[],
                )
            )
            first_package = MODULE.package_return(
                package_args(unit, create_orchestration(root, "one"), root / "packages-one")
            )
            first_args = argparse.Namespace(
                batch_root=str(batch),
                archive=first_package["archive"],
                receipt=first_package["receipt"],
            )
            first = MODULE.import_return(first_args)
            self.assertFalse(first["conflict"])
            self.assertEqual(first["package_id"], first["selected_package_id"])
            duplicate = MODULE.import_return(first_args)
            self.assertTrue(duplicate["idempotent"])
            self.assertEqual(MODULE.load_state(batch)["stages"]["import-return"], "COMPLETED")

            second_package = MODULE.package_return(
                package_args(unit, create_orchestration(root, "two"), root / "packages-two")
            )
            second = MODULE.import_return(
                argparse.Namespace(
                    batch_root=str(batch),
                    archive=second_package["archive"],
                    receipt=second_package["receipt"],
                )
            )
            self.assertTrue(second["conflict"])
            self.assertIsNone(second["selected_package_id"])
            self.assertEqual(MODULE.load_state(batch)["stages"]["import-return"], "NEEDS_ATTENTION")
            targets = list((batch / "returns/astronstudio-macos").iterdir())
            self.assertEqual(len(targets), 2)

            selected = MODULE.select_import(
                argparse.Namespace(
                    batch_root=str(batch),
                    unit_id="astronstudio-macos",
                    package_id=second["package_id"],
                )
            )
            self.assertEqual(selected["selected_package_id"], second["package_id"])
            self.assertEqual(MODULE.load_state(batch)["stages"]["import-return"], "COMPLETED")

    def test_archive_path_traversal_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            unit = create_unit(root)
            package = MODULE.package_return(
                package_args(unit, create_orchestration(root, "one"), root / "packages")
            )
            malicious = root / "malicious.zip"
            malicious.write_bytes(Path(package["archive"]).read_bytes())
            with zipfile.ZipFile(malicious, "a") as archive:
                archive.writestr("../escape.txt", "escape")
            with self.assertRaisesRegex(MODULE.FlowError, "RELATIVE_PATH_INVALID"):
                MODULE.inspect_return_archive(malicious, None)


if __name__ == "__main__":
    unittest.main()
