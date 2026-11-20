"""Trusted JSON/Markdown readers. Does not execute candidate content or follow links."""
import json, re, unicodedata
from decimal import Decimal, InvalidOperation

ALIASES={
 'files':['文件','逐文件计划'],'file_id':['文件编号'],'path':['路径'],'sha256':['内容哈希'],
 'decision':['分类'],'allocated_known_bytes':['已知占用字节'],'allocation_complete':['占用完整'],
 'freeable_if_alone_bytes':['单文件可释放字节'],'evidence':['依据'],'usage_file_id':['快照文件编号'],
 'rule_id':['规则编号'],'reason':['理由'],'summary':['汇总'],'confirmation':['确认状态'],'executed':['已执行'],
 'selected_file_ids':['已选文件编号'],'input_sha256':['输入哈希'],'snapshot_id':['快照编号'],
 'file_count':['文件数'],'known_allocated_union_bytes':['去重已知占用字节'],
 'unknown_block_count':['未知块数'],'cleanable_set_freeable_bytes':['候选全集可释放字节'],
 'follow_target':['跟随目标'],'target_allocated_bytes':['目标占用字节'],
}
REVERSE={alias:k for k,v in ALIASES.items() for alias in v}
def normalize(value):
    if isinstance(value,dict):
        out={}
        for k,v in value.items():
            nk=REVERSE.get(k,k)
            if nk in out: raise ValueError('duplicate normalized key: '+nk)
            out[nk]=normalize(v)
        return out
    if isinstance(value,list):return [normalize(v) for v in value]
    return value
def pairs(items):
    out={}
    for k,v in items:
        if k in out:raise ValueError('duplicate JSON key')
        out[k]=v
    return out
def read_json(path):return normalize(json.loads(path.read_text(encoding='utf-8-sig'),object_pairs_hook=pairs))
def npath(value):
    if not isinstance(value,str):return None
    value=unicodedata.normalize('NFC',value)
    if value.startswith('/tmp_workspace/'):value=value[len('/tmp_workspace/'):]
    if value.startswith('./'):value=value[2:]
    if not value or value.startswith('/') or '\\' in value or any(x in {'','..','.'} for x in value.split('/')):return None
    return value
def number(value):
    if isinstance(value,bool) or value is None:return None
    try:
        d=Decimal(str(value).replace(',','').strip())
        return int(d) if d.is_finite() and d==d.to_integral_value() else None
    except (ValueError,InvalidOperation):return None
def decision(value):
    if not isinstance(value,str):return None
    return {'可清理':'cleanable','需确认':'needs_confirmation','需要确认':'needs_confirmation','必须保留':'must_keep'}.get(value,value)
def pending(value):return value in ('pending','待确认')
def report_summary(path):
    text=path.read_text(encoding='utf-8-sig')
    for match in re.finditer(r'```(?:json|JSON)\s*\n(.*?)\n```',text,re.S):
        try:
            v=normalize(json.loads(match.group(1),object_pairs_hook=pairs));v=v.get('summary',v)
            if isinstance(v,dict) and 'file_count' in v:return v
        except (ValueError,TypeError,AttributeError):pass
    out={}
    for line in text.splitlines():
        cells=[re.sub(r'[`*]','',s.strip()) for s in line.strip().strip('|').split('|')]
        if len(cells)<2:continue
        key=REVERSE.get(cells[0],cells[0]);value=cells[1]
        if key not in ('file_count','known_allocated_union_bytes','unknown_block_count','cleanable_set_freeable_bytes','confirmation','executed'):continue
        if key in out:raise ValueError('duplicate report metric')
        out[key]=False if value.lower() in ('false','否','未执行') else True if value.lower() in ('true','是','已执行') else value
    return out
