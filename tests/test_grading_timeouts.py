from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from src.utils import grading, judge_shim


class GradingTimeoutTest(unittest.TestCase):
    def test_grading_timeout_defaults_to_600_seconds(self) -> None:
        with patch.dict(os.environ, {"WILDCLAW_GRADING_TIMEOUT_SECONDS": ""}):
            self.assertEqual(grading._grading_timeout_seconds(), 600.0)

    def test_grading_timeout_is_configurable_and_invalid_values_fall_back(self) -> None:
        with patch.dict(os.environ, {"WILDCLAW_GRADING_TIMEOUT_SECONDS": "725"}):
            self.assertEqual(grading._grading_timeout_seconds(), 725.0)
        for value in ("invalid", "0", "-1"):
            with self.subTest(value=value), patch.dict(
                os.environ, {"WILDCLAW_GRADING_TIMEOUT_SECONDS": value}
            ):
                self.assertEqual(grading._grading_timeout_seconds(), 600.0)

    @patch("src.utils.grading.subprocess.run")
    def test_all_container_grading_runners_use_configured_timeout(
        self, run: Mock
    ) -> None:
        run.return_value = Mock(returncode=0, stdout='{"overall_score": 1.0}', stderr="")
        with tempfile.TemporaryDirectory() as temp, patch.dict(
            os.environ, {"WILDCLAW_GRADING_TIMEOUT_SECONDS": "725"}
        ):
            output_dir = Path(temp)
            grading._run_grading_legacy(
                "task", "def grade(**kwargs): return {'overall_score': 1.0}", output_dir
            )
            grading._exec_container_grade(
                "task",
                "def grade(**kwargs): return {'overall_score': 1.0}",
                "",
                None,
                "",
            )
            grading._exec_container_python("task", "print('{}')", "")

        timeouts = [
            call.kwargs["timeout"]
            for call in run.call_args_list
            if (
                "timeout" in call.kwargs
                and call.args
                and call.args[0][:2] == ["docker", "exec"]
                and "python3" in call.args[0]
            )
        ]
        self.assertEqual(timeouts, [725.0, 725.0, 725.0])

    def test_judge_timeout_defaults_to_300_seconds(self) -> None:
        with patch.dict(os.environ, {"WILDCLAW_JUDGE_TIMEOUT_SECONDS": ""}):
            client = judge_shim.OpenAI(api_key="test", base_url="https://example.test")
        self.assertEqual(client._timeout, 300.0)
        self.assertEqual(client._init_kwargs["timeout"], 300.0)

    def test_judge_timeout_is_configurable_and_explicit_value_wins(self) -> None:
        with patch.dict(os.environ, {"WILDCLAW_JUDGE_TIMEOUT_SECONDS": "345"}):
            configured = judge_shim.OpenAI()
            explicit = judge_shim.OpenAI(timeout=12)
        self.assertEqual(configured._timeout, 345.0)
        self.assertEqual(explicit._timeout, 12)

    @patch("src.utils.judge_shim.request.urlopen")
    def test_anthropic_request_uses_configured_judge_timeout(self, urlopen: Mock) -> None:
        response = Mock()
        response.read.return_value = (
            b'{"content":[{"type":"text","text":"ok"}],"usage":{}}'
        )
        urlopen.return_value.__enter__.return_value = response
        with patch.dict(os.environ, {
            "ANTHROPIC_API_KEY": "test",
            "ANTHROPIC_BASE_URL": "https://example.test",
            "WILDCLAW_JUDGE_TIMEOUT_SECONDS": "345",
        }):
            judge_shim._anthropic_create(
                model="anthropic/test", messages=[{"role": "user", "content": "test"}]
            )
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 345.0)

    def test_judge_timeout_is_injected_into_grading_container(self) -> None:
        with patch.dict(os.environ, {"WILDCLAW_JUDGE_TIMEOUT_SECONDS": "345"}):
            args = grading._build_grading_env_args("task", "", None)
        self.assertIn("WILDCLAW_JUDGE_TIMEOUT_SECONDS=345", args)


if __name__ == "__main__":
    unittest.main()
