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
    def test_all_seven_positive_examples_validate(self) -> None:
        examples = sorted(VALID.glob("*.json"))
        self.assertEqual(len(examples), 7)
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


if __name__ == "__main__":
    unittest.main()
