from __future__ import annotations

import importlib
import inspect
import re
import unittest
from pathlib import Path

import yaml

from src.utils.task_parser import normalize_tags, parse_task_md
from src.utils.website_checks import website_check_module_name


REPO_ROOT = Path(__file__).resolve().parents[1]


def _discover_website_tasks() -> list[tuple[Path, dict, str]]:
    tasks: list[tuple[Path, dict, str]] = []
    for path in sorted((REPO_ROOT / "tasks").rglob("*.md")):
        relative = path.relative_to(REPO_ROOT / "tasks")
        if relative.parts[:1] == ("cn",) or relative.parts[:2] == ("extension", "cn"):
            continue
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n", path.read_text(encoding="utf-8"), re.DOTALL)
        if not match:
            continue
        metadata = yaml.safe_load(match.group(1))
        if not isinstance(metadata, dict) or "web-site-gen" not in normalize_tags(metadata.get("tags")):
            continue
        task = parse_task_md(path)
        module_name = f"eval.checks.website.tasks.{website_check_module_name(task['task_id'])}"
        tasks.append((path, task, module_name))
    return tasks


WEBSITE_TASKS = _discover_website_tasks()
TASK_MODULES = [module_name for _, _, module_name in WEBSITE_TASKS]
TASK_MODULE_BY_SUFFIX = {
    module_name.rsplit(".", 1)[-1]: module_name for module_name in TASK_MODULES
}


class WebsiteTaskChecksTest(unittest.TestCase):
    def test_each_task_declares_runtime_keys_and_async_run(self) -> None:
        self.assertTrue(WEBSITE_TASKS)
        for module_name in TASK_MODULES:
            with self.subTest(module_name=module_name):
                module = importlib.import_module(module_name)
                self.assertTrue(module.RUNTIME_KEYS)
                self.assertTrue(callable(module.run))
                self.assertTrue(callable(module.capture_visual))
                self.assertTrue(set(module.RUNTIME_KEYS).isdisjoint(module.VISUAL_KEYS))

    def test_declared_keys_exactly_cover_each_task_rubric(self) -> None:
        for path, task, module_name in WEBSITE_TASKS:
            module = importlib.import_module(module_name)
            expected_runtime = {
                item["key"] for item in task["rubric_criteria"]
                if item["primary"] != "visual_layout"
            }
            expected_visual = {
                item["key"] for item in task["rubric_criteria"]
                if item["primary"] == "visual_layout"
            }
            with self.subTest(task_id=task["task_id"]):
                self.assertEqual(set(module.RUNTIME_KEYS), expected_runtime)
                self.assertEqual(set(module.VISUAL_KEYS), expected_visual)

    def test_ledger_checks_use_scoped_chart_and_post_mutation_assertions(self) -> None:
        module = importlib.import_module(TASK_MODULE_BY_SUFFIX["task_005_xiaoman_ledger_dashboard"])
        source = inspect.getsource(module)

        self.assertIn("ancestor_contains_texts", source)
        self.assertIn("element_contains_texts", source)
        self.assertIn("fill_any_named", source)
        self.assertIn("visualization_contains_texts", source)
        self.assertIn("_close_detail", source)
        self.assertIn('click_named(page, "支出")', source)
        self.assertGreaterEqual(source.count('click_named(page, "分析")'), 10)
        self.assertIn('["学习", "¥88.00"]', source)

    def test_travel_checker_keeps_exact_brand_and_passes_destination_name(self) -> None:
        source = inspect.getsource(importlib.import_module(TASK_MODULE_BY_SUFFIX["task_006_xingji_travel_planner"]))

        self.assertIn('contains_texts(page, ["行迹 Planner"', source)
        self.assertNotIn("await _add_destination(page)\n", source)
        self.assertIn('await _add_destination(page, "宽窄巷子")', source)
        self.assertIn("_select_day(page, 2", source)

    def test_dashboard_checker_awaits_text_helpers_and_scopes_pagination(self) -> None:
        source = inspect.getsource(importlib.import_module(TASK_MODULE_BY_SUFFIX["task_009_smart_teaching_dashboard"]))

        self.assertNotIn("return contains_any_texts(", source)
        self.assertIn("ancestor::*[.//tbody", source)
        self.assertIn('len(after) == 6', source)

    def test_responsive_tasks_capture_mobile_evidence(self) -> None:
        for suffix in (
            "task_008_shiguang_personal_blog",
            "task_010_paperwork_pdf_tool",
            "task_011_love_anniversary_site",
        ):
            module_name = TASK_MODULE_BY_SUFFIX[suffix]
            with self.subTest(module_name=module_name):
                source = inspect.getsource(importlib.import_module(module_name).capture_visual)
                self.assertIn('{"width": 375, "height": 812}', source)
                self.assertIn('"mobile-', source)

    def test_pdf_validation_uses_alternative_error_messages(self) -> None:
        source = inspect.getsource(importlib.import_module(TASK_MODULE_BY_SUFFIX["task_010_paperwork_pdf_tool"]))

        self.assertIn("contains_any_texts", source)
        self.assertNotIn('[expected, "不能", "无效"]', source)
        self.assertNotIn('contains_texts(page, ["签名不能为空", "请输入签名"])', source)


if __name__ == "__main__":
    unittest.main()
