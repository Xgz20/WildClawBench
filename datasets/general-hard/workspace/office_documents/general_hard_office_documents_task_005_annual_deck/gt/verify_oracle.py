"""Independent SQL COALESCE/date filtering and Fraction math on actual XLSX."""
from pathlib import Path
from fractions import Fraction as F
from datetime import date,datetime
import hashlib,json,sqlite3
from openpyxl import load_workbook

import argparse
parser=argparse.ArgumentParser()
parser.add_argument('--workbook',required=True,type=Path)
parser.add_argument('--expected',required=True,type=Path)
parser.add_argument('--output',required=True,type=Path)
args=parser.parse_args()
book=load_workbook(args.workbook,data_only=True)
assert book.sheetnames==['财务月度','运营月度','应收明细']
database=sqlite3.connect(':memory:')
database.execute('create table f(month,prior,raw,correction,ru,cost,cc,cu,budget,bu,note)')
database.execute('create table o(month,deliveries,on_time,tickets,resolved,positive,valid,cost,unit,note)')
database.execute('create table a(invoice,due,amount,paid,unit,note)')
finance=list(book['财务月度'].iter_rows(min_row=6,max_row=17,max_col=11,values_only=True))
operations=list(book['运营月度'].iter_rows(min_row=6,max_row=17,max_col=10,values_only=True))
receivables=[tuple([row[0],row[1].date().isoformat() if isinstance(row[1],datetime) else row[1].isoformat(),*row[2:]])
             for row in book['应收明细'].iter_rows(min_row=6,max_row=23,max_col=6,values_only=True)]
assert book['财务月度']['D8'].value==0 and book['财务月度']['D6'].value is None
cutoff=book['应收明细']['B2'].value.date().isoformat()
assert cutoff=='2026-12-31'
database.executemany('insert into f values(?,?,?,?,?,?,?,?,?,?,?)',finance)
database.executemany('insert into o values(?,?,?,?,?,?,?,?,?,?)',operations)
database.executemany('insert into a values(?,?,?,?,?,?)',receivables)
scale={'元':F(1,10000),'千元':F(1,10),'万元':F(1)}
def money(value,unit):return F(str(value))*scale[unit]
selected=list(database.execute('select month,prior,coalesce(correction,raw),ru,coalesce(cc,cost),cu,budget,bu from f order by month'))
current=sum((money(row[2],row[3]) for row in selected),F(0))
old=sum((money(row[1],row[3]) for row in selected),F(0))
expense=sum((money(row[4],row[5]) for row in selected),F(0))
budget=sum((money(row[6],row[7]) for row in selected),F(0))
fourth=sum((money(row[2],row[3]) for row in selected if row[0]>='2026-10'),F(0))
deliveries,on_time,tickets,resolved,positive,valid=database.execute('select sum(deliveries),sum(on_time),sum(tickets),sum(resolved),sum(positive),sum(valid) from o').fetchone()
eligible=list(database.execute('select amount,paid,unit from a where date(due)<=date(?)',(cutoff,)))
due=sum((money(row[0],row[2]) for row in eligible),F(0));paid=sum((money(row[1],row[2]) for row in eligible),F(0))
late=list(database.execute("select amount,paid,unit from a where date(due)<date(?,'-30 days')",(cutoff,)))
over30=sum((money(row[0],row[2])-money(row[1],row[2]) for row in late),F(0))
service=list(database.execute("select cost,unit,tickets from o where month between '2026-10' and '2026-12'"))
servicecost=sum((money(row[0],row[1])*10000 for row in service),F(0));servicetickets=sum(row[2] for row in service)
values=[current,(current/old-1)*100,current/budget*100,current-expense,(current-expense)/current*100,fourth/current*100,
        F(on_time,deliveries)*100,F(resolved,tickets)*100,F(positive,valid)*100,paid/due*100,over30,servicecost/servicetickets]
def round_two(value):
    numerator=abs(value.numerator)*100;whole,remainder=divmod(numerator,value.denominator)
    whole+=int(remainder*2>=value.denominator)
    return ('-' if value<0 else '')+str(whole//100)+'.'+str(whole%100).zfill(2)
truth=json.loads((args.expected).read_text(encoding='utf-8'))
comparisons=[]
for item,value in zip(truth['kpis'],values):
    actual=round_two(value);assert actual==item['value'],(item['kpi_id'],actual,item['value'])
    comparisons.append({'kpi_id':item['kpi_id'],'value':actual,'exact_fraction':str(value),'matches':True})
quarter_checks=[]
for index,expected in enumerate(truth['quarters']):
    lower,upper=f'{index*3+1:02d}',f'{index*3+3:02d}'
    selected_quarter=list(database.execute('select coalesce(correction,raw),ru,coalesce(cc,cost),cu from f where substr(month,6,2) between ? and ?',(lower,upper)))
    qr=sum((money(x[0],x[1]) for x in selected_quarter),F(0));qc=sum((money(x[2],x[3]) for x in selected_quarter),F(0))
    qt,qo,qk,qc24=database.execute('select sum(deliveries),sum(on_time),sum(tickets),sum(resolved) from o where substr(month,6,2) between ? and ?',(lower,upper)).fetchone()
    assert qr==F(expected['revenue']) and qc==F(expected['cost'])
    assert abs(float(F(qo,qt))-float(expected['on_time_rate']))<1e-12
    assert abs(float(F(qc24,qk))-float(expected['resolved_rate']))<1e-12
    quarter_checks.append({'quarter':expected['quarter'],'revenue':str(qr),'cost':str(qc),'on_time_rate':str(F(qo,qt)),'resolved_rate':str(F(qc24,qk)),'matches':True})
aging_sql={key:F(0) for key in truth['aging_wanyuan']}
query="""select amount,paid,unit,case when date(due)>date(?) then '未到期'
when date(due)>=date(?,'-30 days') then '0至30天'
when date(due)>=date(?,'-60 days') then '31至60天' else '大于60天' end from a"""
for amount,paid_value,unit,bucket in database.execute(query,(cutoff,cutoff,cutoff)):
    aging_sql[bucket]+=money(amount,unit)-money(paid_value,unit)
assert all(value==F(truth['aging_wanyuan'][key]) for key,value in aging_sql.items())
report={'schema_version':'h005-physical-workbook-verification/v1','status':'PASS','workbook_sha256':hashlib.sha256((args.workbook).read_bytes()).hexdigest(),
        'zero_correction_preserved':True,'financial_months':len(finance),'operating_months':len(operations),'invoices':len(receivables),'eligible_invoices':len(eligible),
        'comparisons':comparisons,'quarter_checks':quarter_checks,'aging_checks':{key:str(value) for key,value in aging_sql.items()},
        'independence':'SQL COALESCE/date predicates and Fraction arithmetic over actual XLSX; compared with pre-reference Decimal oracle only at the end.',
        'limit':'Independent computation, not independent expert annotation or semantic Judge.'}
(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':'PASS','kpis':len(comparisons),'eligible_invoices':len(eligible)}))
