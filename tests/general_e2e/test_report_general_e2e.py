from __future__ import annotations

import argparse
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "tools/report/skills/general-e2e/report-general-e2e/scripts/report_general_e2e.py"
SPEC = importlib.util.spec_from_file_location("report_general_e2e_tested", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
REPORT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = REPORT
SPEC.loader.exec_module(REPORT)

RUN_SCRIPT = REPO_ROOT / "tools/report/skills/general-e2e/run-general-e2e/scripts/run_general_e2e.py"
RUN_SPEC = importlib.util.spec_from_file_location("run_general_e2e_for_report_test", RUN_SCRIPT)
assert RUN_SPEC is not None and RUN_SPEC.loader is not None
RUN = importlib.util.module_from_spec(RUN_SPEC)
sys.modules[RUN_SPEC.name] = RUN
RUN_SPEC.loader.exec_module(RUN)

EXAMPLES = REPO_ROOT / "eval_general_e2e/contracts/examples/valid"
DATASET_DIGEST = "1" * 64
RELEASE_DIGEST = "2" * 64
TASKS = ["task-zero", "task-valid", "task-error", "task-unscored"]


class DatasetReportMetadataTests(unittest.TestCase):
    def row(self, *, task_id="general_hard_research_verification_task_001_example", label="研究检索与证据核验"):
        contract = {"schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-hard",
                    "category": "research_verification", "category_name": label, "category_order": 2,
                    "checkpoint_capabilities": {"automated.evidence": ["retrieval_verification"]}}
        text = "---\nid: " + task_id + "\ndataset_report: " + json.dumps(contract, ensure_ascii=False) + "\n---\n## Prompt\nFind evidence.\n"
        definition = REPORT.report_case_views.parse_task(text)
        definition.update(status="complete", task_sha256=hashlib.sha256(text.encode()).hexdigest())
        return {"task_id": task_id, "category": "research_verification", "task_definition": definition,
                "score_status": "valid", "checkpoints": {"values": {"automated.evidence": .75}}}

    def test_dataset_labels_and_capabilities_come_from_frozen_private_task(self):
        row = self.row()
        references = {"capabilities": {"legacy": {"key": ["code_generation"]}}}
        mapping, names, order, sources = REPORT.report_views.dataset_references({"tasks": [row]}, references)
        self.assertEqual(names["research_verification"], "研究检索与证据核验")
        self.assertEqual(order["research_verification"], 2)
        score = REPORT.report_views.capability_scores([row], mapping)
        self.assertEqual(score["retrieval_verification"], {"score": .75, "known": 1, "total": 1})
        self.assertEqual(sources[0]["task_sha256"], row["task_definition"]["task_sha256"])
        self.assertNotIn(row["task_id"], references["capabilities"])

    def test_conflicting_or_unverified_dataset_metadata_fails_closed(self):
        first = self.row()
        second = self.row(label="另一个定义")
        with self.assertRaisesRegex(ValueError, "METADATA_CONFLICT"):
            REPORT.report_views.dataset_references({"tasks": [first, second]}, {"capabilities": {}})
        first["task_definition"]["status"] = "unavailable"
        with self.assertRaisesRegex(ValueError, "METADATA_INVALID"):
            REPORT.report_views.dataset_references({"tasks": [first]}, {"capabilities": {}})
        with self.assertRaisesRegex(ValueError, "METADATA_INVALID"):
            REPORT.report_case_views.parse_task("---\nid: example\ndataset_report: broken\n---\n")

    def test_round_view_resolves_and_validates_nested_frozen_metadata(self):
        first = self.row()
        second = copy.deepcopy(first)
        second["checkpoints"]["values"]["automated.evidence"] = .25
        rounds = {"task_id": first["task_id"], "category": first["category"], "rounds": [first, second]}
        mapping, names, _, sources = REPORT.report_views.dataset_references({"tasks": [rounds]}, {"capabilities": {}})
        self.assertEqual(names[first["category"]], "研究检索与证据核验")
        self.assertEqual(len(sources), 1)
        self.assertEqual(REPORT.report_views.capability_scores([rounds], mapping)["retrieval_verification"],
                         {"score": .5, "known": 1, "total": 1})
        second["task_definition"]["dataset_report"]["category_name"] = "冲突的轮次定义"
        with self.assertRaisesRegex(ValueError, "METADATA_CONFLICT"):
            REPORT.report_views.dataset_references({"tasks": [rounds]}, {"capabilities": {}})

    def test_explicit_null_duplicate_or_five_dimension_metadata_fails_closed(self):
        for front in ["dataset_report: null", "dataset_report: []", "dataset_report: {}\ndataset_report: {}"]:
            with self.subTest(front=front), self.assertRaisesRegex(ValueError, "METADATA_INVALID"):
                REPORT.report_case_views.parse_task("---\nid: example\n" + front + "\n---\n")
        row = self.row()
        row["task_definition"]["dataset_report"]["checkpoint_capabilities"] = {"llm_judge.intent": ["intent_understanding"]}
        with self.assertRaisesRegex(ValueError, "CAPABILITY_MAP_INVALID"):
            REPORT.report_views.dataset_references({"tasks": [row]}, {"capabilities": {}})

    def test_missing_frozen_metadata_does_not_read_current_source_or_invent_coverage(self):
        row = self.row()
        row["task_definition"] = {"status": "unavailable"}
        mapping, names, _, sources = REPORT.report_views.dataset_references({"tasks": [row]}, {"capabilities": {}})
        self.assertNotIn(row["task_id"], mapping)
        self.assertNotIn("research_verification", names)
        self.assertEqual(sources, [])
        self.assertEqual(REPORT.report_views.capability_scores([row], mapping)["retrieval_verification"]["score"], None)


def load_example(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Fixture:
    def __init__(self, root: Path, *, partial_collect: bool = False) -> None:
        self.root = root
        self.batch = root / "batch"
        self.unit_id = "astronstudio-macos"
        self.package_id = ""
        self.target = self.batch / "returns" / self.unit_id / ".pending"
        self.dataset = {"id": "general-custom60-v1", "digest": DATASET_DIGEST, "bundle_sha256": "3" * 64}
        self.release = {"id": "release-one", "catalog_digest": RELEASE_DIGEST, "catalog_sha256": "4" * 64, "suite_sha256": "5" * 64}
        self.partial_collect = partial_collect
        self.unit = {
            "unit_id": self.unit_id,
            "task_ids": TASKS,
            "harness": {"id": "astronstudio", "platform": "macos-x86-64", "version": "3.3.1"},
            "model": {"requested_id": "candidate-model", "reasoning_effort": "high"},
            "execution_mode": "automatic",
        }
        self.build()

    def identity(self, task_id: str, attempt: str) -> dict:
        return {"batch_id": "batch-report", "unit_id": self.unit_id, "task_id": task_id, "attempt_id": attempt}

    def resource(self, task_id: str, attempt: str, *, partial: bool = False) -> dict:
        value = copy.deepcopy(load_example("resource-metrics-zero.json"))
        value["identity"] = self.identity(task_id, attempt)
        coverage = {}
        known_subtotals = {}
        for field, group, _ in REPORT.RESOURCE_FIELDS:
            metric = value["metrics"][group][field]
            coverage[field] = {
                "known": 0 if metric["status"] == "unavailable" else 1,
                "total": 1,
                "unit": "fixture",
            }
        if partial:
            value["collection"]["status"] = "partial"
            value["metrics"]["usage"]["input_tokens"] = {"value": None, "status": "partial", "basis": "one of two events visible"}
            coverage["input_tokens"] = {"known": 1, "total": 2, "unit": "usage_update"}
            known_subtotals["input_tokens"] = 5
        value["collection"]["coverage"] = coverage
        value["collection"]["known_subtotals"] = known_subtotals
        value["collection"]["metric_sources"] = {field: ["fixture.json"] for field, _, _ in REPORT.RESOURCE_FIELDS}
        return value

    def score(self, task_id: str, scoring_attempt: str, execution_attempt: str, execution_record_sha: str, *, total: float | None, protocol: str) -> dict:
        value = copy.deepcopy(load_example("score-zero.json"))
        value["identity"] = self.identity(task_id, scoring_attempt)
        value["dataset"] = {"id": self.dataset["id"], "digest": self.dataset["digest"]}
        value["execution"]["attempt_id"] = execution_attempt
        value["execution"]["record_sha256"] = execution_record_sha
        value["judge"] = {
            "protocol": protocol,
            "model": None if protocol == "not-required" else ("judge-codex" if protocol == "codex-agent-judge-v1" else "judge-api"),
            "reasoning_effort": None if protocol == "not-required" else "high",
            "attempt_id": "judge-not-required" if protocol == "not-required" else f"judge-{task_id}",
        }
        if total is None:
            value["components"] = {
                "rules": {"status": "not_required", "score": None},
                "semantics": {"status": "evaluation_error", "score": None},
            }
            value["evaluation"] = {
                "status": "evaluation_error",
                "criteria": [{"key": "semantic", "weight": 1.0, "status": "unresolved", "score": None, "reason": "judge service failed", "evidence": [{"type": "audit", "path": "semantic/audit.json"}]}],
                "error": {"code": "JUDGE_FAILED", "message": "judge service failed"},
            }
            value["result"] = {"valid": False, "total_score": None, "invalid_reason": "JUDGE_FAILED"}
        else:
            value["result"] = {"valid": True, "total_score": total, "invalid_reason": None}
            value["evaluation"]["criteria"][0]["score"] = total
            if protocol != "not-required":
                value["components"] = {
                    "rules": {"status": "not_required", "score": None},
                    "semantics": {"status": "completed", "score": total},
                }
        return value

    def execution(self, task_id: str, attempt: str, index: int, resource_path: str | None) -> dict:
        value = copy.deepcopy(load_example("execution-record.json"))
        value["identity"] = self.identity(task_id, attempt)
        value["dataset"] = {"id": self.dataset["id"], "digest": self.dataset["digest"]}
        value["harness"] = self.unit["harness"]
        value["model"] = {
            "requested_id": self.unit["model"]["requested_id"],
            "actual_id": self.unit["model"]["requested_id"],
            # AstronStudio reports the UI display label while the batch
            # manifest stores the canonical enum value.
            "reasoning_effort": self.unit["model"]["reasoning_effort"].title(),
            "verification_status": "verified",
        }
        start = datetime(2026, 9, 18, 1, 0, tzinfo=timezone.utc) + timedelta(seconds=index * 10)
        value["execution"]["started_at"] = start.isoformat()
        value["execution"]["finished_at"] = (start + timedelta(seconds=5)).isoformat()
        value["resource_metrics_path"] = resource_path
        return value

    def build(self) -> None:
        batch_manifest = {
            "schema_id": REPORT.PACKAGE_SCHEMA,
            "schema_version": 1,
            "manifest_kind": "batch",
            "contract_version": "general-e2e-contract-v1",
            "bundle_protocol": "general-e2e-package-v1",
            "batch_id": "batch-report",
            "dataset": self.dataset,
            "release": self.release,
            "task_ids": TASKS,
            "units": [self.unit],
            "required_skills": [],
            "skill_artifacts": [],
            "artifacts": [],
        }
        write_json(self.batch / "manifest.json", batch_manifest)
        report_config = {
            "schema_version": REPORT.REPORT_CONFIG_SCHEMA,
            "batch_id": "batch-report",
            "dataset": self.dataset,
            "release": self.release,
            "judge": {"protocol": "codex-agent-judge-v1", "model": "judge-codex", "reasoning_effort": "high"},
            "report": {"title": "General E2E fixture"},
            "units": [self.unit],
        }
        write_json(self.batch / "report-config.json", report_config)

        task_meta = []
        submission_tasks = []
        status_specs = [
            ("valid", 0.0, "not-required"),
            ("valid", 0.8, "codex-agent-judge-v1"),
            ("evaluation_error", None, "api-judge-v1"),
            ("unscored", None, None),
        ]
        for index, (task_id, spec) in enumerate(zip(TASKS, status_specs)):
            status, total, protocol = spec
            execution_attempt = f"exec-{index + 1}"
            scoring_attempt = f"score-{index + 1}" if status != "unscored" else None
            resource_relative = None if index >= 2 else f"evidence/{task_id}/resource-metrics.json"
            execution = self.execution(task_id, execution_attempt, index, resource_relative)
            execution_path = self.target / "scoring/execution-records" / f"{task_id}.json"
            write_json(execution_path, execution)
            if resource_relative:
                write_json(self.target / "unit" / resource_relative, self.resource(task_id, execution_attempt, partial=index == 1))
            score_path_value = None
            score_sha = None
            if status != "unscored":
                score_path_value = f"attempts/{scoring_attempt}/score.json"
                score_path = self.target / "scoring" / score_path_value
                write_json(
                    score_path,
                    self.score(
                        task_id,
                        scoring_attempt,
                        execution_attempt,
                        sha256(execution_path),
                        total=total,
                        protocol=protocol,
                    ),
                )
                score_sha = sha256(score_path)
            submission_tasks.append({
                "task_id": task_id,
                "execution_attempt_id": execution_attempt,
                "execution_status": "completed",
                "scoring_attempt_id": scoring_attempt,
                "judge_protocol": protocol,
                "score_status": status,
                "score_path": score_path_value,
                "score_sha256": score_sha,
                "candidate_sha256": "bcde"[index] * 64,
                "evidence_sha256": "6789"[index] * 64,
            })
            task_meta.append({
                "task_id": task_id,
                "order": index + 1,
                "name": f"Task {index + 1}",
                "category": f"0{index + 1}_Category",
                "difficulty": f"L{index + 1}",
                "modality": "pure-text",
                "timeout_seconds": 300,
                "prompt": {},
                "workspace": {},
            })
        unit_manifest = {
            "schema_id": REPORT.PACKAGE_SCHEMA,
            "schema_version": 1,
            "manifest_kind": "execution",
            "contract_version": "general-e2e-contract-v1",
            "bundle_protocol": "general-e2e-package-v1",
            "batch_id": "batch-report",
            "unit_id": self.unit_id,
            "dataset": self.dataset,
            "release": self.release,
            "task_ids": TASKS,
            "unit": self.unit,
            "tasks": task_meta,
            "required_skills": [],
        }
        write_json(self.target / "unit/manifest.json", unit_manifest)
        collect_receipt = {
            "schema_id": REPORT.RECEIPT_SCHEMA,
            "schema_version": 1,
            "scope": {"batch_id": "batch-report", "unit_id": self.unit_id},
            "dataset": {"id": self.dataset["id"], "digest": self.dataset["digest"]},
            "stage": "collect-evidence",
            "status": "partial" if self.partial_collect else "completed",
            "created_at": "2026-09-18T01:09:00+00:00",
            "task_ids": TASKS,
            "tasks": [{
                "task_id": task_id,
                "attempt_id": f"exec-{index + 1}",
                "status": "partial" if self.partial_collect else "completed",
            } for index, task_id in enumerate(TASKS)],
            "artifacts": [],
            "integrity": {"scope_matches": True, "identities_match": True, "hashes_verified": True, "valid": True},
            "error": None,
        }
        write_json(self.target / "unit/receipts/collect-evidence-receipt.json", collect_receipt)
        submission = {
            "schema_id": REPORT.SUBMISSION_SCHEMA,
            "schema_version": 1,
            "scope": {"batch_id": "batch-report", "unit_id": self.unit_id},
            "dataset": {"id": self.dataset["id"], "digest": self.dataset["digest"]},
            "created_at": "2026-09-18T01:10:00+00:00",
            "task_count": len(TASKS),
            "task_ids": TASKS,
            "tasks": submission_tasks,
            "integrity": {"scope_matches": True, "identities_match": True, "hashes_verified": True, "valid": True},
        }
        write_json(self.target / "scoring/submission.json", submission)

        entries = []
        for path in sorted((self.target / "unit").rglob("*")) + sorted((self.target / "scoring").rglob("*")):
            if not path.is_file():
                continue
            data = path.read_bytes()
            entries.append({
                "path": path.relative_to(self.target).as_posix(),
                "kind": "file",
                "mode": f"{path.stat().st_mode & 0o777:04o}",
                "sha256": hashlib.sha256(data).hexdigest(),
                "size": len(data),
            })
        package_manifest = {
            "schema_id": REPORT.RETURN_SCHEMA,
            "schema_version": 1,
            "contract_version": "general-e2e-contract-v1",
            "bundle_protocol": "general-e2e-package-v1",
            "package_kind": "return",
            "package_id": None,
            "identity": {
                "batch_id": "batch-report",
                "unit_id": self.unit_id,
                "dataset": self.dataset,
                "release": self.release,
                "task_ids": TASKS,
            },
            "sources": {
                "unit_manifest_sha256": sha256(self.target / "unit/manifest.json"),
                "collect_receipt_sha256": sha256(self.target / "unit/receipts/collect-evidence-receipt.json"),
                "submission_sha256": sha256(self.target / "scoring/submission.json"),
            },
            "entry_count": len(entries),
            "entries": entries,
        }
        self.package_id = REPORT.return_package_id(package_manifest)
        package_manifest["package_id"] = self.package_id
        write_json(self.target / "package-manifest.json", package_manifest)
        final_target = self.batch / "returns" / self.unit_id / self.package_id
        final_target.parent.mkdir(parents=True, exist_ok=True)
        self.target.rename(final_target)
        self.target = final_target
        package_receipt = {
            "schema_id": REPORT.RECEIPT_SCHEMA,
            "schema_version": 1,
            "scope": {"batch_id": "batch-report", "unit_id": self.unit_id},
            "dataset": {"id": self.dataset["id"], "digest": self.dataset["digest"]},
            "stage": "package",
            "status": "completed",
            "created_at": "2026-09-18T01:10:00+00:00",
            "task_ids": TASKS,
            "tasks": [{"task_id": task_id, "attempt_id": f"exec-{index + 1}", "status": "completed"} for index, task_id in enumerate(TASKS)],
            "artifacts": [
                {"path": "package-manifest.json", "sha256": sha256(self.target / "package-manifest.json"), "size": (self.target / "package-manifest.json").stat().st_size},
                {"path": "scoring/submission.json", "sha256": sha256(self.target / "scoring/submission.json"), "size": (self.target / "scoring/submission.json").stat().st_size},
            ],
            "integrity": {"scope_matches": True, "identities_match": True, "hashes_verified": True, "valid": True},
            "error": None,
        }
        write_json(self.target / "receipts/package-receipt.json", package_receipt)
        receipt = {
            "schema_id": REPORT.RECEIPT_SCHEMA,
            "schema_version": 1,
            "scope": {"batch_id": "batch-report", "unit_id": self.unit_id},
            "dataset": {"id": self.dataset["id"], "digest": self.dataset["digest"]},
            "stage": "import-return",
            "status": "completed",
            "created_at": "2026-09-18T01:20:00+00:00",
            "task_ids": TASKS,
            "tasks": [{"task_id": task_id, "attempt_id": f"exec-{index + 1}", "status": "completed"} for index, task_id in enumerate(TASKS)],
            "artifacts": [],
            "integrity": {"scope_matches": True, "identities_match": True, "hashes_verified": True, "valid": True},
            "error": None,
        }
        write_json(self.target / "receipts/import-return-receipt.json", receipt)
        index = {
            "schema_version": REPORT.IMPORT_INDEX_SCHEMA,
            "revision": 1,
            "batch_id": "batch-report",
            "units": {
                self.unit_id: {
                    "logical_identity_sha256": REPORT.sha256_bytes(
                        REPORT.canonical_json_bytes(package_manifest["identity"])
                    ),
                    "selected_package_id": self.package_id,
                    "conflict": False,
                    "imports": [{
                        "package_id": self.package_id,
                        "archive_sha256": "e" * 64,
                        "target": self.target.relative_to(self.batch).as_posix(),
                        "receipt": (self.target / "receipts/import-return-receipt.json").relative_to(self.batch).as_posix(),
                        "imported_at": "2026-09-18T01:20:00+00:00",
                    }],
                }
            },
            "updated_at": "2026-09-18T01:20:00+00:00",
        }
        write_json(self.batch / ".general-e2e/run-general-e2e-import-index.json", index)


class ReportGeneralE2ETests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="general-e2e-report-test-")
        self.root = Path(self.temp_dir.name)
        self.fixture = Fixture(self.root)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def data(self) -> dict:
        validated = REPORT.validate_batch_inputs(self.fixture.batch)
        return REPORT.aggregate(validated, "2026-09-18T02:00:00Z")

    def test_valid_zero_errors_groups_and_resource_denominators_are_preserved(self) -> None:
        data = self.data()
        score = data["overall"]["score"]
        self.assertEqual(score["frozen_task_run_count"], 4)
        self.assertEqual(score["valid_score_count"], 2)
        self.assertEqual(score["evaluation_error_count"], 1)
        self.assertEqual(score["unscored_count"], 1)
        self.assertEqual(score["valid_zero_score_count"], 1)
        self.assertAlmostEqual(score["mean_score"], 0.4)
        self.assertEqual(len(data["overall"]["categories"]), 4)
        self.assertEqual(len(data["overall"]["difficulties"]), 4)
        groups = {(row["protocol"], row["model"]) for row in data["overall"]["judge_groups"]}
        self.assertIn(("codex-agent-judge-v1", "judge-codex"), groups)
        self.assertIn(("api-judge-v1", "judge-api"), groups)
        self.assertIn(("not-required", None), groups)
        self.assertIn((None, None), groups)

        input_tokens = data["overall"]["resources"]["input_tokens"]
        self.assertEqual(input_tokens["status"], "partial")
        self.assertIsNone(input_tokens["total"])
        self.assertEqual(input_tokens["known_subtotal"], 5)
        self.assertEqual(input_tokens["coverage"], {"known": 1, "total": 4, "unit": "task_run"})
        total_tokens = data["overall"]["resources"]["total_tokens"]
        self.assertIsNone(total_tokens["total"])
        self.assertEqual(total_tokens["known_subtotal"], 0)
        self.assertEqual(data["overall"]["timing"]["batch_wall_clock_seconds"], 35.0)

    def test_import_selection_is_required(self) -> None:
        path = self.fixture.batch / ".general-e2e/run-general-e2e-import-index.json"
        index = json.loads(path.read_text())
        index["units"][self.fixture.unit_id]["selected_package_id"] = None
        write_json(path, index)
        with self.assertRaisesRegex(REPORT.ReportError, "IMPORT_SELECTION_REQUIRED"):
            REPORT.validate_batch_inputs(self.fixture.batch)

    def test_valid_partial_collect_receipt_is_reportable(self) -> None:
        with tempfile.TemporaryDirectory(prefix="general-e2e-partial-report-") as temporary:
            fixture = Fixture(Path(temporary), partial_collect=True)
            validated = REPORT.validate_batch_inputs(fixture.batch)
            data = REPORT.aggregate(validated, "2026-09-18T02:00:00Z")
            self.assertEqual(data["overall"]["score"]["frozen_task_run_count"], 4)

    def test_post_import_file_drift_fails_closed(self) -> None:
        score_path = self.fixture.target / "scoring/attempts/score-1/score.json"
        score_path.write_text(score_path.read_text() + " ", encoding="utf-8")
        with self.assertRaisesRegex(REPORT.ReportError, "RETURN_ENTRY_DRIFT"):
            REPORT.validate_batch_inputs(self.fixture.batch)

    def test_post_import_extra_file_fails_closed(self) -> None:
        extra = self.fixture.target / "scoring/unexpected.txt"
        extra.write_text("unexpected", encoding="utf-8")
        with self.assertRaisesRegex(REPORT.ReportError, "RETURN_MEMBER_SET_MISMATCH"):
            REPORT.validate_batch_inputs(self.fixture.batch)

    def test_cli_adapter_preserves_zero_and_null_without_legacy_fill(self) -> None:
        data = self.data()
        output = self.root / "report"
        output.mkdir()
        manifest = REPORT.write_cli_adapter(output, data)
        zero = json.loads((output / "cli-adapter/units/astronstudio-macos/task-zero/score.json").read_text())
        error = json.loads((output / "cli-adapter/units/astronstudio-macos/task-error/score.json").read_text())
        self.assertEqual(zero["overall_score"], 0.0)
        self.assertFalse(zero["legacy_zero_filled"])
        self.assertIsNone(error["overall_score"])
        self.assertTrue(error["evaluation_error"])
        self.assertFalse(error["legacy_zero_filled"])
        self.assertTrue(manifest.is_file())

    def test_markdown_and_receipt_use_the_same_aggregate(self) -> None:
        data = self.data()
        markdown = REPORT.render_markdown(data)
        self.assertIn("模型@Harness | 总平均分", markdown)
        self.assertIn("40.00", markdown)
        self.assertIn("## 效率对比", markdown)
        self.assertNotIn("总成本", markdown)
        self.assertNotIn("超时数", markdown)
        self.assertNotIn("/Users/", markdown)
        output = self.root / "artifacts"
        output.mkdir()
        data_path = output / "general_e2e_report_data.json"
        md_path = output / "report.md"
        write_json(data_path, data)
        md_path.write_text(markdown, encoding="utf-8")
        receipt = REPORT.build_report_receipt(data, output, [data_path, md_path])
        REPORT.CONTRACTS.validate_contract(receipt, expected_schema_id=REPORT.RECEIPT_SCHEMA)
        self.assertEqual(receipt["scope"]["unit_id"], "batch")
        self.assertEqual(receipt["task_ids"], TASKS)

    def test_display_rounding_matches_excel_without_changing_source_values(self) -> None:
        # Real r28 L1 average: Python's default .2f rounded this to 95.62,
        # whereas Excel's 0.00 number format displays 95.63.
        data = self.data()
        view = data["presentation"]["tables"]["难度对比"]
        view["rows"][0][1] = 95.625
        before = copy.deepcopy(data)
        self.assertIn("95.63", REPORT.render_markdown(data))
        self.assertEqual(data, before)
        self.assertEqual(REPORT.fixed_number(0.95625, multiplier=100), "95.63")
        self.assertEqual(REPORT.fixed_number(0.145, 0, multiplier=100), "15")
        self.assertEqual(REPORT.fixed_number(0), "0.00")
        self.assertEqual(REPORT.fixed_number(1234.565, grouping=True), "1,234.57")
        self.assertEqual(REPORT.fixed_number(-95.625), "-95.63")

    def test_display_rounding_handles_float_half_ties_without_loosening_exact_inputs(self) -> None:
        from decimal import Decimal
        value = 86.52499999999999
        self.assertEqual(REPORT.fixed_number(value), "86.53")
        self.assertEqual(REPORT.fixed_number(-value), "-86.53")
        self.assertEqual(REPORT.fixed_number(.8652499999999999, multiplier=100), "86.53")
        self.assertEqual(REPORT.fixed_number(86.52499999), "86.52")
        self.assertEqual(REPORT.fixed_number("86.52499999999999"), "86.52")
        self.assertEqual(REPORT.fixed_number(Decimal("86.52499999999999")), "86.52")
        self.assertEqual(value, 86.52499999999999)

    def test_markdown_renders_secondary_failure_policy_without_filling_rubric(self) -> None:
        data = self.data()
        row = next(row for row in data['tasks'] if row['score_status'] == 'unscored')
        policy = REPORT.report_run_audit.report_failure_policy
        policy.prepare(data, {'units': [{'failure_zero_decisions': [{
            'unit_id': self.fixture.unit_id, 'task_id': row['task_id'],
            'failure_policy_score': 0, 'basis': 'explicit-human-policy/native-unsubmitted-start-rejection'}]}]})
        label = data['presentation']['tables']['总览']['rows'][0][0]
        policy.attach_views(data, data['presentation']['tables'], {self.fixture.unit_id: label})
        data['presentation']['sheet_order'].append('端到端计分')
        before = copy.deepcopy(data)
        markdown = REPORT.render_markdown(data)
        self.assertIn('## 端到端计分', markdown)
        self.assertIn('Rubric评分状态', markdown)
        self.assertIn('unscored', markdown)
        self.assertEqual(data, before)
        self.assertIsNone(row['total_score'])
        self.assertEqual(row['e2e_score'], 0)

    def test_resource_summary_distinguishes_full_and_fully_missing(self) -> None:
        complete_rows = []
        missing_rows = []
        for value in (1, 2):
            complete = {}
            missing = {}
            for field, _, _ in REPORT.RESOURCE_FIELDS:
                complete[field] = {
                    "value": value,
                    "known_subtotal": value,
                    "status": "observed",
                    "complete": True,
                    "coverage": {"known": 1, "total": 1, "unit": "fixture"},
                    "basis": "fixture",
                }
                missing[field] = REPORT.metric_observation(None, field)
            complete_rows.append({"resource": complete})
            missing_rows.append({"resource": missing})
        full = REPORT.resource_summary(complete_rows)["input_tokens"]
        unavailable = REPORT.resource_summary(missing_rows)["input_tokens"]
        self.assertEqual(full["status"], "complete")
        self.assertEqual(full["total"], 3)
        self.assertEqual(full["known_subtotal"], 3)
        self.assertEqual(unavailable["status"], "unavailable")
        self.assertIsNone(unavailable["total"])
        self.assertIsNone(unavailable["known_subtotal"])

    def test_failed_excel_runtime_leaves_no_partial_report(self) -> None:
        output = self.fixture.batch / "reports/atomic-output"
        args = type("Args", (), {
            "batch_root": str(self.fixture.batch),
            "output_dir": str(output),
            "generated_at": "2026-09-18T02:00:00Z",
            "node": "node",
            "node_modules": str(self.root / "missing-node-modules"),
            "skip_preview": True,
        })()
        with self.assertRaisesRegex(REPORT.ReportError, "EXCEL_RUNTIME_INVALID"):
            REPORT.command_generate(args)
        self.assertFalse(output.exists())
        self.assertFalse(list(output.parent.glob(".atomic-output.pending-*")))

    def test_detached_renderer_receives_the_isolated_preview_helper(self) -> None:
        modules = self.root / "runtime-modules"
        modules.mkdir()
        output = self.root / "report.xlsx"

        def run_renderer(command, **_kwargs):
            renderer = Path(command[1])
            helper = renderer.with_name("isolated_workbook_preview.mjs")
            self.assertEqual(helper.read_bytes(), SCRIPT.with_name(helper.name).read_bytes())
            self.assertIn('"./isolated_workbook_preview.mjs"', renderer.read_text())
            output.write_bytes(b"test-renderer-output")
            return REPORT.subprocess.CompletedProcess(command, 0, json.dumps({"status": "PASS"}), "")

        with patch.object(REPORT.subprocess, "run", side_effect=run_renderer):
            result = REPORT.render_excel(self.root / "input.json", output, self.root / "previews",
                node="node", node_modules=modules, skip_preview=False)
        self.assertEqual(result["status"], "PASS")

    def test_published_receipt_is_accepted_by_run_general_e2e(self) -> None:
        output = self.fixture.batch / "reports/final-smoke"

        def fake_render_excel(
            _input_path: Path,
            output_path: Path,
            preview_dir: Path,
            **_kwargs: object,
        ) -> dict:
            output_path.write_bytes(b"fixture-xlsx")
            validation_path = preview_dir / "excel-validation.json"
            write_json(
                validation_path,
                {"status": "PASS", "sheets": ["fixture"], "formula_errors": []},
            )
            return {"status": "PASS", "validation": str(validation_path)}

        original_render_excel = REPORT.render_excel
        REPORT.render_excel = fake_render_excel
        try:
            result = REPORT.command_generate(
                argparse.Namespace(
                    batch_root=str(self.fixture.batch),
                    output_dir=str(output),
                    generated_at="2026-09-18T02:00:00Z",
                    node="node",
                    node_modules=str(self.root),
                    skip_preview=True,
                    seal_output_dir=str(self.root / "sealed-reports"),
                )
            )
        finally:
            REPORT.render_excel = original_render_excel

        receipt_path = Path(result["receipt"])
        sealed = Path(result["canonical_report_archive"])
        self.assertTrue(sealed.is_file())
        self.assertEqual(sha256(sealed), result["canonical_report_archive_sha256"])
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertTrue(
            all(item["path"].startswith("reports/final-smoke/") for item in receipt["artifacts"])
        )
        self.assertFalse(any(".pending-" in item["path"] for item in receipt["artifacts"]))

        RUN.initialize_state(
            argparse.Namespace(
                root=str(self.fixture.batch),
                scope="batch",
                stage=["report"],
                input=[],
            )
        )
        recorded = RUN.record_receipt(
            argparse.Namespace(
                root=str(self.fixture.batch),
                stage="report",
                receipt=str(receipt_path),
            )
        )
        # A later host metadata variant remains separate; the explicit sealed
        # authority can still register/resume using the untouched receipt.
        Path(result['excel']).write_bytes(b'host workbook metadata variant')
        with self.assertRaisesRegex(RUN.FlowError, 'RECEIPT_ARTIFACT_DRIFT'):
            RUN.record_receipt(argparse.Namespace(root=str(self.fixture.batch), stage='report', receipt=str(receipt_path)))
        canonical = RUN.record_receipt(argparse.Namespace(root=str(self.fixture.batch), stage='report',
            receipt=str(receipt_path), canonical_report_archive=str(sealed)))
        self.assertEqual(canonical['state']['artifacts']['report']['canonical_report_archive']['sha256'], sha256(sealed))
        RUN.verify_recorded_artifacts(self.fixture.batch, canonical['state'])
        sealed.write_bytes(sealed.read_bytes() + b'changed archive')
        with self.assertRaisesRegex(RUN.FlowError, 'DRIFT'):
            RUN.verify_recorded_artifacts(self.fixture.batch, canonical['state'])
        self.assertEqual(recorded["state"]["stages"]["report"], "COMPLETED")


class DoubaoResourceProjectionTests(unittest.TestCase):
    def fixture(self, root, *, complete=False, live=False):
        identity = {"task_id": "task", "attempt_id": "attempt"}
        metrics_root = root / "evidence/task/attempt"
        trace = {"identity": identity, "completeness": {"status": "complete" if complete else "partial"},
                 "calls": [{"call_id": f"call-{i}"} for i in range(0 if complete else 13)]}
        state = {"identity": identity, "extensions": {"doubaowork": {"native_sources": {"finished_at":
            "assistant.local_info.perf_mark_samples.task_finish.receiveTimestamp" if live else "assistant.ext.finish_time_ms (native server completion)"}}}}
        sources = []
        for relative, value in [("trace/trace-index.json", trace), ("execution/automation-state.json", state)]:
            path = metrics_root / relative
            write_json(path, value)
            sources.append({"path": relative, "sha256": sha256(path), "size": path.stat().st_size})
        metrics = {"collection": {"collector": "doubaowork-native-evidence", "status": "partial", "sources": sources,
            "coverage": {}, "known_subtotals": {}}, "metrics": {"tools": {"call_count": {"value": 13, "status": "observed", "basis": "legacy"}},
            "timing": {"duration_seconds": {"value": 100, "status": "observed", "basis": "legacy"},
                "agent_duration_seconds": {"value": 90, "status": "observed", "basis": "native same-clock interval"}}}}
        execution = {"identity": identity, "evidence": {"trace_index_path": "evidence/task/attempt/trace/trace-index.json"}}
        return execution, metrics, metrics_root / "resource-metrics.json"

    def test_withholds_partial_total_and_cross_clock_duration_without_changing_original(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            execution, metrics, path = self.fixture(root)
            original = copy.deepcopy(metrics)
            projected, adjustments, comparable = REPORT.doubao_resource_projection(root, execution, metrics, path)
            self.assertEqual(metrics, original)
            self.assertIsNone(projected["metrics"]["tools"]["call_count"]["value"])
            self.assertEqual(projected["collection"]["known_subtotals"]["call_count"], 13)
            self.assertIsNone(projected["metrics"]["timing"]["duration_seconds"]["value"])
            self.assertEqual(projected["metrics"]["timing"]["agent_duration_seconds"]["value"], 90)
            self.assertFalse(comparable)
            self.assertEqual(len(adjustments), 2)
            row = {"execution_started_at": "2026-09-23T00:00:00Z", "execution_finished_at": "2026-09-23T00:01:40Z",
                "timing_clock_comparable": comparable, "resource": {field: REPORT.metric_observation(projected, field) for field, _, _ in REPORT.RESOURCE_FIELDS}}
            self.assertIsNone(REPORT.timing_summary([row])["batch_wall_clock_seconds"])

    def test_complete_live_zero_is_preserved_and_source_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            execution, metrics, path = self.fixture(root, complete=True, live=True)
            metrics["metrics"]["tools"]["call_count"]["value"] = 0
            projected, adjustments, comparable = REPORT.doubao_resource_projection(root, execution, metrics, path)
            self.assertEqual(projected["metrics"]["tools"]["call_count"]["value"], 0)
            self.assertEqual(projected["metrics"]["timing"]["duration_seconds"]["value"], 100)
            self.assertTrue(comparable)
            self.assertEqual(adjustments, [])
            (path.parent / "execution/automation-state.json").write_text("{}")
            with self.assertRaisesRegex(REPORT.ReportError, "SOURCE_DRIFT"):
                REPORT.doubao_resource_projection(root, execution, metrics, path)

    def test_controller_flow_preserves_missing_and_zero_but_rejects_conflicting_metric(self):
        profile = "prompt-send-to-controller-terminal/v1"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            execution, metrics, path = self.fixture(root, complete=True)
            metrics["metrics"]["tools"]["call_count"]["value"] = 0
            state_path = path.parent / "execution/automation-state.json"
            state = json.loads(state_path.read_text())
            state["extensions"]["timing"] = {"profile": profile}
            state["prompt"] = {"sent_at": "2026-10-12T00:00:00Z"}
            for finish, expected in [(None, None), ("2026-10-12T00:00:00Z", 0),
                                     ("2026-10-12T00:00:03.125Z", 3.125)]:
                state["execution"] = {"finished_at": finish}
                write_json(state_path, state)
                source = next(row for row in metrics["collection"]["sources"]
                              if row["path"] == "execution/automation-state.json")
                source.update(sha256=sha256(state_path), size=state_path.stat().st_size)
                metric = metrics["metrics"]["timing"]["duration_seconds"]
                metric.update(value=expected, status="unavailable" if expected is None else "observed",
                              basis=profile + ": same-host dispatch to terminal observation")
                projected, adjustments, comparable = REPORT.doubao_resource_projection(root, execution, metrics, path)
                self.assertEqual(projected["metrics"]["timing"]["duration_seconds"], metric)
                self.assertEqual(adjustments, [])
                self.assertTrue(comparable)
                metric["value"] = 1 if expected is None else expected + 1
                with self.assertRaisesRegex(REPORT.ReportError, "CONTROLLER_TIMING_MISMATCH"):
                    REPORT.doubao_resource_projection(root, execution, metrics, path)


if __name__ == "__main__":
    unittest.main()
