---
id: 03_Data_Analysis_task_010_contract_escrow_refund_reconciliation
name: Contract Escrow Allocation and Refund Reconciliation
category: data-analysis
timeout_seconds: 7200
modality: pure-text
difficulty: L4
grading_type: hybrid
grading_weights:
  automated: 0.8
  llm_judge: 0.2
tags:
  - custom
  - general_e2e
  - finance
judge_evidence:
  required:
    - path: 评分证据/汇总与差异.json
      role: grader_generated_evidence
    - path: 评分证据/分析与验收.json
      role: grader_generated_evidence
    - path: 评分证据/规则核验.json
      role: grader_generated_evidence
---

## Prompt

帮我核对本期合同托管资金，重点看看分期收款、保证金核销和退款冲正后的余额。资料在 `/tmp_workspace/`，按其中《对账口径.md》整理对账明细、币种汇总、差异与待补材料清单，保留来源、分析和实际核对记录。不要猜配缺失引用，原材料保留不改，结果存到 `/tmp_workspace/results/合同托管对账.xlsx`。

## Expected Behavior

覆盖公开指定账户、渠道、期间及所有工作表的有效币种区块，排除展示标题小计并将同ID同内容导出只计一次。按照明确的收款和分配引用核销合同分期及保证金，保持合同、分期和资金用途边界；退款、冲正与重付按事件净额还原。逐币种复算按笔舍入的费用、批次净额及银行到账窗，分列跨期、已知零额、不适用和待确认。形成公开约定的结构化表、可追溯来源及有记录支持的四类分析；实际核对公开覆盖、匹配、金额守恒及差异归属并留下核对记录。仅采用给定模拟业务口径。

## Grading Criteria

评分版本 escrow-2026-10-14-v1；仅以Prompt明确采用的《对账口径.md》及原始工作簿为公开契约，私有GT、能力目录和生成器不增加义务。规则80分、Judge20分。允许行列顺序、表名与字段的无歧义同义表达、原生日期/等价文本、来源集合顺序和直接行/单元格/来源索引引用。额外真实相关来源可接受。未知同义表达不能机械判错；无法安全识别的等价布局、缺公式缓存或GT异常转评测复核，不计为有效零分。

| 检查点 | 业务对象与公开依据 | 分值 | 证据 |
|---|---|---:|---|
| automated.scope | C1产物范围：口径“范围与材料、交付契约”的九类结构化对象及全部原始来源行 | 10 | 产物 |
| automated.matching | C2关联：口径“显式核销、服务结算与退款链、费用币种银行”中的合同、收款、分配、退款及批次身份 | 22 | 产物 |
| automated.amounts | C3金额：口径公开核销、退款、费用、银行及逐币种公式 | 26 | 产物 |
| automated.uncertainty | C4状态：缺引用、缺凭证、确认零额、不适用、无效分配与退款当前状态 | 12 | 产物 |
| automated.traceability | C5来源：交付契约的来源对照、双方位置和原始记录去向 | 10 | 产物 |
| llm_judge.scope_execution | C1实际范围：Prompt路径、原文件不改及口径账户、日期和全部区块范围 | 4 | 真实轨迹＋产物 |
| llm_judge.analysis | C6差异解释：公开分析说明四项及未知边界 | 10 | 产物＋回答 |
| llm_judge.validation | C7实际核对：公开交付前核对四领域、记录方法范围发现证据 | 6 | 真实轨迹＋产物 |

scope按九类表的应有不同主键集合核对，覆盖率分母=应有主键数+额外对象数+多出的重复行数+缺键行数，表序及辅助表不处罚。九表均精确覆盖得1；九表各至少覆盖一个正确对象、但有缺失/重复/额外对象得0.5；至少一类完全无有效交付得0。等价拆表合并核对。

matching按四业务域分别核对所有相关非数值关联字段：①合同及收款身份；②显式分配到收款/应收；③退款到原收款/合同分期；④批次账户币种、待认领、差异及来源对象身份。amounts的四域为①合同/收款/分配核销余额；②退款本金净额；③结算本金、按笔手续费、银行到账及差异已知数；④逐币种汇总和已知/未知计数。uncertainty的四域为①收款缺凭证、缺引用与零额；②无效分配、合同状态和保证金不适用；③退款当前状态；④银行、差异和来源处理边界。各域仅在所有应有字段均符合公开规则时完成；相应检查点为完成域数÷4，固定五档0/0.25/0.5/0.75/1。四域是同一检查点的业务定档依据，不再独立加分；任一整类错误不会被大表正常行稀释。缺主键或重复主键无唯一内容证据；数值仅核对GT可确定字段，未知标记归uncertainty。金额数值存储容差1e-7主单位，不改变公开最小单位舍入和零业务容差。

traceability按合同分配、收款、退款与银行差异、全部来源索引四域统计必要来源完整且相关的对象比例；全部完整得1；每域至少80%完整得0.5；否则0。缺来源不能当作已观察到错算。重复导出保留全部位置，原始/重复标签允许选择不同同内容代表行，只需每对象恰有一条纳入且其余重复。允许全部真实相关佐证，不能用无关或不存在位置充数。

规则组overall_score=Σ(分值×分档得分)/80；Judge组=Σ(分值×分档得分)/20；总分=80×规则组+20×Judge组。关键轨迹或评测证据缺失导致不可判定时，不输出正式总分、不以有效0占位、不删项重归一。候选明确缺交付按公开内容义务计0；GT缺失、读取能力限制或潜在等价表达未复核是评测异常。人工核对、Excel对账或程序校验均可；不因没有特定脚本扣分。

## Automated Checks

```python
"""Self-contained rule grader; embedded verbatim as the task's first Python fence."""
from pathlib import Path
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
import json
import re
import openpyxl
from zipfile import BadZipFile
from xml.etree.ElementTree import ParseError

WEIGHTS = {'scope':10,'matching':22,'amounts':26,'uncertainty':12,'traceability':10}
KEYS = {'合同余额':'应收编号','收款核对':'收款号','分配核对':'分配号','退款核对':'退款申请号',
        '结算银行核对':'批次号','银行待认领':'银行流水号','币种汇总':'币种',
        '待补与差异':'问题编号','来源索引':'来源定位'}
ALIASES = {'合同余额表':'合同余额','收款对账':'收款核对','核销明细':'分配核对','退款明细':'退款核对',
 '银行结算核对':'结算银行核对','币种汇总表':'币种汇总','差异清单':'待补与差异','来源对照':'来源索引',
 '应收ID':'应收编号','收款编号':'收款号','核销编号':'分配号','退款编号':'退款申请号',
 '结算批次':'批次号','银行流水编号':'银行流水号','币别':'币种','源位置':'来源',
 '待核实':'待确认','未知':'待确认','未确认':'待确认','N/A':'不适用','n.a.':'不适用',
 '已核平':'核平','跨期已核平':'跨期核平','原始行':'来源定位'}
STATE_FIELDS = {'分配状态','结算状态','凭证状态','退款状态','收款状态','对账状态','待认领原因','问题类别','处理状态'}
TEXT_EXCLUDE = {'来源','来源定位','所需材料','问题编号'}

def normalized(value):
    if value is None:return ''
    value=str(value).strip()
    return ALIASES.get(value,value)

def number(value):
    try:
        if isinstance(value,bool) or value is None:return None
        result=Decimal(str(value).replace(',','').strip())
        return result if result.is_finite() else None
    except (InvalidOperation,ValueError):return None

def bands(r):
    if r==1:return 1.0
    if r>=.75:return .75
    if r>=.5:return .5
    if r>0:return .25
    return 0.0

def locations(value,index_cells=None):
    """Accept documented row and cell forms; normalized collection is order independent."""
    if isinstance(value,list):parts=value
    else:parts=re.split(r'[;；\n]',str(value or ''))
    result=set()
    for part in parts:
        part=str(part).strip().replace('！','!')
        if index_cells:
            m=re.fullmatch(r"'?([^'!]+)'?!([A-Z]+)(\d+)(?::([A-Z]+)(\d+))?",part,re.I)
            if m and (m[4] is None or m[4].upper()==m[2].upper()):
                first=int(m[3]);last=int(m[5] or first)
                if last-first>100000:raise ValueError('来源索引区间过大')
                refs=[f'{m[1]}!{m[2].upper()}{i}' for i in range(first,last+1)]
                if all(x in index_cells for x in refs):
                    for x in refs:result.update(locations(index_cells[x]))
                    continue
        m=re.fullmatch(r'([^|!]+\.xlsx)[|!]([^|!]+)[|!](?:行|R)?(\d+)',part,re.I)
        if m:result.add((Path(m[1]).name,m[2].strip("'"),int(m[3])));continue
        m=re.fullmatch(r'([^|!]+\.xlsx)[|!]([^|!]+)[|!](?:\$?[A-Z]+\$?)(\d+)(?::\$?[A-Z]+\$?(\d+))?',part,re.I)
        if m:
            first=int(m[3]);last=int(m[4] or first)
            if last-first>100000:raise ValueError('来源区间过大，需评测复核')
            result.update((Path(m[1]).name,m[2].strip("'"),i) for i in range(first,last+1));continue
        if part:raise ValueError('无法安全识别来源等价表示：'+part[:120])
    return result

def read_tables(path,expected):
    workbook=openpyxl.load_workbook(path,data_only=True,read_only=True)
    result={name:[] for name in expected}; narrative={}; review=[]; formula_missing=[]
    for ws in workbook.worksheets:
        grid=list(ws.iter_rows(values_only=True)); active=None;headers=None;header_row=None
        canonical=normalized(ws.title)
        first_labels={normalized(v) for row in grid[:3] for v in row}
        if canonical in ('分析说明','核对记录','表名字段对应说明') or '分析主题' in first_labels or '检查领域' in first_labels:
            narrative[ws.title]={'file':path.name,'sheet':ws.title,'rows':[[v for v in row] for row in grid],'complete':True}
        for rownum,values in enumerate(grid,1):
            labels=[normalized(v) for v in values]
            possible=[]
            for name,rows in expected.items():
                fields=set(rows[0]) if rows else {KEYS[name]}
                if KEYS[name] in labels and len(fields.intersection(labels))>=min(4,len(fields)):
                    overlap=len(fields.intersection(labels))/len(fields)
                    possible.append((overlap+(2 if canonical==name else 0),name))
            if possible:
                possible.sort(reverse=True);active=possible[0][1];headers=labels;header_row=rownum;continue
            if active and any(v is not None for v in values):
                row={h:v for h,v in zip(headers,values) if h};key=row.get(KEYS[active])
                if not key and not any(v is not None for v in values):continue
                # Display headings/subtotals are allowed, but nonblank business-like rows count.
                if key and any(str(key).startswith(x) for x in ('小计','合计','说明')):continue
                row['_candidate_location']=f'{path.name}|{ws.title}|行{rownum}'
                if active=='来源索引' and '来源定位' in headers:row['_source_ref']=f'{ws.title}!{openpyxl.utils.get_column_letter(headers.index("来源定位")+1)}{rownum}'
                result[active].append(row)
        if canonical in expected and not any(result[canonical]):review.append('工作表未能识别：'+ws.title)
    if '表名字段对应说明' in narrative and any(not rows for rows in result.values()):review.append('存在布局对应说明且有逻辑表未安全识别，需按对照人工复核')
    workbook.close()
    # A formula without a cached result is an evaluator limitation, not proof of a wrong result.
    formula_book=openpyxl.load_workbook(path,data_only=False,read_only=True)
    cached=openpyxl.load_workbook(path,data_only=True,read_only=True)
    for ws in formula_book.worksheets:
        for frow,vrow in zip(ws.iter_rows(),cached[ws.title].iter_rows()):
            for f,v in zip(frow,vrow):
                if f.data_type=='f' and v.value is None:formula_missing.append(f'{ws.title}!{f.coordinate}')
    formula_book.close();cached.close()
    if formula_missing:review.append('公式缓存不可用，须安全只读求值后复核：'+','.join(formula_missing[:12]))
    return result,narrative,review

def grade(transcript: list, workspace_path: str) -> dict:
    base=Path(workspace_path);gtpath=base/'gt'/'标准答案.json'
    if not gtpath.is_file():raise FileNotFoundError('评测参考缺失，不能计候选零分：'+str(gtpath))
    reference=json.loads(gtpath.read_text(encoding='utf-8'));expected=reference['tables']
    if set(expected)!=set(KEYS) or not all(expected.values()):raise ValueError('私有参考损坏或结构异常')
    sourcepath=base/'gt'/'标准记录与源位置.json'
    if not sourcepath.is_file():raise FileNotFoundError('缺少私有源定位参考，属于评测异常')
    raw_sources=json.loads(sourcepath.read_text(encoding='utf-8'))
    if set(raw_sources)!={'应收','收款','分配','退款','结算','银行'} or not all(raw_sources.values()):raise ValueError('私有源定位参考损坏')
    candidate=base/'results'/'合同托管对账.xlsx'; evidence=base/'评分证据';evidence.mkdir(exist_ok=True)
    output={};diagnostic={'status':'valid','raw_ratios':{},'mismatches':[],'review_required':[],
       'process_evidence':'本规则不从正确产物推断实际读取或验收；真实轨迹由Judge单独评定。'}
    def candidate_failure(reason):
        output.update({k:0.0 for k in WEIGHTS});output['overall_score']=0.0
        diagnostic['candidate_error']=reason;output['diagnostics']=diagnostic
        (evidence/'规则核验.json').write_text(json.dumps(diagnostic,ensure_ascii=False,indent=2),encoding='utf-8')
        for name in ('汇总与差异','分析与验收'):(evidence/(name+'.json')).write_text(json.dumps({'candidate_failure':reason,'complete':True},ensure_ascii=False),encoding='utf-8')
        return output
    if not candidate.exists():return candidate_failure('缺少公开要求的交付工作簿')
    try: actual,narrative,review=read_tables(candidate,expected)
    except (BadZipFile,ParseError,ValueError,KeyError,openpyxl.utils.exceptions.InvalidFileException) as e:
        return candidate_failure('候选文件不是有效可读XLSX：'+str(e))
    except OSError as e:raise RuntimeError('评测读取环境异常，不能计候选有效零分：'+str(e)) from e
    diagnostic['review_required'].extend(review)
    known_states={field:{normalized(row.get(field)) for rows in expected.values() for row in rows if field in row} for field in STATE_FIELDS}
    for rows in actual.values():
        for row in rows:
            for field in STATE_FIELDS.intersection(row):
                value=normalized(row[field])
                if value and value not in known_states[field]:diagnostic['review_required'].append(f'未识别但可能等价的状态：{field}={value}；需依据公开口径复核')
    related=defaultdict(set)
    # These two public parameter tables have six data rows each in this rubric's
    # generator, independent of seed/period/scale. They are valid common policy
    # support, not extra mandatory transaction origins.
    parameter_sources={('账户费用与币种.xlsx',sheet,row) for sheet in ('费用币种','账户范围') for row in range(3,9)}
    id_fields={'合同号','应收编号','收款号','分配号','退款申请号','结算流水号','原结算流水号','批次号','银行流水号'}
    for records in raw_sources.values():
        for record in records:
            locs=locations(record['_sources'])
            for field in id_fields:
                if record.get(field):related[str(record[field])].update(locs)
    index_cells={r['_source_ref']:r.get('来源定位') for r in actual['来源索引'] if '_source_ref' in r}
    ref_source_groups=defaultdict(list);got_source_groups=defaultdict(list)
    for r in expected['来源索引']:ref_source_groups[(r['类型'],r['业务编号'])].append(r)
    for r in actual['来源索引']:got_source_groups[(normalized(r.get('类型')),normalized(r.get('业务编号')))].append(r)
    valid_duplicate_groups=set()
    for group,rs in ref_source_groups.items():
        if len(rs)>1 and all(r['处理状态'] in ('纳入','重复导出') for r in rs):
            got=got_source_groups[group];counts=Counter(normalized(r.get('处理状态')) for r in got)
            if len(got)==len(rs) and counts=={'纳入':1,'重复导出':len(rs)-1}:valid_duplicate_groups.add(group)
    indexes={};scope={}
    for name,rows in expected.items():
        key=KEYS[name];counter=Counter(normalized(r.get(key)) for r in actual[name]);refkeys={normalized(r[key]) for r in rows}
        # Problem ids are descriptive combinations, not private synthetic labels.
        if name=='待补与差异':
            key='_problem_key'
            for r in rows:r[key]='|'.join(normalized(r.get(h)) for h in ('对象类型','业务编号','问题类别'))
            for r in actual[name]:r[key]='|'.join(normalized(r.get(h)) for h in ('对象类型','业务编号','问题类别'))
            counter=Counter(normalized(r.get(key)) for r in actual[name]);refkeys={normalized(r[key]) for r in rows}
        if name=='来源索引':
            for r in actual[name]:
                try:
                    loc=locations(r.get(key));r[key]=';'.join(f'{f}|{s}|行{n}' for f,s,n in sorted(loc))
                except ValueError as e:diagnostic['review_required'].append(str(e))
            counter=Counter(normalized(r.get(key)) for r in actual[name])
        denom=len(refkeys)+sum(n for k,n in counter.items() if k not in refkeys)+sum(n-1 for k,n in counter.items() if k in refkeys and n>1)
        scope[name]=len(refkeys.intersection(counter))/denom if denom else 0
        indexes[name]={normalized(r.get(key)):r for r in actual[name] if counter[normalized(r.get(key))]==1}
    diagnostic['raw_ratios']['scope']=scope
    pools={k:[0,0] for k in ('matching','amounts','uncertainty','traceability')}
    domains={k:defaultdict(lambda:[0,0]) for k in pools}
    domain_map={
      'matching':{'合同余额':'合同身份','收款核对':'合同身份','分配核对':'显式分配','退款核对':'退款引用','结算银行核对':'账户批次','银行待认领':'账户批次','币种汇总':'账户批次','待补与差异':'账户批次','来源索引':'账户批次'},
      'amounts':{'合同余额':'核销与余额','收款核对':'核销与余额','分配核对':'核销与余额','退款核对':'退款净额','结算银行核对':'银行与费用','银行待认领':'银行与费用','待补与差异':'银行与费用','币种汇总':'逐币种汇总'},
      'uncertainty':{'收款核对':'收款未知与零额','合同余额':'核销用途与不适用','分配核对':'核销用途与不适用','退款核对':'退款当前状态','结算银行核对':'银行与差异边界','银行待认领':'银行与差异边界','待补与差异':'银行与差异边界','来源索引':'银行与差异边界'},
      'traceability':{'合同余额':'合同分配','分配核对':'合同分配','收款核对':'收款','退款核对':'退款与银行','结算银行核对':'退款与银行','银行待认领':'退款与银行','待补与差异':'退款与银行','来源索引':'全量来源索引'}}
    for name,rows in expected.items():
        key='_problem_key' if name=='待补与差异' else KEYS[name]
        for expected_row in rows:
            pk=normalized(expected_row[key]);row=indexes[name].get(pk,{})
            for field,want in expected_row.items():
                if field.startswith('_') or field==key or field in TEXT_EXCLUDE:continue
                if field in STATE_FIELDS or (field not in {'币种','合同号','客户号','账户','渠道','资金用途','分期号','收款号','应收编号','退款申请号','批次号','类型','业务编号','对象类型'} and normalized(want) in ('待确认','不适用')):group='uncertainty'
                elif isinstance(want,(float,int)):group='amounts'
                else:group='matching'
                pools[group][1]+=1;value=row.get(field)
                if group=='amounts':
                    gotnum=number(value);ok=gotnum is not None and abs(gotnum-Decimal(str(want)))<=Decimal('0.0000001')
                else:
                    ok=normalized(value)==normalized(want)
                    if group=='uncertainty' and normalized(want) in ('待确认','不适用') and normalized(value) not in ('','待确认','不适用') and number(value) is None:
                        diagnostic['review_required'].append(f'非数值标记可能等价：{name}/{field}={value}；需按公开语义复核')
                    if name=='来源索引' and field=='处理状态' and (expected_row['类型'],expected_row['业务编号']) in valid_duplicate_groups:
                        ok=normalized(value) in ('纳入','重复导出')
                pools[group][0]+=int(ok)
                domain=domain_map[group][name];domains[group][domain][0]+=int(ok);domains[group][domain][1]+=1
                if not ok and len(diagnostic['mismatches'])<24:diagnostic['mismatches'].append({'table':name,'key':pk,'field':field,'expected':want,'actual':value,'group':group})
            if '来源' in expected_row:
                pools['traceability'][1]+=1
                try:
                    wantloc=locations(expected_row['来源']);gotloc=locations(row.get('来源'),index_cells)
                    # Additional source support is valid only if it is related to this object.
                    allowed=set(wantloc)
                    allowed.update(parameter_sources)
                    for f in id_fields|{'业务编号'}:
                        if expected_row.get(f):allowed.update(related[str(expected_row[f])])
                    ok=wantloc.issubset(gotloc) and gotloc.issubset(allowed)
                except ValueError as e:
                    ok=False;diagnostic['review_required'].append(str(e))
                pools['traceability'][0]+=int(ok)
                domain=domain_map['traceability'][name];domains['traceability'][domain][0]+=int(ok);domains['traceability'][domain][1]+=1
            elif name=='来源索引':
                pools['traceability'][1]+=1
                ok=all(normalized(row.get(f))==normalized(expected_row[f]) for f in ('类型','业务编号'))
                ok=ok and (normalized(row.get('处理状态'))==normalized(expected_row['处理状态']) or ((expected_row['类型'],expected_row['业务编号']) in valid_duplicate_groups and normalized(row.get('处理状态')) in ('纳入','重复导出')))
                pools['traceability'][0]+=int(ok);domains['traceability']['全量来源索引'][0]+=int(ok);domains['traceability']['全量来源索引'][1]+=1
    for group,(good,total) in pools.items():diagnostic['raw_ratios'][group]=good/total if total else 0
    # Business-domain bands prevent thousands of easy ledger rows diluting refund-chain failures.
    output['scope']=1.0 if all(v==1 for v in scope.values()) else .5 if all(v>0 for v in scope.values()) else 0.0
    for key in ('matching','amounts','uncertainty'):
        if len(domains[key])!=4:raise ValueError('评分业务域配置异常：'+key)
        output[key]=sum(good==total for good,total in domains[key].values())/4
    trace_ratios=[good/total for good,total in domains['traceability'].values()]
    output['traceability']=1.0 if all(v==1 for v in trace_ratios) else .5 if all(v>=.8 for v in trace_ratios) else 0.0
    diagnostic['business_domains']={k:{d:{'correct':v[0],'required':v[1],'complete':v[0]==v[1]} for d,v in ds.items()} for k,ds in domains.items()}
    output['overall_score']=sum(output[k]*w for k,w in WEIGHTS.items())/80
    # Preserve candidate prose as evidence, with no invented tool receipts or author check claims.
    problems=actual['待补与差异'];counts=Counter(normalized(r.get('问题类别')) for r in problems)
    summary={'candidate_file':str(candidate.name),'complete_summary':True,'summary':actual['币种汇总'],
             'difference_counts':dict(counts),'detail_sample_complete':False,
             'detail_samples':[{k:v for k,v in r.items() if k not in ('来源',)} for r in problems[:12]],
             'record_counts':{k:len(v) for k,v in actual.items()},'rule_checks':{k:output[k] for k in WEIGHTS}}
    prose={'candidate_file':candidate.name,'complete':True,'sheets':narrative,
           'evidence_boundary':'核对记录中的自述不替代真实操作及回执；缺轨迹时scope_execution与validation不可判定。'}
    for filename,obj in [('汇总与差异.json',summary),('分析与验收.json',prose)]:
        content=json.dumps(obj,ensure_ascii=False,indent=2,default=str)
        if len(content)>19000:
            diagnostic['review_required'].append(filename+'超出展示预算，需要补完整正文后Judge，不可依据截断片段扣分')
            obj={'complete':False,'review_required':'证据超过19,000字符，评测侧需拆分完整材料后再Judge','candidate_file':candidate.name}
            content=json.dumps(obj,ensure_ascii=False,indent=2)
        (evidence/filename).write_text(content,encoding='utf-8')
    diagnostic['review_required']=sorted(set(diagnostic['review_required']))[:30]
    if diagnostic['review_required']:diagnostic['status']='indeterminate';diagnostic['score_use']='分数仅为规则诊断，不得汇成正式成绩，先完成等价/读取复核。'
    output['diagnostics']=diagnostic
    (evidence/'规则核验.json').write_text(json.dumps(diagnostic,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    if diagnostic['review_required']:raise RuntimeError('评测不可判定，禁止形成正式综合分：'+'；'.join(diagnostic['review_required'][:3]))
    return output
```

## LLM Judge Rubric

仅依据实际Prompt采用的资料与公开规则，不把参考措辞或生成器作为候选义务。评分证据JSON由规则读取候选文件生成，不是候选实际核对行为。先确认汇总与分析正文完整、真实工具轨迹可见；不完整材料须补采。缺证时在notes明确写明对应key不可判定；协议若强制数字可返回0占位，但此占位不是有效零分，不得汇成总分。只在完整证据证明未满足时给有效0。不得从结果正确倒推实际读取/验收，不索取内部思考。

### Criterion 1: 实际处理范围与源文件保护 (key: scope_execution, weight: 4)

公开依据为Prompt路径、原材料不改和口径范围。两个证据单元：①实际操作对象及输出绑定本次指定账户、期间、全部sheet/币种区块，不用别包输入或跳过分片；②实际另存指定结果、全过程未改原始资料。首尾哈希相同不能独自证明全过程只读，实际读取部分和明确承认未读取部分需如实评价。完整轨迹可证明未执行某单元；轨迹不可得则该项不可判定。

**Score 1.0**: 两个单元均有真实操作及产物证据支持。
**Score 0.5**: 完整证据支持恰好一个单元完成，另一单元明确未满足。
**Score 0.0**: 完整证据支持两个单元均未满足，或未交付且未处理本题范围；不包括缺轨迹占位。

### Criterion 2: 差异解释与核查优先事项 (key: analysis, weight: 10)

四个公开分析单元：合同/分期/用途边界与待分配影响；退款冲正与重付当前状态；跨期、手续费与银行差异区别和优先核查；逐币种守恒与未知边界。每单元要有正确记录/汇总支持、引用可定位、结论不超出证据；可提出有条件的核查建议，不把未知原因当事实。不要求照抄参考或固定例子数量。单元符合才计完成，完整正文可确认缺失/错误才不计。

**Score 1.0**: 四个单元均完成。
**Score 0.75**: 三个单元完成。
**Score 0.5**: 两个单元完成。
**Score 0.25**: 一个单元完成。
**Score 0.0**: 四个单元均未完成；仅可在分析正文及相关证据完整时作此判定。

### Criterion 3: 实际核对与验收记录 (key: validation, weight: 6)

四领域来自口径末段：跨sheet/区块/原始明细覆盖；显式匹配及合同分期用途边界；逐币种核销、退款链、服务费用、银行归属金额守恒；差异分类及分析依据。某域需有真实执行的核对对象、方法、结果/回执，并在产物记录实际范围、发现及证据位置；发现错误并如实保留可满足核对要求，实际有效抽查只证明相应抽查范围，不自动外推全量。候选一份核对文件/一句已完成或纯计算代码不证明实际验收。该项缺真实轨迹时不可判定。

**Score 1.0**: 四领域均实际核对并如实记录；证据支持公开要求的范围。
**Score 0.75**: 三领域有充分核对证据，另一领域明确未满足。
**Score 0.5**: 两领域有充分核对证据，其他领域明确未满足。
**Score 0.25**: 一领域有充分核对证据，其他领域明确未满足。
**Score 0.0**: 完整轨迹及产物证明没有一领域满足核对要求；缺轨迹不作有效0。

## Workspace Path

workspace/general_e2e/03_Data_Analysis_task/03_Data_Analysis_task_010_contract_escrow_refund_reconciliation

## Skills

## Env

## Warmup
