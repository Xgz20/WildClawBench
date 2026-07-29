from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.agents.astronclaw import AstronClawAgent
from src.agents.openclaw import OpenClawAgent
from src.agents.openclaw.runner import write_execution_status
from src.utils.anomalies import classify_execution_error, scan_run_dir
from src.utils.cli_args import build_run_batch_parser


class OpenClawBackendTests(unittest.TestCase):
    def make_openclaw(self, **kwargs) -> OpenClawAgent:
        return OpenClawAgent(gateway_port=18789, **kwargs)

    def make_astronclaw(self, **kwargs) -> AstronClawAgent:
        return AstronClawAgent(gateway_port=18789, **kwargs)

    def test_cli_accepts_independent_astronclaw_backend(self) -> None:
        parser = build_run_batch_parser("openrouter/test", 1)
        args = parser.parse_args(["--task", "task.md", "--agent-backend", "astronclaw"])
        self.assertEqual(args.agent_backend, "astronclaw")

    def test_astronclaw_image_model_alias(self) -> None:
        parser = build_run_batch_parser("openrouter/test", 1)
        args = parser.parse_args([
            "--task", "task.md",
            "--astronclaw-image-model", "openrouter/image-model",
        ])
        self.assertEqual(args.openclaw_image_model, "openrouter/image-model")

    def test_backends_use_independent_default_images(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "DOCKER_IMAGE_ASTRONCLAW": "astronclaw:test",
                "OPENCLAW_IMAGE_MODEL": "",
            },
            clear=False,
        ):
            openclaw = self.make_openclaw(image="openclaw:test")
            astronclaw = self.make_astronclaw()
        self.assertEqual(openclaw.image, "openclaw:test")
        self.assertEqual(astronclaw.image, "astronclaw:test")

    def test_metadata_records_distinct_harness_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            openclaw = self.make_openclaw(image="openclaw:test")
            astronclaw = self.make_astronclaw(image="astronclaw:test")
            with patch.object(OpenClawAgent, "_probe_harness_version", return_value="1.2.3"):
                openclaw._write_harness_metadata("openclaw-task", root / "openclaw")
                astronclaw._write_harness_metadata("astronclaw-task", root / "astronclaw")

            openclaw_status = json.loads(
                (root / "openclaw" / "execution_status.json").read_text(encoding="utf-8")
            )
            astronclaw_status = json.loads(
                (root / "astronclaw" / "execution_status.json").read_text(encoding="utf-8")
            )
            self.assertEqual(openclaw_status["harness"], "openclaw")
            self.assertEqual(openclaw_status["image"], "openclaw:test")
            self.assertEqual(astronclaw_status["harness"], "astronclaw")
            self.assertEqual(astronclaw_status["image"], "astronclaw:test")

    @patch("src.agents.astronclaw.runner.subprocess.run")
    def test_gateway_mode_fix_is_astronclaw_only(self, run_mock) -> None:
        run_mock.return_value = subprocess.CompletedProcess([], 0, "", "")
        self.make_astronclaw()._configure_harness("astronclaw-task")
        run_mock.assert_called_once()
        self.assertIn("gateway.mode local", run_mock.call_args.args[0][-1])

    @patch("src.agents.openclaw.runner.subprocess.run")
    def test_openclaw_disables_web_search_without_brave_key(self, run_mock) -> None:
        run_mock.return_value = subprocess.CompletedProcess([], 0, "", "")
        with patch.dict("os.environ", {"BRAVE_API_KEY": ""}, clear=False):
            self.make_openclaw()._configure_harness("openclaw-task")

        run_mock.assert_called_once()
        configure_cmd = run_mock.call_args.args[0][-1]
        self.assertIn('search["enabled"] = False', configure_cmd)
        self.assertIn('search.pop("apiKey", None)', configure_cmd)

    @patch("src.agents.openclaw.runner.subprocess.run")
    def test_openclaw_keeps_web_search_with_brave_key(self, run_mock) -> None:
        with patch.dict(
            "os.environ", {"BRAVE_API_KEY": "configured-key"}, clear=False
        ):
            self.make_openclaw()._configure_harness("openclaw-task")

        run_mock.assert_not_called()

    @patch("src.agents.openclaw.runner.subprocess.run")
    def test_provider_timeout_is_astronclaw_only(self, run_mock) -> None:
        run_mock.return_value = subprocess.CompletedProcess([], 0, "", "")

        self.make_openclaw()._register_provider("openclaw-task", "openrouter/model", 900)
        openclaw_config = run_mock.call_args.args[0][-1]
        self.assertNotIn("timeoutSeconds", openclaw_config)

        self.make_astronclaw()._register_provider(
            "astronclaw-task", "openrouter/model", 900
        )
        astronclaw_config = run_mock.call_args.args[0][-1]
        self.assertIn('\\"timeoutSeconds\\": 900', astronclaw_config)

    def test_astronclaw_running_error_is_a_harness_outcome(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            write_execution_status(output_dir, status="astronclaw_running")
            status = write_execution_status(
                output_dir,
                status="error",
                error="AstronClaw run failed (rc=1)",
            )
        self.assertEqual(status["failure_stage"], "astronclaw_running")
        anomaly = classify_execution_error(status)
        self.assertEqual(anomaly["attribution"], "harness")
        self.assertEqual(anomaly["validity_impact"], "none")

    def test_astronclaw_preparation_error_is_a_framework_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            write_execution_status(output_dir, status="preparing_harness_input")
            status = write_execution_status(
                output_dir,
                status="error",
                error="Provider registration failed",
            )
        self.assertEqual(status["failure_stage"], "preparing_harness_input")
        anomaly = classify_execution_error(status)
        self.assertEqual(anomaly["attribution"], "evaluation_framework")
        self.assertEqual(anomaly["validity_impact"], "fail")

    def test_structured_astronclaw_model_error_is_review_not_validity_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            self.write_json(run_dir / "execution_status.json", {
                "status": "error",
                "error": "AstronClaw run failed (rc=1)",
                "failure_stage": "astronclaw_running",
                "model": "openrouter/xopglm52",
            })
            self.write_json(run_dir / "usage.json", {
                "request_count": 1,
                "total_tokens": 0,
            })
            self.write_json(run_dir / "score.json", {"overall_score": 0.0})
            (run_dir / "chat.jsonl").write_text(
                json.dumps({"message": {"role": "assistant", "content": "request failed"}})
                + "\n",
                encoding="utf-8",
            )
            (run_dir / "gateway.log").write_text(
                "[agent/embedded] embedded run agent end: runId=r1 isError=true "
                "model=xopglm52 provider=wildclaw error=401 invalid token "
                "rawError=401 invalid token\n",
                encoding="utf-8",
            )

            anomaly = scan_run_dir(run_dir)

        ids = {item["id"] for item in anomaly["items"]}
        self.assertIn("MODEL_API_ERROR", ids)
        self.assertNotIn("ZERO_TOKEN_RUN", ids)
        self.assertFalse(anomaly["has_validity_failure"])
        self.assertFalse(anomaly["needs_rerun"])
        self.assertEqual(anomaly["validity_verdict"], "REVIEW")

    @staticmethod
    def write_json(path: Path, value: dict) -> None:
        path.write_text(json.dumps(value), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
