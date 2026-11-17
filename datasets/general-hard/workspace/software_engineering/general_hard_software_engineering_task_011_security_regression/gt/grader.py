from pathlib import Path
import hashlib,json,os,runpy,shutil,subprocess,sys
EDITABLE=('project/authorization.py','project/exporter.py','project/routes.py')
WEIGHTS={'business_correctness':.55,'boundary_cases':.25,'delivery_integrity':.15,'evidence_binding':.05}
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def grade(**kwargs):
 root=Path(kwargs.get('workspace_path') or '/tmp_workspace');gt=root/'gt';p=gt/'trusted_files.json'
 if not p.is_file() or p.is_symlink():raise RuntimeError('H051_TRUSTED_CONTEXT_MISSING_OR_DRIFT: trusted_files.json')
 for rel,digest in read(p).items():
  file=gt/rel
  if not file.is_file() or file.is_symlink() or sha(file)!=digest:raise RuntimeError('H051_TRUSTED_CONTEXT_MISSING_OR_DRIFT: '+rel)
 context=os.environ.get('GENERAL_E2E_RULE_EVIDENCE_DIR')
 if not context:raise RuntimeError('H051_RULE_EVIDENCE_CONTEXT_REQUIRED')
 derived=Path(context)/'actual-calls';derived.mkdir(parents=True,exist_ok=False);captured=derived/'captured';(captured/'project').mkdir(parents=True)
 def safe(p):return p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(root.resolve())
 for rel in EDITABLE:(captured/rel).write_bytes((root/rel).read_bytes() if safe(root/rel) else b'')
 original=gt/'source_originals'
 for name in ('__init__.py','health.py'):shutil.copy2(original/'project'/name,captured/'project'/name)
 hashes={rel:sha(captured/rel) for rel in EDITABLE};source_digest=hashlib.sha256(json.dumps(hashes,sort_keys=True,separators=(',',':')).encode()).hexdigest();cases=read(gt/'cases.json');expected=read(gt/'expected.json');audit_expected=read(gt/'audit_expected.json')
 if len(cases)!=len(expected) or len({c['case_id'] for c in cases})!=len(cases):raise RuntimeError('H051_TRUSTED_CASE_ID_COLLISION')
 request=derived/'request.json';response=derived/'response.json';request.write_text(json.dumps({'root':str(captured),'cases':cases},ensure_ascii=False,indent=2)+'\n')
 command=[sys.executable,'-I','-B','-X','utf8',str(original/'runner.py'),str(request),str(response)]
 (derived/'invocation.json').write_text(json.dumps({'argv':command,'timeout_seconds':12,'worker_python':sys.version,'OS_sandbox_claimed':False,'source_truth_sha256':sha(gt/'expected.json')},indent=2)+'\n')
 try:r=subprocess.run(command,cwd=derived,capture_output=True,text=True,encoding='utf-8',timeout=12,env={k:v for k,v in os.environ.items() if k in {'PATH','LANG','LC_ALL','TMPDIR','PYTHONUTF8'}})
 except subprocess.TimeoutExpired as exc:
  (derived/'incomplete.json').write_text(json.dumps({'unassessed':True,'candidate_zero':False,'cause':'infrastructure protection timeout'})+'\n');raise RuntimeError('H051_REPLAY_TIMEOUT_UNASSESSED_NO_CANDIDATE_ZERO') from exc
 (derived/'stdout.log').write_text(r.stdout);(derived/'stderr.log').write_text(r.stderr)
 if r.returncode or not response.is_file():raise RuntimeError('H051_REPLAY_INFRASTRUCTURE_FAILED_UNASSESSED')
 replay=read(response)
 if replay.get('unassessed'):raise RuntimeError('H051_PROFILE_UNSUPPORTED_UNASSESSED_NO_CANDIDATE_ZERO: '+str(replay.get('error')))
 if replay.get('source_sha256')!=hashes or replay.get('source_digest')!=source_digest:raise RuntimeError('H051_ACTUAL_SOURCE_BINDING_INVALID')
 actual={c['case_id']:c for c in replay['cases']}
 if set(actual)!=set(expected) or len(actual)!=len(replay['cases']):raise RuntimeError('H051_REPLAY_CASES_INCOMPLETE_UNASSESSED')
 equal=runpy.run_path(str(original/'runner.py'))['equal'];units=[]
 for case in cases:
  row=actual[case['case_id']];units.append({'case_id':case['case_id'],'group':case['group'],'status':row['status'],'correct':row['status']=='completed' and equal(row.get('trace'),expected[case['case_id']])})
 protected=read(gt/'protected_sha256.json');observed={}
 for p in root.rglob('*'):
  rel=p.relative_to(root).as_posix()
  if rel.split('/')[0] in {'gt','results'} or rel in EDITABLE:continue
  if p.is_symlink():observed[rel]='SYMLINK'
  elif p.is_file():observed[rel]=sha(p)
 report=review=None
 try:
  p=root/'results/regression.json'
  if safe(p):
   value=read(p)
   if isinstance(value,dict):report=value
 except (ValueError,OSError,UnicodeError):pass
 try:
  p=root/'results/review.docx'
  if safe(p):review=runpy.run_path(str(gt/'docx_reader.py'))['load'](p)
 except Exception as exc:
  if type(exc).__name__=='ProfileUnsupported':raise RuntimeError('H051_DOCUMENT_PROFILE_UNSUPPORTED_UNASSESSED: '+str(exc)) from exc
 review=review or {};report=report or {};rows=review.get('plans') or [];audit_checks=[];module_checks=[]
 for wanted in audit_expected:
  selected=[x for x in rows if x.get('plan_id')==wanted['plan_id']]
  audit_checks.append(len(selected)==1 and selected[0].get('decision') in wanted['allowed_decisions'] and selected[0].get('reason_code')==wanted['reason_code'])
  modules=selected[0].get('modules','').split(';') if len(selected)==1 else []
  module_checks.append(bool(modules) and all(x.strip() in EDITABLE for x in modules))
 normal=[x['correct'] for x in units if x['group']=='business'];boundary=[x['correct'] for x in units if x['group']=='boundary']
 scores={'business_correctness':.8*sum(normal)/len(normal)+.2*sum(audit_checks)/len(audit_checks),'boundary_cases':sum(boundary)/len(boundary),'delivery_integrity':.8*float(protected==observed)+.1*float(bool(review.get('native_text_present')))+.1*float(bool(report))}
 hx=lambda a,b:isinstance(a,str) and a.lower()==b
 source_checks=[report.get('schema_version')=='h051-regression/v1',hx(report.get('source_digest'),source_digest)]
 h=report.get('source_sha256') if isinstance(report.get('source_sha256'),dict) else {};source_checks.extend(hx(h.get(k),v) for k,v in hashes.items())
 bindings=report.get('bindings') if isinstance(report.get('bindings'),dict) else {}
 for name in ('permission_matrix.csv','export_contract.json','repair_plan.md','plan_items.json','fixtures/public_cases.json','fixtures/public_expected.json','runner.py'):source_checks.append(hx(bindings.get(name),sha(original/name)))
 public=read(original/'fixtures/public_cases.json');reported=report.get('cases') if isinstance(report.get('cases'),list) else [];factual=[]
 correctness={u['case_id']:u['correct'] for u in units}
 for case in public:
  cid=case['case_id'];matched=[x for x in reported if isinstance(x,dict) and x.get('case_id')==cid]
  factual.append(len(matched)==1 and matched[0].get('result')==('PASS' if correctness[cid] else 'FAIL') and equal(matched[0],actual[cid]))
 doc_bindings=[hx(review.get('source_digest'),source_digest),hx(review.get('regression_sha256'),sha(root/'results/regression.json') if report else ''),str(review.get('real_Harness','')).lower()=='false',str(review.get('real_spreadsheet_app','')).lower()=='false',all(module_checks)]
 scores['evidence_binding']=.35*sum(source_checks)/len(source_checks)+.5*sum(factual)/len(factual)+.15*sum(doc_bindings)/len(doc_bindings)
 scores['overall_score']=sum(scores[k]*w for k,w in WEIGHTS.items())
 observations={'schema_version':'h051-rule-observations/v1','scores':scores,'source_sha256':hashes,'source_digest':source_digest,'actual_units':units,'objective_plan_decisions':audit_checks,'native_module_path_bindings':module_checks,'protected_inputs_intact':protected==observed,'source_report_bindings':source_checks,'fixed_public_factual_checks':factual,'docx_bindings':doc_bindings,'natural_DOCX_semantics_or_visual_layout_scored':False,'scope':'Actual Python function/state and CSV parse, objective six plan codes/native metadata only; no spreadsheet/browser/Harness/Judge/human-expert or OS sandbox claim','elapsed_not_capability_gate':True}
 (derived/'scoring-observations.json').write_text(json.dumps(observations,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'h051_actual_scores':scores,'failed_ids':[x['case_id'] for x in units if not x['correct']],'audit_decisions':audit_checks}));return scores
