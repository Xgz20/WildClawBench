"""H034 source-first bounded automatic observations, separate from semantic review."""
from pathlib import Path
import hashlib,json,os,re,runpy

def grade(workspace_path=None,transcript=None,**kwargs):
 root=Path(workspace_path or '/tmp_workspace').resolve();gt=root/'gt'
 load=lambda p:json.loads(Path(p).read_text(encoding='utf-8'))
 sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
 binding=load(gt/'scoring_contract.json')
 for rel,digest in binding['private_sha256'].items():
  p=gt/rel
  if not p.is_file() or p.is_symlink() or sha(p)!=digest:raise RuntimeError('H034 private source/rule drift: '+rel)
 io=runpy.run_path(str(gt/'figure_io.py'));office=runpy.run_path(str(gt/'office_runtime.py'))
 mean=io['mean'];text=io['text'];norm=io['norm'];num=io['number']
 if not os.environ.get('GENERAL_E2E_RULE_EVIDENCE_DIR'):raise io['TrustedEvidenceError']('missing managed evidence directory')
 derived=Path(os.environ['GENERAL_E2E_RULE_EVIDENCE_DIR']).resolve()
 if derived==root or root in derived.parents:raise io['TrustedEvidenceError']('derived directory must be outside candidate')
 derived.mkdir(parents=True,exist_ok=True)
 expected=load(gt/'source_truth.json');regions=load(gt/'visual_regions.json');protected=load(gt/'protected_sha256.json');tolerance=load(gt/'source_originals/reading_tolerance.json');machine=load(gt/'machine_contract.json')
 if len(expected['point_readings'])!=28 or len(regions['regions'])!=69 or len(expected['claims'])!=8 or len(protected)!=6:raise io['TrustedEvidenceError']('incomplete adopted source truth')
 # Decode exact originals in the locked Worker, not candidate OCR or arrays.
 from PIL import Image
 sources=[]
 for rel,digest in protected.items():
  p=gt/'source_originals'/rel
  if not p.is_file() or p.is_symlink() or sha(p)!=digest:raise io['TrustedEvidenceError']('missing/drifting private original '+rel)
  if rel.endswith('.png'):
   with Image.open(p) as im:
    im.load()
    if im.size!=(1800,1260) or im.format!='PNG' or getattr(im,'n_frames',1)!=1:raise io['TrustedEvidenceError']('invalid frozen original PNG '+rel)
    sources.append({'file':rel,'sha256':digest,'size':list(im.size),'decoder':'Pillow','frames':1,'actual_candidate_reading_proved':False})
 all_protected={**protected,**machine['auxiliary_public_protected']}
 intact=all((root/p).is_file() and not(root/p).is_symlink() and sha(root/p)==h for p,h in all_protected.items())
 errors={};pending=[];book=None;doc=None;recalculation=None
 def candidate(name,action):
  try:return action(io['BASE']['candidate_path'](root,'results/'+name))
  except io['CandidateError'] as e:errors[name]=str(e);return None
  except office['OfficeRuntimeError'] as e:
   if e.code not in {'OFFICE_INPUT_INVALID','OFFICE_ACTIVE_CONTENT_UNSUPPORTED','OFFICE_EXTERNAL_DATA_UNSUPPORTED'}:raise
   errors[name]=e.code;return None
 def workbook(p):
  nonlocal recalculation
  native=io['read_book'](p)
  if any(c['formula'] for sh in native for c in sh['cells'].values()):
   lockpath=os.environ.get('GENERAL_E2E_OFFICE_LOCK')
   if not lockpath:raise io['TrustedEvidenceError']('formula needs trusted Office lock')
   lock=load(lockpath);office['validate_office_lock'](lock)
   result=office['recalculate_xlsx'](p,lock,derived/'recalculated',timeout_seconds=120);recalculation=result['audit'];native=io['read_book'](result['path'])
  if any(c['kind']=='e' and c['value'] in {'#NAME?','#SPILL!','#CALC!'} for sh in native for c in sh['cells'].values()):raise io['TrustedEvidenceError']('formula engine compatibility needs independent review')
  return native
 book=candidate('figure_review.xlsx',workbook);doc=candidate('review_notes.docx',io['read_docx'])
 data=io['scan'](book or []);claims={ci:io['collect_claim'](data['claims'].get(ci,[])) for ci in machine['claim_ids']}
 if book:
  visible=' '.join(text(c['value']) for sh in book for c in sh['cells'].values() if c['visible'])
  for ci,row in claims.items():
   if row is None and re.search(r'(?<!\w)'+ci+r'(?!\w)',visible):pending.append({'claim':ci,'reason':'visible claim identity in unsupported legal native representation; independent logical extraction required'})
 source_points={p['point_id']:p for p in expected['point_readings']};source_regions={r['region_id']:r for r in regions['regions']}
 for pid,rows in io['inline_points'](claims).items():
  if pid not in data['points']:data['points'][pid]=rows
 def raw_context(ci):return ' '.join(text(v) for k,v in (claims[ci] or {}).items() if k in ['values','axes','limits','target'])
 def claim_route(ci):
  row=claims[ci]
  if not row:return {'score':0.,'missing':True}
  route=io['verdict'](row.get('verdict'));target=text(row.get('target'));ctx=raw_context(ci)
  if route is None:
   pending.append({'claim':ci,'reason':'unhandled legal verdict/prose route','value':row.get('verdict')});return {'score':None,'pending':True}
  wanted=machine['claims'][ci]['source_verdict'];ok=route==wanted
  # Distinct valid assessment targets: a fact may remain unknown while the
  # assertion that the evidence already proves it is refuted. No label-count
  # constraint is imposed, and unsupported interpretations need review.
  if ci in ['C04','C06'] and not ok:
   unknown=bool(re.search(r'未知|未报告|未测|证据不足|unknown|unreported|not measured',ctx,re.I))
   proof_reject=bool(re.search(r'不能|不足以|无效|反驳|not sufficient|does not prove|cannot',ctx,re.I))
   fact_target=bool(re.search(r'事实|真实|质量|显著|等效|fact|quality|significance|equivalence',target,re.I))
   proof_target=bool(re.search(r'推论|充分|证据|证明|inference|sufficien|proof',target,re.I))
   if unknown and proof_reject and ((route=='insufficient' and fact_target) or (route=='refuted' and proof_target)):ok=True
   elif route in ['refuted','insufficient']:
    pending.append({'claim':ci,'reason':'assessment target/fact-versus-proof semantics needs independent review','route':route,'target':target});return {'score':None,'pending':True}
  if ci=='C07' and route=='insufficient':
   # Unknown causal facts are admissible only with the directly visible
   # downward within-group counterevidence and rejected universal inference.
   grouped=(re.search(r'G1.*(?:下降|向下|negative|down)',ctx,re.I) and re.search(r'G2.*(?:下降|向下|negative|down)',ctx,re.I)) or re.search(r'(?:两组|各组|两.*组|both groups|within each group).*(?:下降|向下|negative|down)',ctx,re.I)
   if grouped and re.search(r'反驳|不能|不足以|not sufficient|cannot',ctx,re.I):ok=True
   else:ok=False
  return {'score':float(ok),'observed_route':route,'target':target,'locations':row['_locations'],'semantic_completeness_proved':False}
 routes={ci:claim_route(ci) for ci in claims}
 explicit_ratio=re.search(r'B\s*/\s*A\s*(?:约|approximately|about|[~～])?\s*([0-9]+(?:\.[0-9]+)?)',text((claims['C05'] or {}).get('values')),re.I)
 if explicit_ratio:
  ratio=float(explicit_ratio[1]);ratio_ok=abs(ratio-10)<=10*tolerance['F03']['ratio_relative_tolerance']+1e-8
  routes['C05']['explicit_B_over_A_ratio']={'value':ratio,'within_public_tolerance':ratio_ok}
  if routes['C05'].get('score') is not None:routes['C05']['score']*=float(ratio_ok)
 # Native point records are keyed by observed source identity, not cells or
 # sheet names. Every actually reported known point is checked, so padding
 # false ranges never improves the denominator.
 point_checks={}
 for pid,rows in data['points'].items():
  if pid not in source_points:
   point_checks[pid]={'score':0.,'unplotted_source_identity':True,'locations':[r['location'] for r in rows]};continue
  src=source_points[pid];anchor=src['value']['approximate_visual_anchor'];fig=src['figure'];unit='ms' if fig=='F03' else '%'
  margin=anchor*tolerance['F03']['individual_elapsed_relative_tolerance'] if fig=='F03' else tolerance[fig]['mean_target_pass_absolute_percentage_points' if fig=='F01' else 'mean_and_SD_endpoint_absolute_percentage_points' if fig=='F02' else 'point_success_absolute_percentage_points']
  cs=[]
  for row in rows:
   r=row['record'];bounds=io['bounds'](row,unit);val=io['normalized_number'](row,'value',unit);value_ok=True
   if bounds:
    lo,hi=bounds;center=(lo+hi)/2;source_lo,source_hi=src['value']['consensus_readable_interval'];allowed_lo=source_lo-margin;allowed_hi=source_hi+margin
    value_ok=lo<=hi and hi-lo<=(source_hi-source_lo)+2*margin+1e-8 and allowed_lo-1e-8<=center<=allowed_hi+1e-8 and lo<=allowed_hi and hi>=allowed_lo
    if 'value'in r:value_ok &= val is not None and allowed_lo-1e-8<=val<=allowed_hi+1e-8 and lo-1e-8<=val<=hi+1e-8
   else:value_ok=False
   setting=num(r.get('x'));encoded=io['point_id'](r.get('point_id',''))==pid
   if setting is None and 'x'not in r and encoded and fig!='F02':setting=float(pid.rsplit('-',1)[1])
   setting_ok=fig=='F02' or setting==float(src['value'].get('x',src['annotation_A_x']))
   series=norm(r.get('series'));want=norm(pid.split('-')[1]);series_ok=series in {want,'method'+want,'group'+want} or not series and encoded
   known_units={'%','percent','百分比','百分点','fraction','比例','ratio','0–1','01','ms','毫秒','s','seconds','秒'}
   if bounds is None and norm(r.get('unit')) not in known_units:
    pending.append({'point':pid,'reason':'unhandled legal unit/number representation requires independent review','unit':r.get('unit'),'location':row['location']})
   if series and not series_ok and not re.fullmatch(r'(?:method|group)?[a-z][0-9]*',series):pending.append({'point':pid,'reason':'unhandled descriptive legend/series representation requires independent review','series':r.get('series'),'location':row['location']})
   sd=[]
   for side,left,right in [('lower','sd_low_low','sd_low_high'),('upper','sd_high_low','sd_high_high')]:
    if left in r or right in r:
     a=io['normalized_number'](row,left,unit);z=io['normalized_number'](row,right,unit);band=src.get('error_endpoints',{}).get(side,{}).get('consensus_readable_interval');mid=sum(band)/2 if band else None
     sd.append(bool(a is not None and z is not None and a<=z and band is not None and z-a<=band[1]-band[0]+4+1e-8 and band[0]-2-1e-8<=(a+z)/2<=band[1]+2+1e-8))
   sd_ok=all(sd) and (fig!='F02' or len(sd)==2)
   cs.append({'numeric_interval':bool(value_ok),'unit':bounds is not None,'setting':setting_ok,'series':series_ok,'SD_endpoints':sd_ok,'bounds':bounds,'location':row['location']})
  point_checks[pid]={'score':float(bool(cs) and all(all(c[k] for k in ['numeric_interval','unit','setting','series','SD_endpoints']) for c in cs)),'copies':cs}
 # Source-role prose readouts can be legal. Defer unsupported extraction,
 # never manufacture false zero/full credit merely for a different layout.
 required=machine['required_point_ids']
 for pid in required:
  if pid not in point_checks:
   owner=machine['point_owner'][pid];row=claims[owner]
   if row and re.search(r'\d',text(row.get('values'))):pending.append({'claim':owner,'point':pid,'reason':'legal inline readout representation needs independent extraction/review'})
   point_checks[pid]={'score':0.,'missing':True}
 def reg_boxes(r):
  if 'bbox_xyxy_px'in r:return [r['bbox_xyxy_px']]
  if 'point_bboxes_xyxy_px'in r:return r['point_bboxes_xyxy_px']
  return sum((reg_boxes(source_regions[m]) for m in r.get('member_region_ids',[])),[])
 evidence={}
 for ci in claims:
  row=claims[ci] or {};refs=text(row.get('region_refs'));own=[]
  for rid,rr in data['regions'].items():
   if re.search(r'(?<!\w)'+re.escape(rid)+r'(?!\w)',refs):
    for z in rr:own.append({'file':io['filename'](z['record'].get('file')),'boxes':io['region_geometry'](z['record']),'record':z['record'],'location':z['location']})
  if not own and row.get('region_refs'):
   direct=io['region_geometry'](row);f=io['filename'](row.get('file'));fig=re.search(r'F0[1-4]',text(row.get('claim','')))
   if not f and fig:f=next(p['file'] for p in expected['figures'] if p['figure']==fig[0])
   if direct:own=[{'file':f,'boxes':direct,'location':row.get('_locations')}]
  checks=[]
  for rid in regions['claim_bindings'][ci]:
   r=source_regions[rid];checks.append({'source_region':rid,'bound':all(any(o['file']==r['file'] and io['hit'](o['boxes'],bb) for o in own) for bb in reg_boxes(r))})
  evidence[ci]={'score':mean(c['bound'] for c in checks),'targets':checks,'actual_bound_records':own,'source_SHA_verified':True,'actual_candidate_viewing_proved':False}
 business_ids=machine['business_claims'];boundary_ids=machine['boundary_claims']
 numeric=mean(point_checks[pid]['score'] for pid in required)
 # Extra reported points/errors cannot be diluted by correct duplicates.
 reported=mean(p['score'] for p in point_checks.values());numeric=min(numeric,reported)
 business=.65*numeric+.35*mean(routes[c].get('score') or 0. for c in business_ids)
 boundary=mean(routes[c].get('score') or 0. for c in boundary_ids)
 budget_ctx=raw_context('C02');budget_axes=text((claims['C02'] or {}).get('axes'))
 budget_scale=bool(re.search(r'对数|log',budget_axes,re.I) and all(re.search(r'(?<!\d)'+str(t)+r'(?!\d)',budget_ctx) for t in [1,10,100]))
 stats_ctx=raw_context('C04');quality_ctx=raw_context('C06')
 stats_unknown=bool(re.search(r'未知|unknown|未报告|证据不足',stats_ctx,re.I))
 quality_unknown=bool(re.search(r'未知|unknown|未报告|未测|证据不足',quality_ctx,re.I))
 boundary=mean([routes['C02'].get('score') or 0.,budget_scale,routes['C04'].get('score') or 0.,stats_unknown,routes['C06'].get('score') or 0.,quality_unknown,routes['C07'].get('score') or 0.])
 # Independently reported Word conclusions are transfer checks only. Free
 # thematic prose is permitted; no mirror, fixed headings or page count.
 word_routes={};current=None;word_target=''
 if doc:
  for p in doc['paragraphs']:
   m=re.match(r'^C0*([1-8])(?:\s|\b)',p)
   if m:current=f'C{int(m[1]):02}';word_target=p
   m=re.match(r'^(?:判断|判定|结论|verdict|decision)\s*[:：]\s*([^。.;；\n]+)',p,re.I)
   if m and current:
    route=io['verdict'](m[1]);word_routes.setdefault(current,[]).append({'route':route,'text':p,'target':word_target})
 conflicts=[]
 for ci,obs in word_routes.items():
  left=routes[ci].get('observed_route')
  if left and any(z['route'] and z['route']!=left for z in obs):
   if ci in ['C04','C06','C07']:
    def kind(s):return 'proof' if re.search(r'推论|充分性|已经证明|proof|sufficien',s,re.I) else 'fact' if re.search(r'真实|事实|真实次序|actual|fact',s,re.I) else 'compound' if re.search(r'合并.*组内|复合|compound',s,re.I) else None
    leftkind=kind(text((claims[ci] or {}).get('target')))
    allowed=routes[ci].get('score')==1. and leftkind and all(kind(z['target']) and kind(z['target'])!=leftkind for z in obs if z['route'] and z['route']!=left)
    if not allowed:
     if leftkind and all(kind(z['target'])==leftkind for z in obs if z['route'] and z['route']!=left):conflicts.append({'claim':ci,'xlsx':left,'docx':obs,'same_explicit_target_kind':leftkind})
     else:pending.append({'claim':ci,'reason':'different fact/proof/compound targets across artifacts need independent review','word':obs})
   else:conflicts.append({'claim':ci,'xlsx':left,'docx':obs})
 native_book=bool(book) and any(c['visible'] and c['editable'] and c['value'] is not None for sh in book for c in sh['cells'].values()) and all(c['editable'] for sh in book for c in sh['cells'].values() if c['visible'] and c['value'] not in [None,''])
 native_doc=bool(doc and doc['editable'] and doc['visible_native'])
 delivery=mean([native_book,native_doc,intact,not conflicts]) if book is not None or doc is not None else 0.
 scores={'business_correctness':business,'boundary_cases':boundary,'delivery_integrity':delivery,'evidence_binding':mean(e['score'] for e in evidence.values())}
 # Input preservation is owned by the intact delivery slot; source-first
 # business and figure binding remain independently assessable from private originals.
 scores['overall_score']=sum(scores[k]*w for k,w in machine['checkpoint_weights'].items())
 observation={'schema':'h034-rule-observations/v1','source_author_or_candidate_is_not_expert':True,'scores':scores if not pending else None,'bounded_provisional_observations':scores,'public_inputs_unchanged':intact,'source_images':sources,'native_parse_headers':data['headers'],'point_checks':point_checks,'claim_routes':routes,'evidence_binding':evidence,'cross_artifact_transfer_conflicts':conflicts,'errors':errors,'office_recalculation':recalculation,'pending_independent_semantic_review':pending,'semantic_status':'not executed; automatic values do not certify actual looking or scientific interpretation','hybrid_score':None,'candidate_code_executed':False}
 with (derived/'rule-observations.json').open('x',encoding='utf-8') as f:json.dump(observation,f,ensure_ascii=False,indent=2);f.write('\n')
 if pending:raise io['SemanticReviewRequired']('H034 legal representation/assessment target requires independent review; see derived/rule-observations.json; no ability score emitted')
 return scores
