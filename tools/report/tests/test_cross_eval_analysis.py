from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from src.utils.anomalies import RULESET_VERSION, SCHEMA_VERSION


REPORT_DIR = Path(__file__).resolve().parents[1]
SCRIPT_DIR = REPORT_DIR / "skills/cross-eval-analysis/scripts"
REPORT_SCRIPTS_DIR = REPORT_DIR / "scripts"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


cross_eval = load_module("cross_eval_utils_test", SCRIPT_DIR / "cross_eval_utils.py")
workspace_paths = load_module(
    "report_workspace_paths_test", REPORT_SCRIPTS_DIR / "report_workspace_paths.py"
)


def _anomalies(verdict="PASS", items=None):
    items = list(items or [])
    return {
        "schema_version": SCHEMA_VERSION,
        "ruleset_version": RULESET_VERSION,
        "validity_verdict": verdict,
        "is_anomalous": bool(items),
        "has_error": verdict == "FAIL",
        "has_validity_failure": verdict == "FAIL",
        "has_model_or_harness_issue": any(
            item.get("attribution") in {"model", "harness"} for item in items
        ),
        "needs_review": verdict == "REVIEW",
        "needs_rerun": any(
            item.get("rerun_action") == "required_after_fix" for item in items
        ),
        "items": items,
    }


def _write_anomalies(run_dir: Path, verdict="PASS", items=None) -> None:
    (run_dir / "anomalies.json").write_text(
        json.dumps(_anomalies(verdict, items)), encoding="utf-8"
    )


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
        _write_anomalies(run_dir)

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

    def test_model_manifest_rescans_stale_anomalies_before_comparison(self) -> None:
        task_id = "01_Suite_task_alpha"
        run_dir = (
            self.root / "model-a" / "astroncode" / "01_Suite" /
            task_id / "run_001"
        )
        (run_dir / "score.json").write_text(
            json.dumps({
                "overall_score": 0.9,
                "_grading": {
                    "llm_notes": "judge failed: judge returned no valid JSON",
                },
            }),
            encoding="utf-8",
        )
        stale = _anomalies()
        stale["ruleset_version"] = "obsolete"
        stale_text = json.dumps(stale)
        (run_dir / "anomalies.json").write_text(stale_text, encoding="utf-8")

        manifest = cross_eval.build_manifest(
            self.root,
            axis="model",
            fixed_harness="astroncode",
            models=["model-a", "model-b"],
            target_model="model-a",
            tasks_dir=self.tasks_dir,
        )

        self.assertEqual(manifest["scope"]["task_ids"], ["01_Suite_task_beta"])
        self.assertTrue(any(
            item["code"] == "RESULT_VALIDITY_INVALID"
            and item["task_id"] == task_id
            for item in manifest["issues"]
        ))
        self.assertEqual(
            (run_dir / "anomalies.json").read_text(encoding="utf-8"),
            stale_text,
        )

    def test_harness_manifest_keeps_target_variable(self) -> None:
        other_root = Path(self.temp_dir.name) / "harness-round"
        for harness, score in (("astroncode", 0.8), ("opencode", 0.7)):
            run_dir = other_root / "model-a" / harness / "01_Suite" / "01_Suite_task_alpha" / "run_001"
            run_dir.mkdir(parents=True)
            (run_dir / "score.json").write_text(json.dumps({"overall_score": score}), encoding="utf-8")
            (run_dir / "execution_status.json").write_text(json.dumps({"status": "completed", "exit_code": 0}), encoding="utf-8")
            _write_anomalies(run_dir)
        manifest = cross_eval.build_manifest(
            other_root,
            axis="harness",
            fixed_model="model-a",
            harnesses=["astroncode", "opencode"],
            target_harness="opencode",
        )
        self.assertEqual(manifest["target_unit"], "model-a@opencode")
        self.assertEqual(manifest["comparisons"][0]["pairwise"][0]["delta_pct_points"], -10.0)

    def test_same_round_workspace_defaults_under_round(self) -> None:
        comparison_id = workspace_paths.build_cross_eval_comparison_id(
            axis="harness",
            fixed_model="model-a",
            fixed_harness=None,
            models=None,
            harnesses=["astroncode", "opencode"],
            target_model=None,
            target_harness="astroncode",
            timestamp="20260831_120000",
        )
        workspace, source_map = workspace_paths.resolve_cross_eval_workspace(
            result_root=self.root,
            comparison_scope="same-round",
            comparison_id=comparison_id,
        )

        self.assertIsNone(source_map)
        self.assertEqual(
            workspace,
            self.root.resolve()
            / "report-workspace"
            / "cross-eval"
            / "harness_astroncode_vs_opencode_on_model-a_20260831_120000",
        )

    def test_cross_round_workspace_uses_neutral_reports_root(self) -> None:
        custom_root = Path(self.temp_dir.name) / "custom"
        combined = custom_root / "round2" / "report-workspace" / "combined"
        result_root = combined / "results"
        result_root.mkdir(parents=True)
        source_map = combined / "SOURCE_MAP.tsv"
        source_map.write_text(
            f"{custom_root / 'round1/model-a/astroncode'}\tmodel-a@astroncode-old\n"
            f"{custom_root / 'round2/model-a/astroncode'}\tmodel-a@astroncode-new\n",
            encoding="utf-8",
        )

        workspace, detected = workspace_paths.resolve_cross_eval_workspace(
            result_root=result_root,
            comparison_scope="cross-round",
            comparison_id="astroncode-version-change",
        )

        self.assertEqual(detected, source_map.resolve())
        self.assertEqual(
            workspace,
            custom_root.resolve()
            / "reports"
            / "cross-round"
            / "cross-eval"
            / "astroncode-version-change",
        )

    def test_synthetic_cross_round_root_requires_explicit_scope(self) -> None:
        custom_root = Path(self.temp_dir.name) / "custom"
        combined = custom_root / "round2" / "report-workspace" / "combined"
        result_root = combined / "results"
        result_root.mkdir(parents=True)
        (combined / "SOURCE_MAP.tsv").write_text(
            f"{custom_root / 'round1/model-a/astroncode'}\told\n"
            f"{custom_root / 'round2/model-a/astroncode'}\tnew\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "comparison-scope cross-round"):
            workspace_paths.resolve_cross_eval_workspace(
                result_root=result_root,
                comparison_scope="same-round",
                comparison_id="invalid",
            )

    def test_round_trend_output_uses_neutral_reports_root(self) -> None:
        custom_root = Path(self.temp_dir.name) / "custom"
        output = workspace_paths.resolve_cross_round_trend_build_dir(
            [custom_root / "round1", custom_root / "round2"],
            unit="model-a@astroncode",
            timestamp="20260831_120000",
        )

        self.assertEqual(
            output,
            custom_root.resolve()
            / "reports"
            / "cross-round"
            / "trend"
            / "model-a@astroncode__round1_round2"
            / "builds"
            / "20260831_120000",
        )

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
            _write_anomalies(run_dir, items=[{
                        "attribution": "model",
                        "validity_impact": "none",
                        "score_reliability": "valid_capability_outcome",
                    }])

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

    def test_render_evidence_identifies_unit_without_leaking_absolute_path(self) -> None:
        other_root = Path(self.temp_dir.name) / "harness-evidence-round"
        task_id = "01_Suite_task_alpha"
        for harness, score in (("astroncode", 0.9), ("deepseek-harness", 0.8)):
            run_dir = other_root / "model-a" / harness / "01_Suite" / task_id / "run_001"
            run_dir.mkdir(parents=True)
            (run_dir / "score.json").write_text(
                json.dumps({"overall_score": score}), encoding="utf-8"
            )
            (run_dir / "execution_status.json").write_text(
                json.dumps({"status": "completed", "exit_code": 0}), encoding="utf-8"
            )
            (run_dir / "chat_openclaw.jsonl").write_text(
                json.dumps({"message": {"content": [{"type": "text", "text": "完成"}]}})
                + "\n",
                encoding="utf-8",
            )
            _write_anomalies(run_dir)
        manifest = cross_eval.build_manifest(
            other_root,
            axis="harness",
            fixed_model="model-a",
            harnesses=["astroncode", "deepseek-harness"],
            target_harness="astroncode",
            tasks_dir=self.tasks_dir,
        )
        for unit in manifest["units"]:
            unit["model_display"] = "Model A"
            unit["harness_display"] = {
                "astroncode": "AstronCode",
                "deepseek-harness": "DeepSeek Harness",
            }[unit["harness"]]
        comparison = manifest["comparisons"][0]
        astron_record = comparison["scores"]["model-a@astroncode"]["records"][0]
        deepseek_record = comparison["scores"]["model-a@deepseek-harness"]["records"][0]
        analysis = {
            "schema_version": 1,
            "executive_summary": "两侧证据需要明确区分所属评测单元。",
            "pair_reports": [{
                "target_unit": "model-a@astroncode",
                "reference_unit": "model-a@deepseek-harness",
                "summary": "对比同一任务的两侧轨迹。",
                "strengths": [],
                "weaknesses": [],
                "typical_cases": [{
                    "task_id": task_id,
                    "task_name": "Alpha task",
                    "what_tested": "考察文件整理并验证结果。",
                    "score_summary": "目标 90.0，参照 80.0。",
                    "problem": "两侧完成路径不同。",
                    "evidence_summary": "同名证据文件来自不同评测单元。",
                    "confidence": "confirmed",
                    "evidence_refs": [
                        {
                            "source": astron_record["transcript"],
                            "locator": "line 1",
                            "excerpt": "AstronCode 侧完成验证。",
                        },
                        {
                            "source": deepseek_record["score_path"].replace("/", "\\"),
                            "locator": "overall_score",
                            "excerpt": "DeepSeek Harness 侧得分为 0.8。",
                        },
                        {
                            "source": "/Users/example/external/task_definition.md",
                            "locator": "Prompt",
                            "excerpt": "外部任务定义。",
                        },
                    ],
                }],
            }],
            "unconfirmed_items": [],
        }

        self.assertEqual(cross_eval.validate_analysis(manifest, analysis)["status"], "PASS")
        report = cross_eval.render_markdown(manifest, analysis)

        self.assertIn("Model A@AstronCode / chat_openclaw.jsonl", report)
        self.assertIn("Model A@DeepSeek Harness / score.json", report)
        self.assertIn("task_definition.md（Prompt）", report)
        self.assertNotIn("/Users/example/external", report)
        self.assertNotIn(str(other_root), report)

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
