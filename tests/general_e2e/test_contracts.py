from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from eval_general_e2e.contracts import (
    ContractValidationError,
    KNOWN_SCHEMAS,
    schema_path,
    validate_contract,
    validate_contract_file,
    validate_transcript_jsonl,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = REPO_ROOT / "eval_general_e2e/contracts"
VALID = CONTRACTS / "examples/valid"
INVALID = CONTRACTS / "examples/invalid"


def _mutate(document: object, dotted_path: str, value: object) -> None:
    parts = dotted_path.split(".")
    current = document
    for part in parts[:-1]:
        current = current[int(part)] if isinstance(current, list) else current[part]
    final = parts[-1]
    if isinstance(current, list):
        current[int(final)] = value
    else:
        current[final] = value


class GeneralE2EContractTests(unittest.TestCase):
    def test_all_positive_examples_validate(self) -> None:
        examples = sorted(VALID.glob("*.json"))
        self.assertEqual(len(examples), len(KNOWN_SCHEMAS))
        seen = set()
        for example in examples:
            with self.subTest(example=example.name):
                document = validate_contract_file(example)
                seen.add(document["schema_id"])
        self.assertEqual(seen, set(KNOWN_SCHEMAS))

    def test_declared_negative_examples_fail_with_stable_codes(self) -> None:
        cases = json.loads((INVALID / "cases.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(cases), 5)
        for case in cases:
            with self.subTest(case=case["name"]):
                base = (INVALID / case["base"]).resolve()
                document = copy.deepcopy(json.loads(base.read_text(encoding="utf-8")))
                for dotted_path, value in case["mutations"].items():
                    _mutate(document, dotted_path, value)
                with self.assertRaises(ContractValidationError) as captured:
                    validate_contract(document)
                self.assertEqual(captured.exception.code, case["expected_code"])

    def test_observed_zero_is_valid_and_distinct_from_unavailable(self) -> None:
        metrics = validate_contract_file(VALID / "resource-metrics-zero.json")
        observed = metrics["metrics"]["usage"]["input_tokens"]
        unavailable = metrics["metrics"]["usage"]["cache_creation_input_tokens"]
        self.assertEqual(observed, {
            "value": 0,
            "status": "observed",
            "basis": "native task turn delta",
        })
        self.assertIsNone(unavailable["value"])
        self.assertEqual(unavailable["status"], "unavailable")

        score = validate_contract_file(VALID / "score-zero.json")
        self.assertTrue(score["result"]["valid"])
        self.assertEqual(score["result"]["total_score"], 0.0)
        self.assertIsNone(score["result"]["invalid_reason"])

    def test_resource_metric_coverage_sources_and_known_subtotals_are_consistent(self) -> None:
        metrics = json.loads(
            (VALID / "resource-metrics-zero.json").read_text(encoding="utf-8")
        )
        fields = (
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "cache_read_input_tokens",
            "cache_creation_input_tokens",
            "reasoning_output_tokens",
            "request_count",
            "request_attempt_count",
            "call_count",
            "duration_seconds",
            "agent_duration_seconds",
        )
        metric_by_name = {
            **metrics["metrics"]["usage"],
            **metrics["metrics"]["requests"],
            **metrics["metrics"]["tools"],
            **metrics["metrics"]["timing"],
        }
        metrics["collection"].update({
            "coverage": {
                field: {
                    "known": 0 if metric_by_name[field]["status"] == "unavailable" else 1,
                    "total": None if field == "request_attempt_count" else 1,
                    "unit": "fixture",
                }
                for field in fields
            },
            "known_subtotals": {},
            "metric_sources": {
                field: [f"evidence/raw.jsonl#/{field}"] for field in fields
            },
        })
        validate_contract(metrics)

        metrics["metrics"]["usage"]["total_tokens"].update({
            "value": None,
            "status": "partial",
        })
        metrics["collection"]["coverage"]["total_tokens"] = {
            "known": 1,
            "total": 2,
            "unit": "usage_update",
        }
        metrics["collection"]["known_subtotals"]["total_tokens"] = 10
        validate_contract(metrics)

        metrics["metrics"]["usage"]["total_tokens"]["status"] = "observed"
        with self.assertRaises(ContractValidationError) as captured:
            validate_contract(metrics)
        self.assertEqual(captured.exception.code, "METRIC_STATUS_VALUE_MISMATCH")

    def test_schema_files_cover_every_runtime_contract_identifier(self) -> None:
        for schema_id in KNOWN_SCHEMAS:
            with self.subTest(schema_id=schema_id):
                path = schema_path(schema_id)
                payload = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(payload["$id"], schema_id)
                self.assertEqual(payload["$schema"], "https://json-schema.org/draft/2020-12/schema")
        common = json.loads(
            (CONTRACTS / "schemas/common-v1.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual(common["$id"], "urn:wildclawbench:schema:general-e2e:common:v1")

    def test_trace_v2_preserves_nullable_native_ids_without_weakening_v1(self) -> None:
        trace = json.loads((VALID / "trace-index.json").read_text(encoding="utf-8"))
        trace.update({
            "schema_id": "urn:wildclawbench:schema:general-e2e:trace-index:v2", "schema_version": 2,
            "adapter": {"id": "qwenwork-fixture", "version": "0.1.0", "source": "fixture"},
            "session": {"thread_id": None, "turn_id": None, "session_id": "native-session", "cwd": "/fixture/workspace", "lifecycle_generation": None},
            "binding_evidence": [{"path": "bindings/session.json", "sha256": "1" * 64, "size": 20}],
        })
        trace["transcript"]["path"] = "transcript.jsonl"
        trace["raw_trace"][0]["path"] = "raw/native.jsonl"
        validate_contract(trace)
        legacy = copy.deepcopy(trace)
        legacy.update(schema_id="urn:wildclawbench:schema:general-e2e:trace-index:v1", schema_version=1)
        with self.assertRaises(ContractValidationError):
            validate_contract(legacy)
        for mutation in ("all-null", "duplicate", "escape", "wrong-version", "empty-binding"):
            changed = copy.deepcopy(trace)
            if mutation == "all-null":
                changed["session"]["session_id"] = None
            elif mutation == "duplicate":
                changed["raw_trace"].append(changed["raw_trace"][0])
            elif mutation == "escape":
                changed["binding_evidence"][0]["path"] = "bindings/../outside"
            elif mutation == "wrong-version":
                changed["schema_version"] = 1
            else:
                changed["binding_evidence"] = []
            with self.subTest(mutation=mutation), self.assertRaises(ContractValidationError):
                validate_contract(changed)

    def test_transcript_jsonl_requires_stable_identity_and_sequence(self) -> None:
        first = json.loads((VALID / "transcript-event.json").read_text(encoding="utf-8"))
        second = copy.deepcopy(first)
        second.update({
            "event_id": "event-0002",
            "sequence": 1,
            "occurred_at": "2026-09-17T10:00:01+08:00",
            "type": "assistant_message",
            "role": "assistant",
            "content": "Done.",
        })
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "transcript.jsonl"
            path.write_text(
                "\n".join(json.dumps(item, ensure_ascii=False) for item in (first, second)) + "\n",
                encoding="utf-8",
            )
            events = validate_transcript_jsonl(path)
            self.assertEqual([item["sequence"] for item in events], [0, 1])

            second["sequence"] = 0
            path.write_text(
                "\n".join(json.dumps(item, ensure_ascii=False) for item in (first, second)) + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(ContractValidationError) as captured:
                validate_transcript_jsonl(path)
            self.assertEqual(captured.exception.code, "INVALID_VALUE")

    def test_nullable_required_field_cannot_be_omitted(self) -> None:
        execution = json.loads((VALID / "execution-record.json").read_text(encoding="utf-8"))
        del execution["execution"]["agent_duration_seconds"]
        with self.assertRaises(ContractValidationError) as captured:
            validate_contract(execution)
        self.assertEqual(captured.exception.code, "REQUIRED_FIELD")

    def test_candidate_state_fields_are_semantically_consistent(self) -> None:
        execution = json.loads((VALID / "execution-record.json").read_text(encoding="utf-8"))
        execution["candidate"]["path"] = None
        with self.assertRaises(ContractValidationError) as captured:
            validate_contract(execution)
        self.assertEqual(captured.exception.code, "REQUIRED_FIELD")

        execution["candidate"] = {
            "path": "candidate/workspace",
            "frozen_sha256": None,
            "frozen_at": None,
            "drift_status": "not_frozen",
        }
        with self.assertRaises(ContractValidationError) as captured:
            validate_contract(execution)
        self.assertEqual(captured.exception.code, "INVALID_VALUE")

    def test_completed_receipt_requires_completed_tasks(self) -> None:
        receipt = json.loads((VALID / "receipt.json").read_text(encoding="utf-8"))
        receipt["tasks"][0]["status"] = "partial"
        with self.assertRaises(ContractValidationError) as captured:
            validate_contract(receipt)
        self.assertEqual(captured.exception.code, "INVALID_VALUE")

    def test_trace_index_accepts_adapter_binding_and_consistent_normalization_counts(self) -> None:
        trace = json.loads((VALID / "trace-index.json").read_text(encoding="utf-8"))
        trace.update({
            "adapter": {
                "id": "astronstudio-provider-runtime-events",
                "version": "0.1.0",
                "source": "provider_runtime_events",
            },
            "session": {
                "thread_id": "thread-fixture",
                "turn_id": "turn-fixture",
                "session_id": "session-fixture",
                "cwd": "/tmp/workspace-fixture",
                "lifecycle_generation": "lifecycle-fixture",
            },
            "raw_event_range": {
                "first_sequence": 100,
                "last_sequence": 110,
                "event_count": 8,
            },
            "normalization": {
                "native_event_count": 8,
                "normalized_event_count": 2,
                "filtered_native_event_count": 6,
                "compatibility_profiles": ["general-e2e-transcript-event-v1"],
            },
        })
        validate_contract(trace)

        trace["normalization"]["normalized_event_count"] = 3
        with self.assertRaises(ContractValidationError) as captured:
            validate_contract(trace)
        self.assertEqual(captured.exception.code, "INVALID_VALUE")

        trace["normalization"]["normalized_event_count"] = 2
        trace["raw_trace"] = []
        with self.assertRaises(ContractValidationError) as captured:
            validate_contract(trace)
        self.assertEqual(captured.exception.code, "EVIDENCE_MISSING")


if __name__ == "__main__":
    unittest.main()
