---
id: 03_Data_Analysis_task_007_promotion_discounts_sales_margin
name: Promotional Discounts and Sales Gross Margin Analysis
category: data-analysis
timeout_seconds: 7200
modality: pure-text
difficulty: L4
grading_type: hybrid
grading_weights:
  automated: 0.70
  llm_judge: 0.30
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

帮销售运营复盘2026年7—8月各部门的销售和促销毛利。资料在 `/tmp_workspace/`，按其中《销售口径与交付.docx》的范围和口径，整理可复算明细、分组指标及同月同地区同部门的可比商品分析，按渠道和客户类型分层并用共同商品等权比较毛利率，报告毛利及标准化收入覆盖率，说明销售结构变化和待补资料，配好图表、来源与清洗记录。请实际核对跨sheet覆盖、关联、折扣与净额、分层权重及图表结论并记录，把结果保存到 `/tmp_workspace/results/促销毛利分析.xlsx`，保留原文件。

## Expected Behavior

覆盖3地区、两个月全部订单和退款sheet及客户、成本和折扣维度，不遗漏隐藏行，不混入标题小计。按客户ID、原单行ID、SKU及成本有效区间关联，金额统一以元计、单位成本以元/件计并显示两位小数，用元和分计算，整单折扣按公开权重向下取分后按余数和行ID派发尾分。退款以原行折后额比例确定，成本转回采用真实确认值。取消、不生效退款、确认零额、缺渠道、缺成本分别处理。净销售额可确认但成本缺失时保留毛利未知，汇总毛利率用相同可确认子集收入作分母。各月各地区各部门促销与非促销使用共同SKU集合比较；进一步按渠道、客户类型分层，以两组都有正折后额且已确认毛利对应收入均大于零的共同SKU作标准化集合，两组使用相同等权重，未知渠道不参与标准化。分别保留普通毛利率、标准化毛利率、毛利收入覆盖率和标准化收入覆盖率，单组无业务保留零值、零分母比率留空。变化解释保留数据缺口、样本覆盖及因果边界。真实核对行为须由调用与回执支持。

## Grading Criteria

本题实例化S3-01 C1—C7，总分100，本次数据与评分版本为20261014_促销分层可比；历史结果保留当时冻结版本，不静默重评。公开依据均在《销售口径与交付.docx》：一/二是范围、关联和单位；三/四是分摊、退款、成本与缺失；五规定交付、分层等权比较、分析与验收；六规定对账关系。该文档在exec内，候选可见；标准记录集、来源映射和作者测试均在gt或出题工具，不投递候选。

| 检查点 | 公开要求与对象 | 方式及证据 | 权重 | 档位 |
|---|---|---|---:|---|
| C1 公开范围实际覆盖 | 全部指定工作表、有效区块与隐藏行，排除标题小计 | Judge；真实轨迹＋产物 | 10 | 0/0.5/1 |
| C2 分散事实关联 | 订单客户/成本版本、退款原单关联 | 规则；全量键集合及关联字段 | 18 | 0/0.5/1 |
| C3 组合规则计算 | 折扣分币、退款成本、三种分组、地区内可比SKU及渠道客户类型分层等权 | 规则；全量可复算明细与汇总 | 30 | 0/0.25/0.5/0.75/1 |
| C4 缺失与零额语义 | 成本未知、未知渠道缺口、取消/未生效和确认零额 | 规则；状态、未知数值和缺口集合 | 12 | 0/0.5/1 |
| C5 来源可追溯 | 全部业务ID来源、明细关联来源、缺口位置 | 规则；文件/sheet/记录单元格 | 10 | 0/0.5/1 |
| C6 分析与图表证据 | 月度规模结构、地区内部门促销、分层等权毛利、覆盖率与因果限制 | Judge；产物＋回答 | 12 | 0/0.25/0.5/0.75/1 |
| C7 实际验收 | 覆盖、关联、金额成本、分层权重及图表结论四类核对 | Judge；真实轨迹＋产物 | 8 | 0/0.5/1 |

C2：订单关联族与退款关联族均正确得1，仅一个族完整正确得0.5，均不完整得0。每族以全部应有主键为分母，缺行、重复、额外对象或关联字段错误均使对应族未通过。

C3：四个计算单元为①订单数量、金额精度、行折扣、分币分摊、折后额及净成本毛利；②退款数量、原单净价退款与确认成本转回；③部门、地区、渠道三类分组的全套规模及已知子集毛利分母；④可比商品、分层商品、分层比较三表的完整主键和指标，包括同月同地区同部门共同SKU集合、渠道与客户类型层、两组共同可确认SKU及一致等权重、普通和标准化毛利率、两种收入覆盖率、未知渠道排除及空集合表达。每个单元全量核对通过计一个完成单元，分别完成0/1/2/3/4个时得0/0.25/0.5/0.75/1，诊断保留差异位置，不把单元连续准确率冒充单项分。

C4：三个对象族为①订单/退款收入与成本状态；②缺渠道、缺销售成本、缺退回成本的完整缺口键集合；③未知数值、真实零额及不适用数值表达。三个均正确得1，至少一个但未全正确得0.5，一个也未正确得0。C4观察语义，C3观察金额推导，诊断解释同一根因可能影响二者。

C5：明细追溯族（订单、客户、成本、折扣及退款原单来源）和全量来源索引/缺口定位族均正确得1，仅一个族正确得0.5，均不完整得0。来源接受等价的文件名前缀、美元绝对引用符号和记录ID单元格或包含该单元格的同一行区域；不得用任意同行空白列伪造依据。

列顺序、业务明细顺序和数值/千分文本、等效精度百分比均不影响评分。公开固定的表名与字段用于跨部门复核，额外解释列不扣分。金额容差小于半分，比率及共同权重容差0.000001。公式存在但没有可读缓存时标评测不可判定并补安全只读求值，不执行候选代码来补交付。候选缺文件或确实损坏属有效业务失败；GT缺失/损坏、评测提取失败或关键轨迹缺失不是候选0分。必要检查点不可判定时不输出正式总分，不删除项目后重归一。

规则组预算70，overall_score=(18×C2+30×C3+12×C4+10×C5)/70；Judge组预算30。最终百分制=70×规则组分+10×C1+12×C6+8×C7。能力使用capabilities-2026-09-23-v1：C1→intent_understanding#3，C2→state_awareness#3，C3→reasoning_and_decision_making#1，C7→result_evaluation#1；C4/C5/C6是业务验收，不映射。映射预算66，能力总分=100×(10×C1+18×C2+30×C3+8×C7)/66；各维在自己的预算内归一，工具调用未覆盖。此映射不代表旧七维报告器原生支持五维。

## Automated Checks

```python
"""嵌入正式题目的完整规则实现；仅经workspace_path读写。"""
from pathlib import Path
from collections import Counter
from decimal import Decimal, InvalidOperation
import json
import re
import posixpath
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile
from openpyxl import load_workbook

WEIGHTS={'C2':18,'C3':30,'C4':12,'C5':10}
KEYS={'订单明细':['订单行ID'],'退款明细':['退款ID'],'分组指标':['月份','分组类型','分组值','促销标记'],
      '可比商品':['月份','地区','部门','促销标记'],
      '分层商品':['月份','地区','部门','渠道','客户类型','SKU','促销标记'],
      '分层比较':['月份','地区','部门','渠道','客户类型','促销标记'],
      '缺口表':['订单行ID','缺口类型'],'来源索引':['记录类型','记录ID']}

class GradingIndeterminate(RuntimeError):
    pass

def _normal(v):
    if v is None:return None
    if isinstance(v,str):
        v=v.strip()
        if v in ['','未知','待核实','不适用','N/A','NA','—','-']:return None
    return v

def _same(actual, expected, field):
    if field=='成本版本ID' and expected=='不适用':return _normal(actual) is None
    if '来源' in field or field=='来源定位':
        if expected is None:return _normal(actual) is None
        if actual is None:return False
        # A record's ID cell or its row range are equivalent source locators.
        def loc(x):
            p=str(x).strip().replace('\\','/').replace('$','').split('|')
            if len(p)!=3:return None
            m=re.fullmatch(r'([A-Z]+)([0-9]+)(?::([A-Z]+)([0-9]+))?',p[2].upper())
            if not m:return None
            if m[1]!='A':return None
            return p[0].split('/')[-1],p[1].strip("'"),int(m[2]),int(m[4] or m[2])
        x,y=loc(actual),loc(expected)
        return x is not None and y is not None and x[:2]==y[:2] and x[2]==y[2] and x[3]==y[3]
    if expected is None:return _normal(actual) is None
    if isinstance(expected,(int,float)) and not isinstance(expected,bool):
        try:
            raw=str(actual).strip().replace(',',''); number=Decimal(raw.rstrip('%'))/(100 if raw.endswith('%') else 1)
            if not number.is_finite():return False
            tolerance=Decimal('0.000001') if field.endswith('率') or field=='共同权重' else Decimal('0.0049')
            return abs(number-Decimal(str(expected)))<=tolerance
        except (InvalidOperation,TypeError,ValueError):return False
    return str(actual).strip()==str(expected).strip()

def _load_tables(path, schemas):
    try:
        values=load_workbook(path,data_only=True,read_only=False)
        formula_locations={}
        with ZipFile(path) as archive:
            main='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
            relns='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
            relationships=ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
            paths={r.attrib['Id']:r.attrib['Target'] for r in relationships}
            book=ET.fromstring(archive.read('xl/workbook.xml'))
            for sheet in book.find('{'+main+'}sheets'):
                target=paths[sheet.attrib['{'+relns+'}id']]
                part=target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/'+target)
                root=ET.fromstring(archive.read(part))
                formula_locations[sheet.attrib['name']]={c.attrib['r'] for c in root.iter('{'+main+'}c') if c.find('{'+main+'}f') is not None}
    except (BadZipFile,OSError,ValueError,KeyError,ET.ParseError) as e: return {},{'candidate_file_error':str(e)}
    tables={}; structure={}; uncached=[]
    for name,fields in schemas.items():
        if name not in values.sheetnames:
            tables[name]=[];structure[name]={'missing_sheet':True};continue
        ws=values[name]; headers=None; headerrow=None
        for i,row in enumerate(ws.iter_rows(min_row=1,max_row=min(12,ws.max_row),values_only=True),1):
            labels=[str(x).strip() if x is not None else '' for x in row]
            if fields[0] in labels and sum(x in labels for x in fields)>=min(3,len(fields)):
                headers={h:j for j,h in enumerate(labels) if h};headerrow=i;break
        if headers is None:
            tables[name]=[];structure[name]={'missing_header':True};continue
        records=[]
        for rn,row in enumerate(ws.iter_rows(min_row=headerrow+1,values_only=True),headerrow+1):
            if not any(v is not None for v in row):continue
            # Charts and their separate helper ranges do not turn into prose-table rows.
            if all(row[headers[f]] is None for f in fields if f in headers):continue
            rec={f:(row[headers[f]] if f in headers and headers[f]<len(row) else None) for f in fields}
            rec['_row']=rn;records.append(rec)
            for f,c in headers.items():
                if f not in fields:continue
                coord=ws.cell(rn,c+1).coordinate
                if row[c] is None and coord in formula_locations.get(name,set()):uncached.append(f'{name}!{coord}')
        tables[name]=records;structure[name]={'rows':len(records),'columns':list(headers),'header_row':headerrow,'charts':len(ws._charts)}
    if uncached:raise GradingIndeterminate('候选公式缺缓存，需评测方安全只读求值后再判，不按业务0分：'+','.join(uncached[:20]))
    charts=[]
    for ws in values:
        for idx,ch in enumerate(ws._charts,1):
            series=[]
            for s in ch.series:
                try:v=s.val.numRef.f
                except AttributeError:v=None
                try:c=s.cat.numRef.f
                except AttributeError:
                    try:c=s.cat.strRef.f
                    except AttributeError:c=None
                series.append({'values':v,'categories':c})
            title_xml=ET.tostring(ch.title.to_tree(),encoding='unicode') if ch.title is not None else None
            charts.append({'sheet':ws.title,'chart_index':idx,'chart_type':ch.to_tree().tag,'title_xml':title_xml,'series':series,
                           'x_axis_number_format':getattr(getattr(getattr(ch,'x_axis',None),'numFmt',None),'formatCode',None),
                           'y_axis_number_format':getattr(getattr(getattr(ch,'y_axis',None),'numFmt',None),'formatCode',None)})
    values.close()
    return tables,{'sheets':structure,'charts':charts}

def _compare(cand, target, table, fields):
    keys=KEYS[table]
    def key(r):return tuple(str(r.get(k,'')) for k in keys)
    ar=cand.get(table,[]); er=target[table]; counts=Counter(key(r) for r in ar); amap={key(r):r for r in ar}; eset={key(r) for r in er}
    missing=sorted(eset-set(amap)); extra=sorted(set(amap)-eset); dup=[k for k,v in counts.items() if v>1]; bad=[]
    for e in er:
        k=key(e);a=amap.get(k)
        if a is None:continue
        for f in fields:
            if not _same(a.get(f),e.get(f),f):
                if len(bad)<12:bad.append({'key':k,'field':f,'actual':a.get(f),'expected':e.get(f),'candidate_row':a.get('_row')})
    passed=not(missing or extra or dup or bad)
    return passed,{'table':table,'fields':fields,'expected_records':len(er),'candidate_records':len(ar),'missing':missing[:12],'extra':extra[:12],'duplicates':dup[:12],'mismatches':bad,'passed':passed}

def _write_evidence(base,tables,structure,diagnostics,gt):
    evidence=base/'评分证据';evidence.mkdir(exist_ok=True)
    meta={'author':'评分器在候选冻结副本生成','not_agent_validation':True,'limitations':'本证据只说明候选已交内容和可确定差异，不能证明实际执行、读取覆盖或验收。C1/C7须真实工具调用和回执。图表保存引用，不替代完整图形查看。','source':'results/促销毛利分析.xlsx'}
    concise={k:[{kk:vv for kk,vv in item.items() if kk!='fields'} for item in v] for k,v in diagnostics.get('details',{}).items()}
    gap_evidence={}
    for row in tables.get('缺口表',[]):
        kind=str(row.get('缺口类型'));bucket=gap_evidence.setdefault(kind,{'count':0,'examples':[],'impact_descriptions':[],'requested_materials':[]})
        bucket['count']+=1
        if len(bucket['examples'])<3:bucket['examples'].append(row)
        for field,output in [('影响字段','impact_descriptions'),('待补材料','requested_materials')]:
            text=str(row.get(field,''))
            if text not in bucket[output] and len(bucket[output])<12:bucket[output].append(text)
    def comparison_evidence(name,limit=12):
        rows=tables.get(name,[]);selected=[];seen=set()
        # Show observed states and periods before the first remaining rows. These
        # examples are navigation aids, never a substitute for full-table review.
        for field in ['比较状态','标准化纳入','月份']:
            values=set()
            for idx,row in enumerate(rows):
                value=row.get(field)
                if value is None or str(value) in values:continue
                values.add(str(value))
                if idx not in seen and len(selected)<limit:selected.append(row);seen.add(idx)
        for idx,row in enumerate(rows):
            if idx not in seen and len(selected)<limit:selected.append(row);seen.add(idx)
        return {'meta':meta,'table':name,'records':selected,
                'extraction_limits':{'total_rows':len(rows),'included_rows':len(selected),'omitted_rows':len(rows)-len(selected),
                                     'selection':'各比较状态、标准化纳入状态及月份的首条，随后按候选行序补足；每条保留_row',
                                     'requires_full_workbook_for_judgement':len(selected)<len(rows)},
                'rule_evidence':'04_结构与规则诊断.json含该表全量主键与数值核对结论；差异仅列前12例，不证明分析结论或实际验收。'}
    payloads={
        '01_分析正文.json':{'meta':meta,'analysis':tables.get('分析说明',[]),'gap_categories':gap_evidence,'gap_extraction_limits':'每类示例最多3行，解释去重最多12种；完整缺口键集合由规则核对，逐行措辞须回查原文件。'},
        '02_验收记录.json':{'meta':meta,'checks':tables.get('验收记录',[]),'charts':structure.get('charts',[])},
        '03_可比商品.json':comparison_evidence('可比商品'),
        '06_分层商品.json':comparison_evidence('分层商品'),
        '07_分层比较.json':comparison_evidence('分层比较'),
        '04_结构与规则诊断.json':{'meta':meta,'structure':structure,'units':diagnostics.get('units',{}),'comparison_details':concise,'required_input_sheets':gt['input_sheets']}
    }
    for kind in ['部门','地区','渠道']:
        payloads['05_分组指标_'+kind+'.json']={'meta':meta,'summary':[r for r in tables.get('分组指标',[]) if r.get('分组类型')==kind]}
    for name,p in payloads.items():
        raw=json.dumps(p,ensure_ascii=False,separators=(',',':'),default=str)
        if len(raw)>18000:
            # No silent truncation. Chunk complete records while preserving file/row locators.
            sections={k:v for k,v in p.items() if isinstance(v,list)}
            for k,v in sections.items():
                if len(v)>80:p[k]=v[:80];p.setdefault('extraction_limits',{})[k]={'total_rows':len(v),'included_rows':80,'omitted_rows':len(v)-80,'requires_full_workbook_for_judgement':True}
            raw=json.dumps(p,ensure_ascii=False,separators=(',',':'),default=str)
        if len(raw)>19000:
            raw=json.dumps({'meta':meta,'extraction_incomplete':True,'reason':'单证据超字符预算，必须读取完整候选文件补证后判定','original_characters':len(raw),'source':meta['source']},ensure_ascii=False)
        (evidence/name).write_text(raw,encoding='utf-8')

def grade(transcript:list, workspace_path:str)->dict:
    base=Path(workspace_path);truth=base/'gt'/'标准记录集.json'
    try:
        gt=json.loads(truth.read_text(encoding='utf-8')); expected=gt['tables'];schemas=gt['schemas']
        if len(expected['订单明细'])!=gt['counts']['订单行'] or not expected['订单明细'] or not all(t in expected for t in KEYS):raise ValueError('GT集合不完整')
    except (OSError,ValueError,KeyError,TypeError) as e:raise GradingIndeterminate('评测基准缺失或损坏，不生成候选有效零分：'+str(e)) from e
    output=base/'results'/'促销毛利分析.xlsx'
    if not output.is_file():
        result={k:0.0 for k in WEIGHTS};result['overall_score']=0.0;result['diagnostics']={'candidate_missing':str(output.relative_to(base))}
        _write_evidence(base,{}, {'candidate_missing':True},result['diagnostics'],gt);return result
    tables,structure=_load_tables(output,schemas); diagnostics={}; units={}
    def unit(name, checks):
        parts=[_compare(tables,expected,t,f) for t,f in checks];ok=all(x[0] for x in parts);diagnostics[name]=[x[1] for x in parts];units[name]=ok;return ok
    # C2: two meaningful families of joins, independent of numeric correctness.
    join_order=unit('订单关联',[('订单明细',['订单ID','月份','地区','部门','客户ID','客户类型','渠道','SKU','促销标记','订单状态','成本版本ID'])])
    join_refund=unit('退款关联',[('退款明细',['原订单行ID','订单ID','月份','部门','客户ID','SKU','退款状态'])])
    c2=(int(join_order)+int(join_refund))/2
    a=unit('订单金额及有效成本',[('订单明细',['数量','标价金额','行折扣额','整单分摊额','折后销售额','退款额','净销售额','单位成本','销售成本','退回成本','净成本','毛利额'])])
    b=unit('退款金额与成本转回',[('退款明细',['退货数量','退款额','退回成本'])])
    c=unit('三类分组与毛利分母',[('分组指标',schemas['分组指标'][4:])])
    d=unit('可比商品分层与等权比较',[(name,[f for f in schemas[name] if f not in KEYS[name]])
                                   for name in ['可比商品','分层商品','分层比较']])
    c3=sum([a,b,c,d])/4
    e=unit('状态语义',[('订单明细',['收入状态','成本状态']),('退款明细',['成本状态'])])
    # Exact keyset establishes all missing categories; explanatory wording is Judge evidence.
    f=unit('业务缺口覆盖',[('缺口表',[])])
    g=unit('未知数值及零值',[('订单明细',['净销售额','净成本','毛利额']),('退款明细',['退回成本'])])
    c4=1.0 if e and f and g else (0.5 if any([e,f,g]) else 0.0)
    h=unit('明细追溯',[('订单明细',['订单来源','客户来源','成本来源','折扣来源']),('退款明细',['退款来源','原单来源'])])
    i=unit('全量来源索引',[('来源索引',['来源定位','处理结果']),('缺口表',['来源定位'])])
    c5=(int(h)+int(i))/2
    scores={'C2':c2,'C3':c3,'C4':c4,'C5':c5}; result={**scores,'overall_score':sum(WEIGHTS[k]*v for k,v in scores.items())/sum(WEIGHTS.values()),'diagnostics':{'units':units,'details':diagnostics,'structure':structure}}
    _write_evidence(base,tables,structure,result['diagnostics'],gt)
    return result

```

## LLM Judge Rubric

必须使用原始真实工具调用、对象参数与返回，结合候选交付及回答。评分器生成的“评分证据”不是Agent行为证据；其中有来源文件、sheet、行号、图表引用、规则诊断和提取限制。候选写了“已验收”、生成器参考正确或评分器重算正确，都不能证明候选执行。缺轨迹、正文未完整提取或图表必要内容缺失须在notes明确列不可判定，不把协议数字占位0用于正式总分。完整证据显示业务未完成才给有效0。允许等价工具和分析表述，不要求本题未公开的脚本或操作顺序。

### Criterion 1: C1 公开范围实际覆盖 (key: C1, weight: 10)

**Score 1.0**: 真实操作与产物共同支持订单、退款、客户/成本/折扣三个来源族全部指定sheet与有效区块已处理，隐藏明细有纳入依据，标题小计未混入，期间与地区范围正确。
**Score 0.5**: 真实操作和产物支持至少一个来源族完整处理，但未覆盖全部三个族或有隐藏行/有效区块遗漏、非明细混入；说明具体范围，不能仅凭最终数字推断处理行为。
**Score 0.0**: 完整可用轨迹表明三个来源族均未完整处理，或只复述任务/没有有效交付。评测侧缺轨迹另列不可判定。

### Criterion 2: C6 变化结构及毛利结论 (key: C6, weight: 12)

四个有独立业务意义的分析单元：A，两月净销售规模变化和至少一个部门/地区/渠道结构变化有正确数字与范围；B，各部门在同月同地区共同SKU范围内的促销/非促销规模及毛利收入覆盖率有正确对比；C，在同月同地区同部门的渠道、客户类型层内，以两组共同可确认SKU和相同商品等权重比较，普通与标准化毛利率及两种收入覆盖率的范围、分母和图表正确，解释商品权重调整前后观察到的差异，不能把标准化率当成实际总毛利率；D，成本及渠道缺口、未知渠道不参与标准化、空集合或有限覆盖的影响、补件与相关性/因果限制清楚。销售规模/结构图与分层等权毛利率比较图分别属于A/C，不以图表存在代替数值和范围。评分证据仅提取三张比较表的导航示例，须结合完整候选工作簿和有业务意义的层判断；示例未展示的内容不能推定缺失。明确声称促销造成净增收入/利润而无可识别因果证据时，D不通过且本项最高0.5。因果措辞判断要结合上下文，不用关键词匹配。

**Score 1.0**: A/B/C/D全部成立，图表、明细与文字支持一致，缺口及分母限制明确。
**Score 0.75**: 恰有三个分析单元成立，其余单元缺失或证据不足，且没有触发因果上限。
**Score 0.5**: 恰有两个分析单元成立；或原可达更高档但触发因果上限。
**Score 0.25**: 恰有一个分析单元成立，其他缺失或有实质错误。
**Score 0.0**: 四个单元均不成立、没有相关分析交付，或结论与完整证据普遍矛盾。

### Criterion 3: C7 实际核对并记录 (key: C7, weight: 8)

核对对象为①跨sheet/隐藏行/非明细范围；②订单、退款、客户和成本版本关联；③整单折扣分摊、退款净额及成本守恒；④同月地区部门共同SKU、渠道客户类型分层、两组共同标准化集合及一致权重、两种覆盖率、图表引用和结论。一个对象完成需要真实操作及返回表明做过相应对照，并有记录说明范围和结果。发现问题且如实记录仍可算实际核对；执行脚本的代码文本、只列行数或笼统“通过”不能替代可观察回执。接受Excel人工核对或程序等价方式，不强制某个脚本。

**Score 1.0**: 四类均有真实执行和核对结果，记录可定位对象、方法、结果及限制。
**Score 0.5**: 恰有两类或三类有充分实际核对证据，其余未核对或记录不充分。
**Score 0.0**: 完整轨迹表明最多一类达到上述要求，或没有实际核对。轨迹缺失导致无法判断时另列不可判定，禁止从正确产物推断。

## Workspace Path

workspace/general_e2e/03_Data_Analysis_task/03_Data_Analysis_task_007_promotion_discounts_sales_margin

## Skills

## Env

## Warmup
