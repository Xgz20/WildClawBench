import copy
import importlib.util
from pathlib import Path
import unittest
from types import SimpleNamespace

PATH = Path(__file__).resolve().parents[2] / "tools/report/skills/general-e2e/report-general-e2e/scripts/leader_report.py"
spec = importlib.util.spec_from_file_location("leader_token_comparison", PATH)
LEADER = importlib.util.module_from_spec(spec)
spec.loader.exec_module(LEADER)


def fixture(values, statuses, target=0):
    labels = [f"Model{i}@Harness{i}" for i in range(len(values))]
    return {"target": {"label": labels[target]}, "scope": {"unique_task_count": 60},
            "tables": {"效率对比": {"rows": [[label, None, value] for label, value in zip(labels, values)],
                "cell_annotations": {f"{i}:2": {"status": status, "complete_cases": 59 if status == "partial" else 60,
                                               "partial_cases": 1 if status == "partial" else 0, "total_cases": 60}
                                     for i, status in enumerate(statuses)}}}}


def tool_fixture(totals, statuses, cases=None, target=0):
    cases = cases or [60] * len(totals)
    labels = [f"Model{i}@Harness{i}" for i in range(len(totals))]
    groups = [{"title": label, "rows": [[label, "全部工具", total, "覆盖见注释"]],
               "cell_annotations": {"0:2": {"status": status, "total_cases": n}}}
              for label, total, status, n in zip(labels, totals, statuses, cases)]
    return {"target": {"label": labels[target]}, "tables": {
        "总览": {"rows": [[label, None, n] for label, n in zip(labels, cases)]},
        "工具调用对比": {"groups": groups}}}


def comparison_fixture():
    units = [{"unit_id": uid, "harness": {"id": harness, "version": version}}
             for uid, harness, version in [("target", "studio", "3.5"), ("peer", "studio", "3.5"),
                                          ("old", "studio", "3.3"), ("external", "other", "1.0")]]
    labels = {u["unit_id"]: f"{u['unit_id']}@{u['harness']['id']} {u['harness']['version']}" for u in units}
    source = {"units": units, "presentation": {"unit_labels": labels}}
    order = [labels[u["unit_id"]] for u in units]
    def table(headers, rows):
        return {"headers": headers, "rows": rows, "formats": {"1": "0.00", "2": "0.00"}, "notes": []}
    tables = {"总览": table(["模型@Harness", "总平均分", "用例数"], [[label, score, 60] for label, score in zip(order, [90, 80, 98, 100])]),
              "效率对比": table(["模型@Harness", "总 Token", "平均 Token"], [[label, 60*v, v] for label, v in zip(order, [100, 200, 300, 50])])}
    tables["效率对比"]["cell_annotations"] = {f"{i}:2": {"status": "complete", "complete_cases": 60, "total_cases": 60} for i in range(4)}
    for name in LEADER.DIMENSIONS:
        tables[name] = table(["模型@Harness", "总平均分", "维度甲", "维度乙"],
                             [[label, 90, a, b] for label, a, b in zip(order, [90.004, 89.996, 99, 100], [70, 80, 100, 100])])
    timing = table(["模型@Harness", "总任务耗时(s)", "总模型耗时(s)", "总模型耗时占比", "平均任务耗时(s)",
                    "平均模型耗时(s)", "任务耗时P50(s)", "模型耗时P50(s)", "任务耗时P90(s)", "模型耗时P90(s)"],
                   [[label, 60*v, None, None, v, None, v, None, v, None] for label, v in zip(order, [10, 20, 100, 1])])
    timing["coverage_table"] = table(["模型@Harness", "模型耗时完整用例"], [[label, "0/60"] for label in order])
    tables["效率对比"]["timing_table"] = timing
    tool = tool_fixture([100, 200, 300, 50], ["complete"]*4)["tables"]["工具调用对比"]
    for group, label in zip(tool["groups"], order):
        group["title"] = label
        group["rows"][0][0] = label
        group["headers"] = ["模型@Harness", "工具", "调用数", "计数覆盖"]
    tool["formats"] = {"2": "#,##0"};tool["notes"] = [];tables["工具调用对比"] = tool
    data = {"target": {"label": labels["target"], "harness": "studio"},
            "scope": {"unique_task_count": 60, "unit_count": 4}, "tables": tables,
            "comparison_context": LEADER.comparison_context(source, "target"),
            "dimensions": {name: {"combination_view": tables[name]["rows"]} for name in LEADER.DIMENSIONS}}
    return source, data, labels


class GeneralLeaderScopeAndLayoutTests(unittest.TestCase):
    def test_same_client_version_is_primary_and_all_comparison_rows_remain(self):
        source, data, labels = comparison_fixture()
        before = copy.deepcopy(data)
        self.assertEqual(data["comparison_context"]["primary_unit_ids"], ["peer"])
        text = LEADER.summaries(data)
        self.assertIn(labels["peer"], text["分类对比"])
        self.assertNotIn(labels["old"], text["分类对比"])
        self.assertNotIn(labels["external"], text["分类对比"])
        self.assertIn(labels["external"], text["总览"])
        self.assertNotIn(labels["external"], text["效率对比"])
        self.assertIn("0.50", text["效率对比"])
        self.assertEqual(data, before)
        self.assertTrue(all(len(data["tables"][name]["rows"]) == 4 for name in LEADER.DIMENSIONS))

    def test_differences_use_unrounded_scores_and_secondary_reference_is_explicit(self):
        source, data, labels = comparison_fixture()
        source["leader_config"] = {"secondary_tables": ["难度对比"]}
        data["comparison_context"] = LEADER.comparison_context(source, "target")
        text = LEADER.summaries(data)
        self.assertIn("维度甲高 0.01 分", text["分类对比"])
        self.assertIn(labels["external"], text["难度对比"])
        self.assertNotIn(labels["external"], text["总览"])
        source["leader_config"]["secondary_tables"] = ["not-a-table"]
        with self.assertRaisesRegex(ValueError, "SECONDARY_CONFIG_INVALID"):
            LEADER.comparison_context(source, "target")

    def test_no_matching_version_falls_back_and_all_scope_is_available(self):
        source, _, _ = comparison_fixture()
        source["units"][1]["harness"]["version"] = "3.4"
        context = LEADER.comparison_context(source, "target")
        self.assertEqual(context["primary_scope"], "all-combinations")
        self.assertEqual(context["fallback_reason"], "no-same-version-peer")
        self.assertIsNone(context["fixed_version"])
        source["units"][1]["harness"]["version"] = "3.5"
        source["leader_config"] = {"comparison_scope": "all-combinations"}
        self.assertEqual(len(LEADER.comparison_context(source, "target")["primary_unit_ids"]), 3)

    def test_filtering_resource_peers_preserves_original_partial_coverage_indices(self):
        data = fixture([None, 100, 20, 5], ["unavailable", "complete", "partial", "complete"], target=1)
        result = LEADER.average_token_comparisons(data, ["Model2@Harness2"])
        self.assertEqual(len(result["comparisons"]), 1)
        self.assertEqual(result["comparisons"][0]["basis"], "upper_bound")
        self.assertEqual(result["unavailable_peers"], [])
        self.assertEqual(result["comparisons"][0]["ratio"], 5)

    def test_token_and_task_timing_summaries_are_in_their_own_subsections(self):
        _, data, _ = comparison_fixture()
        data["narratives"] = LEADER.summaries(data)
        token = data["narratives"]["效率对比"]
        timing = data["narratives"]["任务耗时对比"]
        markdown = LEADER.render(data)
        self.assertIn("### Token对比\n\n" + token + "\n\n|", markdown)
        self.assertIn("### 任务耗时对比\n\n" + timing + "\n\n|", markdown)
        self.assertEqual(markdown.count(timing), 1)
        self.assertLess(markdown.index(token), markdown.index("### 任务耗时对比"))
        # Previously saved leader JSON stored both paragraphs in one field.
        del data["narratives"]["任务耗时对比"]
        data["narratives"]["效率对比"] = token + "\n\n" + timing
        self.assertIn("### 任务耗时对比\n\n" + timing + "\n\n|", LEADER.render(data))

    def test_cli_options_do_not_allow_a_peer_scope_without_a_target(self):
        args = SimpleNamespace(target_unit=None, leader_comparison_scope="same-harness-version")
        with self.assertRaisesRegex(ValueError, "REQUIRE_TARGET"):
            LEADER.configure({}, args)


class GeneralLeaderToolComparisonTests(unittest.TestCase):
    def test_tool_ratios_follow_target_and_use_each_frozen_denominator(self):
        data = tool_fixture([596, 903, 799], ["complete"] * 3, cases=[60, 60, 30], target=1)
        result = LEADER.tool_call_comparisons(data)
        self.assertEqual(result["target"]["label"], "Model1@Harness1")
        self.assertEqual(result["target"]["total_calls"], 903)
        self.assertEqual(result["target"]["average_calls"], 15.05)
        peers = {peer["label"]: peer for peer in result["comparisons"]}
        self.assertAlmostEqual(peers["Model0@Harness0"]["ratio"], 903 / 596)
        self.assertEqual(peers["Model0@Harness0"]["display_ratio"], "1.52")
        self.assertAlmostEqual(peers["Model2@Harness2"]["ratio"], (903 / 60) / (799 / 30))
        self.assertEqual(peers["Model2@Harness2"]["display_ratio"], "0.57")
        self.assertTrue(LEADER.render_tool_call_summary(result).startswith("Model1@Harness1"))
        data["target"]["label"] = "Model0@Harness0"
        self.assertEqual(LEADER.tool_call_comparisons(data)["target"]["total_calls"], 596)

    def test_partial_counts_keep_comparison_bounds_and_skip_missing_zero_invalid(self):
        data = tool_fixture([10, 20, 25, 0, None, False, -1, float("nan")],
                            ["partial", "partial", "complete", "complete", "unavailable", "complete", "complete", "complete"])
        result = LEADER.tool_call_comparisons(data)
        self.assertEqual([peer["basis"] for peer in result["comparisons"]], ["observed_values_only", "lower_bound"])
        self.assertEqual(result["zero_peers"], ["Model3@Harness3"])
        self.assertEqual(len(result["unavailable_peers"]), 4)
        self.assertIn("下限", LEADER.render_tool_call_summary(result))
        data["tables"]["工具调用对比"]["groups"][0]["cell_annotations"]["0:2"]["status"] = "complete"
        self.assertEqual(LEADER.tool_call_comparisons(data)["comparisons"][0]["basis"], "upper_bound")
        data["tables"]["工具调用对比"]["groups"][0]["rows"][0][2] = 0
        self.assertEqual(LEADER.tool_call_comparisons(data)["comparisons"][0]["ratio"], 0)
        data["tables"]["工具调用对比"]["groups"][0]["rows"][0][2] = None
        self.assertEqual(LEADER.tool_call_comparisons(data)["comparisons"], [])

    def test_tool_composition_share_uses_known_detail_scope_and_preserves_source(self):
        data = tool_fixture([100, 20], ["complete"] * 2)
        group = data["tables"]["工具调用对比"]["groups"][0]
        group["rows"] += [[group["title"], name, n, "计数完整"] for name, n in [("read", 10), ("bash", 25), ("write", 5), ("exec", 60)]]
        before = copy.deepcopy(data)
        result = LEADER.tool_call_comparisons(data)
        self.assertEqual([tool["name"] for tool in result["composition"]["tools"]], ["exec", "bash", "read"])
        self.assertEqual(result["composition"]["share"], .95)
        self.assertEqual(result["composition"]["basis"], "complete_calls")
        self.assertEqual(data, before)
        group["rows"][-1][2] = 30
        group["rows"][-1][3] = "部分计数"
        result = LEADER.tool_call_comparisons(data)
        self.assertEqual(result["composition"]["known_detail_calls"], 70)
        self.assertEqual(result["composition"]["basis"], "known_detail_calls")
        self.assertIn("已知工具明细计数", LEADER.render_tool_call_summary(result))


class GeneralLeaderTokenComparisonTests(unittest.TestCase):
    def test_ratios_use_unrounded_values_and_follow_selected_target(self):
        data = fixture([0.01001, 0.01449, 0.02], ["complete"] * 3, target=1)
        result = LEADER.average_token_comparisons(data)
        self.assertEqual(result["target_label"], "Model1@Harness1")
        peers = {x["peer_label"]: x for x in result["comparisons"]}
        self.assertAlmostEqual(peers["Model0@Harness0"]["ratio"], 0.01449 / 0.01001)
        self.assertEqual(peers["Model0@Harness0"]["display_ratio"], "1.45")
        self.assertEqual(peers["Model2@Harness2"]["display_ratio"], "0.72")
        self.assertTrue(all(x["basis"] == "complete" for x in peers.values()))
        self.assertTrue(LEADER.render_efficiency_summary(data, result).startswith("Model1@Harness1"))

    def test_partial_target_is_lower_bound_only_against_complete_peer(self):
        data = fixture([1336388.9166666667, 389951.18333333335, 534787.6166666667, 457031.98333333334, None],
                       ["partial", "complete", "complete", "complete", "unavailable"])
        result = LEADER.average_token_comparisons(data)
        self.assertEqual([x["display_ratio"] for x in result["comparisons"]], ["3.43", "2.50", "2.92"])
        self.assertTrue(all(x["basis"] == "lower_bound" for x in result["comparisons"]))
        self.assertEqual(result["unavailable_peers"], ["Model4@Harness4"])
        text = LEADER.render_efficiency_summary(data, result)
        self.assertIn("消耗下限", text)
        self.assertIn("59 题完整、1 题部分", text)
        self.assertNotIn("Model4@Harness4 的", text)

    def test_partial_denominator_does_not_become_lower_bound(self):
        data = fixture([100, 20, 25], ["partial", "partial", "complete"])
        result = LEADER.average_token_comparisons(data)
        self.assertEqual([x["basis"] for x in result["comparisons"]], ["observed_values_only", "lower_bound"])
        self.assertIn("不代表全量精确消耗比", LEADER.render_efficiency_summary(data, result))
        data["tables"]["效率对比"]["cell_annotations"]["0:2"]["status"] = "complete"
        self.assertEqual(LEADER.average_token_comparisons(data)["comparisons"][0]["basis"], "upper_bound")

    def test_missing_zero_and_invalid_peers_never_divide_or_impute(self):
        data = fixture([10, 0, None, False, float("nan"), -1], ["complete"] * 6)
        before = copy.deepcopy(data["tables"]["效率对比"]["rows"][:4])
        result = LEADER.average_token_comparisons(data)
        self.assertEqual(result["comparisons"], [])
        self.assertEqual(result["zero_peers"], ["Model1@Harness1"])
        self.assertEqual(len(result["unavailable_peers"]), 4)
        self.assertEqual(data["tables"]["效率对比"]["rows"][:4], before)
        text = LEADER.render_efficiency_summary(data, result)
        self.assertIn("倍数不适用", text)

    def test_missing_target_has_no_ratios_and_real_zero_is_preserved(self):
        data = fixture([None, 10], ["unavailable", "complete"])
        result = LEADER.average_token_comparisons(data)
        self.assertIsNone(result["target_average_tokens"])
        self.assertEqual(result["comparisons"], [])
        self.assertIn("不可用", LEADER.render_efficiency_summary(data, result))
        data["tables"]["效率对比"]["rows"][0][2] = 0
        result = LEADER.average_token_comparisons(data)
        self.assertEqual(result["target_average_tokens"], 0)
        self.assertEqual(result["comparisons"][0]["ratio"], 0)


if __name__ == "__main__":
    unittest.main()
