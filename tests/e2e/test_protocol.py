import contextlib
import io
import json
import os
import socket
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from src.e2e.cli import main, _run, build_parser
from src.e2e.common import E2EError
from src.e2e.engine import run_batch, cancel_batch
from src.e2e.store import BatchStore
from src.e2e.packages import export_package, import_package
from src.e2e.protocol import artifacts, events, preflight, snapshot
from tests.e2e import test_scheduler as fixtures


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.SchedulerTests()
        self.fixture.setUp()

    def tearDown(self):
        self.fixture.tearDown()

    def test_snapshot_keeps_multi_run_identity_and_additive_fields(self):
        run_batch(
            self.fixture.root, self.fixture.config, driver_factory=self.fixture.factory
        )
        result = snapshot(self.fixture.root)
        self.assertTrue(result["terminal"])
        self.assertEqual(result["state"], "completed")
        self.assertEqual(result["total"], 10)
        self.assertEqual(
            len({row["execution_key"] for row in result["executions"]}), 10
        )
        self.assertTrue(
            all(
                row["trace_completeness"] == "complete"
                and row["backup_status"] == "verified"
                for row in result["executions"]
            )
        )
        self.assertNotIn("scoring", result)
        self.assertNotIn("scoring_concurrency", result["plan"])

    def test_snapshot_flow_duration_is_additive_and_unknown_is_not_zero(self):
        run_batch(self.fixture.root, self.fixture.config, driver_factory=self.fixture.factory)
        store = BatchStore(self.fixture.root)
        row = store.rows()[0]
        store.update(row['key'], 'COMPLETED', dispatch_armed_at='2026-11-16T00:00:00+00:00', finished_at='2026-11-16T00:00:05+00:00')
        value = next(item for item in snapshot(self.fixture.root)['executions'] if item['execution_key'] == row['key'])
        self.assertEqual(value['duration_seconds'], 5)
        store.update(row['key'], 'COMPLETED', dispatch_armed_at=None)
        value = next(item for item in snapshot(self.fixture.root)['executions'] if item['execution_key'] == row['key'])
        self.assertIsNone(value['duration_seconds'])

    def test_cursor_replay_and_legacy_status_share_the_same_batch(self):
        run_batch(
            self.fixture.root, self.fixture.config, driver_factory=self.fixture.factory
        )
        first = events(self.fixture.root, 0)
        self.assertGreater(first["cursor"], 0)
        self.assertEqual(events(self.fixture.root, first["cursor"])["events"], [])
        workspace = self.fixture.root.parent
        target = workspace / "batches" / self.fixture.root.name
        target.parent.mkdir()
        self.fixture.root.rename(target)
        self.fixture.root = target
        arguments = [
            "status",
            "--workspace-root",
            str(workspace),
            "--batch-id",
            self.fixture.root.name,
        ]
        for api in ([], ["--api-version", "1"]):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(api + arguments), 0)
            value = json.loads(output.getvalue())
            self.assertEqual(
                value["data"]["total"] if api else len(value["executions"]), 10
            )

    def test_artifact_roots_and_links_are_checked(self):
        run_batch(
            self.fixture.root, self.fixture.config, driver_factory=self.fixture.factory
        )
        with self.assertRaises(E2EError):
            artifacts(self.fixture.root, "control/state.sqlite")
        with self.assertRaises(E2EError):
            artifacts(self.fixture.root, "units/../../outside")

    def test_failed_snapshot_exposes_diagnostic_and_actual_trace_coverage(self):
        store = BatchStore(self.fixture.root)
        row = store.rows()[0]
        original = self.fixture.root / row["execution_root"] / "original"
        diagnostics = original / "collect/evidence/diagnostics.json"
        diagnostics.parent.mkdir(parents=True)
        diagnostics.write_text(json.dumps({"failure": {"stage": "select_model"}}))
        store.update(
            row["key"], "FAILED", resource_held=False, error={"code": "controller"}
        )
        result = snapshot(self.fixture.root)["executions"][0]
        self.assertEqual(result["error"]["product_failure"]["stage"], "select_model")
        self.assertEqual(result["trace_completeness"], "missing")
        native = original / "native/failure-quiesced/rollout-test.jsonl"
        native.parent.mkdir(parents=True)
        native.write_text("{}\n")
        result = snapshot(self.fixture.root)["executions"][0]
        self.assertEqual(result["trace_completeness"], "partial")
        self.assertTrue(any(item["kind"] == "trace" for item in result["artifacts"]))

    def test_single_zip_can_be_imported_without_sidecar(self):
        run_batch(
            self.fixture.root, self.fixture.config, driver_factory=self.fixture.factory
        )
        path = self.fixture.root / "result.zip"
        export_package(self.fixture.root, path)
        imported = import_package(path, None, self.fixture.root / "recipient")
        self.assertEqual(imported["execution_count"], 10)
        self.assertEqual(
            import_package(path, None, self.fixture.root / "recipient")["status"],
            "already_imported",
        )
        with path.open("ab") as stream:
            stream.write(b"changed")
        # A supplied receipt remains an external whole-file integrity check.
        with self.assertRaises(E2EError):
            import_package(
                path, path.with_suffix(".zip.json"), self.fixture.root / "recipient"
            )

    def test_subset_download_preserves_full_parent_coverage(self):
        import zipfile

        run_batch(
            self.fixture.root, self.fixture.config, driver_factory=self.fixture.factory
        )
        key = BatchStore(self.fixture.root).rows()[0]["key"]
        path = self.fixture.root / "subset.zip"
        export_package(self.fixture.root, path, keys=[key])
        with zipfile.ZipFile(path) as archive:
            index = json.loads(archive.read("package-index.json"))
        self.assertEqual(len(index["parent_scope"]), 10)
        self.assertEqual(index["selected_scope"], [key])
        self.assertEqual(len(index["not_exported"]), 9)
        self.assertTrue(
            all(
                row["reason"] == "NOT_SELECTED"
                for row in index["unavailable_executions"]
            )
        )

    def test_preflight_resolves_real_catalog_without_creating_sandbox(self):
        root = Path(__file__).resolve().parents[2]
        raw = {
            "selection": {
                "scenario": "general",
                "dataset": "general-custom60-v1",
                "task_ids": ["03_Social_Interaction_task_003_colleague_leave_reply"],
            },
            "units": [
                {
                    "harness": "astronstudio",
                    "model": "auto",
                    "reasoning_effort": "high",
                }
            ],
            "runs": 2,
        }
        with patch("src.e2e.agentcube.AgentCubeClient.create_session") as create:
            result = preflight(root, raw)
        self.assertTrue(result["valid"])
        self.assertEqual(result["planned_execution_count"], 2)
        create.assert_not_called()
        raw["units"][0]["reasoning_effort"] = "max"
        self.assertTrue(preflight(root, raw)["valid"])
        raw["units"][0]["model"] = "custom/not-a-builtin"
        unavailable = preflight(root, raw)
        self.assertFalse(unavailable["valid"])
        self.assertIn("CUSTOM_TESTED_MODELS_NOT_SUPPORTED", {issue["code"] for issue in unavailable["issues"]})

    def test_runtime_preflight_rejects_missing_credentials_without_creating_sandbox(self):
        repo = Path(__file__).resolve().parents[2]
        raw = {"selection": {"scenario": "general", "dataset": "general-custom60-v1",
                             "task_ids": ["03_Social_Interaction_task_003_colleague_leave_reply"]},
               "units": [{"harness": "astronstudio", "model": "auto", "reasoning_effort": "high"}]}
        with patch.dict(os.environ, {}, clear=True), \
                patch("src.e2e.agentcube.AgentCubeClient.create_session") as create, \
                patch("src.e2e.protocol.socket.getaddrinfo") as dns:
            offline = preflight(repo, raw)
            runtime = preflight(repo, raw, check_runtime=True)
        self.assertTrue(offline["valid"])
        self.assertFalse(runtime["valid"])
        self.assertEqual(runtime["runtime_checks"]["credentials"], "failed")
        self.assertIn("AGENTCUBE_RUNTIME_CONFIG_INVALID", {i["code"] for i in runtime["issues"]})
        create.assert_not_called()
        dns.assert_not_called()

    def test_runtime_preflight_reports_unresolvable_platform_endpoint(self):
        repo = Path(__file__).resolve().parents[2]
        raw = {"selection": {"scenario": "general", "dataset": "general-custom60-v1",
                             "task_ids": ["03_Social_Interaction_task_003_colleague_leave_reply"]},
               "units": [{"harness": "astronstudio", "model": "auto", "reasoning_effort": "high"}]}
        with patch.dict(os.environ, {"AGENTCUBE_AUTH_TOKEN": "synthetic", "AGENTCUBE_USER_ID": "synthetic"}), \
                patch("src.e2e.protocol.socket.getaddrinfo", side_effect=socket.gaierror("synthetic DNS failure")), \
                patch("src.e2e.agentcube.AgentCubeClient.create_session") as create:
            result = preflight(repo, raw, check_runtime=True)
        self.assertFalse(result["valid"])
        self.assertEqual(result["runtime_checks"], {"credentials": "passed", "dns": "failed"})
        self.assertIn("AGENTCUBE_ENDPOINT_UNRESOLVABLE", {i["code"] for i in result["issues"]})
        create.assert_not_called()

    def test_inline_and_plan_invocations_resolve_identical_scope(self):
        repo = Path(__file__).resolve().parents[2]
        task_id = "03_Social_Interaction_task_003_colleague_leave_reply"
        raw = {
            "batch_id": "equivalent",
            "selection": {
                "scenario": "general",
                "dataset": "general-custom60-v1",
                "task_ids": [task_id],
            },
            "units": [
                {"harness": "astronstudio", "model": "auto", "reasoning_effort": "high"}
            ],
            "runs": 2,
            "execution_concurrency": 3,
            "timeout_override": 3600,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plan.json"
            path.write_text(json.dumps(raw))
            common = [
                "--api-version",
                "1",
                "run",
                "--workspace-root",
                directory,
                "--dry-run",
            ]
            invocations = [
                common + ["--plan", str(path)],
                common
                + [
                    "--batch-id",
                    "equivalent",
                    "--scenario",
                    "general",
                    "--dataset",
                    "general-custom60-v1",
                    "--task-id",
                    task_id,
                    "--harness",
                    "astronstudio",
                    "--model",
                    "auto",
                    "--reasoning-effort",
                    "high",
                    "--runs",
                    "2",
                    "--concurrency",
                    "3",
                    "--timeout-override",
                    "3600",
                ],
            ]
            results = []
            for arguments in invocations:
                with patch(
                    "src.e2e.preparation.prepare_batch",
                    side_effect=E2EError("captured"),
                ) as prepare:
                    with self.assertRaisesRegex(E2EError, "captured"):
                        _run(build_parser().parse_args(arguments))
                    results.append(preflight(repo, prepare.call_args.args[2]))
            self.assertEqual(
                results[0]["selection_sha256"], results[1]["selection_sha256"]
            )
            self.assertEqual(results[0]["plan"]["units"], results[1]["plan"]["units"])
            self.assertEqual(results[0]["planned_execution_count"], 2)

    def test_protocol_error_is_structured(self):
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(
                    [
                        "--api-version",
                        "1",
                        "status",
                        "--workspace-root",
                        directory,
                        "--batch-id",
                        "missing",
                    ]
                )
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(output.getvalue())["type"], "error")

    def test_cancel_prepared_batch_needs_no_remote_operation(self):
        with patch("src.e2e.agentcube.AgentCubeClient.create_session") as create:
            cancel_batch(self.fixture.root, self.fixture.config)
        result = snapshot(self.fixture.root)
        self.assertEqual(result["state"], "cancelled")
        self.assertEqual(result["resource_held"], 0)
        create.assert_not_called()

    def test_cancelled_unstarted_scope_remains_in_download(self):
        import zipfile

        cancel_batch(self.fixture.root, self.fixture.config)
        path = self.fixture.root / "cancelled.zip"
        receipt = export_package(self.fixture.root, path, include_unsealed=True)
        self.assertEqual(receipt["execution_count"], 0)
        with zipfile.ZipFile(path) as archive:
            index = json.loads(archive.read("package-index.json"))
        self.assertEqual(len(index["parent_scope"]), 10)
        self.assertEqual(len(index["not_exported"]), 10)
        self.assertTrue(
            all(
                item["execution"]["phase"] == "CANCELLED"
                for item in index["unavailable_executions"]
            )
        )
        self.assertEqual(
            import_package(path, None, self.fixture.root / "recipient")[
                "execution_count"
            ],
            0,
        )

    def test_cancel_collects_before_release_and_keeps_incomplete_vm(self):
        store = BatchStore(self.fixture.root)
        item = store.rows()[0]
        store.update(
            item["key"],
            "RUNNING",
            resource_held=True,
            session_id="owned",
            dispatch_armed_at="sent",
            runtime=self.fixture.config.public(),
        )
        driver = Mock()
        driver.root = self.fixture.root / item["execution_root"]
        driver.staging = driver.root / "staging"
        driver.config = self.fixture.config
        driver.salvage.return_value = {"complete": False}
        factory = lambda **kwargs: driver
        cancel_batch(self.fixture.root, self.fixture.config, factory)
        self.assertEqual(store.get(item["key"])["phase"], "NEEDS_ATTENTION")
        self.assertTrue(store.get(item["key"])["resource_held"])
        driver.client.delete_session.assert_not_called()
        driver.salvage.return_value = {"complete": True}
        driver.client.delete_session.return_value = {"confirmed": True}
        cancel_batch(self.fixture.root, self.fixture.config, factory)
        self.assertEqual(store.get(item["key"])["phase"], "CANCELLED")
        self.assertFalse(store.get(item["key"])["resource_held"])
        self.assertTrue((driver.root / "backups/backup-receipt.json").exists())


if __name__ == "__main__":
    unittest.main()
