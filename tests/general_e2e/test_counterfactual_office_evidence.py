"""Frozen workbook -> declared numeric-input variant -> actual recalculation evidence.

The fake engine verifies protocol behavior only; business math needs a real engine.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

from src.wildclawbench_grading_core.office_runtime import (
    OfficeRuntimeError, prepare_xlsx_counterfactual, verify_xlsx_counterfactual,
)
from tests.general_e2e import test_office_runtime as office_tests
from tests.general_e2e.test_office_runtime import workbook_bytes, ROOT, Fixture, LOCK_PATH, RUNTIME, S


def replace_part(data, part, replacement):
    result = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as incoming, zipfile.ZipFile(result, 'w') as outgoing:
        for info in incoming.infolist():
            raw = incoming.read(info)
            outgoing.writestr(info, replacement(raw) if info.filename == part else raw)
    return result.getvalue()


class NumericInputVariantTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'budget.xlsx'; self.source.write_bytes(workbook_bytes())

    def prepare(self, name='variant', value='4.12500'):
        return prepare_xlsx_counterfactual(self.source, [{'sheet':'Sheet1','cell':'A1','value':value}], self.root/name)

    def test_only_declared_input_changes_and_source_and_formula_caches_are_preserved(self):
        before = self.source.read_bytes(); result = self.prepare()
        audit = verify_xlsx_counterfactual(self.source, result['path'], result['audit'])
        self.assertEqual(self.source.read_bytes(), before)
        self.assertEqual(audit['changes'], [{'sheet':'Sheet1','cell':'A1','value':'4.125','original_value':'2'}])
        with zipfile.ZipFile(result['path']) as archive:
            node = ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
            self.assertEqual(node.find(f".//{S}c[@r='A1']/{S}v").text, '4.125')
            self.assertEqual(node.find(f".//{S}c[@r='B1']/{S}f").text, 'A1*3')
            self.assertEqual(node.find(f".//{S}c[@r='B1']/{S}v").text, '999')
        with self.assertRaisesRegex(OfficeRuntimeError, 'OFFICE_OUTPUT_EXISTS'):self.prepare()

    def test_formula_missing_text_boolean_duplicate_or_unbounded_inputs_are_rejected(self):
        cases = [
            [], [{'sheet':'Sheet1','cell':'B1','value':4}], [{'sheet':'missing','cell':'A1','value':4}],
            [{'sheet':'Sheet1','cell':'C1','value':4}], [{'sheet':'Sheet1','cell':'A1','value':True}],
            [{'sheet':'Sheet1','cell':'A1','value':'NaN'}], [{'sheet':'Sheet1','cell':'A1','value':'1e16'}],
            [{'sheet':'Sheet1','cell':'A1','value':'1e-1000000000'}],
            [{'sheet':'Sheet1','cell':'A1','value':'4'}, {'sheet':'Sheet1','cell':'A1','value':'5'}],
        ]
        for i, edits in enumerate(cases):
            with self.subTest(edits=edits), self.assertRaises(OfficeRuntimeError):
                prepare_xlsx_counterfactual(self.source, edits, self.root/str(i))
            self.assertFalse((self.root/str(i)/'prepared.xlsx').exists())

    def test_declared_values_and_formulas_cannot_be_rewritten_after_reindexing(self):
        result=self.prepare(); path=Path(result['path']); original=path.read_bytes()
        for name, replacement in [
            ('input', lambda raw:raw.replace(b'>4.125<',b'>8<')),
            ('formula', lambda raw:raw.replace(b'A1*3',b'A1*4')),
            ('cache', lambda raw:raw.replace(b'>999<',b'>6<')),
        ]:
            with self.subTest(name=name):
                path.write_bytes(replace_part(original,'xl/worksheets/sheet1.xml',replacement))
                audit={**result['audit'],'prepared_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
                with self.assertRaisesRegex(OfficeRuntimeError,'OFFICE_COUNTERFACTUAL_AUDIT_INVALID'):
                    verify_xlsx_counterfactual(self.source,path,audit)

    def test_other_part_changes_and_false_original_values_are_rejected(self):
        result=self.prepare();path=Path(result['path'])
        path.write_bytes(replace_part(path.read_bytes(),'xl/workbook.xml',lambda raw:raw.replace(b'manual',b'auto')))
        audit={**result['audit'],'prepared_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        with self.assertRaisesRegex(OfficeRuntimeError,'OFFICE_COUNTERFACTUAL_AUDIT_INVALID'):
            verify_xlsx_counterfactual(self.source,path,audit)
        result=self.prepare('second');audit=json.loads(json.dumps(result['audit']));audit['changes'][0]['original_value']='999'
        with self.assertRaisesRegex(OfficeRuntimeError,'OFFICE_COUNTERFACTUAL_AUDIT_INVALID'):
            verify_xlsx_counterfactual(self.source,result['path'],audit)


@unittest.skipIf(os.name == 'nt','Unix fake engine; real Windows acceptance is separate')
class CounterfactualEvidenceChainTests(unittest.TestCase):
    def setUp(self):office_tests.OfficeRuntimeTests.setUp(self)

    def make_attempt(self,name,rule=None):
        rule=rule or '''def grade(**kwargs):
    from pathlib import Path
    import os,json,runpy
    root=Path(kwargs['workspace_path'])
    api=runpy.run_path(str(root/'gt/office_runtime.py'))
    derived=Path(os.environ['GENERAL_E2E_RULE_EVIDENCE_DIR'])
    variant=api['prepare_xlsx_counterfactual'](root/'budget.xlsx',[{'sheet':'Sheet1','cell':'A1','value':4}],derived/'variant')
    lock=json.loads(Path(os.environ['GENERAL_E2E_OFFICE_LOCK']).read_text())
    calculated=api['recalculate_xlsx'](variant['path'],lock,derived/'calculated')
    return {'protocol':float(calculated['audit']['formula_caches_cleared']==1),'overall_score':1.0}
'''
        fixture=Fixture(self.root/name,rule=rule,scoring_runtime={'office':True},
            extra_gt_files={'office_runtime.py':(ROOT/'src/wildclawbench_grading_core/office_runtime.py').read_bytes()})
        (fixture.candidate/'budget.xlsx').write_bytes(workbook_bytes())
        entries,digest=RUNTIME._inventory_tree(fixture.candidate)
        path=fixture.candidate.parent/'candidate-artifact.json';value=json.loads(path.read_text());value.update(entries=entries,expected_sha256=digest);path.write_text(json.dumps(value))
        value=json.loads(fixture.execution_record.read_text());value['candidate']['frozen_sha256']=digest;fixture.execution_record.write_text(json.dumps(value))
        combined=self.root/(name+'-runtime.json');value=json.loads(LOCK_PATH.read_text());value['office_runtime']=self.lock;combined.write_text(json.dumps(value))
        prepared=RUNTIME.prepare_attempt(unit_root=fixture.unit_root,execution_record_path=fixture.execution_record,
            scoring_package=fixture.scoring_package,task_id=fixture.task_id,scoring_attempt_id=name,
            output_root=fixture.output_root,runtime_lock_path=combined)
        attempt=Path(prepared['attempt_root'])
        result=RUNTIME.run_rules_attempt(attempt_root=attempt,runtime_python=Path(sys.executable),timeout_seconds=30)
        self.assertEqual(result['rule_component']['score'],1.)
        return attempt

    def test_worker_catalog_and_archived_verification_keep_the_full_chain(self):
        attempt=self.make_attempt('variant-chain')
        refs,_=RUNTIME._semantic_reference_inputs(attempt,json.loads((attempt/'attempt-manifest.json').read_text()),[])
        paths={row['path'] for row in refs if row['type']=='rule_derived_artifact'}
        self.assertTrue({'worker/derived/variant/prepared.xlsx','worker/derived/variant/counterfactual-audit.json',
            'worker/derived/calculated/recalculated.xlsx','worker/derived/calculated/office-audit.json'}<=paths)
        RUNTIME.prepare_semantics_attempt(attempt_root=attempt);RUNTIME.finalize_score_attempt(attempt_root=attempt)
        self.binary.unlink();shutil.rmtree(attempt/'runtime')
        self.assertTrue(RUNTIME.verify_score_attempt(attempt,archived=True)['score_valid'])

    def test_false_parent_edits_or_missing_variant_receipt_are_rejected_after_reindexing(self):
        attempt=self.make_attempt('variant-binding')
        receipt_path=attempt/'worker/derived/variant/counterfactual-audit.json';audit_path=attempt/'rule-audit.json'
        before=receipt_path.read_bytes();index_before=audit_path.read_bytes()
        variants=[{'source_sha256':'0'*64},{'prepared_sha256':'0'*64},
            {'changes':[{'sheet':'Sheet1','cell':'A1','value':'4','original_value':'99'}]}]
        for delta in variants:
            with self.subTest(delta=delta):
                receipt={**json.loads(before),**delta};receipt_path.write_text(json.dumps(receipt))
                index=json.loads(index_before);row=next(r for r in index['derived_artifacts'] if r['path'].endswith('/counterfactual-audit.json'))
                row.update(sha256=hashlib.sha256(receipt_path.read_bytes()).hexdigest(),size=receipt_path.stat().st_size);audit_path.write_text(json.dumps(index))
                with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError,'OFFICE_COUNTERFACTUAL_AUDIT_INVALID'):
                    RUNTIME._verify_office_rule_evidence(attempt,required=True)
        receipt_path.unlink();index=json.loads(index_before)
        index['derived_artifacts']=[r for r in index['derived_artifacts'] if not r['path'].endswith('/counterfactual-audit.json')]
        audit_path.write_text(json.dumps(index))
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError,'OFFICE_RECALCULATION_AUDIT_INVALID'):
            RUNTIME._verify_office_rule_evidence(attempt,required=True)


if __name__=='__main__':unittest.main()
