"""Read-only input validation and crash recovery on synthetic workspaces."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / 'tools/report/skills/general-e2e/execute-general-e2e/scripts/prepare_quota_retry.py'
spec = importlib.util.spec_from_file_location('quota_workspace_recovery_test', HELPER)
RECOVERY = importlib.util.module_from_spec(spec)
spec.loader.exec_module(RECOVERY)


class QuotaWorkspaceRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='quota-workspace-test-')
        self.unit = Path(self.temp.name).resolve()
        self.workspace = self.unit / 'execution/tasks/quota-task/workspace'
        self.workspace.mkdir(parents=True)
        self.prompt = self.workspace.parent / 'PROMPT.md'
        self.prompt.write_bytes(b'Frozen prompt.')
        (self.workspace / 'input.txt').write_bytes(b'initial')
        entries = RECOVERY.inventory(self.workspace)
        self.manifest = dict(batch_id='test-batch', unit_id='test-unit', task_ids=['quota-task'], tasks=[
            dict(task_id='quota-task', prompt=dict(path='execution/tasks/quota-task/PROMPT.md', sent_sha256=RECOVERY.sha(self.prompt.read_bytes())),
                 workspace=dict(path='execution/tasks/quota-task/workspace', entries=entries))])
        (self.unit / 'manifest.json').write_bytes(RECOVERY.encoded(self.manifest))
        self.package = self.unit / 'execution.zip'
        with zipfile.ZipFile(self.package, 'w') as z:
            for p in [self.unit / 'manifest.json', self.prompt, self.workspace / 'input.txt']:
                z.write(p, 'fixture/' + p.relative_to(self.unit).as_posix())
        (self.workspace / 'input.txt').write_bytes(b'changed by failed attempt')
        (self.workspace / 'partial.txt').write_bytes(b'old partial evidence')
        self.control = self.unit / '.general-e2e/execution/quota-task'
        self.control.mkdir(parents=True)
        identity = dict(batch_id='test-batch', unit_id='test-unit', task_id='quota-task', attempt_id='old-attempt')
        state = dict(identity=identity, phase='FAILED', run_config=dict(config_digest='a' * 64),
                     prompt=dict(send_status='sent', sha256=RECOVERY.sha(self.prompt.read_bytes())),
                     send=dict(dispatch_attempt_count=1), session=dict(verified=True, thread_id='old-thread', turn_id='old-turn', session_id='old-session', cwd=str(self.workspace)),
                     execution=dict(business_status='candidate_error', error=dict(code='ASTRONSTUDIO_TURN_ERROR',
                         message='unexpected status 402 Payment Required: astron_points_exhausted')))
        (self.control / 'automation-state.json').write_bytes(RECOVERY.encoded(state))
        (self.control / 'execution-record.json').write_bytes(RECOVERY.encoded(dict(identity=identity)))
        self.queue_path = self.unit / '.general-e2e/queues/original/queue-state.json'
        self.queue_path.parent.mkdir(parents=True)
        self.queue = dict(identity=dict(batch_id='test-batch', unit_id='test-unit', queue_id='original', queue_digest='b' * 64),
                          configuration=dict(run_config_digest='a' * 64), tasks=[dict(task_id='quota-task', selected_attempt_id='old-attempt')])
        self.queue_path.write_bytes(RECOVERY.encoded(self.queue))
        self.authorization = RECOVERY.describe(self.unit, 'original', 'quota-task', self.package)
        self.authorization.update(authorized_by='test human', authorization_reference='synthetic explicit instruction',
                                  reason='Quota restored; retry once', quota_restored=True, retry_authorized=True)
        self.authorization_path = self.unit / 'authorization.json'
        self.authorize()

    def tearDown(self):
        self.temp.cleanup()

    def authorize(self):
        raw = RECOVERY.encoded(self.authorization)
        self.authorization_path.write_bytes(raw)
        self.authorization_sha = RECOVERY.sha(raw)
        self.queue['tasks'][0]['quota_recoveries'] = [dict(old_attempt_id='old-attempt',
            new_attempt_id=self.authorization['new_attempt_id'], authorization_sha256=self.authorization_sha)]
        self.queue_path.write_bytes(RECOVERY.encoded(self.queue))

    def test_templates_are_not_automatic_human_approval(self):
        template = RECOVERY.describe(self.unit, 'original', 'quota-task', self.package)
        self.assertFalse(template['quota_restored'])
        self.assertFalse(template['retry_authorized'])
        self.assertEqual(template['authorized_by'], '')

    def test_archival_and_restore_are_exact_and_idempotent(self):
        original = (self.control / 'automation-state.json').read_bytes()
        (self.control / 'driver.lock').write_bytes(b'transient runtime lock')
        receipt = RECOVERY.prepare(self.unit, self.authorization_path, self.authorization_sha)
        archive = Path(receipt['receipt_path']).parent
        self.assertEqual((self.workspace / 'input.txt').read_bytes(), b'initial')
        self.assertFalse((self.workspace / 'partial.txt').exists())
        self.assertEqual((archive / 'failed-workspace/partial.txt').read_bytes(), b'old partial evidence')
        self.assertEqual((archive / 'failed-control/automation-state.json').read_bytes(), original)
        self.assertEqual((self.control / 'automation-state.json').read_bytes(), original)
        self.assertEqual(RECOVERY.prepare(self.unit, self.authorization_path, self.authorization_sha), receipt)

    def test_interruption_between_workspace_renames_recovers_same_transaction(self):
        rename = Path.rename
        def power_loss(path, target):
            if path.name == 'pristine-workspace' and Path(target) == self.workspace:
                raise RuntimeError('synthetic interruption after failed workspace archived')
            return rename(path, target)
        with patch.object(Path, 'rename', power_loss):
            with self.assertRaisesRegex(RuntimeError, 'synthetic interruption'):
                RECOVERY.prepare(self.unit, self.authorization_path, self.authorization_sha)
        self.assertFalse(self.workspace.exists())
        receipt = RECOVERY.prepare(self.unit, self.authorization_path, self.authorization_sha)
        self.assertEqual(receipt['new_attempt_id'], self.authorization['new_attempt_id'])
        self.assertEqual((self.workspace / 'input.txt').read_bytes(), b'initial')
        RECOVERY.verify_receipt(self.unit, self.authorization_path, self.authorization_sha, True)

    def test_rehashed_archive_edits_cannot_change_the_authorized_failed_workspace(self):
        receipt = RECOVERY.prepare(self.unit, self.authorization_path, self.authorization_sha)
        archive = Path(receipt['receipt_path']).parent
        (archive / 'failed-workspace/partial.txt').write_bytes(b'altered evidence')
        metadata_path = archive / 'archive-manifest.json'
        metadata = json.loads(metadata_path.read_bytes())
        metadata['workspace_entries'] = RECOVERY.inventory(archive / 'failed-workspace')
        metadata_path.write_bytes(RECOVERY.encoded(metadata))
        receipt['archive_manifest_sha256'] = RECOVERY.file_sha(metadata_path)
        Path(receipt['receipt_path']).write_bytes(RECOVERY.encoded(receipt))
        with self.assertRaisesRegex(ValueError, 'OLD_WORKSPACE_SHA'):
            RECOVERY.verify_receipt(self.unit, self.authorization_path, self.authorization_sha)

    def test_completed_or_unapproved_tasks_cannot_be_reset(self):
        for approved, completed in [(False, False), (True, True)]:
            with self.subTest(approved=approved, completed=completed):
                state = json.loads((self.control / 'automation-state.json').read_bytes())
                state['phase'] = 'COMPLETED' if completed else 'FAILED'
                (self.control / 'automation-state.json').write_bytes(RECOVERY.encoded(state))
                self.authorization['old_state_sha256'] = RECOVERY.file_sha(self.control / 'automation-state.json')
                self.authorization['old_control_sha256'] = RECOVERY.tree_sha(RECOVERY.control_inventory(self.control))
                self.authorization['retry_authorized'] = approved
                self.authorize()
                before = RECOVERY.inventory(self.workspace)
                with self.assertRaises(ValueError):
                    RECOVERY.prepare(self.unit, self.authorization_path, self.authorization_sha)
                self.assertEqual(RECOVERY.inventory(self.workspace), before)

    def test_scored_or_packaged_units_are_not_reopened(self):
        state = self.unit / '.general-e2e/run-general-e2e-state.json'
        state.write_bytes(RECOVERY.encoded(dict(stages=dict(score='COMPLETED', package='COMPLETED'))))
        before = RECOVERY.inventory(self.workspace)
        with self.assertRaisesRegex(ValueError, 'FROZEN_COMPLETED_UNIT'):
            RECOVERY.prepare(self.unit, self.authorization_path, self.authorization_sha)
        self.assertEqual(RECOVERY.inventory(self.workspace), before)


if __name__ == '__main__':
    unittest.main()
