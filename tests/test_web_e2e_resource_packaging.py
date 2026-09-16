from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "tools/report/skills"


class ResourcePackagingTest(unittest.TestCase):
    def test_history_cli_never_writes_inside_candidate_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task = root / "task"
            task.mkdir()
            state = root / "automation_state.json"
            state.write_text(json.dumps({"driver": {"id": "workbuddy"}, "session": {}}), encoding="utf-8")
            script = SKILLS / "execute-web-e2e/scripts/collect-resource-metrics.mjs"
            args = ["node", str(script), "--state", str(state), "--workspace", str(task), "--harness", "workbuddy", "--output"]
            rejected = subprocess.run([*args, str(task / "new.json")], text=True, capture_output=True)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertFalse((task / "new.json").exists())
            target = root / "audit.json"
            accepted = subprocess.run([*args, str(target)], text=True, capture_output=True)
            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            before = target.read_bytes()
            repeated = subprocess.run([*args, str(target)], text=True, capture_output=True)
            self.assertNotEqual(repeated.returncode, 0)
            self.assertEqual(target.read_bytes(), before)

    def test_standalone_execute_package_contains_resource_collector(self):
        script = SKILLS / "prepare-web-e2e-workspaces/scripts/prepare_web_e2e_workspaces.py"
        spec = importlib.util.spec_from_file_location("prepare_resource_package", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "execute.zip"
            module.zip_skill(SKILLS / "execute-web-e2e", archive)
            with zipfile.ZipFile(archive) as package:
                for name in ("capture", "collect", "worker", "parsers"):
                    self.assertIn(f"execute-web-e2e/drivers/metrics/{name}.mjs", package.namelist())
                self.assertIn("execute-web-e2e/scripts/collect-resource-metrics.mjs", package.namelist())
                self.assertIn("execute-web-e2e/references/resource-metrics.md", package.namelist())
                self.assertFalse(any("node_modules/" in name for name in package.namelist()))
                package.extractall(root)
            result = subprocess.run(
                ["node", str(root / "execute-web-e2e/drivers/metrics/worker.mjs")],
                input=json.dumps({"harness": "workbuddy", "workspace": str(root), "state": {"session": {}}}),
                text=True, capture_output=True, check=True, cwd=root,
            )
            metrics = json.loads(result.stdout)
            self.assertIsNone(metrics["usage"]["total_tokens"])
            self.assertEqual(metrics["collection"]["warnings"], ["MISSING_STABLE_SESSION"])
