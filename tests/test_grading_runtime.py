import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from src.utils import grading, grading_runtime


class GradingRuntimeTests(unittest.TestCase):
    def test_no_pdf_does_not_install_or_probe(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(grading_runtime, "_pdf_version") as probe, patch.object(grading_runtime.subprocess, "run") as install:
            root = Path(directory)
            (root / "gt").mkdir()
            (root / "gt/private.pdf").write_bytes(b"pdf")
            result = grading_runtime.prepare_pdf_runtime(directory)
            self.assertEqual(result["status"], "not_required")
            probe.assert_not_called()
            install.assert_not_called()

    def test_existing_compatible_dependency_needs_no_network(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(grading_runtime, "_pdf_version", return_value="6.0.0"), patch.object(grading_runtime.subprocess, "run") as install:
            (Path(directory) / "reference.PDF").write_bytes(b"pdf")
            self.assertEqual(grading_runtime.prepare_pdf_runtime(directory)["version"], "6.0.0")
            install.assert_not_called()

    def test_installs_in_scoring_python_and_preserves_attempt_audit(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(grading_runtime, "_pdf_version", side_effect=[None, "6.0.0", "6.0.0"]), patch.object(grading_runtime.subprocess, "run", return_value=Mock(returncode=0)) as install:
            root = Path(directory)
            (root / "reference.pdf").write_bytes(b"pdf")
            self.assertTrue(grading_runtime.prepare_pdf_runtime(directory)["installed"])
            grading_runtime.prepare_pdf_runtime(directory)
            self.assertEqual(install.call_count, 1)
            command = install.call_args.args[0]
            self.assertEqual(command[:3], [sys.executable, "-m", "pip"])
            self.assertIn("pypdf>=5,<7", command)
            audit = json.loads((root / ".grading/judge/runtime_dependencies.json").read_text())
            self.assertEqual([r["installed"] for r in audit["checks"]], [True, False])

    def test_install_failure_is_not_silently_ignored(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(grading_runtime, "_pdf_version", return_value=None), patch.object(grading_runtime.subprocess, "run", return_value=Mock(returncode=1, stderr="secret index password")):
            root = Path(directory)
            (root / "reference.pdf").write_bytes(b"pdf")
            with self.assertRaisesRegex(RuntimeError, "DEPENDENCY_INSTALL_FAILED") as raised:
                grading_runtime.prepare_pdf_runtime(directory)
            self.assertNotIn("secret", str(raised.exception))
            self.assertEqual(json.loads((root / ".grading/judge/runtime_dependencies.json").read_text())["checks"][0]["status"], "failed")

    def test_install_timeout_is_audited(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(grading_runtime, "_pdf_version", return_value=None), patch.object(grading_runtime.subprocess, "run", side_effect=subprocess.TimeoutExpired("pip", 120)):
            (Path(directory) / "reference.pdf").write_bytes(b"pdf")
            with self.assertRaisesRegex(RuntimeError, "DEPENDENCY_INSTALL_TIMEOUT"):
                grading_runtime.prepare_pdf_runtime(directory)

    def test_bootstrap_precedes_pdf_evidence_collection(self):
        code = grading._legacy_workspace_reader_code("/tmp_workspace")
        self.assertLess(code.index("prepare_pdf_runtime("), code.index("collect_workspace_evidence("))
        compile(code, "workspace_reader", "exec")
