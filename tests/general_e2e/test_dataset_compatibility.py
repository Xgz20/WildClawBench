"""Regression coverage for independent legacy60/seven-axis and imported116/five-axis flows."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

import jsonschema
import yaml

from eval_general_e2e.datasets.bundle import (
    DEFAULT_DEFINITION, GENERAL116_DEFINITION, compile_dataset, dataset_manifest_path,
    load_manifest_lock, write_dataset_bundle,
)
from tests.general_e2e.test_general_release_prepare import PREPARE, RELEASE
from tests.general_e2e.test_local_scoring_runtime import RUNTIME, Fixture as ScoringFixture, load_module
from tests.general_e2e.test_report_general_e2e import REPORT, Fixture
from wildclawbench_grading_core.rules import inspect_rule_dependencies, run_rules

ROOT = Path(__file__).resolve().parents[2]
WORKER = load_module("compat_rule_worker", ROOT / "tools/report/skills/general-e2e/score-general-e2e/scripts/rule_worker.py")


class DatasetCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest, cls.members = compile_dataset(ROOT, definition=GENERAL116_DEFINITION)

    @classmethod
    def tearDownClass(cls):
        cls.members = []

    def test_legacy_snapshot_and_mapping_are_unchanged(self):
        manifest, _ = compile_dataset(ROOT, definition=DEFAULT_DEFINITION)
        self.assertEqual(manifest, load_manifest_lock())
        self.assertEqual(manifest["dataset_digest"], "e5fd1ed401b45729d85d7aaf9c94c36d3900c1bcb43446bb7d43cca584a2886c")
        self.assertEqual(hashlib.sha256((ROOT / "tools/report/data/checkpoint_capability_map7.yaml").read_bytes()).hexdigest(),
                         "c50de78f02e5bb1f569f8965b3a7f5b87aa42f83d1b82a1861fc9e0d7ccb0e98")

    def test_imported_snapshot_schema_mapping_and_every_scoring_contract(self):
        self.assertEqual(self.manifest, load_manifest_lock(dataset_manifest_path(GENERAL116_DEFINITION.dataset_id)))
        jsonschema.validate(self.manifest, json.loads((ROOT / "eval_general_e2e/datasets/schemas/dataset-manifest-v1.schema.json").read_text()))
        mapping = yaml.safe_load((ROOT / "tools/report/data/checkpoint_capability_map5.yaml").read_text())
        self.assertEqual(set(mapping), {task["task_id"] for task in self.manifest["tasks"]})
        for member in self.members:
            if not member.path.endswith("/private-scoring/contract.json"):
                continue
            contract = json.loads(member.data)
            with self.subTest(task=contract["task_id"]):
                criteria = RUNTIME._parse_semantic_criteria(contract["llm_judge_rubric"], weight_scale=contract.get("semantic_weight_scale", 1))
                self.assertTrue(criteria)
                self.assertAlmostEqual(sum(row["weight"] for row in criteria), 1)
                inspect_rule_dependencies(contract["automated_checks"])
                semantic_keys = {"llm_judge." + row["key"] for row in criteria}
                self.assertFalse({key for key in mapping[contract["task_id"]] if key.startswith("llm_judge.")} - semantic_keys)

    def test_standalone_suite_prepares_and_installs_all_116_tasks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dataset = root / "dataset.zip"
            write_dataset_bundle(self.manifest, self.members, dataset)
            release = RELEASE.build_general_release(ROOT, root / "release", release_id="dataset-compat", source_revision="1" * 40)
            with zipfile.ZipFile(next((root / "release/skills").glob("prepare-general-e2e-workspaces*.zip"))) as archive:
                archive.extractall(root / "installed")
            ids = [task["task_id"] for task in self.manifest["tasks"]]
            config = {"schema_id": PREPARE.CONFIG_SCHEMA_ID, "schema_version": 1,
                      "contract_version": PREPARE.CONTRACT_VERSION, "bundle_protocol": PREPARE.BUNDLE_PROTOCOL,
                      "batch_id": "compat116", "task_ids": ids,
                      "units": [{"unit_id": "astronstudio", "task_ids": ids,
                                 "harness": {"id": "astronstudio", "platform": "macos-arm64", "version": None},
                                 "model": {"requested_id": "fixture", "reasoning_effort": "high"}, "execution_mode": "automatic"}],
                      "report": {"title": "dataset compatibility"}}
            config_path = root / "config.json"
            config_path.write_text(json.dumps(config))
            script = root / "installed/prepare-general-e2e-workspaces/scripts/prepare_general_e2e_workspaces.py"
            prepared = subprocess.run([sys.executable, "-I", "-S", str(script), "prepare", "--dataset-bundle", str(dataset),
                            "--release-suite", release["suite_path"], "--config", str(config_path), "--output-dir", str(root / "batches")],
                           capture_output=True, text=True)
            self.assertEqual(prepared.returncode, 0, prepared.stdout + prepared.stderr)
            batch = root / "batches/compat116"
            PREPARE.verify_batch(batch)
            execution = next(batch.rglob("*__execution.zip"))
            scoring = next(batch.rglob("*__scoring.zip"))
            with zipfile.ZipFile(execution) as archive:
                self.assertFalse(any("private-scoring" in name or "/gt/" in name for name in archive.namelist()))
            _, members, manifest = RUNTIME._read_scoring_package(scoring)
            self.assertEqual(manifest["task_ids"], ids)
            for task in manifest["tasks"]:
                contract = json.loads(members[task["contract"]["path"]][1])
                self.assertIn("rule_result_adapter", contract)
            with zipfile.ZipFile(next((root / "release/skills").glob("run-general-e2e*.zip"))) as archive:
                archive.extractall(root / "installed")
            run = root / "installed/run-general-e2e/scripts/run_general_e2e.py"
            installed = subprocess.run([sys.executable, "-I", "-S", str(run), "install-unit", "--execution-package", str(execution),
                            "--round-root", str(root / "round")], capture_output=True, text=True)
            self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
            self.assertEqual(len(list((root / "round/AstronStudio/execution/tasks").glob("*/workspace"))), 116)


class ScoringTransportCompatibilityTests(unittest.TestCase):
    def test_evidence_only_rule_flows_through_managed_attempt_and_semantic_preparation(self):
        policy = {"schema_version": "wildclawbench.general-e2e-numeric-diagnostics/v1",
                  "diagnostic_keys": ["diagnostics", "诊断"], "evidence_only": True, "default_overall": None}
        rubric = "### A (key: a, weight: 100)\n**Score 0.0**: wrong\n**Score 1.0**: right"
        with tempfile.TemporaryDirectory() as tmp:
            fixture = ScoringFixture(Path(tmp), grading_type="hybrid", grading_weights={"automated": 0, "llm_judge": 1},
                llm_judge_rubric=rubric,
                rule="def grade(transcript, workspace_path):\n return {'diagnostics': {'exported': True}}",
                contract_overrides={"rule_result_adapter": policy, "semantic_weight_scale": 100})
            attempt = fixture.prepare()
            RUNTIME.run_rules_attempt(attempt_root=attempt, runtime_python=Path(sys.executable), timeout_seconds=10)
            component = json.loads((attempt / "rule-component.json").read_text())
            self.assertEqual(component["purpose"], "evidence_preparation_only")
            self.assertEqual(component["criteria"], [])
            RUNTIME.verify_attempt(attempt)
            RUNTIME.prepare_semantics_attempt(attempt_root=attempt)
            request = json.loads((attempt / "semantic/request.json").read_text())
            self.assertEqual(request["rubric"]["criteria"][0]["weight"], 1)

    def test_points_require_explicit_scale_and_keep_original_budget(self):
        rubric = "### A (key: a, weight: 4)\n**Score 0.0**: wrong\n**Score 1.0**: right\n### B (key: b, weight: 18)\n**Score 0.0**: wrong\n**Score 1.0**: right"
        with self.assertRaises(RUNTIME.ScoringRuntimeError):
            RUNTIME._parse_semantic_criteria(rubric)
        result = RUNTIME._parse_semantic_criteria(rubric, weight_scale=22)
        self.assertAlmostEqual(result[0]["weight"] * .22, .04)
        self.assertAlmostEqual(result[1]["weight"] * .22, .18)

    def test_managed_worker_preserves_raw_diagnostics_and_core_stays_strict(self):
        policy = {"schema_version": "wildclawbench.general-e2e-numeric-diagnostics/v1",
                  "diagnostic_keys": ["diagnostics", "诊断"], "evidence_only": False, "default_overall": None}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            request = {"schema_version": WORKER.REQUEST_SCHEMA, "workspace_path": str(root), "transcript": [],
                       "automated_checks": "def grade(transcript, workspace_path):\n return {'a': .5, 'overall_score': .5, '诊断': {'count': 100}}",
                       "rule_result_adapter": policy}
            (root / "request.json").write_text(json.dumps(request))
            subprocess.run([sys.executable, "-I", "-S", WORKER.__file__, "--request", str(root / "request.json"), "--result", str(root / "result.json")], check=True)
            value = json.loads((root / "result.json").read_text())
            self.assertEqual(value["raw_result"]["诊断"], {"count": 100})
            self.assertEqual(value["result"], {"a": .5, "overall_score": .5})
            component = run_rules(request["automated_checks"], executor=lambda *_: value["result"], workspace_path=str(root))
            self.assertEqual(component["score"], .5)
            with self.assertRaises(Exception):
                run_rules(request["automated_checks"], executor=lambda *_: value["raw_result"], workspace_path=str(root))
        only = {**policy, "evidence_only": True}
        self.assertEqual(WORKER.adapt_rule_result({"diagnostics": {"exported": True}}, only), {"overall_score": 0})
        self.assertNotIn("overall_score", WORKER.adapt_rule_result({"diagnostics": {}}, policy))


class ReportProfileCompatibilityTests(unittest.TestCase):
    def test_legacy_new_and_mixed_profiles_keep_independent_columns_and_missing_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture(Path(tmp))
            data = REPORT.aggregate(REPORT.validate_batch_inputs(fixture.batch), "2026-10-29T00:00:00Z")
            refs = REPORT.report_views.load_references()
            legacy = REPORT.report_views.build_views(data, refs)
            self.assertEqual(len(legacy["tables"]["Agent能力对比"]["headers"]), 9)
            new = copy.deepcopy(data)
            for row, task_id in zip(new["tasks"], refs["capabilities5"]):
                row["task_id"] = task_id
                row["checkpoints"] = {"values": {key: .5 for key in refs["capabilities5"][task_id]}}
            views = REPORT.report_views.build_views(new, refs)
            self.assertEqual(views["capability_profile"], "general5")
            self.assertEqual(len(views["tables"]["Agent能力对比"]["headers"]), 7)
            self.assertNotIn("代码生成", views["tables"]["Agent能力对比"]["headers"])
            new["tasks"][0] = copy.deepcopy(data["tasks"][0])
            new["tasks"][0]["task_id"] = next(iter(refs["capabilities"]))
            mixed = REPORT.report_views.build_views(new, refs)
            self.assertEqual(len(mixed["tables"]["Agent能力对比"]["headers"]), 9)
            self.assertIn("Agent五维能力对比", mixed["sheet_order"])
