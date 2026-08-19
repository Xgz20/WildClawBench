from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from eval.checks.website.common import (
    CheckRecorder,
    ancestor_contains_texts,
    contains_any_texts,
    contains_each_any_texts,
    element_contains_texts,
    fill_any_named,
    visualization_contains_texts,
)
from eval.checks.website.runner import (
    browser_context_options,
    build_start_command,
    canvas_text_capture_script,
    capture_visual_evidence,
    evaluator_errors,
)


class WebsiteCheckRunnerTest(unittest.TestCase):
    def test_start_command_is_localhost_and_fixed_port(self) -> None:
        self.assertEqual(
            build_start_command(),
            ["npm", "run", "start", "--", "--host", "127.0.0.1", "--port", "4173"],
        )

    def test_browser_context_has_fixed_desktop_viewport(self) -> None:
        self.assertEqual(
            browser_context_options(),
            {"viewport": {"width": 1440, "height": 900}, "device_scale_factor": 1},
        )

    def test_canvas_text_capture_tracks_current_render_only(self) -> None:
        script = canvas_text_capture_script()
        self.assertIn("fillText", script)
        self.assertIn("clearRect", script)
        self.assertIn("__wildclawbenchRenderedTexts", script)

    def test_common_helpers_support_scoped_dom_and_visualization_assertions(self) -> None:
        self.assertTrue(callable(ancestor_contains_texts))
        self.assertTrue(callable(contains_any_texts))
        self.assertTrue(callable(contains_each_any_texts))
        self.assertTrue(callable(element_contains_texts))
        self.assertTrue(callable(fill_any_named))
        self.assertTrue(callable(visualization_contains_texts))


class _FakeField:
    def __init__(self, name: str, exists: bool):
        self.name = name
        self.exists = exists

    async def count(self):
        return 1 if self.exists else 0

    @property
    def first(self):
        return self

    async def fill(self, value: str):
        self.page.filled.append((self.name, value))


class _FakeFormPage:
    def __init__(self):
        self.filled = []

    def _field(self, name: str, exact: bool, source: str):
        field = _FakeField(f"{source}:{name}:{exact}", False)
        field.page = self
        if source == "placeholder" and exact and name == "输入名称":
            field.exists = True
        if source == "placeholder" and not exact and name == "名称":
            field.exists = True
        return field

    def get_by_label(self, name: str, *, exact: bool):
        return self._field(name, exact, "label")

    def get_by_placeholder(self, name: str, *, exact: bool):
        return self._field(name, exact, "placeholder")


class WebsiteCommonAsyncTest(unittest.IsolatedAsyncioTestCase):
    async def test_visual_capture_failure_is_reported_without_losing_runtime_checks(self) -> None:
        class Module:
            @staticmethod
            async def capture_visual(page, screenshot_dir):
                raise AssertionError("dialog blocked screenshot setup")

        manifest, errors = await capture_visual_evidence(Module, object(), Path("/tmp"))

        self.assertEqual(manifest, [])
        self.assertEqual(errors[0]["key"], "__visual_capture__")
        self.assertIn("dialog blocked screenshot setup", errors[0]["error"])

    async def test_fill_any_named_does_not_match_generic_search_placeholder_first(self) -> None:
        page = _FakeFormPage()

        await fill_any_named(page, ["名称", "输入名称"], "书店购书")

        self.assertEqual(
            page.filled,
            [("placeholder:输入名称:True", "书店购书")],
        )

    async def test_false_assertion_is_candidate_failure(self) -> None:
        page = AsyncMock()
        recorder = CheckRecorder(page, Path("/tmp"))

        async def check():
            return False

        await recorder.check("criterion", check)

        self.assertEqual(recorder.results["criterion"]["status"], "failed")
        self.assertEqual(recorder.results["criterion"]["score"], 0.0)
        self.assertEqual(evaluator_errors(recorder.results), [])

    async def test_checker_exception_is_evaluator_error(self) -> None:
        page = AsyncMock()
        recorder = CheckRecorder(page, Path("/tmp"))

        async def check():
            raise TypeError("missing required argument: name")

        await recorder.check("criterion", check)

        self.assertEqual(recorder.results["criterion"]["status"], "evaluator_error")
        self.assertIsNone(recorder.results["criterion"]["score"])
        self.assertEqual(evaluator_errors(recorder.results)[0]["key"], "criterion")

    async def test_timeout_is_a_candidate_checkpoint_failure(self) -> None:
        page = AsyncMock()
        recorder = CheckRecorder(page, Path("/tmp"))

        async def check():
            raise TimeoutError("locator timed out")

        await recorder.check("criterion", check)

        self.assertEqual(recorder.results["criterion"]["status"], "failed")
        self.assertEqual(recorder.results["criterion"]["score"], 0.0)
        self.assertEqual(evaluator_errors(recorder.results), [])


if __name__ == "__main__":
    unittest.main()
