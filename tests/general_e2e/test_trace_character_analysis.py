import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "tools/report/skills/general-e2e/report-general-e2e/scripts/trace_character_analysis.py"
sys.path.insert(0, str(PATH.parent))
SPEC = importlib.util.spec_from_file_location("trace_character_analysis", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def data(rows):
    return ("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n").encode()


EXECUTION = {"identity": {"attempt_id": "attempt", "task_id": "task", "unit_id": "unit", "batch_id": "batch"},
             "session": {"session_id": "session", "turn_id": "turn", "cwd": "/tmp/task"}}


class TraceCharacterTests(unittest.TestCase):
    def test_workbuddy_excludes_mirrored_result_and_keeps_unknown_reasoning_null(self):
        result = {"type": "function_call_result", "callId": "c", "output": {"type": "text", "text": "返回"},
                  "providerData": {"toolResult": {"content": "返回", "rawResponse": {"stdout": "返回"}}}}
        parsed = MODULE.parse_workbuddy(data([
            {"type": "message", "id": "u", "role": "user", "content": [{"type": "input_text", "text": "prefix任务"}]},
            {"type": "function_call", "callId": "c", "name": "Read", "arguments": '{"路径": "文件"}'},
            result, result,
        ]), EXECUTION, "任务", "source")
        self.assertEqual(parsed.totals()["tool_results"], 2)
        self.assertEqual(parsed.totals()["user_prompt"], 2)
        self.assertEqual(parsed.totals()["injected_context"], 6)
        self.assertIsNone(parsed.totals()["reasoning"])
        self.assertEqual(parsed.diagnostics["duplicate_items_excluded"], 1)

    def test_conflicting_replay_and_wrong_session_are_rejected(self):
        c = MODULE.Contents({"tool_results"})
        c.add("tool_results", "a", "file", "line:1", key="call")
        with self.assertRaisesRegex(ValueError, "REPLAY_CONTENT_CONFLICT"):
            c.add("tool_results", "b", "file", "line:2", key="call")
        with self.assertRaisesRegex(ValueError, "SESSION_MISMATCH"):
            MODULE.check_session({"sessionId": "different"}, EXECUTION)

    def test_qwen_preserves_distinct_blocks_with_shared_message_id_and_excludes_images(self):
        def row(kind, uuid, part):
            return {"type": kind, "uuid": uuid, "message": {"id": "shared", "content": [part]}}
        parsed = MODULE.parse_qwen(data([
            row("user", "prompt", {"type": "text", "text": "任务"}),
            row("assistant", "thought", {"type": "thinking", "thinking": "思考"}),
            row("assistant", "body", {"type": "text", "text": "输出"}),
            row("assistant", "call", {"type": "tool_use", "id": "c", "name": "Read", "input": {"x": "中"}}),
            {**row("user", "result", {"type": "tool_result", "tool_use_id": "c", "content": [
                {"type": "text", "text": "返回"}, {"type": "image", "source": {"data": "x" * 1000}}]}),
             "toolUseResult": {"stdout": "wrong mirrored content"}},
        ]), EXECUTION, "任务", "source")
        self.assertEqual(parsed.totals()["reasoning"], 2)
        self.assertEqual(parsed.totals()["assistant_text"], 2)
        self.assertEqual(parsed.totals()["tool_results"], 2)
        self.assertEqual(parsed.diagnostics["image_blocks_excluded"], 1)
        self.assertIsNone(parsed.totals()["tool_schema"])

    def test_doubao_titles_and_transport_mirrors_do_not_become_reasoning(self):
        rows = [{"identity": EXECUTION["identity"], "type": "user_message", "event_id": "u", "content": "任务"},
                {"identity": EXECUTION["identity"], "type": "tool_call", "tool": {"call_id": "c", "name": "Bash", "arguments": {"command": "ls"}}},
                {"identity": EXECUTION["identity"], "type": "tool_result", "tool": {"call_id": "c", "result": {"content": "返回", "data": {"stdout": "返回"}, "display": {"summary": "返回"}}}}]
        runtime = {"conversation_id": "session", "maps": {"messageMap": {"turn": {
            "message_id": "turn", "conversation_id": "session", "content_blocks_v2": [
                {"block_id": "heading", "content": {"thinking_block": {"finish_title": "Thinking"}}},
                {"block_id": "body", "content": {"text_block": {"text": "正文", "summary": "摘要"}}},
            ]}}}}
        parsed = MODULE.parse_doubao(data(rows), json.dumps(runtime).encode(), EXECUTION, "trace", "runtime")
        self.assertEqual(parsed.totals()["assistant_text"], 2)
        self.assertEqual(parsed.totals()["tool_results"], 2)
        self.assertIsNone(parsed.totals()["reasoning"])
        self.assertEqual(parsed.diagnostics["thinking_title_blocks_without_body"], 1)
        self.assertEqual(parsed.diagnostics["ui_summary_chars_excluded"], 2)

    def test_argument_serialization_is_consistent_between_string_and_object(self):
        args = {"command": "echo 中文\n"}
        self.assertEqual(MODULE.argument_text(json.dumps(args)), MODULE.argument_text(args))
        self.assertEqual(MODULE.visible_text({"content": "a", "text": "b", "data": "mirror"}), "b")

    def test_unavailable_category_is_null_and_p90_uses_nearest_rank(self):
        tasks = [{"visible_chars": {"reasoning": None, "assistant_text": i}} for i in range(1, 11)]
        stat = MODULE.statistics_for(tasks, "reasoning")
        self.assertIsNone(stat["visible_sum_chars"])
        self.assertEqual(stat["available_tasks"], 0)
        self.assertEqual(MODULE.statistics_for(tasks, "assistant_text")["p90_per_task_chars"], 9)

    def test_astron_separates_prompt_environment_schema_and_unmetered_reasoning(self):
        execution = {**EXECUTION, "prompt": {"send_status": "sent", "sha256": hashlib.sha256("任务".encode()).hexdigest()}}
        usage = {"input_tokens": 10, "cached_input_tokens": 0, "output_tokens": 2,
                 "reasoning_output_tokens": 1, "total_tokens": 12}
        checkpoint = {"type": "event_msg", "payload": {"type": "token_count", "info": {
            "total_token_usage": usage, "last_token_usage": usage}}}
        rows = [
            {"type": "session_meta", "payload": {"id": "session", "cwd": "/tmp/task", "base_instructions": {"text": "base"}, "dynamic_tools": [{"name": "initial"}]}},
            {"type": "event_msg", "payload": {"type": "task_started", "turn_id": "turn"}},
            {"type": "event_msg", "payload": {"type": "user_message", "message": "任务"}},
            {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"text": "额外背景"}]}},
            {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"text": "任务环境"}]}},
            {"type": "response_item", "payload": {"type": "reasoning", "id": "r", "summary": [{"text": "思考"}]}},
            checkpoint,
            {"type": "response_item", "payload": {"type": "reasoning", "id": "u", "summary": [{"text": "未计量"}]}},
            checkpoint,
            {"type": "response_item", "payload": {"type": "tool_search_output", "call_id": "search", "tools": [{"name": "dynamic", "parameters": {"type": "object"}}]}},
            {"type": "event_msg", "payload": {"type": "task_complete", "turn_id": "turn"}},
        ]
        parsed = MODULE.parse_astron(data(rows), execution, "任务", "rollout")
        self.assertEqual(parsed.totals()["user_prompt"], 2)
        self.assertEqual(parsed.totals()["injected_context"], 10)
        self.assertEqual(parsed.totals()["reasoning"], 5)
        self.assertEqual(parsed.diagnostics["unmetered_reasoning_chars"], 3)
        self.assertEqual(sum(i["scope"] == "loaded-schema-result" for i in parsed.items), 1)

    def test_changed_execution_hash_is_rejected_before_analysis(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "execution.json").write_text(json.dumps(EXECUTION))
            (root / "TASK_INDEX.json").write_text(json.dumps({"tasks": [{"harness": "WorkBuddy", "task_id": "task",
                "execution_record": "execution.json", "execution_record_sha256": "0" * 64}]}))
            with self.assertRaisesRegex(ValueError, "EXECUTION_SHA_DRIFT"):
                MODULE.analyze(root)


if __name__ == "__main__":
    unittest.main()
