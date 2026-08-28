from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.agents.claudecode.transcript import convert_claudecode_chat_to_openclaw_jsonl


class ClaudeCodeTranscriptTests(unittest.TestCase):
    def convert(self, rows: list[dict]) -> list[dict]:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "chat.json"
            output = root / "chat.jsonl"
            source.write_text(
                "\n".join(json.dumps(row) for row in rows) + "\n",
                encoding="utf-8",
            )

            count = convert_claudecode_chat_to_openclaw_jsonl(source, output)
            converted = [
                json.loads(line)
                for line in output.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertEqual(count, len(converted))
        return converted

    @staticmethod
    def wrapped_message(
        role: str,
        content: str | list[dict],
        *,
        message_id: str | None = None,
    ) -> dict:
        message: dict = {"role": role, "content": content}
        if message_id:
            message["id"] = message_id
        return {"type": role, "uuid": f"wrapper-{message_id or role}", "message": message}

    def test_last_model_request_restores_context_and_appends_final_assistant(self) -> None:
        rows = [
            {
                "event": "model_request",
                "payload": {
                    "messages": [self.wrapped_message("user", "stale request")],
                },
            },
            {
                "event": "model_request",
                "payload": {
                    "messages": [
                        self.wrapped_message("user", "run the task", message_id="user-1"),
                        self.wrapped_message(
                            "assistant",
                            [
                                {
                                    "type": "tool_use",
                                    "id": "call-1",
                                    "name": "Bash",
                                    "input": {"command": "pwd"},
                                }
                            ],
                            message_id="assistant-tool-1",
                        ),
                        self.wrapped_message(
                            "user",
                            [
                                {
                                    "type": "tool_result",
                                    "tool_use_id": "call-1",
                                    "content": "/tmp_workspace",
                                    "is_error": False,
                                }
                            ],
                            message_id="tool-result-1",
                        ),
                        {"type": "attachment", "attachment": {"filePath": "ignored.png"}},
                    ],
                },
            },
            {
                "event": "query_yield",
                "payload": {
                    "message": self.wrapped_message(
                        "assistant",
                        [{"type": "text", "text": "task complete"}],
                        message_id="assistant-final",
                    )
                },
            },
        ]

        converted = self.convert(rows)

        self.assertEqual([row["message"]["role"] for row in converted], [
            "user",
            "assistant",
            "user",
            "assistant",
        ])
        self.assertEqual(converted[0]["message"]["content"][0]["text"], "run the task")
        self.assertEqual(converted[-1]["message"]["content"][0]["text"], "task complete")
        tool_use = converted[1]["message"]["content"][0]
        tool_result = converted[2]["message"]["content"][0]
        self.assertEqual(tool_use["id"], "call-1")
        self.assertEqual(tool_result["tool_use_id"], "call-1")
        self.assertFalse(tool_result["is_error"])

    def test_official_stream_json_preserves_user_tool_flow(self) -> None:
        rows = [
            {
                "type": "system",
                "subtype": "init",
                "claude_code_version": "2.1.250",
            },
            self.wrapped_message("user", "run the task", message_id="user-1"),
            self.wrapped_message(
                "assistant",
                [
                    {
                        "type": "tool_use",
                        "id": "call-1",
                        "name": "Bash",
                        "input": {"command": "pwd"},
                    }
                ],
                message_id="assistant-1",
            ),
            self.wrapped_message(
                "user",
                [
                    {
                        "type": "tool_result",
                        "tool_use_id": "call-1",
                        "content": "/tmp_workspace",
                        "is_error": False,
                    }
                ],
                message_id="tool-result-1",
            ),
            self.wrapped_message(
                "assistant",
                [{"type": "text", "text": "Done."}],
                message_id="assistant-2",
            ),
            {
                "type": "result",
                "subtype": "success",
                "num_turns": 2,
                "usage": {"input_tokens": 20, "output_tokens": 5},
            },
        ]

        converted = self.convert(rows)

        self.assertEqual(
            [row["message"]["role"] for row in converted],
            ["user", "assistant", "user", "assistant"],
        )
        self.assertEqual(converted[1]["message"]["content"][0]["id"], "call-1")
        self.assertEqual(
            converted[2]["message"]["content"][0]["tool_use_id"],
            "call-1",
        )
        self.assertEqual(converted[-1]["message"]["content"][0]["text"], "Done.")

    def test_claude_fragments_merge_by_message_id_without_empty_thinking_message(self) -> None:
        rows = [
            {
                "event": "model_request",
                "payload": {
                    "messages": [
                        self.wrapped_message("user", "run the task", message_id="user-1"),
                        self.wrapped_message(
                            "assistant",
                            [{"type": "thinking", "thinking": "private reasoning"}],
                            message_id="assistant-1",
                        ),
                        self.wrapped_message(
                            "assistant",
                            [{"type": "text", "text": "Checking the workspace."}],
                            message_id="assistant-1",
                        ),
                        {
                            "type": "assistant",
                            "message": {
                                "role": "assistant",
                                "id": "assistant-1",
                                "content": [
                                    {
                                        "type": "tool_use",
                                        "id": "call-1",
                                        "name": "Bash",
                                        "input": {"command": "pwd"},
                                    }
                                ],
                                "stop_reason": "tool_use",
                                "usage": {"input_tokens": 10, "output_tokens": 5},
                            },
                        },
                        self.wrapped_message(
                            "user",
                            [
                                {
                                    "type": "tool_result",
                                    "tool_use_id": "call-1",
                                    "content": "/tmp_workspace",
                                }
                            ],
                            message_id="tool-result-1",
                        ),
                    ]
                },
            },
            {
                "event": "query_yield",
                "payload": {
                    "message": self.wrapped_message(
                        "assistant",
                        [{"type": "text", "text": "Done."}],
                        message_id="assistant-final",
                    )
                },
            },
        ]

        converted = self.convert(rows)

        self.assertEqual(
            [row["message"]["role"] for row in converted],
            ["user", "assistant", "user", "assistant"],
        )
        merged = converted[1]["message"]
        self.assertEqual(merged["id"], "assistant-1")
        self.assertEqual(
            [block["type"] for block in merged["content"]],
            ["text", "tool_use"],
        )
        self.assertEqual(merged["content"][1]["id"], "call-1")
        self.assertEqual(merged["stop_reason"], "tool_use")
        self.assertEqual(merged["usage"]["output"], 5)
        self.assertFalse(any(not row["message"]["content"] for row in converted))

    def test_maas_multi_tool_fragments_merge_without_losing_tool_ids(self) -> None:
        rows = [
            {
                "event": "model_request",
                "payload": {
                    "messages": [
                        self.wrapped_message("user", "run the task", message_id="user-1"),
                        self.wrapped_message(
                            "assistant",
                            [{"type": "text", "text": "I will inspect both files."}],
                            message_id="assistant-1",
                        ),
                        self.wrapped_message(
                            "assistant",
                            [
                                {
                                    "type": "tool_use",
                                    "id": "call-1",
                                    "name": "Read",
                                    "input": {"path": "one.txt"},
                                }
                            ],
                            message_id="assistant-1",
                        ),
                        self.wrapped_message(
                            "assistant",
                            [
                                {
                                    "type": "tool_use",
                                    "id": "call-2",
                                    "name": "Read",
                                    "input": {"path": "two.txt"},
                                }
                            ],
                            message_id="assistant-1",
                        ),
                        self.wrapped_message(
                            "user",
                            [
                                {
                                    "type": "tool_result",
                                    "tool_use_id": "call-1",
                                    "content": "one",
                                },
                                {
                                    "type": "tool_result",
                                    "tool_use_id": "call-2",
                                    "content": "two",
                                },
                            ],
                            message_id="tool-results-1",
                        ),
                    ]
                },
            }
        ]

        converted = self.convert(rows)

        self.assertEqual(len(converted), 3)
        merged = converted[1]["message"]
        self.assertEqual(
            [block["type"] for block in merged["content"]],
            ["text", "tool_use", "tool_use"],
        )
        self.assertEqual(
            [block["id"] for block in merged["content"] if block["type"] == "tool_use"],
            ["call-1", "call-2"],
        )
        result_ids = [
            block["tool_use_id"]
            for block in converted[2]["message"]["content"]
            if block["type"] == "tool_result"
        ]
        self.assertEqual(result_ids, ["call-1", "call-2"])

    def test_same_assistant_id_across_user_boundary_keeps_message_order(self) -> None:
        rows = [
            {
                "event": "model_request",
                "payload": {
                    "messages": [
                        self.wrapped_message("user", "task", message_id="user-1"),
                        self.wrapped_message(
                            "assistant",
                            [{"type": "text", "text": "before"}],
                            message_id="assistant-reused",
                        ),
                        self.wrapped_message("user", "follow-up", message_id="user-2"),
                        self.wrapped_message(
                            "assistant",
                            [{"type": "text", "text": "after"}],
                            message_id="assistant-reused",
                        ),
                    ]
                },
            }
        ]

        converted = self.convert(rows)

        self.assertEqual(
            [row["message"]["role"] for row in converted],
            ["user", "assistant", "user", "assistant"],
        )
        self.assertEqual(converted[1]["message"]["content"][0]["text"], "before")
        self.assertEqual(converted[3]["message"]["content"][0]["text"], "after")

    def test_final_assistant_snapshot_is_not_duplicated(self) -> None:
        final_message = self.wrapped_message(
            "assistant",
            [{"type": "text", "text": "done"}],
            message_id="assistant-final",
        )
        rows = [
            {
                "event": "model_request",
                "payload": {
                    "messages": [
                        self.wrapped_message("user", "task"),
                        final_message,
                    ]
                },
            },
            {"event": "query_yield", "payload": {"message": final_message}},
        ]

        converted = self.convert(rows)

        self.assertEqual(len(converted), 2)
        self.assertEqual(converted[-1]["message"]["id"], "assistant-final")

    def test_same_content_with_different_message_ids_is_preserved(self) -> None:
        rows = [
            {
                "event": "model_request",
                "payload": {
                    "messages": [
                        self.wrapped_message("user", "task"),
                        self.wrapped_message(
                            "assistant",
                            [{"type": "text", "text": "same answer"}],
                            message_id="assistant-earlier",
                        ),
                    ]
                },
            },
            {
                "event": "query_yield",
                "payload": {
                    "message": self.wrapped_message(
                        "assistant",
                        [{"type": "text", "text": "same answer"}],
                        message_id="assistant-final",
                    )
                },
            },
        ]

        converted = self.convert(rows)

        self.assertEqual(len(converted), 3)
        self.assertEqual(
            [row["message"].get("id") for row in converted[1:]],
            ["assistant-earlier", "assistant-final"],
        )

    def test_stream_events_remain_a_compatible_fallback(self) -> None:
        rows = [
            {
                "event": "query_yield",
                "payload": {
                    "message": {
                        "type": "stream_event",
                        "event": {
                            "type": "message_start",
                            "message": {"role": "assistant"},
                        },
                    }
                },
            },
            {
                "event": "query_yield",
                "payload": {
                    "message": {
                        "type": "stream_event",
                        "event": {
                            "type": "content_block_start",
                            "index": 0,
                            "content_block": {
                                "type": "tool_use",
                                "id": "call-fallback",
                                "name": "Bash",
                                "input": {"command": "pwd"},
                            },
                        },
                    }
                },
            },
            {
                "event": "query_yield",
                "payload": {
                    "message": {
                        "type": "stream_event",
                        "event": {"type": "message_stop"},
                    }
                },
            },
        ]

        converted = self.convert(rows)

        self.assertEqual(len(converted), 1)
        self.assertEqual(
            converted[0]["message"]["content"][0]["id"],
            "call-fallback",
        )


if __name__ == "__main__":
    unittest.main()
