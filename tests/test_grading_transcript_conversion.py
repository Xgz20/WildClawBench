from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.agents.astroncode.runner import AstronCodeAgent
from src.agents.codex.runner import CodexAgent


class GradingTranscriptConversionTests(unittest.TestCase):
    def agents(self) -> tuple[AstronCodeAgent, CodexAgent]:
        return (
            AstronCodeAgent(
                openrouter_api_key="test-key",
                openrouter_base_url="https://openrouter.example/api/v1",
            ),
            CodexAgent(
                openrouter_api_key="test-key",
                openrouter_base_url="https://openrouter.example/api/v1",
            ),
        )

    def test_reasoning_stays_in_raw_session_but_not_grading_transcript(self) -> None:
        sensitive_reasoning = "internal-sensitive-reasoning"
        raw_events = [
            {
                "type": "response_item",
                "payload": {
                    "type": "reasoning",
                    "summary": [{"type": "summary_text", "text": sensitive_reasoning}],
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "safe final answer"}],
                },
            },
        ]

        for agent in self.agents():
            with self.subTest(agent=type(agent).__name__):
                with tempfile.TemporaryDirectory() as temp_dir:
                    source = Path(temp_dir) / "chat.jsonl"
                    grading = Path(temp_dir) / "chat_openclaw.jsonl"
                    source.write_text(
                        "\n".join(json.dumps(event) for event in raw_events) + "\n",
                        encoding="utf-8",
                    )

                    emitted = agent._translate_codex_to_openclaw(source, grading)

                    self.assertEqual(emitted, 1)
                    self.assertIn(
                        sensitive_reasoning, source.read_text(encoding="utf-8")
                    )
                    grading_text = grading.read_text(encoding="utf-8")
                    self.assertNotIn(sensitive_reasoning, grading_text)
                    self.assertIn("safe final answer", grading_text)


if __name__ == "__main__":
    unittest.main()
