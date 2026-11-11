from __future__ import annotations

import json
import sys
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from eval_general_e2e.contracts import validate_contract_file
from eval_general_e2e.datasets.bundle import build_default_bundle
from tests.general_e2e.test_local_scoring_runtime import Fixture, MAPPED_RESULTS_RULE, RUNTIME


REPO_ROOT = Path(__file__).resolve().parents[2]
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


def fixture_evaluator_decision_requests(response):
    """These fixtures simulate evaluator input loss, not candidate omission."""
    keys = {row['key'] for row in response['criteria'] if row.get('status') == 'unresolved'}
    for field in ('criterion_evidence_statuses', 'capability_evidence_statuses'):
        keys.update(key for key, value in response.get(field, {}).items()
                    if value.get('status') in {'evidence_insufficient', 'blocked_external', 'not_observed', 'evaluator_error'})
    if response.get('run_validity', {}).get('status') == 'evidence_insufficient': keys.add('run_validity')
    return [{'criterion_key': key, 'origin': 'task_source' if key == 'tool_call_contract' else 'evaluator',
             'problem': '合成评测输入缺少原接口定义或原始证据', 'missing_evidence': '评测侧未保留的必要原始证据或参照',
             'evidence_checked': '已查合成候选与保留轨迹；本例模拟评测方丢证，不代表候选未提供证明',
             'why_rules_cannot_decide': '不能将合成评测输入缺口归因给候选',
             'repair_execution_impact': '本例只修复评测输入，保留合成原作答',
             'proposed_actions': ['恢复缺失参考或原轨迹后独立重评'], 'decision_question': '请确认可恢复的评测输入版本'}
            for key in sorted(keys)]


class GeneralSemanticScoringTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="general-e2e-semantic-test-")
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        RUNTIME._remove_tree(self.root)
        self.temp.cleanup()

    def _hybrid_attempt(self, name: str = "hybrid", *, office_reference: bool = False,
                        candidate_text: str = "ready\n") -> Path:
        fixture = Fixture(
            self.root / name,
            grading_type="hybrid",
            grading_weights={"automated": 0.5, "llm_judge": 0.5},
            llm_judge_rubric=RUBRIC,
            office_reference=office_reference,
            candidate_text=candidate_text,
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
        # A clean checkout must not rely on a previous administrator's cache.
        # Build from the locked source into this test's private temporary root;
        # build_default_bundle rejects source drift and never updates the lock.
        bundle = self.root / "general-custom60-v1.dataset.zip"
        build_default_bundle(REPO_ROOT, bundle)
        with zipfile.ZipFile(bundle) as archive:
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

    def test_generated_evidence_is_frozen_and_verifiable_without_runtime(self) -> None:
        fixture = Fixture(self.root / 'generated-archive', grading_type='llm_judge',
            grading_weights={'automated': 0, 'llm_judge': 1}, llm_judge_rubric=RUBRIC,
            rule="from pathlib import Path\ndef grade(transcript, workspace_path):\n p=Path(workspace_path)/'evaluator_evidence'\n p.mkdir()\n (p/'manifest.json').write_text('{}',encoding='utf-8')\n return {'overall_score':0.0}",
            contract_overrides={
                'judge_evidence': {'required': [{'path':'evaluator_evidence/','role':'grader_generated_evidence'}]},
                'rule_result_adapter': {'schema_version':'wildclawbench.general-e2e-numeric-diagnostics/v1',
                    'diagnostic_keys':['diagnostics'], 'evidence_only':True, 'default_overall':None}})
        attempt = fixture.prepare()
        RUNTIME.run_rules_attempt(attempt_root=attempt, runtime_python=Path(sys.executable), timeout_seconds=10)
        response, candidate_id, transcript_id = self._prepare_and_query(attempt)
        catalog = json.loads((attempt/'semantic/evidence-catalog.json').read_text())
        generated_id = next(e['id'] for e in catalog['evidence_index']['entries'] if e['reference']['type']=='grader_generated_evidence' and '/files/' in e['reference']['path'])
        RUNTIME.query_evidence_attempt(attempt_root=attempt, mode='file', evidence_id=generated_id)
        for row, score, ids, queries in zip(response['criteria'], [1.0, .5],
                [[candidate_id, generated_id], [transcript_id]], [['query-0001','query-0003'], ['query-0002']]):
            row.update(status='judged', score=score, reason='合成证据与测试档位一致，仅用于验证证据归档和计分接口。',
                evidence_ids=ids, review={'query_ids':queries,'supporting_evidence_checked':True,
                    'contradicting_evidence_checked':True,'absence_claim':False,'complete_event_range_checked':False})
        source = attempt/'synthetic-response.json'
        source.write_text(json.dumps(response,ensure_ascii=False),encoding='utf-8')
        RUNTIME.record_semantics_attempt(attempt_root=attempt,response_path=source)
        result = RUNTIME.finalize_score_attempt(attempt_root=attempt)
        self.assertAlmostEqual(result['score']['result']['total_score'], .8)
        RUNTIME._remove_tree(attempt/'runtime')
        self.assertTrue(RUNTIME.verify_score_attempt(attempt,archived=True)['score_valid'])

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

    def test_mapped_nested_results_are_explicit_in_semantic_request(self) -> None:
        fixture = Fixture(
            self.root / "mapped-hybrid",
            rule=MAPPED_RESULTS_RULE,
            grading_type="hybrid",
            grading_weights={"automated": 0.5, "llm_judge": 0.5},
            llm_judge_rubric=RUBRIC,
            mapped_nested_results=True,
        )
        attempt = fixture.prepare("score-mapped-hybrid")
        rule_component = {
            "schema_version": "wildclawbench.general-e2e-rule-component/v1",
            "status": "completed", "score": 1.0,
            "criteria": [{"key": "fixture_rule", "status": "judged", "score": 1.0}],
            "raw_scores": {"fixture_rule": 1.0, "overall_score": 1.0},
            "dependencies": {"imports": [], "stdlib": [], "external": []},
            "error": None,
        }
        (attempt / "rule-component.json").write_text(json.dumps(rule_component), encoding="utf-8")
        prepared = RUNTIME.prepare_semantics_attempt(attempt_root=attempt)
        self.assertEqual(prepared["semantic_status"], "awaiting_response")
        request = json.loads((attempt / "semantic/request.json").read_text())
        resolution = request["evidence"]["path_resolution"]
        self.assertEqual(resolution["mode"], "mapped-nested")
        self.assertEqual(resolution["logical_results_root"], "/tmp_workspace/results")
        self.assertEqual(
            resolution["candidate_results_root"],
            "candidate-original/workspace/workspace/results",
        )
        catalog = json.loads((attempt / "semantic/evidence-catalog.json").read_text())
        paths = [item["reference"].get("path") for item in catalog["evidence_index"]["entries"]]
        self.assertIn("candidate-original/workspace/workspace/results/answer.txt", paths)

    def test_zero_weight_empty_rules_finalize_and_known_failed_aggregation_is_repaired_without_rejudging(self) -> None:
        fixture = Fixture(self.root / "zero-rules", grading_type="hybrid",
            grading_weights={"automated": 0.0, "llm_judge": 1.0}, llm_judge_rubric=RUBRIC,
            rule="def grade(transcript, workspace_path):\n return {'overall_score':0.0}",
            contract_overrides={"rule_result_adapter": {"schema_version": "wildclawbench.general-e2e-numeric-diagnostics/v1",
                "diagnostic_keys": ["diagnostics"], "evidence_only": True, "default_overall": None}})
        attempt = fixture.prepare("zero-rules")
        RUNTIME.run_rules_attempt(attempt_root=attempt, runtime_python=Path(sys.executable), timeout_seconds=10)
        response, candidate_id, transcript_id = self._prepare_and_query(attempt)
        for row, score, evidence in zip(response["criteria"], [1.0, .5], [[candidate_id], [transcript_id]]):
            row.update(status="judged", score=score, reason="本合成用例仅验证零权重规则组件的合分接口。", evidence_ids=evidence,
                review={"query_ids": ["query-0001", "query-0002"], "supporting_evidence_checked": True,
                    "contradicting_evidence_checked": True, "absence_claim": False, "complete_event_range_checked": False})
        source = attempt / "synthetic-zero-response.json"
        source.write_text(json.dumps(response, ensure_ascii=False), encoding="utf-8")
        RUNTIME.record_semantics_attempt(attempt_root=attempt, response_path=source)
        semantic_before = (attempt / "semantic/semantic-component.json").read_bytes()
        with patch.object(RUNTIME, "_automated_component_reason",
                          side_effect=RUNTIME.ScoringRuntimeError("RULE_COMPONENT_INVALID", "criterion summaries")):
            with self.assertRaises(RUNTIME.ScoringRuntimeError):
                RUNTIME.finalize_score_attempt(attempt_root=attempt)
        failed_before = (attempt / "score-audit.json").read_bytes()
        output = self.root / "repaired-zero"
        repaired = RUNTIME.repair_zero_weight_finalization(source_attempt_root=attempt, output_root=output)
        self.assertTrue(repaired["score_valid"])
        self.assertFalse(repaired["semantic_decision_rejudged"])
        self.assertEqual((attempt / "score-audit.json").read_bytes(), failed_before)
        self.assertEqual((output / "semantic/semantic-component.json").read_bytes(), semantic_before)
        score = json.loads((output / "score.json").read_text())
        self.assertAlmostEqual(score["result"]["total_score"], .8)
        self.assertIn("零权重", score["evaluation"]["criteria"][0]["reason"])
        self.assertTrue(RUNTIME.verify_score_attempt(output, archived=True)["score_valid"])
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError, "RULE_COMPONENT_INVALID"):
            RUNTIME._automated_component_reason({"schema_version": RUNTIME.RULE_COMPONENT_SCHEMA_V2,
                "status": "completed", "score": 0.0, "criteria": []}, automated_weight=1.0)

    def test_sealed_office_reference_ids_and_mapping_survive_semantic_archive(self) -> None:
        attempt = self._hybrid_attempt("office-reference", office_reference=True)
        response, candidate_id, transcript_id = self._prepare_and_query(attempt)
        catalog = json.loads((attempt / "semantic/evidence-catalog.json").read_text())
        private = [e for e in catalog["evidence_index"]["entries"] if e["reference"]["type"] == "private_reference"]
        container_id = next(e["id"] for e in private if e["reference"]["path"].endswith(".gtref.zip"))
        mapping_id = next(e["id"] for e in private if e["reference"]["path"] == "attempt-manifest.json")
        RUNTIME.query_evidence_attempt(attempt_root=attempt, mode="catalog", evidence_id=container_id)
        RUNTIME.query_evidence_attempt(attempt_root=attempt, mode="file", evidence_id=mapping_id)
        for row, score, ids, queries in zip(response["criteria"], [1.0, .5],
                [[candidate_id, container_id, mapping_id], [transcript_id]],
                [["query-0001", "query-0003", "query-0004"], ["query-0002"]]):
            row.update(status="judged", score=score, reason="本合成测试仅验证参考容器的证据绑定与归档接口。",
                evidence_ids=ids, review={"query_ids": queries, "supporting_evidence_checked": True,
                    "contradicting_evidence_checked": True, "absence_claim": False,
                    "complete_event_range_checked": False})
        source = attempt / "synthetic-office-response.json"
        source.write_text(json.dumps(response, ensure_ascii=False), encoding="utf-8")
        RUNTIME.record_semantics_attempt(attempt_root=attempt, response_path=source)
        RUNTIME.finalize_score_attempt(attempt_root=attempt)
        RUNTIME._remove_tree(attempt / "runtime")
        self.assertTrue(RUNTIME.verify_score_attempt(attempt, archived=True)["score_valid"])

    def test_duplicate_query_references_are_mechanical_transport_not_an_evaluation_error(self) -> None:
        attempt=self._hybrid_attempt('duplicate-queries')
        response,candidate_id,transcript_id=self._prepare_and_query(attempt)
        for row,score,evidence in zip(response['criteria'],[1.0,.5],[[candidate_id],[transcript_id]]):
            row.update(status='judged',score=score,reason='本合成用例验证同一查询引用重复不改变裁判判定。',evidence_ids=evidence,
                review={'query_ids':['query-0001','query-0002','query-0001'],
                    'supporting_evidence_checked':True,'contradicting_evidence_checked':True,
                    'absence_claim':False,'complete_event_range_checked':False})
        source=attempt/'native-duplicate-response.json'
        source.write_text(json.dumps(response,ensure_ascii=False),encoding='utf-8')
        raw=source.read_bytes()
        result=RUNTIME.record_semantics_attempt(attempt_root=attempt,response_path=source)
        self.assertEqual(result['audit']['response_transport']['removed_query_reference_count'],2)
        self.assertFalse(result['audit']['response_transport']['decisions_or_evidence_modified'])
        self.assertEqual((attempt/'semantic/response.json').read_bytes(),raw)
        RUNTIME.finalize_score_attempt(attempt_root=attempt)
        RUNTIME._remove_tree(attempt/'runtime')
        self.assertTrue(RUNTIME.verify_score_attempt(attempt,archived=True)['score_valid'])
        audit_path=attempt/'semantic/semantic-audit.json'
        audit=json.loads(audit_path.read_text())
        audit['response_transport']['effective_response_sha256']='0'*64
        audit_path.write_text(json.dumps(audit),encoding='utf-8')
        manifest=json.loads((attempt/'attempt-manifest.json').read_text())
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError,'SEMANTIC_RESPONSE_TRANSPORT_DRIFT'):
            RUNTIME._verify_semantic_terminal(attempt,manifest)

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
        response['decision_requests'] = [{
            'criterion_key': row['key'], 'origin': 'evaluator',
            'problem': '合成评测输入缺少必要参考', 'missing_evidence': '用于判定本项的完整参考正文',
            'evidence_checked': '已查测试候选及测试轨迹，不能恢复缺失参考',
            'why_rules_cannot_decide': '此处模拟评测方缺参考，不是候选未满足要求',
            'repair_execution_impact': '测试参考修复不影响原作答，使用原作答重评',
            'proposed_actions': ['补齐评分参考后独立重评'], 'decision_question': '请确认可用的参考版本'}
            for row in response['criteria']]
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

    def test_character_pages_recover_an_entire_long_unicode_line(self) -> None:
        text = "起点😀" + "文🚀" * 40000 + "终点\r\n"
        attempt = self._hybrid_attempt("long-character-pages", candidate_text=text)
        RUNTIME.prepare_semantics_attempt(attempt_root=attempt)
        catalog = RUNTIME.query_evidence_attempt(attempt_root=attempt, mode="catalog", evidence_type="candidate_file")
        eid = next(item["id"] for item in catalog["items"] if item["reference"]["path"].endswith("answer.txt"))
        offset = 0
        parts = []
        while True:
            page = RUNTIME.query_evidence_attempt(attempt_root=attempt, mode="file", evidence_id=eid,
                                                  file_char_offset=offset, max_chars=8192)
            parts.append(page["items"][0]["text"])
            self.assertFalse(page["items"][0]["text_truncated"])
            if not page["has_more"]:
                self.assertIsNone(page["next_file_char_offset"])
                break
            self.assertGreater(page["next_file_char_offset"], offset)
            offset = page["next_file_char_offset"]
        self.assertEqual("".join(parts), text)
        log = json.loads((attempt / "semantic/query-log.json").read_text())
        self.assertEqual(log["queries"][-1]["coverage"]["end"], len(text))
        for args in [{"mode": "catalog", "file_char_offset": 0},
                     {"mode": "file", "file_char_offset": -1},
                     {"mode": "file", "file_char_offset": len(text) + 1},
                     {"mode": "file", "file_char_offset": 1, "offset": 1}]:
            with self.subTest(args=args), self.assertRaisesRegex(RUNTIME.ScoringRuntimeError, "CHAR_PAGE_INVALID"):
                RUNTIME.query_evidence_attempt(attempt_root=attempt, evidence_id=eid, **args)

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
