"""H040 deterministic private checker: source-first truth; tolerant local visual roles."""
from pathlib import Path, PurePosixPath
import hashlib, json, math, os, stat

WEIGHTS={'business_correctness':.55,'boundary_cases':.25,'delivery_integrity':.15,'evidence_binding':.05}
ALIASES={
'selections':['selections','\u9009\u62e9','\u9009\u4e2d\u9879','\u9009\u62e9\u6620\u5c04','\u6620\u5c04'],
'source_images':['source_images','\u6e90\u56fe\u50cf','\u539f\u56fe','\u56fe\u50cf\u6e90'],
'scene_id':['scene_id','scene','image_id','\u573a\u666fID','\u573a\u666f','\u56fe\u50cfID'],
'source_path':['source_path','source','\u6e90\u8def\u5f84','\u5b9e\u9645\u8def\u5f84','\u6e90\u6587\u4ef6'],
'target_path':['target_path','target','\u76ee\u6807\u8def\u5f84','\u4ea4\u4ed8\u8def\u5f84'],
'sha256':['sha256','SHA256','SHA-256','\u6e90SHA256','\u54c8\u5e0c'],
'image_path':['image_path','path','\u56fe\u50cf\u8def\u5f84','\u539f\u56fe\u8def\u5f84'],
'visual_evidence':['visual_evidence','\u89c6\u89c9\u8bc1\u636e','\u8bc1\u636e'],
'active_panel':['active_panel','\u6d3b\u52a8\u9762\u677f','\u6d3b\u52a8\u5217\u8868'],
'selected_row':['selected_row','\u9009\u4e2d\u884c'],
'ancestor_chain':['ancestor_chain','\u7956\u5148\u94fe','\u76ee\u5f55\u7956\u5148\u94fe'],
'coordinate_space':['coordinate_space','\u5750\u6807\u7cfb'],
'bbox':['bbox','bounding_box','\u77e9\u5f62','\u8fb9\u754c\u6846'],
'polygon':['polygon','\u591a\u8fb9\u5f62'],
'regions':['regions','region_table','visual_regions','\u533a\u57df\u8868','\u533a\u57df','\u533a\u57df\u5217\u8868'],
'ref':['region_ref','region_id','region_ids','ref','\u533a\u57dfID']
}
def pick(d,key,default=None):
    if not isinstance(d,dict):return default
    return next((d[k] for k in ALIASES.get(key,[key]) if k in d),default)
def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(131072),b''):h.update(b)
    return h.hexdigest()
def trusted(gt,name):
    p=gt/name
    if not p.is_file() or p.is_symlink():raise RuntimeError('H040_TRUSTED_MISSING:'+name)
    try:return json.loads(p.read_text(encoding='utf-8'))
    except (ValueError,UnicodeError) as e:raise RuntimeError('H040_TRUSTED_INVALID:'+name) from e
def relative(value,root,prefix):
    if not isinstance(value,str) or not value or '\x00' in value:return None
    p=PurePosixPath(value.replace('\\','/'))
    if '..' in p.parts:return None
    text=p.as_posix()
    if text.startswith('/tmp_workspace/'):text=text[len('/tmp_workspace/'):]
    elif p.is_absolute():
        try:text=Path(text).relative_to(root).as_posix()
        except ValueError:return None
    if prefix=='target':
        if text.startswith('results/'):text=text[len('results/'):]
        return text if text.startswith('selected_files/') and len(PurePosixPath(text).parts)>1 else None
    return text if text.startswith(prefix+'/') else None
def ordinary(p,root):
    try:
        if not p.is_relative_to(root) or not stat.S_ISREG(p.lstat().st_mode):return False
        q=p
        while q!=root:
            if q.is_symlink():return False
            q=q.parent
        return True
    except OSError:return False
def read_mapping(p):
    if not ordinary(p,p.parent):return None
    if p.stat().st_size>5*1024*1024:return None
    try:
        d=json.loads(p.read_text(encoding='utf-8-sig'))
        return d if isinstance(d,dict) else None
    except (ValueError,UnicodeError,OSError):return None
class BadGeometry(ValueError):pass
class UnsupportedGeometry(RuntimeError):pass

def region_table(mapping,evidence):
    ans={}
    for d in [mapping,evidence]:
        r=pick(d,'regions')
        if isinstance(r,dict):ans.update(r)
        elif isinstance(r,list):
            for x in r:
                if isinstance(x,dict):
                    key=x.get('id',x.get('region_id',x.get('\u533a\u57dfID')))
                    if isinstance(key,str):ans[key]=x
    return ans
def geometry(value,table,sid,width,height,space='pixels',seen=None):
    """Decode common rect/polygon/normalized/ref representations without layout pinning."""
    seen=set() if seen is None else seen
    result=[]
    def emit(points,sc,local_sid):
        if local_sid!=sid:raise BadGeometry('wrong image ID')
        if not points or any(len(p)!=2 for p in points):raise BadGeometry('invalid point')
        try:pts=[[float(a),float(b)] for a,b in points]
        except (ValueError,TypeError):raise BadGeometry('non numeric point')
        if any(not math.isfinite(v) for p in pts for v in p):raise BadGeometry('nonfinite point')
        if str(sc).lower() in {'normalized','normalised','0-1','0\u20131'}:pts=[[x*width,y*height] for x,y in pts]
        if any(x<0 or x>width or y<0 or y>height for x,y in pts):raise BadGeometry('outside image')
        area=abs(sum(pts[i][0]*pts[(i+1)%len(pts)][1]-pts[(i+1)%len(pts)][0]*pts[i][1] for i in range(len(pts)))/2)
        if len(pts)<3 or area<=0:raise BadGeometry('degenerate shape')
        result.append(pts)
    def walk(v,sc,local_sid,depth=0):
        if depth>16:raise BadGeometry('region recursion limit')
        if isinstance(v,str):
            if v not in table:raise BadGeometry('unresolved region ID')
            if v in seen:raise BadGeometry('cyclic region ID')
            seen.add(v);walk(table[v],sc,local_sid,depth+1);seen.remove(v);return
        if isinstance(v,list):
            if len(v)==4 and all(isinstance(x,(int,float)) and not isinstance(x,bool) for x in v):
                x0,y0,x1,y1=v
                if x1<=x0 or y1<=y0:raise BadGeometry('invalid rectangle')
                emit([[x0,y0],[x1,y0],[x1,y1],[x0,y1]],sc,local_sid);return
            if len(v)>=3 and all(isinstance(p,(list,tuple)) and len(p)==2 and all(isinstance(x,(int,float)) for x in p) for p in v):
                emit(v,sc,local_sid);return
            for x in v:walk(x,sc,local_sid,depth+1)
            return
        if not isinstance(v,dict):raise BadGeometry('no geometry')
        sc=pick(v,'coordinate_space',sc);local_sid=pick(v,'scene_id',local_sid)
        typ=str(v.get('type',v.get('shape',v.get('geometry_type','')))).lower()
        if typ and typ not in {'rectangle','rect','bbox','polygon','region',''}:
            if any(k in v for k in ['center','radius','radii','points','coordinates','cx','x','geometry']):
                raise UnsupportedGeometry('H040_UNSUPPORTED_GEOMETRY:'+typ)
            raise BadGeometry('unrecognized malformed geometry type')
        ref=pick(v,'ref')
        if ref is not None:
            walk(ref,sc,local_sid,depth+1);return
        box=pick(v,'bbox')
        if box is not None:
            if isinstance(box,dict) and {'x','y','width','height'}<=set(box):
                box=[box['x'],box['y'],box['x']+box['width'],box['y']+box['height']]
            walk(box,sc,local_sid,depth+1);return
        poly=pick(v,'polygon')
        if poly is None and typ=='polygon':poly=v.get('points',v.get('coordinates'))
        if poly is not None:emit(poly,sc,local_sid);return
        if {'x','y','width','height'}<=set(v):
            walk([v['x'],v['y'],v['x']+v['width'],v['y']+v['height']],sc,local_sid,depth+1);return
        children=pick(v,'regions')
        if children is not None:walk(children,sc,local_sid,depth+1);return
        for key in ['boxes','nodes','border_segments','geometry','coordinates','area','\u51e0\u4f55']:
            if key in v:walk(v[key],sc,local_sid,depth+1);return
        raise BadGeometry('missing bbox, polygon, or region reference')
    walk(value,space,sid)
    if not result:raise BadGeometry('empty geometry')
    return result

def has_prose(x):
    if isinstance(x,dict):
        for k,v in x.items():
            if k in {'visible_object','selection_relation','description','note','reason','\u8bf4\u660e','\u53ef\u89c1\u5bf9\u8c61','\u9009\u62e9\u5173\u7cfb'} and isinstance(v,str) and len(v.strip())>=3:return True
        return any(has_prose(v) for v in x.values())
    if isinstance(x,list):return any(has_prose(v) for v in x)
    return False
def decode_images(gt,expected):
    try:from PIL import Image,ImageDraw,ImageChops,__version__ as pillow_version
    except ImportError as e:raise RuntimeError('H040_DECODER_UNAVAILABLE:Pillow') from e
    if pillow_version!='12.3.0':raise RuntimeError('H040_DECODER_VERSION:'+pillow_version)
    images={}
    for e in expected['source_images']:
        p=gt/e['path']
        if not p.is_file() or digest(p)!=e['sha256']:raise RuntimeError('H040_TRUSTED_IMAGE_BINDING:'+e['scene_id'])
        try:
            with Image.open(p) as im:
                if im.format!='PNG' or im.size!=(1800,1100):raise ValueError('PNG shape')
                im.load();rgb=im.convert('RGB')
                if hashlib.sha256(rgb.tobytes()).hexdigest()!=e['rgb_sha256']:raise ValueError('RGB content')
        except Exception as ex:raise RuntimeError('H040_TRUSTED_IMAGE_DECODE:'+e['scene_id']) from ex
        r,g,b=rgb.split()
        blue=ImageChops.multiply(r.point(lambda x:255 if x<100 else 0),b.point(lambda x:255 if x>140 else 0))
        blue=ImageChops.multiply(blue,g.point(lambda x:255 if x<165 else 0))
        fill=ImageChops.multiply(r.point(lambda x:255 if 175<=x<=235 else 0),g.point(lambda x:255 if 205<=x<=245 else 0))
        fill=ImageChops.multiply(fill,b.point(lambda x:255 if x>=240 else 0))
        images[e['scene_id']]={'blue':blue,'fill':fill}
    return images,(Image,ImageDraw,ImageChops)
def role_quality(value,evidence,mapping,sid,scene,row,images,pil):
    Image,ImageDraw,ImageChops=pil
    table=region_table(mapping,evidence)
    scores={};notes={};total=1800*1100
    for role in ['active_panel','selected_row','ancestor_chain']:
        v=pick(value,role)
        if v is None:scores[role]=0.;notes[role]='missing role';continue
        try:
            polys=geometry(v,table,sid,1800,1100,pick(evidence,'coordinate_space','pixels'))
        except BadGeometry as ex:scores[role]=0.;notes[role]=str(ex);continue
        mask=Image.new('L',(1800,1100));draw=ImageDraw.Draw(mask)
        for poly in polys:draw.polygon([tuple(p) for p in poly],fill=255)
        area=mask.histogram()[255];bounds=mask.getbbox()
        if not area or not bounds:scores[role]=0.;notes[role]='empty region';continue
        def hit(box):return mask.crop(tuple(int(x) for x in box)).histogram()[255]
        def pixel_hit(kind,box=None):
            p=ImageChops.multiply(mask,images[sid][kind])
            return (p.crop(tuple(int(x) for x in box)) if box else p).histogram()[255]
        def boxarea(b):return (b[2]-b[0])*(b[3]-b[1])
        if role=='active_panel':
            panel=scene['active_panel']
            ok=area<=boxarea(panel)*1.55 and hit(panel)/area>=.70 and pixel_hit('blue',panel)>=30
        elif role=='selected_row':
            box=row['bbox']
            ok=area<=boxarea(box)*2 and hit(box)/area>=.65 and hit(box)/boxarea(box)>=.08 and bounds[2]-bounds[0]>=(box[2]-box[0])*.28 and bounds[3]-bounds[1]>=12 and pixel_hit('fill',box)>=200
        else:
            coverage=[hit(n['bbox'])/boxarea(n['bbox']) for n in scene['ancestor_nodes']]
            navhit=hit([18,140,450,1011])
            ok=area<=total*.12 and navhit/area>=.9 and all(c>=.30 for c in coverage)
        scores[role]=float(ok);notes[role]={'area':area,'bbox':bounds,'accepted':bool(ok)}
    return sum(scores.values())/3,{'roles':scores,'geometry':notes}

def grade(workspace_path):
    root=Path(workspace_path).resolve();gt=root/'gt'
    required=['expected.json','business_oracle.json','counterexamples.json','artifact_contract.json','protected_sha256.json','evidence_requirements.json','visual_regions.json','source_truth_lineage.json','trusted_files.json']
    data={name:trusted(gt,name) for name in required}
    for e in data['trusted_files.json']['files']:
        p=gt/e['path']
        if not p.is_file() or p.is_symlink() or digest(p)!=e['sha256']:raise RuntimeError('H040_TRUSTED_FILE_BINDING:'+e['path'])
    expected=data['expected.json'];scenes=data['visual_regions.json']['scenes']
    images,pil=decode_images(gt,expected)
    results=root/'results';mapping=read_mapping(results/'mapping.json')
    rows=pick(mapping,'selections',[]);image_entries=pick(mapping,'source_images',[])
    rows=rows if isinstance(rows,list) else []
    image_entries=image_entries if isinstance(image_entries,list) else []
    expected_rows={(s['scene_id'],s['source_path']):s for s in expected['selections']}
    expected_hashes={s['sha256'] for s in expected['selections']}
    selected_root=results/'selected_files'
    outputs=[]
    links=[]
    for p in sorted(results.rglob('*')) if results.is_dir() else []:
        if p.is_symlink():links.append(p.relative_to(root).as_posix())
        elif p.is_file() and p.stat().st_nlink>1:links.append(p.relative_to(root).as_posix())
    if selected_root.is_dir() and not selected_root.is_symlink():
        for p in sorted(selected_root.rglob('*')):
            if p.is_file() or p.is_symlink():
                valid=ordinary(p,results) and p.stat().st_size<=5*1024*1024
                outputs.append({'path':p.relative_to(results).as_posix(),'sha256':digest(p) if valid else None,'regular':valid})
    actual_hashes={p['sha256'] for p in outputs if p['regular']}
    object_hits=len(expected_hashes&actual_hashes)
    object_recall=object_hits/len(expected_hashes)
    object_precision=object_hits/len(outputs) if outputs else 0.
    object_f1=2*object_hits/(len(expected_hashes)+len(outputs))
    identity_ok=set();role_scores=[];described=[];mapping_items=[];schema_flags=[]
    for r in rows:
        sid=pick(r,'scene_id');sid=sid if isinstance(sid,str) else None;src=relative(pick(r,'source_path'),root,'source_tree');target=relative(pick(r,'target_path'),root,'target');declared=pick(r,'sha256')
        e=expected_rows.get((sid,src))
        p=results/target if target else None
        good=bool(e and isinstance(declared,str) and declared.lower()==e['sha256'] and p and ordinary(p,results) and p.stat().st_size<=5*1024*1024 and digest(p)==e['sha256'])
        if good:identity_ok.add((sid,src))
        evidence=pick(r,'visual_evidence',{})
        schema_flags.append(isinstance(r,dict) and all(pick(r,k) is not None for k in ['scene_id','source_path','sha256','target_path','visual_evidence']))
        if e:
            row=next(x for x in scenes[sid]['selected_rows'] if x['source_path']==src)
            quality,detail=role_quality(evidence,evidence,mapping or {},sid,scenes[sid],row,images,pil)
            mapping_items.append({'key':[sid,src],'quality':quality,'details':detail})
        else:quality=0.
        role_scores.append(((sid,src),quality))
        table=region_table(mapping or {},evidence)
        def prose_role(v):
            if has_prose(v):return True
            if isinstance(v,str) and v in table:return has_prose(table[v])
            if isinstance(v,list):return any(prose_role(z) for z in v)
            if isinstance(v,dict):
                ref=pick(v,'ref')
                if ref is not None:return prose_role(ref)
            return False
        described.append(((sid,src),sum(float(prose_role(pick(evidence,k))) for k in ['active_panel','selected_row','ancestor_chain'])/3))
    identity_recall=len(identity_ok)/len(expected_rows)
    identity_precision=len(identity_ok)/len(rows) if rows else 0.
    identity_f1=2*len(identity_ok)/(len(expected_rows)+len(rows))
    # Extra and duplicate objects/mappings have one owner: business set precision.
    business=(object_f1+identity_f1)/2
    # Conflicting repeated geometry must not cherry-pick the best candidate claim.
    per_key={k:min([s for kk,s in role_scores if kk==k] or [0]) for k in expected_rows}
    geometry_mean=sum(per_key.values())/len(per_key)
    duplicate_map=len(rows)-len({(str(pick(r,'scene_id')),str(pick(r,'source_path'))) for r in rows})
    no_extra=float(len(outputs)==len(expected_hashes) and len(actual_hashes)==len(expected_hashes) and actual_hashes==expected_hashes and len(rows)==len(expected_rows) and duplicate_map==0 and all((pick(r,'scene_id') if isinstance(pick(r,'scene_id'),str) else None,relative(pick(r,'source_path'),root,'source_tree')) in expected_rows for r in rows))
    boundary=geometry_mean
    # Protected-input failures have one owner: delivery. Independent byte and role truth stay scored.
    protected=data['protected_sha256.json']['entries'];protected_paths={e['path'] for e in protected}
    protected_ok=True;protection_details=[]
    for e in protected:
        p=root/e['path'];ok=ordinary(p,root) and digest(p)==e['sha256']
        if not ok:protected_ok=False;protection_details.append(e['path'])
    outside=[]
    for p in root.rglob('*'):
        rel=p.relative_to(root).as_posix()
        if rel=='gt' or rel.startswith('gt/') or rel=='results' or rel.startswith('results/'):continue
        if (p.is_file() or p.is_symlink()) and rel not in protected_paths:outside.append(rel)
    output_regular=selected_root.is_dir() and bool(outputs) and not links and all(p['regular'] for p in outputs)
    schema_ok=bool(mapping is not None and isinstance(pick(mapping,'selections'),list) and isinstance(pick(mapping,'source_images'),list) and len(rows)>0 and all(schema_flags))
    delivery=(float(schema_ok)+float(protected_ok and not outside)+float(output_regular))/3
    image_ok=[]
    for e in expected['source_images']:
        good=any(pick(x,'scene_id')==e['scene_id'] and isinstance(pick(x,'sha256'),str) and pick(x,'sha256').lower()==e['sha256'] and relative(pick(x,'image_path'),root,'screenshots')==e['image_path'] for x in image_entries)
        image_ok.append(float(good))
    image_binding=sum(image_ok)/len(image_ok)
    prose_mean=sum(max([v for k,v in described if k==key] or [0]) for key in expected_rows)/len(expected_rows)
    evidence=(image_binding+prose_mean)/2
    scores={'business_correctness':business,'boundary_cases':boundary,'delivery_integrity':delivery,'evidence_binding':evidence}
    scores['overall_score']=sum(scores[k]*v for k,v in WEIGHTS.items())
    ev={'schema':'h040-rule-evidence-v2','scores':scores,'object_recall':object_recall,'object_precision':object_precision,'object_f1':object_f1,'mapping_identity_precision':identity_precision,'mapping_identity_f1':identity_f1,'duplicate_mapping_count':duplicate_map,'precision_owner':'business_correctness_only','mapping_identity_recall':identity_recall,'no_extra_output':no_extra,'geometry_mean':geometry_mean,'source_image_binding':image_binding,'role_description_mean':prose_mean,'protected_inputs_unchanged':protected_ok,'protection_failures':protection_details,'unexpected_outside_results':outside,'nonordinary_or_link_outputs':links,'output_members':outputs,'per_selection_geometry':mapping_items,'limits':['Coordinates/hashes are endpoint evidence; actual image viewing and transient writes require execution trajectory review.','Model-authored truth and reviews are not human expert validation.']}
    edir=os.environ.get('GENERAL_E2E_RULE_EVIDENCE_DIR')
    if edir:
        target=Path(edir)/'h040-rule-evidence.json';target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(ev,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return scores
