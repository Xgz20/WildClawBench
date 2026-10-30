from pathlib import Path
import ast
import hashlib
import re
import unittest
from eval_general_e2e.datasets.bundle import _parse_task_source, _strip_codeblock

from tests.general_e2e.test_local_scoring_runtime import RUNTIME, REPO_ROOT


class DatasetRuleCorrectionTests(unittest.TestCase):
    def test_paged_evidence_changes_only_resource_guards_on_exact_sources(self):
        for task_id, (digest, old, new) in RUNTIME.dataset_rule_corrections._PAGED_RULES.items():
            with self.subTest(task_id=task_id):
                task = next((REPO_ROOT / "tasks/general_e2e").rglob(task_id + ".md"))
                _, sections, _ = _parse_task_source(task)
                code = _strip_codeblock(sections["Automated Checks"])
                self.assertEqual(hashlib.sha256(code.encode()).hexdigest(), digest)
                effective, receipt = RUNTIME._effective_rule_source({"identity": {"task_id": task_id}}, code)
                self.assertEqual(effective.replace(new, old), code)
                ast.parse(effective)
                self.assertFalse(receipt["evidence_policy"]["truncation_allowed"])
                self.assertEqual(RUNTIME._effective_rule_source({"identity": {"task_id": task_id}}, code + "\n"), (code + "\n", None))
                self.assertEqual(RUNTIME._effective_rule_source({"identity": {"task_id": "other"}}, code), (code, None))


if __name__ == "__main__":
    unittest.main()
