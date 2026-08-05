"""Unit tests for central v2 LLM Judge score validation.

Run from the repository root with:
``python3 -m unittest tests/test_grading.py``
"""
from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from utils.grading import (  # noqa: E402
    _align_rubric_scores,
    _build_rubric_judge_prompt,
)


def _criteria(keys: list[str]) -> list[dict]:
    return [{"key": key, "weight": 1.0} for key in keys]


class RubricScoreValidationTest(unittest.TestCase):
    def test_all_five_allowed_scores_are_preserved(self):
        keys = ["full", "strong", "partial", "weak", "none"]
        raw_scores = {
            "full": 1,
            "strong": 0.75,
            "partial": 0.5,
            "weak": 0.25,
            "none": 0,
        }

        score, breakdown, notes = _align_rubric_scores(
            "task_test", {"scores": raw_scores, "notes": "valid"}, _criteria(keys)
        )

        self.assertEqual(
            breakdown,
            {"full": 1.0, "strong": 0.75, "partial": 0.5, "weak": 0.25, "none": 0.0},
        )
        self.assertEqual(score, 0.5)
        self.assertEqual(notes, "valid")

    def test_numbers_outside_five_level_scale_are_zeroed_not_clamped(self):
        raw_scores = {
            "negative": -0.1,
            "between": 0.6,
            "almost_level": 0.749999,
            "above_one": 1.1,
            "too_large_to_convert": 10**400,
        }

        with self.assertLogs("utils.grading", level="ERROR") as logs:
            score, breakdown, _ = _align_rubric_scores(
                "task_test", {"scores": raw_scores}, _criteria(list(raw_scores))
            )

        self.assertEqual(breakdown, {key: 0.0 for key in raw_scores})
        self.assertEqual(score, 0.0)
        self.assertTrue(all("allowed scores are" in message for message in logs.output))

    def test_non_numeric_bool_and_non_finite_values_are_zeroed(self):
        raw_scores = {
            "string": "0.75",
            "boolean": True,
            "missing": None,
            "nan": math.nan,
            "positive_inf": math.inf,
            "negative_inf": -math.inf,
        }

        with self.assertLogs("utils.grading", level="ERROR"):
            score, breakdown, _ = _align_rubric_scores(
                "task_test", {"scores": raw_scores}, _criteria(list(raw_scores))
            )

        self.assertEqual(breakdown, {key: 0.0 for key in raw_scores})
        self.assertEqual(score, 0.0)

    def test_prompt_requires_exact_five_level_scale(self):
        prompt = _build_rubric_judge_prompt(
            _criteria(["content", "format"]), "Follow the task-specific rubric."
        )

        self.assertIn("exactly one of these five numeric values", prompt)
        self.assertIn("1, 0.75, 0.5, 0.25, or 0", prompt)
        self.assertIn("invalid values are rejected and scored as 0", prompt)


if __name__ == "__main__":
    unittest.main()
