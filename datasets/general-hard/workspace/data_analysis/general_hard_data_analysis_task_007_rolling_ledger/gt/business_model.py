"""Source-first Decimal event model; never reads a candidate output."""
from collections import defaultdict,Counter
from datetime import date,datetime,timedelta,timezone
from decimal import Decimal

TZ=timezone(timedelta(hours=8));ZERO=Decimal('0.00')
PRIORITY={'invoice':10,'sales_return':20,'receipt':30,'refund':40}
def money(v):return Decimal(str(v)).quantize(Decimal('.01'))
def norm(v):return str(v or '').strip().upper()
def serial_day(day):return (date.fromisoformat(day)-date(1899,12,30)).days
def timestamp(v):return datetime.fromisoformat(v.replace('Z','+00:00')).astimezone(TZ)
def prepare(facts):
    rows=[];start=facts['period_start'];end=facts['as_of_date'];cutoff=timestamp(facts['entered_cutoff'])
    for source,items in [('orders',facts['orders']),('payments',facts['payments'])]:
        for raw in items:
            row=dict(raw);row['source']=source;row['customer_id']=norm(raw['customer_id']);row['currency']=norm(raw['currency']);row['event_type']=raw['event_type'].strip().lower();row['status']=raw['status'].strip().lower()
            row['amount']=money(raw['amount']);row['logical_id']=norm(raw['event_id'] if source=='orders' else raw['payment_id']);row['sequence']=int(raw['record_id'][1:])+(1000 if source=='payments' else 0)
            for k in ['document_no','reference_customer_id','reference_document_no','reference_receipt_id']:row[k]=norm(raw.get(k))
            row['due_date']=raw.get('due_date') or '';row['entered_local']=timestamp(raw['entered_at']).replace(tzinfo=None).isoformat()
            row['sort_key']=serial_day(row['business_date'])*1000000+PRIORITY.get(row['event_type'],90)*10000+row['sequence']
            row['decision']='';row['canonical']=False;row['postable']=False;row['unresolved']=False;row['ar_delta']=ZERO;row['bank_known_delta']=None;row['bank_known']=False;row['cash_disposition']='not_applicable' if source=='orders' else 'outside_scope'
            if row['business_date']<start:row['decision']='scope_before_start'
            elif row['business_date']>end:row['decision']='scope_after_end'
            elif timestamp(raw['entered_at'])>cutoff:row['decision']='scope_after_cutoff'
            payload=[row[k] for k in ['customer_id','event_type','business_date','amount','currency','status']]
            payload.extend(row[k] for k in ['document_no','reference_customer_id','reference_document_no','due_date'] if source=='orders')
            if source=='payments':payload.append(row['reference_receipt_id'])
            row['_payload']=tuple(payload);rows.append(row)
    groups=defaultdict(list)
    for row in rows:
        if not row['decision']:groups[(row['source'],row['logical_id'])].append(row)
    for group in groups.values():
        if len({r['_payload'] for r in group})>1:
            for row in group:row.update(decision='conflict',unresolved=True,cash_disposition='unquantified' if row['source']=='payments' else 'not_applicable')
        else:
            first=min(group,key=lambda r:r['sequence'])
            for row in group:
                if row is first:row['canonical']=True
                else:row.update(decision='duplicate',cash_disposition='duplicate' if row['source']=='payments' else 'not_applicable')
    return rows
def solve(facts):
    customers={norm(r['customer_id']):r for r in facts['opening']};rows=prepare(facts)
    invoice_candidates=[];receipts={};returns=[];refunds=[]
    for row in rows:
        if row['decision']:continue
        source=row['source'];kind=row['event_type']
        if row['status']!=('posted' if source=='orders' else 'confirmed'):row['decision']='not_posted_status';continue
        if row['currency']!='CNY':row['decision']='unsupported_currency';continue
        if row['amount']<=0:row.update(decision='invalid_amount',unresolved=True,cash_disposition='unquantified' if source=='payments' else 'not_applicable');continue
        if kind not in (['invoice','sales_return'] if source=='orders' else ['receipt','refund']):row.update(decision='invalid_type',unresolved=True);continue
        if source=='payments':row.update(bank_known=True,bank_known_delta=row['amount']*(1 if kind=='receipt' else -1),cash_disposition='known_suspense')
        if row['customer_id'] not in customers:row.update(decision='unknown_customer',unresolved=True);continue
        if kind=='invoice':invoice_candidates.append(row)
        elif kind=='receipt':row.update(decision='posted',postable=True,ar_delta=-row['amount'],cash_disposition='matched');receipts[row['logical_id']]=row
        elif kind=='sales_return':returns.append(row)
        else:refunds.append(row)
    invoices=defaultdict(list)
    for row in invoice_candidates:invoices[(row['customer_id'],row['document_no'])].append(row)
    confirmed_invoices={}
    for key,group in invoices.items():
        if len(group)!=1:
            for row in group:row.update(decision='invoice_document_ambiguous',unresolved=True)
        else:
            row=group[0];row.update(decision='posted',postable=True,ar_delta=row['amount']);confirmed_invoices[key]=row
    return_groups=defaultdict(list)
    for row in returns:
        key=(row['customer_id'],row['reference_document_no']);invoice=confirmed_invoices.get(key)
        if row['reference_customer_id']!=row['customer_id']:row.update(decision='cross_customer_reference',unresolved=True)
        elif invoice is None:row.update(decision='invoice_reference_missing',unresolved=True)
        elif invoice['sort_key']>=row['sort_key']:row.update(decision='invoice_not_earlier',unresolved=True)
        else:return_groups[key].append(row)
    for key,group in return_groups.items():
        allowed=sum((r['amount'] for r in group),ZERO)<=confirmed_invoices[key]['amount']
        for row in group:
            if allowed:row.update(decision='posted',postable=True,ar_delta=-row['amount'])
            else:row.update(decision='return_group_exceeds_invoice',unresolved=True)
    refund_groups=defaultdict(list)
    for row in refunds:
        receipt=receipts.get(row['reference_receipt_id'])
        if receipt is None:row.update(decision='receipt_reference_missing',unresolved=True)
        elif receipt['customer_id']!=row['customer_id']:row.update(decision='cross_customer_reference',unresolved=True)
        elif receipt['sort_key']>=row['sort_key']:row.update(decision='receipt_not_earlier',unresolved=True)
        else:refund_groups[row['reference_receipt_id']].append(row)
    for key,group in refund_groups.items():
        allowed=sum((r['amount'] for r in group),ZERO)<=receipts[key]['amount']
        for row in group:
            if allowed:row.update(decision='posted',postable=True,ar_delta=row['amount'],cash_disposition='matched')
            else:row.update(decision='refund_group_exceeds_receipt',unresolved=True)
    assert all(row['decision'] for row in rows)
    flow=[];customer_results={};months=[];lots=[]
    for customer,opening in sorted(customers.items()):
        posted=sorted((r for r in rows if r['customer_id']==customer and r['postable']),key=lambda r:r['sort_key'])
        balance=money(opening['opening_balance'])
        for index,row in enumerate(posted,1):
            row['customer_sequence']=index;row['balance_before']=balance;balance+=row['ar_delta'];row['balance_after']=balance
            flow.append({'record_id':row['record_id'],'customer_id':customer,'customer_sequence':index,'business_date':row['business_date'],
                'event_type':row['event_type'],'logical_id':row['logical_id'],'sort_key':row['sort_key'],'ar_delta':row['ar_delta'],'balance_before':row['balance_before'],'balance_after':row['balance_after']})
        totals={kind:sum((r['amount'] for r in posted if r['event_type']==kind),ZERO) for kind in PRIORITY}
        issue_rows=[r for r in rows if r['customer_id']==customer and r['unresolved']]
        result={'customer_id':customer,'opening_balance':money(opening['opening_balance']),**totals,'closing_balance':balance,
            'matched_net_cash':totals['receipt']-totals['refund'],'unresolved_order_rows':sum(r['source']=='orders' for r in issue_rows),
            'unresolved_payment_rows':sum(r['source']=='payments' for r in issue_rows),'posted_events':len(posted)}
        customer_lots=[]
        if result['opening_balance']>0:
            customer_lots.append({'customer_id':customer,'document_no':opening['opening_doc_no'],'source_record_id':'OPEN_'+customer,
                'business_date':'2026-06-30','sequence':int(customer[1:]),'due_date':opening['due_date'],'original_amount':result['opening_balance'],'return_amount':ZERO,'net_amount':result['opening_balance']})
        for key,invoice in confirmed_invoices.items():
            if key[0]!=customer:continue
            credits=sum((r['amount'] for r in return_groups.get(key,[]) if r['postable']),ZERO)
            customer_lots.append({'customer_id':customer,'document_no':invoice['document_no'],'source_record_id':invoice['record_id'],
                'business_date':invoice['business_date'],'sequence':invoice['sequence'],'due_date':invoice['due_date'],
                'original_amount':invoice['amount'],'return_amount':credits,'net_amount':invoice['amount']-credits})
        funds=max(-result['opening_balance'],ZERO)+result['matched_net_cash'];available=funds;bucket_totals={k:ZERO for k in ['not_due','d1_30','d31_60','d61_90','d90_plus']}
        for lot in sorted(customer_lots,key=lambda r:(r['due_date'],r['business_date'],r['sequence'])):
            used=min(max(available,ZERO),lot['net_amount']);available-=used;remaining=lot['net_amount']-used
            age=(date.fromisoformat(facts['as_of_date'])-date.fromisoformat(lot['due_date'])).days
            bucket='not_due' if age<=0 else 'd1_30' if age<=30 else 'd31_60' if age<=60 else 'd61_90' if age<=90 else 'd90_plus'
            lot.update(allocated_cash=used,remaining=remaining,overdue_days=age if remaining>0 else None,bucket=bucket if remaining>0 else 'cleared');lots.append(lot);bucket_totals[bucket]+=remaining
        result.update(bucket_totals);result['receivable_remaining']=sum(bucket_totals.values(),ZERO);result['customer_credit']=max(available,ZERO)
        assert result['receivable_remaining']-result['customer_credit']==balance,(customer,result)
        customer_results[customer]=result
        for month in [7,8,9]:
            start=f'2026-{month:02}-01';end=f'2026-{month+1:02}-01';period=[r for r in posted if start<=r['business_date']<end]
            first=money(opening['opening_balance'])+sum((r['ar_delta'] for r in posted if r['business_date']<start),ZERO)
            subtotals={kind:sum((r['amount'] for r in period if r['event_type']==kind),ZERO) for kind in PRIORITY}
            closing=first+subtotals['invoice']-subtotals['sales_return']-subtotals['receipt']+subtotals['refund']
            months.append({'customer_id':customer,'month':f'2026-{month:02}','opening_balance':first,**subtotals,'closing_balance':closing})
    for index,row in enumerate(flow,1):row['global_sequence']=index
    exceptions=[]
    for row in rows:
        if row['postable']:continue
        exceptions.append({'record_id':row['record_id'],'source':row['source'],'logical_id':row['logical_id'],'customer_id':row['customer_id'],'decision':row['decision'],
            'unresolved':row['unresolved'],'cash_disposition':row['cash_disposition'],'known_bank_delta':row['bank_known_delta'],
            'source_file':'orders.xlsx' if row['source']=='orders' else 'payments.csv','source_locator':row['record_id']})
    bank_known=sum((r['bank_known_delta'] for r in rows if r['bank_known']),ZERO)
    matched=sum((r['amount']*(1 if r['event_type']=='receipt' else -1) for r in rows if r['source']=='payments' and r['postable']),ZERO)
    suspense=sum((r['bank_known_delta'] for r in rows if r['bank_known'] and not r['postable']),ZERO)
    assert bank_known==matched+suspense
    controls={'bank_known_net':bank_known,'matched_net_cash':matched,'known_suspense_net':suspense,'known_cash_gap':bank_known-matched-suspense,
        'closing_net_AR':sum((r['closing_balance'] for r in customer_results.values()),ZERO),
        'remaining_receivables':sum((r['receivable_remaining'] for r in customer_results.values()),ZERO),
        'customer_credit':sum((r['customer_credit'] for r in customer_results.values()),ZERO),
        'unresolved_order_groups':len({r['logical_id'] for r in rows if r['source']=='orders' and r['unresolved']}),
        'unresolved_payment_groups':len({r['logical_id'] for r in rows if r['source']=='payments' and r['unresolved']}),
        'unquantified_bank_groups':len({r['logical_id'] for r in rows if r['source']=='payments' and r['cash_disposition']=='unquantified'}),
        'unresolved_order_rows':sum(r['source']=='orders' and r['unresolved'] for r in rows),
        'unresolved_payment_rows':sum(r['source']=='payments' and r['unresolved'] for r in rows),
        'fully_identified':not any(r['unresolved'] for r in rows)}
    assert controls['remaining_receivables']-controls['customer_credit']==controls['closing_net_AR']
    def safe_row(row):return {k:v for k,v in row.items() if not k.startswith('_')}
    return {'customers':customer_results,'audit':{r['record_id']:safe_row(r) for r in rows},'flow':flow,'months':months,'lots':lots,
        'exceptions':sorted(exceptions,key=lambda r:r['record_id']),'controls':controls,'decision_counts':dict(Counter(r['decision'] for r in rows))}
