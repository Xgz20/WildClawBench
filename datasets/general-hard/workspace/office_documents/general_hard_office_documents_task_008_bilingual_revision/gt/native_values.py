"""Bounded observable literal values in Vietnamese text, not semantic translation truth."""
from decimal import Decimal,InvalidOperation
from datetime import date
import re,unicodedata

def norm(value):return re.sub(r'\s+',' ',unicodedata.normalize('NFKC',str(value or '')).casefold()).strip()
def decimal_text(text):
    text=text.strip().replace(' ','')
    if re.fullmatch(r'[+-]?\d{1,3}(?:\.\d{3})+',text):text=text.replace('.','')
    elif re.fullmatch(r'[+-]?\d{1,3}(?:,\d{3})+',text):text=text.replace(',','')
    elif ',' in text and '.' in text:
        if text.rfind('.')>text.rfind(','):text=text.replace(',','')
        else:text=text.replace('.','').replace(',','.')
    elif ',' in text:text=text.replace(',','.')
    return Decimal(text)
def currencies(text):
    aliases={'rmb':'CNY','cny':'CNY','nhân dân tệ':'CNY','人民币':'CNY','vnd':'VND','vnđ':'VND','usd':'USD','eur':'EUR'}
    return {aliases[value] for value in re.findall(r'\b(?:cny|rmb|vnd|vnđ|usd|eur|nhân dân tệ)\b|人民币',norm(text))}
def money(text):
    result=[]
    pattern=r'(?<![\w])([+-]?\d(?:[\d., ]*\d)?|tám mươi nghìn|tám mươi ngàn)\s*(?:cny|rmb|nhân dân tệ|人民币)\b'
    for token in re.findall(pattern,norm(text)):
        if token in ('tám mươi nghìn','tám mươi ngàn'):result.append(Decimal(80000))
        else:
            try:result.append(decimal_text(token))
            except InvalidOperation:result.append('invalid_amount')
    return result
def dates(text):
    result=[];text=norm(text)
    patterns=[(r'(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)',(0,1,2)),
              (r'(?<!\d)(\d{1,2})/(\d{1,2})/(\d{4})(?!\d)',(2,1,0)),
              (r'ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})',(2,1,0))]
    for pattern,order in patterns:
        for values in re.findall(pattern,text):
            try:result.append(date(*(int(values[i]) for i in order)).isoformat())
            except ValueError:result.append('invalid_date')
    return result
def numeric_words(text):
    text=norm(text)
    for word,value in [('mười bảy','17'),('mười bốn','14'),('hai mươi','20'),('bốn','4'),('hai','2'),('ba','3')]:
        text=re.sub(r'(?<!\w)'+word+r'(?!\w)',value,text)
    return text
def quantities(text,unit):
    return {Decimal(value) for value in re.findall(r'(?<!\w)(\d+)\s*(?:\(\s*\d+\s*\)\s*)?(?:'+unit+r')(?!\w)',numeric_words(text))}
def evaluate(sentences,truth):
    raw={identity:norm(item.get('text','')) for identity,item in sentences.items()}
    facts={row['sentence_id']:row['facts'] for row in truth['sentences']};checks={};observed={}
    value=money(raw.get('S03',''));checks['S03']={'amount':set(value)=={Decimal(str(facts['S03']['amount']))},'currency':currencies(raw.get('S03',''))=={'CNY'}}
    observed['S03']={'amounts':[str(v) for v in value],'currencies':sorted(currencies(raw.get('S03','')))}
    value=dates(raw.get('S04',''));checks['S04']={'dates':set(value)=={facts['S04']['start_date'],facts['S04']['end_date']}};observed['S04']={'dates':value}
    value=quantities(raw.get('S05',''),r'giờ làm việc');checks['S05']={'work_hours':value=={Decimal(4)}};observed['S05']={'work_hours':sorted(str(v) for v in value)}
    value=quantities(raw.get('S06',''),r'ngày làm việc');checks['S06']={'work_days':value=={Decimal(2)}};observed['S06']={'work_days':sorted(str(v) for v in value)}
    value={int(v) for v in re.findall(r'(?<!\w)\d+(?!\w)',numeric_words(raw.get('S11','')))}
    checks['S11']={'counts':value=={facts['S11'][key] for key in ('total','pending','completed')}};observed['S11']={'numbers':sorted(value)}
    checks['S13']={'backup_name':bool(re.search(r'(?<!\w)linh(?!\w)',raw.get('S13','')))}
    checks['S14']={'currency':currencies(raw.get('S14',''))=={'CNY'}}
    checks['S15']={'mentioned_count':quantities(raw.get('S15',''),r'(?:mục|phụ lục)')=={Decimal(2)}}
    return checks,observed
