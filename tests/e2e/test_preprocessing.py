import base64
import hashlib
import io
import json
import os
import struct
import tempfile
from pathlib import Path, PureWindowsPath
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import zipfile

from src.e2e.backend import ObservationPaused
from src.e2e.common import E2EError, atomic_json, digest, read_json, utc_now
from src.e2e.preparation import normalize_plan
from src.e2e.preprocessing import augment_prompt, effective, freeze_assets, frozen_prompt_directives, frozen_recipe, inspect_asset, selection
from src.e2e.windows_preprocess import _receipt, _upload, apply_recipe, bind_running_acode, build_payload


def recipe(asset):
    return {"version_id": 4, "name": "Test variant", "version": 2,
            "steps": [{"kind": "powershell", "asset": asset, "timeout": 10, "attachments": []}]}


class PreprocessingTests(unittest.TestCase):
    def test_live_kernel_binding_survives_process_exit_after_controller_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            checksum = "a" * 64
            state = {
                "phase": "RUNNING",
                "dispatch_armed_at": utc_now(),
                "preprocess_receipt": {"steps": [
                    {"kind": "acode", "status": "passed", "after_sha256": checksum, "version": "1.0.0"},
                ]},
            }
            driver = SimpleNamespace(key="case", store=Mock(), staging=Path(directory), client=Mock())
            driver.store.get.side_effect = lambda key: state.copy()
            driver._phase = lambda phase, **values: state.update(phase=phase, **values)
            driver.client.windows_execute.side_effect = [
                {"output": "pending"}, {"output": json.dumps({"pid": 123, "sha256": checksum})},
            ]
            self.assertIsNone(bind_running_acode(driver, "original-session", str, required=False))
            proof = bind_running_acode(driver, "original-session", str, required=False)
            self.assertEqual(proof["session_id"], "original-session")
            self.assertEqual(state["phase"], "RUNNING")
            state["phase"] = "COLLECTING"
            self.assertEqual(bind_running_acode(driver, "original-session", str), proof)
            self.assertEqual(driver.client.windows_execute.call_count, 2)
            self.assertEqual(read_json(driver.staging / "metadata/preprocessing.json")["observed_acode"], proof)

    def test_large_payload_routes_wgui_transfers_to_separate_bounded_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            driver = SimpleNamespace(batch=Path(directory), client=Mock(), _checked_job=Mock(), checkpoint=Mock())
            contents = bytes(range(256)) * 2
            stage_count = 0

            def make_payload(batch, step, target):
                nonlocal stage_count
                target.mkdir()
                file = target / "payload.bin"
                file.write_bytes(contents)
                stage_count += 1
                os.utime(file, (1_750_000_000 + stage_count * 60,) * 2)
                return {"kind": "acode"}

            with (patch("src.e2e.windows_preprocess.build_payload", side_effect=make_payload),
                  patch("src.e2e.windows_preprocess.CHUNK_BYTES", 64),
                  patch("src.e2e.windows_preprocess.CHUNKS_PER_UPLOAD", 2)):
                _upload(driver, "session", {}, {"index": 0, "invocation": "fixture"}, "/tmp/fixture",
                        PureWindowsPath(r"C:\fixture"), "wgui", str)
                first_upload = driver.client.upload.call_args_list[:]
                driver.client.upload.reset_mock()
                _upload(driver, "session", {}, {"index": 0, "invocation": "fixture"}, "/tmp/fixture",
                        PureWindowsPath(r"C:\fixture"), "wgui", str)
            self.assertEqual([request.args for request in driver.client.upload.call_args_list],
                             [request.args for request in first_upload])
            by_dir = {}
            for request in driver.client.upload.call_args_list:
                _, path, contents_part = request.args
                folder, filename = path.rsplit("/", 1)
                by_dir.setdefault(folder, {})[filename] = contents_part
            control = by_dir.pop("/tmp/fixture/control")
            self.assertEqual(set(control), {"worker.py", "step.json"})
            self.assertGreater(len(by_dir), 1)
            for folder, parts in by_dir.items():
                self.assertLessEqual(sum(map(len, parts.values())), 128)
                self.assertIn(folder, " ".join(request.args[1] for request in driver._checked_job.call_args_list))
            package = b"".join(part for _, parts in sorted(by_dir.items()) for _, part in sorted(parts.items()))
            self.assertEqual(hashlib.sha256(package).hexdigest(), json.loads(control["step.json"])["package_sha256"])
            with zipfile.ZipFile(io.BytesIO(package)) as archive:
                self.assertEqual(archive.read("payload.bin"), contents)

    def test_windows_receipt_waits_for_atomic_publish_in_the_same_session(self):
        driver = SimpleNamespace(client=Mock(), stop=Mock(), checkpoint=Mock())
        job = {"invocation": "original-invocation", "started_at": utc_now()}
        sent = {"invocation": job["invocation"], "status": "passed",
                "duration_seconds": 1.5, "exit_code": 0, "stdout": "discarded from receipt"}
        output = "receipt:" + base64.b64encode(json.dumps(sent).encode()).decode()
        driver.client.windows_execute.side_effect = [{"output": "pending"}, {"output": output}]
        observed = _receipt(driver, "owned-session", PureWindowsPath(r"C:\wcb"), job,
                            {"kind": "powershell", "timeout": 10}, str)
        self.assertEqual(observed, {"status": "passed", "duration_seconds": 1.5, "exit_code": 0})
        driver.stop.wait.assert_called_once_with(1)
        for request in driver.client.windows_execute.call_args_list:
            self.assertEqual(request.args[0], "owned-session")
            self.assertIn(r"C:\wcb\receipt.json", request.args[1])

    def test_windows_receipt_rejects_foreign_invocation_and_invalid_transport(self):
        driver = SimpleNamespace(client=Mock(), stop=Mock(), checkpoint=Mock())
        job = {"invocation": "original-invocation", "started_at": utc_now()}
        foreign = {"invocation": "another-invocation", "status": "passed",
                   "duration_seconds": 1.5, "exit_code": 0}
        for output in ("oversize", "receipt:%%%", "receipt:" + base64.b64encode(json.dumps(foreign).encode()).decode()):
            with self.subTest(output=output):
                driver.client.windows_execute.return_value = {"output": output}
                with self.assertRaisesRegex(E2EError, "PREPROCESS_STEP_RECEIPT_INVALID"):
                    _receipt(driver, "owned-session", PureWindowsPath(r"C:\wcb"), job,
                             {"kind": "powershell", "timeout": 10}, str)

    def test_zip_previews_reject_windows_path_collisions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("example/SKILL.md", "---\nname: example\n---\n")
            self.assertEqual(inspect_asset(path, "skill", "input.zip")["skills"], {"example": "example"})
            for member in ["../x", "C:/x", "a/COM1.txt", "a/example.txt:alternate", "example/skill.md", "trailing. /x"]:
                with self.subTest(member=member):
                    with zipfile.ZipFile(path, "w") as archive:
                        archive.writestr("example/SKILL.md", "---\nname: example\n---\n")
                        archive.writestr(member, "test")
                    with self.assertRaises(E2EError):
                        inspect_asset(path, "skill", "input.zip")

    def test_plugin_preview_and_acode_manifest_bind_the_actual_package(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("demo/.acode-plugin/plugin.json", '{"name":"demo","version":"1.2.3"}')
                archive.writestr(".agents/plugins/marketplace.json", '{"name":"local-market","plugins":[{"name":"demo"}]}')
            metadata = inspect_asset(path, "plugin", "input.zip")
            self.assertEqual((metadata["plugin"], metadata["version"], metadata["marketplaces"]),
                             ("demo", "1.2.3", ["local-market"]))
            # Header-only fixture for the parser. It contains no runnable code.
            exe = bytearray(70)
            exe[:2] = b"MZ"
            struct.pack_into("<I", exe, 60, 64)
            exe[64:] = b"PE\x00\x00\x64\x86"
            document = {"schemaVersion": 1, "runtime": "acode", "platform": "win32",
                        "arch": "x64", "file": "acode-windows-x64.exe",
                        "sha256": hashlib.sha256(exe).hexdigest(), "version": "1.2.3"}
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr(document["file"], exe)
                archive.writestr("acode-runtime-manifest.json", json.dumps(document))
            self.assertEqual(inspect_asset(path, "acode", "input.zip")["binary_sha256"], document["sha256"])
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr(document["file"], exe + b"drift")
                archive.writestr("acode-runtime-manifest.json", json.dumps(document))
            with self.assertRaisesRegex(E2EError, "ACODE_DIGEST_MISMATCH"):
                inspect_asset(path, "acode", "input.zip")

    def test_binding_precedence_versions_and_private_frozen_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            sha = hashlib.sha256(b"exit 0").hexdigest()
            (source / sha).write_bytes(b"exit 0")
            asset = inspect_asset(source / sha, "powershell", "script.ps1")
            default = recipe(asset)
            variant = {**default, "version_id": 5, "version": 3}
            raw = {"selection": {"scenario": "general", "dataset": "fixture"}, "runs": 2, "units": [
                {"harness": "astronstudio", "model": "test"},
                {"harness": "astronstudio", "model": "test", "preprocessing": {
                    "default": default, "overrides": {"skip": None, "replace": variant},
                }},
            ]}
            plan = normalize_plan(raw)
            baseline, unit = plan["units"]
            self.assertNotEqual(baseline["unit_id"], unit["unit_id"])
            self.assertIsNone(effective(baseline, "inherit"))
            self.assertEqual(effective(unit, "inherit"), default)
            self.assertEqual(effective(unit, "replace"), variant)
            self.assertIsNone(effective(unit, "skip"))
            cases = [{"task_id": task} for task in ("inherit", "replace", "skip")]
            preview = selection(plan["units"], cases)
            self.assertEqual([row["recipe"]["version"] if row["recipe"] else None
                              for row in preview["preprocessing"][0]["cases"]], [2, 3, None])
            with self.assertRaisesRegex(E2EError, "OUTSIDE_SELECTION"):
                selection(plan["units"], cases[:-1])
            freeze_assets(plan["units"], source, root / "preprocess-assets")
            (source / sha).write_bytes(b"tampered")
            self.assertEqual((root / "preprocess-assets" / sha).read_bytes(), b"exit 0")
            bindings = {unit["unit_id"]: unit["preprocessing"]}
            atomic_json(root / "batch.json", {"preprocessing_bindings_sha256": digest(bindings)})
            atomic_json(root / "preprocessing.json", bindings)
            self.assertEqual(frozen_recipe(root, unit["unit_id"], "replace"), variant)
            build_payload(root, default["steps"][0], root / "guest")
            self.assertEqual((root / "guest/step.ps1").read_text(encoding="utf-8-sig"), "exit 0")
            atomic_json(root / "preprocessing.json", {})
            with self.assertRaisesRegex(E2EError, "BINDINGS_DRIFT"):
                frozen_recipe(root, unit["unit_id"], "replace")

    def test_explicit_plugin_prompt_is_opt_in_and_case_scoped(self):
        plugin_asset = {"name": "sites.zip", "kind": "plugin", "sha256": "a" * 64, "size": 10}
        plugin_recipe = {"version_id": 8, "version": 2, "name": "Sites 1.17", "steps": [
            {"kind": "plugin", "target": "sites-skills", "marketplace": "astron-plugin-hub",
             "asset": plugin_asset, "timeout": 20}
        ]}
        plan = normalize_plan({"selection": {"scenario": "web", "dataset": "fixture"}, "runs": 1,
            "units": [{"unit_id": "astudio-web", "harness": "astronstudio", "model": "spark-x2.6",
                "preprocessing": {"default": plugin_recipe, "overrides": {},
                    "prompt_directives": {"default": [], "overrides": {"web-023": ["sites-skills"]}}}}]})
        cases = [{"task_id": task} for task in ("web-023", "web-024")]
        preview = selection(plan["units"], cases)
        directives = preview["preprocessing"][0]["cases"]
        self.assertEqual(directives[0]["prompt_directives"]["plugin_mentions"], ["sites-skills"])
        self.assertEqual(directives[1]["prompt_directives"]["plugin_mentions"], [])
        base = "帮我完成这个 Web 任务。\n"
        unchanged, metadata = augment_prompt(base, directives[1]["prompt_directives"], plugin_recipe)
        self.assertEqual(unchanged, base)
        self.assertFalse(metadata["changed"])
        effective_prompt, metadata = augment_prompt(base, directives[0]["prompt_directives"], plugin_recipe)
        self.assertIn("@sites-skills", effective_prompt)
        self.assertTrue(metadata["changed"])
        self.assertNotEqual(metadata["base_prompt_sha256"], metadata["effective_prompt_sha256"])

    def test_prompt_plugin_requires_a_matching_plugin_recipe(self):
        with self.assertRaisesRegex(E2EError, "PROMPT_PLUGIN_NOT_AVAILABLE"):
            augment_prompt("任务", {"plugin_mentions": ["sites-skills"]}, None)

    def test_resume_observes_existing_step_and_failure_records_no_script_output(self):
        with tempfile.TemporaryDirectory() as directory:
            item = {"attempt_id": "exec-one"}
            driver = SimpleNamespace(key="case", store=Mock(), staging=Path(directory), stop=Event())
            driver.store.get.side_effect = lambda key: item.copy()
            driver._phase = lambda phase, **fields: item.update(fields)
            asset = {"name": "script.ps1", "kind": "powershell", "sha256": "a" * 64, "size": 10}
            source = recipe(asset)
            with (patch("src.e2e.windows_preprocess._upload") as upload,
                  patch("src.e2e.windows_preprocess._launch") as launch,
                  patch("src.e2e.windows_preprocess._receipt", side_effect=[
                      ObservationPaused("observer paused"),
                      E2EError("POST timed out; raw output should stay private"),
                  ])):
                with self.assertRaises(ObservationPaused):
                    apply_recipe(driver, "sid", source, "wgui", str)
                with self.assertRaisesRegex(E2EError, "PREPROCESS_STEP_TRANSPORT_FAILED"):
                    apply_recipe(driver, "sid", source, "wgui", str)
                self.assertEqual(upload.call_count, 1)
                self.assertEqual(launch.call_count, 1)
                receipt = read_json(driver.staging / "metadata/preprocessing.json")
                self.assertEqual(receipt["status"], "failed")
                self.assertNotIn("raw output", str(receipt))


if __name__ == "__main__":
    unittest.main()
