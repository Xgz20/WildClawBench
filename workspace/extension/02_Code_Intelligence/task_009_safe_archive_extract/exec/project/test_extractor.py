import tempfile
import unittest
import zipfile
from pathlib import Path

from extractor import ExtractionError, extract_plugin


class ExtractorTests(unittest.TestCase):
    def make_bundle(self, root, entries):
        bundle_path = root / "plugin.zip"
        with zipfile.ZipFile(bundle_path, "w", zipfile.ZIP_DEFLATED) as bundle:
            for name, data in entries:
                bundle.writestr(name, data)
        return bundle_path

    def test_valid_bundle_preserves_bytes_and_returns_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = self.make_bundle(
                root,
                [
                    ("plugin.json", b'{"name":"demo"}\n'),
                    ("src/main.py", b"VALUE = 7\n"),
                ],
            )
            destination = root / "installed"

            result = extract_plugin(bundle, destination)

            self.assertEqual(result, ["plugin.json", "src/main.py"])
            self.assertEqual(
                (destination / "plugin.json").read_bytes(),
                b'{"name":"demo"}\n',
            )
            self.assertEqual(
                (destination / "src/main.py").read_bytes(),
                b"VALUE = 7\n",
            )

    def test_parent_traversal_is_rejected_without_installation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = self.make_bundle(root, [("../escaped.txt", b"unsafe")])
            destination = root / "installed"

            with self.assertRaises(ExtractionError):
                extract_plugin(bundle, destination)

            self.assertFalse(destination.exists())
            self.assertFalse((root / "escaped.txt").exists())

    def test_entry_limit_is_rejected_without_installation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = self.make_bundle(
                root,
                [("a.txt", b"a"), ("b.txt", b"b")],
            )
            destination = root / "installed"

            with self.assertRaises(ExtractionError):
                extract_plugin(bundle, destination, max_entries=1)

            self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
