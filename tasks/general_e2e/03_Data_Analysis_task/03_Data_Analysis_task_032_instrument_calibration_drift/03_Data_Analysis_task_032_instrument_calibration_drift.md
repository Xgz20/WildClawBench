---
id: 03_Data_Analysis_task_032_instrument_calibration_drift
name: Instrument Calibration Drift
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
  - academic
judge_evidence:
  required:
    - path: 评分证据/分析证据.json
      role: grader_generated_evidence
    - path: 评分证据/引用核验.json
      role: grader_generated_evidence
    - path: 评分证据/参考分析.md
      role: grader_generated_evidence
    - path: results/分析说明.md
      role: deliverable
    - path: 业务口径与交付.md
      role: reference
---

## Prompt

请完成仪器测量时点校准与参数漂移复核，交付可复算结果，回答材料中的两个分析问题并说明复核建议与结论边界。资料及采用的《业务口径与交付.md》在`/tmp_workspace/`，按其中的约定把成果保存到`/tmp_workspace/results/`。

## Expected Behavior

按公开范围、版本、时间、关联及未知规则计算，回答两个指定对照问题。所有关键事实均有来源，不以正确局部掩盖矛盾的补充结论，不将未知填零。

## Grading Criteria

评分及数据版本：difficulty-revision-20261027-v2。公开依据为《业务口径与交付.md》§1–4。四项规则各含两个完整业务域：两个域均正确1，一个正确0.5，均不正确0；每个域核对全量主键及列值，不按行正确率插值。整数精确相等，浮点绝对容差0.000002；允许行列重排、等价数字文本及来源集合重排。参考材料缺失或损坏为评分错误，不计模型零分。

| 检查点 | 分值 | 两个核验域 |
|---|---:|---|
| C1_linkage 关联、版本与来源 | 20 | [[{"table": "计算明细", "fields": ["测量ID", "实验组", "仪器ID", "阶段", "采用校准段", "校准版本", "回收版本", "当前校准段"]}], [{"table": "计算明细", "fields": ["来源"]}]] |
| C2_calculation 组合规则与逐条结果 | 25 | [[{"table": "计算明细", "fields": ["稀释还原浓度_mgL", "回收校正浓度_mgL"]}], [{"table": "计算明细", "fields": ["当前参数浓度_mgL"]}]] |
| C3_summary 分层或多粒度对照汇总 | 25 | [[{"table": "分组汇总", "fields": ["实验组", "阶段", "测量数", "有效数", "稀释还原均值", "回收校正均值"]}], [{"table": "对照分析", "fields": ["仪器ID", "配对数", "差异条数", "正式均值", "当前参数均值", "均值差额", "相对偏差"]}]] |
| C4_uncertainty 未知范围与缺口 | 10 | [[{"table": "计算明细", "fields": ["状态"]}], [{"table": "缺口清单", "fields": ["对象ID", "指标", "原因", "来源"]}]] |
| C5_findings 指定分析问题 | 12 | 问题一与问题二，关键事实矛盾按原档位否决对应问题 |
| C6_limits 缺口及边界 | 8 | 缺口事实完整性；未知及外推边界一致性 |

题目总分=80×规则组分+20×Judge组分；规则组分=Σ权重×档位/80，Judge组分=(12×C5+8×C6)/20。各点只用0/0.5/1。证据不足的必要项不可判定，不填零、不删除分母后合成正式总分。规则产生的证据不是候选执行过验收的证明。
能力映射见同题能力映射.json。只将关联20分映射状态感知#3、组合推导及分层汇总50分映射推理与决策#1，其余为业务分；映射预算70。能力总体=100×Σ映射权重×档位/70，维度=100×Σ本维权重×档位/本维预算。未覆盖意图理解、工具调用、结果评估不计零分，也不从产物正确推定这些过程能力。

## Automated Checks

```python
CONFIG = {'schema': {'分组汇总': ['实验组', '阶段', '测量数', '有效数', '稀释还原均值', '回收校正均值'], '对照分析': ['仪器ID', '配对数', '差异条数', '正式均值', '当前参数均值', '均值差额', '相对偏差'], '计算明细': ['测量ID', '实验组', '仪器ID', '阶段', '采用校准段', '校准版本', '回收版本', '当前校准段', '状态', '稀释还原浓度_mgL', '回收校正浓度_mgL', '当前参数浓度_mgL', '来源'], '缺口清单': ['对象ID', '指标', '原因', '来源']}, 'keys': {'计算明细': ['测量ID'], '分组汇总': ['实验组', '阶段'], '对照分析': ['仪器ID'], '缺口清单': ['对象ID', '指标']}, 'domains': {'C1_linkage': [[{'table': '计算明细', 'fields': ['测量ID', '实验组', '仪器ID', '阶段', '采用校准段', '校准版本', '回收版本', '当前校准段']}], [{'table': '计算明细', 'fields': ['来源']}]], 'C2_calculation': [[{'table': '计算明细', 'fields': ['稀释还原浓度_mgL', '回收校正浓度_mgL']}], [{'table': '计算明细', 'fields': ['当前参数浓度_mgL']}]], 'C3_summary': [[{'table': '分组汇总', 'fields': ['实验组', '阶段', '测量数', '有效数', '稀释还原均值', '回收校正均值']}], [{'table': '对照分析', 'fields': ['仪器ID', '配对数', '差异条数', '正式均值', '当前参数均值', '均值差额', '相对偏差']}]], 'C4_uncertainty': [[{'table': '计算明细', 'fields': ['状态']}], [{'table': '缺口清单', 'fields': ['对象ID', '指标', '原因', '来源']}]]}, 'version': 'difficulty-revision-20261027-v2', 'weights': {'C1_linkage': 20, 'C2_calculation': 25, 'C3_summary': 25, 'C4_uncertainty': 10}, 'expected_counts': {'分组汇总': 24, '对照分析': 13, '计算明细': 8000, '缺口清单': 1268}}

from pathlib import Path
import math,json,re
from collections import Counter
from openpyxl import load_workbook

def _read(path):
    book=load_workbook(path,read_only=True,data_only=True);out={}
    for name,fields in CONFIG['schema'].items():
        if name not in book.sheetnames:raise ValueError('缺少工作表:'+name)
        rows=[];header=None
        for values in book[name].iter_rows(values_only=True):
            if set(fields).issubset(values):
                if any(values.count(f)!=1 for f in fields):raise ValueError('重复表头字段')
                header={f:values.index(f) for f in fields};continue
            if header is None or not any(v is not None for v in values):continue
            rows.append({f:values[i] if i<len(values) else None for f,i in header.items()})
        if header is None:raise ValueError('缺少表头:'+name)
        out[name]=rows
    book.close();return out
def _norm(v):
    return None if v is None or (isinstance(v,str) and v.strip() in ('','未知','不适用','N/A')) else v.strip() if isinstance(v,str) else v
def _equal(a,b,field):
    a=_norm(a);b=_norm(b)
    if a is None or b is None:return a is b
    if '来源' in field:return set(str(a).split(';'))==set(str(b).split(';'))
    if isinstance(a,(int,float)) and not isinstance(a,bool):
        try:
            b=float(str(b).replace(',',''))
            tol=0 if isinstance(a,int) else .000002
            return math.isfinite(b) and abs(a-b)<=tol
        except (ValueError,TypeError):return False
    return str(a)==str(b)
def _domain(expected,actual,blocks):
    errors=[]
    for b in blocks:
        table=b['table'];keys=CONFIG['keys'][table]
        key=lambda r:tuple(str(_norm(r[k])) for k in keys)
        ee={key(r):r for r in expected[table]};aa={key(r):r for r in actual.get(table,[])}
        if len(ee)!=len(expected[table]):raise RuntimeError('参考答案主键重复:'+table)
        if len(aa)!=len(actual.get(table,[])) or set(ee)!=set(aa):errors.append({'table':table,'problem':'主键集合或重复','expected':len(ee),'actual':len(aa)});continue
        for k,r in ee.items():
            for f in b['fields']:
                if not _equal(r[f],aa[k].get(f),f) and len(errors)<12:errors.append({'table':table,'key':k,'field':f,'expected':r[f],'actual':aa[k].get(f)})
    return not errors,errors
def grade(transcript,workspace_path):
    root=Path(workspace_path)
    try:expected=_read(root/'gt/分析结果.xlsx')
    except Exception as exc:raise RuntimeError('参考材料缺失或损坏') from exc
    for t,rows in expected.items():
        if len(rows)!=CONFIG['expected_counts'][t]:raise RuntimeError('参考表范围与版本不符:'+t)
    try:actual=_read(root/'results/分析结果.xlsx');read_error=None
    except Exception as exc:actual={};read_error=str(exc)
    scores={};diagnostics={'read_error':read_error,'domains':{}}
    for key,domains in CONFIG['domains'].items():
        checked=[_domain(expected,actual,blocks) for blocks in domains]
        scores[key]=sum(ok for ok,_ in checked)/2
        diagnostics['domains'][key]=[{'passed':ok,'differences':e} for ok,e in checked]
    scores['overall_score']=sum(scores[k]*w for k,w in CONFIG['weights'].items())/80
    scores['diagnostics']=diagnostics
    report=root/'results/分析说明.md';body=report.read_text(encoding='utf-8-sig') if report.exists() else ''
    folder=root/'评分证据';folder.mkdir(exist_ok=True)
    def emit(name,obj):
        (folder/name).write_text(json.dumps(obj,ensure_ascii=False,separators=(',',':')),encoding='utf8')
    emit('分析证据.json',{'version':CONFIG['version'],'reference_summary':{t:expected[t] for t in ['分组汇总','对照分析']},'reference_status_counts':dict(Counter(r['状态'] for r in expected['计算明细'])),'candidate_summary':{t:actual.get(t,[]) for t in ['对照分析']},'limitations':'这是评分后生成的核验事实，不证明候选主动验收。报告补充的关键事实和解释同样受公开要求约束；证据截断时不得推定正确。'})
    # Include reference facts for concrete IDs cited by any acceptable report, not only the author example.
    tokens=set(re.findall(r'[A-Za-z][A-Za-z0-9_\u4e00-\u9fff]*',body));citations={};used_chars=0;truncated=False
    for table,rr in expected.items():
        if table in ('缺口清单','对照分析'):continue
        relevant=[]
        for r in rr:
            if not any(str(r[k]) in tokens for k in CONFIG['keys'][table]):continue
            length=len(json.dumps(r,ensure_ascii=False,separators=(',',':')))
            if used_chars+length>16000:truncated=True;continue
            relevant.append(r);used_chars+=length
        if relevant:citations[table]=relevant
    emit('引用核验.json',{'reference_rows_for_report_ids':citations,'truncated':truncated,'selection':'只按报告明确出现的完整唯一键提取；未引用或超预算不代表无问题。'})
    reference_report=root/'gt/分析说明.md'
    if not reference_report.is_file():raise RuntimeError('参考分析缺失')
    (folder/'参考分析.md').write_text(reference_report.read_text(encoding='utf-8-sig'),encoding='utf8')
    return scores

```

## LLM Judge Rubric

### Criterion 1: 指定分析问题及建议的事实一致性 (key: C5_findings, weight: 12)

**Score 1.0**: 公开附件所列两个分析问题均完整成立：问题要求的各口径、数字及分母或纳入范围正确，有可回查定位与相符建议；与各问题有关的所有关键事实、阈值和解释均无实质错误或矛盾。只给最高最低但未回答指定对照不成立。

**Score 0.5**: 恰好一个分析问题完整成立。另一个缺失、不完整，或其任一关键数字/阈值/事实/支撑解释存在实质错误；即使同时写了一个正确比较也不能使该问题恢复成立。

**Score 0.0**: 两个分析问题均不完整成立。不得用不相关的正确比较替代指定问题。

两问题为公开附件“分析问题一/二”，不是额外设定。无关的轻微排版或仍可唯一定位的列字母笔误不否决；错误百分比基准、虚构组数、错误阈值、从均值无依据推原因是实质错误。缺口数量和外推边界专由C6评价，避免同一表述重复归因。

### Criterion 2: 缺口事实与结论边界 (key: C6_limits, weight: 8)

**Score 1.0**: 两部分均完整成立。A：至少一种真实缺口有正确数量、影响指标和有效范围，所有写出的缺口数量、类别及分母没有实质矛盾。B：明确本题适用范围，未知不填零或猜值，全文无无依据的缺失偏差方向、现实总体、因果、合格或政策断言；另一段免责声明不能抵消越界结论。

**Score 0.5**: A、B恰好一部分完整成立。A中虚构组数或错误缺口数量使A不成立；B中将未知导致的偏差方向写成确定事实或越界外推使B不成立，即使另有正确免责声明仍不成立。

**Score 0.0**: A、B均不完整成立，或存在与实际未知范围直接矛盾的全量核定/无缺口断言。

判分前先确认文件与证据充分；材料缺失而无法判定时记录受影响项，不用业务零分替代不可判定。合格表达允许多种措辞、方法和建议，不要求复现参考文本。

## Workspace Path

workspace/general_e2e/03_Data_Analysis_task/03_Data_Analysis_task_032_instrument_calibration_drift

## Skills

## Env

## Warmup
