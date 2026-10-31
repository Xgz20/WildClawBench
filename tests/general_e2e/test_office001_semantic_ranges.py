from copy import deepcopy
from pathlib import Path
import json
import tempfile
import unittest

from eval_general_e2e.datasets.bundle import _parse_task_source,_strip_codeblock
from tests.general_e2e.test_local_scoring_runtime import RUNTIME,REPO_ROOT

RANGES=RUNTIME.office001_semantic_ranges


class OriginalOfficeSemanticRangeTests(unittest.TestCase):
    def inputs(self):
        task=next((REPO_ROOT/'tasks/general_e2e').rglob(RANGES.TASK+'.md'))
        _,sections,_=_parse_task_source(task)
        contract={'task_id':RANGES.TASK,'automated_checks':_strip_codeblock(sections['Automated Checks']),
            'llm_judge_rubric':sections['LLM Judge Rubric'].strip()}
        marker=RANGES.marker(contract,RANGES.CONTRACT_SHA)
        self.assertIsNotNone(marker)
        manifest={'identity':{'task_id':RANGES.TASK},'judge':{'protocol':'codex-agent-judge-v1'},
            'digests':{'contract_sha256':RANGES.CONTRACT_SHA},'paths':{'contract':'contract.json'},
            'runtime':{'semantic_score_range_profile':marker}}
        criteria=RUNTIME._parse_semantic_criteria(contract['llm_judge_rubric'])
        return contract,manifest,criteria

    def test_only_four_original_range_criteria_change_and_weights_legacy_stay_exact(self):
        contract,manifest,old=self.inputs();new=RANGES.apply(manifest,contract,old)
        self.assertEqual(RANGES.apply({},contract,old),old)
        self.assertEqual([r['weight'] for r in new],[r['weight'] for r in old])
        for before,after in zip(old,new):
            if before['key'] in RANGES.KEYS:
                self.assertIsNone(after['allowed_scores']);self.assertEqual(after['score_range'],[0.,1.])
                restored=dict(after);restored.pop('score_range');restored['allowed_scores']=before['allowed_scores']
                self.assertEqual(restored,before)
            else:self.assertEqual(before,after)
        for change in [lambda m:m['digests'].update(contract_sha256='0'*64),
                       lambda m:m['judge'].update(protocol='api-judge-v1'),
                       lambda m:m['runtime']['semantic_score_range_profile'].update(range=[0.,2.])]:
            m=deepcopy(manifest);change(m)
            with self.assertRaises(ValueError):RANGES.apply(m,contract,old)

    def test_fractional_original_rubric_values_are_accepted_without_relaxing_other_anchors(self):
        contract,manifest,old=self.inputs();new=RANGES.apply(manifest,contract,old)
        build,evaluate,_,error=RUNTIME._import_semantic_grading_core()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'artifact.txt').write_text('synthetic parser fixture')
            evidence=build([{'type':'candidate_file','path':'artifact.txt'}],base_dir=root)
        reference=evidence['entries'][0]['reference']
        values={'c1_substance':1.,'c2_source_links':.625,'c3_fidelity':1/3,'c4_no_fabrication':.75,
            'c6_readability':.9,'c7_self_verification':.7}
        def run(criteria,overrides=None):
            scores=dict(values,**(overrides or {}))
            return evaluate(criteria,evidence_index=evidence,protocol='codex-agent-judge-v1',evaluator=lambda *_:
                {'criteria':[{'key':r['key'],'status':'judged','score':scores[r['key']],
                    'reason':'合成数据仅验证原比例分的传输契约。','evidence':[reference]} for r in criteria],'notes':''})
        self.assertEqual(run(new)['status'],'completed')
        with self.assertRaises(error):run(old)
        for override in [{'c1_substance':1/3},{'c3_fidelity':1.01},{'c3_fidelity':-.01},{'c3_fidelity':True}]:
            with self.assertRaises(error):run(new,override)

    def test_record_and_archived_request_verification_rederive_exact_original_ranges(self):
        contract,manifest,old=self.inputs();new=RANGES.apply(manifest,contract,old)
        request={'score_range_profile':manifest['runtime']['semantic_score_range_profile'],'rubric':{'criteria':new}}
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'contract.json').write_text(json.dumps(contract),encoding='utf-8')
            RUNTIME._verify_semantic_score_ranges(root,manifest,request)
            bad=deepcopy(request);bad['rubric']['criteria'][0]['allowed_scores']=None
            with self.assertRaises(RUNTIME.ScoringRuntimeError):RUNTIME._verify_semantic_score_ranges(root,manifest,bad)
            legacy=deepcopy(manifest);legacy['runtime']={}
            RUNTIME._verify_semantic_score_ranges(root,legacy,{'rubric':{'criteria':old}})
            with self.assertRaises(RUNTIME.ScoringRuntimeError):RUNTIME._verify_semantic_score_ranges(root,legacy,request)


if __name__=='__main__':unittest.main()
