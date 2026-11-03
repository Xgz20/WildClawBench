import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

SCRIPT = Path(__file__).resolve().parents[2] / "tools/report/skills/general-e2e/execute-general-e2e/scripts/restore_workbuddy_initial_workspace.py"
spec = importlib.util.spec_from_file_location("restore_workbuddy_initial", SCRIPT)
restore = importlib.util.module_from_spec(spec)
spec.loader.exec_module(restore)


class WorkBuddyInitialRestoreTests(unittest.TestCase):
    def fixture(self, root):
        unit = root / "unit"
        (unit / ".general-e2e").mkdir(parents=True)
        content = b"frozen input"
        task = {"task_id": "task", "workspace": {"path": "execution/tasks/task/workspace", "entries": [
            {"path": "input", "kind": "directory", "mode": "0755"},
            {"path": "input/source.txt", "kind": "file", "mode": "0644", "sha256": hashlib.sha256(content).hexdigest(), "size": len(content)}]}}
        manifest = json.dumps({"tasks": [task]}).encode()
        (unit / "manifest.json").write_bytes(manifest)
        archive = root / "execution.zip"
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("package/manifest.json", manifest)
            z.writestr("package/execution/tasks/task/workspace/input/source.txt", content)
        (unit / ".general-e2e/round-unit.json").write_text(json.dumps({"execution_package": "execution.zip", "execution_sha256": hashlib.sha256(archive.read_bytes()).hexdigest()}))
        return unit, archive

    def test_restores_exact_frozen_bytes_without_touching_existing_workspace(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            unit, _ = self.fixture(root)
            old = unit / "execution/tasks/task/workspace"
            old.mkdir(parents=True)
            (old / "candidate.txt").write_text("keep me")
            result = restore.restore(unit, "task", root / "new")
            self.assertEqual(result["file_count"], 1)
            self.assertEqual((root / "new/input/source.txt").read_bytes(), b"frozen input")
            self.assertEqual((old / "candidate.txt").read_text(), "keep me")

    def test_changed_zip_fails_before_creating_new_workspace(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            unit, archive = self.fixture(root)
            with archive.open("ab") as h:
                h.write(b"drift")
            with self.assertRaisesRegex(AssertionError, "EXECUTION_ZIP_DRIFT"):
                restore.restore(unit, "task", root / "new")
            self.assertFalse((root / "new").exists())

    def test_existing_target_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            unit, _ = self.fixture(root)
            target = root / "new"
            target.mkdir()
            (target / "keep.txt").write_text("keep")
            with self.assertRaisesRegex(AssertionError, "RESTORE_TARGET_EXISTS"):
                restore.restore(unit, "task", target)
            self.assertEqual((target / "keep.txt").read_text(), "keep")
