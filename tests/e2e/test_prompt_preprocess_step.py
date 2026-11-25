"""Scheme-bound references share the existing witness and immutable Prompt flow."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from src.e2e.agentcube import AgentCubeConfig
from src.e2e.common import E2EError, read_json
from src.e2e.preprocess_validation import run_validation
from src.e2e.preprocessing import (normalize_recipe, normalize_binding, prompt_directives, selection, freeze_assets,
                                   budget, augment_prompt, PROMPT_STEP_CAPABILITY)
from src.e2e.protocol import describe


STEP = {"kind": "prompt_plugin", "plugin_mentions": ["sites-skills"]}
RECIPE = {"version_id": 1, "version": 1, "name": "只引用 Sites", "steps": [STEP]}
PROFILE = {"id": "fixture", "enabled": True, "harness": "astronstudio", "template": "fixture", "models": [{"id": "model"}]}


class PromptPreprocessStepTests(unittest.TestCase):
    def test_prompt_only_recipe_needs_no_asset_and_keeps_default_prompt_untouched(self):
        recipe = normalize_recipe(RECIPE, "astronstudio")
        binding = normalize_binding({"default": recipe, "overrides": {"skip": None}}, "astronstudio")
        unit = {"unit_id": "u", "preprocessing": binding}
        self.assertEqual(prompt_directives(unit, "web"), {"plugin_mentions": ["sites-skills"]})
        self.assertEqual(prompt_directives(unit, "skip"), {"plugin_mentions": []})
        self.assertEqual(binding["prompt_plugin_validation"], "installed-plugin-v1")
        self.assertGreater(budget(unit), 0)  # Real pre/post witness budget only.
        with TemporaryDirectory() as root:
            destination = Path(root) / "assets"
            freeze_assets([unit], None, destination)
            self.assertFalse(destination.exists())
        base = "创建一个站点。\r\n"
        changed, _ = augment_prompt(base, prompt_directives(unit, "web"), recipe)
        self.assertEqual(changed.count("@sites-skills"), 1)
        self.assertEqual(augment_prompt(base, prompt_directives(unit, "skip"), None)[0], base)
        preview = selection([unit], [{"task_id": "web", "scene": "web"}, {"task_id": "skip", "scene": "general"}])
        self.assertEqual(preview["preprocessing"][0]["cases"][0]["prompt_directives"]["plugin_mentions"], ["sites-skills"])
        self.assertIsNone(preview["preprocessing"][0]["cases"][1]["recipe"])
        self.assertIn(PROMPT_STEP_CAPABILITY, describe(Path(__file__).resolve().parents[2])["capabilities"])

    def test_prompt_step_is_last_and_malformed_or_conflicting_values_are_rejected(self):
        physical = {"kind": "powershell", "timeout": 10, "attachments": [],
                    "asset": {"kind": "powershell", "name": "test.ps1", "size": 1, "sha256": "a" * 64}}
        result = normalize_recipe({**RECIPE, "steps": [STEP, physical]}, "astronstudio")
        self.assertEqual([step["kind"] for step in result["steps"]], ["powershell", "prompt_plugin"])
        for steps in ([STEP, STEP], [{**STEP, "timeout": 120}], [{"kind": "prompt_plugin", "plugin_mentions": []}],
                      [{"kind": "prompt_plugin", "plugin_mentions": ["@sites"]}]):
            with self.subTest(steps=steps), self.assertRaises(E2EError):
                normalize_recipe({**RECIPE, "steps": steps}, "astronstudio")
        with self.assertRaisesRegex(E2EError, "REQUIRES_ASTUDIO"):
            normalize_recipe(RECIPE, "workbuddy")
        with self.assertRaisesRegex(E2EError, "CONFIGURATION_CONFLICT"):
            normalize_binding({"default": RECIPE, "overrides": {}, "prompt_directives": {"default": ["old"], "overrides": {}}}, "astronstudio")

    def run_validation_fixture(self, root, output, recipe=RECIPE):
        client = Mock()
        client.create_session.return_value = "fixture-session"
        client.delete_session.return_value = {"confirmed": True}
        client.windows_execute.side_effect = [{"output": "3.7.0"}, {"output": json.dumps(output)}]
        observed = {}

        def factory(**kwargs):
            store = kwargs["store"]
            key = root.name
            stage = root / "execution/staging"
            stage.mkdir(parents=True)
            driver = SimpleNamespace(**kwargs, key=key, staging=stage, client=client,
                _phase=lambda phase, **fields: store.update(key, phase, **fields), checkpoint=Mock(),
                _checked_job=Mock(), _health=Mock(), _prepare_runtime=Mock())
            observed["driver"] = driver
            return driver

        request = {"profile_id": "fixture", "model": "model", "recipe": deepcopy(recipe)}
        with patch("src.e2e.preprocess_validation.profiles", return_value=[PROFILE]), \
                patch("src.e2e.preprocess_validation.AgentCubeConfig.load", return_value=AgentCubeConfig()):
            value = run_validation(root, request, None, driver_factory=factory)
        self.assertEqual(value, read_json(root / "validation.json"))
        return value, client, observed["driver"]

    def test_sandbox_validation_checks_preinstalled_plugin_and_publishes_proof_without_dispatch(self):
        with TemporaryDirectory() as directory:
            root = Path(directory) / "prompt-validation"
            root.mkdir()
            result, client, driver = self.run_validation_fixture(root, {"status": "passed", "plugins": [
                {"name": "sites-skills", "enabled": True, "version": "1.0.17", "tree_sha256": "a" * 64}]})
            self.assertEqual((result["status"], result["cleanup"]), ("passed", "released"))
            self.assertEqual(result["planned_steps"], ["prompt_plugin"])
            self.assertEqual(result["preprocessing"]["steps"][0]["status"], "passed")
            self.assertNotIn("asset_sha256", result["preprocessing"]["steps"][0])
            self.assertEqual(result["prompt_plugin_witness"]["plugins"][0]["version"], "1.0.17")
            self.assertEqual(driver._checked_job.call_args.args[0], "prompt-plugin-inspector-upload")
            client.delete_session.assert_called_once_with("fixture-session")

    def test_missing_plugin_has_explicit_step_failure_and_still_releases_sandbox(self):
        with TemporaryDirectory() as directory:
            root = Path(directory) / "prompt-validation"
            root.mkdir()
            result, client, _ = self.run_validation_fixture(root, {"status": "failed", "error": "PROMPT_PLUGIN_NOT_INSTALLED"})
            self.assertEqual((result["status"], result["cleanup"]), ("failed", "released"))
            self.assertEqual(result["error"], "PROMPT_PLUGIN_NOT_INSTALLED")
            self.assertEqual(result["preprocessing"]["steps"][0]["error"], "PROMPT_PLUGIN_NOT_INSTALLED")
            self.assertEqual(result["preprocessing"]["status"], "failed")
            client.close.assert_called_once()

    def test_environment_step_finishes_before_reference_verification(self):
        from src.e2e import windows_preprocess
        physical = {"kind": "powershell", "timeout": 10, "attachments": [],
                    "asset": {"kind": "powershell", "name": "test.ps1", "size": 1, "sha256": "a" * 64}}
        events = []
        inspect = windows_preprocess._verify_prompt_plugins

        def verify(*args, **kwargs):
            events.append("verify-plugin")
            return inspect(*args, **kwargs)

        with TemporaryDirectory() as directory:
            root = Path(directory) / "ordered-validation"
            root.mkdir()
            with patch.object(windows_preprocess, "_upload", side_effect=lambda *args: events.append("environment-upload")), \
                    patch.object(windows_preprocess, "_launch"), \
                    patch.object(windows_preprocess, "_receipt", side_effect=lambda *args: events.append("environment-finished") or {"status": "passed"}), \
                    patch.object(windows_preprocess, "_verify_prompt_plugins", side_effect=verify):
                result, _, _ = self.run_validation_fixture(root, {"status": "passed", "plugins": [
                    {"name": "sites-skills", "enabled": True, "version": "1.0.17", "tree_sha256": "a" * 64}]},
                    {**RECIPE, "steps": [STEP, physical]})
            self.assertEqual(events, ["environment-upload", "environment-finished", "verify-plugin"])
            self.assertEqual([row["kind"] for row in result["preprocessing"]["steps"]], ["powershell", "prompt_plugin"])
            self.assertEqual(result["status"], "passed")
