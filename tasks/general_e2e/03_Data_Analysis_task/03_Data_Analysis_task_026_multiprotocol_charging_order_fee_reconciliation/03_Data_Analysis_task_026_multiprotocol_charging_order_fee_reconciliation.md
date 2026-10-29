---
id: 03_Data_Analysis_task_026_multiprotocol_charging_order_fee_reconciliation
name: Multiprotocol Charging Order Mapping and Fee Reconciliation
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
- technology
judge_evidence:
  required:
  - path: 评分证据/分析证据.json
    role: grader_generated_evidence
  - path: 评分证据/映射局部更新证据.json
    role: grader_generated_evidence
---


## Prompt

完成三种充电协议的监管字段映射，用九月订单核验电量、分时计费和总费用能否闭合，并将审定映射回填到接入资料副本。资料和采用的《业务口径与交付.md》在 `/tmp_workspace/`，按其中交付约定将底稿和报告保存到 `/tmp_workspace/results/`。

## Expected Behavior

运营商私有扩展、寄存器回卷、分时费用和字段映射草稿纠错。覆盖全部有效数据区块，按公开规则关联与计算；未知和确认0分开，结论可回查输入，不以参考解法作为唯一实现路线。按公开三处地址将本次字段映射中的选定文本落实到修订副本，保留原资料及副本中全部非目标内容；接受等价工具和实现。

## Grading Criteria

评分版本 query10-20261016-v1；局部更新扩展 tool-mapping-20261028-v1。公开依据为Prompt采用的《业务口径与交付.md》，不以私有参考答案增设义务。自动检查每项为两个完整业务核验域：两域完整正确得1，仅一域完整正确得0.5，均不完整得0；集合按全量多重集合比较，漏行、重行、额外行使对应域不完整。域的内容和字段列在下表，不使用通用准确率阈值。

| key/检查点 | 分值 | 公开依据 | 两个核验域 |
|---|---:|---|---|

| mapping 字段身份与必填约束 | 15 | §2 项目接口 | 字段映射（监管字段,来源协议,原字段位置）；字段映射（监管字段,来源协议,单位,是否必填） |

| normalization 单位转换与分时计费 | 25 | §2 单位和费率 | 订单明细（订单ID,电量,电费,服务费,总费用）；订单明细（订单ID,分时电量,应计电费,应计服务费） |

| closure 闭合差异与运营商汇总 | 25 | §2 差异与分母 | 订单明细（订单ID,计量差,计费差,费用差,状态）；运营商汇总（运营商,订单数,确认电量,电费,服务费,总费用,计量差异数,计费差异数,费用差异数,待确认数） |

| trace 订单关联与来源 | 15 | §1 范围与§3 来源 | 订单明细（订单ID,运营商,来源协议）；订单明细（订单ID,来源） |

| llm_judge.analysis 分析结论与业务建议 | 16 | §4 分析报告 | 见语义rubric |

| llm_judge.tool_mapping_patch 映射草稿局部更新落实 | 4 | §3.1 接入资料修订副本 | 三处选定文本的实际定点写入；原件和全部非目标内容保全。须结合真实调用与回执，不重复判断业务值正确性 |


自动组分=Σ(权重×档位)/80，Judge组分=Σ(权重×档位)/20，总分=自动组分×80+Judge组分×20。每个正式点仅0/0.5/1三档。分析结果表允许行列重排、等价数字文本和来源集合重排；接入资料修订副本须遵守§3.1固定位置和非目标保全约定。缺交付为业务未完成；缺GT/坏GT抛评测异常。部分上游关联错误可能影响多个业务结果，能力解释不得据此重复推断能力缺陷。

评分证据含报告全文、完整小表和标明非完整的大表样例。语义判断须核对原文件及对应源记录，样例不能证明全量结论。若收集器截断关键正文、PDF提取失败或所需真实轨迹缺失，相关Judge项记不可判定并停止正式总分汇总；不得以缺证猜0或1。自动组验证不是实际Agent/LLM Judge运行。

能力映射使用 `capabilities-2026-09-23-v1`：`automated.mapping`与`automated.trace`归`state_awareness`，`automated.normalization`归`reasoning_and_decision_making`，`llm_judge.tool_mapping_patch`仅归`tool_invocation#9`（局部修改准确落实）。`closure`和`analysis`只计题目分。有效映射预算W=15+25+15+4=59；能力总分=100×Σ映射项(题目分值×档位)/59。状态感知、推理与决策、工具调用各自以30、25、4为分母计算独立百分制，对能力总分贡献上限分别为100×30/59、100×25/59、100×4/59；意图理解和结果评估未覆盖。不能平均各维百分制代替加权总分。任一映射项缺证、外部阻断或不可判定时停止正式能力总分，不删项重归一，也不默认0或1。

局部更新的三处内容以候选自己的最终“字段映射”表为传递源，不以GT公式或单位真值替代该源。业务选值错误由原业务检查点判断：例如选错换算式但准确传至指定单元格且保护区完好，工具项仍可通过；业务映射全对但写偏单元格、传递截断或覆盖其他表，则工具项可失败。工具项不从产物正确倒推实际调用，不要求Agent自写日志或使用指定库。

## Automated Checks

```python
CONFIG = {'output': '充电订单映射与对账.xlsx',
 'report': '分析报告.md',
 'schema': {'订单明细': ['订单ID',
                     '运营商',
                     '来源协议',
                     '电量',
                     '电费',
                     '服务费',
                     '总费用',
                     '分时电量',
                     '应计电费',
                     '应计服务费',
                     '计量差',
                     '计费差',
                     '费用差',
                     '状态',
                     '来源'],
            '运营商汇总': ['运营商', '订单数', '确认电量', '电费', '服务费', '总费用', '计量差异数', '计费差异数', '费用差异数', '待确认数'],
            '字段映射': ['监管字段', '来源协议', '原字段位置', '转换规则', '单位', '是否必填', '对账核对说明']},
 'keys': {'订单明细': ['订单ID'], '运营商汇总': ['运营商'], '字段映射': ['监管字段', '来源协议']},
 'checks': [{'key': 'mapping',
             'title': '字段身份与必填约束',
             'weight': 15,
             'domains': [{'table': '字段映射', 'fields': ['监管字段', '来源协议', '原字段位置']},
                         {'table': '字段映射', 'fields': ['监管字段', '来源协议', '单位', '是否必填']}],
             'requirement': '§2 项目接口',
             'allowed_scores': [0, 0.5, 1],
             'capability': 'state_awareness#3'},
            {'key': 'normalization',
             'title': '单位转换与分时计费',
             'weight': 25,
             'domains': [{'table': '订单明细', 'fields': ['订单ID', '电量', '电费', '服务费', '总费用']},
                         {'table': '订单明细', 'fields': ['订单ID', '分时电量', '应计电费', '应计服务费']}],
             'requirement': '§2 单位和费率',
             'allowed_scores': [0, 0.5, 1],
             'capability': 'reasoning_and_decision_making#1'},
            {'key': 'closure',
             'title': '闭合差异与运营商汇总',
             'weight': 25,
             'domains': [{'table': '订单明细', 'fields': ['订单ID', '计量差', '计费差', '费用差', '状态']},
                         {'table': '运营商汇总',
                          'fields': ['运营商',
                                     '订单数',
                                     '确认电量',
                                     '电费',
                                     '服务费',
                                     '总费用',
                                     '计量差异数',
                                     '计费差异数',
                                     '费用差异数',
                                     '待确认数']}],
             'requirement': '§2 差异与分母',
             'allowed_scores': [0, 0.5, 1],
             'capability': None},
            {'key': 'trace',
             'title': '订单关联与来源',
             'weight': 15,
             'domains': [{'table': '订单明细', 'fields': ['订单ID', '运营商', '来源协议']},
                         {'table': '订单明细', 'fields': ['订单ID', '来源']}],
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

PATCH_BASELINE_SHA256 = '1504cf89a2ca56c0a01e817fdfcd0a06bf34ebbf600daf396c96994388104460'
PATCH_INPUT = '分时计费与接入资料.xlsx'
PATCH_OUTPUT = '分时计费与接入资料_修订.xlsx'
PATCH_SHEET = '历史映射草稿'
PATCH_TARGETS = [('D6', 'OCPP1.6', '转换规则'), ('E11', '云快充', '单位'), ('D16', 'Modbus-RTU', '转换规则')]

def _patch_digest(path):
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()

def _patch_cell_value(cell):
    from datetime import date, datetime, time
    value = cell.value
    if value is None:
        return None
    if cell.data_type == 'f':
        return ['formula', value]
    if cell.data_type == 'e':
        return ['error', value]
    if isinstance(value, bool):
        return ['boolean', value]
    if isinstance(value, (int, float)):
        return ['number', value if math.isfinite(value) else str(value)]
    if isinstance(value, (datetime, date, time)):
        return ['date_time', value.isoformat()]
    return ['text', str(value)]

def _patch_snapshot(path):
    # Values/formulas and their actual coordinates are read; styling/ZIP bytes are not compared.
    book = openpyxl.load_workbook(path, read_only=True, data_only=False)
    try:
        sheets = {}
        for sheet in book:
            cells = {}
            for row in sheet.iter_rows():
                for cell in row:
                    value = _patch_cell_value(cell)
                    if value is not None:
                        cells[cell.coordinate] = value
            sheets[sheet.title] = cells
        return {'sheet_order': list(book.sheetnames), 'sheets': sheets}
    finally:
        book.close()

def _patch_compare_protected(before, after, allow_target_updates=True):
    allowed = {(PATCH_SHEET, address) for address, _, _ in PATCH_TARGETS} if allow_target_updates else set()
    differences = []
    count = 0
    compared = 0
    for sheet in sorted(set(before['sheets']) | set(after['sheets'])):
        old = before['sheets'].get(sheet, {})
        new = after['sheets'].get(sheet, {})
        for address in sorted(set(old) | set(new)):
            if (sheet, address) in allowed:
                continue
            compared += 1
            if old.get(address) != new.get(address):
                count += 1
                if len(differences) < 20:
                    differences.append({'sheet': sheet, 'cell': address, 'before': old.get(address), 'after': new.get(address)})
    order_ok = before['sheet_order'] == after['sheet_order']
    return {'all_cells_compared': True, 'protected_nonempty_positions_compared': compared,
            'difference_count': count, 'first_differences': differences,
            'difference_examples_complete': count <= 20, 'sheet_names_and_order_unchanged': order_ok,
            'protected_content_unchanged': count == 0 and order_ok}

def _patch_target_facts(candidate, after):
    facts = []
    for address, protocol, field in PATCH_TARGETS:
        rows = [row for row in candidate.get('字段映射', [])
                if _norm(row.get('监管字段')) == '电量' and _norm(row.get('来源协议')) == protocol]
        source_value = rows[0].get(field) if len(rows) == 1 else None
        selected_text = str(source_value) if source_value is not None else None
        actual = after['sheets'].get(PATCH_SHEET, {}).get(address)
        facts.append({'target_sheet': PATCH_SHEET, 'target_cell': address,
                      'candidate_mapping_key': {'监管字段': '电量', '来源协议': protocol},
                      'candidate_mapping_field': field, 'matching_candidate_rows': len(rows),
                      'candidate_selected_text': selected_text, 'actual_typed_value': actual,
                      'selected_text_transferred': len(rows) == 1 and selected_text is not None
                      and bool(selected_text.strip()) and actual == ['text', selected_text]})
    return facts

def _mapping_patch_evidence(root, candidate, transcript):
    # No tool score is inferred from artifacts. Real invocation/return coverage requires Judge review.
    baseline = root / 'gt/接入资料原始基线.xlsx'
    try:
        if _patch_digest(baseline) != PATCH_BASELINE_SHA256:
            raise ValueError('Trusted patch baseline hash mismatch')
        before = _patch_snapshot(baseline)
    except Exception as exc:
        raise RuntimeError('Evaluation patch baseline missing/corrupt; not candidate failure') from exc
    out = {'schema': 'wildclawbench.mapping-patch-facts/v1', 'score': None,
           'checkpoint': 'llm_judge.tool_mapping_patch',
           'capability_reference': 'capabilities-2026-09-23-v1/tool_invocation/9',
           'status': 'artifact_facts_only_requires_real_call_and_return_review',
           'baseline_sha256': PATCH_BASELINE_SHA256, 'baseline_sheet_order': before['sheet_order'],
           'target_cells': [address for address, _, _ in PATCH_TARGETS],
           'candidate_self_written_log_required': False,
           'file_facts_do_not_prove_tool_execution': True,
           'trace_review': {'transcript_entry_count': len(transcript) if isinstance(transcript, list) else None,
                            'coverage_verified_by_extractor': False,
                            'required': 'Original same-attempt tool calls, actual arguments/script content, paired returns, and final artifact version. Missing/partial records mean indeterminate, not score 0.'},
           'source_input': {'path': PATCH_INPUT, 'unchanged_from_trusted_baseline': False},
           'candidate_patch': {'path': str(Path('results') / PATCH_OUTPUT), 'exists': False, 'readable': False},
           'target_transfers': [], 'protected_region': None}
    source = root / PATCH_INPUT
    target = root / 'results' / PATCH_OUTPUT
    for path, fact in [(source, out['source_input']), (target, out['candidate_patch'])]:
        try:
            expected_root = root.resolve() / 'results' if path == target else root.resolve()
            resolved = path.resolve()
            resolved.relative_to(expected_root)
            if path == source and resolved != root.resolve() / PATCH_INPUT:
                raise ValueError('Input file does not resolve to its public input position')
        except (ValueError, OSError) as exc:
            fact['boundary_error'] = type(exc).__name__
            continue
        fact['exists'] = path.is_file()
        if not fact['exists']:
            continue
        try:
            fact['sha256'] = _patch_digest(path)
        except OSError as exc:
            raise RuntimeError('Evaluation could not read patch evidence') from exc
        if path == source:
            fact['sha256_matches_baseline_diagnostic_only'] = fact['sha256'] == PATCH_BASELINE_SHA256
            try:
                current_source = _patch_snapshot(path)
            except (ValueError, KeyError, zipfile.BadZipFile, TypeError, EOFError) as exc:
                fact['candidate_parse_error'] = type(exc).__name__ + ': ' + str(exc)
                continue
            except OSError as exc:
                raise RuntimeError('Evaluation could not open original input evidence') from exc
            fact['all_content_comparison'] = _patch_compare_protected(before, current_source, allow_target_updates=False)
            fact['unchanged_from_trusted_baseline'] = fact['all_content_comparison']['protected_content_unchanged']
            fact['actual_input_modification_action_requires_trace_review'] = True
            continue
        try:
            after = _patch_snapshot(path)
        except (ValueError, KeyError, zipfile.BadZipFile, TypeError, EOFError) as exc:
            fact['candidate_parse_error'] = type(exc).__name__ + ': ' + str(exc)
            continue
        except OSError as exc:
            raise RuntimeError('Evaluation could not open patch evidence') from exc
        fact['readable'] = True
        fact['sheet_order'] = after['sheet_order']
        out['target_transfers'] = _patch_target_facts(candidate, after)
        out['protected_region'] = _patch_compare_protected(before, after)
    out['artifact_domain_facts'] = {
        'all_three_selected_texts_at_required_cells': len(out['target_transfers']) == 3
        and all(row['selected_text_transferred'] for row in out['target_transfers']),
        'source_and_all_non_target_content_preserved': out['source_input']['unchanged_from_trusted_baseline']
        and out['candidate_patch']['readable'] and bool(out['protected_region'])
        and out['protected_region']['protected_content_unchanged']}
    return out


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
    mapping_patch_facts=_mapping_patch_evidence(root,candidate,transcript)
    folder=root/'评分证据';folder.mkdir(exist_ok=True)
    (folder/'映射局部更新证据.json').write_text(json.dumps(mapping_patch_facts,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    (folder/'分析证据.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
    scores['diagnostics']={'checkpoints':diagnostics,'errors':errors,'counts':{s:{'expected':len(reference[s]),'actual':len(candidate.get(s,[]))} for s in reference},'valid_custom_model':special_ok,'status':'author_artifact_rules_only_no_agent_or_judge_score'}
    return scores
```

## LLM Judge Rubric

### Criterion 1: 分析结论与业务建议 (key: analysis, weight: 16)

**Score 1.0**: 映射转换规则与公开项目语义一致（接受等价公式），指出Wh/0.01kWh、费用分元、寄存器回卷及重置限制；用订单证据解释计量/计费/费用差异，给出针对性整改建议。

**Score 0.5**: 完成主要数值解释或一项可执行建议，并能回查对应事实，但缺少另一部分或材料限制说明。

**Score 0.0**: 没有可回查的业务分析，或主要结论与输入及计算结果矛盾、捏造原因。

依据：公开口径§4 分析报告。实际过程项须真实轨迹和产物；报告中自述不能替代操作证据。语义结论接受有证据的等价表达。缺关键证据时不可判定。


### Criterion 2: 映射草稿局部更新落实 (key: tool_mapping_patch, weight: 4)

规范：`capabilities-2026-09-23-v1/tool_invocation/9`。公开依据为§3.1。评分对象仅为本次候选确定的文本是否在规定位置实际写入，以及非目标内容是否被误改；不重判转换规则、单位或业务关联的真值，不把其他业务分数作为本项得分前提。

证据门：判定操作已执行时，必须同时具备同一执行的真实工具调用、实际参数（若调用脚本，需能回查实际执行脚本内容）、配对回执，以及对应最终版本的修订副本和候选“字段映射”。从原始事件引用调用与回执的call_id或原行号，定位输出路径及三个目标。支持不同工具、批次和等价保存方式，不强制Agent主动复检、提供操作自述或自写日志。评分后生成的`映射局部更新证据.json`只给出文件事实，`score=null`；其中的轨迹条数不证明轨迹完整，也不证明实际执行成功。轨迹缺失，或已发生操作的调用/回执不全、关键参数无法还原、版本不对应、服务阻断或取证截断时，记录不可判定并停止正式题目总分和能力总分；当前数值Judge接口不能原生返回null，评测外层须阻断，不可填0/1继续合分。真实调用参数正确但外部服务失败不直接判为工具错误。完整轨迹明确证实要求的操作未执行时，未出现该操作调用本身不是缺证，可按下述未完成条件判分；完整性无法确认时不可作此推断。

证据充分时，检查两个完整域，分母固定为2：

1. **定点写入域**：工具实际执行将候选最终字段映射中“电量/OCPP1.6”的转换规则、“电量/云快充”的单位、“电量/Modbus-RTU”的转换规则，分别作为文本保存到修订副本“历史映射草稿”D6、E11、D16；三处均与候选对应字段的选定文本一致，无截断、错位或意外作为Excel公式执行。对应候选记录按两个公开键唯一定位，允许候选表行列重排；不要求转换文本与GT措辞一致。三处全部落实该域才通过，重复调用不增加分母。若完整轨迹明确未完成所要求写入，或候选没有可定位的传递源/修订副本，该域不通过。
2. **非目标保全域**：最终修订副本可读取，输入原文件未修改；全部工作表名称及顺序、非D6/E11/D16的所有单元格值、公式和所在位置与可信原始基线相同，没有额外写入、删除或挪动。全量文件事实用于核对，20条差异样例不是全量通过证明；缺副本不因“没有修改”获得此域分。仅样式、包内元数据或压缩变化不构成内容保全失败，不要求xlsx字节一致。

**Score 1.0**: 真实调用与回执证据充分，两个完整域均通过。

**Score 0.5**: 真实调用与回执证据充分，仅一个完整域通过。

**Score 0.0**: 完整执行证据足以确认两个域均不通过。例如全程没有任何复制或写入操作，且未交付可读取的修订副本。缺证或外部阻断不适用此档。

若真实工具仅复制原表，三个目标未承接本次候选选定文本，但可读副本的非目标内容及原件完整保留，则定点写入域失败、非目标保全域通过，得0.5，不能用“未完成更新”改判0。若本次候选选定文本恰与原表目标值一致，真实复制已将这些文本落实到正确位置，不要求为了产生差异而改写相同值；其业务正确性仍由原业务项判断。

只按这两个域判分；选定值的业务错误不在此重复扣分。相同的一处写偏可同时使两域不完整，但只产生本项一次4分预算内的结果，不额外拆点重复扣罚。

## Workspace Path

```text
workspace/general_e2e/03_Data_Analysis_task/03_Data_Analysis_task_026_multiprotocol_charging_order_fee_reconciliation
```

## Skills


## Env


## Warmup

