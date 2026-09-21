from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from tests.general_e2e.test_report_general_e2e import REPORT, Fixture, write_json, sha256

VIEWS = REPORT.report_views
CASES = REPORT.report_case_views


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
        persisted = json.loads(REPORT.pretty_json_bytes(self.data))
        self.assertEqual(persisted["presentation"]["sheet_order"][:2], ["总览", "效率对比"])
        markdown = REPORT.render_markdown(persisted)
        self.assertLess(markdown.index("## 总览"), markdown.index("## 效率对比"))
        self.assertLess(markdown.index("## 效率对比"), markdown.index("## Agent能力对比"))
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
        request = overview["headers"].index("总请求数")
        self.assertEqual(overview["headers"][request + 1], "工具调用数")

    def test_efficiency_uses_total_denominator_and_distinguishes_cache_write_zero(self):
        resources = self.data["units"][0]["resources"]
        for key, value in {"total_tokens": 440, "input_tokens": 400, "output_tokens": 40,
                           "cache_read_input_tokens": 300, "cache_creation_input_tokens": 0}.items():
            resources[key]["total"] = value
        table = VIEWS.build_views(self.data, self.references)["tables"]["效率对比"]
        self.assertEqual(table["rows"][0][1:], [440, 110, 100, 300, 0, 40, .75])
        resources["cache_creation_input_tokens"]["total"] = 20
        row = VIEWS.build_views(self.data, self.references)["tables"]["效率对比"]["rows"][0]
        self.assertEqual(row[3:7], [80, 300, 20, 40])
        self.assertEqual(sum(row[3:7]), row[1])
        resources["total_tokens"]["total"] = None
        resources["cache_creation_input_tokens"]["total"] = None
        resources["input_tokens"]["total"] = 0
        resources["cache_read_input_tokens"]["total"] = 0
        row = VIEWS.build_views(self.data, self.references)["tables"]["效率对比"]["rows"][0]
        self.assertEqual(row[1:3], [None, None])
        self.assertIsNone(row[3])
        self.assertIsNone(row[5])
        self.assertIsNone(row[7])
        resources["cache_read_input_tokens"]["total"] = 1
        with self.assertRaisesRegex(ValueError, "CACHE_EXCEEDS_INPUT"):
            VIEWS.build_views(self.data, self.references)
        resources["input_tokens"]["total"] = 10
        resources["cache_read_input_tokens"]["total"] = 6
        resources["cache_creation_input_tokens"]["total"] = 5
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

    def test_case_comparison_uses_one_row_per_task_and_parallel_unit_scores(self):
        unit = copy.deepcopy(self.data["units"][0]); unit["unit_id"] = "second"
        copied = copy.deepcopy(self.data["tasks"])
        for row in copied:
            row["unit_id"] = "second"
            if row["task_id"] == "task-zero":
                row["total_score"] = .5
        self.data["units"].append(unit); self.data["tasks"].extend(copied)
        views = VIEWS.build_views(self.data, self.references)
        compare = views["case_comparison"]
        self.assertEqual(compare["headers"][:10], ["分类", "用例ID", "用例名称", "难度", "模态", "标签", "输入(Prompt)", "预期行为", "评分标准", "检查点"])
        self.assertEqual(len(compare["rows"]), 4)
        row = next(r for r in compare["rows"] if r[1] == "task-zero")
        self.assertIn("总分：0.00 / 100", row[10])
        self.assertIn("总分：50.00 / 100", row[11])
        self.assertEqual(row[-1], 50)
        self.assertEqual(row[-2], views["unit_labels"]["second"])
        tied = next(r for r in compare["rows"] if r[1] == "task-valid")
        self.assertEqual(tied[-1], 0)
        self.assertIn(views["unit_labels"]["second"], tied[-2])
        self.assertIn(views["unit_labels"][self.fixture.unit_id], tied[-2])
        missing = next(r for r in compare["rows"] if r[1] == "task-error")
        self.assertEqual(missing[-2:], [None, None])
        self.assertEqual(len(views["score_details"]), 2)
        for name, detail in views["score_details"].items():
            self.assertTrue(name.startswith("评分详情_")); self.assertLessEqual(len(name), 31)
            self.assertEqual(len(detail["rows"]), 4)
            self.assertNotIn("根因分析", detail["headers"])
            self.assertIn("裁判判词", detail["headers"])

    def test_single_unit_never_claims_best_and_conflicting_definitions_fail(self):
        self.assertTrue(all(row[-2:] == [None, None] for row in self.data["presentation"]["case_comparison"]["rows"]))
        row = copy.deepcopy(self.data["tasks"][0]); row["unit_id"] = "second"
        row["task_definition"] = {"status": "complete", "task_sha256": "a", "contract_sha256": "a"}
        self.data["tasks"][0]["task_definition"] = {"status": "complete", "task_sha256": "b", "contract_sha256": "b"}
        self.data["tasks"].append(row)
        with self.assertRaisesRegex(ValueError, "TASK_DEFINITION_CONFLICT"):
            VIEWS.build_views(self.data, self.references)

    def test_frozen_definition_checks_identity_and_sha_without_repository_fallback(self):
        identity = {"batch_id": "batch", "unit_id": "unit", "task_id": "task", "attempt_id": "exec"}
        execution = {"identity": identity, "dataset": {"id": "dataset", "digest": "d"}}
        score = {"identity": {**identity, "attempt_id": "judge"}}
        task = self.root / "task.md"
        task.write_text('---\nid: task\ntags:\n  - custom\n---\n## Prompt\nOriginal task\n```text\n## Expected Behavior\nquoted heading\n```\n## Expected Behavior\nExpected\n## Skills\nNone\n', encoding="utf-8")
        contract = self.root / "contract.json"
        write_json(contract, {"task_id": "task", "expected_behavior": "Expected", "grading_criteria": "Rubric", "automated_checks": "return 1"})
        write_json(self.root / "attempt-manifest.json", {"identity": {"batch_id": "batch", "unit_id": "unit", "task_id": "task", "execution_attempt_id": "exec", "scoring_attempt_id": "judge"},
                   "dataset": execution["dataset"], "paths": {"task": "task.md", "contract": "contract.json"},
                   "digests": {"task_sha256": sha256(task), "contract_sha256": sha256(contract)}})
        definition = CASES.frozen_task_definition({"task_id": "task"}, execution, score, self.root / "score.json", REPORT.resolve_file, sha256)
        self.assertEqual(definition["tags"], "custom")
        self.assertIn("quoted heading", definition["prompt"])
        self.assertEqual(definition["expected"], "Expected")
        self.assertEqual(definition["skills"], "None")
        self.assertIsNone(CASES.declaration("```bash\n```"))
        self.assertEqual(CASES.declaration("```text\nworkspace/task\n```"), "workspace/task")
        task.write_text(task.read_text() + "drift")
        with self.assertRaisesRegex(ValueError, "TASK_DEFINITION_DRIFT"):
            CASES.frozen_task_definition({"task_id": "task"}, execution, score, self.root / "score.json", REPORT.resolve_file, sha256)

    def test_detail_sheet_names_are_unique_legal_and_length_bounded(self):
        units = [{"unit_id": "one"}, {"unit_id": "two"}, {"unit_id": "three"}]
        labels = {"one": "model[]:" * 8, "two": "model[]:" * 8, "three": "valid@Harness"}
        names = CASES.detail_sheet_names(units, labels)
        self.assertEqual(len({n.casefold() for n in names.values()}), 3)
        for name in names.values():
            self.assertLessEqual(len(name), 31)
            self.assertNotRegex(name, r"[\\/*?:\[\]]")

    def test_checkpoint_details_exclude_component_totals_and_diagnostics(self):
        row = {"score_status": "valid", "checkpoints": {"values": {"overall_score": .6, "automated.overall_score": .6,
                "x_earned": 2, "x_max": 5, "tool_calls": 0, "ok": 1, "partial": .5}}}
        text = CASES.checkpoint_text(row, lost_only=True)
        self.assertIn("x_earned: 2", text)
        self.assertIn("partial: 0.5", text)
        self.assertNotIn("overall_score", text)
        self.assertNotIn("tool_calls", text)
        self.assertNotIn("ok", text)


if __name__ == "__main__":
    unittest.main()
