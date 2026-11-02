---
id: 03_Data_Analysis_task_013_collaboration_team_activation_seat_retention
name: Collaboration Product Team Activation and Seat Retention
category: data-analysis
timeout_seconds: 7200
modality: pure-text
difficulty: L4
grading_type: hybrid
grading_weights:
  automated: 0.75
  llm_judge: 0.25
tags:
  - custom
  - general_e2e
  - business
judge_evidence:
  required:
    - path: 评分证据/指标与分析.json
      role: grader_generated_evidence
    - path: 评分证据/工具局部更新.json
      role: grader_generated_evidence
---

## Prompt

帮我分析协作产品的团队启用和成员持续使用情况，说明主要问题和改进建议，并校正已有分析。资料和口径说明在 `/tmp_workspace/`。分析结果保存为 `/tmp_workspace/results/用户行为分析.xlsx`，结论说明保存为 `/tmp_workspace/results/分析与验收.md`。 另外按 `/tmp_workspace/旧表更新交付.md` 的指定范围交回 `/tmp_workspace/results/已有分析_更新.xlsx`。

## Expected Behavior

依据公开口径遍历全部渠道周表和补充区块；稳定ID关联用户、对象及有效版本。按本题团队成员时效与双粒度分母重算漏斗和留存，隔离未知、不适用与确认零。保留全量来源定位，识别并修正旧表将事件行数作为去重对象数的缺陷。输出可复算指标、图表及有限定条件的分析，记录实际核对依据。另交按公开范围更新的旧表副本，准确落实C1:C4，保留非目标内容；该动作须由真实调用及产物支持。

## Grading Criteria

评分版本 tool-patch-v2-20261019；原业务口径沿用behavior-20261015-v1。公开依据为Prompt采用的《分析口径与交付.docx》（TXT为等内容副本）、《旧表更新交付.md》和原始工作簿；GT不增加要求。本版本新增交付与C8，不用于追溯重评旧版本。自动规则75分，Judge25分。所有单项仅为0、0.5、1；加权组分允许小数。原分析工作簿允许调整行列顺序、增加附加列，并接受真实Excel百分比格式和同义未知标记；新增的已有分析_更新.xlsx须依《旧表更新交付.md》遵守指定坐标和非目标保留要求。表名与字段名是公开下游接口；无法识别的等价表达、缺公式缓存须人工复核，不能自动当成业务0分。GT缺失或损坏抛出评测异常。

| 检查点 | 分值 | 公开依据和档位 |
| --- | ---: | --- |
| C1_scope 范围及来源集合 | 10 | 第1页范围及来源、第3页交付；六表主键集合均精确且无重复1，每表至少有一个正确对象但不完整0.5，否则0 |
| C2_link 身份版本及链路关联 | 12 | 第1页字段版本、第2页链路；来源事件身份/标准事件域、对象归属/起点/步骤完成事件域均完整1，仅一个域完整0.5，均不完整0 |
| C3_funnel 有序漏斗 | 20 | 第2页漏斗与精度；逐对象步骤标志、全部渠道漏斗汇总两域均正确1，仅一域正确0.5，否则0 |
| C3_retention 留存计算 | 18 | 第2页留存与分母；成熟对象留存值、渠道留存分子分母和率两域均正确1，仅一域正确0.5，否则0 |
| C4_unknown 缺口与观察期 | 10 | 第1页缺口、第2页观察状态；全量事件处置与对象观察状态域、非成熟值及汇总缺口计数域均正确1，仅一域正确0.5，否则0；重复代表行可不同但每个有效事件恰好一条纳入 |
| C5_revision 旧表数值修正 | 5 | 第2页旧表校核；三渠道原值、修正值和差额均正确1，至少一渠道完整正确0.5，否则0 |
| C1_actual 实际范围覆盖 | 5 | 第1页范围、第3页实际核对；见Judge |
| C5_detect 重复计数缺陷识别 | 5 | 第2页旧表校核；见Judge |
| C6_analysis 图表与分析 | 5 | 第3页分析和实际核对；见Judge |
| C7_validation 实际验收 | 5 | 第3页分析和实际核对；见Judge |
| C8_tool_patch 指定区域更新 | 5 | 《旧表更新交付.md》；真实调用证据齐全时，目标域与保留域均完整1，仅一个完整0.5，否则0；见Judge证据与归因边界 |

各域必须覆盖全量应有对象才算完整；自动规则只判断产物。规则组 overall_score=Σ(分值×得分)/75；Judge组=Σ(分值×得分)/25；总分=75×规则组+25×Judge组。C1_actual、C7_validation和C8_tool_patch依赖真实轨迹和产物，不以产物正确代替过程；轨迹或关键证据采集缺失记为不可判定，停止正式总分，不以0占位或删项重归一。完整证据证明未做要求才计0。不存在实际Agent运行时只报告规则作者自检。

C8的5分由未映射能力的C6_analysis原10分中调整，C6现为5分；不改变自动75/Judge25/总100分结构。C8文件比较只生成诊断事实，过程分须独立核验真实调用；缺证据时不得使用通用Judge失败回退的0分。

## Automated Checks

```python
"""Embedded standalone; only public output interface and private numerical oracle."""
from pathlib import Path
import json, math
from collections import Counter, defaultdict
import openpyxl

WEIGHTS={'C1_scope':10,'C2_link':12,'C3_funnel':20,'C3_retention':18,'C4_unknown':10,'C5_revision':5}
KEYS={'对象漏斗':['对象编号'],'留存明细':['对象编号','留存周期'],'漏斗汇总':['归属渠道','步骤'],'留存汇总':['归属渠道','留存周期'],'来源索引':['来源定位'],'旧表校核':['归属渠道','指标']}

def norm(v):
    if v is None:return ''
    if isinstance(v,str):return v.strip()
    return v

def eq(a,b):
    if isinstance(b,(float,int)) and not isinstance(b,bool):
        try:
            if isinstance(a,bool):return False
            value=float(a[:-1])/100 if isinstance(a,str) and a.endswith('%') else float(a)
            return math.isfinite(value) and abs(value-b)<=0.00000051
        except (TypeError,ValueError):return False
    synonyms={'待确认':'未知','未成熟':'观察不足','N/A':'不适用'}
    return synonyms.get(norm(a),norm(a))==norm(b)

def grade(transcript:list,workspace_path:str)->dict:
    root=Path(workspace_path)
    # Missing/corrupt private oracle is an evaluation failure, never a candidate zero.
    reference=json.loads((root/'gt'/'标准答案.json').read_text(encoding='utf-8'))
    for name in KEYS:
        if not isinstance(reference.get(name),list) or not reference[name]:raise ValueError('Invalid oracle: '+name)
    candidate={name:[] for name in KEYS};failure=None
    p=root/'results'/'用户行为分析.xlsx'
    if p.exists():
        try:
            wb=openpyxl.load_workbook(p,data_only=True)
            for name in KEYS:
                if name not in wb:continue
                rows=list(wb[name].values)
                # Exact table/field names are public; blank leading rows and column order are harmless.
                header_at=next((i for i,r in enumerate(rows) if set(KEYS[name]).issubset(set(r))),None)
                if header_at is None:continue
                headers=[norm(x) for x in rows[header_at]]
                for row in rows[header_at+1:]:
                    if any(x is not None for x in row):candidate[name].append(dict(zip(headers,row)))
            wb.close()
        except (OSError,ValueError,KeyError,openpyxl.utils.exceptions.InvalidFileException) as exc:failure=str(exc)
        except Exception as exc:
            # Broken submitted ZIP/XML is a submitted-file defect, but do not hide implementation faults.
            from zipfile import BadZipFile
            from xml.etree.ElementTree import ParseError
            if isinstance(exc,(BadZipFile,ParseError)):failure=str(exc)
            else:raise
    def keyed(rows,name):
        out=defaultdict(list)
        for r in rows:out[tuple(norm(r.get(k)) for k in KEYS[name])].append(r)
        return out
    refs={n:keyed(reference[n],n) for n in KEYS};actual={n:keyed(candidate[n],n) for n in KEYS}
    exact={n:set(refs[n])==set(actual[n]) and all(len(x)==1 for x in actual[n].values()) for n in KEYS}
    def correct(name,fields,predicate=lambda r:True):
        expected=[r for r in reference[name] if predicate(r)]
        if not exact[name]:return False
        return all(all(eq(actual[name][tuple(norm(r[k]) for k in KEYS[name])][0].get(f),r[f]) for f in fields) for r in expected)
    def band(*parts):return 1.0 if all(parts) else (0.5 if any(parts) else 0.0)
    scores={}
    scores['C1_scope']=1.0 if all(exact.values()) else (0.5 if all(any(k in refs[n] for k in actual[n]) for n in KEYS) else 0.0)
    scores['C2_link']=band(correct('来源索引',['事件编号','对象编号','标准事件']),correct('对象漏斗',['归属渠道','起点日期','步骤1事件','步骤2事件','步骤3事件']) and correct('留存明细',['归属渠道','起点日期']))
    scores['C3_funnel']=band(correct('对象漏斗',['步骤1','步骤2','步骤3']),correct('漏斗汇总',['步骤名称','成熟基数','到达数','上步数','步骤转化率','累计转化率']))
    scores['C3_retention']=band(correct('留存明细',['留存值'],lambda r:r['观察状态']=='完整观察'),correct('留存汇总',['可观察基数','留存数','留存率']))
    # Duplicate representatives may differ, but each valid event must have exactly one included location.
    astate=defaultdict(Counter);rstate=defaultdict(Counter)
    for rows,dst in [(candidate['来源索引'],astate),(reference['来源索引'],rstate)]:
        for r in rows:dst[r.get('事件编号')][r.get('处理状态')]+=1
    statuses=exact['来源索引'] and astate==rstate and correct('对象漏斗',['漏斗状态']) and correct('留存明细',['观察状态'])
    unknowns=correct('留存明细',['留存值'],lambda r:r['观察状态']!='完整观察') and correct('留存汇总',['观察不足数','不适用数'])
    scores['C4_unknown']=band(statuses,unknowns)
    matched=[]
    for r in reference['旧表校核']:
        rr=actual['旧表校核'].get(tuple(r[k] for k in KEYS['旧表校核']),[])
        matched.append(len(rr)==1 and all(eq(rr[0].get(f),r[f]) for f in ['原值','修正值','差额']))
    scores['C5_revision']=1.0 if exact['旧表校核'] and all(matched) else (0.5 if any(matched) else 0.0)
    evidence={'输出存在':p.exists(),'读取失败':failure,'对象集合精确':exact,'规则得分':scores,'汇总与修订':{n:candidate[n] for n in ['漏斗汇总','留存汇总','旧表校核']},'来源索引样例':candidate['来源索引'][:12],'说明':'样例不代表全量过程；实际范围与验收须结合真实轨迹。完整源文件可回查。'}
    narrative=root/'results'/'分析与验收.md'
    evidence['分析与验收']=narrative.read_text(encoding='utf-8') if narrative.exists() else '未交付'
    evidence['图表数']=0
    if p.exists() and failure is None:
        from xml.etree.ElementTree import tostring
        w=openpyxl.load_workbook(p);evidence['图表数']=sum(len(s._charts) for s in w)
        evidence['图表定义与数据']=[]
        for s in w:
            for chart in s._charts:
                tree=chart.to_tree();refs={el.text for el in tree.iter() if el.tag.split('}')[-1]=='f' and el.text}
                samples={}
                for ref in refs:
                    if '!' not in ref:continue
                    sn,area=ref.rsplit('!',1);sn=sn.strip("'").replace("''", "'")
                    if sn in w:
                        try:samples[ref]=[[cell.value for cell in row] for row in w[sn][area]]
                        except (ValueError,TypeError):samples[ref]='引用无法提取，须复核原图'
                evidence['图表定义与数据'].append({'工作表':s.title,'图表XML':tostring(tree,encoding='unicode'),'引用数据':samples})
        if any(cell.data_type=='f' for s in w for row in s for cell in row):
            cached=openpyxl.load_workbook(p,data_only=True)
            missing=[f'{s.title}!{cell.coordinate}' for s in w for row in s for cell in row if cell.data_type=='f' and cached[s.title][cell.coordinate].value is None]
            cached.close()
            if missing:raise ValueError('需复核公式缓存，不得计有效零分: '+','.join(missing[:10]))
        w.close()
    out=root/'评分证据';out.mkdir(exist_ok=True)
    (out/'指标与分析.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    return {**scores,'overall_score':sum(WEIGHTS[k]*v for k,v in scores.items())/75,'diagnostics':{'exact_sets':exact,'read_error':failure}}

def collect_tool_patch_evidence(workspace_path):
    """Evaluator observations only: never infer an Agent action or award a score."""
    from pathlib import Path
    import json
    import math
    import hashlib
    import openpyxl

    root = Path(workspace_path)
    baseline_path = root / 'gt' / '工具局部更新基线.xlsx'
    output_path = root / 'results' / '已有分析_更新.xlsx'
    analysis_path = root / 'results' / '用户行为分析.xlsx'
    original_path = root / '已有分析.xlsx'

    def book_values(path, data_only=False):
        wb = openpyxl.load_workbook(path, read_only=True, data_only=data_only)
        try:
            values = {}
            for sheet in wb:
                cells = {}
                for row in sheet.iter_rows():
                    for cell in row:
                        if cell.value is not None:
                            cells[cell.coordinate] = cell.value
                values[sheet.title] = cells
            return list(wb.sheetnames), values
        finally:
            wb.close()

    def equivalent(a, b):
        # Equivalent numeric cell encodings are accepted; formulas are not executed.
        if isinstance(a, bool) or isinstance(b, bool):
            return type(a) is type(b) and a == b
        if a == b:
            return True
        try:
            return math.isfinite(float(a)) and math.isfinite(float(b)) and float(a) == float(b)
        except (TypeError, ValueError):
            return False

    names, baseline = book_values(baseline_path)  # Bad private baseline is an evaluator error.
    if names != ['历史漏斗'] or baseline['历史漏斗'].get('C1') != '原值':
        raise ValueError('Invalid frozen tool-patch baseline')
    target_keys = [('自然访问', '首步骤去重对象数'), ('内容推荐', '首步骤去重对象数'), ('合作推广', '首步骤去重对象数')]
    if baseline['历史漏斗'].get('A1') != '归属渠道' or baseline['历史漏斗'].get('B1') != '指标':
        raise ValueError('Invalid frozen baseline headers')
    for row, key in enumerate(target_keys, 2):
        if (baseline['历史漏斗'].get(f'A{row}'), baseline['历史漏斗'].get(f'B{row}')) != key:
            raise ValueError('Invalid frozen baseline target keys')
    allowed = {'C1', 'C2', 'C3', 'C4'}
    evidence = {
        'version': 'tool-patch-v2-20261019-evidence-fix-20261028',
        'capability': 'tool_invocation#9',
        'candidate_output': str(output_path.relative_to(root)),
        'target_cells': sorted(allowed),
        'target_domain': None,
        'preservation_domain': None,
        'original_input_preservation': None,
        'output_preservation': None,
        'original_input_snapshot': None,
        'original_input_differences': [],
        'baseline_snapshot': {'sheet_names': names, 'cells': baseline},
        'baseline_sha256': hashlib.sha256(baseline_path.read_bytes()).hexdigest(),
        'target_comparisons': [],
        'non_target_differences': [],
        'score': None,
        'status': 'requires_independent_trace_review',
        'boundary': 'These are evaluator file observations, not Agent actions or self-validation. '
                    'Never award a process score from this JSON alone. Candidate-authored claims are not trace evidence.',
    }
    try:
        original_names, original = book_values(original_path)
        evidence['original_input_state'] = 'readable'
        evidence['original_input_snapshot'] = {'sheet_names': original_names, 'cells': original}
        evidence['original_input_sha256'] = hashlib.sha256(original_path.read_bytes()).hexdigest()
    except Exception as exc:
        evidence['original_input_state'] = 'unavailable_requires_review'
        evidence['original_input_error'] = type(exc).__name__ + ': ' + str(exc)
    else:
        source_differences = []
        if names != original_names:
            source_differences.append({'kind': 'sheet_names_or_order', 'before': names, 'after': original_names})
        for sheet in sorted(set(baseline) | set(original)):
            a, b = baseline.get(sheet, {}), original.get(sheet, {})
            for cell in sorted(set(a) | set(b)):
                # The original has no allowed edit area, including C1:C4.
                if not equivalent(a.get(cell), b.get(cell)):
                    source_differences.append({'sheet': sheet, 'cell': cell, 'before': a.get(cell), 'after': b.get(cell)})
        evidence['original_input_differences'] = source_differences
        evidence['original_input_preservation'] = not source_differences
    if not output_path.is_file():
        evidence['output_state'] = 'missing'
        evidence['target_domain'] = False
        evidence['output_preservation'] = False
    else:
        try:
            out_names, output = book_values(output_path)
            evidence['output_state'] = 'readable'
            evidence['output_sha256'] = hashlib.sha256(output_path.read_bytes()).hexdigest()
        except Exception as exc:
            evidence['output_state'] = 'unreadable_requires_review'
            evidence['read_error'] = type(exc).__name__ + ': ' + str(exc)
        else:
            differences = []
            if names != out_names:
                differences.append({'kind': 'sheet_names_or_order', 'before': names, 'after': out_names})
            for sheet in set(baseline) | set(output):
                a, b = baseline.get(sheet, {}), output.get(sheet, {})
                for cell in sorted(set(a) | set(b)):
                    if sheet == '历史漏斗' and cell in allowed:
                        continue
                    if not equivalent(a.get(cell), b.get(cell)):
                        differences.append({'sheet': sheet, 'cell': cell, 'before': a.get(cell), 'after': b.get(cell)})
            evidence['non_target_differences'] = differences
            evidence['output_preservation'] = not differences
            try:
                wb = openpyxl.load_workbook(analysis_path, read_only=True, data_only=True)
                try:
                    rows = list(wb['旧表校核'].values)
                finally:
                    wb.close()
                fields = ['归属渠道', '指标', '修正值']
                header_at = next(i for i, row in enumerate(rows) if set(fields).issubset({str(v).strip() for v in row if v is not None}))
                header = [str(v).strip() if v is not None else '' for v in rows[header_at]]
                columns = [header.index(k) for k in ['归属渠道', '指标', '修正值']]
                transferred = {}
                for row in rows[header_at + 1:]:
                    if all(v is None for v in row):
                        continue
                    key = tuple(str(row[c]).strip() for c in columns[:2])
                    if key not in target_keys:
                        continue
                    if key in transferred and not equivalent(transferred[key], row[columns[2]]):
                        raise ValueError('Ambiguous candidate key: ' + str(key))
                    transferred[key] = row[columns[2]]
                checks = [{'cell': 'C1', 'expected': '修正值', 'observed': output.get('历史漏斗', {}).get('C1')}]
                for row in range(2, 5):
                    key = (baseline['历史漏斗'][f'A{row}'], baseline['历史漏斗'][f'B{row}'])
                    value = transferred[key]
                    if value is None:
                        raise ValueError('Missing candidate update value: ' + str(key))
                    checks.append({'cell': f'C{row}', 'key': list(key), 'expected': value,
                                   'observed': output.get('历史漏斗', {}).get(f'C{row}')})
                _, cached_output = book_values(output_path, data_only=True)
                for check in checks:
                    observed = check['observed']
                    if isinstance(observed, str) and observed.startswith('='):
                        cached = cached_output.get('历史漏斗', {}).get(check['cell'])
                        check['formula'] = observed
                        check['cached_value'] = cached
                        check['matches_candidate_value'] = None if cached is None else equivalent(cached, check['expected'])
                    else:
                        check['matches_candidate_value'] = equivalent(observed, check['expected'])
                evidence['target_comparisons'] = checks
                evidence['target_domain'] = None if any(c['matches_candidate_value'] is None for c in checks) else all(c['matches_candidate_value'] for c in checks)
            except Exception as exc:
                evidence['candidate_value_source_status'] = 'unavailable_or_ambiguous_requires_trace_review'
                evidence['candidate_value_source_error'] = type(exc).__name__ + ': ' + str(exc)
    preservation = [evidence['original_input_preservation'], evidence['output_preservation']]
    evidence['preservation_domain'] = None if any(value is None for value in preservation) else all(preservation)
    evidence_dir = root / '评分证据'
    evidence_dir.mkdir(exist_ok=True)
    (evidence_dir / '工具局部更新.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    return evidence


_grade_business_v1 = grade

def grade(transcript: list, workspace_path: str) -> dict:
    result = _grade_business_v1(transcript, workspace_path)
    collect_tool_patch_evidence(workspace_path)
    return result

```

## LLM Judge Rubric

### Criterion 1: 实际范围覆盖 (key: C1_actual, weight: 5)

**Score 1.0**: 真实操作及产物共同证明处理了目标对象、用户、版本与全部27张渠道周表的两段日志，排除测试与非明细。
**Score 0.5**: 有实际处理多源的证据，但遗漏部分渠道周表或补充区块，仍能定位已处理范围。
**Score 0.0**: 完整轨迹证明仅沿用旧表或未处理目标日志。轨迹缺失为不可判定，不计有效0。

### Criterion 2: 旧表重复计数缺陷识别 (key: C5_detect, weight: 5)

**Score 1.0**: 产物结合回答或真实轨迹证明识别事件行数与去重对象数的混用，用可回查事件或对象支持针对性修正或明确判旧表未通过。
**Score 0.5**: 识别混用并处理旧表，但无可回查例证，或只对部分渠道给出针对性解释。
**Score 0.0**: 完整证据表明采信旧表、未识别缺陷，或只说有差异但未识别重复计数问题。数值正确性单独由C5_revision评分。

### Criterion 3: 图表结论与可确认范围 (key: C6_analysis, weight: 5)

**Score 1.0**: 漏斗与留存图表区分渠道及步骤/周期；最大流失、渠道差异和留存结论引用正确可比指标，解释缺口与观察窗口限制，并给出有据建议且不宣称因果。
**Score 0.5**: 漏斗、留存两类分析至少一类有正确图表和数字依据，但另一类缺失，或缺口限制/建议不完整；主要结论不违背已知数据。
**Score 0.0**: 两类均无有效图表和数字依据，或主要结论建立在错误分母、将未知当零或无依据因果之上。若证据采集未提供必要图表内容，应回查完整工作簿，不能把未采集当缺交付。

### Criterion 4: 实际验收覆盖 (key: C7_validation, weight: 5)

**Score 1.0**: 真实核对及记录覆盖跨sheet/区块范围、分母、公式或等价计算、图表和结论四类对象；记录检查方法、结果与未验证范围，且旧表修正值得到复核。
**Score 0.5**: 实际完成四类中至少两类有效核对并留有记录，但覆盖不全或修正后未复核。
**Score 0.0**: 完整证据表明有效核对不足两类，只有写入成功或空泛自述。缺真实轨迹或关键回执为不可判定，不以产物正确推定验收。

### Criterion 5: 指定区域更新与非目标内容保留 (key: C8_tool_patch, weight: 5)

公开依据：Prompt采用的《旧表更新交付.md》。主映射为工具调用 #9“局部修改准确落实”。按候选本次“旧表校核”已明确的渠道＋指标键值判断内容传递与位置落实，不以私有业务标准值替代候选当次值。

评分前先核对系统采集的真实执行轨迹：关联实际调用ID、调用参数或调用所执行的脚本、返回结果以及输出前后文件。外部执行证据须能定位更新动作、实际目标路径及其结果；创建内容等价工作簿也可，不指定软件或复制API，不强求先保存分析再读回。候选自写日志、自述、两份终态表一致或评分程序成功读取文件都不能独立充当实际调用证据。

在真实执行及关键结果可核验的前提下判断两个独立域：
A. C1为“修正值”，C2:C4准确承接本次明确键值，目标位置与内容均完整；可用同一内存结果。
B. 原件已有分析.xlsx的全部单元格值或公式、行列位置、工作表名称与顺序保持，原件C1:C4也不豁免；更新副本的非目标单元格值或公式及位置、表名与顺序同样保持。两部分均完整才算本域完整。格式、文件字节及内部XML不纳入，SHA仅作版本诊断，不能因元数据差异直接判失败。原件内容差异须结合完整真实轨迹确认操作归因，不猜测修改者。

**Score 1.0**: 两个域均完整，且真实调用、返回与产物共同支持。
**Score 0.5**: 仅一个域完整，且真实执行证据足以归因；例如仅复制旧表并交付、目标要求尚未满足而保留域完整，或目标写对但覆盖了其他内容。
**Score 0.0**: 两个域均不完整。完整轨迹及交付证据证明缺少更新副本时，目标域及副本保留要求均未满足；仅复制旧表的情形按两个域评价，不因“未执行更新”另行覆盖0.5档。文件不可读的原因或操作结果无法确认时先复核，不能将证据缺失、外部工具故障或评测读取限制当作有效0。

边界：本次已明确的数值恰与旧表相同时，不要求再次改写这些数值或必须观察到内容变化；真实复制或等价生成也可作为执行证据，仍须满足公开C1标题“修正值”及各目标位置要求。上游计算或业务归组错误由原业务项评价；即使业务值错，只要本次已明确的键值忠实落到正确位置，也可得本项满分。不得把同一上游错误重复归因于本项。是否主动验收仍由C7评价，评测方文件比较不是Agent主动验收。

不可判定：轨迹、关键回执缺失，候选取值来源无法确定，公式缓存不足或环境故障使操作结果不可验证，均须回查原始证据，未解决前不形成有效C8分或正式总分，不删除该项重新归一。评分证据/工具局部更新.json只有基线、原件现状、候选供值及副本的文件事实和score=null，不会自动给过程能力分；两个布尔域也必须结合真实轨迹复核。现有通用Judge接口只接受数值且失败可回退0，本题的“不可判定”须由正式结果验收独立执行：不得直接采信该回退分或框架数值总分，须先完成证据审核。

## Workspace Path

workspace/general_e2e/03_Data_Analysis_task/03_Data_Analysis_task_013_collaboration_team_activation_seat_retention

## Skills

## Env

## Warmup
