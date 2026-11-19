"""Marker replay and rooted artifact graphs; fake-engine tests are not math proof."""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

from src.wildclawbench_grading_core import (
    OfficeRuntimeError, prepare_xlsx_marker_intervention, verify_xlsx_marker_intervention,
)
from tests.general_e2e import test_counterfactual_office_evidence as variants
from tests.general_e2e import test_office_runtime as office_tests
from tests.general_e2e.test_office_runtime import workbook_bytes, RUNTIME, S
replace_part = variants.replace_part


class MarkerInterventionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'markers.xlsx'; self.source.write_bytes(workbook_bytes())

    def prepare(self, cell='B1', value=0, name='variant'):
        return prepare_xlsx_marker_intervention(self.source, [{'sheet':'Sheet1','cell':cell,'value':value}], self.root/name)

    def replace_cell(self, address, xml):
        def patch(raw):
            root = ET.fromstring(raw)
            for row in root.iter(S+'row'):
                for old in list(row):
                    if old.get('r') == address:
                        row.remove(old); row.append(ET.fromstring(xml))
            return ET.tostring(root)
        self.source.write_bytes(replace_part(self.source.read_bytes(), 'xl/worksheets/sheet1.xml', patch))

    def test_formula_override_keeps_full_before_image_and_other_cells_caches(self):
        before = self.source.read_bytes(); result = self.prepare()
        self.assertEqual(verify_xlsx_marker_intervention(self.source, result['path'], result['audit']), result['audit'])
        self.assertEqual(self.source.read_bytes(), before)
        old = result['audit']['changes'][0]['original_cell']
        self.assertIn('A1*3', old); self.assertIn('999', old)
        with zipfile.ZipFile(result['path']) as z:
            root = ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
            self.assertEqual(root.find(f".//{S}c[@r='A1']/{S}v").text, '2')
            cell = root.find(f".//{S}c[@r='B1']")
            self.assertIsNone(cell.find(S+'f')); self.assertEqual(cell.find(S+'v').text, '0')
        with self.assertRaisesRegex(OfficeRuntimeError, 'OFFICE_OUTPUT_EXISTS'):self.prepare()

    def test_binary_numeric_text_boolean_and_formula_cached_types_are_preserved(self):
        variants = [
            ('numeric', '<c r="B1"><v>1.00</v></c>', 'n', '0'),
            ('boolean', '<c r="B1" t="b"><v>1</v></c>', 'b', '0'),
            ('text', '<c r="B1" t="inlineStr"><is><t> 1 </t></is></c>', 'inlineStr', '0'),
            ('formula-no-cache', '<c r="B1"><f>A1&gt;0</f></c>', 'n', '0'),
            ('formula-stale-error', '<c r="B1" t="e"><f>A1&gt;0</f><v>#REF!</v></c>', 'n', '0'),
            ('formula-boolean', '<c r="B1" t="b"><f>A1&gt;0</f><v>0</v></c>', 'b', '0'),
            ('formula-text', '<c r="B1" t="str"><f>IF(A1,&quot;1&quot;,&quot;0&quot;)</f><v>stale</v></c>', 'inlineStr', '0'),
        ]
        for name, xml, kind, value in variants:
            with self.subTest(name=name):
                self.source.write_bytes(workbook_bytes());self.replace_cell('B1', xml.replace('<c ', '<c xmlns="'+S[1:-1]+'" '))
                result = self.prepare(name=name)
                verify_xlsx_marker_intervention(self.source, result['path'], result['audit'])
                with zipfile.ZipFile(result['path']) as z:
                    cell = ET.fromstring(z.read('xl/worksheets/sheet1.xml')).find(f".//{S}c[@r='B1']")
                    self.assertEqual(cell.get('t'), kind);self.assertIsNone(cell.find(S+'f'))
                    self.assertEqual(''.join(cell.itertext()), value)

    def test_nonbinary_missing_duplicate_or_out_of_range_edits_do_not_publish_variants(self):
        cases = [[], [{'sheet':'Sheet1','cell':'A1','value':0}], [{'sheet':'Sheet1','cell':'missing','value':0}],
                 [{'sheet':'Sheet1','cell':'B1','value':2}], [{'sheet':'Sheet1','cell':'B1','value':True}],
                 [{'sheet':'Sheet1','cell':'B1','value':'NaN'}],
                 [{'sheet':'Sheet1','cell':'B1','value':0}]*2,
                 [{'sheet':'Sheet1','cell':'B1','value':0}]*101]
        for i, edits in enumerate(cases):
            with self.subTest(edits=edits), self.assertRaises(OfficeRuntimeError):
                prepare_xlsx_marker_intervention(self.source, edits, self.root/str(i))
            self.assertFalse((self.root/str(i)/'prepared.xlsx').exists())

    def test_zero_formula_marker_is_frozen_when_another_marker_changes(self):
        self.replace_cell('A1','<c xmlns="'+S[1:-1]+'" r="A1"><v>1</v></c>')
        self.replace_cell('B1','<c xmlns="'+S[1:-1]+'" r="B1"><f>1-A1</f><v>0</v></c>')
        result=prepare_xlsx_marker_intervention(self.source,[{'sheet':'Sheet1','cell':'A1','value':0},{'sheet':'Sheet1','cell':'B1','value':0}],self.root/'both')
        verify_xlsx_marker_intervention(self.source,result['path'],result['audit'])
        with zipfile.ZipFile(result['path']) as z:
            root=ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
            self.assertEqual([n.text for n in root.iter(S+'v')],['0','0'])
            self.assertEqual(list(root.iter(S+'f')),[])

    def test_shared_string_marker_does_not_rewrite_other_string_users(self):
        self.replace_cell('B1','<c xmlns="'+S[1:-1]+'" r="B1" t="s"><v>0</v></c>')
        output=io.BytesIO()
        with zipfile.ZipFile(self.source) as incoming,zipfile.ZipFile(output,'w') as archive:
            for info in incoming.infolist():
                raw=incoming.read(info)
                if info.filename=='[Content_Types].xml':raw=raw.replace(b'</Types>',b'<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/></Types>')
                if info.filename=='xl/_rels/workbook.xml.rels':
                    root=ET.fromstring(raw);ET.SubElement(root,'{http://schemas.openxmlformats.org/package/2006/relationships}Relationship',Id='rSst',Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings',Target='sharedStrings.xml');raw=ET.tostring(root)
                archive.writestr(info,raw)
            archive.writestr('xl/sharedStrings.xml','<sst xmlns="'+S[1:-1]+'"><si><t>1</t></si></sst>')
        self.source.write_bytes(output.getvalue());result=self.prepare();verify_xlsx_marker_intervention(self.source,result['path'],result['audit'])
        with zipfile.ZipFile(self.source) as original,zipfile.ZipFile(result['path']) as prepared:
            self.assertEqual(original.read('xl/sharedStrings.xml'),prepared.read('xl/sharedStrings.xml'))
            cell=ET.fromstring(prepared.read('xl/worksheets/sheet1.xml')).find(f".//{S}c[@r='B1']")
            self.assertEqual(cell.get('t'),'inlineStr');self.assertEqual(''.join(cell.itertext()),'0')

    def test_shared_array_child_and_metadata_backed_markers_are_explicitly_unsupported(self):
        variants = [
            '<c r="B1"><f t="shared" si="0">A1&gt;0</f><v>1</v></c>',
            '<c r="B1"><f t="array" ref="B1:B2">A1&gt;0</f><v>1</v></c>',
            '<c r="B1" cm="1"><f>A1&gt;0</f><v>1</v></c>',
        ]
        for i, xml in enumerate(variants):
            with self.subTest(xml=xml):
                self.source.write_bytes(workbook_bytes());self.replace_cell('B1', xml.replace('<c ', '<c xmlns="'+S[1:-1]+'" '))
                with self.assertRaisesRegex(OfficeRuntimeError, 'OFFICE_MARKER_INTERVENTION_UNSUPPORTED'):self.prepare(name='unsupported'+str(i))
        self.source.write_bytes(workbook_bytes())
        self.replace_cell('B1', '<c xmlns="'+S[1:-1]+'" r="B1"><f t="array" ref="A1:B1">{1,1}</f><v>1</v></c>')
        self.replace_cell('A1', '<c xmlns="'+S[1:-1]+'" r="A1"><v>1</v></c>')
        with self.assertRaisesRegex(OfficeRuntimeError, 'OFFICE_MARKER_INTERVENTION_UNSUPPORTED'):self.prepare(cell='A1', name='array-child')

    def test_reindexing_cannot_hide_other_edits_or_a_false_before_image(self):
        result = self.prepare();path=Path(result['path']);before=path.read_bytes()
        for name, part, patch in [
            ('other-cell','xl/worksheets/sheet1.xml',lambda b:b.replace(b'>2<',b'>7<')),
            ('marker-value','xl/worksheets/sheet1.xml',lambda b:b.replace(b'>0<',b'>1<')),
            ('workbook','xl/workbook.xml',lambda b:b.replace(b'manual',b'auto')),
        ]:
            with self.subTest(name=name):
                path.write_bytes(replace_part(before,part,patch));receipt={**result['audit'],'prepared_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
                with self.assertRaisesRegex(OfficeRuntimeError,'OFFICE_MARKER_INTERVENTION_AUDIT_INVALID'):
                    verify_xlsx_marker_intervention(self.source,path,receipt)
        path.write_bytes(before);receipt=json.loads(json.dumps(result['audit']));receipt['changes'][0]['original_cell']='forged'
        with self.assertRaisesRegex(OfficeRuntimeError,'OFFICE_MARKER_INTERVENTION_AUDIT_INVALID'):
            verify_xlsx_marker_intervention(self.source,path,receipt)


@unittest.skipIf(os.name == 'nt', 'Unix fake engine; real Windows acceptance remains separate')
class VariantGraphTests(unittest.TestCase):
    def setUp(self):office_tests.OfficeRuntimeTests.setUp(self)
    def make_attempt(self, name):
        # Use the ordinary fixture setup but replace its rule via an optional
        # parameter, keeping the original one-step regression intact.
        rule='''def grade(**kwargs):
    from pathlib import Path
    import os,json,runpy
    root=Path(kwargs['workspace_path']);api=runpy.run_path(str(root/'gt/office_runtime.py'))
    derived=Path(os.environ['GENERAL_E2E_RULE_EVIDENCE_DIR'])
    first=api['prepare_xlsx_counterfactual'](root/'budget.xlsx',[{'sheet':'Sheet1','cell':'A1','value':1}],derived/'z-parent')
    marker=api['prepare_xlsx_marker_intervention'](first['path'],[{'sheet':'Sheet1','cell':'B1','value':0}],derived/'a-marker-child')
    last=api['prepare_xlsx_counterfactual'](marker['path'],[{'sheet':'Sheet1','cell':'A1','value':0}],derived/'b-grandchild')
    lock=json.loads(Path(os.environ['GENERAL_E2E_OFFICE_LOCK']).read_text())
    api['recalculate_xlsx'](last['path'],lock,derived/'calculated')
    return {'protocol':1.0,'overall_score':1.0}
'''
        return variants.CounterfactualEvidenceChainTests.make_attempt(self,name,rule=rule)

    def test_rooted_mixed_chain_accepts_child_first_index_and_archives_without_engine(self):
        attempt=self.make_attempt('mixed-chain');audit_path=attempt/'rule-audit.json';audit=json.loads(audit_path.read_text());audit['derived_artifacts'].reverse();audit_path.write_text(json.dumps(audit))
        self.assertTrue(RUNTIME._verify_office_rule_evidence(attempt,required=True))
        RUNTIME.prepare_semantics_attempt(attempt_root=attempt);RUNTIME.finalize_score_attempt(attempt_root=attempt)
        self.binary.unlink();shutil.rmtree(attempt/'runtime')
        self.assertTrue(RUNTIME.verify_score_attempt(attempt,archived=True)['score_valid'])

    def test_unrooted_cycle_missing_receipt_and_false_formula_history_are_rejected(self):
        attempt=self.make_attempt('bad-chain');audit_path=attempt/'rule-audit.json';initial=audit_path.read_bytes()
        parent=attempt/'worker/derived/z-parent/counterfactual-audit.json';marker=attempt/'worker/derived/a-marker-child/marker-intervention-audit.json'
        parent_raw=parent.read_bytes();marker_raw=marker.read_bytes()
        def reindex():
            audit=json.loads(initial)
            for row in audit['derived_artifacts']:
                p=attempt/row['path'];row.update(sha256=hashlib.sha256(p.read_bytes()).hexdigest(),size=p.stat().st_size)
            audit_path.write_text(json.dumps(audit))
        for name, source_hash in [('unrooted','0'*64),('cycle',json.loads(marker_raw)['prepared_sha256'])]:
            with self.subTest(name=name):
                receipt=json.loads(parent_raw);receipt['source_sha256']=source_hash;parent.write_text(json.dumps(receipt));reindex()
                with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError,'OFFICE_COUNTERFACTUAL_AUDIT_INVALID|OFFICE_MARKER_INTERVENTION_AUDIT_INVALID'):
                    RUNTIME._verify_office_rule_evidence(attempt,required=True)
        parent.write_bytes(parent_raw);receipt=json.loads(marker_raw);receipt['changes'][0]['original_cell']='fake';marker.write_text(json.dumps(receipt));reindex()
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError,'OFFICE_MARKER_INTERVENTION_AUDIT_INVALID'):
            RUNTIME._verify_office_rule_evidence(attempt,required=True)
        marker.write_bytes(marker_raw);parent.unlink();audit=json.loads(initial);audit['derived_artifacts']=[r for r in audit['derived_artifacts'] if r['path']!='worker/derived/z-parent/counterfactual-audit.json'];audit_path.write_text(json.dumps(audit))
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError,'OFFICE_COUNTERFACTUAL_AUDIT_INVALID|OFFICE_MARKER_INTERVENTION_AUDIT_INVALID'):
            RUNTIME._verify_office_rule_evidence(attempt,required=True)

if __name__ == '__main__':unittest.main()
