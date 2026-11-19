"""Independent arithmetic over declared primitive activity/weekly allocations.

The authoritative source facts are checked separately. Candidate cached totals
never create ground truth; this model only states how primitive edits propagate.
"""
def calculate(oracle,activities,allocations):
 weeks=oracle['weeks'];weekmap={w['week_id']:w for w in weeks};order={w['week_id']:i for i,w in enumerate(weeks,1)};months=[r['month'] for r in oracle['months']];usage={w['week_id']:0. for w in weeks};byactivity={k:[] for k in activities};invalid=[]
 for row in allocations:
  w,k,h=row['week_id'],row['activity_id'],row['hours']
  if w not in usage or k not in activities or h is None:invalid.append(row);continue
  usage[w]+=h;byactivity[k].append((order[w],h))
 activity_values={};monthly_fees={m:0. for m in months}
 for key,a in activities.items():
  rows=byactivity[key];positive=[i for i,h in rows if h>0];first=min(positive) if positive else None;last=max(positive) if positive else None;fee=a['fee'];charge=weeks[first-1]['month'] if first else None
  activity_values[key]={'first_week':first,'last_week':last,'planned_hours':sum(h for _,h in rows),'fee':fee,'charge_month':charge}
  if charge is not None and fee is not None:monthly_fees[charge]+=fee
 weekly={w['week_id']:{'month':w['month'],'hours_cap':w['hours_cap'],'planned_hours':usage[w['week_id']],'remaining_hours':w['hours_cap']-usage[w['week_id']],'overload_hours':max(0,usage[w['week_id']]-w['hours_cap'])} for w in weeks}
 monthly={};cumulative=0.;years={}
 for m in months:
  cap=sum(w['hours_cap'] for w in weeks if w['month']==m);hours=sum(usage[w['week_id']] for w in weeks if w['month']==m);fee=monthly_fees[m];cumulative+=fee;year=m[:4];years[year]=years.get(year,0.)+fee
  monthly[m]={'hours_cap':cap,'planned_hours':hours,'remaining_hours':cap-hours,'fee':fee,'year_fee':years[year],'cumulative_fee':cumulative,'total_fee_remaining':oracle['total_fee_cap']-cumulative}
 return {'activities':activity_values,'weekly':weekly,'monthly':monthly,'annual_fees':years,'total_fee':cumulative,'total_hours':sum(usage.values()),'invalid_rows':invalid}
