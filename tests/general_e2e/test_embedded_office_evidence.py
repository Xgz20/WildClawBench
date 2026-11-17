"""PPTX -> extracted XLSX -> recalculated XLSX provenance, not visual scoring."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import unittest

from src.wildclawbench_grading_core.office_runtime import (
    OfficeRuntimeError, extract_embedded_xlsx, read_embedded_xlsx, recalculate_xlsx,
)
from tests.general_e2e import test_office_runtime as office_tests
from tests.general_e2e.test_office_runtime import workbook_bytes, ROOT, Fixture, LOCK_PATH, RUNTIME
from tests.general_e2e.test_office_render_runtime import presentation_bytes


@unittest.skipIf(os.name == 'nt', 'Unix fake executable; Windows needs native acceptance')
class EmbeddedOfficeEvidenceTests(unittest.TestCase):
    def setUp(self):
        office_tests.OfficeRuntimeTests.setUp(self)
        self.part = 'ppt/embeddings/source.xlsx'
        self.source = self.root / 'report.pptx'
        self.source.write_bytes(presentation_bytes({self.part: workbook_bytes()}))

    def test_extract_keeps_cache_and_source_bytes_before_recalculation(self):
        original = self.source.read_bytes()
        extracted = extract_embedded_xlsx(self.source, self.part, self.root / 'extracted')
        self.assertEqual(Path(extracted['path']).read_bytes(), workbook_bytes())
        self.assertEqual(read_embedded_xlsx(self.source, self.part), workbook_bytes())
        result = recalculate_xlsx(extracted['path'], self.lock, self.root / 'calculated')
        self.assertEqual(result['audit']['formula_caches_cleared'], 1)
        self.assertEqual(result['audit']['source_sha256'], extracted['audit']['embedded_sha256'])
        self.assertEqual(self.source.read_bytes(), original)
        with self.assertRaisesRegex(OfficeRuntimeError, 'OFFICE_OUTPUT_EXISTS'):
            extract_embedded_xlsx(self.source, self.part, self.root / 'extracted')
        for part in ('../outside.xlsx', 'ppt/embeddings/missing.xlsx', 'ppt/../source.xlsx'):
            with self.subTest(part=part), self.assertRaisesRegex(OfficeRuntimeError, 'OFFICE_EMBEDDED_PART_INVALID'):
                read_embedded_xlsx(self.source, part)

    def test_optional_pdf_imports_require_actual_runtime_declarations(self):
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError,'RUNTIME_DEPENDENCY_UNDECLARED'):
            RUNTIME.probe_runtime(runtime_python=Path(sys.executable),runtime_lock_path=LOCK_PATH,required_import_roots=['pdfplumber'],browser_smoke=False)

    def test_nonportable_prefixed_manifest_is_not_an_engine_failure(self):
        from src.wildclawbench_grading_core.office_runtime import _validate_content_types
        uri='http://schemas.openxmlformats.org/package/2006/content-types'
        with self.assertRaisesRegex(OfficeRuntimeError,'OFFICE_INPUT_INVALID'):
            _validate_content_types(f'<ct:Types xmlns:ct="{uri}"/>'.encode())
        _validate_content_types(f'<?xml version="1.0" encoding="utf-16"?><Types xmlns="{uri}"/>'.encode('utf-16'))

    def make_attempt(self, name):
        rule = '''def grade(**kwargs):
    from pathlib import Path
    import os,json,runpy
    root=Path(kwargs['workspace_path'])
    api=runpy.run_path(str(root/'gt/office_runtime.py'))
    derived=Path(os.environ['GENERAL_E2E_RULE_EVIDENCE_DIR'])
    original=api['extract_embedded_xlsx'](root/'report.pptx','ppt/embeddings/source.xlsx',derived/'extract')
    lock=json.loads(Path(os.environ['GENERAL_E2E_OFFICE_LOCK']).read_text())
    result=api['recalculate_xlsx'](original['path'],lock,derived/'calculation')
    return {'embedded':float(result['audit']['formula_caches_cleared']==1),'overall_score':float(result['audit']['formula_caches_cleared']==1)}
'''
        fixture = Fixture(self.root / name, rule=rule, scoring_runtime={'office': True},
            extra_gt_files={'office_runtime.py': (ROOT / 'src/wildclawbench_grading_core/office_runtime.py').read_bytes()})
        (fixture.candidate / 'report.pptx').write_bytes(self.source.read_bytes())
        entries,digest = RUNTIME._inventory_tree(fixture.candidate)
        path = fixture.candidate.parent / 'candidate-artifact.json'
        value = json.loads(path.read_text());value.update(entries=entries,expected_sha256=digest);path.write_text(json.dumps(value))
        value=json.loads(fixture.execution_record.read_text());value['candidate']['frozen_sha256']=digest;fixture.execution_record.write_text(json.dumps(value))
        combined=self.root/(name+'-runtime.json');value=json.loads(LOCK_PATH.read_text());value['office_runtime']=self.lock;combined.write_text(json.dumps(value))
        prepared=RUNTIME.prepare_attempt(unit_root=fixture.unit_root,execution_record_path=fixture.execution_record,scoring_package=fixture.scoring_package,
            task_id=fixture.task_id,scoring_attempt_id=name,output_root=fixture.output_root,runtime_lock_path=combined)
        attempt=Path(prepared['attempt_root'])
        result=RUNTIME.run_rules_attempt(attempt_root=attempt,runtime_python=Path(sys.executable),timeout_seconds=30)
        self.assertEqual(result['rule_component']['score'],1.0)
        return attempt

    def test_worker_semantic_catalog_and_archive_keep_full_provenance_chain(self):
        attempt=self.make_attempt('embedded-chain')
        refs,_=RUNTIME._semantic_reference_inputs(attempt,json.loads((attempt/'attempt-manifest.json').read_text()),[])
        paths={row['path'] for row in refs if row['type']=='rule_derived_artifact'}
        self.assertTrue({'worker/derived/extract/embedded.xlsx','worker/derived/extract/embedded-xlsx-audit.json',
                         'worker/derived/calculation/recalculated.xlsx','worker/derived/calculation/office-audit.json'}<=paths)
        RUNTIME.prepare_semantics_attempt(attempt_root=attempt);RUNTIME.finalize_score_attempt(attempt_root=attempt)
        self.binary.unlink();shutil.rmtree(attempt/'runtime')
        self.assertTrue(RUNTIME.verify_score_attempt(attempt,archived=True)['score_valid'])

    def test_reindexed_false_parent_part_or_missing_extraction_receipt_are_rejected(self):
        attempt=self.make_attempt('embedded-binding')
        receipt_path=attempt/'worker/derived/extract/embedded-xlsx-audit.json';audit_path=attempt/'rule-audit.json'
        before_receipt=receipt_path.read_bytes();before_audit=audit_path.read_bytes()
        for key,value in [('part','ppt/embeddings/missing.xlsx'),('source_presentation_sha256','0'*64),('embedded_sha256','0'*64)]:
            with self.subTest(key=key):
                receipt=json.loads(before_receipt);receipt[key]=value;receipt_path.write_text(json.dumps(receipt))
                audit=json.loads(before_audit);row=next(row for row in audit['derived_artifacts'] if row['path'].endswith('/embedded-xlsx-audit.json'))
                row.update(sha256=hashlib.sha256(receipt_path.read_bytes()).hexdigest(),size=receipt_path.stat().st_size);audit_path.write_text(json.dumps(audit))
                with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError,'OFFICE_EMBEDDED_AUDIT_INVALID'):
                    RUNTIME._verify_office_rule_evidence(attempt,required=True)
        receipt_path.unlink()
        audit=json.loads(before_audit);audit['derived_artifacts']=[x for x in audit['derived_artifacts'] if not x['path'].endswith('/embedded-xlsx-audit.json')]
        audit_path.write_text(json.dumps(audit))
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError,'OFFICE_RECALCULATION_AUDIT_INVALID'):
            RUNTIME._verify_office_rule_evidence(attempt,required=True)


if __name__=='__main__':unittest.main()
