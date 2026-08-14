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
        "criterion_count": 10,
    },
    "task_002_focus_pomodoro_clock": {
        "task_type": "效率工具／番茄钟",
        "difficulty": "L1",
        "criterion_count": 12,
    },
    "task_003_chengnan_weekend_activity_discovery": {
        "task_type": "生活服务／活动发现",
        "difficulty": "L1",
        "criterion_count": 10,
    },
    "task_004_orchard_memory_game": {
        "task_type": "休闲娱乐／翻牌配对游戏",
        "difficulty": "L1",
        "criterion_count": 11,
    },
    "task_005_xiaoman_ledger_dashboard": {
        "task_type": "个人财务／本地记账仪表盘",
        "difficulty": "L2",
        "criterion_count": 23,
    },
    "task_006_xingji_travel_planner": {
        "task_type": "旅行行程规划器",
        "difficulty": "L2",
        "criterion_count": 20,
    },
    "task_007_neon_snake_game": {
        "task_type": "双人街机小游戏",
        "difficulty": "L2",
        "criterion_count": 14,
    },
    "task_008_shiguang_personal_blog": {
        "task_type": "个人博客",
        "difficulty": "L2",
        "criterion_count": 23,
    },
    "task_009_smart_teaching_dashboard": {
        "task_type": "数据分析看板",
        "difficulty": "L2",
        "criterion_count": 24,
    },
    "task_010_paperwork_pdf_tool": {
        "task_type": "本地文档处理工具",
        "difficulty": "L2",
        "criterion_count": 17,
    },
    "task_011_love_anniversary_site": {
        "task_type": "恋爱纪念与生活记录网站",
        "difficulty": "L2",
        "criterion_count": 25,
    },
}

EXPECTED_FRONTMATTER_KEYS = {
    "id",
    "name",
    "category",
    "sub_category",
    "task_type",
    "timeout_seconds",
    "modality",
    "difficulty",
    "grading_type",
    "tags",
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


def load_sections(path: Path) -> dict[str, str]:
    content = path.read_text(encoding="utf-8")
    body = re.split(r"^---\s*$", content, maxsplit=2, flags=re.MULTILINE)[2]
    sections: dict[str, str] = {}
    current: str | None = None
    lines: list[str] = []
    for line in body.splitlines():
        heading = re.match(r"^##\s+(.+)$", line)
        if heading:
            if current is not None:
                sections[current] = "\n".join(lines).strip()
            current = heading.group(1)
            lines = []
        else:
            lines.append(line)
    if current is not None:
        sections[current] = "\n".join(lines).strip()
    return sections


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
                self.assertEqual(set(metadata), EXPECTED_FRONTMATTER_KEYS)
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

    def test_web_tasks_declare_the_standard_node_startup_contract(self) -> None:
        required_fragments = (
            "package.json",
            "npm install",
            "npm run build",
            "npm run start -- --host 127.0.0.1 --port 4173",
        )
        for path in sorted(TASKS_DIR.glob("*.md")):
            task = parse_task_md(path)

            with self.subTest(task_id=task["task_id"]):
                for fragment in required_fragments:
                    self.assertIn(fragment, task["prompt"])

    def test_web_tasks_do_not_declare_unused_checks_warmup_or_skills(self) -> None:
        for path in sorted(TASKS_DIR.glob("*.md")):
            task = parse_task_md(path)
            sections = load_sections(path)

            with self.subTest(task_id=task["task_id"]):
                self.assertEqual(task["automated_checks"], "")
                self.assertEqual(task["warmup"], "")
                self.assertEqual(task["skills"], "")
                for section in ("Automated Checks", "Skills", "Warmup"):
                    self.assertEqual(sections.get(section), "")

    def test_web_task_workspace_section_contains_only_the_workspace_path(self) -> None:
        for path in sorted(TASKS_DIR.glob("*.md")):
            task = parse_task_md(path)
            short_id = task["task_id"].removeprefix(f"{CATEGORY}_")

            with self.subTest(task_id=task["task_id"]):
                self.assertEqual(
                    load_sections(path).get("Workspace Path"),
                    f"workspace/extension/{CATEGORY}/{short_id}",
                )

    def test_web_task_rubrics_expose_stable_metric_dimensions(self) -> None:
        allowed_primary = {
            "content_structure",
            "interaction_function",
            "visual_layout",
        }

        for path in sorted(TASKS_DIR.glob("*.md")):
            task = parse_task_md(path)
            short_id = task["task_id"].removeprefix(f"{CATEGORY}_")
            criteria = task["rubric_criteria"]

            with self.subTest(task_id=task["task_id"]):
                self.assertEqual(task["metric_profile"], "web-site-gen")
                self.assertEqual(
                    len(criteria), EXPECTED_TASKS[short_id]["criterion_count"]
                )
                keys = [criterion["key"] for criterion in criteria]
                self.assertEqual(len(keys), len(set(keys)))
                self.assertTrue(
                    all(re.fullmatch(r"[a-z][a-z0-9_]*", key) for key in keys)
                )
                self.assertTrue(
                    all(criterion["primary"] in allowed_primary for criterion in criteria)
                )
                self.assertTrue(all(criterion["secondary"] for criterion in criteria))
                self.assertTrue(all(criterion["weight"] > 0 for criterion in criteria))
                self.assertAlmostEqual(
                    sum(criterion["weight"] for criterion in criteria), 1.0, places=3
                )
                self.assertEqual(
                    [
                        int(number)
                        for number in re.findall(
                            r"^###\s+Criterion\s+(\d+)\s*[:：]",
                            task["llm_judge_rubric"],
                            re.MULTILINE,
                        )
                    ],
                    list(range(1, len(criteria) + 1)),
                )
                for criterion in criteria:
                    self.assertIn("Score 1.0:", criterion["rubric"])
                    self.assertIn("Score 0.0:", criterion["rubric"])
                self.assertNotIn(
                    "Judge 只根据实际页面和操作结果判断",
                    task["llm_judge_rubric"],
                )


if __name__ == "__main__":
    unittest.main()
