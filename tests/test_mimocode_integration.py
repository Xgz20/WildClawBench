from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.utils.cli_args import build_run_batch_parser


class MiMoCodeIntegrationTests(unittest.TestCase):
    def test_native_model_error_is_visible_to_anomaly_scan(self):
        from src.utils.anomalies import scan_run_dir

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "mimocode_trace.jsonl").write_text(
                json.dumps(
                    {
                        "type": "error",
                        "sessionID": "session-1",
                        "error": {
                            "name": "APIError",
                            "data": {
                                "statusCode": 429,
                                "message": "HTTP 429 too many requests",
                            },
                        },
                    }
                )
                + "\n"
            )
            report = scan_run_dir(root)
            self.assertIn(
                "MODEL_API_RATE_LIMIT", [item["id"] for item in report["items"]]
            )

    def test_backend_factory_and_error_grading_workspace_collection(self):
        from eval import run_batch
        from src.agents.mimocode import MiMoCodeAgent

        with patch("eval.run_batch.MiMoCodeAgent") as backend:
            run_batch._build_agent_backend(
                SimpleNamespace(
                    agent_backend="mimocode", mimocode_api="anthropic-messages"
                )
            )
        backend.assert_called_once_with(api="anthropic-messages")
        self.assertIn(MiMoCodeAgent, run_batch.GRADE_ON_ERROR_BACKENDS)
        self.assertIn(MiMoCodeAgent, run_batch.WORKSPACE_CHANGE_BACKENDS)

    def test_parser_accepts_responses_api(self) -> None:
        parser = build_run_batch_parser("xopglm52", 1)
        args = parser.parse_args(
            [
                "--task",
                "task.md",
                "--agent-backend",
                "mimocode",
                "--mimocode-api",
                "openai-responses",
            ]
        )
        self.assertEqual(args.agent_backend, "mimocode")
        self.assertEqual(args.mimocode_api, "openai-responses")

    def test_parser_accepts_all_protocols_and_alias(self) -> None:
        parser = build_run_batch_parser("xopglm52", 1)
        for api in (
            "openai-responses",
            "openai-chat-completions",
            "anthropic-messages",
        ):
            args = parser.parse_args(
                ["--task", "task.md", "--agent-backend", "mimocode", "--mimo-api", api]
            )
            self.assertEqual(args.mimocode_api, api)


if __name__ == "__main__":
    unittest.main()
