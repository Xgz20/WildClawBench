from pathlib import Path
from types import SimpleNamespace
import json,tempfile,unittest
from unittest.mock import patch
from src.e2e import headless_worker as worker

class HeadlessSkillRoutingTests(unittest.TestCase):
 def prepare(self,root,*,grading='hybrid',profile=None,evidence=False,review=False,python=(3,11,18)):
  attempt=root/'attempt';attempt.mkdir();skill=root/'skills/score-general-e2e';skill.mkdir(parents=True)
  (attempt/'attempt-manifest.json').write_text(json.dumps({'paths':{'contract':'contract.json','runtime_lock':'runtime-lock.json'},'runtime':{'business_capability_profile':profile,'rule_review_profile':'review' if review else None}}))
  (attempt/'contract.json').write_text(json.dumps({'grading_type':grading}));(attempt/'runtime-lock.json').write_text(json.dumps({'python':{'major':3,'minor':11}}))
  (root/'skills/orchestrate-general-e2e/scripts').mkdir(parents=True);(root/'skills/orchestrate-general-e2e/scripts/orchestrate_general_e2e.py').write_text('frozen');(root/'skills/orchestrate-general-e2e/skill-metadata.json').write_text('{"version":"frozen"}')
  reader=SimpleNamespace(_score_skill_lock=lambda *a,**k:{'python':{'version':list(python)}},_requires_rule_evidence=lambda a:evidence,PROMPT_PROTOCOL='v8',needs_browser_preflight=lambda *a:False,_prompt_text=lambda *a,**k:json.dumps(k))
  with patch.object(worker,'ROOT',root),patch.object(worker,'orchestration_reader',return_value=reader),patch.object(worker,'cli') as cli:
   result=worker.prepare_judge_input(['/managed/python'],attempt,skill,{'task_id':'task','scoring_attempt_id':'a','model':'judge'})
   return result,[c.args[1] for c in cli.call_args_list]
 def test_zero_weight_evidence_and_review_are_not_skipped(self):
  for grading,evidence,review,expected in [('llm_judge',True,False,['run-rules','prepare-semantics']),('llm_judge',False,False,['prepare-semantics']),('hybrid',False,True,['prepare-rule-review'])]:
   with self.subTest(grading=grading,evidence=evidence,review=review),tempfile.TemporaryDirectory() as d:
    (prompt,metadata),actions=self.prepare(Path(d),grading=grading,evidence=evidence,review=review)
    self.assertEqual(actions,expected);self.assertEqual(metadata['rule_evidence_required'],evidence);self.assertEqual(metadata['rule_review_required'],review);self.assertIn('CLI',prompt)
 def test_aggregation_runtime_mismatch_stops_before_any_worker_or_judge(self):
  with tempfile.TemporaryDirectory() as d,self.assertRaisesRegex(RuntimeError,'AGGREGATION_SCORING_PYTHON_MISMATCH'):
   self.prepare(Path(d),profile='independent-business-capability/v2',python=(3,12,16))
