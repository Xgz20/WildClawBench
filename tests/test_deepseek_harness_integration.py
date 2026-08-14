from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from eval import run_batch
from src.agents.deepseek_harness import DeepSeekHarnessAgent
from src.utils.cli_args import build_run_batch_parser


class DeepSeekHarnessCliTests(unittest.TestCase):
    def test_parser_accepts_backend_with_chat_default(self) -> None:
        parser = build_run_batch_parser("openrouter/test", 1)
        args = parser.parse_args(
            ["--task", "task.md", "--agent-backend", "deepseek-harness"]
        )

        self.assertEqual(args.agent_backend, "deepseek-harness")
        self.assertIsNone(args.dsh_api)

    def test_parser_accepts_explicit_responses_api(self) -> None:
        parser = build_run_batch_parser("openrouter/test", 1)
        args = parser.parse_args(
            [
                "--task",
                "task.md",
                "--agent-backend",
                "deepseek-harness",
                "--dsh-api",
                "openai-responses",
            ]
        )

        self.assertEqual(args.dsh_api, "openai-responses")

    def test_parser_rejects_unknown_dsh_api(self) -> None:
        parser = build_run_batch_parser("openrouter/test", 1)
        with self.assertRaises(SystemExit):
            parser.parse_args(
                [
                    "--task",
                    "task.md",
                    "--agent-backend",
                    "deepseek-harness",
                    "--dsh-api",
                    "openai-chat",
                ]
            )


class DeepSeekHarnessRunBatchTests(unittest.TestCase):
    def test_backend_factory_forwards_selected_api(self) -> None:
        args = SimpleNamespace(
            agent_backend="deepseek-harness",
            dsh_api="openai-responses",
            openclaw_image_model=None,
        )
        sentinel = object()

        with patch.object(
            run_batch,
            "DeepSeekHarnessAgent",
            return_value=sentinel,
        ) as constructor:
            backend = run_batch._build_agent_backend(args)

        self.assertIs(backend, sentinel)
        constructor.assert_called_once_with(api="openai-responses")

    def test_backend_is_registered_for_error_grading_and_workspace_collection(self) -> None:
        self.assertIn(DeepSeekHarnessAgent, run_batch.GRADE_ON_ERROR_BACKENDS)
        self.assertIn(DeepSeekHarnessAgent, run_batch.WORKSPACE_CHANGE_BACKENDS)


if __name__ == "__main__":
    unittest.main()
