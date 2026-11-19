"""Numeric intermediate provenance; fake engines only test the protocol."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import shutil
import unittest
import xml.etree.ElementTree as ET
import zipfile

from src.wildclawbench_grading_core import (
    OfficeRuntimeError, prepare_xlsx_numeric_intervention, verify_xlsx_numeric_intervention,
    prepare_xlsx_counterfactual, verify_xlsx_marker_intervention,
)
from tests.general_e2e import test_counterfactual_office_evidence as variants
from tests.general_e2e import test_marker_intervention_office_evidence as markers
from tests.general_e2e import test_office_runtime as fixtures
from tests.general_e2e.test_office_runtime import S, RUNTIME


class NumericInterventionTests(unittest.TestCase):
    def setUp(self):markers.MarkerInterventionTests.setUp(self)
    def replace(self, xml):
        markers.MarkerInterventionTests.replace_cell(self, 'B1', xml.replace('<c ', '<c xmlns="'+S[1:-1]+'" '))
    def prepare(self, value='-1234.50', name='numeric'):
        return prepare_xlsx_numeric_intervention(self.source,[{'sheet':'Sheet1','cell':'B1','value':value}],self.root/name)

    def test_formula_override_tracks_original_and_never_broadens_legacy_numeric_api(self):
        before=self.source.read_bytes();r=self.prepare();verify_xlsx_numeric_intervention(self.source,r['path'],r['audit'])
        self.assertEqual(self.source.read_bytes(),before);self.assertIn('A1*3',r['audit']['changes'][0]['original_cell']);self.assertIn('999',r['audit']['changes'][0]['original_cell'])
        with zipfile.ZipFile(r['path']) as z:
            sheet=ET.fromstring(z.read('xl/worksheets/sheet1.xml'));cell=sheet.find(f".//{S}c[@r='B1']")
            self.assertEqual(cell.get('t'),'n');self.assertIsNone(cell.find(S+'f'));self.assertEqual(cell.find(S+'v').text,'-1234.5');self.assertEqual(sheet.find(f".//{S}c[@r='A1']/{S}v").text,'2')
        with self.assertRaisesRegex(OfficeRuntimeError,'OFFICE_COUNTERFACTUAL_TARGET_INVALID'):
            prepare_xlsx_counterfactual(self.source,[{'sheet':'Sheet1','cell':'B1','value':3.75}],self.root/'legacy')
        with self.assertRaisesRegex(OfficeRuntimeError,'OFFICE_MARKER_INTERVENTION_AUDIT_INVALID'):
            verify_xlsx_marker_intervention(self.source,r['path'],r['audit'])
        with self.assertRaisesRegex(OfficeRuntimeError,'OFFICE_OUTPUT_EXISTS'):self.prepare()

    def test_scalar_formula_cache_types_and_numeric_literals_have_same_numeric_override(self):
        cells=['<c r="B1"><f>A1*3</f></c>','<c r="B1" t="e"><f>A1*3</f><v>#REF!</v></c>',
               '<c r="B1" t="str"><f>TEXT(A1*3,"0")</f><v>stale</v></c>',
               '<c r="B1"><v>999.001</v></c>','<c r="B1" t="inlineStr"><is><t>999.001</t></is></c>',
               '<c r="B1" t="b"><v>1</v></c>']
        for i,xml in enumerate(cells):
            with self.subTest(xml=xml):
                self.source.write_bytes(fixtures.workbook_bytes());self.replace(xml);r=self.prepare('3.75',str(i));verify_xlsx_numeric_intervention(self.source,r['path'],r['audit'])
                with zipfile.ZipFile(r['path']) as z:
                    cell=ET.fromstring(z.read('xl/worksheets/sheet1.xml')).find(f".//{S}c[@r='B1']");self.assertEqual(cell.get('t'),'n');self.assertEqual(cell.find(S+'v').text,'3.75')

    def test_invalid_values_duplicate_cells_and_excess_edits_never_publish(self):
        edits=[[],[{'sheet':'Sheet1','cell':'B1','value':'NaN'}],[{'sheet':'Sheet1','cell':'B1','value':True}],
               [{'sheet':'Sheet1','cell':'B1','value':'1e16'}],[{'sheet':'Sheet1','cell':'B1','value':'1e-16'}],
               [{'sheet':'Sheet1','cell':'B1','value':2}]*2,[{'sheet':'Sheet1','cell':'B1','value':2}]*101]
        for i,changes in enumerate(edits):
            with self.subTest(changes=changes),self.assertRaisesRegex(OfficeRuntimeError,'OFFICE_NUMERIC_INTERVENTION_CHANGE_INVALID'):
                prepare_xlsx_numeric_intervention(self.source,changes,self.root/('invalid'+str(i)))
            self.assertFalse((self.root/('invalid'+str(i))/'prepared.xlsx').exists())
        self.replace('<c r="B1" t="inlineStr"><is><t>missing</t></is></c>')
        with self.assertRaisesRegex(OfficeRuntimeError,'OFFICE_NUMERIC_INTERVENTION_TARGET_INVALID'):self.prepare()

    def test_shared_array_metadata_and_unaddressable_formula_ranges_are_explicitly_unsupported(self):
        cells=['<c r="B1"><f t="shared" si="0">A1*3</f><v>6</v></c>',
               '<c r="B1"><f t="array" ref="A1:B1">{2,6}</f><v>6</v></c>',
               '<c r="B1" cm="1"><f>A1*3</f><v>6</v></c>']
        for i,xml in enumerate(cells):
            self.source.write_bytes(fixtures.workbook_bytes());self.replace(xml)
            with self.subTest(xml=xml),self.assertRaisesRegex(OfficeRuntimeError,'OFFICE_NUMERIC_INTERVENTION_UNSUPPORTED'):self.prepare(name=str(i))
        self.source.write_bytes(fixtures.workbook_bytes());self.replace('<c r="B1"><f t="array" ref="A1:B1">{2,6}</f><v>6</v></c>')
        with self.assertRaisesRegex(OfficeRuntimeError,'OFFICE_NUMERIC_INTERVENTION_UNSUPPORTED'):
            prepare_xlsx_numeric_intervention(self.source,[{'sheet':'Sheet1','cell':'A1','value':4}],self.root/'array-child')

    def test_reindexed_before_image_other_cell_or_cache_tampering_remains_rejected(self):
        r=self.prepare();p=Path(r['path']);before=p.read_bytes()
        for name,part,patch in [('other-cell','xl/worksheets/sheet1.xml',lambda b:b.replace(b'>2<',b'>7<')),
                                ('value','xl/worksheets/sheet1.xml',lambda b:b.replace(b'-1234.5',b'3.75')),
                                ('workbook','xl/workbook.xml',lambda b:b.replace(b'manual',b'auto'))]:
            with self.subTest(name=name):
                p.write_bytes(variants.replace_part(before,part,patch));audit={**r['audit'],'prepared_sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
                with self.assertRaisesRegex(OfficeRuntimeError,'OFFICE_NUMERIC_INTERVENTION_AUDIT_INVALID'):verify_xlsx_numeric_intervention(self.source,p,audit)
        p.write_bytes(before)
        for key,value in [('original_cell','forged formula history'),('value','3.75')]:
            audit=json.loads(json.dumps(r['audit']));audit['changes'][0][key]=value
            with self.subTest(key=key),self.assertRaisesRegex(OfficeRuntimeError,'OFFICE_NUMERIC_INTERVENTION_AUDIT_INVALID'):verify_xlsx_numeric_intervention(self.source,p,audit)


@unittest.skipIf(os.name=='nt','Unix fake engine; real platform math is checked separately')
class NumericVariantGraphTests(unittest.TestCase):
    def setUp(self):fixtures.OfficeRuntimeTests.setUp(self)
    def make_attempt(self,name):
        rule='''def grade(**kwargs):
    from pathlib import Path
    import os,json,runpy
    root=Path(kwargs['workspace_path']);api=runpy.run_path(str(root/'gt/office_runtime.py'));d=Path(os.environ['GENERAL_E2E_RULE_EVIDENCE_DIR'])
    first=api['prepare_xlsx_numeric_intervention'](root/'budget.xlsx',[{'sheet':'Sheet1','cell':'B1','value':3.75}],d/'z-numeric')
    second=api['prepare_xlsx_counterfactual'](first['path'],[{'sheet':'Sheet1','cell':'A1','value':1}],d/'b-input')
    third=api['prepare_xlsx_marker_intervention'](second['path'],[{'sheet':'Sheet1','cell':'A1','value':0}],d/'c-marker')
    last=api['prepare_xlsx_numeric_intervention'](third['path'],[{'sheet':'Sheet1','cell':'B1','value':-2.5}],d/'a-numeric-child')
    api['recalculate_xlsx'](last['path'],json.loads(Path(os.environ['GENERAL_E2E_OFFICE_LOCK']).read_text()),d/'calculated')
    return {'protocol':1.,'overall_score':1.}
'''
        return variants.CounterfactualEvidenceChainTests.make_attempt(self,name,rule=rule)

    def test_all_three_profiles_accept_rooted_mixed_chain_and_archive_without_engine(self):
        attempt=self.make_attempt('numeric-chain');p=attempt/'rule-audit.json';audit=json.loads(p.read_text());audit['derived_artifacts'].reverse();p.write_text(json.dumps(audit))
        normal=RUNTIME._verify_office_rule_evidence(attempt,required=True);archived=RUNTIME._verify_office_rule_evidence(attempt,required=True,archived=True);self.assertEqual(normal,archived)
        RUNTIME.prepare_semantics_attempt(attempt_root=attempt);RUNTIME.finalize_score_attempt(attempt_root=attempt);self.binary.unlink();shutil.rmtree(attempt/'runtime');self.assertTrue(RUNTIME.verify_score_attempt(attempt,archived=True)['score_valid'])

    def test_false_numeric_history_or_unrooted_parent_cannot_be_authorized_by_reindexing(self):
        attempt=self.make_attempt('invalid-numeric');index=attempt/'rule-audit.json';original=index.read_bytes();receipt=attempt/'worker/derived/z-numeric/numeric-intervention-audit.json';raw=receipt.read_bytes()
        for field in ['source','before']:
            audit=json.loads(raw)
            if field=='source':audit['source_sha256']='0'*64
            else:audit['changes'][0]['original_cell']='forged'
            receipt.write_text(json.dumps(audit));catalog=json.loads(original)
            for row in catalog['derived_artifacts']:
                file=attempt/row['path'];row.update(sha256=hashlib.sha256(file.read_bytes()).hexdigest(),size=file.stat().st_size)
            index.write_text(json.dumps(catalog))
            with self.subTest(field=field),self.assertRaisesRegex(RUNTIME.ScoringRuntimeError,'OFFICE_NUMERIC_INTERVENTION_AUDIT_INVALID'):RUNTIME._verify_office_rule_evidence(attempt,required=True)
        receipt.write_bytes(raw)


if __name__=='__main__':unittest.main()
