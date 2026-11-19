import copy
import json
from pathlib import Path
import tempfile
import unittest

from migrate import MigrationError, migrate_document, migrate_file


ROOT = Path(__file__).resolve().parent


class MigrateTest(unittest.TestCase):
    def test_v1_to_v3_preserves_extension(self):
        original = json.loads((ROOT / "sample_v1.json").read_text(encoding="utf-8"))
        source_copy = copy.deepcopy(original)
        self.assertEqual(
            migrate_document(original),
            {
                "version": 3,
                "service": {
                    "name": "billing-api",
                    "endpoint": "https://billing.internal",
                },
                "timeouts": {"request_seconds": 12},
                "features": {"enabled": ["audit", "retry"]},
                "customer_extension": {"region": "ap-east"},
            },
        )
        self.assertEqual(original, source_copy)

    def test_v2_preserves_nested_and_top_level_extensions(self):
        original = json.loads((ROOT / "sample_v2.json").read_text(encoding="utf-8"))
        migrated = migrate_document(original)
        self.assertEqual(migrated["service"]["owner"], "search-platform")
        self.assertEqual(migrated["deployment_hint"], "blue")

    def test_invalid_document_does_not_replace_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "config.json"
            path.write_text('{"version": 1, "service_name": ""}\n', encoding="utf-8")
            before = path.read_bytes()
            with self.assertRaises((MigrationError, ValueError)):
                migrate_file(path, ROOT / "schema_v3.json")
            self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
