from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
import warnings
import zipfile


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))
SCRIPT_PATH = (
    REPO_ROOT
    / "tools/report/skills/general-e2e/score-general-e2e/scripts"
    / "score_general_e2e.py"
)
LOCK_PATH = (
    REPO_ROOT
    / "tools/report/skills/general-e2e/score-general-e2e/references"
    / "scoring-runtime-lock.json"
)
REQUIREMENTS_PATH = LOCK_PATH.with_name("scoring-runtime-requirements.txt")


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


RUNTIME = load_module("wildclawbench_local_scoring_runtime_test", SCRIPT_PATH)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_sha256(value: object) -> str:
    return sha256_bytes(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def zip_info(name: str, kind: str = "file", mode: int = 0o644) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.create_system = 3
    info.compress_type = zipfile.ZIP_STORED
    file_type = {
        "file": stat.S_IFREG,
        "directory": stat.S_IFDIR,
        "symlink": stat.S_IFLNK,
    }[kind]
    info.external_attr = (file_type | mode) << 16
    return info


SUCCESS_RULE = """
def grade(transcript, workspace_path):
    import json
    import os
    from pathlib import Path
    root = Path(workspace_path)
    expected = json.loads((root / "gt/expected.json").read_text(encoding="utf-8"))
    delivered = (root / "answer.txt").read_text(encoding="utf-8")
    clean = "HOME" not in os.environ and "AWS_ACCESS_KEY_ID" not in os.environ
    trace_ok = transcript == [{"event_id": "event-0001", "kind": "assistant"}]
    score = float(delivered == expected["answer"] and clean and trace_ok)
    return {"fixture": score, "overall_score": score}
""".strip()


TIMEOUT_RULE = """
def grade(transcript, workspace_path):
    import subprocess
    import sys
    import time
    from pathlib import Path
    root = Path(workspace_path)
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    (root / "child.pid").write_text(str(child.pid), encoding="utf-8")
    while True:
        time.sleep(0.05)
""".strip()


class Fixture:
    def __init__(
        self,
        root: Path,
        *,
        rule: str = SUCCESS_RULE,
        gt_collision: bool = False,
        grading_type: str = "automated",
        grading_weights: dict | None = None,
        llm_judge_rubric: str = "",
    ):
        self.root = root
        self.grading_type = grading_type
        self.batch_id = "batch-fixture"
        self.unit_id = "unit-fixture"
        self.task_id = "task-fixture"
        self.identity = {
            "batch_id": self.batch_id,
            "unit_id": self.unit_id,
            "task_id": self.task_id,
            "attempt_id": "execution-attempt",
        }
        self.dataset = {"id": "dataset-fixture", "digest": "d" * 64}
        self.release = {"release_id": "release-fixture", "digest": "e" * 64}
        self.unit_root = root / "unit"
        self.candidate = self.unit_root / "evidence/candidate/workspace"
        self.candidate.mkdir(parents=True)
        (self.candidate / "answer.txt").write_text("ready\n", encoding="utf-8")
        if gt_collision:
            (self.candidate / "gt").mkdir()
        entries, candidate_sha = RUNTIME._inventory_tree(self.candidate)
        artifact = {
            "schema_version": RUNTIME.CANDIDATE_SCHEMA,
            "identity": self.identity,
            "hash_algorithm": RUNTIME.TREE_HASH_ALGORITHM,
            "expected_sha256": candidate_sha,
            "entries": entries,
        }
        artifact_path = self.candidate.parent / "candidate-artifact.json"
        artifact_path.write_text(json.dumps(artifact), encoding="utf-8")

        transcript = self.unit_root / "evidence/transcript.jsonl"
        transcript.write_text(
            json.dumps({"event_id": "event-0001", "kind": "assistant"}) + "\n",
            encoding="utf-8",
        )
        self.execution_record = self.unit_root / "evidence/execution-record.json"
        execution = {
            "identity": self.identity,
            "dataset": self.dataset,
            "phase": "COMPLETED",
            "execution": {"business_status": "completed"},
            "evidence": {
                "completeness": "complete",
                "transcript_path": "evidence/transcript.jsonl",
            },
            "candidate": {
                "path": "evidence/candidate/workspace",
                "frozen_sha256": candidate_sha,
                "drift_status": "stable",
            },
        }
        self.execution_record.write_text(json.dumps(execution), encoding="utf-8")
        unit_manifest = {
            "batch_id": self.batch_id,
            "unit_id": self.unit_id,
            "task_ids": [self.task_id],
            "dataset": self.dataset,
            "release": self.release,
        }
        (self.unit_root / "manifest.json").write_text(
            json.dumps(unit_manifest), encoding="utf-8"
        )

        contract = {
            "task_id": self.task_id,
            "automated_checks": rule,
            "grading_type": grading_type,
            "grading_weights": grading_weights or {},
            "llm_judge_rubric": llm_judge_rubric,
        }
        contract_bytes = json.dumps(contract).encode("utf-8")
        task_bytes = b"# Fixture task\n"
        gt_bytes = b'{"answer":"ready\\n"}\n'
        gt_entry = {
            "kind": "file",
            "path": "expected.json",
            "mode": "0644",
            "size": len(gt_bytes),
            "sha256": sha256_bytes(gt_bytes),
        }
        private_tree = {
            "algorithm": RUNTIME.DATASET_TREE_HASH_ALGORITHM,
            "entries": [gt_entry],
        }
        package_root = f"{self.batch_id}__{self.unit_id}"
        private_root = f"score/tasks/{self.task_id}/private-scoring"
        package_manifest = {
            "schema_id": RUNTIME.PACKAGE_SCHEMA,
            "manifest_kind": "scoring",
            "batch_id": self.batch_id,
            "unit_id": self.unit_id,
            "dataset": self.dataset,
            "release": self.release,
            "tasks": [
                {
                    "task_id": self.task_id,
                    "grading_type": grading_type,
                    "grading_weights": grading_weights or {},
                    "contract": {
                        "path": f"{private_root}/contract.json",
                        "sha256": sha256_bytes(contract_bytes),
                    },
                    "task": {
                        "path": f"{private_root}/task.md",
                        "sha256": sha256_bytes(task_bytes),
                    },
                    "private_scoring": {
                        "path": f"{private_root}/gt",
                        "tree_sha256": canonical_sha256(private_tree),
                        "entries": [gt_entry],
                    },
                }
            ],
        }
        self.scoring_package = root / "scoring.zip"
        with zipfile.ZipFile(self.scoring_package, "w") as archive:
            archive.writestr(
                zip_info(
                    f"{package_root}/.general-e2e/scoring-package-manifest.json"
                ),
                json.dumps(package_manifest).encode("utf-8"),
            )
            archive.writestr(
                zip_info(f"{package_root}/{private_root}/contract.json"),
                contract_bytes,
            )
            archive.writestr(
                zip_info(f"{package_root}/{private_root}/task.md"), task_bytes
            )
            archive.writestr(
                zip_info(f"{package_root}/{private_root}/gt/expected.json"),
                gt_bytes,
            )
        self.output_root = root / "attempts"

    def prepare(self, attempt_id: str = "score-attempt") -> Path:
        semantic = self.grading_type != "automated"
        result = RUNTIME.prepare_attempt(
            unit_root=self.unit_root,
            execution_record_path=self.execution_record,
            scoring_package=self.scoring_package,
            task_id=self.task_id,
            scoring_attempt_id=attempt_id,
            output_root=self.output_root,
            runtime_lock_path=LOCK_PATH,
            judge_protocol="codex-agent-judge-v1" if semantic else None,
            judge_model="gpt-fixture" if semantic else None,
            judge_reasoning_effort="high" if semantic else None,
            judge_attempt_id=attempt_id if semantic else None,
        )
        return Path(result["attempt_root"])


class LocalScoringRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.venv_temp = tempfile.TemporaryDirectory(
            prefix="general-e2e-rule-test-venv-"
        )
        cls.venv_root = Path(cls.venv_temp.name) / "venv"
        uv = shutil.which("uv")
        if uv is None:
            raise unittest.SkipTest("uv is required for the managed runtime fixture")
        subprocess.run(
            [uv, "venv", "--python", sys.executable, str(cls.venv_root)],
            check=True,
            capture_output=True,
            text=True,
        )
        cls.runtime_python = cls.venv_root / (
            "Scripts/python.exe" if os.name == "nt" else "bin/python"
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.venv_temp.cleanup()

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="general-e2e-rule-test-")
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_prepare_verify_and_run_rules_use_private_managed_attempt(self) -> None:
        fixture = Fixture(self.root)
        attempt = fixture.prepare()
        verified = RUNTIME.verify_attempt(attempt)
        self.assertEqual(verified["status"], "PASS")
        original = attempt / "candidate-original/workspace/answer.txt"
        runtime_file = attempt / "runtime/workspace/answer.txt"
        self.assertFalse(original.stat().st_mode & 0o222)
        self.assertTrue(runtime_file.stat().st_mode & stat.S_IWUSR)
        self.assertTrue((attempt / "runtime/workspace/gt/expected.json").is_file())

        result = RUNTIME.run_rules_attempt(
            attempt_root=attempt,
            runtime_python=self.runtime_python,
            timeout_seconds=10,
        )
        self.assertEqual(result["rule_component"]["score"], 1.0)
        self.assertFalse(result["audit"]["docker_used"])
        self.assertEqual(
            result["audit"]["worker"]["environment_keys"],
            sorted(RUNTIME._sanitized_environment(self.runtime_python)),
        )
        self.assertFalse(result["audit"]["runtime_workspace"]["drifted"])

    def test_attempt_is_not_overwritten_and_candidate_drift_fails_closed(self) -> None:
        fixture = Fixture(self.root)
        attempt = fixture.prepare()
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError, "SCORING_ATTEMPT_EXISTS"):
            fixture.prepare()

        execution_record = attempt / "private/execution-record.json"
        execution_record.write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(
            RUNTIME.ScoringRuntimeError, "ATTEMPT_PRIVATE_MATERIAL_DRIFT"
        ):
            RUNTIME.verify_attempt(attempt)

        drifted = Fixture(self.root / "drifted")
        (drifted.candidate / "answer.txt").write_text("changed\n", encoding="utf-8")
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError, "CANDIDATE_DIGEST_MISMATCH"):
            drifted.prepare()

    def test_gt_collision_and_runtime_drift_fail_closed(self) -> None:
        collision = Fixture(self.root / "collision", gt_collision=True)
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError, "RUNTIME_GT_COLLISION"):
            collision.prepare()

        artifact_fixture = Fixture(self.root / "artifact-drift")
        artifact_attempt = artifact_fixture.prepare()
        artifact = artifact_attempt / "candidate-original/candidate-artifact.json"
        artifact.chmod(artifact.stat().st_mode | stat.S_IWUSR)
        artifact.write_text("{}\n", encoding="utf-8")
        artifact.chmod(artifact.stat().st_mode & ~0o222)
        with self.assertRaisesRegex(
            RUNTIME.ScoringRuntimeError, "CANDIDATE_ARTIFACT_DRIFT"
        ):
            RUNTIME.verify_attempt(artifact_attempt)

        fixture = Fixture(self.root / "runtime-drift")
        attempt = fixture.prepare()
        (attempt / "runtime/workspace/answer.txt").write_text(
            "tampered\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError, "RUNTIME_WORKSPACE_DRIFT"):
            RUNTIME.run_rules_attempt(
                attempt_root=attempt,
                runtime_python=self.runtime_python,
                timeout_seconds=10,
            )

    @unittest.skipIf(os.name == "nt", "Windows process-tree cleanup requires target-machine validation")
    def test_timeout_terminates_worker_process_group_and_child(self) -> None:
        fixture = Fixture(self.root, rule=TIMEOUT_RULE)
        attempt = fixture.prepare()
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError, "RULE_WORKER_TIMEOUT"):
            RUNTIME.run_rules_attempt(
                attempt_root=attempt,
                runtime_python=self.runtime_python,
                timeout_seconds=0.2,
            )
        child_pid = int(
            (attempt / "runtime/workspace/child.pid").read_text(encoding="utf-8")
        )
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            try:
                os.kill(child_pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.05)
        else:
            self.fail(f"worker child process remained alive: {child_pid}")
        audit = json.loads((attempt / "rule-audit.json").read_text(encoding="utf-8"))
        self.assertTrue(audit["worker"]["timed_out"])
        self.assertIn("SIGTERM", audit["worker"]["process_tree_cleanup"]["actions"])
        self.assertFalse(audit["worker"]["process_tree_cleanup"]["remaining"])

    def test_runtime_lock_and_requirements_are_exact(self) -> None:
        lock, _ = RUNTIME._load_runtime_lock(LOCK_PATH)
        self.assertEqual(lock["python"], {"major": 3, "minor": 11})
        versions = {
            item["distribution"]: item["version"]
            for item in lock["dependencies"]
        }
        self.assertEqual(versions["PyYAML"], "6.0.3")
        self.assertEqual(versions["playwright"], "1.55.0")
        browser = next(
            asset
            for item in lock["dependencies"]
            for asset in item["runtime_assets"]
            if asset["name"] == "chromium"
        )
        self.assertEqual(
            browser,
            {
                "name": "chromium",
                "revision": "1187",
                "version": "140.0.7339.16",
            },
        )
        self.assertEqual(
            sha256_bytes(REQUIREMENTS_PATH.read_bytes()),
            lock["requirements"]["sha256"],
        )
        with self.assertRaisesRegex(
            RUNTIME.ScoringRuntimeError, "RUNTIME_BROWSER_PATH_REQUIRED"
        ):
            RUNTIME.probe_runtime(
                runtime_python=self.runtime_python,
                runtime_lock_path=LOCK_PATH,
                required_import_roots=["playwright"],
            )

    def test_package_paths_duplicates_and_symlink_escape_are_rejected(self) -> None:
        traversal = self.root / "traversal.zip"
        with zipfile.ZipFile(traversal, "w") as archive:
            archive.writestr(zip_info("root/../escape"), b"x")
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError, "SCORING_PACKAGE_PATH_INVALID"):
            RUNTIME._read_scoring_package(traversal)

        duplicate = self.root / "duplicate.zip"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(duplicate, "w") as archive:
                archive.writestr(zip_info("root/file"), b"a")
                archive.writestr(zip_info("root/file"), b"b")
        with self.assertRaisesRegex(
            RUNTIME.ScoringRuntimeError, "SCORING_PACKAGE_MEMBER_DUPLICATE"
        ):
            RUNTIME._read_scoring_package(duplicate)

        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError, "SYMLINK_TARGET_ESCAPE"):
            RUNTIME._safe_symlink_target(PurePosixPath("link"), "../escape")


if __name__ == "__main__":
    unittest.main()
