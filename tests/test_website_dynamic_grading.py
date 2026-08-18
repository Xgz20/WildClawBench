from __future__ import annotations

import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.utils.grading import _grade_llm_rubric, _run_grading_v2
from src.utils.website_checks import (
    CONTAINER_AUDIT_DIR,
    CONTAINER_CHECKS_DIR,
    CONTAINER_EVAL_DIR,
    merge_website_evidence,
    run_website_checks,
    website_check_module_name,
)


class WebsiteDynamicGradingTest(unittest.TestCase):
    def test_module_name_is_resolved_from_full_task_id(self) -> None:
        self.assertEqual(
            website_check_module_name(
                "07_Website_Generation_task_001_daymark_product_website"
            ),
            "task_001_daymark_product_website",
        )

    def test_merge_keeps_runtime_and_visual_scores_by_canonical_key(self) -> None:
        criteria = [
            {"key": "content", "primary": "content_structure", "weight": 0.4},
            {"key": "interaction", "primary": "interaction_function", "weight": 0.3},
            {"key": "visual", "primary": "visual_layout", "weight": 0.3},
        ]
        scores = merge_website_evidence(
            criteria,
            {"content": {"score": 1.0}, "interaction": {"score": 0.0}},
            {"visual": 0.5},
        )
        self.assertEqual(scores["automated.content"], 1.0)
        self.assertEqual(scores["automated.interaction"], 0.0)
        self.assertEqual(scores["llm_judge.visual"], 0.5)
        self.assertEqual(scores["overall_score"], 0.55)
        self.assertEqual(scores["_dimensions"]["evidence_mode"], "browser_runtime+visual_llm")

    def test_missing_runtime_key_is_explicit_zero(self) -> None:
        scores = merge_website_evidence(
            [{"key": "content", "primary": "content_structure", "weight": 1.0}],
            {},
            {},
        )
        self.assertEqual(scores["automated.content"], 0.0)
        self.assertIn("content", scores["_grading"]["missing_runtime_keys"])

    def test_candidate_build_failure_forces_all_criteria_to_zero(self) -> None:
        scores = merge_website_evidence(
            [
                {"key": "content", "primary": "content_structure", "weight": 0.5},
                {"key": "visual", "primary": "visual_layout", "weight": 0.5},
            ],
            {"content": {"score": 1.0}},
            {"visual": 1.0},
            runtime_status="candidate_failed",
            runtime_error="WEB_BUILD_FAILED: missing App.tsx",
        )
        self.assertEqual(scores["automated.content"], 0.0)
        self.assertEqual(scores["llm_judge.visual"], 0.0)
        self.assertEqual(scores["overall_score"], 0.0)
        self.assertEqual(scores["_grading"]["score_policy"], "candidate_failed_zero")
        self.assertFalse(scores["_grading"]["semantic_fallback"])

    def test_evaluator_failure_is_marked_unreliable(self) -> None:
        scores = merge_website_evidence(
            [
                {"key": "content", "primary": "content_structure", "weight": 0.5},
                {"key": "other", "primary": "interaction_function", "weight": 0.5},
            ],
            {
                "content": {"status": "evaluator_error", "score": None},
                "other": {"status": "passed", "score": 1.0},
            },
            {},
            runtime_status="evaluator_failed",
            runtime_error="EVALUATOR_CHECK_FAILED: content",
        )
        self.assertEqual(scores["overall_score"], 0.0)
        self.assertEqual(scores["_grading"]["status"], "evaluator_failed")
        self.assertEqual(scores["_grading"]["score_policy"], "evaluator_failed_zero")
        self.assertIn("content", scores["_grading"]["missing_runtime_keys"])
        self.assertEqual(scores["automated.other"], 0.0)

    def test_runtime_checker_cleans_evaluator_directories_before_copy(self) -> None:
        completed = SimpleNamespace(
            returncode=0,
            stdout='{"status":"success","checks":{},"screenshots":[]}\n',
            stderr="",
        )
        with tempfile.TemporaryDirectory() as tmp, patch(
            "src.utils.website_checks.subprocess.run", return_value=completed,
        ) as run:
            payload, error = run_website_checks(
                "container",
                "07_Website_Generation_task_001_daymark_product_website",
                Path(tmp),
                timeout_seconds=30,
            )

        self.assertEqual(payload["status"], "success")
        self.assertEqual(error, "")
        self.assertEqual(
            run.call_args_list[0].args[0],
            [
                "docker", "exec", "container", "rm", "-rf",
                CONTAINER_CHECKS_DIR, CONTAINER_AUDIT_DIR,
            ],
        )

    def test_runtime_checker_copies_eval_fixtures_after_agent_execution(self) -> None:
        completed = SimpleNamespace(
            returncode=0,
            stdout='{"status":"success","checks":{},"screenshots":[]}\n',
            stderr="",
        )
        with tempfile.TemporaryDirectory() as tmp:
            task_root = Path(tmp) / "task_010_paperwork_pdf_tool" / "eval"
            task_root.mkdir(parents=True)
            (task_root / "fixture.pdf").write_bytes(b"fixture")
            with patch(
                "src.utils.website_checks.WEBSITE_TASK_WORKSPACE_DIR", Path(tmp),
            ), patch(
                "src.utils.website_checks.subprocess.run", return_value=completed,
            ) as run:
                payload, error = run_website_checks(
                    "container",
                    "07_Website_Generation_task_010_paperwork_pdf_tool",
                    Path(tmp) / "out",
                    timeout_seconds=30,
                )
        self.assertEqual(payload["status"], "success")
        self.assertEqual(error, "")
        commands = [call.args[0] for call in run.call_args_list]
        self.assertIn(
            ["docker", "exec", "container", "rm", "-rf", CONTAINER_EVAL_DIR],
            commands,
        )
        self.assertIn(
            [
                "docker", "cp", f"{task_root}/.",
                f"container:{CONTAINER_EVAL_DIR}/",
            ],
            commands,
        )

    def test_web_grading_routes_runtime_and_visual_criteria_separately(self) -> None:
        criteria = [
            {"key": "content", "primary": "content_structure", "secondary": "basic", "weight": 0.4},
            {"key": "interaction", "primary": "interaction_function", "secondary": "switch", "weight": 0.3},
            {"key": "visual", "primary": "visual_layout", "secondary": "layout", "weight": 0.3},
        ]
        with tempfile.TemporaryDirectory() as tmp, patch(
            "src.utils.website_checks.run_website_checks",
            return_value=(
                {
                    "status": "success",
                    "checks": {
                        "content": {"score": 1.0},
                        "interaction": {"score": 0.0},
                    },
                },
                "",
            ),
        ), patch(
            "src.utils.grading._grade_llm_rubric",
            return_value=(0.5, {"visual": 0.5}, "visual evidence"),
        ) as judge:
            scores = _run_grading_v2(
                task_id="container",
                automated_checks="",
                output_dir=Path(tmp),
                extra_env="",
                lobster_env=None,
                transcript_container_path="",
                write_error_score=True,
                llm_judge_rubric="rubric",
                rubric_criteria=criteria,
                grading_weights={},
                metric_profile="web-site-gen",
                task_definition_id="07_Website_Generation_task_001_daymark_product_website",
            )

        self.assertEqual(scores["overall_score"], 0.55)
        self.assertEqual(judge.call_args.args[2], [criteria[2]])
        self.assertEqual(judge.call_args.kwargs["evidence_mode"], "browser_runtime+visual_llm")

    def test_web_grading_without_visual_criteria_skips_judge(self) -> None:
        criteria = [
            {
                "key": "content",
                "primary": "content_structure",
                "secondary": "basic",
                "weight": 1.0,
            }
        ]
        with tempfile.TemporaryDirectory() as tmp, patch(
            "src.utils.website_checks.run_website_checks",
            return_value=(
                {"status": "success", "checks": {"content": {"score": 1.0}}},
                "",
            ),
        ), patch("src.utils.grading._grade_llm_rubric") as judge:
            scores = _run_grading_v2(
                task_id="container",
                automated_checks="",
                output_dir=Path(tmp),
                extra_env="",
                lobster_env=None,
                transcript_container_path="",
                write_error_score=True,
                llm_judge_rubric="rubric",
                rubric_criteria=criteria,
                grading_weights={},
                metric_profile="web-site-gen",
                task_definition_id="07_Website_Generation_task_001_example",
            )

        judge.assert_not_called()
        self.assertEqual(scores["overall_score"], 1.0)

    def test_web_candidate_failure_skips_visual_judge_and_records_error(self) -> None:
        criteria = [
            {
                "key": "visual",
                "primary": "visual_layout",
                "secondary": "layout",
                "weight": 1.0,
            }
        ]
        runtime_error = "WEB_BUILD_FAILED: npm run build failed"
        with tempfile.TemporaryDirectory() as tmp, patch(
            "src.utils.website_checks.run_website_checks",
            return_value=(
                {"status": "candidate_failed", "checks": {}, "error": runtime_error},
                runtime_error,
            ),
        ), patch("src.utils.grading._grade_llm_rubric") as judge:
            scores = _run_grading_v2(
                task_id="container",
                automated_checks="",
                output_dir=Path(tmp),
                extra_env="",
                lobster_env=None,
                transcript_container_path="",
                write_error_score=True,
                llm_judge_rubric="rubric",
                rubric_criteria=criteria,
                grading_weights={},
                metric_profile="web-site-gen",
                task_definition_id="07_Website_Generation_task_001_example",
            )

        judge.assert_not_called()
        self.assertEqual(scores["overall_score"], 0.0)
        self.assertEqual(scores["_grading"]["website_runtime_error"], runtime_error)
        self.assertEqual(scores["_grading"]["status"], "candidate_failed")
        self.assertEqual(scores["_grading"]["score_policy"], "candidate_failed_zero")
        self.assertFalse(scores["_grading"]["semantic_fallback"])

    def test_dynamic_visual_judge_does_not_receive_source_or_transcript(self) -> None:
        criteria = [
            {
                "key": "visual",
                "primary": "visual_layout",
                "secondary": "layout",
                "weight": 1.0,
                "rubric": "### Criterion 3: Visual (key: visual, weight: 1.0)\nvisual evidence",
            }
        ]
        envelope = {
            "candidate_text": '{"scores":{"visual":1.0},"notes":"ok"}',
            "request": {},
            "response": {},
        }
        with patch(
            "src.utils.grading._exec_container_python",
            return_value=(envelope, ""),
        ) as execute:
            _grade_llm_rubric(
                "container",
                (
                    "### Criterion 1: Hero (key: hero_content, weight: 0.5)\n"
                    "interaction_function content\n\n"
                    "### Criterion 3: Visual (key: visual, weight: 1.0)\n"
                    "visual evidence"
                ),
                criteria,
                "/tmp/transcript.jsonl",
                "web-site-gen",
                evidence_mode="browser_runtime+visual_llm",
            )

        runner_code = execute.call_args.args[1]
        self.assertNotIn("## Agent Workspace Files", runner_code)
        self.assertNotIn("## Agent Transcript", runner_code)
        self.assertNotIn("hero_content", runner_code)
        self.assertNotIn("interaction_function", runner_code)
        self.assertIn("Website screenshot:", runner_code)


if __name__ == "__main__":
    unittest.main()
