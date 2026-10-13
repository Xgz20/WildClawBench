import copy
import importlib.util
from pathlib import Path
import unittest

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
