from pathlib import Path
from types import SimpleNamespace
import unittest

import yaml

from tools.report.scripts import generate_eval_report


REPO_ROOT = Path(__file__).resolve().parents[1]
CAPABILITY_MAP_PATH = REPO_ROOT / "tools/report/data/checkpoint_capability_map7.yaml"
CAPABILITIES = {
    "code_generation",
    "tool_use",
    "data_processing",
    "retrieval_verification",
    "reasoning_planning",
    "content_generation",
    "verification_delivery",
}


class CheckpointCapabilityMapTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.capability_map = yaml.safe_load(
            CAPABILITY_MAP_PATH.read_text(encoding="utf-8")
        )

    def capabilities(self, task_id, checkpoint):
        return self.capability_map[task_id][checkpoint]

    def test_every_checkpoint_uses_one_or_two_known_unique_capabilities(self):
        for task_id, checkpoints in self.capability_map.items():
            with self.subTest(task_id=task_id):
                self.assertIsInstance(checkpoints, dict)
                self.assertTrue(checkpoints)
            for checkpoint, capabilities in checkpoints.items():
                with self.subTest(task_id=task_id, checkpoint=checkpoint):
                    self.assertIn(len(capabilities), (1, 2))
                    self.assertEqual(len(capabilities), len(set(capabilities)))
                    self.assertFalse(set(capabilities) - CAPABILITIES)

    def test_retrieval_and_delivery_do_not_share_a_checkpoint(self):
        for task_id, checkpoints in self.capability_map.items():
            for checkpoint, capabilities in checkpoints.items():
                with self.subTest(task_id=task_id, checkpoint=checkpoint):
                    self.assertFalse(
                        {
                            "retrieval_verification",
                            "verification_delivery",
                        }.issubset(capabilities)
                    )

    def test_source_lookup_and_delivery_examples_keep_distinct_boundaries(self):
        self.assertEqual(
            self.capabilities(
                "04_Search_Retrieval_task_003_local_release_note_lookup",
                "evidence_traceable",
            ),
            ["retrieval_verification"],
        )
        self.assertEqual(
            self.capabilities(
                "02_Code_Intelligence_task_006_tomllib_reader",
                "source_delivery_correct",
            ),
            ["verification_delivery"],
        )
        self.assertEqual(
            self.capabilities(
                "05_Creative_Synthesis_task_009_accessibility_law_cards",
                "automated.citation_shape",
            ),
            ["verification_delivery"],
        )

    def test_local_source_fidelity_is_data_processing(self):
        task_ids = (
            "01_Productivity_Flow_task_011_weekly_focus",
            "01_Productivity_Flow_task_012_policy_redesign",
            "01_Productivity_Flow_task_013_version_merge",
            "03_Social_Interaction_task_011_client_update",
            "03_Social_Interaction_task_012_feedback_revision",
            "05_Creative_Synthesis_task_011_training_deck",
            "05_Creative_Synthesis_task_014_bilingual_strategy",
        )
        for task_id in task_ids:
            with self.subTest(task_id=task_id):
                self.assertEqual(
                    self.capabilities(task_id, "automated.source_fidelity"),
                    ["data_processing"],
                )

    def test_code_test_results_are_not_tool_use(self):
        examples = (
            (
                "02_Code_Intelligence_task_001_temperature_cli_fix",
                "public_tests_passed",
            ),
            (
                "02_Code_Intelligence_task_004_csv_dialect_fix",
                "scope_api_preserved",
            ),
            (
                "02_Code_Intelligence_task_009_safe_archive_extract",
                "automated.atomic_no_partial_delivery",
            ),
        )
        for task_id, checkpoint in examples:
            with self.subTest(task_id=task_id, checkpoint=checkpoint):
                capabilities = self.capabilities(task_id, checkpoint)
                self.assertIn("code_generation", capabilities)
                self.assertNotIn("tool_use", capabilities)

    def test_presentation_slide_structure_is_delivery_only(self):
        for task_id, checkpoints in self.capability_map.items():
            checkpoint = "automated.slide_count_and_order"
            if checkpoint not in checkpoints:
                continue
            with self.subTest(task_id=task_id):
                self.assertEqual(checkpoints[checkpoint], ["verification_delivery"])

    def test_known_aggregate_checkpoints_are_not_mapped_with_components(self):
        forbidden = {
            "01_Productivity_Flow_task_1_arxiv_digest": {
                "classify_score",
                "interest_score",
                "metadata_score",
            },
            "02_Code_Intelligence_task_10_acad_homepage_zh": {
                "content_score",
                "prompt_score",
                "style_score",
                "visual_score",
            },
            "02_Code_Intelligence_task_11_resume_homepage_zh": {
                "content_score",
                "prompt_score",
                "style_score",
                "visual_score",
            },
            "03_Social_Interaction_task_2_chat_action_extraction": {
                "points_earned",
            },
            "03_Social_Interaction_task_3_chat_multi_step_reasoning": {
                "points_earned",
                "safety_earned",
            },
        }
        for task_id, checkpoints in forbidden.items():
            with self.subTest(task_id=task_id):
                self.assertFalse(checkpoints & self.capability_map[task_id].keys())

    def test_single_score_task_contributes_without_checkpoint_details(self):
        unit = SimpleNamespace(
            tasks=[
                SimpleNamespace(
                    task_id="single_score_task",
                    checkpoints={},
                    score=0.75,
                )
            ]
        )
        capability_map = {
            "single_score_task": {
                "overall_score": ["retrieval_verification"],
            }
        }
        self.assertEqual(
            generate_eval_report._cap_task_scores(
                unit,
                capability_map,
                "retrieval_verification",
                delivered_only=False,
            ),
            [0.75],
        )


if __name__ == "__main__":
    unittest.main()
