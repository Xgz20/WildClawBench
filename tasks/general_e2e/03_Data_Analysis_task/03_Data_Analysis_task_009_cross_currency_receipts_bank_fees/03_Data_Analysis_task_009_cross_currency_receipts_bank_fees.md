---
id: 03_Data_Analysis_task_009_cross_currency_receipts_bank_fees
name: Cross-Currency Receipts and Bank Fee Reconciliation
category: data-analysis
timeout_seconds: 7200
modality: pure-text
difficulty: L4
grading_type: hybrid
grading_weights:
  automated: 0.80
  llm_judge: 0.20
tags:
  - custom
  - general_e2e
  - finance
judge_evidence:
  required:
    - path: 评分证据/分析与分类.json
      role: grader_generated_evidence
    - path: 评分证据/验收与缺口.json
      role: grader_generated_evidence
    - path: 评分证据/规则与参考摘要.json
      role: grader_generated_evidence
---

## Prompt

帮我核对资料所列月份的出口业务跨币种回款，资料在 `/tmp_workspace/`。按里面的口径整理回款、换汇费用和银行到账，给出对账明细、差异汇总及补证建议，保留双方来源和实际核对记录。原始材料不要改，结果放到 `/tmp_workspace/results/跨币种回款对账.xlsx`。

## Expected Behavior

采用公开《对账口径.md》及费用、币种、账户和锁汇表。覆盖指定期间、全部账户及所有sheet币种区块。识别同编号重复导出和非明细，按明确引用连接应收、收款、结算批次和银行记录；保留一对多、部分回款、负额冲正和跨期到账。逐结算行扣原币手续费，按逐笔/批次/原币直收分别处理换汇，再扣目标币固定费。缺锁汇时保留目标币未知，缺引用时不按金额强配。分别提交六张结构化表、分析说明和验收记录，来源及原币/目标币拆分汇总可复算。这里只采用模拟规则，不作现实税法判断。

## Grading Criteria

版本：2026-10-14-v1。主题：财务对账；场景S3-02。总分100，规则80、裁判20。全部计分义务仅来自Prompt已采用的公开《对账口径.md》，GT用于核对可确定事实，不新增义务。

| 检查点 | 内容与方式 | 分值 | 公开出处 |
|---|---|---:|---|
| automated.C1a | 全部有效对象和原始来源覆盖，规则 | 12 | 口径第1、4节，六张结构化表范围和唯一键 |
| llm_judge.C1b | 实际读取及处理指定账户、期间和资料，轨迹与产物 | 4 | Prompt资料/输出位置；口径第1、2节 |
| automated.C2 | 应收、回款、结算及银行允许匹配集合，规则 | 18 | 口径第2节和第4节关联字段 |
| automated.C3 | 扣费、换汇舍入、到账期间与数值汇总，规则 | 28 | 口径第3节和第4节数值字段 |
| automated.C4 | 缺证、未知、零、不适用、未匹配及排除状态，规则 | 10 | 口径第1—4节缺失语义及待补凭证 |
| automated.C5 | 双方来源完整、拆分与汇总守恒，规则 | 12 | 口径第3、4节来源与守恒 |
| llm_judge.C6 | 四个分析问题证据充分、限定未知原因，裁判 | 8 | 口径第4节分析说明 |
| llm_judge.C7 | 实际核对覆盖四类对象，轨迹与产物 | 8 | 口径第4节实际核对和验收记录 |

自动点最终均为五档0/0.25/0.5/0.75/1。C1a、C2、C5按原始比例分档：r=0得0，0<r<0.5得0.25，0.5≤r<0.75得0.5，0.75≤r<1得0.75，r=1得1，使用未舍入比例。C3和C4按下述业务领域完成情况分别定档，不由正常行总量稀释关键错误。原始计数仅作诊断。规则组overall_score=Σ(点分值×档位)/80。裁判组=Σ(点分值×档位)/20；题目分=80×规则组+20×裁判组。

C1a分别对六表计算命中的不同应有键数/(应有键数+额外键数+多出的重复行数+缺键行数)，六表等权。有效辅助字段/辅助表不算额外对象。待补凭证以对象类别、对象编号、问题类型组成实际键，汇总以账户、原币、目标币、状态组成实际键，不因事项编号的等价重命名失分。

C2以公开要求的标识、账户、币种、日期、换汇方式和编号集合的应有字段为分母；缺行或重复键不能提供唯一可核对值。C3对六域各自要求全部可确定字段正确：原币扣费及净额，逐笔换汇，批次换汇，原币直收，目标币固定费及应到账，到账期间与应收核销/分类汇总。完成6域得1，4—5域得0.75，2—3域得0.5，1域得0.25，0域得0。未知值不纳入C3数字判断。C4分四域：未知金额及缺锁汇状态，零额与不适用，缺引用与匹配/回款状态，重复导出/期间外及补证。每域所有相应状态和标记正确得一个证据单元，最终得分=完成域数/4。补证材料和影响说明自动仅核查非空，内容依据由C6综合核对。来源索引同编号任一原始出现可为保留，其他为重复；不得因选择另一份完全相同导出而失分。

C5为来源记录完整正确率占2/3、候选内部金额守恒率占1/3。前者检查各表全部来源字段，接受相关且真实的额外来源；后者核对每批原币收款/费用/净额=结算行之和、本期+跨期=已到账，以及分类汇总=相应批次已知值之和。数值错误只在C3与实际违反守恒的独立条件上反映，守恒不直接与GT数字再比一次。

接受行列/sheet顺序、中文无歧义同义标题、原生日期或ISO日期、数值或可取得结果的公式、集合顺序及分号/换行/JSON数组表示。来源行号和覆盖同一行的单元格范围均接受。自动字典未能识别但可能等价的内容须复核，不以字典缺词直接判业务失败。数值读取容差为1e-7，仅吸收浮点序列化，不改变业务零差额口径。公式无缓存需要评测方补齐只读求值证据，不得执行候选脚本来补交付。GT/公开输入缺失或损坏属于评分异常，候选缺交付或损坏属于业务无证据。必要复核未完成不出正式综合分。

只有真实轨迹可用于C1b和C7。作者参考中的验收记录、评分器提取JSON及正确产物都不证明候选做过验收。无轨迹或关键内容缺失记不可判定；框架需数字时用0占位且notes明确无效，禁止据此合成正式总分或删除后重归一。

能力映射依据capabilities-2026-09-23-v1：C1b→intent_understanding#3(4)，C2→state_awareness#3(18)，C3→reasoning_and_decision_making#1(28)，C7→result_evaluation#1(8)。能力预算58；其余业务验收不映射。能力总分=100×(4C1b+18C2+28C3+8C7)/58，各维按实际分值归一。工具调用未覆盖；任一必要映射缺证则不合成能力总分。

## Automated Checks

```python
"""完整嵌入正式题目的规则评分器；只读取 workspace_path 内候选和 gt。"""
from pathlib import Path
from collections import defaultdict, Counter
from decimal import Decimal, InvalidOperation
from datetime import datetime, date
import json, re, unicodedata
from openpyxl import load_workbook

WEIGHTS = {'C1a':12,'C2':18,'C3':28,'C4':10,'C5':12}
FIVE = [0,0.25,0.5,0.75,1]
CORE = ['批次对账','结算明细','应收核销','待补凭证','分类汇总','来源索引']
REL = {
 '批次对账':['结算日期','渠道','收款账户','原币','目标币','换汇方式','锁汇编号','结算行号集合','银行流水号集合'],
 '结算明细':['收款流水号','应收单号','批次号','原币','目标币'],
 '应收核销':['原币','收款流水号集合'],
 '分类汇总':['收款账户','原币','目标币'],
 '待补凭证':['对象类别','对象编号'],
 '来源索引':['对象类别','记录编号','关联对象'],
}
STATE = {'批次对账':['对账状态'],'结算明细':['匹配状态'],'应收核销':['回款状态'],'待补凭证':['问题类型'],'分类汇总':['对账状态'],'来源索引':['处理状态']}
ALIASES = {'银行账户':'收款账户','应到金额':'应到账金额','实到金额':'已到账金额','差异金额':'差额','原始来源':'来源','来源定位':'来源','结算号':'结算行号','银行流水集合':'银行流水号集合','批次核对':'批次对账','核对记录':'验收记录','结论说明':'分析说明'}
TOKENS = {'待确认':'未知','未确认':'未知','无法确认':'未知','n/a':'不适用','na':'不适用','N/A':'不适用','无适用':'不适用','已匹配对平':'已对平','已结清回款':'已结清'}

class EvaluationReviewRequired(RuntimeError):
    pass

def norm(v):
    if isinstance(v,(date,datetime)):return v.strftime('%Y-%m-%d')
    if v is None:return ''
    return unicodedata.normalize('NFKC',str(v)).strip()

def token(v):return TOKENS.get(norm(v),norm(v))
def five(r):return 1.0 if r==1 else 0.75 if r>=0.75 else 0.5 if r>=0.5 else 0.25 if r>0 else 0.0
def number(v):
    if isinstance(v,bool) or v is None:return None
    try:
        n=Decimal(norm(v).replace(',',''))
        return n if n.is_finite() else None
    except InvalidOperation:return None

def setparts(v):
    if isinstance(v,list):return {norm(x) for x in v}
    s=norm(v)
    if s.startswith('['):
        try:return {norm(x) for x in json.loads(s)}
        except (ValueError,TypeError):pass
    return {x.strip() for x in re.split(r'[;；\n]',s) if x.strip()}

def locparts(v):
    result=set()
    for p in setparts(v):
        p=p.replace('！','|').replace('!','|').replace('｜','|').replace("'",'').strip()
        bits=p.split('|')
        if len(bits)==3:
            fn,sh,ref=bits
            m=re.fullmatch(r'\$?[A-Z]*\$?(\d+)(?::\$?[A-Z]*\$?(\d+))?',ref.strip(),re.I)
            if m:
                a=int(m[1]);b=int(m[2] or a)
                if b-a<=20000:
                    result.update(f'{Path(fn).name}|{sh}|{i}' for i in range(a,b+1));continue
        result.add(p)
    return result

def same(a,b,field='',row=None):
    nb=number(b)
    if nb is not None:
        na=number(a);return na is not None and abs(na-nb)<=Decimal('0.0000001')
    if '集合' in field:return setparts(a)==setparts(b)
    if token(b)=='未知' and norm(a)=='':
        context=' '.join(norm(v) for v in (row or {}).values())
        return any(x in context for x in ['缺锁汇','未知','缺收款','缺应收'])
    return token(a)==token(b)

def read_candidate(path,headers):
    wb=load_workbook(path,data_only=True,read_only=True);tables={};evidence={};unrecognized=[];formula_checks=[];source_index_locations={}
    try:
        for ws in wb.worksheets:
            name=ALIASES.get(ws.title,ws.title)
            expected=set(headers[name]) if name in headers else set();hr=None;cols={};data=[];raw=[];plausible=False
            for rn,values in enumerate(ws.iter_rows(values_only=True),1):
                values=list(values);labels=[ALIASES.get(norm(v),norm(v)) for v in values]
                if hr is None:
                    if name not in headers:
                        signatures=[(len(set(labels)&set(hh))/len(hh),t) for t,hh in headers.items() if len(set(labels)&set(hh))>=min(3,len(hh)) and hh[0] in labels]
                        best=max((s for s,t in signatures),default=0);matches=[t for s,t in signatures if s==best]
                        if len(matches)==1:name=matches[0];expected=set(headers[name])
                        elif len(matches)>1:raise EvaluationReviewRequired('可能等价但无法唯一识别逻辑表：'+ws.title)
                        elif any(len(set(labels)&set(hh))>=2 for hh in headers.values()):plausible=True
                    if len(set(labels)&expected)>=min(3,len(expected)):
                        if not expected:continue
                        unknown_headers=set(labels)-expected-{''}
                        if expected-set(labels) and unknown_headers:
                            raise EvaluationReviewRequired('字段可能同义但自动字典不能确认：'+ws.title+'；未识别='+','.join(sorted(unknown_headers)))
                        hr=rn;cols={i:k for i,k in enumerate(labels) if k in expected}
                    continue
                if not any(v is not None for v in values):continue
                if len(set(labels)&expected)>=min(3,len(expected)):continue
                row={k:values[i] if i<len(values) else None for i,k in cols.items()};row['_row']=rn;data.append(row)
                if name=='来源索引':
                    from openpyxl.utils.cell import get_column_letter
                    for ci,h in cols.items():
                        if h=='来源':source_index_locations[(ws.title,get_column_letter(ci+1),rn)]=row.get('来源')
                formula_checks.extend((ws.title,rn,i+1) for i,k in cols.items() if (i>=len(values) or values[i] is None))
                if name in ('分析说明','验收记录','分类汇总'):
                    raw.append({'sheet':ws.title,'row':rn,'values':{k:v for k,v in row.items() if k!='_row'}})
            if hr is None:
                if plausible:unrecognized.append(ws.title)
                continue
            tables.setdefault(name,[]).extend(data)
            if name in ('分析说明','验收记录','分类汇总'):evidence.setdefault(name,[]).extend(raw)
    finally:wb.close()
    if unrecognized:raise EvaluationReviewRequired('候选结构可能等价但无法安全识别，需按公开规则人工复核：'+','.join(unrecognized))
    # 来源索引引用是公开允许的等价表示。只展开其来源列，不执行动态表达式。
    for tab,rows in tables.items():
        if tab=='来源索引':continue
        for row in rows:
            for field,value in list(row.items()):
                if '来源' not in field:continue
                expanded=[]
                for part in setparts(value):
                    m=re.fullmatch(r"'?([^'!]+)'?!\$?([A-Z]+)\$?(\d+)(?::\$?([A-Z]+)\$?(\d+))?",part,re.I)
                    if m and (m[1],m[2].upper(),int(m[3])) in source_index_locations:
                        if m[4] and m[4].upper()!=m[2].upper():raise EvaluationReviewRequired('来源索引引用跨列，需复核：'+part)
                        for rr in range(int(m[3]),int(m[5] or m[3])+1):
                            vv=source_index_locations.get((m[1],m[2].upper(),rr))
                            if vv is None:raise EvaluationReviewRequired('来源索引引用包含未识别行：'+part)
                            expanded.append(norm(vv))
                    else:expanded.append(part)
                row[field]=';'.join(expanded)
    fw=load_workbook(path,data_only=False,read_only=False)
    try:
        for sn,r,c in formula_checks:
            if fw[sn].cell(r,c).data_type=='f':raise EvaluationReviewRequired(f'公式缓存缺失，需取得只读求值证据：{sn}!R{r}C{c}')
    finally:fw.close()
    return tables,evidence,unrecognized

def index(rows,key):
    groups=defaultdict(list)
    for row in rows:
        if key=='来源':
            parts=locparts(row.get(key));k=next(iter(parts)) if len(parts)==1 else norm(row.get(key))
        elif key=='事项编号':k=':'.join(norm(row.get(f)) for f in ('对象类别','对象编号','问题类型')) if all(norm(row.get(f)) for f in ('对象类别','对象编号','问题类型')) else ''
        elif key=='汇总键':k='|'.join(norm(row.get(f)) for f in ('收款账户','原币','目标币','对账状态')) if all(norm(row.get(f)) for f in ('收款账户','原币','目标币','对账状态')) else ''
        else:k=norm(row.get(key))
        groups[k].append(row)
    return groups

def grade(transcript: list, workspace_path: str) -> dict:
    root=Path(workspace_path);gp=root/'gt'/'标准答案.json'
    if not gp.is_file():raise FileNotFoundError('评测异常：缺少私有标准答案.json')
    gt=json.loads(gp.read_text(encoding='utf-8'));expected=gt['tables'];headers=gt['headers'];keys=gt['keys']
    if gt.get('schema_version')!='fx-reconcile-v1' or any(not expected.get(t) for t in CORE):raise ValueError('评测异常：GT损坏或缺必需表')
    for filename in ('内部应收与收款.xlsx','支付结算与批次.xlsx','费用币种与锁汇.xlsx','银行到账记录.xlsx','对账口径.md'):
        if not (root/filename).is_file():raise FileNotFoundError('评测异常：公开输入缺失 '+filename)
    candidate=root/'results'/'跨币种回款对账.xlsx';diagnostics={'version':'2026-10-14-v1','candidate':str(candidate),'ratios':{},'mismatches':{},'requires_review':[],'transcript_available':bool(transcript),'formal_total_available':False,'formal_total_reason':'C1b、C6、C7由原Rubric裁判；本函数不伪造Judge或真实验收证据'}
    actual={};ev={};error=None
    if candidate.is_file():
        try:actual,ev,unrecognized=read_candidate(candidate,headers)
        except EvaluationReviewRequired:raise
        except Exception as e:error=f'候选工作簿不可读取：{type(e).__name__}: {e}'
    else:error='候选缺少约定工作簿'
    if error:diagnostics['candidate_error']=error
    else:
        if unrecognized:diagnostics['requires_review'].append('表头可能等价但未自动识别：'+','.join(unrecognized))
    expind={t:index(expected[t],keys[t]) for t in CORE};actind={t:index(actual.get(t,[]),keys[t]) for t in CORE}
    retained_counts=Counter((x.get('对象类别'),x.get('记录编号')) for x in actual.get('来源索引',[]) if token(x.get('处理状态'))=='保留')
    coverage=[]
    for t in CORE:
        exp=set(expind[t]);ac=actind[t];unique=set(ac)-{''};extra=len(unique-exp);dups=sum(max(0,len(v)-1) for k,v in ac.items() if k);blank=len(ac.get('',[]));hit=len(unique&exp);den=len(exp)+extra+dups+blank
        coverage.append(hit/den if den else 1);diagnostics.setdefault('coverage',{})[t]={'expected':len(exp),'unique_hit':hit,'extra':extra,'duplicate_rows':dups,'blank_keys':blank}
    diagnostics['ratios']['C1a']=sum(coverage)/len(coverage)
    checks=defaultdict(lambda:[0,0]);errors=defaultdict(list);numeric_domains=defaultdict(lambda:[0,0]);state_domains=defaultdict(lambda:[0,0])
    def add(cat,ok,t,k,f,want,got):
        checks[cat][1]+=1;checks[cat][0]+=int(bool(ok))
        if not ok and len(errors[cat])<18:errors[cat].append({'table':t,'key':k,'field':f,'expected':want,'actual':got})
    for t in CORE:
        for k,ers in expind[t].items():
            e=ers[0];ars=actind[t].get(k,[]);a=ars[0] if len(ars)==1 else {}
            for f in REL.get(t,[]):add('C2',same(a.get(f),e.get(f),f,a),t,k,f,e.get(f),a.get(f))
            for f in headers[t]:
                v=e.get(f)
                if number(v) is not None:
                    ok=same(a.get(f),v,f,a);add('C3',ok,t,k,f,v,a.get(f))
                    mode=e.get('换汇方式')
                    if t=='结算明细' and f=='逐笔换汇金额':domain='逐笔换汇'
                    elif t=='批次对账' and f in ('锁汇价','换汇毛额'):domain={'逐笔换汇':'逐笔换汇','批次换汇':'批次换汇','原币直收':'原币直收'}[mode]
                    elif t=='批次对账' and f in ('固定银行费','应到账金额'):domain='目标币固定费及应到账'
                    elif t=='结算明细' or (t=='批次对账' and f in ('原币收款合计','原币费用合计','原币净额')):domain='原币扣费及净额'
                    else:domain='到账期间与核销汇总'
                    numeric_domains[domain][0]+=int(ok);numeric_domains[domain][1]+=1
                elif f in STATE.get(t,[]) or (v in ('未知','不适用','缺失') and f not in REL.get(t,[]) and '来源' not in f):
                    ok=same(a.get(f),v,f,a)
                    # 任意重复行可作保留，但每个编号必须恰好一个保留。
                    if t=='来源索引' and f=='处理状态' and v in ('保留','重复导出'):
                        etype=e['对象类别'];eid=e['记录编号']
                        ok=token(a.get(f)) in ('保留','重复导出') and retained_counts[(etype,eid)]==1
                    add('C4',ok,t,k,f,v,a.get(f))
                    domain='未知金额' if v=='未知' or v=='缺锁汇凭证' else '零额与不适用' if v in ('不适用','确认零额') else '重复期间外及补证' if t in ('来源索引','待补凭证') else '缺引用与匹配状态'
                    state_domains[domain][0]+=int(ok);state_domains[domain][1]+=1
                if '来源' in f:
                    target=locparts(v);given=locparts(a.get(f));ok=target<=given
                    # 附加来源必须真实且与当前源记录集合相关；仅接受相同记录的多次出现。
                    if target-{'不适用','缺失'}:
                        expected_idx=expind['来源索引'];related_locs=set().union(*(locparts(vv) for ff,vv in e.items() if '来源' in ff));related_ids={(expected_idx[x][0]['对象类别'],expected_idx[x][0]['记录编号']) for x in related_locs if x in expected_idx}
                        ok=ok and all(x in expected_idx and (expected_idx[x][0]['对象类别'],expected_idx[x][0]['记录编号']) in related_ids for x in given)
                    else:ok=target==given
                    add('C5_sources',ok,t,k,f,v,a.get(f))
    # 待补材料和影响说明接受业务同义表述，保留完整正文交Judge；禁止仅为空。
    for k,ers in expind['待补凭证'].items():
        ars=actind['待补凭证'].get(k,[]);a=ars[0] if len(ars)==1 else {}
        for f in ('需补材料','影响范围'):
            ok=bool(norm(a.get(f)));add('C4',ok, '待补凭证',k,f,'明确非空业务说明',a.get(f));state_domains['重复期间外及补证'][0]+=int(ok);state_domains['重复期间外及补证'][1]+=1
    # C5守恒检查只验证候选内部拆分合计，不重复按GT金额判错。
    details=actual.get('结算明细',[]);batches=actual.get('批次对账',[])
    for k,ers in expind['批次对账'].items():
        ars=actind['批次对账'].get(k,[]);a=ars[0] if len(ars)==1 else {};ds=[d for d in details if norm(d.get('批次号'))==k]
        for bf,df in [('原币收款合计','结算原币'),('原币费用合计','原币费用'),('原币净额','原币净额')]:
            vals=[number(d.get(df)) for d in ds];av=number(a.get(bf));ok=bool(ds) and all(v is not None for v in vals) and av is not None and abs(sum(vals)-av)<=Decimal('0.0000001')
            add('C5_balance',ok,'批次对账',k,bf,'结算行分项之和',a.get(bf))
        cur=number(a.get('本期到账金额'));cross=number(a.get('跨期到账金额'));amt=number(a.get('已到账金额'));ok=all(v is not None for v in (cur,cross,amt)) and abs(cur+cross-amt)<=Decimal('0.0000001')
        add('C5_balance',ok,'批次对账',k,'本期+跨期=已到账','守恒',None)
    for k,ers in expind['分类汇总'].items():
        ars=actind['分类汇总'].get(k,[]);a=ars[0] if len(ars)==1 else {};bs=[b for b in batches if '|'.join(norm(b.get(f)) for f in ('收款账户','原币','目标币','对账状态'))==k]
        for sf,bf in [('原币收款合计','原币收款合计'),('原币费用合计','原币费用合计'),('已确认应到账','应到账金额'),('已到账金额','已到账金额'),('已确认差额','差额')]:
            vals=[number(b.get(bf)) for b in bs];total=sum(v for v in vals if v is not None);av=number(a.get(sf));ok=bool(bs) and av is not None and abs(total-av)<=Decimal('0.0000001')
            add('C5_balance',ok,'分类汇总',k,sf,'相应批次已知金额之和',a.get(sf))
    for cat in ('C2','C3','C4','C5_sources','C5_balance'):
        yes,total=checks[cat];diagnostics['ratios'][cat]=yes/total if total else 0;diagnostics.setdefault('counts',{})[cat]={'correct':yes,'total':total}
    diagnostics['ratios']['C5']=(2*diagnostics['ratios']['C5_sources']+diagnostics['ratios']['C5_balance'])/3
    diagnostics['mismatches']=dict(errors)
    result={k:five(diagnostics['ratios'][k]) for k in WEIGHTS};result['overall_score']=sum(result[k]*w for k,w in WEIGHTS.items())/80;result['diagnostics']=diagnostics
    # 关键币种/舍入域各自判断，数千正常行不能稀释一种错误换汇路线。
    passed_numeric=sum(good==total and total>0 for good,total in numeric_domains.values())
    result['C3']=1.0 if passed_numeric==6 else 0.75 if passed_numeric>=4 else 0.5 if passed_numeric>=2 else 0.25 if passed_numeric==1 else 0.0
    passed_state=sum(good==total and total>0 for good,total in state_domains.values())
    result['C4']=passed_state/4
    diagnostics['business_domains']={'C3':dict(numeric_domains),'C3_completed':passed_numeric,'C4':dict(state_domains),'C4_completed':passed_state}
    result['overall_score']=sum(result[k]*w for k,w in WEIGHTS.items())/80
    ed=root/'评分证据';ed.mkdir(exist_ok=True)
    # 只提取候选正文；超预算显式标识，不能把截断当候选遗漏。
    def evidence_file(name,payload):
        wrapper={'source':'候选工作簿提取，不构成Agent执行证据','candidate':str(candidate),'complete':True,'truncated':False,'data':payload}
        text=json.dumps(wrapper,ensure_ascii=False,default=str,separators=(',',':'))
        if len(text)>18000:
            wrapper={'source':wrapper['source'],'candidate':str(candidate),'complete':False,'truncated':True,'reason':'超过单文件18000字符作者预算；需回读原工作簿，未补齐前该内容不可判定','preview':text[:15000]};text=json.dumps(wrapper,ensure_ascii=False,default=str,separators=(',',':'))
        (ed/name).write_text(text,encoding='utf-8')
    evidence_file('分析与分类.json',{'分析说明':ev.get('分析说明',[]),'分类汇总':ev.get('分类汇总',[]),'coverage':diagnostics.get('coverage',{}),'candidate_error':error})
    evidence_file('验收与缺口.json',{'验收记录':ev.get('验收记录',[]),'待补凭证':[r for r in actual.get('待补凭证',[])][:35],'待补凭证总行数':len(actual.get('待补凭证',[])),'缺口清单仅前35行':len(actual.get('待补凭证',[]))>35,'必须结合完整原件':'差异分析涉及其他缺口时必须补读对应行，不能把抽取未展示当作未交付','transcript_available':bool(transcript)})
    evidence_file('规则与参考摘要.json',{'rule_scores':{k:result[k] for k in WEIGHTS},'ratios':diagnostics['ratios'],'counts':diagnostics.get('counts',{}),'requires_review':diagnostics['requires_review'],'expected_summary':expected['分类汇总'],'expected_issue_counts':dict(Counter(r['问题类型'] for r in expected['待补凭证'])),'score_status':'仅规则组；C1b/C7无真实轨迹不可判定，不得合成正式总分'})
    return result

```

## LLM Judge Rubric

只按Prompt采用的公开口径判分。读取规则提取的候选正文、分类汇总、验收记录和参考摘要，并结合真实轨迹。提取文件标记不完整/截断时回读原件；未能补齐则受影响项不可判定，不能把未展示当缺交付。待补凭证只抽取前35条，完整清单以原工作簿为准。不得把评分后的提取当候选验收。每项允许0/0.25/0.5/0.75/1，输出scores使用key C1b、C6、C7，notes逐项写公开依据、候选位置、可确认范围及判定状态。

### Criterion 1: 实际范围与处理对象 (key: C1b, weight: 4)

四个证据单元：真实操作绑定本包公开资料；实际覆盖内部/结算/锁汇/银行四类工作簿；实际范围覆盖三个指定账户及全部币种区块；实际银行观察窗和业务期间与口径一致且输出另存到约定位置。需用轨迹的操作对象/参数/返回和产物交叉支持，单纯自述或最终数据正确不够。完整轨迹证明没有做到才计未满足；评测侧轨迹缺失则不可判定。

**Score 1.0**: 四个单元均有充分证据。
**Score 0.75**: 三个单元有充分证据，完整其余证据确认一项未满足。
**Score 0.5**: 两个单元有充分证据，完整其余证据确认未满足。
**Score 0.25**: 一个单元有充分证据，完整其余证据确认未满足。
**Score 0.0**: 完整证据确认四项均未满足；若是关键轨迹缺失，仅协议占位并在notes标明不可判定，不能合成正式总分。

### Criterion 2: 差异分析与补证建议 (key: C6, weight: 8)

四个单元分别对应口径第4节：按账户及原/目标币分组解释状态与批次数，引用正确结果；解释逐笔/批次舍入及原币手续费与目标币固定费而未混币；区分跨期与金额差异、不给未证实原因下结论；按缺凭证影响范围提出具体补证优先级并保留未知。每单元须有相应事实或字段依据，正文正确的等价表述可通过，参考措辞不是要求。

**Score 1.0**: 四个单元全部有完整正确依据。
**Score 0.75**: 三个单元有完整正确依据。
**Score 0.5**: 两个单元有完整正确依据。
**Score 0.25**: 一个单元有完整正确依据。
**Score 0.0**: 交付确实未回答或四个单元均无成立依据；评测方未提取正文则不可判定，不作为有效0分。

### Criterion 3: 实际验收覆盖 (key: C7, weight: 8)

四个领域：跨sheet/币种区块和去重范围；允许主键关联及缺引用去向；费用换汇与原币/目标币金额守恒；差异归属、分析依据及未知限制。每领域须真实可观察操作及回执能支持验收记录中的对象、范围、发现和结论。允许Excel复核、程序检查、人工抽样等价路线，抽样须准确说明范围；单独读取、写出成功、正确结果或泛称检查通过不是充分证据。发现问题并如实保留可以满足核对要求，不要求伪造全部通过。

**Score 1.0**: 四个领域均有足够真实核对证据且记录与范围一致。
**Score 0.75**: 三个领域满足，完整其余证据确认未覆盖。
**Score 0.5**: 两个领域满足，完整其余证据确认未覆盖。
**Score 0.25**: 一个领域满足，完整其余证据确认未覆盖。
**Score 0.0**: 完整轨迹确认没有有效核对；缺轨迹/回执或提取不全则仅协议占位，notes注明不可判定，不得合成正式总分。

## Workspace Path

workspace/general_e2e/03_Data_Analysis_task/03_Data_Analysis_task_009_cross_currency_receipts_bank_fees

## Skills

## Env

## Warmup
