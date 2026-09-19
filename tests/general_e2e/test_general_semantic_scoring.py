from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from eval_general_e2e.contracts import validate_contract_file
from tests.general_e2e.test_local_scoring_runtime import Fixture, RUNTIME


REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET_BUNDLE = (
    REPO_ROOT
    / "report-workspace/general-e2e/datasets/general-custom60-v1"
    / "general-custom60-v1.dataset.zip"
)

RUBRIC = """Judge only the declared criteria. Each score must use a declared anchor.

### Criterion 1: Answer fidelity (key: answer_fidelity, weight: 0.6)

**Score 1.0**: The answer exactly matches the frozen reference.

**Score 0.75**: The answer has only a minor omission.

**Score 0.5**: The answer is partially correct.

**Score 0.25**: The answer has major omissions.

**Score 0.0**: The answer is absent or wrong.

### Criterion 2: Trace support (key: trace_support, weight: 0.4)

**Score 1.0**: The trace directly supports the delivered answer.

**Score 0.75**: The trace supports most of the answer.

**Score 0.5**: The trace provides partial support.

**Score 0.25**: The trace is weak or contradictory.

**Score 0.0**: No usable trace support exists.
"""


class GeneralSemanticScoringTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="general-e2e-semantic-test-")
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _hybrid_attempt(self, name: str = "hybrid") -> Path:
        fixture = Fixture(
            self.root / name,
            grading_type="hybrid",
            grading_weights={"automated": 0.5, "llm_judge": 0.5},
            llm_judge_rubric=RUBRIC,
        )
        attempt = fixture.prepare(f"score-{name}")
        rule_component = {
            "schema_version": "wildclawbench.general-e2e-rule-component/v1",
            "status": "completed",
            "score": 0.8,
            "criteria": [{"key": "fixture_rule", "status": "judged", "score": 0.8}],
            "raw_scores": {"fixture_rule": 0.8, "overall_score": 0.8},
            "dependencies": {"imports": [], "stdlib": [], "external": []},
            "error": None,
        }
        (attempt / "rule-component.json").write_text(
            json.dumps(rule_component), encoding="utf-8"
        )
        return attempt

    def _prepare_and_query(self, attempt: Path) -> tuple[dict, str, str]:
        prepared = RUNTIME.prepare_semantics_attempt(attempt_root=attempt)
        self.assertEqual(prepared["semantic_status"], "awaiting_response")
        candidate_page = RUNTIME.query_evidence_attempt(
            attempt_root=attempt,
            mode="catalog",
            evidence_type="candidate_file",
        )
        transcript_page = RUNTIME.query_evidence_attempt(
            attempt_root=attempt,
            mode="transcript",
            offset=0,
            limit=1000,
        )
        candidate_id = candidate_page["items"][0]["id"]
        transcript_id = transcript_page["items"][0]["locator"]["evidence_id"]
        return (
            json.loads((attempt / "semantic/response-template.json").read_text()),
            candidate_id,
            transcript_id,
        )

    def test_all_frozen_semantic_contracts_parse_exact_keys_weights_and_anchors(self) -> None:
        parsed_count = 0
        with zipfile.ZipFile(DATASET_BUNDLE) as archive:
            contracts = sorted(
                name
                for name in archive.namelist()
                if name.endswith("/private-scoring/contract.json")
            )
            self.assertEqual(len(contracts), 60)
            for name in contracts:
                contract = json.loads(archive.read(name))
                if contract["grading_type"] == "automated":
                    continue
                criteria = RUNTIME._parse_semantic_criteria(
                    contract["llm_judge_rubric"]
                )
                with self.subTest(task_id=contract["task_id"]):
                    self.assertTrue(criteria)
                    self.assertAlmostEqual(sum(row["weight"] for row in criteria), 1.0)
                    self.assertTrue(
                        all(
                            row["allowed_scores"] == [0.0, 0.25, 0.5, 0.75, 1.0]
                            for row in criteria
                        )
                    )
                parsed_count += 1
        self.assertEqual(parsed_count, 41)

    def test_automated_task_generates_not_required_semantics_and_standard_score(self) -> None:
        fixture = Fixture(self.root / "automated")
        attempt = fixture.prepare("score-automated")
        rule_component = {
            "schema_version": "wildclawbench.general-e2e-rule-component/v1",
            "status": "completed",
            "score": 0.0,
            "criteria": [{"key": "fixture_rule", "status": "judged", "score": 0.0}],
            "raw_scores": {"fixture_rule": 0.0, "overall_score": 0.0},
            "dependencies": {"imports": [], "stdlib": [], "external": []},
            "error": None,
        }
        (attempt / "rule-component.json").write_text(
            json.dumps(rule_component), encoding="utf-8"
        )
        prepared = RUNTIME.prepare_semantics_attempt(attempt_root=attempt)
        self.assertEqual(prepared["semantic_status"], "not_required")
        score = RUNTIME.finalize_score_attempt(attempt_root=attempt)["score"]
        self.assertTrue(score["result"]["valid"])
        self.assertEqual(score["result"]["total_score"], 0.0)
        self.assertEqual(score["judge"]["protocol"], "not-required")
        validate_contract_file(attempt / "score.json", expected_schema_id=RUNTIME.SCORE_SCHEMA_ID)

    def test_hybrid_codex_response_is_queried_validated_combined_and_verified(self) -> None:
        attempt = self._hybrid_attempt()
        response, candidate_id, transcript_id = self._prepare_and_query(attempt)
        response["criteria"][0].update(
            {
                "status": "judged",
                "score": 1.0,
                "reason": "冻结答案文件与参考答案完全一致，因此本项得满分。",
                "evidence_ids": [candidate_id],
                "review": {
                    "query_ids": ["query-0001", "query-0002"],
                    "supporting_evidence_checked": True,
                    "contradicting_evidence_checked": True,
                    "absence_claim": False,
                    "complete_event_range_checked": False,
                },
            }
        )
        response["criteria"][1].update(
            {
                "status": "judged",
                "score": 0.5,
                "reason": "唯一冻结事件只能提供部分轨迹支持，因此本项得部分分。",
                "evidence_ids": [transcript_id],
                "review": {
                    "query_ids": ["query-0002"],
                    "supporting_evidence_checked": True,
                    "contradicting_evidence_checked": True,
                    "absence_claim": False,
                    "complete_event_range_checked": False,
                },
            }
        )
        response_path = attempt / "semantic-response-input.json"
        response_path.write_text(json.dumps(response), encoding="utf-8")
        semantic = RUNTIME.record_semantics_attempt(
            attempt_root=attempt, response_path=response_path
        )
        self.assertEqual(semantic["semantic_component"]["score"], 0.8)
        result = RUNTIME.finalize_score_attempt(attempt_root=attempt)
        self.assertEqual(result["score"]["result"]["total_score"], 0.8)
        self.assertTrue(result["score"]["result"]["valid"])
        self.assertFalse(result["audit"]["docker_used"])
        validate_contract_file(attempt / "score.json", expected_schema_id=RUNTIME.SCORE_SCHEMA_ID)
        verified = RUNTIME.verify_score_attempt(attempt)
        self.assertTrue(verified["score_valid"])

        tampered_score = json.loads((attempt / "score.json").read_text())
        tampered_score["result"]["total_score"] = 0.9
        (attempt / "score.json").write_text(
            json.dumps(tampered_score, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        tampered_audit = json.loads((attempt / "score-audit.json").read_text())
        tampered_audit["score_sha256"] = RUNTIME._sha256_file(
            attempt / "score.json"
        )
        (attempt / "score-audit.json").write_text(
            json.dumps(tampered_audit, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(
            RUNTIME.ScoringRuntimeError, "SCORE_RECOMPUTE_MISMATCH"
        ):
            RUNTIME.verify_score_attempt(attempt)

    def test_codex_response_with_english_reason_is_rejected(self) -> None:
        attempt = self._hybrid_attempt("english-reason")
        response, candidate_id, transcript_id = self._prepare_and_query(attempt)
        response["criteria"][0].update(
            {
                "status": "judged",
                "score": 1.0,
                "reason": "The frozen answer supports a full score.",
                "evidence_ids": [candidate_id],
                "review": {
                    "query_ids": ["query-0001"],
                    "supporting_evidence_checked": True,
                    "contradicting_evidence_checked": True,
                    "absence_claim": False,
                    "complete_event_range_checked": False,
                },
            }
        )
        response["criteria"][1].update(
            {
                "status": "judged",
                "score": 1.0,
                "reason": "冻结轨迹证据支持该检查点采用满分档位。",
                "evidence_ids": [transcript_id],
                "review": {
                    "query_ids": ["query-0002"],
                    "supporting_evidence_checked": True,
                    "contradicting_evidence_checked": True,
                    "absence_claim": False,
                    "complete_event_range_checked": False,
                },
            }
        )
        response_path = attempt / "semantic-response-input.json"
        response_path.write_text(json.dumps(response), encoding="utf-8")
        with self.assertRaisesRegex(
            RUNTIME.ScoringRuntimeError, "SEMANTIC_REASON_LANGUAGE_INVALID"
        ):
            RUNTIME.record_semantics_attempt(
                attempt_root=attempt, response_path=response_path
            )

    def test_unresolved_criterion_stays_evaluation_error_instead_of_zero(self) -> None:
        fixture = Fixture(
            self.root / "unresolved",
            rule="",
            grading_type="llm_judge",
            grading_weights={"automated": 0.0, "llm_judge": 1.0},
            llm_judge_rubric=RUBRIC,
        )
        attempt = fixture.prepare("score-unresolved")
        response, _, _ = self._prepare_and_query(attempt)
        response_path = attempt / "semantic-response-input.json"
        response_path.write_text(json.dumps(response), encoding="utf-8")
        semantic = RUNTIME.record_semantics_attempt(
            attempt_root=attempt, response_path=response_path
        )
        self.assertEqual(semantic["semantic_component"]["status"], "evaluation_error")
        score = RUNTIME.finalize_score_attempt(attempt_root=attempt)["score"]
        self.assertFalse(score["result"]["valid"])
        self.assertIsNone(score["result"]["total_score"])
        self.assertTrue(all(row["status"] == "unresolved" for row in score["evaluation"]["criteria"]))
        validate_contract_file(attempt / "score.json", expected_schema_id=RUNTIME.SCORE_SCHEMA_ID)

    def test_unknown_evidence_and_missing_counterexample_check_fail_closed(self) -> None:
        unknown_attempt = self._hybrid_attempt("unknown")
        response, _, _ = self._prepare_and_query(unknown_attempt)
        response["criteria"][0].update(
            {
                "status": "judged",
                "score": 1.0,
                "reason": "测试证据支持当前检查点的判定结果。",
                "evidence_ids": ["evidence-9999"],
                "review": {
                    "query_ids": ["query-0001"],
                    "supporting_evidence_checked": True,
                    "contradicting_evidence_checked": True,
                    "absence_claim": False,
                    "complete_event_range_checked": False,
                },
            }
        )
        response_path = unknown_attempt / "semantic-response-input.json"
        response_path.write_text(json.dumps(response), encoding="utf-8")
        with self.assertRaisesRegex(
            RUNTIME.ScoringRuntimeError, "SEMANTIC_EVIDENCE_ID_UNKNOWN"
        ):
            RUNTIME.record_semantics_attempt(
                attempt_root=unknown_attempt, response_path=response_path
            )
        invalid_score = RUNTIME.finalize_score_attempt(
            attempt_root=unknown_attempt
        )["score"]
        self.assertFalse(invalid_score["result"]["valid"])
        self.assertIsNone(invalid_score["result"]["total_score"])
        self.assertFalse(
            RUNTIME.verify_score_attempt(unknown_attempt)["score_valid"]
        )

        counter_attempt = self._hybrid_attempt("counter")
        response, candidate_id, _ = self._prepare_and_query(counter_attempt)
        response["criteria"][0].update(
            {
                "status": "judged",
                "score": 1.0,
                "reason": "测试证据支持当前检查点的判定结果。",
                "evidence_ids": [candidate_id],
                "review": {
                    "query_ids": ["query-0001"],
                    "supporting_evidence_checked": True,
                    "contradicting_evidence_checked": False,
                    "absence_claim": False,
                    "complete_event_range_checked": False,
                },
            }
        )
        response_path = counter_attempt / "semantic-response-input.json"
        response_path.write_text(json.dumps(response), encoding="utf-8")
        with self.assertRaisesRegex(
            RUNTIME.ScoringRuntimeError, "SEMANTIC_COUNTEREVIDENCE_CHECK_REQUIRED"
        ):
            RUNTIME.record_semantics_attempt(
                attempt_root=counter_attempt, response_path=response_path
            )

    def test_query_filters_are_mode_specific(self) -> None:
        attempt = self._hybrid_attempt("filters")
        RUNTIME.prepare_semantics_attempt(attempt_root=attempt)
        with self.assertRaisesRegex(
            RUNTIME.ScoringRuntimeError, "SEMANTIC_QUERY_FILTER_INVALID"
        ):
            RUNTIME.query_evidence_attempt(
                attempt_root=attempt,
                mode="catalog",
                text="answer",
            )

    def test_absence_claim_requires_unfiltered_complete_transcript_pages(self) -> None:
        attempt = self._hybrid_attempt("absence")
        RUNTIME.prepare_semantics_attempt(attempt_root=attempt)
        filtered = RUNTIME.query_evidence_attempt(
            attempt_root=attempt,
            mode="transcript",
            event_id="event-0001",
        )
        response = json.loads((attempt / "semantic/response-template.json").read_text())
        evidence_id = filtered["items"][0]["locator"]["evidence_id"]
        response["criteria"][0].update(
            {
                "status": "judged",
                "score": 1.0,
                "reason": "完整轨迹中没有发现与当前判定相矛盾的事件。",
                "evidence_ids": [evidence_id],
                "review": {
                    "query_ids": ["query-0001"],
                    "supporting_evidence_checked": True,
                    "contradicting_evidence_checked": True,
                    "absence_claim": True,
                    "complete_event_range_checked": True,
                },
            }
        )
        response_path = attempt / "semantic-response-input.json"
        response_path.write_text(json.dumps(response), encoding="utf-8")
        with self.assertRaisesRegex(
            RUNTIME.ScoringRuntimeError, "SEMANTIC_ABSENCE_COVERAGE_REQUIRED"
        ):
            RUNTIME.record_semantics_attempt(
                attempt_root=attempt, response_path=response_path
            )

    def test_bound_judge_identity_and_prepared_material_drift_fail_closed(self) -> None:
        model_attempt = self._hybrid_attempt("model")
        response, _, _ = self._prepare_and_query(model_attempt)
        response["judge"]["model"] = "different-model"
        response_path = model_attempt / "semantic-response-input.json"
        response_path.write_text(json.dumps(response), encoding="utf-8")
        with self.assertRaisesRegex(
            RUNTIME.ScoringRuntimeError, "SEMANTIC_RESPONSE_LOCK_MISMATCH"
        ):
            RUNTIME.record_semantics_attempt(
                attempt_root=model_attempt, response_path=response_path
            )

        drift_attempt = self._hybrid_attempt("drift")
        response, _, _ = self._prepare_and_query(drift_attempt)
        catalog_path = drift_attempt / "semantic/evidence-catalog.json"
        catalog = json.loads(catalog_path.read_text())
        catalog["created_at"] = "changed"
        catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
        response_path = drift_attempt / "semantic-response-input.json"
        response_path.write_text(json.dumps(response), encoding="utf-8")
        with self.assertRaisesRegex(
            RUNTIME.ScoringRuntimeError, "SEMANTIC_RESPONSE_LOCK_MISMATCH"
        ):
            RUNTIME.record_semantics_attempt(
                attempt_root=drift_attempt, response_path=response_path
            )


if __name__ == "__main__":
    unittest.main()
