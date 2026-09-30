import json
import tempfile
import unittest
from pathlib import Path
import importlib.util


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools/report/skills/general-e2e/report-general-e2e/scripts/token_growth_analysis.py"
SPEC = importlib.util.spec_from_file_location("token_growth_analysis", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class TokenGrowthAnalysisTests(unittest.TestCase):
    def test_astron_rollout_series_reconciles_advancing_usage(self):
        with tempfile.TemporaryDirectory() as temp:
            rollout = Path(temp) / "astronstudio-rollout.jsonl"
            rows = [
                {"type": "event_msg", "payload": {"type": "token_count", "info": {
                    "total_token_usage": {"input_tokens": 100, "cached_input_tokens": 80, "output_tokens": 20, "reasoning_output_tokens": 5, "total_tokens": 120},
                    "last_token_usage": {"input_tokens": 100, "cached_input_tokens": 80, "output_tokens": 20, "reasoning_output_tokens": 5, "total_tokens": 120},
                }}},
                {"type": "event_msg", "payload": {"type": "token_count", "info": {
                    "total_token_usage": {"input_tokens": 260, "cached_input_tokens": 220, "output_tokens": 35, "reasoning_output_tokens": 8, "total_tokens": 295},
                    "last_token_usage": {"input_tokens": 160, "cached_input_tokens": 140, "output_tokens": 15, "reasoning_output_tokens": 3, "total_tokens": 175},
                }}},
            ]
            rollout.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
            series = MODULE._series_from_astron(rollout)
            self.assertEqual([row["input_tokens"] for row in series], [100, 160])
            self.assertEqual(series[-1]["cumulative_input_tokens"], 260)
            self.assertEqual(series[-1]["cumulative_total_tokens"], 295)

    def test_jsonl_usage_supports_workbuddy_and_qwen_shapes(self):
        with tempfile.TemporaryDirectory() as temp:
            workbuddy = Path(temp) / "workbuddy.jsonl"
            workbuddy.write_text(json.dumps({"providerData": {"usage": {
                "inputTokens": 100, "outputTokens": 10, "totalTokens": 110,
                "inputTokensDetails": [{"cached_tokens": 80}],
                "outputTokensDetails": [{"reasoning_tokens": 2}],
            }}}) + "\n")
            qwen = Path(temp) / "qwen.jsonl"
            qwen.write_text(json.dumps({"usage": {
                "input_tokens": 120, "cache_read_input_tokens": 100,
                "cache_creation_input_tokens": 0, "output_tokens": 15,
            }}) + "\n")
            self.assertEqual(MODULE._series_from_jsonl(workbuddy)[0]["cached_input_tokens"], 80)
            self.assertEqual(MODULE._series_from_jsonl(qwen)[0]["total_tokens"], 135)

    def test_system_prompt_attribution_is_explicitly_unavailable(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); report = root / "report.json"
            report.write_text(json.dumps({"tasks": []}))
            result = MODULE.analyze(root, report)
            self.assertEqual(result["attribution"]["system_prompt_tokens"]["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
