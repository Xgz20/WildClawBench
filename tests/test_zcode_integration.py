from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from eval import run_batch
from src.agents.zcode import ZCodeAgent
from src.utils.cli_args import build_run_batch_parser


class ZCodeCliTests(unittest.TestCase):
    def test_parser_accepts_zcode_responses_api(self) -> None:
        parser = build_run_batch_parser("openrouter/test", 1)
        args = parser.parse_args([
            "--task", "task.md",
            "--agent-backend", "zcode",
            "--zcode-api", "openai-responses",
        ])
        self.assertEqual(args.agent_backend, "zcode")
        self.assertEqual(args.zcode_api, "openai-responses")

    def test_parser_accepts_fallback_protocols(self) -> None:
        parser = build_run_batch_parser("openrouter/test", 1)
        for api in ("openai-chat-completions", "anthropic-messages"):
            with self.subTest(api=api):
                args = parser.parse_args([
                    "--task", "task.md",
                    "--agent-backend", "zcode",
                    "--zcode-api", api,
                ])
                self.assertEqual(args.zcode_api, api)


class ZCodeRunBatchTests(unittest.TestCase):
    def test_backend_factory_forwards_selected_api(self) -> None:
        args = SimpleNamespace(
            agent_backend="zcode",
            zcode_api="openai-responses",
            mcode_api=None,
            dsh_api=None,
            openclaw_image_model=None,
        )
        sentinel = object()
        with patch.object(run_batch, "ZCodeAgent", return_value=sentinel) as constructor:
            backend = run_batch._build_agent_backend(args)
        self.assertIs(backend, sentinel)
        constructor.assert_called_once_with(api="openai-responses")

    def test_backend_is_registered_for_collection_and_error_grading(self) -> None:
        self.assertIn(ZCodeAgent, run_batch.GRADE_ON_ERROR_BACKENDS)
        self.assertIn(ZCodeAgent, run_batch.WORKSPACE_CHANGE_BACKENDS)


if __name__ == "__main__":
    unittest.main()
