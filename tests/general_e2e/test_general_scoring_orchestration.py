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
        grading_type: str = "llm_judge",
        grading_types: tuple[str, ...] | None = None,
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

        if grading_types is not None and len(grading_types) != len(self.task_ids):
            raise ValueError("grading_types must align with task_ids")

        for index, task_id in enumerate(self.task_ids):
            task_grading_type = (
                grading_types[index] if grading_types is not None else grading_type
            )
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
            grading_weights = {
                "automated": 1.0 if task_grading_type == "automated" else (0.5 if task_grading_type == "hybrid" else 0.0),
                "llm_judge": 0.0 if task_grading_type == "automated" else (0.5 if task_grading_type == "hybrid" else 1.0),
            }
            contract = {
                "task_id": task_id,
                "automated_checks": rule if task_grading_type != "llm_judge" else "",
                "grading_type": task_grading_type,
                "grading_weights": grading_weights,
                "llm_judge_rubric": (
                    "### Fixture criterion (key: fixture, weight: 1.0)\n"
                    "Score 0.0: incorrect\n"
                    "Score 1.0: correct\n"
                ),
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
                    "grading_type": task_grading_type,
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
        acceptance_id: str | None = None,
        score_slots: int = ORCHESTRATOR.DEFAULT_SCORE_SLOTS,
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
            acceptance_id=acceptance_id,
            score_timeout_seconds=timeout,
            score_slots=score_slots,
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

    def _set_execution_status(
        self,
        fixture: Fixture,
        task_id: str,
        *,
        business_status: str,
        phase: str,
        completeness: str = "complete",
    ) -> None:
        path = fixture.execution_records[task_id]
        document = json.loads(path.read_text(encoding="utf-8"))
        document["execution"]["business_status"] = business_status
        document["phase"] = phase
        document["evidence"]["completeness"] = completeness
        path.write_text(json.dumps(document), encoding="utf-8")

    def _record_fixture_score(
        self,
        orchestration_root: Path,
        task_id: str,
        *,
        valid: bool,
        total_score: float | None,
    ) -> None:
        state_path = orchestration_root / "orchestration-state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        task = next(item for item in state["tasks"] if item["task_id"] == task_id)
        score_path = orchestration_root / task["attempt_path"] / "score.json"
        score = {
            "schema_id": ORCHESTRATOR.SCORE_SCHEMA,
            "schema_version": 1,
            "identity": {
                "batch_id": state["identity"]["batch_id"],
                "unit_id": state["identity"]["unit_id"],
                "task_id": task_id,
                "attempt_id": task["scoring_attempt_id"],
            },
            "dataset": {
                "id": state["identity"]["dataset"]["id"],
                "digest": state["identity"]["dataset"]["digest"],
            },
            "execution": {
                "record_path": "private/execution-record.json",
                "record_sha256": task["execution_record_sha256"],
                "attempt_id": task["execution"]["attempt_id"],
                "business_status": task["execution"]["business_status"],
            },
            "judge": {
                "protocol": state["judge"]["protocol"],
                "model": state["judge"]["model"],
                "reasoning_effort": state["judge"]["reasoning_effort"],
                "attempt_id": task["scoring_attempt_id"],
            },
            "components": {
                "rules": {
                    "status": "completed",
                    "score": total_score if total_score is not None else 1.0,
                },
                "semantics": {
                    "status": "completed" if valid else "evaluation_error",
                    "score": total_score if valid else None,
                },
            },
            "evaluation": {
                "status": "completed" if valid else "evaluation_error",
                "criteria": (
                    [
                        {
                            "key": "fixture",
                            "weight": 1.0,
                            "status": "judged",
                            "score": total_score,
                            "reason": "fixture",
                            "evidence": [
                                {
                                    "type": "rule_result",
                                    "path": "rule-component.json",
                                    "sha256": "a" * 64,
                                }
                            ],
                        }
                    ]
                    if valid
                    else []
                ),
                "error": (
                    None
                    if valid
                    else {"code": "JUDGE_FAILED", "message": "fixture failure"}
                ),
            },
            "result": {
                "valid": valid,
                "total_score": total_score,
                "invalid_reason": None if valid else "JUDGE_FAILED",
            },
        }
        score_path.write_text(json.dumps(score), encoding="utf-8")
        task["score"] = {
            "path": score_path.relative_to(orchestration_root).as_posix(),
            "sha256": hashlib.sha256(score_path.read_bytes()).hexdigest(),
            "valid": valid,
            "total_score": total_score,
            "recorded_at": self.t0.isoformat(),
        }
        task["phase"] = "SCORE_RECORDED"
        state["status"] = ORCHESTRATOR._state_status(state)
        state_path.write_text(json.dumps(state), encoding="utf-8")

    def _fixture_score_command(self, _lock, arguments, **_kwargs):
        if arguments[0] == "verify-score":
            score = json.loads(
                (Path(arguments[-1]) / "score.json").read_text()
            )
            return {
                "status": "PASS",
                "score_valid": score["result"]["valid"],
            }
        return {"status": "PASS", "candidate_sha256": "f" * 64}

    def _direct_local_score_command(self, _lock, arguments, **_kwargs):
        command = arguments[0]
        values = {
            arguments[index]: arguments[index + 1]
            for index in range(1, len(arguments) - 1, 2)
            if arguments[index].startswith("--")
        }
        attempt_root = Path(values["--attempt-root"])
        if command == "verify":
            return SCORE_RUNTIME.verify_attempt(attempt_root)
        if command == "run-rules":
            return SCORE_RUNTIME.run_rules_attempt(
                attempt_root=attempt_root,
                runtime_python=Path(values["--runtime-python"]),
                timeout_seconds=float(values["--timeout-seconds"]),
            )
        if command == "prepare-semantics":
            return SCORE_RUNTIME.prepare_semantics_attempt(attempt_root=attempt_root)
        if command == "finalize":
            return SCORE_RUNTIME.finalize_score_attempt(attempt_root=attempt_root)
        if command == "verify-score":
            return SCORE_RUNTIME.verify_score_attempt(attempt_root)
        raise AssertionError(arguments)

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
        self.assertEqual(len(view["recommended_actions"]), 2)
        self.assertTrue(
            all(action["action"] == "REGISTER_PROJECT" for action in view["recommended_actions"])
        )
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
        self.assertEqual(state["score_slots"], 3)
        self.assertTrue(all(len(task["prompt_sha256"]) == 64 for task in state["tasks"]))
        self.assertNotEqual(state["tasks"][0]["prompt_sha256"], state["tasks"][1]["prompt_sha256"])

    def test_operational_normal_prompt_uses_the_frozen_production_skill(self) -> None:
        fixture = Fixture(self.root / "normal-gate", task_ids=("task-one",))
        view = fixture.initialize(now=self.t0)
        self.assertIsNone(view["validation"])
        root = Path(view["orchestration_root"])
        state = json.loads((root / "orchestration-state.json").read_text())
        task = state["tasks"][0]
        prompt = (root / task["prompt_path"]).read_text(encoding="utf-8")
        manifest = json.loads(
            (root / task["attempt_path"] / "attempt-manifest.json").read_text()
        )
        self.assertIn("validation_mode：`production`", prompt)
        self.assertIn("当前冻结 Skill 为 `operational`", prompt)
        self.assertNotIn("允许当前 `interface_only` Skill 执行", prompt)
        self.assertIsNone(manifest["validation"])

    def test_acceptance_mode_is_frozen_in_state_prompt_manifest_and_digest(self) -> None:
        fixture = Fixture(self.root / "acceptance", task_ids=("task-one",))
        view = fixture.initialize(acceptance_id="G4-03", now=self.t0)
        self.assertEqual(
            view["validation"],
            {"mode": "acceptance", "acceptance_id": "G4-03"},
        )
        root = Path(view["orchestration_root"])
        state = json.loads((root / "orchestration-state.json").read_text())
        task = state["tasks"][0]
        prompt = (root / task["prompt_path"]).read_text(encoding="utf-8")
        manifest = json.loads(
            (root / task["attempt_path"] / "attempt-manifest.json").read_text()
        )
        self.assertEqual(state["prompt_protocol"], ORCHESTRATOR.PROMPT_PROTOCOL)
        self.assertEqual(manifest["validation"], state["validation"])
        self.assertIn("validation_mode：`acceptance`", prompt)
        self.assertIn("acceptance_id：`G4-03`", prompt)
        self.assertIn("仍须完整执行所有证据、查询、结构化判定、合分", prompt)
        self.assertIn(f"score_skill_root：`{SCORE_SKILL.resolve()}`", prompt)
        self.assertIn(
            f"score_skill_entrypoint：`{SCORE_RUNTIME_PATH.resolve()}`", prompt
        )
        self.assertIn("不得使用项目、仓库或自动发现路径中的同名 Skill", prompt)
        self.assertNotIn("使用 `$score-general-e2e`", prompt)
        self.assertIn("Selected model is at capacity. Please try a different model.", prompt)
        self.assertIn("同一任务内最多重试 5 次", prompt)
        self.assertIn("不要要求控制器新建评分任务", prompt)
        self.assertIn("候选本身没有产物", prompt)
        self.assertIn("不得因此终止控制会话、停止后续题目", prompt)
        changed = json.loads(json.dumps(state))
        changed["validation"] = {"mode": "acceptance", "acceptance_id": "G4-04"}
        self.assertNotEqual(state["queue_digest"], ORCHESTRATOR._queue_digest(changed))
        self.assertEqual(manifest["grading"]["type"], "llm_judge")
        self.assertEqual(manifest["judge"]["model"], "gpt-fixture")
        self.assertEqual(manifest["judge"]["reasoning_effort"], "high")

    def test_legacy_v3_prompt_remains_verifiable_without_frozen_path_fields(self) -> None:
        prompt = ORCHESTRATOR._prompt_text(
            "task-one",
            "attempt-one",
            {
                "protocol": "codex-agent-judge-v1",
                "model": "gpt-fixture",
                "reasoning_effort": "high",
            },
            "llm_judge",
            {"mode": "acceptance", "acceptance_id": "G4-03"},
            prompt_protocol="general-e2e-codex-scoring-prompt/v3",
        )
        self.assertTrue(prompt.startswith("使用 `$score-general-e2e`"))
        self.assertIn("prompt_protocol：`general-e2e-codex-scoring-prompt/v3`", prompt)
        self.assertNotIn("score_skill_root", prompt)

    def test_legacy_v4_prompt_keeps_frozen_score_skill_identity(self) -> None:
        prompt = ORCHESTRATOR._prompt_text(
            "task-one",
            "attempt-one",
            {
                "protocol": "codex-agent-judge-v1",
                "model": "gpt-fixture",
                "reasoning_effort": "high",
            },
            "llm_judge",
            None,
            {
                "path": str(SCORE_SKILL.resolve()),
                "version": "0.8.1",
                "implementation_status": "operational",
                "entrypoint": str(SCORE_RUNTIME_PATH.resolve()),
                "entrypoint_sha256": ORCHESTRATOR._sha256_file(SCORE_RUNTIME_PATH),
            },
            prompt_protocol="general-e2e-codex-scoring-prompt/v4",
        )
        self.assertIn("score_skill_root", prompt)
        self.assertIn("prompt_protocol：`general-e2e-codex-scoring-prompt/v4`", prompt)
        self.assertNotIn("使用 `$score-general-e2e`", prompt)

    def test_acceptance_marker_mismatch_and_api_backend_fail_closed(self) -> None:
        fixture = Fixture(self.root / "acceptance-mismatch", task_ids=("task-one",))
        view = fixture.initialize(acceptance_id="G4-03", now=self.t0)
        root = Path(view["orchestration_root"])
        state_path = root / "orchestration-state.json"
        state = json.loads(state_path.read_text())
        task = state["tasks"][0]
        manifest_path = root / task["attempt_path"] / "attempt-manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["validation"]["acceptance_id"] = "G4-04"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        state["tasks"][0]["attempt_manifest_sha256"] = ORCHESTRATOR._sha256_file(
            manifest_path
        )
        state["queue_digest"] = ORCHESTRATOR._queue_digest(state)
        state_path.write_text(json.dumps(state), encoding="utf-8")
        with self.assertRaisesRegex(
            ORCHESTRATOR.OrchestrationError, "SCORING_ATTEMPT_IDENTITY_MISMATCH"
        ):
            ORCHESTRATOR.status(root, now=self.t0)

        api_fixture = Fixture(
            self.root / "acceptance-api",
            task_ids=("task-api",),
            protocol="api-judge-v1",
            judge_model="api-fixture",
        )
        with self.assertRaisesRegex(
            ORCHESTRATOR.OrchestrationError,
            "ACCEPTANCE_MODE_REQUIRES_CODEX_JUDGE",
        ):
            api_fixture.initialize(
                acceptance_id="G4-03",
                api_runtime_config=api_fixture.api_runtime_config(),
                now=self.t0,
            )

    def test_three_semantic_slots_refill_without_blocking_on_earlier_tasks(self) -> None:
        task_ids = tuple(f"task-{index}" for index in range(1, 6))
        fixture = Fixture(self.root, task_ids=task_ids)
        view = fixture.initialize(now=self.t0)
        self.assertEqual(
            [action["task_id"] for action in view["recommended_actions"]],
            list(task_ids[:3]),
        )
        root = Path(view["orchestration_root"])
        self._record_fixture_score(root, task_ids[0], valid=True, total_score=0.8)
        with patch.object(
            ORCHESTRATOR,
            "_run_score_command",
            side_effect=self._fixture_score_command,
        ):
            refilled = ORCHESTRATOR.status(root, now=self.t0)
        self.assertEqual(
            [action["task_id"] for action in refilled["recommended_actions"]],
            list(task_ids[1:4]),
        )
        fourth = refilled["tasks"][3]
        with patch.object(
            ORCHESTRATOR,
            "_run_score_command",
            side_effect=self._fixture_score_command,
        ):
            ORCHESTRATOR.record_project(
                root,
                task_id=fourth["task_id"],
                project_id="project-four",
                host_id="host-local",
                project_path=Path(fourth["attempt_path"]),
                desktop_version="2026.918.1",
                now=self.t0,
            )
            with self.assertRaisesRegex(ORCHESTRATOR.OrchestrationError, "TASK_NOT_ACTIVE"):
                ORCHESTRATOR.record_project(
                    root,
                    task_id=task_ids[4],
                    project_id="project-five",
                    host_id="host-local",
                    project_path=Path(refilled["tasks"][4]["attempt_path"]),
                    desktop_version="2026.918.1",
                    now=self.t0,
                )

    def test_automated_and_hybrid_rules_do_not_consume_semantic_slots(self) -> None:
        hybrid = Fixture(
            self.root / "hybrid",
            task_ids=("task-hybrid",),
            grading_type="hybrid",
        )
        hybrid_view = hybrid.initialize(now=self.t0)
        self.assertEqual(hybrid_view["recommended_actions"][0]["action"], "RUN_RULE_COMPONENT")
        with patch.object(
            ORCHESTRATOR,
            "_run_score_command",
            side_effect=self._direct_local_score_command,
        ):
            hybrid_ready = ORCHESTRATOR.run_rule_score_task(
                Path(hybrid_view["orchestration_root"]),
                task_id="task-hybrid",
                runtime_python=Path(sys.executable),
                now=self.t0,
            )
        self.assertEqual(hybrid_ready["tasks"][0]["phase"], "AWAITING_PROJECT")
        self.assertEqual(hybrid_ready["recommended_actions"][0]["action"], "REGISTER_PROJECT")

        automated = Fixture(
            self.root / "automated",
            task_ids=("task-automated",),
            grading_type="automated",
        )
        automated_view = automated.initialize(now=self.t0)
        with patch.object(
            ORCHESTRATOR,
            "_run_score_command",
            side_effect=self._direct_local_score_command,
        ):
            automated_done = ORCHESTRATOR.run_rule_score_task(
                Path(automated_view["orchestration_root"]),
                task_id="task-automated",
                runtime_python=Path(sys.executable),
                now=self.t0,
            )
        self.assertEqual(automated_done["status"], "COMPLETED")
        self.assertEqual(automated_done["tasks"][0]["phase"], "SCORE_RECORDED")
        self.assertEqual(
            automated_done["recommended_actions"][0]["action"],
            "BUILD_SUBMISSION",
        )

    def test_automated_verification_bypasses_full_semantic_slots(self) -> None:
        task_ids = ("semantic-one", "semantic-two", "semantic-three", "automated")
        fixture = Fixture(
            self.root / "mixed-slots",
            task_ids=task_ids,
            grading_types=("llm_judge", "llm_judge", "llm_judge", "automated"),
        )
        view = fixture.initialize(now=self.t0)
        self.assertEqual(
            [
                (action["action"], action["task_id"])
                for action in view["recommended_actions"]
            ],
            [
                ("RUN_RULE_COMPONENT", "automated"),
                ("REGISTER_PROJECT", "semantic-one"),
                ("REGISTER_PROJECT", "semantic-two"),
                ("REGISTER_PROJECT", "semantic-three"),
            ],
        )
        root = Path(view["orchestration_root"])
        original_record_score = ORCHESTRATOR.record_score
        with (
            patch.object(
                ORCHESTRATOR,
                "_run_score_command",
                side_effect=self._direct_local_score_command,
            ),
            patch.object(
                ORCHESTRATOR,
                "record_score",
                side_effect=lambda orchestration_root, **_kwargs: ORCHESTRATOR.status(
                    orchestration_root, now=self.t0
                ),
            ),
        ):
            pending = ORCHESTRATOR.run_rule_score_task(
                root,
                task_id="automated",
                runtime_python=Path(sys.executable),
                now=self.t0,
            )
        self.assertEqual(pending["tasks"][3]["phase"], "SCORE_VERIFICATION_PENDING")
        self.assertEqual(
            [
                (action["action"], action["task_id"])
                for action in pending["recommended_actions"]
            ],
            [
                ("VERIFY_SCORE", "automated"),
                ("REGISTER_PROJECT", "semantic-one"),
                ("REGISTER_PROJECT", "semantic-two"),
                ("REGISTER_PROJECT", "semantic-three"),
            ],
        )
        with patch.object(
            ORCHESTRATOR,
            "_run_score_command",
            side_effect=self._direct_local_score_command,
        ):
            recorded = original_record_score(
                root,
                task_id="automated",
                now=self.t0,
            )
        self.assertEqual(recorded["tasks"][3]["phase"], "SCORE_RECORDED")
        self.assertEqual(
            [action["task_id"] for action in recorded["recommended_actions"]],
            list(task_ids[:3]),
        )

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
            side_effect=self._fixture_score_command,
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
        self.assertEqual(
            terminal["recommended_actions"][0]["action"], "BUILD_SUBMISSION"
        )

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

        # A user-authorized recovery may accept a late but explicitly completed
        # thread after re-verifying its frozen score. The default deadline
        # behavior above remains fail-closed.
        self._record_fixture_score(late_root, "task-one", valid=True, total_score=0.8)
        late_state_path = late_root / "orchestration-state.json"
        late_state = json.loads(late_state_path.read_text(encoding="utf-8"))
        late_task = late_state["tasks"][0]
        late_task["phase"] = "THREAD_FAILED"
        late_task["score"] = None
        late_state["status"] = ORCHESTRATOR._state_status(late_state)
        late_state_path.write_text(json.dumps(late_state), encoding="utf-8")
        with patch.object(
            ORCHESTRATOR,
            "_run_score_command",
            side_effect=self._fixture_score_command,
        ):
            recovered = ORCHESTRATOR.record_score(
                late_root,
                task_id="task-one",
                allow_late_completion=True,
                now=self.t0 + timedelta(seconds=13),
            )
        self.assertEqual(recovered["tasks"][0]["phase"], "SCORE_RECORDED")
        history = json.loads(late_state_path.read_text(encoding="utf-8"))["tasks"][0]["history"]
        self.assertEqual(history[-1]["event"], "SCORE_RECORDED_LATE_COMPLETION")

    def test_late_completion_replaces_only_the_strictly_reproducible_submission(self) -> None:
        fixture = Fixture(self.root, task_ids=("task-one",))
        view = fixture.initialize(timeout=10, now=self.t0)
        view = self._record_first_project(fixture, view)
        root = Path(view["orchestration_root"])
        ORCHESTRATOR.preflight(
            root,
            task_id="task-one",
            desktop_version="2026.918.1",
            now=self.t0,
        )
        ORCHESTRATOR.record_thread(
            root,
            task_id="task-one",
            thread_id="thread-late",
            host_id="host-local",
            now=self.t0,
        )
        ORCHESTRATOR.record_wait(
            root,
            task_id="task-one",
            wait_sequence=1,
            wait_cursor="cursor-late-terminal",
            wait_status="COMPLETED",
            now=self.t0 + timedelta(seconds=11),
        )
        with patch.object(
            ORCHESTRATOR,
            "_run_score_command",
            side_effect=self._fixture_score_command,
        ):
            ORCHESTRATOR.build_submission(
                root, now=self.t0 + timedelta(seconds=12)
            )
        previous_submission = (root / "submission.json").read_bytes()
        previous_sha = hashlib.sha256(previous_submission).hexdigest()
        self.assertEqual(
            json.loads(previous_submission)["tasks"][0]["score_status"],
            "unscored",
        )

        self._record_fixture_score(
            root, "task-one", valid=True, total_score=0.8
        )
        state_path = root / "orchestration-state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["tasks"][0]["phase"] = "THREAD_FAILED"
        state["tasks"][0]["score"] = None
        state["status"] = ORCHESTRATOR._state_status(state)
        state_path.write_text(json.dumps(state), encoding="utf-8")
        with patch.object(
            ORCHESTRATOR,
            "_run_score_command",
            side_effect=self._fixture_score_command,
        ):
            ORCHESTRATOR.record_score(
                root,
                task_id="task-one",
                allow_late_completion=True,
                now=self.t0 + timedelta(seconds=13),
            )
            with self.assertRaisesRegex(
                ORCHESTRATOR.OrchestrationError,
                "SUBMISSION_CONTENT_MISMATCH",
            ):
                ORCHESTRATOR.status(root, now=self.t0 + timedelta(seconds=14))
            replaced = ORCHESTRATOR.build_submission(
                root,
                replace_after_late_completion=True,
                now=self.t0 + timedelta(seconds=14),
            )
            repeated = ORCHESTRATOR.build_submission(
                root,
                replace_after_late_completion=True,
                now=self.t0 + timedelta(seconds=15),
            )

        archive = root / "submission-history" / f"{previous_sha}.json"
        self.assertEqual(archive.read_bytes(), previous_submission)
        replacement = json.loads((root / "submission.json").read_text())
        self.assertEqual(replacement["tasks"][0]["score_status"], "valid")
        self.assertEqual(replaced["completed_count"], 1)
        self.assertEqual(repeated["submission_path"], replaced["submission_path"])
        audit = json.loads(state_path.read_text())["submission_replacements"]
        self.assertEqual(len(audit), 1)
        self.assertEqual(
            audit[0]["event"],
            "SUBMISSION_REPLACED_AFTER_LATE_COMPLETION",
        )
        self.assertEqual(audit[0]["recovered_task_ids"], ["task-one"])
        self.assertEqual(audit[0]["previous"]["sha256"], previous_sha)
        self.assertEqual(
            audit[0]["replacement"]["sha256"],
            hashlib.sha256((root / "submission.json").read_bytes()).hexdigest(),
        )

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
        accepted = ORCHESTRATOR.initialize(
            unit_root=slot_fixture.unit_root,
            scoring_package=slot_fixture.scoring_package,
            report_config=slot_fixture.report_config,
            score_skill_dir=SCORE_SKILL,
            output_root=slot_fixture.output_root,
            orchestration_id="slot-fixture",
            execution_records=slot_fixture.execution_records,
            score_slots=8,
            now=self.t0,
        )
        self.assertEqual(accepted["score_slots"], 8)
        with self.assertRaisesRegex(
            ORCHESTRATOR.OrchestrationError, "SCORE_SLOTS_UNSUPPORTED"
        ):
            ORCHESTRATOR.initialize(
                unit_root=slot_fixture.unit_root,
                scoring_package=slot_fixture.scoring_package,
                report_config=slot_fixture.report_config,
                score_skill_dir=SCORE_SKILL,
                output_root=slot_fixture.output_root,
                orchestration_id="slot-overflow-fixture",
                execution_records=slot_fixture.execution_records,
                score_slots=9,
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

    def test_submission_distinguishes_zero_evaluation_error_and_unscored(self) -> None:
        fixture = Fixture(
            self.root,
            task_ids=("task-zero", "task-judge-error", "task-timeout"),
        )
        self._set_execution_status(
            fixture,
            "task-timeout",
            business_status="timeout",
            phase="FAILED",
        )
        view = fixture.initialize(now=self.t0)
        root = Path(view["orchestration_root"])
        self.assertEqual(view["tasks"][2]["phase"], "UNSCORED")
        self.assertIsNone(view["tasks"][2]["attempt_path"])
        self._record_fixture_score(root, "task-zero", valid=True, total_score=0.0)
        self._record_fixture_score(
            root, "task-judge-error", valid=False, total_score=None
        )
        with patch.object(
            ORCHESTRATOR,
            "_run_score_command",
            side_effect=self._fixture_score_command,
        ):
            completed = ORCHESTRATOR.status(root, now=self.t0)
            self.assertEqual(completed["terminal_count"], 3)
            self.assertEqual(completed["valid_score_count"], 1)
            self.assertEqual(completed["evaluation_error_count"], 1)
            self.assertEqual(completed["unscored_count"], 1)
            self.assertEqual(
                completed["recommended_actions"][0]["action"], "BUILD_SUBMISSION"
            )
            built = ORCHESTRATOR.build_submission(root, now=self.t0)
            repeated = ORCHESTRATOR.build_submission(root, now=self.t0)
        self.assertEqual(built["submission_path"], repeated["submission_path"])
        submission = json.loads((root / "submission.json").read_text())
        self.assertEqual(
            [item["task_id"] for item in submission["tasks"]], fixture.task_ids
        )
        by_id = {item["task_id"]: item for item in submission["tasks"]}
        self.assertEqual(by_id["task-zero"]["score_status"], "valid")
        score = json.loads((root / by_id["task-zero"]["score_path"]).read_text())
        self.assertEqual(score["result"]["total_score"], 0.0)
        self.assertEqual(
            by_id["task-judge-error"]["score_status"], "evaluation_error"
        )
        self.assertIsNotNone(by_id["task-judge-error"]["score_sha256"])
        self.assertEqual(by_id["task-timeout"]["score_status"], "unscored")
        self.assertIsNone(by_id["task-timeout"]["scoring_attempt_id"])
        self.assertIsNone(by_id["task-timeout"]["judge_protocol"])
        self.assertIsNone(by_id["task-timeout"]["score_path"])
        self.assertIsNone(by_id["task-timeout"]["score_sha256"])

        submission["task_ids"] = submission["task_ids"][:-1]
        submission["tasks"] = submission["tasks"][:-1]
        submission["task_count"] -= 1
        (root / "submission.json").write_text(json.dumps(submission), encoding="utf-8")
        state_path = root / "orchestration-state.json"
        state = json.loads(state_path.read_text())
        state["submission"]["sha256"] = hashlib.sha256(
            (root / "submission.json").read_bytes()
        ).hexdigest()
        state_path.write_text(json.dumps(state), encoding="utf-8")
        with patch.object(
            ORCHESTRATOR,
            "_run_score_command",
            side_effect=self._fixture_score_command,
        ):
            with self.assertRaisesRegex(
                ORCHESTRATOR.OrchestrationError, "SUBMISSION_CONTENT_MISMATCH"
            ):
                ORCHESTRATOR.status(root, now=self.t0)
            with self.assertRaisesRegex(
                ORCHESTRATOR.OrchestrationError, "SUBMISSION_CONTENT_MISMATCH"
            ):
                ORCHESTRATOR.build_submission(
                    root,
                    replace_after_late_completion=True,
                    now=self.t0,
                )

    def test_incomplete_evidence_is_unscored_without_judge_attempt(self) -> None:
        fixture = Fixture(self.root, task_ids=("task-one",))
        self._set_execution_status(
            fixture,
            "task-one",
            business_status="completed",
            phase="COMPLETED",
            completeness="partial",
        )
        view = fixture.initialize(now=self.t0)
        self.assertEqual(view["status"], "COMPLETED_WITH_FAILURES")
        self.assertEqual(view["unscored_count"], 1)
        self.assertEqual(view["tasks"][0]["phase"], "UNSCORED")
        self.assertIsNone(view["tasks"][0]["scoring_attempt_id"])
        self.assertIsNone(view["tasks"][0]["attempt_path"])
        root = Path(view["orchestration_root"])
        self.assertFalse((root / "attempts").exists())
        built = ORCHESTRATOR.build_submission(root, now=self.t0)
        self.assertEqual(built["unscored_count"], 1)

    def test_rescore_orchestration_uses_new_attempt_and_preserves_source(self) -> None:
        fixture = Fixture(
            self.root / "source",
            task_ids=("task-one",),
            protocol="api-judge-v1",
            judge_model="api-fixture",
        )
        api_runtime = fixture.api_runtime_config()
        view = fixture.initialize(api_runtime_config=api_runtime, now=self.t0)
        source_root = Path(view["orchestration_root"])
        def direct_score_command(_lock, arguments, **_kwargs):
            command = arguments[0]
            values = {
                arguments[index]: arguments[index + 1]
                for index in range(1, len(arguments) - 1, 2)
                if arguments[index].startswith("--")
            }
            if command == "verify":
                return SCORE_RUNTIME.verify_attempt(Path(values["--attempt-root"]))
            if command == "verify-score":
                return SCORE_RUNTIME.verify_score_attempt(
                    Path(values["--attempt-root"])
                )
            if command == "run-api-score":
                return SCORE_RUNTIME.run_api_score_attempt(
                    attempt_root=Path(values["--attempt-root"]),
                    runtime_python=Path(values["--runtime-python"]),
                    timeout_seconds=float(values["--timeout-seconds"]),
                )
            if command == "prepare-rescore":
                return SCORE_RUNTIME.prepare_rescore_attempt(
                    source_attempt_root=Path(values["--source-attempt-root"]),
                    scoring_attempt_id=values["--scoring-attempt-id"],
                    output_root=Path(values["--output-root"]),
                    judge_protocol=values["--judge-protocol"],
                    judge_model=values["--judge-model"],
                    judge_reasoning_effort=values["--judge-reasoning-effort"],
                    judge_attempt_id=values["--judge-attempt-id"],
                    acceptance_id=values.get("--acceptance-id"),
                )
            raise AssertionError(arguments)

        with (
            patch.dict(
                os.environ, {"GENERAL_E2E_TEST_API_KEY": ""}, clear=False
            ),
            patch.object(
                ORCHESTRATOR,
                "_run_score_command",
                side_effect=direct_score_command,
            ),
        ):
            source_done = ORCHESTRATOR.run_api_score_task(
                source_root,
                task_id="task-one",
                runtime_python=Path(sys.executable),
                now=self.t0,
            )
        self.assertEqual(source_done["evaluation_error_count"], 1)
        with patch.object(
            ORCHESTRATOR,
            "_run_score_command",
            side_effect=direct_score_command,
        ):
            ORCHESTRATOR.build_submission(source_root, now=self.t0)
        source_hashes = {
            path.relative_to(source_root).as_posix(): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for path in source_root.rglob("*")
            if path.is_file()
        }
        report = json.loads(fixture.report_config.read_text())
        report["judge"] = {
            "protocol": "codex-agent-judge-v1",
            "model": "gpt-rescore-fixture",
            "reasoning_effort": "high",
        }
        rescore_report = fixture.root / "rescore-report-config.json"
        rescore_report.write_text(json.dumps(report), encoding="utf-8")
        with patch.object(
            ORCHESTRATOR,
            "_run_score_command",
            side_effect=direct_score_command,
        ):
            rescore = ORCHESTRATOR.initialize_rescore(
                source_orchestration_root=source_root,
                report_config=rescore_report,
                score_skill_dir=SCORE_SKILL,
                output_root=fixture.output_root,
                orchestration_id="rescore-fixture",
                acceptance_id="G4-03",
                now=self.t0,
            )
        self.assertEqual(rescore["judge"]["protocol"], "codex-agent-judge-v1")
        self.assertEqual(
            rescore["validation"],
            {"mode": "acceptance", "acceptance_id": "G4-03"},
        )
        self.assertEqual(rescore["tasks"][0]["phase"], "AWAITING_PROJECT")
        source_state = json.loads(
            (source_root / "orchestration-state.json").read_text()
        )
        rescore_state = json.loads(
            (Path(rescore["orchestration_root"]) / "orchestration-state.json").read_text()
        )
        rescore_attempt = (
            Path(rescore["orchestration_root"])
            / rescore_state["tasks"][0]["attempt_path"]
        )
        rescore_manifest = json.loads(
            (rescore_attempt / "attempt-manifest.json").read_text()
        )
        self.assertEqual(rescore_manifest["validation"], rescore_state["validation"])
        self.assertNotEqual(
            source_state["tasks"][0]["scoring_attempt_id"],
            rescore_state["tasks"][0]["scoring_attempt_id"],
        )
        self.assertEqual(
            source_state["tasks"][0]["execution"]["candidate_sha256"],
            rescore_state["tasks"][0]["execution"]["candidate_sha256"],
        )
        current_source_hashes = {
            path.relative_to(source_root).as_posix(): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for path in source_root.rglob("*")
            if path.is_file()
        }
        self.assertEqual(source_hashes, current_source_hashes)
        with (
            patch.object(
                ORCHESTRATOR,
                "_run_score_command",
                side_effect=direct_score_command,
            ),
            self.assertRaisesRegex(
                ORCHESTRATOR.OrchestrationError, "ORCHESTRATION_EXISTS"
            ),
        ):
            ORCHESTRATOR.initialize_rescore(
                source_orchestration_root=source_root,
                report_config=rescore_report,
                score_skill_dir=SCORE_SKILL,
                output_root=fixture.output_root,
                orchestration_id="rescore-fixture",
                now=self.t0,
            )


if __name__ == "__main__":
    unittest.main()
