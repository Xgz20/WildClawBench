from __future__ import annotations

import unittest
from pathlib import Path


class AstronCodePptImageTest(unittest.TestCase):
    def test_v4_image_declares_ppt_rendering_dependencies_and_build_gate(self) -> None:
        dockerfile = (
            Path(__file__).resolve().parents[1]
            / "docker/astroncode/v4/Dockerfile"
        ).read_text(encoding="utf-8")

        self.assertIn("libreoffice-impress", dockerfile)
        self.assertIn("command -v soffice", dockerfile)
        self.assertIn("soffice --version", dockerfile)
        self.assertIn("import fitz", dockerfile)


if __name__ == "__main__":
    unittest.main()
