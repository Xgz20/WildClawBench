from copy import deepcopy
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest

from tests.general_e2e.test_local_scoring_runtime import RUNTIME, REPO_ROOT
from tests.general_e2e.test_general_scoring_orchestration import ORCHESTRATOR
from eval_general_e2e.datasets.bundle import _strip_codeblock
from tests.general_e2e.frozen_sources import parse_frozen_task_source as _parse_task_source

GUARD=RUNTIME.private_reference_guard


class CanonicalPrivateReferenceTests(unittest.TestCase):
    def contract(self,row):
        path=next((REPO_ROOT/'tasks/general_e2e').rglob(row['task_id']+'.md'))
        _,sections,_=_parse_task_source(path)
        return {'task_id':row['task_id'],'automated_checks':_strip_codeblock(sections['Automated Checks'])}

    def manifest(self,row):
        contract=self.contract(row)
        entries=[{'path':r['path'],'type':'file','size':r['size'],'sha256':r['canonical_sha256']} for r in row['references']]
        dataset={'id':row['dataset_id'],'digest':row['dataset_digest']}
        return {'identity':{'task_id':row['task_id']},'dataset':dataset,
            'digests':{'contract_sha256':row['contract_sha256']},
            'private_scoring':{'workspace_entries':entries},'paths':{'gt':'private/gt'},
            'runtime':{'private_reference_guard_profile':GUARD.marker(contract,row['contract_sha256'],dataset,entries)}}

    def test_both_independent_skills_freeze_identical_registry_and_original_dataset_members(self):
        skills=REPO_ROOT/'tools/report/skills/general-e2e'
        for name in ['scripts/private_reference_guard.py','data/private-reference-guards-v1.json']:
            self.assertEqual((skills/'score-general-e2e'/name).read_bytes(),(skills/'orchestrate-general-e2e'/name).read_bytes())
        dataset=json.loads((REPO_ROOT/'eval_general_e2e/datasets/manifests/general-custom116-v1.json').read_text())
        for row in GUARD.registry():
            task=next(t for t in dataset['tasks'] if t['task_id']==row['task_id'])
            self.assertEqual(dataset['dataset_digest'],row['dataset_digest'])
            self.assertEqual(task['digests']['scoring_contract_sha256'],row['contract_sha256'])
            for ref in row['references']:
                original=next(e for e in task['materials']['private_scoring']['entries'] if e['path']==ref['path'])
                self.assertEqual((original['sha256'],original['size']),(ref['canonical_sha256'],ref['size']))
            for ref in row.get('public_text_guards',[]):
                original=next(e for e in task['materials']['execution']['entries'] if e['path']==ref['path'])
                self.assertEqual((original['sha256'],original['size']),(ref['canonical_sha256'],ref['size']))
                path=REPO_ROOT/'workspace/general_e2e/02_Office/task_014_invoice_email_archive_manifest/exec'/ref['path']
                self.assertEqual(hashlib.sha256(path.read_bytes().replace(b'\n',b'\r\n')).hexdigest(),ref['declared_sha256'])
        self.assertIsNone(GUARD.registered({'task_id':'unrelated','automated_checks':None},'x',{}))

    def test_new_profile_changes_only_registered_checksum_literals_and_legacy_stays_exact(self):
        for row in GUARD.registry():
            contract=self.contract(row);source=contract['automated_checks'];m=self.manifest(row)
            self.assertEqual(hashlib.sha256(source.encode()).hexdigest(),row['source_sha256'])
            fixed,receipt=RUNTIME._effective_rule_source(m,source)
            for ref in row['replacements']:
                self.assertEqual(fixed.count(repr(ref['canonical_sha256'])),ref['occurrences'])
                fixed=fixed.replace(repr(ref['canonical_sha256']),repr(ref['declared_sha256']))
            self.assertEqual(fixed,source)
            self.assertFalse(receipt['reference_bytes_rewritten']);self.assertFalse(receipt['candidate_rewritten'])
            self.assertEqual(RUNTIME._effective_rule_source({},source),(source,None))
            for edit in [lambda x:x['digests'].update(contract_sha256='0'*64),
                         lambda x:x['dataset'].update(digest='0'*64),
                         lambda x:x['private_scoring']['workspace_entries'][0].update(sha256='0'*64),
                         lambda x:x['runtime']['private_reference_guard_profile'].update(catalog_sha256='0'*64)]:
                bad=deepcopy(m);edit(bad)
                with self.subTest(task=row['task_id']),self.assertRaises(RUNTIME.ScoringRuntimeError):
                    RUNTIME._effective_rule_source(bad,source)

    def test_actual_original_rules_accept_canonical_gt_and_empty_candidate_is_not_reference_error(self):
        for row in GUARD.registry():
            with self.subTest(task=row['task_id']),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);workspace=root/'workspace';workspace.mkdir();(workspace/'results').mkdir()
                stem=row['task_id'].removeprefix('02_Office_')
                original=REPO_ROOT/'workspace/general_e2e/02_Office'/stem/'gt'
                shutil.copytree(original,workspace/'gt')
                inventory,_=RUNTIME._inventory_tree(workspace/'gt')
                RUNTIME._guard_candidate_office_copies(workspace/'gt',inventory,role='test-canonical-private-reference')
                manifest=self.manifest(row);source=self.contract(row)['automated_checks']
                effective,_=RUNTIME._effective_rule_source(manifest,source)
                request={'schema_version':RUNTIME.WORKER_REQUEST_SCHEMA,'workspace_path':str(workspace),
                    'transcript':[],'automated_checks':effective}
                path=root/'request.json';path.write_text(json.dumps(request),encoding='utf-8');out=root/'result.json'
                result=subprocess.run([sys.executable,'-I',str(Path(RUNTIME.__file__).with_name('rule_worker.py')),
                    '--request',str(path),'--result',str(out)],capture_output=True,timeout=60)
                document=json.loads(out.read_text())
                try:
                    self.assertEqual(result.returncode,0,document.get('error'))
                    self.assertTrue(document['ok']);self.assertTrue(0<=document['result']['overall_score']<=1)
                    self.assertEqual(RUNTIME._inventory_tree(workspace/'gt')[0],inventory)
                finally:
                    RUNTIME._remove_tree(workspace)

    def test_old_failure_deferral_requires_same_original_file_bytes_and_exact_error(self):
        row=GUARD.registry()[0];manifest=self.manifest(row);manifest['runtime']={}
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'private/gt').mkdir(parents=True)
            ref=row['references'][0]
            original=REPO_ROOT/'workspace/general_e2e/02_Office/task_003_news_event_multifile_extract/gt'/ref['path']
            shutil.copyfile(original,root/'private/gt'/ref['path'])
            error={'type':'EvidenceError','message':'Private reference mismatch: '+ref['path']}
            self.assertTrue(GUARD.matches_old_failure(root,manifest,self.contract(row),error))
            for bad in [dict(error,type='RuntimeError'),dict(error,message='Missing private reference: '+ref['path']),
                        dict(error,message='Private reference mismatch: unknown.md')]:
                self.assertFalse(GUARD.matches_old_failure(root,manifest,self.contract(row),bad))
            target=root/'private/gt'/ref['path'];target.write_bytes(target.read_bytes()+b'changed')
            self.assertFalse(GUARD.matches_old_failure(root,manifest,self.contract(row),error))

    def test_original_crlf_and_registered_lf_fixtures_produce_identical_numeric_results(self):
        row=next(r for r in GUARD.registry() if 'task_014_' in r['task_id'])
        original=REPO_ROOT/'workspace/general_e2e/02_Office/task_014_invoice_email_archive_manifest'
        source=self.contract(row)['automated_checks']
        fixed,_=RUNTIME._effective_rule_source(self.manifest(row),source)
        results=[]
        with tempfile.TemporaryDirectory() as folder:
            for label,code in [('original-crlf',source),('registered-lf',fixed)]:
                root=Path(folder)/label;root.mkdir();workspace=root/'workspace'
                shutil.copytree(original/'exec',workspace)
                shutil.copytree(original/'gt',workspace/'gt')
                # A synthetic conformance fixture; never a Harness submission.
                shutil.copytree(original/'gt',workspace/'results')
                if label=='original-crlf':
                    for path in workspace.rglob('*'):
                        if path.is_file() and path.suffix in {'.txt','.json','.md','.csv','.yml','.yaml'}:
                            raw=path.read_bytes();self.assertNotIn(b'\r',raw)
                            path.write_bytes(raw.replace(b'\n',b'\r\n'))
                request={'schema_version':RUNTIME.WORKER_REQUEST_SCHEMA,'workspace_path':str(workspace),
                    'transcript':[],'automated_checks':code}
                path=root/'request.json';path.write_text(json.dumps(request),encoding='utf-8');out=root/'result.json'
                process=subprocess.run([sys.executable,'-I',str(Path(RUNTIME.__file__).with_name('rule_worker.py')),
                    '--request',str(path),'--result',str(out)],capture_output=True,timeout=60)
                result=json.loads(out.read_text())
                self.assertEqual(process.returncode,0,result.get('error'))
                results.append({k:v for k,v in result['result'].items() if isinstance(v,(int,float)) and not isinstance(v,bool)})
            self.assertTrue(results[0]);self.assertEqual(results[0],results[1])

    def test_office020_declared_runtime_guard_retains_only_proven_original_reference_failure(self):
        row=next(r for r in GUARD.registry() if 'task_020_' in r['task_id'])
        manifest=self.manifest(row);manifest['runtime']={};contract=self.contract(row)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'private/gt').mkdir(parents=True)
            ref=row['references'][0];path=root/'private/gt'/ref['path']
            source=REPO_ROOT/'workspace/general_e2e/02_Office/task_020_research_factor_table_extract/gt'/ref['path']
            shutil.copyfile(source,path)
            error={'type':'RuntimeError','message':'Evaluator GT changed: research_factor_extract.json'}
            self.assertTrue(ORCHESTRATOR._registered_reference_failure(root,manifest,contract,error))
            for bad in [dict(error,type='ValueError'),dict(error,message='Evaluator GT missing: research_factor_extract.json'),
                        dict(error,message='Evaluator reference shape changed')]:
                self.assertFalse(ORCHESTRATOR._registered_reference_failure(root,manifest,contract,bad))
            path.write_bytes(path.read_bytes()+b'changed')
            self.assertFalse(ORCHESTRATOR._registered_reference_failure(root,manifest,contract,error))


if __name__=='__main__':unittest.main()
