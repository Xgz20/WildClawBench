"""Author validation of banded deductions. No Agent/Judge run; frozen scores stay unchanged."""
from pathlib import Path
from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import patch
import ast, hashlib, importlib.util, io, json, unittest

GT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('v6_regression',GT/'validate_evaluator_v6.py')
v6=importlib.util.module_from_spec(spec);spec.loader.exec_module(v6)
old=v6.old;g=old.g;FACTS=old.FACTS;TASK=old.TASK
V6_FUNCTION_HASHES={"sha":"3d6744d313854ed7399df0b5e7098c44345b6c92ff94dd815f2e448dffc055d7","load":"f38265861ffa10f4818f2de2139244cc099e9400ca4a62f49b32c6e2c9ebd9e5","save":"ad76e2558cba33677bf4632985f23b7eace6f921d0aa54baf0d2768c93827186","norm":"e31b46316582b7c2141af29ff3414658a228849075a946f6762a812cb90eada7","result":"550f5f67a65ab0623ccba7f21975d49c1bf832400df0d94d51ed87f637df56f5","fraction":"88d6e35d7c1cfad12bfe1cffbf51b883df5d02db3eb99bab53119a4e1b8a1c5a","extract_docx":"423b1c1825d76e6f016e9647f4b8c31b96aee6bdbf8dece80f43c4340e5320de","identifier_matches":"3b99112d0c4297ec7729adfd3ebfe36d2562816b4971fbb03d98a7f621ee0aa5","header_fields":"4dc0304323e9da17533ed10fa9d375311d6205d47dcb8935cd1f6569786d4770","pair_values":"ce12dc26f229b35e33ccd54b3fb3bb32097171b6edadef9e2fc5f14e639f1a12","rows_from_tables":"2ee58b5c89e2ed74280231c680341bfbf592b8d1984b012729b5c7b35ac889df","field_observations":"37a68b085023ca9821c43a5abdaa509a1bd8d1ee898658be0cd73dbc1c5f15e6","number":"fdae2c86c2164088bd616de244067f8b5c9609ff1dab85f9099b314c43c4ecb2","rule_scores":"32c94d33bf50cdd30ada63de9f5c387b661929304c15657cc23021bf98a622f6","native_probe":"ddcb209e267c08d781cec6d7ef4a8723dee69e56352362c63ca55a76b161caca","render_pdf":"a96669c3810b251c8b7ce545966f864a88f2fc42b83c6845d3f43fbaab16f42c","c2_from_review":"d7af8a25c98df6318c646f9616dee15bf2665719d595843a8a4e75ed15fa5ff7","c4_from_review":"cca40889d4f121a2b5bee9aee287f53037e1da844b1cc929c016e7bac091f077","c6_from_review":"80630a7f4bcdc8414c64195d12dbbc0c82aec9423b5b7a3b6bdb4af5fc98f945","c7_from_review":"16f1cea77e97a2188fc53be2312ce07770d0a5a304ee9e2a44caa8c0ccad8d27","c3_from_review":"44bf6deb2f8fa408479d76f9eeebe89e6cff9f6c8c863db2a842cf3900f27959","task_score_caps":"21a645f70c1dfe72691003b4b9e36270e7792c16e0af5af7df773d9a851c8a53","aggregate":"e65661c4e1b25a9e0a3ef8bf20a751f1409c3f796c0c46c8224e9baccd83b993","apply_review":"0b889b22b0388f02345878c869a5ec4f124a863606a8044b7a6c7f2fc58ea34b","run":"57a6e53c8c48454665091875e5567433759383571217ce4d466681eb58634a01","review_existing":"f7f631516841ea051787e44936a28cc6f9b07caa817840422c820bca8049034a","grade":"f76c8a93b93c8eb435d2081d3c458cb5b17d1cd78eef4a84774ed0f431813eed"}
baseline=old.baseline;total=old.total;load=old.load;sha=old.sha
def deduction(report,c=None):
    if c is None:return report['scheduled_task_score_deduction']
    return sum(x['deduction'] for x in report['deduction_reasons'] if x['checkpoint']==c)
def item_score(key,s):return total(key,g.fraction(s,1,'Author arithmetic fixture'))

class BandedDeductionTests(unittest.TestCase):
    def test_full_score_weights_and_schema(self):
        r=g.aggregate(baseline())
        self.assertEqual(r['task_score'],1);self.assertEqual(deduction(r),0)
        self.assertEqual(r['weighted_task_score'],r['uncapped_task_score'])
        self.assertNotIn('task_score_cap',r);self.assertNotIn('cap_reasons',r)
        self.assertEqual(g.GROUPS,{'automated':.6,'llm_judge':.4})
        for group in g.GROUPS:self.assertAlmostEqual(sum(v[1] for k,v in g.SPECS.items() if k.startswith(group+'.')),1)
        self.assertEqual(r['applicable_count'],10)

    def test_error_bands_and_exact_boundaries(self):
        for n,want in [(0,0),(1,2),(5,2),(6,5),(23,5),(24,10),(120,10)]:
            r=item_score('automated.c3_numeric_facts',(120-n)/120)
            self.assertAlmostEqual(deduction(r),want/100)
        for rate,want in [(0,0),(.049999,2),(.05,5),(.199999,5),(.2,10),(1,10)]:
            r=item_score('automated.c3_numeric_facts',1-rate)
            self.assertAlmostEqual(deduction(r),want/100)

    def test_coverage_band_boundaries(self):
        for key in ['llm_judge.c2_source_links','llm_judge.c3_fidelity']:
            for s,want in [(1,0),(.8,0),(.79999,5),(.5,5),(.49999,10),(0,10)]:
                self.assertAlmostEqual(deduction(item_score(key,s)),want/100)

    def test_c3_real_inventory_coverage_and_c2_omission_dedup(self):
        a=old.atoms();b=old.assoc()
        for x in a['atomic_facts']:
            if x['fact_id'].endswith(('.footnote','.qualifier')):x['verdict']='omitted'
        for x in b['association_units']:
            if x['unit_id'].endswith(('.footnote','.qualifier')):x['present']=False
        s=baseline();s['llm_judge.c3_fidelity']=g.c3_from_review(a,FACTS);s['llm_judge.c2_source_links']=g.c2_from_review(b,FACTS)
        r=g.aggregate(s)
        self.assertEqual(s['llm_judge.c2_source_links']['score'],1)
        self.assertAlmostEqual(r['weighted_task_score'],.9);self.assertAlmostEqual(r['task_score'],.8)
        self.assertEqual([x['checkpoint'] for x in r['deduction_reasons']],['C3'])

    def test_c3_group_coverage_monotonicity(self):
        points=[]
        for n in range(25):
            a=old.atoms();goals=[x for x in a['atomic_facts'] if x['fact_id'].endswith('.goal')]
            for x in goals[:n]:x['verdict']='omitted'
            points.append(total('llm_judge.c3_fidelity',g.c3_from_review(a,FACTS))['task_score'])
        self.assertTrue(all(a>=b for a,b in zip(points,points[1:])))
        self.assertAlmostEqual(points[12],.9);self.assertAlmostEqual(points[-1],.8)

    def test_c3_contradiction_band_overrides_omission_band(self):
        for kind in ['incorrect','unsupported']:
            a=old.atoms()
            if kind=='incorrect':a['atomic_facts'][0]['verdict']='incorrect'
            else:a['unsupported_assertions']=[dict(claim='Unsupported assertion',citations=old.CITE)]
            r=total('llm_judge.c3_fidelity',g.c3_from_review(a,FACTS))
            self.assertAlmostEqual(deduction(r),.15);self.assertEqual(len(r['deduction_reasons']),1)
            self.assertAlmostEqual(r['task_score'],.75)

    def test_c4_incomplete_count_and_fabrication(self):
        for n,want in enumerate([0,0,2,5,5,10,10,10,10]):
            u=old.unknowns()
            for x in u['unknown_items'][:n]:x['confirmation_owner_complete']=False
            r=total('llm_judge.c4_no_fabrication',g.c4_from_review(u,FACTS))
            self.assertAlmostEqual(deduction(r),want/100)
        u=old.unknowns();u['unknown_items'][0]['fabricated']=True
        r=total('llm_judge.c4_no_fabrication',g.c4_from_review(u,FACTS))
        self.assertAlmostEqual(deduction(r),.2);self.assertAlmostEqual(r['task_score'],.76)

    def test_c6_bands_and_duplicate_rejection(self):
        for severity,want in [('cosmetic',0),('minor',0),('moderate',2),('major',10),('critical',20)]:
            r=total('llm_judge.c6_readability',g.c6_from_review(old.visual(severity)))
            self.assertAlmostEqual(deduction(r),want/100)
        v=old.visual('minor');v['defects']*=2
        with self.assertRaises(ValueError):g.c6_from_review(v)
        for s,want in [(.8,0),(.5,2),(.499,10),(0,20)]:
            self.assertAlmostEqual(deduction(item_score('llm_judge.c6_readability',s)),want/100)

    def test_c7_bands_from_actual_protocol(self):
        for values,want in [([1]*5,0),([.5,1,1,1,1],2),([.5,.5,1,1,1],5),([.5]*5,10),([0]*5,15)]:
            r=total('llm_judge.c7_self_verification',g.c7_from_review(old.verification(values),True,True))
            self.assertAlmostEqual(deduction(r),want/100)
        for s,want in [(.8,2),(.5,5),(.499,10),(.001,10),(0,15)]:
            self.assertAlmostEqual(deduction(item_score('llm_judge.c7_self_verification',s)),want/100)

    def test_c1_c5_missing_and_theme_bands(self):
        for k,s,want in [('automated.c1_files',0,100),('automated.c1_files',.5,20),('llm_judge.c1_substance',0,15),('llm_judge.c1_substance',.5,5),('automated.c5_editability',0,15)]:
            r=item_score(k,s);self.assertAlmostEqual(deduction(r),want/100)
            self.assertGreaterEqual(r['task_score'],0)
        self.assertEqual(item_score('automated.c1_files',0)['task_score'],0)

    def test_same_c_rule_and_semantic_only_largest(self):
        s=baseline();s['automated.c3_numeric_facts']=g.fraction(.8,1,'Author arithmetic fixture')
        a=old.atoms();a['atomic_facts'][0]['verdict']='incorrect';s['llm_judge.c3_fidelity']=g.c3_from_review(a,FACTS)
        r=g.aggregate(s);self.assertAlmostEqual(deduction(r),.15);self.assertEqual(len(r['deduction_reasons']),1)
        self.assertGreater(len(r['deduction_reasons'][0]['triggers']),1)

    def test_distinct_checkpoints_add_not_cap(self):
        s=baseline();s['llm_judge.c6_readability']=g.c6_from_review(old.visual('major'))
        s['llm_judge.c7_self_verification']=g.c7_from_review(old.verification([0]*5),True,True)
        r=g.aggregate(s)
        self.assertAlmostEqual(deduction(r),.25)
        self.assertAlmostEqual(r['task_score'],r['weighted_task_score']-.25)
        self.assertAlmostEqual(r['task_score'],.642)

    def test_missing_deliverables_suppress_derivative_penalties(self):
        s={k:g.result('fail',0,'Missing artifact fixture') for k in g.SPECS}
        s['llm_judge.c7_self_verification']=g.result('undetermined',reason='No trace')
        r=g.aggregate(s);self.assertEqual(r['task_score'],0)
        self.assertEqual([x['checkpoint'] for x in r['deduction_reasons']],['C1'])
        self.assertEqual(r['task_score_deduction'],0);self.assertEqual(deduction(r),1)
        s['automated.c1_files']=g.fraction(.5,1,'Author missing-report fixture')
        r=g.aggregate(s);self.assertAlmostEqual(deduction(r),.2)
        s['llm_judge.c7_self_verification']=g.c7_from_review(old.verification([0]*5),True,True)
        self.assertAlmostEqual(deduction(g.aggregate(s)),.35)

    def test_uncertain_not_applicable_and_evaluator_errors_never_charge(self):
        for state in ['undetermined','not_applicable','evaluator_error']:
            r=g.aggregate({k:g.result(state,reason='Author missing evidence') for k in g.SPECS})
            self.assertIsNone(r['task_score']);self.assertEqual(r['deduction_reasons'],[])
            self.assertIsNone(r['task_score_deduction'])
        a=old.atoms();a['atomic_facts'][0]['verdict']='undetermined'
        r=total('llm_judge.c3_fidelity',g.c3_from_review(a,FACTS))
        self.assertTrue(r['provisional']);self.assertEqual(deduction(r),0)

    def test_confirmed_error_survives_other_unknowns(self):
        def edit(d):
            d.tables[3].cell(1,3).text='2502 2852'
            d.tables[3].cell(2,5).text='999/40'
        s,_=v6.fixture(edit);item=s['automated.c3_numeric_facts']
        self.assertIsNone(item['score']);r=total('automated.c3_numeric_facts',item)
        self.assertAlmostEqual(deduction(r),.02);self.assertTrue(r['provisional'])
        for state in ['not_applicable','evaluator_error']:
            item['status']=state
            self.assertEqual(deduction(total('automated.c3_numeric_facts',item)),0)

    def test_real_rule_errors_are_penalized_by_rate(self):
        for n,want in [(1,2),(6,5),(24,10)]:
            d=g.extract_docx(old.TRIAL/'deliverables/project_report.docx');t=d['tables'][2];col=t['rows'][0].index('计划量(条)')
            for row in t['rows'][1:n+1]:row[col]='999999'
            item=old.candidate_scores(d)['automated.c3_numeric_facts']
            self.assertAlmostEqual(deduction(total('automated.c3_numeric_facts',item)),want/100)

    def test_real_compound_errors_and_foreign_ids(self):
        def edit(d):
            t=d.tables[2];r=t.add_row()
            for cell,value in zip(r.cells,['YL-001\n其他项目任务','研发','其他负责人','其他项目目标']):cell.text=value
        item=v6.fixture(edit)[0]['automated.c2_task_links']
        self.assertLess(item['score'],1);self.assertAlmostEqual(deduction(total('automated.c2_task_links',item)),.02)
        for raw in ['2,852\n2,502','999,999\n2,852','-1\n2,852','2502.5\n2852']:
            def change(d):d.tables[3].cell(1,3).text=raw
            item=v6.fixture(change)[0]['automated.c3_numeric_facts']
            self.assertLess(item['score'],1);self.assertAlmostEqual(deduction(total('automated.c3_numeric_facts',item)),.02)

    def test_c2_associations_source_bands_and_same_c_dedup(self):
        for n,want in [(1,2),(6,2),(7,5),(26,5),(27,10)]:
            a=old.assoc()
            for x in a['association_units'][:n]:x['associated']=False
            r=total('llm_judge.c2_source_links',g.c2_from_review(a,FACTS))
            self.assertAlmostEqual(deduction(r),want/100)
        a=old.assoc()
        for x in a['association_units']:x['locatable']=False
        r=total('llm_judge.c2_source_links',g.c2_from_review(a,FACTS))
        self.assertAlmostEqual(deduction(r),.1);self.assertEqual(len(r['deduction_reasons']),1)

    def test_c2_unresolved_locations_are_not_missing(self):
        a=old.assoc();a['association_units'][0]['locatable']=None
        r=total('llm_judge.c2_source_links',g.c2_from_review(a,FACTS))
        self.assertEqual(deduction(r),0);self.assertTrue(r['provisional'])

    def test_capabilities_and_raw_scores_unchanged(self):
        u=old.unknowns()
        for x in u['unknown_items'][:4]:x['confirmation_owner_complete']=False
        s=baseline();s['llm_judge.c4_no_fabrication']=g.c4_from_review(u,FACTS);before=deepcopy(s)
        r=g.aggregate(s)
        with patch.object(g,'task_score_deductions',return_value=[]):control=g.aggregate(s)
        self.assertEqual(s,before);self.assertEqual(r['capabilities'],control['capabilities'])
        self.assertEqual(r['collapsed_checkpoints'],control['collapsed_checkpoints'])
        self.assertEqual(r['capabilities']['state_awareness']['score'],.625)
        for dim in ['reasoning_and_decision_making','tool_invocation']:self.assertIsNone(r['capabilities'][dim]['score'])

    def test_score_monotonicity_and_floor(self):
        for key in ['automated.c3_numeric_facts','llm_judge.c2_source_links','llm_judge.c3_fidelity','llm_judge.c4_no_fabrication','llm_judge.c6_readability','llm_judge.c7_self_verification']:
            scores=[item_score(key,i/100)['task_score'] for i in range(101)]
            self.assertTrue(all(a<=b+1e-12 for a,b in zip(scores,scores[1:])),key)
            self.assertTrue(all(0<=x<=1 for x in scores))
        s={k:g.result('fail',0) for k in g.SPECS}
        self.assertEqual(g.aggregate(s)['task_score'],0)

    def test_six_state_entrypoint_uses_deductions(self):
        with patch.object(g,'load',return_value=FACTS),patch.object(g,'save'),patch.object(g,'sha',return_value='fixture'),patch.object(Path,'is_file',return_value=False),patch.object(Path,'exists',return_value=False),patch.object(Path,'is_dir',return_value=False),patch.object(Path,'mkdir'),patch.object(Path,'glob',return_value=iter(())),patch.object(Path,'iterdir',return_value=iter(())):
            r=g.run('author_missing_fixture','author_output_fixture',truth_dir='author_truth_fixture',native=False)
        self.assertEqual(r['task_score'],0);self.assertEqual(r['score_adjustment'],'banded_deductions')
        self.assertTrue(r['provisional']);self.assertIsNone(r['checkpoints']['llm_judge.c7_self_verification']['score'])

    def test_extraction_semantic_and_native_code_preserved(self):
        code=old.CODE.replace('confirmed errors remain evidence for task-score deductions','confirmed errors remain evidence for task-score caps')
        current={n.name:hashlib.sha256(ast.dump(n,include_attributes=False).encode()).hexdigest() for n in ast.parse(code).body if isinstance(n,ast.FunctionDef)}
        for name,h in V6_FUNCTION_HASHES.items():
            if name not in ['task_score_caps','aggregate']:self.assertEqual(current[name],h,name)
        frozen=old.section((v6.TRIAL/'task_snapshot.md').read_text(encoding='utf-8'),'LLM Judge Rubric')
        current_rubric=old.section(old.TEXT,'LLM Judge Rubric').replace('分数和分档附加扣分由题内函数计算','分数和总分上限由题内函数计算')
        self.assertEqual(current_rubric,frozen)

    def test_projection_frozen_evidence_only(self):
        r=v6.recheck()
        self.assertAlmostEqual(r['weighted_task_score'],.883)
        self.assertAlmostEqual(deduction(r),.12);self.assertAlmostEqual(r['task_score'],.763)
        self.assertEqual(r['decidable_coverage'],1)

REUSE_V5=[
 'test_c4_semantic_only_and_bands','test_c4_null_and_invalid_inventory','test_c6_deductions',
 'test_c7_missing_trace_and_actual_evidence','test_reference_rule_content','test_latest_natural_headers',
 'test_reordered_equivalent_tables','test_actual_parser_and_workspace','test_mapping_manifest_and_prompt_unchanged',
 'test_apply_review_c4_and_evidence_gate','test_calibration_gate_not_bypassed','test_missing_reports_rule_entrypoint',
 'test_native_probe_unchanged_for_receipt_reuse']
REUSE_V6=[
 'test_actual_latest_delivery','test_canonical_identifiers_and_boundaries','test_equivalent_compound_id_cells',
 'test_fullwidth_and_chinese_adjacency','test_id_name_field_order_and_labels',
 'test_shared_or_unrecognized_id_requires_review','test_id_annotations_keep_raw_evidence',
 'test_conflicting_id_columns_are_not_bound_by_first_match','test_supported_pair_headers_and_rejected_detail_pairs',
 'test_numeric_pair_reversed_headers_and_values','test_numeric_pair_explicit_labels_override_display_order',
 'test_pass_fail_counts_and_reverse_order','test_conflicting_repeated_pair_is_penalized',
 'test_column_row_table_order_has_no_effect','test_issue_join_uses_candidate_links_not_truth_order']

def main():
    expected=load(GT/'evaluator_v6_validation.json')['protected_hashes']
    protected=[Path(p) for p in expected]+[GT/n for n in ['validate_evaluator_v5.py','validate_evaluator_v6.py','evaluator_v5_validation.json','evaluator_v6_validation.json']]
    before={str(p):sha(p) for p in protected}
    suite=unittest.TestSuite([old.Tests(n) for n in REUSE_V5]+[v6.CompoundExtractionTests(n) for n in REUSE_V6])
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(BandedDeductionTests))
    log=io.StringIO();r=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    unchanged=all(sha(p)==h for p,h in before.items())
    record=dict(revision=g.RUBRIC_REVISION,utc=datetime.now(timezone.utc).isoformat(),status='pass' if r.wasSuccessful() and unchanged else 'fail',
      tests_run=r.testsRun,failures=[dict(test=str(t),detail=e) for t,e in r.failures+r.errors],log=log.getvalue(),
      protected_hashes=before,protected_files_unchanged=unchanged,task_sha256=sha(TASK),
      scope='Author banded-deduction, extraction, parser and protocol validation; historical cap assertions replaced with band assertions.',
      new_agent_trial='not_run',new_semantic_judge='not_run',independent_semantic_calibration='not_performed')
    if r.wasSuccessful():
        p=v6.recheck();p['scope']='Author arithmetic projection using v6 extraction and frozen v5 semantic/native evidence; not a new Agent/Judge score.'
        record['frozen_delivery_projection']=p
    (GT/'evaluator_v7_validation.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(log.getvalue());print(json.dumps({k:record[k] for k in ['status','tests_run','protected_files_unchanged']}))
    if 'frozen_delivery_projection' in record:
        print(json.dumps({k:p[k] for k in ['task_score','weighted_task_score','task_score_deduction','decidable_coverage']}))
    return 0 if record['status']=='pass' else 1
if __name__=='__main__':raise SystemExit(main())
