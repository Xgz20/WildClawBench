"""Objective source/index/visible native relations and bounded explicit contradictions.

All unrestricted natural semantics and channel adaptation remain35% Judge.
"""
from pathlib import Path
from decimal import Decimal,InvalidOperation
import os,json,hashlib,runpy,re
class TrustedEvidenceError(RuntimeError):pass
WEIGHTS={'business_correctness':.55,'boundary_cases':.25,'delivery_integrity':.15,'evidence_binding':.05}
BUSINESS_UNITS={'ledger_values':.20,'ledger_shape':.05,'channel_fact_opportunities':.45,'approved_change_receipts':.15,'channel_structure':.15}
BOUNDARY_UNITS={'channel_publication_compatibility':.85,'passive_offline_scope':.15}
DELIVERY_UNITS={'native_parse_and_render':.60,'input_protection':.30,'output_footprint':.10}
def grade(workspace_path=None,**kwargs):
 root=Path(workspace_path or '/tmp_workspace').resolve();gt=Path(__file__).resolve().parent
 def load(name):
  try:return json.loads((gt/name).read_text())
  except (OSError,ValueError,UnicodeError) as e:raise TrustedEvidenceError('H060_TRUSTED_MISSING_OR_INVALID: '+name) from e
 for name,digest in load('trusted_files.json').items():
  p=gt/name
  if p.is_symlink() or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:raise TrustedEvidenceError('H060_TRUSTED_MISSING_OR_DRIFT: '+name)
 o=load('business_oracle.json');contract=load('artifact_contract.json');protected=load('protected_sha256.json');load('expected.json');load('counterexamples.json');load('evidence_requirements.json');io=runpy.run_path(str(gt/'content_io.py'));claims=runpy.run_path(str(gt/'claim_checks.py'));office=runpy.run_path(str(gt/'office_runtime.py'));browser=runpy.run_path(str(gt/'html_runtime.py'));norm=io['norm'];errors={}
 ev=os.environ.get('GENERAL_E2E_RULE_EVIDENCE_DIR');locks=[os.environ.get(k) for k in ['GENERAL_E2E_OFFICE_LOCK','GENERAL_E2E_OFFICE_RENDER_LOCK','GENERAL_E2E_HTML_LOCK']]
 if not ev or not all(locks):raise TrustedEvidenceError('H060_TRUSTED_OFFICE_HTML_OR_EVIDENCE_CONTEXT_MISSING')
 evidence=Path(ev).resolve()
 if any(p==evidence or p in evidence.parents or evidence in p.parents for p in [root,gt]):raise TrustedEvidenceError('H060_TRUSTED_EVIDENCE_OVERLAP')
 evidence.mkdir(parents=True,exist_ok=True)
 try:
  office_lock,render_lock,html_lock=[json.loads(Path(p).read_text()) for p in locks];office['validate_office_lock'](office_lock);office['validate_office_render_lock'](render_lock);browser['validate_html_lock'](html_lock)
 except (OSError,ValueError,office['OfficeRuntimeError'],browser['HtmlRuntimeError']) as e:raise TrustedEvidenceError('H060_TRUSTED_RUNTIME_INVALID: '+str(e)) from e
 def candidate(name,fn):
  try:return fn()
  except io['CandidateError'] as e:errors[name]=str(e);return None
 def off(fn,*args,**kw):
  try:return fn(*args,**kw)
  except office['OfficeRuntimeError'] as e:
   if 'UNSUPPORTED' in e.code:raise io['UnsupportedRepresentation']('H060_UNSUPPORTED_REPRESENTATION: '+str(e)) from e
   if e.code in {'OFFICE_INPUT_INVALID','OFFICE_DOCX_INPUT_INVALID','OFFICE_INPUT_LIMIT'}:raise io['CandidateError'](str(e)) from e
   raise TrustedEvidenceError('H060_TRUSTED_OFFICE_FAILURE: '+str(e)) from e
 def html_observe(source):
  try:return browser['observe_html'](source,html_lock,evidence/'website',resource_root=source.parent,timeout_seconds=60)
  except browser['HtmlRuntimeError'] as e:
   if 'UNSUPPORTED' in e.code:raise io['UnsupportedRepresentation']('H060_UNSUPPORTED_REPRESENTATION: '+str(e)) from e
   if e.code in {'HTML_INPUT_INVALID','HTML_INPUT_LIMIT'}:raise io['CandidateError'](str(e)) from e
   raise TrustedEvidenceError('H060_TRUSTED_HTML_FAILURE: '+str(e)) from e
 paths={n:candidate(n,lambda n=n:io['path'](root,'results/'+n)) for n in contract['required_names']};channels={n:{'text':'','paragraphs':[]} for n in contract['channel_names']};static=None;html_result=None;word_result=None;pdf_text='';native={n:False for n in contract['required_names']}
 if paths['website.html']:
  raw=candidate('website_UTF8',lambda:io['text_read'](paths['website.html']))
  if raw is not None:
   static=candidate('website_static',lambda:io['html_static'](raw));html_result=candidate('website_render',lambda:html_observe(paths['website.html']))
   if html_result:
    observation=json.loads(Path(html_result['path']).read_text());channels['website.html']=io['html_visible'](observation);native['website.html']=True
 if paths['social.docx']:
  parsed=candidate('social_native',lambda:io['word'](paths['social.docx']))
  if parsed:
   channels['social.docx']=parsed;word_result=candidate('social_render',lambda:off(office['render_docx_pdf'],paths['social.docx'],render_lock,evidence/'social',timeout_seconds=60))
   if word_result:
    try:
     from pypdf import PdfReader
     pdf_text='\n'.join(page.extract_text() or '' for page in PdfReader(word_result['path']).pages)
    except ImportError as e:raise TrustedEvidenceError('H060_TRUSTED_DEPENDENCY_MISSING: pypdf') from e
    except Exception as e:raise TrustedEvidenceError('H060_TRUSTED_PDF_READBACK_FAILURE: '+str(e)) from e
    native['social.docx']=True
 if paths['email_en.md']:
  raw=candidate('email_UTF8',lambda:io['text_read'](paths['email_en.md']))
  if raw is not None:channels['email_en.md']=io['markdown'](raw);native['email_en.md']=True
 index=candidate('change_map_native',lambda:io['json_read'](paths['change_map.json'])) if paths['change_map.json'] else None;native['change_map.json']=index is not None;index=index or {}
 def mean(values):
  values=list(values);return sum(bool(v) for v in values)/len(values) if values else 0.
 def items(v):return v if isinstance(v,list) else []
 def text(v):return isinstance(v,str) and bool(v.strip())
 def grouped(rows,key):
  out={}
  for row in rows:
   if isinstance(row,dict):out.setdefault(str(row.get(key) or '').upper(),[]).append(row)
  return out
 def one(rows,key):return rows[key][0] if len(rows.get(key,[]))==1 else {}
 def equal(a,b,key=None):
  if isinstance(b,bool):return type(a) is bool and a is b
  if isinstance(b,dict):return isinstance(a,dict) and set(a)==set(b) and all(equal(a[k],v,k) for k,v in b.items())
  if isinstance(b,(int,float)) or key=='vat_rate':
   try:
    v=str(a).strip();actual=Decimal(v[:-1])/100 if key=='vat_rate' and v.endswith('%') else Decimal(v);return actual.is_finite() and abs(actual-Decimal(str(b)))<=Decimal('0.00000001')
   except (InvalidOperation,ValueError,TypeError):return False
  return str(a).strip().casefold()==str(b).strip().casefold()
 facts=grouped(items(index.get('facts')),'fact_id');value_checks={fid:equal(one(facts,fid).get('value'),value) for fid,value in o['facts'].items()};shape=set(facts)==set(o['facts']) and all(len(v)==1 for v in facts.values());bindings=[];sourcechecks=[];opportunities=[];eligible={n:{} for n in channels}
 for fid,want in o['facts'].items():
  row=one(facts,fid);owner=o['owners'][fid];ref=row.get('source_ref') if isinstance(row.get('source_ref'),dict) else {};expected={'path':'changes.jsonl' if owner['kind']=='change' else 'approved_facts.json','pointer':owner['pointer']};expected.update({'change_id':owner['change_id'],'seq':owner['seq']} if owner['kind']=='change' else {'approval_id':owner['approval_id']});sourcechecks.append(all(ref.get(k)==v for k,v in expected.items()))
  for name in channels:
   matches=[v for v in items(row.get('locations')) if isinstance(v,dict) and v.get('path')==name];loc=matches[0] if len(matches)==1 else {};bound=io['bind'](channels[name],loc) if loc else False
   if name=='social.docx' and bound:bound=norm(loc['quote']) in norm(pdf_text)
   signal=bool(bound and claims['signal'](fid,loc['quote'],name));ok=value_checks[fid] and signal and native[name];eligible[name][fid]=ok;bindings.append(bound);opportunities.append({'channel':name,'fact_id':fid,'ledger_value_correct':value_checks[fid],'visible_actual_quote_bound':bound,'bounded_identifier_numeric_or_topic_signal':signal,'ready':ok,'semantic_equivalence_proven':False})
 channel_ready={name:all(v['ready'] for v in opportunities if v['channel']==name) for name in channels};records=grouped(items(index.get('changes')),'change_id');changes=[]
 for e in o['events']:
  row=one(records,e['change_id']);changes.append(row.get('seq')==e['seq'] and row.get('status')=='applied' and set(items(row.get('fact_ids')))==set(e['changes']))
 structures={'website.html':bool(static) and static['h1']>=1 and static['semantic_container'] and len(channels['website.html']['text'])>=200,'social.docx':len(channels['social.docx']['paragraphs'])>=5 and len(channels['social.docx']['text'])>=200 and bool(re.search(r'[?？]',channels['social.docx']['text'])),'email_en.md':bool(re.search(r'^Subject\s*:',channels['email_en.md'].get('raw',''),re.I)) and len(channels['email_en.md']['paragraphs'])>=5 and bool(re.search(r'\b(?:review|take a look|please)\b',channels['email_en.md']['text'],re.I))};violations={name:claims['contradictions'](data['text'],eligible[name]) if native[name] else [] for name,data in channels.items()};compatibility={name:not rows for name,rows in violations.items()};publication=index.get('publication') if isinstance(index.get('publication'),dict) else {};declared=index.get('mode')=='draft_only' and all(publication.get(k)==v for k,v in {'website':'not_deployed','social':'draft_only','email':'not_sent'}.items());passive=(not static or not static['active'] and not static['external'] and not static['css_external']) and declared
 units={'ledger_values':mean(value_checks.values()),'ledger_shape':float(shape),'channel_fact_opportunities':mean(channel_ready.values()),'approved_change_receipts':mean(changes),'channel_structure':mean(structures.values())};boundary={'channel_publication_compatibility':mean(compatibility.values()),'passive_offline_scope':float(passive)};changed=[]
 for rel,digest in protected.items():
  p=root/rel
  if not p.is_file() or p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:changed.append(rel)
 footprint={p.relative_to(root/'results').as_posix() for p in (root/'results').rglob('*') if p.is_file()} if (root/'results').is_dir() else set();delivery={'native_parse_and_render':mean([*native.values(),html_result is not None,word_result is not None,not static or not static['duplicate_ids']]),'input_protection':float(not changed),'output_footprint':float(footprint==set(contract['required_names']))};binding_score=.6*mean(sourcechecks)+.4*mean(bindings);scores={'business_correctness':sum(BUSINESS_UNITS[k]*v for k,v in units.items()),'boundary_cases':sum(BOUNDARY_UNITS[k]*v for k,v in boundary.items()),'delivery_integrity':sum(DELIVERY_UNITS[k]*v for k,v in delivery.items()),'evidence_binding':binding_score};scores['overall_score']=sum(WEIGHTS[k]*scores[k] for k in WEIGHTS)
 analysis={'scores':scores,'business_units':units,'boundary_units':boundary,'delivery_units':delivery,'weights':{'business':BUSINESS_UNITS,'boundary':BOUNDARY_UNITS,'delivery':DELIVERY_UNITS},'fact_value_checks':value_checks,'fact_channel_opportunities':opportunities,'channel_ready':channel_ready,'channel_structure':structures,'bounded_explicit_violations':violations,'source_owner_checks':sourcechecks,'actual_quote_bindings':bindings,'changed_inputs':changed,'candidate_errors':errors,'render_receipts':{'HTML':html_result,'Word':word_result},'semantic_Judge_percentage':.35,'semantic_Judge_run':False,'semantic_equivalence_or_publication_proven':False,'causal_ownership':'Required source values, actual visible fact/index coverage and numeric/identity signals are business. Explicit current highrisk qualifiers/extra stale claims are boundary only when that fact has a valid business representation in that channel. Missing/incorrect numeric provision is not charged again in boundary. Wrong owner only evidence. Protected input mutation only delivery protection.','limits':['Bounded explicit phrase checks are not unrestricted natural semantic interpretation','Arbitrary unsupported promises, scoped cross-language meaning and channel suitability require35%Judge','Publication fields are declarations; actual non-sending/deployment requires formal bound traces','All four clients require preflight; L4/discrimination are design estimates; model QA is not human expert review'],'source_sha256':o['source_sha256']};(evidence/'h060-analysis.json').write_text(json.dumps(analysis,ensure_ascii=False,indent=2)+'\n');return scores
