---
id: 03_Data_Analysis_task_025_support_ticket_trends_recurring_issues
name: Support Ticket Trends and Recurring Issue Analysis
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
- business
judge_evidence:
  required:
  - path: 评分证据/分析证据.json
    role: grader_generated_evidence
---


## Prompt

分析Q3客服工单相对Q2的变化，找出产品高发问题、客户分层差异和反复提交的顽疾，给出改善优先级。资料和采用的《业务口径与交付.md》在 `/tmp_workspace/`，按其中交付约定将底稿和报告保存到 `/tmp_workspace/results/`。

## Expected Behavior

Q2基线、客户暴露分母、产品发布窗口、重复问题与统计关联。覆盖全部有效数据区块，按公开规则关联与计算；未知和确认0分开，结论可回查输入，不以参考解法作为唯一实现路线。

## Grading Criteria

评分版本 query10-20261016-v1。公开依据为Prompt采用的《业务口径与交付.md》，不以私有参考答案增设义务。自动检查每项为两个完整业务核验域：两域完整正确得1，仅一域完整正确得0.5，均不完整得0；集合按全量多重集合比较，漏行、重行、额外行使对应域不完整。域的内容和字段列在下表，不使用通用准确率阈值。

| key/检查点 | 分值 | 公开依据 | 两个核验域 |
|---|---:|---|---|

| trend 季度与月度趋势 | 20 | §2 期间和趋势 | 季度概况（产品,Q2工单数,Q3工单数,环比,Q2占比,Q3占比）；月度交叉（月份,产品,问题类型,工单数） |

| customers 等级时效与客户暴露 | 20 | §2 客户日分母和等级历史 | 工单明细（工单ID,客户ID,等级,响应小时,解决小时）；客户分层（等级,问题类型,工单数,等级工单数,客户日数,每千客户日工单数,类型占比） |

| statistics 时长检验与满意度关联 | 20 | §2 统计方法与有效样本 | 时长检验（比较,企业样本数,其他样本数,企业均值,其他均值,t,自由度,p）；满意度相关（因素,样本数,Spearman,p） |

| issues 顽疾与版本关联窗口 | 20 | §2 重复问题与发布窗口 | 顽疾清单（客户ID,产品,问题类型,工单数,已解决数,工单集合）；发布窗口（发布ID,产品,版本,前7天工单数,后7天工单数,日均差） |

| llm_judge.analysis 分析结论与业务建议 | 20 | §4 分析报告 | 见语义rubric |


自动组分=Σ(权重×档位)/80，Judge组分=Σ(权重×档位)/20，总分=自动组分×80+Judge组分×20。每个正式点仅0/0.5/1三档。允许行列重排、等价数字文本和来源集合重排。缺交付为业务未完成；缺GT/坏GT抛评测异常。部分上游关联错误可能影响多个业务结果，能力解释不得据此重复推断能力缺陷。

评分证据含报告全文、完整小表和标明非完整的大表样例。语义判断须核对原文件及对应源记录，样例不能证明全量结论。若收集器截断关键正文、PDF提取失败或所需真实轨迹缺失，相关Judge项记不可判定并停止正式总分汇总；不得以缺证猜0或1。自动组验证不是实际Agent/LLM Judge运行。

## Automated Checks

```python
CONFIG = {'output': '客服工单分析.xlsx',
 'report': '分析报告.md',
 'schema': {'季度概况': ['产品', 'Q2工单数', 'Q3工单数', '环比', 'Q2占比', 'Q3占比'],
            '月度趋势': ['月份', '全部工单', '协作台', '数据云', '移动端'],
            '月度交叉': ['月份', '产品', '问题类型', '工单数'],
            '客户分层': ['等级', '问题类型', '工单数', '等级工单数', '客户日数', '每千客户日工单数', '类型占比'],
            '时长检验': ['比较', '企业样本数', '其他样本数', '企业均值', '其他均值', 't', '自由度', 'p'],
            '满意度相关': ['因素', '样本数', 'Spearman', 'p'],
            '顽疾清单': ['客户ID', '产品', '问题类型', '工单数', '已解决数', '工单集合'],
            '发布窗口': ['发布ID', '产品', '版本', '前7天工单数', '后7天工单数', '日均差'],
            '工单明细': ['工单ID', '客户ID', '产品', '问题类型', '月份', '季度', '等级', '响应小时', '解决小时', '满意度', '来源']},
 'keys': {'季度概况': ['产品'],
          '月度趋势': ['月份'],
          '月度交叉': ['月份', '产品', '问题类型'],
          '客户分层': ['等级', '问题类型'],
          '时长检验': ['比较'],
          '满意度相关': ['因素'],
          '顽疾清单': ['客户ID'],
          '发布窗口': ['发布ID'],
          '工单明细': ['工单ID']},
 'checks': [{'key': 'trend',
             'title': '季度与月度趋势',
             'weight': 20,
             'domains': [{'table': '季度概况', 'fields': ['产品', 'Q2工单数', 'Q3工单数', '环比', 'Q2占比', 'Q3占比']},
                         {'table': '月度交叉', 'fields': ['月份', '产品', '问题类型', '工单数']}],
             'requirement': '§2 期间和趋势',
             'allowed_scores': [0, 0.5, 1],
             'capability': None},
            {'key': 'customers',
             'title': '等级时效与客户暴露',
             'weight': 20,
             'domains': [{'table': '工单明细', 'fields': ['工单ID', '客户ID', '等级', '响应小时', '解决小时']},
                         {'table': '客户分层', 'fields': ['等级', '问题类型', '工单数', '等级工单数', '客户日数', '每千客户日工单数', '类型占比']}],
             'requirement': '§2 客户日分母和等级历史',
             'allowed_scores': [0, 0.5, 1],
             'capability': 'state_awareness#3'},
            {'key': 'statistics',
             'title': '时长检验与满意度关联',
             'weight': 20,
             'domains': [{'table': '时长检验', 'fields': ['比较', '企业样本数', '其他样本数', '企业均值', '其他均值', 't', '自由度', 'p']},
                         {'table': '满意度相关', 'fields': ['因素', '样本数', 'Spearman', 'p']}],
             'requirement': '§2 统计方法与有效样本',
             'allowed_scores': [0, 0.5, 1],
             'capability': 'reasoning_and_decision_making#1'},
            {'key': 'issues',
             'title': '顽疾与版本关联窗口',
             'weight': 20,
             'domains': [{'table': '顽疾清单', 'fields': ['客户ID', '产品', '问题类型', '工单数', '已解决数', '工单集合']},
                         {'table': '发布窗口', 'fields': ['发布ID', '产品', '版本', '前7天工单数', '后7天工单数', '日均差']}],
             'requirement': '§2 重复问题与发布窗口',
             'allowed_scores': [0, 0.5, 1],
             'capability': None}],
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

**Score 1.0**: 用与月度表一致的总量/产品趋势曲线和发布窗口解释激增线索，正确解释客户日频率、Welch与相关检验，针对顽疾提出调查或改进建议；披露未解决、缺评分与观察性关联限制。

**Score 0.5**: 完成主要数值解释或一项可执行建议，并能回查对应事实，但缺少另一部分或材料限制说明。

**Score 0.0**: 没有可回查的业务分析，或主要结论与输入及计算结果矛盾、捏造原因。

依据：公开口径§4 分析报告。实际过程项须真实轨迹和产物；报告中自述不能替代操作证据。语义结论接受有证据的等价表达。缺关键证据时不可判定。

## Workspace Path

```text
workspace/general_e2e/03_Data_Analysis_task/03_Data_Analysis_task_025_support_ticket_trends_recurring_issues
```

## Skills


## Env


## Warmup

