import base64
import json
import ntpath
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

from src.e2e import desktop_scoring as scoring
from src.e2e.agentcube import AgentCubeConfig
from src.e2e.common import E2EError, atomic_json, file_sha256
from src.e2e.desktop_web_bundle_guest import unpack


CONFIG = {
    "harness": "astronstudio", "template": "score-template", "model": scoring.MODEL,
    "concurrency": 1, "timeout_seconds": 120,
    "template_binding": {"id": 5, "namespace": "trial-windows", "image_digest": "sha256:" + "a" * 64,
                         "waa_revision": "7db162a", "profile_id": "astudio-default"},
}
ITEM = {"key": "execution-key", "task_id": "case", "unit_id": "unit", "run_index": 1,
        "phase": "COMPLETED", "scene": "web", "attempt_id": "candidate-attempt"}


class DesktopScoringTests(unittest.TestCase):
    def test_model_and_template_are_pinned(self):
        self.assertEqual(scoring._config(CONFIG), CONFIG)
        with self.assertRaisesRegex(E2EError, "DESKTOP_SCORER_MODEL_MUST_MATCH"):
            scoring._config({**CONFIG, "model": "DeepSeek-V4-Flash"})

    def test_native_model_is_bound_to_the_exact_catalog_entry(self):
        other = {"name": "DeepSeek-V4-Flash", "slug": "xopdsv4flash0731in"}
        expected = {"name": "DeepSeek-V4.1-Flash", "slug": "xdeepseek-flash-in"}
        self.assertEqual(scoring._catalog_model({"models": [other, expected]})["slug"], expected["slug"])
        for models in ([other], [expected, expected], [expected, {**other, "slug": expected["slug"]}]):
            with self.assertRaisesRegex(E2EError, "DESKTOP_SCORING_MODEL_CATALOG_MISMATCH"):
                scoring._catalog_model({"models": models})

    def test_retry_after_release_failure_does_not_dispatch_twice(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            driver = Mock()
            driver.client.delete_session.side_effect = [{"confirmed": False}, {"confirmed": True}]

            def setup(**_kwargs):
                state = _kwargs["store"]

                def execute():
                    self.assertEqual(
                        {key: state.get(ITEM["key"])[key] for key in ("attempt_id", "task_id", "unit_id", "run_index")},
                        {"attempt_id": "desk-scope", "task_id": "case", "unit_id": "unit", "run_index": 1},
                    )
                    state.update(None, "RUNNING", session_id="session", resource_held=True)
                    return {}

                driver.execute.side_effect = execute
                return driver

            def score(_work, _response, _driver, row, _attempt):
                row.update(status="valid", total_score=81)

            with patch.object(scoring, "_prepare", return_value={}), \
                    patch.object(scoring, "ScoringDriver", side_effect=setup), \
                    patch.object(scoring, "_record_agent_response", side_effect=score):
                args = (root, ITEM, CONFIG, AgentCubeConfig(), root / "job", "desk-scope", root / "cancel.json")
                first = scoring._job(*args)
                second = scoring._job(*args)
                third = scoring._job(*args)
            self.assertFalse(first["container_released"])
            self.assertTrue(second["container_released"])
            self.assertEqual(second, third)
            self.assertEqual(second["total_score"], 81)
            driver.execute.assert_called_once()
            self.assertEqual(driver.client.delete_session.call_count, 2)

    def test_native_visual_evidence_binds_capture_receiver_and_image_tool(self):
        with tempfile.TemporaryDirectory() as tmp:
            private = Path(tmp)
            evidence = private / "evidence"
            evidence.mkdir()
            filename = "native-12345678-1234-1234-1234-123456789abc-home.png"
            screenshot = evidence / filename
            screenshot.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR" + struct.pack(">II", 1280, 800) + b"a" * 9)
            relative = "evidence/" + filename
            sha256 = file_sha256(screenshot)
            guest = ntpath.join(scoring.GUEST_WORKSPACE, "private-scoring")
            atomic_json(evidence / (filename + ".receipt.json"), {
                "path": "private-scoring/" + relative, "format": "png", "content_type": "image/png",
                "sha256": sha256, "bytes": screenshot.stat().st_size,
            })
            def event(server, name, call, output, arguments=None):
                return {"native_status": {"type": "mcp_tool_call_end", "call_id": call,
                                           "invocation": {"server": server, "tool": name, "arguments": arguments},
                                           "result": {"Ok": output}}}

            omitted = event("acode", "astron_browser_screenshot", "direct", {"content": [{
                "type": "text", "text": "<image content omitted because you do not support image input>",
            }]})
            capture = {"structuredContent": {
                "schema": "astudio.browser-screenshot/v1", "filename": filename,
                "path": ntpath.join(guest, "browser-captures", filename), "sha256": sha256,
                "bytes": screenshot.stat().st_size, "url": "http://127.0.0.1:4173/page",
                "tabId": 1, "viewport": {"width": 1280, "height": 800},
            }}
            read = event("acode_apps", "image_understanding", "read", {"structuredContent": {"text": "页面标题可见"}},
                         {"image": ntpath.join(guest, "evidence", filename), "question": "标题是否清晰？"})
            binding = {"events": [event("acode", "astron_browser_open", "open", {}), omitted, read]}
            score = {"site_url": "http://127.0.0.1:4173/", "criteria": [
                {"evidence": [{"type": "screenshot", "path": relative}]},
            ]}
            with self.assertRaisesRegex(E2EError, "NATIVE_CAPTURE_MISSING"):
                scoring.verify_native_browser(binding, private, score)
            binding["events"].append(event("acode", "astron_browser_save_screenshot", "capture", capture))
            with self.assertRaisesRegex(E2EError, "IMAGE_UNDERSTANDING_MISSING"):
                scoring.verify_native_browser(binding, private, score)
            binding["events"].append(read)
            audit = scoring.verify_native_browser(binding, private, score)
            self.assertEqual(audit["screenshots"][0]["capture_call_id"], "capture")
            self.assertEqual(audit["screenshots"][0]["image_understanding"][0]["call_id"], "read")
            with self.assertRaisesRegex(E2EError, "ORIGIN_INVALID"):
                scoring.verify_native_browser(binding, private, {**score, "site_url": "http://127.0.0.1:4174/"})
            with self.assertRaisesRegex(E2EError, "VIEWPORT_MISMATCH"):
                scoring.verify_native_browser(binding, private, {**score, "aesthetic": {
                    "screenshots": [{"path": relative, "viewport": {"width": 375, "height": 800}}],
                }})
            screenshot.write_bytes(b"modified evidence")
            with self.assertRaisesRegex(E2EError, "SCREENSHOT_DRIFT"):
                scoring.verify_native_browser(binding, private, score)

    def test_native_screenshot_uses_the_existing_skill_receiver(self):
        from tests.test_score_web_e2e import BuildSubmissionTest

        repo = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            package = Path(tmp)
            workspace = package / "score/tasks/task-1"
            (workspace / "private-scoring/browser-captures").mkdir(parents=True)
            BuildSubmissionTest.materialize_candidate_integrity(package)
            (workspace / ".web-e2e-scoring-ready").write_text("batch-1\ntask-1\n", encoding="utf-8")
            filename = "native-12345678-1234-1234-1234-123456789abc-home.png"
            capture = workspace / "private-scoring/browser-captures" / filename
            capture.write_bytes(base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAACklEQVR42mNgAAAAAgABSK+kcQAAAABJRU5ErkJggg=="
            ))
            tooling = workspace / "desktop-scoring-tooling"
            tooling.mkdir()
            helper = tooling / "desktop_web_screenshot.mjs"
            shutil.copyfile(repo / "src/e2e" / helper.name, helper)
            (tooling / "score-web-e2e").symlink_to(repo / ".agents/skills/score-web-e2e", target_is_directory=True)
            command = ["node", helper, filename, file_sha256(capture)]
            first = subprocess.run(command, cwd=workspace, capture_output=True, check=True, timeout=30)
            receipt = json.loads(first.stdout)
            output = Path(receipt["path"])
            self.assertEqual(output.read_bytes(), capture.read_bytes())
            sidecar = output.with_name(filename + ".receipt.json")
            sidecar.unlink()
            retry = subprocess.run(command, cwd=workspace, capture_output=True, check=True, timeout=30)
            self.assertEqual(json.loads(retry.stdout), receipt)
            self.assertTrue(sidecar.is_file())

    def test_web_verification_bundle_can_resume_with_bounded_parts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            upload = root / "payload.zip"
            with zipfile.ZipFile(upload, "w") as archive:
                archive.writestr("unit/manifest.json", b"fixture" * 200)
                archive.writestr("verifier/scripts/build_submission.mjs", b"// fixture")
            data = upload.read_bytes()
            guest = root / "guest"
            for index, offset in enumerate(range(0, len(data), 128)):
                group = guest / f"parts-{index // 4:05d}"
                group.mkdir(parents=True, exist_ok=True)
                (group / f"part-{index:05d}").write_bytes(data[offset:offset + 128])
            unpack(guest, file_sha256(upload))
            self.assertEqual((guest / "contents/unit/manifest.json").read_bytes(), b"fixture" * 200)
            unpack(guest, file_sha256(upload))
            (guest / "parts-00000/part-00000").write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "WEB_BUNDLE_DRIFT"):
                unpack(guest, file_sha256(upload))

    def test_general_rejects_a_score_for_a_different_frozen_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            returned = work / "returned/attempts/foreign"
            returned.mkdir(parents=True)
            context = work / "context"
            context.mkdir()
            (context / "record.json").write_text("original", encoding="utf-8")
            (context / "rules.zip").write_bytes(b"fixture")
            atomic_json(returned / "score.json", {"identity": {"attempt_id": "desk-scope"}, "judge": {"model": scoring.MODEL},
                                                  "result": {"valid": True, "total_score": 0.7}})
            atomic_json(returned / "attempt-manifest.json", {
                "source": {"execution_record_sha256": file_sha256(context / "record.json"),
                           "scoring_package_sha256": file_sha256(context / "rules.zip")},
                "digests": {"execution_record_sha256": file_sha256(context / "record.json")},
            })
            handoff = {"execution_record": "record.json", "scoring_package": "rules.zip", "installed_skills": tmp}
            with patch.object(scoring, "_run", return_value=b'{"status":"PASS"}') as verify:
                _, number, _, _ = scoring._read_general(work, work / "returned", handoff, "desk-scope", scoring.MODEL)
                self.assertEqual(number, 0.7)
                verify.assert_called_once()
            (context / "record.json").write_text("another execution", encoding="utf-8")
            with patch.object(scoring, "_run") as verify, self.assertRaisesRegex(E2EError, "GENERAL_SOURCE_DRIFT"):
                scoring._read_general(work, work / "returned", handoff, "desk-scope", scoring.MODEL)
            verify.assert_not_called()

    def test_web_round_recomputes_score_and_exports_a_standard_return(self):
        from tests.test_score_web_e2e import artifactsbench_fixtures, fixtures

        for profile, factory, expected in [
            ("web-e2e-detailed-v1", fixtures, 70),
            ("artifactsbench-web-v1", artifactsbench_fixtures, 82),
        ]:
            with self.subTest(profile=profile):
                self._check_web_return(profile, factory, expected)

    def _check_web_return(self, profile, factory, expected):
        import shutil
        from tests.test_score_web_e2e import BuildSubmissionTest

        repo = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            package = work / "context/unit"
            source = package / "score/tasks/task-1"
            private = source / "private-scoring"
            private.mkdir(parents=True)
            _, contract, execution, score_input = factory()
            atomic_json(private / "task_contract.json", contract)
            atomic_json(source / "execution_record.json", execution)
            atomic_json(package / "manifest.json", {
                "batch_id": "batch-1", "source_revision": "abc", "metric_profile": profile,
                "harness": {"id": "codex", "display_name": "Codex"},
                "tasks": [{"task_id": "task-1", "task_sha256": "task-hash", "workspace_exec_sha256": "workspace-hash"}],
            })
            BuildSubmissionTest.materialize_candidate_integrity(package)
            (source / ".web-e2e-scoring-ready").write_text("batch-1\ntask-1\n", encoding="utf-8")
            returned = work / "returned"
            shutil.copytree(source, returned)
            BuildSubmissionTest.materialize_evidence(returned)
            atomic_json(returned / "private-scoring/score_input.json", score_input)
            handoff = {"score_task_root": "unit/score/tasks/task-1", "unit_root": "unit",
                       "installed_skills": str(repo / "tools/report/skills/web-e2e")}

            def seal(_driver, root, skill):
                scoring._run(["node", skill / "scripts/build_submission.mjs",
                              "--package-root", root, "--output", root / "submission.json"], root)

            with patch.object(scoring, "verify_native_browser", return_value={"screenshots": []}) as verify, \
                    patch.object(scoring, "_build_web_on_guest", side_effect=seal):
                score, number, receipt, artifacts = scoring._read_web(
                    work, returned, handoff, {"actual_model": scoring.MODEL}, Mock())
            verify.assert_called_once()
            self.assertTrue(score.is_file())
            self.assertEqual(number, expected)
            self.assertEqual(receipt["status"], "PASS")
            self.assertTrue(artifacts["submission"].is_file())
            self.assertTrue(artifacts["evidence"].is_file())
