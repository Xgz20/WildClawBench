from pathlib import Path
import hashlib,json,os,re,runpy,shutil,subprocess,sys
EDITABLE=('project/api.py','project/service.py','project/repository.py','project/client.mjs')
WEIGHTS={'business_correctness':.55,'boundary_cases':.25,'delivery_integrity':.15,'evidence_binding':.05}
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def fenced(text):
 for block in re.findall(r'```(?:json|JSON)\s*\n(.*?)\n```',text,re.S):
  try:
   v=json.loads(block)
   if isinstance(v,dict):return v
  except ValueError:pass
 return None

def grade(**kwargs):
 root=Path(kwargs.get('workspace_path') or '/tmp_workspace');gt=root/'gt'
 trusted=gt/'trusted_files.json'
 if not trusted.is_file() or trusted.is_symlink():raise RuntimeError('H052_TRUSTED_CONTEXT_MISSING_OR_DRIFT: trusted_files.json')
 for rel,digest in read(trusted).items():
  p=gt/rel
  if not p.is_file() or p.is_symlink() or sha(p)!=digest:raise RuntimeError('H052_TRUSTED_CONTEXT_MISSING_OR_DRIFT: '+rel)
 context=os.environ.get('GENERAL_E2E_RULE_EVIDENCE_DIR')
 if not context:raise RuntimeError('H052_RULE_EVIDENCE_CONTEXT_REQUIRED')
 derived=Path(context)/'actual-replay';derived.mkdir(parents=True,exist_ok=False)
 captured=derived/'captured';(captured/'project').mkdir(parents=True)
 def safe(p):return p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(root.resolve())
 for rel in EDITABLE:(captured/rel).write_bytes((root/rel).read_bytes() if safe(root/rel) else b'')
 hashes={p:sha(captured/p) for p in EDITABLE};digest=hashlib.sha256(json.dumps(hashes,sort_keys=True,separators=(',',':')).encode()).hexdigest()
 original=gt/'source_originals';cases=read(gt/'cases.json');expected=read(gt/'expected.json')
 if len(cases)!=len(expected) or len({c['case_id'] for c in cases})!=len(cases):raise RuntimeError('H052_TRUSTED_CASE_ID_COLLISION')
 request={'candidate_root':str(captured),'trusted_root':str(original),'work_root':str(derived/'runs'),'cases':cases}
 requestpath=derived/'request.json';responsepath=derived/'response.json';requestpath.write_text(json.dumps(request,ensure_ascii=False,indent=2)+'\n')
 command=[sys.executable,'-I','-B','-X','utf8',str(original/'runner.py'),str(requestpath),str(responsepath)]
 invocation={'argv':command,'actual_worker_python':sys.version,'loopback_only':True,'timeout_seconds':90,'os_sandbox_claimed':False,'expected_sha256':sha(gt/'expected.json')}
 (derived/'invocation.json').write_text(json.dumps(invocation,indent=2)+'\n')
 try:r=subprocess.run(command,cwd=derived,capture_output=True,text=True,encoding='utf-8',timeout=90,env={k:v for k,v in os.environ.items() if k in {'PATH','LANG','LC_ALL','TMPDIR','PYTHONUTF8'}})
 except subprocess.TimeoutExpired as exc:
  (derived/'incomplete.json').write_text(json.dumps({'status':'unassessed_infrastructure_timeout','candidate_zero':False})+'\n');raise RuntimeError('H052_REPLAY_TIMEOUT_UNASSESSED_NO_CANDIDATE_ZERO') from exc
 (derived/'stdout.log').write_text(r.stdout);(derived/'stderr.log').write_text(r.stderr)
 if r.returncode or not responsepath.is_file():raise RuntimeError('H052_REPLAY_INFRASTRUCTURE_FAILED_UNASSESSED: '+str(r.returncode))
 replay=read(responsepath)
 if replay.get('unassessed'):raise RuntimeError('H052_PROFILE_OR_REPLAY_UNASSESSED_NO_CANDIDATE_ZERO: '+str(replay.get('error')))
 if replay.get('source_sha256')!=hashes or replay.get('source_digest')!=digest:raise RuntimeError('H052_REPLAY_SOURCE_BINDING_INVALID')
 helpers=runpy.run_path(str(original/'runner.py'));equal=helpers['equal']
 actual={c['case_id']:c for c in replay['cases']}
 if set(actual)!=set(expected) or len(actual)!=len(replay['cases']):raise RuntimeError('H052_REPLAY_INCOMPLETE_UNASSESSED')
 units=[]
 for c in cases:
  got=actual[c['case_id']];wanted=expected[c['case_id']]
  ok=helpers['satisfies'](c,got,wanted)
  units.append({'case_id':c['case_id'],'requirement':c['requirement'],'group':c['group'],'kind':c['kind'],'status':got['status'],'correct':ok})
 scores={}
 for key,group in [('business_correctness','business'),('boundary_cases','boundary')]:
  requirement_ids=sorted({x['requirement'] for x in units if x['group']==group})
  scores[key]=sum(sum(x['correct'] for x in units if x['group']==group and x['requirement']==rid)/sum(x['group']==group and x['requirement']==rid for x in units) for rid in requirement_ids)/len(requirement_ids)
 protected=read(gt/'protected_sha256.json');observed={}
 for p in root.rglob('*'):
  rel=p.relative_to(root).as_posix()
  if rel.split('/')[0] in {'gt','results'} or rel in EDITABLE:continue
  if p.is_symlink():observed[rel]='SYMLINK'
  elif p.is_file():observed[rel]=sha(p)
 protected_ok=protected==observed
 test_text=handoff_text=None;report=handoff=None;workbook=None
 for rel in ('tests.txt','handoff.md'):
  try:
   p=root/'results'/rel
   if safe(p):
    text=p.read_text(encoding='utf-8-sig')
    if rel=='tests.txt':test_text=text;report=fenced(text)
    else:handoff_text=text;handoff=fenced(text)
  except (OSError,ValueError,UnicodeError):pass
 try:
  p=root/'results/acceptance.xlsx'
  if safe(p):workbook=runpy.run_path(str(gt/'xlsx_reader.py'))['load'](p)
 except Exception as exc:
  if type(exc).__name__=='ProfileUnsupported':raise RuntimeError('H052_ARTIFACT_PROFILE_UNSUPPORTED_UNASSESSED: '+str(exc)) from exc
 required_ids=read(original/'requirements.json')
 native_rows=(workbook or {}).get('rows',[])
 trace_rows=(report or {}).get('cases',[])
 trace_rows=trace_rows if isinstance(trace_rows,list) else []
 native_coverage=sum(sum(isinstance(row,dict) and row.get('id')==requirement['id'] for row in native_rows)==1 for requirement in required_ids)/len(required_ids) if workbook is not None else 0
 trace_coverage=sum(sum(isinstance(row,dict) and row.get('case_id')==requirement['public_test_id'] for row in trace_rows)==1 for requirement in required_ids)/len(required_ids) if report is not None else 0
 scores['delivery_integrity']=.7*float(protected_ok)+.1*trace_coverage+.1*float(bool(handoff_text and handoff_text.strip()))+.1*native_coverage
 report=report or {};handoff=handoff or {};workbook=workbook or {};hx=lambda a,b:isinstance(a,str) and a.lower()==b
 bindings=[report.get('schema_version')=='h052-acceptance-run/v1',hx(report.get('source_digest'),digest)]
 h=report.get('source_sha256') if isinstance(report.get('source_sha256'),dict) else {}
 bindings.extend(hx(h.get(k),v) for k,v in hashes.items())
 for field,name in [('fixture_sha256','fixtures/acceptance_cases.json'),('public_expected_sha256','fixtures/acceptance_expected.json'),('runner_sha256','runner.py'),('client_runner_sha256','client_runner.mjs')]:bindings.append(hx(report.get(field),sha(original/name)))
 reported=report.get('cases') if isinstance(report.get('cases'),list) else [];public_units={x['case_id']:x for x in units if x['case_id'].startswith('PUB-')};factual=[]
 for case_id,unit in public_units.items():
  rows=[x for x in reported if isinstance(x,dict) and x.get('case_id')==case_id]
  factual.append(len(rows)==1 and rows[0].get('status')==('PASS' if unit['correct'] else 'FAIL') and equal(rows[0].get('actual'),actual[case_id]))
 tests_sha=sha(root/'results/tests.txt') if test_text is not None else ''
 tracker_bindings=[hx(workbook.get('source_digest'),digest),hx(workbook.get('tests_sha256'),tests_sha)]
 requirements=read(original/'requirements.json');rows=workbook.get('rows') or [];track=[]
 for requirement in requirements:
  selected=[x for x in rows if x.get('id')==requirement['id']]
  if len(selected)!=1:track.append(False);continue
  row=selected[0];paths=row.get('implementation_paths');paths=[x.strip() for x in paths.split(';')] if isinstance(paths,str) else []
  test=requirement['public_test_id'];track.append(row.get('priority')==requirement['priority'] and requirement['owner'] in paths and all(x in EDITABLE for x in paths) and row.get('test_ids')==test and row.get('status')==('PASS' if public_units[test]['correct'] else 'FAIL'))
 handoff_checks=[hx(handoff.get('source_digest'),digest),hx(handoff.get('tests_sha256'),tests_sha),handoff.get('entrypoint')=='python -B app.py --db results/demo.sqlite --port 0 --ready-file results/ready.json',handoff.get('real_browser') is False,handoff.get('external_services') is False]
 scores['evidence_binding']=.25*sum(bindings)/len(bindings)+.5*sum(factual)/len(factual)+.15*(sum(tracker_bindings)/len(tracker_bindings))*(sum(track)/len(track))+.1*sum(handoff_checks)/len(handoff_checks)
 scores['overall_score']=sum(scores[k]*v for k,v in WEIGHTS.items())
 cleanup=[read(p) for p in (derived/'runs').rglob('*.cleanup.json')]
 if cleanup and not all(x['terminated'] for x in cleanup):raise RuntimeError('H052_SERVER_CLEANUP_INCOMPLETE_UNASSESSED')
 observations={'schema_version':'h052-rule-observations/v1','scores':scores,'source_sha256':hashes,'source_digest':digest,'units':units,'protected_inputs_intact':protected_ok,'report_source_bindings':bindings,'fixed_public_factual_checks':factual,'tracker_bindings':tracker_bindings,'fixed_requirement_tracker_checks':track,'handoff_checks':handoff_checks,'actual_server_cleanup':{'processes':len(cleanup),'all_terminated':all(x['terminated'] for x in cleanup)},'scope':'actual localhost HTTP/SQLite/JS controller+HTML semantics; no browser DOM/Harness/Judge/expert or OS sandbox claim','parallel':'actual two HTTP request threads, either raw-source allowed linearization accepted','elapsed_not_capability_gate':True}
 (derived/'scoring-observations.json').write_text(json.dumps(observations,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'h052_actual_scores':scores,'failed_units':[x['case_id'] for x in units if not x['correct']]}))
 return scores
