"""H030 answer-free mechanical rubric. Scientific eligibility and execution honesty require Judge."""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import runpy


class TrustedEvidenceError(RuntimeError):
    """Missing or drifted evaluator evidence; never a candidate ability zero."""


WEIGHTS = {'record_contract': .2, 'time_and_scope': .25, 'citation_resolution': .4, 'protected_delivery': .15}


def _object(value): return value if isinstance(value, dict) else {}
def _array(value): return value if isinstance(value, list) else []
def _string(value): return isinstance(value, str) and bool(value.strip())
def _mean(values):
    values = list(values)
    return sum(values) / len(values) if values else 0.0

def _date_aware(value):
    try:
        return isinstance(value, str) and dt.datetime.fromisoformat(value.replace('Z', '+00:00')).tzinfo is not None
    except ValueError:
        return False


def declared_platform_record_trace(ledger, docx, io):
    """Declared fields and native document linkage only, never execution proof."""
    text = io['norm'](_object(docx).get('text', ''))
    values = []
    for site in ('arxiv', 'pubmed'):
        rows = [r for r in _array(_object(ledger).get('searches')) if isinstance(r, dict) and r.get('site') == site]
        checks = []
        for row in rows:
            checks.append(all((_string(row.get('query_or_navigation')), _string(row.get('outcome')),
                               _date_aware(row.get('performed_at')) or row.get('performed_at') is None and _string(row.get('unknown_reason')),
                               site in text)))
        values.append(float(bool(checks) and all(checks)))
    return _mean(values)


def fixed_denominators(ledger):
    data=_object(ledger)
    NR=max(6,len(_array(data.get('records')))); NW=max(6,len(_array(data.get('works'))))
    NI=max(4,sum(isinstance(w,dict) and w.get('decision')=='include' for w in _array(data.get('works'))))
    return {'NR':NR,'NW':NW,'NI':NI,'D6':6*NI}


def evidence_slot_checks(items):
    return {'graph':bool(items) and all(c['graph'] and c['shape'] for c in items),
            'provenance':bool(items) and all(c['source'] and c['source'].get('status')=='acquired' for c in items),
            'literal':bool(items) and all(c['resolution']['resolved'] for c in items)}


def grade(transcript=None, workspace_path=None, **kwargs):
    # transcript intentionally unused. Actual search/read execution is 60% Judge work.
    if not workspace_path:
        raise TrustedEvidenceError('H030 workspace_path missing')
    gt = Path(__file__).resolve().parent
    root = Path(workspace_path).resolve()
    def load(name):
        try:
            value = json.loads((gt / name).read_text(encoding='utf-8'))
        except (OSError, ValueError, UnicodeError) as exc:
            raise TrustedEvidenceError('H030 private evaluator material missing/invalid: ' + name) from exc
        if not isinstance(value, dict):
            raise TrustedEvidenceError('H030 private evaluator object required: ' + name)
        return value
    binding = load('scoring_contract.json')
    hashes = binding.get('private_sha256')
    if not isinstance(hashes, dict) or not hashes:
        raise TrustedEvidenceError('H030 scoring hash bindings missing')
    for name, digest in hashes.items():
        if not isinstance(name, str) or Path(name).name != name or name == 'scoring_contract.json':
            raise TrustedEvidenceError('H030 invalid private hash binding')
        path = gt / name
        if not path.is_file() or path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise TrustedEvidenceError('H030 private material drift: ' + name)
    contract, runtime, protected = load('artifact_contract.json'), load('runtime_contract.json'), load('protected_sha256.json')
    if binding.get('checkpoint_weights') != WEIGHTS or binding.get('automatic_weight') != .4 or binding.get('semantic_weight') != .6 or runtime.get('semantic_judge_required') is not True:
        raise TrustedEvidenceError('H030 hybrid weights/semantic boundary drift')
    io = runpy.run_path(str(gt / 'native_io.py'))
    office = runpy.run_path(str(gt / 'office_runtime.py'))
    projector = runpy.run_path(str(gt / 'source_projection.py'))
    evidence_env = os.environ.get('GENERAL_E2E_RULE_EVIDENCE_DIR')
    if not evidence_env or Path(evidence_env).is_symlink():
        raise TrustedEvidenceError('H030 managed rule evidence context missing/unsafe')
    evidence = Path(evidence_env).resolve()
    if any(evidence == p or p in evidence.parents or evidence in p.parents for p in (root, gt)):
        raise TrustedEvidenceError('H030 evidence must be separate from candidate and GT')
    evidence.mkdir(parents=True, exist_ok=True)
    errors = {}
    def candidate(name, action):
        try:
            return action()
        except io['CandidateError'] as exc:
            errors[name] = str(exc)
            return None
    ledger = candidate('evidence_matrix', lambda: io['read_ledger'](io['candidate_path'](root, 'results/evidence_matrix.json')))
    docx = candidate('protocol', lambda: io['read_docx'](io['candidate_path'](root, 'results/protocol.docx')))
    recalculation = None
    def workbook():
        nonlocal recalculation
        path = io['candidate_path'](root, 'results/screening.xlsx', limit=32 * 1024 * 1024)
        try:
            office['_clean_package'](path.read_bytes())
            original = io['read_book'](path)
            if not any(c['formula'] for s in original for c in s['cells'].values()):
                return original
            lock_path = os.environ.get('GENERAL_E2E_OFFICE_LOCK')
            if not lock_path:
                raise TrustedEvidenceError('H030 formula workbook requires trusted Office lock')
            try:
                lock = json.loads(Path(lock_path).read_text(encoding='utf-8'))
            except (OSError, ValueError, UnicodeError) as exc:
                raise TrustedEvidenceError('H030 Office lock missing/invalid') from exc
            office['validate_office_lock'](lock)
            recalculation = office['recalculate_xlsx'](path, lock, evidence / 'recalculated', timeout_seconds=60)
            book = io['read_book'](recalculation['path'])
            original_sheets = {s['name']: s for s in original}
            for sheet in book:
                if sheet['name'] not in original_sheets:
                    raise TrustedEvidenceError('H030 Office changed worksheet identity')
                for pos, cell in sheet['cells'].items():
                    old = original_sheets[sheet['name']]['cells'].get(pos, {'visible': True, 'editable': True})
                    cell['visible'] &= old['visible']; cell['editable'] &= old['editable']
                    if cell['formula'] and cell.get('kind') == 'e':
                        raise io['CandidateError']('candidate formula recalculates to an error')
            return book
        except office['OfficeRuntimeError'] as exc:
            if exc.code in {'OFFICE_INPUT_INVALID', 'OFFICE_ACTIVE_CONTENT_UNSUPPORTED', 'OFFICE_EXTERNAL_DATA_UNSUPPORTED'}:
                raise io['CandidateError'](str(exc)) from exc
            raise TrustedEvidenceError('H030 trusted Office failure: ' + str(exc)) from exc
    book = candidate('screening', workbook)
    # No source-dependent score is silently returned without independent evidence.
    try:
        manifest, bundle = io['load_bundle'](ledger, ledger_path=root / 'results/evidence_matrix.json')
    except io['TrustedEvidenceError'] as exc:
        raise TrustedEvidenceError(str(exc)) from exc
    if manifest.get('collector_sha256') != runtime.get('source_collector_sha256') or manifest.get('bindings', {}).get('policy_sha256') != io['sha'](gt / 'research_source_policy.json'):
        raise TrustedEvidenceError('H030 production collector/policy binding drift')
    if ledger is None and manifest.get('candidate_input_status') == 'valid':
        raise TrustedEvidenceError('H030 collector failed to bind candidate JSON failure')
    bundle_root = Path(os.environ['GENERAL_E2E_RESEARCH_SOURCE_BUNDLE']).resolve()
    if evidence == bundle_root or bundle_root in evidence.parents or evidence in bundle_root.parents:
        raise TrustedEvidenceError('H030 derived evidence overlaps source bundle')
    derived_receipts = []
    for index, (sid, source) in enumerate(bundle.items(), 1):
        if source.get('status') == 'candidate_invalid':
            continue
        if source.get('status') != 'acquired':
            raise TrustedEvidenceError('H030 required independent source not acquired: ' + str(sid))
        try:
            projection = projector['project_source'](source['_body'], source.get('media_type', ''), source['_text'])
        except (ValueError, TypeError, KeyError, UnicodeError) as exc:
            raise TrustedEvidenceError('H030 source derivation failed: ' + sid) from exc
        projection['attempt_binding'] = {
            'source_id': sid, 'source_bundle_manifest_sha256': os.environ['GENERAL_E2E_RESEARCH_SOURCE_BUNDLE_SHA256'],
            'bundle_acquisition_identity': manifest.get('acquisition_identity'), 'bundle_bindings': manifest.get('bindings'),
            'candidate_ledger_sha256': io['sha'](root / 'results/evidence_matrix.json') if ledger is not None else None,
            'rule_source_sha256': io['sha'](gt / 'source_projection.py'), 'source_acquisition': source.get('_acquisition'),
            'boundary': 'Independent original bytes only; no candidate snapshot as truth; no historical GET recast as fresh'}
        try:
            receipt = projector['write_derived_projection'](projection, evidence / 'sources', stem='source-' + str(index))
        except (ValueError, OSError) as exc:
            raise TrustedEvidenceError('H030 managed derived evidence write failure') from exc
        derived_receipts.append(dict(receipt, source_id=sid, source_acquisition=source.get('_acquisition')))
        if projection.get('complete') is not True:
            raise TrustedEvidenceError('H030 safe source projection unresolved: ' + sid + ': ' + json.dumps(projection.get('errors'), ensure_ascii=False))
        source['_derived'] = projection
    data = _object(ledger)
    records = _array(data.get('records')); works = _array(data.get('works')); sources = _array(data.get('sources'))
    includes = [(i, w) for i, w in enumerate(works) if isinstance(w, dict) and w.get('decision') == 'include']
    denominators=fixed_denominators(data)
    NR,NW,NI,D6=(denominators[k] for k in ('NR','NW','NI','D6'))
    record_ids = [_object(r).get('record_id') for r in records]
    work_ids = [_object(w).get('work_id') for w in works]
    def unique(value, seq): return _string(value) and seq.count(value) == 1
    def graph_record(r):
        r = _object(r); wid = r.get('work_id')
        return _mean((unique(r.get('record_id'), record_ids), wid is None or unique(wid, work_ids), io['record_shape'](r), io['discovery_shape'](r.get('discovery'))))
    def graph_work(w):
        w = _object(w); wid = w.get('work_id'); selected = w.get('selected_record_id')
        assigned = [r for r in records if isinstance(r, dict) and r.get('work_id') == wid and _string(wid)]
        selected_ok = selected is None or unique(selected, record_ids) and any(r.get('record_id') == selected for r in assigned)
        return _mean((unique(wid, work_ids), bool(assigned), selected_ok, selected_ok and (w.get('decision') != 'include' or _string(selected))))
    root_shape = _mean((isinstance(ledger, dict), data.get('schema_version') == 'h030-evidence-matrix/v1', *[isinstance(data.get(k), list) for k in ('searches','records','works','sources')], isinstance(data.get('flow'), dict)))
    id_graph = .5 * sum(map(graph_record, records)) / NR + .5 * sum(map(graph_work, works)) / NW
    decision_shape = sum(_mean((_object(w).get('decision') in ('include','exclude','pending'), _string(_object(w).get('decision_reason')))) for w in works) / NW
    six_shape = sum(io['claim_shape'](_object(w).get(f)) for _,w in includes for f in io['CONTENT_FIELDS']) / D6
    view = candidate('screening_mapping', lambda: io['extract_screening'](book or [])) or {'works':{},'records':{},'mappings':[],'conflicts':[]}
    def same(a,b): return not isinstance(a,dict) and not isinstance(b,dict) and io['norm'](a)==io['norm'](b)
    def date_same(a,b):
        left=io['calendar_cell'](a); right=io['date_object'](b)
        return left is not None and right is not None and left['value']==right['value'] and left['precision']==right['precision'] or io['calendar_cell_unknown'](a) and (b is None or isinstance(b,dict) and b.get('status')=='unknown')
    source_ids = [_object(s).get('source_id') for s in sources]
    source_urls = [_object(s).get('url') for s in sources]
    def work_agreement(w):
        w=_object(w); row=_object(view['works'].get(w.get('work_id') if _string(w.get('work_id')) else None))
        if not row: return 0.0
        selected=next((_object(r) for r in records if _object(r).get('record_id')==w.get('selected_record_id')), {})
        selected_row=_object(view['records'].get(w.get('selected_record_id') if _string(w.get('selected_record_id')) else None))
        selected_ok = io['selected_record_matches'](w,row,selected_row,selected)
        return _mean((same(row.get('work_id'),w.get('work_id')),io['decision_equivalent'](row.get('decision'),w.get('decision')),_string(row.get('decision_reason')),selected_ok))
    def record_agreement(r):
        r=_object(r); row=_object(view['records'].get(r.get('record_id') if _string(r.get('record_id')) else None))
        if not row: return 0.0
        date_ok=date_same(row.get('report_date'),r.get('report_date'))
        basis_ok=_string(row.get('date_basis')) or io['basis_in_text'](_object(r.get('report_date')).get('basis'),row.get('report_date'))
        return _mean((same(row.get('record_id'),r.get('record_id')),same(row.get('work_id'),r.get('work_id')),_string(row.get('title')),same(row.get('report_version'),r.get('report_version')),date_ok and basis_ok,io['source_cell_members'](row.get('source'),source_ids+source_urls) is not None))
    xlsx_agreement=.5*sum(map(work_agreement,works))/NW+.5*sum(map(record_agreement,records))/NR
    doc_checks=io['docx_structure'](docx,data)
    record_contract=.2*root_shape+.3*id_graph+.2*(.25*decision_shape+.75*six_shape)+.2*xlsx_agreement+.1*_mean(doc_checks.values())
    # Build token-aware field evidence slots. Shared citations are never copied into closure arrays.
    cited=[]; citation_ids=[]
    for si,s in enumerate(sources):
        for ci,c in enumerate(_array(_object(s).get('citations'))):
            c=_object(c); citation_ids.append(c.get('citation_id'))
            pointers=[]; graph=True
            for pointer in _array(c.get('supports_fields')):
                try: io['resolve_pointer'](data,pointer); pointers.append(pointer)
                except io['CandidateError']: graph=False
            graph &= isinstance(c.get('supports_fields'),list) and bool(c['supports_fields']) and len(pointers)==len(c['supports_fields']) and len(set(pointers))==len(pointers)
            source=bundle.get(_object(s).get('source_id') if _string(_object(s).get('source_id')) else None)
            resolved=io['resolve_citation'](source,c) if source else {'resolved':False,'reason':'candidate source not independently acquired'}
            cited.append({'source_index':si,'citation_index':ci,'source_id':_object(s).get('source_id'),'citation_id':c.get('citation_id'),'pointers':pointers,'graph':bool(graph),'shape':io['citation_shape'](c),'source':source,'citation':c,'resolution':resolved})
    for c in cited: c['graph'] &= unique(c['citation_id'],citation_ids)
    def links(path): return [c for c in cited if any(io['pointer_overlaps'](p,path) for p in c['pointers'])]
    slots={'content':[],'metadata':[],'decision':[]}
    for wi,w in includes:
        for f in io['CONTENT_FIELDS']:
            value=_object(w).get(f); slots['content'].append({'path':f'/works/{wi}/{f}','value':value,'unknown':_object(value).get('status')=='unknown','scope':f'/works/{wi}','kind':f})
    for ri,r in enumerate(records):
        r=_object(r)
        for kind,path,value in [('identity',f'/records/{ri}/title',r),('report_date',f'/records/{ri}/report_date',r.get('report_date')),('version',f'/records/{ri}/report_version',r)]:
            paths=[path]
            if kind=='identity': paths=[f'/records/{ri}/{k}' for k in ('title','authors','identifiers')]
            if kind=='version': paths=[f'/records/{ri}/report_version',f'/records/{ri}/version_date']
            slots['metadata'].append({'path':path,'paths':paths,'value':value,'unknown':kind=='report_date' and _object(value).get('status')=='unknown' or kind=='version' and io['declared_unknown_version'](r),'scope':f'/records/{ri}','kind':kind})
    for wi,w in enumerate(works):
        slots['decision'].append({'path':f'/works/{wi}/decision_reason','value':_object(w).get('decision_reason'),'unknown':False,'scope':f'/works/{wi}','kind':'decision'})
    def inspect_slot(slot):
        attached=[]
        for path in slot.get('paths',[slot['path']]):
            for c in links(path):
                if c not in attached: attached.append(c)
        inherited=links(slot['scope']) if slot['unknown'] else []
        evidence_links=attached or inherited
        evidence_checks=evidence_slot_checks(evidence_links)
        graph,provenance,literal=(evidence_checks[k] for k in ('graph','provenance','literal'))
        metadata=graph and provenance and literal
        if metadata and slot['kind']=='report_date' and not slot['unknown']:
            metadata=any(io['date_literal_binding'](slot['value'],dict(c['resolution'],quote=c['citation'].get('quote')),c['source']) for c in evidence_links)
        if metadata and slot['kind']=='version' and _object(slot['value']).get('version_date') is not None:
            metadata=any(io['date_literal_binding'](_object(slot['value']).get('version_date'),dict(c['resolution'],quote=c['citation'].get('quote')),c['source']) for c in evidence_links)
        return {'path':slot['path'],'kind':slot['kind'],'unknown':slot['unknown'],'citation_ids':[c['citation_id'] for c in evidence_links], 'graph':float(graph),'provenance':float(provenance),'literal':float(literal),'metadata':float(metadata)}
    checked={group:[inspect_slot(slot) for slot in rows] for group,rows in slots.items()}
    def E(component): return .6*sum(c[component] for c in checked['content'])/D6+.25*sum(c[component] for c in checked['metadata'])/(3*NR)+.15*sum(c[component] for c in checked['decision'])/NW
    metadata_trace=sum(c['metadata'] for c in checked['metadata'])/(3*NR)
    def report_calendar(ri,r):
        r=_object(r); d=_object(r.get('report_date')); shape=io['report_date_shape'](d)
        token=io['date_object'](d); unknown=d.get('status')=='unknown'
        normalized=unknown or token is not None and (not d.get('timestamp') or _date_aware(d['timestamp']) and io['calendar_token'](d.get('value'),d.get('precision')) is not None and io['calendar_token'](d['timestamp'])['value']==io['calendar_token'](d['value'])['value'])
        selected=[w for w in works if isinstance(w,dict) and w.get('selected_record_id')==r.get('record_id')]
        relation=io['window_relation'](token)
        arithmetic=not selected or all(w.get('decision')!='include' or relation=='inside' for w in selected)
        return _mean((shape,normalized,arithmetic))
    def selected_version(w):
        r=next((_object(r) for r in records if _object(r).get('record_id')==_object(w).get('selected_record_id')), {})
        value=r.get('version_date'); token=io['date_object'](value)
        explicit_unknown=value is None and io['has_unknown_explanation'](r)
        # This is declared date arithmetic only, not an actual version-role verdict.
        return _mean((explicit_unknown or token is not None,explicit_unknown or token is not None and token['end']<='2026-09-30'))
    calendar_consistency=.5*sum(report_calendar(i,r) for i,r in enumerate(records))/NR+.5*sum(selected_version(w) for _,w in includes)/NI
    flow_checks=io['flow_checks'](data)
    declared_trace=declared_platform_record_trace(data,docx,io)
    def body_trace(wi,w):
        r=next((_object(r) for r in records if _object(r).get('record_id')==_object(w).get('selected_record_id')), {})
        valid=bool(r) and r.get('work_id')==_object(w).get('work_id')
        related=links(f'/works/{wi}')
        return float(valid and any(_object(sources[c['source_index']]).get('access_status')=='read_full' and c['source'] and c['source'].get('status')=='acquired' for c in related))
    bodies=sum(body_trace(wi,w) for wi,w in includes)/NI
    time_and_scope=.30*metadata_trace+.25*calendar_consistency+.30*_mean(flow_checks.values())+.15*(.5*declared_trace+.5*bodies)
    ledger_checks=[len(sources)<=60 and all(unique(_object(s).get('source_id'),source_ids) and io['source_shape'](s) for s in sources),
                   all(unique(c.get('citation_id'),citation_ids) for c in cited),
                   all(c['graph'] for c in cited),all(io['source_shape'](s) for s in sources) and all(c['resolution']['resolved'] for c in cited)]
    pointer_graph=.75*E('graph')+.25*_mean(ledger_checks)
    epistemic_numeric=sum(io['epistemic_numeric_shape'](_object(w).get(f),f,trace=checked['content'][index]['graph'] and checked['content'][index]['provenance']) for index,(w,f) in enumerate((w,f) for _,w in includes for f in io['CONTENT_FIELDS']))/D6
    citation_resolution=.20*pointer_graph+.20*E('provenance')+.40*E('literal')+.20*epistemic_numeric
    input_checks={name:(root/name).is_file() and not (root/name).is_symlink() and io['sha'](root/name)==digest for name,digest in protected.items()}
    if len(input_checks)!=3:
        raise TrustedEvidenceError('H030 protected input baseline must contain exactly three public MDs')
    presence=[(root/'results'/n).is_file() and not (root/'results'/n).is_symlink() for n in ('screening.xlsx','protocol.docx','evidence_matrix.json')]
    readability=[book is not None and any(c['visible'] and c['editable'] and c['value'] is not None for s in book for c in s['cells'].values()),docx is not None and docx['editable'] and docx['visible_native'],ledger is not None]
    protected_delivery=.5*_mean(input_checks.values())+.25*_mean(presence)+.25*_mean(readability)
    scores={'record_contract':record_contract,'time_and_scope':time_and_scope,'citation_resolution':citation_resolution,'protected_delivery':protected_delivery}
    scores['overall_score']=sum(scores[k]*weight for k,weight in WEIGHTS.items())
    observations={'schema_version':'h030-rule-observations/v1','scores':scores,'denominators':{'NR':NR,'NW':NW,'NI':NI,'D6':D6},
                  'candidate_errors':errors,'input_checks':input_checks,'record_parts':{'root_shape':root_shape,'id_graph':id_graph,'decision_shape':decision_shape,'six_shape':six_shape,'xlsx_agreement':xlsx_agreement,'docx_structure':doc_checks},
                  'time_parts':{'metadata_trace':metadata_trace,'calendar_consistency':calendar_consistency,'flow':flow_checks,'declared_platform_record_trace':declared_trace,'declared_body_trace':bodies},
                  'citation_parts':{'pointer_graph':pointer_graph,'provenance':E('provenance'),'literal':E('literal'),'epistemic_numeric':epistemic_numeric},'field_evidence_slots':checked,
                  'citations':[{k:v for k,v in c.items() if k not in {'source','citation'}} for c in cited],
                  'native_mapping':view,'docx_flow_observations':io['docx_flow_observations'](docx,data),'office_recalculation':recalculation,'derived_source_receipts':derived_receipts,'source_acquisition_summary':manifest.get('acquisition_summary'),
                  'source_bundle_manifest_sha256':os.environ['GENERAL_E2E_RESEARCH_SOURCE_BUNDLE_SHA256'],'scoring_contract_sha256':io['sha'](gt/'scoring_contract.json'),
                  'semantic_status':'NEEDS_INDEPENDENT_JUDGE','semantic_score':None,'formal_hybrid_score':None,
                  'execution_honesty_is_judge_only':True,'automatic_full_score_is_not_scientific_or_execution_pass':True}
    target=evidence/'rule-observations.json'
    if target.exists(): raise TrustedEvidenceError('H030 rule evidence already exists; use a fresh managed directory')
    try: target.write_text(json.dumps(observations,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    except (OSError,ValueError,TypeError) as exc: raise TrustedEvidenceError('H030 observation write failed') from exc
    return scores
