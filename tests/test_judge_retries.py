from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.utils.grading import _grade_llm_rubric, _judge_retries


class JudgeRetryTest(unittest.TestCase):
    def test_judge_retries_defaults_to_two_and_is_configurable(self) -> None:
        with patch.dict("os.environ", {"WILDCLAW_JUDGE_RETRIES": ""}):
            self.assertEqual(_judge_retries(), 2)
        with patch.dict("os.environ", {"WILDCLAW_JUDGE_RETRIES": "1"}):
            self.assertEqual(_judge_retries(), 1)

    def test_invalid_json_is_retried_and_every_attempt_is_audited(self) -> None:
        attempts = iter([
            ({"candidate_text": "not-json", "request": {"model": "judge"}, "response": {"raw_text": "not-json"}}, ""),
            ({"candidate_text": json.dumps({"scores": {"quality": 0.75}, "notes": "ok"}), "request": {"model": "judge"}, "response": {"raw_text": "valid"}}, ""),
        ])
        with tempfile.TemporaryDirectory() as tmp, patch(
            "src.utils.grading._exec_container_python", side_effect=lambda *args, **kwargs: next(attempts)
        ), patch.dict("os.environ", {"WILDCLAW_JUDGE_RETRIES": "2"}):
            score, breakdown, notes = _grade_llm_rubric(
                "task", "rubric", [{"key": "quality", "weight": 1.0}], "",
                output_dir=Path(tmp),
            )
            judge_dir = Path(tmp) / "judge"
            self.assertEqual(score, 0.75)
            self.assertEqual(breakdown, {"quality": 0.75})
            self.assertEqual(notes, "ok")
            self.assertTrue((judge_dir / "attempt-001/response.json").exists())
            self.assertTrue((judge_dir / "attempt-002/parsed.json").exists())
            summary = json.loads((judge_dir / "summary.json").read_text())
            self.assertEqual(summary["selected_attempt"], 2)
            self.assertEqual(summary["status"], "success")

    def test_exhausted_invalid_json_retains_failure_semantics(self) -> None:
        envelope = {"candidate_text": "not-json", "request": {}, "response": {"raw_text": "not-json"}}
        with tempfile.TemporaryDirectory() as tmp, patch(
            "src.utils.grading._exec_container_python", return_value=(envelope, "")
        ), patch.dict("os.environ", {"WILDCLAW_JUDGE_RETRIES": "1"}):
            score, breakdown, notes = _grade_llm_rubric(
                "task", "rubric", [{"key": "quality", "weight": 1.0}], "",
                output_dir=Path(tmp),
            )
            self.assertEqual(score, 0.0)
            self.assertEqual(breakdown, {"quality": 0.0})
            self.assertIn("judge failed", notes)
            summary = json.loads((Path(tmp) / "judge/summary.json").read_text())
            self.assertEqual(summary["attempt_count"], 2)
            self.assertEqual(summary["status"], "failed")

    def test_ppt_render_failure_is_not_retried(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch(
            "src.utils.grading._exec_container_python",
            return_value=(None, "judge runner failed: PPT_RENDER_FAILED: no soffice"),
        ) as execute, patch.dict("os.environ", {"WILDCLAW_JUDGE_RETRIES": "2"}):
            score, _, notes = _grade_llm_rubric(
                "task", "rubric", [{"key": "quality", "weight": 1.0}], "",
                metric_profile="ppt", output_dir=Path(tmp),
            )
            self.assertEqual(score, 0.0)
            self.assertIn("PPT_RENDER_FAILED", notes)
            self.assertEqual(execute.call_count, 1)
            summary = json.loads((Path(tmp) / "judge/summary.json").read_text())
            self.assertEqual(summary["attempt_count"], 1)


if __name__ == "__main__":
    unittest.main()
