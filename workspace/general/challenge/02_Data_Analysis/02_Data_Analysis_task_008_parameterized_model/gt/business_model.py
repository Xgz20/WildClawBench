"""Source-first monthly Decimal model; no candidate workbook is read."""
from collections import defaultdict
from decimal import Decimal as D,ROUND_HALF_UP
ZERO=D(0)
def money(value):return D(value).quantize(D('.01'),rounding=ROUND_HALF_UP)
def curve(amount,p):
    t1=D(p['tier1_limit']);t2=D(p['tier2_limit']);amount=max(amount,ZERO)
    return (min(amount,t1)*D(p['rate1'])+max(min(amount,t2)-t1,ZERO)*D(p['rate2'])+max(amount-t2,ZERO)*D(p['rate3'])).quantize(D('.000001'))
def capped(amount,p):return min(money(curve(amount,p)),D(p['commission_cap']))
def solve(facts):
    months=facts['months'];employees={r['employee_id']:r for r in facts['employees']};attendance={(r['employee_id'],r['month']):r for r in facts['attendance']};sale_lookup={r['sale_id']:r for r in facts['sales']};gross=defaultdict(lambda:ZERO);audit=[];valid=[]
    assert len(employees)==12 and len(attendance)==36 and len(sale_lookup)==len(facts['sales'])
    for row in facts['sales']:
        decision='outside_period' if row['month'] not in months else 'not_posted' if row['status']!='posted' else 'posted'
        audit.append({'source':'sales','record_id':row['sale_id'],'decision':decision})
        if decision=='posted':assert row['employee_id'] in employees and D(row['amount'])>=0;gross[row['employee_id'],row['month']]+=D(row['amount'])
    capacity=defaultdict(lambda:ZERO)
    for row in facts['refunds']:
        decision='outside_period' if row['refund_month'] not in months else 'not_posted' if row['status']!='posted' else 'posted'
        audit.append({'source':'refunds','record_id':row['refund_id'],'decision':decision})
        if decision!='posted':continue
        sale=sale_lookup[row['original_sale_id']];assert sale['employee_id']==row['employee_id'] and sale['status']=='posted' and sale['month'] in months and sale['month']<row['refund_month'] and D(row['amount'])>0
        valid.append({**row,'original_month':sale['month']});capacity[sale['sale_id']]+=D(row['amount'])
    assert all(value<=D(sale_lookup[identity]['amount']) for identity,value in capacity.items())
    params={(r['scenario_id'],r['month']):r for r in facts['parameters']};scenarios={}
    for sid in [1,2,3]:
        retro=[];payroll=[];totals=[]
        for emp in employees:
            for origin in months:
                p=params[sid,origin];original=gross[emp,origin]
                for current in months:
                    if current<origin:continue
                    before=sum((D(r['amount']) for r in valid if r['employee_id']==emp and r['original_month']==origin and r['refund_month']<current),ZERO)
                    through=sum((D(r['amount']) for r in valid if r['employee_id']==emp and r['original_month']==origin and r['refund_month']<=current),ZERO)
                    eligible_before=original-before;eligible_after=original-through;cap_before=capped(eligible_before,p);cap_after=capped(eligible_after,p)
                    retro.append({'employee_id':emp,'original_month':origin,'pay_month':current,'original_gross':original,'refund_before':before,'refund_through':through,'eligible_before':eligible_before,'eligible_after':eligible_after,'commission_before':cap_before,'commission_after':cap_after,'current_clawback':cap_before-cap_after if current>origin else ZERO})
        for emp,employee in employees.items():
            for month in months:
                row=attendance[emp,month];p=params[sid,month];fraction=D(row['paid_days'])/D(row['standard_days']);base=money(D(employee['base_monthly_salary'])*D(p['salary_multiplier'])*fraction);allowance=money(D(p['full_allowance'])*fraction);raw=curve(gross[emp,month],p);earned=capped(gross[emp,month],p)
                clawback=sum((r['current_clawback'] for r in retro if r['employee_id']==emp and r['pay_month']==month),ZERO);net=earned-clawback;pay=base+allowance+net
                payroll.append({'employee_id':emp,'month':month,'paid_fraction':fraction,'gross_sales':gross[emp,month],'commission_raw':raw,'base_pay':base,'allowance':allowance,'earned_commission':earned,'clawback':clawback,'net_commission':net,'total_pay':pay})
        for month in months:
            totals.append({'scenario_id':sid,'scenario_name':params[sid,month]['scenario_name'],'month':month,**{key:sum((r[key] for r in payroll if r['month']==month),ZERO) for key in ['base_pay','allowance','earned_commission','clawback','net_commission','total_pay']}})
        scenarios[str(sid)]={'payroll':payroll,'retro':retro,'months':totals}
    compare=[]
    for sid in [1,2,3]:
        for row,base in zip(scenarios[str(sid)]['months'],scenarios['1']['months']):compare.append({**row,**{'delta_'+key:row[key]-base[key] for key in ['base_pay','allowance','earned_commission','clawback','net_commission','total_pay']}})
    assert all(r['current_clawback']>=0 for s in scenarios.values() for r in s['retro'])
    assert next(r for r in scenarios['1']['payroll'] if r['employee_id']=='E12' and r['month']=='2026-09')['total_pay']<0
    return {'scenarios':scenarios,'comparisons':compare,'source_audit':audit}
