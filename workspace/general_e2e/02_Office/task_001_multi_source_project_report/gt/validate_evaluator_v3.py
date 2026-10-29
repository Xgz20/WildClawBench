"""Current evaluator regression (entrypoint filename retained), not a solver run or Judge calibration.

Run bundled Python -B -X utf8 validate_evaluator_v3.py --parser-python C:/Python312/python.exe.
Only writes gt/evaluator_v4_validation.json; reads frozen original trial deliveries.
"""
from pathlib import Path
from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import patch
import argparse
import hashlib
import importlib.util
import io
import json
import shutil
import tempfile
import unittest

GT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('previous_tests', GT / 'validate_realistic_prompt.py')
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
g = old.GRADER
old.REVISION = g.RUBRIC_REVISION
old.EXPECTED_MAPPING_SHA = '66bd038d1ad6f897a701c55d2408b460c113545748e390f7e814b8f15bb9cf42'
FACTS = old.FACTS
TRIAL = Path('D:/tmp/_evaluation/20260923075047Z')
REAL_DOCX = TRIAL / 'deliverables/project_report.docx'
CITE = [{'evidence_id': 'candidate/project_report.docx', 'locator': 'fixture: report table'},
        {'evidence_id': 'independent_facts.json', 'locator': 'fixture: source fact'}]


def score_doc(doc):
    with patch.object(g, 'extract_docx', return_value=doc):
        return g.rule_scores(old.REFERENCE, FACTS)[0]


def c2_fixture():
    return dict(association_units=[dict(unit_id=f'{t["id"]}.{kind}', present=True,
                associated=True, locatable=True, citations=deepcopy(CITE))
                for t in FACTS for kind in g.C2_FAMILIES if kind!='qualifier' or t.get('qualifier')],
                foreign_units=[], citations=deepcopy(CITE))


def c7_fixture(values):
    return dict(coverage=dict(zip(g.C7_SCOPES,values)), citations=[{'evidence_id':'raw_trace','locator':'fixture events'}],
                coverage_evidence={k:dict(reason='Protocol fixture, not actual candidate checking',
                citations=[{'evidence_id':'raw_trace','locator':f'fixture event {i+1}'}]) for i,k in enumerate(g.C7_SCOPES)})


class EvaluatorTests(old.RevisionTests):
    def real_doc(self):
        if not REAL_DOCX.exists():self.skipTest('Frozen real trial delivery absent on this host')
        return g.extract_docx(REAL_DOCX)

    def test_actual_latest_trial_all_rule_fields(self):
        scores=score_doc(self.real_doc())
        for key in ['automated.c2_task_links','automated.c3_numeric_facts']:
            self.assertEqual(scores[key]['score'],1,(key,scores[key]))

    def test_natural_headers_and_acceptance_orders(self):
        for title,value,want in [('验收(通过/不通过)','35/5',(35,40)),
                                 ('验收(通过/不通过)','通过35条 / 不通过5条',(35,40)),
                                 ('验收（不通过／通过）','5/35',(35,40)),
                                 ('验收（总数/通过）','40/35',(35,40)),
                                 ('验收通过数/未通过数','35条/5条',(35,40))]:
            rows=g.rows_from_tables({'tables':[{'table':1,'rows':[
                ['任务编号',title,'计划量（合计）','已登记原因（或未提供）'],['XQ-001',value,'2,852','尚未确认']]}]})
            self.assertEqual((g.number(rows[0]['accepted']),g.number(rows[0]['acceptance_total'])),want)
            self.assertEqual(g.number(rows[0]['planned']),2852)
            self.assertEqual(rows[0]['reason'],'尚未确认')
        self.assertEqual(g.header_fields('计划量(明细/补录)'),())
        self.assertEqual(g.header_fields('完成率'),())

    def test_multiline_merged_headers(self):
        rows=g.rows_from_tables({'tables':[{'table':1,'rows':[
            ['任务ID','验收','验收'],['任务ID','通过','不通过'],['XQ-001','35','5']]}]})
        self.assertEqual(g.number(rows[0]['acceptance_total']),40)

    def test_join_reordered_tables_duplicate_representations(self):
        doc=self.real_doc()
        # Separating every column and reversing all rows/tables preserves ID relations.
        split=[]
        for table in doc['tables']:
            heads=table['rows'][0]
            if '任务 ID' not in heads:continue
            idcol=heads.index('任务 ID')
            for col,title in enumerate(heads):
                if col==idcol:continue
                split.append({'table':len(split)+1,'rows':[['任务 ID',title]]+
                    [[r[idcol],r[col]] for r in reversed(table['rows'][1:])]})
        doc['tables']=list(reversed(split))+deepcopy(split[:3])
        for key in ['automated.c2_task_links','automated.c3_numeric_facts']:
            self.assertEqual(score_doc(doc)[key]['score'],1,key)

    def test_issue_only_table_joins_from_candidate_link(self):
        doc=self.real_doc()
        issue=next(t for t in doc['tables'] if '优先跟进问题 ID' in t['rows'][0])
        doc['tables'].append({'table':99,'rows':[['任务ID','问题ID']]+[[r[0],r[1]] for r in issue['rows'][1:]]})
        issue['rows']=[r[1:] for r in issue['rows']]
        joined=[r for r in g.rows_from_tables(doc) if r.get('_joined_via_issue')]
        self.assertEqual({(r['id'],r['issue']) for r in joined},{(f['id'],f['issue']) for f in FACTS})
        self.assertEqual(score_doc(doc)['automated.c2_task_links']['score'],1)

    def test_wrong_id_conflicting_duplicates_and_contamination(self):
        doc=self.real_doc()
        goals=doc['tables'][0]
        goals['rows'][1][0],goals['rows'][2][0]=goals['rows'][2][0],goals['rows'][1][0]
        self.assertLess(score_doc(doc)['automated.c2_task_links']['score'],1)
        doc=self.real_doc()
        doc['tables'].append({'table':99,'rows':[['任务ID','计划量'],['XQ-001','0']]})
        self.assertAlmostEqual(score_doc(doc)['automated.c3_numeric_facts']['score'],119/120)
        doc=self.real_doc()
        doc['tables'].append({'table':99,'rows':[['任务ID','任务名称'],['YL-001','其他项目']]})
        self.assertLess(score_doc(doc)['automated.c2_task_links']['score'],1)

    def test_hidden_supplement_omission_is_detected(self):
        doc=self.real_doc()
        table=next(t for t in doc['tables'] if '计划量(合计)' in t['rows'][0])
        heads=table['rows'][0]
        for row in table['rows'][1:]:
            for base in ['计划量','完成量']:
                row[heads.index(base+'(合计)')]=row[heads.index(base+'(明细/补录)')].split('/')[0]
        self.assertLess(score_doc(doc)['automated.c3_numeric_facts']['score'],1)

    def test_unsupported_numeric_layout_is_not_zero(self):
        doc=self.real_doc()
        table=next(t for t in doc['tables'] if '计划量(合计)' in t['rows'][0])
        table['rows'][0][table['rows'][0].index('计划量(合计)')]='未支持的特殊口径标题'
        self.assertEqual(score_doc(doc)['automated.c3_numeric_facts']['status'],'undetermined')

    def test_c4_is_semantic_only(self):
        self.assertNotIn('automated.c4_unknowns',g.SPECS)
        self.assertFalse(hasattr(g,'unknown_verdict'))
        self.assertEqual([k for k,v in g.SPECS.items() if v[0]=='C4'],['llm_judge.c4_no_fabrication'])
        self.assertIn('仅由语义评审',old.RUBRIC)
        self.assertIn('不要求固定表头',old.RUBRIC)
        self.assertIn('报告或回答补造任一未知信息',old.RUBRIC)
        for value in ['—','未确认','已完成','0']:
            doc=self.real_doc()
            table=next(t for t in doc['tables'] if '正式状态' in t['rows'][0])
            row=next(r for r in table['rows'][1:] if r[0]=='XQ-004')
            row[table['rows'][0].index('正式状态')]=value
            self.assertEqual(set(score_doc(doc)),{k for k in g.SPECS if k.startswith('automated.')})

    def test_c4_semantic_score_controls_checkpoint_and_ability(self):
        for status,score in [('pass',1),('partial',.5),('fail',0),('undetermined',None)]:
            config,package,review=self.review_fixture()
            review['checkpoints']={'llm_judge.c4_no_fabrication':dict(status=status,score=score,
                reason='Protocol fixture, not a real semantic judgment',citations=deepcopy(CITE))}
            evaluated=self.apply_fixture(config,package,review)
            self.assertEqual(evaluated['llm_judge.c4_no_fabrication']['score'],score)
            scores={k:g.result('pass',1) for k in g.SPECS};scores.update(evaluated)
            combined=g.aggregate(scores)
            self.assertEqual(combined['applicable_count'],10)
            self.assertEqual(combined['collapsed_checkpoints']['C4'],score)
            if score is not None:
                self.assertAlmostEqual(combined['task_score'],1-.4*.1*(1-score))
                self.assertAlmostEqual(combined['capabilities']['state_awareness']['score'],(1+score)/2)
                self.assertEqual(combined['decidable_count'],10)
            else:
                self.assertEqual(combined['decidable_count'],9)
                self.assertEqual(combined['capabilities']['state_awareness']['subcheck_coverage'],2/3)

    def test_c2_omission_only_penalizes_c3(self):
        c2=c2_fixture();c3=old.review_items()
        for unit in c2['association_units']:
            if unit['unit_id'].endswith(('.qualifier','.footnote')):unit['present']=False
        for atom in c3['atomic_facts']:
            if atom['fact_id'].endswith(('.qualifier','.footnote')):atom['verdict']='omitted'
        self.assertEqual(g.c2_from_review(c2,FACTS)['score'],1)
        self.assertAlmostEqual(g.c3_from_review(c3,FACTS)['score'],96/132)
        # A present assertion with no source still loses provenance credit.
        c2['association_units'][0]['locatable']=False
        self.assertAlmostEqual(g.c2_from_review(c2,FACTS)['score'],1-1/(96*2))
        c2['association_units'][0]['associated']=False
        self.assertAlmostEqual(g.c2_from_review(c2,FACTS)['score'],1-2/(96*2))

    def test_c2_inventory_evidence_and_foreign_units(self):
        review=c2_fixture()
        review['foreign_units']=[dict(unit_id='YL-001.metrics',claim='foreign project included',citations=deepcopy(CITE))]
        self.assertAlmostEqual(g.c2_from_review(review,FACTS)['score'],132/133)
        review['association_units'][0]['associated']=None
        self.assertEqual(g.c2_from_review(review,FACTS)['status'],'undetermined')
        review['association_units'].pop()
        with self.assertRaises(ValueError):g.c2_from_review(review,FACTS)

    def c6_fixture(self,severities):
        return dict(viewed_pages=['docx/page/1','pdf/page/1'],citations=deepcopy(CITE),
            defects=[dict(id=f'defect-{i}',severity=v,impact='Fixture effect on readability',
            citations=[{'evidence_id':'pdf/page/1','locator':f'fixture defect {i}'}]) for i,v in enumerate(severities)])

    def test_c6_fine_deductions_and_no_double_count(self):
        for severities,want in [([],1),(['cosmetic'],1),(['minor'],.95),(['moderate'],.85),
                                (['major'],.65),(['minor','moderate'],.8),(['critical'],0),(['major']*3,0)]:
            self.assertAlmostEqual(g.c6_from_review(self.c6_fixture(severities))['score'],want)
        review=self.c6_fixture(['minor']);review['defects']*=2
        with self.assertRaises(ValueError):g.c6_from_review(review)

    def test_c7_states_and_nonvisual_scope(self):
        for n in range(6):
            review=c7_fixture([1]*n+[0]*(5-n))
            self.assertAlmostEqual(g.c7_from_review(review,True,True)['score'],n/5)
        self.assertAlmostEqual(g.c7_from_review(c7_fixture([.5,1,1,1,1]),True,True)['score'],.9)
        for available,complete in [(False,False),(True,False)]:
            self.assertEqual(g.c7_from_review(c7_fixture([1]*5),available,complete)['status'],'undetermined')
        self.assertEqual(g.c7_from_review(c7_fixture([None,1,1,1,1]),True,True)['status'],'undetermined')
        self.assertFalse(g.DEFAULT_JUDGE_CONFIG['candidate_visual_inspection_required'])
        self.assertIn('有意义的两版抽查',old.RUBRIC)
        self.assertIn('只读原材料',old.RUBRIC)

    def test_c7_assertion_only_and_missing_scope_evidence(self):
        review=c7_fixture([0]*5)
        self.assertEqual(g.c7_from_review(review,True,True)['score'],0)
        review=c7_fixture([1]*5);review['coverage_evidence']['sources']['citations']=[]
        with self.assertRaises(ValueError):g.c7_from_review(review,True,True)

    def test_c6_evaluator_visual_coverage_is_separate_from_candidate(self):
        config,package,review=self.review_fixture()
        package['evidence_files'] += [{'id':p,'path':p+'.png'} for p in package['page_ids']]
        item=self.c6_fixture(['minor']);item.update(status='pass',score=1)
        review['checkpoints']['llm_judge.c6_readability']=item
        self.assertAlmostEqual(self.apply_fixture(config,package,review)['llm_judge.c6_readability']['score'],.95)
        item['viewed_pages']=['docx/page/1']
        self.assertEqual(self.apply_fixture(config,package,review)['llm_judge.c6_readability']['status'],'undetermined')
        package['renders_ready']=False
        self.assertEqual(self.apply_fixture(config,package,review)['llm_judge.c6_readability']['status'],'evaluator_error')

    def test_apply_review_computes_c2_c7_and_validates_nested_citations(self):
        config,package,review=self.review_fixture()
        c2=c2_fixture();c2.update(status='pass',score=1)
        c2['association_units'][0]['locatable']=False
        c7=c7_fixture([1,1,1,1,0]);c7.update(status='pass',score=1)
        review['checkpoints']={'llm_judge.c2_source_links':c2,'llm_judge.c7_self_verification':c7}
        scores=self.apply_fixture(config,package,review)
        self.assertAlmostEqual(scores['llm_judge.c2_source_links']['score'],263/264)
        self.assertAlmostEqual(scores['llm_judge.c7_self_verification']['score'],.8)
        c7['coverage_evidence']['sources']['citations'][0]['evidence_id']='invented'
        with self.assertRaisesRegex(ValueError,'Citation'):self.apply_fixture(config,package,review)

    def test_frozen_prompt_and_mapping(self):
        expected='''请根据 `/tmp_workspace/` 下的研发、实施和运营 Word 材料、项目 Excel 工作簿及阶段汇报 PPT，参考报告模板，编制一份《星桥客服平台升级项目阶段工作报告》，用于项目阶段汇报。报告截至 **2026-09-15**，仅涵盖星桥客服平台升级项目（`XQ-CS-26`）。

请完整总结材料中本项目各项任务的目标，按任务整理当前进展、工作量和验收情况，汇总需要优先跟进的问题，以及已确定的后续安排、责任人和时间。保留影响结论的适用范围和前置条件，分清已完成事项与后续安排；材料没有提供或尚未确认的信息不要自行补全，集中列为“待确认事项”。

进展、问题和安排用便于查阅的表格呈现，并用两幅图展示各部门的记录完成比例和未关闭问题数量。附上能定位原文的来源信息，并在交付前复核报告内容、来源及 Word/PDF 的一致性；无法确认或未完成验证的部分请如实说明。

请在 `/tmp_workspace/results/` 下交付 `project_report.docx`，以及由它导出的 `project_report.pdf`。正文和表格应可编辑，排版清晰；模板的结构和样式可以按需要调整。'''
        self.assertEqual(old.PROMPT,expected)
        self.assertEqual(old.sha(old.MAP),old.EXPECTED_MAPPING_SHA)

    def test_actual_deliverables_entrypoint(self):
        if not REAL_DOCX.is_file():self.skipTest('Frozen real trial absent')
        with tempfile.TemporaryDirectory(prefix='.evaluator-v3-',dir=GT) as temp:
            work=Path(temp);(work/'results').mkdir()
            for name in ['project_report.docx','project_report.pdf']:
                shutil.copyfile(TRIAL/'deliverables'/name,work/'results'/name)
            scores,_=g.rule_scores(work,FACTS)
            for key in ['automated.c1_files','automated.c2_task_links','automated.c3_numeric_facts']:
                self.assertEqual(scores[key]['score'],1)
            # Exercise six-state integration; do not claim this fixture is visual validation.
            with patch.object(g,'render_pdf',return_value={'status':'evaluator_error','reason':'render deliberately unavailable in protocol fixture'}):
                report=g.run(work,work/'evaluation',native=False,truth_dir=GT)
            self.assertEqual(report['checkpoints']['automated.c3_numeric_facts']['score'],1)
            self.assertEqual(report['checkpoints']['automated.c5_editability']['status'],'undetermined')
            self.assertIsNone(report['checkpoints']['llm_judge.c7_self_verification']['score'])


    def test_reference_rules(self):
        scores,_=g.rule_scores(old.REFERENCE,FACTS)
        self.assertEqual(set(scores),{k for k in g.SPECS if k.startswith('automated.')})
        for key in ['automated.c1_files','automated.c2_task_links','automated.c3_numeric_facts']:
            self.assertEqual(scores[key]['score'],1)

    def test_weights_and_exact_mapping_key_set(self):
        self.assertEqual(g.GROUPS,{'automated':.6,'llm_judge':.4})
        for group in g.GROUPS:
            self.assertAlmostEqual(sum(v[1] for k,v in g.SPECS.items() if k.startswith(group+'.')),1)
        self.assertEqual([g.SPECS[k][1] for k in ['automated.c1_files','automated.c2_task_links','automated.c3_numeric_facts','automated.c5_editability']],[3/17,4/17,6/17,4/17])
        mappings=old.parser_process('import yaml,json,sys; from pathlib import Path; print(json.dumps(yaml.safe_load(Path(sys.argv[1]).read_text(encoding="utf-8"))[sys.argv[2]]))',old.MAP,old.TASK.stem)
        self.assertEqual(set(mappings),{k for k,v in g.SPECS.items() if v[2]})
        self.assertEqual(mappings['llm_judge.c4_no_fabrication'],['state_awareness'])
        # The only YAML change is removal of this task's retired rule mapping.
        prior=(Path('D:/tmp/_evaluation/20260923092855Z')/'mapping_snapshot.yaml').read_bytes()
        tag=b'02_Office_task_001_multi_source_project_report:'
        prefix,tail=prior.split(tag,1)
        expected=prefix+tag+b''.join(x for x in tail.splitlines(keepends=True) if x.rstrip(b'\r\n')!=b'  automated.c4_unknowns: [state_awareness]')
        self.assertEqual(old.MAP.read_bytes(),expected)

    def test_latest_delivery_no_c4_rule_or_coverage_placeholder(self):
        latest=Path('D:/tmp/_evaluation/20260923092855Z')
        with tempfile.TemporaryDirectory(prefix='.evaluator-v4-',dir=GT) as temp:
            work=Path(temp);(work/'results').mkdir();(work/'gt').mkdir()
            for name in ['project_report.docx','project_report.pdf']:shutil.copyfile(latest/'deliverables'/name,work/'results'/name)
            shutil.copyfile(GT/'independent_facts.json',work/'gt/independent_facts.json')
            scores,_=g.rule_scores(work,FACTS)
            self.assertEqual(set(scores),{'automated.c1_files','automated.c2_task_links','automated.c3_numeric_facts','automated.c5_editability'})
            self.assertTrue(all(scores[k]['score']==1 for k in scores if k!='automated.c5_editability'))
            # Native C5 is unchanged; mock its receipt only to exercise grade's four-key contract.
            with patch.object(g,'native_probe',return_value=(g.result('pass',1,'Protocol fixture; no native validation claimed'),None)):
                numeric=g.grade([],str(work))
            self.assertEqual(numeric,{'c1_files':1,'c2_task_links':1,'c3_numeric_facts':1,'c5_editability':1})
        with tempfile.TemporaryDirectory(prefix='.evaluator-v4-missing-',dir=GT) as temp:
            scores,_=g.rule_scores(temp,FACTS)
            self.assertEqual(len(scores),4)
            self.assertTrue(all(v['status']=='fail' for v in scores.values()))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--parser-python',default='C:/Python312/python.exe')
    args=parser.parse_args();old.PARSER_PYTHON=args.parser_python
    history=[p for root in [old.TRIAL,TRIAL,Path('D:/tmp/_evaluation/20260923092855Z')] for name in ['task_snapshot.md','submitted_prompt.txt','raw_trace.jsonl',
              'evaluation/single_run_result.json','deliverables/project_report.docx','deliverables/project_report.pdf']
              if (p:=root/name).is_file()]
    before={str(p):old.sha(p) for p in history}
    log=io.StringIO();result=unittest.TextTestRunner(stream=log,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(EvaluatorTests))
    unchanged=all(old.sha(Path(p))==h for p,h in before.items())
    record=dict(revision=g.RUBRIC_REVISION,utc=datetime.now(timezone.utc).isoformat(),
        status='pass' if result.wasSuccessful() and unchanged else 'fail',tests_run=result.testsRun,
        failures=[dict(test=str(t),detail=e) for t,e in result.failures+result.errors],
        skipped=[dict(test=str(t),reason=e) for t,e in result.skipped],log=log.getvalue(),
        task_sha256=old.sha(old.TASK),rubric_sha256=hashlib.sha256(old.RUBRIC.encode()).hexdigest(),
        mapping_sha256=old.sha(old.MAP),historical_evidence_unchanged=unchanged,historical_hashes=before,
        scope='Author extraction, scoring arithmetic and evidence-protocol regression; no new solver or semantic/visual review',
        new_agent_trial='not_run',independent_semantic_calibration='not_performed',native_edit_export='not_rerun_unchanged_code')
    if REAL_DOCX.is_file():
        with tempfile.TemporaryDirectory(prefix='.evaluator-v3-',dir=GT) as temp:
            work=Path(temp);(work/'results').mkdir()
            for name in ['project_report.docx','project_report.pdf']:shutil.copyfile(TRIAL/'deliverables'/name,work/'results'/name)
            scores,_=g.rule_scores(work,FACTS)
        record['historical_candidate_rule_recheck']={'candidate_sha256':old.sha(REAL_DOCX),
            'scores':{k:v for k,v in scores.items() if 'c5_' not in k},
            'note':'Parser regression only; original trial results and Judge review are not replaced.'}
    old.save(GT/'evaluator_v4_validation.json',record)
    print(log.getvalue());print(json.dumps({k:record[k] for k in ['status','tests_run','skipped','historical_evidence_unchanged']},ensure_ascii=False))
    return 0 if record['status']=='pass' else 1


if __name__=='__main__':raise SystemExit(main())
