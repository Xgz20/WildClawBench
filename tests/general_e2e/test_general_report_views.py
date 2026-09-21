from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from tests.general_e2e.test_report_general_e2e import REPORT, Fixture, write_json, sha256

VIEWS = REPORT.report_views


class GeneralReportViewsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.fixture = Fixture(self.root)
        self.data = REPORT.aggregate(REPORT.validate_batch_inputs(self.fixture.batch), "2026-09-21T00:00:00Z")
        self.references = VIEWS.load_references()

    def tearDown(self):
        self.temp.cleanup()

    def test_overview_has_requested_columns_and_valid_score_denominator(self):
        tables = self.data["presentation"]["tables"]
        self.assertEqual(list(tables)[:2], ["总览", "效率对比"])
        overview = tables["总览"]
        values = dict(zip(overview["headers"], overview["rows"][0]))
        self.assertEqual(values["总平均分"], 40)
        self.assertEqual(values["有效评分数"], 2)
        self.assertEqual(values["用例数"], 4)
        self.assertEqual(values["正常完成数"], 4)
        for key in ("总成本(USD)", "超时数", "格式准确率", "执行成功率", "不确定占比"):
            self.assertNotIn(key, overview["headers"])
        self.assertIn("任务耗时(s)", values)
        self.assertIn("流程耗时(s)", values)

    def test_efficiency_uses_total_denominator_and_distinguishes_cache_write_zero(self):
        resources = self.data["units"][0]["resources"]
        for key, value in {"total_tokens": 440, "input_tokens": 400, "output_tokens": 40,
                           "cache_read_input_tokens": 300, "cache_creation_input_tokens": 0}.items():
            resources[key]["total"] = value
        table = VIEWS.build_views(self.data, self.references)["tables"]["效率对比"]
        self.assertEqual(table["rows"][0][1:], [440, 110, 400, 40, 300, 0, .75])
        resources["total_tokens"]["total"] = None
        resources["cache_creation_input_tokens"]["total"] = None
        resources["input_tokens"]["total"] = 0
        resources["cache_read_input_tokens"]["total"] = 0
        row = VIEWS.build_views(self.data, self.references)["tables"]["效率对比"]["rows"][0]
        self.assertEqual(row[1:3], [None, None])
        self.assertIsNone(row[6])
        self.assertIsNone(row[7])
        resources["cache_read_input_tokens"]["total"] = 1
        with self.assertRaisesRegex(ValueError, "CACHE_EXCEEDS_INPUT"):
            VIEWS.build_views(self.data, self.references)

    def test_capabilities_average_within_task_then_between_tasks_and_keep_missing(self):
        mapping = {"a": {"x": ["code_generation"], "y": ["code_generation"]},
                   "b": {"x": ["code_generation"]}, "c": {"x": ["code_generation"]}}
        rows = [{"task_id": "a", "score_status": "valid", "checkpoints": {"values": {"x": 0, "y": 1}}},
                {"task_id": "b", "score_status": "valid", "checkpoints": {"values": {"x": 1}}},
                {"task_id": "c", "score_status": "evaluation_error", "checkpoints": {"values": {"x": 0}}}]
        result = VIEWS.capability_scores(rows, mapping)
        self.assertEqual(result["code_generation"], {"score": .75, "known": 2, "total": 3})
        self.assertEqual(result["tool_use"], {"score": None, "known": 0, "total": 0})
        del rows[0]["checkpoints"]["values"]["y"]
        self.assertEqual(VIEWS.capability_scores(rows, mapping)["code_generation"], {"score": 1, "known": 1, "total": 3})

    def test_hybrid_rule_and_semantic_checkpoints_are_bound_to_frozen_evidence(self):
        path = self.root / "rules.json"
        write_json(path, {"status": "completed", "score": .8, "raw_scores": {"first": .6, "second": 1}})
        score = {"result": {"valid": True, "total_score": .7}, "components": {"semantics": {"status": "completed"}},
                 "evaluation": {"criteria": [
                     {"key": "automated_component", "score": .8, "evidence": [{"type": "rule_result", "path": "rules.json", "sha256": sha256(path)}]},
                     {"key": "wording", "status": "judged", "score": .5}]}}
        result = VIEWS.checkpoints(score, self.root / "score.json", REPORT.resolve_file, sha256)
        self.assertEqual(result["values"], {"automated.first": .6, "automated.second": 1, "llm_judge.wording": .5, "overall_score": .7})
        path.write_text(path.read_text() + " ")
        with self.assertRaisesRegex(ValueError, "RULE_RESULT_DRIFT"):
            VIEWS.checkpoints(score, self.root / "score.json", REPORT.resolve_file, sha256)

    def test_tool_count_deduplicates_ids_without_claiming_success_and_checks_identity(self):
        identity = {"batch_id": "batch", "unit_id": "unit", "task_id": "task", "attempt_id": "attempt"}
        events = [{"identity": identity, "type": "tool_call", "tool": {"call_id": "one", "name": "Bash"}},
                  {"identity": identity, "type": "tool_result", "tool": {"call_id": "one", "status": "completed", "result": "Exit Code: 2"}}]
        events.append(copy.deepcopy(events[0]))
        transcript = self.root / "transcript.jsonl"
        transcript.write_text("\n".join(json.dumps(row) for row in events))
        index = {"identity": identity, "completeness": {"status": "complete"},
                 "transcript": {"path": transcript.name, "sha256": sha256(transcript), "size": transcript.stat().st_size}}
        write_json(self.root / "index.json", index)
        execution = {"identity": identity, "evidence": {"trace_index_path": "index.json"}}
        result = VIEWS.trace_tools(self.root, execution, REPORT.resolve_file, sha256)
        self.assertEqual(result["by_tool"], {"Bash": 1})
        self.assertEqual(result["total"], 1)
        self.assertNotIn("success", result)
        events[0]["identity"] = {**identity, "task_id": "other"}
        transcript.write_text("\n".join(json.dumps(row) for row in events))
        index["transcript"].update(sha256=sha256(transcript), size=transcript.stat().st_size)
        write_json(self.root / "index.json", index)
        with self.assertRaisesRegex(ValueError, "TRANSCRIPT_IDENTITY_MISMATCH"):
            VIEWS.trace_tools(self.root, execution, REPORT.resolve_file, sha256)

    def test_unknown_models_and_repeated_display_names_do_not_merge_units(self):
        unit = copy.deepcopy(self.data["units"][0]); unit["unit_id"] = "other"
        new_rows = copy.deepcopy(self.data["tasks"])
        for row in new_rows:
            row["unit_id"] = "other"
        self.data["units"].append(unit); self.data["tasks"].extend(new_rows)
        for row in self.data["tasks"]:
            row["model"]["verification_status"] = "unverified"
        views = VIEWS.build_views(self.data, self.references)
        rows = views["tables"]["总览"]["rows"]
        self.assertEqual(len(rows), 2)
        self.assertNotEqual(rows[0][0], rows[1][0])
        self.assertTrue(all(row[0].startswith("未知模型@") for row in rows))

    def test_infrastructure_and_scoring_anomalies_count_once_per_task(self):
        row = next(row for row in self.data["tasks"] if row["score_status"] == "evaluation_error")
        row["execution_status"] = "infrastructure_error"
        view = VIEWS.build_views(self.data, self.references)["tables"]["总览"]
        self.assertEqual(view["rows"][0][5], 1)


if __name__ == "__main__":
    unittest.main()
