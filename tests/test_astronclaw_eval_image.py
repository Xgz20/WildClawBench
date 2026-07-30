from __future__ import annotations

import unittest
from pathlib import Path


DOCKERFILE = Path(__file__).resolve().parents[1] / "docker/astronclaw/Dockerfile"


class AstronClawEvalImageTest(unittest.TestCase):
    def test_image_layers_eval_runtime_on_astronclaw(self) -> None:
        text = DOCKERFILE.read_text(encoding="utf-8")

        self.assertIn("AS eval-base", text)
        self.assertIn("astronclaw-core-cicd:v0.2.9", text)
        self.assertIn(
            "COPY --from=eval-base /root/miniconda3/envs/eval /root/miniconda3/envs/eval",
            text,
        )
        self.assertIn('PATH="/root/miniconda3/envs/eval/bin:', text)

    def test_image_preinstalls_batch_dependencies(self) -> None:
        text = DOCKERFILE.read_text(encoding="utf-8")

        for dependency in (
            "numpy==1.26.4",
            "opencv-python==4.9.0.80",
            "ortools==9.10.4067",
            "playwright install chromium",
            "ffmpeg",
            "agent-browser",
        ):
            self.assertIn(dependency, text)
        self.assertIn("PLAYWRIGHT_HOST_PLATFORM_OVERRIDE=ubuntu24.04-x64", text)

    def test_image_has_build_time_smoke_check(self) -> None:
        text = DOCKERFILE.read_text(encoding="utf-8")

        self.assertIn("import PIL, cv2, numpy, playwright", text)
        self.assertIn("sync_playwright", text)
        self.assertIn("chromium.executable_path", text)
        self.assertNotIn("chromium-*/chrome-linux/chrome", text)
        self.assertIn("openclaw --version", text)


if __name__ == "__main__":
    unittest.main()
