from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from eval_general_e2e.datasets.bundle import (compile_dataset, DEFAULT_DEFINITION, GENERAL116_DEFINITION,
    GENERAL70_V2_DEFINITION, dataset_manifest_path, load_manifest_lock, _parse_task_source, _strip_codeblock)
from src.utils.task_parser import parse_task_md, normalize_judge_evidence
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
        for task in legacy['tasks'][70:]:
            self.assertEqual(hashlib.sha256((ROOT/task['source']['task_path']).read_bytes()).hexdigest(),task['digests']['task_sha256'])

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

    def test_cli_consumes_the_same_materialized_rule_source_as_the_skill(self):
        contracts={m.path:json.loads(m.data) for m in self.members if m.path.endswith('/private-scoring/contract.json')}
        for task in self.manifest['tasks']:
            current=parse_task_md(ROOT/task['source']['task_path'])
            contract=contracts[task['bundle']['scoring_contract_path']]
            self.assertEqual(current['automated_checks'],contract['automated_checks'])
            self.assertEqual(current['judge_evidence']['semantic_status_profile'],'evidence-aware-v1')
            self.assertEqual(current['judge_evidence'],normalize_judge_evidence(contract['judge_evidence']))
            RUNTIME._parse_semantic_criteria(contract['llm_judge_rubric'],weight_scale=contract.get('semantic_weight_scale',1))

    def test_materialized_repair_chain_is_bound_to_the_current_source(self):
        ledger=json.loads((ROOT/'eval_general_e2e/datasets/audits/general-custom70-v2-source-repairs.json').read_text())
        final={r['task_id']:r for r in ledger['repairs']}
        for tid,row in final.items():
            p=next((ROOT/'tasks/general_e2e').rglob(tid+'.md'))
            source=parse_task_md(p)['automated_checks']
            self.assertEqual(hashlib.sha256(source.encode()).hexdigest(),row['effective_source_sha256'])

    def test_warranty_prompt_headers_work_without_runtime_profiles(self):
        p=next((ROOT/'tasks/general_e2e').rglob('02_Office_task_010_*.md'))
        scope={};exec(compile(parse_task_md(p)['automated_checks'],'<materialized-warranty>','exec'),scope)
        for value,key in [('本次金额','current'),('政策责任比例','ratio'),('已追偿','already'),('分摊及合同依据说明','note')]:
            self.assertEqual(scope['header_key'](value),key)

    def test_reference_index_is_real_exported_and_does_not_invent_yang_evidence(self):
        p=next((ROOT/'tasks/general_e2e').rglob(INFO+'.md'));task=parse_task_md(p);scope={}
        exec(compile(task['automated_checks'],'<info004-v2>','exec'),scope)
        source=ROOT/'workspace/general_e2e/01_Information_Search_Organization/task_004_luxun_national_character_source_comparison/gt'
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp);shutil.copytree(source,work/'gt')
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
