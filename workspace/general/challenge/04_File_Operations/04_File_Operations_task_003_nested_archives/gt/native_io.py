import json,unicodedata
from decimal import Decimal,InvalidOperation
ALIASES={'已执行':'executed','输入哈希':'input_sha256','成员':'members','未展开容器':'unvisited_containers','成员编号':'member_id','容器编号':'container_id','成员序号':'member_index','根归档':'top_archive','容器哈希':'archive_sha256','原始名称十六进制':'raw_name_hex','解码名称':'decoded_name','深度':'depth','声明字节':'declared_bytes','压缩字节':'compressed_bytes','动作':'action','原因代码':'reason_code','目标路径':'target_path','实际状态':'actual_state','实际字节':'actual_bytes','内容哈希':'sha256'}
def nfc(v):return unicodedata.normalize('NFC',v) if isinstance(v,str) else v
def pairs(items):
    out={}
    for k,v in items:
        k=ALIASES.get(k,k)
        if k in out:raise ValueError('duplicate normalized key')
        out[k]=v
    return out
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'),object_pairs_hook=pairs)
def number(v):
    if v is None or isinstance(v,bool):return None
    try:
        d=Decimal(str(v));return int(d) if d.is_finite() and d==d.to_integral_value() else None
    except (InvalidOperation,ValueError):return None
def path_value(v,kind='target'):
    if v is None:return None
    if not isinstance(v,str):return 'INVALID'
    v=nfc(v);prefix='/tmp_workspace/results/' if kind=='target' else '/tmp_workspace/'
    if v.startswith(prefix):v=v[len(prefix):]
    v=v.rstrip('/')
    if v.startswith('./'):v=v[2:]
    if not v or v.startswith('/') or '\\' in v or any(x in ('','..','.') for x in v.split('/')):return 'INVALID'
    if not v.startswith('staging/' if kind=='target' else 'archives/'):return 'INVALID'
    return v
def hex_equal(a,b):return isinstance(a,str) and isinstance(b,str) and a.lower()==b.lower()
