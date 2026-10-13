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
