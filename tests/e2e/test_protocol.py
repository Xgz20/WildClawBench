import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from src.e2e.cli import main
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
