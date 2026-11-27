from pathlib import Path
from types import SimpleNamespace
import json,os,tempfile,unittest
from unittest.mock import Mock,patch
from src.e2e import headless_worker as worker

class HeadlessSkillRoutingTests(unittest.TestCase):
 def prepare(self,root,*,grading='hybrid',profile=None,evidence=False,review=False,python=(3,11,18),browser=None,browser_probe=None):
  attempt=root/'attempt';attempt.mkdir();skill=root/'skills/score-general-e2e';skill.mkdir(parents=True)
  (attempt/'attempt-manifest.json').write_text(json.dumps({'paths':{'contract':'contract.json','runtime_lock':'runtime-lock.json'},'runtime':{'business_capability_profile':profile,'rule_review_profile':'review' if review else None}}))
  (attempt/'contract.json').write_text(json.dumps({'grading_type':grading}));(attempt/'runtime-lock.json').write_text(json.dumps({'python':{'major':3,'minor':11}}))
  (root/'skills/orchestrate-general-e2e/scripts').mkdir(parents=True);(root/'skills/orchestrate-general-e2e/scripts/orchestrate_general_e2e.py').write_text('frozen');(root/'skills/orchestrate-general-e2e/skill-metadata.json').write_text('{"version":"frozen"}')
  reader=SimpleNamespace(_score_skill_lock=lambda *a,**k:{'python':{'version':list(python)}},_requires_rule_evidence=lambda a:evidence,PROMPT_PROTOCOL='v8',needs_browser_preflight=lambda *a:browser is not None,prepare_browser_environment=browser_probe,_prompt_text=lambda *a,**k:json.dumps(k))
  with patch.object(worker,'ROOT',root),patch.object(worker,'orchestration_reader',return_value=reader),patch.object(worker,'cli') as cli,patch.dict(os.environ,{'PLAYWRIGHT_BROWSERS_PATH':str(browser)} if browser is not None else {}):
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
 def test_image_browser_alias_is_resolved_before_frozen_skill_preflight(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);real=root/'runtime/browsers';real.mkdir(parents=True)
   alias=root/'scoring-browsers';alias.symlink_to(real,target_is_directory=True)
   probe=Mock();self.prepare(root,browser=alias,browser_probe=probe)
   self.assertEqual(probe.call_args.args[-1],real.resolve())
   self.assertFalse(probe.call_args.args[-1].is_symlink());self.assertTrue(alias.is_symlink())
 def test_missing_browser_alias_stops_before_frozen_preflight(self):
  with tempfile.TemporaryDirectory() as d:
   alias=Path(d)/'scoring-browsers';alias.symlink_to(Path(d)/'missing')
   probe=Mock()
   with self.assertRaises(FileNotFoundError):self.prepare(Path(d),browser=alias,browser_probe=probe)
   probe.assert_not_called()
 def test_admission_inventory_locks_derived_evidence_but_leaves_query_logs_mutable(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);attempt=root/'attempt';(attempt/'grader-evidence').mkdir(parents=True);(attempt/'semantic').mkdir()
   (attempt/'attempt-manifest.json').write_text('{}');(attempt/'grader-evidence/reference.docx').write_bytes(b'locked derived input')
   (attempt/'semantic/query-log.json').write_text('{}')
   with patch.object(worker,'ROOT',root):files=worker.immutable_inventory(attempt)
   self.assertIn('attempt/grader-evidence/reference.docx',files)
   self.assertNotIn('attempt/semantic/query-log.json',files)
