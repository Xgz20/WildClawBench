from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.utils.task_parser import parse_rubric_criteria, parse_task_md


class RubricCriteriaParserTest(unittest.TestCase):
    def test_parses_optional_website_dimension_keys(self) -> None:
        rubric = """\
### Criterion 1: 首屏内容 (key: hero_content, primary: content_structure, secondary: basic_content, weight: 0.2)

Score 1.0: 内容完整。
Score 0.0: 内容缺失。
"""

        self.assertEqual(
            parse_rubric_criteria(rubric),
            [
                {
                    "key": "hero_content",
                    "primary": "content_structure",
                    "secondary": "basic_content",
                    "weight": 0.2,
                    "name": "首屏内容",
                    "rubric": rubric.strip(),
                }
            ],
        )

    def test_keeps_key_and_weight_only_format_compatible(self) -> None:
        rubric = """\
### Criterion 1: 结果正确性 (key: result_accuracy, weight: 1.0)

Score 1.0: 结果正确。
Score 0.0: 结果错误。
"""

        criterion = parse_rubric_criteria(rubric)[0]

        self.assertEqual(criterion["key"], "result_accuracy")
        self.assertEqual(criterion["weight"], 1.0)
        self.assertEqual(criterion["primary"], "")
        self.assertEqual(criterion["secondary"], "")

    def test_website_task_rejects_any_unparseable_criterion(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "website.md"
            path.write_text(
                "---\n"
                "id: website\n"
                "grading_type: llm_judge\n"
                "tags: [custom, web-site-gen]\n"
                "---\n\n"
                "## Prompt\nTest\n\n"
                "## Automated Checks\n\n"
                "## LLM Judge Rubric\n\n"
                "### Criterion 1: Valid (key: valid, primary: content_structure, secondary: basic_content, weight: 0.5)\n\n"
                "Score 1.0: pass\n\n"
                "### Criterion 2: Missing key (weight: 0.5)\n\n"
                "Score 1.0: pass\n\n"
                "## Workspace Path\nworkspace/example\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "declares 2 criteria but parsed 1"):
                parse_task_md(path)

    def test_website_tag_selects_metric_profile(self) -> None:
        task = parse_task_md(
            Path(__file__).resolve().parents[1]
            / "tasks/extension/07_Website_Generation"
            / "07_Website_Generation_task_001_daymark_product_website.md"
        )

        self.assertEqual(task["metric_profile"], "web-site-gen")

    def test_ppt_tag_selects_metric_profile(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "ppt.md"
            path.write_text(
                "---\n"
                "id: ppt\n"
                "tags: [ppt]\n"
                "---\n\n"
                "## Prompt\nTest\n\n"
                "## Workspace Path\nworkspace/example\n",
                encoding="utf-8",
            )

            self.assertEqual(parse_task_md(path)["metric_profile"], "ppt")

    def test_non_specialized_task_has_no_metric_profile(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "plain.md"
            path.write_text(
                "---\n"
                "id: plain\n"
                "tags: [custom]\n"
                "---\n\n"
                "## Prompt\nTest\n\n"
                "## Workspace Path\nworkspace/example\n",
                encoding="utf-8",
            )

            self.assertEqual(parse_task_md(path)["metric_profile"], "")


if __name__ == "__main__":
    unittest.main()
