from copy import deepcopy
from pathlib import Path
import hashlib
import importlib.util
import json
import tempfile
import sys
import unittest
from unittest.mock import patch

from tests.general_e2e.test_local_scoring_runtime import RUNTIME,Fixture,REPO_ROOT
from eval_general_e2e.datasets.bundle import _strip_codeblock
from tests.general_e2e.frozen_sources import parse_frozen_task_source as _parse_task_source
from tests.general_e2e import test_general_scoring_orchestration as orchtests

GROUP=RUNTIME.escrow_grouped_review
DETAILS=RUNTIME.domain_details_diagnostics
RELEASE=RUNTIME.release_baseline_text
spec=importlib.util.spec_from_file_location('grouped_details_worker',Path(RUNTIME.__file__).with_name('rule_worker.py'))
WORKER=importlib.util.module_from_spec(spec);spec.loader.exec_module(WORKER)


class NewRuleCompatibilityTests(unittest.TestCase):
    def test_domain_diagnostics_keep_numbers_and_reject_wrong_shape_or_unknown_objects(self):
        adapter={'schema_version':'wildclawbench.general-e2e-numeric-diagnostics/v1','diagnostic_keys':[], 'domain_details_object_key':'details'}
        raw={'C1_scope':.4,'overall_score':.4,'details':{'domains':{'C1_scope':[True,False]},'read_error':None}}
        before=deepcopy(raw);self.assertEqual(WORKER.adapt_rule_result(raw,adapter),{'C1_scope':.4,'overall_score':.4});self.assertEqual(raw,before)
        for value in [{'domains':{'unknown':[True]},'read_error':None},{'domains':{'C1_scope':[1]},'read_error':None},{'domains':{},'read_error':3}]:
            with self.subTest(value=value),self.assertRaises(ValueError):WORKER.adapt_rule_result(dict(raw,details=value),adapter)
        self.assertIn('unknown_object',WORKER.adapt_rule_result(dict(raw,unknown_object={}),adapter))

    def test_isolated_managed_worker_keeps_raw_details_and_archived_input_verification(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);marker={'profile':DETAILS.PROFILE,'synthetic_fixture':True}
            details={'domains':{'C1_scope':[False]},'read_error':None}
            rule="def grade(transcript,workspace_path):\n return {'accuracy':.4,'overall_score':.4,'details':"+repr(details)+"}"
            adapter={'schema_version':'wildclawbench.general-e2e-numeric-diagnostics/v1','diagnostic_keys':[]}
            with patch.object(DETAILS,'marker',return_value=marker):
                attempt=Fixture(root/'fixture',rule=rule,contract_overrides={'rule_result_adapter':adapter}).prepare()
                try:
                    result=RUNTIME.run_rules_attempt(attempt_root=attempt,runtime_python=Path(sys.executable),timeout_seconds=30)
                    self.assertEqual(result['rule_component']['score'],.4)
                    worker=json.loads((attempt/'worker/result.json').read_text());self.assertEqual(worker['raw_result']['details'],details)
                    self.assertNotIn('details',worker['result']);RUNTIME.verify_attempt(attempt)
                finally:RUNTIME._remove_tree(root)

    def test_grouped_review_deduplicates_11000_occurrences_preserving_all_locations_and_distinct_words(self):
        source="""STATE_FIELDS={'状态'}
def normalized(value):return value
def grade(transcript: list, workspace_path: str) -> dict:
    expected={'表':[{'状态':'批准'},{'状态':'取消'}]}
    actual={'表':[{'状态':'别称','_candidate_location':f'synthetic.xlsx|表|行{i}'} for i in range(11000)]}
    known_states={field:{normalized(row.get(field)) for rows in expected.values() for row in rows if field in row} for field in STATE_FIELDS}
    diagnostic={'review_required':[]}
    for rows in actual.values():
        for row in rows:
            for field in STATE_FIELDS.intersection(row):
                value=normalized(row[field])
                if value and value not in known_states[field]:diagnostic['review_required'].append(f'未识别但可能等价的状态：{field}={value}；需依据公开口径复核')
    return {'overall_score':float(all(r['状态']=='批准' for r in actual['表']))}
"""
        manifest={'identity':{'task_id':RUNTIME.escrow_state_review.TASK},'digests':{'contract_sha256':'synthetic'},'runtime':{'rule_review_profile':GROUP.PROFILE}}
        with patch.object(RUNTIME.escrow_state_review,'matches',return_value=True):
            code,receipt=GROUP.effective_source(manifest,source,source,None)
        namespace={'_GENERAL_E2E_RULE_REVIEW':RUNTIME.rule_review.worker_configuration('discover',profile=GROUP.PROFILE)}
        exec(compile(code,'<synthetic-grouped-protocol>','exec'),namespace)
        namespace['grade']([],'.');contexts=namespace['_GENERAL_E2E_RULE_REVIEW']['observations']
        self.assertEqual(len(contexts),3)
        for item in contexts.values():
            self.assertEqual(len(item['all_occurrence_locations']),11000);self.assertTrue(item['occurrences_complete'])
        for choice,total in [('批准',1.),('__keep_literal_known_distinct__',0.)]:
            namespace['_GENERAL_E2E_RULE_REVIEW']=RUNTIME.rule_review.worker_configuration('apply',
                {key:value['canonical_choice']==choice for key,value in contexts.items()},profile=GROUP.PROFILE)
            self.assertEqual(namespace['grade']([],'.')['overall_score'],total)
        self.assertFalse(receipt['numeric_decisions_assigned'])
        distinct=source.replace("'状态':'别称'","'状态':f'别称{i}'").replace('range(11000)','range(3334)')
        with patch.object(RUNTIME.escrow_state_review,'matches',return_value=True):
            code,_=GROUP.effective_source(manifest,distinct,distinct,None)
        namespace={'_GENERAL_E2E_RULE_REVIEW':RUNTIME.rule_review.worker_configuration('discover',profile=GROUP.PROFILE)}
        exec(compile(code,'<synthetic-grouped-context-limit>','exec'),namespace)
        with self.assertRaisesRegex(RuntimeError,'RULE_REVIEW_CONTEXT_LIMIT'):
            namespace['grade']([],'.')
        self.assertEqual(len(namespace['_GENERAL_E2E_RULE_REVIEW']['observations']),10000)

    def test_grouped_review_keeps_each_literal_and_does_not_add_candidate_evidence_fields(self):
        source="""STATE_FIELDS={'状态'}
def normalized(value):return str(value).strip()
def grade(transcript: list, workspace_path: str) -> dict:
    expected={'表':[{'状态':'批准'},{'状态':'取消'}]}
    actual={'表':[dict(row) for row in transcript]}
    known_states={field:{normalized(row.get(field)) for rows in expected.values() for row in rows if field in row} for field in STATE_FIELDS}
    diagnostic={'review_required':[]}
    for rows in actual.values():
        for row in rows:
            for field in STATE_FIELDS.intersection(row):
                value=normalized(row[field])
                if value and value not in known_states[field]:diagnostic['review_required'].append(f'未识别但可能等价的状态：{field}={value}；需依据公开口径复核')
    return {'rows':actual['表'],'overall_score':0.}
"""
        manifest={'identity':{'task_id':RUNTIME.escrow_state_review.TASK},'digests':{'contract_sha256':'synthetic'},'runtime':{'rule_review_profile':GROUP.PROFILE}}
        with patch.object(RUNTIME.escrow_state_review,'matches',return_value=True):
            code,_=GROUP.effective_source(manifest,source,source,None)
        namespace={'_GENERAL_E2E_RULE_REVIEW':RUNTIME.rule_review.worker_configuration('discover',profile=GROUP.PROFILE)}
        exec(compile(code,'<synthetic-grouped-preservation>','exec'),namespace)
        rows=[{'状态':word,'_candidate_location':f'synthetic.xlsx|表|行{i}'} for i,word in enumerate([' 别称','别称 ','别称'],2)]
        original=deepcopy(rows)
        # Discovery and literal retention must leave the original evidence rows intact.
        self.assertEqual(namespace['grade'](rows,'.')['rows'],original)
        self.assertEqual(rows,original)
        contexts=namespace['_GENERAL_E2E_RULE_REVIEW']['observations']
        self.assertEqual(len(contexts),3)
        self.assertTrue(all(len(item['all_occurrence_locations'])==3 for item in contexts.values()))
        namespace['_GENERAL_E2E_RULE_REVIEW']=RUNTIME.rule_review.worker_configuration('apply',
            {key:value['canonical_choice']=='__keep_literal_known_distinct__' for key,value in contexts.items()},profile=GROUP.PROFILE)
        self.assertEqual(namespace['grade'](rows,'.')['rows'],original)
        self.assertEqual(len(namespace['_GENERAL_E2E_RULE_REVIEW']['applied']),3)

    def test_exact_release_text_hashes_accept_only_registered_original_newlines(self):
        row=RELEASE.registry();task=next((REPO_ROOT/'tasks/general_e2e').rglob(row['task_id']+'.md'));_,sections,_=_parse_task_source(task)
        source=_strip_codeblock(sections['Automated Checks']);contract={'task_id':row['task_id'],'automated_checks':source}
        marker=RELEASE.marker(contract,row['contract_sha256'],row['dataset']);self.assertIsNotNone(marker)
        m={'identity':{'task_id':row['task_id']},'digests':{'contract_sha256':row['contract_sha256']},'dataset':row['dataset'],'runtime':{'release_baseline_text_profile':marker}}
        fixed,receipt=RELEASE.effective_source(m,source,source,None);namespace={};exec(compile(fixed,'<exact-release-baseline>','exec'),namespace)
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'reference';ref=row['files'][0]
            raw=(REPO_ROOT/'workspace/general_e2e/02_Office/task_007_release_phase_gate_progression/exec'/ref['path']).read_bytes()
            for content in [raw,raw.replace(b'\n',b'\r\n')]:
                p.write_bytes(content);self.assertTrue(namespace['_ge2e_release_protected_matches'](p,ref['path']))
            p.write_bytes(b'arbitrary\n');self.assertFalse(namespace['_ge2e_release_protected_matches'](p,ref['path']))
        self.assertEqual(len(receipt['original_public_text_identities']),8)
        self.assertEqual(RUNTIME._effective_rule_source({},source),(source,None))

    def test_failed_discovery_requires_exited_owner_and_replays_original_failure_locks(self):
        rule="""STATE_FIELDS={'状态'}
def normalized(value):return value
def grade(transcript: list, workspace_path: str) -> dict:
    actual={'表':[{'状态':'别称','_candidate_location':f'synthetic.xlsx|表|行{i}'} for i in range(10001)]}
    known_states={'状态':{'批准','取消'}}
    diagnostic={'review_required':[]}
    for rows in actual.values():
        for row in rows:
            for field in STATE_FIELDS.intersection(row):
                value=normalized(row[field])
                if value and value not in known_states[field]:diagnostic['review_required'].append(f'未识别但可能等价的状态：{field}={value}；需依据公开口径复核')
    return {'overall_score':1.}
"""
        import contextlib,subprocess,io
        orch=orchtests.ORCHESTRATOR;retire=orch.framework_failure_retirement
        with tempfile.TemporaryDirectory() as folder,contextlib.ExitStack() as stack:
            for module,name,value in [(RUNTIME.rule_review,'matches',False),(RUNTIME.office001_rule_review,'matches',False),
                    (RUNTIME.escrow_state_review,'matches',True)]:stack.enter_context(patch.object(module,name,return_value=value))
            direct=orchtests.GeneralScoringOrchestrationTests()._direct_local_score_command
            def local(lock,args,**kwargs):
                if args[0]=='prepare':
                    output=io.StringIO()
                    with contextlib.redirect_stdout(output):code=orchtests.SCORE_RUNTIME.main(args)
                    if code:raise AssertionError(output.getvalue())
                    return json.loads(output.getvalue())
                if args[0]=='prepare-rule-review':
                    return orchtests.SCORE_RUNTIME.rule_review_runtime.prepare(orchtests.SCORE_RUNTIME,
                        attempt_root=Path(args[args.index('--attempt-root')+1]),runtime_python=Path(sys.executable))
                return direct(lock,args,**kwargs)
            stack.enter_context(patch.object(orch,'_run_score_command',side_effect=local))
            fixture=orchtests.Fixture(Path(folder),task_ids=('task-discovery',),grading_type='hybrid',contract_overrides={'automated_checks':rule})
            root=Path(fixture.initialize()['orchestration_root'])
            # Synthetic legacy-v1 fixture; production manifests are never edited.
            legacy=json.loads((root/'orchestration-state.json').read_text());mp=root/legacy['tasks'][0]['attempt_path']/'attempt-manifest.json'
            document=json.loads(mp.read_text());document['runtime']['rule_review_profile']=RUNTIME.escrow_state_review.PROFILE
            mp.write_text(json.dumps(document),encoding='utf-8');legacy['tasks'][0]['attempt_manifest_sha256']=hashlib.sha256(mp.read_bytes()).hexdigest()
            legacy['queue_digest']=orch._queue_digest(legacy);(root/'orchestration-state.json').write_text(json.dumps(legacy),encoding='utf-8')
            try:
                with self.assertRaises((orch.OrchestrationError,RUNTIME.ScoringRuntimeError,orchtests.SCORE_RUNTIME.ScoringRuntimeError)):
                    orch.run_rule_score_task(root,task_id='task-discovery',runtime_python=Path(sys.executable))
                s=json.loads((root/'orchestration-state.json').read_text());self.assertEqual(s['tasks'][0]['phase'],'RULES_RUNNING')
                original_run=subprocess.run
                def live_owner(argv,**kwargs):
                    return subprocess.CompletedProcess(argv,0,'still alive','') if argv[0]=='ps' else original_run(argv,**kwargs)
                with patch.object(retire.subprocess,'run',side_effect=live_owner):
                    with self.assertRaisesRegex(ValueError,'OWNER_NOT_PROVEN_EXITED'):
                        retire.record(orch,root,task_id='task-discovery',reason='合成发现重复超限保留原失败，不跳过活跃所有者。')
                view=retire.record(orch,root,task_id='task-discovery',reason='已退出发现任务的重复上下文超限，原证据保留，新attempt独立修复。')
                self.assertEqual(view['unscored_count'],1);self.assertEqual(orch.status(root)['unscored_count'],1)
                attempt=root/s['tasks'][0]['attempt_path'];self.assertFalse((attempt/'rule-audit.json').exists());self.assertFalse((attempt/'score.json').exists())
                proof=root/json.loads((root/'orchestration-state.json').read_text())['tasks'][0]['framework_failure']['path']
                before=proof.read_bytes();proof.write_bytes(before+b' ')
                with self.assertRaisesRegex(orch.OrchestrationError,'FRAMEWORK_FAILURE_PROOF_INVALID'):orch.status(root)
            finally:RUNTIME._remove_tree(Path(folder))


if __name__=='__main__':unittest.main()
