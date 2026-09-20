import json
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from qwenwork_metadata_preflight import inspect  # noqa: E402


class QwenWorkMetadataPreflightTest(unittest.TestCase):
    def test_counts_explicit_bindings_and_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "native.jsonl").write_text("\n".join([
                json.dumps({"sessionId": "s-1", "cwd": str(root / "workspace")}),
                json.dumps({"type": "segment", "segmentId": "a", "sessionId": "s-1", "cwd": str(root / "workspace")}),
                json.dumps({"type": "segment", "segmentId": "b", "sessionId": "s-1"}),
                json.dumps({"type": "segment", "segmentId": "c", "sessionId": "other", "cwd": "/elsewhere"}),
            ]) + "\n", encoding="utf-8")
            report = inspect(root)
        self.assertEqual(report["sessionId"], "s-1")
        self.assertEqual(report["cwd"], str((root / "workspace").resolve()))
        self.assertEqual(report["segments"]["session"], {"known": 2, "total": 3, "missing": 0, "mismatched": 1})
        self.assertEqual(report["segments"]["workspace"], {"known": 1, "total": 3, "missing": 1, "mismatched": 1})
        self.assertIsNone(report["usage"])
        self.assertIsNone(report["terminal"])

    def test_does_not_infer_from_directory_name(self):
        with tempfile.TemporaryDirectory(prefix="session-s-1-") as tmp:
            report = inspect(Path(tmp))
        self.assertIsNone(report["sessionId"])
        self.assertIsNone(report["cwd"])
        self.assertEqual(report["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
