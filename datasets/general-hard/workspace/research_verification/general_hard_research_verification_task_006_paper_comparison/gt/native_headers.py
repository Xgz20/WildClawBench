"""Generic, bounded native semantic headings and same-value verdict labels.

No task/file/sheet/claim identifiers or source truth. Combined human headings
retain their full cell; evidence/source composites are not invented IDs.
"""
import re,unicodedata
class NativeHeaderError(RuntimeError):pass
def norm(value):return re.sub(r'\s+','',unicodedata.normalize('NFKC',str('' if value is None else value))).casefold()
NATIVE_ALIASES={
 'verdict':('判断','判别','判定结果','decision','outcome'),
 'assessment_target':('命题','命题对象','命题与对象','被核命题','核查命题','评估命题','待评估对象','proposition','proposition and target'),
 'rationale':('依据','判断依据','判定依据','核验依据','判断说明','reason','reasoning','grounds'),
 'comparison':('比较条件','比较范围','适用条件','条件与口径','comparison conditions','comparison basis'),
 'limitations':('未决事项','未决问题','未确定项','局限','不确定性','未决与限制','unresolved matters','limitations and uncertainties'),
 'locator':('原件位置','原文位置','来源位置','证据位置','original location','source location'),
 'quantity':('报告量','报告量或指标','量或指标','reported quantity','reported metric'),
 'value':('原数值','原始数值','报告值','原值','reported value','source value'),
 'denominator':('任务分母','执行分母','任务或执行分母','样本分母','execution denominator','task denominator'),
 'source_context':('来源与版本','来源及版本','报告与版本','source and version'),
 'derived_value':('派生值','推算值','计算值','derived value'),
 'derived_context':('派生单位或状态','派生单位与状态','derived unit or state'),
 'comparison_notes':('条件推算与限制','条件、推算与限制','conditions calculations and limitations'),
}
SAFE_PREFIXES=('本例','本项','本次','当前','最终','核验后','核查后','审查后','最终核验','final','current','reviewed')
SAFE_SUFFIXES=('标签','结果','说明','label','result')
HISTORICAL_PREFIXES=('原始','初始','初稿','原稿','旧稿','旧版','旧','历史','草案','previous','historical','initial','original','draft','old')
def _simple(value,aliases):
    key=norm(value)
    native={norm(name):field for field,names in NATIVE_ALIASES.items() for name in names}
    for prefix in HISTORICAL_PREFIXES:
        if key.startswith(prefix):
            tail=key[len(prefix):]
            if aliases.get(tail)=='verdict' or native.get(tail)=='verdict' or tail in ('判断结果','verdictresult'):return ('historical_verdict',)
    if key in aliases:return (aliases[key],)
    if key in native:return (native[key],)
    stripped=key
    for _ in range(3):
        previous=stripped
        for prefix in SAFE_PREFIXES:
            if stripped.startswith(prefix):stripped=stripped[len(prefix):];break
        for suffix in SAFE_SUFFIXES:
            if stripped.endswith(suffix):stripped=stripped[:-len(suffix)];break
        if stripped in aliases:return (aliases[stripped],)
        if stripped in native:return (native[stripped],)
        if stripped==previous:break
    return ()
def header_fields(value,aliases):
    if not isinstance(value,str):return ()
    direct=_simple(value,aliases)
    if direct:return direct
    parts=[p for p in re.split(r'\s*(?:与|及|和|或|[/|&\n]|\s+)\s*',unicodedata.normalize('NFKC',value)) if p]
    if len(parts)<2:return ()
    fields=[]
    for part in parts:
        match=_simple(part,aliases)
        if not match:return ()
        fields.extend(match)
    unique=set(fields)
    if unique=={'locator','citation_id'}:return ('evidence_context',)
    if unique=={'report','version'} or unique=={'file','version'}:return ('source_context',)
    if unique.issubset({'quantity','metric'}):return ('quantity',)
    if unique=={'rationale','comparison'}:return ('rationale','comparison')
    if len(unique)==1:return (fields[0],)
    return ()
def verdict_observation(value,aliases):
    values=value if isinstance(value,list) else [value]
    labels=[];unhandled=[]
    for item in values:
        if not isinstance(item,str) or not item.strip():unhandled.append(item);continue
        key=norm(item)
        if key in aliases:labels.append(aliases[key]);continue
        pieces=[p for p in re.split(r'[\s/|,，;；、()\[\]{}]+',unicodedata.normalize('NFKC',item).strip()) if p]
        for piece in pieces:
            label=aliases.get(norm(piece))
            if label:labels.append(label)
            else:unhandled.append(piece)
    unique=sorted(set(labels))
    status='unhandled' if unhandled or not unique else 'same_value' if len(unique)==1 else 'conflict'
    return {'status':status,'value':unique[0] if status=='same_value' else None,'labels':unique,'raw':value,'unhandled':unhandled}
def make_record(values,mapping,verdict_aliases):
    fields={};observations=[]
    for column,names in mapping.items():
        if column not in values:continue
        value=values[column]
        for name in names:
            fields.setdefault(name,[]).append(value);observations.append({'column':column,'field':name,'raw_value':value})
    record={};conflicts=[]
    for name,items in fields.items():
        nonempty=[v for v in items if v is not None and (not isinstance(v,str) or v.strip())]
        if not nonempty:continue
        if name=='verdict':
            observation=verdict_observation(nonempty,verdict_aliases)
            if observation['status']=='unhandled':raise NativeHeaderError('UNSUPPORTED_NATIVE_VERDICT: clear final label cannot be faithfully normalized; preserve for independent review')
            record[name]=nonempty[0] if len(nonempty)==1 else nonempty
            if observation['status']=='conflict':conflicts.append({'field':name,'observation':observation})
        else:
            unique=[]
            for value in nonempty:
                if all(norm(value)!=norm(existing) for existing in unique):unique.append(value)
            record[name]=unique[0] if len(unique)==1 else unique
    role='decision' if 'verdict' in record else 'historical' if 'historical_verdict' in record else 'auxiliary'
    return {'record':record,'role':role,'field_observations':observations,'conflicts':conflicts}
def verdict_conflicts(rows,identity,verdict_aliases):
    groups={}
    for row in rows:
        record=row['record']
        if 'verdict' not in record:continue
        ref=identity(row)
        if ref is None:continue
        groups.setdefault(ref,[]).append({'observation':verdict_observation(record['verdict'],verdict_aliases),'origin':row.get('origin'),'field_observations':row.get('field_observations',[])})
    result=[]
    for ref,items in groups.items():
        labels={label for item in items for label in item['observation']['labels']}
        if len(labels)>1:result.append({'input_ref':ref,'field':'verdict','kind':'actual_native_final_verdict_conflict','labels':sorted(labels),'observations':items,'historical_and_auxiliary_values_are_not_final_verdicts':True})
    return result
