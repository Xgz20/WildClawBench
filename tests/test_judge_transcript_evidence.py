from __future__ import annotations

import json
import unittest

from src.utils.transcript_loader import build_judge_evidence


def message(role: str, text: str) -> dict:
    return {
        "type": "message",
        "message": {
            "role": role,
            "content": [{"type": "text", "text": text}],
        },
    }


def tool_call(name: str, status: str) -> dict:
    return {
        "type": "message",
        "message": {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "name": name, "id": f"call-{name}"},
                {
                    "type": "tool_result",
                    "tool_use_id": f"call-{name}",
                    "status": status,
                    "content": "y" * 3000,
                },
            ],
        },
    }


class JudgeTranscriptEvidenceTest(unittest.TestCase):
    def test_short_transcript_is_sent_unchanged(self) -> None:
        transcript = [
            message("user", "task prompt"),
            message("assistant", "final answer"),
        ]

        evidence = build_judge_evidence(transcript, max_chars=80000)

        expected = json.dumps(transcript, ensure_ascii=False)
        self.assertEqual(evidence["text"], expected)
        self.assertEqual(evidence["metadata"]["original_chars"], len(expected))
        self.assertEqual(evidence["metadata"]["included_chars"], len(expected))
        self.assertFalse(evidence["metadata"]["compacted"])
        self.assertEqual(evidence["metadata"]["omitted_event_count"], 0)
        self.assertEqual(evidence["metadata"]["truncated_event_count"], 0)
        self.assertTrue(evidence["metadata"]["final_answer_included"])
        self.assertFalse(evidence["metadata"]["final_answer_truncated"])

    def test_long_transcript_keeps_prompt_and_final_answer(self) -> None:
        transcript = [
            message("user", "unique-task-prompt"),
            tool_call("early-source-fetch", "failed"),
        ]
        transcript.extend(
            message("assistant", f"intermediate-{index}-" + "x" * 1200)
            for index in range(20)
        )
        transcript.append(message("assistant", "unique-final-answer"))

        evidence = build_judge_evidence(transcript, max_chars=4000)

        self.assertLessEqual(len(evidence["text"]), 4000)
        self.assertIn("unique-task-prompt", evidence["text"])
        self.assertIn("unique-final-answer", evidence["text"])
        self.assertIn("early-source-fetch", evidence["text"])
        self.assertIn("failed", evidence["text"])
        self.assertTrue(evidence["metadata"]["compacted"])
        self.assertGreater(
            evidence["metadata"]["omitted_event_count"]
            + evidence["metadata"]["truncated_event_count"],
            0,
        )
        self.assertTrue(evidence["metadata"]["final_answer_included"])
        self.assertFalse(evidence["metadata"]["final_answer_truncated"])

    def test_oversized_final_answer_keeps_head_and_tail_with_audit_flag(self) -> None:
        final_answer = "final-answer-head-" + "z" * 6000 + "-final-answer-tail"
        transcript = [
            message("user", "task prompt"),
            message("assistant", final_answer),
        ]

        evidence = build_judge_evidence(transcript, max_chars=2200)

        self.assertLessEqual(len(evidence["text"]), 2200)
        self.assertIn("final-answer-head", evidence["text"])
        self.assertIn("final-answer-tail", evidence["text"])
        self.assertTrue(evidence["metadata"]["final_answer_included"])
        self.assertTrue(evidence["metadata"]["final_answer_truncated"])


if __name__ == "__main__":
    unittest.main()
