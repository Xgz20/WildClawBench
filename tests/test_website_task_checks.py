from __future__ import annotations

import importlib
import inspect
import unittest
from pathlib import Path

from src.utils.task_parser import parse_task_md


TASK_MODULES = [
    "eval.checks.website.tasks.task_001_daymark_product_website",
    "eval.checks.website.tasks.task_002_focus_pomodoro_clock",
    "eval.checks.website.tasks.task_003_chengnan_weekend_activity_discovery",
    "eval.checks.website.tasks.task_004_orchard_memory_game",
    "eval.checks.website.tasks.task_005_xiaoman_ledger_dashboard",
    "eval.checks.website.tasks.task_006_xingji_travel_planner",
    "eval.checks.website.tasks.task_007_neon_snake_game",
    "eval.checks.website.tasks.task_008_shiguang_personal_blog",
    "eval.checks.website.tasks.task_009_smart_teaching_dashboard",
    "eval.checks.website.tasks.task_010_paperwork_pdf_tool",
    "eval.checks.website.tasks.task_011_love_anniversary_site",
]


class WebsiteTaskChecksTest(unittest.TestCase):
    def test_each_task_declares_runtime_keys_and_async_run(self) -> None:
        for module_name in TASK_MODULES:
            with self.subTest(module_name=module_name):
                module = importlib.import_module(module_name)
                self.assertTrue(module.RUNTIME_KEYS)
                self.assertTrue(callable(module.run))
                self.assertTrue(callable(module.capture_visual))
                self.assertTrue(set(module.RUNTIME_KEYS).isdisjoint(module.VISUAL_KEYS))

    def test_declared_keys_exactly_cover_each_task_rubric(self) -> None:
        tasks_dir = Path(__file__).resolve().parents[1] / "tasks" / "extension" / "07_Website_Generation"
        for path, module_name in zip(sorted(tasks_dir.glob("*.md")), TASK_MODULES):
            task = parse_task_md(path)
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
        module = importlib.import_module(TASK_MODULES[4])
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
        source = inspect.getsource(importlib.import_module(TASK_MODULES[5]))

        self.assertIn('contains_texts(page, ["行迹 Planner"', source)
        self.assertNotIn("await _add_destination(page)\n", source)
        self.assertIn('await _add_destination(page, "宽窄巷子")', source)
        self.assertIn("_select_day(page, 2", source)

    def test_dashboard_checker_awaits_text_helpers_and_scopes_pagination(self) -> None:
        source = inspect.getsource(importlib.import_module(TASK_MODULES[8]))

        self.assertNotIn("return contains_any_texts(", source)
        self.assertIn("ancestor::*[.//tbody", source)
        self.assertIn('len(after) == 6', source)

    def test_responsive_tasks_capture_mobile_evidence(self) -> None:
        for module_name in (TASK_MODULES[7], TASK_MODULES[9], TASK_MODULES[10]):
            with self.subTest(module_name=module_name):
                source = inspect.getsource(importlib.import_module(module_name).capture_visual)
                self.assertIn('{"width": 375, "height": 812}', source)
                self.assertIn('"mobile-', source)

    def test_pdf_validation_uses_alternative_error_messages(self) -> None:
        source = inspect.getsource(importlib.import_module(TASK_MODULES[9]))

        self.assertIn("contains_any_texts", source)
        self.assertNotIn('[expected, "不能", "无效"]', source)
        self.assertNotIn('contains_texts(page, ["签名不能为空", "请输入签名"])', source)


if __name__ == "__main__":
    unittest.main()
