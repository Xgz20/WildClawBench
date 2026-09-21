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


def load_example(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Fixture:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.batch = root / "batch"
        self.unit_id = "astronstudio-macos"
        self.package_id = ""
        self.target = self.batch / "returns" / self.unit_id / ".pending"
        self.dataset = {"id": "general-custom60-v1", "digest": DATASET_DIGEST, "bundle_sha256": "3" * 64}
        self.release = {"id": "release-one", "catalog_digest": RELEASE_DIGEST, "catalog_sha256": "4" * 64, "suite_sha256": "5" * 64}
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
            "status": "completed",
            "created_at": "2026-09-18T01:09:00+00:00",
            "task_ids": TASKS,
            "tasks": [{"task_id": task_id, "attempt_id": f"exec-{index + 1}", "status": "completed"} for index, task_id in enumerate(TASKS)],
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
                )
            )
        finally:
            REPORT.render_excel = original_render_excel

        receipt_path = Path(result["receipt"])
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
        self.assertEqual(recorded["state"]["stages"]["report"], "COMPLETED")


if __name__ == "__main__":
    unittest.main()
