from __future__ import annotations

import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from src.utils.task_parser import parse_task_md


REPO_ROOT = Path(__file__).resolve().parents[1]
TASK_FILES = (
    REPO_ROOT / "tasks/05_Creative_Synthesis/05_Creative_Synthesis_task_3_product_poster.md",
    REPO_ROOT / "tasks/cn/05_Creative_Synthesis/05_Creative_Synthesis_task_3_product_poster.md",
)


class ProductPosterGraderTest(unittest.TestCase):
    def _grade(self, task_file: Path, judge_response: str) -> dict:
        checks = parse_task_md(task_file)["automated_checks"]
        with tempfile.TemporaryDirectory() as temp:
            results = Path(temp) / "results"
            results.mkdir()
            Image.new("RGB", (1080, 1440), "white").save(results / "poster.png")
            checks = checks.replace(
                'Path("/tmp_workspace/results")',
                f"Path({json.dumps(str(results))})",
            )

            class FakeCompletions:
                @staticmethod
                def create(**_kwargs):
                    return SimpleNamespace(choices=[SimpleNamespace(
                        message=SimpleNamespace(content=judge_response)
                    )])

            class FakeOpenAI:
                def __init__(self, **_kwargs):
                    self.chat = SimpleNamespace(completions=FakeCompletions())

            openai = types.ModuleType("openai")
            openai.OpenAI = FakeOpenAI
            namespace: dict = {}
            with patch.dict(sys.modules, {"openai": openai}), patch.dict(os.environ, {
                "OPENROUTER_API_KEY": "test-key",
                "OPENROUTER_BASE_URL": "https://example.test",
                "JUDGE_MODEL": "test-judge",
            }):
                exec(checks, namespace)
                return namespace["grade"]()

    def test_accepts_json_followed_by_judge_commentary(self) -> None:
        response = (
            "```json\n"
            '{"content_completeness": 0.8, "feature_highlighting": 0.6, '
            '"design_impact": 0.4}\n'
            "```\nThe poster has a clear hierarchy."
        )
        for task_file in TASK_FILES:
            with self.subTest(task_file=task_file):
                scores = self._grade(task_file, response)
                self.assertNotIn("llm_error", scores)
                self.assertEqual(scores["dimensions_correct"], 1.0)
                self.assertEqual(scores["overall_score"], 0.56)

    def test_invalid_judge_response_preserves_automated_scores_and_excerpt(self) -> None:
        for task_file in TASK_FILES:
            with self.subTest(task_file=task_file):
                scores = self._grade(task_file, "The judge did not return JSON.")
                self.assertEqual(scores["poster_exists"], 1.0)
                self.assertEqual(scores["dimensions_correct"], 1.0)
                self.assertEqual(scores["overall_score"], 0.0)
                self.assertIn("llm_error", scores)
                self.assertEqual(
                    scores["llm_raw_excerpt"], "The judge did not return JSON."
                )


if __name__ == "__main__":
    unittest.main()
