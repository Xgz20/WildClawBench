---
id: 03_Data_Analysis_task_024_flood_control_supply_gaps_transfers
name: Flood Control Supply Reserve Gaps and Transfer Analysis
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
- public_administration
judge_evidence:
  required:
  - path: 评分证据/分析证据.json
    role: grader_generated_evidence
---


## Prompt

整理汛前防汛物资盘点，找出储备缺口、风险错配及应优先调拨或轮换的物资。资料和采用的《业务口径与交付.md》在 `/tmp_workspace/`，按其中交付约定将底稿和报告保存到 `/tmp_workspace/results/`。

## Expected Behavior

多单位多批次库存、风险分层需求、可用储备和临期轮换。覆盖全部有效数据区块，按公开规则关联与计算；未知和确认0分开，结论可回查输入，不以参考解法作为唯一实现路线。

## Grading Criteria

评分版本 query10-20261016-v1。公开依据为Prompt采用的《业务口径与交付.md》，不以私有参考答案增设义务。自动检查每项为两个完整业务核验域：两域完整正确得1，仅一域完整正确得0.5，均不完整得0；集合按全量多重集合比较，漏行、重行、额外行使对应域不完整。域的内容和字段列在下表，不使用通用准确率阈值。

| key/检查点 | 分值 | 公开依据 | 两个核验域 |
|---|---:|---|---|

| stock 单位与库存状态 | 20 | §2 单位、状态、有效期 | 批次清单（盘点行ID,确认件数,可用件数）；批次清单（盘点行ID,剩余天数,临期状态） |

| needs 风险配置与满足率 | 25 | §2 需求和分档 | 需求与缺口（储备点,物资编码,理论需求,确认可用量,满足率）；需求与缺口（储备点,物资编码,未知批次数,储备判定,确认缺口） |

| distribution 物资分布与批次质量 | 20 | §2 分布与状态 | 储备分布（储备点,类别,确认件数,确认可用件数,参考价值,未知批次数）；状态评估（维度,对象,确认件数,完好件数,报废件数,完好率,报废率） |

| lineage 实体关联与来源 | 15 | §1 范围与§3 来源 | 批次清单（盘点行ID,储备点,物资编码,采购批次,供应商）；批次清单（盘点行ID,来源） |

| llm_judge.analysis 分析结论与业务建议 | 20 | §4 分析报告 | 见语义rubric |


自动组分=Σ(权重×档位)/80，Judge组分=Σ(权重×档位)/20，总分=自动组分×80+Judge组分×20。每个正式点仅0/0.5/1三档。允许行列重排、等价数字文本和来源集合重排。缺交付为业务未完成；缺GT/坏GT抛评测异常。部分上游关联错误可能影响多个业务结果，能力解释不得据此重复推断能力缺陷。

评分证据含报告全文、完整小表和标明非完整的大表样例。语义判断须核对原文件及对应源记录，样例不能证明全量结论。若收集器截断关键正文、PDF提取失败或所需真实轨迹缺失，相关Judge项记不可判定并停止正式总分汇总；不得以缺证猜0或1。自动组验证不是实际Agent/LLM Judge运行。

## Automated Checks

```python
CONFIG = {'output': '防汛储备分析.xlsx',
 'report': '分析报告.md',
 'schema': {'需求与缺口': ['储备点', '物资编码', '风险等级', '核心物资', '理论需求', '确认可用量', '满足率', '未知批次数', '储备判定', '确认缺口'],
            '批次清单': ['盘点行ID', '储备点', '物资编码', '类别', '供应商', '采购批次', '状态', '确认件数', '可用件数', '剩余天数', '临期状态', '来源'],
            '储备分布': ['储备点', '类别', '确认件数', '确认可用件数', '参考价值', '未知批次数'],
            '状态评估': ['维度', '对象', '确认件数', '完好件数', '报废件数', '完好率', '报废率']},
 'keys': {'需求与缺口': ['储备点', '物资编码'], '批次清单': ['盘点行ID'], '储备分布': ['储备点', '类别'], '状态评估': ['维度', '对象']},
 'checks': [{'key': 'stock',
             'title': '单位与库存状态',
             'weight': 20,
             'domains': [{'table': '批次清单', 'fields': ['盘点行ID', '确认件数', '可用件数']},
                         {'table': '批次清单', 'fields': ['盘点行ID', '剩余天数', '临期状态']}],
             'requirement': '§2 单位、状态、有效期',
             'allowed_scores': [0, 0.5, 1],
             'capability': 'reasoning_and_decision_making#1'},
            {'key': 'needs',
             'title': '风险配置与满足率',
             'weight': 25,
             'domains': [{'table': '需求与缺口', 'fields': ['储备点', '物资编码', '理论需求', '确认可用量', '满足率']},
                         {'table': '需求与缺口', 'fields': ['储备点', '物资编码', '未知批次数', '储备判定', '确认缺口']}],
             'requirement': '§2 需求和分档',
             'allowed_scores': [0, 0.5, 1],
             'capability': 'reasoning_and_decision_making#1'},
            {'key': 'distribution',
             'title': '物资分布与批次质量',
             'weight': 20,
             'domains': [{'table': '储备分布', 'fields': ['储备点', '类别', '确认件数', '确认可用件数', '参考价值', '未知批次数']},
                         {'table': '状态评估', 'fields': ['维度', '对象', '确认件数', '完好件数', '报废件数', '完好率', '报废率']}],
             'requirement': '§2 分布与状态',
             'allowed_scores': [0, 0.5, 1],
             'capability': None},
            {'key': 'lineage',
             'title': '实体关联与来源',
             'weight': 15,
             'domains': [{'table': '批次清单', 'fields': ['盘点行ID', '储备点', '物资编码', '采购批次', '供应商']},
                         {'table': '批次清单', 'fields': ['盘点行ID', '来源']}],
             'requirement': '§1 范围与§3 来源',
             'allowed_scores': [0, 0.5, 1],
             'capability': 'state_awareness#3'}],
 'special': None,
 'csv_outputs': {},
 'pdf': False}

"""Embedded verbatim after CONFIG in every task. Reads only grading workspace."""
from pathlib import Path
from collections import defaultdict
import json, math, csv, re, zipfile
import openpyxl

def _norm(v,field=''):
    if v is None or str(v).strip() in ('','未知','n.a.','N/A'):return None
    if isinstance(v,str):
        v=v.strip()
        if field.endswith('集合') or field in ('来源','异常类型'):
            return ';'.join(sorted(set(x.strip() for x in v.split(';') if x.strip())))
    return v

def _equal(a,b,field):
    a=_norm(a,field);b=_norm(b,field)
    if a is None or b is None:return a is b
    if isinstance(a,(int,float)) and not isinstance(a,bool):
        try:
            v=float(str(b).replace(',',''))
            tol=.0100001 if re.search('金额|费用|余额|成本|价值|期初|期末|应入账|实际入账|贡献|应结|实结|结算差|电费|服务费|计费差|费用差|销售$|收款$',field) else 1e-5
            return math.isfinite(v) and abs(float(a)-v)<=tol
        except (ValueError,TypeError):return False
    return str(a)==str(b)

def _read_workbook(path,schema):
    result={s:[] for s in schema}
    if not path.exists():return result,[]
    errors=[]
    try:
        wb=openpyxl.load_workbook(path,data_only=True,read_only=True)
        for name,fields in schema.items():
            if name not in wb:continue
            header=None
            for row in wb[name].values:
                if set(fields)<=set(row):header=list(row);continue
                if header is None or not any(x is not None for x in row):continue
                result[name].append({f:row[header.index(f)] if header.index(f)<len(row) else None for f in fields})
        wb.close()
    except (OSError,ValueError,KeyError,zipfile.BadZipFile,TypeError) as exc:
        errors.append(type(exc).__name__+': '+str(exc))
    return result,errors

def _same(expected,actual,fields,keys):
    if len(expected)!=len(actual):return False
    if not expected:return True
    usekeys=[k for k in keys if k in fields]
    def key(r):return tuple(str(_norm(r.get(k),k)) for k in usekeys)
    eg=defaultdict(list);ag=defaultdict(list)
    for r in expected:eg[key(r)].append(r)
    for r in actual:ag[key(r)].append(r)
    if set(eg)!=set(ag):return False
    for k,rr in eg.items():
        available=list(ag[k])
        if len(available)!=len(rr):return False
        for er in rr:
            j=next((i for i,ar in enumerate(available) if all(_equal(er.get(f),ar.get(f),f) for f in fields)),None)
            if j is None:return False
            available.pop(j)
    return True

def grade(transcript:list,workspace_path:str)->dict:
    root=Path(workspace_path)
    try:
        oracle=json.loads((root/'gt/标准答案.json').read_text(encoding='utf-8'))
        reference=oracle['tables']
        if set(reference)!=set(CONFIG['schema']):raise ValueError('Oracle table mismatch')
        for name,cols in CONFIG['schema'].items():
            if not isinstance(reference[name],list) or any(not set(cols)<=set(r) for r in reference[name]):raise ValueError('Oracle schema invalid: '+name)
    except (OSError,ValueError,KeyError,TypeError) as exc:raise RuntimeError('Evaluation data missing/corrupt; not candidate failure') from exc
    candidate,errors=_read_workbook(root/'results'/CONFIG['output'],CONFIG['schema'])
    # CSVs are the authoritative delivery for the two cinema tables.
    for sheet,filename in CONFIG.get('csv_outputs',{}).items():
        p=root/'results'/filename
        if not p.exists():candidate[sheet]=[];continue
        try:
            with p.open(encoding='utf-8-sig',newline='') as f:candidate[sheet]=list(csv.DictReader(f))
        except (OSError,UnicodeError,csv.Error) as exc:candidate[sheet]=[];errors.append(str(exc))
    special_ok=True
    if CONFIG.get('special')=='leads':
        dims=['需求匹配','预算可信','决策角色','竞争态势','时间紧迫']
        model=candidate.get('评分模型',[])
        try:
            weights={z['维度']:float(z['权重']) for z in model}
            special_ok=len(model)==5 and set(weights)==set(dims) and all(math.isfinite(v) and v>0 for v in weights.values()) and abs(sum(weights.values())-100)<1e-6
        except (ValueError,TypeError,KeyError):special_ok=False
        if special_ok:
            def band(v):return 'A' if v>=80-1e-9 else 'B' if v>=60-1e-9 else 'C' if v>=40-1e-9 else 'D'
            for row in reference['统一线索与评分']:
                lo=sum(weights[d]*row[d+'标准值'] for d in dims if row[d+'标准值'] is not None)
                hi=lo+sum(weights[d] for d in dims if row[d+'标准值'] is None)
                row.update(最低分=lo,最高分=hi,等级=band(lo) if band(lo)==band(hi) else '待确认')
            for z in reference['等级分布']:z['线索数']=sum(r['展会']==z['展会'] and r['等级']==z['等级'] for r in reference['统一线索与评分'])
    scores={};diagnostics={}
    for checkpoint in CONFIG['checks']:
        flags=[]
        for domain in checkpoint['domains']:
            name=domain['table'];fields=domain['fields']
            flags.append(_same(reference[name],candidate.get(name,[]),fields,CONFIG['keys'][name]))
        if checkpoint['key']=='scoring' and not special_ok:flags=[False,False]
        scores[checkpoint['key']]=1.0 if all(flags) else .5 if any(flags) else 0.0
        diagnostics[checkpoint['key']]={'complete_business_domains':flags}
    if CONFIG.get('special')=='environment':
        # Different spatial models may predict different values; deterministic observations remain fixed.
        ref={(z['实验室'],z['指标'],z['日期']):z for z in reference['日均数据']}
        final_ok=True
        for z in candidate.get('日均数据',[]):
            key=tuple(z.get(k) for k in ['实验室','指标','日期']);e=ref.get(key)
            if e is None:final_ok=False;continue
            if e['状态']=='未知':final_ok &= _norm(z.get('最终日均')) is None
            elif e['状态']=='实测':final_ok &= _equal(e['最终日均'],z.get('最终日均'),'最终日均')
            else:
                try:
                    v=float(z.get('最终日均'));final_ok &= math.isfinite(v) and v>=0 and v<={'PM2.5':500,'PM10':700,'O3':350,'NO2':250,'SO2':150,'CO':15}[e['指标']]
                except (TypeError,ValueError):final_ok=False
        if not final_ok:scores['daily']=min(scores['daily'],.5)
        diagnostics['imputed_values']={'basic_bounds_and_observation_preservation':bool(final_ok),'scientific_validity':'requires imputation rubric; no unique numeric oracle'}
    budget=sum(c['weight'] for c in CONFIG['checks'])
    scores['overall_score']=sum(scores[x['key']]*x['weight'] for x in CONFIG['checks'])/budget
    reportpath=root/'results'/CONFIG['report'];report=reportpath.read_text(encoding='utf-8') if reportpath.exists() else None
    pdftext=None
    if CONFIG.get('pdf'):
        p=root/'results/应收账款复核报告.pdf'
        if p.exists():
            try:
                from pypdf import PdfReader
                pdftext='\n'.join(page.extract_text() or '' for page in PdfReader(str(p)).pages)
            except Exception as exc:errors.append('PDF extraction failed: '+str(exc))
    # Keep evidence complete for summary tables. Large detail is explicitly sampled,
    # with sources and original files available; never pretend it is the full workbook.
    summaries={k:v for k,v in candidate.items() if len(v)<=120}
    detail_samples={k:{'rows':v[:12],'total_rows':len(v),'complete':False} for k,v in candidate.items() if len(v)>120}
    chart_structure=[]
    bookpath=root/'results'/CONFIG['output']
    if bookpath.exists():
        try:
            import xml.etree.ElementTree as ET
            with zipfile.ZipFile(bookpath) as archive:
                types=ET.fromstring(archive.read('[Content_Types].xml'))
                parts=[x.attrib['PartName'].lstrip('/') for x in types if x.attrib.get('ContentType')=='application/vnd.openxmlformats-officedocument.drawingml.chart+xml']
                for name in parts:
                    xml=ET.fromstring(archive.read(name));chart_structure.append({'part':name,'formulas':[x.text for x in xml.iter() if x.tag.endswith('}f')],'labels':[x.text for x in xml.iter() if x.tag.endswith('}t')],'scope':'native structure and bindings only; not a visual rendering'})
        except Exception as exc:errors.append('Chart extraction: '+str(exc))
    evidence={'report':report,'pdf_text':pdftext,'summary_tables':summaries,'detail_samples':detail_samples,'native_chart_structure':chart_structure,
      'automated_scores':{k:v for k,v in scores.items()},'extraction_errors':errors,
      'evidence_limits':'Large tables sampled, not full coverage for case assertions. Inspect original files for claims beyond samples. No actual Agent process is inferred from artifacts.',
      'source_files':{'workbook':str(Path('results')/CONFIG['output']),'report':str(Path('results')/CONFIG['report'])}}
    folder=root/'评分证据';folder.mkdir(exist_ok=True)
    (folder/'分析证据.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
    scores['diagnostics']={'checkpoints':diagnostics,'errors':errors,'counts':{s:{'expected':len(reference[s]),'actual':len(candidate.get(s,[]))} for s in reference},'valid_custom_model':special_ok,'status':'author_artifact_rules_only_no_agent_or_judge_score'}
    return scores
```

## LLM Judge Rubric

### Criterion 1: 分析结论与业务建议 (key: analysis, weight: 20)

**Score 1.0**: 准确识别具体高风险核心物资缺口，给出有供需数量依据且不透支调出方需求的调拨或采购建议；结合批次和供应商解释报废及临期轮换，明确未知单位对结论的影响。

**Score 0.5**: 完成主要数值解释或一项可执行建议，并能回查对应事实，但缺少另一部分或材料限制说明。

**Score 0.0**: 没有可回查的业务分析，或主要结论与输入及计算结果矛盾、捏造原因。

依据：公开口径§4 分析报告。实际过程项须真实轨迹和产物；报告中自述不能替代操作证据。语义结论接受有证据的等价表达。缺关键证据时不可判定。

## Workspace Path

```text
workspace/general_e2e/03_Data_Analysis_task/03_Data_Analysis_task_024_flood_control_supply_gaps_transfers
```

## Skills


## Env


## Warmup

