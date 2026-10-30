from pathlib import Path
from io import BytesIO
import ast
import base64
import hashlib
import json
import re
import unittest
import zipfile
from xml.etree import ElementTree as ET
from eval_general_e2e.datasets.bundle import _parse_task_source, _strip_codeblock

from tests.general_e2e.test_local_scoring_runtime import RUNTIME, REPO_ROOT, SCRIPT_PATH, load_module


class DatasetRuleCorrectionTests(unittest.TestCase):
    def test_hr_row_prefix_is_equivalent_parsing_with_legacy_source_unchanged(self):
        tid='03_Data_Analysis_task_001_hr_worktime_reconciliation'
        _,sections,_=_parse_task_source(next((REPO_ROOT/'tasks/general_e2e').rglob(tid+'.md')))
        source=_strip_codeblock(sections['Automated Checks']);review=RUNTIME.rule_review
        old,old_receipt=review.effective_source(source)
        fixed,receipt=review.effective_source(source,source_row_aliases=True)
        def functions(code):
            return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(code).body if isinstance(n,ast.FunctionDef)}
        a,b=functions(old),functions(fixed)
        for name in a:
            if name!='parse_source_refs':self.assertEqual(a[name],b[name],name)
        self.assertNotIn('source_locator_profile',old_receipt)
        self.assertEqual(receipt['source_locator_profile'],review.ROW_LOCATOR_PROFILE)
        # Only the pure source-locator parser is exercised; never execute grade here.
        node=next(n for n in ast.parse(fixed).body if isinstance(n,ast.FunctionDef) and n.name=='parse_source_refs')
        scope={'re':re,'normalize_text':lambda x:str(x or '').strip()}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'<locator-fixture>','exec'),scope)
        parse=scope['parse_source_refs']
        for raw in ['员工与组织信息.xlsx#人员名册!行5','员工与组织信息.xlsx#人员名册!第5行','员工与组织信息.xlsx#人员名册!A5']:
            self.assertEqual(parse(raw),frozenset({('员工与组织信息.xlsx','人员名册',5,'')}))
        self.assertEqual(parse('月度排班计划.xlsx#生产一部8月!C7'),frozenset({('月度排班计划.xlsx','生产一部8月',7,'C')}))
        # Row-only schedule refs remain column-less, so the unchanged existence rule rejects them.
        self.assertEqual(parse('月度排班计划.xlsx#生产一部8月!行7'),frozenset({('月度排班计划.xlsx','生产一部8月',7,'')}))
        for raw in ['员工与组织信息.xlsx#人员名册!行A5','员工与组织信息.xlsx#人员名册!行5行']:
            self.assertEqual(next(iter(parse(raw)))[0],'无效定位')
        manifest={'identity':{'task_id':tid},'runtime':{'rule_review_profile':review.PROFILE}}
        self.assertEqual(RUNTIME._effective_rule_source(manifest,source)[0],old)
        manifest['runtime']['hr_source_locator_profile']=review.ROW_LOCATOR_PROFILE
        self.assertEqual(RUNTIME._effective_rule_source(manifest,source)[0],fixed)

    def test_procurement_alias_fix_preserves_all_numeric_scoring_functions(self):
        tid='02_Office_task_015_procurement_reconciliation'
        _,sections,_=_parse_task_source(next((REPO_ROOT/'tasks/general_e2e').rglob(tid+'.md')))
        source=_strip_codeblock(sections['Automated Checks'])
        effective,receipt=RUNTIME._effective_rule_source({'identity':{'task_id':tid}},source)
        def functions(code):
            return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(code).body if isinstance(n,ast.FunctionDef)}
        old,new=functions(source),functions(effective)
        for name in ['grade','population','numeric_score','summary_diagnostics','score_tool' if 'score_tool' in old else 'summary_key']:
            with self.subTest(name=name):self.assertEqual(old[name],new[name])
        self.assertIn("'id':['单号'",effective)
        self.assertEqual(receipt['correction_id'],'procurement-header-summary-aliases/v1')
        self.assertEqual(RUNTIME._effective_rule_source({'identity':{'task_id':tid}},source+'\n'),(source+'\n',None))

    def test_declared_text_diagnostic_is_not_a_numeric_checkpoint(self):
        worker = load_module('rule_worker_text_adapter_test', SCRIPT_PATH.with_name('rule_worker.py'))
        raw = {'C2': 1.0, 'overall_score': 0.75, 'evidence_status': '仅规则组，不冒充正式总分', 'diagnostics': {'checked': True}}
        policy = {'schema_version': 'wildclawbench.general-e2e-numeric-diagnostics/v1',
                  'diagnostic_keys': ['diagnostics'], 'diagnostic_text_keys': ['evidence_status']}
        before = json.loads(json.dumps(raw))
        self.assertEqual(worker.adapt_rule_result(raw, policy), {'C2': 1.0, 'overall_score': 0.75})
        self.assertEqual(raw, before)
        legacy = {k:v for k,v in policy.items() if k != 'diagnostic_text_keys'}
        self.assertIn('evidence_status', worker.adapt_rule_result(raw, legacy))
        for value in [0.5, {'status': 'complete'}]:
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'must be a string'):
                worker.adapt_rule_result({**raw, 'evidence_status': value}, policy)
        with self.assertRaisesRegex(ValueError, 'invalid diagnostic text key'):
            worker.adapt_rule_result(raw, {**policy, 'diagnostic_text_keys': ['C2']})

    def test_result_adapter_extension_requires_exact_source_and_keeps_original_policy(self):
        tid = '03_Data_Analysis_task_005_cross_month_returns_regional_sales'
        _, sections, _ = _parse_task_source(next((REPO_ROOT/'tasks/general_e2e').rglob(tid+'.md')))
        code = _strip_codeblock(sections['Automated Checks'])
        policy = {'schema_version': 'wildclawbench.general-e2e-numeric-diagnostics/v1', 'diagnostic_keys': ['diagnostics', '诊断']}
        before = dict(policy)
        fn = RUNTIME.dataset_rule_corrections.effective_result_adapter
        self.assertEqual(fn(tid, code, policy)['diagnostic_text_keys'], ['evidence_status'])
        self.assertEqual(policy, before)
        self.assertEqual(fn(tid, code+'\n', policy), policy)
        self.assertEqual(fn('other', code, policy), policy)

    def test_cwm_profile_keeps_business_members_and_rejects_other_changes(self):
        data_dir = Path(RUNTIME.dataset_rule_corrections.__file__).resolve().parents[1] / 'data/public-input-baselines'
        baseline = json.loads((data_dir / 'cross-month-sales-v1.json').read_text())['files'][0]
        original = base64.b64decode(baseline['base64'])
        with zipfile.ZipFile(BytesIO(original)) as z:
            members = {name: z.read(name) for name in z.namelist()}
        custom = b'<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/custom-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"><property name="CWM_TEST" pid="2" fmtid="{D5CDD505-2E9C-101B-9397-08002B2CF9AE}"><vt:lpwstr>test</vt:lpwstr></property></Properties>'
        members['docProps/custom.xml'] = custom
        rel = ET.fromstring(members['_rels/.rels'])
        ET.SubElement(rel, '{http://schemas.openxmlformats.org/package/2006/relationships}Relationship',
                      Id='rIdCwmTest', Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/custom-properties', Target='docProps/custom.xml')
        members['_rels/.rels'] = ET.tostring(rel)
        types = ET.fromstring(members['[Content_Types].xml'])
        ET.SubElement(types, '{http://schemas.openxmlformats.org/package/2006/content-types}Override',
                      PartName='/docProps/custom.xml', ContentType='application/vnd.openxmlformats-officedocument.custom-properties+xml')
        members['[Content_Types].xml'] = ET.tostring(types)
        def archive(values):
            out = BytesIO()
            with zipfile.ZipFile(out, 'w') as z:
                for name, value in values.items(): z.writestr(name, value)
            return out.getvalue()
        compare = RUNTIME.dataset_rule_corrections.office_input_compat.compare_office_cwm
        candidate = archive(members)
        before = hashlib.sha256(candidate).hexdigest()
        proof = compare(original, candidate, baseline['sha256'])
        self.assertTrue(proof['business_members_byte_identical'])
        self.assertFalse(proof['candidate_rewritten'])
        self.assertEqual(hashlib.sha256(candidate).hexdigest(), before)
        tampered = dict(members)
        sheet = next(name for name in tampered if name.startswith('xl/worksheets/'))
        tampered[sheet] += b' '
        self.assertIsNone(compare(original, archive(tampered), baseline['sha256']))
        tampered = dict(members)
        tampered['docProps/custom.xml'] = custom.replace(b'CWM_TEST', b'BUSINESS_SETTING')
        self.assertIsNone(compare(original, archive(tampered), baseline['sha256']))
        with self.assertRaisesRegex(ValueError, 'digest mismatch'):
            compare(original, candidate, '0'*64)

    def test_cross_month_source_correction_is_exact_and_preserves_original_guard(self):
        tid = '03_Data_Analysis_task_005_cross_month_returns_regional_sales'
        task = next((REPO_ROOT / 'tasks/general_e2e').rglob(tid + '.md'))
        _, sections, _ = _parse_task_source(task)
        code = _strip_codeblock(sections['Automated Checks'])
        effective, receipt = RUNTIME._effective_rule_source({'identity': {'task_id': tid}}, code)
        ast.parse(effective)
        self.assertEqual(receipt['correction_id'], 'canonical-public-office-cwm-only/v1')
        self.assertIn("raise ReviewRequired('公开材料哈希变化", effective)
        self.assertEqual(RUNTIME._effective_rule_source({'identity': {'task_id': tid}}, code + '\n'), (code + '\n', None))

    def test_paged_evidence_changes_only_resource_guards_on_exact_sources(self):
        for task_id, (digest, old, new) in RUNTIME.dataset_rule_corrections._PAGED_RULES.items():
            with self.subTest(task_id=task_id):
                task = next((REPO_ROOT / "tasks/general_e2e").rglob(task_id + ".md"))
                _, sections, _ = _parse_task_source(task)
                code = _strip_codeblock(sections["Automated Checks"])
                self.assertEqual(hashlib.sha256(code.encode()).hexdigest(), digest)
                effective, receipt = RUNTIME._effective_rule_source({"identity": {"task_id": task_id}}, code)
                self.assertEqual(effective.replace(new, old), code)
                ast.parse(effective)
                self.assertFalse(receipt["evidence_policy"]["truncation_allowed"])
                self.assertEqual(RUNTIME._effective_rule_source({"identity": {"task_id": task_id}}, code + "\n"), (code + "\n", None))
                self.assertEqual(RUNTIME._effective_rule_source({"identity": {"task_id": "other"}}, code), (code, None))


if __name__ == "__main__":
    unittest.main()
