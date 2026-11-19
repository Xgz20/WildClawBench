"""Author regression for v5; frozen observations are not a new Agent/Judge run.

Run with bundled Python -B -X utf8. Writes one validation record in this task's gt.
No source, reference, historical run, mapping or common framework is modified.
"""
from pathlib import Path
from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import patch
import ast, hashlib, io, json, re, subprocess, types, unittest

GT=Path(__file__).resolve().parent
CASE=GT.parent
ROOT=CASE.parents[3]
TASK=ROOT/'tasks/general_e2e/02_Office/02_Office_task_001_multi_source_project_report.md'
MAP=ROOT/'tools/report/data/checkpoint_capability_map7.yaml'
TRIAL=Path('D:/tmp/_evaluation/20261012T021913Z')
PYTHON_PARSER='C:/Python312/python.exe'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def section(text,name):return re.search(r'^## '+re.escape(name)+r'\s*\n(.*?)(?=^## |\Z)',text,re.M|re.S)[1].strip()
TEXT=TASK.read_text(encoding='utf-8')
CODE=re.search(r'```python\s*\n(.*?)\n```',section(TEXT,'Automated Checks'),re.S)[1]
g=types.ModuleType('v5_grader');exec(compile(CODE,str(TASK),'exec'),g.__dict__)
FACTS=load(GT/'independent_facts.json')
CITE=[{'evidence_id':'candidate/project_report.docx','locator':'author fixture, not actual judgment'}]

def baseline():return {k:g.result('pass',1,'Synthetic all-pass arithmetic fixture') for k in g.SPECS}
def atoms():return {'atomic_facts':[dict(fact_id=f'{t["id"]}.{field}',verdict='supported',citations=deepcopy(CITE)) for t in FACTS for field in ['goal','plan','owner','deadline','footnote','qualifier'] if t.get(field)],'unsupported_assertions':[],'citations':deepcopy(CITE)}
def assoc():return dict(association_units=[dict(unit_id=f'{t["id"]}.{field}',present=True,associated=True,locatable=True,citations=deepcopy(CITE)) for t in FACTS for field in g.C2_FAMILIES if field!='qualifier' or t.get(field)],foreign_units=[],citations=deepcopy(CITE))
def unknowns():
    fields=['unknown_preserved_in_related_table','unknown_preserved_in_confirmation_section','source_identified','confirmation_owner_complete']
    items=[]
    for t in FACTS:
        for field in ['status','reason']:
            if t.get(field) is None:
                item=dict(item_id=f'{t["id"] if field=="status" else t["issue"]}.{field}',fabricated=False,reason='Author semantic fixture',citations=deepcopy(CITE))
                item.update({k:True for k in fields});items.append(item)
    return dict(unknown_items=items,citations=deepcopy(CITE))
def visual(*severities):return dict(viewed_pages=['docx/page/1','pdf/page/1'],citations=deepcopy(CITE),defects=[dict(id=f'd{i}',severity=s,impact='Author demonstrated defect fixture',citations=[{'evidence_id':'pdf/page/1','locator':f'defect {i}'}]) for i,s in enumerate(severities)])
def verification(values):return dict(coverage=dict(zip(g.C7_SCOPES,values)),coverage_evidence={k:dict(reason='Author evidence protocol fixture',citations=[{'evidence_id':'raw_trace','locator':'author fixture lines 1-2'}]) for k in g.C7_SCOPES},citations=[{'evidence_id':'raw_trace','locator':'author fixture lines 1-2'}])
def total(key,value):
    scores=baseline();scores[key]=value;return g.aggregate(scores)
def candidate_scores(doc=None):
    if doc is None:return g.rule_scores(TRIAL/'evaluation_candidate',FACTS)[0]
    with patch.object(g,'extract_docx',return_value=doc):return g.rule_scores(TRIAL/'evaluation_candidate',FACTS)[0]
def parsed():
    code='import importlib.util,json,sys; from pathlib import Path; s=importlib.util.spec_from_file_location("parser",sys.argv[1]); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); p=m.parse_task_md(Path(sys.argv[2])); print(json.dumps({k:p[k] for k in ["prompt","rubric_criteria","automated_checks","workspace_path"]},ensure_ascii=False))'
    p=subprocess.run([PYTHON_PARSER,'-B','-X','utf8','-c',code,str(ROOT/'src/utils/task_parser.py'),str(TASK)],check=True,capture_output=True,text=True,encoding='utf-8')
    return json.loads(p.stdout)
def yaml_mapping():
    p=subprocess.run([PYTHON_PARSER,'-B','-X','utf8','-c','import yaml,json,sys; from pathlib import Path; print(json.dumps(yaml.safe_load(Path(sys.argv[1]).read_text(encoding="utf-8"))[sys.argv[2]]))',str(MAP),TASK.stem],check=True,capture_output=True,text=True,encoding='utf-8')
    return json.loads(p.stdout)

class Tests(unittest.TestCase):
    def test_full_score_and_fixed_weights(self):
        a=g.aggregate(baseline());self.assertEqual(a['task_score'],1);self.assertEqual(a['cap_reasons'],[])
        self.assertEqual(g.GROUPS,{'automated':.6,'llm_judge':.4})
        for group in g.GROUPS:self.assertAlmostEqual(sum(v[1] for k,v in g.SPECS.items() if k.startswith(group+'.')),1)
        self.assertEqual(a['applicable_count'],10)
    def test_c3_all_groups_and_no_omission_double_penalty(self):
        a=atoms();b=assoc()
        for x in a['atomic_facts']:
            if x['fact_id'].endswith(('.footnote','.qualifier')):x['verdict']='omitted'
        for x in b['association_units']:
            if x['unit_id'].endswith(('.footnote','.qualifier')):x['present']=False
        self.assertEqual(g.c2_from_review(b,FACTS)['score'],1)
        item=g.c3_from_review(a,FACTS);self.assertEqual(item['score'],0)
        self.assertEqual(total('llm_judge.c3_fidelity',item)['task_score'],.59)
    def test_c3_each_group_boundary(self):
        for field in ['goal','plan','footnote','qualifier']:
            a=atoms()
            for x in a['atomic_facts']:
                if x['fact_id'].endswith('.'+field):x['verdict']='omitted'
            item=g.c3_from_review(a,FACTS);report=total('llm_judge.c3_fidelity',item)
            self.assertEqual(report['task_score_cap'],.59 if field in ['goal','footnote'] else .79)
        a=atoms();a['atomic_facts'][0]['verdict']='omitted'
        self.assertAlmostEqual(g.c3_from_review(a,FACTS)['score'],23/24)
    def test_c3_thresholds_and_monotonicity(self):
        scores=[]
        for n in range(25):
            a=atoms();goals=[x for x in a['atomic_facts'] if x['fact_id'].endswith('.goal')]
            for x in goals[:n]:x['verdict']='omitted'
            scores.append(total('llm_judge.c3_fidelity',g.c3_from_review(a,FACTS))['task_score'])
        self.assertTrue(all(a>=b for a,b in zip(scores,scores[1:])))
        self.assertEqual(scores[12],.79);self.assertEqual(scores[13],.59)
    def test_contradiction_and_fabrication_cap(self):
        for field in ['incorrect','unsupported']:
            a=atoms()
            if field=='incorrect':a['atomic_facts'][0]['verdict']='incorrect'
            else:a['unsupported_assertions']=[dict(claim='Unfounded completed rollout',citations=deepcopy(CITE))]
            self.assertEqual(total('llm_judge.c3_fidelity',g.c3_from_review(a,FACTS))['task_score'],.49)
    def test_c3_unresolved_is_not_omission(self):
        a=atoms();a['atomic_facts'][0]['verdict']='undetermined'
        item=g.c3_from_review(a,FACTS);self.assertIsNone(item['score'])
        report=total('llm_judge.c3_fidelity',item);self.assertTrue(report['provisional']);self.assertEqual(report['cap_reasons'],[])
    def test_c4_semantic_only_and_bands(self):
        self.assertNotIn('automated.c4_unknowns',g.SPECS)
        for n,want in enumerate([1,.75,.5,.25,.25,0,0,0,0]):
            u=unknowns()
            for item in u['unknown_items'][:n]:item['confirmation_owner_complete']=False
            self.assertEqual(g.c4_from_review(u,FACTS)['score'],want)
    def test_c4_shared_gap_count_and_fabrication(self):
        u=unknowns();x=u['unknown_items'][0];x['source_identified']=x['confirmation_owner_complete']=False
        self.assertEqual(g.c4_from_review(u,FACTS)['score'],.75)
        x['fabricated']=True
        self.assertEqual(total('llm_judge.c4_no_fabrication',g.c4_from_review(u,FACTS))['task_score'],.49)
    def test_c4_null_and_invalid_inventory(self):
        u=unknowns();u['unknown_items'][0]['source_identified']=None
        self.assertIsNone(g.c4_from_review(u,FACTS)['score'])
        u['unknown_items'].pop()
        with self.assertRaises(ValueError):g.c4_from_review(u,FACTS)
    def test_c4_caps_do_not_scale_capability(self):
        u=unknowns()
        for x in u['unknown_items'][:4]:x['confirmation_owner_complete']=False
        report=total('llm_judge.c4_no_fabrication',g.c4_from_review(u,FACTS))
        self.assertEqual(report['task_score'],.79);self.assertEqual(report['capabilities']['state_awareness']['score'],.625)
        self.assertEqual(report['capabilities']['intent_understanding']['score'],1)
    def test_c6_deductions(self):
        for severity,want in [('cosmetic',1),('minor',.9),('moderate',.75),('major',.4),('critical',0)]:
            self.assertEqual(g.c6_from_review(visual(severity))['score'],want)
        self.assertEqual(g.c6_from_review(visual('major','minor','minor'))['score'],.2)
    def test_c6_caps_and_deduplication(self):
        self.assertEqual(total('llm_judge.c6_readability',g.c6_from_review(visual('major')))['task_score'],.69)
        self.assertEqual(total('llm_judge.c6_readability',g.c6_from_review(visual('critical')))['task_score'],.49)
        v=visual('minor');v['defects']*=2
        with self.assertRaises(ValueError):g.c6_from_review(v)
    def test_c7_partial_credit_and_caps(self):
        for scopes,score,cap in [([1]*5,1,1),([.5,1,.5,1,1],.7,.89),([0]*5,0,.69),([.5]*5,.25,.79)]:
            item=g.c7_from_review(verification(scopes),True,True)
            self.assertAlmostEqual(item['score'],score);self.assertEqual(total('llm_judge.c7_self_verification',item)['task_score_cap'],cap)
    def test_c7_missing_trace_and_actual_evidence(self):
        for available,complete in [(False,False),(True,False)]:self.assertIsNone(g.c7_from_review(verification([1]*5),available,complete)['score'])
        v=verification([1]*5);v['coverage_evidence']['facts']['citations']=[]
        with self.assertRaises(ValueError):g.c7_from_review(v,True,True)
    def test_c2_wrong_binding_foreign_and_sources(self):
        for defect in ['binding','foreign','sources']:
            a=assoc()
            if defect=='binding':a['association_units'][0]['associated']=False
            elif defect=='foreign':a['foreign_units']=[dict(unit_id='YL-001.metrics',claim='foreign assertion',citations=deepcopy(CITE))]
            else:
                for x in a['association_units']:x['locatable']=False
            self.assertEqual(total('llm_judge.c2_source_links',g.c2_from_review(a,FACTS))['task_score_cap'],.69)
    def test_absent_artifacts_and_editability_failure(self):
        for key,value,cap in [('automated.c1_files',0,0),('automated.c1_files',.5,.49),('automated.c5_editability',0,.49),('llm_judge.c1_substance',.5,.59)]:
            item=g.fraction(value,1,'Author fixture');self.assertEqual(total(key,item)['task_score_cap'],cap)
    def test_minimum_cap_not_additive(self):
        s=baseline();s['llm_judge.c6_readability']=g.c6_from_review(visual('major'));s['llm_judge.c7_self_verification']=g.c7_from_review(verification([0]*5),True,True)
        r=g.aggregate(s);self.assertEqual(r['task_score'],.69);self.assertEqual(r['task_score_cap'],.69)
        self.assertGreater(r['uncapped_task_score'],.69)
    def test_all_unresolved_and_uncovered_dimensions(self):
        r=g.aggregate({k:g.result('undetermined',reason='No evidence') for k in g.SPECS})
        self.assertIsNone(r['task_score']);self.assertEqual(r['cap_reasons'],[])
        for dim in ['reasoning_and_decision_making','tool_invocation']:self.assertIsNone(r['capabilities'][dim]['score'])
    def test_reference_rule_content(self):
        s,_=g.rule_scores(GT/'reference',FACTS)
        for k in ['automated.c1_files','automated.c2_task_links','automated.c3_numeric_facts']:self.assertEqual(s[k]['score'],1)
    def test_latest_natural_headers(self):
        s=candidate_scores()
        for k in ['automated.c1_files','automated.c2_task_links','automated.c3_numeric_facts']:self.assertEqual(s[k]['score'],1)
        for title,key in [('验收样本','acceptance_total'),('独立验收样本（条）','acceptance_total'),('未关闭','open_issues')]:self.assertEqual(g.header_fields(title),(key,))
    def test_numeric_wrong_value_caps(self):
        for n,cap in [(1,.79),(6,.59)]:
            d=g.extract_docx(TRIAL/'deliverables/project_report.docx');t=d['tables'][2];col=t['rows'][0].index('计划量(条)')
            for row in t['rows'][1:n+1]:row[col]='999999'
            item=candidate_scores(d)['automated.c3_numeric_facts'];self.assertEqual(total('automated.c3_numeric_facts',item)['task_score_cap'],cap)
    def test_unknown_header_does_not_erase_confirmed_error(self):
        d=g.extract_docx(TRIAL/'deliverables/project_report.docx');t=d['tables'][2]
        t['rows'][1][t['rows'][0].index('计划量(条)')]='999999'
        t['rows'][0][t['rows'][0].index('完成量(条)')]='未支持的新表头'
        item=candidate_scores(d)['automated.c3_numeric_facts'];self.assertIsNone(item['score'])
        r=total('automated.c3_numeric_facts',item);self.assertTrue(r['provisional']);self.assertEqual(r['task_score'],.79)
    def test_reordered_equivalent_tables(self):
        d=g.extract_docx(TRIAL/'deliverables/project_report.docx');d['tables'].reverse()
        for t in d['tables']:t['rows'][1:]=reversed(t['rows'][1:])
        s=candidate_scores(d)
        for k in ['automated.c2_task_links','automated.c3_numeric_facts']:self.assertEqual(s[k]['score'],1)
    def test_actual_parser_and_workspace(self):
        p=parsed();self.assertEqual(p['prompt'],section(TEXT,'Prompt'));self.assertEqual(p['automated_checks'],CODE.strip())
        self.assertEqual(len(p['rubric_criteria']),6)
        criterion=next(x for x in p['rubric_criteria'] if x['key']=='c4_no_fabrication')
        self.assertEqual(criterion['allowed_scores'],[0,.25,.5,.75,1])
        self.assertTrue(Path(p['workspace_path']).is_dir())
    def test_mapping_manifest_and_prompt_unchanged(self):
        self.assertEqual(yaml_mapping(),{k:[v[2]] for k,v in g.SPECS.items() if v[2]})
        m=load(GT/'checkpoint_manifest.json');self.assertEqual(m['rubric_revision'],g.RUBRIC_REVISION)
        self.assertEqual(m['rubric_sha256'],hashlib.sha256(section(TEXT,'LLM Judge Rubric').encode()).hexdigest())
        self.assertEqual(m['automated_checks_sha256'],hashlib.sha256(CODE.encode()).hexdigest())
        self.assertEqual(section(TEXT,'Prompt'),section((TRIAL/'task_snapshot.md').read_text(encoding='utf-8'),'Prompt'))
        for item in load(GT/'material_manifest.json')['files']:self.assertEqual(sha(CASE/'exec'/item['name']),item['sha256'])
    def test_apply_review_c4_and_evidence_gate(self):
        config=dict(g.DEFAULT_JUDGE_CONFIG,availability='ready',independent_calibration_completed=True)
        package=dict(rubric_revision=g.RUBRIC_REVISION,evidence_files=[{'id':'candidate/project_report.docx','path':'fixture.docx'},{'id':'independent_facts.json','path':'fixture_facts.json'}],trace=dict(available=True,complete=True),renders_ready=True,page_ids=[])
        u=unknowns();u.update(status='partial',score=.5)
        for x in u['unknown_items'][:4]:x['confirmation_owner_complete']=False
        review=dict(rubric_revision=g.RUBRIC_REVISION,config_sha256='fixture',evidence_package_sha256='fixture',reviewer='author fixture',independently_calibrated=True,checkpoints={'llm_judge.c4_no_fabrication':u})
        def loader(p):return FACTS if str(p)=='fixture_facts.json' else config
        with patch.object(g,'load',side_effect=loader),patch.object(g,'sha',return_value='fixture'):
            scores={};g.apply_review(scores,review,package,Path('fixture_package.json'),Path('fixture_output'))
            self.assertEqual(scores['llm_judge.c4_no_fabrication']['score'],.25)
            u['unknown_items'][0]['citations'][0]['evidence_id']='invented'
            with self.assertRaisesRegex(ValueError,'Citation'):g.apply_review({},review,package,Path('fixture_package.json'),Path('fixture_output'))
    def test_calibration_gate_not_bypassed(self):
        config=dict(g.DEFAULT_JUDGE_CONFIG)
        review=dict(rubric_revision=g.RUBRIC_REVISION);package=dict(rubric_revision=g.RUBRIC_REVISION)
        with patch.object(g,'load',return_value=config):
            with self.assertRaisesRegex(ValueError,'calibrated'):g.apply_review({},review,package,Path('fixture'),Path('fixture'))
    def test_missing_reports_rule_entrypoint(self):
        with patch.object(Path,'is_file',return_value=False):
            scores,_=g.rule_scores(Path('author_missing_fixture'),FACTS)
        self.assertTrue(all(x['status']=='fail' for x in scores.values()))
    def test_native_probe_unchanged_for_receipt_reuse(self):
        old_code=(TRIAL/'embedded_grader.py').read_text(encoding='utf-8')
        def office_parts(code):
            return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(code).body if isinstance(n,ast.FunctionDef) and n.name in ['native_probe','render_pdf']}
        self.assertEqual(office_parts(CODE),office_parts(old_code))
        def native_script(code):
            return next(ast.literal_eval(n.value) for n in ast.parse(code).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='NATIVE_OFFICE_PS' for t in n.targets))
        self.assertEqual(native_script(CODE),native_script(old_code))
    def test_six_state_run_applies_caps(self):
        # In-memory missing-delivery fixture: exercise run(), no files/app/trace created.
        with patch.object(g,'load',return_value=FACTS),patch.object(g,'save'),patch.object(g,'sha',return_value='fixture'),patch.object(Path,'is_file',return_value=False),patch.object(Path,'exists',return_value=False),patch.object(Path,'is_dir',return_value=False),patch.object(Path,'mkdir'),patch.object(Path,'glob',return_value=iter(())),patch.object(Path,'iterdir',return_value=iter(())):
            report=g.run('author_missing_fixture','author_output_fixture',truth_dir='author_truth_fixture',native=False)
        self.assertEqual(report['task_score'],0)
        self.assertEqual(report['task_score_cap'],0)
        self.assertTrue(report['provisional']) # absent trace leaves C7 unknown, never a fabricated zero.
        self.assertIsNone(report['checkpoints']['llm_judge.c7_self_verification']['score'])

def projection():
    """Same frozen semantic findings, new arithmetic; not a new independent review."""
    review=load(TRIAL/'judge_review.json')['checkpoints'];old=load(TRIAL/'evaluation/single_run_result.json')
    s=candidate_scores()
    s['automated.c5_editability']=deepcopy(old['checkpoints']['automated.c5_editability'])
    s['llm_judge.c1_substance']=g.result(review['llm_judge.c1_substance']['status'],review['llm_judge.c1_substance']['score'],review['llm_judge.c1_substance']['reason'],review['llm_judge.c1_substance']['citations'])
    for key,fn in [('llm_judge.c2_source_links',g.c2_from_review),('llm_judge.c3_fidelity',g.c3_from_review),('llm_judge.c4_no_fabrication',g.c4_from_review)]:s[key]=fn(review[key],FACTS)
    s['llm_judge.c6_readability']=g.c6_from_review(review['llm_judge.c6_readability'])
    trace=load(TRIAL/'trace_receipt.json');s['llm_judge.c7_self_verification']=g.c7_from_review(review['llm_judge.c7_self_verification'],True,trace['complete'])
    return dict(scope='Arithmetic projection from frozen v4 independent judgments and unchanged native receipt. Not a new v5 Agent or semantic Judge run.',source_run=str(TRIAL),source_judge_sha256=sha(TRIAL/'judge_review.json'),historical_task_score=old['task_score'],checkpoints=s,**g.aggregate(s))

def main():
    protected=[TRIAL/name for name in ['task_snapshot.md','raw_trace.jsonl','judge_review.json','evaluation/single_run_result.json','report.md','deliverables/project_report.docx','deliverables/project_report.pdf']]
    before={str(p):sha(p) for p in protected}
    log=io.StringIO();r=unittest.TextTestRunner(stream=log,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    same=all(sha(p)==h for p,h in before.items())
    record=dict(revision=g.RUBRIC_REVISION,utc=datetime.now(timezone.utc).isoformat(),status='pass' if r.wasSuccessful() and same else 'fail',tests_run=r.testsRun,failures=[dict(test=str(t),detail=e) for t,e in r.failures+r.errors],log=log.getvalue(),historical_evidence_unchanged=same,historical_hashes=before,task_sha256=sha(TASK),scope='Author scoring, extraction, protocol and parser validation only',new_agent_trial='not_run',new_semantic_judge='not_run',independent_semantic_calibration='not_performed')
    if r.wasSuccessful():record['frozen_trial_projection']=projection()
    (GT/'evaluator_v5_validation.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(log.getvalue());print(json.dumps({k:record[k] for k in ['status','tests_run','historical_evidence_unchanged']},ensure_ascii=False))
    if 'frozen_trial_projection' in record:print(json.dumps({k:record['frozen_trial_projection'][k] for k in ['historical_task_score','task_score','uncapped_task_score','task_score_cap','group_scores','decidable_coverage']},ensure_ascii=False))
    return 0 if record['status']=='pass' else 1
if __name__=='__main__':raise SystemExit(main())
