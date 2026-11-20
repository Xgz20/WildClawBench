"""Pure source observation + policy event reconciliation; no candidate outputs."""
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
KEY_FIELDS=['voucher_no','counterparty_id','business_date','currency','direction']
def key(row):return tuple(row[k] for k in KEY_FIELDS)
def money(value):return Decimal(str(value)).quantize(Decimal('.01'))
def scope(row):
    if not '2026-09-01'<=row['business_date']<='2026-09-30':return 'excluded_period'
    if row['currency']!='CNY':return 'excluded_currency'
    if row['book_status']!='posted' or row['direction']!='expense':return 'excluded_status'
    return 'eligible'
def group_state(rows):
    statuses={r['status_selection'] for r in rows}
    if 'void' in statuses:return 'void',money(0)
    if statuses!={'valid'}:return 'pending',None
    approved={money(r['handwritten_amount']) for r in rows if r['has_handwritten_correction'] and r['correction_status']=='approved' and r['handwritten_amount'] is not None}
    if len(approved)==1:return 'confirmed',next(iter(approved))
    if len(approved)>1 or any(r['has_handwritten_correction'] for r in rows):return 'pending',None
    originals={money(r['printed_amount']) for r in rows if r['printed_amount'] is not None}
    if len(originals)==1:return 'confirmed',next(iter(originals))
    return 'pending',None
def solve(observations,ledger):
    by=defaultdict(list)
    for row in observations:by[key(row)].append(row)
    groups=[];lookup={}
    eligible=defaultdict(list)
    for row in ledger:
        if scope(row)=='eligible':eligible[key(row)].append(row)
    for identity,images in sorted(by.items()):
        state,amount=group_state(images);group={**dict(zip(KEY_FIELDS,identity)),'state':state,'effective_amount':amount,'voucher_files':sorted(r['file'] for r in images),'eligible_entry_ids':sorted(r['entry_id'] for r in eligible[identity]),'canonical_entry_id':None}
        if state=='confirmed' and eligible[identity]:group['canonical_entry_id']=min(eligible[identity],key=lambda r:(datetime.fromisoformat(r['posted_at']),r['entry_id']))['entry_id']
        groups.append(group);lookup[identity]=group
    decisions=[];proposals=[]
    for row in sorted(ledger,key=lambda r:r['entry_id']):
        s=scope(row);group=lookup.get(key(row)) if s=='eligible' else None;amount=money(row['amount']);target=delta=None;canonical=group['canonical_entry_id'] if group else None;files=group['voucher_files'] if group else []
        if s!='eligible':action='excluded';match='excluded';rules=['P1']
        elif group is None:action='hold';match='no_voucher';rules=['P2','P5']
        elif group['state']=='void':action='reverse_void';match='matched_void';target=money(0);delta=-amount;rules=['P3','P5']
        elif group['state']=='pending':action='hold';match='matched_pending';rules=['P3','P4','P5']
        elif row['entry_id']!=canonical:action='reverse_duplicate';match='matched_confirmed';target=money(0);delta=-amount;rules=['P2','P5']
        else:
            target=group['effective_amount'];delta=target-amount;action='keep' if delta==0 else 'correct_amount';match='matched_confirmed';rules=['P2','P4','P5']
        result={**row,'scope_status':s,'match_status':match,'canonical_entry_id':canonical,'action':action,'target_amount':target,'proposed_delta':delta,'voucher_files':files,'rule_ids':rules};decisions.append(result)
        if action in {'reverse_void','reverse_duplicate','correct_amount'}:proposals.append({**dict(zip(KEY_FIELDS,key(row))),'entry_id':row['entry_id'],'action':action,'delta_amount':delta,'target_amount':target,'source_files':files,'approval_required':True,'approval_status':'pending','applied':False})
    for group in groups:
        if group['state']=='confirmed' and not group['eligible_entry_ids']:
            proposals.append({**{k:group[k] for k in KEY_FIELDS},'entry_id':None,'action':'create','delta_amount':group['effective_amount'],'target_amount':group['effective_amount'],'source_files':group['voucher_files'],'approval_required':True,'approval_status':'pending','applied':False})
    book=sum((money(r['amount']) for r in ledger if scope(r)=='eligible'),Decimal(0));change=sum((r['delta_amount'] for r in proposals),Decimal(0));holds=[r for r in decisions if r['action']=='hold'];unresolved=sum((money(r['amount']) for r in holds),Decimal(0));confirmed_target=sum((g['effective_amount'] for g in groups if g['state']=='confirmed'),Decimal(0))
    summary={'image_count':len(observations),'voucher_group_count':len(groups),'ledger_row_count':len(ledger),'eligible_entry_count':sum(scope(r)=='eligible' for r in ledger),'excluded_entry_count':sum(scope(r)!='eligible' for r in ledger),'eligible_book_amount':book,'proposed_delta_sum':change,'book_amount_after_proposals':book+change,'unresolved_book_amount':unresolved,'unresolved_entry_count':len(holds),'proposal_count':len(proposals),'unbooked_pending_group_count':sum(g['state']=='pending' and not g['eligible_entry_ids'] for g in groups),'confirmed_voucher_target_sum':confirmed_target,'fully_reconciled':not holds and not any(g['state']=='pending' for g in groups),'applied':False,'approval_required':True}
    assert summary['book_amount_after_proposals']==confirmed_target+unresolved
    assert all(r['target_amount'] is None and r['proposed_delta'] is None for r in decisions if r['action'] in {'hold','excluded'})
    return {'images':observations,'voucher_groups':groups,'ledger_decisions':decisions,'proposals':proposals,'summary':summary}
