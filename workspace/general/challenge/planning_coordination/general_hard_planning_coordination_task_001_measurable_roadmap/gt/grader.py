"""H053 objective record/constraint checks. Semantic quality belongs to the separate Judge."""
from pathlib import Path
import json,hashlib,os,runpy,re
class TrustedEvidenceError(RuntimeError):pass
WEIGHTS={'business_correctness':.55,'boundary_cases':.25,'delivery_integrity':.15,'evidence_binding':.05}
def grade(workspace_path=None,**kwargs):
 root=Path(workspace_path or '/tmp_workspace').resolve();gt=Path(__file__).resolve().parent
 def load(name):
  try:return json.loads((gt/name).read_text())
  except (OSError,ValueError,UnicodeError) as e:raise TrustedEvidenceError('H053_TRUSTED_MISSING_OR_INVALID: '+name) from e
 trusted=load('trusted_files.json')
 for name,digest in trusted.items():
  p=gt/name
  if p.is_symlink() or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:raise TrustedEvidenceError('H053_TRUSTED_MISSING_OR_DRIFT: '+name)
 o=load('business_oracle.json');contract=load('artifact_contract.json');protected=load('protected_sha256.json');load('expected.json');load('counterexamples.json');load('evidence_requirements.json')
 io=runpy.run_path(str(gt/'native_io.py'));office=runpy.run_path(str(gt/'office_runtime.py'));N=io['number'];U=io['unknown'];norm=io['norm'];errors={}
 ev=os.environ.get('GENERAL_E2E_RULE_EVIDENCE_DIR');lp=os.environ.get('GENERAL_E2E_OFFICE_LOCK');rp=os.environ.get('GENERAL_E2E_OFFICE_RENDER_LOCK')
 if not ev or not lp or not rp:raise TrustedEvidenceError('H053_TRUSTED_OFFICE_OR_EVIDENCE_CONTEXT_MISSING')
 evidence=Path(ev).resolve()
 if any(p==evidence or p in evidence.parents or evidence in p.parents for p in [root,gt]):raise TrustedEvidenceError('H053_TRUSTED_EVIDENCE_OVERLAP')
 evidence.mkdir(parents=True,exist_ok=True)
 try:lock=json.loads(Path(lp).read_text());renderlock=json.loads(Path(rp).read_text());office['validate_office_lock'](lock);office['validate_office_render_lock'](renderlock)
 except (OSError,ValueError,office['OfficeRuntimeError']) as e:raise TrustedEvidenceError('H053_TRUSTED_OFFICE_RUNTIME: '+str(e)) from e
 def office_call(fn,*args,**kw):
  try:return fn(*args,**kw)
  except office['OfficeRuntimeError'] as e:
   if 'UNSUPPORTED' in e.code:raise io['UnsupportedRepresentation']('H053_UNSUPPORTED_REPRESENTATION: '+str(e)) from e
   if e.code in {'OFFICE_INPUT_INVALID','OFFICE_INPUT_LIMIT','OFFICE_DOCX_INPUT_INVALID'}:raise io['CandidateError'](str(e)) from e
   raise TrustedEvidenceError('H053_TRUSTED_OFFICE_FAILURE: '+str(e)) from e
 def candidate(name,fn):
  try:return fn()
  except io['CandidateError'] as e:errors[name]=str(e);return None
 xlsx=candidate('xlsx_path',lambda:io['candidate_path'](root,'results/roadmap.xlsx'));docpath=candidate('docx_path',lambda:io['candidate_path'](root,'results/explanation.docx'))
 original=candidate('xlsx',lambda:io['read_book'](xlsx)) if xlsx else None
 tables={k:[] for k in contract['tables']};recalc=None
 if original is not None:
  recalc=candidate('xlsx_recalculation',lambda:office_call(office['recalculate_xlsx'],xlsx,lock,evidence/'recalculated',timeout_seconds=60))
  if recalc:
   calculated=candidate('xlsx_readback',lambda:io['read_book'](recalc['path']))
   if calculated is not None:tables=io['tables'](calculated,contract)
 doc=candidate('docx',lambda:io['read_docx'](docpath)) if docpath else None
 rendered=candidate('docx_render',lambda:office_call(office['render_docx_pdf'],docpath,renderlock,evidence/'document',timeout_seconds=60)) if doc else None
 checks={k:{} for k in WEIGHTS}
 def check(family,name,values):
  if isinstance(values,(list,tuple)):score=sum(bool(v) for v in values)/len(values) if values else 0.
  else:score=float(bool(values))
  checks[family][name]=score
 def nonempty(v):return isinstance(v,str) and bool(v.strip())
 def period(v):
  m=re.fullmatch(r'P([1-6])',str(v).strip(),re.I);return int(m[1]) if m else None
 def tokens(v):return {s for s in re.split(r'[,，;；\s]+',str(v or '').strip()) if s}
 def equal(a,b):return N(a) is not None and abs(N(a)-b)<=1e-8
 def unique(rows,key):
  d={}
  for r in rows:d.setdefault(str(r.get(key,'')),[]).append(r)
  return d
 goals=unique(tables['goals'],'goal_id');actions=tables['actions'];loads=tables['loads'];decisions=unique(tables['decisions'],'decision_id');byout=unique(actions,'outcome');byid=unique(actions,'action_id');roles={'PM','OPS','ANALYST'}
 goalshape=[];targets=[];baseline=[];unknown=[];formula_records=[]
 for gid,g in o['goals'].items():
  rows=goals.get(gid,[]);r=rows[0] if len(rows)==1 else {};m=o['metrics'][g['metric_id']]
  goalshape.append(len(rows)==1 and r.get('metric_id')==g['metric_id'] and all(nonempty(r.get(k)) for k in ['objective','definition','acceptance']) and r.get('owner') in roles and period(r.get('due_period'))==g['due'])
  if m['status']=='verified':
   baseline.append(equal(r.get('baseline_n'),m['n']) and equal(r.get('baseline_d'),m['d']) and equal(r.get('baseline_rate'),m['rate']) and r.get('baseline_status')=='verified')
   n,d,rate=map(N,[r.get('target_n'),r.get('target_d'),r.get('target_rate')]);targets.append(n is not None and d is not None and rate is not None and n==int(n) and d==int(d) and d>=g['minimum_sample'] and 0<=n<=d and abs(rate-n/d)<=1e-8 and rate>=g['minimum_rate']-1e-8 and r.get('target_kind')=='proposed')
   for prefix in ['baseline','target']:
    if r:formula_records.append({'goal':gid,'row':r,'prefix':prefix})
  else:
   unknown.append(len(rows)==1 and r.get('baseline_status')=='unknown' and all(U(r.get(k)) for k in ['baseline_n','baseline_d','baseline_rate','target_n','target_d','target_rate']) and r.get('target_kind')=='measurement_only')
 check('business_correctness','goal_record_contract',goalshape);check('business_correctness','measurable_proposed_targets',targets)
 check('boundary_cases','source_baselines_not_retired_dashboard',baseline);check('boundary_cases','missing_population_stays_unknown',unknown)
 # Grade arbitrary valid decompositions/methods, never reference action text or a fixed schedule.
 outcomechecks=[];efforts=[];dependencies=[];gates=[];selected={};outtimes={}
 for outcome in sorted({r['outcome'] for r in o['outcomes']}):
  rows=byout.get(outcome,[]);methods={r.get('method') for r in rows};options=[v for v in o['outcomes'] if v['outcome']==outcome and v['method'] in methods]
  opt=options[0] if len(methods)==len(options)==1 else None;selected[outcome]=opt
  starts=[period(r.get('start_period')) for r in rows];ends=[period(r.get('end_period')) for r in rows];validperiod=bool(rows) and all(v is not None for v in starts+ends)
  outtimes[outcome]=(min(starts),max(ends)) if validperiod else (None,None)
  declaredgoals=set().union(*(tokens(r.get('goal_ids')) for r in rows)) if rows else set()
  outcomechecks.append(opt is not None and declaredgoals>=set(opt['goals']) and all(tokens(r.get('goal_ids'))<=set(o['goals']) and tokens(r.get('goal_ids')) and all(nonempty(r.get(k)) for k in ['action_id','action','acceptance']) and r.get('owner') in roles and r.get('status') in {'planned','conditional'} for r in rows))
  charge={role:sum(N(l.get(role)) or 0 for l in loads if l.get('outcome')==outcome) for role in roles}
  efforts.append(opt is not None and all(charge[role]>=opt['effort'][role]-1e-8 for role in roles))
  if opt:
   endlimit=validperiod and all(s<=e for s,e in zip(starts,ends)) and max(ends)<=opt['latest'] and (outcome!='O8' or min(starts)==max(ends)==6)
   predecessor=all(outtimes.get(dep,(None,None))[1] is not None and validperiod and outtimes[dep][1]<min(starts) for dep in opt['predecessors'])
   dependencies.append(endlimit and predecessor)
   if opt['gate']=='Q1':gates.append(validperiod and min(starts)>=4 and all(r.get('status')=='conditional' for r in rows) and all(r.get('status')=='conditional' for r in byout.get('O8',[])))
 # The loop above uses sorted O1..O8, a topological order for the declared dependency graph.
 check('business_correctness','required_outcomes_linked_to_goals',outcomechecks);check('business_correctness','per_outcome_effort_not_erased_by_merging',efforts)
 check('boundary_cases','time_and_required_dependency_barriers',dependencies)
 loadkeys=[];loadshape=[];usage={k:0 for k in o['capacities']}
 for l in loads:
  key=(l.get('action_id'),l.get('outcome'),l.get('period'));loadkeys.append(key);candidates=[a for a in byid.get(str(l.get('action_id')),[]) if a.get('outcome')==l.get('outcome')];p=period(l.get('period'));hours=[N(l.get(role)) for role in roles]
  okay=len(candidates)==1 and p is not None and all(n is not None and n>=0 for n in hours)
  if okay:
   a=candidates[0];s,e=period(a.get('start_period')),period(a.get('end_period'));okay=s is not None and e is not None and s<=p<=e
  loadshape.append(okay)
  if p is not None:
   for role in roles:
    n=N(l.get(role))
    if n is not None:usage[f'{role}:P{p}']+=n
 loadcoverage=all(any(l.get('action_id')==a.get('action_id') and l.get('outcome')==a.get('outcome') for l in loads) for a in actions)
 check('business_correctness','concrete_load_records',bool(loads) and all(loadshape) and len(set(loadkeys))==len(loadkeys) and loadcoverage)
 check('boundary_cases','confirmed_role_period_capacity',bool(loads) and all(loadshape) and all(0<=usage[k]<=cap+1e-8 for k,cap in o['capacities'].items()) and all(a.get('owner') in roles for a in actions))
 # Explicit dependencies can be action IDs or outcome IDs; validate them and cycle/time consistency.
 explicit=[]
 for a in actions:
  s=period(a.get('start_period'));dep=tokens(a.get('depends_on'));opt=selected.get(a.get('outcome'));required=set(opt['predecessors']) if opt else set();covered=set()
  for token in dep:
   targets=byout.get(token) if token in byout else byid.get(token)
   if not targets:explicit.append(False);continue
   covered.update(t.get('outcome') for t in targets)
   explicit.append(s is not None and all(period(t.get('end_period')) is not None and period(t.get('end_period'))<s for t in targets))
  explicit.append(required<=covered)
 check('boundary_cases','declared_dependencies_resolve',bool(actions) and all(explicit))
 q=decisions.get('Q1',[]);q=q[0] if len(q)==1 else {};method=selected.get('O5',{});method=method.get('method') if method else None
 gates.append(q.get('status')=='unknown' and q.get('owner')=='PM' and period(q.get('review_period')) is not None and period(q.get('review_period'))<=2 and q.get('disposition')==('conditional_wait' if method=='live_pilot' else 'internal_alternative'))
 check('boundary_cases','unconfirmed_permission_not_assumed',gates)
 # Check actual dependency response in an independent trusted engine on disposable copies.
 variants=[];dynamic=[]
 if recalc and len(formula_records)==6:
  for label,field,delta in [('numerator','n',1),('denominator','d',10)]:
   changes=[];expected=[]
   for item in formula_records:
    r,prefix=item['row'],item['prefix'];cell=r['_cells'].get(prefix+'_'+field,{});n,d=N(r.get(prefix+'_n')),N(r.get(prefix+'_d'))
    if n is None or d is None or d<=0 or not cell.get('address'):continue
    changes.append({'sheet':cell['sheet'],'cell':cell['address'],'value':(n if field=='n' else d)+delta});expected.append((r['_cells'][prefix+'_rate'],(n+delta)/d if field=='n' else n/(d+delta)))
   if len(changes)!=6:dynamic.append(False);continue
   prepared=office_call(office['prepare_xlsx_numeric_intervention'],xlsx,changes,evidence/'variants'/label/'prepared')
   result=office_call(office['recalculate_xlsx'],prepared['path'],lock,evidence/'variants'/label/'calculated',timeout_seconds=60)
   b=io['read_book'](result['path']);lookup={(s['name'],c['address']):c for s in b for c in s['cells'].values()}
   okay=[equal(lookup.get((c['sheet'],c['address']),{}).get('value'),v) for c,v in expected];dynamic.extend(okay);variants.append({'label':label,'prepared':prepared,'recalculation':result,'changed_ratio_cells':sum(okay),'expected_cells':len(okay)})
 else:dynamic=[False]
 check('business_correctness','ratios_recalculate_after_input_changes',dynamic)
 # Cross-document facts are explicit scalars, not a semantic text-match surrogate.
 factchecks=[]
 if doc:
  expectedfacts={'M1基线':.78,'M2基线':.6,'M3基线':.6,'M4基线':'unknown','Q1状态':'unknown','O5方法':method}
  actualfacts={**{f'M{i}基线':goals.get(f'G{i}',[{}])[0].get('baseline_rate') for i in range(1,5)},'Q1状态':q.get('status'),'O5方法':method}
  def samevalue(v,w):
   if U(w):return U(v)
   if N(w) is not None:return equal(v,N(w))
   return norm(v)==norm(w)
  for key,value in expectedfacts.items():
   vals=doc['facts'].get(norm(key),[]);factchecks.append(len(vals)==1 and samevalue(vals[0],value) and samevalue(vals[0],actualfacts[key]))
 check('delivery_integrity','native_deliverables_parse_and_render',[original is not None,recalc is not None,doc is not None and nonempty(doc.get('text')),rendered is not None])
 check('delivery_integrity','cross_document_fact_table',factchecks)
 changed=[]
 for rel,digest in protected.items():
  p=root/rel
  if p.is_symlink() or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:changed.append(rel)
 check('delivery_integrity','original_inputs_unchanged',not changed)
 def locator(v):
  if not nonempty(v):return False
  refs=re.findall(r'(baseline\.csv|constraints\.md|strategy_notes\.docx)\s*#\s*([^;；\s]+)',v)
  if not refs:return False
  for file,loc in refs:
   if file=='baseline.csv':
    m=re.fullmatch(r'(M[1-4])@(.+)',loc)
    if not m or m[1] not in o['metrics'] or m[2]!=o['metrics'][m[1]]['period']:return False
   elif file=='constraints.md':
    if loc not in {'C01','C02','C03','C04','C05','C06'}:return False
   elif loc not in {'N1','N2','N3','N4','N5'}:return False
  return True
 check('evidence_binding','source_locators_resolve',[locator(r.get('source_ref')) for kind in ['goals','actions','decisions'] for r in tables[kind]])
 scores={k:sum(v.values())/len(v) for k,v in checks.items()};scores['overall_score']=sum(WEIGHTS[k]*scores[k] for k in WEIGHTS)
 (evidence/'h053-analysis.json').write_text(json.dumps({'status':'AUTHOR_RULE_COMPONENT_ONLY','scores':scores,'checks':checks,'candidate_errors':errors,'changed_inputs':changed,'resource_usage':usage,'formula_variants':variants,'semantic_judge':'not_run; explanation quality and action adequacy require blueprint Judge','source_sha256':o['source_sha256'],'candidate_workbook_sha256':hashlib.sha256(xlsx.read_bytes()).hexdigest() if xlsx else None},ensure_ascii=False,indent=2)+'\n')
 return scores
