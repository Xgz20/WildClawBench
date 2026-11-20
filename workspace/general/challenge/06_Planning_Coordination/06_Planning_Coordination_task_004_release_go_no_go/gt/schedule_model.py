"""Arithmetic only: no cached candidate result becomes source truth."""
def calculate(tasks,durations,costs,budget_cap):
 pending=set(tasks);order=[]
 while pending:
  ready=sorted(k for k in pending if all(p in order for p in tasks[k]['predecessors']))
  if not ready:raise ValueError('trusted source DAG cycle')
  order.extend(ready);pending-=set(ready)
 out={};succ={k:[s for s,v in tasks.items() if k in v['predecessors']] for k in tasks}
 for k in order:
  duration=durations[k];es=max([out[p]['ef'] for p in tasks[k]['predecessors']] or [0]);out[k]={'duration':duration,'es':es,'ef':es+duration}
 finish=max(v['ef'] for v in out.values())
 for k in order[::-1]:
  lf=min([out[s]['ls'] for s in succ[k]] or [finish]);v=out[k];v.update(lf=lf,ls=lf-v['duration']);v['total_float']=v['ls']-v['es'];v['critical']=int(abs(v['total_float'])<1e-9)
 extended={k:r['selected']*r['fixed_cost'] for k,r in costs.items()};total=sum(extended.values())
 return {'cpm':out,'costs':extended,'budget':{'budget_cap':budget_cap,'total_cost':total,'budget_remaining':budget_cap-total},'cpm_duration':finish}
