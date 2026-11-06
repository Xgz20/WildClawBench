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
import uuid

ENTRY = Path(__file__).resolve().parents[2] / 'tools/report/skills/general-e2e/execute-general-e2e/scripts/initial_office_metadata.py'
SPEC = importlib.util.spec_from_file_location('workbuddy_initial_office_metadata', ENTRY)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
sha = lambda data: hashlib.sha256(data).hexdigest()


def office(marker=False, changed=False, unqualified=False):
    output = BytesIO()
    with zipfile.ZipFile(output, 'w') as z:
        extra = '<Override PartName="/docProps/custom.xml" ContentType="%s"/>' % MODULE.CUSTOM_TYPE if marker else ''
        if unqualified: extra = extra.replace('<Override ', '<Override xmlns="" ')
        z.writestr('[Content_Types].xml', '<Types xmlns="%s">%s</Types>' % (MODULE.CT, extra))
        extra = '<Relationship Id="cwm" Type="%s" Target="docProps/custom.xml"/>' % MODULE.CUSTOM_REL if marker else ''
        if unqualified: extra = extra.replace('<Relationship ', '<Relationship xmlns="" ')
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

    def test_registered_unqualified_custom_metadata_nodes_keep_all_business_parts_exact(self):
        delta = MODULE.office_delta(office(), office(marker=True, unqualified=True))
        self.assertTrue(delta['business_members_unchanged'])
        with self.assertRaisesRegex(ValueError, 'business Office member changed'):
            MODULE.office_delta(office(), office(marker=True, changed=True, unqualified=True))

    def framework_archive(self):
        entry=ENTRY.with_name('snapshot_framework_dispatch.py')
        sys.path.insert(0,str(entry.parent))
        try:
            spec=importlib.util.spec_from_file_location('framework_archive',entry)
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        finally:
            sys.path.pop(0)
        controls=self.unit/'.general-e2e/execution/task';controls.mkdir(parents=True)
        identity=dict(batch_id='batch',unit_id='workbuddy',task_id='task',attempt_id='old')
        old=json.dumps(dict(identity=identity,phase='NEEDS_ATTENTION',prompt={'send_status':'uncertain'},
                            send={'dispatch_attempt_count':1},session={'verified':False})).encode()
        record=json.dumps({'identity':identity}).encode()
        (controls/'automation-state.json').write_bytes(old);(controls/'execution-record.json').write_bytes(record)
        human=self.round/'human.json';human.write_bytes(b'direct human retry instruction')
        manifest_bytes=(self.unit/'manifest.json').read_bytes();initial=json.loads(manifest_bytes)['tasks'][0]['workspace']['entries']
        auth=dict(schema_version='general-e2e.unaccepted-dispatch-retry-authorization/v1',cleanup_authorized=True,retry_authorized=True,
                  task_id='task',batch_id='batch',unit_id='workbuddy',old_attempt_id='old',new_attempt_id=str(uuid.uuid4()),
                  unit_manifest_sha256=sha(manifest_bytes),old_state_sha256=sha(old),old_record_sha256=sha(record),
                  old_workspace_sha256=module.tree_sha(initial),human_source={'path':str(human),'sha256':sha(human.read_bytes())})
        root=self.unit/'.general-e2e/framework-dispatch-recoveries/task'/auth['new_attempt_id'];root.mkdir(parents=True)
        authorization=root/'authorization.json';authorization.write_text(json.dumps(auth))
        return module,authorization,root

    def test_framework_retry_archive_retains_both_CWM_versions_and_exact_business_comparison(self):
        module,authorization,root=self.framework_archive()
        with patch.object(MODULE.time,'sleep'):
            result=module.archive(self.unit,authorization)
        self.assertEqual(result['status'],'ARCHIVED')
        self.assertEqual(self.file.read_bytes(),self.current)
        metadata=json.loads((root/'archive-manifest.json').read_bytes())
        self.assertEqual(metadata['initial_office_metadata']['status'],'PASS_CWM_ONLY')
        self.assertEqual(module.archive(self.unit,authorization,True)['status'],'VERIFIED')

    def test_framework_retry_rejects_real_Office_edits_even_with_retry_authorization(self):
        module,authorization,root=self.framework_archive()
        self.file.write_bytes(office(marker=True,changed=True))
        with self.assertRaisesRegex(ValueError,'business Office member changed'),patch.object(MODULE.time,'sleep'):
            module.archive(self.unit,authorization)
        self.assertFalse((root/'failed-attempt.zip').exists())
