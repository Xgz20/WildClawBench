"""Source-embedded procurement summary sections; preserve original scoring units."""


def _ps_sections(tables, records, metrics, numeric, truth, root):
    import csv
    import hashlib
    from collections import defaultdict
    from decimal import Decimal

    def literal(value):
        return re.sub(r'[\s\u3000:：()（）,，。;；]', '', str(value or '')).casefold()

    with (root/'input/采购订单.csv').open(encoding='utf-8-sig', newline='') as stream:
        order_rows=list(csv.DictReader(stream))
    with (root/'input/入库记录.csv').open(encoding='utf-8-sig', newline='') as stream:
        receipt_rows=list(csv.DictReader(stream))
    orders={r['ORDER_ID']:r for r in order_rows}
    receipts={r['RECEIPT_NO']:r for r in receipt_rows}
    if (len(orders)!=len(order_rows) or len(receipts)!=len(receipt_rows)
            or number(len(orders))!=metrics['orders'] or number(len(receipts))!=metrics['receipts']
            or sum((number(r['TOTAL_AMOUNT']) for r in orders.values()),Decimal(0))!=metrics['orders_amount']
            or sum((number(r['RECV_AMOUNT']) for r in receipts.values()),Decimal(0))!=metrics['receipts_amount']):
        raise EvaluationError('Procurement source rows/totals do not match frozen reference')
    by_kind={k:{r['id']:r for r in rows} for k,rows in records.items()}
    complete={k:set(rows)==set(truth[k]) for k,rows in by_kind.items()}
    sign=numeric['categories']['amount']['direction']
    priorities={k:defaultdict(set) for k in by_kind}
    for table in tables:
        kind=table['kind']
        if kind not in by_kind or table.get('header_row') is None:continue
        header=next((r for r in table['rows'] if r['row']==table['header_row']),None)
        if header is None:continue
        columns=[i for i,v in enumerate(header['values']) if literal(v) in {'优先级','复核优先级','处理优先级'}]
        if len(columns)>1:raise EvaluationError('Ambiguous priority columns')
        if not columns:continue
        col=columns[0];rows={r['row']:r for r in table['rows']}
        for item in table.get('records',[]):
            vals=rows[item['row']]['values'];value=literal(vals[col] if col<len(vals) else None)
            # Priority labels are candidate text, not a prescribed enum.
            # Preserve exact categories without inferring 高=P1 or a business rank.
            # Only explicitly supported summary claims are interpreted below.
            if value:priorities[kind][value].add(item['id'])

    def total(kind, role, subset=None, absolute=False):
        if not complete[kind]:return None
        rows=by_kind[kind]
        chosen=set(rows) if subset is None else set(subset)
        values=[]
        for key in chosen:
            row=rows[key];value=number(row['values'].get(role))
            # Quantity rows may legitimately omit money. The same submitted ID
            # in the amount table is an explicit candidate source, not GT fill.
            if value is None and kind=='qty' and key in by_kind['amount']:
                value=number(by_kind['amount'][key]['values'].get(role))
            if value is None:return None
            values.append(abs(value) if absolute else value)
        return sum(values,Decimal(0))

    def difference(a,b):return None if a is None or b is None else a-b
    def subject(label,parent):
        text=literal(label);short=re.split(r'[（(]',str(label or ''),maxsplit=1)[0]
        aliases={'orders':['采购订单','全部采购订单','采购订单全部状态'],
                 'receipts':['入库记录','全部入库记录','入库记录全部'],
                 'matched':['已匹配','已匹配组数','已匹配订单'],
                 'clean':['已匹配且数量金额一致','匹配且数量金额均一致','完全匹配'],
                 'qty':['由数量差异传导','数量差异'],
                 'amount':['金额差异合计','金额差异'],
                 'price_only':['数量一致、仅单价差异','纯单价差异'],
                 'missing':['未入库订单','未入库订单金额','未入库订单金额合计'],
                 'orphan':['无对应订单入库','无对应订单入库金额','无订单入库金额','孤立入库金额合计'],
                 'unmatched_net':['两类未匹配金额净额'],
                 'unmatched_sum':['两类未匹配金额合计'],
                 'source_net':['差额合计','总差额','恒等式：总差额 ＝ 未入库 － 无订单 ＋ 已匹配差']}
        text=re.sub(r'^其中', '',text)
        for kind,values in aliases.items():
            if text in {literal(x) for x in values} or literal(short) in {literal(x) for x in values}:
                return kind,None
        if parent=='missing':
            match=re.fullmatch(r'状态[“”"\']?(.+?)[“”"\']?',text)
            if match:
                status=match.group(1)
                if status not in {literal(r['STATUS']) for r in orders.values()}:
                    raise EvaluationError('Unknown source order status in summary')
                ids={key for key in by_kind['missing'] if key in orders and literal(orders[key]['STATUS'])==status}
                return 'missing',ids
        match=re.fullmatch(r'去重后(p[123])合计',text)
        return ('priority_union',match.group(1)) if match else (None,None)

    def expected(kind,field,subset):
        selected=set(by_kind[kind]) if kind in by_kind and subset is None else subset
        if field=='count':
            if kind in by_kind:return Decimal(len(selected))
            if kind in {'orders','receipts'}:return metrics[kind]
            if kind=='matched':return metrics['orders']-len(by_kind['missing'])
            if kind=='clean':return metrics['orders']-len(set().union(*(set(by_kind[k]) for k in ('qty','amount','missing'))))
            if kind=='price_only':return Decimal(len(set(by_kind['amount'])-set(by_kind['qty'])))
            if kind in {'unmatched_net','unmatched_sum'}:return Decimal(len(by_kind['missing'])+len(by_kind['orphan']))
        if kind=='unmatched_sum' and field=='unmatched_amount':
            a=total('missing','oa');b=total('orphan','ra')
            return None if a is None or b is None else a+b
        if kind=='price_only':kind='amount';selected=set(by_kind['amount'])-set(by_kind['qty'])
        if kind in by_kind:
            if field=='reported_difference':return total(kind,'da',selected)
            if field=='order_amount':return Decimal(0) if kind=='orphan' else total(kind,'oa',selected)
            if field=='receipt_amount':return Decimal(0) if kind=='missing' else total(kind,'ra',selected)
            if field in {'net','abs'}:
                a=Decimal(0) if kind=='orphan' else total(kind,'oa',selected)
                b=Decimal(0) if kind=='missing' else total(kind,'ra',selected)
                if field=='abs':return total(kind,'da',selected,absolute=True) if kind in {'qty','amount'} else (a if kind=='missing' else b)
                return None if a is None or b is None else sign*(b-a)
            if field in {'order_quantity','receipt_quantity','quantity'}:
                role='rq' if field=='receipt_quantity' or field=='quantity' and kind=='orphan' else 'oq'
                return total(kind,role,selected)
            if field in {'less','more'}:
                if kind not in {'qty','amount'}:return None
                role='dq' if kind=='qty' else 'da'
                # These headers describe receipt vs order, independent of the
                # candidate's chosen signed-difference convention.
                values=[number(r['values'].get(role)) for k,r in by_kind[kind].items() if k in selected]
                if any(v is None for v in values):return None
                direction=numeric['categories'][kind]['direction']
                return Decimal(sum((direction*v<0 if field=='less' else direction*v>0) for v in values))
        if kind in {'orders','receipts'}:
            if field==('order_amount' if kind=='orders' else 'receipt_amount'):return metrics[kind+'_amount']
            if field==('order_quantity' if kind=='orders' else 'receipt_quantity'):
                return sum((number(r['ORDER_QTY'] if kind=='orders' else r['RECV_QTY']) for r in (orders if kind=='orders' else receipts).values()),Decimal(0))
        if kind in {'matched','clean'}:
            if not all(complete.values()):return None
            if kind=='clean' and field in {'less','more'}:return Decimal(0)
            if field in {'order_amount','receipt_amount','order_quantity','receipt_quantity'}:
                is_order=field.startswith('order');source='orders' if is_order else 'receipts'
                base=expected(source,field,None)
                role={'order_amount':'oa','receipt_amount':'ra','order_quantity':'oq','receipt_quantity':'rq'}[field]
                excluded='missing' if is_order else 'orphan'
                value=difference(base,total(excluded,role))
                if kind=='clean':value=difference(value,total('amount',role))
                return value
            if field in {'net','abs'}:
                if kind=='clean':return Decimal(0)
                return expected('amount',field,None)
        if kind in {'source_net','unmatched_net'}:
            a=metrics['orders_amount'] if kind=='source_net' else total('missing','oa')
            b=metrics['receipts_amount'] if kind=='source_net' else total('orphan','ra')
            if field=='order_amount':return a
            if field=='receipt_amount':return b
            if field=='order_quantity':return expected('orders',field,None) if kind=='source_net' else None
            if field=='receipt_quantity':return expected('receipts',field,None) if kind=='source_net' else None
            if field=='net':return None if a is None or b is None else sign*(b-a)
        return None

    header_names={'笔数':'count','记录数':'count','订单笔数':'count',
        '订单金额元':'order_amount','订单金额':'order_amount','采购订单金额':'order_amount',
        '入库金额元':'receipt_amount','入库金额':'receipt_amount',
        '金额差额订单－入库':'net','金额差额元':'net','金额差额净额元':'net','差额元':'net',
        '金额差额/金额合计元':'unmatched_amount',
        '差额绝对值合计元':'abs','订单数量':'order_quantity','入库数量':'receipt_quantity',
        '数量订单':'order_quantity','数量入库':'receipt_quantity','数量':'quantity',
        '少于订单笔数':'less','多于订单笔数':'more','占订单总额':'ratio',
        'p1':'p1','p2':'p2','p3':'p3','跟踪':'跟踪','合计':'count',
        '表内值':'check','源数据复算值':'check','差异':'check_difference'}
    text_headers={'说明','说明与表间关系','备注','优先级判定规则','结论','校验方法','核对口径对应明细表'}
    converted=[];extra={};locations={};audit=[]
    for table in tables:
        if table['kind']!='summary':converted.append(table);continue
        rows=[];headers=None;parent=None;header_hidden=set()
        for row in table['rows']:
            vals=row['values'];names=[literal(v) for v in vals]
            if names and names[0] in {'项目','差异类型','工作表','校验项','类别'}:
                recognized={i:header_names[n] for i,n in enumerate(names[1:],1) if n in header_names}
                if recognized and all(not n or i==0 or i in recognized or n in text_headers for i,n in enumerate(names)):
                    headers=recognized;header_hidden=set(row.get('hidden_columns',[]));parent=None;continue
                headers=None
            if len(vals)==1 and isinstance(vals[0],str) and re.match(r'^[一二三四五六七八九十]+[、.]',vals[0]):
                headers=None;parent=None
            if headers is None or not any(number(v) is not None for v in vals):rows.append(row);continue
            kind,subset=subject(vals[0],parent)
            if kind is None and 'unmatched_amount' in headers.values():
                fallback=summary_key(vals[0])
                if fallback in CATEGORIES:kind=fallback
            if kind is None:rows.append(row);continue
            mixed_field=None
            if 'unmatched_amount' in headers.values():
                # A mixed amount header alone cannot decide sum versus signed net.
                # Bind each value to its declared submitted column or explicit
                # addition; preserve unknown meanings for the original failure gate.
                texts=[literal(v).replace('＋','+') for i,v in enumerate(vals)
                       if i not in headers and i!=0 and literal(v)]
                descriptions={
                    'qty': [('对应「数量差异」表，金额差额(订单-入库)列合计','reported_difference')],
                    'amount': [('对应「金额差异」表，金额差额(订单-入库)列合计','reported_difference')],
                    'missing': [('对应「未入库订单」表，订单金额列合计','order_amount')],
                    'orphan': [('对应「'+name+'」表，入库金额列合计','receipt_amount')
                               for name in ['无对应订单入库','无对应订单入库记录','无对应订单的入库记录']],
                    'unmatched_sum': [('未入库订单金额合计+无对应订单入库金额合计','unmatched_amount')],
                }
                if len(texts)==1:
                    mixed_field=next((field for note,field in descriptions.get(kind,[])
                                      if texts[0]==literal(note)),None)
                if (mixed_field is None or sorted(headers.values())!=['count','unmatched_amount']):
                    rows.append(row);continue
            if subset is None and kind in by_kind:parent=kind
            # Unknown numeric columns remain subject to the original failure gate.
            if any(number(v) is not None and i not in headers for i,v in enumerate(vals)):
                rows.append(row);continue
            emitted=[]
            subset_tag=(str(subset) if isinstance(subset,str) else
                        hashlib.sha256('\0'.join(sorted(subset)).encode()).hexdigest()[:12]
                        if subset is not None else 'all')
            for col,field in headers.items():
                if col>=len(vals) or number(vals[col]) is None:continue
                if field in {'p1','p2','p3','跟踪'} or kind=='priority_union':
                    if kind=='priority_union':
                        union=set().union(*(v.get(subset,set()) for v in priorities.values()))
                        e=Decimal(len(union)) if field in {subset,'count'} else Decimal(0)
                    elif kind in by_kind:e=Decimal(len(priorities[kind].get(field,set())))
                    else:raise EvaluationError('Unsupported priority summary subject')
                    group='counts';key=f'ps_{kind}_{subset or "all"}_{field}'
                else:
                    mapped=mixed_field if field=='unmatched_amount' else field
                    if field in {'check','check_difference'}:
                        mapped=('order_amount' if kind=='missing' or kind=='orders' and '金额' in str(vals[0]) else
                                'receipt_amount' if kind=='orphan' or kind=='receipts' and '金额' in str(vals[0]) else
                                'net' if kind=='source_net' else 'count')
                        # A label mentioning only counts must not become a money claim.
                        if kind in {'missing','orphan'} and '金额' not in str(vals[0]):mapped='count'
                    e=expected(kind,mapped,subset)
                    if field=='check_difference':e=Decimal(0)
                    if field=='ratio':
                        basis=expected(kind,'abs' if kind in {'qty','amount','price_only'} else 'order_amount' if kind=='missing' else 'receipt_amount' if kind=='orphan' else 'net',subset)
                        e=None if basis is None else abs(basis)/metrics['orders_amount']
                    group='money' if mapped in {'order_amount','receipt_amount','net','abs','unmatched_amount','reported_difference'} else 'counts'
                    key=(kind if mapped=='count' and kind in {'qty','amount','missing','orphan','orders','receipts','matched','clean','price_only'} and subset is None and field!='check_difference' else
                         'net_amount' if kind=='amount' and mapped in {'net','reported_difference'} else
                         'abs_amount' if kind=='amount' and mapped=='abs' else
                         'missing_amount' if kind=='missing' and mapped=='order_amount' and subset is None and field!='check_difference' else
                         'orphan_amount' if kind=='orphan' and mapped=='receipt_amount' and subset is None and field!='check_difference' else
                         f'ps_{kind}_{subset_tag}_{field}_{mapped}')
                extra[key]=e
                if group=='money':MONEY_KEYS.add(key)
                if field=='ratio':_PS_TOLERANCES[key]=Decimal('0.000000001')
                label=f'_ps/{key}/{col}'
                SUMMARY_LABELS.setdefault(key,[]).append(label)
                projection={'row':row['row'],'values':[label,vals[col]]}
                if 0 in row.get('hidden_columns',[]) or col in row.get('hidden_columns',[]) or col in header_hidden:projection['hidden_columns']=[1]
                emitted.append(projection)
                location=table['sheet']+'!'+get_column_letter(col+1)+str(row['row'])
                locations[(table['sheet'],row['row'],label)]={'value_location':location,'extraction_profile':'procurement-section-columns/v1'}
                audit.append({'location':location,'subject':kind,'field':field,'key':key,'expected_unavailable':e is None})
            rows.extend(emitted)
        copy=dict(table);copy['rows']=rows;converted.append(copy)
    return converted,extra,locations,audit


_PS_TOLERANCES={}
_ps_original_matrix_view=_pl_matrix_view


def _pl_matrix_view(tables,records,metrics,numeric,truth,*args):
    converted,expected,locations,projections=_ps_original_matrix_view(tables,records,metrics,numeric,truth,*args)
    converted,extra,new_locations,audit=_ps_sections(converted,records,metrics,numeric,truth,_PS_ROOT)
    expected.update(extra);locations.update(new_locations);projections.extend(audit)
    return converted,expected,locations,projections


_pt_previous_matrix_view = _pl_matrix_view


def _pl_matrix_view(tables, records, metrics, numeric, truth, *args):
    """Project explicit source totals and declared arithmetic; retain raw locations."""
    import csv
    from decimal import Decimal

    converted, expected, locations, audit = _pt_previous_matrix_view(
        tables, records, metrics, numeric, truth, *args)
    by_kind = {k: {r['id']: r for r in rows} for k, rows in records.items()}
    complete = {k: set(rows) == set(truth[k]) for k, rows in by_kind.items()}

    def total(kind, role, subset=None):
        if not complete[kind]:
            return None
        selected = set(by_kind[kind]) if subset is None else set(subset)
        values = [number(by_kind[kind][key]['values'].get(role)) for key in selected]
        return None if any(v is None for v in values) else sum(values, Decimal(0))

    def count(kind, subset=None):
        return None if not complete[kind] else Decimal(len(by_kind[kind] if subset is None else subset))

    def calc(left, right, subtract=False):
        return None if left is None or right is None else left-right if subtract else left+right

    with (_PS_ROOT/'input/采购订单.csv').open(encoding='utf-8-sig', newline='') as stream:
        orders = list(csv.DictReader(stream))
    with (_PS_ROOT/'input/入库记录.csv').open(encoding='utf-8-sig', newline='') as stream:
        receipts = list(csv.DictReader(stream))
    # The preceding section verifier binds source identities/counts/money.
    def source_quantity(rows, field):
        values = [number(row[field]) for row in rows]
        if any(v is None for v in values):
            raise EvaluationError('Invalid source quantity for declared totals')
        return sum(values, Decimal(0))

    oq = source_quantity(orders, 'ORDER_QTY')
    rq = source_quantity(receipts, 'RECV_QTY')
    missing_amount = total('missing', 'oa')
    orphan_amount = total('orphan', 'ra')
    amount_difference = total('amount', 'da')
    detail_net = calc(calc(amount_difference, orphan_amount), missing_amount, True)
    source_net = metrics['receipts_amount']-metrics['orders_amount']
    matched_oq = calc(oq, total('missing', 'oq'), True)
    matched_rq = calc(rq, total('orphan', 'rq'), True)
    price_ids = set(by_kind['amount'])-set(by_kind['qty'])
    price_count = count('amount', price_ids) if complete['qty'] else None
    price_amount = total('amount', 'da', price_ids) if complete['qty'] else None

    def text(value):
        value = str(value or '').strip().casefold()
        value = value.replace('＝', '=').replace('＋', '+').replace('－', '-')
        return re.sub(r'[\s\u3000:：()（）,，。;；]', '', value)

    ordinal_values = {
        ('①', text('已匹配金额差额（金额差异表净差额）')): ('amount_detail', amount_difference, True),
        ('②', text('加：无对应订单入库金额')): ('orphan_detail', orphan_amount, True),
        ('③', text('减：未入库订单金额（取绝对值）')): ('missing_detail', missing_amount, True),
        ('④', text('明细推算总差额 =①+②-③')): ('detail_net', detail_net, True),
        ('⑤', text('源表总差额 = 入库总额-订单总额')): ('source_net', source_net, True),
        ('⑥', text('校验差异 =⑤-④（应为 0.00）')): ('source_detail_difference', calc(source_net, detail_net, True), True),
        ('⑦', text('数量勾稽：已匹配两侧数量差（应为 0）')): ('matched_quantity_difference', calc(matched_rq, matched_oq, True), False),
    }
    output = []
    for table in converted:
        if table['kind'] != 'summary':
            output.append(table)
            continue
        rows = []
        context = None
        header_hidden = set()
        cause_parts = set()
        for row in table['rows']:
            vals = row['values']
            names = [text(v) for v in vals]
            contexts = {
                ('项目', '笔数', '数量', '金额元', '备注'): 'source',
                ('成因', '笔数', '金额差额元', '说明'): 'cause',
                ('类别', '订单状态', '笔数', '金额元', '处理提示'): 'status',
                ('勾稽项', '', '', '数值', '校验说明'): 'reconcile',
            }
            if tuple(names) in contexts:
                context = contexts[tuple(names)]
                header_hidden = set(row.get('hidden_columns', []))
                cause_parts = set()
                rows.append(row)
                continue
            if len(vals) == 1 and isinstance(vals[0], str) and re.match(r'^[一二三四五六七八九十]+[、.]', vals[0]):
                context = None
                cause_parts = set()
            claims = None
            label = names[0] if names else ''
            if context == 'source':
                if label == text('采购订单（源表）'):
                    claims = [(1, 'orders_count', metrics['orders'], False),
                              (2, 'orders_quantity', oq, False),
                              (3, 'orders_amount', metrics['orders_amount'], True)]
                elif label == text('入库记录（源表）'):
                    claims = [(1, 'receipts_count', metrics['receipts'], False),
                              (2, 'receipts_quantity', rq, False),
                              (3, 'receipts_amount', metrics['receipts_amount'], True)]
                elif label == text('其中：已匹配入库'):
                    claims = [(1, 'matched_receipts_count', calc(metrics['receipts'], count('orphan'), True), False),
                              (2, 'matched_receipts_quantity', matched_rq, False),
                              (3, 'matched_receipts_amount', calc(metrics['receipts_amount'], orphan_amount, True), True)]
                elif label == text('差额合计（入库-订单）'):
                    claims = [(2, 'source_quantity_difference', rq-oq, False),
                              (3, 'source_amount_difference', source_net, True)]
            elif context == 'cause':
                if label == text('数量差异导致（单价一致）'):
                    cause_parts.add('qty')
                    claims = [(1, 'qty_cause_count', count('qty'), False),
                              (2, 'qty_cause_amount', total('qty', 'da'), True)]
                elif label == text('单价差异导致（数量一致）'):
                    cause_parts.add('price')
                    claims = [(1, 'price_cause_count', price_count, False),
                              (2, 'price_cause_amount', price_amount, True)]
                elif label == '合计' and cause_parts == {'qty', 'price'}:
                    claims = [(1, 'cause_total_count', count('amount'), False),
                              (2, 'cause_total_amount', amount_difference, True)]
            elif context == 'status' and label == text('未入库订单 小计'):
                claims = [(2, 'missing_subtotal_count', count('missing'), False),
                          (3, 'missing_subtotal_amount', missing_amount, True)]
            elif context == 'reconcile' and vals and isinstance(vals[0], str):
                raw = vals[0].lstrip()
                item = ordinal_values.get((raw[:1], text(raw[1:])))
                if item is not None:
                    key, value, money = item
                    claims = [(3, key, value, money)]
            if not claims:
                rows.append(row)
                continue
            allowed = {col for col, _, _, _ in claims}
            if (any(number(v) is not None and i not in allowed for i, v in enumerate(vals))
                    or any(col >= len(vals) or number(vals[col]) is None for col in allowed)):
                rows.append(row)
                continue
            for col, key, value, money in claims:
                key = 'pt_'+key
                expected[key] = value
                if money:
                    MONEY_KEYS.add(key)
                projected_label = '_pt/'+key+'/'+str(col)
                SUMMARY_LABELS.setdefault(key, []).append(projected_label)
                projected = {**row, 'values': [projected_label, vals[col]]}
                if 0 in row.get('hidden_columns', []) or col in row.get('hidden_columns', []) or 0 in header_hidden or col in header_hidden:
                    projected['hidden_columns'] = [1]
                rows.append(projected)
                location = table['sheet']+'!'+get_column_letter(col+1)+str(row['row'])
                locations[(table['sheet'], row['row'], projected_label)] = {
                    'value_location': location, 'extraction_profile': 'procurement-declared-source-totals/v1'}
                audit.append({'location': location, 'key': key, 'expected_unavailable': value is None,
                              'candidate_statement_synthesized': False})
        output.append({**table, 'rows': rows})
    return output, expected, locations, audit


