from __future__ import annotations

import unittest
from pathlib import Path

from src.utils.task_parser import parse_task_md


ROOT = Path(__file__).resolve().parents[1]
TASKS_DIR = ROOT / "tasks"
REQUIRED_TAG = "requires-native-multimodal"
EXPECTED_TASK_IDS = {
    "01_Productivity_Flow_task_8_real_image_category",
    *{
        f"02_Code_Intelligence_task_{task_id}_{suffix}"
        for task_id, suffix in [
            ("7", "connect_the_dots_medium_img_zh"),
            ("8", "link_a_pix_color_zh"),
            ("9", "link_a_pix_color_easy_zh"),
            ("10", "acad_homepage_zh"),
            ("11", "resume_homepage_zh"),
            ("12", "connect_the_dots_hard_zh"),
        ]
    },
    "04_Search_Retrieval_task_7_location_search",
    "04_Search_Retrieval_task_9_artwork_search",
    *{
        f"05_Creative_Synthesis_task_{task_id}_{suffix}"
        for task_id, suffix in [
            ("1", "match_report"),
            ("2", "goal_highlights"),
            ("3", "product_poster"),
            ("4", "video_notes"),
            ("5", "product_launch_video_to_json"),
            ("6", "clothing_outfit_to_model_image"),
            ("7", "paper_to_poster"),
            ("10", "social_poster_multi_crop"),
            ("11", "video_en_to_zh_dub"),
        ]
    },
}


class RequiredMultimodalTaskTagsTest(unittest.TestCase):
    def test_required_multimodal_tag_matches_reviewed_official_task_set(self) -> None:
        self.assert_tagged_set(TASKS_DIR, EXPECTED_TASK_IDS)

    def test_required_multimodal_tag_matches_reviewed_chinese_task_set(self) -> None:
        self.assert_tagged_set(TASKS_DIR / "cn", EXPECTED_TASK_IDS)

    def assert_tagged_set(self, tasks_dir: Path, expected: set[str]) -> None:
        tagged: set[str] = set()
        for path in tasks_dir.glob("*/*task_*.md"):
            task = parse_task_md(path)
            if REQUIRED_TAG in task["tags"]:
                tagged.add(task["task_id"])

        self.assertEqual(tagged, expected)
        self.assertEqual(len(tagged), 18)


if __name__ == "__main__":
    unittest.main()
