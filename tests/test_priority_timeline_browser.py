from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from src.utils.task_parser import parse_task_md


ROOT = Path(__file__).resolve().parents[1]
TASK = (
    ROOT
    / "tasks/extension/05_Creative_Synthesis"
    / "05_Creative_Synthesis_task_008_accessible_timeline_microsite.md"
)
WORKSPACE = (
    ROOT
    / "workspace/extension/05_Creative_Synthesis"
    / "task_008_accessible_timeline_microsite"
)


class PriorityTimelineBrowserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise unittest.SkipTest("Playwright is only guaranteed in evaluation images")

        with sync_playwright() as playwright:
            if not Path(playwright.chromium.executable_path).is_file():
                raise unittest.SkipTest("Playwright Chromium is unavailable")

    def test_native_details_summary_passes_runtime_behavior(self) -> None:
        score = self._grade_html(self._native_html())

        self.assertEqual(score["single_file_offline"], 1.0)
        self.assertEqual(score["event_fidelity_order"], 1.0)
        self.assertEqual(score["keyboard_behavior"], 1.0)
        self.assertEqual(score["semantic_accessibility"], 1.0)
        self.assertEqual(score["runtime_integrity"], 1.0)
        self.assertEqual(score["overall_score"], 1.0)

    def test_runtime_generated_dom_passes_without_source_selectors(self) -> None:
        score = self._grade_html(self._runtime_html())

        self.assertEqual(score["event_fidelity_order"], 1.0)
        self.assertEqual(score["keyboard_behavior"], 1.0)
        self.assertEqual(score["semantic_accessibility"], 1.0)
        self.assertEqual(score["runtime_integrity"], 1.0)

    def test_runtime_checks_reject_keyboard_aria_and_overflow_failures(self) -> None:
        keyboard = self._grade_html(self._runtime_html(control_tag="div"))
        aria = self._grade_html(self._runtime_html(broken_aria=True))
        overflow = self._grade_html(self._runtime_html(force_overflow=True))

        self.assertEqual(keyboard["keyboard_behavior"], 0.5)
        self.assertEqual(aria["semantic_accessibility"], 0.8)
        self.assertEqual(overflow["runtime_integrity"], round(5 / 6, 6))

    def _expected(self) -> dict:
        return json.loads(
            (WORKSPACE / "gt/expected.json").read_text(encoding="utf-8")
        )

    def _native_html(self) -> str:
        expected = self._expected()
        events = "\n".join(
            "<details><summary>"
            f"<span>{event['id']}</span> "
            f"<time>{event['date']}</time> "
            f"<strong>{event['title']}</strong>"
            f"</summary><p>{event['description']}</p></details>"
            for event in expected["events"]
        )
        return self._document(events)

    def _runtime_html(
        self,
        *,
        control_tag: str = "button",
        broken_aria: bool = False,
        force_overflow: bool = False,
    ) -> str:
        events = json.dumps(self._expected()["events"], ensure_ascii=False)
        script = f"""
<script>
const events = {events};
const timeline = document.getElementById('timeline');
events.forEach((event, index) => {{
  const wrapper = document.createElement('section');
  const control = document.createElement('{control_tag}');
  const details = document.createElement('div');
  details.id = `details-${{index}}`;
  details.hidden = true;
  details.setAttribute('role', 'region');
  details.textContent = `${{event.id}} ${{event.description}}`;
  control.innerHTML = `<time>${{event.date}}</time> <strong>${{event.title}}</strong>`;
  control.setAttribute('aria-expanded', 'false');
  control.setAttribute('aria-controls', {"index === 0 ? 'missing-target' : details.id" if broken_aria else "details.id"});
  {"control.type = 'button';" if control_tag == "button" else "control.setAttribute('role', 'button'); control.tabIndex = 0;"}
  control.addEventListener('click', () => {{
    const expanded = control.getAttribute('aria-expanded') === 'true';
    control.setAttribute('aria-expanded', String(!expanded));
    details.hidden = expanded;
  }});
  wrapper.append(control, details);
  timeline.append(wrapper);
}});
</script>
"""
        extra_style = (
            "body { width: 900px; min-width: 900px; max-width: none; }"
            if force_overflow else ""
        )
        return self._document('<div id="timeline"></div>', script, extra_style)

    def _document(self, events: str, script: str = "", extra_style: str = "") -> str:
        return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Product history</title>
  <style>
    * {{ box-sizing: border-box; }}
    html, body {{ margin: 0; max-width: 100%; overflow-x: hidden; }}
    body {{ font-family: sans-serif; }}
    main {{ margin: 0 auto; max-width: 40rem; padding: 1rem; }}
    details, summary, section, button, [role="button"], p {{
      display: block; max-width: 100%; overflow-wrap: anywhere;
    }}
    summary, button, [role="button"] {{ cursor: pointer; padding: .75rem; }}
    summary:focus-visible, button:focus-visible, [role="button"]:focus-visible {{
      outline: 3px solid black; outline-offset: 2px;
    }}
    {extra_style}
  </style>
</head>
<body>
  <main>
    <h1>Product history</h1>
    <p>Six milestones from prototype to community archive.</p>
    {events}
  </main>
  {script}
</body>
</html>
"""

    def _grade_html(self, html: str) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "gt").mkdir()
            (root / "results").mkdir()
            shutil.copy2(WORKSPACE / "gt/expected.json", root / "gt/expected.json")
            for source in (WORKSPACE / "exec").iterdir():
                if source.is_file():
                    shutil.copy2(source, root / source.name)
            (root / "results/index.html").write_text(html, encoding="utf-8")

            namespace: dict = {}
            exec(parse_task_md(TASK)["automated_checks"], namespace)
            return namespace["grade"](workspace_path=str(root))


if __name__ == "__main__":
    unittest.main()
