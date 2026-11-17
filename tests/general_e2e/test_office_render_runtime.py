"""Frozen rendering lifecycle controls; a fake converter does not prove appearance."""
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
    OfficeRuntimeError, _inspect_render_package, create_office_lock, create_office_render_lock,
    office_render_lock_digest, render_pptx_pdf, validate_office_render_lock,
)
from tests.general_e2e.test_local_scoring_runtime import Fixture, LOCK_PATH, RUNTIME
from tests.general_e2e.test_office_runtime import workbook_bytes

ROOT = Path(__file__).resolve().parents[2]
P = 'http://schemas.openxmlformats.org/presentationml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'


def presentation_bytes(extra=None):
    parts = {
        '[Content_Types].xml': '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        '_rels/.rels': f'<Relationships><Relationship Id="main" Type="{R}/officeDocument" Target="ppt/presentation.xml"/></Relationships>',
        'ppt/presentation.xml': f'<p:presentation xmlns:p="{P}" xmlns:r="{R}"><p:sldIdLst><p:sldId id="1" r:id="s1"/></p:sldIdLst></p:presentation>',
        'ppt/_rels/presentation.xml.rels': f'<Relationships><Relationship Id="s1" Type="{R}/slide" Target="slides/slide1.xml"/></Relationships>',
        'ppt/slides/slide1.xml': f'<p:sld xmlns:p="{P}"><p:cSld><p:spTree/></p:cSld></p:sld>',
        **(extra or {}),
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        for name, data in parts.items(): archive.writestr(name, data)
    return buffer.getvalue()


@unittest.skipIf(os.name == 'nt', 'Unix fake executable; native Windows rendering requires separate acceptance')
class OfficeRenderRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.font = self.root / 'fixture.ttf'
        self.font.write_bytes(b'\x00\x01\x00\x00font-identity-only')
        self.binary = self.root / 'fake-soffice'
        self.binary.write_text('#!' + sys.executable + '\n' + '''import sys,pathlib,os,json
if '--version' in sys.argv:
    print('LibreOffice 99.0 rendering-fixture');raise SystemExit(0)
assert 'AWS_ACCESS_KEY_ID' not in os.environ
assert pathlib.Path(os.environ['FONTCONFIG_FILE']).is_file()
fonts=pathlib.Path(os.environ['SAL_FONTPATH_PRIVATE'])
assert len(list(fonts.glob('*.ttf')))==1
options=sys.argv[sys.argv.index('--convert-to')+1]
assert options.startswith('pdf:impress_pdf_Export:')
assert json.loads(options.split(':',2)[2])['ExportNotesPages']['value']=='false'
source=pathlib.Path(sys.argv[-1]);assert source.name=='presentation.pptx'
target=pathlib.Path(sys.argv[sys.argv.index('--outdir')+1])/'presentation.pdf'
target.write_bytes(b'%PDF-1.4\\nfixture-envelope-only\\n%%EOF\\n')
''', encoding='utf-8')
        self.binary.chmod(0o755)
        self.office = create_office_lock(self.binary)
        self.render = create_office_render_lock(self.office, [self.font])
        self.source = self.root / 'annual.pptx'
        self.source.write_bytes(presentation_bytes())

    def test_byte_identical_copy_frozen_fonts_filter_and_immutable_outputs(self):
        original = self.source.read_bytes()
        with patch.dict(os.environ, {'AWS_ACCESS_KEY_ID': 'must-not-be-inherited'}):
            result = render_pptx_pdf(self.source, self.render, self.root / 'derived')
        self.assertEqual(self.source.read_bytes(), original)
        self.assertEqual(result['audit']['source_sha256'], hashlib.sha256(original).hexdigest())
        self.assertEqual(result['audit']['render_lock_sha256'], office_render_lock_digest(self.render))
        self.assertEqual(result['audit']['font_assets'], [{'sha256': self.render['fonts'][0]['sha256'], 'size': self.font.stat().st_size}])
        self.assertEqual(result['audit']['source_slide_count'], 1)
        with self.assertRaisesRegex(OfficeRuntimeError, 'OFFICE_OUTPUT_EXISTS'):
            render_pptx_pdf(self.source, self.render, self.root / 'derived')

    def test_font_drift_missing_font_and_archived_schema_validation(self):
        self.font.write_bytes(b'changed')
        with self.assertRaisesRegex(OfficeRuntimeError, 'OFFICE_RENDER_FONT_DRIFT'):
            render_pptx_pdf(self.source, self.render, self.root / 'font-drift')
        self.font.unlink()
        with self.assertRaisesRegex(OfficeRuntimeError, 'OFFICE_RENDER_FONT_UNAVAILABLE'):
            validate_office_render_lock(self.render)
        self.assertEqual(validate_office_render_lock(self.render, require_files=False), self.binary.resolve())
        bad = json.loads(json.dumps(self.render));bad['fonts'][0]['sha256'] = 'invalid'
        with self.assertRaisesRegex(OfficeRuntimeError, 'OFFICE_RENDER_LOCK_INVALID'):
            validate_office_render_lock(bad, require_files=False)
        with self.assertRaisesRegex(OfficeRuntimeError, 'OFFICE_RENDER_LOCK_INVALID'):
            create_office_render_lock(self.office, [])

    def test_unsupported_active_external_and_escaping_relationships_are_explicit(self):
        variants = [({'ppt/vbaProject.bin': b'fake'}, 'ACTIVE_CONTENT'),
                    ({'ppt/embeddings/oleObject.bin': b'fake'}, 'ACTIVE_CONTENT'),
                    ({'ppt/slides/_rels/slide1.xml.rels': f'<Relationships><Relationship Id="x" Type="{R}/image" TargetMode="External" Target="https://example.invalid/i.png"/></Relationships>'}, 'EXTERNAL_DATA'),
                    ({'ppt/_rels/presentation.xml.rels': f'<Relationships><Relationship Id="s1" Type="{R}/slide" Target="../../outside.xml"/></Relationships>'}, 'INPUT_INVALID')]
        for extra, code in variants:
            with self.subTest(code=code), self.assertRaisesRegex(OfficeRuntimeError, code):
                _inspect_render_package(presentation_bytes(extra))

    def test_frozen_font_directory_detects_added_fallback_fonts(self):
        directory = self.root / 'engine-fonts';directory.mkdir()
        (directory / 'first.ttf').write_bytes(b'font-one')
        lock = create_office_render_lock(self.office, [self.font], font_directories=[directory])
        self.assertEqual(len(lock['fonts']), 2)
        (directory / 'new-fallback.otf').write_bytes(b'font-two')
        with self.assertRaisesRegex(OfficeRuntimeError, 'OFFICE_RENDER_FONT_DRIFT'):
            validate_office_render_lock(lock)
        self.assertEqual(validate_office_render_lock(lock, require_files=False), self.binary.resolve())

    def test_embedded_workbook_is_validated_but_its_cache_is_not_rewritten(self):
        data = presentation_bytes({'ppt/embeddings/book.xlsx': workbook_bytes()})
        self.assertEqual(_inspect_render_package(data)['embedded_xlsx_validated'], 1)
        self.source.write_bytes(data)
        render_pptx_pdf(self.source, self.render, self.root / 'embedded')
        self.assertEqual(self.source.read_bytes(), data)

    def test_failed_converter_timeout_and_source_drift_do_not_publish_a_pdf(self):
        real_run = subprocess.run
        with patch('src.wildclawbench_grading_core.office_runtime.subprocess.run', return_value=subprocess.CompletedProcess([], 1, b'', b'failure')):
            with self.assertRaisesRegex(OfficeRuntimeError, 'OFFICE_RENDER_FAILED'):
                render_pptx_pdf(self.source, self.render, self.root / 'failed')
        with patch('src.wildclawbench_grading_core.office_runtime.subprocess.run', side_effect=subprocess.TimeoutExpired([], 1)):
            with self.assertRaisesRegex(OfficeRuntimeError, 'OFFICE_RENDER_TIMEOUT'):
                render_pptx_pdf(self.source, self.render, self.root / 'timeout')
        def drift(*args, **kwargs):
            result = real_run(*args, **kwargs)
            self.source.write_bytes(self.source.read_bytes() + b'changed')
            return result
        with patch('src.wildclawbench_grading_core.office_runtime.subprocess.run', side_effect=drift):
            with self.assertRaisesRegex(OfficeRuntimeError, 'OFFICE_SOURCE_DRIFT'):
                render_pptx_pdf(self.source, self.render, self.root / 'drift')
        for name in ('failed', 'timeout', 'drift'):
            self.assertFalse((self.root / name / 'rendered.pdf').exists())

    def make_attempt(self, name, *, rule=None, include_render=True):
        helper = (ROOT / 'src/wildclawbench_grading_core/office_runtime.py').read_bytes()
        checks = rule or '''def grade(**kwargs):
    from pathlib import Path
    import os,json,runpy
    root=Path(kwargs['workspace_path'])
    lock=json.loads(Path(os.environ['GENERAL_E2E_OFFICE_RENDER_LOCK']).read_text())
    result=runpy.run_path(str(root/'gt/office_runtime.py'))['render_pptx_pdf'](root/'annual.pptx',lock,Path(os.environ['GENERAL_E2E_RULE_EVIDENCE_DIR'])/'presentation')
    score=float(Path(result['path']).is_file())
    return {'rendering':score,'overall_score':score}
'''
        fixture = Fixture(self.root / name, rule=checks, scoring_runtime={'office': True, 'office_render': True}, extra_gt_files={'office_runtime.py': helper})
        (fixture.candidate / 'annual.pptx').write_bytes(self.source.read_bytes())
        entries, digest = RUNTIME._inventory_tree(fixture.candidate)
        artifact = fixture.candidate.parent / 'candidate-artifact.json'
        value = json.loads(artifact.read_text());value.update(entries=entries, expected_sha256=digest);artifact.write_text(json.dumps(value))
        value = json.loads(fixture.execution_record.read_text());value['candidate']['frozen_sha256'] = digest;fixture.execution_record.write_text(json.dumps(value))
        base = self.root / (name + '-office.json');base.write_text(json.dumps(self.office))
        combined = self.root / (name + '-runtime.json')
        if include_render:
            RUNTIME.bootstrap_office_render_runtime(base, [self.font], combined, LOCK_PATH)
        else:
            value = json.loads(LOCK_PATH.read_text());value['office_runtime'] = self.office;combined.write_text(json.dumps(value))
        prepared = RUNTIME.prepare_attempt(unit_root=fixture.unit_root, execution_record_path=fixture.execution_record, scoring_package=fixture.scoring_package,
            task_id=fixture.task_id, scoring_attempt_id=name, output_root=fixture.output_root, runtime_lock_path=combined)
        return Path(prepared['attempt_root'])

    def test_missing_render_lock_blocks_before_worker_and_missing_delivery_can_score(self):
        attempt = self.make_attempt('missing-lock', include_render=False)
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError, 'OFFICE_RENDER_RUNTIME_REQUIRED'):
            RUNTIME.run_rules_attempt(attempt_root=attempt, runtime_python=Path(sys.executable), timeout_seconds=10)
        self.assertFalse((attempt / 'rule-component.json').exists())
        other = self.make_attempt('missing-delivery', rule="def grade(**kwargs):\n    return {'rendering':0.0,'overall_score':0.0}\n")
        RUNTIME.run_rules_attempt(attempt_root=other, runtime_python=Path(sys.executable), timeout_seconds=10)
        RUNTIME.prepare_semantics_attempt(attempt_root=other)
        self.assertEqual(RUNTIME.finalize_score_attempt(attempt_root=other)['score']['result']['total_score'], 0.0)

    def test_worker_archive_and_semantic_catalog_preserve_bound_pdf_and_font_lock(self):
        attempt = self.make_attempt('render-worker')
        result = RUNTIME.run_rules_attempt(attempt_root=attempt, runtime_python=Path(sys.executable), timeout_seconds=30)
        self.assertEqual(result['rule_component']['score'], 1.0)
        references, _ = RUNTIME._semantic_reference_inputs(attempt, json.loads((attempt / 'attempt-manifest.json').read_text()), [])
        derived = {row['path'] for row in references if row['type'] == 'rule_derived_artifact'}
        self.assertTrue({'worker/office-render-runtime.json', 'worker/derived/presentation/rendered.pdf', 'worker/derived/presentation/render-audit.json'} <= derived)
        RUNTIME.prepare_semantics_attempt(attempt_root=attempt)
        RUNTIME.finalize_score_attempt(attempt_root=attempt)
        self.font.unlink();self.binary.unlink();shutil.rmtree(attempt / 'runtime')
        self.assertTrue(RUNTIME.verify_score_attempt(attempt, archived=True)['score_valid'])
        pdf = attempt / 'worker/derived/presentation/rendered.pdf'
        pdf.write_bytes(b'tampered')
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError, 'OFFICE_DERIVED_ARTIFACT_DRIFT'):
            RUNTIME.verify_score_attempt(attempt, archived=True)

    def test_unrelated_source_and_changed_export_filter_cannot_be_reindexed_as_valid(self):
        attempt = self.make_attempt('receipt-binding')
        RUNTIME.run_rules_attempt(attempt_root=attempt, runtime_python=Path(sys.executable), timeout_seconds=30)
        receipt_path = attempt / 'worker/derived/presentation/render-audit.json'
        original_receipt = receipt_path.read_bytes()
        audit_path = attempt / 'rule-audit.json'
        original_audit = audit_path.read_bytes()
        for key, value in [('source_sha256', '0' * 64), ('export_filter', {}), ('font_assets', [])]:
            with self.subTest(key=key):
                receipt = json.loads(original_receipt);receipt[key] = value;receipt_path.write_text(json.dumps(receipt))
                audit = json.loads(original_audit)
                row = next(row for row in audit['derived_artifacts'] if row['path'].endswith('/render-audit.json'))
                row.update(sha256=hashlib.sha256(receipt_path.read_bytes()).hexdigest(), size=receipt_path.stat().st_size)
                audit_path.write_text(json.dumps(audit))
                with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError, 'OFFICE_RENDER_AUDIT_INVALID'):
                    RUNTIME._verify_office_rule_evidence(attempt, required=True, render_required=True)


if __name__ == '__main__':
    unittest.main()
