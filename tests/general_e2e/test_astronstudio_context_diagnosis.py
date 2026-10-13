import hashlib
import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "tools/report/skills/general-e2e/report-general-e2e/scripts/astronstudio_context_diagnosis.py"
SPEC = importlib.util.spec_from_file_location("context_diagnosis", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def usage(i, c, o, r):
    return {"input_tokens": i, "cached_input_tokens": c, "output_tokens": o,
            "reasoning_output_tokens": r, "total_tokens": i + o}


def event(kind, **payload):
    return {"type": "event_msg", "payload": {"type": kind, **payload}}


def item(kind, **payload):
    return {"type": "response_item", "payload": {"type": kind, **payload}}


def fixture(extra):
    execution = {"session": {"session_id": "session", "turn_id": "target", "cwd": "/tmp/task"},
                 "prompt": {"send_status": "sent", "sha256": hashlib.sha256(b"task").hexdigest()}}
    rows = [{"type": "session_meta", "payload": {"id": "session", "cwd": "/tmp/task",
              "base_instructions": {"text": "system"}}},
            event("task_started", turn_id="target"),
            event("user_message", message="task"), *extra,
            event("task_complete", turn_id="target")]
    return ("\n".join(json.dumps(row) for row in rows) + "\n").encode(), execution


class ContextDiagnosisTests(unittest.TestCase):
    def test_compaction_size_in_unchanged_last_usage_is_audited_without_counting_a_response(self):
        first, second = usage(100, 80, 10, 2), usage(130, 100, 8, 3)
        malformed = usage(0, 0, 0, 0)
        malformed["total_tokens"] = 16912
        data, execution = fixture([
            item("reasoning", id="r1", summary=[{"text": "abc"}]),
            event("token_count", info={"total_token_usage": first, "last_token_usage": first}),
            item("reasoning", id="unmetered", summary=[{"text": "extra"}]),
            event("token_count", info={"total_token_usage": first, "last_token_usage": malformed}),
            item("reasoning", id="r2", summary=[{"text": "defgh"}]),
            event("token_count", info={"total_token_usage": usage(230, 180, 18, 5), "last_token_usage": second}),
        ])
        result = MODULE.parse_rollout(data, execution)
        self.assertEqual(len(result["requests"]), 2)
        self.assertEqual(sum(r["total_tokens"] for r in result["requests"]), 248)
        self.assertEqual([r["reasoning_chars"] for r in result["requests"]], [3, 5])
        self.assertEqual(result["unmetered_windows"][0]["reasoning_chars"], 5)
        anomaly = result["nonadvancing_invalid_last_usage"][0]
        self.assertEqual(anomaly["last_token_usage"]["total_tokens"], 16912)
        self.assertFalse(anomaly["counted_as_model_response"])

    def test_invalid_last_usage_on_an_advancing_checkpoint_remains_rejected(self):
        malformed = usage(0, 0, 0, 0)
        malformed["total_tokens"] = 16912
        data, execution = fixture([
            event("token_count", info={"total_token_usage": usage(100, 80, 10, 2), "last_token_usage": malformed}),
        ])
        with self.assertRaisesRegex(ValueError, "INVALID_NATIVE_USAGE"):
            MODULE.parse_rollout(data, execution)

    def test_fresh_reasoning_at_unchanged_usage_is_not_merged_into_next_response(self):
        first, second = usage(100, 80, 10, 2), usage(130, 100, 8, 3)
        total = usage(230, 180, 18, 5)
        data, execution = fixture([
            item("reasoning", id="r1", summary=[{"text": "abc"}]),
            event("agent_reasoning", text="abc"),  # mirrored event must not count again
            event("token_count", info={"total_token_usage": first, "last_token_usage": first}),
            item("reasoning", id="unmetered", summary=[{"text": "x" * 100}]),
            event("token_count", info={"total_token_usage": first, "last_token_usage": first}),
            item("reasoning", id="r2", summary=[{"text": "defgh"}]),
            event("token_count", info={"total_token_usage": total, "last_token_usage": second}),
        ])
        result = MODULE.parse_rollout(data, execution)
        self.assertEqual([r["reasoning_chars"] for r in result["requests"]], [3, 5])
        self.assertEqual(result["unmetered_windows"][0]["reasoning_chars"], 100)
        self.assertIsNone(result["unmetered_windows"][0]["native_tokens"])
        self.assertEqual(sum(r["input_tokens"] for r in result["requests"]), 230)

    def test_late_tool_result_remains_with_its_call_and_replays_are_deduplicated(self):
        first, second = usage(100, 80, 10, 2), usage(130, 100, 8, 3)
        call = item("function_call", id="c", call_id="call", name="read", arguments="{}")
        output = item("function_call_output", call_id="call", output="工具返回")
        data, execution = fixture([
            call, call,
            event("token_count", info={"total_token_usage": first, "last_token_usage": first}),
            output, output,
            event("token_count", info={"total_token_usage": usage(230, 180, 18, 5),
                                        "last_token_usage": second}),
        ])
        result = MODULE.parse_rollout(data, execution)
        self.assertEqual(result["requests"][0]["tool_arguments_chars"], 2)
        self.assertEqual(result["requests"][0]["tool_results_chars"], 4)
        self.assertEqual(result["requests"][1]["tool_results_chars"], 0)
        self.assertEqual(result["late_tool_results"], 1)
        self.assertEqual(result["requests"][0]["contents"][-1]["utf8_bytes"], 12)

    def test_mismatched_native_usage_and_changed_prompt_fail_closed(self):
        data, execution = fixture([
            event("token_count", info={"total_token_usage": usage(110, 90, 11, 2),
                                        "last_token_usage": usage(100, 80, 10, 2)})])
        with self.assertRaisesRegex(ValueError, "UNRECONCILED"):
            MODULE.parse_rollout(data, execution)
        data, execution = fixture([
            event("token_count", info={"total_token_usage": usage(100, 80, 10, 2),
                                        "last_token_usage": usage(100, 80, 10, 2)})])
        execution["prompt"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "PROMPT_SHA"):
            MODULE.parse_rollout(data, execution)

    def test_previous_turn_usage_is_only_a_cumulative_baseline(self):
        base, current = usage(100, 80, 10, 2), usage(130, 100, 8, 3)
        execution = {"session": {"session_id": "session", "turn_id": "target", "cwd": "/tmp/task"},
                     "prompt": {"send_status": "sent", "sha256": hashlib.sha256(b"task").hexdigest()}}
        rows = [{"type": "session_meta", "payload": {"id": "session", "cwd": "/tmp/task"}},
                event("task_started", turn_id="old"),
                item("reasoning", id="old-reason", summary=[{"text": "old"}]),
                event("token_count", info={"total_token_usage": base, "last_token_usage": base}),
                event("task_started", turn_id="target"), event("user_message", message="task"),
                item("reasoning", id="new-reason", summary=[{"text": "new"}]),
                event("token_count", info={"total_token_usage": usage(230, 180, 18, 5),
                                           "last_token_usage": current}),
                event("task_complete", turn_id="target")]
        result = MODULE.parse_rollout(("\n".join(json.dumps(row) for row in rows) + "\n").encode(), execution)
        self.assertEqual(len(result["requests"]), 1)
        self.assertEqual(result["requests"][0]["input_tokens"], 130)
        self.assertEqual(result["requests"][0]["reasoning_chars"], 3)


if __name__ == "__main__":
    unittest.main()
