"""Native semantic grids and stable identities; no author sheet names or coordinates."""
from pathlib import Path
from collections import defaultdict
from decimal import Decimal,InvalidOperation
import csv,io,re,runpy,unicodedata
HERE=Path(__file__).resolve().parent
XLSX=runpy.run_path(str(HERE/'xlsx_observations.py'));WORD=runpy.run_path(str(HERE/'word_model.py'))
CandidateError=XLSX['CandidateError']
def canon(v):return re.sub(r'[\s_()（）/、:：%％-]','',unicodedata.normalize('NFKC',str(v if v is not None else ''))).casefold()
def norm(v):return str(v if v is not None else '').strip().upper()
def blank(v):return v is None or isinstance(v,str) and not v.strip()
def number(v,unit=False):
    if isinstance(v,bool) or blank(v):return None
    text=unicodedata.normalize('NFKC',str(v)).strip().replace('−','-')
    if unit:text=re.sub(r'(?:人|条)$','',text).strip()
    if re.fullmatch(r'[+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?',text):text=text.replace(',','')
    try:n=Decimal(text)
    except InvalidOperation:return None
    return n if n.is_finite() else None
def equal(v,w,tolerance=0,word=False,percent_header=False):
    if w is None:return isinstance(v,str) and canon(v) in {'na','不适用'}
    if isinstance(w,(int,float,Decimal)):
        text=unicodedata.normalize('NFKC',str(v)).strip() if v is not None else ''
        percent=word and ('%' in text or percent_header)
        n=number(text.replace('%','') if percent else v,unit=word)
        if n is None:return False
        if percent:n/=100
        return abs(n-Decimal(str(w)))<=Decimal(str(tolerance))
    return v==w
def bit(v,w):
    if isinstance(v,bool):return int(v)==w
    return equal(v,w)
def raw_equal(v,w,key):
    if w=='':return blank(v)
    if key in {'q1_use','q2_sat','q4_recommend'} and isinstance(v,(int,float)) and not isinstance(v,bool):return equal(v,int(w)) if re.fullmatch(r'-?\d+',w) else False
    return v==w
def candidate_path(root,name):
    p=Path(root)/'results'/name
    if p.parent.is_symlink() or not p.is_file() or p.is_symlink() or p.stat().st_size>5242880 or p.resolve().parent!=p.parent.resolve():raise CandidateError('missing, unsafe or oversized '+name)
    return p
def read_word(path):
    try:return WORD['read_document'](path)
    except WORD['CandidateWordError'] as e:raise CandidateError(str(e)) from e
def csv_rows(path,fields):
    try:text=Path(path).read_text(encoding='utf-8-sig')
    except UnicodeDecodeError as e:raise CandidateError('exclusions CSV must be UTF-8') from e
    try:
        reader=csv.DictReader(io.StringIO(text,newline=''),strict=True)
        if not reader.fieldnames or len(reader.fieldnames)!=len(set(reader.fieldnames)) or not set(fields)<=set(reader.fieldnames):raise CandidateError('exclusions CSV headers mismatch')
        rows=list(reader)
    except csv.Error as e:raise CandidateError('invalid exclusions CSV') from e
    if len(rows)>10000 or any(None in r or any(r.get(k) is None for k in fields) for r in rows):raise CandidateError('invalid exclusions rows')
    return [{k:r[k] for k in fields} for r in rows]
def grids_word(model):
    grids=[]
    for table in model['tables']:
        if table['parent_cell'] is not None:continue
        cells={}
        for anchor in table['anchors']:
            if anchor.get('invalid_merge'):raise CandidateError('invalid Word merged-cell relation')
            texts=[t for t in anchor['text_parts'] if t.strip()];unique=list(dict.fromkeys(texts));value=unique[0] if len(unique)==1 else '\n'.join(unique)
            for row in range(anchor['row'],anchor['row']+anchor['rowspan']):
                for col in range(anchor['column'],anchor['column']+anchor['colspan']):cells[row,col]={'value':value,'row':row,'col':col,'visible':True,'locator':anchor['locator']}
        grids.append({'name':table['locator'],'cells':cells,'state':'visible'})
    return grids
def discover(grids,aliases,required,id_field=None,id_test=None,forbidden=()):
    lookup={canon(a):key for key,values in aliases.items() for a in values};out=[]
    for grid in grids:
        rows=defaultdict(dict)
        for (r,c),cell in grid['cells'].items():rows[r][c]=cell
        headers=[]
        for r,values in sorted(rows.items()):
            found=defaultdict(list)
            for c,cell in values.items():
                key=lookup.get(canon(cell['value']))
                if key and not cell.get('merged_from'):found[key].append(c)
            if not set(required)<=set(found) or set(forbidden)&set(found) or any(len(found[k])!=1 for k in required):continue
            cols={k:v[0] for k,v in found.items() if len(v)==1};headers.append((r,cols))
        for i,(r,cols) in enumerate(headers):
            end=headers[i+1][0] if i+1<len(headers) else 50001;records=[]
            header_visible=all(grid['cells'][r,cols[k]]['visible'] for k in required)
            for rn,row in sorted(rows.items()):
                if not r<rn<end:continue
                values={k:row.get(c,{}).get('value') for k,c in cols.items()}
                if id_field is not None and id_test is not None and not id_test(values.get(id_field)):continue
                if all(blank(v) for v in values.values()):continue
                locations={k:{'sheet':grid['name'],'row':rn,'col':c,'cell':row.get(c,{}),'header':grid['cells'][r,c]['value']} for k,c in cols.items()}
                visible=header_visible and all(row.get(cols[k],{'visible':True})['visible'] for k in required)
                records.append({**values,'_locations':locations,'_sheet':grid['name'],'_row':rn,'_visible':visible})
            out.append({'sheet':grid['name'],'header_row':r,'columns':cols,'rows':records,'header_visible':header_visible})
    return out
def flatten(groups):return [r for group in groups for r in group['rows']]
def weight_groups(book,aliases,keys):
    groups=discover(book,aliases,['stratum','weight'],id_field='stratum',id_test=lambda v:norm(v) in keys,forbidden=['record_id','metric_id'])
    # A transposed two-field source is still the same four business inputs.
    for grid in book:
        rows=defaultdict(dict)
        for (r,c),cell in grid['cells'].items():rows[r][c]=cell
        for r,values in rows.items():
            for label_col,label in values.items():
                if canon(label['value']) not in {canon(v) for v in aliases['stratum']}:continue
                columns={norm(cell['value']):c for c,cell in values.items() if norm(cell['value']) in keys}
                if set(columns)!=set(keys):continue
                for rr in range(r+1,min(r+11,50001)):
                    if canon(rows.get(rr,{}).get(label_col,{}).get('value')) not in {canon(v) for v in aliases['weight']}:continue
                    records=[]
                    for key,c in columns.items():
                        cell=rows[rr].get(c,{})
                        records.append({'stratum':key,'weight':cell.get('value'),'_visible':bool(label['visible'] and cell.get('visible',True)),'_locations':{'weight':{'sheet':grid['name'],'row':rr,'col':c,'cell':cell,'header':'weight'}},'_sheet':grid['name'],'_row':rr})
                    groups.append({'sheet':grid['name'],'header_row':r,'rows':records,'transposed':True})
    return groups
def models(book,contract,expected):
    known={r['record_id'] for r in expected['cleaned']};kept={r['record_id']:r for r in expected['cleaned'] if r['keep']};flags=list(next(iter(kept.values()))['flags']);rows=[]
    # In a combined source/build table q2_sat is the original 1..5 answer;
    # its derived binary marker must use a disambiguated alias.
    marker_book=[];raw_lookup={canon(a):k for k,values in contract['raw_aliases'].items() for a in values}
    for grid in book:
        cells=dict(grid['cells']);headers=defaultdict(dict)
        for (r,c),cell in cells.items():
            field=raw_lookup.get(canon(cell['value']))
            if field:headers[r][field]=c
        for r,fields in headers.items():
            if {'record_id','q1_use','q2_sat','q3_barriers','q4_recommend','keep'}<=set(fields):
                pos=(r,fields['q2_sat']);cells[pos]={**cells[pos],'value':'__raw_q2_sat_answer__'}
        marker_book.append({**grid,'cells':cells})
    wide=discover(marker_book,contract['model_aliases'],['record_id','respondent_id','stratum','weight',*flags],id_field='record_id',id_test=lambda v:bool(re.fullmatch(r'S\d+',norm(v))))
    for row in flatten(wide):
        rid=norm(row['record_id'])
        if rid in known and rid not in kept:continue
        rows.append({'record_id':rid,'respondent_id':row['respondent_id'],'stratum':row['stratum'],'weight':row['weight'],'flags':{k:row[k] for k in flags},'locations':{k:row['_locations'][k] for k in flags},'visible':row['_visible'],'weight_location':row['_locations']['weight']})
    long=discover(book,contract['long_model_aliases'],['record_id','respondent_id','stratum','weight','marker_key','marker_value'],id_field='record_id',id_test=lambda v:bool(re.fullmatch(r'S\d+',norm(v))))
    keymap={canon(a):k for k in flags for a in contract['model_aliases'][k]};by_id=defaultdict(list)
    for row in flatten(long):
        rid=norm(row['record_id'])
        if rid in known and rid not in kept:continue
        by_id[rid].append(row)
    for rid,records in by_id.items():
        fields=defaultdict(list)
        for row in records:fields[keymap.get(canon(row['marker_key']),'UNKNOWN')].append(row)
        if set(fields)!=set(flags) or any(len(v)!=1 for v in fields.values()):
            rows.append({'record_id':rid,'flags':{},'locations':{},'visible':False,'weight':None,'stratum':None,'respondent_id':None,'weight_location':None});continue
        first=records[0];consistent=all(norm(r['respondent_id'])==norm(first['respondent_id']) and norm(r['stratum'])==norm(first['stratum']) and equal(r['weight'],number(first['weight'])) for r in records)
        rows.append({'record_id':rid,'respondent_id':first['respondent_id'],'stratum':first['stratum'],'weight':first['weight'],'flags':{k:v[0]['marker_value'] for k,v in fields.items()},'locations':{k:v[0]['_locations']['marker_value'] for k,v in fields.items()},'weight_location':first['_locations']['weight'],'visible':consistent and all(r['_visible'] for r in records)})
    return rows
