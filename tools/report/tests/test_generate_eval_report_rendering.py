import unittest

from tools.report.scripts import generate_eval_report


def _summary(cost_usd):
    return {
        "overview": {
            "unit_count": 1,
            "total_tasks": 1,
            "average_score": 0.956,
        },
        "run_summaries": [
            {
                "run_label": "xopglm51@DeepSeek Harness",
                "average_score": 0.956,
                "total_tokens": 1234,
                "cost_usd": cost_usd,
                "error_count": 0,
                "timeout_count": 0,
                "evaluation_anomaly_count": 0,
            }
        ],
        "case_comparisons": [],
        "capability_comparison": {},
        "dimension_comparisons": {},
        "diff_matrix": [],
    }


class ReportRenderingTest(unittest.TestCase):
    def test_unavailable_cost_renders_as_dash(self):
        summary = _summary(None)

        markdown = generate_eval_report.render_markdown(summary)
        html = generate_eval_report.render_html(summary)

        self.assertIn("| 1,234 | - |", markdown)
        self.assertIn("<td>1,234</td><td>-</td>", html)

    def test_available_cost_keeps_four_decimal_places(self):
        summary = _summary(1.2)

        markdown = generate_eval_report.render_markdown(summary)
        html = generate_eval_report.render_html(summary)

        self.assertIn("| 1,234 | 1.2000 |", markdown)
        self.assertIn("<td>1,234</td><td>1.2000</td>", html)


if __name__ == "__main__":
    unittest.main()
