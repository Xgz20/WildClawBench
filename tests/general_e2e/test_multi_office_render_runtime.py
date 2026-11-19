"""Shared Word/PPTX lock protocol. Fake PDF envelopes do not prove appearance."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

from src.wildclawbench_grading_core.office_runtime import (
    DOCX_RENDER_FILTER,DOCX_RENDER_PROFILE,RENDER_FILTER,RENDER_PROFILE,RENDER_LOCK_SCHEMA,
    MULTI_RENDER_LOCK_SCHEMA,MULTI_RENDER_PROFILE,OfficeRuntimeError,create_office_lock,
    create_office_render_lock,office_render_lock_digest,office_render_lock_formats,
    render_docx_pdf,render_pptx_pdf,validate_office_render_lock,
)
from tests.general_e2e.test_docx_render_runtime import document_bytes
from tests.general_e2e.test_office_render_runtime import presentation_bytes
from tests.general_e2e.test_local_scoring_runtime import Fixture,LOCK_PATH,RUNTIME

ROOT=Path(__file__).resolve().parents[2]

@unittest.skipIf(os.name=='nt','Unix fake converter; real native acceptance remains separate')
class MultiOfficeRenderRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.font=self.root/'fixture.ttf';self.font.write_bytes(b'font-identity-only')
        self.binary=self.root/'fake-soffice'
        self.binary.write_text('#!'+sys.executable+'\n'+'''import sys,pathlib,os,json
if '--version' in sys.argv:print('LibreOffice 99.0 dual-protocol-fixture');raise SystemExit(0)
assert 'AWS_ACCESS_KEY_ID' not in os.environ
assert pathlib.Path(os.environ['FONTCONFIG_FILE']).is_file()
source=pathlib.Path(sys.argv[-1]);export=sys.argv[sys.argv.index('--convert-to')+1]
if source.suffix=='.docx':
    assert export.startswith('pdf:writer_pdf_Export:')
    assert json.loads(export.split(':',2)[2])['ExportFormFields']['value']=='false'
else:
    assert source.suffix=='.pptx' and export.startswith('pdf:impress_pdf_Export:')
    assert json.loads(export.split(':',2)[2])['ExportHiddenSlides']['value']=='true'
target=pathlib.Path(sys.argv[sys.argv.index('--outdir')+1])/(source.stem+'.pdf')
target.write_bytes(b'%PDF-1.4\\nprotocol-only\\n%%EOF\\n')
''');self.binary.chmod(0o755)
        self.office=create_office_lock(self.binary)
        self.both=create_office_render_lock(self.office,[self.font],document_format='both')
        self.word=self.root/'report.docx';self.word.write_bytes(document_bytes())
        self.slides=self.root/'deck.pptx';self.slides.write_bytes(presentation_bytes())

    def test_explicit_v2_shared_inventory_and_legacy_defaults(self):
        self.assertEqual(self.both['schema_version'],MULTI_RENDER_LOCK_SCHEMA)
        self.assertEqual(self.both['profile'],MULTI_RENDER_PROFILE)
        self.assertEqual(len(self.both['fonts']),1)
        self.assertEqual(office_render_lock_formats(self.both),('docx','pptx'))
        for fmt in ['docx','pptx']:
            legacy=create_office_render_lock(self.office,[self.font],document_format=fmt)
            self.assertEqual(legacy['schema_version'],RENDER_LOCK_SCHEMA)
            self.assertEqual(office_render_lock_formats(legacy),(fmt,))
        self.assertEqual(office_render_lock_formats(create_office_render_lock(self.office,[self.font])),('pptx',))

    def test_cross_schema_profiles_and_unknown_formats_cannot_widen_authority(self):
        for field,value in [('schema_version',RENDER_LOCK_SCHEMA),('profile',DOCX_RENDER_PROFILE),('profile',RENDER_PROFILE),('profile',[])]:
            with self.subTest(field=field,value=value),self.assertRaises(OfficeRuntimeError):
                validate_office_render_lock({**self.both,field:value},require_files=False)
        with self.assertRaises(OfficeRuntimeError):create_office_render_lock(self.office,[self.font],document_format='pdf')

    def test_both_receipts_bind_same_full_lock_but_distinct_filters_and_source_formats(self):
        before=[self.word.read_bytes(),self.slides.read_bytes()]
        word=render_docx_pdf(self.word,self.both,self.root/'word')
        slides=render_pptx_pdf(self.slides,self.both,self.root/'slides')
        self.assertEqual([self.word.read_bytes(),self.slides.read_bytes()],before)
        for result,profile,filters in [(word,DOCX_RENDER_PROFILE,DOCX_RENDER_FILTER),(slides,RENDER_PROFILE,RENDER_FILTER)]:
            self.assertEqual(result['audit']['profile'],profile)
            self.assertEqual(result['audit']['export_filter'],filters)
            self.assertEqual(result['audit']['render_lock_sha256'],office_render_lock_digest(self.both))
        self.assertEqual(word['audit']['source_format'],'docx')
        self.assertEqual(slides['audit']['source_slide_count'],1)

    def test_single_format_locks_still_reject_the_other_operation(self):
        for fmt,api,source in [('docx',render_pptx_pdf,self.slides),('pptx',render_docx_pdf,self.word)]:
            with self.subTest(fmt=fmt),self.assertRaisesRegex(OfficeRuntimeError,'OFFICE_RENDER_PROFILE_MISMATCH'):
                api(source,create_office_render_lock(self.office,[self.font],document_format=fmt),self.root/fmt)

    def test_shared_font_drift_or_missing_engine_is_not_a_capability_zero(self):
        self.font.write_bytes(b'drift')
        with self.assertRaisesRegex(OfficeRuntimeError,'OFFICE_RENDER_FONT_DRIFT'):
            render_docx_pdf(self.word,self.both,self.root/'drift')
        self.font.write_bytes(b'font-identity-only');self.binary.unlink()
        with self.assertRaisesRegex(OfficeRuntimeError,'OFFICE_EXECUTABLE_UNAVAILABLE'):
            validate_office_render_lock(self.both)
        validate_office_render_lock(self.both,require_files=False)
        self.assertFalse((self.root/'drift/rendered.pdf').exists())

    def attempt(self,name,*,fmt='both',legacy_helper=None,one_format=None):
        helper=(ROOT/'src/wildclawbench_grading_core/office_runtime.py').read_bytes() if legacy_helper is None else legacy_helper
        operations="api['render_docx_pdf'](root/'report.docx',lock,derived/'word')\n    api['render_pptx_pdf'](root/'deck.pptx',lock,derived/'slides')"
        if one_format:operations=("api['render_docx_pdf'](root/'report.docx',lock,derived/'word')" if one_format=='docx' else "api['render_pptx_pdf'](root/'deck.pptx',lock,derived/'slides')")
        rule='''def grade(**kwargs):
    from pathlib import Path
    import os,json,runpy
    root=Path(kwargs['workspace_path']);api=runpy.run_path(str(root/'gt/office_runtime.py'))
    lock=json.loads(Path(os.environ['GENERAL_E2E_OFFICE_RENDER_LOCK']).read_text())
    derived=Path(os.environ['GENERAL_E2E_RULE_EVIDENCE_DIR'])
    '''+operations+'''
    return {'pair':1.0,'overall_score':1.0}
'''
        fixture=Fixture(self.root/name,rule=rule,scoring_runtime={'office':True,'office_render':True},extra_gt_files={'office_runtime.py':helper})
        shutil.copyfile(self.word,fixture.candidate/'report.docx');shutil.copyfile(self.slides,fixture.candidate/'deck.pptx')
        entries,digest=RUNTIME._inventory_tree(fixture.candidate)
        path=fixture.candidate.parent/'candidate-artifact.json';value=json.loads(path.read_text());value.update(entries=entries,expected_sha256=digest);path.write_text(json.dumps(value))
        value=json.loads(fixture.execution_record.read_text());value['candidate']['frozen_sha256']=digest;fixture.execution_record.write_text(json.dumps(value))
        office_path=self.root/(name+'-office.json');office_path.write_text(json.dumps(self.office))
        runtime=self.root/(name+'-runtime.json')
        bootstrap=RUNTIME.bootstrap_office_render_runtime(office_path,[self.font],runtime,LOCK_PATH,document_format=fmt)
        self.assertEqual(bootstrap['document_formats'],['docx','pptx'] if fmt=='both' else [fmt])
        prepared=RUNTIME.prepare_attempt(unit_root=fixture.unit_root,execution_record_path=fixture.execution_record,
            scoring_package=fixture.scoring_package,task_id=fixture.task_id,scoring_attempt_id=name,output_root=fixture.output_root,runtime_lock_path=runtime)
        return Path(prepared['attempt_root'])

    def test_managed_worker_catalog_and_archive_keep_both_sources_and_pdfs(self):
        attempt=self.attempt('both')
        result=RUNTIME.run_rules_attempt(attempt_root=attempt,runtime_python=Path(sys.executable),timeout_seconds=30)
        self.assertEqual(result['rule_component']['score'],1.)
        refs,_=RUNTIME._semantic_reference_inputs(attempt,json.loads((attempt/'attempt-manifest.json').read_text()),[])
        self.assertTrue({'worker/derived/word/rendered.pdf','worker/derived/slides/rendered.pdf'}<={v['path'] for v in refs})
        RUNTIME.prepare_semantics_attempt(attempt_root=attempt);RUNTIME.finalize_score_attempt(attempt_root=attempt)
        self.binary.unlink();self.font.unlink();shutil.rmtree(attempt/'runtime')
        self.assertTrue(RUNTIME.verify_score_attempt(attempt,archived=True)['score_valid'])

    def test_wrong_single_lock_still_fails_worker_without_score(self):
        attempt=self.attempt('wrong-single',fmt='docx')
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError,'OFFICE_RENDER_PROFILE_MISMATCH'):
            RUNTIME.run_rules_attempt(attempt_root=attempt,runtime_python=Path(sys.executable),timeout_seconds=30)
        self.assertFalse((attempt/'rule-component.json').exists());self.assertFalse((attempt/'score.json').exists())

    def test_reindexed_receipt_cannot_swap_format_filter_digest_or_source(self):
        attempt=self.attempt('binding');RUNTIME.run_rules_attempt(attempt_root=attempt,runtime_python=Path(sys.executable),timeout_seconds=30)
        index_path=attempt/'rule-audit.json';index_before=index_path.read_bytes()
        for name in ['word','slides']:
            path=attempt/f'worker/derived/{name}/render-audit.json';before=path.read_bytes()
            variants=[('profile',RENDER_PROFILE if name=='word' else DOCX_RENDER_PROFILE),('export_filter',{}),('render_lock_sha256','0'*64),('source_sha256','0'*64),('font_assets',[])]
            if name=='slides':variants.extend([('source_slide_count',999),('embedded_xlsx_validated',3)])
            for field,value in variants:
                with self.subTest(name=name,field=field):
                    self.assertIn(field,json.loads(before))
                    receipt={**json.loads(before),field:value};path.write_text(json.dumps(receipt))
                    index=json.loads(index_before);row=next(r for r in index['derived_artifacts'] if r['path']==path.relative_to(attempt).as_posix())
                    row.update(sha256=hashlib.sha256(path.read_bytes()).hexdigest(),size=path.stat().st_size);index_path.write_text(json.dumps(index))
                    with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError,'OFFICE_RENDER_AUDIT_INVALID'):
                        RUNTIME._verify_office_rule_evidence(attempt,required=True,render_required=True)
            path.write_bytes(before);index_path.write_bytes(index_before)

    def test_frozen_old_word_and_pptx_helpers_keep_v1_compatibility(self):
        for fmt,task in [('docx','general_hard_office_documents_task_010_capex_packet'),('pptx','general_hard_office_documents_task_005_annual_deck')]:
            helper=(ROOT/'workspace/general/challenge/office_documents'/task/'gt/office_runtime.py').read_bytes()
            attempt=self.attempt('legacy-'+fmt,fmt=fmt,legacy_helper=helper,one_format=fmt)
            result=RUNTIME.run_rules_attempt(attempt_root=attempt,runtime_python=Path(sys.executable),timeout_seconds=30)
            self.assertEqual(result['rule_component']['score'],1.)
            self.assertTrue(RUNTIME._verify_office_rule_evidence(attempt,required=True,render_required=True))

if __name__=='__main__':unittest.main()
