"""Independent integer-cent relational/window implementation of P1-P6."""
from fractions import Fraction
import json,sqlite3
K=['voucher_no','counterparty_id','business_date','currency','direction']
def cents(value):
    if value is None:return None
    v=Fraction(str(value))*100
    if v.denominator!=1:raise ValueError('Not exact cents')
    return v.numerator
def compute(images,ledger):
    db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
    db.execute('CREATE TABLE image(file TEXT,voucher_no TEXT,counterparty_id TEXT,business_date TEXT,currency TEXT,direction TEXT,printed INTEGER,hand INTEGER,has_hand INTEGER,status TEXT,approval_location TEXT,crossed INTEGER)')
    for r in images:db.execute('INSERT INTO image VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',[r['file'],*[r[k] for k in K],cents(r['printed_amount']),cents(r['handwritten_amount']),int(r['has_handwritten_correction']),r['status_selection'],r['approval_location'],int(r['approval_crossed_out'])])
    db.execute('CREATE TABLE ledger(entry_id TEXT,voucher_no TEXT,counterparty_id TEXT,business_date TEXT,currency TEXT,direction TEXT,amount INTEGER,book_status TEXT,posted_at TEXT)')
    for r in ledger:db.execute('INSERT INTO ledger VALUES (?,?,?,?,?,?,?,?,?)',[r['entry_id'],*[r[k] for k in K],cents(r['amount']),r['book_status'],r['posted_at']])
    keys=','.join(K)
    db.execute('''CREATE VIEW grouped AS SELECT '''+keys+''',
      MAX(status='void') AS has_void, MAX(status IS NULL OR status<>'valid') AS has_not_valid,
      COUNT(DISTINCT CASE WHEN has_hand=1 AND approval_location='correction' AND crossed=0 THEN hand END) AS approved_count,
      MIN(CASE WHEN has_hand=1 AND approval_location='correction' AND crossed=0 THEN hand END) AS approved_value,
      MAX(has_hand) AS any_hand, COUNT(DISTINCT printed) AS original_count,MIN(printed) AS original_value
      FROM image GROUP BY '''+keys)
    db.execute('''CREATE VIEW voucher_group AS SELECT *, CASE WHEN has_void=1 THEN 'void' WHEN has_not_valid=1 THEN 'pending'
      WHEN approved_count=1 THEN 'confirmed' WHEN approved_count>1 OR any_hand=1 THEN 'pending' WHEN original_count=1 THEN 'confirmed' ELSE 'pending' END AS state,
      CASE WHEN has_void=1 THEN 0 WHEN has_not_valid=1 THEN NULL WHEN approved_count=1 THEN approved_value
      WHEN approved_count>1 OR any_hand=1 THEN NULL WHEN original_count=1 THEN original_value ELSE NULL END AS effective_cents FROM grouped''')
    db.execute('''CREATE VIEW scoped AS SELECT *, CASE WHEN business_date<'2026-09-01' OR business_date>'2026-09-30' THEN 'excluded_period'
      WHEN currency<>'CNY' THEN 'excluded_currency' WHEN book_status<>'posted' OR direction<>'expense' THEN 'excluded_status' ELSE 'eligible' END AS scope_status FROM ledger''')
    db.execute('CREATE VIEW eligible AS SELECT *, ROW_NUMBER() OVER(PARTITION BY '+keys+' ORDER BY julianday(posted_at),entry_id) AS n FROM scoped WHERE scope_status=\'eligible\'')
    db.execute('CREATE VIEW first_entry AS SELECT '+keys+',entry_id AS canonical FROM eligible WHERE n=1')
    join=' AND '.join('l.'+k+'=g.'+k for k in K);first_join=' AND '.join('l.'+k+'=f.'+k for k in K)
    sql='''SELECT l.*,g.state,g.effective_cents,f.canonical,
      CASE WHEN l.scope_status<>'eligible' THEN 'excluded' WHEN g.state IS NULL THEN 'hold' WHEN g.state='void' THEN 'reverse_void'
      WHEN g.state='pending' THEN 'hold' WHEN l.entry_id<>f.canonical THEN 'reverse_duplicate'
      WHEN l.amount=g.effective_cents THEN 'keep' ELSE 'correct_amount' END AS action FROM scoped l
      LEFT JOIN voucher_group g ON '''+join+' LEFT JOIN first_entry f ON '+first_join+' ORDER BY l.entry_id'
    group_list=[]
    for r in db.execute('SELECT * FROM voucher_group ORDER BY '+keys):
        match=' AND '.join(k+'=?' for k in K);identity=[r[k] for k in K];files=[x[0] for x in db.execute('SELECT file FROM image WHERE '+match+' ORDER BY file',identity)];entries=[x[0] for x in db.execute('SELECT entry_id FROM eligible WHERE '+match+' ORDER BY entry_id',identity)];first=db.execute('SELECT canonical FROM first_entry WHERE '+match,identity).fetchone();group_list.append({**dict(zip(K,identity)),'state':r['state'],'effective_amount':Fraction(r['effective_cents'],100) if r['effective_cents'] is not None else None,'voucher_files':files,'eligible_entry_ids':entries,'canonical_entry_id':first['canonical'] if first and r['state']=='confirmed' else None})
    lookup={tuple(r[k] for k in K):r for r in group_list};decisions=[];proposals=[]
    for r in db.execute(sql):
        original=next(v for v in ledger if v['entry_id']==r['entry_id']);identity=tuple(r[k] for k in K);group=lookup.get(identity) if r['scope_status']=='eligible' else None;action=r['action'];target=0 if action in ['reverse_void','reverse_duplicate'] else r['effective_cents'] if action in ['keep','correct_amount'] else None;delta=target-r['amount'] if target is not None else None;match='excluded' if action=='excluded' else 'no_voucher' if group is None else 'matched_'+group['state'];canonical=group['canonical_entry_id'] if group else None;files=group['voucher_files'] if group else [];rule={'excluded':['P1'],'no_voucher':['P2','P5'],'matched_void':['P3','P5'],'matched_pending':['P3','P4','P5']}.get(match,['P2','P5'] if action=='reverse_duplicate' else ['P2','P4','P5'])
        decisions.append({**original,'scope_status':r['scope_status'],'match_status':match,'canonical_entry_id':canonical,'action':action,'target_amount':Fraction(target,100) if target is not None else None,'proposed_delta':Fraction(delta,100) if delta is not None else None,'voucher_files':files,'rule_ids':rule})
        if action in ['reverse_void','reverse_duplicate','correct_amount']:proposals.append({**{k:r[k] for k in K},'entry_id':r['entry_id'],'action':action,'delta_amount':Fraction(delta,100),'target_amount':Fraction(target,100),'source_files':files,'approval_required':True,'approval_status':'pending','applied':False})
    for g in group_list:
        if g['state']=='confirmed' and not g['eligible_entry_ids']:proposals.append({**{k:g[k] for k in K},'entry_id':None,'action':'create','delta_amount':g['effective_amount'],'target_amount':g['effective_amount'],'source_files':g['voucher_files'],'approval_required':True,'approval_status':'pending','applied':False})
    count=db.execute('SELECT count(*),COALESCE(SUM(amount),0) FROM scoped WHERE scope_status=\'eligible\'').fetchone();book=Fraction(count[1],100);change=sum((r['delta_amount'] for r in proposals),Fraction(0));holds=[r for r in decisions if r['action']=='hold'];hold_amount=sum((Fraction(cents(r['amount']),100) for r in holds),Fraction(0));confirmed=sum((r['effective_amount'] for r in group_list if r['state']=='confirmed'),Fraction(0));summary={'image_count':len(images),'voucher_group_count':len(group_list),'ledger_row_count':len(ledger),'eligible_entry_count':count[0],'excluded_entry_count':len(ledger)-count[0],'eligible_book_amount':book,'proposed_delta_sum':change,'book_amount_after_proposals':book+change,'unresolved_book_amount':hold_amount,'unresolved_entry_count':len(holds),'proposal_count':len(proposals),'unbooked_pending_group_count':sum(g['state']=='pending' and not g['eligible_entry_ids'] for g in group_list),'confirmed_voucher_target_sum':confirmed,'fully_reconciled':not holds and not any(g['state']=='pending' for g in group_list),'applied':False,'approval_required':True};db.close()
    return {'images':images,'voucher_groups':group_list,'ledger_decisions':decisions,'proposals':proposals,'summary':summary}
