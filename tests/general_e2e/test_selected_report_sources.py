from pathlib import Path
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / "tools/report/skills/general-e2e/report-general-e2e/scripts/selected_report.py"
SPEC = importlib.util.spec_from_file_location("selected_report_sources_tested", SCRIPT)
REPORT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = REPORT
SPEC.loader.exec_module(REPORT)


class SelectedReportSourcesTest(unittest.TestCase):
    def test_source_config_uses_frozen_unit_and_rejects_client_or_model_drift(self):
        target={"unit_id":"unit","harness":{"id":"doubaowork","version":"2.31.10"},"model":{"requested_id":"current"},"execution_mode":"automatic"}
        REPORT.verify_source_unit_config({"unit":target},target)
        for key,value in [("harness",{"id":"doubaowork","version":"other"}),("model",{"requested_id":"other"}),("execution_mode","manual"),("unit_id","other")]:
            with self.assertRaisesRegex(ValueError,"UNIT_CONFIG_DRIFT"):
                REPORT.verify_source_unit_config({"unit":{**target,key:value}},target)

    def test_multiple_sources_require_an_explicit_package_for_each_task(self):
        sources = {"original": {"task_ids": ["a", "b"]}, "recovery": {"task_ids": ["b"]}}
        with self.assertRaisesRegex(ValueError, "SOURCE_PACKAGE_REQUIRED"):
            REPORT.select_source_package(sources, {}, "b")
        self.assertIs(REPORT.select_source_package(sources, {"source_package_id": "recovery"}, "b"), sources["recovery"])
        for choice, task, error in [("unknown", "b", "PACKAGE_UNKNOWN"), ("recovery", "a", "OUTSIDE_SOURCE_SCOPE")]:
            with self.assertRaisesRegex(ValueError, error):
                REPORT.select_source_package(sources, {"source_package_id": choice}, task)
        self.assertIs(REPORT.select_source_package({"original": sources["original"]}, {}, "a"), sources["original"])

    def test_duplicate_or_empty_source_lists_are_rejected(self):
        for value, error in [([], "PACKAGES_INVALID"), ([{"package_id": "same"}, {"package_id": "same"}], "PACKAGE_DUPLICATE")]:
            with self.assertRaisesRegex(ValueError, error):
                REPORT.source_package_items({"packages": value})

    def test_subset_sources_still_require_sha_unit_and_ordered_scope(self):
        with tempfile.TemporaryDirectory() as temp:
            REPORT.ROOT = Path(temp).resolve()
            root = Path(temp) / "package"
            root.mkdir()
            path = root / "package-manifest.json"
            def check(scope, unit="unit", allow_subset=True, digest=None):
                path.write_text(json.dumps({"identity": {"unit_id": unit, "task_ids": scope}, "entries": []}))
                expected = digest or hashlib.sha256(path.read_bytes()).hexdigest()
                return REPORT.verify_source_package(root, expected, "unit", ["a", "b", "c"], allow_subset=allow_subset)
            check(["b"])
            for scope in [[], ["unknown"], ["b", "b"], ["c", "a"]]:
                with self.assertRaisesRegex(ValueError, "PACKAGE_SCOPE"):
                    check(scope)
            with self.assertRaisesRegex(ValueError, "PACKAGE_SCOPE"):
                check(["b"], unit="another")
            with self.assertRaisesRegex(ValueError, "PACKAGE_SCOPE"):
                check(["b"], allow_subset=False)
            with self.assertRaisesRegex(ValueError, "MANIFEST_DRIFT"):
                check(["b"], digest="0" * 64)


if __name__ == "__main__":
    unittest.main()
