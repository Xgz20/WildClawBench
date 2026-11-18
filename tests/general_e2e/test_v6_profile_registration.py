from copy import deepcopy
from pathlib import Path
import hashlib
import importlib.util
import json
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from eval_general_e2e.datasets.bundle import _parse_task_source, _strip_codeblock
from tests.general_e2e.test_local_scoring_runtime import RUNTIME, REPO_ROOT

RELEASE=RUNTIME.release_baseline_text
import sterilization_quote_complete_layout as QUOTE

def rule(task):
    p=next((REPO_ROOT/'tasks/general_e2e').rglob(task+'.md'))
    return _strip_codeblock(_parse_task_source(p)[1]['Automated Checks'])


class V6ProfileRegistrationTests(unittest.TestCase):
    def test_same_release_source_enables_only_exact_v6_identity_and_keeps_old_manifests(self):
        row=RELEASE.registry(RELEASE.V4_CONTRACT);source=rule(row['task_id'])
        contract={'task_id':row['task_id'],'automated_checks':source}
        marker=RELEASE.marker(contract,RELEASE.V4_CONTRACT,RELEASE.V6_DATASET)
        self.assertIsNotNone(marker)
        self.assertIsNone(RELEASE.marker(contract,RELEASE.V4_CONTRACT,{**RELEASE.V6_DATASET,'digest':'0'*64}))
        self.assertIsNone(RELEASE.marker({**contract,'automated_checks':source+'\n'},RELEASE.V4_CONTRACT,RELEASE.V6_DATASET))
        m={'identity':{'task_id':row['task_id']},'dataset':RELEASE.V6_DATASET,
           'digests':{'contract_sha256':RELEASE.V4_CONTRACT},'runtime':{}}
        self.assertEqual(RELEASE.effective_source(m,source,source,None),(source,None))
        m['runtime']['release_baseline_text_profile']=marker
        code,receipt=RELEASE.effective_source(m,source,source,None)
        old={};new={};exec(source,old);exec(code,new)
        self.assertEqual(old['WEIGHTS'],new['WEIGHTS'])
        self.assertFalse(receipt['candidate_rewritten']);self.assertFalse(receipt['numeric_decisions_assigned'])
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'protected.txt';ref=row['files'][0]
            raw=(REPO_ROOT/'workspace/general_e2e/02_Office/task_007_release_phase_gate_progression/exec'/ref['path']).read_bytes()
            for data in [raw,raw.replace(b'\n',b'\r\n')]:
                p.write_bytes(data);self.assertTrue(new['_ge2e_release_protected_matches'](p,ref['path']))
            p.write_bytes(raw+b' ');self.assertFalse(new['_ge2e_release_protected_matches'](p,ref['path']))

    def release_fixture(self,folder):
        root=Path(folder);base=root/'candidate-original/workspace';base.mkdir(parents=True)
        row=RELEASE.registry(RELEASE.V4_CONTRACT)
        original=REPO_ROOT/'workspace/general_e2e/02_Office/task_007_release_phase_gate_progression/exec'
        for ref in row['files']:
            target=base/ref['path'];target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((original/ref['path']).read_bytes())
        identity={'task_id':row['task_id'],'scoring_attempt_id':'synthetic-v6','execution_attempt_id':'execution-001'}
        m={'identity':identity,'dataset':dict(RELEASE.V6_DATASET),'digests':{'contract_sha256':RELEASE.V4_CONTRACT},
           'runtime':{'workspace_argument':'runtime/workspace','runtime_workspace':'runtime/workspace'},
           'paths':{'candidate_original':'candidate-original/workspace','runtime_workspace':'runtime/workspace'}}
        (root/'rule-component.json').write_text('{}');(root/'semantic').mkdir();(root/'semantic/query-log.json').write_text('{}')
        sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
        report={'schema_version':'judge-scoring-infrastructure-blocker/v1','status':'evaluation_error',
                'error_code':'FROZEN_RULE_PUBLIC_TEXT_BASELINE_MISMATCH',**identity,
                'score_published':False,'total_score':None,'evidence':{
                    'registry_sha256':RELEASE.CATALOG_SHA,'frozen_rule_component_sha256':sha(root/'rule-component.json'),
                    'frozen_contract_sha256':RELEASE.V4_CONTRACT,'frozen_rule_source_sha256':RELEASE.V4_SOURCE,
                    'dataset':dict(RELEASE.V6_DATASET),'profile_in_attempt':None,'all_eight_registered_original_identities':True},
                'preservation':{k:False for k in ['candidate_original_modified','frozen_skill_modified','harness_executed',
                    'rule_component_rerun','old_component_modified','semantic_response_imported','finalize_run','verify_score_passed']}}
        (root/'scoring-infrastructure-blocker.json').write_text(json.dumps(report))
        rt=SimpleNamespace(_read_json=lambda p:json.loads(Path(p).read_text()),_sha256_file=sha)
        return root,m,{'task_id':row['task_id'],'automated_checks':rule(row['task_id'])},rt,report

    def test_v6_original_native_failure_replays_all_eight_bytes_and_rejects_changed_content(self):
        with tempfile.TemporaryDirectory() as folder:
            root,m,c,rt,_=self.release_fixture(folder)
            self.assertTrue(RELEASE.native_blocker_matches(rt,root,m,c))
            ref=RELEASE.registry()['files'][0]
            p=root/m['paths']['candidate_original']/ref['path'];p.write_bytes(p.read_bytes()+b' ')
            with self.assertRaisesRegex(ValueError,'NONCANONICAL'):RELEASE.native_blocker_matches(rt,root,m,c)

    def test_v6_native_failure_requires_exact_identity_preservation_and_unpublished_state(self):
        for field in ['execution','source','mutation','component','dataset']:
            with self.subTest(field=field),tempfile.TemporaryDirectory() as folder:
                root,m,c,rt,b=self.release_fixture(folder)
                if field=='execution':b['execution_attempt_id']='other'
                elif field=='source':b['evidence']['frozen_rule_source_sha256']='0'*64
                elif field=='mutation':b['preservation']['rule_component_rerun']=True
                elif field=='component':b['evidence']['frozen_rule_component_sha256']='0'*64
                else:b['evidence']['dataset']['digest']='0'*64
                (root/'scoring-infrastructure-blocker.json').write_text(json.dumps(b))
                with self.assertRaises(ValueError):RELEASE.native_blocker_matches(rt,root,m,c)

    def test_quote_profile_for_v6_is_identical_to_prior_registered_source_and_old_missing_marker_stays_missing(self):
        source=rule(QUOTE.TASK);c={'task_id':QUOTE.TASK,'automated_checks':source}
        marker=QUOTE.marker(c,QUOTE.CONTRACT,QUOTE.V6_DATASET)
        self.assertEqual(marker,QUOTE.marker(c,QUOTE.CONTRACT,QUOTE.DATASET))
        self.assertIsNone(QUOTE.marker(c,QUOTE.CONTRACT,{**QUOTE.V6_DATASET,'digest':'0'*64}))
        m={'identity':{'task_id':QUOTE.TASK},'dataset':QUOTE.V6_DATASET,
           'digests':{'contract_sha256':QUOTE.CONTRACT},'runtime':{}}
        self.assertEqual(QUOTE.effective_source(m,source,source,None),(source,None))
        m['runtime']['sterilization_quote_layout_profile']=marker
        new,_=QUOTE.effective_source(m,source,source,None)
        old=deepcopy(m);old['dataset']=QUOTE.DATASET
        previous,_=QUOTE.effective_source(old,source,source,None)
        self.assertEqual(new,previous)

    def test_prepared_quote_failure_proves_no_worker_or_judge_and_rejects_started_or_enabled_profile(self):
        scripts=REPO_ROOT/'tools/report/skills/general-e2e/orchestrate-general-e2e/scripts'
        sys.path.insert(0,str(scripts))
        try:
            spec=importlib.util.spec_from_file_location('_v6_prepared_profile_test',scripts/'prepared_v6_profile_failure.py')
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        finally:sys.path.remove(str(scripts))
        source=rule(QUOTE.TASK);contract={'task_id':QUOTE.TASK,'automated_checks':source}
        m={'identity':{'task_id':QUOTE.TASK},'dataset':QUOTE.V6_DATASET,
           'digests':{'contract_sha256':QUOTE.CONTRACT},'runtime':{}}
        task={'phase':'RULES_READY','thread':None,'score':None}
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);proof=module.evidence(None,root,m,contract,task)
            self.assertTrue(proof['worker_never_started']);self.assertFalse(proof['process_created'])
            self.assertFalse(proof['numeric_score_assigned'])
            task['thread']={'status':'RUNNING'}
            with self.assertRaises(ValueError):module.evidence(None,root,m,contract,task)
            task['thread']=None;(root/'worker').mkdir()
            with self.assertRaises(ValueError):module.evidence(None,root,m,contract,task)
            (root/'worker').rmdir();m['runtime']['sterilization_quote_layout_profile']=proof['expected_registered_profile']
            with self.assertRaises(ValueError):module.evidence(None,root,m,contract,task)

    def test_prepared_retirement_uses_only_registered_ready_state_without_native_or_rule_execution(self):
        scripts=REPO_ROOT/'tools/report/skills/general-e2e/orchestrate-general-e2e/scripts'
        sys.path.insert(0,str(scripts))
        try:
            spec=importlib.util.spec_from_file_location('_v6_prepared_retirement_test',scripts/'framework_failure_retirement.py')
            retirement=importlib.util.module_from_spec(spec);spec.loader.exec_module(retirement)
        finally:sys.path.remove(str(scripts))
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);attempt=root/'case';(attempt/'private').mkdir(parents=True)
            source=rule(QUOTE.TASK);contract={'task_id':QUOTE.TASK,'automated_checks':source}
            m={'identity':{'task_id':QUOTE.TASK,'scoring_attempt_id':'prepared-001'},
               'dataset':QUOTE.V6_DATASET,'digests':{'contract_sha256':QUOTE.CONTRACT},
               'runtime':{},'paths':{'contract':'private/contract.json'}}
            (attempt/'attempt-manifest.json').write_text(json.dumps(m))
            (attempt/'private/contract.json').write_text(json.dumps(contract));(root/'prompt.md').write_text('synthetic prompt')
            task={'task_id':QUOTE.TASK,'scoring_attempt_id':'prepared-001','attempt_path':'case',
                  'prompt_path':'prompt.md','phase':'RULES_READY','thread':None,'score':None,'history':[]}
            state={'tasks':[task],'score_skill':{}}
            def write_new(path,value):
                with Path(path).open('x') as stream:json.dump(value,stream)
            commands=[]
            rt=SimpleNamespace(_state_root=lambda p:Path(p),_verify_state=lambda p:state,
                _task_by_id=lambda s,t:s['tasks'][0],_identifier=lambda v,n:v,_required_string=lambda v,n:v,
                _read_json=lambda p:json.loads(Path(p).read_text()),
                _sha256_file=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest(),
                _run_score_command=lambda lock,args:commands.append(args),_write_new_json=write_new,
                _now=lambda:None,_timestamp=lambda now:'2026-11-18T00:00:00Z',_save=lambda r,s,n:s)
            with patch.object(retirement.aggregation_runtime_failure,'matches',return_value=False):
                retirement.record(rt,root,task_id=QUOTE.TASK,reason='registered v6 preparation profile omission')
                proof=retirement.verify(rt,root,state,task)
            self.assertEqual(task['phase'],'UNSCORED')
            self.assertEqual([args[0] for args in commands],['verify'])
            self.assertFalse(proof['semantic_judging_performed'])
            self.assertNotIn('native_context',proof)
            self.assertTrue(proof['prepared_registration_failure']['worker_never_started'])


if __name__=='__main__':unittest.main()
