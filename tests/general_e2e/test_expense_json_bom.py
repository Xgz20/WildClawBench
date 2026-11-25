"""UTF-8 BOM compatibility must preserve the candidate and the business rules."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from eval_general_e2e.datasets.bundle import _parse_task_source, _strip_codeblock
from src.wildclawbench_grading_core.source_repairs import effective_source, profile_entry
from tests.general_e2e.test_local_scoring_runtime import RUNTIME


ROOT = Path(__file__).resolve().parents[2]
TASK = "01_Productivity_Flow_task_001_expense_policy_check"
SOURCE_SHA = "641db66b4245b9cbd97b959dacada889b48ce86e33312bc12a6db023bce85792"
EFFECTIVE_SHA = "ff528beef73aa9bc7ef4cadba196cae09318bd34358d8a234dd56e617acef6c0"
PROFILE = "expense-policy-json-utf8-bom/v1"
WORKSPACE = ROOT / "workspace/general/regression/01_Productivity_Flow" / TASK


class ExpenseJsonBomTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, sections, _ = _parse_task_source(ROOT / "tasks/general/regression/01_Productivity_Flow" / (TASK + ".md"))
        cls.original = _strip_codeblock(sections["Automated Checks"])
        cls.repaired, cls.receipt = effective_source(TASK, cls.original)

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.work = Path(temp.name) / "workspace"
        shutil.copytree(WORKSPACE / "exec", self.work)
        shutil.copytree(WORKSPACE / "gt", self.work / "gt")
        expected = json.loads((self.work / "gt/expected.json").read_text(encoding="utf-8"))
        self.correct = {key: expected[key] for key in (
            "policy_id", "applied_rules", "expenses", "approved_total", "rejected_total")}
        self.output = self.work / "results/reimbursement.json"
        self.output.parent.mkdir(exist_ok=True)

    def write_result(self, value=None, *, bom=False):
        raw = json.dumps(self.correct if value is None else value, ensure_ascii=False).encode("utf-8")
        self.output.write_bytes((b"\xef\xbb\xbf" if bom else b"") + raw)

    def grade(self, source=None):
        # Exercise only this repository-owned frozen rule against synthetic
        # fixtures; this is not a formal score or a sandbox/client acceptance run.
        namespace = {}
        exec(compile(source or self.repaired, "<expense-json-rule-test>", "exec"), namespace)
        return namespace["grade"](workspace_path=str(self.work))

    def test_bom_and_plain_utf8_have_identical_scores_without_rewriting(self):
        self.write_result()
        expected = self.grade(self.original)
        self.assertEqual(expected["overall_score"], 1.0)
        self.assertEqual(self.grade(), expected)
        self.write_result(bom=True)
        original_bytes = self.output.read_bytes()
        self.assertEqual(self.grade(self.original)["overall_score"], 0.0)
        self.assertEqual(self.grade(), expected)
        self.assertEqual(self.output.read_bytes(), original_bytes)

    def test_wrong_policy_and_totals_are_still_penalized_with_bom(self):
        wrong = deepcopy(self.correct)
        wrong["policy_id"] = "wrong-policy"
        wrong["approved_total"] += 100
        wrong["rejected_total"] += 100
        self.write_result(wrong)
        expected = self.grade(self.original)
        self.assertEqual(expected["applicable_policy_correct"], 0.0)
        self.assertEqual(expected["totals_correct"], 0.0)
        self.write_result(wrong, bom=True)
        self.assertEqual(self.grade(), expected)

    def test_input_hash_protection_is_unchanged(self):
        self.write_result(bom=True)
        with (self.work / "expenses.csv").open("ab") as stream:
            stream.write(b"\nchanged-input")
        self.assertTrue(all(score == 0.0 for score in self.grade().values()))

    def test_bom_character_inside_a_json_value_is_not_removed(self):
        wrong = deepcopy(self.correct)
        wrong["policy_id"] = "\ufeff" + wrong["policy_id"]
        self.write_result(wrong)
        expected = self.grade(self.original)
        self.assertEqual(expected["applicable_policy_correct"], 0.0)
        self.write_result(wrong, bom=True)
        self.assertEqual(self.grade(), expected)

    def test_malformed_or_other_encodings_are_not_repaired(self):
        for raw in (b'\xef\xbb\xbf{"policy_id":', b'\xef\xbb\xbf\xef\xbb\xbf{}',
                    b' \xef\xbb\xbf{}', json.dumps(self.correct).encode("utf-16")):
            with self.subTest(prefix=raw[:12]):
                self.output.write_bytes(raw)
                self.assertTrue(all(score == 0.0 for score in self.grade().values()))

    def test_exact_source_binding_and_audit(self):
        self.assertEqual(hashlib.sha256(self.original.encode()).hexdigest(), SOURCE_SHA)
        self.assertEqual(hashlib.sha256(self.repaired.encode()).hexdigest(), EFFECTIVE_SHA)
        self.assertEqual(profile_entry(SOURCE_SHA)["profile"], PROFILE)
        self.assertEqual(self.receipt["original_source_sha256"], SOURCE_SHA)
        self.assertEqual(self.receipt["effective_source_sha256"], EFFECTIVE_SHA)
        self.assertFalse(self.receipt["candidate_rewritten"])
        self.assertFalse(self.receipt["rubric_and_weights_changed"])
        self.assertEqual(effective_source("different-task", self.original), (self.original, None))
        self.assertEqual(effective_source(TASK, self.original + "\n"), (self.original + "\n", None))

    def test_old_attempts_keep_original_source_and_new_markers_are_verified(self):
        contract = {"task_id": TASK, "automated_checks": self.original}
        manifest = {"identity": {"task_id": TASK}, "runtime": {}}
        self.assertEqual(RUNTIME._effective_rule_source(manifest, self.original), (self.original, None))
        marker = RUNTIME.shared_source_repairs.marker(contract)
        self.assertEqual(marker["profile"], PROFILE)
        manifest["runtime"]["shared_rule_source_repair"] = marker
        source, receipt = RUNTIME._effective_rule_source(manifest, self.original)
        self.assertEqual(source, self.repaired)
        self.assertEqual(receipt["correction_id"], PROFILE)
        manifest["runtime"]["shared_rule_source_repair"] = {**marker, "current_source_sha256": "0" * 64}
        with self.assertRaisesRegex(ValueError, "RULE_SOURCE_CORRECTION_MISMATCH"):
            RUNTIME._effective_rule_source(manifest, self.original)


if __name__ == "__main__":
    unittest.main()
