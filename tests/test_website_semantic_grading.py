from __future__ import annotations

import unittest
from unittest.mock import patch

from src.utils.grading import (
    _aggregate_rubric_dimensions,
    _build_rubric_judge_prompt,
    _combine_v2,
    _grade_llm_rubric,
    _judge_max_tokens,
    _legacy_workspace_reader_code,
    _semantic_workspace_reader_code,
)


class WebsiteSemanticGradingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.criteria = [
            {
                "key": "hero_content",
                "primary": "content_structure",
                "secondary": "basic_content",
                "weight": 0.2,
            },
            {
                "key": "pricing_switch",
                "primary": "interaction_function",
                "secondary": "content_switching",
                "weight": 0.5,
            },
            {
                "key": "page_layout",
                "primary": "visual_layout",
                "secondary": "page_layout",
                "weight": 0.3,
            },
        ]

    def test_source_reader_includes_frontend_sources_and_excludes_generated_dirs(self) -> None:
        code = _semantic_workspace_reader_code("/tmp_workspace")

        for extension in (".html", ".css", ".js", ".jsx", ".ts", ".tsx"):
            with self.subTest(extension=extension):
                self.assertIn(repr(extension), code)
        for directory in ("node_modules", "dist", "build", "coverage"):
            with self.subTest(directory=directory):
                self.assertIn(repr(directory), code)
        for lockfile in ("package-lock.json", "pnpm-lock.yaml", "yarn.lock"):
            with self.subTest(lockfile=lockfile):
                self.assertIn(repr(lockfile), code)
        self.assertIn("_max_source_chars = 80000", code)
        self.assertIn("_total_source_chars", code)

    def test_legacy_reader_does_not_collect_frontend_source_extensions(self) -> None:
        code = _legacy_workspace_reader_code("/tmp_workspace")

        self.assertIn(repr(".html"), code)
        for extension in (".css", ".js", ".jsx", ".ts", ".tsx"):
            with self.subTest(extension=extension):
                self.assertNotIn(repr(extension), code)
        self.assertIn("if len(_files) >= 12", code)

    def test_dimension_scores_are_weighted_within_each_dimension(self) -> None:
        dimensions = _aggregate_rubric_dimensions(
            self.criteria,
            {
                "hero_content": 1.0,
                "pricing_switch": 0.4,
                "page_layout": 0.8,
            },
            metric_profile="web-site-gen",
        )

        self.assertEqual(dimensions["metric_profile"], "web-site-gen")
        self.assertEqual(dimensions["evidence_mode"], "source_semantic")
        self.assertEqual(
            dimensions["primary"]["content_structure"],
            {"score": 1.0, "weight": 0.2, "criterion_count": 1},
        )
        self.assertEqual(
            dimensions["primary"]["interaction_function"],
            {"score": 0.4, "weight": 0.5, "criterion_count": 1},
        )
        self.assertEqual(
            dimensions["secondary"]["page_layout"],
            {
                "score": 0.8,
                "weight": 0.3,
                "criterion_count": 1,
                "primary": "visual_layout",
            },
        )

    def test_combined_score_keeps_atomic_keys_and_adds_dimension_metadata(self) -> None:
        scores = _combine_v2(
            None,
            {},
            0.64,
            {"hero_content": 1.0, "pricing_switch": 0.4, "page_layout": 0.8},
            "source-only review",
            {},
            self.criteria,
            metric_profile="web-site-gen",
        )

        self.assertEqual(scores["overall_score"], 0.64)
        self.assertEqual(scores["_grading"]["mode"], "v2_llm_only")
        self.assertEqual(scores["llm_judge.hero_content"], 1.0)
        self.assertEqual(scores["_dimensions"]["evidence_mode"], "source_semantic")

    def test_source_semantic_scope_is_only_added_for_website_profile(self) -> None:
        website_prompt = _build_rubric_judge_prompt(
            self.criteria, "website rubric", metric_profile="web-site-gen"
        )
        legacy_prompt = _build_rubric_judge_prompt(
            self.criteria, "legacy rubric", metric_profile=""
        )
        other_grouped_prompt = _build_rubric_judge_prompt(
            [{
                "key": "accuracy",
                "primary": "answer_quality",
                "secondary": "factuality",
                "weight": 1.0,
            }],
            "grouped rubric",
        )

        self.assertIn("source-semantic review only", website_prompt)
        self.assertIn("no browser interaction is run", website_prompt)
        self.assertNotIn("source-semantic review only", legacy_prompt)
        self.assertNotIn("source-semantic review only", other_grouped_prompt)

    def test_non_website_dimensions_do_not_emit_website_metadata(self) -> None:
        dimensions = _aggregate_rubric_dimensions(
            self.criteria,
            {"hero_content": 1.0, "pricing_switch": 0.4, "page_layout": 0.8},
            metric_profile="",
        )

        self.assertEqual(dimensions, {})

    def test_judge_max_tokens_defaults_to_1000(self) -> None:
        with patch.dict("os.environ", {}, clear=False):
            with patch.dict("os.environ", {"JUDGE_MAX_TOKENS": ""}):
                self.assertEqual(_judge_max_tokens(), 1000)

    def test_judge_max_tokens_accepts_positive_integer(self) -> None:
        with patch.dict("os.environ", {"JUDGE_MAX_TOKENS": "2400"}):
            self.assertEqual(_judge_max_tokens(), 2400)

    def test_judge_max_tokens_invalid_values_fall_back_to_default(self) -> None:
        for raw in ("invalid", "0", "-1", "1.5"):
            with self.subTest(raw=raw), patch.dict(
                "os.environ", {"JUDGE_MAX_TOKENS": raw}
            ), self.assertLogs("src.utils.grading", level="WARNING"):
                self.assertEqual(_judge_max_tokens(), 1000)

    def test_v2_rubric_judge_request_uses_configured_max_tokens(self) -> None:
        captured = {}

        def fake_exec(_task_id, runner_code, _transcript_path):
            captured["runner_code"] = runner_code
            return {"scores": {"hero_content": 1.0}, "notes": "ok"}, ""

        with patch.dict("os.environ", {"JUDGE_MAX_TOKENS": "2400"}), patch(
            "src.utils.grading._exec_container_python", side_effect=fake_exec
        ):
            _grade_llm_rubric(
                "task",
                "rubric",
                [{"key": "hero_content", "weight": 1.0}],
                "/tmp/chat.jsonl",
            )

        self.assertIn("max_tokens=2400", captured["runner_code"])


if __name__ == "__main__":
    unittest.main()
