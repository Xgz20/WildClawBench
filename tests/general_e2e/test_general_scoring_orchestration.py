from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))
ORCHESTRATOR_PATH = (
    REPO_ROOT
    / "tools/report/skills/general-e2e/orchestrate-general-e2e/scripts"
    / "orchestrate_general_e2e.py"
)
SCORE_SKILL = REPO_ROOT / "tools/report/skills/general-e2e/score-general-e2e"
SCORE_RUNTIME_PATH = SCORE_SKILL / "scripts/score_general_e2e.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ORCHESTRATOR = load_module("wildclawbench_general_orchestrator_test", ORCHESTRATOR_PATH)
SCORE_RUNTIME = load_module("wildclawbench_score_runtime_for_orchestrator", SCORE_RUNTIME_PATH)


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


class Fixture:
    def __init__(
        self,
        root: Path,
        task_ids: tuple[str, ...] = ("task-one", "task-two"),
        *,
        protocol: str = "codex-agent-judge-v1",
        judge_model: str = "gpt-fixture",
        reasoning_effort: str | None = "high",
    ) -> None:
        self.root = root
        self.batch_id = "batch-orchestration"
        self.unit_id = "unit-macos"
        self.task_ids = list(task_ids)
        self.dataset = {
            "id": "dataset-fixture",
            "digest": "d" * 64,
            "bundle_sha256": "b" * 64,
        }
        self.release = {
            "id": "release-fixture",
            "catalog_digest": "c" * 64,
            "catalog_sha256": "a" * 64,
            "suite_sha256": "e" * 64,
        }
        self.unit_root = root / "unit"
        self.unit_root.mkdir(parents=True)
        self.execution_records: dict[str, Path] = {}
        scoring_tasks = []
        package_root = f"{self.batch_id}__{self.unit_id}"
        self.scoring_package = root / "scoring.zip"
        archive_entries: list[tuple[zipfile.ZipInfo, bytes]] = []

        for index, task_id in enumerate(self.task_ids):
            identity = {
                "batch_id": self.batch_id,
                "unit_id": self.unit_id,
                "task_id": task_id,
                "attempt_id": f"execution-{index + 1}",
            }
            evidence_root = self.unit_root / "evidence/tasks" / task_id / identity["attempt_id"]
            candidate = evidence_root / "candidate/workspace"
            candidate.mkdir(parents=True)
            (candidate / "answer.txt").write_text(
                f"answer-{index + 1}\n", encoding="utf-8"
            )
            candidate_entries, candidate_sha = SCORE_RUNTIME._inventory_tree(candidate)
            artifact = {
                "schema_version": SCORE_RUNTIME.CANDIDATE_SCHEMA,
                "identity": identity,
                "hash_algorithm": SCORE_RUNTIME.TREE_HASH_ALGORITHM,
                "expected_sha256": candidate_sha,
                "entries": candidate_entries,
            }
            (candidate.parent / "candidate-artifact.json").write_text(
                json.dumps(artifact), encoding="utf-8"
            )
            transcript = evidence_root / "transcript.jsonl"
            transcript.write_text(
                json.dumps({"event_id": f"event-{index + 1}", "kind": "assistant"})
                + "\n",
                encoding="utf-8",
            )
            execution_record = evidence_root / "execution-record.json"
            execution_record.write_text(
                json.dumps(
                    {
                        "identity": identity,
                        "dataset": self.dataset,
                        "phase": "COMPLETED",
                        "execution": {"business_status": "completed"},
                        "evidence": {
                            "completeness": "complete",
                            "transcript_path": transcript.relative_to(self.unit_root).as_posix(),
                        },
                        "candidate": {
                            "path": candidate.relative_to(self.unit_root).as_posix(),
                            "frozen_sha256": candidate_sha,
                            "drift_status": "stable",
                        },
                    }
                ),
                encoding="utf-8",
            )
            self.execution_records[task_id] = execution_record

            rule = (
                "def grade(transcript, workspace_path):\n"
                "    return {'criterion': 1.0, 'overall_score': 1.0}\n"
            )
            contract = {
                "task_id": task_id,
                "automated_checks": rule,
                "grading_type": "hybrid",
                "grading_weights": {"automated": 0.5, "llm_judge": 0.5},
            }
            contract_bytes = json.dumps(contract).encode("utf-8")
            task_bytes = f"# {task_id}\n".encode("utf-8")
            gt_bytes = json.dumps({"answer": f"answer-{index + 1}"}).encode("utf-8")
            gt_entry = {
                "kind": "file",
                "path": "expected.json",
                "mode": "0644",
                "size": len(gt_bytes),
                "sha256": sha256_bytes(gt_bytes),
            }
            tree = {
                "algorithm": SCORE_RUNTIME.DATASET_TREE_HASH_ALGORITHM,
                "entries": [gt_entry],
            }
            private_root = f"score/tasks/{task_id}/private-scoring"
            scoring_tasks.append(
                {
                    "task_id": task_id,
                    "order": index,
                    "grading_type": "hybrid",
                    "grading_weights": contract["grading_weights"],
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
                        "tree_sha256": canonical_sha256(tree),
                        "entries": [gt_entry],
                    },
                }
            )
            archive_entries.extend(
                [
                    (
                        zip_info(f"{package_root}/{private_root}/contract.json"),
                        contract_bytes,
                    ),
                    (zip_info(f"{package_root}/{private_root}/task.md"), task_bytes),
                    (
                        zip_info(f"{package_root}/{private_root}/gt/expected.json"),
                        gt_bytes,
                    ),
                ]
            )

        unit_manifest = {
            "schema_id": SCORE_RUNTIME.PACKAGE_SCHEMA,
            "schema_version": 1,
            "manifest_kind": "execution",
            "contract_version": "general-e2e-contract-v1",
            "bundle_protocol": "general-e2e-package-v1",
            "batch_id": self.batch_id,
            "unit_id": self.unit_id,
            "dataset": self.dataset,
            "release": self.release,
            "task_ids": self.task_ids,
            "unit": {
                "unit_id": self.unit_id,
                "task_ids": self.task_ids,
                "harness": {"id": "astronstudio", "platform": "macos-x86-64"},
                "model": {"requested_id": "candidate-model", "reasoning_effort": "high"},
                "execution_mode": "automatic",
            },
            "tasks": [{"task_id": task_id, "order": index} for index, task_id in enumerate(self.task_ids)],
        }
        (self.unit_root / "manifest.json").write_text(
            json.dumps(unit_manifest), encoding="utf-8"
        )
        scoring_manifest = {
            **unit_manifest,
            "manifest_kind": "scoring",
            "tasks": scoring_tasks,
        }
        with zipfile.ZipFile(self.scoring_package, "w") as archive:
            archive.writestr(
                zip_info(
                    f"{package_root}/.general-e2e/scoring-package-manifest.json"
                ),
                json.dumps(scoring_manifest).encode("utf-8"),
            )
            for info, data in archive_entries:
                archive.writestr(info, data)

        self.report_config = root / "report-config.json"
        self.report_config.write_text(
            json.dumps(
                {
                    "schema_version": ORCHESTRATOR.REPORT_CONFIG_SCHEMA,
                    "batch_id": self.batch_id,
                    "dataset": self.dataset,
                    "release": self.release,
                    "judge": {
                        "protocol": protocol,
                        "model": judge_model,
                        "reasoning_effort": reasoning_effort,
                    },
                    "report": {"title": "fixture"},
                    "units": [unit_manifest["unit"]],
                }
            ),
            encoding="utf-8",
        )
        self.output_root = root / "orchestrations"

    def initialize(
        self,
        *,
        orchestration_id: str = "orchestration-fixture",
        timeout: int = 60,
        api_runtime_config: Path | None = None,
        now: datetime | None = None,
    ) -> dict:
        return ORCHESTRATOR.initialize(
            unit_root=self.unit_root,
            scoring_package=self.scoring_package,
            report_config=self.report_config,
            score_skill_dir=SCORE_SKILL,
            output_root=self.output_root,
            orchestration_id=orchestration_id,
            execution_records=self.execution_records,
            api_runtime_config=api_runtime_config,
            score_timeout_seconds=timeout,
            now=now,
        )

    def api_runtime_config(self) -> Path:
        path = self.root / "api-runtime.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": SCORE_RUNTIME.API_JUDGE_CONFIG_SCHEMA,
                    "provider": "openai-chat-completions",
                    "base_url": "https://judge.example.test/v1",
                    "credential_env": "GENERAL_E2E_TEST_API_KEY",
                    "max_output_tokens": 1024,
                    "timeout_seconds": 30,
                    "max_attempts": 1,
                    "max_input_chars": 20000,
                    "max_evidence_item_chars": 512,
                    "temperature": 0,
                    "reasoning_parameter": "reasoning_effort",
                }
            ),
            encoding="utf-8",
        )
        return path

    def registration_evidence(self, task: dict, path: Path) -> Path:
        evidence = self.root / f"{task['task_id']}-registration.json"
        evidence.write_text(
            json.dumps(
                {
                    "schema_version": ORCHESTRATOR.REGISTRATION_SCHEMA,
                    "status": "UI_REGISTRATION_COMPLETED",
                    "desktop_version": "2026.918.1",
                    "projects": [
                        {
                            "canonical_path": str(path.resolve()),
                            "ui_method": "direct-open-folder",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return evidence


class GeneralScoringOrchestrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="general-e2e-orchestration-")
        self.root = Path(self.temp.name)
        self.t0 = datetime(2026, 9, 18, 1, 0, tzinfo=timezone.utc)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _record_first_project(self, fixture: Fixture, view: dict, *, now=None) -> dict:
        task = view["tasks"][0]
        path = Path(task["attempt_path"])
        evidence = fixture.registration_evidence(task, path)
        return ORCHESTRATOR.record_project(
            Path(view["orchestration_root"]),
            task_id=task["task_id"],
            project_id="project-one",
            host_id="host-local",
            project_path=path,
            registration_evidence=evidence,
            now=now or self.t0,
        )

    def test_init_creates_isolated_attempts_and_freezes_judge_and_prompt(self) -> None:
        fixture = Fixture(self.root)
        view = fixture.initialize(now=self.t0)
        self.assertEqual(view["status"], "RUNNING")
        self.assertEqual(view["judge"], {
            "protocol": "codex-agent-judge-v1",
            "model": "gpt-fixture",
            "reasoning_effort": "high",
        })
        self.assertEqual(view["task_count"], 2)
        self.assertEqual(len(view["recommended_actions"]), 1)
        self.assertEqual(view["recommended_actions"][0]["action"], "REGISTER_PROJECT")
        attempts = [Path(task["attempt_path"]) for task in view["tasks"]]
        self.assertNotEqual(attempts[0], attempts[1])
        self.assertTrue(all((path / "attempt-manifest.json").is_file() for path in attempts))
        self.assertTrue(all((path / "private/judge-config.json").is_file() for path in attempts))
        first_attempt_manifest = json.loads(
            (attempts[0] / "attempt-manifest.json").read_text()
        )
        self.assertEqual(
            first_attempt_manifest["judge"],
            {
                "protocol": "codex-agent-judge-v1",
                "model": "gpt-fixture",
                "reasoning_effort": "high",
                "attempt_id": "orchestration-fixture-001",
            },
        )
        state = json.loads(
            (Path(view["orchestration_root"]) / "orchestration-state.json").read_text()
        )
        self.assertEqual(state["score_slots"], 1)
        self.assertTrue(all(len(task["prompt_sha256"]) == 64 for task in state["tasks"]))
        self.assertNotEqual(state["tasks"][0]["prompt_sha256"], state["tasks"][1]["prompt_sha256"])

    def test_project_preflight_thread_cursor_and_next_task_are_recoverable(self) -> None:
        fixture = Fixture(self.root)
        view = fixture.initialize(now=self.t0)
        view = self._record_first_project(fixture, view)
        self.assertEqual(view["recommended_actions"][0]["action"], "PREFLIGHT_PROJECT")
        root = Path(view["orchestration_root"])
        task_id = view["tasks"][0]["task_id"]
        view = ORCHESTRATOR.preflight(
            root,
            task_id=task_id,
            desktop_version="2026.918.1",
            now=self.t0,
        )
        create = view["recommended_actions"][0]
        self.assertEqual(create["action"], "CREATE_THREAD")
        self.assertEqual(create["model"], "gpt-fixture")
        self.assertEqual(create["thinking"], "high")
        with self.assertRaisesRegex(
            ORCHESTRATOR.OrchestrationError, "THREAD_HOST_MISMATCH"
        ):
            ORCHESTRATOR.record_thread(
                root,
                task_id=task_id,
                thread_id="thread-wrong-host",
                host_id="host-remote",
                now=self.t0,
            )

        view = ORCHESTRATOR.record_thread(
            root,
            task_id=task_id,
            thread_id="thread-one",
            host_id="host-local",
            now=self.t0,
        )
        deadline = view["tasks"][0]["deadline_at"]
        view = ORCHESTRATOR.record_wait(
            root,
            task_id=task_id,
            wait_sequence=1,
            wait_cursor="cursor-one",
            wait_status="POLL_TIMEOUT",
            now=self.t0 + timedelta(seconds=10),
        )
        wait = view["recommended_actions"][0]
        self.assertEqual(wait["action"], "WAIT_EXISTING_THREAD")
        self.assertEqual(wait["after_cursor"], "cursor-one")
        self.assertEqual(wait["next_wait_sequence"], 2)
        self.assertEqual(view["tasks"][0]["deadline_at"], deadline)
        resumed = ORCHESTRATOR.status(root, now=self.t0 + timedelta(seconds=10))
        self.assertEqual(resumed["recommended_actions"], view["recommended_actions"])
        with self.assertRaisesRegex(ORCHESTRATOR.OrchestrationError, "WAIT_SEQUENCE_MISMATCH"):
            ORCHESTRATOR.record_wait(
                root,
                task_id=task_id,
                wait_sequence=3,
                wait_cursor="cursor-stale",
                wait_status="RUNNING",
                now=self.t0 + timedelta(seconds=11),
            )
        completed = ORCHESTRATOR.record_wait(
            root,
            task_id=task_id,
            wait_sequence=2,
            wait_cursor="cursor-two",
            wait_status="COMPLETED",
            now=self.t0 + timedelta(seconds=20),
        )
        self.assertEqual(completed["completed_count"], 0)
        self.assertEqual(completed["recommended_actions"][0]["task_id"], "task-one")
        self.assertEqual(completed["recommended_actions"][0]["action"], "VERIFY_SCORE")
        attempt = Path(completed["tasks"][0]["attempt_path"])
        (attempt / "score.json").write_text(
            json.dumps({"result": {"valid": True, "total_score": 0.8}}),
            encoding="utf-8",
        )
        with patch.object(
            ORCHESTRATOR,
            "_run_score_command",
            return_value={"status": "PASS", "score_valid": True},
        ):
            scored = ORCHESTRATOR.record_score(
                root,
                task_id=task_id,
                now=self.t0 + timedelta(seconds=21),
            )
        self.assertEqual(scored["completed_count"], 1)
        self.assertEqual(scored["recommended_actions"][0]["task_id"], "task-two")
        self.assertEqual(scored["recommended_actions"][0]["action"], "REGISTER_PROJECT")

    def test_existing_project_can_be_reused_from_exact_list_projects_match(self) -> None:
        fixture = Fixture(self.root, task_ids=("task-one",))
        view = fixture.initialize(now=self.t0)
        task = view["tasks"][0]
        reused = ORCHESTRATOR.record_project(
            Path(view["orchestration_root"]),
            task_id=task["task_id"],
            project_id="existing-project",
            host_id="host-local",
            project_path=Path(task["attempt_path"]),
            desktop_version="2026.918.1",
            now=self.t0,
        )
        self.assertEqual(reused["recommended_actions"][0]["action"], "PREFLIGHT_PROJECT")
        state = json.loads(
            (Path(view["orchestration_root"]) / "orchestration-state.json").read_text()
        )
        self.assertEqual(
            state["tasks"][0]["project"]["registration_method"], "existing-project"
        )

    def test_api_queue_never_creates_codex_project_or_thread(self) -> None:
        fixture = Fixture(
            self.root / "api-queue",
            task_ids=("task-one",),
            protocol="api-judge-v1",
            judge_model="openai-fixture",
        )
        view = fixture.initialize(
            api_runtime_config=fixture.api_runtime_config(), now=self.t0
        )
        self.assertEqual(view["recommended_actions"][0]["action"], "RUN_API_SCORE")
        self.assertEqual(view["tasks"][0]["phase"], "API_READY")
        state_path = Path(view["orchestration_root"]) / "orchestration-state.json"
        state = json.loads(state_path.read_text())
        self.assertIsNone(state["tasks"][0]["prompt_path"])
        self.assertIsNone(state["tasks"][0]["project"])
        self.assertIsNone(state["tasks"][0]["thread"])
        self.assertEqual(
            state["judge"]["api_runtime"]["credential_env"],
            "GENERAL_E2E_TEST_API_KEY",
        )

        attempt = Path(view["tasks"][0]["attempt_path"])
        (attempt / "score.json").write_text(
            json.dumps({"result": {"valid": False, "total_score": None}}),
            encoding="utf-8",
        )
        calls = []

        def fake_score(_lock, arguments, **kwargs):
            calls.append((list(arguments), dict(kwargs)))
            if arguments[0] in {"run-api-score", "verify-score"}:
                return {"status": "PASS", "score_valid": False}
            return {"status": "PASS", "candidate_sha256": "f" * 64}

        with patch.object(ORCHESTRATOR, "_run_score_command", side_effect=fake_score):
            completed = ORCHESTRATOR.run_api_score_task(
                Path(view["orchestration_root"]),
                task_id="task-one",
                now=self.t0,
            )
        self.assertEqual(completed["status"], "COMPLETED")
        self.assertEqual(completed["completed_count"], 1)
        api_calls = [call for call in calls if call[0][0] == "run-api-score"]
        self.assertEqual(len(api_calls), 1)
        self.assertEqual(
            api_calls[0][1]["credential_env"], "GENERAL_E2E_TEST_API_KEY"
        )
        self.assertFalse(
            any(
                action.get("action") in {"REGISTER_PROJECT", "CREATE_THREAD"}
                for action in completed["recommended_actions"]
            )
        )

    def test_deadline_does_not_create_replacement_before_original_thread_is_terminal(self) -> None:
        fixture = Fixture(self.root, task_ids=("task-one",))
        view = fixture.initialize(timeout=10, now=self.t0)
        view = self._record_first_project(fixture, view)
        root = Path(view["orchestration_root"])
        task_id = view["tasks"][0]["task_id"]
        ORCHESTRATOR.preflight(
            root, task_id=task_id, desktop_version="2026.918.1", now=self.t0
        )
        ORCHESTRATOR.record_thread(
            root,
            task_id=task_id,
            thread_id="thread-one",
            host_id="host-local",
            now=self.t0,
        )
        with self.assertRaisesRegex(
            ORCHESTRATOR.OrchestrationError, "THREAD_DEADLINE_NOT_REACHED"
        ):
            ORCHESTRATOR.mark_timeout(
                root, task_id=task_id, now=self.t0 + timedelta(seconds=9)
            )
        due = ORCHESTRATOR.status(root, now=self.t0 + timedelta(seconds=11))
        self.assertEqual(due["recommended_actions"][0]["action"], "MARK_TIMEOUT")
        timed_out = ORCHESTRATOR.mark_timeout(
            root, task_id=task_id, now=self.t0 + timedelta(seconds=11)
        )
        action = timed_out["recommended_actions"][0]
        self.assertEqual(action["action"], "WAIT_EXISTING_THREAD_AFTER_DEADLINE")
        self.assertEqual(action["thread_id"], "thread-one")
        terminal = ORCHESTRATOR.record_wait(
            root,
            task_id=task_id,
            wait_sequence=1,
            wait_cursor="cursor-terminal",
            wait_status="COMPLETED",
            now=self.t0 + timedelta(seconds=12),
        )
        self.assertEqual(terminal["status"], "COMPLETED_WITH_FAILURES")
        self.assertEqual(terminal["failed_count"], 1)
        self.assertEqual(terminal["recommended_actions"], [])

        late_fixture = Fixture(self.root / "late", task_ids=("task-one",))
        late = late_fixture.initialize(timeout=10, now=self.t0)
        late = self._record_first_project(late_fixture, late)
        late_root = Path(late["orchestration_root"])
        ORCHESTRATOR.preflight(
            late_root,
            task_id="task-one",
            desktop_version="2026.918.1",
            now=self.t0,
        )
        ORCHESTRATOR.record_thread(
            late_root,
            task_id="task-one",
            thread_id="thread-late",
            host_id="host-local",
            now=self.t0,
        )
        late_terminal = ORCHESTRATOR.record_wait(
            late_root,
            task_id="task-one",
            wait_sequence=1,
            wait_cursor="cursor-late-terminal",
            wait_status="COMPLETED",
            now=self.t0 + timedelta(seconds=11),
        )
        self.assertEqual(late_terminal["status"], "COMPLETED_WITH_FAILURES")
        self.assertEqual(late_terminal["failed_count"], 1)

    def test_configuration_backend_and_concurrency_fail_closed(self) -> None:
        api_fixture = Fixture(self.root / "api", protocol="api-judge-v1")
        with self.assertRaisesRegex(
            ORCHESTRATOR.OrchestrationError, "API_JUDGE_CONFIG_REQUIRED"
        ):
            api_fixture.initialize(now=self.t0)
        unsupported_fixture = Fixture(self.root / "unsupported", protocol="other-judge-v1")
        with self.assertRaisesRegex(
            ORCHESTRATOR.OrchestrationError, "JUDGE_PROTOCOL_UNSUPPORTED"
        ):
            unsupported_fixture.initialize(now=self.t0)
        null_fixture = Fixture(self.root / "null", reasoning_effort=None)
        with self.assertRaisesRegex(ORCHESTRATOR.OrchestrationError, "STRING_REQUIRED"):
            null_fixture.initialize(now=self.t0)
        unconfigured_fixture = Fixture(
            self.root / "unconfigured", judge_model="unconfigured-g3-03"
        )
        with self.assertRaisesRegex(
            ORCHESTRATOR.OrchestrationError, "JUDGE_MODEL_UNCONFIGURED"
        ):
            unconfigured_fixture.initialize(now=self.t0)
        unsupported_effort = Fixture(
            self.root / "unsupported-effort", reasoning_effort="extreme"
        )
        with self.assertRaisesRegex(
            ORCHESTRATOR.OrchestrationError, "JUDGE_REASONING_EFFORT_UNSUPPORTED"
        ):
            unsupported_effort.initialize(now=self.t0)
        slot_fixture = Fixture(self.root / "slots")
        with self.assertRaisesRegex(
            ORCHESTRATOR.OrchestrationError, "SCORE_SLOTS_UNSUPPORTED"
        ):
            ORCHESTRATOR.initialize(
                unit_root=slot_fixture.unit_root,
                scoring_package=slot_fixture.scoring_package,
                report_config=slot_fixture.report_config,
                score_skill_dir=SCORE_SKILL,
                output_root=slot_fixture.output_root,
                orchestration_id="slot-fixture",
                execution_records=slot_fixture.execution_records,
                score_slots=2,
                now=self.t0,
            )

    def test_project_path_and_frozen_material_drift_fail_closed(self) -> None:
        fixture = Fixture(self.root)
        view = fixture.initialize(now=self.t0)
        task = view["tasks"][0]
        expected = Path(task["attempt_path"])
        evidence = fixture.registration_evidence(task, expected)
        wrong = self.root / "wrong-project"
        wrong.mkdir()
        with self.assertRaisesRegex(ORCHESTRATOR.OrchestrationError, "PROJECT_PATH_MISMATCH"):
            ORCHESTRATOR.record_project(
                Path(view["orchestration_root"]),
                task_id=task["task_id"],
                project_id="project-one",
                host_id="host-local",
                project_path=wrong,
                registration_evidence=evidence,
                now=self.t0,
            )
        linked = self.root / "linked-project"
        try:
            linked.symlink_to(expected, target_is_directory=True)
        except (NotImplementedError, OSError):
            pass
        else:
            with self.assertRaisesRegex(
                ORCHESTRATOR.OrchestrationError, "PROJECT_PATH_INVALID"
            ):
                ORCHESTRATOR.record_project(
                    Path(view["orchestration_root"]),
                    task_id=task["task_id"],
                    project_id="project-one",
                    host_id="host-local",
                    project_path=linked,
                    registration_evidence=evidence,
                    now=self.t0,
                )
        root = Path(view["orchestration_root"])
        state = json.loads((root / "orchestration-state.json").read_text())
        prompt = root / state["tasks"][0]["prompt_path"]
        original_prompt = prompt.read_text(encoding="utf-8")
        prompt.write_text(original_prompt + "tampered\n", encoding="utf-8")
        with self.assertRaisesRegex(ORCHESTRATOR.OrchestrationError, "SCORING_PROMPT_DRIFT"):
            ORCHESTRATOR.status(root, now=self.t0)
        prompt.write_text(original_prompt, encoding="utf-8")
        ORCHESTRATOR.record_project(
            root,
            task_id=task["task_id"],
            project_id="project-one",
            host_id="host-local",
            project_path=expected,
            registration_evidence=evidence,
            now=self.t0,
        )
        state = json.loads((root / "orchestration-state.json").read_text())
        recorded_evidence = root / state["tasks"][0]["project"]["evidence_path"]
        recorded_evidence.write_text(
            recorded_evidence.read_text(encoding="utf-8") + " ", encoding="utf-8"
        )
        with self.assertRaisesRegex(
            ORCHESTRATOR.OrchestrationError, "PROJECT_REGISTRATION_DRIFT"
        ):
            ORCHESTRATOR.status(root, now=self.t0)


if __name__ == "__main__":
    unittest.main()
