"""Opt-in real Docker CLI checks against synthetic, local-only model servers.

WCB_MIMOCODE_DOCKER_TESTS=1 python -m unittest tests.test_mimocode_wire -v
No real credentials or model requests are used.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ARGS = json.dumps({"command": "printf WCB_WIRE_OK", "description": "wire smoke"})


def response_events(tool: bool):
    item = (
        {
            "type": "function_call",
            "id": "fc_probe",
            "call_id": "call_probe",
            "name": "bash",
            "arguments": ARGS,
            "status": "completed",
        }
        if tool
        else {
            "type": "message",
            "id": "msg_probe",
            "role": "assistant",
            "status": "completed",
            "content": [
                {"type": "output_text", "text": "WCB_FINAL_OK", "annotations": []}
            ],
        }
    )
    response = {
        "id": "resp_probe",
        "object": "response",
        "created_at": 1700000000,
        "model": "test-model",
        "status": "completed",
        "output": [item],
        "usage": {
            "input_tokens": 100,
            "output_tokens": 10,
            "total_tokens": 110,
            "input_tokens_details": {"cached_tokens": 20},
            "output_tokens_details": {"reasoning_tokens": 2},
        },
    }
    events = [
        {
            "type": "response.created",
            "response": {**response, "status": "in_progress", "output": []},
        }
    ]
    events.append(
        {
            "type": "response.output_item.added",
            "output_index": 0,
            "item": {**item, "arguments": "", "content": []},
        }
    )
    if tool:
        events.append(
            {
                "type": "response.function_call_arguments.delta",
                "output_index": 0,
                "item_id": "fc_probe",
                "delta": ARGS,
            }
        )
        events.append(
            {
                "type": "response.function_call_arguments.done",
                "output_index": 0,
                "item_id": "fc_probe",
                "arguments": ARGS,
            }
        )
    else:
        events.append(
            {
                "type": "response.output_text.delta",
                "output_index": 0,
                "content_index": 0,
                "item_id": "msg_probe",
                "delta": "WCB_FINAL_OK",
            }
        )
    events.extend(
        [
            {"type": "response.output_item.done", "output_index": 0, "item": item},
            {"type": "response.completed", "response": response},
        ]
    )
    return response, events


def chat_events(tool: bool):
    delta = (
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "index": 0,
                    "id": "call_probe",
                    "type": "function",
                    "function": {"name": "bash", "arguments": ARGS},
                }
            ],
        }
        if tool
        else {"role": "assistant", "content": "WCB_FINAL_OK"}
    )
    base = {
        "id": "chatcmpl_probe",
        "object": "chat.completion.chunk",
        "created": 1700000000,
        "model": "test-model",
    }
    usage = {
        "prompt_tokens": 100,
        "completion_tokens": 10,
        "total_tokens": 110,
        "prompt_tokens_details": {"cached_tokens": 20},
        "completion_tokens_details": {"reasoning_tokens": 2},
    }
    events = [
        {**base, "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
        {
            **base,
            "choices": [
                {
                    "index": 0,
                    "delta": {},
                    "finish_reason": "tool_calls" if tool else "stop",
                }
            ],
            "usage": usage,
        },
    ]
    return {
        **base,
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": delta,
                "finish_reason": "tool_calls" if tool else "stop",
            }
        ],
        "usage": usage,
    }, events


def anthropic_events(tool: bool):
    block = (
        {"type": "tool_use", "id": "call_probe", "name": "bash", "input": {}}
        if tool
        else {"type": "text", "text": ""}
    )
    message = {
        "id": "msg_probe",
        "type": "message",
        "role": "assistant",
        "model": "test-model",
        "content": [],
        "stop_reason": None,
        "usage": {
            "input_tokens": 80,
            "output_tokens": 0,
            "cache_read_input_tokens": 20,
            "cache_creation_input_tokens": 0,
        },
    }
    events = [
        {"type": "message_start", "message": message},
        {"type": "content_block_start", "index": 0, "content_block": block},
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "input_json_delta", "partial_json": ARGS}
            if tool
            else {"type": "text_delta", "text": "WCB_FINAL_OK"},
        },
        {"type": "content_block_stop", "index": 0},
        {
            "type": "message_delta",
            "delta": {
                "stop_reason": "tool_use" if tool else "end_turn",
                "stop_sequence": None,
            },
            "usage": {"output_tokens": 10},
        },
        {"type": "message_stop"},
    ]
    final = {
        **message,
        "content": [
            {**block, "input": json.loads(ARGS)}
            if tool
            else {"type": "text", "text": "WCB_FINAL_OK"}
        ],
        "stop_reason": "tool_use" if tool else "end_turn",
    }
    return final, events


@unittest.skipUnless(
    os.environ.get("WCB_MIMOCODE_DOCKER_TESTS") == "1",
    "requires built MiMoCode image and Docker",
)
class MiMoCodeWireTests(unittest.TestCase):
    def test_three_protocols_execute_tool_and_complete(self):
        for api, endpoint, factory in (
            ("openai-responses", "/v1/responses", response_events),
            ("openai-chat-completions", "/v1/chat/completions", chat_events),
            ("anthropic-messages", "/v1/messages", anthropic_events),
        ):
            with self.subTest(api=api):
                requests = []

                class Handler(BaseHTTPRequestHandler):
                    def log_message(self, *_args):
                        pass

                    def do_POST(self):
                        data = json.loads(
                            self.rfile.read(int(self.headers["Content-Length"]))
                        )
                        requests.append((self.path, data))
                        history = json.dumps(
                            data.get("input", data.get("messages", []))
                        )
                        tool = bool(
                            data.get("tools")
                        ) and "WCB_WIRE_OK" not in history.replace(
                            "printf WCB_WIRE_OK", ""
                        )
                        final, events = factory(tool)
                        self.send_response(200)
                        self.send_header(
                            "Content-Type",
                            "text/event-stream"
                            if data.get("stream")
                            else "application/json",
                        )
                        self.end_headers()
                        if data.get("stream"):
                            for event in events:
                                name = (
                                    f"event: {event['type']}\n"
                                    if "type" in event
                                    else ""
                                )
                                self.wfile.write(
                                    (
                                        name + "data: " + json.dumps(event) + "\n\n"
                                    ).encode()
                                )
                            if api == "openai-chat-completions":
                                self.wfile.write(b"data: [DONE]\n\n")
                        else:
                            self.wfile.write(json.dumps(final).encode())

                server = ThreadingHTTPServer(("0.0.0.0", 0), Handler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    result = subprocess.run(
                        [
                            "docker",
                            "run",
                            "--rm",
                            "--add-host",
                            "host.docker.internal:host-gateway",
                            "-e",
                            "MIMOCODE_MODEL_ID=test-model",
                            "-e",
                            f"MIMOCODE_API={api}",
                            "-e",
                            "MIMOCODE_TIMEOUT_SECONDS=60",
                            "-e",
                            "OPENROUTER_API_KEY=test-key",
                            "-e",
                            f"OPENROUTER_BASE_URL=http://host.docker.internal:{server.server_port}/v1",
                            os.environ.get(
                                "DOCKER_IMAGE_MIMOCODE",
                                "wildclawbench-mimocode-ubuntu:v0.1",
                            ),
                            "Execute the requested shell tool, then give the final answer.",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=90,
                    )
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=5)
                self.assertEqual(
                    result.returncode, 0, result.stderr[-2000:] + result.stdout[-2000:]
                )
                rows = [
                    json.loads(line)
                    for line in result.stdout.splitlines()
                    if line.startswith("{")
                ]
                calls = [r for r in rows if r.get("type") == "tool_use"]
                self.assertTrue(calls, result.stdout[-2000:])
                self.assertIn("WCB_WIRE_OK", calls[0]["part"]["state"]["output"])
                self.assertTrue(
                    any(
                        r.get("type") == "text" and "WCB_FINAL_OK" in r["part"]["text"]
                        for r in rows
                    )
                )
                self.assertTrue(requests)
                self.assertTrue(
                    all(p == endpoint for p, _ in requests), [p for p, _ in requests]
                )


if __name__ == "__main__":
    unittest.main()
