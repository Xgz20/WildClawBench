from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import json
import unittest
from unittest.mock import Mock, patch

from src.e2e import preprocess_windows_guest as guest
from src.e2e.common import E2EError
from src.e2e.windows_preprocess import verify_remote_plugins


class RemotePluginTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.home = self.root / "home"
        self.work = self.root / "step"
        self.payload = self.work / "payload"
        self.cache = self.home / "plugins/cache/astron-plugin-hub/sites-skills"
        self.slot = self.cache / "1.0.16"
        self.write_plugin(self.slot, "sites-skills", "1.0.16", "original")
        self.write_plugin(self.payload, "sites-skills", "1.0.17", "candidate")
        self.identity = self.cache / guest.REMOTE_PLUGIN_METADATA
        self.identity.write_text(json.dumps({"schema_version": 1, "remote_plugin_id": "test-identity"}))
        self.step = {"target": "sites-skills", "marketplace": "astron-plugin-hub", "version": "1.0.17", "timeout": 20}
        self.rpc = Mock()
        self.rpc.call.side_effect = lambda method, _: {"marketplaces": []} if method == "plugin/installed" else {"data": []}
        self.enterContext(patch.object(guest, "user_path", side_effect=lambda path: path.resolve(strict=True)))
        self.enterContext(patch.object(guest, "astudio_paths", return_value=(None, None, None, self.home)))

        @contextmanager
        def runtime(*args):
            yield self.rpc

        self.enterContext(patch.object(guest, "runtime", side_effect=runtime))

    def write_plugin(self, root, name, version, body):
        manifest = root / ".codex-plugin/plugin.json"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps({"name": name, "version": version}))
        skill = root / "skills/sites-building/SKILL.md"
        skill.parent.mkdir(parents=True, exist_ok=True)
        skill.write_text("---\nname: sites-building\n---\n" + body)

    def test_overlay_keeps_remote_identity_and_published_cache_slot(self):
        old_identity = self.identity.read_bytes()
        result = guest.apply_plugin(self.work, self.step, None, self.home)
        self.assertEqual(result["version"], "1.0.17")
        self.assertEqual(result["plugin_cache_version"], "1.0.16")
        self.assertFalse(result["plugin_runtime_observed"])
        self.assertNotEqual(result["before_sha256"], result["after_sha256"])
        self.assertEqual(guest.tree(self.slot), guest.tree(self.payload))
        self.assertEqual(self.identity.read_bytes(), old_identity)
        self.assertNotIn("plugin/install", [call.args[0] for call in self.rpc.call.call_args_list])
        args = (*[self.step[key] for key in ("marketplace", "target")], result["plugin_cache_version"],
                result["after_sha256"], result["plugin_identity_sha256"])
        guest.verify_remote_plugin_cache(*args)
        (self.slot / "skills/sites-building/SKILL.md").write_text("restored or modified")
        with self.assertRaisesRegex(guest.StepError, "ASTUDIO_REMOTE_PLUGIN_CACHE_DRIFT"):
            guest.verify_remote_plugin_cache(*args)

    def test_conflicting_runtime_skill_path_rolls_back_overlay(self):
        self.rpc.call.side_effect = lambda method, _: {"marketplaces": []} if method == "plugin/installed" else {
            "data": [{"skills": [{"name": "sites-building", "enabled": True, "path": str(self.root / "other/SKILL.md")}]}],
        }
        baseline = guest.tree(self.slot)
        with self.assertRaisesRegex(guest.StepError, "ASTUDIO_REMOTE_PLUGIN_SKILL_NOT_ACTIVE"):
            guest.apply_plugin(self.work, self.step, None, self.home)
        self.assertEqual(guest.tree(self.slot), baseline)

    def test_worker_verification_failure_surfaces_before_result_handoff(self):
        recipe = {"steps": [{"kind": "plugin", "marketplace": "astron-plugin-hub", "target": "sites-skills"}]}
        proof = {"index": 0, "status": "passed", "plugin_cache_version": "1.0.16",
                 "after_sha256": "a" * 64, "plugin_identity_sha256": "b" * 64}
        driver = SimpleNamespace(key="fixture", store=Mock(), client=Mock())
        driver.store.get.return_value = {"attempt_id": "attempt", "preprocess_receipt": {"steps": [proof]}}
        driver.client.windows_execute.return_value = {"output": json.dumps({
            "status": "failed", "error": "ASTUDIO_REMOTE_PLUGIN_CACHE_DRIFT",
        })}
        with self.assertRaisesRegex(E2EError, "ASTUDIO_REMOTE_PLUGIN_CACHE_DRIFT"):
            verify_remote_plugins(driver, "sandbox-session", recipe, str)
        command = driver.client.windows_execute.call_args.args[1]
        self.assertIn("--verify-remote-plugin 'astron-plugin-hub' 'sites-skills' '1.0.16'", command)
