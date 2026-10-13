import importlib.util
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "tools/report/skills/general-e2e/report-general-e2e/scripts/astronstudio_version_comparison.py"
sys.path.insert(0, str(PATH.parent))
SPEC = importlib.util.spec_from_file_location("astronstudio_version_comparison", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def request(index, input_tokens, output_tokens, thinking=0, body=0, results=0):
    return {"request_index": index, "usage_line": index * 10,
            "input_tokens": input_tokens, "output_tokens": output_tokens,
            "reasoning_output_tokens": 0, "reasoning_chars": thinking,
            "assistant_text_chars": body, "tool_arguments_chars": 0,
            "tool_results_chars": results}


class VersionComparisonTests(unittest.TestCase):
    def test_shell_command_capture_preserves_raw_text_and_selects_only_candidate_calls(self):
        command = 'rg -n "net income" /tmp/report.htm | head -20'
        rows = [
            {"type": "response_item", "payload": {"type": "function_call", "call_id": "selected", "name": "bash",
                "arguments": json.dumps({"command": command, "max_output_tokens": "3000"})}},
            {"type": "response_item", "payload": {"type": "function_call", "call_id": "outside", "name": "bash",
                "arguments": json.dumps({"command": "outside-window-content"})}},
        ]
        requests = [{"request_index": 1, "contents": [{"category": "tool_results", "tool_name": "bash", "call_id": "selected"}]},
                    {"request_index": 2, "contents": [{"category": "tool_results", "tool_name": "bash", "call_id": "outside"}]}]
        steps = [{"from_request": 1, "common_screen": "large-tool-result-candidate"}]
        captured = MODULE.shell_commands_for_candidates(("\n".join(json.dumps(r) for r in rows)).encode(), requests, steps)
        self.assertEqual(set(captured), {"selected"})
        self.assertEqual(captured["selected"]["command"], command)
        self.assertEqual(captured["selected"]["max_output_tokens"], "3000")

    def test_missing_original_shell_call_is_rejected(self):
        requests = [{"request_index": 1, "contents": [{"category": "tool_results", "tool_name": "exec_command", "call_id": "missing"}]}]
        steps = [{"from_request": 1, "common_screen": "large-tool-result-candidate"}]
        with self.assertRaisesRegex(ValueError, "SHELL_COMMAND_BINDING_INCOMPLETE"):
            MODULE.shell_commands_for_candidates(b"", requests, steps)

    def test_workspace_root_normalization_does_not_rewrite_similarly_named_files(self):
        text = 'Read ./workspace/data.txt; root `./workspace`; "relative to ./workspace"; ./workspace_notes.txt'
        self.assertEqual(MODULE.normalize_workspace_prompt(text),
                         'Read ./data.txt; root `.`; "relative to ."; ./workspace_notes.txt')

    def test_missing_reasoning_split_does_not_become_proven_reasoning_usage(self):
        rows = [request(1, 10000, 10000, thinking=25000, body=100), request(2, 20500, 100)]
        row = MODULE.transitions("task", rows)[0]
        self.assertEqual(row["original_screen"], "mixed-or-unresolved-large-jump")
        self.assertEqual(row["common_screen"], "reasoning-dominated-output-history-candidate")
        self.assertEqual(row["previous_reasoning_tokens"], 0)

    def test_large_plain_body_is_not_labeled_as_reasoning_history(self):
        rows = [request(1, 10000, 10000, body=25000), request(2, 20500, 100)]
        self.assertEqual(MODULE.transitions("task", rows)[0]["common_screen"], "mixed-or-unresolved-large-jump")

    def test_large_result_can_be_screened_without_thinking_token_split(self):
        rows = [request(1, 10000, 300, thinking=100, results=25000), request(2, 22000, 100)]
        self.assertEqual(MODULE.transitions("task", rows)[0]["common_screen"], "large-tool-result-candidate")

    def test_compaction_negative_delta_is_not_a_large_growth_candidate(self):
        rows = [request(1, 200000, 400, results=50000), request(2, 30000, 100)]
        row = MODULE.transitions("task", rows)[0]
        self.assertEqual(row["input_delta_tokens"], -170000)
        self.assertEqual(row["common_screen"], "ordinary-or-unresolved")


if __name__ == "__main__":
    unittest.main()
