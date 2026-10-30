"""Read-only matrix/conditional-formula extraction; no scoring weights live here."""
from decimal import Decimal as _pl_decimal


def _pl_conditional(name,args,number):
    if name=='SUMIF' and len(args) in {2,3}:
        ranges=[args[0] if isinstance(args[0],list) else [args[0]]]
        criteria=[args[1]];sums=args[-1] if len(args)==3 else args[0]
        sums=sums if isinstance(sums,list) else [sums]
    elif name=='COUNTIF' and len(args)==2:
        ranges=[args[0] if isinstance(args[0],list) else [args[0]]];criteria=[args[1]];sums=None
    elif name=='COUNTIFS' and len(args)>=2 and len(args)%2==0:
        ranges=[v if isinstance(v,list) else [v] for v in args[::2]];criteria=args[1::2];sums=None
    else:raise ValueError('unsupported conditional formula')
    if len({len(v) for v in ranges})!=1 or (sums is not None and len(sums)!=len(ranges[0])):
        raise ValueError('conditional formula range mismatch')
    # The registered candidate uses literal criteria. Unsupported operators/wildcards
    # remain explicit extraction failures instead of approximate Excel semantics.
    if any(isinstance(v,(dict,list)) or (isinstance(v,str) and any(c in v for c in '*?~<>=')) for v in criteria):
        raise ValueError('conditional criteria require a supported literal')
    def match(value,criterion):
        a,b=number(value),number(criterion)
        return a==b if a is not None and b is not None else str(value or '').casefold()==str(criterion or '').casefold()
    chosen=[i for i,row in enumerate(zip(*ranges)) if all(match(v,c) for v,c in zip(row,criteria))]
    if sums is None:return len(chosen)
    return sum((number(sums[i]) or _pl_decimal(0) for i in chosen),_pl_decimal(0))


_PL_MATRIX_KEYS={f'matrix_{kind}_{field}' for kind in ['qty','amount','missing','orphan','clean','price_only']
                 for field in ['order','receipt','net']}
_PL_MATRIX_KEYS.add('matrix_total_net')


def _pl_matrix_view(tables,records,metrics,numeric,truth,norm,summary_key,number):
    sets={k:{r['id'] for r in records[k]} for k in records}
    complete=all(sets[k]==set(truth[k]) for k in records)
    expected={};locations={};projections=[];converted=[]
    def total(kind,field):
        if sets[kind]!=set(truth[kind]):return None
        values={r['id']:number(r['values'].get(field)) for r in records[kind]}
        return None if any(v is None for v in values.values()) else sum(values.values(),_pl_decimal(0))
    def sub(a,b):return None if a is None or b is None else a-b
    sign=numeric['categories']['amount']['direction']
    def signed(value):return None if value is None else sign*value
    for kind in ['qty','amount','missing','orphan']:
        order=total(kind,'oa') if kind!='orphan' else _pl_decimal(0)
        receipt=total(kind,'ra') if kind!='missing' else _pl_decimal(0)
        expected.update({f'matrix_{kind}_order':order,f'matrix_{kind}_receipt':receipt,
                         f'matrix_{kind}_net':signed(sub(receipt,order))})
    clean_order=sub(sub(number(metrics['orders_amount']),total('amount','oa')),total('missing','oa')) if complete and sets['qty']<=sets['amount'] else None
    clean_receipt=sub(sub(number(metrics['receipts_amount']),total('amount','ra')),total('orphan','ra')) if complete and sets['qty']<=sets['amount'] else None
    expected.update(matrix_clean_order=clean_order,matrix_clean_receipt=clean_receipt,
                    matrix_clean_net=signed(sub(clean_receipt,clean_order)),
                    matrix_total_net=sign*(number(metrics['receipts_amount'])-number(metrics['orders_amount'])))
    price=[r for r in records['amount'] if r['id'] not in sets['qty']]
    for field,role in [('order','oa'),('receipt','ra'),('net','da')]:
        values=[number(r['values'].get(role)) for r in price]
        expected['matrix_price_only_'+field]=sum(values,_pl_decimal(0)) if complete and all(v is not None for v in values) else None
    def cell(col,row):
        result='';n=col+1
        while n:n,r=divmod(n-1,26);result=chr(65+r)+result
        return result+str(row)
    def plain(value):
        text=str(value or '');text=text.split('（',1)[0].split('(',1)[0]
        return norm(text).removesuffix('元')
    for table in tables:
        if table['kind']!='summary':converted.append(table);continue
        headers=None;rows=[];matrix_values={};matrix_locs={};matrix_visible={};net_present=False;seen=set()
        for row in table['rows']:
            vals=row['values'];names=[plain(v) for v in vals]
            cats=[i for i,v in enumerate(names) if v in {'对账类别','差异类型','异常类别'}]
            counts=[i for i,v in enumerate(names) if v in {'笔数','记录数','订单笔数'}]
            if len(cats)==1 and len(counts)==1:
                headers={'category':cats[0],'count':counts[0]}
                headers_hidden=set(row.get('hidden_columns',[]))
                sequence={i for i,n in enumerate(names) if n in {'序号','编号'}}
                for i,n in enumerate(names):
                    if n in {'采购订单金额','订单金额','采购金额','订单总额'}:headers['order']=i
                    elif n in {'入库记录金额','入库金额','实收金额'}:headers['receipt']=i
                    elif n in {'金额差额','金额差额合计','金额差异合计','金额差额净额'}:headers['net']=i
                continue
            category=summary_key(vals[headers['category']]) if headers and headers['category']<len(vals) else None
            is_total=headers is not None and any(norm(v) in {'合计','总计','total'} for v in vals[:headers['category']+1])
            if headers is None or category not in {'qty','amount','missing','orphan','clean','price_only'} and not is_total:
                rows.append(row);continue
            kind='total' if is_total else category
            if kind in seen:raise ValueError('Duplicate matrix category; extraction review required')
            seen.add(kind)
            mapped=set(headers.values())|sequence
            if any(number(v) is not None and i not in mapped for i,v in enumerate(vals)):
                raise ValueError('Unrecognized numeric matrix column; extraction review required')
            def emit(key,col,value=None,derived_from=None):
                nonlocal net_present
                value=vals[col] if value is None and col<len(vals) else value
                if number(value) is None:return
                label={'qty':'数量差异订单数','amount':'金额差异订单数','missing':'未入库订单数',
                       'orphan':'无对应订单入库单数','clean':'匹配且数量金额均一致订单数','price_only':'纯单价差异',
                       'orders':'总采购订单数','orders_amount':'订单金额合计','receipts_amount':'入库金额合计',
                       'net_amount':'金额差异净额合计','missing_amount':'未入库订单金额合计','orphan_amount':'孤立入库金额合计'}.get(key,key)
                hidden=[i for i,source in [(0,headers['category']),(1,col)]
                        if source in set(row.get('hidden_columns',[]))|headers_hidden]
                new={'row':row['row'],'values':[label,value]}
                if hidden:new['hidden_columns']=hidden
                rows.append(new);location=table['sheet']+'!'+cell(col,row['row'])
                locations[(table['sheet'],row['row'],label)]={'value_location':location,'derived_from':derived_from}
                projections.append({'sheet':table['sheet'],'row':row['row'],'key':key,'value_location':location,'derived_from':derived_from})
                matrix_values[key]=number(value);matrix_locs[key]=location
                matrix_visible[key]=not hidden
                if key=='net_amount':net_present=True
            emit('orders' if is_total else kind,headers['count'])
            for field in ['order','receipt','net']:
                if field not in headers:continue
                key=f'matrix_{kind}_{field}'
                if is_total:key={'order':'orders_amount','receipt':'receipts_amount','net':'matrix_total_net'}[field]
                elif kind=='amount' and field=='net':key='net_amount'
                elif kind=='missing' and field=='order':key='missing_amount'
                elif kind=='orphan' and field=='receipt':key='orphan_amount'
                elif field=='net' and 'order' not in headers and 'receipt' not in headers:
                    text=' '.join(str(v) for v in vals if v is not None)
                    if kind=='missing' and '按订单总额' in text:key='missing_amount'
                    elif kind=='orphan' and '按入库金额' in text:key='orphan_amount'
                    elif kind=='missing':
                        # An unlabeled signed/unmatched amount needs semantic extraction review.
                        raise ValueError('Unrecognized signed unmatched summary amount; extraction review required')
                emit(key,headers[field])
        if (not net_present and {'matrix_qty_net','matrix_price_only_net'}<=set(matrix_values)
                and sets['qty']<=sets['amount'] and complete):
            # Explicit quantity-linked + price-only partitions cover matched differences once.
            originals=[matrix_locs['matrix_qty_net'],matrix_locs['matrix_price_only_net']]
            label='金额差异净额合计';value=matrix_values['matrix_qty_net']+matrix_values['matrix_price_only_net']
            source_row=table['rows'][0]['row']
            derived={'row':source_row,'values':[label,float(value)]}
            if not all(matrix_visible[k] for k in ['matrix_qty_net','matrix_price_only_net']):derived['hidden_columns']=[1]
            rows.append(derived)
            locations[(table['sheet'],source_row,label)]={'value_location':'derived: '+' + '.join(originals),'derived_from':originals}
            projections.append({'key':'net_amount','derived_from':originals,'candidate_statement_synthesized':False})
        item=dict(table);item['rows']=rows;converted.append(item)
    return converted,expected,locations,projections


def _pl_install_summary_view():
    global summary_diagnostics
    original=summary_diagnostics
    def wrapped(tables,records,metrics,numeric,truth):
        global _PL_EXPECTED
        view,expected,locations,projections=_pl_matrix_view(tables,records,metrics,numeric,truth,norm,summary_key,number)
        _PL_EXPECTED=expected
        try:result=original(view,records,metrics,numeric,truth)
        finally:_PL_EXPECTED={}
        for claim in result['claims']:
            location=locations.get((claim['sheet'],claim['row'],claim['label']))
            if location:claim.update(location,extraction_profile='procurement-matrix-formulas/v2')
        result['matrix_extraction_provenance']=projections
        return result
    summary_diagnostics=wrapped


_PL_EXPECTED={}
