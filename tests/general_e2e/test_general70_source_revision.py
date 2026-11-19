from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import ast
import re
from unittest.mock import patch
import os

from eval_general_e2e.datasets.bundle import (compile_dataset, DEFAULT_DEFINITION, GENERAL116_DEFINITION,
    GENERAL70_V2_DEFINITION, dataset_manifest_path, load_manifest_lock, _parse_task_source, _strip_codeblock)
from src.utils.task_parser import parse_task_md as _parse_task_md, normalize_judge_evidence
from eval_general_e2e.datasets.source_history import frozen_v2_task_path
from eval_general_e2e.datasets.layout import load_layout, relocated_task, workspace_for_task

def parse_task_md(path):
    # These regressions exercise the immutable v2 correction profiles.
    return _parse_task_md(frozen_v2_task_path(path))
from tests.general_e2e.test_local_scoring_runtime import RUNTIME

ROOT=Path(__file__).resolve().parents[2]
INFO='01_Information_Search_Organization_task_004_luxun_national_character_source_comparison'


class General70SourceRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest,cls.members=compile_dataset(ROOT,definition=GENERAL70_V2_DEFINITION)

    def test_scope_is_exactly_the_frozen_70_and_other_46_source_is_unchanged(self):
        legacy=load_manifest_lock(dataset_manifest_path('general-custom116-v1'))
        self.assertEqual([t['task_id'] for t in self.manifest['tasks']],[t['task_id'] for t in legacy['tasks'][:70]])
        self.assertEqual(self.manifest['statistics']['category_counts'],{'01_Information_Search_Organization':20,'02_Office':30,'data-analysis':20})
        moves = load_layout(ROOT)["workspace_paths"]
        for task in legacy['tasks'][70:]:
            raw = relocated_task(ROOT, Path(task['source']['task_path'])).read_bytes()
            old = task["source"]["workspace_path"]
            raw = raw.replace(moves[old].encode(), old.encode(), 1)
            self.assertEqual(hashlib.sha256(raw).hexdigest(),task['digests']['task_sha256'])

    def test_historical_60_and_116_locks_are_byte_identical_after_rebuild(self):
        for definition in [DEFAULT_DEFINITION,GENERAL116_DEFINITION]:
            manifest,_=compile_dataset(ROOT,definition=definition)
            self.assertEqual(manifest,load_manifest_lock(dataset_manifest_path(definition.dataset_id)))

    def test_public_prompts_inputs_and_budgets_do_not_change(self):
        old={t['task_id']:t for t in load_manifest_lock(dataset_manifest_path('general-custom116-v1'))['tasks']}
        for task in self.manifest['tasks']:
            previous=old[task['task_id']]
            self.assertEqual(task['digests']['prompt_sha256'],previous['digests']['prompt_sha256'])
            self.assertEqual(task['digests']['workspace_exec_sha256'],previous['digests']['workspace_exec_sha256'])
            self.assertEqual(task['grading_weights'],previous['grading_weights'])

    def test_material_repairs_change_only_the_documented_digest_value(self):
        ledger=json.loads((ROOT/'eval_general_e2e/datasets/audits/general-custom70-v2-source-repairs.json').read_text())
        from eval_general_e2e.datasets.source_history import FrozenSources
        frozen=FrozenSources(ROOT,GENERAL116_DEFINITION.frozen_source_index)
        self.assertEqual(len(ledger['material_repairs']),2)
        for row in ledger['material_repairs']:
            p = ROOT / row['path']
            original = frozen.read_bytes(p)
            workspace, _, relative = row['path'].partition('/gt/')
            current = (workspace_for_task(ROOT, Path(workspace)) / 'gt' / relative).read_bytes()
            self.assertEqual(hashlib.sha256(original).hexdigest(),row['original_file_sha256'])
            self.assertEqual(hashlib.sha256(current).hexdigest(),row['revised_file_sha256'])
            self.assertEqual(original.replace(row['declared_text_sha256_before'].encode(),row['canonical_text_sha256_after'].encode()),current)

    def test_reference_workbooks_pass_raw_grading_after_input_digest_repair(self):
        for token in ['03_Data_Analysis_task_002_','03_Data_Analysis_task_003_']:
            p=next((ROOT/'tasks/general/work').rglob(token+'*.md'));task=parse_task_md(p);scope={}
            exec(compile(task['automated_checks'],'<reference-source-selfcheck>','exec'),scope)
            source=Path(task['workspace_path'])
            with tempfile.TemporaryDirectory() as tmp:
                work=Path(tmp);shutil.copytree(source/'exec',work,dirs_exist_ok=True);shutil.copytree(source/'gt',work/'gt');(work/'results').mkdir()
                for name in re.findall(r'results/([^`\s/]+\.xlsx)',task['prompt']):
                    shutil.copyfile(next((source/'gt').rglob(name)),work/'results'/name)
                actual=scope['grade']([],str(work))
                self.assertEqual(actual['overall_score'],1.)

    def test_cli_consumes_the_same_materialized_rule_source_as_the_skill(self):
        contracts={m.path:json.loads(m.data) for m in self.members if m.path.endswith('/private-scoring/contract.json')}
        for task in self.manifest['tasks']:
            current=parse_task_md(ROOT/task['source']['task_path'])
            contract=contracts[task['bundle']['scoring_contract_path']]
            self.assertEqual(current['automated_checks'],contract['automated_checks'])
            self.assertEqual(current['category'],task['category'])
            self.assertEqual(current['judge_evidence']['semantic_status_profile'],'evidence-aware-v1')
            self.assertEqual(current['judge_evidence'],normalize_judge_evidence(contract['judge_evidence']))
            RUNTIME._parse_semantic_criteria(contract['llm_judge_rubric'],weight_scale=contract.get('semantic_weight_scale',1))

    def test_materialized_repair_chain_is_bound_to_the_current_source(self):
        ledger=json.loads((ROOT/'eval_general_e2e/datasets/audits/general-custom70-v2-source-repairs.json').read_text())
        final={r['task_id']:r for r in ledger['repairs']}
        for tid,row in final.items():
            p=next((ROOT/'tasks/general/work').rglob(tid+'.md'))
            source=parse_task_md(p)['automated_checks']
            self.assertEqual(hashlib.sha256(source.encode()).hexdigest(),row['effective_source_sha256'])

    def test_warranty_prompt_headers_work_without_runtime_profiles(self):
        p=next((ROOT/'tasks/general/work').rglob('02_Office_task_010_*.md'))
        scope={};exec(compile(parse_task_md(p)['automated_checks'],'<materialized-warranty>','exec'),scope)
        for value,key in [('本次金额','current'),('政策责任比例','ratio'),('已追偿','already'),('分摊及合同依据说明','note')]:
            self.assertEqual(scope['header_key'](value),key)

    def test_cli_preserves_authored_continuous_office_scores(self):
        p=next((ROOT/'tasks/general/work').rglob('02_Office_task_001_*.md'))
        rows={r['key']:r for r in parse_task_md(p)['rubric_criteria']}
        for key in ['c2_source_links','c3_fidelity','c6_readability','c7_self_verification']:
            self.assertEqual(rows[key]['allowed_scores'],[])

    def test_reference_index_is_real_exported_and_does_not_invent_yang_evidence(self):
        p=next((ROOT/'tasks/general/work').rglob(INFO+'.md'));task=parse_task_md(p);scope={}
        exec(compile(task['automated_checks'],'<info004-v2>','exec'),scope)
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            prefix = f"tasks/{INFO}/private-scoring/gt/"
            for member in self.members:
                if member.kind == "file" and member.path.startswith(prefix):
                    target = work / "gt" / member.path.removeprefix(prefix)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(member.data)
            trace=[{'role':'assistant','channel':'final','content':'使用已取得段落，其他解释待核验。 https://example.org/source'},
                   {'type':'task_complete','last_agent_message':'使用已取得段落，其他解释待核验。 https://example.org/source'}]
            result=scope['grade'](trace,str(work));self.assertEqual(result['source_link_present'],1.)
            index=json.loads((work/'evaluator_evidence/reference_sources.json').read_text())
            self.assertEqual(len(index['sources']),5)
            self.assertFalse(index['policy']['unavailable_is_failure'])
            for row in index['sources']:
                data=(work/'evaluator_evidence'/row['path']).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(),row['sha256'])
            self.assertEqual({c['status'] for c in index['known_unresolved_claims']},{'evaluator_reference_unavailable'})
            (work/'gt/source_evidence/S2-yang-jingjian.json').write_text('tampered')
            with self.assertRaisesRegex(ValueError,'reference source bytes mismatch'):
                scope['grade'](trace,str(work))

    def test_general_and_cli_share_the_same_claim_unknown_gate(self):
        criteria=[{'key':'scholar_claim_binding','weight':1.,'allowed_scores':[0.,.5,1.]}]
        contract={'judge_evidence':{'claim_review_keys':['scholar_claim_binding']}}
        req={'rubric':{'criteria':criteria},'claim_review_policy':{'profile':'evidence-aware-v1',
            'criterion_keys':['scholar_claim_binding'],'units':[1,2],'unavailable_score':None,'cite_queried_frozen_evidence':True}}
        response={'criteria':[{'key':'scholar_claim_binding','status':'unresolved','score':None,
            'reason':'原文相关段落尚不能核定。','evidence_ids':['evidence-1']}],
            'claim_reviews':{'scholar_claim_binding':[{'unit':i,'claim_id':str(i),'claim':'作者具体观点',
                'status':'evaluator_reference_unavailable','evidence_refs':[]} for i in [1,2]]}}
        RUNTIME._validate_declared_claim_reviews(contract,req,response)
        broken=deepcopy(response);broken['criteria'][0].update(status='judged',score=0)
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError,'CLAIM_REVIEW_INVALID'):
            RUNTIME._validate_declared_claim_reviews(contract,req,broken)

    def test_declared_original_cap_and_non_numeric_diagnostics_are_preserved(self):
        contracts=[json.loads(m.data) for m in self.members if m.path.endswith('/private-scoring/contract.json')]
        cap=next(c for c in contracts if c['task_id'].startswith('02_Office_task_026_'))
        self.assertEqual(cap['rule_result_adapter']['final_total_policy_object_key'],'_score_policy')
        for c in contracts:
            if c['task_id'].startswith(tuple('03_Data_Analysis_task_'+n+'_' for n in ['014','015','016'])):
                self.assertEqual(c['rule_result_adapter']['domain_details_object_key'],'details')

    def test_all_research_answer_extractors_keep_completed_public_delivery(self):
        count=0
        for t in self.manifest['tasks']:
            if t['category']!='01_Information_Search_Organization':continue
            source=parse_task_md(ROOT/t['source']['task_path'])['automated_checks']
            nodes=[n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name in {'_visible_text','_final_answer'}]
            if len(nodes)!=2:continue
            namespace={'hashlib':hashlib,'re':re}
            exec(compile(ast.Module(body=nodes,type_ignores=[]),'<research-answer-fixture>','exec'),namespace)
            trace=[{'type':'task_started'},{'role':'assistant','content':'完整研究结果及来源 https://example.org/paper'},
                   {'role':'assistant','content':'已完成。'},{'type':'task_complete','last_agent_message':'已完成。'}]
            answer,_=namespace['_final_answer'](trace)
            self.assertIn('完整研究结果',answer,t['task_id']);count+=1
        self.assertEqual(count,18)

    def test_required_native_review_and_validity_admissions_keep_new_identity(self):
        contracts={json.loads(m.data)['task_id']:json.loads(m.data) for m in self.members if m.path.endswith('/private-scoring/contract.json')}
        rows={t['task_id']:t for t in self.manifest['tasks']}
        for token,check in [('001_multi_source',RUNTIME.office001_rule_review.matches),('010_contract',RUNTIME.escrow_state_review.matches)]:
            tid=next(k for k in contracts if token in k)
            self.assertTrue(check(contracts[tid],rows[tid]['digests']['scoring_contract_sha256']))
        tid=next(k for k in contracts if '001_hr' in k)
        self.assertTrue(RUNTIME.rule_review.matches(contracts[tid]))
        tid=next(k for k in contracts if '013_spy' in k)
        self.assertEqual(RUNTIME.business_capability.profile_marker(contracts[tid],rows[tid]['digests']['scoring_contract_sha256']),RUNTIME.business_capability.PROFILE)
        registered=RUNTIME.business_capability.general_module().REGISTRY_70_V2
        self.assertEqual(len(registered),15)
        for tid in registered:
            self.assertEqual(RUNTIME.business_capability.profile_marker(contracts[tid],rows[tid]['digests']['scoring_contract_sha256']),'independent-business-capability/v2')
        tid=next(k for k in contracts if '001_multi_source' in k)
        self.assertEqual(RUNTIME.office001_semantic_ranges.marker(contracts[tid],rows[tid]['digests']['scoring_contract_sha256'])['contract_sha256'],rows[tid]['digests']['scoring_contract_sha256'])

    def test_public_input_admissions_reject_other_contracts_and_keep_legacy_registry(self):
        contracts={json.loads(m.data)['task_id']:json.loads(m.data) for m in self.members if m.path.endswith('/private-scoring/contract.json')}
        rows={t['task_id']:t for t in self.manifest['tasks']}
        old=RUNTIME.public_office_profiles.registry()
        self.assertEqual(sum(len(r['files']) for r in old),12)
        for row in old:
            tid=row['task_id'];sha=rows[tid]['digests']['scoring_contract_sha256']
            marker=RUNTIME.public_office_profiles.marker(contracts[tid],sha)
            self.assertIsNotNone(marker,tid)
            self.assertIsNone(RUNTIME.public_office_profiles.marker(contracts[tid],'0'*64))
            manifest={'identity':{'task_id':tid},'digests':{'contract_sha256':sha},
                'dataset':{'id':self.manifest['dataset_id'],'digest':self.manifest['dataset_digest']},
                'runtime':{'public_office_input_profile':marker}}
            RUNTIME.public_office_profiles.effective_source(manifest,contracts[tid]['automated_checks'],contracts[tid]['automated_checks'],None)

    def test_explicit_cli_dataset_selects_exactly_70_and_rejects_unknown_id(self):
        from src.utils.dataset_selection import dataset_task_paths
        manifest,grouped=dataset_task_paths(ROOT,'general-custom70-v2')
        self.assertEqual(sum(map(len,grouped.values())),70)
        self.assertEqual(manifest['dataset_id'],'general-custom70-v2')
        with self.assertRaisesRegex(ValueError,'UNSUPPORTED_CLI_DATASET'):
            dataset_task_paths(ROOT,'general-custom116-v2')

    def test_cli_scope_keeps_data_category_and_dataset_identity(self):
        from eval.run_batch import _task_scope_entry
        p=next((ROOT/'tasks/general/work').rglob('03_Data_Analysis_task_002_*.md'));task=parse_task_md(p)
        task['dataset']={'id':self.manifest['dataset_id'],'digest':self.manifest['dataset_digest']}
        row=_task_scope_entry(task)
        self.assertEqual(row['category'],'data-analysis')
        self.assertEqual(row['source'],'general_e2e')
        self.assertEqual(row['dataset'],task['dataset'])

    def test_cli_rejects_cross_version_output_reuse_before_dispatch(self):
        from src.utils.dataset_selection import require_dataset_output_scope
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'evaluation_scope.json'
            path.write_text(json.dumps({'tasks':[{'task_id':'same-task','dataset':{'id':'general-custom116-v1','digest':'0'*64}}]}))
            with self.assertRaisesRegex(ValueError,'OUTPUT_SCOPE_CONFLICT'):
                require_dataset_output_scope(root,self.manifest)
            path.write_text(json.dumps({'tasks':[{'task_id':'same-task','dataset':{'id':self.manifest['dataset_id'],'digest':self.manifest['dataset_digest']}}]}))
            require_dataset_output_scope(root,self.manifest)

    def test_cli_dataset_namespace_preserves_legacy_configuration(self):
        from eval import run_batch
        from src.utils.cli_args import build_run_batch_parser
        args=build_run_batch_parser('fixture',3).parse_args(['--dataset','general-custom70-v2','--agent-backend','astroncode'])
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);legacy=root/'astroncode';legacy.mkdir();config=legacy/'run_configuration.json';config.write_text('original legacy configuration')
            manifest={'dataset_id':'general-custom70-v2','dataset_digest':'1'*64,'task_count':70}
            with patch.object(run_batch,'OUTPUT_DIR',root),patch.object(run_batch,'parse_run_batch_args',return_value=args),\
                    patch('src.utils.dataset_selection.dataset_task_paths',return_value=(manifest,{})),\
                    patch.object(run_batch,'attach_file_logging') as logging,\
                    patch.object(run_batch,'_build_agent_backend',side_effect=RuntimeError('test-stop-before-model')),\
                    patch.dict(os.environ,{'WILDCLAW_TIMEOUT_MULTIPLIER':'1','WILDCLAW_TIMEOUT_OVERRIDE':''}):
                with self.assertRaisesRegex(RuntimeError,'test-stop-before-model'):run_batch.main()
            self.assertEqual(config.read_text(),'original legacy configuration')
            logging.assert_called_once_with(legacy/'general-custom70-v2/run.log')

    def test_cli_scope_conflict_stops_before_log_or_configuration_writes(self):
        from eval import run_batch
        from src.utils.cli_args import build_run_batch_parser
        args=build_run_batch_parser('fixture',3).parse_args(['--dataset','general-custom70-v2','--agent-backend','astroncode'])
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);unit=root/'astroncode/general-custom70-v2';unit.mkdir(parents=True)
            scope=unit/'evaluation_scope.json';scope.write_text(json.dumps({'tasks':[{'dataset':{'id':'older','digest':'0'*64}}]}));original=scope.read_bytes()
            with patch.object(run_batch,'OUTPUT_DIR',root),patch.object(run_batch,'parse_run_batch_args',return_value=args),\
                    patch('src.utils.dataset_selection.dataset_task_paths',return_value=({'dataset_id':'general-custom70-v2','dataset_digest':'1'*64},{})),\
                    patch.object(run_batch,'attach_file_logging') as logging,patch.object(run_batch,'_build_agent_backend') as backend:
                with self.assertRaisesRegex(ValueError,'OUTPUT_SCOPE_CONFLICT'):run_batch.main()
            logging.assert_not_called();backend.assert_not_called();self.assertEqual(scope.read_bytes(),original)
