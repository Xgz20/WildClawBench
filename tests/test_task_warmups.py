from __future__ import annotations

import unittest
from pathlib import Path

from src.utils.task_parser import parse_task_md


REPO_ROOT = Path(__file__).resolve().parents[1]
AGENT_BROWSER_WARMUP = (
    "command -v agent-browser >/dev/null 2>&1 || npm install -g agent-browser"
)


class TaskWarmupTest(unittest.TestCase):
    def test_agent_browser_install_is_skipped_when_preinstalled(self) -> None:
        task_files = [
            *REPO_ROOT.glob("tasks/[0-9][0-9]_*/[0-9][0-9]_*_task_*.md"),
            *REPO_ROOT.glob("tasks/cn/[0-9][0-9]_*/[0-9][0-9]_*_task_*.md"),
        ]
        unconditional: list[str] = []
        for path in task_files:
            warmup = parse_task_md(path).get("warmup", "")
            if "npm install -g agent-browser" in warmup and AGENT_BROWSER_WARMUP not in warmup:
                unconditional.append(str(path.relative_to(REPO_ROOT)))

        self.assertEqual(unconditional, [])


if __name__ == "__main__":
    unittest.main()
