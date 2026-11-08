"""Copied selected records must bind the original native evidence byte-for-byte."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
PATH=ROOT/'tools/report/skills/general-e2e/report-general-e2e/scripts/execution_evidence_root.py'
SPEC=importlib.util.spec_from_file_location('_execution_evidence_root_test',PATH)
MODULE=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(MODULE)


class ExecutionEvidenceRootTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.unit=Path(self.temp.name).resolve()/'unit';self.unit.mkdir()
        self.root=self.unit/'evidence/tasks/task/attempt';(self.root/'execution').mkdir(parents=True)
        self.record={'identity':{'task_id':'task','attempt_id':'attempt'}}
        self.original=self.root/'execution-record.json';self.original.write_text(json.dumps(self.record))
        (self.root/'execution/automation-state.json').write_text('{}')
        self.copy=self.unit.parent/'scoring/execution-records/task.json';self.copy.parent.mkdir(parents=True)
        self.copy.write_bytes(self.original.read_bytes())

    def test_formal_record_and_exact_selected_copy_resolve_the_same_root(self):
        for p in [self.original,self.copy]:
            self.assertEqual(MODULE.frozen_execution_evidence_root(self.unit,p,self.record),self.root)

    def test_different_original_missing_state_or_symlink_is_rejected(self):
        self.original.write_text('{"changed":true}')
        with self.assertRaisesRegex(ValueError,'ORIGINAL_RECORD_MISMATCH'):
            MODULE.frozen_execution_evidence_root(self.unit,self.copy,self.record)
        self.original.write_bytes(self.copy.read_bytes())
        (self.root/'execution/automation-state.json').unlink()
        with self.assertRaisesRegex(ValueError,'STATE_MISSING'):
            MODULE.frozen_execution_evidence_root(self.unit,self.copy,self.record)
        link=self.copy.parent/'link.json';link.symlink_to(self.copy)
        with self.assertRaisesRegex(ValueError,'UNSAFE'):
            MODULE.frozen_execution_evidence_root(self.unit,link,self.record)

    def test_unsafe_identity_cannot_escape_to_an_unrelated_directory(self):
        record={'identity':{'task_id':'../other','attempt_id':'attempt'}}
        with self.assertRaisesRegex(ValueError,'IDENTITY_UNSAFE'):
            MODULE.frozen_execution_evidence_root(self.unit,self.copy,record)


if __name__=='__main__':unittest.main()
