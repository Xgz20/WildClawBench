"""Semantic visible-table observations; no author sheet/coordinate binding."""
from pathlib import Path
from collections import defaultdict
from datetime import date,timedelta,datetime,timezone
from decimal import Decimal,InvalidOperation
import csv,io,json,re,runpy
_api=runpy.run_path(str(Path(__file__).with_name('xlsx_observations.py')))
CandidateError=_api['CandidateError'];read_book=_api['read_book'];canon=_api['canon'];blank=_api['blank']
MONEY={'opening_balance','invoice','sales_return','receipt','refund','matched_net_cash','available_funds','closing_balance','receivable_remaining','customer_credit','not_due','d1_30','d31_60','d61_90','d90_plus','ar_delta','balance_before','balance_after','original_amount','return_amount','net_amount','allocated_cash','remaining','bank_known_delta','known_bank_delta','amount'}
FIELDS={
'customers':['customer_id','opening_balance','invoice','sales_return','receipt','refund','matched_net_cash','closing_balance','unresolved_order_rows','unresolved_payment_rows','posted_events','receivable_remaining','customer_credit','not_due','d1_30','d31_60','d61_90','d90_plus'],
'flow':['record_id','customer_id','customer_sequence','business_date','event_type','logical_id','ar_delta','balance_before','balance_after','global_sequence'],
'audit':['record_id','source','logical_id','customer_id','decision','unresolved_flag','cash_disposition','bank_known_delta'],
'months':['customer_id','month','opening_balance','invoice','sales_return','receipt','refund','closing_balance'],
'lots':['source_record_id','customer_id','document_no','business_date','due_date','original_amount','return_amount','net_amount','allocated_cash','remaining','overdue_days','bucket'],
'orders':['record_id','event_id','customer_id','document_no','event_type','business_date','entered_at','amount','currency','status','reference_customer_id','reference_document_no','due_date'],
'payments':['record_id','payment_id','customer_id','event_type','business_date','entered_at','amount','currency','status','reference_receipt_id']}
CN={'record_id':['记录ID','物理记录ID','源行ID'],'customer_id':['客户ID','客户编号'],'logical_id':['逻辑ID','逻辑事件ID'],'event_id':['订单事件ID'],'payment_id':['银行事件ID'],'source':['来源类型','源类型'],'document_no':['单据号','订单号'],'event_type':['业务类型','事件类型'],'business_date':['业务日期'],'entered_at':['录入时点','录入时间','本地录入时间'],'amount':['金额'],'currency':['币种'],'status':['状态'],'reference_customer_id':['引用客户ID'],'reference_document_no':['引用单据号','原订单号'],'reference_receipt_id':['引用收款ID'],'due_date':['到期日'],'opening_balance':['期初余额','期初净应收'],'invoice':['订单金额','订单应收'],'sales_return':['退货金额'],'receipt':['回款金额','收款金额'],'refund':['退款金额'],'matched_net_cash':['已匹配净回款'],'closing_balance':['期末余额','期末净应收'],'unresolved_order_rows':['未决订单行'],'unresolved_payment_rows':['未决银行行'],'posted_events':['已确认事件数'],'receivable_remaining':['未清应收'],'customer_credit':['客户预收','客户贷方'],'not_due':['未到期'],'d1_30':['逾期1至30天'],'d31_60':['逾期31至60天'],'d61_90':['逾期61至90天'],'d90_plus':['逾期90天以上'],'customer_sequence':['客户内序号'],'global_sequence':['全局序号'],'ar_delta':['应收增减'],'balance_before':['笔前余额'],'balance_after':['笔后余额'],'decision':['处理结果','处理状态'],'unresolved_flag':['实质未决','未决标志'],'cash_disposition':['现金归属'],'bank_known_delta':['已知银行净额'],'month':['月份'],'source_record_id':['债权来源记录ID'],'original_amount':['原始债权'],'return_amount':['有效退货'],'net_amount':['净债权'],'allocated_cash':['已分配资金'],'remaining':['剩余应收'],'overdue_days':['逾期天数'],'bucket':['账龄桶'],'control':['控制项'],'value':['控制值'],'recognized_flag':['有效债权标志']}
ALL=set(sum(FIELDS.values(),[]))|{'control','value','recognized_flag'}
ALIASES={canon(alias):key for key in ALL for alias in [key,*CN.get(key,[])]}
VALUE_CN={'posted':['已确认','已入账'],'scope_before_start':['期初前排除','业务期前排除'],'scope_after_end':['期末后排除','业务期后排除'],'scope_after_cutoff':['截点后录入','录入超截点'],'duplicate':['重传重复','相同重传'],'conflict':['冲突','同ID冲突'],'not_posted_status':['状态未确认','未入账状态'],'unsupported_currency':['不支持币种','币种排除'],'invalid_amount':['非法金额','金额无效'],'invalid_type':['非法类型','类型无效'],'unknown_customer':['未知客户','客户未匹配'],'invoice_document_ambiguous':['原单歧义','同客户单据多版本'],'cross_customer_reference':['跨客户引用'],'invoice_reference_missing':['缺少有效订单引用','原订单引用缺失'],'invoice_not_earlier':['原订单不早于退货'],'return_group_exceeds_invoice':['整组退货超额'],'receipt_reference_missing':['缺少有效收款引用','原收款引用缺失'],'receipt_not_earlier':['原收款不早于退款'],'refund_group_exceeds_receipt':['整组退款超额'],'orders':['订单','订单来源'],'payments':['银行','银行来源'],'invoice':['订单','销售订单'],'sales_return':['退货','销售退货'],'receipt':['收款','回款'],'refund':['退款'],'not_applicable':['不适用'],'outside_scope':['范围外'],'unquantified':['未量化','金额未知'],'known_suspense':['已知暂挂','已知未匹配'],'matched':['已匹配'],'cleared':['已清','已结清项'],'not_due':['未到期'],'d1_30':['逾期1至30天'],'d31_60':['逾期31至60天'],'d61_90':['逾期61至90天'],'d90_plus':['逾期90天以上']}
def category(value,want):return value==want or isinstance(value,str) and canon(value) in {canon(x) for x in VALUE_CN.get(want,[])}
def table(book,kind,prefer_minimal=True):
    needed=set(FIELDS[kind]);candidates=[]
    for sheet in book:
        grid=defaultdict(dict)
        for (r,c),cell in sheet['cells'].items():grid[r][c]=cell
        heads=[]
        for r,cells in grid.items():
            blocks=[];block=[];previous=None
            for c,cell in sorted(cells.items()):
                if blank(cell['value']) or cell.get('merged_from'):continue
                if previous is not None and c>previous+1:
                    blocks.append(block);block=[]
                block.append((c,cell));previous=c
            if block:blocks.append(block)
            for block in blocks:
                by=defaultdict(list)
                for c,cell in block:
                    key=ALIASES.get(canon(cell['value']))
                    if key:by[key].append(c)
                if needed<=set(by) and all(len(by[k])==1 for k in needed):
                    columns={k:by[k][0] for k in needed}
                    extra=len(block)-len(needed)
                    heads.append((r,columns,extra,by))
        for i,(r,cols,extra,by) in enumerate(sorted(heads,key=lambda item:(item[0],min(item[1].values())))):
            end=min((n for n,_,_,_ in heads if n>r),default=50001);rows=[]
            for rn,cells in sorted(grid.items()):
                if not r<rn<end:continue
                row={k:cells.get(c,{}).get('value') for k,c in cols.items()}
                ident=row.get('record_id') or row.get('source_record_id') or row.get('customer_id')
                if not isinstance(ident,str) or not re.fullmatch(r'(?:C\d\d|[OP]\d{3}|OPEN_C\d\d)',ident):continue
                if kind=='lots' and 'recognized_flag' in by:
                    if cells.get(by['recognized_flag'][0],{}).get('value')!=1:continue
                row.update(_sheet=sheet['name'],_row=rn,_columns=cols,_date1904=sheet['date1904'],_visible=all(grid[r][c].get('visible') and cells.get(c,{'visible':True}).get('visible') for c in cols.values()),_cells={k:cells.get(c,{}) for k,c in cols.items()})
                rows.append(row)
            if rows:candidates.append((extra,rows))
    # Prefer a purpose-built readable output over a superset event build. Equal
    # alternatives must be unambiguous; partitioned customer sheets can combine.
    if not candidates:return []
    best=min(n for n,_ in candidates);rows=[row for n,part in candidates if not prefer_minimal or n==best for row in part]
    return rows
def day(value,date1904=False):
    if isinstance(value,(int,float)) and not isinstance(value,bool):return ((date(1904,1,1) if date1904 else date(1899,12,30))+timedelta(days=int(value))).isoformat()
    if isinstance(value,str):
        try:return date.fromisoformat(value[:10]).isoformat()
        except ValueError:return value
    return value
def equal(a,b,key=''):
    if b is None:return blank(a)
    if b=='' and blank(a):return True
    if isinstance(b,bool):return a in ([True,1,'true','TRUE','1'] if b else [False,0,'false','FALSE','0'])
    if key in ['business_date','due_date']:return day(a)==b
    if key in ['source','event_type','decision','cash_disposition','bucket']:return category(a,b)
    if key in MONEY or isinstance(b,(int,float)) or isinstance(b,str) and re.fullmatch(r'[+-]?\d+(?:\.\d+)?',b):
        if isinstance(a,bool) or blank(a):return False
        try:return Decimal(str(a)).is_finite() and abs(Decimal(str(a))-Decimal(str(b)))<=Decimal('0.000001')
        except InvalidOperation:return False
    return a==b or blank(a) and b==''
def controls(book):
    results={}
    for sheet in book:
        grid=defaultdict(dict)
        for (r,c),cell in sheet['cells'].items():grid[r][c]=cell
        for r,cols in grid.items():
            keycols=[c for c,cell in cols.items() if ALIASES.get(canon(cell['value']))=='control'];valcols=[c for c,cell in cols.items() if ALIASES.get(canon(cell['value']))=='value']
            if len(keycols)!=1 or len(valcols)!=1:continue
            for rn,cells in grid.items():
                if rn<=r:continue
                key=cells.get(keycols[0],{}).get('value');cell=cells.get(valcols[0],{})
                if isinstance(key,str) and re.fullmatch('[A-Za-z_]+',key):
                    if key in results:raise CandidateError('ambiguous control '+key)
                    results[key]={'value':cell.get('value'),'visible':cells.get(keycols[0],{}).get('visible') and cell.get('visible')}
    return results
def observe(path,expected):
    book=read_book(path);checks={};tables={}
    for s in book:
        checks['errors/'+s['name']]=not s['errors']
    specs={'customers':list(expected['customers'].values()),'flow':expected['flow'],'audit':list(expected['audit'].values()),'months':expected['months'],'lots':expected['lots']}
    identities={'customers':lambda r:r['customer_id'],'flow':lambda r:r['record_id'],'audit':lambda r:r['record_id'],'months':lambda r:(r['customer_id'],r['month']),'lots':lambda r:r['source_record_id']}
    for kind,wanted in specs.items():
        actual=table(book,kind);tables[kind]=actual;key=identities[kind];by=defaultdict(list)
        for row in actual:by[key(row)].append(row)
        expected_ids={key(r) for r in wanted};checks[kind+'/identity_set']=set(by)==expected_ids
        if kind=='flow':checks['flow/visible_business_order']=[key(r) for r in actual]==[key(r) for r in wanted]
        for row in wanted:
            identity=key(row);prefix=kind+'/'+str(identity);matches=by.get(identity,[]);checks[prefix+'/unique']=len(matches)==1
            if len(matches)!=1:actual_row={}
            else:actual_row=matches[0]
            checks[prefix+'/visible']=bool(actual_row.get('_visible'))
            for field in FIELDS[kind]:
                ek={'unresolved_flag':'unresolved','bank_known_delta':'bank_known_delta'}.get(field,field)
                value=actual_row.get(field)
                if field in ['business_date','due_date']:value=day(value,actual_row.get('_date1904',False))
                checks[prefix+'/'+field]=equal(value,row[ek],field)
    found=controls(book)
    for key,want in expected['controls'].items():
        checks['controls/'+key]=key in found and found[key]['visible'] and equal(found[key]['value'],want)
    groups={k:[v for name,v in checks.items() if name.startswith(k+'/')] for k in ['customers','flow','audit','months','lots','controls','errors']}
    return {'checks':checks,'scores':{k:sum(v)/len(v) if v else 0 for k,v in groups.items()},'complete':all(checks.values()),'tables':{k:len(v) for k,v in tables.items()},'controls':found}
def matching_literal(row,record,source):
    if row['record_id']!=record['record_id'] or not row['_visible']:return False
    for key in FIELDS[source]:
        value=record.get(key,'')
        if key=='entered_at':
            local=datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(timezone(timedelta(hours=8))).replace(tzinfo=None)
            base=datetime(1904,1,1) if row['_date1904'] else datetime(1899,12,30);serial=(local-base).total_seconds()/86400
            actual=row.get(key)
            if row['_cells'][key].get('kind')=='d':
                try:actual=(datetime.fromisoformat(actual.replace('Z','+00:00')).replace(tzinfo=None)-base).total_seconds()/86400
                except (ValueError,TypeError,AttributeError):return False
            if not equal(actual,serial,key):return False
        else:
            actual=day(row.get(key),row['_date1904']) if key in ['business_date','due_date'] else row.get(key)
            if not equal(actual,float(value) if key=='amount' else value,key):return False
    return all(not row['_cells'][key].get('formula') and (isinstance(row['_cells'][key].get('value'),(int,float)) or key!='amount' and row['_cells'][key].get('kind')=='d') for key in ['amount','business_date','entered_at'])

def raw_inventory(path,records):
    book=read_book(path);checks={}
    for source in ['orders','payments']:
        rows=table(book,source,False);by=defaultdict(list)
        for row in rows:by[row['record_id']].append(row)
        for record in records[source]:checks[record['record_id']]=any(matching_literal(row,record,source) for row in by[record['record_id']])
    return {'checks':checks,'complete':all(checks.values())}

def raw_targets(path,record,source):
    # Only literal editable drivers with the actual full source identity/payload
    # qualify. Formula audit views are not mistaken for raw source inputs.
    book=read_book(path);rows=table(book,source,False);matches=[]
    for row in rows:
        if matching_literal(row,record,source):
            matches.append({'sheet':row['_sheet'],'cell':row['_cells']['entered_at']['cell'],'old_value':row['entered_at'],'date1904':row['_date1904']})
    return matches

def truth_map(expected):
    """Source-derived semantic values corresponding to observed check keys."""
    out={};specs={'customers':list(expected['customers'].values()),'flow':expected['flow'],'audit':list(expected['audit'].values()),'months':expected['months'],'lots':expected['lots']}
    identity={'customers':lambda r:r['customer_id'],'flow':lambda r:r['record_id'],'audit':lambda r:r['record_id'],'months':lambda r:(r['customer_id'],r['month']),'lots':lambda r:r['source_record_id']}
    for kind,rows in specs.items():
        key=identity[kind];out[kind+'/identity_set']=sorted(str(key(r)) for r in rows)
        for row in rows:
            for field in FIELDS[kind]:out[kind+'/'+str(key(row))+'/'+field]=row['unresolved' if field=='unresolved_flag' else field]
    out['flow/visible_business_order']=[r['record_id'] for r in expected['flow']]
    out.update({'controls/'+key:value for key,value in expected['controls'].items()})
    return out

def read_exceptions(path,expected):
    try:
        with Path(path).open(encoding='utf-8-sig',newline='') as f:
            reader=csv.DictReader(f,strict=True);fields=reader.fieldnames
            required=['record_id','source','logical_id','customer_id','decision','unresolved','cash_disposition','known_bank_delta','source_file','source_locator','next_action']
            if not fields or len(fields)!=len(set(fields)) or not set(required)<=set(fields):raise CandidateError('exceptions CSV header contract')
            rows=list(reader)
    except (UnicodeError,csv.Error) as error:raise CandidateError('exceptions CSV encoding or syntax') from error
    if len(rows)>1000 or any(None in row or any(v is None for v in row.values()) for row in rows):raise CandidateError('exceptions CSV malformed or oversized')
    by=defaultdict(list)
    for row in rows:by[row['record_id']].append(row)
    checks={'exact_nonposted_set':set(by)=={r['record_id'] for r in expected['exceptions']}}
    binding=[];decisions=defaultdict(list)
    for want in expected['exceptions']:
        rid=want['record_id'];matches=by[rid];checks[rid+'/unique']=len(matches)==1;row=matches[0] if len(matches)==1 else {}
        for key,value in want.items():
            if key=='source_file':checks[rid+'/'+key]=str(row.get(key,'')).replace('\\','/').rsplit('/',1)[-1]==value
            elif key=='source_locator':
                # ID itself is an unambiguous native source locator. Coordinates
                # are accepted if they resolve to that actual physical row.
                source=json.loads(Path(__file__).with_name('source_records.json').read_text(encoding='utf-8'))
                items=source[want['source']];line=next(i for i,item in enumerate(items,6 if want['source']=='orders' else 2) if item['record_id']==rid)
                choices={rid,'订单记录!A'+str(line),'订单记录!A'+str(line)+':M'+str(line)} if want['source']=='orders' else {rid,'row '+str(line),'第'+str(line)+'行','line '+str(line)}
                locator=str(row.get(key,'')).strip();checks[rid+'/'+key]=locator in choices or locator.removeprefix(want['source_file']+'#') in choices
            else:checks[rid+'/'+key]=equal(row.get(key),value,'known_bank_delta' if key=='known_bank_delta' else key)
        checks[rid+'/next_action']=bool(str(row.get('next_action','')).strip())
        decisions[want['decision']].extend(v for key,v in checks.items() if key.startswith(rid+'/') and key.rsplit('/',1)[1] not in {'source_file','source_locator','next_action'})
        binding.extend(checks[rid+'/'+k] for k in ['source_file','source_locator','logical_id','customer_id'])
    mean=lambda xs:sum(xs)/len(xs) if xs else 0
    return {'checks':checks,'complete':all(checks.values()),'score':mean([mean(v) for v in decisions.values()])*checks['exact_nonposted_set'],'binding_score':mean(binding)*checks['exact_nonposted_set']}

def read_method(path,expected):
    try:text=Path(path).read_text(encoding='utf-8-sig')
    except UnicodeError as error:raise CandidateError('method.md must be UTF-8') from error
    checks={}
    for key,value in expected['controls'].items():
        found=re.findall(r'(?m)^\s*'+re.escape(key)+r'\s*[:：=]\s*([^\n]+?)\s*$',text)
        checks[key]=len(found)==1 and equal(found[0].strip().replace(',',''),value)
    checks['fixed_business_period']=all(d in text for d in ['2026-06-30','2026-07-01','2026-09-30'])
    checks['fixed_cutoff']='2026-10-05' in text and '18:00' in text and ('Asia/Shanghai' in text or '上海' in text)
    checks['nonempty']=len(text.strip())>=150
    return {'checks':checks,'score':sum(checks.values())/len(checks),'complete':all(checks.values()),'limit':'Bounded period and disclosed-control consistency, not an open prose quality or accounting-expert judgement.'}
