from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[2] / 'tools/report/skills/general-e2e/score-general-e2e/scripts/native_moa_assistant_view.py'
SPEC = importlib.util.spec_from_file_location('native_moa_assistant_view_test', SOURCE)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class NativeMoaAssistantViewTests(unittest.TestCase):
    def fixture(self, root: Path, profile=MODULE.PROFILE):
        trace = root / 'trace/raw'
        trace.mkdir(parents=True)
        rows = [dict(role='assistant', content='我会先核验来源。', tool_calls=[{'id': 'c'}]),
                dict(role='tool', content='tool result', tool_call_id='c'),
                dict(role='assistant', content='final answer')]
        raw = b''.join((json.dumps(r, ensure_ascii=False)+'\n').encode() for r in rows)
        proof = json.dumps(dict(profile=profile, source_sha256=hashlib.sha256(raw).hexdigest())).encode()
        (trace/'trajectory.jsonl').write_bytes(raw)
        (trace/'native-moa-sdk-protocol.json').write_bytes(proof)
        identity = dict(batch_id='b', unit_id='u', task_id='t', attempt_id='execution')
        index = dict(identity=identity, normalization=dict(compatibility_profiles=[profile]), raw_trace=[
            dict(path='raw/trajectory.jsonl', sha256=hashlib.sha256(raw).hexdigest(), size=len(raw)),
            dict(path='raw/native-moa-sdk-protocol.json', sha256=hashlib.sha256(proof).hexdigest(), size=len(proof))])
        (root/'trace/trace-index.json').write_text(json.dumps(index))
        manifest = dict(trace_bundle={'path': 'trace/bundle.json'}, identity=dict(batch_id='b', unit_id='u', task_id='t', execution_attempt_id='execution', scoring_attempt_id='score'))
        return manifest, raw

    def test_preserves_original_assistant_rows_beside_calls_without_rewriting_frozen_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, raw = self.fixture(root)
            self.assertEqual(MODULE.materialize(root, manifest, create=False), [])
            view, audit = MODULE.materialize(root, manifest, create=True)
            selected = [json.loads(line) for line in view.read_bytes().splitlines()]
            self.assertEqual([r['content'] for r in selected], ['我会先核验来源。', 'final answer'])
            self.assertEqual(selected[0]['tool_calls'], [{'id': 'c'}])
            self.assertEqual([r['raw_line'] for r in json.loads(audit.read_bytes())['locations']], [1, 3])
            self.assertEqual((root/'trace/raw/trajectory.jsonl').read_bytes(), raw)
            self.assertEqual(MODULE.materialize(root, manifest, create=False), [view, audit])
            view.chmod(0o600)
            view.write_text('changed')
            with self.assertRaisesRegex(ValueError, 'content drift'):
                MODULE.materialize(root, manifest, create=False)

    def test_rejects_raw_digest_and_cross_execution_identity_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, raw = self.fixture(root)
            manifest['identity']['execution_attempt_id'] = 'other'
            with self.assertRaisesRegex(ValueError, 'identity mismatch'):
                MODULE.materialize(root, manifest, create=True)
            manifest['identity']['execution_attempt_id'] = 'execution'
            (root/'trace/raw/trajectory.jsonl').write_bytes(raw+b'\n')
            with self.assertRaisesRegex(ValueError, 'digest mismatch'):
                MODULE.materialize(root, manifest, create=True)

    def test_legacy_attempts_do_not_receive_a_native_view(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(MODULE.materialize(Path(tmp), {}, create=True), [])
            self.assertFalse((Path(tmp)/'native-compatibility').exists())

    def test_23519_view_preserves_raw_rows_and_rejects_conflicting_profile_declarations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = 'doubaowork-native-moa-sdk-model-protocol-2.35.19/v1'
            manifest, raw = self.fixture(root, profile)
            view, audit = MODULE.materialize(root, manifest, create=True)
            self.assertEqual((root/'trace/raw/trajectory.jsonl').read_bytes(), raw)
            self.assertEqual(len(view.read_bytes().splitlines()), 2)
            index_path = root/'trace/trace-index.json'
            index = json.loads(index_path.read_bytes())
            index['normalization']['compatibility_profiles'].append(MODULE.PROFILE)
            index_path.write_text(json.dumps(index))
            with self.assertRaisesRegex(ValueError, 'profile is ambiguous'):
                MODULE.materialize(root, manifest, create=False)
