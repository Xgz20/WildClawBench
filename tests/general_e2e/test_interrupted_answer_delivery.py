import hashlib
import unittest
from unittest.mock import patch

from tests.general_e2e.test_local_scoring_runtime import RUNTIME

DELIVERY = RUNTIME.interrupted_answer_delivery


class InterruptedAnswerDeliveryTests(unittest.TestCase):
    def test_absent_optional_profile_preserves_legacy_manifest_and_prior_correction(self):
        prior = {"correction_id": "existing-profile"}
        for manifest in [{}, {"runtime": {}}, {"runtime": {"interrupted_answer_delivery_profile": None}}]:
            self.assertEqual(DELIVERY.effective_source(manifest, "original", "current", prior), ("current", prior))

    def test_enabled_profile_still_requires_valid_bound_metadata(self):
        manifest = {"runtime": {"interrupted_answer_delivery_profile": {"profile": "unknown"}},
                    "identity": {"task_id": "fixture"}, "digests": {"contract_sha256": "wrong"},
                    "dataset": {"id": "wrong", "digest": "wrong"}}
        with self.assertRaises(ValueError):
            DELIVERY.effective_source(manifest, "original", "current", None)

    def extractor(self):
        source = RUNTIME.answer_delivery.FUNCTION
        source_sha = hashlib.sha256(source.encode()).hexdigest()
        contract = {"task_id": "fixture", "automated_checks": source}
        with patch.dict(DELIVERY.REGISTRY, {"fixture": ("contract-sha", source_sha)}, clear=True):
            marker = DELIVERY.marker(contract, "contract-sha", DELIVERY.DATASET, DELIVERY.ADMISSION)
            manifest = {"identity": {"task_id": "fixture"}, "digests": {"contract_sha256": "contract-sha"},
                        "dataset": DELIVERY.DATASET, "evidence_admission": DELIVERY.ADMISSION,
                        "runtime": {"interrupted_answer_delivery_profile": marker}}
            fixed, receipt = DELIVERY.effective_source(manifest, source, source, None)
        namespace = {"hashlib": hashlib, "_visible_text": lambda row: row.get("content", "")}
        exec(compile(fixed, "<interrupted-answer-delivery>", "exec"), namespace)
        return namespace["_final_answer"], receipt

    def test_proven_abort_exports_absent_delivery_and_retains_progress(self):
        extract, receipt = self.extractor()
        rows = [{"role": "user", "content": "q"},
                {"role": "assistant", "channel": "commentary", "content": "progress"},
                {"type": "status", "status": {"type": "turn_aborted", "reason": "interrupted", "turn_id": "turn"}}]
        answer, proof = extract(rows)
        self.assertEqual(answer, "")
        self.assertFalse(proof["formal_answer_present"])
        self.assertEqual(proof["status"], "verified_interrupted_without_formal_answer")
        self.assertEqual(rows[1]["content"], "progress")
        self.assertFalse(receipt["numeric_decisions_assigned"])

    def test_missing_or_nonfinal_abort_remains_unresolved(self):
        extract, _ = self.extractor()
        rows = [{"role": "user", "content": "q"}]
        with self.assertRaisesRegex(ValueError, "final answer cannot be determined"):
            extract(rows)
        rows += [{"type": "status", "status": {"type": "turn_aborted", "reason": "interrupted", "turn_id": "turn"}},
                 {"role": "assistant", "channel": "commentary", "content": "later"}]
        with self.assertRaisesRegex(ValueError, "final answer cannot be determined"):
            extract(rows)

    def test_scope_requires_verified_admission_and_exact_contract(self):
        self.assertIsNone(DELIVERY.marker({"task_id": next(iter(DELIVERY.REGISTRY)), "automated_checks": ""},
                                         "wrong-contract", DELIVERY.DATASET, DELIVERY.ADMISSION))
        self.assertIsNone(DELIVERY.marker({}, "wrong-contract", DELIVERY.DATASET, "standard"))

    def test_general_v2_null_index_and_v1_frozen_source_remain_distinct(self):
        source = RUNTIME.answer_delivery.FUNCTION
        contract = {'task_id': 'fixture', 'automated_checks': source}
        admission = next(iter(RUNTIME.execution_accountability.NATIVE_ADMISSIONS))
        marker = DELIVERY.marker(contract, 'contract-sha', {}, admission)
        manifest = {'identity': {'task_id': 'fixture'}, 'digests': {'contract_sha256': 'contract-sha'},
                    'dataset': {}, 'evidence_admission': admission,
                    'runtime': {'interrupted_answer_delivery_profile': marker}}
        prior = {'correction_id': 'prior'}
        for profile, replacement in [(DELIVERY.GENERAL_PROFILE, DELIVERY.GENERAL_REPLACEMENT),
                                     (DELIVERY.GENERAL_PROFILE_V2, DELIVERY.GENERAL_REPLACEMENT_V2)]:
            manifest['runtime']['interrupted_answer_delivery_profile'] = {**marker, 'profile': profile}
            fixed, receipt = DELIVERY.effective_source(manifest, source, source, prior)
            self.assertEqual(fixed, source.replace(DELIVERY.GUARD, replacement))
            self.assertEqual(receipt['prior_correction'], prior)
            namespace = {'hashlib': hashlib, '_visible_text': lambda row: row.get('content', '')}
            exec(compile(fixed, '<general-failure-answer>', 'exec'), namespace)
            answer, evidence = namespace['_final_answer']([{'role': 'user', 'content': 'q'}])
            self.assertEqual(answer, '')
            if profile == DELIVERY.GENERAL_PROFILE_V2:
                self.assertIsNone(evidence['event_index'])
                self.assertEqual(evidence['delivery_profile'], profile)
            else:
                self.assertNotIn('event_index', evidence)


if __name__ == "__main__":
    unittest.main()
