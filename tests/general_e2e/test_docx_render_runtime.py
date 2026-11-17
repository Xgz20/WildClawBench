"""Word render protocol controls; the fake PDF envelope is not visual evidence."""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from src.wildclawbench_grading_core.office_runtime import (
    DOCX_RENDER_AUDIT_SCHEMA, DOCX_RENDER_FILTER, DOCX_RENDER_PROFILE,
    OfficeRuntimeError, _inspect_docx_render_package, create_office_lock,
    create_office_render_lock, render_docx_pdf, render_pptx_pdf,
    validate_office_render_lock,
)
from tests.general_e2e.test_local_scoring_runtime import Fixture, LOCK_PATH, RUNTIME

ROOT = Path(__file__).resolve().parents[2]
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
PKG = 'http://schemas.openxmlformats.org/package/2006/relationships'


def document_bytes(extra=None, *, body=None, relationships=''):
    body = body if body is not None else '<w:p><w:r><w:t>正文</w:t></w:r></w:p><w:sectPr/>'
    parts = {
        '[Content_Types].xml': '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        '_rels/.rels': f'<Relationships xmlns="{PKG}"><Relationship Id="main" Type="{R}officeDocument" Target="word/document.xml"/></Relationships>',
        'word/document.xml': f'<w:document xmlns:w="{W}"><w:body>{body}</w:body></w:document>',
        'word/_rels/document.xml.rels': f'<Relationships xmlns="{PKG}">{relationships}</Relationships>',
        **(extra or {}),
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        for name, data in parts.items():
            archive.writestr(name, data)
    return buffer.getvalue()


@unittest.skipIf(os.name == 'nt', 'Unix fake executable; native Windows rendering needs separate acceptance')
class DocxRenderRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.font = self.root / 'fixture.ttf'
        self.font.write_bytes(b'font-identity-only')
        self.binary = self.root / 'fake-soffice'
        self.binary.write_text('#!' + sys.executable + '\n' + '''import sys,pathlib,os,json
if '--version' in sys.argv:
    print('LibreOffice 99.0 word-render-fixture');raise SystemExit(0)
assert 'AWS_ACCESS_KEY_ID' not in os.environ
assert pathlib.Path(os.environ['FONTCONFIG_FILE']).is_file()
assert pathlib.Path(os.environ['SAL_FONTPATH_PRIVATE']).is_dir()
options=sys.argv[sys.argv.index('--convert-to')+1]
assert options.startswith('pdf:writer_pdf_Export:')
properties=json.loads(options.split(':',2)[2])
assert properties['ExportNotes']['value']=='false'
assert properties['IsSkipEmptyPages']['value']=='false'
source=pathlib.Path(sys.argv[-1]);assert source.name=='document.docx'
target=pathlib.Path(sys.argv[sys.argv.index('--outdir')+1])/'document.pdf'
target.write_bytes(b'%PDF-1.4\\nprotocol-fixture-only\\n%%EOF\\n')
''', encoding='utf-8')
        self.binary.chmod(0o755)
        self.office = create_office_lock(self.binary)
        self.render = create_office_render_lock(self.office, [self.font], document_format='docx')
        self.source = self.root / 'converted.docx'
        self.source.write_bytes(document_bytes())

    def test_explicit_word_profile_preserves_source_and_records_writer_options(self):
        original = self.source.read_bytes()
        with patch.dict(os.environ, {'AWS_ACCESS_KEY_ID': 'not-inherited'}):
            result = render_docx_pdf(self.source, self.render, self.root / 'derived')
        self.assertEqual(self.source.read_bytes(), original)
        audit = result['audit']
        self.assertEqual(audit['schema_version'], DOCX_RENDER_AUDIT_SCHEMA)
        self.assertEqual(audit['profile'], DOCX_RENDER_PROFILE)
        self.assertEqual(audit['export_filter'], DOCX_RENDER_FILTER)
        self.assertEqual(audit['source_sha256'], hashlib.sha256(original).hexdigest())
        self.assertEqual(audit['source_body_paragraph_count'], 1)
        self.assertEqual(audit['source_body_table_count'], 0)
        self.assertNotIn('source_slide_count', audit)
        with self.assertRaisesRegex(OfficeRuntimeError, 'OFFICE_OUTPUT_EXISTS'):
            render_docx_pdf(self.source, self.render, self.root / 'derived')

    def test_pptx_default_lock_is_not_silently_reused_for_word(self):
        old = create_office_render_lock(self.office, [self.font])
        with self.assertRaisesRegex(OfficeRuntimeError, 'OFFICE_RENDER_PROFILE_MISMATCH'):
            render_docx_pdf(self.source, old, self.root / 'wrong-profile')
        other = self.root / 'annual.pptx'
        other.write_bytes(b'not inspected before profile check')
        with self.assertRaisesRegex(OfficeRuntimeError, 'OFFICE_RENDER_PROFILE_MISMATCH'):
            render_pptx_pdf(other, self.render, self.root / 'wrong-pptx-profile')

    def test_passive_hyperlinks_and_note_parts_are_allowed_but_active_sources_rejected(self):
        hyperlink = f'<Relationship Id="h" Type="{R}hyperlink" Target="https://example.invalid/" TargetMode="External"/>'
        self.assertEqual(_inspect_docx_render_package(document_bytes(relationships=hyperlink))['source_format'], 'docx')
        note = f'<Relationship Id="n" Type="{R}footnotes" Target="notes/note%20one.xml"/>'
        self.assertEqual(_inspect_docx_render_package(document_bytes({'word/notes/note one.xml': f'<w:footnotes xmlns:w="{W}"/>'}, relationships=note))['source_format'], 'docx')
        variants = [
            ({'word/vbaProject.bin': b'fake'}, '', 'ACTIVE_CONTENT'),
            ({'word/embeddings/book.xlsx': b'fake'}, '', 'ACTIVE_CONTENT'),
            ({'word/afchunk.htm': b'fake'}, '', 'ACTIVE_CONTENT'),
            ({}, f'<Relationship Id="n" Type="{R}attachedTemplate" Target="https://example.invalid/template" TargetMode="External"/>', 'EXTERNAL_DATA'),
            ({}, f'<Relationship Id="n" Type="{R}image" Target="../../outside.png"/>', 'INPUT_INVALID'),
            ({}, f'<Relationship Id="n" Type="{R}image" Target="missing.png"/>', 'INPUT_INVALID'),
            ({}, f'<Relationship Id="n" Type="{R}image" Target="%2e%2e/%2e%2e/outside.png"/>', 'INPUT_INVALID'),
            ({'../escape.txt': b'fake'}, '', 'INPUT_INVALID'),
        ]
        for extra, relationships, code in variants:
            with self.subTest(code=code, extra=list(extra)), self.assertRaisesRegex(OfficeRuntimeError, code):
                _inspect_docx_render_package(document_bytes(extra, relationships=relationships))

    def test_simple_split_and_unbalanced_field_instructions_are_checked(self):
        for instruction in ['DDEAUTO service', 'INCLUDETEXT "https://example.invalid/a"', 'LINK Excel.Sheet.12 a', 'DATABASE source']:
            with self.subTest(instruction=instruction), self.assertRaisesRegex(OfficeRuntimeError, 'EXTERNAL_DATA'):
                _inspect_docx_render_package(document_bytes(body='<w:p><w:fldSimple w:instr="' + instruction.replace('"', '&quot;') + '"/></w:p>'))
        split = '<w:p><w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText> DDE</w:instrText></w:r><w:r><w:instrText>AUTO service</w:instrText></w:r><w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>cache</w:t></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>'
        with self.assertRaisesRegex(OfficeRuntimeError, 'EXTERNAL_DATA'):
            _inspect_docx_render_package(document_bytes(body=split))
        allowed = split.replace(' DDE', ' PA').replace('AUTO service', 'GE ')
        self.assertEqual(_inspect_docx_render_package(document_bytes(body=allowed))['source_body_paragraph_count'], 1)
        with self.assertRaisesRegex(OfficeRuntimeError, 'unbalanced'):
            _inspect_docx_render_package(document_bytes(body='<w:p><w:r><w:instrText> DDEAUTO x</w:instrText></w:r></w:p>'))

    def test_wrong_main_root_and_ambiguous_relationships_are_explicit(self):
        variants = [
            {'word/document.xml': f'<w:settings xmlns:w="{W}"/>'},
            {'word/_rels/document.xml.rels': f'<Relationships xmlns="{PKG}"><Relationship Id="n" Type="{R}hyperlink" Target="#a"/><Relationship Id="n" Type="{R}hyperlink" Target="#b"/></Relationships>'},
            {'_rels/.rels': f'<Relationships xmlns="{PKG}"><Relationship Id="a" Type="{R}officeDocument" Target="word/document.xml"/><Relationship Id="b" Type="{R}officeDocument" Target="word/document.xml"/></Relationships>'},
            {'word/comments.xml': b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY x "bad">]><x/>'},
        ]
        for extra in variants:
            with self.subTest(extra=list(extra)), self.assertRaisesRegex(OfficeRuntimeError, 'OFFICE_INPUT_INVALID'):
                _inspect_docx_render_package(document_bytes(extra))

    def test_word_font_drift_converter_failure_timeout_and_source_drift_publish_no_pdf(self):
        self.font.write_bytes(b'changed')
        with self.assertRaisesRegex(OfficeRuntimeError, 'FONT_DRIFT'):
            render_docx_pdf(self.source, self.render, self.root / 'font-drift')
        self.font.write_bytes(b'font-identity-only')
        with patch('src.wildclawbench_grading_core.office_runtime.subprocess.run', return_value=subprocess.CompletedProcess([], 1, b'', b'failure')):
            with self.assertRaisesRegex(OfficeRuntimeError, 'OFFICE_RENDER_FAILED'):
                render_docx_pdf(self.source, self.render, self.root / 'failed')
        with patch('src.wildclawbench_grading_core.office_runtime.subprocess.run', side_effect=subprocess.TimeoutExpired([], 1)):
            with self.assertRaisesRegex(OfficeRuntimeError, 'OFFICE_RENDER_TIMEOUT'):
                render_docx_pdf(self.source, self.render, self.root / 'timeout')
        real_run = subprocess.run
        def drift(*args, **kwargs):
            result = real_run(*args, **kwargs)
            self.source.write_bytes(self.source.read_bytes() + b'changed')
            return result
        with patch('src.wildclawbench_grading_core.office_runtime.subprocess.run', side_effect=drift):
            with self.assertRaisesRegex(OfficeRuntimeError, 'OFFICE_SOURCE_DRIFT'):
                render_docx_pdf(self.source, self.render, self.root / 'drift')
        for name in ['font-drift', 'failed', 'timeout', 'drift']:
            self.assertFalse((self.root / name / 'rendered.pdf').exists())

    def make_attempt(self, name, *, use_reference=False, missing_lock=False, rule=None):
        helper = (ROOT / 'src/wildclawbench_grading_core/office_runtime.py').read_bytes()
        location = "gt/reference.docx" if use_reference else "converted.docx"
        checks = rule or f'''def grade(**kwargs):
    from pathlib import Path
    import os,json,runpy
    root=Path(kwargs['workspace_path'])
    lock=json.loads(Path(os.environ['GENERAL_E2E_OFFICE_RENDER_LOCK']).read_text())
    result=runpy.run_path(str(root/'gt/office_runtime.py'))['render_docx_pdf'](root/'{location}',lock,Path(os.environ['GENERAL_E2E_RULE_EVIDENCE_DIR'])/'word')
    score=float(Path(result['path']).is_file())
    return {{'rendering':score,'overall_score':score}}
'''
        extra = {'office_runtime.py': helper}
        if use_reference:
            extra['reference.docx'] = self.source.read_bytes()
        fixture = Fixture(self.root / name, rule=checks, scoring_runtime={'office': True, 'office_render': True}, extra_gt_files=extra)
        if not use_reference:
            (fixture.candidate / 'converted.docx').write_bytes(self.source.read_bytes())
        entries, digest = RUNTIME._inventory_tree(fixture.candidate)
        artifact_path = fixture.candidate.parent / 'candidate-artifact.json'
        value = json.loads(artifact_path.read_text()); value.update(entries=entries, expected_sha256=digest)
        artifact_path.write_text(json.dumps(value), encoding='utf-8')
        value = json.loads(fixture.execution_record.read_text()); value['candidate']['frozen_sha256'] = digest
        fixture.execution_record.write_text(json.dumps(value), encoding='utf-8')
        base = self.root / (name + '-office.json'); base.write_text(json.dumps(self.office), encoding='utf-8')
        combined = self.root / (name + '-runtime.json')
        if missing_lock:
            value = json.loads(LOCK_PATH.read_text()); value['office_runtime'] = self.office
            combined.write_text(json.dumps(value), encoding='utf-8')
        else:
            RUNTIME.bootstrap_office_render_runtime(base, [self.font], combined, LOCK_PATH, document_format='docx')
        prepared = RUNTIME.prepare_attempt(unit_root=fixture.unit_root, execution_record_path=fixture.execution_record,
            scoring_package=fixture.scoring_package, task_id=fixture.task_id, scoring_attempt_id=name,
            output_root=fixture.output_root, runtime_lock_path=combined)
        return Path(prepared['attempt_root'])

    def test_missing_render_lock_does_not_make_a_candidate_zero(self):
        attempt = self.make_attempt('missing-lock', missing_lock=True)
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError, 'OFFICE_RENDER_RUNTIME_REQUIRED'):
            RUNTIME.run_rules_attempt(attempt_root=attempt, runtime_python=Path(sys.executable), timeout_seconds=10)
        self.assertFalse((attempt / 'rule-component.json').exists())
        self.assertFalse((attempt / 'score.json').exists())

    def test_worker_and_archive_bind_word_pdf_and_remain_verifiable_without_engine(self):
        attempt = self.make_attempt('worker')
        result = RUNTIME.run_rules_attempt(attempt_root=attempt, runtime_python=Path(sys.executable), timeout_seconds=30)
        self.assertEqual(result['rule_component']['score'], 1.)
        references, _ = RUNTIME._semantic_reference_inputs(attempt, json.loads((attempt / 'attempt-manifest.json').read_text()), [])
        self.assertIn('worker/derived/word/rendered.pdf', {row['path'] for row in references})
        RUNTIME.prepare_semantics_attempt(attempt_root=attempt)
        RUNTIME.finalize_score_attempt(attempt_root=attempt)
        self.font.unlink(); self.binary.unlink(); shutil.rmtree(attempt / 'runtime')
        self.assertTrue(RUNTIME.verify_score_attempt(attempt, archived=True)['score_valid'])
        (attempt / 'worker/derived/word/rendered.pdf').write_bytes(b'tampered')
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError, 'OFFICE_DERIVED_ARTIFACT_DRIFT'):
            RUNTIME.verify_score_attempt(attempt, archived=True)

    def test_private_reference_can_be_bound_without_fabricating_candidate_delivery(self):
        attempt = self.make_attempt('reference', use_reference=True)
        result = RUNTIME.run_rules_attempt(attempt_root=attempt, runtime_python=Path(sys.executable), timeout_seconds=30)
        self.assertEqual(result['rule_component']['score'], 1.)
        self.assertTrue(RUNTIME._verify_office_rule_evidence(attempt, required=True, render_required=True))

    def test_changed_profile_source_structure_and_filter_cannot_be_reindexed_as_valid(self):
        attempt = self.make_attempt('receipt-binding')
        RUNTIME.run_rules_attempt(attempt_root=attempt, runtime_python=Path(sys.executable), timeout_seconds=30)
        receipt_path = attempt / 'worker/derived/word/render-audit.json'
        original_receipt = receipt_path.read_bytes()
        audit_path = attempt / 'rule-audit.json'; original_audit = audit_path.read_bytes()
        for key, value in [('source_sha256', '0' * 64), ('source_sha256', []), ('profile', 'offline-pptx-to-pdf-with-fonts/v1'),
                           ('export_filter', {}), ('font_assets', []), ('source_body_table_count', 3),
                           ('source_format', 'pptx'), ('source_body_paragraph_count', True)]:
            with self.subTest(key=key, value=value):
                receipt = json.loads(original_receipt); receipt[key] = value
                receipt_path.write_text(json.dumps(receipt), encoding='utf-8')
                audit = json.loads(original_audit)
                row = next(row for row in audit['derived_artifacts'] if row['path'].endswith('/render-audit.json'))
                row.update(sha256=hashlib.sha256(receipt_path.read_bytes()).hexdigest(), size=receipt_path.stat().st_size)
                audit_path.write_text(json.dumps(audit), encoding='utf-8')
                with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError, 'OFFICE_RENDER_AUDIT_INVALID'):
                    RUNTIME._verify_office_rule_evidence(attempt, required=True, render_required=True)


if __name__ == '__main__':
    unittest.main()
