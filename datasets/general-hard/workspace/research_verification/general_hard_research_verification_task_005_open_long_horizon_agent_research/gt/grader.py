"""H031 answer-free mechanical rubric. Scientific meaning and process truth require independent Judge."""
from __future__ import annotations
import hashlib,json,os,runpy
from pathlib import Path

class TrustedEvidenceError(RuntimeError):pass
WEIGHTS={'record_contract':.2,'time_and_scope':.25,'citation_resolution':.4,'protected_delivery':.15}
def obj(x):return x if isinstance(x,dict) else {}
def arr(x):return x if isinstance(x,list) else []
def string(x):return isinstance(x,str) and bool(x.strip())
def mean(x):
    x=list(x);return sum(x)/len(x) if x else 0.
def fixed_denominators(ledger,coverage=None):
    data=obj(ledger);NE=max(5,len(arr(data.get('entities'))));NP=max(5,len(arr(data.get('publications'))));NC=max(12,len(arr(data.get('claims'))))
    return {'NE':NE,'NP':NP,'NC':NC,'DCAP':5*NE,'DMETA':2*NE+3*NP,'DDATE':NE+2*NP,'NPR':max(1,len(arr(obj(coverage).get('priorities'))))}

def require_formula_office(book):
    if any(c.get('formula') for s in book for c in s.get('cells',{}).values()):
        path=os.environ.get('GENERAL_E2E_OFFICE_LOCK')
        if not path:raise TrustedEvidenceError('H031 formula workbook requires trusted Office lock')
        return path
    return None

def slot_evidence_checks(connected,unasserted=False):
    if not connected:return {'graph':bool(unasserted),'provenance':bool(unasserted),'literal':bool(unasserted),'evidence_state':'unasserted_unknown' if unasserted else 'missing_actual_links'}
    return {'graph':all(c['graph'] and c['shape'] for c in connected),'provenance':all(c['source'] and c['source'].get('status')=='acquired' for c in connected),'literal':all(c['resolution']['resolved'] for c in connected),'evidence_state':'actual_independent_links'}

def weighted_field_evidence(checked,den,key):
    return .45*sum(s[key] for s in checked['capabilities'])/den['DCAP']+.25*sum(s[key] for s in checked['claims'])/den['NC']+.30*sum(s[key] for s in checked['metadata'])/den['DMETA']

def grade(transcript=None,workspace_path=None,**kwargs):
    if not workspace_path:raise TrustedEvidenceError('H031 workspace_path missing')
    gt=Path(__file__).resolve().parent;root=Path(workspace_path).resolve()
    def load(name):
        try:value=json.loads((gt/name).read_text(encoding='utf-8'))
        except (OSError,ValueError,UnicodeError) as exc:raise TrustedEvidenceError('H031 private evaluator material missing/invalid: '+name) from exc
        if not isinstance(value,dict):raise TrustedEvidenceError('H031 private evaluator object required: '+name)
        return value
    binding=load('scoring_contract.json');hashes=binding.get('private_sha256')
    if not isinstance(hashes,dict) or not hashes:raise TrustedEvidenceError('H031 scoring hash bindings missing')
    for name,digest in hashes.items():
        if not isinstance(name,str) or Path(name).name!=name or name=='scoring_contract.json':raise TrustedEvidenceError('H031 unsafe private hash binding')
        path=gt/name
        if not path.is_file() or path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise TrustedEvidenceError('H031 private material drift: '+name)
    contract=load('artifact_contract.json');runtime=load('runtime_contract.json');protected=load('protected_sha256.json')
    if binding.get('checkpoint_weights')!=WEIGHTS or binding.get('automatic_weight')!=.4 or binding.get('semantic_weight')!=.6 or runtime.get('semantic_judge_required') is not True:raise TrustedEvidenceError('H031 hybrid/semantic boundary drift')
    io=runpy.run_path(str(gt/'native_io.py'));office=runpy.run_path(str(gt/'office_runtime.py'));projector=runpy.run_path(str(gt/'source_projection.py'))
    env=os.environ.get('GENERAL_E2E_RULE_EVIDENCE_DIR')
    if not env or Path(env).is_symlink():raise TrustedEvidenceError('H031 managed rule evidence missing/unsafe')
    evidence=Path(env).resolve()
    if any(evidence==p or p in evidence.parents or evidence in p.parents for p in (root,gt)):raise TrustedEvidenceError('H031 derived evidence overlaps candidate/GT')
    evidence.mkdir(parents=True,exist_ok=True);errors={};recalculation=None
    def candidate(name,action):
        try:return action()
        except io['CandidateError'] as exc:errors[name]=str(exc);return None
        except io['TrustedEvidenceError'] as exc:raise TrustedEvidenceError(str(exc)) from exc
    ledger=candidate('ledger',lambda:io['read_ledger'](io['candidate_path'](root,'results/evidence_ledger.json')))
    coverage=candidate('coverage',lambda:io['read_ledger'](io['candidate_path'](root,'results/coverage.json')))
    docx=candidate('report',lambda:io['read_docx'](io['candidate_path'](root,'results/research_report.docx')))
    def workbook():
        nonlocal recalculation
        path=io['candidate_path'](root,'results/capability_matrix.xlsx')
        try:
            office['_clean_package'](path.read_bytes());original=io['read_book'](path)
            if not any(c['formula'] for s in original for c in s['cells'].values()):return original
            lock_path=require_formula_office(original)
            try:lock=json.loads(Path(lock_path).read_text(encoding='utf-8'))
            except (OSError,ValueError,UnicodeError) as exc:raise TrustedEvidenceError('H031 Office lock missing/invalid') from exc
            office['validate_office_lock'](lock);recalculation=office['recalculate_xlsx'](path,lock,evidence/'recalculated',timeout_seconds=60);result=io['read_book'](recalculation['path']);old={s['name']:s for s in original}
            for sheet in result:
                if sheet['name'] not in old:raise TrustedEvidenceError('H031 Office changed worksheet identity')
                for pos,cell in sheet['cells'].items():
                    before=old[sheet['name']]['cells'].get(pos,{'visible':True,'editable':True});cell['visible'] &= before['visible'];cell['editable'] &= before['editable']
                    if cell['formula'] and cell.get('kind')=='e':raise io['CandidateError']('candidate formula recalculates to an error')
            return result
        except office['OfficeRuntimeError'] as exc:
            if exc.code in {'OFFICE_INPUT_INVALID','OFFICE_ACTIVE_CONTENT_UNSUPPORTED','OFFICE_EXTERNAL_DATA_UNSUPPORTED'}:raise io['CandidateError'](str(exc)) from exc
            raise TrustedEvidenceError('H031 trusted Office failure: '+str(exc)) from exc
    book=candidate('matrix',workbook)
    try:manifest,bundle=io['load_bundle'](ledger,ledger_path=root/'results/evidence_ledger.json')
    except io['TrustedEvidenceError'] as exc:raise TrustedEvidenceError(str(exc)) from exc
    if runtime.get('source_acquisition_protocols')!=io['SOURCE_PROTOCOLS'] or manifest.get('bindings',{}).get('policy_sha256')!=io['sha'](gt/'research_source_policy.json'):raise TrustedEvidenceError('H031 collector/policy binding drift')
    if ledger is None and manifest.get('candidate_input_status')=='valid':raise TrustedEvidenceError('H031 collector did not bind invalid candidate ledger')
    bundle_root=Path(os.environ['GENERAL_E2E_RESEARCH_SOURCE_BUNDLE']).resolve()
    if evidence==bundle_root or bundle_root in evidence.parents or evidence in bundle_root.parents:raise TrustedEvidenceError('H031 derived/source overlap')
    derived=[]
    for index,(sid,source) in enumerate(bundle.items(),1):
        if source.get('status')=='candidate_invalid':continue
        if source.get('status')!='acquired':raise TrustedEvidenceError('H031 required source not acquired: '+str(sid))
        try:
            projection=projector['project_source'](source['_body'],source.get('media_type',''),source['_text'])
            projection['attempt_binding']={'source_id':sid,'source_bundle_manifest_sha256':os.environ['GENERAL_E2E_RESEARCH_SOURCE_BUNDLE_SHA256'],'bundle_acquisition_identity':manifest.get('acquisition_identity'),'bundle_bindings':manifest.get('bindings'),'candidate_ledger_sha256':io['sha'](root/'results/evidence_ledger.json') if ledger else None,'rule_source_sha256':io['sha'](gt/'source_projection.py'),'source_acquisition':source.get('_acquisition'),'boundary':'Actual original bytes only; deterministic decoding is no new GET/source or execution'}
            receipt=projector['write_derived_projection'](projection,evidence/'sources',stem='source-'+str(index));derived.append(dict(receipt,source_id=sid,source_acquisition=source.get('_acquisition')))
        except (OSError,ValueError,TypeError,KeyError,UnicodeError) as exc:raise TrustedEvidenceError('H031 trusted source derivation failed: '+sid) from exc
        if projection.get('complete') is not True:raise TrustedEvidenceError('H031 safe source projection unresolved: '+sid+': '+json.dumps(projection.get('errors'),ensure_ascii=False))
        source['_derived']=projection
    data=obj(ledger);cover=obj(coverage);entities=arr(data.get('entities'));pubs=arr(data.get('publications'));claims=arr(data.get('claims'));sources=arr(data.get('sources'));den=fixed_denominators(data,cover);NE,NP,NC,DCAP,DMETA=(den[k] for k in ('NE','NP','NC','DCAP','DMETA'))
    eids=[obj(e).get('entity_id') for e in entities];pids=[obj(p).get('publication_id') for p in pubs];cids=[obj(c).get('claim_id') for c in claims];sids=[obj(s).get('source_id') for s in sources]
    def unique(value,values):return string(value) and values.count(value)==1
    def refs(value,known):return isinstance(value,list) and all(string(v) and v in known for v in value)
    def entity_shape(e):
        e=obj(e);return mean((all(k in e for k in ('entity_id','name','kind','selection_reason','version','as_of','capabilities')),string(e.get('name')),e.get('kind') in ('product','framework'),io['rich'](e.get('selection_reason')),io['rich'](e.get('version')),io['date_shape'](e.get('as_of')),isinstance(e.get('capabilities'),dict) and all(k in e['capabilities'] for k in io['DIMENSIONS'])))
    def publication_shape(p):
        p=obj(p);return mean((all(k in p for k in ('publication_id','title','authors','identifiers','work_identity','selected_report','report_date','version_date','research_question','task_and_budget','findings_and_limits','selection_reason')),string(p.get('title')),io['rich'](p.get('authors')),p.get('identifiers') is None or io['rich'](p.get('identifiers')),io['rich'](p.get('work_identity')),io['rich'](p.get('selected_report')),io['date_shape'](p.get('report_date')),p.get('version_date') is None or io['rich'](p.get('version_date')),all(io['rich'](p.get(k)) for k in ('research_question','task_and_budget','findings_and_limits','selection_reason'))))
    def claim_record_shape(c):
        c=obj(c);topics=c.get('topics');return mean((all(k in c for k in ('claim_id','text','status','topics','entity_ids','publication_ids','evidence_level','conditions','implication')),io['claim_shape'](c)==1,isinstance(topics,list) and bool(topics) and all(isinstance(v,str) and v in io['DIMENSIONS'] for v in topics),io['rich'](c.get('conditions')),io['rich'](c.get('implication'))))
    known_claims=[v for v in cids if string(v)];budget=io['budget_dag'](cover.get('priorities'),known_claims)
    coverage_shape=mean((isinstance(coverage,dict),cover.get('schema_version')=='h031-coverage/v1',all(k in cover for k in ('scope','search_branches','dedup_groups','exclusions','unresolved','priorities')),io['rich'](cover.get('scope')),io['rich'](cover.get('search_branches')),all(isinstance(cover.get(k),list) for k in ('dedup_groups','exclusions','unresolved','priorities')),budget['checks']['all_shapes']))
    def search_shape(s):
        s=obj(s)
        try:aware=s.get('performed_at') is None and string(s.get('unknown_reason')) or io['_get_time'](s.get('performed_at'),'declared performed_at') is not None
        except io['TrustedEvidenceError']:aware=False
        return string(s.get('query_or_navigation')) and string(s.get('outcome')) and bool(aware)
    root_shape=mean((isinstance(ledger,dict),data.get('schema_version')=='h031-evidence-ledger/v1',*[isinstance(data.get(k),list) for k in ('searches','entities','publications','claims','sources')],all(search_shape(s) for s in arr(data.get('searches')))))
    item_shapes=.30*sum(map(entity_shape,entities))/NE+.25*sum(map(publication_shape,pubs))/NP+.35*sum(map(claim_record_shape,claims))/NC+.10*coverage_shape
    id_graph=.3*sum(unique(obj(e).get('entity_id'),eids) for e in entities)/NE+.3*sum(unique(obj(p).get('publication_id'),pids) for p in pubs)/NP+.4*sum(unique(obj(c).get('claim_id'),cids) and refs(obj(c).get('entity_ids'),eids) and refs(obj(c).get('publication_ids'),pids) and bool(obj(c).get('entity_ids') or obj(c).get('publication_ids')) for c in claims)/NC
    view=candidate('matrix_mapping',lambda:io['extract_capability_matrix'](book or [],known_entity_ids=eids)) or {'entities':{},'mappings':[],'conflicts':[]}
    matrix_rows=io['matrix_agreement'](view,entities);native_matrix=.45*sum(r['identity'] for r in matrix_rows)/NE+.55*sum(r['capabilities'] for r in matrix_rows)/NE
    report=io['report_native_checks'](docx,cover);native_report=mean(report[k] for k in ('native_readable_editable','explicit_budget_mirrors_consistent'))
    record_contract=.15*root_shape+.25*item_shapes+.20*id_graph+.25*native_matrix+.15*native_report
    cited=[];all_cids=[]
    for si,s in enumerate(sources):
        for ci,c in enumerate(arr(obj(s).get('citations'))):
            c=obj(c);all_cids.append(c.get('citation_id'));pointers=[];graph=True
            for pointer in arr(c.get('supports_fields')):
                try:io['resolve_pointer'](data,pointer);pointers.append(pointer)
                except io['CandidateError']:graph=False
            graph &= isinstance(c.get('supports_fields'),list) and bool(c['supports_fields']) and len(pointers)==len(c['supports_fields']) and len(set(pointers))==len(pointers)
            source=bundle.get(obj(s).get('source_id') if string(obj(s).get('source_id')) else None)
            try:resolution=io['resolve_citation'](source,c) if source else {'resolved':False,'reason':'candidate source not independently acquired'}
            except io['TrustedEvidenceError'] as exc:raise TrustedEvidenceError(str(exc)) from exc
            cited.append({'source_index':si,'citation_index':ci,'source_id':obj(s).get('source_id'),'citation_id':c.get('citation_id'),'pointers':pointers,'graph':bool(graph),'shape':io['citation_shape'](c),'source':source,'citation':c,'resolution':resolution})
    for c in cited:c['graph'] &= unique(c['citation_id'],all_cids)
    def links(path):return [c for c in cited if any(io['pointer_overlaps'](p,path) for p in c['pointers'])]
    slots={'capabilities':[],'claims':[],'metadata':[]}
    for ei,e in enumerate(entities):
        for dim in io['DIMENSIONS']:slots['capabilities'].append({'path':f'/entities/{ei}/capabilities/{dim}','scope':f'/entities/{ei}','kind':'capability','value':obj(obj(e).get('capabilities')).get(dim)})
        for kind,field in (('identity','name'),('date','as_of')):slots['metadata'].append({'path':f'/entities/{ei}/{field}','scope':f'/entities/{ei}','kind':kind,'value':obj(e).get(field),'record':e})
    for pi,p in enumerate(pubs):
        for kind,field in (('identity','title'),('date','report_date'),('version','version_date')):slots['metadata'].append({'path':f'/publications/{pi}/{field}','scope':f'/publications/{pi}','kind':kind,'value':obj(p).get(field),'record':p})
    for ci,c in enumerate(claims):slots['claims'].append({'path':f'/claims/{ci}','scope':f'/claims/{ci}','kind':'claim','value':c})
    def inspect_slot(slot):
        value=slot['value'];status=obj(value).get('status');unknown=io['version_date_is_unknown'](value) if slot['kind']=='version' else status=='unknown'
        attached=links(slot['scope']) if slot['kind']=='identity' else links(slot['path']);inherited=[]
        if unknown or status=='inference':
            inherited=links(slot['scope'])
            if slot['kind']=='claim':
                for key,ids in (('entities',eids),('publications',pids)):
                    for identity in arr(obj(value).get('entity_ids' if key=='entities' else 'publication_ids')):
                        for index,actual in enumerate(ids):
                            if actual==identity:inherited+=links(f'/{key}/{index}')
        connected=[]
        for c in attached or inherited:
            if c not in connected:connected.append(c)
        unasserted=unknown and (io['claim_shape'](value)==1 if slot['kind'] in ('capability','claim') else io['date_shape'](value) if slot['kind']=='date' else io['rich'](obj(slot.get('record')).get('selected_report')))
        evidence_checks=slot_evidence_checks(connected,unasserted);graph=evidence_checks['graph'];provenance=evidence_checks['provenance'];literal=evidence_checks['literal']
        metadata=bool(graph and provenance and literal)
        if metadata and slot['kind']=='date' and not unknown:metadata=any(io['date_literal_binding'](value,dict(c['resolution'],quote=c['citation'].get('quote')),c['source']) for c in connected)
        if metadata and slot['kind']=='version' and not unknown:metadata=any(io['date_literal_binding'](value,dict(c['resolution'],quote=c['citation'].get('quote')),c['source']) for c in connected)
        return {'path':slot['path'],'kind':slot['kind'],'unknown':bool(unknown),'evidence_state':evidence_checks['evidence_state'],'citation_ids':[c['citation_id'] for c in connected],'graph':float(bool(graph)),'provenance':float(bool(provenance)),'literal':float(bool(literal)),'metadata':float(bool(metadata))}
    checked={group:[inspect_slot(s) for s in rows] for group,rows in slots.items()}
    def E(key):return weighted_field_evidence(checked,den,key)
    metadata_trace=sum(s['metadata'] for s in checked['metadata'])/DMETA
    calendar=[];supported_entity_dates=[];supported_pub_dates=[]
    for group,records,field,counts in (('entities',entities,'as_of',supported_entity_dates),('publications',pubs,'report_date',supported_pub_dates)):
        for index,r in enumerate(records):
            value=obj(r).get(field);token=io['date_object'](value);valid=io['date_calendar'](value);inside=token is not None and io['window_relation'](token)=='inside';calendar.append(mean((io['date_shape'](value),valid,inside or obj(value).get('status')=='unknown')))
            actual=next((s for s in checked['metadata'] if s['path']==f'/{group}/{index}/{field}'),{});counts.append(bool(inside and actual.get('metadata') and obj(value).get('status')=='documented'))
    for p in pubs:
        value=obj(p).get('version_date');token=io['date_object'](value);calendar.append(float(io['version_date_is_unknown'](value) and io['rich'](obj(p).get('selected_report')) or token is not None and io['window_relation'](token)=='inside'))
    calendar_consistency=sum(calendar)/den['DDATE']
    topics={v for c in claims for v in arr(obj(c).get('topics')) if isinstance(v,str)}
    declared_full=sum(any(obj(sources[c['source_index']]).get('access_status')=='read_full' and c['source'] and c['source'].get('status')=='acquired' for c in links(f'/publications/{pi}')) for pi,p in enumerate(pubs))
    scope_checks={'entities_minimum_declaration':len(entities)>=5,'publications_minimum_declaration':len(pubs)>=5,'supported_declared_entity_dates_at_least5':sum(supported_entity_dates)>=5,'supported_declared_publication_dates_at_least5':sum(supported_pub_dates)>=5,'declared_full_research_source_connections_at_least5':declared_full>=5,'claims_exactly12':len(claims)==12,'five_topic_keys':set(io['DIMENSIONS']).issubset(topics),'sources_cap':len(sources)<=60,'priority_count':budget['checks']['priority_count']}
    time_and_scope=.40*metadata_trace+.25*calendar_consistency+.20*mean(scope_checks.values())+.15*mean(budget['checks'].values())
    integrity=[len(sources)<=60 and all(unique(obj(s).get('source_id'),sids) and io['source_shape'](s) for s in sources),all(c['graph'] and c['shape'] for c in cited),all(c['resolution']['resolved'] for c in cited),all(unique(c['citation_id'],all_cids) for c in cited)]
    pointer_graph=.75*E('graph')+.25*mean(integrity)
    epistemic=.5*sum(io['claim_shape'](obj(obj(e).get('capabilities')).get(dim)) for e in entities for dim in io['DIMENSIONS'])/DCAP+.5*sum(io['claim_shape'](c) for c in claims)/NC
    numbers=[n for value in (entities,pubs,claims) for n in io['numeric_records'](value)];numeric=all(io['number_shape'](n) for n in numbers)
    epistemic_numeric=.75*epistemic+.25*float(numeric)
    citation_resolution=.20*pointer_graph+.20*E('provenance')+.40*E('literal')+.20*epistemic_numeric
    baselines=protected.get('protected_files')
    if not isinstance(baselines,list) or len(baselines)!=3:raise TrustedEvidenceError('H031 exactly three protected input baselines required')
    inputs={}
    for row in baselines:
        name=row.get('path');digest=row.get('sha256')
        if not string(name) or Path(name).name!=name or not string(digest):raise TrustedEvidenceError('H031 invalid protected baseline')
        path=root/name;inputs[name]=path.is_file() and not path.is_symlink() and io['sha'](path)==digest
    paths=('capability_matrix.xlsx','evidence_ledger.json','research_report.docx','coverage.json');presence=[(root/'results'/p).is_file() and not (root/'results'/p).is_symlink() for p in paths]
    readable=[book is not None and any(c['visible'] and c['editable'] and c['value'] is not None for s in book for c in s['cells'].values()),ledger is not None,bool(report['native_readable_editable']),coverage is not None]
    protected_delivery=.50*mean(inputs.values())+.25*mean(presence)+.25*mean(readable)
    scores={'record_contract':record_contract,'time_and_scope':time_and_scope,'citation_resolution':citation_resolution,'protected_delivery':protected_delivery};scores['overall_score']=sum(scores[k]*w for k,w in WEIGHTS.items())
    observations={'schema_version':'h031-rule-observations/v1','scores':scores,'denominators':den,'candidate_errors':errors,'input_checks':inputs,'record_parts':{'root_shape':root_shape,'item_shapes':item_shapes,'id_graph':id_graph,'native_matrix':native_matrix,'native_report':native_report},'time_parts':{'metadata_trace':metadata_trace,'calendar_consistency':calendar_consistency,'scope_arithmetic':scope_checks,'priority_budget_DAG':budget},'citation_parts':{'pointer_graph':pointer_graph,'E_provenance':E('provenance'),'E_literal':E('literal'),'epistemic_numeric':epistemic_numeric,'actual_numeric_records':len(numbers)},'field_evidence_slots':checked,'citations':[{k:v for k,v in c.items() if k not in ('source','citation')} for c in cited],'native_mapping':view,'native_report_checks':report,'office_recalculation':recalculation,'derived_source_receipts':derived,'source_acquisition_summary':manifest.get('acquisition_summary'),'source_bundle_manifest_sha256':os.environ['GENERAL_E2E_RESEARCH_SOURCE_BUNDLE_SHA256'],'scoring_contract_sha256':io['sha'](gt/'scoring_contract.json'),'semantic_status':'NEEDS_INDEPENDENT_JUDGE','semantic_score':None,'formal_hybrid_score':None,'actual_search_read_identity_roles_representativeness_comparability_priorities_are_Judge_only':True,'automatic_full_score_is_not_scientific_or_execution_pass':True}
    target=evidence/'rule-observations.json'
    if target.exists():raise TrustedEvidenceError('H031 derived evidence already exists; use a fresh managed directory')
    try:target.write_text(json.dumps(observations,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    except (OSError,ValueError,TypeError) as exc:raise TrustedEvidenceError('H031 observation write failed') from exc
    return scores
