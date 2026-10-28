"""Source/visible-location/HTML delivery checks; prose truth/argument remains Judge duty."""
from pathlib import Path
from html.parser import HTMLParser
import csv,hashlib,json,os,re,runpy,unicodedata,math
W={'business_correctness':.55,'boundary_cases':.25,'delivery_integrity':.15,'evidence_binding':.05}
class TrustedError(RuntimeError):pass
class CandidateError(ValueError):pass
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def norm(x):return re.sub(r'\s+','',unicodedata.normalize('NFKC',str(x or '')))
def mean(v):v=list(v);return sum(v)/len(v) if v else 0.
def safe(root,name):
 p=root/name
 if p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(root.resolve()) and not any(x.is_symlink() for x in [p,*p.parents] if x!=root.parent):return p
 return None
class Document(HTMLParser):
 def __init__(self):super().__init__(convert_charrefs=True);self.stack=[];self.nodes=[];self.styles=[];self.active=[];self.resources=[];self.style_depth=0;self.fragments=[]
 def handle_starttag(self,tag,attrs):
  a=dict(attrs);node={'tag':tag,'attrs':a,'text':[]};self.nodes.append(node)
  if tag in {'script','iframe','frame','canvas','object','embed','form','input','button','textarea','select'}:self.active.append(tag)
  if any(k.lower().startswith('on') for k in a):self.active.append('event_attribute')
  if tag=='meta' and str(a.get('http-equiv','')).lower()=='refresh':self.active.append('meta_refresh')
  for k in ['src','srcset','href','poster','data','background','action']:
   value=a.get(k)
   if value:
    # Only in-document anchors and embedded data are self-contained.
    if not (k=='href' and value.startswith('#')) and not value.lower().startswith('data:'):self.resources.append({'tag':tag,'attribute':k,'value':value})
  if a.get('style'):self.styles.append(a['style'])
  if tag=='style':self.style_depth+=1
  if tag not in {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}:self.stack.append(node)
 def handle_startendtag(self,tag,attrs):self.handle_starttag(tag,attrs);self.handle_endtag(tag)
 def handle_endtag(self,tag):
  if tag=='style':self.style_depth=max(0,self.style_depth-1)
  for i in range(len(self.stack)-1,-1,-1):
   if self.stack[i]['tag']==tag:del self.stack[i:];break
 def handle_data(self,data):
  if self.style_depth:self.styles.append(data)
  if any(n['tag'] in {'style','script','noscript','head'} for n in self.stack):return
  for node in self.stack:node['text'].append(data)
  if any(n['tag']=='body' for n in self.stack) and not any(n['tag']=='template' for n in self.stack) and data.replace('\ufeff','').strip():self.fragments.append({'text':data,'ancestors':list(self.stack)})
 def css_issues(self):
  source='\n'.join(self.styles);source=re.sub(r'/\*.*?\*/','',source,flags=re.S)
  # Decode CSS escapes before examining import/url/property tokens.
  source=re.sub(r'\\([0-9a-fA-F]{1,6})\s?',lambda m:chr(int(m[1],16)) if 0<int(m[1],16)<=0x10ffff else '\ufffd',source);source=re.sub(r'\\([^\r\n])',r'\1',source)
  issues=[]
  if re.search(r'@import\b',source,re.I):issues.append('css_import')
  if re.search(r'(?:^|[;{])\s*(?:-webkit-|-moz-|-ms-)?user-select\s*:',source,re.I):issues.append('css_user_select_declaration')
  for match in re.finditer(r'url\(\s*(["\']?)(.*?)\1\s*\)',source,re.I|re.S):
   if not match[2].strip().lower().startswith('data:'):issues.append('nonembedded_css_url')
  return issues
ALIASES={'source_id':['source_id','来源ID','源ID','事实ID'],'source_locator':['source_locator','来源定位','源定位'],'source_quote':['source_quote','来源短引','源短引'],'target_id':['target_id','段落ID','目标ID'],'article_quote':['article_quote','正文短引','文章短引']}
def parse_map(p):
 if p is None:return None
 try:
  with p.open(encoding='utf-8-sig',newline='') as handle:
   reader=csv.reader(handle);header=next(reader);columns={key:[i for i,h in enumerate(header) if h.strip() in aliases] for key,aliases in ALIASES.items()}
   if any(len(v)!=1 for v in columns.values()):return None
   rows=[]
   for values in reader:
    if not any(values):continue
    if len(values)!=len(header):return None
    rows.append({key:values[indices[0]].strip() for key,indices in columns.items()})
   return rows if len(rows)<=1000 else None
 except (OSError,UnicodeError,csv.Error,StopIteration):return None

def paint_prerequisites(projection, screenshot, rawdoc):
 # Necessary, observable conditions only. Nonuniform pixels are NOT a positive
 # verdict of semantic legibility; the separate Judge must inspect actual PNG.
 try:
  from PIL import Image
  with Image.open(screenshot) as source:
   source.load();rgb=source.convert('RGB')
 except (ImportError,OSError,ValueError) as exc:raise TrustedError('H057_TRUSTED_PNG_DECODER:'+str(exc)) from exc
 extrema=rgb.getextrema();uniform=all(a==b for a,b in extrema);size=rgb.size;records=[];flags=[]
 css='\n'.join(rawdoc.styles)
 for fragment in projection.get('texts',[]):
  color=fragment.get('style',{}).get('color','').strip().lower();alpha_zero=color=='transparent' or bool(re.fullmatch(r'rgba\([^)]*,\s*0(?:\.0*)?\s*\)',color))
  if alpha_zero and re.search(r'text-shadow|text-stroke|background-clip\s*:\s*text',css,re.I):
   raise TrustedError('H057_UNSUPPORTED_PAINT: transparent foreground with composite text requires independent representation review, no ability zero')
  lines=[]
  for rect in fragment.get('rects',[]):
   x0=max(0,math.floor(rect['x']));y0=max(0,math.floor(rect['y']));x1=min(size[0],math.ceil(rect['x']+rect['width']));y1=min(size[1],math.ceil(rect['y']+rect['height']))
   if x1-x0<2 or y1-y0<2:continue
   bounds=(x0,y0,x1,y1);ranges=rgb.crop(bounds).getextrema();nonuniform=any(a!=b for a,b in ranges)
   lines.append({'bbox':bounds,'RGB_extrema':ranges,'nonuniform_necessary_condition':nonuniform})
  effective=bool(fragment.get('visible') and not uniform and not alpha_zero and lines and all(x['nonuniform_necessary_condition'] for x in lines))
  flags.append(effective);records.append({'id':fragment['id'],'DOM_visible':bool(fragment.get('visible')),'foreground_alpha_proven_zero':alpha_zero,'line_rectangles':lines,'effective_prerequisites':effective})
 return flags,{'PNG_sha256':sha(Path(screenshot)),'size':size,'RGB_extrema':extrema,'strictly_uniform_page':uniform,'fragments':records,'scope':'Necessary native/alpha/line-pixel conditions only; NOT proof that nonuniform pixels are glyphs or all content is readable. Separate Judge must inspect actual render; complex unsupported composite has typed review.'}

def grade(workspace_path=None,**kw):
 root=Path(workspace_path or '/tmp_workspace').resolve();gt=Path(__file__).resolve().parent
 def read(name):
  p=gt/name
  try:
   if p.is_symlink() or not p.is_file():raise OSError('not regular')
   return json.loads(p.read_text())
  except (ValueError,OSError,UnicodeError) as e:raise TrustedError('H057_TRUSTED_MISSING_OR_INVALID:'+name) from e
 trusted=read('trusted_files.json')
 for name,digest in trusted.items():
  p=gt/name
  if p.is_symlink() or not p.is_file() or sha(p)!=digest:raise TrustedError('H057_TRUSTED_DRIFT:'+name)
 expected=read('expected.json');contract=read('artifact_contract.json');read('counterexamples.json');read('business_oracle.json');read('evidence_requirements.json');protected=read('protected_sha256.json')
 evidence=os.environ.get('GENERAL_E2E_RULE_EVIDENCE_DIR');lockpath=os.environ.get('GENERAL_E2E_HTML_LOCK')
 if not evidence or not lockpath:raise TrustedError('H057_TRUSTED_HTML_CONTEXT_MISSING')
 derived=Path(evidence).resolve()
 if derived==root or derived in root.parents or root in derived.parents:raise TrustedError('H057_TRUSTED_DERIVED_OVERLAP')
 api=runpy.run_path(str(gt/'html_runtime.py'))
 try:lock=json.loads(Path(lockpath).read_text());api['validate_html_lock'](lock)
 except (OSError,ValueError,api['HtmlRuntimeError']) as e:raise TrustedError('H057_TRUSTED_HTML_RUNTIME:'+str(e)) from e
 article=safe(root,'results/article.html');mp=safe(root,'results/fact_map.csv');notes=safe(root,'results/edit_notes.md');errors={};rawdoc=None;actualdoc=None;projection=None;render=None;paint_report=None;effective_flags=[]
 if article:
  if article.stat().st_size>5*1024*1024:errors['article']='candidate exceeds public5MiB limit'
  else:
   try:source=article.read_text(encoding='utf-8-sig');rawdoc=Document();rawdoc.feed(source)
   except (OSError,UnicodeError,ValueError) as e:errors['article']=str(e)
 if rawdoc is not None and not rawdoc.active:
  try:
   render=api['observe_html'](article,lock,derived/'article-render',resource_root=article.parent,timeout_seconds=60);observation=json.loads(Path(render['path']).read_text());projection=observation['projection'];actualdoc=Document();actualdoc.feed(Path(render['path']).with_name('rendered.html').read_text())
   projected=projection.get('texts',[])
   if len(actualdoc.fragments)!=len(projected) or any(norm(a['text'])!=norm(p['text']) for a,p in zip(actualdoc.fragments,projected)):
    raise TrustedError('H057_UNSUPPORTED_TEXT_NODE_ALIGNMENT: valid rendering needs separate review, no ability zero')
   effective_flags,paint_report=paint_prerequisites(projection,render['screenshot'],rawdoc)
   for fragment,observed,effective in zip(actualdoc.fragments,projected,effective_flags):
    if effective:
     for node in fragment['ancestors']:node.setdefault('visible_text',[]).append(observed['text'])
  except api['HtmlRuntimeError'] as e:
   if e.code in {'HTML_INPUT_INVALID','HTML_INPUT_LIMIT'}:errors['article']=str(e)
   else:raise TrustedError('H057_HTML_OBSERVATION_UNAVAILABLE:'+str(e)) from e
 rows=parse_map(mp);rows=rows if rows is not None else []
 byid={}
 for n in actualdoc.nodes if actualdoc else []:
  ident=n['attrs'].get('id')
  if ident:byid.setdefault(ident,[]).append(n)
 visible=norm(''.join(x['text'] for x,flag in zip((projection or {}).get('texts',[]),effective_flags) if flag))
 idgroups={sid:[r for r in rows if r['source_id']==sid] for sid in expected['expected_ids']}
 native_text=bool(projection and visible and 600<=len(visible)<=2000 and not (projection.get('canvases') or projection.get('frames')))
 h1=[n for n in actualdoc.nodes if n['tag']=='h1' and norm(''.join(n.get('visible_text',[])))] if actualdoc else []
 h2=[n for n in actualdoc.nodes if n['tag']=='h2' and norm(''.join(n.get('visible_text',[])))] if actualdoc else []
 paragraph_count=sum(n['tag'] in {'p','li','blockquote'} and bool(norm(''.join(n.get('visible_text',[])))) for n in actualdoc.nodes) if actualdoc else 0
 checks={'business_correctness':{'native_article':float(native_text),'native_argument_sections':float(len(h1)==1 and len(h2)>=3 and paragraph_count>=3),'facts_structural_coverage':mean(bool(idgroups[sid]) for sid in expected['facts'])},'boundary_cases':{},'delivery_integrity':{},'evidence_binding':{}}
 resources=(rawdoc.resources+rawdoc.css_issues()) if rawdoc else ['article unavailable'];requests=(observation.get('requests',[]) if render else []);blocked=[r for r in requests if r.get('result') not in {'fulfilled','local','allowed'} and not str(r.get('url','')).startswith('http://html-evidence.invalid/')]
 # Remote requests must be judged against the actual request receipts, including escaped CSS.
 remote_attempts=[r for r in requests if not str(r.get('url','')).startswith('http://html-evidence.invalid/') and not str(r.get('url','')).startswith('data:')]
 checks['boundary_cases']={'qualifier_structural_coverage':mean(bool(idgroups[sid]) for sid in expected['qualifiers']),'self_contained_no_active_controls':float(rawdoc is not None and not rawdoc.active and not resources and not remote_attempts)}
 note_text=None
 if notes and notes.stat().st_size<=1024*1024:
  try:note_text=notes.read_text(encoding='utf-8-sig')
  except (UnicodeError,OSError):pass
 changed=[name for name,digest in protected.items() if safe(root,name) is None or sha(root/name)!=digest]
 actual_inputs={p.relative_to(root).as_posix() for p in root.rglob('*') if (p.is_file() or p.is_symlink()) and p.relative_to(root).parts[0] not in {'gt','results'}}
 extra=sorted(actual_inputs-set(protected))
 checks['delivery_integrity']={'original_inputs_and_scope':float(not changed and not extra),'three_parseable_deliverables':mean([projection is not None,mp is not None and bool(rows),isinstance(note_text,str) and len(norm(note_text))>=40])}
 bindings=[]
 for r in rows:
  sid=r['source_id'];src=expected['facts'][sid]['statement'] if sid in expected['facts'] else expected['qualifiers'].get(sid);locator=('facts.csv#' if sid in expected['facts'] else 'editorial.md#')+sid
  targets=byid.get(r['target_id'],[]);target=targets[0] if len(targets)==1 else None;excerpt=norm(r['article_quote']);sq=norm(r['source_quote']);text=norm(''.join(target['text'])) if target else ''
  source_ok=src is not None and r['source_locator']==locator and len(sq)>=6 and sq in norm(src)
  target_ok=target is not None and len(excerpt)>=6 and excerpt in text and excerpt in norm(''.join(target.get('visible_text',[])))
  bindings.append({'source_id':sid,'source_locator_resolves':source_ok,'unique_rendered_target_and_visible_quote':target_ok,'target_id':r['target_id'],'source_quote':r['source_quote'],'article_quote':r['article_quote'],'scope':'binding only, not semantic entailment'})
 # Missing source records have coverage ownership above. Existing records use
 # fixed source-ID units; all locations for one source must bind. Correct row
 # padding cannot dilute an existing wrong quote; extra IDs are invalid units.
 binding_units=[]
 for sid in dict.fromkeys(x['source_id'] for x in bindings):
  values=[x for x in bindings if x['source_id']==sid]
  binding_units.append({'source_id':sid,'record_count':len(values),'source_quote_binding':min(float(x['source_locator_resolves']) for x in values),'rendered_target_quote_binding':min(float(x['unique_rendered_target_and_visible_quote']) for x in values)})
 checks['evidence_binding']={'source_quote_binding':mean(x['source_quote_binding'] for x in binding_units),'rendered_target_quote_binding':mean(x['rendered_target_quote_binding'] for x in binding_units)}
 scores={key:mean(values.values()) for key,values in checks.items()};scores['overall_score']=sum(W[k]*scores[k] for k in W)
 (derived/'h057-analysis.json').write_text(json.dumps({'schema_version':'h057-observable-binding-analysis/v4','scores':scores,'checks':checks,'candidate_errors':errors,'native_visible_nonspace_characters':len(visible),'paint_prerequisites':paint_report,'paragraphs':paragraph_count,'source_ids':{k:len(v) for k,v in idgroups.items()},'binding_observations':bindings,'fixed_source_binding_units':binding_units,'input_changes':changed,'extra_paths':extra,'raw_active_controls':rawdoc.active if rawdoc else None,'raw_resource_dependencies':resources,'actual_remote_request_attempts':remote_attempts,'source_html_sha256':sha(article) if article else None,'source_first_oracle_sha256':sha(gt/'expected.json'),'limits':['Source/target location and rendered text are mechanical evidence, not fact support or argument quality.','Actual platform clipboard/publication not performed or claimed.','Model-authored source/QA is not human expert review; no Harness/Judge/finalize.']},ensure_ascii=False,indent=2)+'\n')
 return scores
