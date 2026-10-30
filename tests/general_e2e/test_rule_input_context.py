from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from tests.general_e2e.test_local_scoring_runtime import RUNTIME


class RuleInputContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for name in ("candidate-original/workspace", "private", "trace/raw", "worker"):
            (self.root / name).mkdir(parents=True, exist_ok=True)
        self.context = "Public case scope.\nUse the declared historical period.\n"
        (self.root / "candidate-original/workspace/AGENTS.md").write_text(self.context, encoding="utf-8")
        self.transcript = [{"type": "user_message", "role": "user", "content": "question"},
                           {"type": "assistant_message", "role": "assistant", "content": "answer", "final": True}]
        data = "".join(json.dumps(r) + "\n" for r in self.transcript).encode()
        (self.root / "private/transcript.jsonl").write_bytes(data)
        self.contract = {"judge_evidence": {"required": [{"path": "evaluator_evidence/task_context.md", "role": "public_task_context"}]}}
        (self.root / "private/contract.json").write_text(json.dumps(self.contract))
        session = {"session_id": "session", "turn_id": "turn", "cwd": "/bound/workspace"}
        (self.root / "private/execution-record.json").write_text(json.dumps({"session": session}))
        (self.root / "trace/bundle-manifest.json").write_text(json.dumps({"raw_trace": ["raw/astronstudio-rollout.jsonl"]}))
        self.manifest = {"identity": {"task_id": "fixture"},
            "paths": {"candidate_original": "candidate-original/workspace", "execution_record": "private/execution-record.json",
                      "transcript": "private/transcript.jsonl", "contract": "private/contract.json"},
            "digests": {"transcript_sha256": RUNTIME._sha256_bytes(data)},
            "runtime": {"evaluator_input_profile": RUNTIME.EVALUATOR_INPUT_PROFILE},
            "trace_bundle": {"path": "trace/bundle-manifest.json"}}
        self.rows = [
            {"type": "session_meta", "payload": {"id": "session", "cwd": session["cwd"]}},
            {"type": "event_msg", "payload": {"type": "task_started", "turn_id": "turn"}},
            {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text":
                "<recommended_plugins>public metadata</recommended_plugins>\n# AGENTS.md instructions for /bound/workspace\n\n" + self.context}]}},
            {"type": "world_state", "payload": {"state": {"agents_md": {"directory": session["cwd"], "text": self.context}}}},
            {"type": "turn_context", "payload": {"turn_id": "turn", "cwd": session["cwd"]}},
            {"type": "event_msg", "payload": {"type": "user_message", "message": "question"}},
        ]
        self.write_raw()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_raw(self) -> None:
        (self.root / "trace/raw/astronstudio-rollout.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in self.rows), encoding="utf-8")

    def test_bound_native_user_instruction_and_verified_finality_are_only_rule_views(self) -> None:
        original = (self.root / "private/transcript.jsonl").read_bytes()
        canonical = RUNTIME._canonical_rule_view(self.transcript)
        self.assertTrue(canonical[-1]["end_turn"])
        self.assertEqual(canonical[-1]["channel"], "final")
        self.assertNotIn("end_turn", self.transcript[-1])
        view, proof = RUNTIME._native_context_rule_input(self.root, self.manifest, self.contract, canonical)
        self.assertEqual(proof["raw_line"], 3)
        self.assertEqual(view[0]["role"], "user")
        self.assertIn(self.context.strip(), view[0]["content"])
        self.assertEqual((self.root / "private/transcript.jsonl").read_bytes(), original)
        (self.root / "rule-input-context.json").write_text(json.dumps(proof))
        (self.root / "worker/request.json").write_text(json.dumps({"transcript": view}))
        RUNTIME._verify_rule_input_context(self.root, self.manifest)
        view[0]["content"] = "fabricated context"
        (self.root / "worker/request.json").write_text(json.dumps({"transcript": view}))
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError, "RULE_INPUT_CONTEXT_DRIFT"):
            RUNTIME._verify_rule_input_context(self.root, self.manifest)

    def test_file_presence_world_state_or_assistant_quotes_do_not_prove_delivery(self) -> None:
        for mutation in ("assistant", "missing_header", "late"):
            with self.subTest(mutation=mutation):
                rows = json.loads(json.dumps(self.rows))
                if mutation == "assistant":
                    rows[2]["payload"]["role"] = "assistant"
                elif mutation == "missing_header":
                    rows[2]["payload"]["content"][0]["text"] = self.context
                else:
                    rows.append(rows.pop(2))
                (self.root / "trace/raw/astronstudio-rollout.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
                view, proof = RUNTIME._native_context_rule_input(self.root, self.manifest, self.contract, self.transcript)
                self.assertIsNone(proof)
                self.assertEqual(view, self.transcript)

    def test_wrong_session_turn_or_loaded_directory_fail_closed(self) -> None:
        for field in ("session", "turn", "directory"):
            with self.subTest(field=field):
                rows = json.loads(json.dumps(self.rows))
                if field == "session": rows[0]["payload"]["id"] = "other"
                elif field == "turn": rows[1]["payload"]["turn_id"] = "other"
                else: rows[3]["payload"]["state"]["agents_md"]["directory"] = "/other"
                (self.root / "trace/raw/astronstudio-rollout.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
                with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError, "NATIVE_PUBLIC_CONTEXT_BINDING_INVALID"):
                    RUNTIME._native_context_rule_input(self.root, self.manifest, self.contract, self.transcript)

    def test_declared_evaluator_namespace_is_snapshotted_without_treating_deliverables_as_generated(self) -> None:
        contract = {"judge_evidence": {"required": [
            {"path": "evaluator_evidence/reference.md", "role": "evaluator_reference_not_agent_output"},
            {"path": "evaluator_evidence/answer.md", "role": "evaluator_extracted_candidate_final"},
            {"path": "results/report.xlsx", "role": "deliverable"}]}}
        self.assertEqual(RUNTIME._required_generated_evidence(contract), [])
        self.assertEqual(RUNTIME._required_generated_evidence(contract, extended=True),
                         ["evaluator_evidence/reference.md", "evaluator_evidence/answer.md"])

    def workbuddy_fixture(self) -> list[dict]:
        path = self.root / "private/execution-record.json"
        execution = json.loads(path.read_text())
        execution.update(identity={"task_id": "fixture"}, harness={"id": "workbuddy"},
                         prompt={"sha256": RUNTIME._sha256_bytes(b"question")})
        path.write_text(json.dumps(execution))
        (self.root / "trace/raw/workbuddy-runtime").mkdir(exist_ok=True)
        (self.root / "trace/raw/workbuddy-runtime/runtime-binding.json").write_text(json.dumps({
            "identity": execution["identity"], "source_kind": "workbuddy-runtime-api", "runtime_snapshot": {
                "conversation": {"id": "session", "space": {"cwd": "/bound/workspace"}},
                "request": {"id": "turn", "conversationRequestId": "turn", "traceId": "distributed",
                    "userMessage": {"content": [{"type": "text", "text": "question"}]}}}}))
        (self.root / "trace/bundle-manifest.json").write_text(json.dumps({"raw_trace": [
            "raw/workbuddy-session.jsonl", "raw/workbuddy-runtime/runtime-binding.json"]}))
        rows = [{"type": "message", "role": "user", "sessionId": "session", "cwd": "/bound/workspace",
                 "providerData": {"conversationRequestId": "turn", "startsNewUserRequest": True},
                 "content": [{"type": "input_text", "text": "<system-reminder>\nFile: /bound/workspace/AGENTS.md\n"
                     + self.context + "</system-reminder>\n<user_query>question</user_query>"}]}]
        self.write_workbuddy(rows)
        return rows

    def write_workbuddy(self, rows: list[dict]) -> None:
        (self.root / "trace/raw/workbuddy-session.jsonl").write_text("".join(json.dumps(row)+"\n" for row in rows), encoding="utf-8")

    def test_workbuddy_bound_public_context_is_preserved_as_a_reverified_rule_view(self) -> None:
        self.workbuddy_fixture()
        before = (self.root / "private/transcript.jsonl").read_bytes()
        canonical = RUNTIME._canonical_rule_view(self.transcript)
        view, proof = RUNTIME._native_context_rule_input(self.root, self.manifest, self.contract, canonical)
        self.assertEqual(proof["raw_line"], 1)
        self.assertEqual(view[0]["source"]["adapter"], "bound-workbuddy-user-instructions/v1")
        self.assertIn(self.context.strip(), view[0]["content"])
        (self.root / "rule-input-context.json").write_text(json.dumps(proof))
        (self.root / "worker/request.json").write_text(json.dumps({"transcript": view}))
        RUNTIME._verify_rule_input_context(self.root, self.manifest)
        self.assertEqual((self.root / "private/transcript.jsonl").read_bytes(), before)
        binding_path = self.root / "trace/raw/workbuddy-runtime/runtime-binding.json"
        binding = json.loads(binding_path.read_text())
        binding["runtime_snapshot"]["request"]["id"] = "other"
        binding_path.write_text(json.dumps(binding))
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError, "NATIVE_PUBLIC_CONTEXT_BINDING_INVALID"):
            RUNTIME._verify_rule_input_context(self.root, self.manifest)

    def test_workbuddy_context_rejects_other_requests_and_does_not_infer_file_delivery(self) -> None:
        original = self.workbuddy_fixture()
        for mutation in ("session", "request", "cwd", "assistant", "duplicate", "not_new_request", "missing_header", "late_context"):
            with self.subTest(mutation=mutation):
                rows = json.loads(json.dumps(original))
                if mutation == "session": rows[0]["sessionId"] = "other"
                elif mutation == "request": rows[0]["providerData"]["conversationRequestId"] = "other"
                elif mutation == "cwd": rows[0]["cwd"] = "/other"
                elif mutation == "assistant": rows[0]["role"] = "assistant"
                elif mutation == "duplicate": rows.append(rows[0])
                elif mutation == "not_new_request": rows[0]["providerData"]["startsNewUserRequest"] = False
                elif mutation == "missing_header": rows[0]["content"][0]["text"] = self.context + "<user_query>question</user_query>"
                else: rows[0]["content"][0]["text"] = "<user_query>question</user_query>\nFile: /bound/workspace/AGENTS.md\n" + self.context
                self.write_workbuddy(rows)
                if mutation in {"missing_header", "late_context"}:
                    view, proof = RUNTIME._native_context_rule_input(self.root, self.manifest, self.contract, self.transcript)
                    self.assertIsNone(proof)
                    self.assertEqual(view, self.transcript)
                else:
                    with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError, "NATIVE_PUBLIC_CONTEXT_BINDING_INVALID"):
                        RUNTIME._native_context_rule_input(self.root, self.manifest, self.contract, self.transcript)


if __name__ == "__main__":
    unittest.main()
