from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
import unittest

from src.e2e import desktop_scoring as desktop, headless
from src.e2e.common import E2EError, read_json
from tests.e2e.test_desktop_scoring import CONFIG, ITEM


START = "2026-11-26T00:00:00+00:00"
FINISH = "2026-11-26T00:01:00+00:00"
RELEASED = "2026-11-26T00:03:00+00:00"


class ScoringTimeTests(unittest.TestCase):
    def test_desktop_result_boundary_is_atomic_and_release_retry_preserves_it(self):
        with TemporaryDirectory() as directory:
            state = desktop.JobState(Path(directory) / "state.json")
            state.update(None, "PENDING", scoring_started_at=START)
            row = {"status": "valid", "total_score": 0}
            with patch.object(desktop, "utc_now", return_value=FINISH):
                state.update(None, "release", result=row)
            self.assertEqual(read_json(state.path)["result"]["scoring_timing"]["finished_at"], FINISH)
            with patch.object(desktop, "utc_now", return_value=RELEASED):
                state.update(None, "completed", result=row, resource_held=False)
            self.assertEqual(row["scoring_timing"], {"started_at": START, "finished_at": FINISH})

    def test_desktop_failure_records_claim_to_result_before_closing_client(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            driver = Mock()
            driver.execute.side_effect = E2EError("FIXTURE_FAILURE")
            driver.staging = root / "work/desktop"

            def close():
                self.assertEqual(read_json(root / "control/state.json")["scoring_finished_at"], FINISH)

            driver.client.close.side_effect = close
            with patch.object(desktop, "_prepare", return_value={}), patch.object(desktop, "ScoringDriver", return_value=driver), \
                    patch.object(desktop, "utc_now", side_effect=[START, FINISH, RELEASED]):
                row = desktop._job(root, ITEM, CONFIG, Mock(), root, "judge-time", root / "cancel.json")
            self.assertEqual(row["status"], "evaluation_error")
            self.assertEqual(row["scoring_timing"], {"started_at": START, "finished_at": FINISH})
            self.assertEqual(row["scoring_runtime"]["finished_at"], RELEASED)

    def test_legacy_desktop_state_does_not_invent_a_start_on_resume(self):
        with TemporaryDirectory() as directory:
            state = desktop.JobState(Path(directory) / "state.json")
            state.update(None, "release", result={"status": "evaluation_error"})
            self.assertNotIn("scoring_timing", state.data["result"])
            self.assertNotIn("scoring_finished_at", state.data)

    def test_cli_failure_and_explicit_recovery_use_the_same_start_and_new_result_boundary(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            item = {"key": "u/r1/t", "unit_id": "u", "task_id": "t", "run_index": 1,
                    "attempt_id": "exec", "phase": "COMPLETED", "execution_root": "original"}
            manifest = {"tasks": [{"task_id": "t", "scene": "general"}]}
            with patch.object(headless, "verify_ready", side_effect=E2EError("FIXTURE_FAILURE")), \
                    patch.object(headless, "owned", return_value=None), \
                    patch.object(headless, "utc_now", side_effect=[START, FINISH, RELEASED]):
                first = headless.score_one(root, item, manifest, {}, root / "job", "test-job", "")
                recovered = headless.score_one(root, item, manifest, {}, root / "job", "test-job", "")
            self.assertEqual(first["scoring_timing"], {"started_at": START, "finished_at": FINISH})
            self.assertEqual(recovered["scoring_timing"], {"started_at": START, "finished_at": RELEASED})
