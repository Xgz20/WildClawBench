import hashlib
import importlib.util
from io import BytesIO
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ENTRY = Path(__file__).resolve().parents[2] / 'tools/report/skills/general-e2e/execute-general-e2e/scripts/initial_office_metadata.py'
SPEC = importlib.util.spec_from_file_location('workbuddy_initial_office_metadata', ENTRY)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
sha = lambda data: hashlib.sha256(data).hexdigest()


def office(marker=False, changed=False):
    output = BytesIO()
    with zipfile.ZipFile(output, 'w') as z:
        extra = '<Override PartName="/docProps/custom.xml" ContentType="%s"/>' % MODULE.CUSTOM_TYPE if marker else ''
        z.writestr('[Content_Types].xml', '<Types xmlns="%s">%s</Types>' % (MODULE.CT, extra))
        extra = '<Relationship Id="cwm" Type="%s" Target="docProps/custom.xml"/>' % MODULE.CUSTOM_REL if marker else ''
        z.writestr('_rels/.rels', '<Relationships xmlns="%s">%s</Relationships>' % (MODULE.REL, extra))
        z.writestr('xl/workbook.xml', b'changed-business' if changed else b'original-business')
        if marker:
            z.writestr('docProps/custom.xml', '<Properties xmlns="%s" xmlns:vt="urn:types"><property name="CWM0123456789abcdef0123456789abcdef" pid="2" fmtid="{D5CDD505-2E9C-101B-9397-08002B2CF9AE}"><vt:lpwstr>host marker</vt:lpwstr></property></Properties>' % MODULE.CP)
    return output.getvalue()


class InitialOfficeMetadataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.round = Path(self.temp.name).resolve()
        self.unit = self.round / 'WorkBuddy'
        self.workspace = self.unit / 'execution/tasks/task/workspace'
        self.workspace.mkdir(parents=True)
        self.original = office()
        self.current = office(marker=True)
        self.file = self.workspace / 'input.xlsx'; self.file.write_bytes(self.current)
        manifest = {'batch_id': 'batch', 'unit_id': 'workbuddy', 'tasks': [{
            'task_id': 'task', 'workspace': {'path': 'execution/tasks/task/workspace', 'entries': [
                {'kind': 'file', 'mode': '0644', 'path': 'input.xlsx', 'sha256': sha(self.original), 'size': len(self.original)}]}}]}
        raw = (json.dumps(manifest) + '\n').encode()
        (self.unit / 'manifest.json').write_bytes(raw)
        self.archive = self.round / '.general-e2e/packages/WorkBuddy/execution.zip'
        self.archive.parent.mkdir(parents=True)
        with zipfile.ZipFile(self.archive, 'w') as z:
            z.writestr('original/manifest.json', raw)
            z.writestr('original/execution/tasks/task/workspace/input.xlsx', self.original)
        (self.unit / '.general-e2e').mkdir()
        (self.unit / '.general-e2e/round-unit.json').write_text(json.dumps({
            'batch_id': 'batch', 'unit_id': 'workbuddy', 'execution_package': '.general-e2e/packages/WorkBuddy/execution.zip',
            'execution_sha256': sha(self.archive.read_bytes())}))

    def tearDown(self):
        if sys.platform == 'darwin':
            for file in self.round.rglob('*'):
                if file.is_file() and not file.is_symlink(): os.chflags(file, 0)
        self.temp.cleanup()

    def test_cwm_only_audit_retains_original_and_observed_bytes_without_editing_workspace(self):
        with patch.object(MODULE.time, 'sleep'):
            result = MODULE.audit(self.unit, 'task', self.unit / '.general-e2e/queue-repairs/test/audit')
        self.assertEqual(result['status'], 'PASS_CWM_ONLY')
        self.assertEqual(self.file.read_bytes(), self.current)
        proof = json.loads(Path(result['proof']).read_text())
        self.assertEqual(proof['execution_package_sha256'], sha(self.archive.read_bytes()))
        self.assertTrue(proof['variants'][0]['office_delta']['business_members_unchanged'])
        self.assertEqual((self.unit / proof['variants'][0]['original']['path']).read_bytes(), self.original)
        self.assertFalse(proof['workspace_modified'])

    def test_business_member_changes_are_never_admitted_as_metadata(self):
        self.file.write_bytes(office(marker=True, changed=True))
        with self.assertRaisesRegex(ValueError, 'business Office member changed'), patch.object(MODULE.time, 'sleep'):
            MODULE.audit(self.unit, 'task', self.unit / '.general-e2e/queue-repairs/test/audit')

    def test_original_archive_drift_is_rejected_before_publication(self):
        with self.archive.open('ab') as stream: stream.write(b'drift')
        with self.assertRaisesRegex(ValueError, 'original execution ZIP drift'):
            MODULE.audit(self.unit, 'task', self.unit / '.general-e2e/queue-repairs/test/audit')
