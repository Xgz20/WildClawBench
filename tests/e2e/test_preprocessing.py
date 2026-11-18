import hashlib
import json
import struct
import tempfile
from pathlib import Path
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import zipfile

from src.e2e.agentcube import AgentCubeConfig
from src.e2e.backend import ObservationPaused
from src.e2e.common import E2EError, atomic_json, digest, read_json
from src.e2e.preparation import normalize_plan
from src.e2e.preprocessing import effective, freeze_assets, frozen_recipe, inspect_asset, require_admission, selection
from src.e2e.windows_preprocess import apply_recipe, build_payload


def recipe(asset):
    return {"version_id": 4, "name": "Test variant", "version": 2,
            "steps": [{"kind": "powershell", "asset": asset, "timeout": 10, "attachments": []}]}


class PreprocessingTests(unittest.TestCase):
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
            with self.assertRaisesRegex(E2EError, "ISOLATION_NOT_VERIFIED"):
                require_admission(AgentCubeConfig(), unit)
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
