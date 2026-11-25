"""Windows ZIP imports must keep frozen bytes and restore verifier protections."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

from src.e2e import desktop_scoring as scoring
from src.e2e.artifacts import extract_zip, inventory, remove_temporary_tree
from src.e2e.common import E2EError, atomic_json, file_sha256
from src.e2e.desktop_score_import import restore_general_permissions
from tests.e2e.test_desktop_scoring import CONFIG, ITEM


class DesktopScoreImportTests(unittest.TestCase):
    def fixture(self, root):
        archive = root / "windows.zip"
        manifest = {"paths": {"gt": "private/gt"}, "private_scoring": {"workspace_entries": [
            {"path": "nested", "type": "directory", "mode": "0555"},
            {"path": "nested/expected.json", "type": "file", "mode": "0444"},
        ]}}
        with zipfile.ZipFile(archive, "w") as output:
            for name, body in {
                "candidate-original/workspace/results/result.json": b'\xef\xbb\xbf{"answer": 42}',
                "private/gt/nested/expected.json": b'{"answer": 42}',
                "score.json": b'{"result":{"valid":true,"total_score":0}}',
                "attempt-manifest.json": json.dumps(manifest).encode(),
            }.items():
                entry = zipfile.ZipInfo(name)
                entry.create_system = 0  # Windows/DOS attributes do not encode POSIX protections.
                entry.external_attr = 1
                output.writestr(entry, body)
        returned = root / "returned"
        extract_zip(archive, returned)
        target = root / "imported"
        shutil.copytree(returned, target)
        self.addCleanup(lambda: remove_temporary_tree(target) if target.exists() else None)
        return returned, target

    def test_zip_roundtrip_restores_exact_gt_modes_and_seals_all_candidate_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            source, target = self.fixture(Path(directory))
            before = {row["path"]: row["sha256"] for row in inventory(target) if row["kind"] == "file"}
            self.assertTrue((target / "candidate-original").stat().st_mode & 0o222)
            receipt = restore_general_permissions(target)
            for path in [target / "candidate-original", *(target / "candidate-original").rglob("*")]:
                self.assertFalse(path.stat().st_mode & 0o222)
            self.assertEqual((target / "private/gt/nested").stat().st_mode & 0o777, 0o555)
            self.assertEqual((target / "private/gt/nested/expected.json").stat().st_mode & 0o777, 0o444)
            after = {row["path"]: row["sha256"] for row in inventory(target) if row["kind"] == "file"}
            self.assertEqual(before, after)
            self.assertTrue(receipt["content_unchanged"])
            self.assertTrue((source / "candidate-original").stat().st_mode & 0o222)
            self.assertEqual(restore_general_permissions(target)["permissions"], [])

    def test_unexpected_gt_entries_and_symlink_are_rejected_before_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            _, target = self.fixture(Path(directory))
            (target / "private/gt/extra.json").write_text("unexpected")
            with self.assertRaisesRegex(E2EError, "GT_INVENTORY_INVALID"):
                restore_general_permissions(target)
            (target / "private/gt/extra.json").unlink()
            (target / "escape").symlink_to(Path(directory))
            with self.assertRaisesRegex(E2EError, "UNSUPPORTED_ARTIFACT_TYPE"):
                restore_general_permissions(target)

    def test_failed_verification_keeps_diagnostic_code_and_redacted_log(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log = root / "scoring-verification.json"
            result = subprocess.CompletedProcess([], 2, stdout=b"", stderr=json.dumps({"error": {
                "code": "CANDIDATE_ORIGINAL_DRIFT", "detail": "secret-value-never-public Bearer hidden-token " + "x" * 20000}}).encode())
            with patch.object(scoring.subprocess, "run", return_value=result), patch.dict(scoring.os.environ, {"WCB_API_KEY": "secret-value-never-public"}):
                with self.assertRaisesRegex(E2EError, "DESKTOP_SCORING_VERIFICATION_FAILED"):
                    scoring._run(["python", "verify.py", "verify-score"], root, log=log)
            data = json.loads(log.read_text())
            self.assertEqual(data["steps"][-1]["error_code"], "CANDIDATE_ORIGINAL_DRIFT")
            self.assertEqual(data["steps"][-1]["exit_code"], 2)
            self.assertNotIn("secret-value-never-public", log.read_text())
            self.assertNotIn("hidden-token", log.read_text())

    def test_timeout_is_logged_as_a_verification_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log = root / "scoring-verification.json"
            with patch.object(scoring.subprocess, "run", side_effect=subprocess.TimeoutExpired("verify", 180)):
                with self.assertRaisesRegex(E2EError, "DESKTOP_SCORING_VERIFICATION_FAILED"):
                    scoring._run(["python", "verify.py"], root, log=log)
            self.assertEqual(json.loads(log.read_text())["steps"][-1]["error_code"], "DESKTOP_SCORING_VERIFICATION_TIMEOUT")

    def test_verification_error_is_attached_to_the_round_and_sandbox_cleanup_continues(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work = root / "work"
            work.mkdir()
            log = work / "scoring-verification.json"
            atomic_json(log, {"steps": [{"error_code": "CANDIDATE_ORIGINAL_DRIFT", "occurred_at": "fixture-time"}]})
            driver = Mock()
            driver.execute.side_effect = E2EError("DESKTOP_SCORING_VERIFICATION_FAILED")
            driver.staging = work / "desktop"
            with patch.object(scoring, "_prepare", return_value={}), patch.object(scoring, "ScoringDriver", return_value=driver):
                row = scoring._job(root, ITEM, CONFIG, Mock(), root, "judge", root / "cancel.json")
            self.assertEqual(row["status"], "evaluation_error")
            self.assertIsNone(row["total_score"])
            self.assertEqual(row["failure_diagnostics"]["message"], "评分产物校验失败：CANDIDATE_ORIGINAL_DRIFT")
            self.assertEqual(row["artifacts"]["log"]["sha256"], file_sha256(log))
            driver.client.close.assert_called_once()
