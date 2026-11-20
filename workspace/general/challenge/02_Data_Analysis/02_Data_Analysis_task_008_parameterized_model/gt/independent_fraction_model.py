"""Independent cent/rational evaluation, refund timeline deltas and tier bands."""
from collections import defaultdict
from fractions import Fraction as Q
def cents(value):return int(Q(str(value))*100)
def round_unit(value):
    if value<0:return -round_unit(-value)
    return (2*value.numerator+value.denominator)//(2*value.denominator)
def compute(facts):
    period=set(facts['months']);active_sales=[r for r in facts['sales'] if r['month'] in period and r['status']=='posted'];sales={r['sale_id']:r for r in active_sales};groups=defaultdict(int);refund_month=defaultdict(int);audits=[]
    for row in active_sales:groups[row['employee_id'],row['month']]+=cents(row['amount'])
    for row in facts['refunds']:
        if row['refund_month'] in period and row['status']=='posted':
            original=sales[row['original_sale_id']];refund_month[row['employee_id'],original['month'],row['refund_month']]+=cents(row['amount'])
    for source,rows,identity,mkey in [('sales',facts['sales'],'sale_id','month'),('refunds',facts['refunds'],'refund_id','refund_month')]:
        for row in rows:audits.append({'source':source,'record_id':row[identity],'decision':'outside_period' if row[mkey] not in period else 'not_posted' if row['status']!='posted' else 'posted'})
    def raw_tiers(value,p):
        bounds=[0,cents(p['tier1_limit']),cents(p['tier2_limit']),max(value,cents(p['tier2_limit']))];answer=Q(0)
        for low,high,key in zip(bounds,bounds[1:],['rate1','rate2','rate3']):answer+=max(0,min(value,high)-low)*Q(p[key])
        return answer
    def rounded_cap(value,p):return min(round_unit(raw_tiers(max(value,0),p)),cents(p['commission_cap']))
    output={};months=sorted(period);employees=sorted(facts['employees'],key=lambda x:x['employee_id'])
    for sid in [1,2,3]:
        parameters={p['month']:p for p in facts['parameters'] if p['scenario_id']==sid};schedules=[];by_pay_month=defaultdict(int);records=[]
        for emp in employees:
            eid=emp['employee_id']
            for origin in months:
                p=parameters[origin];g=groups[eid,origin];previous_refund=0;previous_commission=rounded_cap(g,p)
                for current in months:
                    if current<origin:continue
                    this_refund=refund_month[eid,origin,current];after_refund=previous_refund+this_refund;after_commission=rounded_cap(g-after_refund,p);delta=previous_commission-after_commission if current!=origin else 0
                    schedules.append({'employee_id':eid,'original_month':origin,'pay_month':current,'original_gross':Q(g,100),'refund_before':Q(previous_refund,100),'refund_through':Q(after_refund,100),'eligible_before':Q(g-previous_refund,100),'eligible_after':Q(g-after_refund,100),'commission_before':Q(previous_commission,100),'commission_after':Q(after_commission,100),'current_clawback':Q(delta,100)})
                    by_pay_month[eid,current]+=delta;previous_refund=after_refund;previous_commission=after_commission
        emp_map={r['employee_id']:r for r in employees}
        for emp in employees:
            eid=emp['employee_id']
            for month in months:
                attend=next(r for r in facts['attendance'] if r['employee_id']==eid and r['month']==month);p=parameters[month];fraction=Q(attend['paid_days'])/Q(attend['standard_days']);base=round_unit(cents(emp['base_monthly_salary'])*Q(p['salary_multiplier'])*fraction);allowance=round_unit(cents(p['full_allowance'])*fraction);g=groups[eid,month];raw=raw_tiers(g,p);earned=rounded_cap(g,p);claw=by_pay_month[eid,month];net=earned-claw;total=base+allowance+net
                records.append({'employee_id':eid,'month':month,'paid_fraction':fraction,'gross_sales':Q(g,100),'commission_raw':raw/100,'base_pay':Q(base,100),'allowance':Q(allowance,100),'earned_commission':Q(earned,100),'clawback':Q(claw,100),'net_commission':Q(net,100),'total_pay':Q(total,100)})
        totals=[]
        for month in months:totals.append({'scenario_id':sid,'scenario_name':parameters[month]['scenario_name'],'month':month,**{key:sum((r[key] for r in records if r['month']==month),Q(0)) for key in ['base_pay','allowance','earned_commission','clawback','net_commission','total_pay']}})
        output[str(sid)]={'payroll':records,'retro':schedules,'months':totals}
    comparisons=[]
    for sid in [1,2,3]:
        for row,base in zip(output[str(sid)]['months'],output['1']['months']):comparisons.append({**row,**{'delta_'+key:row[key]-base[key] for key in ['base_pay','allowance','earned_commission','clawback','net_commission','total_pay']}})
    return {'scenarios':output,'comparisons':comparisons,'source_audit':audits}
