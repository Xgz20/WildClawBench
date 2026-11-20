"""H032 fixed-owner mechanical anchors over independent actual local originals.
No candidate code execution, network, or automatic claim of semantic science.
"""
from pathlib import Path
import hashlib,json,os,runpy

class TrustedEvidenceError(RuntimeError):pass
WEIGHTS={'business_correctness':.55,'boundary_cases':.25,'delivery_integrity':.15,'evidence_binding':.05}
BUNDLED_OFFICE='/Users/gzx/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/override/soffice'
def obj(value):return value if isinstance(value,dict) else {}
def arr(value):return value if isinstance(value,list) else []
def string(value):return isinstance(value,str) and bool(value.strip())
def mean(values):
    values=list(values);return sum(values)/len(values) if values else 0.
def core_rollup(anchors,results):
    owners={key:[a for a in anchors if a['owner']==key] for key in ('business_correctness','boundary_cases')}
    if not owners['business_correctness'] or not owners['boundary_cases']:raise TrustedEvidenceError('H032 fixed owner baseline missing')
    return {key:sum(results.get(a['input_ref'],{}).get('score',0.) for a in rows)/len(rows) for key,rows in owners.items()}
def citation_slot(items,absence_scope=False):
    if items:return {'literal':all(i['resolution']['resolved'] for i in items),'graph':all(i['graph'] for i in items),'evidence_state':'actual_all_declared_citations'}
    return {'literal':bool(absence_scope),'graph':bool(absence_scope),'evidence_state':'declared_absence_scope_positions' if absence_scope else 'missing_binding'}
def require_formula_lock(book):
    if not any(c.get('formula') for s in book for c in s['cells'].values()):return None
    path=os.environ.get('GENERAL_E2E_OFFICE_LOCK')
    if not path:raise TrustedEvidenceError('H032 formula requires trusted Office lock; cached values cannot substitute')
    return path
def protected_input_matches(root,name,digest,hash_file):
    root=Path(root).resolve();path=root/name
    return path.is_file() and not path.is_symlink() and root in path.resolve().parents and hash_file(path)==digest

def collect_absence_scopes(claim,registry,sources,io,engine,pdf):
    eligible=io['verdict'](claim.get('verdict'))=='insufficient' or io['target_kind'](claim.get('assessment_target'))=='evidence_sufficiency'
    if not eligible:return []
    found=[]
    page_keys=('physical_page_1_based','physical_page_1based','physical_page','page','pages','physical_pages','page_range')
    def bound_source(value,inherited_source):
        did=value.get('document_id');source=registry['doc_sources'].get(did) if string(did) else inherited_source
        for key in ('file','report','report_id'):
            if source is None and key in value:
                rid=engine['resolve_subject'](value[key],registry)
                if rid:source=sources['reports'][rid]
        return source
    def visit(value,inherited_source=None):
        if isinstance(value,list):
            for child in value:visit(child,inherited_source)
        elif isinstance(value,dict):
            source=bound_source(value,inherited_source)
            locator=value.get('locator',value)
            positioned=isinstance(locator,dict) and any(key in locator for key in page_keys)
            before=len(found)
            if positioned:
                try:found.append(pdf['reviewed_scope'](source,locator))
                except pdf['TrustedEvidenceError'] as exc:raise TrustedEvidenceError(str(exc)) from exc
            # A document-only parent carries source context, not a second,
            # invalid position. A declared locator is checked exactly once.
            for key,child in value.items():
                if positioned and (key in page_keys or key=='locator'):continue
                if isinstance(child,(dict,list)):visit(child,source)
                elif key=='locator' and string(child):raise TrustedEvidenceError('UNSUPPORTED_REVIEWED_SCOPE_PROSE: clear public scope text needs faithful position mapping, not candidate0')
            if not positioned and len(found)==before and any(string(value.get(key)) for key in ('scope','text','reason','checked_scope')):
                raise TrustedEvidenceError('UNSUPPORTED_REVIEWED_SCOPE_PROSE: clear public scope text needs faithful position mapping, not candidate0')
        elif string(value):raise TrustedEvidenceError('UNSUPPORTED_REVIEWED_SCOPE_PROSE: clear public scope text needs faithful position mapping, not candidate0')
    if 'reviewed_scope' in claim:visit(claim['reviewed_scope'])
    else:
        # Scan only explicit scope objects, not arbitrary explanatory strings.
        def explicit(value,inherited_source=None):
            if isinstance(value,dict):
                source=bound_source(value,inherited_source)
                for key,child in value.items():
                    if key in ('reviewed_scope','checked_scope'):visit(child,source)
                    elif isinstance(child,(dict,list)):explicit(child,source)
            elif isinstance(value,list):
                for child in value:explicit(child,inherited_source)
        explicit(claim.get('comparison',{}))
    return found

def grade(transcript=None,workspace_path=None,**kwargs):
    if not workspace_path:raise TrustedEvidenceError('H032 workspace path missing')
    gt=Path(__file__).resolve().parent;root=Path(workspace_path).resolve()
    def load(name):
        try:value=json.loads((gt/name).read_text(encoding='utf-8'))
        except (OSError,ValueError,UnicodeError) as exc:raise TrustedEvidenceError('H032 private baseline missing/invalid: '+name) from exc
        if not isinstance(value,dict):raise TrustedEvidenceError('H032 private baseline object required: '+name)
        return value
    binding=load('scoring_contract.json');hashes=binding.get('private_sha256')
    if not isinstance(hashes,dict) or not hashes:raise TrustedEvidenceError('H032 private hash baseline missing')
    for name,digest in hashes.items():
        if not string(name) or name.startswith('/') or '\\' in name or any(p in ('','.','..') for p in name.split('/')) or name=='scoring_contract.json':raise TrustedEvidenceError('H032 unsafe private hash binding')
        path=gt/name
        if path.is_symlink() or not path.is_file() or gt not in path.resolve().parents or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise TrustedEvidenceError('H032 private material drift/missing: '+name)
    if binding.get('checkpoint_weights')!=WEIGHTS or binding.get('automatic_weight')!=.75 or binding.get('semantic_weight')!=.25:raise TrustedEvidenceError('H032 frozen scoring weights drift')
    io=runpy.run_path(str(gt/'native_io.py'));pdf=runpy.run_path(str(gt/'pdf_evidence.py'));engine=runpy.run_path(str(gt/'scientific_engine.py'));office=runpy.run_path(str(gt/'office_runtime.py'))
    env=os.environ.get('GENERAL_E2E_RULE_EVIDENCE_DIR')
    if not env or Path(env).is_symlink():raise TrustedEvidenceError('H032 managed derived evidence context missing')
    evidence=Path(env).resolve()
    if any(evidence==p or p in evidence.parents or evidence in p.parents for p in (gt,root)):raise TrustedEvidenceError('H032 derived evidence overlaps inputs')
    evidence.mkdir(parents=True,exist_ok=True)
    try:sources=pdf['load_sources'](gt)
    except pdf['TrustedEvidenceError'] as exc:raise TrustedEvidenceError(str(exc)) from exc
    expected=load('expected.json');spec=load('machine_anchor_spec.json');anchors=spec.get('claims');protected=load('protected_sha256.json')
    if not isinstance(anchors,list) or len(anchors)!=len(expected.get('claim_expectations',[])):raise TrustedEvidenceError('H032 machine/source claim baseline incomplete')
    expected_ids=[a['input_ref'] for a in anchors]
    if len(set(expected_ids))!=12 or sum(a['owner']=='business_correctness' for a in anchors)!=5 or sum(a['owner']=='boundary_cases' for a in anchors)!=7:raise TrustedEvidenceError('H032 fixed12/5/7 owner baseline invalid')
    source_receipts=[]
    for rid,source in sources['reports'].items():
        path=evidence/'sources'/(rid+'.physical-pages.json');payload={'report_id':rid,'file':source['file'],'work_id':source['work_id'],'read_version':source['version'],'original_sha256':source['sha256'],'source_registry_sha256':sources['source_manifest_sha256'],'projection':source['projection'],'scope':'Actual trusted local original, not candidate source snapshot, reading trace or science judgment'}
        if path.exists():raise TrustedEvidenceError('H032 derived source output already exists')
        path.parent.mkdir(exist_ok=True);path.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');source_receipts.append({'path':str(path),'sha256':io['sha'](path),'report_id':rid})
    errors={};recalculation=None
    def candidate(name,action):
        try:return action()
        except io['CandidateError'] as exc:errors[name]=str(exc);return None
        except io['TrustedEvidenceError'] as exc:raise TrustedEvidenceError(str(exc)) from exc
    raw=candidate('bibliography',lambda:io['strict_json'](io['candidate_path'](root,'results/bibliography.json')))
    biblio=candidate('bibliography_normalization',lambda:io['normalize_bibliography'](raw)) if raw is not None else None
    docx=candidate('review',lambda:io['read_docx'](io['candidate_path'](root,'results/review.docx')))
    def workbook():
        nonlocal recalculation
        path=io['candidate_path'](root,'results/evidence_matrix.xlsx')
        try:
            office['_clean_package'](path.read_bytes());original=io['read_book'](path);lock_path=require_formula_lock(original)
            if lock_path is None:return original
            try:lock=json.loads(Path(lock_path).read_text(encoding='utf-8'))
            except (OSError,ValueError,UnicodeError) as exc:raise TrustedEvidenceError('H032 Office lock missing/invalid') from exc
            if lock.get('executable')!=BUNDLED_OFFICE:raise TrustedEvidenceError('H032 trusted Office must be the frozen bundled absolute executable')
            office['validate_office_lock'](lock);recalculation=office['recalculate_xlsx'](path,lock,evidence/'recalculated',timeout_seconds=60);result=io['read_book'](recalculation['path']);before={s['name']:s for s in original}
            for sheet in result:
                if sheet['name'] not in before:raise TrustedEvidenceError('H032 Office changed worksheet identity')
                for position,cell in sheet['cells'].items():
                    old=before[sheet['name']]['cells'].get(position,{'visible':True,'editable':True});cell['visible'] &= old['visible'];cell['editable'] &= old['editable']
                    if cell['formula'] and cell.get('kind')=='e':raise io['CandidateError']('candidate formula recomputes to error')
            return result
        except office['OfficeRuntimeError'] as exc:
            if exc.code in {'OFFICE_INPUT_INVALID','OFFICE_ACTIVE_CONTENT_UNSUPPORTED','OFFICE_EXTERNAL_DATA_UNSUPPORTED'}:raise io['CandidateError'](str(exc)) from exc
            raise TrustedEvidenceError('H032 trusted Office failure: '+str(exc)) from exc
    book=candidate('evidence_matrix',workbook)
    data=obj(biblio);documents=arr(data.get('documents'));claims=arr(data.get('claims'));citations=arr(data.get('citations'));registry=engine['subject_registry'](sources,documents)
    id_to_ref={c['claim_id']:io['original_ref'](c.get('input_ref'),expected_ids) for c in claims if isinstance(c,dict) and string(c.get('claim_id'))}
    field_map=obj(raw).get('field_map',obj(raw).get('字段映射',{}));field_map=field_map if isinstance(field_map,dict) else {}
    matrix=candidate('matrix_layout',lambda:io['extract_matrix'](book or [],expected_ids+list(id_to_ref),field_map)) or {'records':[]}
    explicit_rows=matrix['records']+io['docx_explicit_rows'](docx,expected_ids)
    def row_ref(row):
        record=row['record'];value=record.get('input_ref',record.get('claim_id'));return io['original_ref'](value,expected_ids) or id_to_ref.get(value) if isinstance(value,(str,int)) else io['original_ref'](value,expected_ids)
    groups={key:[] for key in expected_ids};candidate_id_counts={}
    for index,c in enumerate(claims):
        if not isinstance(c,dict):continue
        ref=io['original_ref'](c.get('input_ref'),expected_ids)
        if ref:groups[ref].append({'claim':c,'origin':'bibliography','index':index})
        if string(c.get('claim_id')):candidate_id_counts[c['claim_id']]=candidate_id_counts.get(c['claim_id'],0)+1
    # Native content remains available if one machine container/row is absent.
    for ref in expected_ids:
        if groups[ref]:continue
        rows=[row for row in explicit_rows if row_ref(row)==ref]
        if not rows:continue
        claim={'claim_id':ref,'input_ref':ref};parts={}
        for row in rows:
            numeric={key:value for key,value in row['record'].items() if key in ('report','document_id','file','version','metric','quantity','value','unit','denominator','arm','task','split','condition','state')}
            if numeric:parts.setdefault('comparison',[]).append(numeric)
            for key,value in row['record'].items():
                if key in ('claim_id','input_ref') or not io['rich'](value):continue
                if key in ('comparison','rationale','limitations'):parts.setdefault(key,[]).append(value)
                elif key not in claim:claim[key]=value
        for key,values in parts.items():
            if key=='comparison':
                normalized=[]
                for value in values:
                    if isinstance(value,str) and value.lstrip().startswith(('{','[')):
                        try:value=json.loads(value)
                        except ValueError:pass
                    normalized.append(value)
                claim[key]=normalized
            else:claim[key]='\n'.join(map(str,values))
        claim.setdefault('assessment_target','fact');groups[ref].append({'claim':claim,'origin':'available_native_logical_rows','index':None})
    results={};error_ledger=[];pending=[]
    for anchor in anchors:
        ref=anchor['input_ref'];rows=groups[ref]
        if len(rows)!=1:
            result={'score':0.,'missing':not rows,'duplicate_original':len(rows)>1,'checks':{},'pending_semantic':[]}
        elif candidate_id_counts.get(rows[0]['claim'].get('claim_id'),1)>1:
            result={'score':0.,'ambiguous_candidate_claim_id':True,'checks':{},'pending_semantic':[]}
        else:result=engine['evaluate_claim'](rows[0]['claim'],anchor,registry,documents,io['verdict'],io['target_kind'])
        results[ref]=result;pending += [{'input_ref':ref,'owner':anchor['owner'],'item':item} for item in result.get('pending_semantic',[])]
        if result['score']<1:error_ledger.append({'error_id':'core:'+ref,'input_ref':ref,'owner_key':anchor['owner'],'opportunity':ref,'core_opportunity_score':result['score'],'related_label_value_reason_signals_no_extra_cross_owner_deduction':True})
    dids=[obj(d).get('document_id') for d in documents];citation_ids=[obj(c).get('citation_id') for c in citations];checked=[]
    document_shapes={obj(d).get('document_id'):all(key in obj(d) for key in ('document_id','file','title','authors','work_id','version')) and io['rich'](obj(d).get('title')) and io['rich'](obj(d).get('authors')) and io['rich'](obj(d).get('version')) for d in documents if string(obj(d).get('document_id'))}
    for index,c in enumerate(citations):
        c=obj(c);did=c.get('document_id');source=registry['doc_sources'].get(did) if string(did) and dids.count(did)==1 else None;targets=[];graph=True
        for pointer in arr(c.get('supports_fields')):
            try:io['resolve_pointer'](raw,pointer);targets.append(io['canonical_pointer'](pointer,field_map))
            except io['CandidateError']:graph=False
        graph &= bool(targets) and isinstance(c.get('supports_fields'),list) and len(targets)==len(c['supports_fields']) and len(set(targets))==len(targets) and source is not None and document_shapes.get(did,False) and string(c.get('citation_id')) and citation_ids.count(c['citation_id'])==1 and io['relation'](c.get('relation')) is not None
        try:resolution=pdf['resolve_citation'](source,c,io['quote_match'])
        except (pdf['TrustedEvidenceError'],io['TrustedEvidenceError']) as exc:raise TrustedEvidenceError(str(exc)) from exc
        linked=[]
        for ref,rows in groups.items():
            for row in rows:
                if row['index'] is not None and any(io['pointer_overlaps'](target,'/claims/'+str(row['index'])) for target in targets):linked.append(ref)
        item={'index':index,'citation_id':c.get('citation_id'),'document_id':did,'targets':targets,'input_refs':list(set(linked)),'graph':bool(graph),'resolution':resolution};checked.append(item)
        if not graph or not resolution['resolved']:error_ledger.append({'error_id':'binding:'+str(index),'owner_key':'evidence_binding','citation_id':c.get('citation_id'),'actual_observation':item,'core_truth_not_inferred_from_bad_citation':True})
    evidence_slots=[]
    for ref in expected_ids:
        attached=[c for c in checked if ref in c['input_refs']];rows=groups[ref];scope=collect_absence_scopes(rows[0]['claim'],registry,sources,io,engine,pdf) if len(rows)==1 and not attached else [];slot=citation_slot(attached,bool(scope) and all(item['valid'] for item in scope));slot.update({'input_ref':ref,'citation_ids':[c['citation_id'] for c in attached],'absence_scope':scope});evidence_slots.append(slot)
    any_binding=any(slot['literal'] and slot['graph'] for slot in evidence_slots)
    inventory=bool(any_binding) and all(c['graph'] and c['resolution']['resolved'] for c in checked)
    evidence_binding=.60*sum(slot['literal'] for slot in evidence_slots)/12+.25*sum(slot['graph'] for slot in evidence_slots)/12+.15*float(inventory)
    transfer=io['native_verdict_conflicts'](explicit_rows,row_ref)
    for conflict in transfer:
        rows=groups.get(conflict['input_ref'],[])
        if not rows or any(row['origin']!='bibliography' for row in rows):pending.append({'input_ref':conflict['input_ref'],'item':{'status':'needs_judge','detail':'Conflicting actual final native verdicts cannot be resolved by choosing a row','actual_conflict':conflict}})
    for row in explicit_rows:
        ref=row_ref(row)
        if ref not in groups or len(groups[ref])!=1 or groups[ref][0]['origin']!='bibliography':continue
        base=groups[ref][0]['claim'];record=row['record'];left=io['verdict'](base.get('verdict'));right=io['verdict'](record.get('verdict'));lk=io['target_kind'](base.get('assessment_target'));rk=io['target_kind'](record.get('assessment_target'))
        if left and right and left!=right and (lk==rk or rk is None) and not base.get('components'):
            item={'input_ref':ref,'field':'verdict','bibliography':left,'native':right,'origin':row['origin'],'owner_key':'delivery_integrity'};transfer.append(item)
    for index,item in enumerate(transfer):error_ledger.append({'error_id':'transfer:'+str(index),'owner_key':'delivery_integrity','actual_transfer_conflict':item,'not_a_consistent_scientific_error_recount':True})
    input_checks={name:protected_input_matches(root,name,digest,io['sha']) for name,digest in protected.items()}
    if len(input_checks)!=11:raise TrustedEvidenceError('H032 frozen protected input baseline must have11 records')
    paths=('bibliography.json','evidence_matrix.xlsx','review.docx');presence=[(root/'results'/name).is_file() and not (root/'results'/name).is_symlink() for name in paths]
    native_matrix=book is not None and any(cell['visible'] and cell['editable'] and cell['value'] is not None for sheet in book for cell in sheet['cells'].values());native_docx=docx is not None and docx['editable'] and docx['visible_native']
    biblio_container=biblio is not None and data.get('schema_version')=='h032-bibliography/v1' and all(isinstance(data.get(key),list) for key in ('documents','claims','citations'))
    readable=[bool(biblio_container),bool(native_matrix),bool(native_docx)];containers=.5*mean(presence)+.5*mean(readable)
    same_transfer=not transfer;delivery_integrity=.35*mean(input_checks.values())+.40*containers+.25*float(same_transfer and any(readable))
    scores=core_rollup(anchors,results);scores.update({'delivery_integrity':delivery_integrity,'evidence_binding':evidence_binding});scores['overall_score']=sum(scores[key]*weight for key,weight in WEIGHTS.items())
    observations={'schema_version':'h032-rule-observations/v1','reviewer_kind':'model','human_expert':False,'scope':'Bounded mechanical source-table anchors; not semantic scientific completion','scores':scores,'owner_denominators':{'business_correctness':5,'boundary_cases':7,'evidence_binding':12},'candidate_errors':errors,'core_claims':results,'pending_independent_semantic_review':pending,'error_ledger':error_ledger,'citation_evidence':checked,'fixed_evidence_slots':evidence_slots,'input_checks':input_checks,'native_matrix':matrix,'actual_transfer_conflicts':transfer,'source_receipts':source_receipts,'source_baseline_anchor_count':sources['source_anchor_count'],'office_recalculation':recalculation,'scoring_contract_sha256':io['sha'](gt/'scoring_contract.json'),'source_first_spec_sha256':io['sha'](gt/'machine_anchor_spec.json'),'semantic_status':'NEEDS_INDEPENDENT_JUDGE','semantic_score':None,'final_hybrid_score':None,'no_candidate_code_or_network_executed':True}
    target=evidence/'rule-observations.json'
    if target.exists():raise TrustedEvidenceError('H032 fresh derived directory required')
    # Decimal observations are exact strings in evidence, never coerced to floats.
    target.write_text(json.dumps(observations,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
    if pending:raise TrustedEvidenceError('NEEDS_INDEPENDENT_SCIENTIFIC_REVIEW: legal comparison/condition representation not mechanically confirmed; see frozen observations; no automatic0 or semantic fabrication')
    return scores
