"""H027 deterministic checks; substantive facts and explanations require Judge.

Entry point is the General E2E core's grade(transcript, workspace_path).
The independent network acquisition runs before this offline rule.
"""
from pathlib import Path
import hashlib
import json
import math
import os
import re
import runpy

def mean(values):
    values=list(values)
    return sum(bool(x) if isinstance(x,bool) else x for x in values)/len(values) if values else 0.

def grade(transcript, workspace_path, **kwargs):
    root=Path(workspace_path).resolve();gt=root/'gt'
    def load(name):
        try:return json.loads((gt/name).read_text(encoding='utf-8'))
        except (OSError,ValueError,UnicodeError) as exc:raise RuntimeError('H027 private material missing/invalid: '+name) from exc
    binding=load('scoring_contract.json')
    for name,digest in binding['private_sha256'].items():
        path=gt/name
        if not path.is_file() or path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
            raise RuntimeError('H027 private material drift: '+name)
    contract=load('runtime_contract.json');answer=load('artifact_contract.json');expected=load('expected.json');protected=load('protected_sha256.json')
    if expected.get('status')!='TWO_INDEPENDENT_MODEL_SOURCE_READS_RECONCILED' or expected.get('candidate_answer_used_for_truth') is not False or expected.get('source_before_reference') is not True:
        raise RuntimeError('H027 independent source oracle invalid')
    if binding.get('grading_type')!='hybrid' or contract.get('semantic_judge_required') is not True:
        raise RuntimeError('H027 hybrid scoring boundary invalid')
    io=runpy.run_path(str(gt/'research_io.py'));office=runpy.run_path(str(gt/'office_runtime.py'))
    if not os.environ.get('GENERAL_E2E_OFFICE_LOCK') or not os.environ.get('GENERAL_E2E_RULE_EVIDENCE_DIR'):
        raise RuntimeError('H027 managed Office/evidence runtime context missing')
    try:lock=json.loads(Path(os.environ['GENERAL_E2E_OFFICE_LOCK']).read_text(encoding='utf-8'))
    except (OSError,ValueError,UnicodeError) as exc:raise RuntimeError('H027 Office runtime lock missing/invalid') from exc
    office['validate_office_lock'](lock)
    evidence=Path(os.environ['GENERAL_E2E_RULE_EVIDENCE_DIR']).resolve()
    if evidence==root or root in evidence.parents:
        raise RuntimeError('H027 derived evidence must remain outside frozen candidate Workspace')
    errors={};book=None;original=None;ledger=None;answer_text=None;recalculation=None
    def attempt(name,action):
        try:return action()
        except io['CandidateError'] as exc:errors[name]=str(exc);return None
        except office['OfficeRuntimeError'] as exc:
            if exc.code not in {'OFFICE_INPUT_INVALID','OFFICE_INPUT_LIMIT','OFFICE_ACTIVE_CONTENT_UNSUPPORTED','OFFICE_EXTERNAL_DATA_UNSUPPORTED'}:raise
            errors[name]=str(exc);return None
    def workbook():
        nonlocal original,recalculation
        path=io['candidate_path'](root,'results/findings.xlsx');office['_clean_package'](path.read_bytes())
        original=io['read_book'](path)
        if any(c['formula'] for s in original for c in s['cells'].values()):
            recalculation=office['recalculate_xlsx'](path,lock,evidence/'recalculated',timeout_seconds=90)
            result=io['read_book'](recalculation['path']);source={s['name']:s for s in original}
            for sheet in result:
                if sheet['name'] not in source:raise RuntimeError('H027 Office unexpectedly changed worksheet identities')
                for pos,cell in sheet['cells'].items():
                    cell['visible']=cell['visible'] and source[sheet['name']]['cells'].get(pos,{'visible':source[sheet['name']]['state']=='visible'})['visible']
            return result
        return original
    def markdown():
        path=io['candidate_path'](root,'results/answer.md')
        try:return path.read_text(encoding='utf-8')
        except UnicodeError as exc:raise io['CandidateError']('answer.md must be UTF-8') from exc
    book=attempt('workbook',workbook)
    ledger=attempt('ledger',lambda:io['read_ledger'](io['candidate_path'](root,'results/source_ledger.json')))
    answer_text=attempt('answer',markdown)
    manifest,bundle=io['load_bundle'](ledger)
    if ledger is None and manifest['candidate_input_status']=='valid':raise RuntimeError('H027 trusted collector did not bind candidate ledger failure')
    tables,headers=io['extract_tables'](book or [],answer)
    num=io['number'];integer=io['integer'];unknown=io['unknown'];factor=io['unit_factor'];metric=lambda v:io['metric'](v,answer);norm=io['norm'];ids=io['citations'];relation=io['relation']
    metadata={x['report_year']:x for x in expected['observations']}
    def version_unit(year):
        matches=[factor(r.get('unit')) for r in tables['versions'] if integer(r.get('report_year'))==year]
        return matches[0] if len(matches)==1 else None
    minimum={'versions':2,'rankings':12,'shares':5,'revisions':len(expected['common_year_revisions'])}
    table_checks={k:{'header':bool(headers[k]),'row_coverage':len(tables[k])>=minimum[k]} for k in tables}
    # Fields required to be present, with declared unknowns allowed only in the time fields.
    row_checks=[]
    for name,rows in tables.items():
        required=[k for k in answer['xlsx_tables'][name] if k not in {'statistical_year','reserves_statistical_year'}]
        row_checks.extend(all(not unknown(r.get(k)) for k in required) for r in rows)
    sources=ledger.get('sources',[]) if ledger else []
    if not isinstance(sources,list):sources=[]
    source_ids=[];citation_map={};citation_duplicates=set();source_structure=[]
    for s in sources:
        if not isinstance(s,dict):source_structure.append(False);continue
        sid=s.get('source_id');source_ids.append(sid)
        source_structure.append(all(k in s for k in answer['source_ledger']['sources_fields']) and isinstance(sid,str) and bool(sid.strip()) and isinstance(s.get('url'),str) and s.get('access_status') in answer['source_ledger']['access_status'] and isinstance(s.get('citations'),list))
        for citation in s.get('citations',[]) if isinstance(s.get('citations'),list) else []:
            if not isinstance(citation,dict):source_structure.append(False);continue
            cid=citation.get('citation_id')
            source_structure.append(all(k in citation for k in answer['source_ledger']['citation_fields']) and isinstance(cid,str) and bool(cid.strip()) and isinstance(citation.get('locator'),dict) and isinstance(citation.get('quote'),str))
            if isinstance(cid,str):
                if cid in citation_map:citation_duplicates.add(cid)
                citation_map[cid]=(sid,citation)
    searches=ledger.get('searches') if ledger else None
    search_shape=isinstance(searches,list) or isinstance(searches,str) and unknown(searches)
    if isinstance(searches,list):
        search_shape=all(isinstance(x,dict) and any(k in x for k in ('query','navigation','navigation_condition')) and 'observed_at' in x and isinstance(x.get('candidate_source_ids'),list) for x in searches)
    ledger_shape=bool(ledger and all(k in ledger for k in answer['source_ledger']['top']) and isinstance(ledger.get('sources'),list) and search_shape and len(source_ids)==len(set(str(x) for x in source_ids)) and not citation_duplicates)
    record_score=.5*mean(x for checks in table_checks.values() for x in checks.values())+.2*mean(row_checks)+.3*mean([ledger_shape,mean(source_structure)])
    time_checks=[];time_details=[]
    for year,truth in metadata.items():
        rows=[r for r in tables['versions'] if integer(r.get('report_year'))==year]
        checks={'unique_version_record':len(rows)==1}
        if len(rows)==1:
            row=rows[0];v=re.search(r'\d+\.\d+',str(row.get('version','')))
            checks.update(version=bool(v and v.group()==truth['version']),publication_date=io['date'](row.get('publication_date'))==truth['first_posted'],revision_date=io['date'](row.get('revision_date'))==truth['revision_date'],latest_production_year=integer(row.get('latest_production_year'))==truth['latest_production_year'],reserves_year_unknown=unknown(row.get('reserves_statistical_year')),reo_unit=factor(row.get('unit')) is not None)
        else:checks.update({k:False for k in ['version','publication_date','revision_date','latest_production_year','reserves_year_unknown','reo_unit']})
        time_checks.extend(checks.values());time_details.append({'report_year':year,'checks':checks})
    scoped=[]
    for name in ['rankings','shares']:
        for row in tables[name]:
            year=integer(row.get('report_year'));m=metric(row.get('metric'));y=row.get('statistical_year')
            # The newer common-year share is explicitly part of the answer contract.
            valid_year=year in metadata and (m=='reserves' and unknown(y) or m=='mine_production' and integer(y) in ({metadata[year]['latest_production_year'],2024} if name=='shares' and year==2026 else {metadata[year]['latest_production_year']}))
            scoped.append(bool(valid_year and (factor(row.get('unit')) is not None if name=='rankings' else version_unit(year) is not None)))
    scoped.extend(integer(r.get('statistical_year'))==2024 and integer(r.get('older_report'))==2025 and integer(r.get('newer_report'))==2026 and factor(r.get('unit')) is not None for r in tables['revisions'])
    share_keys={(integer(r.get('report_year')),metric(r.get('metric')),None if unknown(r.get('statistical_year')) else integer(r.get('statistical_year'))) for r in tables['shares']}
    expected_share_keys={(2025,'mine_production',2024),(2026,'mine_production',2025),(2026,'mine_production',2024),(2025,'reserves',None),(2026,'reserves',None)}
    time_score=.65*mean(time_checks)+.25*mean(scoped)+.1*float(expected_share_keys<=share_keys)
    citation_results={}
    for cid,(sid,citation) in citation_map.items():
        ok,reason=io['resolve_citation'](bundle.get(sid) if isinstance(sid,str) else None,citation)
        if cid in citation_duplicates:ok=False;reason='citation ID duplicated'
        citation_results[cid]={'resolved':ok,'reason':reason,'source_id':sid,'locator':citation.get('locator')}
    used_checks=[]
    for rows in tables.values():
        for row in rows:
            refs=ids(row.get('citation_ids'))
            used_checks.append(bool(refs) and all(c in citation_results and citation_results[c]['resolved'] for c in refs))
    answer_refs=[cid for cid in citation_map if re.search(r'(?<![\w-])'+re.escape(cid)+r'(?![\w-])',answer_text or '')]
    used_checks.append(bool(answer_refs) and all(citation_results[c]['resolved'] for c in answer_refs))
    citation_score=.7*mean(r['resolved'] for r in citation_results.values())+.3*mean(used_checks)
    intact=all((root/name).is_file() and not (root/name).is_symlink() and io['sha'](root/name)==digest for name,digest in protected.items())
    visible=bool(book and all(rows for rows in tables.values()) and all(r['_visible'] for rows in tables.values() for r in rows))
    math_checks=[];math_details=[]
    def close(a,b):return a is not None and b is not None and math.isclose(a,b,rel_tol=1e-7,abs_tol=1e-8)
    def ischina(value):return norm(value) in {'china','中国'}
    def isworld(value):return norm(value) in {'world','worldtotal','世界','全球','世界合计','世界总计'}
    for row in tables['shares']:
        year=integer(row.get('report_year'));m=metric(row.get('metric'));sy=integer(row.get('statistical_year'));f=version_unit(year)
        a,b,share=(num(row.get(k)) for k in ('china_value','world_value','share_value'))
        calc=bool(a is not None and b is not None and b>0 and share is not None and 0<=share<=1 and math.isclose(share,a/b,rel_tol=1e-7,abs_tol=contract['share_absolute_tolerance']))
        worldrel=relation(row.get('world_relation'));sharerel=relation(row.get('share_relation'))
        calc=calc and (worldrel in {'=','approximately_equal'} and sharerel in {'=','approximately_equal'} or worldrel=='>' and sharerel=='<' or worldrel=='<' and sharerel=='>')
        links=[]
        for rank in tables['rankings']:
            if integer(rank.get('report_year'))==year and metric(rank.get('metric'))==m and (unknown(rank.get('statistical_year')) and unknown(row.get('statistical_year')) or integer(rank.get('statistical_year'))==sy) and ischina(rank.get('country')):
                rf=factor(rank.get('unit'));links.append(f is not None and rf is not None and close(a*f if a is not None and f else None,num(rank.get('value'))*rf if num(rank.get('value')) is not None and rf else None))
        if m=='mine_production' and sy==2024:
            for rev in tables['revisions']:
                if ischina(rev.get('country')) or isworld(rev.get('country')):
                    v=num(rev.get('older_value' if year==2025 else 'newer_value'));rf=factor(rev.get('unit'));target=a if ischina(rev.get('country')) else b
                    links.append(f is not None and rf is not None and close(target*f if target is not None and f else None,v*rf if v is not None and rf else None))
        math_checks.append(calc and bool(links) and all(links));math_details.append({'kind':'share','location':row['_location'],'arithmetic':calc,'cross_table_links':links})
    for row in tables['revisions']:
        old,new,delta=(num(row.get(k)) for k in ('older_value','newer_value','delta'))
        ok=close(delta,new-old if new is not None and old is not None else None)
        math_checks.append(ok);math_details.append({'kind':'revision','location':row['_location'],'arithmetic':ok})
    delivery=bool(book is not None and ledger is not None and answer_text and answer_text.strip() and not errors)
    protected_score=float(intact)*(.35*float(delivery)+.25*float(visible)+.4*mean(math_checks))
    scores={'record_contract':record_score,'time_and_scope':time_score,'citation_resolution':citation_score,'protected_delivery':protected_score}
    scores={k:round(float(v),12) for k,v in scores.items()}
    scores['overall_score']=round(sum(scores[k]*w for k,w in binding['checkpoint_weights'].items()),12)
    if any(not 0<=v<=1 for v in scores.values()):raise RuntimeError('H027 score out of bounds')
    evidence.mkdir(parents=True,exist_ok=True)
    report={'schema_version':'h027-rule-observations/v1','scores':scores,'candidate_errors':errors,'input_unchanged':intact,'native_core_visible':visible,'delivery_complete':delivery,'table_structure':table_checks,'table_row_counts':{k:len(v) for k,v in tables.items()},'ledger_structure':ledger_shape,'version_checks':time_details,'scope_checks':scoped,'share_scope_coverage':expected_share_keys<=share_keys,'citation_checks':citation_results,'referenced_citation_checks':used_checks,'arithmetic_checks':math_details,'office_recalculation':recalculation,'source_bundle_manifest_sha256':os.environ['GENERAL_E2E_RESEARCH_SOURCE_BUNDLE_SHA256'],'semantic_boundary':'No semantic score, country ranking truth, substantive numerical/source-support correctness, discovery honesty, same-year vs cross-year explanation, source independence or full visual judgement is inferred from these automatic checks.'}
    with (evidence/'h027-analysis.json').open('x',encoding='utf-8') as handle:
        json.dump(report,handle,ensure_ascii=False,indent=2,default=str);handle.write('\n')
    return scores
