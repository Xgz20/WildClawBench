---
id: 03_Data_Analysis_task_008_payment_channel_settlement_reserves
name: Payment Channel Settlement and Rolling Reserve Reconciliation
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
    - path: 评分证据/分析与核对.json
      role: grader_generated_evidence
    - path: 评分证据/汇总与差异.json
      role: grader_generated_evidence
    - path: 评分证据/规则诊断.json
      role: grader_generated_evidence
---

## Prompt

帮我核一下这期各商户的支付渠道结算和保证金余额。资料在 `/tmp_workspace/`，请按里面的《对账口径》整理交易匹配、批次和到账差异、保证金滚存及账户汇总，保留来源、待补材料和实际核对记录，并说明需要优先跟进的问题。原始文件不要改，结果放到 `/tmp_workspace/results/渠道结算对账.xlsx`。

## Expected Behavior

按公开范围核对模拟商户甲、乙、丙在云付、海桥两个渠道的CNY和USD原币结算。覆盖多sheet、重复标题和多币种区块，区分重复导出、取消、零额、缺凭证及缺引用。内部交易通过明确引用匹配拆分结算明细，批次净额组合逐笔费用、保证金扣留/释放、退款冲正及跨期银行到账；缺引用保留未知。保证金从独立计算余额逐批滚存，不能把有误的申报余额当下一批正确起点。按《对账口径》交付九张表及四方面有据分析，实际核对公开要求的四类对象。

## Grading Criteria

评分版本2026-10-14-v1。总分100，规则80、Judge20。依据仅为Prompt采用的公开《对账口径》，不以私有参考实现、能力目录、作者偏好或指定工具增加要求。所有独立检查点只用二/三/五档；无额外排版、脚本或图表评分。C1拆分为产物全量覆盖与实际处理证据，C2—C7不改变S3-02证据要求。

| 检查点 | 对象 | 分值 | 公开口径出处 | 证据 |
|---|---|---:|---|---|
| `automated.coverage` | C1产物范围：账户、批次、交易、银行、差异、源行全量覆盖 | 10 | 第1、2、4节 | 产物 |
| `automated.association` | C2分散事实关联：内部交易到拆分结算明细、银行到批次的确定关联 | 20 | 第2、4节 | 产物 |
| `automated.amounts` | C3金额组合规则：逐笔费率、冲正退款、跨期及保证金滚存和账户汇总 | 28 | 第3、4节 | 产物 |
| `automated.unknowns` | C4未知与差异边界：零、未知、不适用及待补凭证清单不混淆 | 12 | 第2、3、4节 | 产物 |
| `automated.traceability` | C5来源与金额守恒：完整双方来源及拆分、批次和账户金额守恒 | 10 | 第3、4节 | 产物 |
| `llm_judge.actual_scope` | C1实际处理范围：实际处理公开账户、工作表、区块与期间边界 | 4 | 第1、2、4、5节及Prompt | 轨迹+产物 |
| `llm_judge.analysis` | C6差异分析：四项分析有数据支持，原因和补件优先级有边界 | 8 | 第5节 | 产物+回答 |
| `llm_judge.acceptance` | C7实际核对：范围、关联、金额、差异与分析四个核对域 | 8 | 第5节 | 轨迹+产物 |

规则组分为Σ(权重×检查点得分)/80；Judge组分为Σ(权重×检查点得分)/20。题目分=80×规则组分+20×Judge组分。各项正式分只采用预先声明档位，诊断比例和数量不参与额外计分。

各规则项按自己的业务域定档，不把数千笔正常交易当作可掩盖保证金整域错误的分母。域内原始比例只供诊断与选档，正式分只取五档。条件从高档往低档依次判定，使用未舍入比例；缺少一条必须交付记录不能四舍五入满分。表内主键重复时该对象内容不构成唯一可验结果。所有比较分母来自公开要求应有对象，不取“已交且正确”小样本为分母。

- coverage：账户汇总、批次对账、保证金滚存、交易匹配、银行分配、差异及补件、来源索引七表等权。各表r=命中不同应有键数/(应有键数+额外键数+多出的重复行数)。辅助列与辅助sheet不当作额外业务对象。
- association：逐内部流水的账户/渠道/币种/批次/全部结算明细集合，以及逐银行流水账户/渠道/币种/归属批次，按全部应有字段等权比较。缺引用只有未知符合公开规则，不用隐藏真值填入批次。
- amounts：账户、批次、保证金、内部交易、银行五表的公开数值字段按应有数值字段数量计算r。每笔四舍五入后相加，币种分开，符号、期间和保证金公式一并适用；“实列结算金额”未知/不适用在unknowns检查，不转成0。
- unknowns：状态字段正确率、未知/不适用字段正确率、差异补件对象与账户币种及影响金额完整率三者等权。第三项为差异字段正确率×差异对象覆盖率；缺凭证补件文字合理性归analysis检查，允许等价建议，不以关键词评分。
- traceability：交易、银行、批次、保证金、差异、来源索引六类来源记录完整率等权后，与交付自身的拆分/批次/账户金额守恒正确率等权。来源索引还核对记录类型、业务编号和批次去向；补充真实且相关来源允许，同对象源行或原始文件单元格定位均接受。守恒独立比较交易对批次四项金额与账户对批次七项汇总，不能凭有源地址掩盖配平错误。

**本题业务档位（按从高到低判断）**：

- coverage：七表全部完整为1；至少五表完整为0.75；至少三表覆盖≥50%为0.5；其余有正确对象为0.25；无为0。
- association：内部到结算、银行到批次分别计算域内字段正确率。两域全对为1；两域各≥90%为0.75；两域各≥50%或一域完整为0.5；其余有正确关联字段为0.25；无为0。
- amounts：逐笔费率及实列金额、批次净结算（不含银行到账）、银行金额及跨期到账、保证金滚存、账户汇总共五域，各自按应有字段算正确率。五域全对为1；四域完整或三域完整且其余域各≥75%为0.75；至少三域各≥50%为0.5；其余有正确数值为0.25；无为0。
- unknowns：状态、未知/不适用值、差异清单三个域均完整正确为1；三域各≥80%为0.75；至少两域各≥50%为0.5；其余有正确处理为0.25；无为0。
- traceability：来源完整性与金额守恒两域均全对为1；两域各≥90%为0.75；两域各≥50%，或一域≥90%且另一域大于0为0.5；其余至少一域有正确证据为0.25；无为0。

评分读取数值的0.005001容差只容纳2位小数表达，不改变业务判断差异是否超0.01的公开容差。接受行列/表序、同义表头、数值文本、来源集合顺序、直接行号或单元格定位等价表达；未能安全辨认的等价命名、无法取得公式计算值进入评测方复核，不自动计业务0。缺交付或损坏交付可判相应项未满足；GT缺失或损坏是评分异常，必须阻止正式合分。

Judge证据由规则在评分副本事后提取，三个文件每个低于20,000字符，含完整性字段。正文过长或轨迹缺失须补采；不得把评分器提取当作候选验收。必要项不可判定时不输出正式综合分，也不能删项重归一。

能力映射版本capabilities-2026-09-23-v1：actual_scope→intent_understanding#3，association→state_awareness#3，amounts→reasoning_and_decision_making#1，acceptance→result_evaluation#1；其他项为业务验收。映射预算60，工具调用未覆盖；能力总分=100×(4×actual_scope+20×association+28×amounts+8×acceptance)/60，各维按其权重独立归一。仅追加本题映射不表示旧七维报告器已实现五维汇总。

## Automated Checks

```python
"""正式题目的完整嵌入评分器来源；只读取候选与私有GT，不执行候选脚本。"""
from pathlib import Path
from collections import defaultdict, Counter
from decimal import Decimal, InvalidOperation
import json, re, unicodedata
from openpyxl import load_workbook

WEIGHTS = {'coverage':10,'association':20,'amounts':28,'unknowns':12,'traceability':10}
KEYS = {'账户汇总':['商户账户','渠道','币种'],'批次对账':['批次编号'],'保证金滚存':['批次编号'],'交易匹配':['内部流水号'],'银行分配':['银行流水号'],'差异及补件':['对象类型','对象编号','问题类型'],'来源索引':['来源定位']}
TABLE_ALIASES={'来源对照':'来源索引','待补凭证清单':'差异及补件','交易关联':'交易匹配','批次汇总':'批次对账'}
FIELD_ALIASES={'内部交易号':'内部流水号','结算批次':'批次编号','账户':'商户账户','源位置':'来源定位'}
STATE_ALIASES={'待确认':'未知','待核实':'未知','N/A':'不适用','n/a':'不适用','已对上':'已匹配','匹配成功':'已匹配','已到账':'已收齐','已齐全':'已提供','已排除':'不适用'}
NUMBER_FIELDS={
 '账户汇总':['批次数','内部净额','应计手续费','应扣保证金','释放保证金','应结净额','已分配到账','未分配到账','跨期到账','期初保证金','期末保证金'],
 '批次对账':['内部净额','应计手续费','实列手续费','手续费差额','应扣保证金','释放保证金','应结净额','申报净结算','结算差额','截至观察日到账','跨期到账','到账差额'],
 '保证金滚存':['应有期初保证金','本批扣留','本批释放','应有期末保证金','申报期末保证金','滚存差额'],
 '交易匹配':['内部净额','应计手续费','应扣保证金','实列结算金额'],
 '银行分配':['到账金额']}

def textnorm(value):
    return unicodedata.normalize('NFKC',str(value if value is not None else '')).strip()

def state(value):
    value=textnorm(value)
    return STATE_ALIASES.get(value,value)

def number(value):
    try:
        result=Decimal(textnorm(value).replace(',',''))
        return result if result.is_finite() else None
    except (InvalidOperation,ValueError):return None

def same(a,b):
    if isinstance(b,(float,int)):
        av=number(a)
        return av is not None and abs(av-Decimal(str(b)))<=Decimal('0.005001')
    return state(a)==state(b)

def splitset(value):
    if isinstance(value,list):return {textnorm(x) for x in value if textnorm(x)}
    return {state(x) for x in re.split(r'[;,；，\n]+',textnorm(value)) if textnorm(x)}

def source_token(value):
    value=textnorm(value).replace('\\','/')
    parts=value.split('|')
    if len(parts)==3 and parts[2].isdigit():return (Path(parts[0]).name,parts[1].strip("'"),int(parts[2]))
    m=re.fullmatch(r'(.+\.xlsx)#(.+)!\$?[A-Z]+\$?(\d+)',value,re.I)
    if m:return (Path(m[1]).name,m[2].strip("'"),int(m[3]))
    return ('无法识别',value,0)

def sources(value):
    return {source_token(x) for x in re.split(r'[;；\n]+',textnorm(value)) if textnorm(x)}

def key_for(table,row):
    return tuple(source_token(row.get(k)) if k=='来源定位' else state(row.get(k)) for k in KEYS[table])

def read_tables(path,expected):
    values=load_workbook(path,data_only=True,read_only=True)
    formulas=load_workbook(path,data_only=False,read_only=True)
    result={};positions={};review=[]
    for sheet in values:
        name=TABLE_ALIASES.get(textnorm(sheet.title),textnorm(sheet.title))
        rows=list(sheet.iter_rows(values_only=True))
        if name not in expected:
            candidates=[];business_like=False
            for row in rows[:25]:
                labels={FIELD_ALIASES.get(textnorm(c),textnorm(c)) for c in row if c is not None}
                for candidate,records in expected.items():
                    signature=set(records[0]);overlap=len(signature&labels)
                    business_like=business_like or overlap>=3
                    if overlap/len(signature)>=.8 and set(KEYS.get(candidate,[]))<=labels:
                        candidates.append((overlap/len(signature),candidate))
            if candidates:
                best=max(v for v,t in candidates);matches={t for v,t in candidates if v==best}
                if len(matches)==1:name=matches.pop()
                else:review.append(f'{sheet.title}:同义表名无法唯一识别，需复核');continue
            elif business_like:
                review.append(f'{sheet.title}:疑似等价业务表但无法安全识别，需复核');continue
            else:continue
        if name in result:review.append(f'{sheet.title}:多张表可能属于同一逻辑表，需合并复核');continue
        schema=list(expected[name][0])
        found=None
        for i,row in enumerate(rows[:25]):
            cols={FIELD_ALIASES.get(textnorm(c),textnorm(c)):j for j,c in enumerate(row) if c is not None}
            if len(set(schema)&set(cols))>=min(3,len(schema)):
                found=(i,cols);break
        if not found:
            review.append(f'{sheet.title}:无法辨认表头；可能是等价表述，需复核');continue
        i,cols=found
        required=KEYS.get(name,[])
        if any(k not in cols for k in required):review.append(f'{sheet.title}:关键字段无法辨认');continue
        # 未知同义列不直接当业务错误；正式人工复核后才可合分。
        missing=[c for c in schema if c not in cols]
        if missing:review.append(f'{sheet.title}:待核同义或缺失列 {missing}')
        parsed=[]
        for ri,row in enumerate(rows[i+1:],start=i+2):
            if not any(v is not None for v in row):continue
            obj={c:row[j] if j<len(row) else None for c,j in cols.items()}
            parsed.append(obj);positions.setdefault(name,[]).append(ri)
        result[name]=parsed
        fs=formulas[sheet.title]
        for row in fs.iter_rows():
            for cell in row:
                if cell.data_type=='f' and values[sheet.title].cell(cell.row,cell.column).value is None:
                    review.append(f'{sheet.title}!{cell.coordinate}:公式无可读取缓存，需评测方只读求值')
                    break
            if len(review)>30:break
    values.close();formulas.close()
    return result,positions,review

def grade(transcript:list, workspace_path:str)->dict:
    root=Path(workspace_path)
    standard=root/'gt'/'标准记录集合.json'
    if not standard.is_file():raise RuntimeError('评分异常：私有标准记录集合缺失，不能记候选0分')
    try:package=json.loads(standard.read_text(encoding='utf-8'));expected=package['tables']
    except Exception as exc:raise RuntimeError('评分异常：私有GT损坏') from exc
    if not all(expected.get(k) for k in KEYS):raise RuntimeError('评分异常：私有GT不完整')
    output=root/'results'/'渠道结算对账.xlsx'
    result={k:0.0 for k in WEIGHTS};diag={'status':'ok','counts':{},'mismatch_examples':{},'review_required':[]}
    actual={};positions={}
    if output.exists():
        try:actual,positions,review=read_tables(output,expected)
        except Exception as exc:
            diag['candidate_read_error']=f'{type(exc).__name__}: {exc}'
            review=[]
        if review:diag['review_required']=review;diag['status']='needs_evaluator_review'
    else:diag['candidate_read_error']='缺少公开要求的交付工作簿'
    expmaps={t:{key_for(t,r):r for r in expected[t]} for t in KEYS}
    actmaps={};coverage=[]
    for t in KEYS:
        groups=defaultdict(list)
        for r in actual.get(t,[]):groups[key_for(t,r)].append(r)
        actmaps[t]={k:v[0] for k,v in groups.items() if len(v)==1}
        matched=len(set(expmaps[t])&set(groups));extra=len(set(groups)-set(expmaps[t]));duplicates=sum(len(v)-1 for v in groups.values())
        denom=len(expmaps[t])+extra+duplicates
        r=matched/denom if denom else 1
        coverage.append(r)
        diag['counts'][t]={'expected':len(expmaps[t]),'actual_rows':len(actual.get(t,[])),'matched_keys':matched,'extra_keys':extra,'duplicate_rows':duplicates}
    coverage_raw=sum(coverage)/len(coverage)
    complete_tables=sum(r==1 for r in coverage)
    result['coverage']=1.0 if complete_tables==7 else .75 if complete_tables>=5 else .5 if sum(r>=.5 for r in coverage)>=3 else .25 if any(r>0 for r in coverage) else 0.0
    def cells(check,table_fields,cmp=same,condition=lambda value:True):
        passed=total=0;examples=[]
        for t,fields in table_fields.items():
            for key,er in expmaps[t].items():
                ar=actmaps[t].get(key,{})
                for field in fields:
                    if not condition(er[field]):continue
                    total+=1
                    ok=field in ar and cmp(ar.get(field),er[field])
                    passed+=ok
                    if not ok and len(examples)<4:examples.append({'表':t,'对象':str(key),'字段':field,'期望':er[field],'实际':ar.get(field)})
        raw=passed/total if total else 0
        diag['mismatch_examples'][check]=examples
        diag[check]={'passed':passed,'total':total,'raw_ratio':raw}
        return raw
    association_fields={'交易匹配':['商户账户','渠道','币种','批次编号','结算明细集合'],'银行分配':['商户账户','渠道','币种','归属批次']}
    def association_cmp(a,b):return splitset(a)==splitset(b)
    arat=[cells('association_'+t,{t:fields},association_cmp) for t,fields in association_fields.items()]
    result['association']=1.0 if all(r==1 for r in arat) else .75 if min(arat)>=.9 else .5 if min(arat)>=.5 or max(arat)==1 else .25 if max(arat)>0 else 0.0
    amount_domains={
       '逐笔费率':{'交易匹配':NUMBER_FIELDS['交易匹配']},
       '批次净结算':{'批次对账':['内部净额','应计手续费','实列手续费','手续费差额','应扣保证金','释放保证金','应结净额','申报净结算','结算差额']},
       '银行与跨期':{'银行分配':['到账金额'],'批次对账':['截至观察日到账','跨期到账','到账差额']},
       '保证金滚存':{'保证金滚存':NUMBER_FIELDS['保证金滚存']},
       '账户汇总':{'账户汇总':NUMBER_FIELDS['账户汇总']}}
    nrat=[cells('amounts_'+label,fields,condition=lambda x:isinstance(x,(int,float))) for label,fields in amount_domains.items()]
    full=sum(r==1 for r in nrat)
    result['amounts']=1.0 if full==5 else .75 if full>=4 or (min(nrat)>=.75 and full>=3) else .5 if sum(r>=.5 for r in nrat)>=3 else .25 if max(nrat)>0 else 0.0
    unknown_fields={'交易匹配':['匹配状态','凭证状态'],'银行分配':['期间归属','匹配状态'],'批次对账':['批次状态'],'来源索引':['处理结果']}
    semantic=cells('unknown_states',unknown_fields)
    nons=cells('non_numeric_values',{'交易匹配':['实列结算金额','结算明细集合'],'银行分配':['归属批次']},condition=lambda x:state(x) in ['未知','不适用'])
    gapfields={ '差异及补件':['商户账户','币种','影响金额'] }
    gaps=cells('gap_register',gapfields)
    # 未知/零/不适用，逐项差异集合及状态分别等权，避免正常记录掩盖缺口。
    gapkeys=coverage[list(KEYS).index('差异及补件')]
    urat=[semantic,nons,gaps*gapkeys]
    result['unknowns']=1.0 if min(urat)==1 else .75 if min(urat)>=.8 else .5 if sum(r>=.5 for r in urat)>=2 else .25 if max(urat)>0 else 0.0
    location_owner={source_token(s['来源定位']):(s['记录类型'],s['业务编号'],s['归属批次']) for s in package['raw_sources']}
    location_record={source_token(s['来源定位']):s['_record'] for s in package['raw_sources']}
    raw_batches={r['批次编号']:r for r in package['raw_unique']['批次结算']}
    raw_transactions={r['内部流水号']:r for r in package['raw_unique']['内部流水']}
    def related_source(locator,owners,table,record):
        if locator not in location_owner:return False
        kind,rid,batch=location_owner[locator]
        if (kind,rid) in owners:return True
        extra=location_record[locator]
        if table=='交易匹配':
            tx=raw_transactions.get(record['内部流水号'],{})
            return (kind=='批次结算' and rid==record['批次编号']) or (kind=='费用币种' and extra.get('渠道')==record['渠道']) or (kind=='内部流水' and rid==tx.get('原交易号') and bool(rid))
        is_batch=table in ['批次对账','保证金滚存'] or (table=='差异及补件' and record.get('对象类型')=='批次')
        if is_batch:
            bid=record.get('批次编号',record.get('对象编号'));current=raw_batches.get(bid,{})
            if kind=='费用币种':return extra.get('渠道')==current.get('渠道')
            same_account=all(extra.get(k)==current.get(k) for k in ['商户账户','渠道','币种'])
            if not same_account:return False
            if kind=='期初保证金' or batch==bid:return True
            if table=='保证金滚存' and kind=='批次结算':return extra.get('批次截止日','')<=current.get('批次截止日','')
        return False
    trace_passed=trace_total=0;trace_examples=[]
    for t in ['交易匹配','银行分配','批次对账','保证金滚存','差异及补件','来源索引']:
        tp=tt=0
        for key,er in expmaps[t].items():
            ar=actmaps[t].get(key,{});tt+=1
            es=sources(er['来源定位']);aset=sources(ar.get('来源定位'))
            if any(s[0]=='无法识别' and '.xlsx' in s[1] for s in aset):
                diag['review_required'].append(f'{t}:{key}:源定位可能为未支持等价格式，需复核')
                diag['status']='needs_evaluator_review'
            expected_owners={location_owner[s][:2] for s in es if s in location_owner}
            valid_extra=all(related_source(s,expected_owners,t,er) for s in aset-es)
            ok=bool(aset) and es<=aset and valid_extra
            if t=='来源索引':ok=ok and all(same(ar.get(f),er[f]) for f in ['记录类型','业务编号','归属批次'])
            tp+=ok
            if not ok and len(trace_examples)<10:trace_examples.append({'表':t,'对象':str(key),'缺失位置数':len(es-aset),'错误或无关补充':not valid_extra})
        trace_passed+=tp/max(1,tt);trace_total+=1
    trace_raw=trace_passed/trace_total
    # 交付自身的金额拆分和汇总守恒；不依赖GT金额，错误不可被正确来源掩盖。
    conservation=[]
    def n(v):return number(v)
    for bid,br in actmaps['批次对账'].items():
        tx=[r for r in actual.get('交易匹配',[]) if state(r.get('批次编号'))==bid[0]]
        banks=[r for r in actual.get('银行分配',[]) if state(r.get('归属批次'))==bid[0]]
        for dest,rows,field in [('内部净额',tx,'内部净额'),('应计手续费',tx,'应计手续费'),('应扣保证金',tx,'应扣保证金'),('截至观察日到账',banks,'到账金额')]:
            vals=[n(r.get(field)) for r in rows];target=n(br.get(dest));conservation.append(target is not None and all(v is not None for v in vals) and abs(sum(vals,Decimal(0))-target)<=Decimal('.005001'))
    for ar in actual.get('账户汇总',[]):
        bs=[r for r in actual.get('批次对账',[]) if all(state(r.get(k))==state(ar.get(k)) for k in ['商户账户','渠道','币种'])]
        for af,bf in [('内部净额','内部净额'),('应计手续费','应计手续费'),('应扣保证金','应扣保证金'),('释放保证金','释放保证金'),('应结净额','应结净额'),('已分配到账','截至观察日到账'),('跨期到账','跨期到账')]:
            vals=[n(r.get(bf)) for r in bs];target=n(ar.get(af));conservation.append(target is not None and all(v is not None for v in vals) and abs(sum(vals,Decimal(0))-target)<=Decimal('.005001'))
    cr=sum(conservation)/len(conservation) if conservation else 0
    result['traceability']=1.0 if trace_raw==cr==1 else .75 if min(trace_raw,cr)>=.9 else .5 if min(trace_raw,cr)>=.5 or (max(trace_raw,cr)>=.9 and min(trace_raw,cr)>0) else .25 if max(trace_raw,cr)>0 else 0.0
    diag['coverage']={'raw_ratio':coverage_raw};diag['traceability']={'source_ratio':trace_raw,'conservation_ratio':cr,'source_errors':trace_examples}
    diag['诊断完整性']={'计数和原始比例':'完整','错误实例':'每个域最多4条，来源最多10条；仅诊断抽样，不替代完整正文或全量比较'}
    # 只传文本及原币汇总，明确完整性；不把几千行塞进文本采集上限。
    evidence=root/'评分证据';evidence.mkdir(exist_ok=True)
    def save_evidence(filename,obj):
        body=json.dumps(obj,ensure_ascii=False,indent=2,default=str)
        if len(body)>19000:raise RuntimeError('评分异常：Judge证据超过单文件安全预算')
        (evidence/filename).write_text(body,encoding='utf-8')
    semantic_evidence={'候选文件':'results/渠道结算对账.xlsx','提取说明':'评分后只读提取。候选分析和核对记录完整展示；该文件不是候选自检证据。','分析说明':actual.get('分析说明',[]),'核对记录':actual.get('核对记录',[]),'完整性':{'分析说明行数':len(actual.get('分析说明',[])),'核对记录行数':len(actual.get('核对记录',[])),'截断':False},'来源行':{k:positions.get(k,[]) for k in ['分析说明','核对记录']}}
    summary_evidence={'账户汇总':actual.get('账户汇总',[]),'候选差异分类数量':dict(Counter(state(r.get('问题类型')) for r in actual.get('差异及补件',[]))),'候选差异原币金额':{},'说明':'仅为候选内容提取；正确性须结合规则诊断，跨币种不得相加。','截断':False}
    grouped=defaultdict(Decimal)
    for r in actual.get('差异及补件',[]):
        val=number(r.get('影响金额'))
        if val is not None:grouped[(state(r.get('问题类型')),state(r.get('币种')))]+=val
    summary_evidence['候选差异原币金额']={'|'.join(k):str(v) for k,v in grouped.items()}
    if len(json.dumps(semantic_evidence,ensure_ascii=False))>18500:
        # 正确但长文不能被静默截断；留清楚不可判定原因以便评测方补全文本。
        semantic_evidence={'完整性':{'截断':True,'原因':'分析或核对文本超过安全预算，需评测方分段补采原文件正文后Judge；不能给候选0分'},'候选文件':'results/渠道结算对账.xlsx'}
        diag['review_required'].append('分析/核对文本需分段补采');diag['status']='needs_evaluator_review'
    save_evidence('分析与核对.json',semantic_evidence)
    save_evidence('汇总与差异.json',summary_evidence)
    save_evidence('规则诊断.json',diag)
    result['diagnostics']=diag
    if diag['review_required']:
        result['evaluation_status']='needs_evaluator_review'
        # 禁止缺证时输出能被误读为正式合分的overall_score。
        raise RuntimeError('评测方需复核后才能合分：'+ '; '.join(diag['review_required'][:5]))
    result['overall_score']=sum(WEIGHTS[k]*result[k] for k in WEIGHTS)/80
    return result

```

## LLM Judge Rubric

只评以下三项。先检查证据完整性，结合真实工具调用及返回与候选产物；需要轨迹的项不能凭过程自述推定完成。评测侧轨迹/正文缺失标明不可判定，不作为有效0，不合成正式总分。完整轨迹证明未做才可给有效0。允许Excel、人工或程序等价处理与核对，不要求指定工具和独立脚本。输出协议为`{"scores":{"actual_scope":数字,"analysis":数字,"acceptance":数字},"notes":"逐项证据与限制"}`；仅使用声明档位。若数字协议迫使0占位，notes必须明确不可判定并阻止正式合分。

### Criterion 1: 实际账户与期间范围 (key: actual_scope, weight: 4)

**Score 1.0**: 真实读取/处理及返回证明使用本次公开全部工作簿和账户、渠道、币种区块，期间/观察窗及重复、排除边界与交付一致；原始文件保留，输出另存结果目录。无需逐文件单独工具调用，只要处理范围和返回足以确认。
**Score 0.5**: 有真实读取及交付证据表明正确处理本期多数账户与币种，但某些sheet/区块/期间边界漏查或输出保护范围未完全确认；不能仅由正确产物推断读取覆盖。
**Score 0.0**: 完整轨迹显示处理错目录/错期/错对象，或只有极少范围且没有形成可用本期处理，或违反明确源文件保留约束。评测侧轨迹缺失不属于本档。

### Criterion 2: 差异原因与补件优先级 (key: analysis, weight: 8)

以公开四项分析主题为四个独立可成立单元：①按原币给资金到账和未分配范围；②费用差额依据及逐笔舍入规则；③保证金逐批滚存问题及影响；④有根据的补件优先级并保留未知原因。每单元须有可回查且正确的数据依据，解释不超出记录，引用汇总表/差异对象及数值均可。表达顺序、篇幅和建议措辞不固定。不得把缺引用说成已证实拖欠、把差额总和当实际损失、跨币种硬加。某单元重大错误或无依据则该单元不成立；同一错误只影响实际相关单元。

**Score 1.0**: 四个单元全部成立。
**Score 0.75**: 三个单元成立。
**Score 0.5**: 两个单元成立。
**Score 0.25**: 一个单元成立。
**Score 0.0**: 没有单元成立，或缺少分析。若正文未采集属于不可判定。

### Criterion 3: 实际验收覆盖 (key: acceptance, weight: 8)

公开四个核对域是①所有sheet/币种区块及重复排除；②内部到结算拆分和银行到批次匹配；③费用、净结算、保证金及原币汇总守恒；④差异分类、跨期/未知及分析依据。有效核对须在真实工具返回或可验证人工操作中看到对象、方法和核对结果，并有交付核对记录对应范围/发现/证据位置；实际发现未通过且如实披露也可成立，不能把业务正确与验收过程混为一谈。只写计划、只打印数量或结果、只提交已写好的核对结论不能证明完整核对。

**Score 1.0**: 四个核对域都有实际有效核对及记录，范围完整；任何未通过结果如实说明并纳入限制。
**Score 0.5**: 至少一个但未满四个核对域有实际有效核对及记录；部分抽查只能证明实际样本范围，未覆盖域如实区分。
**Score 0.0**: 完整轨迹和交付表明没有任何有效核对及记录，或只有计划/无结果脚本/自述通过。评测侧缺轨迹或回执不是本档。

## Workspace Path

workspace/general_e2e/03_Data_Analysis_task/03_Data_Analysis_task_008_payment_channel_settlement_reserves

## Skills

## Env

## Warmup
