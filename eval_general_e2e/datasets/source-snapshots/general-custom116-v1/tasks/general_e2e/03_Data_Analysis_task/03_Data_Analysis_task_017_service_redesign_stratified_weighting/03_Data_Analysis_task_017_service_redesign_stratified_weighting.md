---
id: 03_Data_Analysis_task_017_service_redesign_stratified_weighting
name: Customer Service Redesign Stratified Weighting and Comparability
category: data-analysis
timeout_seconds: 7200
modality: pure-text
difficulty: L4
grading_type: hybrid
grading_weights:
  automated: 0.65
  llm_judge: 0.35
tags:
  - custom
  - general_e2e
  - business
judge_evidence:
  required:
    - path: 评分证据/公开反馈.json
      role: grader_generated_evidence
    - path: 评分证据/候选主题.json
      role: grader_generated_evidence
    - path: 评分证据/统计与说明.json
      role: grader_generated_evidence
---

## Prompt

请帮我分析这批问卷与开放反馈，区分样本构成变化与同口径服务评价，比较原始、加权和固定人群结构的结果。资料及口径在 `/tmp_workspace/`，请按《口径与交付.md》交付 `/tmp_workspace/results/问卷分析.xlsx` 和 `/tmp_workspace/results/分析与验收.md`。

## Expected Behavior

覆盖S3-07全部版本、人群及响应区块，按公开题目映射、修订顺序、跳题和分母规则统计。完成本题专项分析，保留文字中的分歧与条件及正确来源，明确未知和小样本，实际核对覆盖与结果。

## Grading Criteria

评分版本survey-20261015-v1。仅以Prompt采用的口径与交付.md及公开工作簿为依据。自动65分，Judge35分，总分100。单项0/0.5/1；自动项按下表两个业务域均完整=1，仅一个完整=0.5，均不完整=0。域完整要求应有主键集合无缺无多无重复、所列字段全量正确。单域项为二元。行列顺序及额外列不影响判断，浮点容差0.000051；无公式缓存或无法识别的等价表达须人工复核，不直接认定业务失败。缺GT是评测错误。来源重复的代表行允许不同。

| 检查点 | 分值 | 公开依据与判定域 |
| --- | ---: | --- |
| C1_scope | 10 | 一、范围与来源；四、交付；响应明细的样本编号,阶段；来源索引的来源定位 |
| C2_statistics | 20 | 二、题目、状态及分母；响应明细的提交编号,版本,权重,标准分,扩展题号,扩展标准分,通知,导出,权限；指标汇总的阶段,人群,指标,有效人数,加权分母,加权分子,结果,小样本 |
| C2_special | 15 | 三、本题专项；专项分析的原始均值,加权均值,有效人数；专项分析的固定结构均值 |
| C4_source | 10 | 一、范围与来源；四、交付；来源索引的提交编号,样本编号,阶段,版本,处置 |
| C5_missing | 10 | 二、状态与分母；四、交付；响应明细的评价状态,多选状态；样本缺口的阶段,人群,目标人数,提交人数,未提交人数,有效,拒答,漏答,不适用,有效零分,多选冲突 |
| C1_actual 实际处理范围 | 5 | 四、交付与分析（专项结论另见三）；见下方Judge档位 |
| C3_themes 主题、分歧与条件 | 15 | 四、交付与分析（专项结论另见三）；见下方Judge档位 |
| C4_text_sources 反馈证据定位 | 5 | 四、交付与分析（专项结论另见三）；见下方Judge档位 |
| C5_limits 专项结论与样本边界 | 5 | 四、交付与分析（专项结论另见三）；见下方Judge档位 |
| C6_validation 实际验收 | 5 | 四、交付与分析（专项结论另见三）；见下方Judge档位 |

自动组overall_score=Σ(权重×档位)/65，Judge组=Σ(权重×档位)/35，题目分为两组按原始预算加权之和。C1_scope只查产物集合，C1_actual才检查实际范围。C4_source检查响应来源，C4_text_sources检查主题引用，避免把引用存在当作观点忠实。C1_actual与C6_validation必须有真实轨迹及产物；评测采集缺失记不可判定，正式总分为null，不用0占位、不删项重归一。完整证据证明未做才计业务0分。没有真实Agent执行只能报告作者规则自检。参考文本不是唯一答案，主题相同不要求措辞相同。

## Automated Checks

```python
"""Only reads candidate results and the injected oracle; no host paths."""
from pathlib import Path
from collections import Counter
import json, math
import openpyxl

WEIGHTS = {'C1_scope': 10, 'C2_statistics': 20, 'C2_special': 15, 'C4_source': 10, 'C5_missing': 10}
DOMAINS = {'C1_scope': [['响应明细', ['样本编号', '阶段']], ['来源索引', ['来源定位']]], 'C2_statistics': [['响应明细', ['提交编号', '版本', '权重', '标准分', '扩展题号', '扩展标准分', '通知', '导出', '权限']], ['指标汇总', ['阶段', '人群', '指标', '有效人数', '加权分母', '加权分子', '结果', '小样本']]], 'C2_special': [['专项分析', ['原始均值', '加权均值', '有效人数']], ['专项分析', ['固定结构均值']]], 'C4_source': [['来源索引', ['提交编号', '样本编号', '阶段', '版本', '处置']]], 'C5_missing': [['响应明细', ['评价状态', '多选状态']], ['样本缺口', ['阶段', '人群', '目标人数', '提交人数', '未提交人数', '有效', '拒答', '漏答', '不适用', '有效零分', '多选冲突']]]}

def equal(a,b):
    if a is None: a=''
    if b is None: b=''
    if isinstance(a,str): a=a.strip()
    if isinstance(b,str): b=b.strip()
    if b=='未知' and a in ('未知','无法确认','未确认'): return True
    if isinstance(b,(int,float)) and not isinstance(b,bool):
        try:return math.isfinite(float(a)) and abs(float(a)-b)<=0.000051
        except (ValueError,TypeError):return False
    return a==b

def grade(transcript:list, workspace_path:str)->dict:
    root=Path(workspace_path)
    truth=json.loads((root/'gt'/'标准答案.json').read_text(encoding='utf-8'))
    assert truth['tables'] and truth['keys'], 'Invalid private oracle'
    file=root/'results'/'问卷分析.xlsx'
    tables={}
    read_error=None
    if file.exists():
        try:
            wb=openpyxl.load_workbook(file,data_only=True)
            for sh in wb:
                vals=list(sh.values)
                if not vals:continue
                heads=[str(x).strip() if x is not None else '' for x in vals[0]]
                if len(set(heads)-{''}) != len([x for x in heads if x]):
                    raise ValueError('重复输出字段')
                tables[sh.title]=[dict(zip(heads,row)) for row in vals[1:] if any(v is not None for v in row)]
        except Exception as e:read_error=str(e);tables={}
    diagnostics={}
    # A duplicate export may use any physical representative, but disposition counts must agree.
    src_expected=truth['tables']['来源索引']; src_actual=tables.get('来源索引',[])
    egroup={};agroup={}
    for row in src_expected:egroup.setdefault(row['提交编号'],[]).append(row)
    for row in src_actual:agroup.setdefault(row.get('提交编号'),[]).append(row)
    for sid,ers in egroup.items():
        ars=agroup.get(sid,[])
        if Counter(r.get('处置') for r in ars)==Counter(r['处置'] for r in ers):
            emap={r['来源定位']:r['处置'] for r in ers}
            for row in ars:
                if row.get('来源定位') in emap:row['处置']=emap[row['来源定位']]
    def domain(spec):
        name, fields=spec
        expected=truth['tables'][name]; actual=tables.get(name,[]); keys=truth['keys'][name]
        def k(r):return tuple(str(r.get(x,'')).strip() for x in keys)
        ec=Counter(k(r) for r in expected); ac=Counter(k(r) for r in actual)
        same=ec==ac and all(v==1 for v in ac.values())
        lookup={k(r):r for r in actual}
        good=sum(all(equal(lookup.get(k(r),{}).get(f),r.get(f)) for f in fields) for r in expected)
        ok=same and good==len(expected)
        diagnostics[name+'|'+','.join(fields)]={'objects':len(expected),'submitted':len(actual),'matched_values':good,'key_set_exact':same}
        return ok
    scores={}
    for key,domains in DOMAINS.items():
        hits=[domain(d) for d in domains]
        scores[key]=1.0 if all(hits) else (0.5 if any(hits) else 0.0)
    evidence=root/'评分证据';evidence.mkdir(exist_ok=True)
    # Full semantic evidence, not a keyword scorer; excludes private expected answers.
    public_feedback={}
    p=root/'开放反馈.xlsx'
    if p.exists():
        for sh in openpyxl.load_workbook(p,data_only=True):
            public_feedback[sh.title]=list(sh.values)
    report=root/'results'/'分析与验收.md'
    payload={'candidate_tables':{k:v for k,v in tables.items() if k in ('指标汇总','专项分析')},
             'candidate_report':report.read_text(encoding='utf-8') if report.exists() else None,
             'numeric_diagnostics':diagnostics,'read_error':read_error,
             'note':'全文提取；真实处理及验收须结合外部执行轨迹，不能从本评分器的读取推定。'}
    def compact(records):
        if not records:return {'headers':[],'rows':[]}
        headers=list(records[0]);return {'headers':headers,'rows':[[r.get(k) for k in headers] for r in records]}
    payload['candidate_tables']={k:compact(v) for k,v in payload['candidate_tables'].items()}
    # Public metadata permits the Judge to check adopted submission, version and population.
    adopted={r['提交编号']:[r['版本'],r['人群']] for r in truth['tables']['响应明细']}
    cited_ids={str(r[1]) for vv in public_feedback.values() for r in vv if len(r)>1}
    public_payload={'feedback_sheets':public_feedback,'adopted_submission_metadata':{k:v for k,v in adopted.items() if k in cited_ids},
                    'metadata_note':'由公开响应、版本、人群和去重规则可复算；未列入采用集合的反馈不计当前观点。'}
    for name,obj in [('公开反馈.json',public_payload),('候选主题.json',compact(tables.get('主题证据',[]))),('统计与说明.json',payload)]:
        (evidence/name).write_text(json.dumps(obj,ensure_ascii=False,separators=(',',':'),default=str),encoding='utf-8')
    return {**scores,'overall_score':sum(WEIGHTS[k]*v for k,v in scores.items())/sum(WEIGHTS.values()),
            'diagnostics':diagnostics,'candidate_read_error':read_error}

```

## LLM Judge Rubric

先读取完整公开反馈、候选统计与主题表、分析说明及真实轨迹。主题接受同义表达及合理合并/拆分。禁止按关键词或参考措辞评分。评分证据json为评分后提取，不是候选主动验收。证据截断或关键轨迹缺失须在notes明确不可判定并阻止正式汇总；不能把协议数字占位解释为有效0。

### Criterion 1: 实际处理范围 (key: C1_actual, weight: 5)

**Score 1.0**: 实际读取和处理覆盖全部版本、人群与两个响应区块；结合真实调用及回执和来源产物。

**Score 0.5**: 已覆盖两个版本但有一部分人群或补录区块未处理。

**Score 0.0**: 完整证据支持的结果未达到0.5条件，或未交付本项要求。采集缺失不是业务0。

### Criterion 2: 主题、分歧与条件 (key: C3_themes, weight: 15)

**Score 1.0**: 通知、导出、权限三个主题均保留支持与反对观点及改变含义的前提，跨人群说明分歧，无虚构或反向概括；接受等价主题。

**Score 0.5**: 至少一个主题完整保留双向观点及关键条件，其余主题不全；若没有任何主题完整或将全部条件观点变为无条件支持则为0。

**Score 0.0**: 完整证据支持的结果未达到0.5条件，或未交付本项要求。采集缺失不是业务0。

### Criterion 3: 反馈证据定位 (key: C4_text_sources, weight: 5)

**Score 1.0**: 三个主题的双向观点均有正确反馈编号、版本及文件sheet行定位，引用确属采用提交，证据原意与结论相符。

**Score 0.5**: 至少一个主题双向观点的定位和引用全部正确，但其余主题不全或有误。

**Score 0.0**: 完整证据支持的结果未达到0.5条件，或未交付本项要求。采集缺失不是业务0。

### Criterion 4: 专项结论与样本边界 (key: C5_limits, weight: 5)

**Score 1.0**: 专项分析回答“区分样本构成变化与同口径服务评价，比较原始、加权和固定人群结构的结果”，引用正确专项数值，并说明小样本、缺口和不可推广/非因果限制。

**Score 0.5**: 专项比较有正确数值依据但边界说明不全，或边界说明正确但专项比较不完整；无正确数值比较且无正确边界说明为0。

**Score 0.0**: 完整证据支持的结果未达到0.5条件，或未交付本项要求。采集缺失不是业务0。

### Criterion 5: 实际验收 (key: C6_validation, weight: 5)

**Score 1.0**: 真实核对覆盖sheet区块、题目映射、有效分母及主题证据四类，记录对象、方法、结果与未确认项；实际回执足以支撑。

**Score 0.5**: 真实核对覆盖其中至少两类且有可确认的具体检查结果，其余不全；不足两类为0。

**Score 0.0**: 完整证据支持的结果未达到0.5条件，或未交付本项要求。采集缺失不是业务0。

## Workspace Path

workspace/general_e2e/03_Data_Analysis_task/03_Data_Analysis_task_017_service_redesign_stratified_weighting

## Skills

## Env

## Warmup
