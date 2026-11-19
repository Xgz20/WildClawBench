"""H055 objective source/time/fee/sequence checks; competence evidence quality is Judge work."""
from pathlib import Path
import os,json,hashlib,runpy,re,copy
class TrustedEvidenceError(RuntimeError):pass
WEIGHTS={'business_correctness':.55,'boundary_cases':.25,'delivery_integrity':.15,'evidence_binding':.05}
BUSINESS_UNITS={'record_contract':.10,'monthly_coverage':.10,'weekly_feasibility_phases':.20,'selected_activity_hours_and_bounds':.15,'milestone_contracts':.25,'calculation_baseline':.10,'live_model_interventions':.10}
BOUNDARY_UNITS={'source_prerequisite_opportunities':.40,'fee_integrity_and_limits':.25,'no_course_to_competence_shortcut':.25,'unknown_practice_and_scope':.10}
def grade(workspace_path=None,**kwargs):
 root=Path(workspace_path or '/tmp_workspace').resolve();gt=Path(__file__).resolve().parent
 def load(name):
  try:return json.loads((gt/name).read_text())
  except (OSError,ValueError,UnicodeError) as e:raise TrustedEvidenceError('H055_TRUSTED_MISSING_OR_INVALID: '+name) from e
 for name,digest in load('trusted_files.json').items():
  p=gt/name
  if p.is_symlink() or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:raise TrustedEvidenceError('H055_TRUSTED_MISSING_OR_DRIFT: '+name)
 o=load('business_oracle.json');contract=load('artifact_contract.json');protected=load('protected_sha256.json');load('expected.json');load('counterexamples.json');load('evidence_requirements.json');io=runpy.run_path(str(gt/'native_io.py'));office=runpy.run_path(str(gt/'office_runtime.py'));calculate=runpy.run_path(str(gt/'plan_model.py'))['calculate'];N=io['number'];U=io['unknown'];norm=io['norm'];WN=lambda v:io['week_number'](v,o);MN=io['month_value'];errors={}
 ev=os.environ.get('GENERAL_E2E_RULE_EVIDENCE_DIR');lp=os.environ.get('GENERAL_E2E_OFFICE_LOCK');rp=os.environ.get('GENERAL_E2E_OFFICE_RENDER_LOCK')
 if not ev or not lp or not rp:raise TrustedEvidenceError('H055_TRUSTED_OFFICE_OR_EVIDENCE_CONTEXT_MISSING')
 evidence=Path(ev).resolve()
 if any(p==evidence or p in evidence.parents or evidence in p.parents for p in [root,gt]):raise TrustedEvidenceError('H055_TRUSTED_EVIDENCE_OVERLAP')
 evidence.mkdir(parents=True,exist_ok=True)
 try:lock=json.loads(Path(lp).read_text());renderlock=json.loads(Path(rp).read_text());office['validate_office_lock'](lock);office['validate_office_render_lock'](renderlock)
 except (OSError,ValueError,office['OfficeRuntimeError']) as e:raise TrustedEvidenceError('H055_TRUSTED_OFFICE_RUNTIME: '+str(e)) from e
 def office_call(fn,*args,**kw):
  try:return fn(*args,**kw)
  except office['OfficeRuntimeError'] as e:
   if 'UNSUPPORTED' in e.code:raise io['UnsupportedRepresentation']('H055_UNSUPPORTED_REPRESENTATION: '+str(e)) from e
   if e.code in {'OFFICE_INPUT_INVALID','OFFICE_INPUT_LIMIT','OFFICE_DOCX_INPUT_INVALID'}:raise io['CandidateError'](str(e)) from e
   raise TrustedEvidenceError('H055_TRUSTED_OFFICE_FAILURE: '+str(e)) from e
 def candidate(name,fn):
  try:return fn()
  except io['CandidateError'] as e:errors[name]=str(e);return None
 artifact_paths={name:candidate(name,lambda name=name:io['candidate_path'](root,'results/'+name)) for name in ['learning_plan.xlsx','portfolio.docx']};original=candidate('xlsx_native',lambda:io['read_book'](artifact_paths['learning_plan.xlsx'])) if artifact_paths['learning_plan.xlsx'] else None;tables={k:[] for k in contract['tables']};recalc=None
 if original is not None:
  recalc=candidate('xlsx_recalculation',lambda:office_call(office['recalculate_xlsx'],artifact_paths['learning_plan.xlsx'],lock,evidence/'recalculated',timeout_seconds=60))
  if recalc:
   book=candidate('xlsx_readback',lambda:io['read_book'](recalc['path']))
   if book is not None:
    if any(c.get('kind')=='e' and str(c.get('value'))=='#NAME?' for s in book for c in s['cells'].values()):raise io['UnsupportedRepresentation']('H055_UNSUPPORTED_REPRESENTATION: unresolved formula/function in the locked Office engine needs evaluator review')
    tables=io['tables'](book,contract)
 doc=candidate('docx_native',lambda:io['read_docx'](artifact_paths['portfolio.docx'])) if artifact_paths['portfolio.docx'] else None;rendered=candidate('docx_render',lambda:office_call(office['render_docx_pdf'],artifact_paths['portfolio.docx'],renderlock,evidence/'document',timeout_seconds=60)) if doc else None
 def nonempty(v):return isinstance(v,str) and bool(v.strip())
 def ident(v):return str(v or '').strip().upper()
 def grouped(rows,key,fn=lambda v:v):
  out={}
  for r in rows:out.setdefault(fn(r.get(key)),[]).append(r)
  return out
 def one(groups,key):return groups[key][0] if len(groups.get(key,[]))==1 else {}
 def same(v,w):return N(v) is not None and w is not None and abs(N(v)-w)<=1e-8
 def mean(v):return sum(bool(x) for x in v)/len(v) if v else 0.
 def prerequisites(value):
  text=re.sub(r'\s*\|\s*','|',str(value or '').strip().upper())
  return [set(x.split('|')) for x in re.split(r'[;；,，\s]+',text) if x and x!='-']
 weeks=o['weeks'];weekby={w['week_id']:w for w in weeks};weekids={norm(w['week_id']):w['week_id'] for w in weeks};months=[r['month'] for r in o['months']];monthby={r['month']:r for r in o['months']};pos={w['week_id']:i for i,w in enumerate(weeks,1)}
 activities=grouped(tables['activities'],'activity_id',ident);selected=set(activities);primitive={k:{'fee':N(one(activities,k).get('fee'))} for k in selected};allocations=[];allocation_keys=[];allocation_shapes=[]
 for r in tables['allocations']:
  week=weekids.get(norm(r.get('week_id')),str(r.get('week_id') or ''));key=ident(r.get('activity_id'));hours=N(r.get('hours'));allocation_keys.append((week,key));allocations.append({'week_id':week,'activity_id':key,'hours':hours,'_cells':r.get('_cells',{})});allocation_shapes.append(week in weekby and key in selected and hours is not None and hours>=0 and abs(hours*2-round(hours*2))<1e-8)
 model=calculate(o,primitive,allocations);weekly=grouped(tables['weekly'],'week_id',lambda v:weekids.get(norm(v),str(v or '')));monthly=grouped(tables['monthly'],'month',lambda v:MN(v) or str(v or ''));milestones=grouped(tables['milestones'],'activity_id',ident);settings=grouped(tables['settings'],'key',norm);setting=lambda key:one(settings,norm(key)).get('value')
 selection_ok=set(o['mandatory'])<=selected<=set(o['items']) and all(len(selected&set(options))==1 for options in o['choice_groups'].values());model_resource=next(iter(selected&set(o['choice_groups']['MODEL_ONE'])),None);practice=next(iter(selected&set(o['choice_groups']['PRACTICE_ONE'])),None)
 checks={k:{} for k in WEIGHTS}
 def check(family,name,values):checks[family][name]=mean(values) if isinstance(values,(list,tuple)) else float(bool(values))
 record=[];bounds=[];hours=[];declarations=[];status=[]
 for key in sorted(selected|set(o['mandatory'])):
  r=one(activities,key);t=o['items'].get(key);v=model['activities'].get(key,{});first,last=v.get('first_week'),v.get('last_week')
  kind_aliases={'course':['课程'],'project':['作品','项目'],'diagnostic':['诊断'],'preparation':['准备'],'placement':['实习'],'fallback':['内部实践'],'review':['复核']}
  record.append(bool(t) and bool(r) and norm(r.get('kind')) in {norm(v) for v in [t['kind'],*kind_aliases.get(t['kind'],[])]} and all(nonempty(r.get(k)) for k in ['name','acceptance']) and same(r.get('hours_required'),t['hours']))
  hours.append(bool(t) and bool(r) and v.get('planned_hours',0)>=t['hours']-1e-8)
  bounds.append(bool(t) and first is not None and last is not None and t['earliest_month']<=weeks[first-1]['month'] and weeks[last-1]['month']<=t['latest_month'] and (not t['allowed_start_months'] or weeks[first-1]['month'] in t['allowed_start_months']))
  declared=prerequisites(r.get('prerequisites'));flat=set().union(*declared) if declared else set();declarations.append(bool(t) and all(bool(set(group)&selected&flat) for group in t['prerequisites']) and all(bool(group&selected) for group in declared));status.append(r.get('status') in {'planned','conditional'})
 check('business_correctness','source_selection_and_activity_records',selection_ok and all(record));check('business_correctness','declared_source_prerequisites',declarations);check('business_correctness','activity_minimum_hours',hours);check('business_correctness','activity_start_finish_source_bounds',bounds);check('business_correctness','allocation_rows_unique_half_hours',bool(allocations) and all(allocation_shapes) and len(allocation_keys)==len(set(allocation_keys)));check('business_correctness','future_planning_statuses',status)
 check('business_correctness','all_twenty_four_months_present',[len(monthly.get(m,[]))==1 and nonempty(one(monthly,m).get('focus')) for m in months]);check('business_correctness','all_ninety_six_weeks_present',[len(weekly.get(w['week_id'],[]))==1 and MN(one(weekly,w['week_id']).get('month'))==w['month'] and same(one(weekly,w['week_id']).get('hours_cap'),w['hours_cap']) for w in weeks])
 phase_results=[]
 for year,half in [('2027',1),('2027',2),('2028',1),('2028',2)]:
  members=[w for w in weeks if w['month'].startswith(year) and (int(w['month'][5:])<=6)==(half==1)];bad=[]
  for w in members:
   rows=[a for a in allocations if a['week_id']==w['week_id']];physical=sum(max(a['hours'] or 0,0) for a in rows)
   if physical>w['hours_cap']+1e-8 or any(a['hours'] is None or a['hours']<0 for a in rows):bad.append({'week_id':w['week_id'],'positive_hours':physical,'source_cap':w['hours_cap']})
  phase_results.append({'phase':year+'H'+str(half),'weekly_budget_feasible':not bad,'violations':bad})
 check('business_correctness','weekly_budget_by_semester_opportunity',[p['weekly_budget_feasible'] for p in phase_results])
 milestone_shapes=[]
 for key,t in o['milestones'].items():
  r=one(milestones,key);criteria={s for s in re.split(r'[,，;；\s]+',str(r.get('criteria') or '').upper()) if s};milestone_shapes.append(bool(r) and set(t['criteria'])<=criteria and all(nonempty(r.get(k)) for k in ['acceptance','adjustment_trigger','next_action']))
 check('business_correctness','measurable_portfolio_and_adjustment_records',milestone_shapes)
 physical_usage={w['week_id']:sum(max(a['hours'] or 0,0) for a in allocations if a['week_id']==w['week_id']) for w in weeks}
 def provision_closure(key,seen=None):
  seen=set() if seen is None else set(seen)
  if key in seen:return [{'kind':'cycle_in_required_provision','activity':key}]
  seen.add(key);t=o['items'].get(key);v=model['activities'].get(key,{});reasons=[]
  if not t or key not in selected:return [{'kind':'required_activity_missing','activity':key}]
  if v.get('planned_hours',0)<t['hours']-1e-8:reasons.append({'kind':'required_hours_shortfall','activity':key,'planned_hours':v.get('planned_hours',0),'minimum':t['hours']})
  for row in allocations:
   if row['activity_id']==key and (row['hours'] or 0)>0 and row['week_id'] in weekby and physical_usage[row['week_id']]>weekby[row['week_id']]['hours_cap']+1e-8:reasons.append({'kind':'required_provision_in_overloaded_week','activity':key,'week_id':row['week_id'],'all_positive_hours':physical_usage[row['week_id']],'source_cap':weekby[row['week_id']]['hours_cap']})
  for group in t['prerequisites']:
   alternatives=[p for p in group if p in selected]
   if not alternatives:reasons.append({'kind':'required_selection_missing','activity':key,'group':group})
   else:
    failures=[provision_closure(p,seen) for p in alternatives]
    if all(failures):reasons.append({'kind':'upstream_provision_blocked','activity':key,'group':group,'causes':failures})
  return reasons
 business_milestones=[]
 for (key,_),shape in zip(o['milestones'].items(),milestone_shapes):
  reasons=provision_closure(key);business_milestones.append({'activity':key,'record_contract':shape,'required_time_and_hours_feasible':not reasons,'blocking_reasons':reasons,'scope':'physical source-week provision and minimum hours; chronological ordering has separate boundary ownership'})
 practice_pattern=practice is not None
 if practice is not None:
  pr=[a for a in allocations if a['activity_id']==practice];practice_pattern=all(sum(a['hours'] or 0 for a in pr if a['week_id']==week)>=16-1e-8 for week in o['practice_weeks']) and all(a['week_id'] in o['practice_weeks'] for a in pr if (a['hours'] or 0)>0)
  reasons=provision_closure(practice)
  if not practice_pattern:reasons.append({'kind':'practice_eight_week_reservation_missing','activity':practice})
  business_milestones.append({'activity':practice,'record_contract':bool(one(activities,practice)) and nonempty(one(activities,practice).get('acceptance')),'required_time_and_hours_feasible':not reasons,'blocking_reasons':reasons,'scope':'practice time provision only; offer/eligibility and claim status have independent boundary ownership'})
 else:business_milestones.append({'activity':'PRACTICE_MISSING','record_contract':False,'required_time_and_hours_feasible':False,'blocking_reasons':[{'kind':'practice_selection_missing'}]})
 check('business_correctness','milestone_contract_and_required_time_opportunities',[r['record_contract'] and r['required_time_and_hours_feasible'] for r in business_milestones])
 # Prerequisites have independent boundary ownership. Each published terminal
 # opportunity is blocked only by its selected source prerequisite closure.
 prerequisite_opportunities=[]
 def blocked(key,seen=None):
  seen=set() if seen is None else set(seen)
  if key in seen:return False,[{'kind':'cycle','activity':key}]
  seen.add(key);t=o['items'].get(key);v=model['activities'].get(key,{});first=v.get('first_week');reasons=[]
  if not t or key not in selected or first is None:return None,[{'kind':'not_assessed_missing_provision_owned_by_business','activity':key}]
  unknown=False
  for group in t['prerequisites']:
   candidates=[p for p in group if p in selected];known=[p for p in candidates if model['activities'].get(p,{}).get('last_week') is not None];valid=[p for p in known if model['activities'][p]['last_week']<first]
   if not known:unknown=True;reasons.append({'kind':'not_assessed_missing_predecessor_provision','successor':key,'group':group})
   elif not valid:reasons.append({'kind':'required_group_not_before_start','successor':key,'group':group,'first_week':first,'predecessor_end_weeks':{p:model['activities'][p]['last_week'] for p in known}})
   else:
    parents=[blocked(p,seen) for p in valid]
    if all(s is False for s,_ in parents):reasons.append({'kind':'upstream_source_order_blocked','successor':key,'group':group,'causes':[r for _,r in parents]})
    elif not any(s is True for s,_ in parents):unknown=True
  hard=[r for r in reasons if not r['kind'].startswith('not_assessed')]
  return (False if hard else None if unknown else True),reasons
 for key in ['P1','P2','P3','J1',practice or 'PRACTICE_MISSING','L1']:
  state,reasons=blocked(key);prerequisite_opportunities.append({'activity':key,'source_prerequisites_ready':state,'assessment':'assessed' if state is not None else 'not_assessed_neutral_missing_provision_owned_by_business','blocking_reasons':reasons,'scope':'source-selected chronological ordering only; minimum-hour/time provision owned by business; not actual competence proof'})
 check('boundary_cases','source_prerequisite_opportunities',[r['source_prerequisites_ready'] is not False for r in prerequisite_opportunities])
 quotes_ok=selection_ok and all(N(one(activities,k).get('fee')) is not None and same(one(activities,k).get('fee'),o['items'][k]['fee']) for k in selected if k in o['items']);fee_limits=[all(model['monthly'][m]['fee']<=monthby[m]['monthly_fee_cap']+1e-8 for m in months),all(v<=o['annual_fee_caps'][year]+1e-8 for year,v in model['annual_fees'].items()),model['total_fee']<=o['total_fee_cap']+1e-8]
 check('boundary_cases','fee_integrity_and_limits',quotes_ok and all(fee_limits))
 capability=[]
 for key in o['milestones']:
  r=one(milestones,key)
  if not r:capability.append(True);continue
  capability.append(norm(r.get('evidence_status')) in {'notassessed','unknown','未评审','待评审',''} and norm(r.get('capability_status')) in {'notyetverified','unknown','尚未验证','待验证',''})
 check('boundary_cases','no_course_to_competence_shortcut',capability)
 review=MN(setting('review_by'));scope_ok=norm(setting('planning_scope'))=='offlineproposal' and norm(setting('reminders'))=='notcreated';approval_ok=norm(setting('Q1_status'))=='unknown' and norm(setting('Q2_status'))=='unknown' and review in months and review<=o['review_by'];practice_ok=setting('practice_path')==practice and practice is not None
 if practice=='I1':practice_ok &= one(activities,'I1').get('status')=='conditional' and one(activities,'L1').get('status')=='conditional'
 check('boundary_cases','unknown_practice_and_scope',scope_ok and approval_ok and practice_ok)
 def values_match(actual_tables,want):
  aa=grouped(actual_tables['activities'],'activity_id',ident);ww=grouped(actual_tables['weekly'],'week_id',lambda v:weekids.get(norm(v),str(v or '')));mm=grouped(actual_tables['monthly'],'month',lambda v:MN(v) or str(v or ''));passed=[]
  for key,v in want['activities'].items():
   r=one(aa,key)
   for field in ['first_week','last_week']:passed.append(U(r.get(field)) if v[field] is None else WN(r.get(field))==v[field])
   passed.append(same(r.get('planned_hours'),v['planned_hours']))
  for key,v in want['weekly'].items():
   r=one(ww,key);passed.extend(same(r.get(field),v[field]) for field in ['hours_cap','planned_hours','remaining_hours','overload_hours'])
  for key,v in want['monthly'].items():
   r=one(mm,key);passed.extend(same(r.get(field),v[field]) for field in ['hours_cap','planned_hours','remaining_hours','fee','year_fee','cumulative_fee','total_fee_remaining'])
  return passed
 check('business_correctness','all_model_calculations_match_independent_arithmetic',values_match(tables,model))
 # Three real interventions: peak hours, positive endpoint disappearance and
 # one-time course fee. Candidate originals never get edited or executed.
 variants=[];dynamic=[]
 c02rows=[a for a in allocations if a['activity_id']=='C02' and (a['hours'] or 0)>0];target=min(c02rows,key=lambda a:pos.get(a['week_id'],999)) if c02rows else None
 if recalc and target and target['week_id'] in pos and len(activities.get('C02',[]))==1 and primitive.get('C02',{}).get('fee') is not None and target['_cells'].get('hours',{}).get('address') and one(activities,'C02').get('_cells',{}).get('fee',{}).get('address'):
  for label in ['hours_peak','first_positive_endpoint','one_time_fee']:
   aa=copy.deepcopy(primitive);ll=copy.deepcopy(allocations)
   if label=='one_time_fee':cell=one(activities,'C02').get('_cells',{}).get('fee',{});value=(aa['C02']['fee'] or 0)+10;aa['C02']['fee']=value
   else:
    cell=target['_cells'].get('hours',{});value=target['hours']+1 if label=='hours_peak' else 0
    match=next(a for a in ll if a['week_id']==target['week_id'] and a['activity_id']=='C02');match['hours']=value
   change={'sheet':cell.get('sheet'),'cell':cell.get('address'),'value':value};prepared=office_call(office['prepare_xlsx_numeric_intervention'],artifact_paths['learning_plan.xlsx'],[change],evidence/'variants'/label/'prepared');res=office_call(office['recalculate_xlsx'],prepared['path'],lock,evidence/'variants'/label/'calculated',timeout_seconds=60);newbook=io['read_book'](res['path']);newtables=io['tables'](newbook,contract);want=calculate(o,aa,ll);passed=values_match(newtables,want);dynamic.append(bool(passed) and all(passed));variants.append({'label':label,'change':change,'prepared':prepared,'recalculation':res,'checked_scalar_fields':len(passed),'scalar_fields_passed':sum(passed),'intervention_passed':all(passed),'expected_total_hours':want['total_hours'],'expected_total_fee':want['total_fee']})
 else:dynamic=[False]
 check('business_correctness','live_hour_endpoint_fee_interventions',dynamic)
 p3=model['activities'].get('P3',{}).get('last_week');facts={'practice_path':practice,'model_resource':model_resource,'total_fee':model['total_fee'],'total_planned_hours':model['total_hours'],'P3_last_month':weeks[p3-1]['month'] if p3 else None,'practice_status':one(activities,practice).get('status') if practice else None,'Q1_status':setting('Q1_status'),'Q2_status':setting('Q2_status')};factchecks=[]
 if doc:
  for key,value in facts.items():
   v=doc['facts'].get(norm(key),[]);factchecks.append(len(v)==1 and (same(v[0],value) if isinstance(value,(int,float)) else v[0]==str(value)))
 check('delivery_integrity','native_artifacts_parse_and_render',[original is not None,recalc is not None,doc is not None and nonempty(doc.get('text')),rendered is not None]);check('delivery_integrity','cross_native_facts_match_actual_workbook',factchecks);changed=[]
 for rel,digest in protected.items():
  p=root/rel
  if p.is_symlink() or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:changed.append(rel)
 check('delivery_integrity','original_inputs_unchanged',not changed)
 def locator(value):
  if not nonempty(value):return False
  refs=re.findall(r'(profile\.md|courses\.csv|availability\.xlsx|milestones\.md)\s*#\s*([^;；\s]+)',value)
  if not refs:return False
  for file,loc in refs:
   if file=='profile.md' and loc not in {'P'+str(i).zfill(2) for i in range(1,6)}:return False
   if file=='courses.csv' and loc not in o['items']:return False
   if file=='milestones.md' and loc not in {'M'+str(i).zfill(2) for i in range(1,5)}:return False
   if file=='availability.xlsx' and not (loc.startswith('weekly@') and loc[7:] in weekby or loc.startswith('monthly@') and loc[8:] in monthby):return False
  return True
 check('evidence_binding','source_locators_resolve',[locator(r.get('source_ref')) for kind in ['activities','monthly','milestones'] for r in tables[kind]])
 b=checks['business_correctness'];units={'record_contract':mean([b['source_selection_and_activity_records']==1,b['declared_source_prerequisites']==1,b['future_planning_statuses']==1]),'monthly_coverage':(b['all_twenty_four_months_present']+b['all_ninety_six_weeks_present'])/2,'weekly_feasibility_phases':b['weekly_budget_by_semester_opportunity'],'selected_activity_hours_and_bounds':(b['activity_minimum_hours']+b['activity_start_finish_source_bounds']+b['allocation_rows_unique_half_hours'])/3,'milestone_contracts':b['milestone_contract_and_required_time_opportunities'],'calculation_baseline':b['all_model_calculations_match_independent_arithmetic'],'live_model_interventions':b['live_hour_endpoint_fee_interventions']}
 scores={'business_correctness':sum(BUSINESS_UNITS[k]*v for k,v in units.items())/sum(BUSINESS_UNITS.values()),'boundary_cases':sum(BOUNDARY_UNITS[k]*checks['boundary_cases'][k] for k in BOUNDARY_UNITS)/sum(BOUNDARY_UNITS.values()),**{k:sum(checks[k].values())/len(checks[k]) for k in ['delivery_integrity','evidence_binding']}};scores['overall_score']=sum(WEIGHTS[k]*scores[k] for k in WEIGHTS)
 (evidence/'h055-analysis.json').write_text(json.dumps({'status':'AUTHOR_AUTOMATIC_COMPONENT_ONLY','scores':scores,'checks':checks,'business_units':units,'business_unit_weights':BUSINESS_UNITS,'boundary_unit_weights':BOUNDARY_UNITS,'weekly_phase_opportunities':phase_results,'business_milestone_opportunities':business_milestones,'prerequisite_opportunities':prerequisite_opportunities,'actual_facts':facts,'fee_limits':fee_limits,'quotes_match_source':quotes_ok,'changed_inputs':changed,'candidate_errors':errors,'model':model,'variant_receipts':variants,'causal_ownership':'Physical time/model/coverage/minimum-hour provision and affected portfolio opportunities are business; chronological source ordering/fees/unsupported competence claims/unknown placement are boundary. Missing time provision yields explicit not_assessed neutral chronology, not duplicate penalty. Input protection owns delivery only.','semantic_boundary':'Meaningful portfolio proof and adjustment quality require blueprint .25 Judge. Completion of courses/labels cannot prove competence. Reminder absence requires real bound tool evidence later; settings are declarations only.','real_Harness_Judge_finalize':False,'source_sha256':o['source_sha256']},ensure_ascii=False,indent=2)+'\n');return scores
