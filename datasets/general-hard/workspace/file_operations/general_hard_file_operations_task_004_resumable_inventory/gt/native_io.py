from pathlib import Path
from decimal import Decimal,InvalidOperation
import csv,hashlib,io,json,unicodedata
ALIASES={'幂等键':'key','原路径':'source_path','归档路径':'archive_path','内容哈希':'sha256','字节数':'bytes','状态':'status','初始':'initial','文件':'files','最终':'final','输入哈希':'input_sha256','处理结论':'resolution','初始副本状态':'initial_copy_state','初始索引行数':'initial_index_row_count','来源哈希':'source_sha256','初始副本哈希':'initial_archive_sha256','已核验数':'verified_count','唯一键数':'unique_keys','归档文件数':'archive_file_count','完成':'complete','缺失键':'missing_keys','损坏键':'corrupt_keys'}
ALIASES.update({'来源数':'source_count','初始已校验副本数':'initial_copy_verified_count','部分副本文件数':'partial_file_count','初始索引总行数':'initial_manifest_row_count','重复登记键':'duplicate_index_keys','忽略登记行号':'ignored_manifest_rows','孤儿副本路径':'orphan_partial_paths','检查点声明完成键':'claimed_complete_keys','错误完成键':'false_complete_keys','未声明已校验键':'unclaimed_verified_keys','检查点声明完成数':'checkpoint_declared_complete_count','恢复前实际完成数':'observed_complete_before_resume'})
COLS=['key','source_path','archive_path','sha256','bytes','status']
def nfc(v):return unicodedata.normalize('NFC',v) if isinstance(v,str) else v
def number(v):
    if v is None or isinstance(v,bool):return None
    try:
        d=Decimal(str(v).replace(',',''));return int(d) if d.is_finite() and d==d.to_integral_value() else None
    except (InvalidOperation,ValueError):return None
def path_value(v,kind='archive'):
    if not isinstance(v,str):return None
    v=nfc(v);prefix='/tmp_workspace/results/' if kind=='archive' else '/tmp_workspace/'
    if v.startswith(prefix):v=v[len(prefix):]
    if v.startswith('./'):v=v[2:]
    if not v or v.startswith('/') or '\\' in v or any(x in ('','..','.') for x in v.split('/')):return None
    if kind=='archive' and not v.startswith('archive/'):return None
    if kind=='source' and not v.startswith('source_tree/'):return None
    return v
def pairs(items):
    out={}
    for k,v in items:
        k=ALIASES.get(k,k)
        if k in out:raise ValueError('duplicate JSON key')
        out[k]=v
    return out
def read_json(p):return json.loads(p.read_text(encoding='utf-8-sig'),object_pairs_hook=pairs)
def read_manifest(p):
    reader=csv.DictReader(io.StringIO(p.read_text(encoding='utf-8-sig'),newline=''),delimiter='\t')
    if reader.fieldnames is None:raise ValueError('missing TSV header')
    fields=[ALIASES.get(k.strip(),k.strip()) for k in reader.fieldnames]
    if len(set(fields))!=len(fields) or not set(COLS)<=set(fields):raise ValueError('bad TSV fields')
    rows=[]
    for r in reader:
        if None in r:raise ValueError('ragged TSV')
        rows.append({ALIASES.get(k.strip(),k.strip()):v.strip() if isinstance(v,str) else '' for k,v in r.items()})
    return rows
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def tree(root,exclude_gt=False):
    files={};dirs=[]
    for p in sorted(root.rglob('*')):
        rel=nfc(p.relative_to(root).as_posix())
        if exclude_gt and (rel=='gt' or rel.startswith('gt/')):continue
        if p.is_symlink():files[rel]='SYMLINK'
        elif p.is_file():files[rel]=digest(p)
        elif p.is_dir():dirs.append(rel)
    return {'files':files,'directories':dirs}
def tree_sha(root,exclude_gt=False):return hashlib.sha256(json.dumps(tree(root,exclude_gt),ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def normalize(v,key=None):
    if key=='input_sha256' and isinstance(v,dict):return {nfc(k):x.lower() if isinstance(x,str) else x for k,x in v.items()}
    if isinstance(v,dict):return {ALIASES.get(k,k):normalize(x,ALIASES.get(k,k)) for k,x in v.items()}
    if isinstance(v,list):
        items=[normalize(x,key) for x in v]
        return sorted(items,key=lambda x:json.dumps(x,ensure_ascii=False,sort_keys=True))
    if key in {'bytes','initial_index_row_count','verified_count','unique_keys','archive_file_count','source_count','initial_copy_verified_count','partial_file_count','initial_manifest_row_count','checkpoint_declared_complete_count','observed_complete_before_resume','ignored_manifest_rows'}:return number(v)
    if key and ('sha256' in key or key=='sha256') and isinstance(v,str):return v.lower()
    return nfc(v)
def semantic(root):
    result=root/'results'
    if result.is_symlink() or (result/'archive').is_symlink():raise ValueError('unsafe output root')
    rows=read_manifest(result/'manifest.tsv');report=read_json(result/'recovery.json');files={nfc(p.relative_to(result).as_posix()):digest(p) for p in (result/'archive').rglob('*') if p.is_file() and not p.is_symlink()}
    for row in rows:
        row['key']=nfc(row.get('key'));row['source_path']=path_value(row.get('source_path'),'source');row['archive_path']=path_value(row.get('archive_path'));row['sha256']=row.get('sha256','').lower();row['bytes']=number(row.get('bytes'))
    return {'archive':files,'manifest':normalize(rows),'recovery':normalize(report)}
def validate_final(root,expected,protected=None):
    try:
        if (root/'results').is_symlink() or (root/'results/archive').is_symlink():return False
        rows=read_manifest(root/'results/manifest.tsv');report=read_json(root/'results/recovery.json')
        if not isinstance(report,dict):return False
        bykey={s['key']:s for s in expected['sources']};seen=set();paths=set()
        if len(rows)!=60:return False
        for row in rows:
            key=nfc(row.get('key'));s=bykey.get(key);rel=path_value(row.get('archive_path'))
            if not s or key in seen or not rel or rel in paths:return False
            p=root/'results'/rel
            if p.is_symlink() or not p.is_file() or not p.resolve().is_relative_to((root/'results/archive').resolve()) or digest(p)!=s['sha256']:return False
            if path_value(row.get('source_path'),'source')!=s['source_path'] or row.get('sha256','').lower()!=s['sha256'] or number(row.get('bytes'))!=s['bytes'] or row.get('status')!='verified':return False
            seen.add(key);paths.add(rel)
        actual={nfc(p.relative_to(root/'results').as_posix()) for p in (root/'results/archive').rglob('*') if p.is_file() or p.is_symlink()}
        if actual!=paths:return False
        initial=report.get('initial');final=report.get('final')
        if not isinstance(initial,dict) or not isinstance(final,dict):return False
        if final.get('complete') is not True:return False
        if normalize({k:initial.get(k) for k in expected['recovery']['initial']})!=normalize(expected['recovery']['initial']) or normalize({k:final.get(k) for k in expected['recovery']['final']})!=normalize(expected['recovery']['final']):return False
        files=report.get('files',[])
        if not isinstance(files,list) or any(not isinstance(r,dict) for r in files):return False
        fields=expected['recovery']['files'][0].keys()
        if normalize([{k:r.get(k) for k in fields} for r in files])!=normalize(expected['recovery']['files']):return False
        if protected is not None:
            hashes=report.get('input_sha256',{})
            if not isinstance(hashes,dict) or any(not isinstance(hashes.get(n),str) or hashes[n].lower()!=h for n,h in protected.items()):return False
        return True
    except (ValueError,UnicodeError,OSError,TypeError,AttributeError):return False
