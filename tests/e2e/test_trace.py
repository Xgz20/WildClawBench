import json
from pathlib import Path
import tempfile
import unittest
import subprocess

from src.e2e.common import E2EError, load_script
from src.e2e.trace import normalize_rollout, resource_metrics, ensure_resource_coverage, mcp_callable_matches
from tests.e2e.test_scheduler import GUEST, native_fixture


class NativeMcpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "rollout.jsonl"
        self.rows = [json.loads(line) for line in native_fixture("prompt", "session", "turn").splitlines()]
        call = self.rows[3]["payload"]
        call.update(name="mcp__acode_apps__connector_sites__manage_site", arguments='{"operation":"create"}')
        self.end = {"type": "mcp_tool_call_end", "call_id": "call-1",
                    "invocation": {"server": "acode_apps", "tool": "manage_site", "arguments": {"operation": "create"}},
                    "result": {"Ok": {"content": [{"type": "text", "text": "created"}]}}}
        self.rows.insert(4, {"type": "event_msg", "payload": self.end})

    def tearDown(self):
        self.temp.cleanup()

    def normalize(self, *, prompt="prompt", desktop=False):
        self.path.write_text("\n".join(json.dumps(row) for row in self.rows), encoding="utf-8")
        return normalize_rollout(self.path, identity={"batch_id": "b", "unit_id": "u", "task_id": "t", "attempt_id": "a"},
                                 prompt=prompt, guest_cwd=GUEST, requested_model="spark-x2.6", requested_effort="high",
                                 report={"usage": {"input_tokens": 100, "output_tokens": 10, "cache_tokens": 50}},
                                 desktop=desktop)

    def test_mcp_end_keeps_native_metadata_without_duplicating_tools(self):
        value = self.normalize()
        self.assertEqual(value["missing"], [])
        self.assertEqual(len(value["calls"]), 1)
        meta = next(event for event in value["events"] if event.get("content") == "mcp_tool_call_end")
        self.assertEqual(meta["native_status"], self.end)

    def test_single_pasted_text_binds_without_rewriting_raw_user_event(self):
        message = '<pasted_text>\n' + json.dumps([{"text": "prompt"}]) + '\n</pasted_text>'
        user = next(row for row in self.rows if row.get("type") == "event_msg"
                    and row["payload"].get("type") == "user_message")
        user["payload"]["message"] = message
        binding = self.normalize()
        self.assertEqual(binding["prompt_transport"]["kind"], "astudio-single-pasted-text-json")
        self.assertEqual(next(event for event in binding["events"] if event["type"] == "user_message")["content"], message)
        self.assertEqual(binding["missing"], [])

    def test_chatgpt_markdown_escapes_bind_only_the_exact_prompt(self):
        prompt = "读取 `input.txt`。\n\n写入 `result.txt`。"
        text = "读取 \\`input.txt\\`。\\\n\\\n写入 \\`result.txt\\`。\n"
        self.rows[0]["payload"]["originator"] = "Codex Desktop"
        part = {"type": "text", "text": text}
        self.rows[2]["payload"] = {
            "type": "item_completed", "thread_id": "session", "turn_id": "turn",
            "item": {"type": "UserMessage", "content": [part]},
        }
        self.rows.insert(2, {"type": "event_msg", "payload": {"type": "task_started", "turn_id": "turn"}})
        binding = self.normalize(prompt=prompt, desktop=True)
        self.assertEqual(binding["prompt_transport"]["kind"], "chatgpt-desktop-markdown-escaped")
        self.assertEqual(next(event["content"] for event in binding["events"]
                              if event["type"] == "user_message"), prompt)
        part["text"] = text.replace("result.txt", "different.txt")
        with self.assertRaisesRegex(E2EError, "NATIVE_PROMPT_MISMATCH"):
            self.normalize(prompt=prompt, desktop=True)

    def test_client_tool_search_preserves_the_call_and_catalog_result(self):
        tools = [{"type": "function", "name": "preview", "parameters": {"type": "object"}}]
        native = [
            {"type": "tool_search_call", "call_id": "search", "execution": "client",
             "status": "completed", "arguments": {"query": "preview"}},
            {"type": "tool_search_output", "call_id": "search", "execution": "client",
             "status": "completed", "tools": tools},
        ]
        self.rows[3:3] = [{"type": "response_item", "payload": payload} for payload in native]
        binding = self.normalize()
        self.assertEqual(binding["missing"], [])
        call, result = [event for event in binding["events"] if event.get("tool", {}).get("call_id") == "search"]
        self.assertEqual(call["tool"]["name"], "tool_search")
        self.assertEqual(result["tool"]["result"], {"tools": tools})
        native[1]["call_id"] = "call-1"
        with self.assertRaisesRegex(E2EError, "NATIVE_TOOL_SEARCH_CALL_MISMATCH"):
            self.normalize()

    def test_parser_failure_with_empty_id_binds_only_to_adjacent_search(self):
        message = 'failed to parse tool_search arguments: invalid type: string "20", expected usize'
        metadata = {"turn_id": "turn"}
        call = {"type": "tool_search_call", "call_id": "search", "execution": "client",
                "arguments": {"limit": "20"}, "internal_chat_message_metadata_passthrough": metadata}
        result = {"type": "function_call_output", "call_id": "", "output": message,
                  "internal_chat_message_metadata_passthrough": metadata}
        self.rows[3:3] = [{"type": "response_item", "payload": value} for value in (call, result)]
        binding = self.normalize()
        self.assertEqual(binding["missing"], [])
        event = next(event for event in binding["events"] if event.get("tool", {}).get("result") == message)
        self.assertEqual(event["tool"]["call_id"], "search")
        self.assertEqual(result["call_id"], "")
        result["internal_chat_message_metadata_passthrough"] = {"turn_id": "other"}
        with self.assertRaisesRegex(E2EError, "NATIVE_RESULT_ID_INVALID"):
            self.normalize()

    def test_pasted_text_rejects_different_body_additions_and_multiple_entries(self):
        user = next(row for row in self.rows if row.get("type") == "event_msg"
                    and row["payload"].get("type") == "user_message")
        for entries, prefix, suffix in [
            ([{"text": "different"}], "", ""),
            ([{"text": "prompt"}, {"text": "extra"}], "", ""),
            ([{"text": "prompt", "file": "extra"}], "", ""),
            ([{"text": "prompt"}], "additional instructions\n", ""),
            ([{"text": "prompt"}], "", "\nadditional instructions"),
            ([{"text": {"text": "prompt"}}], "", ""),
        ]:
            with self.subTest(entries=entries, prefix=prefix, suffix=suffix):
                user["payload"]["message"] = prefix + '<pasted_text>\n' + json.dumps(entries) + '\n</pasted_text>' + suffix
                with self.assertRaisesRegex(E2EError, "NATIVE_PROMPT_MISMATCH"):
                    self.normalize()

    def test_builtin_browser_mirror_requires_same_name_and_acode_server(self):
        name = "astron_browser_press"
        self.rows[3]["payload"]["name"] = name
        self.end["invocation"].update(server="acode", tool=name)
        self.assertEqual(self.normalize()["missing"], [])
        self.end["invocation"]["server"] = "acode_apps"
        with self.assertRaisesRegex(E2EError, "NATIVE_MCP_INVOCATION_MISMATCH"):
            self.normalize()

    def test_mcp_end_with_wrong_invocation_is_rejected(self):
        self.end["invocation"]["arguments"] = {"operation": "delete"}
        with self.assertRaisesRegex(E2EError, "MCP_INVOCATION_MISMATCH"):
            self.normalize()

    def test_hashed_connector_alias_preserves_raw_name_and_rejects_tampering(self):
        alias = "mcp__acode_apps__connector_image_understanding__ima_e439a9fe053a"
        call = self.rows[3]["payload"]
        call["name"] = alias
        self.end["invocation"]["tool"] = "image_understanding"
        value = self.normalize()
        self.assertEqual(next(event for event in value["events"] if event["type"] == "tool_call")["tool"]["name"], alias)
        for name in (alias[:-1] + "b", alias.replace("__ima_", "__img_"), alias + "x"):
            call["name"] = name
            with self.assertRaisesRegex(E2EError, "MCP_INVOCATION_MISMATCH"):
                self.normalize()
        call["name"] = alias
        self.end["invocation"]["arguments"] = {"operation": "different"}
        with self.assertRaisesRegex(E2EError, "MCP_INVOCATION_MISMATCH"):
            self.normalize()

    def test_independent_collector_replays_same_alias_gate(self):
        alias = "mcp__acode_apps__connector_image_understanding__ima_e439a9fe053a"
        cases = [(alias, "acode_apps", "image_understanding"),
                 (alias[:-1] + "b", "acode_apps", "image_understanding"),
                 (alias, "other", "image_understanding"),
                 (alias, "acode_apps", "other"),
                 ("list_mcp_resources", "acode", "list_mcp_resources"),
                 ("list_mcp_resources", "acode_apps", "list_mcp_resources"),
                 ("astron_browser_screenshot", "acode", "astron_browser_screenshot"),
                 ("mcp__acode_apps__connector_sites__manage_site", "acode_apps", "manage_site")]
        module = Path(__file__).resolve().parents[2] / "tools/report/skills/general-e2e/collect-general-e2e/scripts/lib/agentcube-native-verification.mjs"
        code = "const {mcpCallableMatches:f}=await import(process.argv[1]);process.stdout.write(JSON.stringify(JSON.parse(process.argv[2]).map(x=>f(...x))));"
        result = subprocess.run(["node", "--input-type=module", "-e", code, module.as_uri(), json.dumps(cases)],
                                capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout), [True, False, False, False, True, False, True, True])
        self.assertEqual(json.loads(result.stdout), [mcp_callable_matches(*case) for case in cases])

    def test_mcp_end_without_canonical_pair_marks_trace_incomplete(self):
        self.end["call_id"] = "unbound-call"
        self.assertIn("mcp-end-without-canonical-pair", self.normalize()["missing"])

    def test_resource_coverage_reaches_existing_general_report(self):
        binding = self.normalize()
        metrics = resource_metrics(binding["identity"], binding, [])
        report = load_script(
            Path(__file__).resolve().parents[2]
            / "tools/report/skills/general-e2e/report-general-e2e/scripts/report_general_e2e.py",
            "sandbox_resource_report_test",
        )
        observed = report.metric_observation(metrics, "input_tokens")
        self.assertTrue(observed["complete"])
        self.assertEqual(observed["value"], 100)
        self.assertIsNone(report.metric_observation(metrics, "request_count")["value"])
        metrics["collection"].pop("coverage")
        self.assertEqual(
            ensure_resource_coverage(metrics)["collection"]["coverage"]["input_tokens"][
                "known"
            ],
            1,
        )
