---
id: 03_Data_Analysis_task_039_asset_depreciation_disposal_cutoff
name: Asset Depreciation Disposal Cutoff
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
    - path: 评分证据/分析证据.json
      role: grader_generated_evidence
---

## Prompt

请完成固定资产折旧与处置月份核算，交付可复算结果和有依据的比较分析，说明需要复核的事项。资料及采用的《业务口径与交付.md》在`/tmp_workspace/`，按其中的交付约定将结果保存到`/tmp_workspace/results/`。

## Expected Behavior

覆盖两批主记录和截止前有效关联版本，按公开业务规则生成明细、汇总和缺口清单。分清已确认零、未知和不适用，结论能回查数据；不能依据私有参考材料补填公开输入。

## Grading Criteria

评分版本domain-expansion-20261019-v1。公开依据为Prompt采用的《业务口径与交付.md》§1–4。每个规则点有两个完整业务核验域：两个均正确得1，一个完整正确得0.5，均不完整得0；不是按行准确率任意插值。所有域核对完整主键集合，拒绝漏行、重复和额外记录。允许行列重排、等价数字文本和来源集合重排；数值以公开精度核验，绝对容差0.000002。

| 检查点 | 分值 | 两个核验域 |
|---|---:|---|
| C1_linkage 实体版本与来源关联 | 15 | 计算明细：记录ID,分组,关联ID,采用版本；计算明细：记录ID,主记录来源,关联来源 |
| C2_calculation 固定资产折旧与处置月份核算 | 35 | 计算明细：记录ID,当月折旧_元；计算明细：记录ID,期末账面价值_元 |
| C3_summary 分组范围与指标分母 | 20 | 分组汇总：分组,主记录数,可计算记录数,非可计算记录数；分组汇总：分组,当月折旧_元有效数,当月折旧_元汇总,期末账面价值_元有效数,期末账面价值_元汇总 |
| C4_uncertainty 缺口原因与未知范围 | 10 | 计算明细：记录ID,状态；缺口清单：记录ID,指标,原因,主记录来源,关联来源 |
| llm_judge.C5_findings 比较与建议 | 12 | 两个指标分别有正确比较、定位和对应建议 |
| llm_judge.C6_limits 缺口与结论边界 | 8 | 实际缺口数量及影响；适用范围限制 |

规则组=Σ(权重×档位)/80，Judge组=Σ(权重×档位)/20，总分=80×规则组+20×Judge组。规则和Judge单项均为0/0.5/1。缺交付为未完成；缺GT/损坏GT是评测错误，抛出异常。评分证据为评分后生成的提取材料，不是Agent主动自检证据。Judge证据被截断或缺少判断必要的原件时不可判定，应停止正式总分汇总；当前原生Judge只接收数值，需评测外层处理该状态，不以猜测得分替代。

## Automated Checks

```python
CONFIG = {'output': '分析结果.xlsx', 'rows': 12000, 'schema': {'计算明细': ['记录ID', '分组', '关联ID', '采用版本', '状态', '当月折旧_元', '期末账面价值_元', '主记录来源', '关联来源'], '分组汇总': ['分组', '主记录数', '可计算记录数', '非可计算记录数', '当月折旧_元有效数', '当月折旧_元汇总', '期末账面价值_元有效数', '期末账面价值_元汇总'], '缺口清单': ['记录ID', '指标', '原因', '主记录来源', '关联来源']}, 'keys': {'计算明细': ['记录ID'], '分组汇总': ['分组'], '缺口清单': ['记录ID', '指标']}, 'checks': [{'key': 'C1_linkage', 'title': '实体版本与来源关联', 'weight': 15, 'capability': 'state_awareness#3', 'domains': [{'table': '计算明细', 'fields': ['记录ID', '分组', '关联ID', '采用版本']}, {'table': '计算明细', 'fields': ['记录ID', '主记录来源', '关联来源']}]}, {'key': 'C2_calculation', 'title': '固定资产折旧与处置月份核算', 'weight': 35, 'capability': 'reasoning_and_decision_making#1', 'domains': [{'table': '计算明细', 'fields': ['记录ID', '当月折旧_元']}, {'table': '计算明细', 'fields': ['记录ID', '期末账面价值_元']}]}, {'key': 'C3_summary', 'title': '分组范围与指标分母', 'weight': 20, 'capability': 'reasoning_and_decision_making#1', 'domains': [{'table': '分组汇总', 'fields': ['分组', '主记录数', '可计算记录数', '非可计算记录数']}, {'table': '分组汇总', 'fields': ['分组', '当月折旧_元有效数', '当月折旧_元汇总', '期末账面价值_元有效数', '期末账面价值_元汇总']}]}, {'key': 'C4_uncertainty', 'title': '缺口原因与未知范围', 'weight': 10, 'capability': None, 'domains': [{'table': '计算明细', 'fields': ['记录ID', '状态']}, {'table': '缺口清单', 'fields': ['记录ID', '指标', '原因', '主记录来源', '关联来源']}]}]}

"""Embedded grader; CONFIG is injected by the task authoring pipeline."""
from pathlib import Path
from collections import Counter
import json, math, re
import openpyxl

def _read(path, schemas):
    if not path.is_file(): return {s:[] for s in schemas},['文件不存在']
    tables={s:[] for s in schemas}; errors=[]
    try:
        book=openpyxl.load_workbook(path,read_only=True,data_only=True)
        for name,fields in schemas.items():
            if name not in book.sheetnames:
                errors.append('缺少工作表:'+name);continue
            header=None
            for values in book[name].iter_rows(values_only=True):
                labels=[str(v).strip() if v is not None else '' for v in values]
                if set(fields).issubset(labels):
                    if any(labels.count(f)!=1 for f in fields):errors.append('重复字段:'+name);continue
                    header={f:labels.index(f) for f in fields};continue
                if header is None or not any(v is not None for v in values):continue
                tables[name].append({f:values[i] if i<len(values) else None for f,i in header.items()})
            if header is None:errors.append('缺少表头:'+name)
        book.close()
    except Exception as exc: errors.append(type(exc).__name__+':'+str(exc)[:180])
    return tables,errors

def _norm(value, field):
    if value is None or (isinstance(value,str) and value.strip() in ('','未知','不适用','N/A')):return None
    if isinstance(value,str):
        value=value.strip()
        if field.endswith('来源'):return ';'.join(sorted(set(t.strip() for t in value.split(';') if t.strip())))
    return value

def _equal(expected,actual,field):
    expected=_norm(expected,field);actual=_norm(actual,field)
    if expected is None or actual is None:return expected is actual
    if isinstance(expected,(int,float)) and not isinstance(expected,bool):
        try:
            v=float(str(actual).replace(',',''));return math.isfinite(v) and abs(expected-v)<=0.000002
        except (ValueError,TypeError):return False
    return str(expected)==str(actual)

def _domain(expected,actual,table,fields):
    keys=CONFIG['keys'][table]
    def key(row):return tuple(str(_norm(row.get(k),k)) for k in keys)
    erows=expected[table];arows=actual[table]
    e={key(r):r for r in erows};a={key(r):r for r in arows}
    if len(e)!=len(erows):raise RuntimeError('私有参考答案含重复主键:'+table)
    if len(a)!=len(arows) or set(e)!=set(a):return False,{'expected_rows':len(e),'actual_rows':len(arows),'key_set_match':False}
    bad=[]
    for identity,row in e.items():
        for f in fields:
            if not _equal(row[f],a[identity].get(f),f):
                if len(bad)<5:bad.append({'key':identity,'field':f})
    return not bad,{'expected_rows':len(e),'actual_rows':len(arows),'first_mismatches':bad}

def grade(transcript:list, workspace_path:str)->dict:
    root=Path(workspace_path)
    gt_path=root/'gt'/CONFIG['output']
    if not gt_path.is_file():raise RuntimeError('评测材料缺失：gt参考工作簿不存在')
    expected,errors=_read(gt_path,CONFIG['schema'])
    if errors or len(expected['计算明细'])!=CONFIG['rows'] or not expected['分组汇总']:
        raise RuntimeError('私有参考答案损坏或规模不符:'+str(errors))
    actual,read_errors=_read(root/'results'/CONFIG['output'],CONFIG['schema'])
    scores={};diagnostics={'read_errors':read_errors,'checkpoint_domains':{}}
    for check in CONFIG['checks']:
        outcomes=[];info=[]
        for domain in check['domains']:
            passed,details=_domain(expected,actual,domain['table'],domain['fields'])
            outcomes.append(passed);info.append(details)
        # Exactly two complete business domains per criterion: 0 / 0.5 / 1.
        scores[check['key']]=sum(outcomes)/2
        diagnostics['checkpoint_domains'][check['key']]=info
    scores['overall_score']=sum(c['weight']*scores[c['key']] for c in CONFIG['checks'])/80
    scores['diagnostics']=diagnostics
    report_path=root/'results'/'分析说明.md'
    report=report_path.read_text(encoding='utf-8-sig') if report_path.is_file() else ''
    evidence={'schema':'domain-expansion-20261019-v1','report_file':'results/分析说明.md',
      'report_present':report_path.is_file(),'report':report[:40000],
      'report_truncated':len(report)>40000,
      'candidate_summary':actual['分组汇总'][:100],
      'summary_truncated':len(actual['分组汇总'])>100,
      'reference_summary':expected['分组汇总'],
      'reference_status_counts':dict(Counter(r['状态'] for r in expected['计算明细'])),
      'reference_gap_reasons':dict(Counter(r['原因'] for r in expected['缺口清单'])),
      'automatic_diagnostics':diagnostics,
      'boundary':'规则回放不是Agent执行或自检证据；报告涉及具体原始记录时须回查相应工作簿。'}
    evidence_path=root/'评分证据'/'分析证据.json';evidence_path.parent.mkdir(exist_ok=True)
    evidence_path.write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
    return scores

```

## LLM Judge Rubric

### Criterion 1: 两项指标比较与建议 (key: C5_findings, weight: 12)

**Score 1.0**: 两项指标各有至少一项正确的分组比较，数值、分母、汇总口径均与公开材料及实际结果一致，给出可回查的分组及字段定位，并各有一条与比较相符的复核或处理建议。

**Score 0.5**: 仅一项指标完整满足上述比较、定位和建议要求；另一项缺失或不成立。

**Score 0.0**: 两项指标均没有完整成立的比较、定位和建议。

### Criterion 2: 缺口与统计边界 (key: C6_limits, weight: 8)

**Score 1.0**: 说明至少一种实际缺口的正确数量、影响指标及分母限制；同时明确本题描述范围或观察限制，不将未知填零，不把模拟比较推断为现实总体、因果或政策结论。

**Score 0.5**: 仅完整做到缺口数量与影响说明、统计结论边界说明中的一项。

**Score 0.0**: 两项均未完整做到，或存在与实际缺口直接矛盾的全量完成断言。

## Workspace Path

workspace/general_e2e/03_Data_Analysis_task/03_Data_Analysis_task_039_asset_depreciation_disposal_cutoff

## Skills

## Env

## Warmup
