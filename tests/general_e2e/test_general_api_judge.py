from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.general_e2e.test_general_semantic_scoring import RUBRIC
from tests.general_e2e.test_local_scoring_runtime import Fixture, LOCK_PATH, RUNTIME


class GeneralApiJudgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="general-e2e-api-judge-")
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _config(
        self,
        root: Path,
        *,
        provider: str = "anthropic-messages",
        max_attempts: int = 1,
        max_input_chars: int = 20_000,
    ) -> Path:
        value = {
            "schema_version": RUNTIME.API_JUDGE_CONFIG_SCHEMA,
            "provider": provider,
            "base_url": "https://judge.example.test/proxy",
            "credential_env": "GENERAL_E2E_TEST_API_KEY",
            "max_output_tokens": 1024,
            "timeout_seconds": 30,
            "max_attempts": max_attempts,
            "max_input_chars": max_input_chars,
            "max_evidence_item_chars": 512,
            "temperature": 0,
            "reasoning_parameter": (
                "none" if provider == "anthropic-messages" else "reasoning_effort"
            ),
        }
        path = root / "api-runtime.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def _attempt(
        self,
        name: str,
        *,
        provider: str = "anthropic-messages",
        max_attempts: int = 1,
        grading_type: str = "llm_judge",
        max_input_chars: int = 20_000,
        candidate_chars: int | None = None,
    ) -> Path:
        weights = (
            {"automated": 0.5, "llm_judge": 0.5}
            if grading_type == "hybrid"
            else {"automated": 0.0, "llm_judge": 1.0}
        )
        fixture = Fixture(
            self.root / name,
            rule="" if grading_type == "llm_judge" else None,
            grading_type=grading_type,
            grading_weights=weights,
            llm_judge_rubric=RUBRIC,
        )
        if candidate_chars is not None:
            (fixture.candidate / "answer.txt").write_text(
                "x" * candidate_chars, encoding="utf-8"
            )
            entries, candidate_sha = RUNTIME._inventory_tree(fixture.candidate)
            artifact_path = fixture.candidate.parent / "candidate-artifact.json"
            artifact = json.loads(artifact_path.read_text())
            artifact["entries"] = entries
            artifact["expected_sha256"] = candidate_sha
            artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
            execution = json.loads(fixture.execution_record.read_text())
            execution["candidate"]["frozen_sha256"] = candidate_sha
            fixture.execution_record.write_text(json.dumps(execution), encoding="utf-8")
        config = self._config(
            fixture.root,
            provider=provider,
            max_attempts=max_attempts,
            max_input_chars=max_input_chars,
        )
        result = RUNTIME.prepare_attempt(
            unit_root=fixture.unit_root,
            execution_record_path=fixture.execution_record,
            scoring_package=fixture.scoring_package,
            task_id=fixture.task_id,
            scoring_attempt_id=f"score-{name}",
            output_root=fixture.output_root,
            runtime_lock_path=LOCK_PATH,
            judge_protocol="api-judge-v1",
            judge_model=(
                "anthropic/claude-fixture"
                if provider == "anthropic-messages"
                else "openai-fixture"
            ),
            judge_reasoning_effort="high",
            judge_attempt_id=f"judge-{name}",
            api_runtime_config_path=config,
        )
        attempt = Path(result["attempt_root"])
        if grading_type == "hybrid":
            component = {
                "schema_version": "wildclawbench.general-e2e-rule-component/v1",
                "status": "completed",
                "score": 0.8,
                "criteria": [],
                "raw_scores": {"overall_score": 0.8},
                "dependencies": {"imports": [], "stdlib": [], "external": []},
                "error": None,
            }
            (attempt / "rule-component.json").write_text(
                json.dumps(component), encoding="utf-8"
            )
        prepared = RUNTIME.prepare_semantics_attempt(attempt_root=attempt)
        self.assertEqual(prepared["semantic_status"], "awaiting_api")
        return attempt

    def _candidate(self, attempt: Path, *, score: float = 1.0) -> dict:
        api_input = json.loads((attempt / "semantic/api-input.json").read_text())
        evidence_ids = api_input["packet_summary"]["usable_evidence_ids"]
        self.assertTrue(evidence_ids)
        request = json.loads((attempt / "semantic/request.json").read_text())
        return {
            "criteria": [
                {
                    "key": criterion["key"],
                    "status": "judged",
                    "score": score,
                    "reason": "冻结证据支持当前检查点采用这个分值锚点。",
                    "evidence_ids": [evidence_ids[0]],
                    "supporting_evidence_checked": True,
                    "contradicting_evidence_checked": True,
                }
                for criterion in request["rubric"]["criteria"]
            ],
            "notes": "fixture",
        }

    @staticmethod
    def _anthropic_response(candidate: dict) -> tuple[int, dict, bytes]:
        response = {
            "id": "msg-fixture",
            "model": "claude-returned",
            "stop_reason": "end_turn",
            "content": [{"type": "text", "text": json.dumps(candidate)}],
            "usage": {
                "input_tokens": 120,
                "output_tokens": 40,
                "cache_read_input_tokens": 30,
                "cache_creation_input_tokens": 10,
            },
        }
        return 200, response, json.dumps(response).encode("utf-8")

    @staticmethod
    def _openai_response(text: str, response_id: str) -> tuple[int, dict, bytes]:
        response = {
            "id": response_id,
            "model": "openai-returned",
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": text},
                }
            ],
            "usage": {
                "prompt_tokens": 90,
                "completion_tokens": 20,
                "prompt_tokens_details": {"cached_tokens": 12},
            },
        }
        return 200, response, json.dumps(response).encode("utf-8")

    @staticmethod
    def _responses_api_response(candidate: dict) -> tuple[int, dict, bytes]:
        response = {
            "id": "resp-fixture",
            "model": "openai-responses-returned",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {"type": "output_text", "text": json.dumps(candidate)}
                    ],
                }
            ],
            "usage": {
                "input_tokens": 110,
                "output_tokens": 35,
                "input_tokens_details": {"cached_tokens": 18},
                "output_tokens_details": {"reasoning_tokens": 7},
            },
        }
        return 200, response, json.dumps(response).encode("utf-8")

    def test_anthropic_hybrid_is_scored_audited_and_does_not_persist_credential(self) -> None:
        attempt = self._attempt("anthropic", grading_type="hybrid")
        candidate = self._candidate(attempt)
        secret = "test-secret-must-not-be-persisted"
        with patch.dict(os.environ, {"GENERAL_E2E_TEST_API_KEY": secret}), patch.object(
            RUNTIME,
            "_api_http_exchange",
            return_value=self._anthropic_response(candidate),
        ) as exchange:
            result = RUNTIME.run_api_score_attempt(attempt_root=attempt)
        self.assertTrue(result["score_valid"])
        self.assertEqual(exchange.call_count, 1)
        audit = json.loads((attempt / "semantic/api-audit.json").read_text())
        self.assertEqual(audit["selected_attempt"], 1)
        self.assertEqual(audit["retry_count"], 0)
        self.assertEqual(audit["returned_model"], "claude-returned")
        self.assertEqual(audit["usage"]["cache_read_tokens"], 30)
        self.assertFalse(audit["fallback_used"])
        self.assertFalse(audit["docker_used"])
        self.assertTrue(RUNTIME.verify_score_attempt(attempt)["score_valid"])
        for path in attempt.rglob("*"):
            if path.is_file():
                self.assertNotIn(secret, path.read_text(encoding="utf-8", errors="ignore"))

    def test_openai_parse_failure_retries_exactly_once_and_reuses_terminal(self) -> None:
        attempt = self._attempt(
            "openai-retry", provider="openai-chat-completions", max_attempts=2
        )
        candidate = self._candidate(attempt, score=0.75)
        responses = [
            self._openai_response("not json", "chat-first"),
            self._openai_response(
                "prose\n```json\n" + json.dumps(candidate) + "\n```",
                "chat-second",
            ),
        ]
        with patch.dict(os.environ, {"GENERAL_E2E_TEST_API_KEY": "test-key"}), patch.object(
            RUNTIME, "_api_http_exchange", side_effect=responses
        ) as exchange:
            first = RUNTIME.run_api_judge_attempt(attempt_root=attempt)
        self.assertEqual(first["attempt_count"], 2)
        self.assertEqual(first["selected_attempt"], 2)
        audit = json.loads((attempt / "semantic/api-audit.json").read_text())
        self.assertEqual(audit["retry_count"], 1)
        self.assertEqual([row["status"] for row in audit["attempts"]], ["failed", "completed"])
        self.assertEqual(exchange.call_count, 2)
        with patch.object(
            RUNTIME,
            "_api_http_exchange",
            side_effect=AssertionError("terminal API call must not repeat"),
        ):
            reused = RUNTIME.run_api_judge_attempt(attempt_root=attempt)
        self.assertTrue(reused["reused_terminal"])

    def test_english_reason_retries_once_and_prompt_requires_chinese(self) -> None:
        attempt = self._attempt(
            "english-reason-retry",
            provider="openai-chat-completions",
            max_attempts=2,
        )
        api_input = json.loads((attempt / "semantic/api-input.json").read_text())
        semantic_request = json.loads((attempt / "semantic/request.json").read_text())
        self.assertIn("Chinese (zh-CN)", api_input["system_prompt"])
        self.assertEqual(semantic_request["requirements"]["reason_language"], "zh-CN")
        valid = self._candidate(attempt)
        invalid = json.loads(json.dumps(valid))
        for row in invalid["criteria"]:
            row["reason"] = "The frozen evidence supports this score anchor."
        responses = [
            self._openai_response(json.dumps(invalid), "chat-english"),
            self._openai_response(json.dumps(valid), "chat-chinese"),
        ]
        with patch.dict(os.environ, {"GENERAL_E2E_TEST_API_KEY": "test-key"}), patch.object(
            RUNTIME, "_api_http_exchange", side_effect=responses
        ) as exchange:
            result = RUNTIME.run_api_judge_attempt(attempt_root=attempt)
        self.assertEqual(result["attempt_count"], 2)
        self.assertEqual(result["selected_attempt"], 2)
        self.assertEqual(exchange.call_count, 2)
        audit = json.loads((attempt / "semantic/api-audit.json").read_text())
        self.assertEqual(audit["retry_count"], 1)
        self.assertEqual(audit["attempts"][0]["error"]["code"], "SEMANTIC_REASON_LANGUAGE_INVALID")
        self.assertEqual(audit["attempts"][1]["status"], "completed")

    def test_openai_responses_request_shape_and_usage_are_audited(self) -> None:
        attempt = self._attempt("openai-responses", provider="openai-responses")
        candidate = self._candidate(attempt, score=0.5)

        def exchange(**kwargs):
            self.assertTrue(kwargs["endpoint"].endswith("/responses"))
            self.assertEqual(kwargs["provider"], "openai-responses")
            body = kwargs["body"]
            self.assertIn("input", body)
            self.assertNotIn("messages", body)
            self.assertEqual(body["max_output_tokens"], 1024)
            self.assertEqual(body["text"]["format"]["type"], "json_object")
            self.assertEqual(body["reasoning"], {"effort": "high"})
            return self._responses_api_response(candidate)

        with patch.dict(os.environ, {"GENERAL_E2E_TEST_API_KEY": "test-key"}), patch.object(
            RUNTIME, "_api_http_exchange", side_effect=exchange
        ):
            result = RUNTIME.run_api_score_attempt(attempt_root=attempt)
        self.assertTrue(result["score_valid"])
        audit = json.loads((attempt / "semantic/api-audit.json").read_text())
        self.assertEqual(audit["provider"], "openai-responses")
        self.assertEqual(audit["returned_model"], "openai-responses-returned")
        self.assertEqual(audit["usage"]["cache_read_tokens"], 18)
        self.assertEqual(audit["usage"]["reasoning_output_tokens"], 7)

    def test_missing_credential_and_exhausted_invalid_responses_stay_evaluation_errors(self) -> None:
        missing = self._attempt("missing-credential")
        with patch.dict(os.environ, {}, clear=True), patch.object(
            RUNTIME, "_api_http_exchange"
        ) as exchange:
            result = RUNTIME.run_api_score_attempt(attempt_root=missing)
        self.assertFalse(result["score_valid"])
        self.assertEqual(exchange.call_count, 0)
        score = json.loads((missing / "score.json").read_text())
        self.assertIsNone(score["result"]["total_score"])

        exhausted = self._attempt(
            "exhausted", provider="openai-chat-completions", max_attempts=2
        )
        invalid = self._openai_response("still not json", "chat-invalid")
        with patch.dict(os.environ, {"GENERAL_E2E_TEST_API_KEY": "test-key"}), patch.object(
            RUNTIME, "_api_http_exchange", return_value=invalid
        ) as exchange:
            result = RUNTIME.run_api_score_attempt(attempt_root=exhausted)
        self.assertFalse(result["score_valid"])
        self.assertEqual(exchange.call_count, 2)
        api_audit = json.loads((exhausted / "semantic/api-audit.json").read_text())
        self.assertEqual(api_audit["status"], "failed")
        self.assertEqual(api_audit["attempt_count"], 2)

    def test_api_runtime_endpoint_and_provider_are_fail_closed(self) -> None:
        config = self._config(self.root)
        value = json.loads(config.read_text())
        value["base_url"] = "http://judge.example.test"
        config.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(
            RUNTIME.ScoringRuntimeError, "API_JUDGE_ENDPOINT_INVALID"
        ):
            RUNTIME._load_api_runtime_config(config)
        value["base_url"] = "https://user:pass@judge.example.test/path?secret=x"
        config.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(
            RUNTIME.ScoringRuntimeError, "API_JUDGE_ENDPOINT_INVALID"
        ):
            RUNTIME._load_api_runtime_config(config)
        value["base_url"] = "http://127.0.0.1:8765"
        value["provider"] = "unknown-provider"
        config.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(
            RUNTIME.ScoringRuntimeError, "API_JUDGE_PROVIDER_UNSUPPORTED"
        ):
            RUNTIME._load_api_runtime_config(config)

    def test_evidence_packet_marks_truncated_content_and_stays_within_budget(self) -> None:
        attempt = self._attempt(
            "truncated-input",
            max_input_chars=7000,
            candidate_chars=4000,
        )
        api_input = json.loads((attempt / "semantic/api-input.json").read_text())
        summary = api_input["packet_summary"]
        self.assertGreaterEqual(summary["truncated_content_count"], 1)
        self.assertLessEqual(
            summary["system_chars"] + summary["user_chars"],
            summary["maximum_input_chars"],
        )
        user_document = json.loads(api_input["user_prompt"])
        truncated = [
            row for row in user_document["evidence"] if row["content_status"] == "truncated"
        ]
        self.assertTrue(truncated)
        self.assertTrue(all(row["included_chars"] < row["original_chars"] for row in truncated))

    def test_failed_api_score_can_create_separate_codex_rescore_attempt(self) -> None:
        source = self._attempt("api-failed-before-rescore", provider="openai-responses")
        with patch.dict(os.environ, {}, clear=True):
            result = RUNTIME.run_api_score_attempt(attempt_root=source)
        self.assertFalse(result["score_valid"])
        source_hashes = {
            path.relative_to(source).as_posix(): RUNTIME._sha256_file(path)
            for path in source.rglob("*")
            if path.is_file()
        }

        prepared = RUNTIME.prepare_rescore_attempt(
            source_attempt_root=source,
            scoring_attempt_id="score-codex-rescore",
            output_root=self.root / "rescore-attempts",
            judge_protocol="codex-agent-judge-v1",
            judge_model="gpt-rescore-fixture",
            judge_reasoning_effort="high",
            judge_attempt_id="judge-codex-rescore",
        )
        rescore = Path(prepared["attempt_root"])
        verified = RUNTIME.verify_attempt(rescore)
        self.assertEqual(verified["candidate_sha256"], result["candidate_sha256"])
        manifest = json.loads((rescore / "attempt-manifest.json").read_text())
        self.assertEqual(manifest["lineage"]["kind"], "rescore")
        self.assertEqual(
            manifest["lineage"]["source_scoring_attempt_id"],
            "score-api-failed-before-rescore",
        )
        self.assertFalse(manifest["lineage"]["source_score_valid"])
        self.assertEqual(manifest["judge"]["protocol"], "codex-agent-judge-v1")
        self.assertNotIn("api_runtime", manifest["judge"])
        semantic = RUNTIME.prepare_semantics_attempt(attempt_root=rescore)
        self.assertEqual(semantic["semantic_status"], "awaiting_response")
        self.assertEqual(
            source_hashes,
            {
                path.relative_to(source).as_posix(): RUNTIME._sha256_file(path)
                for path in source.rglob("*")
                if path.is_file()
            },
        )

        with self.assertRaisesRegex(
            RUNTIME.ScoringRuntimeError, "RESCORE_ATTEMPT_ID_REUSED"
        ):
            RUNTIME.prepare_rescore_attempt(
                source_attempt_root=source,
                scoring_attempt_id="score-api-failed-before-rescore",
                output_root=self.root / "reuse-rejected",
                judge_protocol="codex-agent-judge-v1",
                judge_model="gpt-rescore-fixture",
                judge_reasoning_effort="high",
                judge_attempt_id="judge-reuse-rejected",
            )


if __name__ == "__main__":
    unittest.main()
