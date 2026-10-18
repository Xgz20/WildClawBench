from __future__ import annotations

import copy
import json
import subprocess
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from eval_memory_e2e import DIMENSIONS, HARNESS_PORTS
from eval_memory_e2e.batch import load_batch, operation_id, prepare
from eval_memory_e2e.dataset import DATA, load_dataset, materialize
from eval_memory_e2e.fixture_driver import respond
from eval_memory_e2e.io import (MemoryEvaluationError, append, decode, digest, encoded, events,
                                lock, publish, read_json, safe_file, sha)
from eval_memory_e2e.probe import native_preflight
from eval_memory_e2e.report import aggregate, write_report
from eval_memory_e2e.runner import advance, import_receipt, next_action, register_intent
from eval_memory_e2e.scoring import import_review, review_template


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / "batch"

    def test_native_ui_lock_blocks_before_creating_a_new_send_intent(self):
        self.prepare(mode='native')
        item = self.episodes()[0]
        shared = self.base / '.memory-native-ui.lock'
        shared.write_text('{"id":"foreign-owner"}')
        for action in (advance, register_intent):
            with self.subTest(action=action.__name__), self.assertRaises(MemoryEvaluationError) as error:
                action(self.root, item['id'])
            self.assertEqual(error.exception.code, 'NATIVE_UI_LOCK_PRESENT')
        self.assertEqual(events(self.root), [])
        self.assertTrue(shared.exists())

    def test_explicit_global_ui_lock_is_independent_of_batch_parent(self):
        from eval_memory_e2e.batch import memory_ui_lock_path, MEMORY_UI_LOCK
        profile = {'WorkBuddy': {'ui_lock_path': str(MEMORY_UI_LOCK)}}
        self.assertEqual(memory_ui_lock_path('/one/batch', profile), memory_ui_lock_path('/two/nested/batch', profile))
        self.assertEqual(memory_ui_lock_path('/old/batch', {'WorkBuddy': {}}), Path('/old/.memory-native-ui.lock'))
        with self.assertRaises(MemoryEvaluationError):
            memory_ui_lock_path('/one/batch', {'WorkBuddy': {'ui_lock_path': '/Users/gzx/.codex/config.toml'}})

    def test_manual_advance_and_handoff_cannot_start_the_next_harness_early(self):
        self.prepare(harnesses=('AstronStudio','WorkBuddy'), scenarios=('MEM-01','MEM-10'))
        first, second = self.episodes()[0], next(e for e in self.episodes() if e['harness']=='WorkBuddy')
        self.complete(first)
        for action in (advance, register_intent):
            with self.subTest(action=action.__name__), self.assertRaises(MemoryEvaluationError) as error:
                action(self.root,second['id'])
            self.assertEqual(error.exception.code,'PREDECESSOR_HARNESS_INCOMPLETE')
        self.assertFalse(any(e['kind']=='INTENT' and e['episode_id']==second['id'] for e in events(self.root)))
        for item in self.episodes():
            if item['harness']=='AstronStudio':self.complete(item)
        self.assertEqual(advance(self.root,second['id'])['status'],'completed')

    def test_unresolved_control_error_is_attention_until_the_same_operation_has_a_new_receipt(self):
        self.prepare();item=self.episodes()[0]
        request=register_intent(self.root,item['id'])
        append(self.root,'UNCERTAIN',item['id'],{'operation_id':request['operation_id'],'error_code':'DRIVER_TRANSPORT_TIMEOUT'})
        row=aggregate(self.root,include_fixture=True)['episodes'][0]
        self.assertEqual(row['execution_status'],'needs_attention');self.assertEqual(row['status'],'evaluation_error');self.assertIsNone(row['score'])
        reply=respond({**request,'transport_action':'dispatch'});path=publish(self.base/'recovered.json',reply)
        import_receipt(self.root,item['id'],path)
        row=aggregate(self.root,include_fixture=True)['episodes'][0]
        self.assertEqual(row['unresolved_control_errors'],[]);self.assertEqual(row['status'],'unscored')

    def prepare(self, scenarios=("MEM-01",), repeats=1, mode="fixture", harnesses=("AstronStudio",)):
        return prepare(self.root, batch_id="test-memory", seed="seed-v1", repeats=repeats,
                       scenario_ids=list(scenarios), harnesses=list(harnesses), mode=mode)

    def episodes(self):
        return load_batch(self.root)["episodes"]

    def complete(self, item):
        while next_action(self.root, item["id"])["status"] != "COMPLETED":
            advance(self.root, item["id"])

    def review(self, item, quality=1):
        review = review_template(self.root, item["id"])
        review["judge_context_id"] = "independent-fixture-judge"
        for check in review["checkpoints"]:
            check["value"] = quality if check["direction"] == "higher" else 1 - quality
            check["reason"] = "离线协议测试判定，不是实际模型成绩。"
            artifact = check["available_evidence"]["final_response"]
            check["evidence"] = [{"step_id": check["step_id"], "artifact": "final_response",
                                  "sha256": artifact["sha256"],
                                  "quote": (self.root / artifact["path"]).read_text().strip()}]
        return review

    def save_review(self, item, review):
        path = self.base / (item["id"] + ".review.json")
        publish(path, review)
        return path

    def test_twenty_cases_distribution_and_checkpoints(self):
        data = load_dataset()
        self.assertEqual(len(data["scenarios"]), 20)
        self.assertEqual(Counter(c["dimension"] for c in data["scenarios"]), DIMENSIONS)
        self.assertEqual(Counter(c["difficulty"] for c in data["scenarios"]), {"easy": 6, "medium": 8, "hard": 6})
        self.assertEqual(sum(len(c["checkpoints"]) for c in data["scenarios"]), 61)
        self.assertEqual(len(list(DATA.parent.glob("MEM-*.json"))), 20)

    def test_repeat_variants_are_fresh_and_deterministic(self):
        case = load_dataset()["scenarios"][0]
        first = materialize(case, "seed", 1)
        self.assertEqual(first, materialize(case, "seed", 1))
        self.assertNotEqual(first["variant_id"], materialize(case, "seed", 2)["variant_id"])
        self.assertNotIn(first["variant_id"], first["steps"][-1]["prompt"])

    def test_full_plan_is_160_chains_and_three_repeats_480(self):
        info = prepare(self.root, batch_id="full", seed="fresh", repeats=3)
        self.assertEqual(info["episode_count"], 480)
        self.assertEqual(len(load_batch(self.root)["episodes"]), 480)

    def test_public_materials_exclude_rubrics_and_answers(self):
        self.prepare()
        manifest = load_batch(self.root)
        public = [read_json(self.root / ep["plan_path"]) for ep in manifest["episodes"]]
        for plan in public:
            self.assertNotIn("checkpoints", json.dumps(plan))
            self.assertNotIn("expectation", json.dumps(plan))
        cold_steps = public[0]["steps"]
        self.assertEqual(len(cold_steps), 1)
        self.assertTrue(all(step["phase"] == "probe" for step in cold_steps))
        experienced_probe = [step for step in public[1]["steps"] if step["phase"] == "probe"]
        self.assertEqual(cold_steps[0]["prompt"], experienced_probe[0]["prompt"])

    def test_reprepare_does_not_overwrite(self):
        self.prepare()
        original = (self.root / "manifest.json").read_bytes()
        with self.assertRaisesRegex(MemoryEvaluationError, str(self.root)):
            self.prepare()
        self.assertEqual(original, (self.root / "manifest.json").read_bytes())

    def test_scope_escape_rejected_before_creating_root(self):
        with self.assertRaises(MemoryEvaluationError):
            self.prepare(scenarios=("../secret",))
        self.assertFalse(self.root.exists())

    def test_manifest_and_private_input_drift_rejected(self):
        self.prepare()
        path = self.root / "private/scenarios.json"
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaises(MemoryEvaluationError) as error:
            load_batch(self.root)
        self.assertEqual(error.exception.code, "INPUT_DRIFT")

    def test_symlink_inputs_rejected(self):
        self.prepare()
        path = self.root / self.episodes()[0]["plan_path"]
        target = self.base / "original.json"
        path.rename(target)
        path.symlink_to(target)
        with self.assertRaises(MemoryEvaluationError) as error:
            load_batch(self.root)
        self.assertEqual(error.exception.code, "SYMLINK_REJECTED")

    def test_nonfinite_and_duplicate_json_rejected(self):
        for text in ('{"x": NaN}', '{"x": 1,"x":2}', '{"x":1e999}'):
            with self.subTest(text=text), self.assertRaises(MemoryEvaluationError):
                decode(text)

    def test_native_batch_has_no_unverified_default_driver(self):
        self.prepare(mode="native")
        first = self.episodes()[0]
        with self.assertRaises(MemoryEvaluationError) as error:
            advance(self.root, first["id"])
        self.assertEqual(error.exception.code, "DRIVER_NOT_CONFIGURED")
        self.assertEqual(events(self.root), [])

    def test_fixture_refuses_native_request(self):
        with self.assertRaises(ValueError):
            respond({"mode": "native"})

    def test_cold_must_finish_before_experienced(self):
        self.prepare()
        with self.assertRaises(MemoryEvaluationError) as error:
            register_intent(self.root, self.episodes()[1]["id"])
        self.assertEqual(error.exception.code, "PREDECESSOR_INCOMPLETE")
        self.assertEqual(events(self.root), [])

    def test_timeout_recovers_by_observation_never_dispatch(self):
        self.prepare()
        first = self.episodes()[0]["id"]
        request = None
        def dispatch_then_timeout(command, **kwargs):
            nonlocal request
            request = decode(kwargs["input"])
            respond(request)  # accepted by Driver, controller loses its reply
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        with patch("eval_memory_e2e.runner.subprocess.run", side_effect=dispatch_then_timeout):
            with self.assertRaises(MemoryEvaluationError) as error:
                advance(self.root, first)
        self.assertEqual(error.exception.code, "DRIVER_TRANSPORT_TIMEOUT")
        self.assertEqual(next_action(self.root, first)["status"], "OBSERVE_ONLY")
        real_run = subprocess.run
        def observe_only(command, **kwargs):
            self.assertEqual(decode(kwargs["input"])["transport_action"], "observe")
            return real_run(command, **kwargs)
        with patch("eval_memory_e2e.runner.subprocess.run", side_effect=observe_only):
            result = advance(self.root, first)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(sum(event["kind"] == "INTENT" for event in events(self.root)), 1)

    def test_duplicate_intent_and_unbound_receipt_rejected(self):
        self.prepare()
        item = self.episodes()[0]
        request = register_intent(self.root, item["id"])
        with self.assertRaises(MemoryEvaluationError):
            register_intent(self.root, item["id"])
        reply = respond({**request, "transport_action": "dispatch"})
        reply["namespace"] = "wrong-scope"
        path = self.base / "wrong.json"
        publish(path, reply)
        with self.assertRaises(MemoryEvaluationError) as error:
            import_receipt(self.root, item["id"], path)
        self.assertEqual(error.exception.code, "NATIVE_BINDING_MISMATCH")

    def test_candidate_files_not_repaired_between_steps(self):
        self.prepare(scenarios=("MEM-19",))
        cold, experienced = self.episodes()
        self.complete(cold)
        advance(self.root, experienced["id"])  # prepare namespace
        advance(self.root, experienced["id"])  # learning
        candidate = Path(experienced["workspaces"]["A"]) / "quote_tool.py"
        candidate.unlink()
        advance(self.root, experienced["id"])
        self.assertFalse(candidate.exists())

    def test_continuation_preserves_session_but_changes_turn(self):
        self.prepare(scenarios=("MEM-04",))
        for item in self.episodes():
            self.complete(item)
        experienced = self.episodes()[1]["id"]
        records = [event["payload"] for event in events(self.root) if event["kind"] == "RECEIPT"
                   and event["episode_id"] == experienced and event["payload"]["step_id"] != "prepare"]
        self.assertEqual(records[0]["native"]["session_id"], records[1]["native"]["session_id"])
        self.assertNotEqual(records[0]["native"]["turn_id"], records[1]["native"]["turn_id"])
        self.assertNotEqual(records[1]["native"]["session_id"], records[2]["native"]["session_id"])

    def test_restart_requires_process_evidence(self):
        self.prepare(scenarios=("MEM-03",))
        item = self.episodes()[0]
        advance(self.root, item["id"])
        request = register_intent(self.root, item["id"])
        self.assertEqual(request["session_action"], "restart_new")
        reply = respond({**request, "transport_action": "dispatch"})
        reply.pop("restart_evidence")
        path = self.base / "restart.json"
        publish(path, reply)
        with self.assertRaises(MemoryEvaluationError) as error:
            import_receipt(self.root, item["id"], path)
        self.assertEqual(error.exception.code, "RESTART_UNVERIFIED")

    def test_configuration_drift_rejected(self):
        self.prepare()
        item = self.episodes()[0]
        advance(self.root, item["id"])
        request = register_intent(self.root, item["id"])
        reply = respond({**request, "transport_action": "dispatch"})
        reply["actual_config"]["model_display"] = "different-model"
        path = self.base / "config-drift.json"
        publish(path, reply)
        with self.assertRaises(MemoryEvaluationError) as error:
            import_receipt(self.root, item["id"], path)
        self.assertEqual(error.exception.code, "CONFIG_DRIFT")

    def test_unsupported_is_separate_from_valid_zero(self):
        self.prepare()
        item = self.episodes()[0]
        request = register_intent(self.root, item["id"])
        reply = respond({**request, "transport_action": "dispatch"})
        reply.update(status="unsupported_product", reason="明确的原生不支持证据")
        path = self.base / "unsupported.json"
        publish(path, reply)
        import_receipt(self.root, item["id"], path)
        report = aggregate(self.root, include_fixture=True)
        self.assertEqual(report["episodes"][0]["status"], "unsupported_product")
        self.assertIsNone(report["episodes"][0]["score"])

    def test_journal_tampering_and_partial_append_rejected(self):
        self.prepare()
        item = self.episodes()[0]
        register_intent(self.root, item["id"])
        path = self.root / "events.jsonl"
        original = path.read_bytes()
        path.write_bytes(original.replace(b'"INTENT"', b'"FORGED"'))
        with self.assertRaises(MemoryEvaluationError) as error:
            events(self.root)
        self.assertEqual(error.exception.code, "JOURNAL_INTEGRITY")
        path.write_bytes(original + b'{"incomplete":')
        with self.assertRaises(MemoryEvaluationError) as error:
            events(self.root)
        self.assertEqual(error.exception.code, "JOURNAL_TRUNCATED")

    def test_incomplete_execution_cannot_be_scored(self):
        self.prepare()
        with self.assertRaises(MemoryEvaluationError):
            review_template(self.root, self.episodes()[0]["id"])

    def test_valid_zero_keeps_score_and_coverage(self):
        self.prepare()
        for item in self.episodes():
            self.complete(item)
            result = import_review(self.root, self.save_review(item, self.review(item, quality=0)))
            self.assertEqual(result["result"], "valid")
            self.assertEqual(result["score"], 0)
        report = aggregate(self.root, include_fixture=True)
        self.assertEqual(report["units"]["AstronStudio"]["valid_scenarios"], 1)
        self.assertEqual(report["units"]["AstronStudio"]["score"], 0)

    def test_lower_is_better_metrics_and_required_checks(self):
        self.prepare(scenarios=("MEM-10",))
        item = self.episodes()[0]
        self.complete(item)
        review = self.review(item)
        bad = next(c for c in review["checkpoints"] if c["metric"] == "stale_value_misuse")
        bad["value"] = 1
        result = import_review(self.root, self.save_review(item, review))
        self.assertFalse(result["success"])
        self.assertAlmostEqual(result["score"], 2/3)

    def test_missing_checkpoint_rejected(self):
        self.prepare()
        item = self.episodes()[0]
        self.complete(item)
        review = self.review(item)
        review["checkpoints"].pop()
        with self.assertRaises(MemoryEvaluationError) as error:
            import_review(self.root, self.save_review(item, review))
        self.assertEqual(error.exception.code, "CHECKPOINT_SCOPE")

    def test_citation_must_match_exact_probe_and_frozen_bytes(self):
        self.prepare()
        item = self.episodes()[0]
        self.complete(item)
        review = self.review(item)
        review["checkpoints"][0]["evidence"][0]["quote"] = "fabricated source quote"
        with self.assertRaises(MemoryEvaluationError) as error:
            import_review(self.root, self.save_review(item, review))
        self.assertEqual(error.exception.code, "CITATION_NOT_FOUND")

    def test_judge_cannot_reuse_candidate_context(self):
        self.prepare()
        item = self.episodes()[0]
        self.complete(item)
        review = self.review(item)
        receipt = next(e["payload"] for e in events(self.root)
                       if e["kind"] == "RECEIPT" and e["payload"].get("native"))
        review["judge_context_id"] = receipt["native"]["session_id"]
        with self.assertRaises(MemoryEvaluationError) as error:
            import_review(self.root, self.save_review(item, review))
        self.assertEqual(error.exception.code, "JUDGE_CONTEXT_OVERLAP")

    def test_evidence_drift_prevents_reporting(self):
        self.prepare()
        item = self.episodes()[0]
        self.complete(item)
        import_review(self.root, self.save_review(item, self.review(item)))
        review = review_template(self.root, item["id"])
        artifact = review["checkpoints"][0]["available_evidence"]["final_response"]
        (self.root / artifact["path"]).write_bytes(b"changed")
        with self.assertRaises(MemoryEvaluationError) as error:
            aggregate(self.root, include_fixture=True)
        self.assertEqual(error.exception.code, "ARTIFACT_DRIFT")

    def test_partial_repeats_do_not_inflate_scenario_count(self):
        self.prepare(repeats=2)
        for item in self.episodes()[:2]:
            self.complete(item)
            import_review(self.root, self.save_review(item, self.review(item)))
        report = aggregate(self.root, include_fixture=True)
        unit = report["units"]["AstronStudio"]
        self.assertEqual(unit["valid_scenarios"], 0)
        self.assertIsNone(unit["score"])
        self.assertEqual(report["experience_gain"]["AstronStudio"]["scenario_count"], 0)

    def test_paired_delta_preserves_negative_gains(self):
        self.prepare()
        for item in self.episodes():
            self.complete(item)
            quality = 1 if item["arm"] == "C0" else 0
            import_review(self.root, self.save_review(item, self.review(item, quality)))
        gain = aggregate(self.root, include_fixture=True)["experience_gain"]["AstronStudio"]
        self.assertEqual(gain["scenario_count"], 1)
        self.assertEqual(gain["delta"], -1)
        self.assertIsNone(gain["bootstrap_95"])

    def test_negative_controls_excluded_from_experience_gain(self):
        self.prepare(scenarios=("MEM-13",))
        for item in self.episodes():
            self.complete(item)
            import_review(self.root, self.save_review(item, self.review(item)))
        gain = aggregate(self.root, include_fixture=True)["experience_gain"]["AstronStudio"]
        self.assertEqual(gain["scenario_count"], 0)
        self.assertIsNone(gain["delta"])

    def test_common_scope_requires_every_harness(self):
        self.prepare(harnesses=("AstronStudio", "WorkBuddy"))
        for item in self.episodes()[:2]:
            self.complete(item)
            import_review(self.root, self.save_review(item, self.review(item)))
        report = aggregate(self.root, include_fixture=True)
        self.assertEqual(report["common_scenarios"], [])
        self.assertIsNone(report["common_scores"]["AstronStudio"])

    def test_fixture_report_rejected_without_explicit_opt_in(self):
        self.prepare()
        with self.assertRaises(MemoryEvaluationError) as error:
            aggregate(self.root)
        self.assertEqual(error.exception.code, "FIXTURE_NOT_FORMAL")

    def test_report_json_and_markdown_share_same_scope(self):
        self.prepare()
        output = self.base / "report"
        result = write_report(self.root, output, include_fixture=True)
        self.assertEqual(result["status"], "FIXTURE_ONLY")
        report = read_json(output / "report.json")
        markdown = (output / "report.md").read_text()
        self.assertIn("FIXTURE_ONLY", markdown)
        for item in report["episodes"]:
            self.assertIn(item["id"], markdown)
        self.assertIsNone(report["internal_retrieval_metrics"]["recall_at_k"])
        self.assertEqual(report["resource_metrics"]["status"], "unavailable")

    def test_parent_traversal_cannot_escape_artifact_root(self):
        directory = self.base / "inside"
        directory.mkdir()
        secret = self.base / "outside.json"
        secret.write_text("{}")
        with self.assertRaises(MemoryEvaluationError) as error:
            safe_file(directory / ".." / "outside.json", directory)
        self.assertEqual(error.exception.code, "PATH_ESCAPE")

    def test_candidate_snapshot_survives_later_candidate_changes(self):
        self.prepare(scenarios=("MEM-19",))
        cold, experienced = self.episodes()
        self.complete(cold)
        advance(self.root, experienced["id"])
        advance(self.root, experienced["id"])
        saved = next(event["payload"] for event in events(self.root)
                     if event["episode_id"] == experienced["id"] and event["kind"] == "RECEIPT"
                     and event["payload"]["step_id"] == "s1")
        self.assertTrue(saved["candidate_snapshot"])
        artifact = saved["candidate_snapshot"][0]["artifact"]
        original = (self.root / artifact["path"]).read_bytes()
        (Path(experienced["workspaces"]["A"]) / "quote_tool.py").write_text("# changed later\n")
        self.assertEqual(original, (self.root / artifact["path"]).read_bytes())
        self.complete(experienced)

    def test_relabeling_fixture_as_native_is_rejected(self):
        self.prepare(mode="native")
        item = self.episodes()[0]
        request = register_intent(self.root, item["id"])
        reply = respond({**request, "mode": "fixture", "transport_action": "dispatch"})
        reply["mode"] = "native"
        path = self.base / "relabeled.json"
        publish(path, reply)
        with self.assertRaises(MemoryEvaluationError) as error:
            import_receipt(self.root, item["id"], path)
        self.assertEqual(error.exception.code, "FIXTURE_NOT_NATIVE")

    def test_unknown_background_needs_frozen_observation_window(self):
        self.prepare()
        item = self.episodes()[0]
        request = register_intent(self.root, item["id"])
        reply = respond({**request, "transport_action": "dispatch"})
        reply["background_settled"] = None
        reply["memory_observation"] = {"status": "unobservable", "wait_seconds": 3}
        path = self.base / "too-early.json"
        publish(path, reply)
        with self.assertRaises(MemoryEvaluationError) as error:
            import_receipt(self.root, item["id"], path)
        self.assertEqual(error.exception.code, "BACKGROUND_UNSETTLED")
        reply["memory_observation"]["wait_seconds"] = 10
        path2 = self.base / "observed-window.json"
        publish(path2, reply)
        imported = import_receipt(self.root, item["id"], path2)
        self.assertIsNone(imported["background_settled"])

    def test_known_pending_background_is_not_hidden_as_unknown(self):
        self.prepare()
        item = self.episodes()[0]
        request = register_intent(self.root, item["id"])
        reply = respond({**request, "transport_action": "dispatch"})
        reply["background_settled"] = False
        reply["memory_observation"] = {"status": "unobservable", "wait_seconds": 300}
        path = self.base / "pending.json"
        publish(path, reply)
        with self.assertRaises(MemoryEvaluationError) as error:
            import_receipt(self.root, item["id"], path)
        self.assertEqual(error.exception.code, "BACKGROUND_UNSETTLED")

    def test_native_preflight_reuses_read_only_probes_without_admitting_memory(self):
        def fake(command, **kwargs):
            if "--output-dir" in command:
                path = Path(command[command.index("--output-dir") + 1]) / "probe.json"
            else:
                path = Path(command[command.index("--output") + 1])
            publish(path, {"status": "PASS", "ready": True})
            self.assertNotIn("--capture-sensitive-artifacts", command)
            self.assertNotIn("--resume", command)
            return subprocess.CompletedProcess(command, 0, b"{}", b"")
        with patch("eval_memory_e2e.probe.subprocess.run", side_effect=fake):
            report = native_preflight(self.base / "native-probe")
        self.assertEqual(len(report["clients"]), 4)
        self.assertTrue(all(row["memory_admission"] == "UNVERIFIED" for row in report["clients"]))
        self.assertFalse(any(row["prompt_send_attempted"] for row in report["clients"]))

    def test_shell_command_string_never_accepted(self):
        from eval_memory_e2e.batch import default_profiles
        profiles = default_profiles()
        profiles["AstronStudio"]["driver_command"] = "python something.py; rm -rf /"
        with self.assertRaises(MemoryEvaluationError) as error:
            prepare(self.root, batch_id="bad-command", seed="seed", harnesses=["AstronStudio"], profiles=profiles)
        self.assertEqual(error.exception.code, "DRIVER_COMMAND")
        self.assertFalse(self.root.exists())

    def test_new_batches_have_fresh_facts_and_global_operation_ids(self):
        self.prepare()
        first = load_batch(self.root)
        second_root = self.base / "another-batch"
        prepare(second_root, batch_id="test-memory", seed="seed-v1", scenario_ids=["MEM-01"], harnesses=["AstronStudio"])
        second = load_batch(second_root)
        self.assertNotEqual(first["experiment_id"], second["experiment_id"])
        ep = first["episodes"][0]["id"]
        self.assertNotEqual(operation_id(first, ep, "s1"), operation_id(second, ep, "s1"))
        self.assertNotEqual(read_json(self.root / "private/scenarios.json")["MEM-01/r01"]["variant_id"],
                            read_json(second_root / "private/scenarios.json")["MEM-01/r01"]["variant_id"])

    def test_external_driver_source_drift_prevents_dispatch(self):
        from eval_memory_e2e.batch import default_profiles
        script = self.base / "external-driver.py"
        script.write_text("print('{}')\n")
        profiles = default_profiles()
        profiles["AstronStudio"]["driver_command"] = ["python3", str(script)]
        profiles["AstronStudio"]["driver_sources"] = {str(script): sha(script.read_bytes())}
        prepare(self.root, batch_id="driver-source", seed="seed", harnesses=["AstronStudio"],
                scenario_ids=["MEM-01"], profiles=profiles)
        episode_id = load_batch(self.root)["episodes"][0]["id"]
        script.write_text("print('changed')\n")
        with self.assertRaises(MemoryEvaluationError) as error:
            advance(self.root, episode_id)
        self.assertEqual(error.exception.code, "DRIVER_SOURCE_DRIFT")
        self.assertEqual(events(self.root), [])

    def test_logged_in_account_cannot_change_between_steps(self):
        self.prepare()
        item = self.episodes()[0]
        advance(self.root, item["id"])
        request = register_intent(self.root, item["id"])
        reply = respond({**request, "transport_action": "dispatch"})
        reply["actual_config"]["account_fingerprint"] = "another-account"
        path = self.base / "account-drift.json"
        publish(path, reply)
        with self.assertRaises(MemoryEvaluationError) as error:
            import_receipt(self.root, item["id"], path)
        self.assertEqual(error.exception.code, "CONFIG_DRIFT")

    def test_failed_review_is_retained_as_evaluation_error(self):
        self.prepare()
        item = self.episodes()[0]
        self.complete(item)
        review = self.review(item)
        review["checkpoints"][0]["evidence"][0]["quote"] = "not in frozen evidence"
        path = self.save_review(item, review)
        original = path.read_bytes()
        with self.assertRaises(MemoryEvaluationError):
            import_review(self.root, path)
        report = aggregate(self.root, include_fixture=True)
        self.assertEqual(report["episodes"][0]["status"], "evaluation_error")
        self.assertIsNone(report["episodes"][0]["score"])
        saved = report["scoring_errors"][0]["review_artifact"]
        self.assertEqual((self.root / saved["path"]).read_bytes(), original)
        path.write_text(json.dumps(self.review(item), ensure_ascii=False))
        imported = import_review(self.root, path)
        self.assertEqual(imported["result"], "valid")
        final = aggregate(self.root, include_fixture=True)
        self.assertEqual(final["episodes"][0]["status"], "valid")
        self.assertEqual(len(final["scoring_errors"]), 1)

    def test_replaced_workspace_symlink_cannot_be_snapshotted(self):
        self.prepare()
        item = self.episodes()[0]
        advance(self.root, item["id"])
        request = register_intent(self.root, item["id"])
        workspace = Path(request["workspace"])
        workspace.rmdir()
        outside = self.base / "outside"
        outside.mkdir()
        workspace.symlink_to(outside, target_is_directory=True)
        reply = respond({**request, "transport_action": "dispatch"})
        path = self.base / "replaced-workspace.json"
        publish(path, reply)
        with self.assertRaises(MemoryEvaluationError) as error:
            import_receipt(self.root, item["id"], path)
        self.assertEqual(error.exception.code, "SYMLINK_REJECTED")


if __name__ == "__main__":
    unittest.main()
