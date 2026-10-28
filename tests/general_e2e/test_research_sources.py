from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit
import zipfile

from tests.general_e2e.test_local_scoring_runtime import Fixture, RUNTIME, REPO_ROOT, load_module


SOURCES = RUNTIME.research_sources
POLICY = {
    "schema_version": SOURCES.POLICY_SCHEMA,
    "ledger_path": "results/source_ledger.json",
    "deliverable_paths": ["results/source_ledger.json", "results/answer.md"],
    "as_of_inclusive": "2026-09-30", "timezone": "Asia/Shanghai",
}
RULE = '''
def grade(transcript, workspace_path):
    import hashlib
    import json
    import os
    from pathlib import Path
    root = Path(os.environ["GENERAL_E2E_RESEARCH_SOURCE_BUNDLE"])
    raw = (root / "manifest.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != os.environ["GENERAL_E2E_RESEARCH_SOURCE_BUNDLE_SHA256"]:
        raise ValueError("source manifest drift")
    bundle = json.loads(raw)
    rows = bundle["sources"]
    passed = bool(rows) and rows[0]["status"] == "acquired"
    if passed:
        passed = "independent publication" in (root / rows[0]["text_path"]).read_text(encoding="utf-8")
    value = float(passed)
    return {"fixture": value, "overall_score": value}
'''.strip()
RUBRIC = '''### Criterion 1: 来源支持 (key: support, weight: 1.0)
**Score 1.0**: 原文支持。
**Score 0.0**: 交付缺失。
'''


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == "/redirect-private":
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{self.server.server_port}/publication?edition=kept")
            self.end_headers()
        elif self.path == "/redirect?edition=kept":
            self.send_response(302)
            self.send_header("Location", "/publication?edition=kept")
            self.end_headers()
        elif self.path == "/publication?edition=kept":
            content = b"<html><body><p>independent publication</p><script>ignored_secret</script></body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        else:
            self.send_response(404)
            self.end_headers()


class ResearchSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runtime_temp = tempfile.TemporaryDirectory(prefix="research-source-runtime-")
        cls.venv = Path(cls.runtime_temp.name) / "venv"
        uv = shutil.which("uv")
        command = ([uv, "venv", "--python", sys.executable, str(cls.venv)] if uv else
                   [sys.executable, "-m", "venv", "--without-pip", str(cls.venv)])
        subprocess.run(command, check=True, capture_output=True)
        cls.runtime_python = cls.venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.runtime_temp.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="research-source-tests-")
        self.root = Path(self.temp.name)

    def tearDown(self):
        for path in self.root.rglob("*"):
            if not path.is_symlink():
                path.chmod(0o755 if path.is_dir() else 0o644)
        self.temp.cleanup()

    def fixture(self, name="fixture", *, ledger="default", hybrid=False, specification=None):
        specification = POLICY if specification is None else specification
        fixture = Fixture(self.root / name, rule=RULE,
                          scoring_runtime={"research_sources": True},
                          extra_gt_files={SOURCES.POLICY_PATH: SOURCES.encoded(specification)},
                          grading_type="hybrid" if hybrid else "automated",
                          grading_weights={"automated": 0.4, "llm_judge": 0.6} if hybrid else {},
                          llm_judge_rubric=RUBRIC if hybrid else "")
        results = fixture.candidate / "results"
        results.mkdir()
        (results / "answer.md").write_text("candidate fabricated snapshot\n", encoding="utf-8")
        if ledger == "default":
            ledger = {"sources": [
                {"source_id": "arbitrary-legal-id", "url": self.base + "/redirect?edition=kept",
                 "access_status": "read_full", "reported_publication_date": "2099-01-01",
                 "citations": [{"citation_id": "citation-any", "locator": "paragraph 1", "quote": "independent publication"}]},
                {"source_id": "search-only", "url": self.base + "/not-read", "access_status": "search_only", "citations": []}
            ]}
        if ledger is not None:
            data = ledger if isinstance(ledger, str) else json.dumps(ledger)
            (results / "source_ledger.json").write_text(data, encoding="utf-8")
        entries, digest = RUNTIME._inventory_tree(fixture.candidate)
        artifact_path = fixture.candidate.parent / "candidate-artifact.json"
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        artifact.update({"entries": entries, "expected_sha256": digest})
        artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
        execution = json.loads(fixture.execution_record.read_text(encoding="utf-8"))
        execution["candidate"]["frozen_sha256"] = digest
        fixture.execution_record.write_text(json.dumps(execution), encoding="utf-8")
        return fixture

    def collect(self, attempt):
        # Explicit test-only resolver seam; production has no allow-private flag.
        def local_target(url):
            parsed = urlsplit(url)
            self.assertEqual(parsed.hostname, "127.0.0.1")
            return parsed.hostname, parsed.port, "127.0.0.1", ["127.0.0.1"]
        with patch.object(SOURCES, "_public_target", side_effect=local_target):
            return RUNTIME.collect_research_sources_attempt(attempt_root=attempt)

    def run_rules(self, attempt):
        return RUNTIME.run_rules_attempt(attempt_root=attempt, runtime_python=self.runtime_python, timeout_seconds=15)

    def finish_automated(self, attempt):
        self.run_rules(attempt)
        RUNTIME.prepare_semantics_attempt(attempt_root=attempt)
        return RUNTIME.finalize_score_attempt(attempt_root=attempt)["score"]

    def test_redirect_query_and_independent_content_are_frozen_without_mutating_inputs(self):
        attempt = self.fixture().prepare()
        before = {p: SOURCES.sha(attempt / p) for p in ("attempt-manifest.json", "private/contract.json")}
        candidate_before = RUNTIME._inventory_tree(attempt / "candidate-original/workspace")[1]
        gt_before = RUNTIME._inventory_tree(attempt / "private/gt")[1]
        result = self.collect(attempt)
        self.assertEqual(result["acquired_count"], 1)
        manifest = SOURCES.read(attempt / SOURCES.BUNDLE_PATH / "manifest.json")
        source = manifest["sources"][0]
        self.assertEqual(source["url"], self.base + "/redirect?edition=kept")
        self.assertEqual(source["final_url"], self.base + "/publication?edition=kept")
        response = SOURCES.read(attempt / SOURCES.BUNDLE_PATH / source["receipt_path"])
        self.assertEqual([r["status"] for r in response["responses"]], [302, 200])
        self.assertEqual(response["redirect_count"], 1)
        self.assertTrue(response["finished_at"].endswith("Z"))
        text = (attempt / SOURCES.BUNDLE_PATH / source["text_path"]).read_text(encoding="utf-8")
        self.assertIn("independent publication", text)
        self.assertNotIn("fabricated", text)
        self.assertNotIn("ignored_secret", text)
        self.assertFalse(manifest["historical_publication_verified"])
        self.assertEqual(candidate_before, RUNTIME._inventory_tree(attempt / "candidate-original/workspace")[1])
        self.assertEqual(gt_before, RUNTIME._inventory_tree(attempt / "private/gt")[1])
        self.assertEqual(before, {p: SOURCES.sha(attempt / p) for p in before})
        score = self.finish_automated(attempt)
        self.assertEqual(score["result"]["total_score"], 1.0)
        self.assertTrue(RUNTIME.verify_score_attempt(attempt)["score_valid"])

    def test_missing_bundle_blocks_both_rule_and_semantic_consumers(self):
        attempt = self.fixture(hybrid=True).prepare()
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError, "RESEARCH_SOURCE_BUNDLE_REQUIRED"):
            self.run_rules(attempt)
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError, "RESEARCH_SOURCE_BUNDLE_REQUIRED"):
            RUNTIME.prepare_semantics_attempt(attempt_root=attempt)
        self.assertFalse((attempt / "worker").exists())

    def test_missing_or_bad_ledger_is_candidate_evidence_and_can_receive_a_real_zero(self):
        for name, ledger, status in (("missing", None, "missing_ledger"), ("bad", "{broken", "invalid_ledger"),
                                     ("empty", {"sources": []}, "valid")):
            with self.subTest(name=name):
                attempt = self.fixture(name, ledger=ledger).prepare()
                with patch.object(SOURCES, "fetch", side_effect=AssertionError("must not fetch expected answers")):
                    self.assertEqual(self.collect(attempt)["candidate_input_status"], status)
                score = self.finish_automated(attempt)
                self.assertTrue(score["result"]["valid"])
                self.assertEqual(score["result"]["total_score"], 0.0)

    def test_current_404_is_collection_error_and_never_candidate_zero(self):
        ledger = {"sources": [{"source_id": "gone", "url": self.base + "/404", "access_status": "read_full"}]}
        attempt = self.fixture(ledger=ledger).prepare()
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError, "RESEARCH_SOURCE_ACQUISITION_FAILED"):
            self.collect(attempt)
        self.assertFalse((attempt / SOURCES.LOCK_PATH).exists())
        self.assertFalse((attempt / SOURCES.BUNDLE_PATH).exists())
        self.assertTrue(list(attempt.glob("research-source-failure-*.json")))
        self.assertFalse((attempt / "rule-component.json").exists())

    def test_public_collector_rejects_initial_private_and_mixed_dns_before_network(self):
        for url in (self.base, "http://localhost./doc", "http://user:password@example.com/a", "http://example.com/\nprivate", "http://example.com:0/doc"):
            with self.subTest(url=url), patch.object(SOURCES.subprocess, "run", side_effect=AssertionError("must reject before curl")):
                with self.assertRaisesRegex(SOURCES.ResearchSourceError, "RESEARCH_SOURCE_URL_NOT_PUBLIC"):
                    SOURCES.fetch(url, self.root / "never.bin", {**SOURCES.POLICY_DEFAULTS, **POLICY})
        addresses = [(2, 1, 6, "", (address, 80)) for address in ("8.8.8.8", "10.0.0.1")]
        with patch.object(SOURCES.socket, "getaddrinfo", return_value=addresses):
            with self.assertRaisesRegex(SOURCES.ResearchSourceError, "RESEARCH_SOURCE_URL_NOT_PUBLIC"):
                SOURCES._public_target("http://public.example/doc")

    def test_public_redirect_to_private_is_rejected_before_second_request(self):
        original_target = SOURCES._public_target
        start = f"http://public-fixture.example:{self.server.server_port}/redirect-private"
        calls = []
        def controlled_target(url):
            calls.append(url)
            if url == start:
                return "public-fixture.example", self.server.server_port, "127.0.0.1", ["127.0.0.1"]
            return original_target(url)
        with patch.object(SOURCES, "_public_target", side_effect=controlled_target):
            with self.assertRaisesRegex(SOURCES.ResearchSourceError, "RESEARCH_SOURCE_URL_NOT_PUBLIC"):
                SOURCES.fetch(start, self.root / "redirect.bin", {**SOURCES.POLICY_DEFAULTS, **POLICY})
        self.assertEqual(len(calls), 2)

    def test_source_budget_is_infrastructure_failure_without_truncation(self):
        ledger = {"sources": [{"source_id": str(i), "url": self.base + "/publication?edition=kept", "access_status": "read_full"}
                              for i in range(2)]}
        attempt = self.fixture(ledger=ledger, specification={**POLICY, "max_sources": 1}).prepare()
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError, "RESEARCH_SOURCE_BUDGET_INSUFFICIENT"):
            self.collect(attempt)
        self.assertFalse((attempt / SOURCES.LOCK_PATH).exists())

    def test_malformed_url_is_observed_candidate_input_without_network_failure(self):
        attempt = self.fixture(ledger={"sources": [{"source_id": "bad-url", "url": "file:///tmp/candidate.pdf", "access_status": "read_full"}]}).prepare()
        self.collect(attempt)
        document = SOURCES.read(attempt / SOURCES.BUNDLE_PATH / "manifest.json")
        self.assertEqual(document["sources"][0]["status"], "candidate_invalid")
        self.assertEqual(self.finish_automated(attempt)["result"]["total_score"], 0.0)

    def test_content_extra_member_and_lock_drift_fail_closed(self):
        for name in ("body", "extra", "lock"):
            with self.subTest(name=name):
                attempt = self.fixture(name).prepare()
                self.collect(attempt)
                if name == "body":
                    path = next((attempt / SOURCES.BUNDLE_PATH).rglob("body.html"))
                    path.chmod(0o644)
                    path.write_text("tampered", encoding="utf-8")
                elif name == "extra":
                    bundle = attempt / SOURCES.BUNDLE_PATH
                    bundle.chmod(0o755)
                    (bundle / "new.txt").write_text("extra", encoding="utf-8")
                else:
                    path = attempt / SOURCES.LOCK_PATH
                    lock = SOURCES.read(path)
                    lock["identity"]["scoring_attempt_id"] = "another"
                    path.chmod(0o644)
                    path.write_bytes(SOURCES.encoded(lock))
                with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError, "RESEARCH_SOURCE_(BUNDLE_DRIFT|LOCK_INVALID)"):
                    RUNTIME.verify_attempt(attempt)

    def test_semantic_catalog_contains_actual_sources_and_query_returns_text(self):
        attempt = self.fixture(hybrid=True).prepare()
        self.collect(attempt)
        self.run_rules(attempt)
        RUNTIME.prepare_semantics_attempt(attempt_root=attempt)
        page = RUNTIME.query_evidence_attempt(attempt_root=attempt, mode="catalog", evidence_type="independent_research_source", limit=100)
        text = next(row for row in page["items"] if row["reference"]["path"].endswith("/text.txt"))
        result = RUNTIME.query_evidence_attempt(attempt_root=attempt, mode="file", evidence_id=text["id"], limit=100)
        self.assertIn("independent publication", json.dumps(result))
        audit = SOURCES.read(attempt / "rule-audit.json")
        self.assertEqual(audit["research_sources"]["manifest_sha256"], SOURCES.sha(attempt / SOURCES.BUNDLE_PATH / "manifest.json"))

    def test_api_packet_requires_actual_complete_source_content_without_calling_judge(self):
        attempt = self.fixture(hybrid=True).prepare()
        self.collect(attempt)
        self.run_rules(attempt)
        RUNTIME.prepare_semantics_attempt(attempt_root=attempt)
        manifest = SOURCES.read(attempt / "attempt-manifest.json")
        request = SOURCES.read(attempt / "semantic/request.json")
        catalog = SOURCES.read(attempt / "semantic/evidence-catalog.json")
        runtime = {"provider": "openai-responses", "endpoint": "https://judge.invalid/v1/responses",
                   "endpoint_sha256": "a" * 64, "credential_env": "NO_CREDENTIAL",
                   "max_output_tokens": 1024, "timeout_seconds": 10, "max_attempts": 1,
                   "temperature": 0, "reasoning_parameter": "reasoning_effort",
                   "max_input_chars": 1_000_000, "max_evidence_item_chars": 32}
        args = dict(manifest=manifest, request_document=request, catalog=catalog, transcript=[],
                    judge={"api_runtime": runtime}, request_sha256=SOURCES.sha(attempt / "semantic/request.json"),
                    catalog_sha256=SOURCES.sha(attempt / "semantic/evidence-catalog.json"))
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError, "RESEARCH_SOURCE_API_INPUT_INCOMPLETE"):
            RUNTIME._build_api_input(attempt, **args)
        runtime["max_evidence_item_chars"] = 100_000
        packet = RUNTIME._build_api_input(attempt, **args)
        delivered = json.loads(packet["user_prompt"])
        source_texts = [row for row in delivered["evidence"] if (row.get("path") or "").endswith("/text.txt")]
        self.assertEqual(len(source_texts), 1)
        self.assertEqual(source_texts[0]["content_status"], "complete")
        self.assertIn("independent publication", source_texts[0]["content"])

    def test_rescore_preserves_bytes_and_rebinds_identity_without_network(self):
        attempt = self.fixture().prepare()
        self.collect(attempt)
        self.finish_automated(attempt)
        original = SOURCES.inventory(attempt / SOURCES.BUNDLE_PATH)
        with patch.object(SOURCES, "fetch", side_effect=AssertionError("no new retrieval")):
            result = RUNTIME.prepare_rescore_attempt(source_attempt_root=attempt,
                                                     scoring_attempt_id="new-score", output_root=self.root / "rescore")
        target = Path(result["attempt_root"])
        self.assertEqual(original, SOURCES.inventory(target / SOURCES.BUNDLE_PATH))
        self.assertEqual(SOURCES.read(target / SOURCES.LOCK_PATH)["identity"]["scoring_attempt_id"], "new-score")
        self.assertIsNotNone(SOURCES.read(target / SOURCES.LOCK_PATH)["parent_lock"])
        self.assertEqual(self.finish_automated(target)["result"]["total_score"], 1.0)

    def test_independent_skill_zip_and_moved_archive_verify_without_collector_tools(self):
        attempt = self.fixture().prepare()
        self.collect(attempt)
        self.finish_automated(attempt)
        builder = load_module("research_source_skill_builder", REPO_ROOT / "tools/e2e-build/build_skill_packages.py")
        distribution = self.root / "distribution"
        result = builder.build_skill_package(REPO_ROOT, distribution, "score-general-e2e", source_revision="research-test")
        with zipfile.ZipFile(distribution / result["archive"]) as archive:
            archive.extractall(distribution / "installed")
        script = distribution / "installed/score-general-e2e/scripts/score_general_e2e.py"
        self.assertTrue(script.with_name("research_sources.py").is_file())
        returned = self.root / "returned.zip"
        with zipfile.ZipFile(returned, "w") as archive:
            for path in attempt.rglob("*"):
                relative = path.relative_to(attempt)
                if path.is_file() and relative.parts[0] != "runtime":
                    archive.write(path, relative.as_posix())
        moved = self.root / "different-directory/archive"
        with zipfile.ZipFile(returned) as archive:
            archive.extractall(moved)
        RUNTIME._make_read_only(moved / "candidate-original")
        with patch.object(SOURCES, "project", side_effect=AssertionError("archived parser must not be required")):
            self.assertTrue(RUNTIME.verify_score_attempt(moved, archived=True)["score_valid"])
        env = {key: value for key, value in os.environ.items() if key not in {"PYTHONPATH", "PYTHONHOME"}}
        checked = subprocess.run([sys.executable, "-X", "utf8", str(script), "verify-score", "--attempt-root", str(moved), "--archived"],
                                 cwd=self.root, env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
        self.assertTrue(json.loads(checked.stdout)["score_valid"])
        victim = next((moved / SOURCES.BUNDLE_PATH).rglob("body.html"))
        victim.unlink()
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError, "RESEARCH_SOURCE_BUNDLE_DRIFT"):
            RUNTIME.verify_score_attempt(moved, archived=True)


if __name__ == "__main__":
    unittest.main()
