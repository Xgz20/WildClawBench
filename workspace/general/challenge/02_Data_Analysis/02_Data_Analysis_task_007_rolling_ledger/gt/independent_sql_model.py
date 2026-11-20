"""Independent integer-cent relational ledger, using materialized SQL groups, joins and window frames."""
import sqlite3
def cents(text):
    value=str(text);sign=-1 if value.startswith('-') else 1;value=value.lstrip('+-');whole,fraction=(value+'.').split('.')[:2]
    assert len(fraction)<=2
    return sign*(int(whole)*100+int((fraction+'00')[:2]))
def solve(facts):
    db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
    db.executescript('''
CREATE TABLE raw(record_id TEXT, src TEXT, logical_id TEXT, customer_id TEXT, document_no TEXT, kind TEXT, bday TEXT, entered_iso TEXT,
 amount INTEGER, currency TEXT, status TEXT, ref_cust TEXT, ref_doc TEXT, ref_receipt TEXT, due_day TEXT, source_seq INTEGER);
CREATE TABLE opening(customer_id TEXT PRIMARY KEY, document_no TEXT, amount INTEGER, due_day TEXT);
CREATE TABLE settings(start_day TEXT,end_day TEXT,cutoff TEXT);
CREATE TABLE months(month TEXT,first_day TEXT,next_day TEXT);
''')
    for src,key in [('orders','event_id'),('payments','payment_id')]:
        for r in facts[src]:
            db.execute('INSERT INTO raw VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(r['record_id'],src,r[key],r['customer_id'],r.get('document_no',''),r['event_type'],r['business_date'],r['entered_at'],cents(r['amount']),r['currency'],r['status'],r.get('reference_customer_id',''),r.get('reference_document_no',''),r.get('reference_receipt_id',''),r.get('due_date',''),int(r['record_id'][1:])))
    db.executemany('INSERT INTO opening VALUES(?,?,?,?)',[(r['customer_id'].strip().upper(),r['opening_doc_no'],cents(r['opening_balance']),r['due_date']) for r in facts['opening']])
    db.execute('INSERT INTO settings VALUES(?,?,?)',(facts['period_start'],facts['as_of_date'],facts['entered_cutoff']))
    db.executemany('INSERT INTO months VALUES(?,?,?)',[(f'2026-{m:02}',f'2026-{m:02}-01',f'2026-{m+1:02}-01') for m in [7,8,9]])
    db.executescript('''
CREATE TEMP TABLE normalized AS SELECT record_id,src,UPPER(TRIM(logical_id)) logical_id,UPPER(TRIM(customer_id)) customer_id,UPPER(TRIM(document_no)) document_no,
 LOWER(TRIM(kind)) kind,bday,entered_iso,amount,UPPER(TRIM(currency)) currency,LOWER(TRIM(status)) status,UPPER(TRIM(ref_cust)) ref_cust,
 UPPER(TRIM(ref_doc)) ref_doc,UPPER(TRIM(ref_receipt)) ref_receipt,due_day,
 source_seq+CASE src WHEN 'payments' THEN 1000 ELSE 0 END sequence,
 CAST(julianday(bday)-julianday('1899-12-30') AS INTEGER)*1000000+
 CASE LOWER(TRIM(kind)) WHEN 'invoice' THEN 10 WHEN 'sales_return' THEN 20 WHEN 'receipt' THEN 30 WHEN 'refund' THEN 40 ELSE 90 END*10000+
 source_seq+CASE src WHEN 'payments' THEN 1000 ELSE 0 END sort_key,
 CASE WHEN bday<(SELECT start_day FROM settings) THEN 'scope_before_start'
 WHEN bday>(SELECT end_day FROM settings) THEN 'scope_after_end'
 WHEN CAST(strftime('%s',entered_iso) AS INTEGER)>CAST(strftime('%s',(SELECT cutoff FROM settings)) AS INTEGER) THEN 'scope_after_cutoff' ELSE '' END scope_reason
 FROM raw;
CREATE TEMP TABLE available AS SELECT *,json_array(customer_id,kind,bday,amount,currency,status,document_no,ref_cust,ref_doc,due_day,ref_receipt) payload FROM normalized WHERE scope_reason='';
CREATE TEMP TABLE ids AS SELECT src,logical_id,COUNT(DISTINCT payload) variants,MIN(sequence) first_sequence FROM available GROUP BY src,logical_id;
CREATE TEMP TABLE base AS SELECT n.*,CASE WHEN n.scope_reason<>'' THEN n.scope_reason WHEN i.variants>1 THEN 'conflict'
 WHEN n.sequence<>i.first_sequence THEN 'duplicate'
 WHEN n.status<>CASE n.src WHEN 'orders' THEN 'posted' ELSE 'confirmed' END THEN 'not_posted_status'
 WHEN n.currency<>'CNY' THEN 'unsupported_currency' WHEN n.amount<=0 THEN 'invalid_amount'
 WHEN n.kind NOT IN ('invoice','sales_return','receipt','refund') THEN 'invalid_type'
 WHEN o.customer_id IS NULL THEN 'unknown_customer' ELSE '' END initial_reason,
 CASE WHEN n.scope_reason='' AND i.variants=1 AND n.sequence=i.first_sequence THEN 1 ELSE 0 END canonical,
 CASE WHEN n.src='payments' AND n.scope_reason='' AND i.variants=1 AND n.sequence=i.first_sequence AND n.status='confirmed' AND n.currency='CNY' AND n.amount>0 AND n.kind IN ('receipt','refund') THEN 1 ELSE 0 END bank_known
 FROM normalized n LEFT JOIN ids i ON i.src=n.src AND i.logical_id=n.logical_id LEFT JOIN opening o ON o.customer_id=n.customer_id;
CREATE TEMP TABLE invoice_candidates AS SELECT * FROM base WHERE initial_reason='' AND kind='invoice';
CREATE TEMP TABLE invoice_counts AS SELECT customer_id,document_no,COUNT(*) n FROM invoice_candidates GROUP BY customer_id,document_no;
CREATE TEMP TABLE invoices AS SELECT i.* FROM invoice_candidates i JOIN invoice_counts c ON c.customer_id=i.customer_id AND c.document_no=i.document_no AND c.n=1;
CREATE TEMP TABLE receipts AS SELECT * FROM base WHERE initial_reason='' AND kind='receipt';
CREATE TEMP TABLE return_pre AS SELECT r.*,i.amount original_amount FROM base r JOIN invoices i ON i.customer_id=r.customer_id AND i.document_no=r.ref_doc
 WHERE r.initial_reason='' AND r.kind='sales_return' AND r.ref_cust=r.customer_id AND i.sort_key<r.sort_key;
CREATE TEMP TABLE return_totals AS SELECT customer_id,ref_doc,SUM(amount) total,MAX(original_amount) original FROM return_pre GROUP BY customer_id,ref_doc;
CREATE TEMP TABLE returns AS SELECT r.* FROM return_pre r JOIN return_totals t ON t.customer_id=r.customer_id AND t.ref_doc=r.ref_doc AND t.total<=t.original;
CREATE TEMP TABLE refund_pre AS SELECT f.*,r.amount original_amount FROM base f JOIN receipts r ON r.logical_id=f.ref_receipt AND r.customer_id=f.customer_id
 WHERE f.initial_reason='' AND f.kind='refund' AND r.sort_key<f.sort_key;
CREATE TEMP TABLE refund_totals AS SELECT ref_receipt,SUM(amount) total,MAX(original_amount) original FROM refund_pre GROUP BY ref_receipt;
CREATE TEMP TABLE refunds AS SELECT r.* FROM refund_pre r JOIN refund_totals t ON t.ref_receipt=r.ref_receipt AND t.total<=t.original;
CREATE TEMP TABLE posted AS
 SELECT record_id,customer_id,logical_id,kind,bday,sequence,sort_key,amount,amount delta FROM invoices
 UNION ALL SELECT record_id,customer_id,logical_id,kind,bday,sequence,sort_key,amount,-amount FROM receipts
 UNION ALL SELECT record_id,customer_id,logical_id,kind,bday,sequence,sort_key,amount,-amount FROM returns
 UNION ALL SELECT record_id,customer_id,logical_id,kind,bday,sequence,sort_key,amount,amount FROM refunds;
CREATE TEMP TABLE decisions AS SELECT b.*,CASE WHEN initial_reason<>'' THEN initial_reason
 WHEN kind='invoice' AND record_id NOT IN (SELECT record_id FROM invoices) THEN 'invoice_document_ambiguous'
 WHEN kind='sales_return' AND ref_cust<>customer_id THEN 'cross_customer_reference'
 WHEN kind='sales_return' AND NOT EXISTS(SELECT 1 FROM invoices i WHERE i.customer_id=b.customer_id AND i.document_no=b.ref_doc) THEN 'invoice_reference_missing'
 WHEN kind='sales_return' AND NOT EXISTS(SELECT 1 FROM return_pre r WHERE r.record_id=b.record_id) THEN 'invoice_not_earlier'
 WHEN kind='sales_return' AND record_id NOT IN (SELECT record_id FROM returns) THEN 'return_group_exceeds_invoice'
 WHEN kind='refund' AND NOT EXISTS(SELECT 1 FROM receipts r WHERE r.logical_id=b.ref_receipt) THEN 'receipt_reference_missing'
 WHEN kind='refund' AND NOT EXISTS(SELECT 1 FROM receipts r WHERE r.logical_id=b.ref_receipt AND r.customer_id=b.customer_id) THEN 'cross_customer_reference'
 WHEN kind='refund' AND NOT EXISTS(SELECT 1 FROM refund_pre r WHERE r.record_id=b.record_id) THEN 'receipt_not_earlier'
 WHEN kind='refund' AND record_id NOT IN (SELECT record_id FROM refunds) THEN 'refund_group_exceeds_receipt' ELSE 'posted' END decision
 FROM base b;
CREATE TEMP TABLE audit AS SELECT d.*,CASE WHEN p.record_id IS NULL THEN 0 ELSE 1 END postable,COALESCE(p.delta,0) delta,
 CASE WHEN decision IN ('conflict','invalid_amount','invalid_type','unknown_customer','invoice_document_ambiguous','cross_customer_reference','invoice_reference_missing','invoice_not_earlier','return_group_exceeds_invoice','receipt_reference_missing','receipt_not_earlier','refund_group_exceeds_receipt') THEN 1 ELSE 0 END unresolved,
 CASE WHEN bank_known=1 THEN d.amount*CASE d.kind WHEN 'receipt' THEN 1 ELSE -1 END ELSE NULL END bank_known_delta,
 CASE WHEN src='orders' THEN 'not_applicable' WHEN decision='duplicate' THEN 'duplicate' WHEN decision IN ('conflict','invalid_amount') THEN 'unquantified'
 WHEN bank_known=1 AND p.record_id IS NOT NULL THEN 'matched' WHEN bank_known=1 THEN 'known_suspense' ELSE 'outside_scope' END cash_disposition
 FROM decisions d LEFT JOIN posted p ON p.record_id=d.record_id;
CREATE TEMP TABLE flow AS SELECT p.*,ROW_NUMBER() OVER(PARTITION BY p.customer_id ORDER BY sort_key) customer_sequence,
 ROW_NUMBER() OVER(ORDER BY p.customer_id,sort_key) global_sequence,
 o.amount+COALESCE(SUM(delta) OVER(PARTITION BY p.customer_id ORDER BY sort_key ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING),0) balance_before,
 o.amount+SUM(delta) OVER(PARTITION BY p.customer_id ORDER BY sort_key ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) balance_after
 FROM posted p JOIN opening o ON o.customer_id=p.customer_id;
CREATE TEMP TABLE customer_sums AS SELECT o.customer_id,o.amount opening_balance,
 COALESCE(SUM(CASE p.kind WHEN 'invoice' THEN p.amount ELSE 0 END),0) invoice,
 COALESCE(SUM(CASE p.kind WHEN 'sales_return' THEN p.amount ELSE 0 END),0) sales_return,
 COALESCE(SUM(CASE p.kind WHEN 'receipt' THEN p.amount ELSE 0 END),0) receipt,
 COALESCE(SUM(CASE p.kind WHEN 'refund' THEN p.amount ELSE 0 END),0) refund,
 o.amount+COALESCE(SUM(p.delta),0) closing_balance,COALESCE(SUM(CASE WHEN p.kind='receipt' THEN p.amount WHEN p.kind='refund' THEN -p.amount ELSE 0 END),0) matched_net_cash,
 (SELECT COUNT(*) FROM audit a WHERE a.customer_id=o.customer_id AND a.src='orders' AND a.unresolved=1) unresolved_order_rows,
 (SELECT COUNT(*) FROM audit a WHERE a.customer_id=o.customer_id AND a.src='payments' AND a.unresolved=1) unresolved_payment_rows,COUNT(p.record_id) posted_events
 FROM opening o LEFT JOIN posted p ON p.customer_id=o.customer_id GROUP BY o.customer_id;
CREATE TEMP TABLE lot_base AS SELECT customer_id,document_no,'OPEN_'||customer_id source_record_id,'2026-06-30' bday,CAST(SUBSTR(customer_id,2) AS INTEGER) sequence,due_day,amount original_amount,0 return_amount,amount net_amount FROM opening WHERE amount>0
 UNION ALL SELECT i.customer_id,i.document_no,i.record_id,i.bday,i.sequence,i.due_day,i.amount,
 COALESCE((SELECT SUM(r.amount) FROM returns r WHERE r.customer_id=i.customer_id AND r.ref_doc=i.document_no),0),
 i.amount-COALESCE((SELECT SUM(r.amount) FROM returns r WHERE r.customer_id=i.customer_id AND r.ref_doc=i.document_no),0) FROM invoices i;
CREATE TEMP TABLE lot_prefix AS SELECT l.*,COALESCE(SUM(net_amount) OVER(PARTITION BY customer_id ORDER BY due_day,bday,sequence ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING),0) previous_net FROM lot_base l;
CREATE TEMP TABLE lot_allocation AS SELECT l.*,MIN(net_amount,MAX(MAX(-c.opening_balance,0)+c.matched_net_cash-previous_net,0)) allocated_cash,
 net_amount-MIN(net_amount,MAX(MAX(-c.opening_balance,0)+c.matched_net_cash-previous_net,0)) remaining,
 CAST(julianday((SELECT end_day FROM settings))-julianday(due_day) AS INTEGER) raw_age FROM lot_prefix l JOIN customer_sums c USING(customer_id);
CREATE TEMP TABLE lots AS SELECT *,CASE WHEN remaining=0 THEN NULL ELSE raw_age END overdue_days,
 CASE WHEN remaining=0 THEN 'cleared' WHEN raw_age<=0 THEN 'not_due' WHEN raw_age<=30 THEN 'd1_30' WHEN raw_age<=60 THEN 'd31_60' WHEN raw_age<=90 THEN 'd61_90' ELSE 'd90_plus' END bucket FROM lot_allocation;
CREATE TEMP TABLE customer_results AS SELECT c.*,
 (SELECT COALESCE(SUM(remaining),0) FROM lots l WHERE l.customer_id=c.customer_id) receivable_remaining,
 MAX(MAX(-c.opening_balance,0)+c.matched_net_cash-(SELECT COALESCE(SUM(net_amount),0) FROM lot_base l WHERE l.customer_id=c.customer_id),0) customer_credit,
 (SELECT COALESCE(SUM(remaining),0) FROM lots l WHERE l.customer_id=c.customer_id AND bucket='not_due') not_due,
 (SELECT COALESCE(SUM(remaining),0) FROM lots l WHERE l.customer_id=c.customer_id AND bucket='d1_30') d1_30,
 (SELECT COALESCE(SUM(remaining),0) FROM lots l WHERE l.customer_id=c.customer_id AND bucket='d31_60') d31_60,
 (SELECT COALESCE(SUM(remaining),0) FROM lots l WHERE l.customer_id=c.customer_id AND bucket='d61_90') d61_90,
 (SELECT COALESCE(SUM(remaining),0) FROM lots l WHERE l.customer_id=c.customer_id AND bucket='d90_plus') d90_plus FROM customer_sums c;
CREATE TEMP TABLE monthly AS SELECT o.customer_id,m.month,
 o.amount+COALESCE((SELECT SUM(delta) FROM posted p WHERE p.customer_id=o.customer_id AND p.bday<m.first_day),0) opening_balance,
 COALESCE((SELECT SUM(amount) FROM posted p WHERE p.customer_id=o.customer_id AND p.kind='invoice' AND p.bday>=m.first_day AND p.bday<m.next_day),0) invoice,
 COALESCE((SELECT SUM(amount) FROM posted p WHERE p.customer_id=o.customer_id AND p.kind='sales_return' AND p.bday>=m.first_day AND p.bday<m.next_day),0) sales_return,
 COALESCE((SELECT SUM(amount) FROM posted p WHERE p.customer_id=o.customer_id AND p.kind='receipt' AND p.bday>=m.first_day AND p.bday<m.next_day),0) receipt,
 COALESCE((SELECT SUM(amount) FROM posted p WHERE p.customer_id=o.customer_id AND p.kind='refund' AND p.bday>=m.first_day AND p.bday<m.next_day),0) refund,
 o.amount+COALESCE((SELECT SUM(delta) FROM posted p WHERE p.customer_id=o.customer_id AND p.bday<m.next_day),0) closing_balance
 FROM opening o CROSS JOIN months m;
''')
    query=lambda sql:[dict(r) for r in db.execute(sql)]
    result={'audit':query('SELECT * FROM audit ORDER BY record_id'),'flow':query('SELECT * FROM flow ORDER BY global_sequence'),
        'customers':query('SELECT * FROM customer_results ORDER BY customer_id'),'months':query('SELECT * FROM monthly ORDER BY customer_id,month'),
        'lots':query('SELECT * FROM lots ORDER BY customer_id,due_day,bday,sequence'),
        'controls':query('''SELECT (SELECT COALESCE(SUM(bank_known_delta),0) FROM audit WHERE bank_known=1) bank_known_net,
        (SELECT COALESCE(SUM(CASE WHEN kind='receipt' THEN amount WHEN kind='refund' THEN -amount ELSE 0 END),0) FROM posted WHERE kind IN ('receipt','refund')) matched_net_cash,
        (SELECT COALESCE(SUM(bank_known_delta),0) FROM audit WHERE bank_known=1 AND postable=0) known_suspense_net,
        (SELECT COUNT(DISTINCT logical_id) FROM audit WHERE src='orders' AND unresolved=1) unresolved_order_groups,
        (SELECT COUNT(DISTINCT logical_id) FROM audit WHERE src='payments' AND unresolved=1) unresolved_payment_groups,
        (SELECT COUNT(DISTINCT logical_id) FROM audit WHERE src='payments' AND cash_disposition='unquantified') unquantified_bank_groups''')[0]}
    db.close();return result
