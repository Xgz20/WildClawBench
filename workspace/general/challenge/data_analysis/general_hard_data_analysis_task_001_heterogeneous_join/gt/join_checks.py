"""Exact logical target/source identities, scalar semantics, and actual row bindings."""
from collections import Counter,defaultdict
def mean(values):
    values=list(values);return sum(values)/len(values) if values else 0.
def inspect(tables,unmatched,audit,expected,io):
    eq=io['equal'];blank=io['blank'];targets={t['target_id']:t for t in expected['targets']};sources={s['source_id']:s for s in expected['sources']};rows=defaultdict(list)
    for r in tables['rows']:rows[r['_id']].append(r)
    scalar={};original={};locations={};visibility={}
    for tid,t in targets.items():
        hits=rows.get(tid,[]);r=hits[0] if len(hits)==1 else {};locations[tid]={'sheet':r.get('_sheet'),'row':r.get('_row')};visibility[tid]=bool(r.get('_visible'))
        scalar[tid]={key:eq(r.get(key),t[key],expected['tolerance'].get(key,0)) if r else False for key in ['status','match_count','amount_cny','hours','count']}
        original[tid]=bool(r and r['target_id']==tid and all(eq(r.get(k),v) for k,v in {'project_id':t['original']['project_id'],'contract_id':t['original']['contract_id'],'service_month':t['original']['month'],'project_name':t['original']['name']}.items()))
    expected_unmatched={(u['side'],u['record_id'],u['reason']) for u in expected['unmatched']}
    got_unmatched=[(str(r['side']).strip().lower(),r['_id'],str(r['reason']).strip().lower()) for r in unmatched['rows']]
    un_counts=Counter(got_unmatched);un_checks={side+'/'+rid:un_counts[(side,rid,reason)]==1 for side,rid,reason in expected_unmatched}
    exact_unmatched=set(un_counts)==expected_unmatched and all(v==1 for v in un_counts.values())
    expected_audit=[]
    for edge in expected['edges']:
        s=sources[edge['source_id']];t=edge['target_id'];loc=locations[t]
        expected_audit.append({**edge,'target_sheet':loc['sheet'],'target_row':loc['row'],'source_sheet':s['source_sheet'],'source_row':s['source_row'],'status':'matched',**{k:s[k] for k in ['amount_cny','hours','count']}})
    for u in expected['unmatched']:
        if u['side']=='target':
            tid=u['record_id'];loc=locations[tid];expected_audit.append({'target_id':tid,'target_sheet':loc['sheet'],'target_row':loc['row'],'source_id':None,'source_sheet':None,'source_row':None,'match_basis':None,'status':u['reason'],'amount_cny':None,'hours':None,'count':None})
        else:
            s=sources[u['record_id']];expected_audit.append({'target_id':None,'target_sheet':None,'target_row':None,'source_id':s['source_id'],'source_sheet':s['source_sheet'],'source_row':s['source_row'],'match_basis':None,'status':'unused_source',**{k:s[k] for k in ['amount_cny','hours','count']}})
    identity=lambda r:(r.get('target_id') or '',r.get('source_id') or '',r.get('status') or '')
    keyed=defaultdict(list)
    for r in audit or []:keyed[identity(r)].append(r)
    audit_checks={};edge_checks={};locator_checks={}
    for r in expected_audit:
        ident=identity(r);candidates=keyed.get(ident,[]);tag='/'.join(ident);got=candidates[0] if len(candidates)==1 else None
        fields={k:eq(got.get(k),v,expected['tolerance'].get(k,0)) if got is not None else False for k,v in r.items()}
        # A target locator cannot be credited when the target row is missing/duplicated.
        if r.get('target_id') and locations[r['target_id']]['row'] is None:fields['target_row']=False
        audit_checks[tag]=fields
        edge_checks[tag]=bool(got is not None and fields['match_basis'] and all(fields[k] for k in ['amount_cny','hours','count']))
        locator_checks[tag]=all(fields[k] for k in ['target_sheet','target_row','source_sheet','source_row'])
    expected_keys={identity(r) for r in expected_audit};exact_audit=bool(audit is not None and len(audit)==len(expected_audit) and set(keyed)==expected_keys and all(len(v)==1 for v in keyed.values()))
    unique_targets=len(tables['rows'])==len(targets) and set(rows)==set(targets) and all(len(v)==1 for v in rows.values())
    output_visible=all(visibility.values()) and bool(unmatched['rows']) and all(r['_visible'] for r in unmatched['rows'])
    # Boundary groups have independent weight; numerous easy scalar rows cannot conceal a dropped exception group.
    groups={}
    for status in ['one_to_many','no_match','no_key']:
        ids=[t['target_id'] for t in expected['targets'] if t['status']==status];groups[status]=mean(all(scalar[tid].values()) for tid in ids)
    groups['unmatched_targets']=mean(v for k,v in un_checks.items() if k.startswith('target/'))
    groups['unused_sources']=mean(v for k,v in un_checks.items() if k.startswith('source/'))
    groups['blank_zero_negative']=mean(all(scalar[tid].values()) for tid in ['T0001','T0097','T0115','T0116','T0117','T0118','T0119','T0120'])
    groups['all_connections_retained']=mean(edge_checks.values())*exact_audit
    correctness=.75*mean(mean(fields.values()) for fields in scalar.values())+.25*mean(edge_checks.values())*exact_audit
    return {'correctness':correctness,'boundary':mean(groups.values()),'evidence':mean(locator_checks.values())*exact_audit,
      'scalar_checks':scalar,'original_target_checks':original,'target_locations':locations,'visibility_checks':visibility,
      'unmatched_checks':un_checks,'audit_checks':audit_checks,'boundary_groups':groups,
      'delivery_checks':{'unique_targets':unique_targets,'original_target_fields':all(original.values()),'exact_unmatched':exact_unmatched,'exact_audit':exact_audit,'visible_outputs':output_visible},
      'actual_target_rows':len(tables['rows']),'actual_unmatched_rows':len(unmatched['rows']),'actual_audit_rows':len(audit or [])}
