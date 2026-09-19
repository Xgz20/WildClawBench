from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "eval_general_e2e/contracts"
SPEC = importlib.util.spec_from_file_location("general_collection_validation_test", CONTRACTS / "collection_validation.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.path.insert(0, str(CONTRACTS))
try:
    SPEC.loader.exec_module(MODULE)
finally:
    sys.path.remove(str(CONTRACTS))


def create_fixture(parent: Path) -> dict:
    uri = (ROOT / "tests/general_e2e/helpers/general-collection-fixture.mjs").as_uri()
    source = f"import {{ fixture }} from {json.dumps(uri)}; process.stdout.write(JSON.stringify(await fixture({{parent:{json.dumps(str(parent))}}})));"
    result = subprocess.run(["node", "--input-type=module", "-e", source], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def validate(value: dict, **overrides) -> dict:
    args = {"unit_root": Path(value["root"]), "state_path": Path(value["statePath"]),
            "index_path": Path(value["indexPath"]), "resource_path": Path(value["resourcePath"])}
    return MODULE.validate_collection(**{**args, **overrides})


class GeneralCollectionSnapshotTests(unittest.TestCase):
    def test_ancestor_symlink_inside_same_unit_is_rejected_before_resolution(self):
        with tempfile.TemporaryDirectory() as temporary:
            value = create_fixture(Path(temporary))
            alias = Path(value["root"]) / "alias"
            alias.symlink_to(Path(value["statePath"]).parent, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "COLLECTION_PATH_INVALID.*symbolic link"):
                validate(value, state_path=alias / "automation-state.json")

    def test_prompt_changed_between_state_validation_and_snapshot_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            value = create_fixture(Path(temporary))
            original = MODULE.validate_terminal_execution_state

            def validate_then_change(document, **kwargs):
                original(document, **kwargs)
                Path(document["prompt"]["path"]).write_text("changed after validation", encoding="utf-8")

            with mock.patch.object(MODULE, "validate_terminal_execution_state", side_effect=validate_then_change):
                with self.assertRaisesRegex(ValueError, "COLLECTION_PROMPT_SNAPSHOT_MISMATCH"):
                    validate(value)

    def test_transcript_validation_uses_locked_bytes_even_if_file_is_swapped(self):
        with tempfile.TemporaryDirectory() as temporary:
            value = create_fixture(Path(temporary))
            transcript = Path(value["traceRoot"]) / "transcript.jsonl"
            valid_bytes = transcript.read_bytes()
            invalid_bytes = b"invalid-json\n"
            transcript.write_bytes(invalid_bytes)
            index = value["index"]
            index["transcript"].update(sha256=hashlib.sha256(invalid_bytes).hexdigest(), size=len(invalid_bytes))
            index_path = Path(value["indexPath"])
            index_path.write_text(json.dumps(index), encoding="utf-8")
            resource = value["metrics"]
            index_bytes = index_path.read_bytes()
            resource["collection"]["sources"][1].update(sha256=hashlib.sha256(index_bytes).hexdigest(), size=len(index_bytes))
            Path(value["resourcePath"]).write_text(json.dumps(resource), encoding="utf-8")
            original = MODULE.validate_transcript_jsonl_bytes

            def swap_then_validate(data):
                self.assertEqual(data, invalid_bytes)
                transcript.write_bytes(valid_bytes)
                return original(data)

            with mock.patch.object(MODULE, "validate_transcript_jsonl_bytes", side_effect=swap_then_validate):
                with self.assertRaisesRegex(ValueError, "JSON_INVALID"):
                    validate(value)
