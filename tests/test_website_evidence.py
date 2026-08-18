from __future__ import annotations

import unittest

from src.utils.website_evidence import build_website_evidence_code


class WebsiteEvidenceTest(unittest.TestCase):
    def test_generated_code_reads_framework_screenshots_with_limits(self) -> None:
        code = build_website_evidence_code("/tmp_workspace")
        self.assertIn('".grading" / "website"', code)
        self.assertIn('summary.json', code)
        self.assertIn('screenshots', code)
        self.assertIn("len(_web_manifest) >= 8", code)
        self.assertIn("_web_total_bytes + len(_data) > 12582912", code)
        self.assertIn("WEB_VISUAL_EVIDENCE_FAILED", code)

    def test_generated_code_builds_image_blocks_and_manifest(self) -> None:
        code = build_website_evidence_code("/tmp_workspace")
        self.assertIn("data:image/png;base64,", code)
        self.assertIn('"sha256"', code)
        self.assertIn('"size_bytes"', code)


if __name__ == "__main__":
    unittest.main()
