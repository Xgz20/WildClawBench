import json
from pathlib import Path
import tempfile
import unittest
from tests.general_e2e.test_local_scoring_runtime import Fixture, RUNTIME, sha256_bytes


RULE = "def grade(**kwargs):\n    from pathlib import Path\n    p = Path(kwargs.get('workspace_path'))\n    return {'overall_score': float((p / 'answer.txt').exists())}\n"


class PartialTraceAdmissionTests(unittest.TestCase):
    def test_only_workspace_inputs_are_allowed(self):
        contract = {"grading_type": "automated", "automated_checks": RULE}
        self.assertTrue(RUNTIME._workspace_only_automated_rule(contract))
        for source in [RULE.replace("workspace_path", "transcript"), RULE.replace("kwargs.get('workspace_path')", "kwargs.get(key)"),
                       RULE.replace("p = Path", "other = kwargs\n    p = Path"), RULE.replace("p = Path", "eval('1')\n    p = Path")]:
            self.assertFalse(RUNTIME._workspace_only_automated_rule({**contract, "automated_checks": source}))
        self.assertFalse(RUNTIME._workspace_only_automated_rule({**contract, "grading_type": "hybrid"}))

    def test_prepare_preserves_partial_record_and_rejects_raw_drift(self):
        with tempfile.TemporaryDirectory() as temp:
            f = Fixture(Path(temp), rule=RULE)
            execution = json.loads(f.execution_record.read_text())
            execution["evidence"].update(completeness="partial", missing=["native-tool-trajectory-incomplete"], trace_index_path="evidence/trace-index.json")
            f.execution_record.write_text(json.dumps(execution))
            raw = f.unit_root / "evidence/raw.json"; raw.write_text('{"native":"fixture"}\n')
            transcript = f.unit_root / "evidence/transcript.jsonl"
            def row(p):
                data = p.read_bytes(); return {"path": p.name, "sha256": sha256_bytes(data), "size": len(data)}
            index = {"schema_id": "urn:wildclawbench:schema:general-e2e:trace-index:v2", "identity": execution["identity"],
                     "completeness": {"status": "partial"}, "transcript": row(transcript), "raw_trace": [row(raw)], "binding_evidence": [row(raw)]}
            (f.unit_root / "evidence/trace-index.json").write_text(json.dumps(index))
            attempt = f.prepare()
            manifest = json.loads((attempt / "attempt-manifest.json").read_text())
            self.assertEqual(manifest["evidence_admission"], "automated-workspace-only/v1")
            self.assertEqual(json.loads((attempt / "private/execution-record.json").read_text())["evidence"]["completeness"], "partial")
            RUNTIME.verify_attempt(attempt)
            raw.write_text("changed")
            with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError, "TRACE_ARTIFACT_DRIFT"):
                f.prepare("second")

    def test_trace_grader_semantics_and_missing_candidates_stay_blocked(self):
        execution = {"evidence": {"completeness": "partial", "missing": ["native-tool-trajectory-incomplete"], "transcript_path": "trace", "trace_index_path": "index"}}
        for contract in [{"grading_type": "automated", "automated_checks": RULE.replace("workspace_path", "transcript")},
                         {"grading_type": "llm_judge", "automated_checks": RULE}, {"grading_type": "hybrid", "automated_checks": RULE}]:
            with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError, "EXECUTION_NOT_SCORABLE"):
                RUNTIME._validate_evidence_admission(execution, contract)
        execution["evidence"]["missing"].append("raw_trace")
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError, "EXECUTION_NOT_SCORABLE"):
            RUNTIME._validate_evidence_admission(execution, {"grading_type": "automated", "automated_checks": RULE})
