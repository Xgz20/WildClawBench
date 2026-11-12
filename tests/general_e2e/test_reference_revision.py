"""Mechanical reference provenance and denominator checks; no production grading."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.general_e2e.test_local_scoring_runtime import RUNTIME

REVISION = RUNTIME.reference_revision


class ReferenceRevisionTests(unittest.TestCase):
    def test_registry_is_hash_bound(self):
        self.assertEqual(REVISION.registry()['corrected_Q'], 57)
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder)/'registry.json'
            file.write_text('{}')
            with patch.object(REVISION, 'DATA', file), self.assertRaisesRegex(ValueError, 'REGISTRY_DRIFT'):
                REVISION.registry()

    def fixture(self, root):
        data = REVISION.registry()
        manifest = {'identity': {'task_id': data['task_id']},
                    'digests': {'contract_sha256': data['original_contract_sha256']}}
        supplement = {'authorization_reference': 'human approved 2026-11-11', 'files': [
            {'sha256': data['corrected_reference_sha256'], 'path': 'files/reference.xlsx'},
            {'sha256': data['independent_review_sha256'], 'path': 'files/review.json'}]}
        target = root/REVISION.reference_supplement.DIRECTORY/'manifest.json'
        target.parent.mkdir(); target.write_text(json.dumps(supplement))
        return manifest, supplement, target

    def test_only_exact_reviewed_reference_and_original_contract_activate(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(REVISION.reference_supplement, 'validate', return_value=[True]):
            root = Path(folder); manifest, supplement, target = self.fixture(root)
            result = REVISION.policy(root, manifest)
            self.assertEqual(result['effective_Q'], 57)
            self.assertFalse(result['formula_and_weights_changed'])
            manifest['digests']['contract_sha256'] = 'a'*64
            self.assertIsNone(REVISION.policy(root, manifest))
            manifest['digests']['contract_sha256'] = REVISION.registry()['original_contract_sha256']
            supplement['files'].pop(); target.write_text(json.dumps(supplement))
            with self.assertRaisesRegex(ValueError, 'REVIEW_AND_REFERENCE_REQUIRED'):
                REVISION.policy(root, manifest)

    def test_coverage_formula_and_unique_matching_ledger_are_enforced(self):
        expected = {'effective_Q': 57}
        response = {'criteria': [{'key': 'C3a_qa_coverage', 'status': 'judged', 'score': 0.95}],
                    'reference_revision_review': {'Q': 57, 'm': 56,
                        'matched_qa_ids': [f'QA{i:03}' for i in range(1,57)]}}
        REVISION.validate_response(expected, response)
        for mutation in ('old-Q', 'duplicate', 'unknown', 'object', 'count', 'formula', 'boolean'):
            with self.subTest(mutation=mutation):
                value = copy.deepcopy(response); review = value['reference_revision_review']
                if mutation == 'old-Q': review['Q'] = 56
                if mutation == 'duplicate': review['matched_qa_ids'][0] = 'QA002'
                if mutation == 'unknown': review['matched_qa_ids'][0] = 'QA058'
                if mutation == 'object': review['matched_qa_ids'][0] = {}
                if mutation == 'count': review['m'] = 55
                if mutation == 'formula': value['criteria'][0]['score'] = 1.0
                if mutation == 'boolean': value['criteria'][0]['score'] = True
                with self.assertRaises(ValueError): REVISION.validate_response(expected, value)


if __name__ == '__main__': unittest.main()
