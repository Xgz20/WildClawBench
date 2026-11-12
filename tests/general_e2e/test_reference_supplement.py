from pathlib import Path
from types import SimpleNamespace
from copy import deepcopy
import hashlib, json, os, stat, sys, tempfile, unittest

from tests.general_e2e.test_local_scoring_runtime import RUNTIME, Fixture

SUPPLEMENT = RUNTIME.reference_supplement
AUTH = 'Direct human request to research and independently rescore on 2026-11-01'
SHA = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()


class ReferenceSupplementTests(unittest.TestCase):
    def test_new_office_reference_is_guarded_without_rewriting_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            fixture = self.fixture(Path(folder)); attempt, manifest, request, document, rt = fixture
            source = request.with_name('source.txt'); office = source.with_suffix('.xlsx')
            source.rename(office)
            document['documents'][0].update(name='reference.xlsx',path=office.name)
            request.write_text(json.dumps(document))
            try:
                self.register(fixture)
                copied = attempt/'reference-supplement/files/reference.xlsx'
                self.assertEqual(copied.read_bytes(),office.read_bytes())
                guard=json.loads((attempt/'reference-supplement/manifest.json').read_bytes())['office_byte_guard']
                self.assertFalse(guard['original_bytes_changed'])
                if sys.platform=='darwin':
                    self.assertTrue(copied.stat().st_flags & stat.UF_IMMUTABLE)
                    with self.assertRaises(PermissionError):copied.write_bytes(b'host metadata mutation')
                self.assertEqual(len(SUPPLEMENT.validate(attempt,manifest)),2)
            finally:RUNTIME._remove_tree(attempt)

    def fixture(self, root, *, attempt=None):
        source = root / 'research'; source.mkdir()
        (source / 'source.txt').write_text('Public source evidence; not candidate behavior.', encoding='utf-8')
        attempt = attempt or root / 'attempt'; attempt.mkdir(exist_ok=True)
        manifest = {'identity': {'task_id': 'fixture-task', 'scoring_attempt_id': 'rescore-new'},
                    'judge': {'protocol': 'codex-agent-judge-v1'},
                    'lineage': {'kind': 'rescore', 'source_score_sha256': 'a' * 64}}
        (attempt / 'attempt-manifest.json').write_text(json.dumps(manifest))
        document = {'schema_version': SUPPLEMENT.INPUT_SCHEMA, 'task_id': 'fixture-task',
                    'source_score_sha256': 'a' * 64, 'documents': [{
                        'name': 'source.txt', 'path': 'source.txt', 'sha256': SHA(source / 'source.txt'),
                        'size': (source / 'source.txt').stat().st_size, 'url': 'https://publisher.example/paper',
                        'retrieved_at': '2026-11-01T00:00:00+00:00', 'kind': 'citation_context_excerpt',
                        'description': 'A public citation excerpt; full article not obtained.'}]}
        request = source / 'request.json'; request.write_text(json.dumps(document))
        rt = SimpleNamespace(verify_attempt=lambda path: None, _make_read_only=RUNTIME._make_read_only,
                             _remove_tree=RUNTIME._remove_tree)
        return attempt, manifest, request, document, rt

    def register(self, fixture):
        attempt, manifest, request, document, rt = fixture
        return SUPPLEMENT.register(rt, attempt_root=attempt, source_manifest=request, authorization_reference=AUTH)

    def test_registration_is_portable_idempotent_and_preserves_original_inputs(self):
        with tempfile.TemporaryDirectory() as folder:
            fixture = self.fixture(Path(folder)); attempt, manifest, request, document, rt = fixture
            old = (attempt / 'attempt-manifest.json').read_bytes()
            result = self.register(fixture)
            self.assertFalse(result['candidate_output']); self.assertFalse(result['candidate_behavior_evidence'])
            self.assertEqual((attempt / 'attempt-manifest.json').read_bytes(), old)
            self.assertFalse((attempt / 'reference-supplement/files/source.txt').stat().st_mode & 0o222)
            self.assertTrue(self.register(fixture)['idempotent'])
            request.unlink(); request.with_name('source.txt').unlink()
            self.assertEqual(len(SUPPLEMENT.validate(attempt, manifest)), 2)

    def test_source_identity_authorization_and_rescore_are_required(self):
        for kind in ['task', 'score', 'initial', 'authorization', 'api']:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as folder:
                fixture = self.fixture(Path(folder)); attempt, manifest, request, document, rt = fixture
                if kind in {'task', 'score'}:
                    document['task_id' if kind == 'task' else 'source_score_sha256'] = 'other'
                    request.write_text(json.dumps(document))
                if kind == 'initial':
                    manifest.pop('lineage'); (attempt / 'attempt-manifest.json').write_text(json.dumps(manifest))
                if kind == 'api':
                    manifest['judge']['protocol'] = 'api-judge-v1'
                    (attempt / 'attempt-manifest.json').write_text(json.dumps(manifest))
                with self.assertRaises(ValueError):
                    SUPPLEMENT.register(rt, attempt_root=attempt, source_manifest=request,
                                        authorization_reference='bad' if kind == 'authorization' else AUTH)
                self.assertFalse((attempt / 'reference-supplement').exists())

    def test_no_new_supplement_after_semantic_request_or_final_score(self):
        for name in ['semantic', 'semantic-component.json', 'score.json']:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as folder:
                fixture = self.fixture(Path(folder)); attempt = fixture[0]
                if name == 'semantic': (attempt / name).mkdir()
                else: (attempt / name).write_text('{}')
                with self.assertRaisesRegex(ValueError, 'TOO_LATE'):
                    self.register(fixture)
                self.assertFalse((attempt / 'reference-supplement').exists())

    def test_bad_paths_links_provenance_and_source_hash_fail_before_publication(self):
        for kind in ['parent', 'absolute', 'symlink', 'url', 'timestamp', 'hash', 'duplicate', 'unknown-score-field']:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as folder:
                fixture = self.fixture(Path(folder)); attempt, manifest, request, document, rt = fixture
                row = document['documents'][0]
                if kind == 'parent': row['path'] = '../source.txt'
                if kind == 'absolute': row['path'] = str(request.with_name('source.txt'))
                if kind == 'symlink':
                    request.with_name('link.txt').symlink_to('source.txt'); row['path'] = 'link.txt'
                if kind == 'url': row['url'] = 'https://user:secret@publisher.example/paper'
                if kind == 'timestamp': row['retrieved_at'] = '2026-11-01T00:00:00'
                if kind == 'hash': row['sha256'] = '0' * 64
                if kind == 'duplicate': document['documents'].append(deepcopy(row))
                if kind == 'unknown-score-field': row['score'] = 1.0
                request.write_text(json.dumps(document))
                with self.assertRaises(ValueError): self.register(fixture)
                self.assertFalse((attempt / 'reference-supplement').exists())

    def test_supplement_must_be_in_frozen_catalog_and_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            fixture = self.fixture(Path(folder)); attempt, manifest, request, document, rt = fixture
            self.register(fixture); files = SUPPLEMENT.validate(attempt, manifest)
            semantic = attempt / 'semantic'; semantic.mkdir()
            (semantic / 'evidence-catalog.json').write_text('{"evidence_index":{"entries":[]}}')
            with self.assertRaisesRegex(ValueError, 'NOT_IN_FROZEN_CATALOG'):
                SUPPLEMENT.validate(attempt, manifest)
            catalog = {'evidence_index': {'entries': [{'reference': {'path': p.relative_to(attempt).as_posix(), 'sha256': SHA(p)}} for p in files]}}
            (semantic / 'evidence-catalog.json').write_text(json.dumps(catalog))
            self.assertEqual(len(SUPPLEMENT.validate(attempt, manifest)), 2)
            source = attempt / 'reference-supplement/files/source.txt'; source.chmod(0o600); source.write_text('drift')
            with self.assertRaisesRegex(ValueError, 'FILE_DRIFT'):
                SUPPLEMENT.validate(attempt, manifest)

    def test_candidate_role_identity_and_extra_members_cannot_drift(self):
        for kind in ['role', 'identity', 'member']:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as folder:
                fixture = self.fixture(Path(folder)); attempt, manifest, request, document, rt = fixture
                self.register(fixture); base = attempt / 'reference-supplement'; target = base / 'manifest.json'
                current = json.loads(target.read_text())
                if kind == 'role': current['candidate_behavior_evidence'] = True
                if kind == 'identity': current['identity']['task_id'] = 'other'
                if kind == 'member':
                    base.chmod(0o700); (base / 'extra.txt').write_text('not registered')
                else:
                    target.chmod(0o600); target.write_text(json.dumps(current))
                with self.assertRaises(ValueError): SUPPLEMENT.validate(attempt, manifest)

    def test_semantic_reference_inputs_include_frozen_supplement_as_grader_material(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); baseline = Fixture(root / 'case', grading_type='llm_judge', rule='',
                llm_judge_rubric='### Criterion 1: Source (key: source, weight: 1)\nEvidence required.')
            attempt = baseline.prepare(); manifest = json.loads((attempt / 'attempt-manifest.json').read_text())
            manifest['lineage'] = {'kind': 'rescore', 'source_score_sha256': 'a' * 64}
            (attempt / 'attempt-manifest.json').write_text(json.dumps(manifest))
            (root / 'inputs').mkdir(); fixture = self.fixture(root / 'inputs', attempt=attempt)
            # Keep the real task's frozen paths for the catalogue integration.
            fake = fixture[1]; manifest['identity'] = fake['identity']
            (attempt / 'attempt-manifest.json').write_text(json.dumps(manifest))
            self.register((attempt, manifest, fixture[2], fixture[3], fixture[4]))
            references, _ = RUNTIME._semantic_reference_inputs(attempt, manifest, [])
            added = [r for r in references if r.get('path', '').startswith('reference-supplement/')]
            self.assertEqual(len(added), 2)
            self.assertTrue(all(row['type'] == 'grader_generated_evidence' for row in added))

    def test_real_semantic_preparation_query_and_archive_use_the_nested_catalog(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            baseline = Fixture(root / 'case', grading_type='llm_judge', rule='', task_id='fixture-task',
                llm_judge_rubric='### Criterion 1: Source (key: source, weight: 1)\n**Score 1.0**: Supported.\n**Score 0.0**: Wrong.')
            attempt = baseline.prepare('score-reference-rescore')
            manifest = json.loads((attempt / 'attempt-manifest.json').read_text())
            manifest['lineage'] = {'kind': 'rescore', 'source_scoring_attempt_id': 'score-prior',
                'source_attempt_manifest_sha256': 'b' * 64, 'source_score_sha256': 'a' * 64,
                'source_score_valid': False, 'source_candidate_sha256': manifest['digests']['candidate_original_sha256'],
                'source_judge': manifest['judge']}
            (attempt / 'attempt-manifest.json').write_text(json.dumps(manifest))
            inputs = root / 'inputs'; inputs.mkdir()
            (inputs / 'source.txt').write_text('Public source evidence; not candidate behavior.')
            request = {'schema_version': SUPPLEMENT.INPUT_SCHEMA, 'task_id': 'fixture-task',
                'source_score_sha256': 'a' * 64, 'documents': [{
                    'name': 'source.txt', 'path': 'source.txt', 'sha256': SHA(inputs / 'source.txt'),
                    'size': (inputs / 'source.txt').stat().st_size, 'url': 'https://publisher.example/paper',
                    'retrieved_at': '2026-11-01T00:00:00+00:00', 'kind': 'citation_context_excerpt',
                    'description': 'Public excerpt, not a full article.'}]}
            request_file = inputs / 'request.json'; request_file.write_text(json.dumps(request))
            SUPPLEMENT.register(RUNTIME, attempt_root=attempt, source_manifest=request_file, authorization_reference=AUTH)
            RUNTIME.prepare_semantics_attempt(attempt_root=attempt)
            RUNTIME.verify_attempt(attempt)
            catalog = RUNTIME.query_evidence_attempt(attempt_root=attempt, mode='catalog',
                path_contains='reference-supplement/')
            entry = next(row for row in catalog['items'] if row['reference']['path'].endswith('/source.txt'))
            page = RUNTIME.query_evidence_attempt(attempt_root=attempt, mode='file', evidence_id=entry['id'])
            self.assertIn('Public source evidence', json.dumps(page))
            response = json.loads((attempt / 'semantic/response-template.json').read_text())
            response['criteria'][0].update(status='judged', score=1.0,
                reason='合成补证材料已通过正式目录查询，仅验证协议闭包，不代表真实模型判分。',
                evidence_ids=[entry['id']], review={'query_ids': ['query-0002'],
                    'supporting_evidence_checked': True, 'contradicting_evidence_checked': True,
                    'absence_claim': False, 'complete_event_range_checked': False})
            response['notes'] = '合成响应用于补证、查询、合分和归档接口测试。'
            response_file = attempt / 'fixture-response.json'; response_file.write_text(json.dumps(response))
            RUNTIME.record_semantics_attempt(attempt_root=attempt, response_path=response_file)
            RUNTIME.finalize_score_attempt(attempt_root=attempt)
            score_bytes = (attempt / 'score.json').read_bytes()
            RUNTIME._remove_tree(attempt / 'runtime')
            RUNTIME._remove_tree(inputs)
            RUNTIME.verify_attempt(attempt, require_runtime=False)
            RUNTIME.verify_score_attempt(attempt_root=attempt, archived=True)
            self.assertEqual((attempt / 'score.json').read_bytes(), score_bytes)


if __name__ == '__main__': unittest.main()
