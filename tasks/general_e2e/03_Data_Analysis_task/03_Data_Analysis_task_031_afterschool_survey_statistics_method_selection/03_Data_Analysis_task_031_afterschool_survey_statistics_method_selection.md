---
id: 03_Data_Analysis_task_031_afterschool_survey_statistics_method_selection
name: After-School Service Survey Statistical Definitions and Method Selection
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
- education
judge_evidence:
  required:
  - path: 评分证据/分析证据.json
    role: grader_generated_evidence
---


## Prompt

为本轮课后服务问卷统一分析口径：区分事实题、多选题和满意度题组，判断量表分析前提，完成相应统计与方法选型。资料和采用的《业务口径与交付.md》在 `/tmp_workspace/`，按其中交付约定将底稿和报告保存到 `/tmp_workspace/results/`。

## Expected Behavior

题型与构念边界、反向题、完整样本信度与结构适用性、跳题分母。覆盖全部有效数据区块，按公开规则关联与计算；未知和确认0分开，结论可回查输入，不以参考解法作为唯一实现路线。

## Grading Criteria

评分版本 query10-20261016-v1。公开依据为Prompt采用的《业务口径与交付.md》，不以私有参考答案增设义务。自动检查每项为两个完整业务核验域：两域完整正确得1，仅一域完整正确得0.5，均不完整得0；集合按全量多重集合比较，漏行、重行、额外行使对应域不完整。域的内容和字段列在下表，不使用通用准确率阈值。

| key/检查点 | 分值 | 公开依据 | 两个核验域 |
|---|---:|---|---|

| C2_descriptive 题型分组与描述统计 | 25 | §2 题型、映射和分母 | 题组分类（题组,题型,统计路线）；描述统计（学校,题目,选项,有效n,加权分母,频数,加权频数,百分比,均值） |

| C2_scale 量表前提与信效度诊断 | 25 | §2 量表前提和公式 | 量表前提与诊断（人群,题组,完整n,题数,路线）；量表前提与诊断（人群,alpha,KMO,Bartlett卡方,自由度,p） |

| C4_source 最新提交与题目来源 | 15 | §2 版本、反向与来源 | 标准作答（受访者ID,作答ID,学校,统一题号,值）；标准作答（受访者ID,统一题号,来源） |

| C5_missing 拒答跳题与有效分母 | 15 | §2 缺失与不适用 | 缺失分母（学校,题目,有效,漏答,拒答,不适用）；标准作答（受访者ID,统一题号,状态） |

| llm_judge.C1_scope 实际人群与版本覆盖 | 5 | §1 范围与§2 映射 | 见语义rubric |

| llm_judge.C3_themes 条件反馈与选型结论 | 10 | §2 选型与§4 报告 | 见语义rubric |

| llm_judge.C6_validation 实际核对范围与证据 | 5 | §2 核对要求 | 见语义rubric |


自动组分=Σ(权重×档位)/80，Judge组分=Σ(权重×档位)/20，总分=自动组分×80+Judge组分×20。每个正式点仅0/0.5/1三档。允许行列重排、等价数字文本和来源集合重排。缺交付为业务未完成；缺GT/坏GT抛评测异常。部分上游关联错误可能影响多个业务结果，能力解释不得据此重复推断能力缺陷。

评分证据含报告全文、完整小表和标明非完整的大表样例。语义判断须核对原文件及对应源记录，样例不能证明全量结论。若收集器截断关键正文、PDF提取失败或所需真实轨迹缺失，相关Judge项记不可判定并停止正式总分汇总；不得以缺证猜0或1。自动组验证不是实际Agent/LLM Judge运行。

## Automated Checks

```python
CONFIG = {'output': '课后服务问卷分析.xlsx',
 'report': '课后服务满意度问卷分析口径与选型方案.md',
 'schema': {'题组分类': ['题组', '题型', '统计路线'],
            '描述统计': ['学校', '题目', '选项', '有效n', '加权分母', '频数', '加权频数', '百分比', '均值'],
            '量表前提与诊断': ['人群', '题组', '完整n', '题数', 'alpha', 'KMO', 'Bartlett卡方', '自由度', 'p', '路线'],
            '缺失分母': ['学校', '题目', '有效', '漏答', '拒答', '不适用'],
            '标准作答': ['受访者ID', '作答ID', '学校', '统一题号', '值', '状态', '来源']},
 'keys': {'题组分类': ['题组'],
          '描述统计': ['学校', '题目', '选项'],
          '量表前提与诊断': ['人群'],
          '缺失分母': ['学校', '题目'],
          '标准作答': ['受访者ID', '作答ID', '学校', '统一题号']},
 'checks': [{'key': 'C2_descriptive',
             'title': '题型分组与描述统计',
             'weight': 25,
             'domains': [{'table': '题组分类', 'fields': ['题组', '题型', '统计路线']},
                         {'table': '描述统计',
                          'fields': ['学校', '题目', '选项', '有效n', '加权分母', '频数', '加权频数', '百分比', '均值']}],
             'requirement': '§2 题型、映射和分母',
             'allowed_scores': [0, 0.5, 1],
             'capability': 'reasoning_and_decision_making#1'},
            {'key': 'C2_scale',
             'title': '量表前提与信效度诊断',
             'weight': 25,
             'domains': [{'table': '量表前提与诊断', 'fields': ['人群', '题组', '完整n', '题数', '路线']},
                         {'table': '量表前提与诊断', 'fields': ['人群', 'alpha', 'KMO', 'Bartlett卡方', '自由度', 'p']}],
             'requirement': '§2 量表前提和公式',
             'allowed_scores': [0, 0.5, 1],
             'capability': 'reasoning_and_decision_making#1'},
            {'key': 'C4_source',
             'title': '最新提交与题目来源',
             'weight': 15,
             'domains': [{'table': '标准作答', 'fields': ['受访者ID', '作答ID', '学校', '统一题号', '值']},
                         {'table': '标准作答', 'fields': ['受访者ID', '统一题号', '来源']}],
             'requirement': '§2 版本、反向与来源',
             'allowed_scores': [0, 0.5, 1],
             'capability': 'state_awareness#3'},
            {'key': 'C5_missing',
             'title': '拒答跳题与有效分母',
             'weight': 15,
             'domains': [{'table': '缺失分母', 'fields': ['学校', '题目', '有效', '漏答', '拒答', '不适用']},
                         {'table': '标准作答', 'fields': ['受访者ID', '统一题号', '状态']}],
             'requirement': '§2 缺失与不适用',
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

### Criterion 1: 实际人群与版本覆盖 (key: C1_scope, weight: 5)

**Score 1.0**: 真实处理记录与产物覆盖A/B、SC0—SC5及各响应区块，使用最新提交和公开题目映射。

**Score 0.5**: 真实证据表明覆盖全部版本但漏部分区块或人群，或覆盖完整但个别题目映射遗漏。

**Score 0.0**: 完整证据表明主要版本或人群未处理。

依据：公开口径§1 范围与§2 映射。实际过程项须真实轨迹和产物；报告中自述不能替代操作证据。语义结论接受有证据的等价表达。缺关键证据时不可判定。

### Criterion 2: 条件反馈与选型结论 (key: C3_themes, weight: 10)

**Score 1.0**: 准确区分题型、同构念与异质单项，按实际n/诊断选择路线；主题保留支持、反对、条件及反馈ID；明确小样本和效度边界。

**Score 0.5**: 选型结论或反馈归纳有一部分完整且有证据，另一部分不完整；未捏造总体效度。

**Score 0.0**: 把所有题型当同一量表、将KMO/alpha等同已证明效度，或主题歪曲主要意见。

依据：公开口径§2 选型与§4 报告。实际过程项须真实轨迹和产物；报告中自述不能替代操作证据。语义结论接受有证据的等价表达。缺关键证据时不可判定。

### Criterion 3: 实际核对范围与证据 (key: C6_validation, weight: 5)

**Score 1.0**: 真实核对及报告覆盖跨sheet、题目映射、分母、主题证据四类对象，结果和未验证范围一致。

**Score 0.5**: 真实有效核对至少覆盖其中两类，但其余未核或未交代限制。

**Score 0.0**: 完整证据显示未作相关有效核对，或将无效检查当全部通过。

依据：公开口径§2 核对要求。实际过程项须真实轨迹和产物；报告中自述不能替代操作证据。语义结论接受有证据的等价表达。缺关键证据时不可判定。

## Workspace Path

```text
workspace/general_e2e/03_Data_Analysis_task/03_Data_Analysis_task_031_afterschool_survey_statistics_method_selection
```

## Skills


## Env


## Warmup

