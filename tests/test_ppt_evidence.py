from __future__ import annotations

import unittest

from src.utils.ppt_evidence import build_ppt_evidence_code


class PptEvidenceTest(unittest.TestCase):
    def test_generated_code_discovers_and_renders_pptx_in_stable_order(self) -> None:
        code = build_ppt_evidence_code("/tmp_workspace")
        self.assertIn('_ppt_ws / "results"', code)
        self.assertIn("rglob('*.pptx')", code)
        self.assertIn("soffice", code)
        self.assertIn("fitz", code)
        self.assertIn("rendered", code)
        self.assertIn("PPT_RENDER_FAILED", code)
        self.assertIn("len(_ppt_manifest) >= 60", code)
        self.assertIn("_ppt_total_bytes + len(_data) > 18874368", code)

    def test_generated_code_builds_image_url_blocks(self) -> None:
        code = build_ppt_evidence_code("/tmp_workspace")
        self.assertIn("image_url", code)
        self.assertIn("data:image/png;base64,", code)
        self.assertIn("slide", code)
        self.assertIn("sha256", code)
        self.assertIn("mime_type", code)


if __name__ == "__main__":
    unittest.main()
