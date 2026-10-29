---
id: 03_Data_Analysis_task_016_store_campaign_cost_allocation_comparability
name: Chain Store Campaign Cost Allocation and Regional Comparability
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
- marketing
judge_evidence:
  required:
  - path: 评分证据/营销分析.json
    role: grader_generated_evidence
  - path: 评分证据/汇总回填.json
    role: grader_generated_evidence
---

## Prompt

帮我分析两个活动的门店渠道表现，说明费用分摊、区域结构对比较的影响及投入建议，更新已有汇总。资料及采用的口径说明在 `/tmp_workspace/`，结果放在 `/tmp_workspace/results/营销分析.xlsx`，分析与验收说明放在 `/tmp_workspace/results/分析与验收.md`。 另按 `/tmp_workspace/汇总回填交付.md` 将本次费用和净额回填到旧表副本，交付 `/tmp_workspace/results/旧版渠道汇总_回填.xlsx`。

## Expected Behavior

覆盖全部有效区块，采用V2明细完成连锁门店活动费用分摊与区域可比分析。保留未知与不可比范围，交付可复算指标、来源、图表、版本校核及实际验收记录。

按《汇总回填交付.md》以活动、渠道、分层绑定本次版本校核值，追加Q:R且保留原历史区域；实际操作、返回与产物应可关联，不以业务数值正确代替操作证据。

## Grading Criteria

评分版本：marketing-summary-patch-v1-20261028。规则80分，Judge20分。唯一公开依据为Prompt采用的《归因与分析口径.docx》（TXT同内容）、《汇总回填交付.md》及原始附件。原自动规则及其权重不变，图表分析预算为6分，新增回填操作4分；原分析语义判据保留。各单项只取0/0.5/1；C1_scope仅0/1。字段、表名是公开下游接口；原营销分析允许调整行列顺序，回填副本遵守公开指定位置及非目标保留约定；数值与等值百分数均可。GT缺失损坏为评测错误。

|正式评分点|分值|公开依据与判据|
|---|---:|---|
|automated.C1_scope 跨表范围与对象覆盖|10|口径一范围及三交付接口。全部主键集合一致且无重复1，否则0。域：归因明细[@keys]；渠道指标[@keys]；费用分摊[@keys]；来源索引[@keys]；标准化比较[@keys]；版本校核[@keys]|
|automated.C2_current 最新版本与旧表更新|8|口径一版本，三版本校核。两域均完整正确1，仅一域完整正确0.5，否则0。域：来源索引[类别、记录编号、版本、采用状态] / 版本校核[旧净额、最新净额、净额变化、旧费用、最新费用、费用变化]|
|automated.C3_attribution 核销码优先及门店关联|14|口径二本题归因及支付退款规则。两域均完整正确1，仅一域完整正确0.5，否则0。域：归因明细[活动、渠道、分层、归因状态、触点编号] / 归因明细[订单编号集合、退款编号集合]|
|automated.C3_metrics 分层分摊及标准化可比率|26|口径二完整指标与分摊规则。两域均完整正确1，仅一域完整正确0.5，否则0。域：归因明细[支付额、退款额、净额、转化数]；费用分摊[活动、渠道、费用、权重来源] / 渠道指标[对象数、成熟对象数、观察不足数、转化数、费用、净额、获客成本、净回报倍数、线索获取率、转化率]；标准化比较[标准化转化率、原始合并转化率]|
|automated.C4_unknown 缺口与可比范围|12|口径一缺失语义及二分母/成熟度。两域均完整正确1，仅一域完整正确0.5，否则0。域：归因明细[成熟状态、归因状态] / 渠道指标[外部分母、转化率、线索获取率]|
|automated.C5_source 来源可追溯与费用关联|10|口径二来源定位及三交付字段。两域均完整正确1，仅一域完整正确0.5，否则0。域：归因明细[对象来源、触点来源] / 费用分摊[费用来源、权重来源]|
|llm_judge.C1_actual 实际范围处理|5|口径一与三；实际范围处理证据，见Rubric|
|llm_judge.C6_analysis 图表与可比分析|6|口径三；保留原图表、比较、方法与限制判据，见Rubric|
|llm_judge.C7_validation 实际验收及差异处置|5|口径三；真实检查与记录，见Rubric|
|llm_judge.C8_tool_patch 汇总回填与历史内容保留|4|汇总回填交付；真实操作证据充分后，回填域与保留域均完整1，仅一域完整0.5，否则0|

每域要求全量应有行，金额容差0.00000051元、比率容差0.00000051。来源索引按公开唯一坐标比较；集合字段允许重排。自动组分=Σ(权重×档位)/80；Judge组=Σ(权重×档位)/20；总分为两组合计100分。复杂等价表达或公式缓存缺失转人工复核，不直接据接口读取失败推断业务错误。

C1_actual、C7_validation、C8_tool_patch需要真实轨迹；关键轨迹缺失时不可判定并停止正式总分，不补零或重分配权重。作者自检不代表Agent或Judge得分。

能力映射使用capabilities-2026-09-23-v1：C1_actual对应intent_understanding#3，C2_current对应state_awareness#7，C3_attribution与C3_metrics对应reasoning_and_decision_making#1，C7_validation对应result_evaluation#1，C8_tool_patch对应tool_invocation#9。其余项只计题目分。题目分为全部项的真实题目权重乘得分之和，满分100；有效映射预算为62分，能力总分为100×(8×automated.C2_current+14×automated.C3_attribution+26×automated.C3_metrics+5×llm_judge.C1_actual+5×llm_judge.C7_validation+4×llm_judge.C8_tool_patch)/62。每维独立百分制为100×该维Σ(真实题目权重×得分)/该维权重之和，各维对能力总分的贡献上限为100×该维权重/62。不能简单平均各维百分制。未覆盖维度报告未覆盖；未触发、外部阻断、证据不足或评分器异常不能作为0或删除后重新归一。所有映射项有效后才输出正式能力总分；某维全部项有效时可单列该维。字段和业务正确性由原业务项负责，C8不重复归因；图表分析、实际验收与工具落实分别以其规定证据判断。

## Automated Checks

```python
"""Standalone numeric grading. All columns and bands are adopted in public contract."""
import json,math
from pathlib import Path
from collections import Counter
import openpyxl

KEYS={'归因明细':['对象编号'],'渠道指标':['活动','渠道','分层'],'费用分摊':['费用编号','分层'],'来源索引':['来源定位'],'版本校核':['活动','渠道','分层'],'标准化比较':['活动','渠道']}

def equal(a,b,field=''):
    if field.endswith('编号集合'):
        return set(str(a).split('|'))==set(str(b).split('|'))
    if isinstance(b,(int,float)):
        try:
            v=float(a[:-1])/100 if isinstance(a,str) and a.endswith('%') else float(a)
            return math.isfinite(v) and abs(v-b)<=0.00000051
        except (ValueError,TypeError):return False
    aliases={'待确认':'未知','N/A':'不适用','未成熟':'观察不足'}
    return aliases.get(str(a).strip(),str(a).strip())==str(b).strip()

def grade(transcript:list,workspace_path:str)->dict:
    root=Path(workspace_path)
    reference=json.loads((root/'gt'/'标准答案.json').read_text(encoding='utf-8'))
    contract=json.loads((root/'gt'/'评分配置.json').read_text(encoding='utf-8'))
    for name in reference:
        if name not in KEYS or not reference[name]:raise ValueError('Invalid oracle '+name)
        if len({tuple(r[x] for x in KEYS[name]) for r in reference[name]})!=len(reference[name]):raise ValueError('Duplicate oracle keys')
    candidate={n:[] for n in reference};charts=[];failure=None
    path=root/'results'/'营销分析.xlsx'
    if path.exists():
        try:
            wb=openpyxl.load_workbook(path,data_only=True)
            for name in candidate:
                if name not in wb:continue
                rows=list(wb[name].values)
                pos=next((i for i,r in enumerate(rows) if set(KEYS[name])<=set(r)),None)
                if pos is None:continue
                head=[str(x).strip() if x is not None else '' for x in rows[pos]]
                candidate[name]=[dict(zip(head,r)) for r in rows[pos+1:] if any(x is not None for x in r)]
            for sh in wb:
                for ch in sh._charts:
                    charts.append({'sheet':sh.title,'type':type(ch).__name__,'series':[str(s) for s in ch.series]})
            wb.close()
        except Exception as exc:
            from zipfile import BadZipFile
            if isinstance(exc,(BadZipFile,ValueError,OSError,KeyError)):failure=str(exc)
            else:raise
    def key(r,n):return tuple(str(r.get(c,'')).strip() for c in KEYS[n])
    def covered(n):return Counter(key(r,n) for r in candidate[n])==Counter(key(r,n) for r in reference[n])
    def domain(n,cols):
        if not covered(n):return False
        lookup={key(r,n):r for r in candidate[n]}
        return all(all(equal(lookup[key(r,n)].get(c),r[c],c) for c in cols) for r in reference[n])
    states={};scores={}
    for name,spec in contract['checks'].items():
        passed=[]
        for group in spec['domains']:
            passed.append(all(covered(n) if cols==['@keys'] else domain(n,cols) for n,cols in group.items()))
        states[name]=passed
        scores[name]=sum(passed)/len(passed)
        assert scores[name] in [0,.5,1]
    score=sum(contract['checks'][n]['weight']*s for n,s in scores.items())/80
    report=root/'results'/'分析与验收.md'
    evidence={'说明':'评分后提取，不是候选过程。来源与明细仅提供行数；完整文件可回查，不能据此推断实际验收。','读取错误':failure,'表行数':{n:len(r) for n,r in candidate.items()},'渠道指标':candidate['渠道指标'],'版本校核':candidate['版本校核'],'标准化比较':candidate.get('标准化比较',[]),'图表定义':charts,'分析与验收':report.read_text(encoding='utf-8') if report.exists() else None,'截断':False}
    out=root/'评分证据';out.mkdir(exist_ok=True)
    (out/'营销分析.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
    return {**scores,'overall_score':score,'details':{'domains':states,'read_error':failure}}

def collect_summary_patch_evidence(workspace_path):
    """Read-only file facts for an independent trace review; never assign C8."""
    import hashlib
    from decimal import Decimal, InvalidOperation

    root = Path(workspace_path).resolve()
    baseline_path = root / 'gt' / '工具回填基线.xlsx'
    output_path = root / 'results' / '旧版渠道汇总_回填.xlsx'
    source_path = root / 'results' / '营销分析.xlsx'
    original_path = root / '旧版渠道汇总.xlsx'

    def safe_path(path):
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError('Workbook path escapes grading workspace')

    def snapshot(path, sheets=None):
        safe_path(path)
        payload = path.read_bytes()
        wb = openpyxl.load_workbook(path, read_only=True, data_only=False, keep_links=False)
        cached = openpyxl.load_workbook(path, read_only=True, data_only=True, keep_links=False)
        try:
            cells = {}
            for sheet in wb:
                if sheets is not None and sheet.title not in sheets:
                    continue
                observed = {}
                for row in sheet.iter_rows():
                    for cell in row:
                        if cell.value is None:
                            continue
                        item = {'value': cell.value, 'type': cell.data_type}
                        if cell.data_type == 'f':
                            item['cached_value'] = cached[sheet.title][cell.coordinate].value
                            item['cached_type'] = cached[sheet.title][cell.coordinate].data_type
                        observed[cell.coordinate] = item
                cells[sheet.title] = observed
            return {'path': str(path.relative_to(root)), 'sha256': hashlib.sha256(payload).hexdigest(),
                    'size': len(payload), 'sheet_names': list(wb.sheetnames), 'cells': cells}
        finally:
            wb.close()
            cached.close()

    def equivalent(a, b):
        if isinstance(a, bool) or isinstance(b, bool):
            return type(a) is type(b) and a == b
        if a == b:
            return True
        try:
            x, y = Decimal(str(a).strip()), Decimal(str(b).strip())
            return x.is_finite() and y.is_finite() and x == y
        except (InvalidOperation, ValueError, TypeError):
            return False

    def resolved_value(item):
        if item is None or item.get('type') == 'e' or item.get('type') == 'f' and item.get('cached_type') == 'e':
            return None
        value = item.get('cached_value') if item.get('type') == 'f' else item['value']
        if isinstance(value, float) and not math.isfinite(value):
            return None
        return value

    def content_differences(before, after, allowed=None):
        differences = []
        if before['sheet_names'] != after['sheet_names']:
            differences.append({'kind': 'sheet_names_or_order', 'before': before['sheet_names'],
                                'after': after['sheet_names']})
        for sheet in sorted(set(before['cells']) | set(after['cells'])):
            a, b = before['cells'].get(sheet, {}), after['cells'].get(sheet, {})
            for cell in sorted(set(a) | set(b)):
                if sheet == '旧汇总' and allowed is not None and cell in allowed:
                    continue
                left, right = a.get(cell), b.get(cell)
                if not equivalent(None if left is None else left['value'],
                                  None if right is None else right['value']):
                    differences.append({'sheet': sheet, 'cell': cell, 'before': left, 'after': right})
        return differences

    before = snapshot(baseline_path)  # Missing/corrupt private baseline is an evaluator error.
    if before['sha256'] != '020caabec59479b17b3d6f88d239f7fa283a5767c1ece8135f2a30349b48b23c' or before['sheet_names'] != ['旧汇总']:
        raise ValueError('Invalid frozen summary-patch baseline')
    original = before['cells']['旧汇总']
    headers = ['活动', '渠道', '分层', '对象数', '成熟对象数', '观察不足数', '转化数', '费用',
               '净额', '外部分母', '转化率', '获客成本', '净回报倍数', '线索获取率', '生成版本', '生成时间']
    if [original.get(f'{chr(65 + i)}1', {}).get('value') for i in range(16)] != headers:
        raise ValueError('Invalid baseline headers')
    row_keys = {row: tuple(original[f'{column}{row}']['value'] for column in 'ABC')
                for row in range(2, 21 + 1)}
    if len(set(row_keys.values())) != len(row_keys):
        raise ValueError('Duplicate baseline business keys')
    allowed = {f'{column}{row}' for column in 'QR' for row in range(1, 21 + 1)}
    evidence = {
        'version': 'marketing-summary-patch-v1-20261028',
        'capability': 'capabilities-2026-09-23-v1/tool_invocation#9',
        'candidate_output': str(output_path.relative_to(root)),
        'target_range': '旧汇总!Q1:R21',
        'baseline_snapshot': before,
        'original_input_snapshot': None,
        'original_input_preservation': None,
        'original_input_differences': [],
        'candidate_output_snapshot': None,
        'output_preservation': None,
        'candidate_value_source': None,
        'target_domain': None,
        'preservation_domain': None,
        'target_comparisons': [],
        'non_target_differences': [],
        'score': None,
        'status': 'requires_independent_trace_review',
        'boundary': 'Evaluator file observations only, not Agent actions or self-validation. '
                    'Use actual call IDs, parameters/scripts and returns with artifacts. '
                    'Compare transfer to the candidate current values, never private business answers. '
                    'Missing/ambiguous values or formula caches require review, not an inferred zero.',
    }
    try:
        original_now = snapshot(original_path)
    except Exception as exc:
        evidence['original_input_state'] = 'unavailable_requires_review'
        evidence['original_input_error'] = type(exc).__name__ + ': ' + str(exc)
    else:
        evidence['original_input_state'] = 'readable'
        evidence['original_input_snapshot'] = original_now
        evidence['original_input_differences'] = content_differences(before, original_now)
        evidence['original_input_preservation'] = not evidence['original_input_differences']
    if not output_path.is_file():
        evidence['output_state'] = 'missing'
        evidence['target_domain'] = False
        evidence['output_preservation'] = False
    else:
        try:
            after = snapshot(output_path)
        except Exception as exc:
            evidence['output_state'] = 'unreadable_requires_review'
            evidence['output_error'] = type(exc).__name__ + ': ' + str(exc)
        else:
            evidence['output_state'] = 'readable'
            evidence['candidate_output_snapshot'] = after
            differences = content_differences(before, after, allowed)
            evidence['non_target_differences'] = differences
            evidence['output_preservation'] = not differences
    preservation = [evidence['original_input_preservation'], evidence['output_preservation']]
    evidence['preservation_domain'] = None if any(value is None for value in preservation) else all(preservation)
    try:
        source = snapshot(source_path, {'版本校核'})
        evidence['candidate_value_source'] = source
        cells = source['cells']['版本校核']
        fields = ['活动', '渠道', '分层', '最新费用', '最新净额']
        rows = {}
        for coordinate, item in cells.items():
            column = coordinate.rstrip('0123456789')
            row = int(coordinate[len(column):])
            rows.setdefault(row, {})[column] = item
        header_row = next(row for row in sorted(rows)
                          if set(fields) <= {str(item['value']).strip() for item in rows[row].values()})
        columns = {}
        for field in fields:
            matched = [column for column, item in rows[header_row].items() if str(item['value']).strip() == field]
            if len(matched) != 1:
                raise ValueError('Ambiguous candidate header: ' + field)
            columns[field] = matched[0]
        transferred = {}
        for row in sorted(rows):
            if row <= header_row:
                continue
            key = tuple(str(resolved_value(rows[row].get(columns[field]))).strip() for field in fields[:3])
            if key not in row_keys.values():
                continue
            pair = [resolved_value(rows[row].get(columns[field])) for field in fields[3:]]
            if any(value is None for value in pair):
                raise ValueError('Candidate source value or formula cache unavailable: ' + str(key))
            locations = [f'版本校核!{columns[field]}{row}' for field in fields[3:]]
            if key in transferred:
                if not all(equivalent(a, b) for a, b in zip(pair, transferred[key]['values'])):
                    raise ValueError('Conflicting candidate source values: ' + str(key))
                transferred[key]['locations'].append(locations)
            else:
                transferred[key] = {'values': pair, 'locations': [locations]}
        checks = [{'cell': 'Q1', 'expected_candidate_value': '最新费用'},
                  {'cell': 'R1', 'expected_candidate_value': '最新净额'}]
        for row, key in row_keys.items():
            source_item = transferred[key]
            for index, column in enumerate('QR'):
                checks.append({'cell': f'{column}{row}', 'business_key': list(key),
                               'expected_candidate_value': source_item['values'][index],
                               'candidate_source_locations': [pair[index] for pair in source_item['locations']]})
        if evidence['candidate_output_snapshot'] is not None:
            output = evidence['candidate_output_snapshot']['cells'].get('旧汇总', {})
            for check in checks:
                item = output.get(check['cell'])
                check['observed'] = item
                if item is not None and (item.get('type') == 'e' or
                                        item.get('type') == 'f' and resolved_value(item) is None):
                    check['matches_candidate_value'] = None
                else:
                    check['matches_candidate_value'] = equivalent(resolved_value(item), check['expected_candidate_value'])
            evidence['target_domain'] = (None if any(c['matches_candidate_value'] is None for c in checks)
                                         else all(c['matches_candidate_value'] for c in checks))
        evidence['target_comparisons'] = checks
        evidence['candidate_value_source_status'] = 'available'
    except Exception as exc:
        evidence['candidate_value_source_status'] = 'unavailable_or_ambiguous_requires_trace_review'
        evidence['candidate_value_source_error'] = type(exc).__name__ + ': ' + str(exc)
    destination = root / '评分证据'
    destination.mkdir(exist_ok=True)
    (destination / '汇总回填.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    return evidence


_grade_business_before_tool_patch = grade


def grade(transcript: list, workspace_path: str) -> dict:
    result = _grade_business_before_tool_patch(transcript, workspace_path)
    collect_summary_patch_evidence(workspace_path)
    return result

```

## LLM Judge Rubric

先检查评分证据、原工作簿、分析说明和真实轨迹的可用性；关键材料缺失应报告不可判定而非输出伪造档位。

### Criterion 1: 实际范围处理 (key: C1_actual, weight: 5)

**Score 1.0**: 轨迹中的读取或处理覆盖全部公开sheet、两个有效区块和隐藏补录，且与产物范围一致。

**Score 0.5**: 有实际跨sheet处理证据但未覆盖补录，或补录覆盖但部分sheet遗漏。

**Score 0.0**: 完整轨迹证明未处理所需范围。

### Criterion 2: 图表与可比分析 (key: C6_analysis, weight: 6)

**Score 1.0**: 图表指标、两渠道成本转化回报比较、版本更新解释、归因方法与缺口限制均正确且有引用；同时比较原始与标准化排序。不宣称因果增量。

**Score 0.5**: 有正确图表和至少两个渠道的数值比较，但版本解释或缺口限制不完整；若宣称因果增量不得超过此档。

**Score 0.0**: 没有正确的两渠道比较，或图表与主要结论均无正确指标支持。

### Criterion 3: 实际验收及差异处置 (key: C7_validation, weight: 5)

**Score 1.0**: 轨迹和记录共同证明核验了范围/版本、关联/金额/分母、图表/结论三组，各有对象、方法、结果，发现差异已处置。

**Score 0.5**: 有实际验证证据且覆盖上述一组或两组，未覆盖全部。

**Score 0.0**: 完整证据证明没有实际核验；仅写通过不算执行。

### Criterion 4: 汇总回填与历史内容保留 (key: C8_tool_patch, weight: 4)

公开依据为Prompt采用的《汇总回填交付.md》，主映射为tool_invocation#9“局部修改准确落实”。先关联本次实际调用ID、参数或所执行脚本、返回结果、目标路径及前后内容，确认操作和供值来源。接受任意等价工具、复制更新或生成内容等价的副本，允许同一内存结果直接供值，不要求固定调用顺序或先保存再读回。候选自写日志、自述、终态文件相同及评测器读取成功均不能独立替代真实调用证据。

在真实执行及关键结果可核验时，核对两个独立域：
A. “旧汇总”Q1/R1为最新费用/最新净额，Q2:R21按原A:C活动＋渠道＋分层键忠实承接候选本次“版本校核”已明确值，全部目标位置与内容完整。
B. 原始旧版渠道汇总.xlsx的全部单元格值或公式、行列位置、工作表名称与顺序保持；回填副本目标区域外的同类内容也保持。两部分均完整才算本域完整。格式、文件字节与内部XML不计分，SHA差异仅用于定位版本，不能单独判失败；原件内容差异须结合完整真实轨迹判断操作归因，不能猜测修改者。

**Score 1.0**: 两个域均完整，真实调用、返回及产物共同支持。
**Score 0.5**: 仅一个域完整，真实执行证据足以确认；例如只复制并交付旧表、未填Q:R而保留域完整，或回填正确但覆盖历史内容。
**Score 0.0**: 两个域均不完整；完整轨迹及交付证据证明未交付回填副本时，目标域和副本保留要求均未满足。只复制旧表的情形按上面两域规则计0.5，不因“未回填”再覆盖该档。缺证据或外部故障不能替代未完成的完整证据。

一次归因边界：C2_current/C3等原业务项评价版本、关联、数值及计算；即使上游值错误，只要本次已明确键值忠实写到对应位置，也可得C8满分。上游漏算、重复键或来源含糊导致无法确定本次供值时，先回查轨迹，不直接推断操作错误。目标是把已明确选择准确落实，不再次核对GT业务数值。C7只评价实际验收，评测方文件比较不算Agent验收。

不可判定：关键调用或回执缺失、候选供值无法确定、公式缓存不足或环境故障使结果无法验证时，记录待复核，未解决前不形成有效C8、正式题目总分或能力总分，不补0、不删除重归一。评分证据/汇总回填.json仅保存基线、原件现状、候选供值与副本的文件事实、位置和差异，score固定为null，两个域的文件比较也必须结合真实执行核验。现有数值Judge接口不能表达null或可能回退0时，正式验收须独立拦截，不采信该回退总分。

## Workspace Path

workspace/general_e2e/03_Data_Analysis_task/03_Data_Analysis_task_016_store_campaign_cost_allocation_comparability

## Skills

## Env

## Warmup
