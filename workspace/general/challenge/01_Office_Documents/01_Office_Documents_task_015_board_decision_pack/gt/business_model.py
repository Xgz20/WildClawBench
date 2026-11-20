"""Independent source-event model; never read a candidate's predicted answer as truth."""
from fractions import Fraction
def cash_model(truth,initial=None,floor=None):
    src=truth['cash'];initial=src['initial_cny'] if initial is None else initial;floor=src['floor_cny'] if floor is None else floor
    out={}
    for case,payments in src['payments'].items():
        events=src['base_events']+payments
        days=sorted({'2026-10-01',*[e['date'] for e in events]})
        rows=[{'date':day,'balance_cny':float(Fraction(initial)+sum(Fraction(e['amount_cny']) for e in events if e['date']<=day))} for day in days]
        minimum=min(r['balance_cny'] for r in rows);viol=[r for r in rows if r['balance_cny']<floor]
        out[case]={'rows':rows,'minimum_cny':minimum,'minimum_date':[r['date'] for r in rows if r['balance_cny']==minimum],
                  'end_cash_cny':rows[-1]['balance_cny'],'first_violation':viol[0]['date'] if viol else None,
                  'maximum_floor_gap_cny':max(0,floor-minimum),'cash_feasible':not viol}
    return out
