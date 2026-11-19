from copy import deepcopy
from io import BytesIO
from pathlib import Path
import ast
import base64
import hashlib
import json
import tempfile
import sys
import unittest
import zipfile
from xml.etree import ElementTree as ET

from eval_general_e2e.datasets.bundle import _strip_codeblock
from tests.general_e2e.frozen_sources import parse_frozen_task_source as _parse_task_source
from tests.general_e2e.test_local_scoring_runtime import RUNTIME, REPO_ROOT, Fixture

PROFILE = RUNTIME.public_office_profiles
COMPARATOR = PROFILE.office_input_compat


def with_cwm(original):
    with zipfile.ZipFile(BytesIO(original)) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    ns = 'http://schemas.openxmlformats.org/officeDocument/2006/custom-properties'
    root = ET.fromstring(members['docProps/custom.xml']) if 'docProps/custom.xml' in members else ET.Element('{'+ns+'}Properties')
    pid = max([int(p.get('pid')) for p in root]+[1])+1
    prop = ET.SubElement(root,'{'+ns+'}property',name='CWM_PROFILE_TEST',pid=str(pid),fmtid='{D5CDD505-2E9C-101B-9397-08002B2CF9AE}')
    ET.SubElement(prop,'{http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes}lpwstr').text='synthetic metadata'
    members['docProps/custom.xml'] = ET.tostring(root)
    rel = ET.fromstring(members['_rels/.rels'])
    if not any(e.get('Type','').endswith('/custom-properties') for e in rel):
        ET.SubElement(rel,'{http://schemas.openxmlformats.org/package/2006/relationships}Relationship',
                      Id='rIdCwmProfileTest',Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/custom-properties',Target='docProps/custom.xml')
    members['_rels/.rels'] = ET.tostring(rel)
    content = ET.fromstring(members['[Content_Types].xml'])
    if not any(e.get('PartName')=='/docProps/custom.xml' for e in content):
        ET.SubElement(content,'{http://schemas.openxmlformats.org/package/2006/content-types}Override',
                      PartName='/docProps/custom.xml',ContentType='application/vnd.openxmlformats-officedocument.custom-properties+xml')
    members['[Content_Types].xml'] = ET.tostring(content)
    return package(members)


def package(members):
    stream = BytesIO()
    with zipfile.ZipFile(stream,'w') as archive:
        for name,content in members.items():
            archive.writestr(name,content)
    return stream.getvalue()


def matcher(row):
    # Execute only our trusted equivalence helper, never a dataset grade().
    namespace = dict(COMPARATOR.__dict__)
    namespace['_GE2E_PUBLIC_OFFICE_PROFILE'] = row
    exec(PROFILE.MATCHER, namespace)
    return namespace['_ge2e_public_office_matches']


class PublicOfficeProfilesTests(unittest.TestCase):
    def test_real_managed_worker_records_the_audit_without_rewriting_protected_input(self):
        row = PROFILE.registry()[0]
        baseline = row['files'][0]
        content = with_cwm(base64.b64decode(baseline['base64']))
        helper = Path(COMPARATOR.__file__).read_text(encoding='utf-8')
        source = helper+'\n_GE2E_PUBLIC_OFFICE_PROFILE = '+repr(row)+'\n'+PROFILE.MATCHER+'\n'
        source += 'def grade(transcript,workspace_path):\n'
        source += '    root=_ge2e_Path(workspace_path)\n'
        source += '    value=float(_ge2e_public_office_matches(root/'+repr(baseline['path'])+','+repr(baseline['sha256'])+',root))\n'
        source += '    return {"probe":value,"overall_score":value}\n'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            try:
                fixture = Fixture(root,rule=source,candidate_files={baseline['path']:content})
                attempt = fixture.prepare(protect_runtime_office_inputs=sys.platform=='darwin')
                file = attempt/'runtime/workspace'/baseline['path']
                before = file.read_bytes()
                result = RUNTIME.run_rules_attempt(attempt_root=attempt,runtime_python=Path(sys.executable),timeout_seconds=20)
                self.assertEqual(result['rule_component']['score'],1.0)
                self.assertEqual(file.read_bytes(),before)
                audit = attempt/'runtime/workspace'/row['evidence_directory']/'00_public_office_metadata_variance.json'
                self.assertTrue(json.loads(audit.read_text(encoding='utf-8'))[0]['business_members_byte_identical'])
                RUNTIME.verify_attempt(attempt)
            finally:
                RUNTIME._remove_tree(root)

    def test_only_new_marked_exact_contracts_apply_and_original_math_stays_intact(self):
        for row in PROFILE.registry():
            task_id = row['task_id']
            _,sections,_ = _parse_task_source(next((REPO_ROOT/'tasks/general/work').rglob(task_id+'.md')))
            source = _strip_codeblock(sections['Automated Checks'])
            contract = {'task_id':task_id,'automated_checks':source}
            marker = PROFILE.marker(contract,row['contract_sha256'])
            self.assertIsNotNone(marker)
            manifest = {'identity':{'task_id':task_id},'digests':{'contract_sha256':row['contract_sha256']}}
            legacy = RUNTIME._effective_rule_source(manifest,source)
            self.assertEqual(PROFILE.effective_source(manifest,source,*legacy),legacy)
            manifest['runtime'] = {'public_office_input_profile':marker}
            effective,receipt = RUNTIME._effective_rule_source(manifest,source)
            compile(effective,'<corrected-public-office-rule>','exec')
            self.assertEqual(receipt['correction_id'],PROFILE.PROFILE)
            self.assertFalse(receipt['candidate_rewritten'])
            original_ast = ast.parse(legacy[0])
            fixed_ast = ast.parse(effective)
            fixed_functions = {n.name:n for n in fixed_ast.body if isinstance(n,ast.FunctionDef)}
            for node in original_ast.body:
                if isinstance(node,ast.FunctionDef) and node.name!='grade':
                    self.assertEqual(ast.dump(node),ast.dump(fixed_functions[node.name]),(task_id,node.name))
                if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id in {'WEIGHTS','ABILITY_MAP','SPECS'} for t in node.targets):
                    self.assertTrue(any(ast.dump(n)==ast.dump(node) for n in fixed_ast.body),task_id)
            if task_id.startswith('02_Office_task_002_'):
                self.assertEqual(receipt['prior_correction']['correction_id'],'complete-paged-grader-evidence/v1')
            self.assertIsNone(PROFILE.marker(contract,'0'*64))
            self.assertIsNone(PROFILE.marker({**contract,'automated_checks':source+'\n'},row['contract_sha256']))
            wrong = deepcopy(manifest);wrong['runtime']['public_office_input_profile']['catalog_sha256']='0'*64
            with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError,'FROZEN_PROFILE_MISMATCH'):
                RUNTIME._effective_rule_source(wrong,source)

    def test_all_twelve_public_office_inputs_accept_only_cwm_and_remain_unmodified(self):
        count = 0
        for row in PROFILE.registry():
            compare = matcher(row)
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                for baseline in row['files']:
                    original = base64.b64decode(baseline['base64'])
                    self.assertEqual(hashlib.sha256(original).hexdigest(),baseline['sha256'])
                    candidate = with_cwm(original)
                    target = root/baseline['path'];target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(candidate)
                    self.assertTrue(compare(target,baseline['sha256'],root),(row['task_id'],baseline['path']))
                    self.assertEqual(target.read_bytes(),candidate)
                    with zipfile.ZipFile(BytesIO(candidate)) as archive:
                        parts = {name:archive.read(name) for name in archive.namelist()}
                    # Changing any ordinary OPC member, including formulas,
                    # document properties or styles, must not pass this profile.
                    ordinary = next(name for name in parts if name not in {'docProps/custom.xml','_rels/.rels','[Content_Types].xml'})
                    changed = dict(parts);changed[ordinary] += b' '
                    target.write_bytes(package(changed))
                    self.assertFalse(compare(target,baseline['sha256'],root))
                    target.write_bytes(candidate)
                    self.assertFalse(compare(target,'0'*64,root))
                    unknown = root/'unregistered.xlsx';unknown.write_bytes(candidate)
                    self.assertFalse(compare(unknown,baseline['sha256'],root))
                    count += 1
                audit = json.loads((root/row['evidence_directory']/'00_public_office_metadata_variance.json').read_text(encoding='utf-8'))
                self.assertEqual(len(audit),len(row['files']))
                self.assertTrue(all(p['not_agent_action_evidence'] for p in audit))
        self.assertEqual(count,12)

    def test_unchanged_template_detection_has_only_its_registered_output_exception(self):
        row = next(r for r in PROFILE.registry() if r['output_template_paths'])
        output,source = next(iter(row['output_template_paths'].items()))
        baseline = next(f for f in row['files'] if f['path']==source)
        candidate = with_cwm(base64.b64decode(baseline['base64']))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory);target = root/output;target.parent.mkdir(parents=True);target.write_bytes(candidate)
            compare = matcher(row)
            self.assertFalse(compare(target,baseline['sha256'],root))
            self.assertTrue(compare(target,baseline['sha256'],root,role='unchanged_template'))
            self.assertFalse(compare(target,baseline['sha256'],root,role='unknown'))
            self.assertEqual(target.read_bytes(),candidate)


if __name__=='__main__':
    unittest.main()
