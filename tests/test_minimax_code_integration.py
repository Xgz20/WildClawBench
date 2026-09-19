from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from eval import run_batch
from src.agents.minimax_code import MiniMaxCodeAgent
from src.utils.cli_args import build_run_batch_parser


class MiniMaxCodeCliTests(unittest.TestCase):
    def test_parser_accepts_backend_and_explicit_responses_api(self) -> None:
        parser = build_run_batch_parser("openrouter/test", 1)
        args = parser.parse_args(
            [
                "--task",
                "task.md",
                "--agent-backend",
                "minimax-code",
                "--mcode-api",
                "openai-responses",
            ]
        )

        self.assertEqual(args.agent_backend, "minimax-code")
        self.assertEqual(args.mcode_api, "openai-responses")

    def test_parser_accepts_anthropic_messages_and_rejects_unknown_api(self) -> None:
        parser = build_run_batch_parser("openrouter/test", 1)
        args = parser.parse_args(
            [
                "--task",
                "task.md",
                "--agent-backend",
                "minimax-code",
                "--mcode-api",
                "anthropic-messages",
            ]
        )
        self.assertEqual(args.mcode_api, "anthropic-messages")

        with self.assertRaises(SystemExit):
            parser.parse_args(
                [
                    "--task",
                    "task.md",
                    "--agent-backend",
                    "minimax-code",
                    "--mcode-api",
                    "openai-chat",
                ]
            )


class MiniMaxCodeRunBatchTests(unittest.TestCase):
    def test_backend_factory_forwards_selected_api(self) -> None:
        args = SimpleNamespace(
            agent_backend="minimax-code",
            mcode_api="openai-responses",
            dsh_api=None,
            openclaw_image_model=None,
        )
        sentinel = object()

        with patch.object(
            run_batch,
            "MiniMaxCodeAgent",
            return_value=sentinel,
        ) as constructor:
            backend = run_batch._build_agent_backend(args)

        self.assertIs(backend, sentinel)
        constructor.assert_called_once_with(api="openai-responses")

    def test_backend_is_registered_for_error_grading_and_workspace_collection(self) -> None:
        self.assertIn(MiniMaxCodeAgent, run_batch.GRADE_ON_ERROR_BACKENDS)
        self.assertIn(MiniMaxCodeAgent, run_batch.WORKSPACE_CHANGE_BACKENDS)


if __name__ == "__main__":
    unittest.main()
