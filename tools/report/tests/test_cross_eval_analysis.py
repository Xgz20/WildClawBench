from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


REPORT_DIR = Path(__file__).resolve().parents[1]
SCRIPT_DIR = REPORT_DIR / "skills/cross-eval-analysis/scripts"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


cross_eval = load_module("cross_eval_utils_test", SCRIPT_DIR / "cross_eval_utils.py")


class CrossEvalAnalysisTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name) / "round1"
        self.tasks_dir = Path(self.temp_dir.name) / "tasks"
        task_dir = self.tasks_dir / "01_Suite"
        task_dir.mkdir(parents=True)
        for task_id, name, prompt in (
            ("01_Suite_task_alpha", "Alpha task", "考察模型能否完成文件整理并验证结果。"),
            ("01_Suite_task_beta", "Beta task", "考察模型能否进行多步规划和最终交付。"),
            ("01_Suite_task_missing", "Missing task", "不应进入共同有效任务。"),
        ):
            (task_dir / f"{task_id}.md").write_text(
                "---\n"
                f"id: {task_id}\n"
                f"name: {name}\n"
                "category: 01_Suite\n"
                "difficulty: L2\n"
                "modality: pure-text\n"
                "---\n\n"
                f"## Prompt\n{prompt}\n",
                encoding="utf-8",
            )
        for model, scores in (
            ("model-a", {"alpha": 0.9, "beta": 0.4}),
            ("model-b", {"alpha": 0.8, "beta": 0.6}),
        ):
            for suffix, score in scores.items():
                task_id = f"01_Suite_task_{suffix}"
                self._write_run(model, "astroncode", task_id, score, "completed")
            self._write_run(model, "astroncode", "01_Suite_task_missing", 0.0, "error")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_run(self, model: str, harness: str, task_id: str, score: float, status: str) -> None:
        run_dir = self.root / model / harness / "01_Suite" / task_id / "run_001"
        run_dir.mkdir(parents=True)
        (run_dir / "score.json").write_text(
            json.dumps({"overall_score": score, "check_file": score}),
            encoding="utf-8",
        )
        (run_dir / "execution_status.json").write_text(
            json.dumps({"status": status, "exit_code": 0 if status == "completed" else 1}),
            encoding="utf-8",
        )
        (run_dir / "usage.json").write_text(json.dumps({"request_count": 1}), encoding="utf-8")
        (run_dir / "chat_openclaw.jsonl").write_text(
            json.dumps({"message": {"content": [{"type": "text", "text": "完成"}]}}) + "\n",
            encoding="utf-8",
        )

    def test_model_manifest_aligns_common_valid_tasks_and_metadata(self) -> None:
        manifest = cross_eval.build_manifest(
            self.root,
            axis="model",
            fixed_harness="astroncode",
            models=["model-a", "model-b"],
            target_model="model-a",
            tasks_dir=self.tasks_dir,
        )

        self.assertEqual(manifest["target_unit"], "model-a@astroncode")
        self.assertEqual(
            manifest["scope"]["task_ids"],
            ["01_Suite_task_alpha", "01_Suite_task_beta"],
        )
        self.assertTrue(any(item["code"] == "RESULT_EXECUTION_INVALID" for item in manifest["issues"]))
        alpha = next(item for item in manifest["comparisons"] if item["task_id"].endswith("alpha"))
        self.assertEqual(alpha["task_name"], "Alpha task")
        self.assertIn("文件整理", alpha["what_tested"])
        self.assertEqual(alpha["scores"]["model-a@astroncode"]["score_pct"], 90.0)
        self.assertEqual(alpha["pairwise"][0]["delta_pct_points"], 10.0)

    def test_harness_manifest_keeps_target_variable(self) -> None:
        other_root = Path(self.temp_dir.name) / "harness-round"
        for harness, score in (("astroncode", 0.8), ("opencode", 0.7)):
            run_dir = other_root / "model-a" / harness / "01_Suite" / "01_Suite_task_alpha" / "run_001"
            run_dir.mkdir(parents=True)
            (run_dir / "score.json").write_text(json.dumps({"overall_score": score}), encoding="utf-8")
            (run_dir / "execution_status.json").write_text(json.dumps({"status": "completed", "exit_code": 0}), encoding="utf-8")
        manifest = cross_eval.build_manifest(
            other_root,
            axis="harness",
            fixed_model="model-a",
            harnesses=["astroncode", "opencode"],
            target_harness="opencode",
        )
        self.assertEqual(manifest["target_unit"], "model-a@opencode")
        self.assertEqual(manifest["comparisons"][0]["pairwise"][0]["delta_pct_points"], -10.0)

    def test_valid_model_timeout_is_included_in_capability_comparison(self) -> None:
        timeout_root = Path(self.temp_dir.name) / "timeout-round"
        task_id = "01_Suite_task_timeout"
        for model, score in (("model-a", 0.9), ("model-b", 0.4)):
            run_dir = timeout_root / model / "astroncode" / "01_Suite" / task_id / "run_001"
            run_dir.mkdir(parents=True)
            (run_dir / "score.json").write_text(
                json.dumps({"overall_score": score}), encoding="utf-8"
            )
            (run_dir / "execution_status.json").write_text(
                json.dumps({
                    "status": "timed_out",
                    "timed_out": True,
                    "exit_code": None,
                    "timeout_seconds": 300,
                }),
                encoding="utf-8",
            )
            (run_dir / "anomalies.json").write_text(
                json.dumps({
                    "validity_verdict": "PASS",
                    "has_validity_failure": False,
                    "items": [{
                        "attribution": "model",
                        "validity_impact": "none",
                        "score_reliability": "valid_capability_outcome",
                    }],
                }),
                encoding="utf-8",
            )

        manifest = cross_eval.build_manifest(
            timeout_root,
            axis="model",
            fixed_harness="astroncode",
            models=["model-a", "model-b"],
            target_model="model-a",
        )

        self.assertIn(task_id, manifest["scope"]["task_ids"])
        snapshot = manifest["comparisons"][0]["scores"]["model-b@astroncode"]["records"][0]
        self.assertFalse(snapshot["execution_usable"])
        self.assertTrue(snapshot["usable"])
        self.assertTrue(any(item["code"] == "CAPABILITY_TIMEOUT_INCLUDED" for item in manifest["issues"]))
        self.assertFalse(any(item["code"] == "RESULT_EXECUTION_INVALID" for item in manifest["issues"]))

    def test_validation_and_render_require_full_case_evidence(self) -> None:
        manifest = cross_eval.build_manifest(
            self.root,
            axis="model",
            fixed_harness="astroncode",
            models=["model-a", "model-b"],
            target_model="model-a",
            tasks_dir=self.tasks_dir,
        )
        task_id = manifest["scope"]["task_ids"][0]
        analysis = {
            "schema_version": 1,
            "executive_summary": "目标模型在整理任务上更稳，在多步交付任务上差异更集中。",
            "pair_reports": [{
                "target_unit": "model-a@astroncode",
                "reference_unit": "model-b@astroncode",
                "summary": "两侧在整理任务上接近，目标模型在该任务略高；多步交付任务需要进一步核对。",
                "strengths": [{
                    "task_id": task_id,
                    "task_name": "Alpha task",
                    "mechanism": "目标侧完成了验证闭环。",
                    "delta_pct_points": 10.0,
                    "evidence_refs": [{
                        "source": "model-a/chat_openclaw.jsonl",
                        "locator": "line 1",
                        "excerpt": "完成验证。",
                    }],
                }],
                "weaknesses": [],
                "typical_cases": [{
                    "task_id": task_id,
                    "task_name": "Alpha task",
                    "what_tested": "考察文件整理并验证结果。",
                    "score_summary": "目标 90.0，参照 80.0。",
                    "problem": "参照侧未完成最后验证。",
                    "evidence_summary": "两侧轨迹显示目标侧多了一步验证命令。",
                    "confidence": "confirmed",
                    "evidence_refs": [{
                        "source": "model-a/chat_openclaw.jsonl",
                        "locator": "line 1",
                        "excerpt": "完成验证。",
                    }],
                }],
            }],
            "comparability_analysis": {
                "summary": "原始分差包含一项时限不可比结果，正文只保留提示。",
                "scope_note": "该项需统一时限重跑后再归因。",
                "impact_rows": [{
                    "scope": "原始结果",
                    "task_count": 2,
                    "target_score": 65.0,
                    "reference_score": 70.0,
                    "delta_pct_points": -5.0,
                    "note": "未排除异常。",
                }],
            },
            "unconfirmed_items": [{
                "label": "时限不可比",
                "task_id": "01_Suite_task_beta",
                "task_name": "Beta task",
                "score_summary": "目标 40.0，参照 60.0。",
                "reason": "两侧有效时限不同。",
                "conclusion": "不进入能力归因。",
                "evidence_summary": "execution_status.json 显示时限不同。",
                "evidence_refs": [{
                    "source": "model-a/execution_status.json",
                    "locator": "timeout_seconds",
                    "excerpt": "timeout_seconds=300",
                }],
            }],
        }
        quality = cross_eval.validate_analysis(manifest, analysis)
        self.assertEqual(quality["status"], "PASS")
        report = cross_eval.render_markdown(manifest, analysis)
        self.assertIn("01_Suite_task_alpha", report)
        self.assertIn("Alpha task", report)
        self.assertIn("考察文件整理并验证结果", report)
        self.assertIn("附录：异常与不可比结果", report)
        self.assertIn("排除口径对均分的影响", report)
        self.assertIn("01_Suite_task_beta", report)
        self.assertIn("execution_status.json", report)
        self.assertNotIn("model-a/execution_status.json", report)
        self.assertNotIn("model-a/chat_openclaw.jsonl", report)

        analysis["pair_reports"][0]["strengths"].append({
            "task_id": manifest["scope"]["task_ids"][1],
            "task_name": "Beta task",
            "mechanism": "两侧在多步交付任务上得分相同。",
            "delta_pct_points": 0.0,
            "evidence_refs": [{
                "source": "model-a/chat_openclaw.jsonl",
                "locator": "line 1",
                "excerpt": "两侧均完成交付。",
            }],
        })
        quality = cross_eval.validate_analysis(manifest, analysis)
        self.assertEqual(quality["status"], "PASS")
        self.assertIn("| 0.0 |", cross_eval.render_markdown(manifest, analysis))

        analysis["pair_reports"][0]["strengths"][0]["evidence_refs"][0]["excerpt"] = ""
        quality = cross_eval.validate_analysis(manifest, analysis)
        self.assertEqual(quality["status"], "FAIL")
        self.assertTrue(any(item["code"] == "FINDING_EVIDENCE_MISSING" for item in quality["issues"]))

    def test_validation_rejects_out_of_scope_case(self) -> None:
        manifest = cross_eval.build_manifest(
            self.root,
            axis="model",
            fixed_harness="astroncode",
            models=["model-a", "model-b"],
        )
        analysis = {
            "executive_summary": "总结",
            "pair_reports": [{
                "target_unit": "model-a@astroncode",
                "reference_unit": "model-b@astroncode",
                "summary": "总结",
                "strengths": [],
                "weaknesses": [],
                "typical_cases": [{"task_id": "not_in_manifest"}],
            }],
        }
        quality = cross_eval.validate_analysis(manifest, analysis)
        self.assertEqual(quality["status"], "FAIL")
        self.assertTrue(any(item["code"] == "CASE_TASK_OUT_OF_SCOPE" for item in quality["issues"]))


if __name__ == "__main__":
    unittest.main()
