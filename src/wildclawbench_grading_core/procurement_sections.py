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
            if value in {'p1','p2','p3','跟踪'}:priorities[kind][value].add(item['id'])
            elif value:raise EvaluationError('Unrecognized priority literal: '+value)

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
            if kind=='unmatched_net':return Decimal(len(by_kind['missing'])+len(by_kind['orphan']))
        if kind=='price_only':kind='amount';selected=set(by_kind['amount'])-set(by_kind['qty'])
        if kind in by_kind:
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
        '差额绝对值合计元':'abs','订单数量':'order_quantity','入库数量':'receipt_quantity',
        '数量订单':'order_quantity','数量入库':'receipt_quantity','数量':'quantity',
        '少于订单笔数':'less','多于订单笔数':'more','占订单总额':'ratio',
        'p1':'p1','p2':'p2','p3':'p3','跟踪':'跟踪','合计':'count',
        '表内值':'check','源数据复算值':'check','差异':'check_difference'}
    text_headers={'说明','说明与表间关系','备注','优先级判定规则','结论','校验方法'}
    converted=[];extra={};locations={};audit=[]
    for table in tables:
        if table['kind']!='summary':converted.append(table);continue
        rows=[];headers=None;parent=None;header_hidden=set()
        for row in table['rows']:
            vals=row['values'];names=[literal(v) for v in vals]
            if names and names[0] in {'项目','差异类型','工作表','校验项'}:
                recognized={i:header_names[n] for i,n in enumerate(names[1:],1) if n in header_names}
                if recognized and all(not n or i==0 or i in recognized or n in text_headers for i,n in enumerate(names)):
                    headers=recognized;header_hidden=set(row.get('hidden_columns',[]));parent=None;continue
                headers=None
            if len(vals)==1 and isinstance(vals[0],str) and re.match(r'^[一二三四五六七八九十]+[、.]',vals[0]):
                headers=None;parent=None
            if headers is None or not any(number(v) is not None for v in vals):rows.append(row);continue
            kind,subset=subject(vals[0],parent)
            if kind is None:rows.append(row);continue
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
                    mapped=field
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
                    group='money' if mapped in {'order_amount','receipt_amount','net','abs'} else 'counts'
                    key=(kind if mapped=='count' and kind in {'qty','amount','missing','orphan','orders','receipts','matched','clean','price_only'} and subset is None and field!='check_difference' else
                         'net_amount' if kind=='amount' and mapped=='net' else
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


_ps_original_grade=grade


def grade(transcript,workspace_path):
    global _PS_ROOT
    _PS_ROOT=Path(workspace_path).resolve()
    return _ps_original_grade(transcript,workspace_path)
