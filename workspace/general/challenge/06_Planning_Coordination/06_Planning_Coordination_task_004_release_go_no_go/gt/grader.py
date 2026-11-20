"""H056 source-folded scheduling/gates; usefulness of decisions remains semantic Judge."""
from pathlib import Path
import os,json,hashlib,runpy,re,copy
class TrustedEvidenceError(RuntimeError):pass
WEIGHTS={'business_correctness':.55,'boundary_cases':.25,'delivery_integrity':.15,'evidence_binding':.05}
BUSINESS_UNITS={'records':.05,'effective_scope_and_events':.20,'required_milestone_opportunities':.35,'window_path_reasoning':.10,'minimal_blockers_and_alternatives':.10,'calculation_baseline':.10,'live_interventions':.10}
BOUNDARY_UNITS={'daily_resource_and_venue':.35,'budget_integrity_and_limits':.25,'approval_and_plan_scope':.40}
def grade(workspace_path=None,**kwargs):
 root=Path(workspace_path or '/tmp_workspace').resolve();gt=Path(__file__).resolve().parent
 def load(name):
  try:return json.loads((gt/name).read_text())
  except (OSError,ValueError,UnicodeError) as e:raise TrustedEvidenceError('H056_TRUSTED_MISSING_OR_INVALID: '+name) from e
 for name,digest in load('trusted_files.json').items():
  p=gt/name
  if p.is_symlink() or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:raise TrustedEvidenceError('H056_TRUSTED_MISSING_OR_DRIFT: '+name)
 o=load('business_oracle.json');contract=load('artifact_contract.json');protected=load('protected_sha256.json');load('expected.json');load('counterexamples.json');load('evidence_requirements.json');io=runpy.run_path(str(gt/'native_io.py'));office=runpy.run_path(str(gt/'office_runtime.py'));calc=runpy.run_path(str(gt/'schedule_model.py'))['calculate'];N=io['number'];norm=io['norm'];D=io['date_value'];errors={}
 ev=os.environ.get('GENERAL_E2E_RULE_EVIDENCE_DIR');lp=os.environ.get('GENERAL_E2E_OFFICE_LOCK');rp=os.environ.get('GENERAL_E2E_OFFICE_RENDER_LOCK')
 if not ev or not lp or not rp:raise TrustedEvidenceError('H056_TRUSTED_OFFICE_OR_EVIDENCE_CONTEXT_MISSING')
 evidence=Path(ev).resolve()
 if any(p==evidence or p in evidence.parents or evidence in p.parents for p in [root,gt]):raise TrustedEvidenceError('H056_TRUSTED_EVIDENCE_OVERLAP')
 evidence.mkdir(parents=True,exist_ok=True)
 try:lock=json.loads(Path(lp).read_text());renderlock=json.loads(Path(rp).read_text());office['validate_office_lock'](lock);office['validate_office_render_lock'](renderlock)
 except (OSError,ValueError,office['OfficeRuntimeError']) as e:raise TrustedEvidenceError('H056_TRUSTED_OFFICE_RUNTIME: '+str(e)) from e
 def off(fn,*args,**kw):
  try:return fn(*args,**kw)
  except office['OfficeRuntimeError'] as e:
   if 'UNSUPPORTED' in e.code:raise io['UnsupportedRepresentation']('H056_UNSUPPORTED_REPRESENTATION: '+str(e)) from e
   if e.code in {'OFFICE_INPUT_INVALID','OFFICE_INPUT_LIMIT','OFFICE_DOCX_INPUT_INVALID'}:raise io['CandidateError'](str(e)) from e
   raise TrustedEvidenceError('H056_TRUSTED_OFFICE_FAILURE: '+str(e)) from e
 def candidate(name,fn):
  try:return fn()
  except io['CandidateError'] as e:errors[name]=str(e);return None
 paths={n:candidate(n,lambda n=n:io['candidate_path'](root,'results/'+n)) for n in ['release_plan.xlsx','decision.docx','alternatives.json']};original=candidate('xlsx_native',lambda:io['read_book'](paths['release_plan.xlsx'])) if paths['release_plan.xlsx'] else None;recalc=None;tables={k:[] for k in contract['tables']}
 if original is not None:
  recalc=candidate('xlsx_recalculate',lambda:off(office['recalculate_xlsx'],paths['release_plan.xlsx'],lock,evidence/'recalculated',timeout_seconds=60))
  if recalc:
   fresh=io['read_book'](recalc['path'])
   if any(c.get('kind')=='e' and c.get('value')=='#NAME?' for s in fresh for c in s['cells'].values()):raise io['UnsupportedRepresentation']('H056_UNSUPPORTED_REPRESENTATION: unresolved locked-engine function')
   tables=io['tables'](fresh,contract)
 doc=candidate('docx_native',lambda:io['read_docx'](paths['decision.docx'])) if paths['decision.docx'] else None;render=candidate('docx_render',lambda:off(office['render_docx_pdf'],paths['decision.docx'],renderlock,evidence/'document',timeout_seconds=60)) if doc else None
 def read_json():
  def pairs(p):
   d={}
   for k,v in p:
    if k in d:raise io['CandidateError']('duplicate JSON key')
    d[k]=v
   return d
  try:
   value=json.loads(paths['alternatives.json'].read_text(encoding='utf-8-sig'),object_pairs_hook=pairs,parse_constant=lambda v:(_ for _ in ()).throw(ValueError(v)))
   if not isinstance(value,dict):raise ValueError('object required')
   return value
  except (ValueError,UnicodeError,OSError) as e:raise io['CandidateError']('invalid alternatives JSON') from e
 alt=candidate('alternatives_json',read_json) if paths['alternatives.json'] else None;alt=alt or {}
 def text(v):return isinstance(v,str) and bool(v.strip())
 def mean(v):
  v=list(v);return sum(bool(x) for x in v)/len(v) if v else 0.
 def same(a,b):return N(a) is not None and b is not None and abs(N(a)-b)<=1e-8
 def grouped(rows,key):
  d={}
  for r in rows:d.setdefault(str(r.get(key) or '').strip(),[]).append(r)
  return d
 def one(d,k):return d[k][0] if len(d.get(k,[]))==1 else {}
 schedule=grouped(tables['schedule'],'task_id');costgroups=grouped(tables['costs'],'task_id');cp=grouped(tables['cpm'],'task_id');budgetrows=grouped(tables['budget'],'key');selected={k for k in o['tasks'] if one(schedule,k).get('status')!='not_selected' and one(schedule,k)};path='A' if 'T09A' in selected and 'T09B' not in selected else 'B' if 'T09B' in selected and 'T09A' not in selected else None;expected_selected={k for k,t in o['tasks'].items() if t['selection_group']=='mandatory' or k=='T12' and o['effective_state']['T12_required'] or k=='T09'+str(path)};tasks={}
 for k in expected_selected:
  if k not in o['tasks']:continue
  t=dict(o['tasks'][k]);t['predecessors']=[p for g in t['prerequisite_groups'] for p in g if p in expected_selected];t['venue']=('HALL' if path=='A' else 'STUDIO') if t['venue']=='PATH_VENUE' else t['venue'];tasks[k]=t
 days=o['days'];dateby={d['date']:i for i,d in enumerate(days,1)};dayby={d['day_id']:d['date'] for d in days};positions={};records=[];provision={};loadshape=[];used={};occupied={};minimums=[]
 for key,t in o['tasks'].items():
  r=one(schedule,key);a=D(r.get('start_date'),r.get('_cells',{}).get('start_date'));b=D(r.get('end_date'),r.get('_cells',{}).get('end_date'));positions[key]=(dateby.get(a),dateby.get(b));records.append(bool(r) and r.get('owner')==t['owner'] and all(text(r.get(k)) for k in ['summary','acceptance']))
  if key in tasks:
   start,end=positions[key];provision[key]=start is not None and end is not None and end-start+1>=t['duration'];decl=set(re.split(r'[,;；\s]+',str(r.get('dependencies') or '')));records.append(all(any(p in decl and p in tasks for p in g) for g in t['prerequisite_groups']))
  else:records.append(r.get('status')=='not_selected' and r.get('start_date') in [None,''] and r.get('end_date') in [None,''])
 # Additional declarations may constrain a real schedule, but must not invent
 # IDs, cycles or a predecessor that actually finishes after its successor.
 # Required source ordering already belongs to milestone closure below.
 for k,t in tasks.items():
  r=one(schedule,k)
  if not r:continue
  declared={p for p in re.split(r'[,;；\s]+',str(r.get('dependencies') or '')) if p};required={p for g in t['prerequisite_groups'] for p in g if p in tasks};start,_=positions.get(k,(None,None))
  records.append(all(p in tasks and start is not None and positions.get(p,(None,None))[1] is not None and positions[p][1]<start for p in declared-required))
 keys=[]
 for r in tables['loads']:
  k=str(r.get('task_id') or '');date=D(r.get('date'),r.get('_cells',{}).get('date'));role=r.get('role');h=N(r.get('hours'));pos=dateby.get(date);keys.append((k,date,role));start,end=positions.get(k,(None,None));physical=k in tasks and pos is not None and role in o['roles'] and h is not None and h>=0;valid=physical and start is not None and end is not None and start<=pos<=end;loadshape.append(valid)
  if physical:used[pos,role]=used.get((pos,role),0)+h
 for k,t in tasks.items():
  start,end=positions.get(k,(None,None));ok=provision.get(k,False)
  if start is not None and end is not None:
   ok &= end-start+1==t['duration']
   for pos in range(start,end+1):
    for role,h in t['hours'].items():ok &= sum(N(r.get('hours')) or 0 for r in tables['loads'] if r.get('task_id')==k and D(r.get('date'),r.get('_cells',{}).get('date'))==days[pos-1]['date'] and r.get('role')==role)>=h
    if t['venue']!='NONE':occupied.setdefault((pos,t['venue']),[]).append(k)
  minimums.append(ok);provision[k]=ok
 def closure(k,seen=None):
  seen=set() if seen is None else set(seen)
  if k in seen:return [{'kind':'source_cycle','task':k}]
  seen.add(k);reasons=[];t=tasks.get(k);start,end=positions.get(k,(None,None))
  if not t or not provision.get(k):return [{'kind':'required_task_duration_or_load_missing','task':k}]
  for g in t['prerequisite_groups']:
   options=[p for p in g if p in tasks];good=[];bad=[]
   for p in options:
    a,b=positions.get(p,(None,None));why=closure(p,seen)
    if b is None or start is None or b>=start:why=why+[{'kind':'required_predecessor_not_before','predecessor':p,'successor':k}]
    if why:bad.append(why)
    else:good.append(p)
   if not good:reasons.append({'kind':'required_source_group_blocked','task':k,'group':g,'causes':bad})
  return reasons
 opportunities=[{'task_id':k,'blocking_reasons':closure(k)} for k in ['T12','T14','T15','T16','T17']];milestone_score=mean(not v['blocking_reasons'] for v in opportunities)
 def listof(v):return v if isinstance(v,list) else []
 scope=alt.get('effective_scope') if isinstance(alt.get('effective_scope'),dict) else {};events=grouped(listof(alt.get('effective_events')),'event_id');scope_checks=[scope.get(k) is v if isinstance(v,bool) else scope.get(k)==v for k,v in o['effective_state'].items()]+[one(events,r['event_id']).get('status')==r['status'] for r in o['effective_events']];scenario=grouped(listof(alt.get('window_paths')),'window_id');matrix={r['path']+'/'+r['window_id']:r for r in load('expected.json')['window_paths']};reason_checks=[]
 for key,want in matrix.items():
  matches=[r for r in scenario.get(want['window_id'],[]) if r.get('path')==want['path']];r=matches[0] if len(matches)==1 else {};reason_checks.append(all(r.get(k) is v for k,v in want.items() if k in ['schedule_feasible','within_budget','conditional_feasible']) and set(listof(r.get('blockers')))==set(want['blockers']) and text(r.get('reason')))
 declared=listof(alt.get('minimum_blocker_sets'));valid_min=[(v['path'],v['window_id'],set(v['blockers'])) for v in o['minimum_blocker_sets']];minimal_ok=bool(declared) and all(any(r.get('path')==p and r.get('window_id')==w and set(listof(r.get('blockers')))==b for p,w,b in valid_min) for r in declared);fallbacks=listof(alt.get('fallbacks'));fallback_ok=all(any(r.get('path')==p and r.get('window_id') in ['W1','W2'] and same(r.get('total_cost'),cost) and text(r.get('trigger')) and len(listof(r.get('conditions')))>=2 for r in fallbacks) for p,cost in [('A',7850),('B',6700)]);riskrows=listof(alt.get('risks'));risks_ok=len(riskrows)>=3 and all(all(text(r.get(k)) for k in ['id','trigger','owner','response','source_ref']) for r in riskrows)
 durations={k:N(one(cp,k).get('duration')) for k in tasks};durations={k:v if v is not None and v>0 else tasks[k]['duration'] for k,v in durations.items()};costs={k:{'selected':N(one(costgroups,k).get('selected')) or 0,'fixed_cost':N(one(costgroups,k).get('fixed_cost')) or 0} for k in o['tasks']};budgetcap=N(one(budgetrows,'budget_cap').get('value'));budgetcap=budgetcap if budgetcap is not None else 0;model=calc(tasks,durations,costs,budgetcap)
 def values_match(tab,want):
  cc=grouped(tab['cpm'],'task_id');ff=grouped(tab['costs'],'task_id');bb=grouped(tab['budget'],'key');v=[]
  for k,fields in want['cpm'].items():v.extend(same(one(cc,k).get(f),value) for f,value in fields.items())
  v.extend(same(one(ff,k).get('extended_cost'),value) for k,value in want['costs'].items());v.extend(same(one(bb,k).get('value'),value) for k,value in want['budget'].items());return v
 base_calcs=values_match(tables,model);variants=[];dynamic=[]
 if recalc and all(one(cp,k).get('_cells',{}).get('duration',{}).get('address') for k in ['T12','T08']) and one(costgroups,'T09B').get('_cells',{}).get('fixed_cost',{}).get('address'):
  for label in ['T12_duration','T08_duration','T09B_cost']:
   dd=dict(durations);ff=copy.deepcopy(costs)
   if label=='T09B_cost':cell=one(costgroups,'T09B')['_cells']['fixed_cost'];value=ff['T09B']['fixed_cost']+100;ff['T09B']['fixed_cost']=value
   else:
    key=label.split('_')[0];cell=one(cp,key)['_cells']['duration'];value=dd[key]+(1 if key=='T12' else 3);dd[key]=value
   change={'sheet':cell['sheet'],'cell':cell['address'],'value':value};prepared=off(office['prepare_xlsx_numeric_intervention'],paths['release_plan.xlsx'],[change],evidence/'variants'/label/'prepared');res=off(office['recalculate_xlsx'],prepared['path'],lock,evidence/'variants'/label/'calculated',timeout_seconds=60);newtables=io['tables'](io['read_book'](res['path']),contract);want=calc(tasks,dd,ff,budgetcap);checks=values_match(newtables,want);dynamic.append(all(checks));variants.append({'label':label,'change':change,'prepared':prepared,'recalculation':res,'checked_scalar_fields':len(checks),'scalar_fields_passed':sum(checks),'passed':all(checks)})
 else:dynamic=[False]
 resource_ok=all(r.get('task_id') in tasks and D(r.get('date'),r.get('_cells',{}).get('date')) in dateby and r.get('role') in o['roles'] and N(r.get('hours')) is not None and N(r.get('hours'))>=0 for r in tables['loads']) and all(h<=o['capacities'][days[pos-1]['day_id']][role]+1e-8 for (pos,role),h in used.items());venue_ok=all(len(ks)==1 and o['venues'][days[pos-1]['day_id']][venue]==1 for (pos,venue),ks in occupied.items()) and all(one(schedule,k).get('venue')==t['venue'] for k,t in tasks.items() if one(schedule,k));quotes=all(same(one(costgroups,k).get('fixed_cost'),t['fixed_cost']) and same(one(costgroups,k).get('selected'),int(k in tasks)) for k,t in o['tasks'].items());financial_ok=quotes and budgetcap==o['effective_state']['budget_cap'] and sum(t['fixed_cost'] for t in tasks.values())<=budgetcap
 approvals=grouped(listof(alt.get('approvals')),'id');approval_ok=all(one(approvals,k).get('status')=='unknown' and one(approvals,k).get('owner')==v['owner'] and text(one(approvals,k).get('next_action')) for k,v in o['approvals'].items());status_ok=all(one(schedule,k).get('status')==('conditional' if k in ['T15','T16','T17'] else 'planned') for k in tasks if one(schedule,k));scope_ok=alt.get('current_go')=='no_go' and alt.get('mode')=='plan_only' and alt.get('scope_limit')=='offline_proposal';chosen=alt.get('selected_window');launch_start=positions.get('T15',(None,None))[0];chosen_ok=chosen in o['windows'] and launch_start is not None and days[launch_start-1]['day_id']==o['windows'][chosen] and alt.get('selected_path')==path
 records_ok=all(loadshape) and len(keys)==len(set(keys)) and set(schedule)==set(o['tasks']) and selected==expected_selected and all(records) and bool(tasks) and chosen_ok and set(cp)==set(tasks) and set(costgroups)==set(o['tasks'])
 truecp=o['cpms'].get(path,{'records':{},'critical_paths':[]});critical=listof(alt.get('critical_paths'));cp_path_ok=bool(critical) and all(v in truecp['critical_paths'] for v in critical);duration_source=all(same(one(cp,k).get('duration'),t['duration']) for k,t in tasks.items())
 units={'records':float(records_ok),'effective_scope_and_events':mean(scope_checks),'required_milestone_opportunities':milestone_score,'window_path_reasoning':mean(reason_checks),'minimal_blockers_and_alternatives':mean([minimal_ok,fallback_ok,risks_ok,cp_path_ok]),'calculation_baseline':mean([bool(base_calcs) and all(base_calcs),duration_source]),'live_interventions':mean(dynamic)};bound={'daily_resource_and_venue':mean([resource_ok,venue_ok]),'budget_integrity_and_limits':float(financial_ok),'approval_and_plan_scope':mean([approval_ok,status_ok,scope_ok])}
 launchdate=days[launch_start-1]['date'] if launch_start else None;facts={'selected_path':path,'selected_window':chosen,'launch_date':launchdate,'total_cost':model['budget']['total_cost'],'budget_cap':budgetcap,'budget_remaining':model['budget']['budget_remaining'],'T12_duration':N(one(cp,'T12').get('duration')),'current_go':alt.get('current_go'),'Q_RELEASE_status':one(approvals,'Q_RELEASE').get('status'),'cpm_duration':model['cpm_duration']};factchecks=[]
 if doc:
  for k,value in facts.items():
   got=doc['facts'].get(norm(k),[]);factchecks.append(len(got)==1 and (same(got[0],value) if isinstance(value,(int,float)) else got[0]==str(value)))
 changed=[k for k,h in protected.items() if not (root/k).is_file() or (root/k).is_symlink() or hashlib.sha256((root/k).read_bytes()).hexdigest()!=h];delivery={'native_artifacts':mean([original is not None,recalc is not None,doc is not None,render is not None,bool(alt)]),'cross_native_facts':mean(factchecks),'input_protection':float(not changed)}
 def locator(v):
  if not text(v):return False
  matches=re.findall(r'(work_breakdown\.csv|resources\.xlsx|changes\.jsonl|gates\.md)#([^;；\s]+)',v)
  if not matches:return False
  for file,loc in matches:
   if file=='work_breakdown.csv' and loc not in o['tasks']:return False
   if file=='gates.md' and loc not in {'G0'+str(i) for i in range(1,8)}:return False
   if file=='changes.jsonl' and loc not in {'E01','E02','E03','E04'}:return False
   if file=='resources.xlsx' and loc not in {'windows','budget',*['capacity@'+d['day_id'] for d in days]}:return False
  return True
 evidence_ok=mean([locator(r.get('source_ref')) for r in tables['schedule']]+[locator(r.get('source_ref')) for r in riskrows]);scores={'business_correctness':sum(BUSINESS_UNITS[k]*v for k,v in units.items()),'boundary_cases':sum(BOUNDARY_UNITS[k]*v for k,v in bound.items()),'delivery_integrity':sum(delivery.values())/3,'evidence_binding':evidence_ok};scores['overall_score']=sum(WEIGHTS[k]*scores[k] for k in WEIGHTS)
 analysis={'scores':scores,'business_units':units,'business_unit_weights':BUSINESS_UNITS,'boundary_units':bound,'boundary_unit_weights':BOUNDARY_UNITS,'milestone_opportunities':opportunities,'effective_scope_checks':scope_checks,'scenario_checks':reason_checks,'minimum_blockers_valid':minimal_ok,'financial_source_valid':financial_ok,'resource_valid':resource_ok,'venue_valid':venue_ok,'facts':facts,'model':model,'variant_receipts':variants,'changed_inputs':changed,'candidate_errors':errors,'causal_ownership':'Effective scope/dependency/duration/minimum provision and affected milestones are business; daily overload/venue/financial/unknown approval and plan scope are boundary. Input mutation only delivery protection. No global zero on unrelated declarations.','semantic_boundary':'Narrative usefulness, risk/conditions quality and evidence interpretation remain .25 Judge; no actual release/approval proof from fields','real_Harness_Judge_finalize':False};(evidence/'h056-analysis.json').write_text(json.dumps(analysis,ensure_ascii=False,indent=2)+'\n');return scores
