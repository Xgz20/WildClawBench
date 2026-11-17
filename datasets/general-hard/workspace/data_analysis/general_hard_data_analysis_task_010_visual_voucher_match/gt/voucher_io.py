"""Passive bounded OOXML cell observations and semantic table discovery."""
from pathlib import Path
from decimal import Decimal,InvalidOperation
from collections import defaultdict
import csv,io,json,math,posixpath,re,zipfile
import xml.etree.ElementTree as E
X='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
D='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
class CandidateError(ValueError):pass
def integer(v,label):
    try:return int(v)
    except (TypeError,ValueError) as error:raise CandidateError('invalid integer '+label) from error
def point(address):
    match=re.fullmatch(r'([A-Z]+)([1-9][0-9]*)',address or '')
    if not match:raise CandidateError('invalid cell address')
    col=0
    for c in match[1]:col=col*26+ord(c)-64
    row=integer(match[2],'row')
    if not 1<=col<=512 or not 1<=row<=50000:raise CandidateError('candidate table coordinate limit')
    return row,col
def canon(v):return re.sub(r'[\s_()（）/、:：-]','',str(v or '')).casefold()
def sid(value,prefix):
    if not isinstance(value,str):return None
    result=value.strip().upper()
    return result if re.fullmatch(prefix+r'[0-9]+',result) else None
def blank(v):return v is None or isinstance(v,str) and not v.strip()
def equal(value,expected,tolerance=0):
    if expected is None:return blank(value)
    if isinstance(expected,(int,float)):
        if isinstance(value,bool) or blank(value):return False
        try:a=Decimal(str(value));b=Decimal(str(expected))
        except InvalidOperation:return False
        return a.is_finite() and abs(a-b)<=Decimal(str(tolerance))+Decimal('1e-12')
    return value==expected
def read_book(path):
    p=Path(path)
    try:archive=zipfile.ZipFile(p)
    except zipfile.BadZipFile as error:raise CandidateError('invalid XLSX ZIP') from error
    with archive as z:
        names=z.namelist()
        if len(names)!=len(set(names)) or len(names)>5000 or sum(i.file_size for i in z.infolist())>100000000:raise CandidateError('XLSX package limit or duplicates')
        def xml(name):
            try:raw=z.read(name)
            except KeyError as error:raise CandidateError('missing XLSX part '+name) from error
            if len(raw)>16000000 or b'<!DOCTYPE' in raw.replace(b'\0',b'').upper() or b'<!ENTITY' in raw.replace(b'\0',b'').upper():raise CandidateError('unsafe XLSX XML')
            try:return E.fromstring(raw)
            except E.ParseError as error:raise CandidateError('invalid XLSX XML '+name) from error
        strings=[]
        if 'xl/sharedStrings.xml' in names:strings=[''.join(n.text or '' for n in s.iter(X+'t')) for s in xml('xl/sharedStrings.xml')]
        font_defs=[];fill_defs=[];formats={};xfs=[]
        if 'xl/styles.xml' in names:
            styles=xml('xl/styles.xml');font_defs=styles.findall(X+'fonts/'+X+'font');fill_defs=styles.findall(X+'fills/'+X+'fill');xfs=styles.findall(X+'cellXfs/'+X+'xf')
            formats={integer(n.get('numFmtId'),'format id'):n.get('formatCode','') for n in styles.findall(X+'numFmts/'+X+'numFmt')}
        def invisible(style):
            if style>=len(xfs):return False
            xf=xfs[style];fid=integer(xf.get('fontId','0'),'font id');fillid=integer(xf.get('fillId','0'),'fill id');fmt=integer(xf.get('numFmtId','0'),'numFmt id')
            font=font_defs[fid] if 0<=fid<len(font_defs) else None;fill=fill_defs[fillid] if 0<=fillid<len(fill_defs) else None
            if formats.get(fmt,'').replace(' ','') in {';;;',';;;;'}:return True
            if font is None:return False
            size=font.find(X+'sz');color=font.find(X+'color');fg=fill.find(X+'patternFill/'+X+'fgColor') if fill is not None else None
            try:tiny=size is not None and float(size.get('val','11'))<6
            except ValueError as error:raise CandidateError('invalid font size') from error
            white=color is not None and color.get('rgb','').upper().endswith('FFFFFF')
            white_background=fg is None or fg.get('rgb','').upper().endswith('FFFFFF')
            return tiny or white and white_background
        rels={n.get('Id'):n.get('Target') for n in xml('xl/_rels/workbook.xml.rels') if n.get('TargetMode')!='External'}
        out=[];seen_names=set();workbook=xml('xl/workbook.xml');sheets=workbook.find(X+'sheets');properties=workbook.find(X+'workbookPr');date1904=properties is not None and properties.get('date1904','0') in {'1','true'}
        if sheets is None:raise CandidateError('missing XLSX worksheets')
        for sheet in sheets:
            name=sheet.get('name');target=rels.get(sheet.get(D+'id'))
            if not name or name in seen_names or not target:raise CandidateError('ambiguous worksheet identity')
            seen_names.add(name);part=target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/'+target)
            if part.startswith('../') or part not in names:raise CandidateError('missing worksheet relationship')
            doc=xml(part);cells={};hidden_rows=set();hidden_cols=[];errors=[]
            for row in doc.findall(X+'sheetData/'+X+'row'):
                rn=integer(row.get('r'),'row')
                if row.get('hidden','0') in {'1','true'} or row.get('ht')=='0':hidden_rows.add(rn)
                for c in row.findall(X+'c'):
                    pos=point(c.get('r'));kind=c.get('t');v=c.find(X+'v');value=v.text if v is not None else None
                    if pos in cells:raise CandidateError('duplicate cell address')
                    if kind=='s':
                        i=integer(value,'shared string')
                        if not 0<=i<len(strings):raise CandidateError('invalid shared string index')
                        value=strings[i]
                    elif kind=='inlineStr':value=''.join(t.text or '' for t in c.iter(X+'t'))
                    elif kind=='b':value=value=='1'
                    elif kind=='e':errors.append({'cell':c.get('r'),'error':value})
                    elif kind not in {'str','d'} and value is not None:
                        try:value=float(value)
                        except ValueError as error:raise CandidateError('invalid numeric cell') from error
                        if not math.isfinite(value):raise CandidateError('nonfinite numeric cell')
                    cells[pos]={'value':value,'kind':kind,'cell':c.get('r'),'row':pos[0],'col':pos[1],'style':integer(c.get('s','0'),'cell style'),'formula':c.find(X+'f') is not None}
            if len(cells)>100000:raise CandidateError('XLSX cell limit')
            for col in doc.findall(X+'cols/'+X+'col'):
                if col.get('hidden','0') in {'1','true'} or col.get('width')=='0':hidden_cols.append((integer(col.get('min'),'column min'),integer(col.get('max'),'column max')))
            for m in doc.findall(X+'mergeCells/'+X+'mergeCell'):
                parts=m.get('ref','').split(':')
                if len(parts)!=2:raise CandidateError('invalid merged range')
                (r1,c1),(r2,c2)=map(point,parts)
                if r2<r1 or c2<c1 or (r2-r1+1)*(c2-c1+1)>10000:raise CandidateError('merged range limit')
                anchor=cells.get((r1,c1))
                if anchor:
                    for r in range(r1,r2+1):
                        for c in range(c1,c2+1):
                            if (r,c)==(r1,c1):continue
                            old=cells.get((r,c))
                            if old is not None and not blank(old['value']) and old['value']!=anchor['value']:raise CandidateError('conflicting merged cells')
                            cells[r,c]={**anchor,'row':r,'col':c,'merged_from':(r1,c1)}
                if len(cells)>100000:raise CandidateError('expanded cell limit')
            state=sheet.get('state','visible')
            for (r,c),cell in cells.items():cell['visible']=bool(state=='visible' and r not in hidden_rows and not any(a<=c<=b for a,b in hidden_cols) and not invisible(cell['style']))
            out.append({'name':name,'state':state,'cells':cells,'errors':errors,'date1904':date1904})
        return out

# These are semantic column names, not fixed worksheet or cell locations.
KEY_FIELDS=['voucher_no','counterparty_id','business_date','currency','direction']
FIELDS={
 'images':['file',*KEY_FIELDS,'counterparty_name','printed_amount','has_handwritten_correction','handwritten_amount','status_selection','approval_location','approval_crossed_out','correction_status'],
 'ledger':['entry_id',*KEY_FIELDS,'ledger_amount','scope_status','match_status','canonical_entry_id','action','target_amount','proposed_delta','source_files','reason'],
 'groups':[*KEY_FIELDS,'state','effective_amount','canonical_entry_id','source_files','reason'],
 'raw':['entry_id','voucher_no','counterparty_id','counterparty_name','business_date','currency','direction','amount','book_status','posted_at'],
 'summary':['key','value']}
CN={
 'file':['图片文件','凭据图片','源图片','文件'], 'voucher_no':['凭据编号','凭证编号'],
 'counterparty_id':['往来方编码','往来方编号'], 'counterparty_name':['往来方名称','往来方'],
 'business_date':['业务日期'], 'currency':['币种'], 'direction':['方向'],
 'printed_amount':['原始金额','印刷金额'], 'has_handwritten_correction':['有手写更正','是否手写更正','是否有手写更正'],
 'handwritten_amount':['手写金额','手写更正金额'], 'status_selection':['状态选择','状态章落格','状态确认'],
 'approval_location':['复核位置','复核章位置','更正复核章位置'], 'approval_crossed_out':['复核章划销','复核章是否划销','复核章被划销'],
 'correction_status':['更正状态','更正确认状态'], 'entry_id':['账目编号','账目ID','分录编号'],
 'ledger_amount':['账面金额','原账金额'], 'amount':['原账金额','账面金额'], 'book_status':['账面状态','记账状态'],
 'posted_at':['入账时间','录入时间'], 'scope_status':['范围状态','核对范围'], 'match_status':['匹配状态'],
 'canonical_entry_id':['首笔账目','首笔编号','首笔账目编号','首笔entry_id'], 'action':['动作','建议动作','处理动作'],
 'target_amount':['目标金额'], 'proposed_delta':['建议差额','调账差额'], 'source_files':['源图片列表','来源图片','来源文件','凭据文件'],
 'state':['组状态','经济组状态'], 'effective_amount':['有效金额','组有效金额'], 'reason':['依据','理由','原因'],
 'key':['汇总项','指标','控制项','key'], 'value':['汇总值','指标值','控制值','value']}
for _field,_names in {
 'file':['图片文件名','文件名','扫描文件','源文件'], 'voucher_no':['凭据号','凭证号'],
 'counterparty_id':['往来方ID','往来单位编码'], 'counterparty_name':['往来单位名称'],
 'business_date':['业务发生日期','日期'], 'currency':['货币'], 'direction':['业务方向','费用方向'],
 'printed_amount':['票面金额','原金额'], 'has_handwritten_correction':['存在手写更正','是否更正'],
 'handwritten_amount':['手写值','更正金额'], 'status_selection':['凭据状态','状态格','状态章'],
 'approval_location':['复核章所在栏','更正复核位置'], 'approval_crossed_out':['复核章是否被划销'],
 'correction_status':['更正批准状态','手写更正状态'], 'scope_status':['范围判定','范围分类'],
 'match_status':['匹配结论'], 'canonical_entry_id':['首笔账目ID','保留账目编号'],
 'action':['处理方式'], 'source_files':['源文件列表','来源图片列表','源文件','凭据图片'],
 'state':['凭据组状态','凭据状态','状态'], 'effective_amount':['确认金额','组确认金额'],
 'key':['项目'], 'value':['数值']}.items():CN.setdefault(_field,[]).extend(_names)
SUMMARY_CN={
 'image_count':['图片数'], 'voucher_group_count':['凭据组数'], 'ledger_row_count':['账目行数'],
 'eligible_entry_count':['本轮账目行数','范围内账目数'], 'excluded_entry_count':['排除行数'],
 'eligible_book_amount':['本轮账面金额','范围内账面金额'], 'proposed_delta_sum':['建议差额合计','调账建议合计'],
 'book_amount_after_proposals':['建议获批后测算账面金额','建议后测算账面金额','测算账面金额'],
 'unresolved_book_amount':['待核账面金额','未决账面金额'], 'unresolved_entry_count':['待核账目行数','未决账目行数'],
 'proposal_count':['金额建议数','建议数量'], 'unbooked_pending_group_count':['未入账待核组数','缺账待核组数'],
 'confirmed_voucher_target_sum':['已确认凭据目标金额合计'], 'fully_reconciled':['全部核清','是否完全核清'],
 'applied':['已应用','已调账'], 'approval_required':['需要审批','需审批']}
CORE_SUMMARY=['eligible_book_amount','proposed_delta_sum','book_amount_after_proposals','unresolved_book_amount','unresolved_entry_count','proposal_count','unbooked_pending_group_count']
NULL_TEXT={'','null','none','unknown','n/a','na','未决','未知','待核','无','不适用','—','-'}
ENUM={
 'expense':['费用','支出'], 'valid':['有效','有效格'], 'void':['作废','作废格'], 'pending':['待核','待审批','待核格'],
 'general':['一般复核','一般复核格'], 'correction':['更正复核','更正复核格'], 'none':['无更正','无','无手写更正'],
 'approved':['已批准','已确认'], 'unapproved':['未批准','未确认','未经批准'],
 'confirmed':['已确认','确认'], 'eligible':['范围内','本轮核对'],
 'excluded_period':['期间排除','期间外'], 'excluded_currency':['币种排除','非本轮币种'],
 'excluded_status':['状态排除','非posted状态'], 'excluded':['已排除','排除','scope_excluded'],
 'matched_confirmed':['匹配已确认','匹配有效'], 'matched_void':['匹配作废'], 'matched_pending':['匹配待核'],
 'no_voucher':['未匹配','无凭据','无匹配凭据','unmatched','no_exact_key_match'],
 'keep':['保留'], 'correct_amount':['更正金额','调整金额'], 'reverse_duplicate':['冲回重复','重复冲回'],
 'reverse_void':['冲回作废','作废冲回'], 'hold':['暂缓','待核保留'], 'create':['新增','补账'],
 'posted':['已入账','已过账'], 'draft':['草稿'], 'reversed':['已冲回','已冲销'],
 'ledger_hold':['账目待核'], 'unbooked_pending':['未入账待核']}
ENUM_LOOKUP={canon(a):k for k,items in ENUM.items() for a in [k,*items]}
SUMMARY_LOOKUP={canon(a):k for k,items in SUMMARY_CN.items() for a in [k,*items]}

def null(v):
    return v is None or isinstance(v,str) and v.strip().casefold() in NULL_TEXT

def enum(v,field=None):
    # Chinese '已确认' means approved in a correction field, confirmed in a group.
    # Resolve existing aliases within the field before the shared fallback.
    if field=='correction_status':
        normalized=canon(v)
        for state in ['none','approved','unapproved']:
            if normalized in {canon(alias) for alias in [state,*ENUM[state]]}:return state
    return ENUM_LOOKUP.get(canon(v),str(v).strip() if v is not None else None)

def boolean(v):
    if isinstance(v,bool):return v
    if v in (0,1):return bool(v)
    if isinstance(v,str):
        if v.strip().casefold() in {'true','1','yes','是','有','已划销','需要'}:return True
        if v.strip().casefold() in {'false','0','no','否','无','未划销','不需要'}:return False
    return None

def money(v):
    if null(v):return None
    if isinstance(v,bool):return 'INVALID_AMOUNT'
    try:
        n=Decimal(str(v).replace(',','').strip())
        if not n.is_finite() or abs(n)>Decimal('100000000000'):return 'INVALID_AMOUNT'
        rounded=n.quantize(Decimal('.01'))
        if abs(n-rounded)>Decimal('.0000001'):return 'INVALID_AMOUNT'
        return format(rounded,'.2f')
    except (InvalidOperation,ValueError):return 'INVALID_AMOUNT'

def number(v):
    if isinstance(v,bool) or null(v):return None
    try:
        n=Decimal(str(v));return n if n.is_finite() else None
    except (InvalidOperation,ValueError):return None

def text(v):return str(v).strip() if not null(v) else None

def date_value(v,date1904=False,timestamp=False):
    from datetime import datetime,timedelta,timezone
    if isinstance(v,(int,float)) and not isinstance(v,bool):
        origin=datetime(1904,1,1) if date1904 else datetime(1899,12,30)
        try:d=origin+timedelta(seconds=round(float(v)*86400))
        except (ValueError,OverflowError):return str(v)
    elif isinstance(v,str):
        try:d=datetime.fromisoformat(v.strip().replace('/','-').replace('Z','+00:00'))
        except ValueError:return v.strip()
    else:return v
    if not timestamp:return d.date().isoformat()
    if d.tzinfo is None:d=d.replace(tzinfo=timezone(timedelta(hours=8)))
    return d.astimezone(timezone(timedelta(hours=8))).isoformat(timespec='seconds')

def file_name(v):
    if not isinstance(v,str):return None
    s=v.strip().replace('\\','/')
    while s.startswith('./'):s=s[2:]
    if s.startswith(('input/','exec/')):s=s.split('/',1)[1]
    if re.fullmatch(r'voucher_\d{2}\.png',s):s='vouchers/'+s
    return s if re.fullmatch(r'vouchers/voucher_\d{2}\.png',s) else None

def source_files(v):
    if null(v):return []
    if isinstance(v,str):
        if v.strip().startswith('['):
            try:v=json.loads(v)
            except (ValueError,TypeError):return None
        else:v=re.split(r'[;,；，、|\n]+',v.strip())
    if not isinstance(v,list):return None
    normalized=[file_name(x) for x in v]
    if any(x is None for x in normalized):return None
    return sorted(set(normalized))

def key(row):
    obj=row.get('key',row)
    if not isinstance(obj,dict):return None
    vals=[]
    for field in KEY_FIELDS:
        value=obj.get(field)
        if field=='business_date' and (isinstance(value,bool) or not isinstance(value,(str,int,float))):return None
        if field!='business_date' and not isinstance(value,str):return None
        if field=='business_date':value=date_value(value,row.get('_date1904',False))
        elif field=='direction':value=enum(value)
        else:value=text(value)
        vals.append(value)
    return tuple(vals) if all(v is not None for v in vals) else None

def aliases(kind):
    result={}
    for f in FIELDS[kind]:
        for a in [f,*CN.get(f,[])]:result[canon(a)]=f
    if kind=='ledger':result[canon('amount')]='ledger_amount'
    if kind=='raw':result[canon('ledger_amount')]='amount'
    if 'source_files' in FIELDS[kind]:result[canon('voucher_files')]='source_files'
    return result

def tables(book,kind):
    needed=set(FIELDS[kind]);lookup=aliases(kind);result=[];seen=set()
    for sheet in book:
        grid=defaultdict(dict)
        for (r,c),cell in sheet['cells'].items():grid[r][c]=cell
        heads=[];all_headers=[]
        for rn,cells in sorted(grid.items()):
            row=[(c,cell) for c,cell in sorted(cells.items()) if not blank(cell['value']) and not cell.get('merged_from')]
            blocks=[];part=[];prev=None
            for c,cell in row:
                if prev is not None and c>prev+1:
                    if part:blocks.append(part)
                    part=[]
                part.append((c,cell));prev=c
            if part:blocks.append(part)
            for block in blocks:
                if sum(canon(cell['value']) in lookup for _,cell in block)>=2:all_headers.append((rn,block[0][0],block[-1][0]))
            for block in blocks+[row]:
                found=defaultdict(list)
                for c,cell in block:
                    f=lookup.get(canon(cell['value']))
                    if f:found[f].append(c)
                if not needed<=set(found) or any(len(found[f])!=1 for f in needed):continue
                cols={f:found[f][0] for f in needed};signature=(sheet['name'],rn,tuple(sorted(cols.items())))
                if signature in seen:continue
                seen.add(signature);heads.append((rn,cols,min(cols.values()),max(cols.values())))
        for head,cols,lo,hi in heads:
            end=min((r for r,l,h in all_headers if r>head and l<=hi and h>=lo),default=50001)
            for rn,cells in sorted(grid.items()):
                if not head<rn<end:continue
                row={f:cells.get(c,{}).get('value') for f,c in cols.items()}
                if kind=='summary':
                    if canon(row['key']) not in SUMMARY_LOOKUP:continue
                    row['key']=SUMMARY_LOOKUP[canon(row['key'])]
                elif kind=='images':
                    if blank(row['file']) and blank(row['voucher_no']):continue
                elif kind in {'ledger','raw'}:
                    if blank(row['entry_id']):continue
                elif blank(row['voucher_no']) or blank(row['counterparty_id']):continue
                row.update(_sheet=sheet['name'],_row=rn,_columns=cols,_cells={f:cells.get(c,{}) for f,c in cols.items()},_date1904=sheet['date1904'],_visible=all(grid[head][c].get('visible') and cells.get(c,{'visible':True}).get('visible') for c in cols.values()))
                result.append(row)
    return result

def read_json(path):
    def unique(pairs):
        d={}
        for k,v in pairs:
            if k in d:raise CandidateError('duplicate JSON key '+k)
            d[k]=v
        return d
    try:result=json.loads(Path(path).read_text(encoding='utf-8-sig'),object_pairs_hook=unique,parse_constant=lambda x:(_ for _ in ()).throw(CandidateError('nonfinite JSON number')))
    except (ValueError,UnicodeError) as exc:raise CandidateError('invalid JSON '+Path(path).name+': '+str(exc)) from exc
    if not isinstance(result,dict):raise CandidateError('JSON top level must be object')
    return result

def summary_values(rows):
    by=defaultdict(list)
    for r in rows:by[r['key']].append(r)
    return {k:parts[0]['value'] for k,parts in by.items() if len(parts)==1 and parts[0]['_visible']},all(len(parts)==1 and parts[0]['_visible'] for parts in by.values())

def summary_checks(actual,want):
    if not isinstance(actual,dict):return {f:False for f in CORE_SUMMARY}
    return {f:(money(actual.get(f))==money(want[f]) and not null(actual.get(f)) if 'amount' in f or f=='proposed_delta_sum' else number(actual.get(f))==number(want[f]) and not null(actual.get(f))) for f in CORE_SUMMARY}

def source_inventory(book,source):
    rows=tables(book,'raw');by=defaultdict(list)
    for row in rows:by[text(row['entry_id'])].append(row)
    checks={}
    for want in source:
        found=by.get(want['entry_id'],[]);ok=[]
        for row in found:
            checks_row=[]
            for f in FIELDS['raw']:
                a=row.get(f);b=want[f]
                if f=='amount':checks_row.append(money(a)==money(b) and not null(a))
                elif f=='business_date':checks_row.append(date_value(a,row['_date1904'])==b)
                elif f=='posted_at':checks_row.append(date_value(a,row['_date1904'],True)==date_value(b,timestamp=True))
                elif f in {'book_status','direction'}:checks_row.append(enum(a)==enum(b))
                else:checks_row.append(text(a)==b)
            ok.append(row['_visible'] and all(checks_row))
        checks[want['entry_id']]=bool(found) and all(ok)
    return {'checks':checks,'complete':set(by)=={r['entry_id'] for r in source} and all(checks.values()),'row_count':len(rows)}

def approval_ok(obj):
    return isinstance(obj,dict) and obj.get('approval_required') is True and enum(obj.get('approval_status'))=='pending' and obj.get('applied') is False

def unsafe_claims(value,path='$'):
    found=[]
    if isinstance(value,dict):
        for k,v in value.items():
            ck=canon(k)
            if ck in {'applied','已应用','已调账'} and boolean(v) is True:found.append(path+'.'+k)
            if ck in {'approvalrequired','需要审批','需审批'} and boolean(v) is False:found.append(path+'.'+k)
            if ck in {'approvalstatus','审批状态'} and enum(v) not in {'pending',None} and not null(v):found.append(path+'.'+k)
            if ck in {'fullyreconciled','全部核清','是否完全核清'} and boolean(v) is True:found.append(path+'.'+k)
            found+=unsafe_claims(v,path+'.'+str(k))
    elif isinstance(value,list):
        for i,v in enumerate(value):found+=unsafe_claims(v,path+'['+str(i)+']')
    return found

def visual_binding(actual,regions):
    from collections import Counter
    checks={};shape=True
    if not isinstance(actual,dict) or not isinstance(actual.get('images'),list):return {'checks':{},'score':0.,'complete':False}
    expected=regions['images'];by=defaultdict(list)
    for row in actual['images']:
        if isinstance(row,dict):by[file_name(row.get('file'))].append(row)
        else:shape=False
    shape=shape and set(by)==set(expected) and all(len(v)==1 for v in by.values())
    windows={r['file']:{f['feature']:f['bbox'] for f in r['features']} for r in regions['regions']}
    for filename,meta in expected.items():
        prefix=filename+'/';parts=by.get(filename,[]);row=parts[0] if len(parts)==1 else {};w,h=meta['width'],meta['height']
        checks[prefix+'source_identity']=len(parts)==1 and row.get('sha256')==meta['sha256'] and row.get('width')==w and row.get('height')==h
        observations=row.get('observations',[]);obs=defaultdict(list)
        if not isinstance(observations,list):observations=[];shape=False
        for item in observations:
            if isinstance(item,dict) and isinstance(item.get('feature'),str):obs[item['feature']].append(item)
            else:shape=False
        required=['identity','date_currency_direction','amount','status_context']+(['local_review'] if filename.endswith(('05.png','06.png','12.png')) or 'local_review' in obs else [])
        for feature in required:
            valid=False
            for item in obs.get(feature,[]):
                box=item.get('bbox');system=item.get('coordinate_system');observation=item.get('observation')
                if not isinstance(box,list) or len(box)!=4 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in box):continue
                if system=='normalized':
                    if not all(0<=v<=1 for v in box):continue
                    box=[box[0]*w,box[1]*h,box[2]*w,box[3]*h]
                elif system!='pixel':continue
                x0,y0,x1,y1=box
                if not (0<=x0<x1<=w and 0<=y0<y1<=h):continue
                area=(x1-x0)*(y1-y0)
                if area>w*h*.25:continue
                a,b,c,d=windows[filename][feature];intersection=max(0,min(x1,c)-max(x0,a))*max(0,min(y1,d)-max(y0,b));union=area+(c-a)*(d-b)-intersection
                if union>0 and intersection/union>=.08 and isinstance(observation,str) and observation.strip():valid=True
            checks[prefix+feature]=checks[prefix+'source_identity'] and valid
    return {'checks':checks,'score':sum(checks.values())/len(checks) if checks else 0.,'complete':shape and all(checks.values()),'limit':'Mechanical source/region binding only; text meaning, stamp-slot and crossing interpretation require the semantic Judge.'}
