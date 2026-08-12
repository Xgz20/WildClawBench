from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml

from src.utils.task_parser import parse_task_md


REPO_ROOT = Path(__file__).resolve().parents[1]
CATEGORY = "07_Website_Generation"
TASKS_DIR = REPO_ROOT / "tasks" / "extension" / CATEGORY
WORKSPACE_DIR = REPO_ROOT / "workspace" / "extension" / CATEGORY

EXPECTED_TASKS = {
    "task_001_daymark_product_website": {
        "task_type": "企业／产品官网",
        "difficulty": "L1",
    },
    "task_002_focus_pomodoro_clock": {
        "task_type": "效率工具／番茄钟",
        "difficulty": "L1",
    },
    "task_003_chengnan_weekend_activity_discovery": {
        "task_type": "生活服务／活动发现",
        "difficulty": "L1",
    },
    "task_004_orchard_memory_game": {
        "task_type": "休闲娱乐／翻牌配对游戏",
        "difficulty": "L1",
    },
    "task_005_xiaoman_ledger_dashboard": {
        "task_type": "个人财务／本地记账仪表盘",
        "difficulty": "L2",
    },
}


def load_frontmatter(path: Path) -> dict:
    content = path.read_text(encoding="utf-8")
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not match:
        raise AssertionError(f"YAML frontmatter not found: {path}")
    metadata = yaml.safe_load(match.group(1))
    if not isinstance(metadata, dict):
        raise AssertionError(f"YAML frontmatter must be a mapping: {path}")
    return metadata


class WebsiteGenerationTaskContractTest(unittest.TestCase):
    def test_web_task_frontmatter_matches_the_website_metadata_contract(self) -> None:
        task_files = sorted(TASKS_DIR.glob("*.md"))
        self.assertEqual(len(task_files), len(EXPECTED_TASKS))

        for path in task_files:
            metadata = load_frontmatter(path)
            task_id = str(metadata["id"])
            short_id = task_id.removeprefix(f"{CATEGORY}_")
            expected = EXPECTED_TASKS[short_id]

            with self.subTest(task_id=task_id):
                self.assertEqual(metadata["category"], CATEGORY)
                self.assertEqual(metadata["sub_category"], "自然语言页面构建")
                self.assertEqual(metadata["task_type"], expected["task_type"])
                self.assertEqual(metadata["difficulty"], expected["difficulty"])
                self.assertEqual(metadata["grading_type"], "llm_judge")
                self.assertEqual(metadata["tags"], ["custom", "web-site-gen"])
                self.assertNotIn("sub_scene", metadata)
                self.assertNotIn("application_type", metadata)
                self.assertNotIn("acceptance_tests", metadata)

    def test_web_task_workspace_paths_resolve_to_extension_workspaces(self) -> None:
        for path in sorted(TASKS_DIR.glob("*.md")):
            task = parse_task_md(path)
            short_id = task["task_id"].removeprefix(f"{CATEGORY}_")
            expected_workspace = (WORKSPACE_DIR / short_id).resolve()

            with self.subTest(task_id=task["task_id"]):
                self.assertEqual(Path(task["workspace_path"]), expected_workspace)
                self.assertTrue((expected_workspace / "exec").is_dir())
                self.assertFalse((expected_workspace / "gt").exists())

    def test_web_tasks_do_not_declare_unused_checks_warmup_or_skills(self) -> None:
        for path in sorted(TASKS_DIR.glob("*.md")):
            task = parse_task_md(path)

            with self.subTest(task_id=task["task_id"]):
                self.assertEqual(task["automated_checks"], "")
                self.assertEqual(task["warmup"], "")
                self.assertEqual(task["skills"], "")


if __name__ == "__main__":
    unittest.main()
