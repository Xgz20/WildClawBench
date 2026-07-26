"""tool_metrics 单元测试：判定口径 + 跨 harness 文件格式兼容。

运行：python3 -m unittest tests/test_tool_metrics.py（在仓库根目录）
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from utils.tool_metrics import (  # noqa: E402
    classify_codex,
    classify_opencode,
    execution_success_rate,
    format_accuracy,
    merge_metrics,
    overall_success_rate,
    parse_tool_metrics,
    unclear_ratio,
)


def _codex_line(role: str, block: dict) -> str:
    """一行 Codex 风格 JSONL（逐行紧凑 JSON）。"""
    return json.dumps({"type": "message", "message": {"role": role, "content": [block]}})


def _tool_use(call_id: str, name: str) -> dict:
    return {"type": "tool_use", "id": call_id, "name": name, "input": {}}


def _tool_result(call_id: str, content: str, status: str = "") -> dict:
    block = {"type": "tool_result", "tool_use_id": call_id, "content": content}
    if status:
        block["status"] = status
    return block


class CodexClassifierTest(unittest.TestCase):
    def test_exec_exit_codes(self):
        self.assertEqual(classify_codex("exec_command", "Process exited with code 0\n"), "success")
        self.assertEqual(classify_codex("exec_command", "Process exited with code 1\n"), "failure")
        self.assertEqual(classify_codex("exec_command", "Process exited with code -1\n"), "failure")

    def test_background_process_unclear(self):
        self.assertEqual(
            classify_codex("exec_command", "Process running with session ID 3870\n"),
            "unclear",
        )

    def test_format_errors(self):
        self.assertEqual(classify_codex("exec", "unsupported call: exec"), "format_error")
        self.assertEqual(
            classify_codex("shell", "failed to parse function arguments: missing field `command`"),
            "format_error",
        )

    def test_runtime_error(self):
        self.assertEqual(
            classify_codex("write_stdin", "Traceback (most recent call last):\n  ..."),
            "failure",
        )

    def test_state_tools(self):
        self.assertEqual(classify_codex("update_plan", "Plan updated"), "success")
        self.assertEqual(
            classify_codex("spawn_agent", '{"agent_id":"abc","nickname":"Lagrange"}'),
            "success",
        )
        self.assertEqual(
            classify_codex("send_input", '{"submission_id":"019f"}'), "success"
        )
        self.assertEqual(
            classify_codex("view_image", '[{"type": "input_image", "image_url": "data:..."}]'),
            "success",
        )
        self.assertEqual(
            classify_codex("request_user_input", "request_user_input is unavailable in Default mode"),
            "failure",
        )


class OpenCodeClassifierTest(unittest.TestCase):
    def test_status_wins(self):
        self.assertEqual(classify_opencode("bash", "anything", "completed"), "success")
        self.assertEqual(classify_opencode("bash", "anything", "error"), "failure")
        self.assertEqual(classify_opencode("bash", "anything", "running"), "unclear")

    def test_business_error_is_success(self):
        # 业务层 error JSON，但工具执行成功（status=completed）
        self.assertEqual(
            classify_opencode("bash", '{"error":"rate_limit_exceeded"}', "completed"),
            "success",
        )

    def test_content_fallback_no_status(self):
        # 存量轨迹无 status：Traceback 开头判失败，正常内容判成功
        self.assertEqual(
            classify_opencode("bash", "Traceback (most recent call last):\n ImportError"),
            "failure",
        )
        self.assertEqual(classify_opencode("bash", '{"messages":[...]}'), "success")
        self.assertEqual(classify_opencode("bash", ""), "unclear")

    def test_no_format_error(self):
        # OpenCode 口径下不产出 format_error
        for content in ("unsupported call: exec", "failed to parse ..."):
            self.assertNotEqual(classify_opencode("bash", content, "completed"), "format_error")


class RatioTest(unittest.TestCase):
    def test_ratios_and_none_guards(self):
        m = {"total": 10, "success": 6, "failure": 2, "format_error": 1, "unclear": 1}
        self.assertAlmostEqual(format_accuracy(m), 0.9)
        self.assertAlmostEqual(execution_success_rate(m), 0.75)
        self.assertAlmostEqual(overall_success_rate(m), 0.6)
        self.assertAlmostEqual(unclear_ratio(m), 0.1)

        empty = {"total": 0, "success": 0, "failure": 0, "format_error": 0, "unclear": 0}
        self.assertIsNone(format_accuracy(empty))
        self.assertIsNone(execution_success_rate(empty))
        self.assertIsNone(overall_success_rate(empty))
        self.assertIsNone(unclear_ratio(empty))


class ParseIntegrationTest(unittest.TestCase):
    def _write(self, name: str, text: str) -> Path:
        p = Path(self.tmp.name) / name
        p.write_text(text, encoding="utf-8")
        return p

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_codex_jsonl_format(self):
        lines = [
            _codex_line("assistant", _tool_use("c1", "exec_command")),
            _codex_line("user", _tool_result("c1", "Process exited with code 0\nOutput:\n")),
            _codex_line("assistant", _tool_use("c2", "exec")),
            _codex_line("user", _tool_result("c2", "unsupported call: exec")),
            _codex_line("assistant", _tool_use("c3", "update_plan")),
            _codex_line("user", _tool_result("c3", "Plan updated")),
        ]
        path = self._write("chat.jsonl", "\n".join(lines) + "\n")
        m = parse_tool_metrics(path, "codex")
        self.assertEqual(m["total"], 3)
        self.assertEqual(m["success"], 2)  # exec_command + update_plan
        self.assertEqual(m["format_error"], 1)  # exec
        self.assertEqual(m["by_tool"]["exec_command"]["success"], 1)

    def test_opencode_multiline_pretty_json(self):
        # OpenCode：多个 pretty-printed 对象直接拼接（对象跨多行）
        objs = [
            {"type": "message", "message": {"role": "assistant",
                "content": [_tool_use("o1", "bash")]}},
            {"type": "message", "message": {"role": "user",
                "content": [_tool_result("o1", '{"ok":1}', status="completed")]}},
            {"type": "message", "message": {"role": "assistant",
                "content": [_tool_use("o2", "bash")]}},
            {"type": "message", "message": {"role": "user",
                "content": [_tool_result("o2", "boom", status="error")]}},
        ]
        text = "".join(json.dumps(o, indent=2) for o in objs)
        path = self._write("chat_openclaw.jsonl", text)
        m = parse_tool_metrics(path, "opencode")
        self.assertEqual(m["total"], 2)
        self.assertEqual(m["success"], 1)
        self.assertEqual(m["failure"], 1)
        self.assertEqual(m["format_error"], 0)

    def test_unregistered_harness_returns_empty(self):
        path = self._write("chat.jsonl", _codex_line("assistant", _tool_use("x", "foo")))
        m = parse_tool_metrics(path, "openclaw")
        self.assertEqual(m["total"], 0)

    def test_missing_file(self):
        m = parse_tool_metrics(Path(self.tmp.name) / "nope.jsonl", "codex")
        self.assertEqual(m["total"], 0)

    def test_merge(self):
        m1 = {"total": 2, "success": 1, "failure": 1, "format_error": 0, "unclear": 0,
              "by_tool": {"a": {"total": 2, "success": 1, "failure": 1, "format_error": 0, "unclear": 0}}}
        m2 = {"total": 1, "success": 1, "failure": 0, "format_error": 0, "unclear": 0,
              "by_tool": {"a": {"total": 1, "success": 1, "failure": 0, "format_error": 0, "unclear": 0}}}
        agg = merge_metrics([m1, m2])
        self.assertEqual(agg["total"], 3)
        self.assertEqual(agg["success"], 2)
        self.assertEqual(agg["by_tool"]["a"]["total"], 3)


if __name__ == "__main__":
    unittest.main()
