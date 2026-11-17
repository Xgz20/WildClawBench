"""H054 source-derived scheduling/identity/gate checks; semantic quality remains Judge work."""
from pathlib import Path
import os,json,hashlib,runpy,re
class TrustedEvidenceError(RuntimeError):pass
WEIGHTS={'business_correctness':.55,'boundary_cases':.25,'delivery_integrity':.15,'evidence_binding':.05}
BUSINESS_UNITS={'record_contract':.10,'required_milestones':.55,'window_and_buffer_declarations':.05,'window_feasibility':.05,'reserved_effort':.05,'CPM_values':.10,'critical_path':.025,'CPM_interventions':.075}
BOUNDARY_UNITS={'daily_confirmed_capacity_no_averaging':.20,'single_SANDBOX_tenant_not_parallel':.15,'unknown_Q1_never_grants_production':.20,'irreversible_retirement_deferred_not_fake_date':.15,'actual_rollback_thresholds_and_restore_preconditions':.20,'cohort_specific_identity_and_permission_guards':.10}
def grade(workspace_path=None,**kwargs):
 root=Path(workspace_path or '/tmp_workspace').resolve();gt=Path(__file__).resolve().parent
 def load(name):
  try:return json.loads((gt/name).read_text())
  except (OSError,ValueError,UnicodeError) as e:raise TrustedEvidenceError('H054_TRUSTED_MISSING_OR_INVALID: '+name) from e
 for name,digest in load('trusted_files.json').items():
  p=gt/name
  if p.is_symlink() or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:raise TrustedEvidenceError('H054_TRUSTED_MISSING_OR_DRIFT: '+name)
 o=load('business_oracle.json');contract=load('artifact_contract.json');protected=load('protected_sha256.json');expected=load('expected.json');load('counterexamples.json');load('evidence_requirements.json')
 io=runpy.run_path(str(gt/'native_io.py'));office=runpy.run_path(str(gt/'office_runtime.py'));N=io['number'];U=io['unknown'];norm=io['norm'];D=io['date_value'];errors={}
 ev=os.environ.get('GENERAL_E2E_RULE_EVIDENCE_DIR');lp=os.environ.get('GENERAL_E2E_OFFICE_LOCK');rp=os.environ.get('GENERAL_E2E_OFFICE_RENDER_LOCK')
 if not ev or not lp or not rp:raise TrustedEvidenceError('H054_TRUSTED_OFFICE_OR_EVIDENCE_CONTEXT_MISSING')
 evidence=Path(ev).resolve()
 if any(p==evidence or p in evidence.parents or evidence in p.parents for p in [root,gt]):raise TrustedEvidenceError('H054_TRUSTED_EVIDENCE_OVERLAP')
 evidence.mkdir(parents=True,exist_ok=True)
 try:lock=json.loads(Path(lp).read_text());renderlock=json.loads(Path(rp).read_text());office['validate_office_lock'](lock);office['validate_office_render_lock'](renderlock)
 except (OSError,ValueError,office['OfficeRuntimeError']) as e:raise TrustedEvidenceError('H054_TRUSTED_OFFICE_RUNTIME: '+str(e)) from e
 def office_call(fn,*args,**kw):
  try:return fn(*args,**kw)
  except office['OfficeRuntimeError'] as e:
   if 'UNSUPPORTED' in e.code:raise io['UnsupportedRepresentation']('H054_UNSUPPORTED_REPRESENTATION: '+str(e)) from e
   if e.code in {'OFFICE_INPUT_INVALID','OFFICE_INPUT_LIMIT','OFFICE_DOCX_INPUT_INVALID'}:raise io['CandidateError'](str(e)) from e
   raise TrustedEvidenceError('H054_TRUSTED_OFFICE_FAILURE: '+str(e)) from e
 def candidate(name,fn):
  try:return fn()
  except io['CandidateError'] as e:errors[name]=str(e);return None
 paths={name:candidate(name,lambda name=name:io['candidate_path'](root,'results/'+name)) for name in ['cutover_plan.xlsx','runbook.docx','risks.json']}
 original=candidate('xlsx_native',lambda:io['read_book'](paths['cutover_plan.xlsx'])) if paths['cutover_plan.xlsx'] else None;recalc=None;tables={k:[] for k in contract['tables']}
 if original is not None:
  recalc=candidate('xlsx_recalculation',lambda:office_call(office['recalculate_xlsx'],paths['cutover_plan.xlsx'],lock,evidence/'recalculated',timeout_seconds=60))
  if recalc:
   book=candidate('xlsx_readback',lambda:io['read_book'](recalc['path']))
   if book is not None:tables=io['tables'](book,contract)
 doc=candidate('docx_native',lambda:io['read_docx'](paths['runbook.docx'])) if paths['runbook.docx'] else None
 rendered=candidate('docx_render',lambda:office_call(office['render_docx_pdf'],paths['runbook.docx'],renderlock,evidence/'document',timeout_seconds=60)) if doc else None
 aliases={norm(alias):key for key,vals in contract['json_aliases'].items() for alias in [key,*vals]}
 risks=candidate('risks_json',lambda:io['read_risks'](paths['risks.json'],aliases)) if paths['risks.json'] else None;risks=risks or {}
 def obj(v):return v if isinstance(v,dict) else {}
 def arr(v):return v if isinstance(v,list) else []
 def nonempty(v):return isinstance(v,str) and bool(v.strip())
 def tokens(v):return {s for s in re.split(r'[,，;；\s]+',str(v or '').strip()) if s}
 def same(v,n):return N(v) is not None and abs(N(v)-n)<=1e-8
 def groups(rows,key):
  result={}
  for r in rows:result.setdefault(str(r.get(key,'')),[]).append(r)
  return result
 checks={k:{} for k in WEIGHTS}
 def check(family,name,values):checks[family][name]=sum(bool(v) for v in values)/len(values) if isinstance(values,(list,tuple)) and values else 0. if isinstance(values,(list,tuple)) else float(bool(values))
 schedule=groups(tables['schedule'],'task_id');cpms=groups(tables['cpm'],'task_id');loads=tables['loads'];days=o['workdays'];positions={d:i for i,d in enumerate(days)};records={};dates={};basic=[];calendar=[];durations=[];links=[]
 for key,t in o['tasks'].items():
  rows=schedule.get(key,[]);r=rows[0] if len(rows)==1 else {};records[key]=r
  a=D(r.get('start_date'),obj(r.get('_cells')).get('start_date'));b=D(r.get('end_date'),obj(r.get('_cells')).get('end_date'));dates[key]=(a,b)
  basic.append(len(rows)==1 and r.get('owner')==t['owner'] and r.get('environment')==t['environment'] and tokens(r.get('cohorts'))==set(t['cohorts']) and all(nonempty(r.get(k)) for k in ['summary','acceptance']))
  if key=='T14':continue
  valid=a in positions and b in positions and positions[a]<=positions[b];calendar.append(valid);durations.append(valid and positions[b]-positions[a]+1==t['duration']);links.append(set(t['predecessors'])<=tokens(r.get('dependencies')))
 check('business_correctness','all_fourteen_task_records_and_identity_scope',basic);check('business_correctness','working_day_spans_and_fixed_durations',calendar+durations);check('business_correctness','all_source_dependencies_declared',links)
 # Explicit predecessors may be strengthened; all resolve and must finish on an earlier supplied workday.
 temporal=[];additional=[]
 for key,t in o['tasks'].items():
  if key=='T14':continue
  a,b=dates[key];r=records[key];deps=tokens(r.get('dependencies'))|set(t['predecessors'])
  for pred in deps:
   end=dates.get(pred,(None,None))[1];valid=a in positions and end in positions and positions[end]<positions[a];temporal.append(valid)
   if pred not in t['predecessors']:additional.append(valid)
 check('business_correctness','authorization_and_all_prerequisites_before_successors',temporal)
 window=next((w for w in o['windows'] if w['window_id']==risks.get('selected_window')),None);cut=dates['T11'];review=dates['T10'];last=dates['T13'];ready=positions[cut[0]]-positions[review[1]]-1 if cut[0] in positions and review[1] in positions else None;finishbuffer=len(days)-positions[last[1]]-1 if last[1] in positions else None
 check('business_correctness','finite_cutover_window_and_live_buffers',[bool(window) and cut[0]==cut[1]==window['date'],ready==1,same(risks.get('ready_buffer_workdays'),ready) if ready is not None else False,same(risks.get('completion_buffer_workdays'),finishbuffer) if finishbuffer is not None else False])
 milestone_opportunities=[]
 def closure(key):
  result={key}
  for pred in o['tasks'][key]['predecessors']:result|=closure(pred)
  return result
 actual_window=next((w for w in o['windows'] if cut[0]==cut[1]==w['date'] and expected['window_feasibility'][w['window_id']]),None)
 for milestone in ['T04','T11','T12','T13']:
  needed=closure(milestone);blockers=[]
  for task in sorted(needed):
   a,b=dates[task];valid=a in positions and b in positions and positions[a]<=positions[b]
   if len(schedule.get(task,[]))!=1:blockers.append({'kind':'missing_or_duplicate_task','task':task})
   if not valid:blockers.append({'kind':'invalid_source_calendar_span','task':task,'start':a,'end':b})
   elif positions[b]-positions[a]+1!=o['tasks'][task]['duration']:blockers.append({'kind':'source_duration_mismatch','task':task})
   for pred in o['tasks'][task]['predecessors']:
    end=dates[pred][1]
    if not (a in positions and end in positions and positions[end]<positions[a]):blockers.append({'kind':'required_source_edge','predecessor':pred,'successor':task,'predecessor_end':end,'successor_start':a})
  if 'T11' in needed:
   if actual_window is None:blockers.append({'kind':'no_feasible_published_actual_window','task':'T11','date':cut[0]})
   if ready!=1:blockers.append({'kind':'required_review_preparation_gap','task':'T11','observed_full_workdays':ready})
  milestone_opportunities.append({'milestone':milestone,'scope':'source DAG/calendar prerequisites; resources, Q1 and rollback have independent boundary ownership','dependency_schedule_ready':not blockers,'blocking_reasons':blockers,'execution_authorization':'plan_only_not_executed' if milestone=='T04' else 'current_no_go_unknown_Q1'})
 check('business_correctness','affected_required_milestones',[m['dependency_schedule_ready'] for m in milestone_opportunities]);check('business_correctness','additional_declared_edges_only',additional if additional else True)
 check('business_correctness','buffer_declarations_accurate',[bool(window) and cut[0]==cut[1]==window['date'],same(risks.get('ready_buffer_workdays'),ready) if ready is not None else False,same(risks.get('completion_buffer_workdays'),finishbuffer) if finishbuffer is not None else False])
 wf=groups([r for r in arr(risks.get('window_feasibility')) if isinstance(r,dict)],'window_id');check('business_correctness','all_windows_have_source_supported_feasibility',[len(wf.get(k,[]))==1 and wf[k][0].get('feasible') is v and nonempty(wf[k][0].get('reason')) for k,v in expected['window_feasibility'].items()])
 # Compute minimum and declared daily loads independently, using immutable source capacities.
 actual={};loadkeys=[];loadshape=[];required={};spans={}
 for key,t in o['tasks'].items():
  a,b=dates[key]
  if key=='T14' or a not in positions or b not in positions or positions[a]>positions[b]:continue
  span=days[positions[a]:positions[b]+1];spans[key]=span
  for date in span:
   for role,h in t['hours'].items():
    if h:required[key,date,role]=h
 for r in loads:
  key=str(r.get('task_id',''));date=D(r.get('date'),obj(r.get('_cells')).get('date'));role=r.get('role');h=N(r.get('hours'));triple=(key,date,role);loadkeys.append(triple);valid=key in o['tasks'] and key!='T14' and date in spans.get(key,[]) and role in o['roles'] and h is not None and h>=0;loadshape.append(valid)
  if date in positions and role in o['roles'] and h is not None:actual[triple]=actual.get(triple,0)+h
 check('business_correctness','each_task_day_role_minimum_reserved',bool(required) and all(actual.get(k,0)>=h-1e-8 for k,h in required.items()) and bool(loads) and all(loadshape) and len(loadkeys)==len(set(loadkeys)))
 usage={date:{r:0 for r in o['roles']} for date in days}
 for key in set(required)|set(actual):
  _,date,role=key
  if date in positions and role in o['roles']:usage[date][role]+=max(required.get(key,0),actual.get(key,0))
 check('boundary_cases','daily_confirmed_capacity_no_averaging',bool(loads) and all(loadshape) and all(0<=h<=o['capacities'][date][r]+1e-8 for date,values in usage.items() for r,h in values.items()))
 occupied={}
 for key in o['exclusive_tasks']:
  for date in spans.get(key,[]):occupied.setdefault(date,[]).append(key)
 check('boundary_cases','single_SANDBOX_tenant_not_parallel',all(key in spans for key in o['exclusive_tasks']) and all(len(keys)<=1 for keys in occupied.values()))
 approval=obj(risks.get('approval'));reviewby=D(approval.get('review_by'));current_mode=risks.get('mode')=='plan_only' and risks.get('current_go')=='no_go';statuses=[records[k].get('status')==('deferred' if k=='T14' else 'conditional' if k in ['T11','T12','T13'] else 'planned') for k in o['tasks']]
 check('boundary_cases','unknown_Q1_never_grants_production',current_mode and approval.get('id')=='Q1' and approval.get('status')=='unknown' and approval.get('owner')=='SEC' and reviewby in positions and review[0] in positions and positions[reviewby]<=positions[review[0]] and all(records[k].get('status')=='conditional' for k in ['T11','T12','T13']))
 retirement=obj(risks.get('retirement'));check('boundary_cases','irreversible_retirement_deferred_not_fake_date',[retirement.get('task_id')=='T14' and retirement.get('status')=='deferred',retirement.get('approval_id')=='Q2' and retirement.get('approval_status')=='unknown',same(retirement.get('minimum_full_workdays'),5),retirement.get('earliest_date_status')=='after_supplied_calendar_unknown' and U(retirement.get('earliest_date')),U(records['T14'].get('start_date')) and U(records['T14'].get('end_date')),not any(r.get('task_id')=='T14' for r in loads)])
 rollback=obj(risks.get('rollback'));triggers=groups([r for r in arr(rollback.get('triggers')) if isinstance(r,dict)],'metric_id');triggerchecks=[]
 for t in o['triggers']:
  rows=triggers.get(t['metric_id'],[]);r=rows[0] if len(rows)==1 else {};triggerchecks.append(len(rows)==1 and norm(r.get('operator'))==t['operator'] and same(r.get('threshold'),t['threshold']) and same(r.get('consecutive_checks'),t['consecutive_checks']))
 check('boundary_cases','actual_rollback_thresholds_and_restore_preconditions',[same(rollback.get('max_minutes'),60),same(rollback.get('interval_minutes'),5),rollback.get('scope')=='before_retirement_only',rollback.get('snapshot_required') is True,rollback.get('owner')=='OPS' and rollback.get('validation_task')=='T07',*triggerchecks])
 for name in ['irreversible_retirement_deferred_not_fake_date','actual_rollback_thresholds_and_restore_preconditions']:
  checks['boundary_cases'][name]=float(checks['boundary_cases'][name]==1.)
 identities=groups([r for r in arr(risks.get('identity_controls')) if isinstance(r,dict)],'cohort');check('boundary_cases','cohort_specific_identity_and_permission_guards',[len(identities.get(v['cohort'],[]))==1 and all(identities[v['cohort']][0].get(k)==value and (not isinstance(value,bool) or isinstance(identities[v['cohort']][0].get(k),bool)) for k,value in v.items()) for v in o['identity_controls']])
 # Full CPM is an objective model; path words and reference schedule are not matched.
 fields=['duration','es','ef','ls','lf','total_float','critical'];baseline=[]
 for key,want in o['cpm']['tasks'].items():
  rows=cpms.get(key,[]);r=rows[0] if len(rows)==1 else {};baseline.extend(len(rows)==1 and same(r.get(k),want[k]) for k in fields)
 check('business_correctness','complete_original_DAG_CPM',baseline)
 critical_paths=arr(risks.get('critical_paths'));validpaths=[]
 for path in critical_paths:
  valid=isinstance(path,list) and bool(path) and all(k in o['cpm']['tasks'] for k in path) and len(set(path))==len(path)
  validpaths.append(valid and not o['tasks'][path[0]]['predecessors'] and path[-1]=='T13' and all(a in o['tasks'][b]['predecessors'] for a,b in zip(path,path[1:])) and sum(o['tasks'][k]['duration'] for k in path)==o['cpm']['duration'])
 check('business_correctness','at_least_one_true_critical_path',bool(validpaths) and all(validpaths))
 variant_receipts=[];dynamic=[]
 if recalc and all(len(cpms.get(k,[]))==1 for k in o['cpm']['tasks']):
  for task in ['T06','T08']:
   r=cpms[task][0];cell=obj(r.get('_cells')).get('duration',{});change={'sheet':cell.get('sheet'),'cell':cell.get('address'),'value':o['tasks'][task]['duration']+1}
   prepared=office_call(office['prepare_xlsx_numeric_intervention'],paths['cutover_plan.xlsx'],[change],evidence/'variants'/task/'prepared');res=office_call(office['recalculate_xlsx'],prepared['path'],lock,evidence/'variants'/task/'calculated',timeout_seconds=60);b=io['read_book'](res['path']);now=groups(io['tables'](b,contract)['cpm'],'task_id');want=io['dag_cpm'](o['tasks'],{task:o['tasks'][task]['duration']+1});passed=[]
   for key,expected_row in want['tasks'].items():
    row=now.get(key,[]);row=row[0] if len(row)==1 else {};passed.extend(same(row.get(k),expected_row[k]) for k in fields)
   dynamic.append(all(passed));variant_receipts.append({'task':task,'prepared':prepared,'recalculation':res,'scalar_fields_passed':sum(passed),'scalar_fields':len(passed),'branch_opportunity_passed':all(passed),'expected_project_duration':want['duration']})
 else:dynamic=[False]
 check('business_correctness','CPM_reacts_to_each_parallel_branch_duration',dynamic)
 # Native factual cross-reference only; prose adequacy and no-go/runbook quality require semantic Judge.
 actualfacts={'selected_window':risks.get('selected_window'),'cutover_date':cut[0],'Q1_status':approval.get('status'),'T14_status':retirement.get('status'),'ready_buffer_workdays':ready,'completion_buffer_workdays':finishbuffer,'cpm_duration':N(cpms.get('T13',[{}])[0].get('ef'))}
 riskfacts={**actualfacts,'cutover_date':window['date'] if window else None,'ready_buffer_workdays':N(risks.get('ready_buffer_workdays')),'completion_buffer_workdays':N(risks.get('completion_buffer_workdays'))}
 factchecks=[]
 if doc:
  for key,value in actualfacts.items():
   vals=doc['facts'].get(norm(key),[])
   def equal_fact(v,w):return same(v,w) if isinstance(w,(int,float)) else D(v)==w if key=='cutover_date' else v==str(w)
   factchecks.append(len(vals)==1 and equal_fact(vals[0],value) and equal_fact(vals[0],riskfacts[key]))
 check('delivery_integrity','native_deliverables_parse_and_render',[original is not None,recalc is not None,doc is not None and nonempty(doc.get('text')),rendered is not None,bool(risks)])
 check('delivery_integrity','actual_cross_artifact_fact_table',factchecks)
 changed=[]
 for rel,digest in protected.items():
  p=root/rel
  if p.is_symlink() or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:changed.append(rel)
 check('delivery_integrity','original_inputs_unchanged',not changed)
 def locator(value):
  if not nonempty(value):return False
  refs=re.findall(r'(work_items\.csv|resources\.xlsx|calendar\.csv|acceptance\.md)\s*#\s*([^;；\s]+)',value)
  if not refs:return False
  for file,loc in refs:
   if file=='work_items.csv' and loc not in o['tasks']:return False
   if file=='calendar.csv' and loc not in {r['date'] for r in o['calendar']}:return False
   if file=='resources.xlsx' and (not loc.startswith('capacity@') or loc.split('@',1)[1] not in o['capacities']):return False
   if file=='acceptance.md' and loc not in {'A'+str(i).zfill(2) for i in range(1,8)}:return False
  return True
 check('evidence_binding','native_task_source_locators_resolve',[locator(r.get('source_ref')) for r in tables['schedule']])
 check('evidence_binding','unresolved_conditions_have_owner_and_next_action',bool(arr(risks.get('unresolved'))) and all(isinstance(r,dict) and all(nonempty(r.get(k)) for k in ['condition','owner','next_action']) and locator(r.get('source_ref')) for r in arr(risks.get('unresolved'))))
 b=checks['business_correctness'];units={'record_contract':sum([b['all_fourteen_task_records_and_identity_scope'],b['working_day_spans_and_fixed_durations'],b['all_source_dependencies_declared'],b['additional_declared_edges_only'],sum(statuses)/len(statuses)])/5,'required_milestones':b['affected_required_milestones'],'window_and_buffer_declarations':b['buffer_declarations_accurate'],'window_feasibility':b['all_windows_have_source_supported_feasibility'],'reserved_effort':b['each_task_day_role_minimum_reserved'],'CPM_values':b['complete_original_DAG_CPM'],'critical_path':b['at_least_one_true_critical_path'],'CPM_interventions':b['CPM_reacts_to_each_parallel_branch_duration']}
 scores={'business_correctness':sum(BUSINESS_UNITS[k]*v for k,v in units.items()),'boundary_cases':sum(BOUNDARY_UNITS[k]*checks['boundary_cases'][k] for k in BOUNDARY_UNITS),**{k:sum(checks[k].values())/len(checks[k]) for k in ['delivery_integrity','evidence_binding']}};scores['overall_score']=sum(WEIGHTS[k]*scores[k] for k in WEIGHTS)
 (evidence/'h054-analysis.json').write_text(json.dumps({'status':'AUTHOR_AUTOMATIC_COMPONENT_ONLY','scores':scores,'checks':checks,'business_opportunity_units':units,'business_unit_weights':BUSINESS_UNITS,'boundary_unit_weights':BOUNDARY_UNITS,'milestone_opportunities':milestone_opportunities,'causal_ownership':'Required source DAG/calendar milestone failures belong to business. Capacities/shared tenant/Q1/retirement/rollback/identity safety belong only to boundary; unrelated declaration edge does not zero milestones. Input protection belongs only to delivery.','candidate_errors':errors,'changed_inputs':changed,'daily_usage':usage,'shared_tenant_occupancy':occupied,'actual_dates':dates,'actual_facts':actualfacts,'variant_receipts':variant_receipts,'semantic_boundary':'Natural language plan/acceptance/rollback handoff adequacy remains .25 blueprint Judge; no real execution/Judge/finalize','source_sha256':o['source_sha256']},ensure_ascii=False,indent=2)+'\n');return scores
