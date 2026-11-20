"""H033 rules: contract mechanics, literal located evidence, native delivery.
No notice/URL/fact answer whitelist. Semantic support and discovery remain Judge.
"""
from pathlib import Path
import hashlib,json,os,runpy

class TrustedEvidenceError(RuntimeError):pass
WEIGHTS={'record_contract':.20,'time_and_scope':.25,'citation_resolution':.40,'protected_delivery':.15}
BUNDLED_OFFICE='/Users/gzx/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/override/soffice'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def mean(values):
    values=list(values);return sum(values)/len(values) if values else 0.
def safe(root,name):
    p=root/name
    if p.is_symlink() or root not in p.resolve().parents or not p.is_file():return None
    return p
def grade(transcript=None,workspace_path=None,**kwargs):
    if not workspace_path:raise TrustedEvidenceError('H033 candidate context missing')
    gt=Path(__file__).resolve().parent;root=Path(workspace_path).resolve()
    try:binding=json.loads((gt/'scoring_contract.json').read_text());runtime=json.loads((gt/'runtime_contract.json').read_text())
    except (OSError,ValueError) as e:raise TrustedEvidenceError('H033 required private binding/runtime absent') from e
    for name,digest in binding.get('private_sha256',{}).items():
        if name=='scoring_contract.json' or not isinstance(name,str) or name.startswith('/') or '\\' in name or any(x in ('','.','..') for x in name.split('/')):raise TrustedEvidenceError('unsafe private binding')
        p=safe(gt,name)
        if p is None or sha(p)!=digest:raise TrustedEvidenceError('H033 private material missing/drift: '+name)
    if not binding.get('private_sha256') or binding.get('checkpoint_weights')!=WEIGHTS or binding.get('automatic_weight')!=.4 or binding.get('semantic_weight')!=.6:raise TrustedEvidenceError('H033 frozen rule contract mismatch')
    try:
        io=runpy.run_path(str(gt/'ledger_rules.py'));src=runpy.run_path(str(gt/'verified_sources.py'));native=runpy.run_path(str(gt/'native_text.py'));office=runpy.run_path(str(gt/'office_runtime.py'))
    except Exception as e:raise TrustedEvidenceError('H033 trusted helper unavailable') from e
    env=os.environ.get('GENERAL_E2E_RULE_EVIDENCE_DIR')
    if not env or Path(env).is_symlink():raise TrustedEvidenceError('H033 managed derived context absent')
    derived=Path(env).resolve()
    if any(derived==p or derived in p.parents or p in derived.parents for p in (root,gt)):raise TrustedEvidenceError('derived evidence overlaps inputs')
    derived.mkdir(parents=True,exist_ok=True);target=derived/'rule-observations.json'
    if target.exists():raise TrustedEvidenceError('fresh derived directory required')
    errors={};data=None;schema=[];traversable=False;graph={'passed':False,'errors':[],'citations':{},'targets':[]};time={'groups':{},'errors':[]};checked=[];sources=None;native_results={};recalculation=None
    protected=json.loads((gt/'protected_sha256.json').read_text());inputs={k:bool(safe(root,k) and sha(root/k)==v) for k,v in protected.items()}
    ledger=safe(root,'results/source_ledger.json')
    if ledger:
        try:
            data=io['strict_json'](ledger)
            schema=io['schema_errors'](data,json.loads((gt/'artifact_contract.json').read_text())['source_ledger_schema'])
            if not isinstance(data,dict):raise io['CandidateError']('ledger object required')
            # A leaf const/enum/required defect does not erase independent valid
            # date, quote or native observations. Ill-typed containers are gated.
            traversable=not any(e['rule']=='type' for e in schema)
            if traversable:
                graph=io['graph_checks'](data)
                time=io['date_scope_checks'](data,runtime['public_scope'],runtime['publication_window'],graph)
                sources=src['load_bundle'](root,gt,derived,data)
                if sources.get('candidate_input_error') and not schema and graph['passed']:
                    raise src['TrustedSourceError']('NEEDS_COLLECTOR_INPUT_REVIEW: public ledger parses and its graph is valid, but the production collector rejected its representation; no candidate zero from this parser mismatch')
                for cid,(carrier,c,p) in graph['citations'].items():
                    s=sources['sources'].get(carrier.get('carrier_id'))
                    if sources.get('candidate_input_error') or s is not None and s.get('candidate_invalid'):
                        r={'resolved':False,'reason':'candidate_source_descriptor_invalid','source_reading_trace':'NOT_PROVED'}
                    elif s is None:raise src['TrustedSourceError']('declared citation trusted source missing')
                    else:r=src['resolve'](s,c)
                    checked.append({'citation_id':cid,'carrier_id':carrier.get('carrier_id'),'pointer':p,'relation':c.get('relation'),'supports_fields':c.get('supports_fields',[]),'resolution':r})
                alias=src['official_alias_links'](sources,runtime['public_scope'])
                uses_alias=any(io['url_allowed'](c.get('url'),runtime['public_scope']) and 'law.hbu.cn'==(__import__('urllib.parse',fromlist=['urlsplit']).urlsplit(c['url']).hostname or '').rstrip('.') for c in data.get('carriers',[]))
                actual_scope=all(io['url_allowed'](s['source'].get('final_url') or s['source']['url'],runtime['public_scope']) for s in sources['sources'].values())
                time['groups']['URL_scope']=time['groups'].get('URL_scope',False) and actual_scope
                if not actual_scope:time['errors'].append({'rule':'actual_source_redirect_outside_public_scope'})
                if uses_alias and not alias and not sources.get('candidate_input_error'):
                    raise src['UnsupportedLocator']('NEEDS_ALIAS_NAVIGATION_REVIEW: no machine-confirmed official link in sealed sources; actual navigation trace may support alias and requires independent review')
                sources['official_alias_links']=alias
        except io['CandidateError'] as e:errors['ledger']=str(e)
        except (src['TrustedSourceError'],io['ContractError']) as e:
            payload={'schema_version':'h033-rule-observations/v1','status':'EVALUATOR_ERROR_OR_PENDING_REVIEW','error_type':type(e).__name__,'detail':str(e),'schema_errors':schema,'graph_errors':graph['errors'],'date_scope_checks':time,'citation_evidence':checked,'semantic_score':None,'final_hybrid_score':None}
            target.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            raise TrustedEvidenceError(str(e)) from e
    else:errors['ledger']='missing/unsafe source ledger'
    for path in ('results/notice_timeline.xlsx','results/action_plan.docx'):
        p=safe(root,path)
        if p is None:errors[path]='missing/unsafe native delivery';continue
        try:
            if path.endswith('.xlsx'):office['_clean_package'](p.read_bytes())
            else:office['_inspect_docx_render_package'](p.read_bytes())
            projection=native['extract_native_text'](p,max_chars=4_000_000)
            if projection['truncated']:raise TrustedEvidenceError('NEEDS_NATIVE_REVIEW: legal native evidence exceeds bounded complete extraction')
            rows=[json.loads(line) for line in projection['text'].splitlines()];formulas=[r for r in rows if 'formula' in r]
            visible=True;usable=[]
            for row in rows:
                if str(row.get('locator','')).startswith('sheet:'):visible=row.get('state')=='visible'
                if (row.get('text') or row.get('value') is not None) and visible:usable.append(row)
            if formulas:
                lock_path=os.environ.get('GENERAL_E2E_OFFICE_LOCK')
                if not lock_path:raise TrustedEvidenceError('formula output requires actual trusted Office lock')
                lock=json.loads(Path(lock_path).read_text())
                if lock.get('executable')!=BUNDLED_OFFICE:raise TrustedEvidenceError('only locked bundled Office executable authorized')
                # Standalone upstream helper defaults to /private/tmp on macOS.
                # Keep all author/managed scratch inside this derived context.
                import tempfile
                office['recalculate_xlsx'].__globals__['_temporary']=lambda:tempfile.TemporaryDirectory(prefix='h033-office-',dir=str(derived))
                office['validate_office_lock'](lock);recalculation=office['recalculate_xlsx'](p,lock,derived/'recalculated',timeout_seconds=60)
                reprojection=native['extract_native_text'](Path(recalculation['path']),max_chars=4_000_000)
                if reprojection['truncated']:raise TrustedEvidenceError('recomputed evidence truncated')
                actual={r['locator']:r for r in (json.loads(line) for line in reprojection['text'].splitlines())}
                for r in formulas:
                    r2=actual.get(r['locator'],{})
                    if not r2.get('cached_value_available') or r2.get('type')=='e' or str(r2.get('value','')).startswith(('#REF!','#VALUE!','#DIV/0!','#NAME?','#N/A','#NUM!','#SPILL!')):raise io['CandidateError']('actual recomputed formula missing/error at '+r['locator'])
                projection['actual_recalculation']=reprojection
            native_results[path]={'usable_native':bool(usable),'formula_count':len(formulas),'projection':projection,'visual_usability':'NEEDS_INDEPENDENT_JUDGE'}
        except io['CandidateError'] as e:errors[path]=str(e)
        except native['NativeTextError'] as e:
            if e.code in ('NATIVE_TEXT_DEPENDENCY_MISSING','NATIVE_TEXT_LIMIT'):raise TrustedEvidenceError(str(e)) from e
            errors[path]=str(e)
        except office['OfficeRuntimeError'] as e:
            if e.code in ('OFFICE_INPUT_INVALID','OFFICE_ACTIVE_CONTENT_UNSUPPORTED','OFFICE_EXTERNAL_DATA_UNSUPPORTED'):errors[path]=str(e)
            else:raise TrustedEvidenceError(str(e)) from e
    shape_ok=data is not None and not schema and 'ledger' not in errors
    scores={'record_contract':.5*float(shape_ok)+.5*float(traversable and graph['passed']),
            'time_and_scope':mean(time.get('groups',{}).values()) if traversable else 0.,
            'citation_resolution':0.,
            'protected_delivery':.4*mean(inputs.values())+.45*mean([bool(ledger and data is not None),*[bool(native_results.get(k,{}).get('usable_native')) for k in ('results/notice_timeline.xlsx','results/action_plan.docx')]])+.15*float(all(k in native_results and k not in errors for k in ('results/notice_timeline.xlsx','results/action_plan.docx')))}
    if checked:
        citation_targets_ok=not any('/citations/' in e.get('path','') for e in graph['errors'])
        scores['citation_resolution']=.5*float(all(c['resolution']['resolved'] for c in checked))+.25*float(citation_targets_ok)+.25*float(bool(sources and sources['receipts']) and time['groups'].get('URL_scope',False))
    scores['overall_score']=sum(scores[k]*v for k,v in WEIGHTS.items())
    observations={'schema_version':'h033-rule-observations/v1','reviewer_kind':'model','human_expert':False,'scope':'Facts-free structural/date/locator/native mechanics only','scores':scores,'fixed_subcheck_denominators':{'record_contract':2,'time_and_scope':5,'citation_resolution':3,'protected_delivery':3},'candidate_errors':errors,'schema_errors':schema,'graph_errors':graph['errors'],'date_scope_checks':time,'citation_evidence':checked,'input_checks':inputs,'native_delivery':native_results,'office_recalculation':recalculation,'source_receipts':sources['receipts'] if sources else [],'source_bundle_manifest_sha256':sources['manifest_sha256'] if sources else None,'source_acquisition_summary':sources['acquisition_summary'] if sources else None,'official_alias_links':sources.get('official_alias_links') if sources else [],'scoring_contract_sha256':sha(gt/'scoring_contract.json'),'semantic_status':'NEEDS_INDEPENDENT_JUDGE','semantic_score':None,'final_hybrid_score':None,'semantic_limits':['literal quote at locator does not prove support/refutation/qualification of target','actual reading and autonomous discovery require trace evidence','no count-based coverage, completeness or independent-source score','date-role source semantics, matter/version conflict, applicability and latest status require Judge','native text extraction does not prove usable design or human workflow completion'],'candidate_code_or_network_execution':False}
    target.write_text(json.dumps(observations,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return scores
