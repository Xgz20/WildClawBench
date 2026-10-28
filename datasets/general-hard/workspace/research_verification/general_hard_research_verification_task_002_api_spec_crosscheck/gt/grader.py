"""H028 source-first automatic rule. Formal prose judgement remains independent.

General E2E entry point: grade(transcript, workspace_path, **kwargs). The worker
must provide independently acquired sources and a locked Office runtime. No
network access, model calls, answer-derived oracle or candidate writes occur.
"""
from pathlib import Path
import datetime as dt
import hashlib
import json
import os
import re
import runpy

def grade(transcript=None,workspace_path=None,**kwargs):
    if workspace_path is None:raise RuntimeError('H028 workspace_path required')
    root=Path(workspace_path).resolve();gt=root/'gt'
    def load(name):
        try:return json.loads((gt/name).read_text(encoding='utf-8'))
        except (OSError,ValueError,UnicodeError) as exc:raise RuntimeError('H028 private material missing/invalid: '+name) from exc
    binding=load('scoring_contract.json')
    if not isinstance(binding.get('private_sha256'),dict) or not binding['private_sha256']:raise RuntimeError('H028 private bindings missing')
    for name,digest in binding['private_sha256'].items():
        path=gt/name
        if not path.is_file() or path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise RuntimeError('H028 private material drift: '+name)
    contract=load('artifact_contract.json');expected=load('expected.json');snapshot=load('document_snapshot.json');runtime=load('runtime_contract.json');protected=load('protected_sha256.json')
    if expected.get('source_precedes_reference') is not True or expected.get('candidate_answer_used_for_truth') is not False or len(expected.get('facts',{}))!=38 or len(expected.get('signature_vectors',[]))!=3:raise RuntimeError('H028 source-first oracle provenance/shape invalid')
    if binding.get('grading_type')!='hybrid' or runtime.get('semantic_judge_required') is not True:raise RuntimeError('H028 hybrid scoring boundary invalid')
    io=runpy.run_path(str(gt/'api_io.py'));office=runpy.run_path(str(gt/'office_runtime.py'));article=runpy.run_path(str(gt/'api_snapshot.py'));mean=io['mean']
    if not os.environ.get('GENERAL_E2E_OFFICE_LOCK') or not os.environ.get('GENERAL_E2E_RULE_EVIDENCE_DIR'):raise RuntimeError('H028 managed Office/evidence runtime context missing')
    try:lock=json.loads(Path(os.environ['GENERAL_E2E_OFFICE_LOCK']).read_text(encoding='utf-8'))
    except (OSError,ValueError,UnicodeError) as exc:raise RuntimeError('H028 Office runtime lock missing/invalid') from exc
    office['validate_office_lock'](lock)
    evidence=Path(os.environ['GENERAL_E2E_RULE_EVIDENCE_DIR']).resolve()
    if evidence==root or root in evidence.parents:raise RuntimeError('H028 derived evidence must remain outside frozen candidate Workspace')
    errors={};original=None;recalculation=None
    def attempt(name,action):
        try:return action()
        except io['CandidateError'] as exc:errors[name]=str(exc);return None
        except office['OfficeRuntimeError'] as exc:
            if exc.code not in {'OFFICE_INPUT_INVALID','OFFICE_INPUT_LIMIT','OFFICE_ACTIVE_CONTENT_UNSUPPORTED','OFFICE_EXTERNAL_DATA_UNSUPPORTED'}:raise
            errors[name]=str(exc);return None
    def workbook():
        nonlocal original,recalculation
        path=io['candidate_path'](root,'results/api_contract.xlsx');office['_clean_package'](path.read_bytes());original=io['read_book'](path)
        if any(c['formula'] for s in original for c in s['cells'].values()):
            recalculation=office['recalculate_xlsx'](path,lock,evidence/'recalculated',timeout_seconds=90);book=io['read_book'](recalculation['path']);source={s['name']:s for s in original}
            for sheet in book:
                if sheet['name'] not in source:raise RuntimeError('H028 Office unexpectedly changed worksheet identities')
                for pos,cell in sheet['cells'].items():
                    prior=source[sheet['name']]['cells'].get(pos,{'visible':source[sheet['name']]['state']=='visible','editable':True})
                    cell['visible']=cell['visible'] and prior['visible'];cell['editable']=cell['editable'] and prior['editable']
            return book
        return original
    def markdown():
        path=io['candidate_path'](root,'results/integration_revised.md')
        try:return path.read_text(encoding='utf-8')
        except UnicodeError as exc:raise io['CandidateError']('integration_revised.md must be UTF-8') from exc
    book=attempt('workbook',workbook);ledger=attempt('ledger',lambda:io['read_ledger'](io['candidate_path'](root,'results/sources.json')));narrative=attempt('markdown',markdown)
    manifest,bundle=io['load_bundle'](ledger)
    if ledger is None and manifest['candidate_input_status']=='valid':raise RuntimeError('H028 trusted collector did not bind candidate ledger failure')
    identity_checks=[]
    for sid,source in bundle.items():
        # Missing/wrong source is a candidate evidence defect. Only an actually
        # acquired designated main article is authoritative for runtime drift.
        if source.get('status')=='acquired' and snapshot['official_url'] in {source.get('url'),source.get('final_url')}:
            try:identity=article['article_identity'](source['_body'])
            except article['SnapshotError'] as exc:raise RuntimeError('H028 designated main article identity unavailable: '+str(exc)) from exc
            if identity['main_text_sha256']!=snapshot['identity']['main_text_sha256']:raise RuntimeError('H028 designated main article content drift')
            identity_checks.append({'source_id':sid,'identity':identity,'matched':True})
    extracted=attempt('workbook_structure',lambda:io['extract_records'](book or [],contract))
    facts,vectors,headers=extracted if extracted is not None else ({f['field_id']:[] for f in contract['field_catalog']},{},[])
    combined={k:io['combine_rows'](rows,k,contract) for k,rows in facts.items()}
    field_checks={field:io['compare_field'](field,combined[field],truth,contract) for field,truth in expected['facts'].items()}
    vector_checks={v['vector_id']:io['compare_vector'](vectors.get(v['vector_id'],[]),v) for v in expected['signature_vectors']}
    business=[field_checks[k]['score'] for k,v in expected['facts'].items() if v['primary_checkpoint']=='business_correctness'];boundary=[field_checks[k]['score'] for k,v in expected['facts'].items() if v['primary_checkpoint']=='boundary_cases']
    if len(business)!=27 or len(boundary)!=11:raise RuntimeError('H028 primary checkpoint allocation drift')
    business_score=.7*mean(business)+.3*mean(v['score'] for v in vector_checks.values());boundary_score=mean(boundary)
    sources=ledger.get('sources',[]) if ledger else [];sources=sources if isinstance(sources,list) else []
    citation_map={};duplicates=set();source_ids=[];source_structure=[];citation_structure=[];official_citations=set();source_metadata=[]
    for source in sources:
        if not isinstance(source,dict):source_structure.append(False);continue
        sid=source.get('source_id');source_ids.append(sid);status=source.get('access_status');items=source.get('citations',[])
        try:dt.datetime.fromisoformat(str(source.get('accessed_at','')).replace('Z','+00:00'));time_valid=True
        except ValueError:time_valid=source.get('accessed_at') is None and isinstance(status,str) and status in {'search_only','unavailable'}
        source_structure.append(all(k in source for k in ('source_id','url','access_status','accessed_at','title','citations')) and isinstance(sid,str) and bool(sid.strip()) and isinstance(source.get('url'),str) and isinstance(status,str) and status in {'read_full','read_excerpt','search_only','unavailable'} and isinstance(items,list) and time_valid and isinstance(source.get('title'),str))
        safe_sid=sid if isinstance(sid,str) else None
        source_metadata.append({'source_id':sid,'candidate':{k:source.get(k) for k in ('url','access_status','accessed_at','title')},'independent_status':bundle.get(safe_sid,{}).get('status')})
        for citation in items if isinstance(items,list) else []:
            if not isinstance(citation,dict):citation_structure.append(False);continue
            cid=citation.get('citation_id');valid=isinstance(cid,str) and bool(cid.strip()) and isinstance(citation.get('locator'),dict) and isinstance(citation.get('quote'),str) and bool(citation['quote'].strip());citation_structure.append(valid)
            if not isinstance(cid,str):continue
            if cid in citation_map:duplicates.add(cid)
            citation_map[cid]=(safe_sid,citation)
            if source.get('url')==snapshot['official_url'] and isinstance(status,str) and status in {'read_full','read_excerpt'}:official_citations.add(cid)
    ledger_structure=bool(ledger is not None and isinstance(ledger.get('sources'),list) and 'limitations' in ledger and len(source_ids)==len(set(str(x) for x in source_ids)) and all(source_structure) and all(citation_structure) and not duplicates)
    citation_checks={}
    for cid,(sid,citation) in citation_map.items():
        ok,reason=io['resolve_citation'](bundle.get(sid),citation)
        if cid in duplicates:ok=False;reason='citation ID duplicated'
        citation_checks[cid]={'resolved':ok,'reason':reason,'source_id':sid,'locator':citation.get('locator')}
    def refs_ok(refs):return bool(refs) and all(c in citation_checks and citation_checks[c]['resolved'] for c in refs)
    reference_checks=[]
    for field,rows in facts.items():reference_checks.append({'field_id':field,'passed':bool(rows) and all(refs_ok(io['citations'](r.get('citation_ids'))) for r in rows)})
    for vector in expected['signature_vectors']:
        rows=vectors.get(vector['vector_id'],[]);reference_checks.append({'vector_id':vector['vector_id'],'passed':bool(rows) and all(refs_ok(io['citations'](r.get('citation_ids'))) for r in rows)})
    # Markdown structure has no prose-fact or keyword scoring. Blocks around
    # explicit L identifiers need associated field and citation identifiers.
    narrative=narrative or '';occurrences=list(re.finditer(r'(?<![\w-])L(?:0[1-9]|1[0-2])(?!\d)',narrative));issue_checks=[]
    for issue in contract['legacy_issues']:
        blocks=[narrative[m.start():occurrences[i+1].start() if i+1<len(occurrences) else len(narrative)] for i,m in enumerate(occurrences) if m.group()==issue['legacy_id']]
        valid=False;matched_fields=[];matched_refs=[]
        for block in blocks:
            fields=[field for field in issue['corrected_by_fields'] if re.search(r'(?<![\w.])'+re.escape(field)+r'(?![\w.])',block)]
            refs=[cid for cid in citation_map if re.search(r'(?<![\w-])'+re.escape(cid)+r'(?![\w-])',block)]
            if fields and refs:valid=True;matched_fields=fields;matched_refs=refs;break
        issue_checks.append({'legacy_id':issue['legacy_id'],'structured':valid,'field_ids':matched_fields,'citation_ids':matched_refs,'citations_resolve':refs_ok(matched_refs)})
    references_score=mean(int(x['passed']) for x in reference_checks+ [{'passed':x['citations_resolve']} for x in issue_checks])
    official_main_bound=bool(identity_checks and any(c in citation_checks and citation_checks[c]['resolved'] for c in official_citations))
    evidence_score=.2*float(ledger_structure)+.3*references_score+.5*mean([mean(int(x['resolved']) for x in citation_checks.values()),float(official_main_bound)])
    input_checks={name:(root/name).is_file() and not (root/name).is_symlink() and io['sha'](root/name)==digest for name,digest in protected.items()};intact=all(input_checks.values())
    all_rows=[r for rows in facts.values() for r in rows]+[r for rows in vectors.values() for r in rows]
    native_visible=bool(book and all_rows and all(r['_visible'] and r['_editable'] for r in all_rows))
    delivery_complete=bool(book is not None and ledger is not None and narrative.strip() and not errors)
    field_structure=[]
    for spec in contract['field_catalog']:
        field=spec['field_id'];rows=facts[field];combined_row=combined[field]
        topics=all(r.get('topic_id') is None or r.get('topic_id')==spec['topic_id'] for r in rows)
        value=combined_row['value'];shape=spec['value_type'];typed=isinstance(value,dict) if shape in {'record','json_object'} else isinstance(value,list) if shape=='record_set' else value is not io['MISSING']
        field_structure.append({'field_id':field,'present':bool(rows),'typed_shape':typed,'topic_consistent':bool(rows and topics),'no_conflicting_duplicates':not combined_row['conflict']})
    identifiers_score=.8*mean(mean(int(x[k]) for k in ('present','typed_shape','topic_consistent','no_conflicting_duplicates')) for x in field_structure)+.2*mean(int(len(vectors.get(v['vector_id'],[]))==1) for v in expected['signature_vectors'])
    structure_score=mean([float(ledger_structure),mean(int(x['structured']) for x in issue_checks),mean(int(not row['metadata_conflicts']) for row in combined.values())])
    delivery_score=float(intact)*(.4*mean([float(delivery_complete),float(native_visible)])+.25*identifiers_score+.2*structure_score+.15*float(intact))
    scores={'business_correctness':business_score,'boundary_cases':boundary_score,'delivery_integrity':delivery_score,'evidence_binding':evidence_score};scores={k:round(float(v),12) for k,v in scores.items()}
    scores['overall_score']=round(sum(scores[k]*w for k,w in binding['checkpoint_weights'].items()),12)
    if any(not 0<=v<=1 for v in scores.values()):raise RuntimeError('H028 automatic score out of bounds')
    report={'schema_version':'h028-rule-observations/v1','scores':scores,'candidate_errors':errors,'input_checks':input_checks,'native_visible_editable':native_visible,'delivery_complete':delivery_complete,'field_checks':field_checks,'signature_checks':vector_checks,'field_structure':field_structure,'markdown_identifier_checks':issue_checks,'ledger_structure':ledger_structure,'source_metadata':source_metadata,'citation_checks':citation_checks,'record_citation_checks':reference_checks,'designated_main_article_checks':identity_checks,'main_article_citation_bound':official_main_bound,'office_recalculation':recalculation,'source_bundle_manifest_sha256':os.environ['GENERAL_E2E_RESEARCH_SOURCE_BUNDLE_SHA256'],'semantic_boundary':'No automatic judgement of actual L01-L12 revision meaning, factual prose, claim-specific citation support, unsupported guarantees, suggested-vs-required explanation, completeness of diagnostics, authorization handoff, no-service-test honesty or source independence. Independent Judge must read full delivered prose and acquired official article.'}
    evidence.mkdir(parents=True,exist_ok=True)
    with (evidence/'h028-observations.json').open('x',encoding='utf-8') as handle:json.dump(report,handle,ensure_ascii=False,indent=2,default=str);handle.write('\n')
    return scores
