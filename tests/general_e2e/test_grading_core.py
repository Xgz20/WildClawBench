from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.utils import grading as legacy_grading
from src.utils.task_parser import parse_task_md
from src.wildclawbench_grading_core import (
    CORE_VERSION,
    GradingCoreError,
    build_evidence_index,
    evaluate_semantics,
    finalize_score,
    inspect_rule_dependencies,
    run_rules,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = REPO_ROOT / "eval_general_e2e/datasets/manifests/general-custom60-v1.json"
AUDIT = REPO_ROOT / "eval_general_e2e/datasets/audits/general-custom60-v1-capability-matrix.json"


def local_fixture_executor(source: str, context: dict) -> dict:
    namespace: dict = {}
    exec(compile(source, "<grading-fixture>", "exec"), namespace)
    return namespace["grade"](
        transcript=context["transcript"],
        workspace_path=context["workspace_path"],
    )


class GradingCoreTests(unittest.TestCase):
    def test_public_api_and_same_fixture_match_legacy_combiner(self) -> None:
        self.assertEqual(CORE_VERSION, "0.2.0")
        source = """
def grade(transcript: list, workspace_path: str) -> dict:
    assert workspace_path == "/tmp_workspace"
    assert transcript == [{"event_id": "event-0001"}]
    return {"rule_accuracy": 0.8, "overall_score": 0.8}
"""
        rules = run_rules(
            source,
            executor=local_fixture_executor,
            workspace_path="/tmp_workspace",
            transcript=[{"event_id": "event-0001"}],
            expected_keys=["rule_accuracy"],
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence_path = root / "private-scoring/rule-result.json"
            evidence_path.parent.mkdir(parents=True)
            evidence_path.write_text('{"score":0.8}\n', encoding="utf-8")
            evidence = build_evidence_index(
                [{
                    "type": "rule_result",
                    "path": "private-scoring/rule-result.json",
                    "event_ids": ["event-0001"],
                }],
                base_dir=root,
                known_event_ids={"event-0001"},
            )
        reference = evidence["entries"][0]["reference"]

        def semantic_evaluator(_criteria, _evidence):
            return {
                "criteria": [{
                    "key": "answer_quality",
                    "status": "judged",
                    "score": 0.5,
                    "reason": "冻结证据支持该检查点采用中间分值档位。",
                    "evidence": [reference],
                }],
                "notes": "fixture",
            }

        semantics = evaluate_semantics(
            [{
                "key": "answer_quality",
                "weight": 1.0,
                "allowed_scores": [0.0, 0.5, 1.0],
            }],
            evaluator=semantic_evaluator,
            evidence_index=evidence,
            protocol="codex-agent-judge-v1",
        )
        final = finalize_score(
            grading_type="hybrid",
            grading_weights={"automated": 0.7, "llm_judge": 0.3},
            rules=rules,
            semantics=semantics,
        )
        legacy = legacy_grading._combine_v2(
            0.8,
            {"rule_accuracy": 0.8},
            0.5,
            {"answer_quality": 0.5},
            "fixture",
            {"automated": 0.7, "llm_judge": 0.3},
        )
        self.assertEqual(rules["score"], 0.8)
        self.assertEqual(
            rules["schema_version"],
            "wildclawbench.general-e2e-rule-component/v2",
        )
        self.assertEqual(rules["criteria"][0]["decision"]["anchor"], "partial_score")
        self.assertEqual(rules["criteria"][0]["decision"]["result_key"], "rule_accuracy")
        self.assertIn("部分得分", rules["criteria"][0]["reason"])
        self.assertEqual(
            rules["criteria"][0]["evidence"],
            [{"type": "managed_rule_result", "result_key": "rule_accuracy"}],
        )
        self.assertEqual(semantics["score"], 0.5)
        self.assertEqual(final["result"], {
            "valid": True,
            "total_score": 0.71,
            "invalid_reason": None,
        })
        self.assertEqual(final["result"]["total_score"], legacy["overall_score"])

    def test_all_sixty_rule_imports_have_complete_dependency_mapping(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        audit = json.loads(AUDIT.read_text(encoding="utf-8"))
        audit_by_task = {row["task_id"]: row for row in audit["tasks"]}
        external_roots: set[str] = set()
        self.assertEqual(len(manifest["tasks"]), 60)
        self.assertEqual(set(audit_by_task), {
            row["task_id"] for row in manifest["tasks"]
        })
        for row in manifest["tasks"]:
            task_id = row["task_id"]
            task = parse_task_md(REPO_ROOT / row["source"]["task_path"])
            discovered = inspect_rule_dependencies(task["automated_checks"])
            expected = audit_by_task[task_id]["automated_checks"]
            with self.subTest(task_id=task_id):
                self.assertEqual(
                    set(discovered["imports"]),
                    {name.split(".", 1)[0] for name in expected["imports"]},
                )
                self.assertEqual(
                    {item["import_root"] for item in discovered["external"]},
                    set(expected["external_imports"]),
                )
                self.assertFalse(expected["embedded_judge"]["detected"])
            external_roots.update(
                item["import_root"] for item in discovered["external"]
            )
        self.assertEqual(external_roots, {"yaml", "playwright"})

    def test_unknown_and_dynamic_rule_dependencies_fail_closed(self) -> None:
        with self.assertRaisesRegex(
            GradingCoreError, "RULE_DEPENDENCY_UNDECLARED"
        ):
            inspect_rule_dependencies("import unknown_grading_package")
        with self.assertRaisesRegex(
            GradingCoreError, "RULE_DYNAMIC_IMPORT_UNSUPPORTED"
        ):
            inspect_rule_dependencies("import importlib\nimportlib.import_module('yaml')")

    def test_rule_values_and_keys_are_strict(self) -> None:
        source = "def grade(**kwargs): return {'quality': True, 'overall_score': 1.0}"
        with self.assertRaisesRegex(GradingCoreError, "SCORE_VALUE_INVALID"):
            run_rules(
                source,
                executor=local_fixture_executor,
                workspace_path="/tmp_workspace",
                expected_keys=["quality"],
            )

    def test_rule_criteria_explain_full_zero_and_partial_scores_in_chinese(self) -> None:
        source = "def grade(**kwargs): return {}"
        values = {"full": 1.0, "zero": 0.0, "partial": 0.5, "overall_score": 0.5}
        component = run_rules(
            source,
            executor=lambda _rule, _context: values,
            workspace_path="/tmp_workspace",
            expected_keys=["full", "zero", "partial"],
        )
        rows = {row["key"]: row for row in component["criteria"]}
        self.assertEqual(rows["full"]["decision"]["anchor"], "full_score")
        self.assertEqual(rows["zero"]["decision"]["anchor"], "zero_score")
        self.assertEqual(rows["partial"]["decision"]["anchor"], "partial_score")
        self.assertIn("达到满分", rows["full"]["reason"])
        self.assertIn("命中零分", rows["zero"]["reason"])
        self.assertIn("部分得分", rows["partial"]["reason"])

    def test_semantic_reason_must_be_a_chinese_explanation(self) -> None:
        evidence = build_evidence_index([
            {"type": "transcript", "event_ids": ["event-0001"]}
        ], known_event_ids={"event-0001"})
        reference = evidence["entries"][0]["reference"]

        def evaluator(_criteria, _evidence):
            return {
                "criteria": [{
                    "key": "quality",
                    "status": "judged",
                    "score": 1.0,
                    "reason": "The frozen evidence supports a full score.",
                    "evidence": [reference],
                }]
            }

        with self.assertRaisesRegex(
            GradingCoreError, "SEMANTIC_REASON_LANGUAGE_INVALID"
        ):
            evaluate_semantics(
                [{"key": "quality", "weight": 1.0, "allowed_scores": [0.0, 1.0]}],
                evaluator=evaluator,
                evidence_index=evidence,
                protocol="codex-agent-judge-v1",
            )
        source = "def grade(**kwargs): return {'renamed': 1.0, 'overall_score': 1.0}"
        with self.assertRaisesRegex(GradingCoreError, "RULE_RESULT_KEYS_MISMATCH"):
            run_rules(
                source,
                executor=lambda rule, context: {"renamed": 1.0, "overall_score": 1.0},
                workspace_path="/tmp_workspace",
                expected_keys=["quality"],
            )

    def test_evidence_digest_event_and_path_validation_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "evidence.json").write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(
                GradingCoreError, "EVIDENCE_DIGEST_MISMATCH"
            ):
                build_evidence_index(
                    [{
                        "type": "rule_result",
                        "path": "evidence.json",
                        "sha256": "0" * 64,
                    }],
                    base_dir=root,
                )
            with self.assertRaisesRegex(
                GradingCoreError, "EVIDENCE_EVENT_MISSING"
            ):
                build_evidence_index(
                    [{
                        "type": "transcript",
                        "event_ids": ["event-missing"],
                    }],
                    known_event_ids={"event-known"},
                )
            with self.assertRaisesRegex(
                GradingCoreError, "EVIDENCE_PATH_INVALID"
            ):
                build_evidence_index(
                    [{"type": "file", "path": "../escape"}], base_dir=root
                )

    def test_unresolved_semantics_make_total_invalid_without_zero_fallback(self) -> None:
        evidence = build_evidence_index([
            {"type": "transcript", "event_ids": ["event-0001"]}
        ], known_event_ids={"event-0001"})

        def evaluator(_criteria, _evidence):
            return {
                "criteria": [{
                    "key": "quality",
                    "status": "unresolved",
                    "score": None,
                    "reason": "完成该检查点判定所需的冻结证据缺失。",
                    "evidence": [],
                }]
            }

        semantics = evaluate_semantics(
            [{"key": "quality", "weight": 1.0}],
            evaluator=evaluator,
            evidence_index=evidence,
            protocol="api-judge-v1",
        )
        rules = run_rules(
            "",
            executor=None,
            workspace_path="/tmp_workspace",
        )
        final = finalize_score(
            grading_type="llm_judge",
            grading_weights={"automated": 0.0, "llm_judge": 1.0},
            rules=rules,
            semantics=semantics,
        )
        self.assertEqual(semantics["status"], "evaluation_error")
        self.assertFalse(final["result"]["valid"])
        self.assertIsNone(final["result"]["total_score"])

    def test_all_not_applicable_semantics_remain_invalid(self) -> None:
        evidence = build_evidence_index([])

        def evaluator(_criteria, _evidence):
            return {
                "criteria": [{
                    "key": "quality",
                    "status": "not_applicable",
                    "score": None,
                    "reason": "该检查点无法应用到当前冻结候选结果。",
                    "evidence": [],
                }]
            }

        semantics = evaluate_semantics(
            [{
                "key": "quality",
                "weight": 1.0,
                "not_applicable_allowed": True,
            }],
            evaluator=evaluator,
            evidence_index=evidence,
            protocol="codex-agent-judge-v1",
        )
        self.assertEqual(semantics["status"], "evaluation_error")
        self.assertEqual(
            semantics["error"]["code"], "SEMANTIC_NO_JUDGED_CRITERIA"
        )

    def test_final_weights_reject_unknown_keys(self) -> None:
        rules = run_rules(
            "def grade(**kwargs): return {'quality': 1.0, 'overall_score': 1.0}",
            executor=local_fixture_executor,
            workspace_path="/tmp_workspace",
            expected_keys=["quality"],
        )
        semantics = evaluate_semantics(
            [],
            evaluator=None,
            evidence_index=build_evidence_index([]),
            protocol="not-required",
        )
        with self.assertRaisesRegex(
            GradingCoreError, "GRADING_WEIGHTS_INVALID"
        ):
            finalize_score(
                grading_type="automated",
                grading_weights={
                    "automated": 1.0,
                    "llm_judge": 0.0,
                    "unexpected": 0.0,
                },
                rules=rules,
                semantics=semantics,
            )

    def test_legacy_cli_dispatch_default_is_unchanged(self) -> None:
        with patch.object(
            legacy_grading, "_run_grading_legacy", return_value={"overall_score": 1.0}
        ) as legacy, patch.object(
            legacy_grading, "_run_grading_v2", return_value={"overall_score": 0.5}
        ) as v2:
            result = legacy_grading.run_grading(
                task_id="fixture",
                automated_checks="def grade(**kwargs): return {'overall_score': 1.0}",
                output_dir=Path("unused"),
            )
            self.assertEqual(result["overall_score"], 1.0)
            legacy.assert_called_once()
            v2.assert_not_called()


if __name__ == "__main__":
    unittest.main()
