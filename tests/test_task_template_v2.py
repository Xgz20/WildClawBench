from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = REPO_ROOT / "tasks" / "TASK_TEMPLATE_v2.md"


class TaskTemplateV2Test(unittest.TestCase):
    def test_optional_executable_sections_require_an_empty_body_when_unused(self) -> None:
        content = TEMPLATE.read_text(encoding="utf-8")

        for section in ("Automated Checks", "Skills", "Warmup"):
            with self.subTest(section=section):
                self.assertIn(
                    f"`## {section}` 不涉及时必须保留标题并将正文置空",
                    content,
                )

        self.assertIn("禁止填写 `无`、`N/A`、说明文字、注释或空代码块", content)


if __name__ == "__main__":
    unittest.main()
