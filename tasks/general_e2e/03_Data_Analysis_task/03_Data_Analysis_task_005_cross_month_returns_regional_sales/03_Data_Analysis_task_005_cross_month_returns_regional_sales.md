---
id: 03_Data_Analysis_task_005_cross_month_returns_regional_sales
name: Cross-Month Returns and Regional Sales Review
category: data-analysis
timeout_seconds: 7200
modality: pure-text
difficulty: L3
grading_type: hybrid
grading_weights:
  automated: 0.68
  llm_judge: 0.32
tags:
  - custom
  - general_e2e
  - business
judge_evidence:
  required:
    - path: 评分证据/
      role: grader_generated_evidence
---

## Prompt

帮我做一下8—9月的区域销售复盘，重点看看跨月退货后，两个月的净销售规模和区域、渠道结构怎么变。材料在 `/tmp_workspace/`，按其中的口径和交付说明整理明细、汇总、图表及分析，保留来源、缺口和实际核对记录，原始文件不要改。结果放到 `/tmp_workspace/results/区域销售复盘.xlsx`。

## Expected Behavior

采用《销售复盘口径与交付说明.docx》的公开范围与交付契约。分析2026年8—9月订单，观察截止2026年10月5日18:00（含），全部时间为北京时间。此题以同一截止下的原单月净销重述与退款发生月区分为特色，不考查协销分摊、毛利或实际税法。

1. 覆盖三地订单两个月份、全部退款申请月sheet和客户名册；隐藏sheet及隐藏行属于范围，历史留样不属于范围；识别合并标题、重复字段行、小计、页尾说明与重复业务导出。
2. 按订单行ID、退款ID、客户ID正确关联，保留同名不同ID，按稳定ID去重而不丢失重复出现位置。多次部分退款先以原单对应关系处理，避免重复放大订单额。
3. 数量统一箱与件；金额统一以元计、单价以元/件计，金额与单价均显示两位小数，按实付折扣逐行四舍五入；只有截止内已生效退款计入原单月净销，发生额另按生效月份。取消、撤销、待审批、截止后一秒和真实零额各按公开规则处理。
4. 交付八张表、两图与有据的比较说明，渠道与分层缺失保留待确认，不能根据名称猜补，真实零和不适用不混同；逐笔来源与范围清洗可回查。
5. 实际检查全部sheet范围、ID关联、退款双时间口径与净额守恒、图表和结论，保留执行证据对应的核对记录。工具和实现路线不限。

## Grading Criteria

评分版本：2026-10-14-金额统一元，S3-01，100分。依据仅限本次Prompt和其明确采用的公开《销售复盘口径与交付说明.docx》。私有参考、技能和能力目录不增加候选义务。公开字段名和sheet名是交付接口；允许列/行顺序变化、辅助列、辅助表以及等价的行号或同一行单元格来源。金额容差0.00501元，比例容差0.000051，日期月份按公開格式；公式需可取得实际计算值，评测端不能读取缓存则先补只读求值证据，不能因此自动判业务失败。

| key | 检查点 | 分值 | 证据及公开依据 |
|---|---|---:|---|
| llm_judge.C1 | 实际处理范围覆盖 | 12 | 真实轨迹＋产物；公开第一、二、五、六节：全部指定sheet与区块，排除历史留样及非明细 |
| automated.C2 | 订单退款客户关联 | 16 | 产物；公开三、五节：稳定ID关联、原订单归属，保留同名不同ID |
| automated.C3 | 单位折扣与双时间退款指标 | 30 | 产物；公开三、五节：有效状态、换算、逐行舍入、原单月与生效月、完整组合与分母 |
| automated.C4 | 缺失零额与不适用 | 10 | 产物；公开四、六节：缺渠道/分层、确认零额、不适用及缺口对象 |
| automated.C5 | 来源与清洗可追溯 | 12 | 产物；公开二、五、六节：全源记录处理结果，订单/退款/客户与缺口源位置 |
| llm_judge.C6 | 规模结构变化结论 | 12 | 产物＋最终回答；公开六节四个分析问题及图表要求 |
| llm_judge.C7 | 实际业务验收 | 8 | 真实轨迹＋产物；公开七节四类实际核对与记录 |

规则组预算68分，Judge组预算32分。规则overall_score=Σ规则权重×得分/68；Judge组分=ΣJudge权重×得分/32；题目百分制=68×规则组分+32×Judge组分。规则诊断不参与平均。每项仅用下列预先固定档位；业务单元是判断完成程度的依据，不是新增分项。

C2采用三档。订单—客户关联（订单月份、客户ID/名称、区域）和退款—原单关联（订单行ID、客户ID、区域、订单月份）为两个完整业务单元。每个单元要求全体应有唯一对象和字段正确，无额外、缺失、重复或缺键。两单元通过得1；仅一个通过得0.5；均未完整通过得0。保留每类差异诊断，不将部分错误宣称为全部关联错误。

C3采用五档，四个具有独立使用价值的业务输出单元分别为：订单逐行标准数量及折后/退款/净額；退款逐行生效月、标准额及两种计入金额；月度规模、有效/零额/缺渠道行数、两种退款、环比和缺渠道净额；区域渠道完整组合、金额、订单行数与占比。每单元要求完整应有对象集合及列明数值正确。四个完整通过得1，三个得0.75，两个得0.5，一个得0.25，零个得0。不会以通用正确率或样本数代替业务单元完整性。

C4采用三档。单元一为全部订单的分层/渠道/订单状态/金额语义及全部退款的原状态/截止处理均正确；单元二为全部应有缺口“订单行ID＋缺口类别”对象集合完整且唯一。两个通过得1，仅一个通过得0.5，均未完整通过得0。缺口影响说明和建议由C6语义核验，不机械匹配参考措辞。

C5采用三档。单元一为全部订单的订单与客户来源、全部退款的退款与原订单来源可正确定位，保留全部相关重复出现位置；单元二为全体范围内原始业务源记录处理结果及全部缺口来源正确、完整且唯一。两个通过得1，仅一个通过得0.5，均未完整通过得0。额外非业务区块清洗说明不算多交业务记录；支持文件名|sheet|行号及同一行单元格范围，集合顺序不限。无法安全识别而可能等价的来源表达需人工复核，不把评分器限制当业务错。

缺交付或确实不可读属于相应产物项的业务零分；GT缺失/损坏、评分副本公开材料缺失/变化、公式无可读缓存等属于评分异常或待复核，不产生候选有效零分。轨迹缺失不证明未做；C1/C7不可判定时说明需补证据，不得删除后重归一，不能输出正式总分。当前框架数值占位0仅供协议兼容，notes必须明确不可判定且不当作有效0。

能力遵循 capabilities-2026-09-23-v1 的S3-01原映射：C1→意图理解#3，C2→状态感知#3，C3→推理与决策#1，C7→结果评估#1；C4/C5/C6为业务验收、不映射。映射权重66分，能力总分=100×(12C1+16C2+30C3+8C7)/66。各维按本维权重归一，工具调用未覆盖，不计0。历史map7只记录兼容映射，不宣称原报告器已实现该五维公式。

## Automated Checks

```python
from pathlib import Path
from collections import Counter
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import re
import unicodedata
from zipfile import ZipFile, BadZipFile
from xml.etree import ElementTree
from openpyxl import load_workbook

WEIGHTS = {'C2': 16, 'C3': 30, 'C4': 10, 'C5': 12}
KEYS = {'订单明细':['订单行ID'], '退款明细':['退款ID'], '月度指标':['月份'],
        '区域渠道汇总':['月份','区域','渠道'], '来源与清洗':['来源定位'],
        '缺口表':['订单行ID','缺口类别']}
class EvaluationError(RuntimeError): pass
class ReviewRequired(EvaluationError): pass

def norm(v):
    if v is None: return ''
    if isinstance(v, float) and v.is_integer(): return str(int(v))
    return unicodedata.normalize('NFKC', str(v)).strip()

def value_equal(a,b,field=''):
    if isinstance(b,(int,float)) and not isinstance(b,bool):
        try:
            s=norm(a).replace(',','');val=Decimal(s[:-1])/100 if s.endswith('%') else Decimal(s)
            # Ratios are explicitly required at >=4 decimals; money at 2 decimals.
            tolerance=Decimal('.000051') if field in ['净额环比','月净额占比'] else (Decimal('.000001') if field in ['标准数量','有效订单行数','确认零额行数','缺渠道行数'] else Decimal('.00501'))
            return val.is_finite() and abs(val-Decimal(str(b)))<=tolerance
        except (InvalidOperation,TypeError,ValueError):return False
    if re.fullmatch(r'\d{4}-\d{2}',norm(b)) and hasattr(a,'strftime'):return a.strftime('%Y-%m')==norm(b)
    aliases={'未知':'待确认','未登记':'待确认','已确认零额':'确认零额','有效':'已确认'}
    aa=norm(a);bb=norm(b)
    return aa==bb or (bb in ['待确认','确认零额','已确认'] and aliases.get(aa)==bb)

def source_set(v):
    found=set()
    for token in re.split(r'[;；\n]+',norm(v)):
        if not token:continue
        parts=token.strip().split('|')
        if len(parts)!=3:return None
        row=parts[2].strip().replace('$','')
        # A is the stable business ID column in every supplied raw table. A cell
        # reference must include that identifier; an unrelated blank ZZ cell is
        # not equivalent to the complete record row.
        letters=re.match(r'([A-Za-z]+)',row)
        if letters and letters.group(1).upper()!='A':return None
        match=re.fullmatch(r'(?:[A-Za-z]+)?(\d+)(?::(?:[A-Za-z]+)?\1)?',row)
        if not match:return None
        found.add((parts[0].strip(),parts[1].strip(),int(match.group(1))))
    return found

def read_candidate(path):
    try:
        values=load_workbook(path,data_only=True);formulas=load_workbook(path,data_only=False)
    except (OSError,ValueError,BadZipFile,KeyError,ElementTree.ParseError) as e:
        return {}, {'status':'候选文件无法读取','reason':str(e)}
    tables={};info={'status':'可读取','sheets':[]}
    for ws in values:
        header=[norm(c.value) for c in ws[1]]
        records=[]
        for row in ws.iter_rows(min_row=2):
            if not any(c.value is not None for c in row):continue
            record={header[i]:cell.value for i,cell in enumerate(row) if i<len(header) and header[i]}
            record['_row']=row[0].row
            records.append(record)
            for cell in row:
                if cell.value is None and formulas[ws.title][cell.coordinate].data_type=='f':
                    raise ReviewRequired(f'公式无可读缓存，须补只读求值证据：{ws.title}!{cell.coordinate}')
        tables[ws.title]=records
        info['sheets'].append({'name':ws.title,'rows':len(records),'columns':header,'hidden':ws.sheet_state})
    values.close();formulas.close();return tables,info

def indexed(rows,keys):
    result={};duplicate=set();invalid=0
    for row in rows:
        key=tuple(norm(row.get(k)) for k in keys)
        if any(not v for v in key):invalid+=1;continue
        if key in result:duplicate.add(key)
        result[key]=row
    for key in duplicate:result.pop(key,None)
    return result,duplicate,invalid

def compare(tables,truth,sheet,fields,sources=False):
    expected=truth[sheet];actual=tables.get(sheet,[]);keys=KEYS[sheet]
    if sheet=='来源与清洗':actual=[r for r in actual if norm(r.get('来源类型')) in ['订单','退款','客户']]
    a,dup,bad=indexed(actual,keys);e,_,_=indexed(expected,keys)
    # Source-key syntax may use equivalent A7:M7 versus row 7.
    if sheet=='来源与清洗':
        a={tuple(sorted(source_set(k[0]) or {('INVALID','',0)})):v for k,v in a.items()}
        e={tuple(sorted(source_set(k[0]))):v for k,v in e.items()}
    extra=set(a)-set(e);miss=set(e)-set(a);mismatch=[];correct=0
    for key,row in e.items():
        if key not in a:continue
        good=True
        for f in fields:
            av=a[key].get(f);bv=row.get(f)
            ok=(source_set(av)==source_set(bv) and source_set(av) is not None) if sources else value_equal(av,bv,f)
            if not ok:
                good=False
                if len(mismatch)<12:mismatch.append({'key':list(key),'field':f,'expected':bv,'actual':av})
        if good:correct+=1
    ok=not extra and not miss and not dup and not bad and correct==len(e)
    return ok,{'expected':len(e),'actual':len(actual),'correct':correct,'missing':len(miss),'extra':len(extra),'duplicate_keys':len(dup),'missing_keys':bad,'examples':mismatch}

def write_evidence(base,tables,info,diagnostics,expected):
    folder=base/'评分证据';folder.mkdir(exist_ok=True)
    def save(name,payload,limit=19000):
        text=json.dumps(payload,ensure_ascii=False,indent=2,default=str)
        if len(text)>limit:
            # Never silently truncate; this blocks use of omitted critical material.
            text=json.dumps({'status':'证据超预算，需补充读取','original_characters':len(text),'preview':text[:limit-700],'truncated':True},ensure_ascii=False,indent=2)
        (folder/name).write_text(text,encoding='utf-8')
    save('01_范围与诊断.json',{'candidate':'results/区域销售复盘.xlsx','extracted_after_run':True,'not_agent_acceptance':True,'candidate_info':info,'expected_input_sheets':expected['input_manifest'],'expected_counts':expected['counts'],'diagnostics':diagnostics})
    save('02_汇总指标.json',{'candidate':'results/区域销售复盘.xlsx','tables':{k:tables.get(k,[]) for k in ['月度指标','区域渠道汇总']},'rows_carry_excel_row':True})
    save('03_分析与核对.json',{'candidate':'results/区域销售复盘.xlsx','tables':{k:tables.get(k,[]) for k in ['分析说明','验收记录']},'rows_carry_excel_row':True,'process_evidence':'实际行为须结合真实轨迹；本提取不证明候选执行了核对。'})
    charts=[];path=base/'results'/'区域销售复盘.xlsx'
    if path.exists():
        try:
            with ZipFile(path) as z:
                for filename in z.namelist():
                    if re.fullmatch(r'xl/charts/chart\d+\.xml',filename):
                        root=ElementTree.fromstring(z.read(filename));ns={'c':'http://schemas.openxmlformats.org/drawingml/2006/chart','a':'http://schemas.openxmlformats.org/drawingml/2006/main'}
                        charts.append({'xml':filename,'titles':[e.text for e in root.findall('.//c:title//a:t',ns)],'references':[e.text for e in root.findall('.//c:f',ns)],'cached_values':[e.text for e in root.findall('.//c:pt/c:v',ns)][:120]})
        except (BadZipFile,ElementTree.ParseError):pass
    save('04_图表与缺口.json',{'charts':charts,'limits':'仅提取原生Excel图表绑定与缓存；若候选使用图片图表或其它等价图形，需读取原交付后判断，不因该提取器未识别而计零。','gap_rows':len(tables.get('缺口表',[])),'gap_examples':tables.get('缺口表',[])[:20]})

def grade(transcript:list, workspace_path:str)->dict:
    base=Path(workspace_path);gt=base/'gt'/'标准记录与来源.json';manifest=base/'gt'/'公开输入清单.json'
    if not gt.is_file() or not manifest.is_file():raise EvaluationError('私有GT或公开输入清单缺失；不是候选零分。')
    try:
        expected=json.loads(gt.read_text(encoding='utf-8'));truth=expected['reference'];inputs=json.loads(manifest.read_text(encoding='utf-8'))
        assert all(k in truth and isinstance(truth[k],list) and truth[k] for k in KEYS)
        assert expected['schema_version']==1 and expected['counts']['orders']==len(truth['订单明细'])
    except Exception as exc:raise EvaluationError('私有GT损坏或结构错误') from exc
    for item in inputs:
        p=base/item['path']
        if not p.is_file():raise EvaluationError('评分副本公开材料缺失：'+item['path'])
        if hashlib.sha256(p.read_bytes()).hexdigest()!=item['sha256']:
            # A mutated supplied file is a review question requiring actual trajectory.
            raise ReviewRequired('公开材料哈希变化，需根据真实轨迹区分候选修改与评测复制错误：'+item['path'])
    candidate=base/'results'/'区域销售复盘.xlsx'
    tables,info=read_candidate(candidate) if candidate.is_file() else ({},{'status':'缺交付'})
    diagnostics={};units={}
    def check(label,sheet,fields,sources=False):
        ok,d=compare(tables,truth,sheet,fields,sources);diagnostics[label]=d;return ok
    units['C2']=[check('订单与客户关联','订单明细',['订单月份','客户ID','客户名称','区域']),check('退款与原单关联','退款明细',['订单行ID','客户ID','区域','订单月份'])]
    # Four complete business outputs determine the five C3 bands, not cell accuracy.
    units['C3']=[check('订单逐行计量','订单明细',['标准数量','折后销售额','归属退款额','重述净销售额']),check('退款截止与双时间口径','退款明细',['退款发生月份','标准退款额','计入归属退款额','计入发生退款额']),check('月度规模与环比','月度指标',['有效订单行数','确认零额行数','缺渠道行数','折后销售额','归属退款额','重述净销售额','当期退款发生额','净额环比','缺渠道净额']),check('区域渠道结构','区域渠道汇总',['有效订单行数','折后销售额','归属退款额','重述净销售额','月净额占比'])]
    state=check('订单缺失零与不适用','订单明细',['客户分层','渠道','订单状态','金额语义']) and check('退款非生效语义','退款明细',['退款状态','截止处理'])
    gap=check('缺口对象集合','缺口表',[])
    units['C4']=[state,gap]
    trace=check('订单源及客户源','订单明细',['订单来源','客户来源'],True) and check('退款源及原订单源','退款明细',['退款来源','订单来源'],True)
    clean=check('源记录处理全集','来源与清洗',['来源类型','记录ID','处理结果']) and check('缺口来源','缺口表',['来源定位'],True)
    units['C5']=[trace,clean]
    scores={key:sum(vals)/len(vals) for key,vals in units.items()}
    diagnostics['business_units']={k:[bool(v) for v in vals] for k,vals in units.items()}
    write_evidence(base,tables,info,diagnostics,expected)
    return {**scores,'overall_score':sum(WEIGHTS[k]*scores[k] for k in WEIGHTS)/68,'diagnostics':diagnostics,'evidence_status':'仅规则组；C1/C6/C7需真实轨迹和Judge，不产生正式题目总分'}

```

## LLM Judge Rubric

仅按公开要求及本题档位判定。读取真实工具轨迹、最终回答、候选工作簿与评分证据。评分后提取不算候选验收。证据文件给出Excel行号、图表数据绑定、完整性与截断限制；关键正文或轨迹缺失先补原件，不能臆测行为。图片图表等可接受，但若自动提取未识别需读原交付，不据未识别扣分。缺执行轨迹时C1/C7写“不可判定：缺轨迹”，如协议强制数字可0占位，但阻断正式题目与能力总分。完整轨迹证明没做时才是有效0。输出格式为 {"scores":{"C1":0.5,"C6":0.5,"C7":0.5},"notes":"逐项理由、定位与证据充分性"}；各值只用声明档位。

### Criterion 1: 实际处理范围覆盖 (key: C1, weight: 12)

**Score 1.0**: 真实轨迹与交付共同证明对全部公开范围内订单、退款和客户sheet及有效区块进行了处理，包括隐藏sheet/行；去除重复导出计数、非明细和历史留样。交付的业务对象集合与范围吻合，原文件受保护。不能仅凭正确输出推断实际读取全范围。

**Score 0.5**: 真实轨迹和产物证明已处理三类业务源并形成订单与退款结果，但对一个或多个指定sheet、隐藏区块或范围排除仍有具体遗漏/混入，或实际处理全范围却交付对象范围有可定位缺陷；尚有可用的本期销售复盘结果。

**Score 0.0**: 完整证据证明未形成对本期订单、退款和客户三类源的实际处理，或主要处理的是范围外/错误材料而不能支持本期复盘。

### Criterion 2: 规模结构变化结论 (key: C6, weight: 12)

**Score 1.0**: 两月净额及变化、区域渠道的金额贡献和结构变化、归属退款与发生退款的区别、缺口边界与跟进四个问题均有正确可定位指标支撑；两张图正确反映规模和结构/变化，注明单位与口径，未隐藏待确认组，未把相关变化或缺失猜成已证实原因。文字不必复刻参考分析，正确的其它重点可接受。

**Score 0.5**: 至少正确回答两月规模变化，并正确回答其余三个问题中的至少一个，具有至少一张依据正确的比较图；其它问题、第二图、量化结构或缺口边界存在遗漏/错误，但尚有可使用的销售比较，且核心结论未建立在编造缺失数值或因果上。

**Score 0.0**: 未达到0.5条件；例如缺少正确两月规模比较或任何正确比较图，分析主要基于错误指标，或把补造缺失值/未经支持的原因作为核心结论。

### Criterion 3: 实际业务验收 (key: C7, weight: 8)

**Score 1.0**: 真实执行和验收记录共同证明实际覆盖公开七节四领域：全部sheet/隐藏明细/重复与非明细范围；稳定ID关联及同名/多次退款；单位折扣、截止及两种归属、净额与汇总守恒；图表、结论及缺口边界。记录范围、方法、结果和可定位证据，发现问题如实说明。方法不限，不强制另交脚本或日志。

**Score 0.5**: 真实执行及记录证明至少完成其中两个领域的实质核对，且至少含ID关联或金额与归属之一；其它领域未完成，或记录缺少部分范围/结果/证据。只列数目、复制结果或写“已核对”不构成实质验收。

**Score 0.0**: 完整轨迹显示未达到0.5条件，没有可验证的上述实质核对，或验收记录宣称通过但对应核对没有实际发生。

## Workspace Path

workspace/general_e2e/03_Data_Analysis_task/03_Data_Analysis_task_005_cross_month_returns_regional_sales

## Skills

## Env

## Warmup
