from concurrent.futures import ThreadPoolExecutor
import json
import io
import os
from pathlib import Path
import tempfile
import unittest

from src.e2e.artifacts import _protect, copy_stream_readonly, execution_source, export_execution, freeze_metadata_files, import_execution, quarantine_local_metadata, restore_execution, seal_execution, verify_execution
from src.e2e.common import E2EError, atomic_json
from src.e2e.preparation import normalize_plan
from src.e2e.store import BatchStore, controller_lock


class ExecutionCoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        for path in self.root.rglob("*"):
            if path.is_dir():
                path.chmod(0o700)
        self.temp.cleanup()

    def seal(self):
        execution = self.root / "execution"
        (execution / "staging/workspace/empty").mkdir(parents=True)
        (execution / "staging/workspace/结果.txt").write_bytes(b"original\r\n\x00")
        identity = {"batch_id": "b", "unit_id": "u", "task_id": "t", "run_index": 1, "attempt_id": "a"}
        receipt = seal_execution(execution, identity)
        return execution, receipt

    def test_backup_restore_preserves_empty_directories_and_original_bytes(self):
        execution, receipt = self.seal()
        destination = self.root / "restored"
        restored = restore_execution(execution, destination)
        self.assertEqual(restored["source_archive_sha256"], receipt["archive_sha256"])
        self.assertTrue((destination / "workspace/empty").is_dir())
        self.assertEqual((destination / "workspace/结果.txt").read_bytes(), b"original\r\n\x00")
        self.assertEqual(verify_execution(execution), receipt)

    def test_contamination_can_be_restored_without_accepting_new_original_hash(self):
        execution, _ = self.seal()
        damaged = execution / "original/workspace/结果.txt"
        damaged.chmod(0o600)
        damaged.write_text("polluted")
        with self.assertRaisesRegex(E2EError, "ORIGINAL_DRIFT"):
            verify_execution(execution)
        restore_execution(execution, self.root / "new-generation")
        self.assertEqual((self.root / "new-generation/workspace/结果.txt").read_bytes(), b"original\r\n\x00")

    def test_export_import_is_portable_and_idempotent(self):
        execution, receipt = self.seal()
        archive = self.root / "share.zip"
        export_execution(execution, archive)
        imported = self.root / "another-computer/execution"
        self.assertEqual(import_execution(archive, self.root / "share.zip.json", imported)["status"], "imported")
        self.assertEqual(verify_execution(imported)["archive_sha256"], receipt["archive_sha256"])
        self.assertEqual(import_execution(archive, self.root / "share.zip.json", imported)["status"], "already_imported")

    def test_corrupted_archive_is_rejected(self):
        execution, _ = self.seal()
        archive = execution / "backups/execution-original.zip"
        with archive.open("ab") as stream:
            stream.write(b"changed")
        with self.assertRaisesRegex(E2EError, "ARCHIVE_DRIFT"):
            restore_execution(execution, self.root / "bad-restore")

    def test_resealing_requires_the_original_execution_identity(self):
        execution, receipt = self.seal()
        different = {**receipt["identity"], "task_id": "another-task"}
        with self.assertRaisesRegex(E2EError, "IDENTITY_CONFLICT"):
            seal_execution(execution, different)
        self.assertEqual(verify_execution(execution), receipt)

    def test_local_metadata_is_preserved_outside_the_verified_payload(self):
        payload = self.root / "payload"
        payload.mkdir()
        (payload / "answer.txt").write_bytes(b"original")
        (payload / ".DS_Store").write_bytes(b"local metadata")
        _protect(payload)
        quarantine = self.root / "quarantine"
        records = quarantine_local_metadata(payload, {"answer.txt"}, quarantine)
        self.assertEqual([row["path"] for row in records], [".DS_Store"])
        self.assertFalse((payload / ".DS_Store").exists())
        self.assertEqual((quarantine / ".DS_Store.snapshot").read_bytes(), b"local metadata")
        self.assertEqual((payload / "answer.txt").read_bytes(), b"original")
        self.assertEqual(payload.stat().st_mode & 0o222, 0)

    def test_undeclared_content_is_quarantined_and_rejected(self):
        payload = self.root / "payload"
        payload.mkdir()
        (payload / "answer.txt").write_bytes(b"original")
        (payload / "extra.txt").write_bytes(b"untrusted local edit")
        _protect(payload)
        quarantine = self.root / "quarantine"
        with self.assertRaisesRegex(E2EError, "UNDECLARED_LOCAL_CONTENT"):
            quarantine_local_metadata(payload, {"answer.txt"}, quarantine)
        self.assertEqual((quarantine / "extra.txt.snapshot").read_bytes(), b"untrusted local edit")

    def test_source_declared_metadata_is_retained(self):
        payload = self.root / "payload"
        payload.mkdir()
        (payload / ".DS_Store").write_bytes(b"source declared file")
        _protect(payload)
        self.assertEqual(quarantine_local_metadata(payload, {".DS_Store"}, self.root / "quarantine"), [])
        self.assertEqual((payload / ".DS_Store").read_bytes(), b"source declared file")

    def test_restored_file_is_readonly_from_its_first_write(self):
        destination = self.root / "source-file"
        test = self

        class Source(io.BytesIO):
            def read(self, size=-1):
                test.assertTrue(destination.exists())
                test.assertEqual(destination.stat().st_mode & 0o222, 0)
                return super().read(size)

        copy_stream_readonly(Source(b"frozen bytes"), destination)
        self.assertEqual(destination.read_bytes(), b"frozen bytes")

    @unittest.skipIf(os.name == "nt", "macOS metadata descriptor replacement")
    def test_metadata_snapshot_detaches_an_existing_writer(self):
        metadata = self.root / ".DS_Store"
        metadata.write_bytes(b"before snapshot")
        with metadata.open("r+b") as writer:
            freeze_metadata_files(self.root)
            writer.seek(0)
            writer.write(b"changed payload")
            writer.flush()
        self.assertEqual(metadata.read_bytes(), b"before snapshot")
        self.assertEqual(metadata.stat().st_mode & 0o222, 0)

    def test_restored_source_is_selected_and_reverified(self):
        source, _ = self.seal()
        execution = self.root / "task/executions/exec-test"
        execution.parent.mkdir(parents=True)
        source.rename(execution)
        restores = execution.parent.parent / "restores"
        destination = restores / "generation-01"
        restoration = restore_execution(execution, destination)
        atomic_json(restores / "current.json", restoration)
        selected, _ = execution_source(execution)
        self.assertEqual(selected, destination.resolve())
        (destination / "workspace/结果.txt").chmod(0o600)
        (destination / "workspace/结果.txt").write_text("polluted again")
        with self.assertRaisesRegex(E2EError, "ORIGINAL_DRIFT"):
            execution_source(execution)

    def test_uncertain_scoring_retains_its_slot(self):
        store = BatchStore(self.root)
        store.initialize({}, [{"key": f"t{i}", "unit_id": "u", "run_index": 1, "task_id": f"t{i}"} for i in range(2)])
        for i in range(2):
            store.publish_ready(f"t{i}", {"backup_sha256": str(i)})
        claim = store.claim_score("owner", 1, mode="streaming")
        store.score_update(claim["key"], claim["claim_id"], "NEEDS_ATTENTION")
        self.assertIsNone(store.claim_score("owner", 1, mode="streaming"))

    def test_targeted_claim_leaves_other_scoring_sources_ready(self):
        store = BatchStore(self.root)
        store.initialize({}, [{"key": f"t{i}", "unit_id": "u", "run_index": 1, "task_id": f"t{i}"} for i in range(3)])
        for i in range(3):
            store.publish_ready(f"t{i}", {"backup_sha256": str(i)})
        claim = store.claim_score("owner", 1, mode="streaming", execution_key="t2")
        self.assertEqual(claim["key"], "t2")
        self.assertEqual({item["key"]: item["phase"] for item in store.scoring_rows()},
                         {"t0": "READY", "t1": "READY", "t2": "CLAIMED"})

    def test_kernel_controller_lock_rejects_second_owner(self):
        with controller_lock(self.root):
            with self.assertRaisesRegex(E2EError, "ALREADY_RUNNING"):
                with controller_lock(self.root):
                    self.fail("second controller acquired lock")
        with controller_lock(self.root):
            pass

    def test_scoring_claim_is_transactional_and_preserves_slot_budget(self):
        store = BatchStore(self.root)
        items = [{"key": f"u/run-0001/t{i}", "unit_id": "u", "run_index": 1, "task_id": f"t{i}"} for i in range(10)]
        store.initialize({"batch": "b"}, items)
        for item in items:
            store.publish_ready(item["key"], {"backup_sha256": item["task_id"]})
        with ThreadPoolExecutor(max_workers=10) as pool:
            claims = list(pool.map(lambda i: store.claim_score(str(i), 3, mode="streaming"), range(10)))
        claimed = [claim for claim in claims if claim]
        self.assertEqual(len(claimed), 3)
        self.assertEqual(len({claim["key"] for claim in claimed}), 3)
        self.assertIsNone(store.claim_score("batch", 3, mode="batch"))

    def test_plan_freezes_defaults_and_distinguishes_units(self):
        raw = {"batch_id": "batch", "selection": {"scenario": "general", "dataset": "general-custom70-v3"},
               "units": [{"harness": "astronstudio", "model": "spark-x2.6"},
                         {"harness": "astronstudio", "model": "spark-x2.6", "reasoning_effort": "high"}]}
        plan = normalize_plan(raw)
        self.assertEqual(plan["execution_concurrency"], 3)
        self.assertNotEqual(plan["units"][0]["unit_id"], plan["units"][1]["unit_id"])
        raw["timeout_override"] = 2400
        self.assertTrue(all(unit["timeout_override"] == 2400 for unit in normalize_plan(raw)["units"]))
        raw["timeout_override"] = 0
        with self.assertRaises(E2EError):
            normalize_plan(raw)


if __name__ == "__main__":
    unittest.main()
